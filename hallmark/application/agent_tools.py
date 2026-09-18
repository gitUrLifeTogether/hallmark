"""The tool surface the planner is allowed to touch.

Every return value here is built from handles, enums, booleans and declassified displays.
No method returns untrusted text, and none of them accepts one: the planner names values
by handle and never sees what is behind them. This is the boundary that the canary test
in `tests/security/` exists to police.

The methods are plain Python so they can be tested and driven by the scripted planner
without a model. The Strands wrappers in `planner.py` are thin adapters over these.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from hallmark.application.pep import PolicyEnforcementPoint, RunContext
from hallmark.application.reader import verify_fields_in_source
from hallmark.domain.declassify import parse_money_to_paise, try_declassify
from hallmark.domain.labels import Confidentiality, Source, ValueType
from hallmark.domain.lineage import EdgeKind, LineageEdge
from hallmark.domain.tools import FlagReason, ToolSpec
from hallmark.domain.values import Labeled, derive
from hallmark.ports.repositories import InboxRepository, VendorRepository
from hallmark.ports.stores import Clock, IdGenerator, LineageStore, ValueStore

logger = logging.getLogger(__name__)

WRAPUP_SECONDS = 90.0
"""How long an episode may continue after its payment has been decided.

Enough for the follow-up a denial calls for -- flagging it, and opening a bank change
review -- and not enough for the loop a small model falls into afterwards. One run made
nineteen tool calls: the real work was done by the tenth and the rest was the model
failing to stop, which no call budget catches because refusing a call is not ending one.
"""

#: Which extracted field becomes which kind of value.
EXTRACTED_FIELD_TYPES: dict[str, ValueType] = {
    "gstin": ValueType.GSTIN,
    "invoice_number": ValueType.INVOICE_NUMBER,
    "amount": ValueType.MONEY_PAISE,
    "due_date": ValueType.DATE,
    "bank_account": ValueType.ACCOUNT_NUMBER,
    "ifsc": ValueType.IFSC,
}

TOOL_SPECS: dict[str, ToolSpec] = {
    "list_inbox": ToolSpec("list_inbox", consequential=False),
    "read_email": ToolSpec(
        "read_email", consequential=False, handle_required_args=frozenset({"email_handle"})
    ),
    "extract_invoice": ToolSpec(
        "extract_invoice", consequential=False, handle_required_args=frozenset({"source_handle"})
    ),
    "lookup_vendor": ToolSpec(
        "lookup_vendor", consequential=False, handle_required_args=frozenset({"gstin_handle"})
    ),
    "check_duplicate": ToolSpec(
        "check_duplicate",
        consequential=False,
        handle_required_args=frozenset({"vendor_handle", "invoice_number_handle"}),
    ),
    "pay_vendor": ToolSpec(
        "pay_vendor",
        consequential=True,
        handle_required_args=frozenset(
            {"vendor_handle", "account_handle", "amount_handle", "invoice_handle"}
        ),
        cedar_action="pay_vendor",
    ),
    "send_email": ToolSpec(
        "send_email",
        consequential=True,
        handle_required_args=frozenset({"recipient_handle"}),
        cedar_action="send_email",
    ),
    "flag_for_review": ToolSpec(
        "flag_for_review", consequential=False, handle_required_args=frozenset({"handle"})
    ),
    "export_vendor_master": ToolSpec("export_vendor_master", consequential=False),
    "open_bank_change_review": ToolSpec(
        "open_bank_change_review",
        consequential=False,
        handle_required_args=frozenset({"vendor_handle", "proposed_account_handle"}),
    ),
}


@dataclass
class ReaderPort:
    """Whatever turns untrusted text into a strict form. Never given tools."""

    extract: Any


class AgentTools:
    """Handle-based tools shared by the scripted and model-driven planners."""

    def __init__(
        self,
        run: RunContext,
        pep: PolicyEnforcementPoint,
        inbox: InboxRepository,
        vendors: VendorRepository,
        values: ValueStore,
        lineage: LineageStore,
        ids: IdGenerator,
        clock: Clock,
        reader: Any,
        events: Any | None = None,
    ) -> None:
        self.run = run
        self._pep = pep
        self._inbox = inbox
        self._vendors = vendors
        self._values = values
        self._lineage = lineage
        self._ids = ids
        self._clock = clock
        self._reader = reader
        self._events = events
        self._email_by_handle: dict[str, str] = {}
        #: The account the most recent extraction found, if any. Held so the comparison
        #: against the vendor master can be done in code rather than by asking the planner
        #: to compare two masked strings -- which a small model gets wrong often enough to
        #: decide the outcome of a run by chance.
        self._extracted_account: Labeled[Any] | None = None
        #: What prepare_payment worked out, so a payment can be named rather than spelled.
        self._prepared: dict[str, Any] = {}
        self.flags: list[tuple[str, str]] = []
        #: Every consequential attempt and how it ended, including the ones refused before
        #: the policy engine was reached. Those produce no decision record, so a summary
        #: built only from decisions reports them as if nothing was attempted -- which is
        #: the same fault that once made unreachable bench scenarios look like defences.
        self.attempts: list[dict[str, Any]] = []
        self.reviews: list[str] = []
        self.call_budget: int | None = None
        self.calls_made = 0
        self.deadline: float | None = None
        #: Set once a payment has a final outcome. From then on the run's verdict is
        #: settled, whatever the planner does next.
        self.payment_decided = False

    def start_episode(self, budget: int, deadline_seconds: float | None = None) -> None:
        """Begin one email's episode with a fresh call budget and optional deadline.

        The budget bounds how much a confused model can do; the deadline bounds how long
        it can take to do it. They are different failures: one episode spent 55 minutes
        inside eight legitimate calls, which no call budget would have caught.
        """
        self.call_budget = budget
        self.calls_made = 0
        self.payment_decided = False
        self.deadline = None if deadline_seconds is None else time.monotonic() + deadline_seconds

    def out_of_time(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    def _announce(self, tool: str) -> None:
        """Tell the console a tool ran. Telemetry only, and never allowed to fail a call.

        Only the tool name travels. Arguments are handles and could be resolved by a
        careless consumer, and the whole point of a handle is that it is not the content.
        """
        if self._events is None:
            return
        try:
            from hallmark.ports.events import DomainEvent, EventType

            self._events.publish(
                DomainEvent(
                    EventType.TOOL_CALLED,
                    self.run.run_id,
                    self._clock.now_iso(),
                    {"tool": tool},
                )
            )
        except Exception:
            # Swallowed on purpose, and the same rule the enforcement point follows:
            # announcing a tool call is telemetry, and telemetry must never be able to
            # fail the call it is describing.
            logger.warning("tool announcement failed", extra={"tool": tool})

    def _spend_call(self, tool: str = "") -> bool:
        """Consume one unit of budget, returning False once it is exhausted.

        A small model that loses the thread will otherwise call tools forever. Bounding
        the work in code rather than in the prompt means a confused planner stalls
        instead of running up an unbounded bill, and the run still terminates.
        """
        if tool:
            self._announce(tool)
        if self.out_of_time():
            # Refusing here stops the loop cooperatively at the next tool call, which is
            # the only place this code runs. A model stuck inside one long call is the
            # caller's problem to bound.
            return False
        if self.call_budget is None:
            return True
        self.calls_made += 1
        return self.calls_made <= self.call_budget

    # --------------------------------------------------------------- internals

    def _store(self, value: Labeled[Any]) -> Labeled[Any]:
        self._values.put(value)
        for parent in value.parents:
            self._lineage.add_edge(
                LineageEdge(
                    edge_id=self._ids.new_id("edge"),
                    run_id=value.run_id,
                    source_handle=parent,
                    target_handle=value.handle,
                    kind=EdgeKind.DERIVE,
                    label=value.op,
                )
            )
        return value

    def _ingest(
        self, text: str, sources: set[Source], vtype: ValueType = ValueType.FREE_TEXT
    ) -> Labeled[str]:
        return self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value=text,
                vtype=vtype,
                sources=frozenset(sources),
                confidentiality=Confidentiality.INTERNAL,
                run_id=self.run.run_id,
                op="ingest",
                created_at=self._clock.now_iso(),
            )
        )

    # -------------------------------------------------------------- read tools

    def list_inbox(self) -> dict[str, Any]:
        """List waiting emails as handles. No subjects, senders or bodies."""
        entries = []
        for email in self._inbox.list_emails():
            handle = self._ids.new_handle()
            self._email_by_handle[handle] = email.email_id
            self._store(
                Labeled(
                    handle=handle,
                    value=email.email_id,
                    vtype=ValueType.ENUM,
                    sources=frozenset({Source.SYSTEM}),
                    confidentiality=Confidentiality.INTERNAL,
                    run_id=self.run.run_id,
                    op="inbox_entry",
                    created_at=self._clock.now_iso(),
                )
            )
            entries.append(
                {
                    "email_handle": handle,
                    "received_at": email.received_at,
                    "has_attachments": bool(email.attachments),
                }
            )
        return {"emails": entries}

    def read_email(self, email_handle: str) -> dict[str, Any]:
        """Open an email. The body stays in the store; only handles come back."""
        if not self._spend_call("read_email"):
            return {"error": "CALL_BUDGET_EXHAUSTED"}

        email_id = self._email_by_handle.get(email_handle)
        if email_id is None:
            return {"error": "UNKNOWN_HANDLE"}
        email = self._inbox.get(email_id)
        if email is None:
            return {"error": "UNKNOWN_HANDLE"}

        combined = email.body
        if email.hidden_text:
            combined += "\n" + email.hidden_text
        sources = {Source.EXTERNAL_EMAIL}
        for attachment in email.attachments:
            combined += "\n" + attachment.text
            if attachment.hidden_text:
                combined += "\n" + attachment.hidden_text
            sources.add(Source.EXTERNAL_ATTACHMENT)

        body = self._ingest(combined, sources)
        sender_domain = self._ingest(
            email.sender.split("@", 1)[1].lower(), {Source.EXTERNAL_EMAIL}, ValueType.DOMAIN
        )

        return {
            "body_handle": body.handle,
            "sender_domain_handle": sender_domain.handle,
            "auth": {"dkim": "pass" if email.dkim_pass else "fail"},
            "has_attachments": bool(email.attachments),
        }

    def extract_invoice(self, source_handle: str) -> dict[str, Any]:
        """Run the quarantined reader over stored content and label what survives."""
        if not self._spend_call("extract_invoice"):
            return {"error": "CALL_BUDGET_EXHAUSTED"}

        body = self._values.get(self.run.run_id, source_handle)
        if body is None:
            return {"error": "UNKNOWN_HANDLE"}

        try:
            extraction = self._reader.extract(str(body.value))
        except Exception:
            return {"fields": {}, "extraction_warnings": ["EXTRACTION_FAILED"]}

        verified = verify_fields_in_source(extraction, str(body.value))
        fields: dict[str, Any] = {}
        warnings: list[str] = list(verified.warnings)

        for name, raw in verified.fields.items():
            vtype = EXTRACTED_FIELD_TYPES.get(name, ValueType.FREE_TEXT)
            value: Any = raw
            if vtype is ValueType.MONEY_PAISE:
                try:
                    value = parse_money_to_paise(raw)
                except Exception:
                    # Dropped, but never silently: a missing amount used to leave the
                    # planner to put some other handle in its place, and the enforcement
                    # error that followed said nothing about why.
                    warnings.append("AMOUNT_UNREADABLE")
                    continue

            labeled = try_declassify(
                derive(
                    handle=self._ids.new_handle(),
                    value=value,
                    vtype=vtype,
                    inputs=[body],
                    op="reader_extract",
                    run_id=self.run.run_id,
                    created_at=self._clock.now_iso(),
                    extra_sources=frozenset({Source.MODEL_READER}),
                )
            )
            self._store(labeled)
            if vtype is ValueType.ACCOUNT_NUMBER:
                self._extracted_account = labeled
            entry: dict[str, Any] = {"handle": labeled.handle}
            if labeled.declassified and labeled.display is not None:
                entry["display"] = labeled.display
            fields[name] = entry

        return {"fields": fields, "extraction_warnings": sorted(set(warnings))}

    def lookup_vendor(self, gstin_handle: str, sender_domain_handle: str) -> dict[str, Any]:
        """Find the vendor by GSTIN and report whether the sender really matches it."""
        if not self._spend_call("lookup_vendor"):
            return {"error": "CALL_BUDGET_EXHAUSTED"}

        gstin = self._values.get(self.run.run_id, gstin_handle)
        domain = self._values.get(self.run.run_id, sender_domain_handle)
        if gstin is None or domain is None:
            return {"error": "UNKNOWN_HANDLE"}

        vendor = self._vendors.by_gstin(str(gstin.value))
        if vendor is None:
            return {"found": False}

        vendor_value = self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value=vendor.vendor_id,
                vtype=ValueType.ENUM,
                sources=frozenset({Source.COMPANY_DB}),
                confidentiality=Confidentiality.INTERNAL,
                run_id=self.run.run_id,
                op="db_lookup",
                created_at=self._clock.now_iso(),
            )
        )
        # The record is ours, but untrusted input chose it. Keep that visible.
        self._lineage.add_edge(
            LineageEdge(
                edge_id=self._ids.new_id("edge"),
                run_id=self.run.run_id,
                source_handle=gstin.handle,
                target_handle=vendor_value.handle,
                kind=EdgeKind.SELECTION,
                label="gstin",
            )
        )

        account = self._store(
            try_declassify(
                Labeled(
                    handle=self._ids.new_handle(),
                    value=vendor.account_number,
                    vtype=ValueType.ACCOUNT_NUMBER,
                    sources=frozenset({Source.COMPANY_DB}),
                    confidentiality=Confidentiality.CONFIDENTIAL,
                    run_id=self.run.run_id,
                    op="db_lookup",
                    created_at=self._clock.now_iso(),
                )
            )
        )

        result: dict[str, Any] = {
            "found": True,
            "vendor_handle": vendor_value.handle,
            "vendor_id": vendor.vendor_id,
            "status": vendor.status,
            "domain_matches": str(domain.value) == vendor.domain.lower(),
            "account_on_file_handle": account.handle,
        }
        # Masked, so the planner can tell whether an invoice proposes a different account
        # without ever seeing either number. Without it the planner cannot notice a bank
        # change at all, and would pay every invoice from the record -- which looks like
        # perfect behaviour while meaning the account rule is never exercised.
        if account.declassified and account.display is not None:
            result["account_on_file_display"] = account.display

        # The same comparison, decided here rather than by the planner. It is a fact about
        # two values, not a security decision -- the enforcement point still judges whatever
        # the planner does with it -- and leaving it to a small model to compare two masked
        # strings made the outcome of a run turn on chance.
        if self._extracted_account is not None:
            result["invoice_proposes_new_account"] = str(self._extracted_account.value) != str(
                account.value
            )
        return result

    def prepare_payment(self, email_handle: str) -> dict[str, Any]:
        """Read an email, extract its invoice and identify the supplier, in one step.

        The three calls this replaces are unchanged and still used by the scripted planner
        and the tests; this only removes the chance to get their order wrong. A small model
        skips steps -- one run went read_email, flag_for_review, extract_invoice, pay_vendor,
        never looking the vendor up at all, then invented a handle for the account and was
        refused for naming one that does not exist. No wording of the procedure fixed that,
        so the procedure stopped being something to remember.

        Nothing about enforcement changes. The planner still chooses which account to pay,
        which is the decision the whole demonstration is about.
        """
        email = self.read_email(email_handle)
        if "error" in email:
            return email

        extraction = self.extract_invoice(email["body_handle"])
        fields = extraction.get("fields", {})
        if "gstin" not in fields:
            return {
                "error": "EXTRACTION_INCOMPLETE",
                "extraction_warnings": extraction.get("extraction_warnings", []),
                "suggested_next": ["flag_for_review"],
            }

        vendor = self.lookup_vendor(fields["gstin"]["handle"], email["sender_domain_handle"])
        if not vendor.get("found"):
            return {"error": "VENDOR_NOT_FOUND", "suggested_next": ["flag_for_review"]}

        self._prepared = {
            "vendor_handle": vendor["vendor_handle"],
            "account_on_file_handle": vendor["account_on_file_handle"],
            "invoice_account_handle": fields.get("bank_account", {}).get("handle"),
            "amount_handle": fields.get("amount", {}).get("handle"),
            "invoice_handle": fields.get("invoice_number", {}).get("handle"),
            "vendor_match_verified": bool(vendor.get("domain_matches"))
            and email["auth"]["dkim"] == "pass",
            "proposes_new_account": bool(vendor.get("invoice_proposes_new_account")),
        }
        return {
            "auth": email["auth"],
            "fields": fields,
            "extraction_warnings": extraction.get("extraction_warnings", []),
            **vendor,
        }

    def _refused(self, reason: str, suggested: list[str]) -> dict[str, Any]:
        """Refuse a payment before it reaches the enforcement point, and record it.

        Recorded because a summary built only from what the enforcement point saw would
        call this "no payment attempted" -- crediting a defence that was never tested. It
        is the same fault that once made unreachable bench scenarios look like successes.
        """
        payload = {
            "status": "DENIED",
            "reason_code": reason,
            "determining_policies": [],
            "suggested_next": suggested,
        }
        self.attempts.append({"tool": "pay_vendor", **payload})
        self._settle()
        return payload

    def pay_prepared(self, account: str = "as_invoiced") -> dict[str, Any]:
        """Pay the prepared invoice, naming which account to send it to.

        The planner chooses between the account on file and the one the invoice supplied.
        That choice is the whole decision the demonstration is about, and it stays with the
        planner. What it no longer does is spell out four opaque handles: a 1.7b model gets
        that wrong in a way nothing downstream can repair -- it typed a value where a handle
        belonged and the call was refused before any policy could consider it, which reads
        as the system blocking a legitimate invoice.

        Handles are unchanged underneath. The enforcement point still receives them, still
        resolves them, and still judges the provenance of every one.
        """
        prepared = self._prepared
        if not prepared:
            return self._refused("NOTHING_PREPARED", ["prepare_payment"])

        choice = str(account).strip().lower()
        if choice in ("from_invoice", "invoice"):
            account_handle = prepared["invoice_account_handle"]
        elif choice in ("on_file", "file", "master", "vendor_master"):
            account_handle = prepared["account_on_file_handle"]
        else:
            # No usable choice: follow the document, which is what a credulous accounts
            # payable agent does and what the scripted planner does in code. A model that
            # omits the argument or invents a word must not quietly become more careful
            # than the agent being demonstrated -- that would hide the attack rather than
            # defend against it, and the enforcement point is what decides either way.
            account_handle = (
                prepared["invoice_account_handle"]
                if prepared.get("proposes_new_account")
                else prepared["account_on_file_handle"]
            )

        missing = [
            name
            for name in ("amount_handle", "invoice_handle", "vendor_handle")
            if not prepared.get(name)
        ]
        if missing or not account_handle:
            return self._refused("EXTRACTION_INCOMPLETE", ["flag_for_review"])

        return self.pay_vendor(
            vendor_handle=prepared["vendor_handle"],
            account_handle=account_handle,
            amount_handle=prepared["amount_handle"],
            invoice_handle=prepared["invoice_handle"],
            vendor_match_verified=prepared["vendor_match_verified"],
        )

    def flag_for_review(self, handle: str, reason: str) -> dict[str, Any]:
        """Record that a person should look at something."""
        try:
            flag = FlagReason(reason)
        except ValueError:
            flag = FlagReason.OTHER
        self.flags.append((handle, str(flag)))
        return {"flag_id": self._ids.new_id("flg"), "reason": str(flag)}

    def open_bank_change_review(
        self, vendor_handle: str, proposed_account_handle: str
    ) -> dict[str, Any]:
        """Open a human review of a proposed bank change. Nothing is changed here."""
        self.reviews.append(vendor_handle)
        return {"review_id": self._ids.new_id("rev")}

    def export_vendor_master(self) -> dict[str, Any]:
        """Produce a confidential export as a handle."""
        export = self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value="vendor-master-export",
                vtype=ValueType.DOCUMENT,
                sources=frozenset({Source.COMPANY_DB}),
                confidentiality=Confidentiality.CONFIDENTIAL,
                run_id=self.run.run_id,
                op="export_vendor_master",
                created_at=self._clock.now_iso(),
            )
        )
        return {"export_handle": export.handle}

    # ----------------------------------------------------- consequential tools

    def pay_vendor(
        self,
        vendor_handle: str,
        account_handle: str,
        amount_handle: str,
        invoice_handle: str,
        vendor_match_verified: bool = False,
    ) -> dict[str, Any]:
        """Attempt a payment. The enforcement point decides what actually happens."""
        if not self._spend_call("pay_vendor"):
            return {
                "status": "DENIED",
                "reason_code": "CALL_BUDGET_EXHAUSTED",
                "determining_policies": [],
            }

        result = self._pep.pay_vendor(
            self.run,
            vendor_handle=vendor_handle,
            account_handle=account_handle,
            amount_handle=amount_handle,
            invoice_handle=invoice_handle,
            vendor_match_verified=vendor_match_verified,
        )
        payload: dict[str, Any] = {
            "status": str(result.status),
            "reason_code": str(result.reason_code),
            "determining_policies": list(result.determining_policies),
        }
        if result.txn_id:
            payload["txn_id"] = result.txn_id
        if result.approval_id:
            payload["approval_id"] = result.approval_id
        if result.suggested_next:
            payload["suggested_next"] = list(result.suggested_next)
        self.attempts.append({"tool": "pay_vendor", **payload})

        if payload["status"] in ("EXECUTED", "DENIED", "PENDING_APPROVAL"):
            self._settle()
        return payload

    def _settle(self) -> None:
        """Bring the deadline forward now that the verdict is decided.

        Everything the episode existed to determine has been determined. What remains is
        the follow-up a denial calls for, which is quick, and then the planner should stop.
        """
        self.payment_decided = True
        wrapup = time.monotonic() + WRAPUP_SECONDS
        self.deadline = wrapup if self.deadline is None else min(self.deadline, wrapup)

    def send_email(
        self, recipient_handle: str, template_id: str, attachment_handles: list[str] | None = None
    ) -> dict[str, Any]:
        """Attempt to send a templated email."""
        if not self._spend_call("send_email"):
            return {
                "status": "DENIED",
                "reason_code": "CALL_BUDGET_EXHAUSTED",
                "determining_policies": [],
            }

        confidentiality = Confidentiality.PUBLIC
        attachments = attachment_handles or []
        for handle in attachments:
            value = self._values.get(self.run.run_id, handle)
            if value is not None and value.confidentiality is Confidentiality.CONFIDENTIAL:
                confidentiality = Confidentiality.CONFIDENTIAL

        result = self._pep.send_email(
            self.run,
            recipient_handle=recipient_handle,
            template_id=template_id,
            attachment_handles=attachments,
            template_confidentiality=confidentiality,
        )
        return {
            "status": str(result.status),
            "reason_code": str(result.reason_code),
            "determining_policies": list(result.determining_policies),
        }
