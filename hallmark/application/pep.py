"""The Policy Enforcement Point.

Every consequential call arrives here first. The sequence is always the same: resolve
handles to labeled values, compute facts from company records, ask Cedar, and only then
act. A denial is re-asked once with `humanApproved` set, which is how an approvable
denial is told apart from one no human can lift.

Anything that throws becomes a denial. Failing closed is the only safe direction for a
component whose job is to stand between a model and a bank transfer.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hallmark.application.cedar_request_builder import (
    build_email_request,
    build_payment_request,
)
from hallmark.application.fact_checkers import (
    EmailFacts,
    PaymentFacts,
    compute_email_facts,
    compute_payment_facts,
)
from hallmark.domain.labels import Confidentiality
from hallmark.domain.lineage import EdgeKind, LineageEdge
from hallmark.domain.mandate import Mandate
from hallmark.domain.tools import ReasonCode, ToolOutcome, ToolResult
from hallmark.domain.values import Labeled
from hallmark.ports.authorizer import Authorizer, Decision
from hallmark.ports.repositories import (
    Company,
    LedgerEntry,
    LedgerRepository,
    VendorRepository,
)
from hallmark.ports.stores import (
    Clock,
    DecisionRecord,
    DecisionStore,
    IdGenerator,
    LineageStore,
    ValueStore,
)

#: Which policy, when it denies, maps to which reason the planner is told.
POLICY_REASONS: dict[str, ReasonCode] = {
    "pay-account-must-be-master": ReasonCode.ACCOUNT_NOT_FROM_VENDOR_MASTER,
    "pay-vendor-match-required": ReasonCode.VENDOR_NOT_VERIFIED,
    "pay-no-duplicates": ReasonCode.DUPLICATE_INVOICE,
    "pay-above-auto-limit-needs-human": ReasonCode.ABOVE_AUTO_APPROVE_LIMIT,
    "email-recipient-must-be-trusted": ReasonCode.RECIPIENT_NOT_TRUSTED,
    "email-confidential-internal-only": ReasonCode.CONFIDENTIAL_TO_EXTERNAL,
}

#: Several forbids can fire at once, and the engine does not promise an order. Report the
#: most fundamental reason rather than whichever happened to be listed first: the
#: guarantees no approver can lift come before the ones that merely need a signature, so
#: an operator reading the result learns the thing that actually matters.
REASON_PRECEDENCE: tuple[str, ...] = (
    "pay-account-must-be-master",
    "email-confidential-internal-only",
    "pay-no-duplicates",
    "email-recipient-must-be-trusted",
    "pay-vendor-match-required",
    "pay-above-auto-limit-needs-human",
)

SUGGESTED_AFTER_PAYMENT_DENIAL: tuple[str, ...] = (
    "open_bank_change_review",
    "flag_for_review",
)


@dataclass
class RunContext:
    """Everything an enforcement decision needs to know about the run it belongs to."""

    run_id: str
    user_id: str
    mandate: Mandate


class PolicyEnforcementPoint:
    """Wraps consequential tools with resolution, fact checks and authorization."""

    def __init__(
        self,
        authorizer: Authorizer,
        values: ValueStore,
        lineage: LineageStore,
        decisions: DecisionStore,
        vendors: VendorRepository,
        ledger: LedgerRepository,
        company: Company,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._authorizer = authorizer
        self._values = values
        self._lineage = lineage
        self._decisions = decisions
        self._vendors = vendors
        self._ledger = ledger
        self._company = company
        self._ids = ids
        self._clock = clock

    # ---------------------------------------------------------------- helpers

    def _resolve(self, run_id: str, handle: Any) -> Labeled[Any]:
        if not isinstance(handle, str) or not handle.startswith("h_"):
            raise _ArgumentNotAHandle
        value = self._values.get(run_id, handle)
        if value is None:
            raise _UnknownHandle
        return value

    def _record(
        self,
        run: RunContext,
        tool: str,
        args: dict[str, Labeled[Any]],
        facts: dict[str, Any],
        decision: Decision,
        outcome: ToolOutcome,
        reason: ReasonCode,
        started: float,
    ) -> str:
        decision_id = self._ids.new_id("dec")
        self._decisions.add(
            DecisionRecord(
                decision_id=decision_id,
                run_id=run.run_id,
                tool=tool,
                args_handles={name: value.handle for name, value in args.items()},
                facts=facts,
                allow=decision.allow,
                outcome=str(outcome),
                determining_policies=decision.determining_policies,
                reason_code=str(reason),
                latency_ms=int((time.perf_counter() - started) * 1000),
                created_at=self._clock.now_iso(),
            )
        )
        for name, value in args.items():
            self._lineage.add_edge(
                LineageEdge(
                    edge_id=self._ids.new_id("edge"),
                    run_id=run.run_id,
                    source_handle=value.handle,
                    target_handle=decision_id,
                    kind=EdgeKind.ARG,
                    label=name,
                )
            )
        return decision_id

    @staticmethod
    def _reason_for(decision: Decision, fallback: ReasonCode) -> ReasonCode:
        """Pick the most fundamental reason among the policies that denied."""
        fired = set(decision.determining_policies)
        for policy in REASON_PRECEDENCE:
            if policy in fired:
                return POLICY_REASONS[policy]
        for policy in decision.determining_policies:
            if policy in POLICY_REASONS:
                return POLICY_REASONS[policy]
        return fallback

    # ------------------------------------------------------------- pay_vendor

    def pay_vendor(
        self,
        run: RunContext,
        vendor_handle: str,
        account_handle: str,
        amount_handle: str,
        invoice_handle: str,
        vendor_match_verified: bool,
        execute: Callable[[LedgerEntry], None] | None = None,
    ) -> ToolResult:
        """Authorize and, if permitted, perform a payment."""
        started = time.perf_counter()
        try:
            vendor_value = self._resolve(run.run_id, vendor_handle)
            account = self._resolve(run.run_id, account_handle)
            amount = self._resolve(run.run_id, amount_handle)
            invoice = self._resolve(run.run_id, invoice_handle)
        except _ArgumentNotAHandle:
            return ToolResult(ToolOutcome.DENIED, ReasonCode.ARG_MUST_BE_HANDLE)
        except _UnknownHandle:
            return ToolResult(ToolOutcome.DENIED, ReasonCode.UNKNOWN_HANDLE)

        args = {
            "vendor": vendor_value,
            "account": account,
            "amount": amount,
            "invoice": invoice,
        }

        try:
            vendor_id = str(vendor_value.value)
            facts = compute_payment_facts(
                vendor_id=vendor_id,
                account=account,
                amount_paise=int(amount.value),
                invoice_number=str(invoice.value),
                vendor_match_verified=vendor_match_verified,
                vendors=self._vendors,
                ledger=self._ledger,
            )
            fact_dict = _payment_facts_dict(facts)

            decision = self._authorizer.is_authorized(
                build_payment_request(
                    run.run_id,
                    run.user_id,
                    vendor_id,
                    facts.vendor_status,
                    run.mandate,
                    amount,
                    account,
                    facts,
                    human_approved=False,
                )
            )
        except Exception:
            # Fail closed: an enforcement bug must never become an executed payment.
            self._record(
                run,
                "pay_vendor",
                args,
                {},
                Decision(allow=False),
                ToolOutcome.DENIED,
                ReasonCode.ENFORCEMENT_ERROR,
                started,
            )
            return ToolResult(ToolOutcome.DENIED, ReasonCode.ENFORCEMENT_ERROR)

        if decision.allow:
            txn_id = self._ids.new_id("txn")
            entry = LedgerEntry(
                txn_id=txn_id,
                run_id=run.run_id,
                vendor_id=vendor_id,
                invoice_number=str(invoice.value),
                amount_paise=facts.amount_paise,
                account_masked=_mask(str(account.value)),
                status="SETTLED",
            )
            (execute or self._ledger.record)(entry)
            self._record(
                run,
                "pay_vendor",
                args,
                fact_dict,
                decision,
                ToolOutcome.EXECUTED,
                ReasonCode.OK,
                started,
            )
            return ToolResult(
                ToolOutcome.EXECUTED,
                ReasonCode.OK,
                decision.determining_policies,
                txn_id=txn_id,
            )

        # Would a human approver change the answer? Asking is what separates an
        # escalation from something nobody can authorise.
        hypothetical = self._authorizer.is_authorized(
            build_payment_request(
                run.run_id,
                run.user_id,
                vendor_id,
                facts.vendor_status,
                run.mandate,
                amount,
                account,
                facts,
                human_approved=True,
            )
        )
        reason = self._reason_for(decision, ReasonCode.POLICY_DENIED)

        if hypothetical.allow:
            approval_id = self._ids.new_id("apr")
            self._record(
                run,
                "pay_vendor",
                args,
                fact_dict,
                decision,
                ToolOutcome.PENDING_APPROVAL,
                reason,
                started,
            )
            return ToolResult(
                ToolOutcome.PENDING_APPROVAL,
                reason,
                decision.determining_policies,
                approval_id=approval_id,
            )

        self._record(
            run, "pay_vendor", args, fact_dict, decision, ToolOutcome.DENIED, reason, started
        )
        return ToolResult(
            ToolOutcome.DENIED,
            reason,
            decision.determining_policies,
            suggested_next=SUGGESTED_AFTER_PAYMENT_DENIAL,
        )

    # ------------------------------------------------------------- send_email

    def send_email(
        self,
        run: RunContext,
        recipient_handle: str,
        template_id: str,
        attachment_handles: list[str],
        template_confidentiality: Confidentiality = Confidentiality.PUBLIC,
    ) -> ToolResult:
        """Authorize an outbound email."""
        started = time.perf_counter()
        try:
            recipient = self._resolve(run.run_id, recipient_handle)
            attachments = [self._resolve(run.run_id, h) for h in attachment_handles]
        except _ArgumentNotAHandle:
            return ToolResult(ToolOutcome.DENIED, ReasonCode.ARG_MUST_BE_HANDLE)
        except _UnknownHandle:
            return ToolResult(ToolOutcome.DENIED, ReasonCode.UNKNOWN_HANDLE)

        args = {"recipient": recipient}
        for index, item in enumerate(attachments):
            args[f"attachment{index}"] = item

        try:
            facts = compute_email_facts(
                recipient, attachments, template_confidentiality, self._company, self._vendors
            )
            fact_dict = _email_facts_dict(facts)
            decision = self._authorizer.is_authorized(
                build_email_request(
                    run.run_id, run.user_id, run.mandate, recipient, facts, human_approved=False
                )
            )
        except Exception:
            self._record(
                run,
                "send_email",
                args,
                {},
                Decision(allow=False),
                ToolOutcome.DENIED,
                ReasonCode.ENFORCEMENT_ERROR,
                started,
            )
            return ToolResult(ToolOutcome.DENIED, ReasonCode.ENFORCEMENT_ERROR)

        if decision.allow:
            self._record(
                run,
                "send_email",
                args,
                fact_dict,
                decision,
                ToolOutcome.EXECUTED,
                ReasonCode.OK,
                started,
            )
            return ToolResult(ToolOutcome.EXECUTED, ReasonCode.OK, decision.determining_policies)

        hypothetical = self._authorizer.is_authorized(
            build_email_request(
                run.run_id, run.user_id, run.mandate, recipient, facts, human_approved=True
            )
        )
        reason = self._reason_for(decision, ReasonCode.POLICY_DENIED)

        if hypothetical.allow:
            approval_id = self._ids.new_id("apr")
            self._record(
                run,
                "send_email",
                args,
                fact_dict,
                decision,
                ToolOutcome.PENDING_APPROVAL,
                reason,
                started,
            )
            return ToolResult(
                ToolOutcome.PENDING_APPROVAL,
                reason,
                decision.determining_policies,
                approval_id=approval_id,
            )

        self._record(
            run, "send_email", args, fact_dict, decision, ToolOutcome.DENIED, reason, started
        )
        return ToolResult(ToolOutcome.DENIED, reason, decision.determining_policies)


class _ArgumentNotAHandle(Exception):
    """A consequential argument arrived as a literal where a handle was required."""


class _UnknownHandle(Exception):
    """A handle referred to a value this run does not have."""


def _mask(account: str) -> str:
    return "X" * max(len(account) - 4, 0) + account[-4:]


def _payment_facts_dict(facts: PaymentFacts) -> dict[str, Any]:
    return {
        "accountMatchesVendorMaster": facts.account_matches_vendor_master,
        "vendorMatchVerified": facts.vendor_match_verified,
        "isDuplicateInvoice": facts.is_duplicate_invoice,
        "vendorStatus": facts.vendor_status,
        "amountPaise": facts.amount_paise,
    }


def _email_facts_dict(facts: EmailFacts) -> dict[str, Any]:
    return {
        "recipientIsInternal": facts.recipient_is_internal,
        "recipientIsKnownContact": facts.recipient_is_known_contact,
        "bodyConfidentiality": facts.body_confidentiality,
        "attachmentSources": list(facts.attachment_sources),
    }
