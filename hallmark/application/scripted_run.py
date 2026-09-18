"""A deterministic planner that follows the standard invoice procedure.

This exists so the security kernel can be proven without a model in the loop. It calls
exactly the same tools through exactly the same enforcement point a language model would,
so what it demonstrates about labels, facts and policy holds for the real planner too.
It is used for acceptance and tests, never for benchmark results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hallmark.application.pep import PolicyEnforcementPoint, RunContext
from hallmark.application.reader import InvoiceExtraction, verify_fields_in_source
from hallmark.domain.declassify import try_declassify
from hallmark.domain.labels import Confidentiality, Source, ValueType
from hallmark.domain.lineage import EdgeKind, LineageEdge
from hallmark.domain.tools import FlagReason, ToolOutcome
from hallmark.domain.values import Labeled, derive
from hallmark.ports.repositories import InboxEmail, InboxRepository, VendorRepository
from hallmark.ports.stores import Clock, IdGenerator, LineageStore, ValueStore


@dataclass
class EmailOutcome:
    """What happened to one email."""

    email_id: str
    status: str
    reason_code: str = "OK"
    determining_policies: tuple[str, ...] = ()
    flag_reason: str | None = None


@dataclass
class RunSummary:
    """Counts across the whole run, plus the per-email detail."""

    outcomes: list[EmailOutcome] = field(default_factory=list)
    reviews_opened: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for item in self.outcomes if item.status == status)

    def by_id(self, email_id: str) -> EmailOutcome:
        return next(item for item in self.outcomes if item.email_id == email_id)


class RegexInvoiceReader:
    """A stand-in reader that pulls fields out with patterns rather than a model.

    It is deliberately credulous: it reads hidden text along with visible text, exactly
    as a manipulable model would. What protects the run is not this component's judgment
    but the verification and labelling applied to whatever it returns.
    """

    def extract(self, source_text: str) -> InvoiceExtraction:
        import re

        def first(*patterns: str) -> str | None:
            """The first pattern that matches, so one wording is not privileged.

            The fixtures write "Total INR 4,62,000" and a person typing an invoice into
            the console writes "Amount: 462000.00". Reading only the first shape made the
            scripted planner look broken on anything a person actually wrote, which is
            the opposite of what a deterministic fallback is for.
            """
            for pattern in patterns:
                match = re.search(pattern, source_text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            return None

        return InvoiceExtraction(
            gstin=first(r"GSTIN:?\s*([0-9A-Z]+)"),
            invoice_number=first(
                r"invoice\s*(?:number|no\.?|#)?\s*:?\s*(INV-[A-Z0-9\-]+)",
                r"(INV-[A-Z0-9\-]+)",
            ),
            amount=first(
                r"(?:amount|total)\s*:?\s*(?:INR|Rs\.?|₹|\$)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
                r"(?:INR|Rs\.?|₹|\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
            ),
            due_date=first(r"due\s*(?:date)?\s*:?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9/\-]{8,10})"),
            bank_account=first(r"(?:bank\s*)?account\s*(?:number|no\.?)?\s*:?\s*([0-9]{9,18})"),
            ifsc=first(r"IFSC\s*(?:code)?\s*:?\s*([A-Z]{4}0[A-Z0-9]{6})"),
        )


class ScriptedRun:
    """Walks the inbox and processes each email the same way every time."""

    def __init__(
        self,
        pep: PolicyEnforcementPoint,
        inbox: InboxRepository,
        vendors: VendorRepository,
        values: ValueStore,
        lineage: LineageStore,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._pep = pep
        self._inbox = inbox
        self._vendors = vendors
        self._values = values
        self._lineage = lineage
        self._ids = ids
        self._clock = clock
        self._reader = RegexInvoiceReader()

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

    def _ingest_email(self, run: RunContext, email: InboxEmail) -> Labeled[str]:
        """The whole message, hidden text included, as one untrusted value."""
        combined = email.body
        if email.hidden_text:
            combined += "\n" + email.hidden_text
        for attachment in email.attachments:
            combined += "\n" + attachment.text
            if attachment.hidden_text:
                combined += "\n" + attachment.hidden_text

        sources = {Source.EXTERNAL_EMAIL}
        if email.attachments:
            sources.add(Source.EXTERNAL_ATTACHMENT)

        return self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value=combined,
                vtype=ValueType.FREE_TEXT,
                sources=frozenset(sources),
                confidentiality=Confidentiality.INTERNAL,
                run_id=run.run_id,
                op="ingest",
                created_at=self._clock.now_iso(),
            )
        )

    def _read_fields(
        self, run: RunContext, body: Labeled[str]
    ) -> tuple[dict[str, Labeled[Any]], list[str]]:
        """Extract, verify against the source, then label and declassify what survived."""
        extraction = self._reader.extract(body.value)
        verified = verify_fields_in_source(extraction, body.value)

        field_types = {
            "gstin": ValueType.GSTIN,
            "invoice_number": ValueType.INVOICE_NUMBER,
            "amount": ValueType.MONEY_PAISE,
            "due_date": ValueType.DATE,
            "bank_account": ValueType.ACCOUNT_NUMBER,
            "ifsc": ValueType.IFSC,
        }

        fields: dict[str, Labeled[Any]] = {}
        for name, raw in verified.fields.items():
            vtype = field_types.get(name, ValueType.FREE_TEXT)
            value: Any = raw
            if vtype is ValueType.MONEY_PAISE:
                value = int(raw.replace(",", "")) * 100

            labeled = derive(
                handle=self._ids.new_handle(),
                value=value,
                vtype=vtype,
                inputs=[body],
                op="reader_extract",
                run_id=run.run_id,
                created_at=self._clock.now_iso(),
                extra_sources=frozenset({Source.MODEL_READER}),
            )
            fields[name] = self._store(try_declassify(labeled))

        return fields, verified.warnings

    def _vendor_value(
        self, run: RunContext, vendor_id: str, gstin_field: Labeled[Any]
    ) -> Labeled[str]:
        """The vendor id, labelled COMPANY_DB because the record is ours.

        The untrusted GSTIN that selected it is recorded as a selection edge rather than
        folded into the value's sources: the record is trustworthy, but the fact that
        external content chose it is part of the audit trail.
        """
        value = self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value=vendor_id,
                vtype=ValueType.ENUM,
                sources=frozenset({Source.COMPANY_DB}),
                confidentiality=Confidentiality.INTERNAL,
                run_id=run.run_id,
                op="db_lookup",
                created_at=self._clock.now_iso(),
            )
        )
        self._lineage.add_edge(
            LineageEdge(
                edge_id=self._ids.new_id("edge"),
                run_id=run.run_id,
                source_handle=gstin_field.handle,
                target_handle=value.handle,
                kind=EdgeKind.SELECTION,
                label="gstin",
            )
        )
        return value

    def _account_on_file(self, run: RunContext, account_number: str) -> Labeled[str]:
        """The account from the vendor master: the only one a payment may reach."""
        return self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value=account_number,
                vtype=ValueType.ACCOUNT_NUMBER,
                sources=frozenset({Source.COMPANY_DB}),
                confidentiality=Confidentiality.CONFIDENTIAL,
                run_id=run.run_id,
                op="db_lookup",
                created_at=self._clock.now_iso(),
            )
        )

    def _attempt_requested_export(
        self, run: RunContext, email_id: str, body: Labeled[str]
    ) -> EmailOutcome | None:
        """If the content names an address to send records to, try sending them there.

        Modelling the agent as obedient here is the point. The vendor master is genuinely
        confidential company data and the address genuinely came from an attachment, so
        the decision rests on provenance rather than on the agent noticing anything.
        """
        import re

        match = re.search(
            r"send the current vendor master list to\s+([^\s]+@[^\s.]+(?:\.[^\s.]+)+)",
            body.value,
            re.IGNORECASE,
        )
        if match is None:
            return None

        recipient = self._store(
            derive(
                handle=self._ids.new_handle(),
                value=match.group(1).rstrip("."),
                vtype=ValueType.EMAIL_ADDRESS,
                inputs=[body],
                op="reader_extract",
                run_id=run.run_id,
                created_at=self._clock.now_iso(),
                extra_sources=frozenset({Source.MODEL_READER}),
            )
        )

        export = self._store(
            Labeled(
                handle=self._ids.new_handle(),
                value="vendor-master-export",
                vtype=ValueType.DOCUMENT,
                sources=frozenset({Source.COMPANY_DB}),
                confidentiality=Confidentiality.CONFIDENTIAL,
                run_id=run.run_id,
                op="export_vendor_master",
                created_at=self._clock.now_iso(),
            )
        )

        result = self._pep.send_email(
            run,
            recipient_handle=recipient.handle,
            template_id="NEED_INFO",
            attachment_handles=[export.handle],
            template_confidentiality=Confidentiality.CONFIDENTIAL,
        )

        status = "EXECUTED" if result.status is ToolOutcome.EXECUTED else "DENIED"
        return EmailOutcome(
            email_id,
            status,
            str(result.reason_code),
            result.determining_policies,
            flag_reason=str(FlagReason.OTHER),
        )

    def process_email(self, run: RunContext, email: InboxEmail) -> EmailOutcome:
        """Read one email and attempt the payment it asks for."""
        body = self._ingest_email(run, email)
        fields, warnings = self._read_fields(run, body)

        if "gstin" not in fields or "invoice_number" not in fields or "amount" not in fields:
            # No invoice to act on. If the content asks for company data to be sent
            # somewhere, a credulous agent obliges -- so attempt it and let policy answer.
            exfil = self._attempt_requested_export(run, email.email_id, body)
            if exfil is not None:
                return exfil
            return EmailOutcome(
                email.email_id, "FLAGGED", flag_reason=str(FlagReason.EXTRACTION_FAILED)
            )

        vendor = self._vendors.by_gstin(str(fields["gstin"].value))
        if vendor is None:
            return EmailOutcome(
                email.email_id, "FLAGGED", flag_reason=str(FlagReason.VENDOR_MISMATCH)
            )

        sender_domain = email.sender.split("@", 1)[1].lower()
        vendor_match_verified = sender_domain == vendor.domain.lower() and email.dkim_pass

        vendor_value = self._vendor_value(run, vendor.vendor_id, fields["gstin"])

        # A credulous agent pays what the invoice says. When the document supplies an
        # account that differs from the one on file, following the document means
        # reaching for a value that came out of the email -- which is exactly what the
        # attack is engineering. The planner is allowed to try; the enforcement point is
        # what decides. When the document agrees with the vendor master there is nothing
        # to be fooled about, so the trusted record is used.
        extracted_account = fields.get("bank_account")
        proposes_new_account = (
            extracted_account is not None and str(extracted_account.value) != vendor.account_number
        )
        account_value = (
            extracted_account
            if proposes_new_account and extracted_account is not None
            else self._account_on_file(run, vendor.account_number)
        )

        result = self._pep.pay_vendor(
            run,
            vendor_handle=vendor_value.handle,
            account_handle=account_value.handle,
            amount_handle=fields["amount"].handle,
            invoice_handle=fields["invoice_number"].handle,
            vendor_match_verified=vendor_match_verified,
        )

        if result.status is ToolOutcome.EXECUTED:
            return EmailOutcome(email.email_id, "EXECUTED", str(result.reason_code))
        if result.status is ToolOutcome.PENDING_APPROVAL:
            return EmailOutcome(
                email.email_id,
                "PENDING_APPROVAL",
                str(result.reason_code),
                result.determining_policies,
            )

        flag = (
            FlagReason.SUSPICIOUS_BANK_CHANGE
            if proposes_new_account
            else FlagReason.DUPLICATE
            if result.reason_code.value == "DUPLICATE_INVOICE"
            else FlagReason.OTHER
        )
        return EmailOutcome(
            email.email_id,
            "DENIED",
            str(result.reason_code),
            result.determining_policies,
            flag_reason=str(flag),
        )

    def run(self, run: RunContext) -> RunSummary:
        """Process every email in the inbox."""
        summary = RunSummary()
        for email in self._inbox.list_emails():
            outcome = self.process_email(run, email)
            summary.outcomes.append(outcome)
            if outcome.flag_reason == str(FlagReason.SUSPICIOUS_BANK_CHANGE):
                summary.reviews_opened.append(outcome.email_id)
        return summary
