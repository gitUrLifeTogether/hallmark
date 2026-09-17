"""Deterministic checks against the company's own records.

Every fact here is computed in code from trusted data. None of them asks a model what it
thinks, because a fact a model can be talked out of is not a fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hallmark.domain.labels import Confidentiality
from hallmark.domain.values import Labeled
from hallmark.ports.repositories import Company, LedgerRepository, VendorRepository


@dataclass(frozen=True)
class PaymentFacts:
    """What the company's records say about a proposed payment."""

    account_matches_vendor_master: bool
    vendor_match_verified: bool
    is_duplicate_invoice: bool
    vendor_status: str
    amount_paise: int


@dataclass(frozen=True)
class EmailFacts:
    """What the company's records say about a proposed outbound email."""

    recipient_is_internal: bool
    recipient_is_known_contact: bool
    body_confidentiality: str
    attachment_sources: tuple[str, ...]


def compute_payment_facts(
    vendor_id: str,
    account: Labeled[Any],
    amount_paise: int,
    invoice_number: str,
    vendor_match_verified: bool,
    vendors: VendorRepository,
    ledger: LedgerRepository,
) -> PaymentFacts:
    """Check a payment against the vendor master and the ledger.

    `account_matches_vendor_master` requires both that the digits equal the account on
    file *and* that the value's provenance is trusted. Matching digits alone is not
    enough: an attacker who echoes back the real account in an email would otherwise
    launder their content into a trusted-looking argument.
    """
    vendor = vendors.by_id(vendor_id)
    if vendor is None:
        return PaymentFacts(False, False, False, "UNKNOWN", amount_paise)

    account_digits = str(account.value).strip().replace(" ", "")
    matches = account_digits == vendor.account_number and account.trusted

    return PaymentFacts(
        account_matches_vendor_master=matches,
        vendor_match_verified=vendor_match_verified,
        is_duplicate_invoice=ledger.has_invoice(vendor_id, invoice_number),
        vendor_status=vendor.status,
        amount_paise=amount_paise,
    )


def compute_email_facts(
    recipient: Labeled[Any],
    attachments: list[Labeled[Any]],
    template_confidentiality: Confidentiality,
    company: Company,
    vendors: VendorRepository,
) -> EmailFacts:
    """Check an outbound email's recipient and payload against company records."""
    address = str(recipient.value).strip().lower()
    domain = address.split("@", 1)[1] if "@" in address else ""

    known_contacts = {
        contact.lower() for vendor in vendors.all_vendors() for contact in vendor.contact_emails
    }

    levels = [template_confidentiality, *(item.confidentiality for item in attachments)]
    highest = max(
        levels,
        key=lambda level: [
            Confidentiality.PUBLIC,
            Confidentiality.INTERNAL,
            Confidentiality.CONFIDENTIAL,
        ].index(level),
    )

    sources: set[str] = set()
    for item in attachments:
        sources.update(str(s) for s in item.sources)

    return EmailFacts(
        recipient_is_internal=domain == company.domain.lower(),
        recipient_is_known_contact=address in known_contacts,
        body_confidentiality=str(highest),
        attachment_sources=tuple(sorted(sources)),
    )
