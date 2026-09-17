"""The mock enterprise systems the agent acts against."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Vendor:
    """A vendor master record. The bank account here is the only one payable."""

    vendor_id: str
    legal_name: str
    gstin: str
    domain: str
    account_number: str
    ifsc: str
    status: str = "ACTIVE"
    contact_emails: tuple[str, ...] = ()
    contact_phone: str = ""
    version: int = 1


@dataclass(frozen=True)
class LedgerEntry:
    """A payment that was made, or is awaiting approval."""

    txn_id: str
    run_id: str
    vendor_id: str
    invoice_number: str
    amount_paise: int
    account_masked: str
    status: str = "SETTLED"


@dataclass(frozen=True)
class EmailAttachment:
    """An attachment, including any text hidden in the document."""

    attachment_id: str
    filename: str
    text: str
    hidden_text: str = ""


@dataclass(frozen=True)
class InboxEmail:
    """A fixture email. Everything here is attacker-controllable except `dkim_pass`."""

    email_id: str
    sender: str
    sender_display_name: str
    subject: str
    body: str
    received_at: str
    dkim_pass: bool = True
    hidden_text: str = ""
    attachments: tuple[EmailAttachment, ...] = ()


class VendorRepository(Protocol):
    def by_gstin(self, gstin: str) -> Vendor | None: ...
    def by_id(self, vendor_id: str) -> Vendor | None: ...
    def all_vendors(self) -> list[Vendor]: ...


class LedgerRepository(Protocol):
    def has_invoice(self, vendor_id: str, invoice_number: str) -> bool: ...
    def record(self, entry: LedgerEntry) -> None: ...
    def entries(self) -> list[LedgerEntry]: ...


class InboxRepository(Protocol):
    def list_emails(self) -> list[InboxEmail]: ...
    def get(self, email_id: str) -> InboxEmail | None: ...


@dataclass
class Company:
    """The operating company. Its domain defines what counts as internal."""

    name: str
    domain: str
    internal_emails: tuple[str, ...] = field(default_factory=tuple)
