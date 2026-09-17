"""The unprotected agent, driven deterministically.

Same inbox, same mock systems, same procedure as the protected run — but the tools hand
back full text and payments execute the moment they are asked for. There is no enforcement
point, no provenance, and no policy.

It follows the document, which is what an accounts-payable agent is *supposed* to do. That
is the whole point of the comparison: the baseline is not careless, it is obedient, and
obedience is sufficient for the attack to succeed.

Deterministic on purpose. A model-driven baseline would sometimes get lucky, and "the
attack worked four times out of five" is a weaker claim than "following the document leads
here every time".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hallmark.ports.repositories import (
    InboxEmail,
    InboxRepository,
    LedgerEntry,
    VendorRepository,
)


@dataclass
class BaselinePayment:
    """A payment the unprotected agent made."""

    email_id: str
    vendor_id: str
    invoice_number: str
    amount_paise: int
    account_number: str
    """The account it actually paid, which is whatever the document said."""


@dataclass
class BaselineSend:
    """Data the unprotected agent sent somewhere, because it was asked to."""

    email_id: str
    recipient: str
    contents: str


@dataclass
class BaselineRun:
    """What the unprotected agent did."""

    payments: list[BaselinePayment] = field(default_factory=list)
    sends: list[BaselineSend] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def paid_to(self, account_number: str) -> list[BaselinePayment]:
        return [p for p in self.payments if p.account_number == account_number]

    def sent_to(self, recipient: str) -> list[BaselineSend]:
        return [s for s in self.sends if s.recipient == recipient]

    @property
    def total_paise(self) -> int:
        return sum(p.amount_paise for p in self.payments)


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None


class ScriptedBaseline:
    """Reads each email in full and pays what it says."""

    def __init__(self, inbox: InboxRepository, vendors: VendorRepository) -> None:
        self._inbox = inbox
        self._vendors = vendors

    def _full_text(self, email: InboxEmail) -> str:
        """Everything the agent ingests, including what the sender hid.

        Hidden text is included because an agent reading an email really does receive it:
        it is in the document. Excluding it here would quietly make the baseline stronger
        than a real one and flatter the comparison.
        """
        text = email.body
        if email.hidden_text:
            text += "\n" + email.hidden_text
        for attachment in email.attachments:
            text += "\n" + attachment.text
            if attachment.hidden_text:
                text += "\n" + attachment.hidden_text
        return text

    def run(self, ledger_entries: list[LedgerEntry] | None = None) -> BaselineRun:
        result = BaselineRun()
        seen: set[tuple[str, str]] = {
            (e.vendor_id, e.invoice_number.upper()) for e in (ledger_entries or [])
        }

        for email in self._inbox.list_emails():
            text = self._full_text(email)

            gstin = _find(r"GSTIN:\s*([0-9A-Z]+)", text)
            invoice = _find(r"[Ii]nvoice\s+(INV-[A-Z0-9\-]+)", text)
            amount = _find(r"INR\s+([0-9,]+)", text)
            account = _find(r"Account:\s*([0-9]+)", text)

            if not (gstin and invoice and amount and account):
                # No invoice to act on. If the content asks for company records to be sent
                # somewhere, an obedient agent sends them: there is nothing here that
                # distinguishes a genuine request from an attacker's.
                requested = _find(
                    r"send the current vendor master list to\s+([^\s]+@[^\s.]+(?:\.[^\s.]+)+)",
                    text,
                )
                if requested:
                    result.sends.append(
                        BaselineSend(
                            email_id=email.email_id,
                            recipient=requested.rstrip("."),
                            contents="vendor-master-export",
                        )
                    )
                else:
                    result.skipped.append(email.email_id)
                continue

            vendor = self._vendors.by_gstin(gstin)
            if vendor is None:
                result.skipped.append(email.email_id)
                continue

            key = (vendor.vendor_id, invoice.upper())
            if key in seen:
                # Even an unprotected agent usually notices an exact repeat.
                result.skipped.append(email.email_id)
                continue
            seen.add(key)

            result.payments.append(
                BaselinePayment(
                    email_id=email.email_id,
                    vendor_id=vendor.vendor_id,
                    invoice_number=invoice.upper(),
                    amount_paise=int(amount.replace(",", "")) * 100,
                    # The document's account, not the vendor master's. This single line is
                    # the difference between the two runs.
                    account_number=account,
                )
            )

        return result
