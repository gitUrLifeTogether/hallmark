"""Money parsing, which had two implementations that disagreed.

The extractor rolled its own and could not read an amount written with paise — "462000.00"
— so it dropped the field. The planner then had no amount handle and passed another value's
handle in its place, and enforcement failed closed with an error that named nothing. The
outcome was safe and the diagnosis was nearly impossible.

These fix the shapes a real invoice actually uses.
"""

from __future__ import annotations

import pytest

from hallmark.domain.declassify import DeclassificationRejected, parse_money_to_paise


@pytest.mark.parametrize(
    ("written", "paise"),
    [
        ("$45000.00", 4_500_000),
        # Moved here from the rejected cases when currency stripping was added. A trailing
        # code is an ordinary way to write an amount, and refusing it cost the planner a
        # field it needed; the digits are still required to be the ones in the document.
        ("462000.00 INR", 46_200_000),
        ("Rs 45000.00", 4_500_000),
        ("INR 4,62,000", 46_200_000),
        ("462000", 46_200_000),
        ("462000.00", 46_200_000),
        ("462000.50", 46_200_050),
        ("4,62,000.00", 46_200_000),
        ("4,62,000", 46_200_000),
        ("₹462000.00", 46_200_000),
        ("  462000.00  ", 46_200_000),
        ("45000.00", 4_500_000),
    ],
)
def test_the_ways_an_invoice_writes_an_amount(written: str, paise: int) -> None:
    assert parse_money_to_paise(written) == paise


@pytest.mark.parametrize(
    "written",
    [
        "INV-SM-2291",
        "four lakh",
        "",
        "-100",
        "462000.123",
        "0",
    ],
)
def test_what_is_not_an_amount_is_rejected_not_guessed(written: str) -> None:
    """Rejection must be loud. Silently dropping the field is what caused the original bug."""
    with pytest.raises(DeclassificationRejected):
        parse_money_to_paise(written)


def test_a_boolean_is_not_an_amount() -> None:
    """True would otherwise parse as 1 paise, because bool is an int in Python."""
    with pytest.raises(DeclassificationRejected):
        parse_money_to_paise(True)


def test_an_amount_beyond_the_permitted_range_is_rejected() -> None:
    with pytest.raises(DeclassificationRejected):
        parse_money_to_paise("999999999999")


# --- field-in-source verification, for amounts the reader decorates -----------

from hallmark.application.reader import InvoiceExtraction, verify_fields_in_source  # noqa: E402

SOURCE = "Invoice number: INV-SM-9902\nAmount: 45000.00\nBank account: 911020033456"


def verified(amount: str) -> dict[str, str]:
    return verify_fields_in_source(InvoiceExtraction(amount=amount), SOURCE).fields


@pytest.mark.parametrize(
    "written", ["45000.00", "45,000.00", "$45000.00", "Rs 45000.00", "INR 45,000.00", "₹45000.00"]
)
def test_an_amount_the_reader_decorated_still_verifies(written: str) -> None:
    """The reader returned "$45000.00" for a document reading "Amount: 45000.00".

    The digits were right and the symbol was invented. Dropping the field cost the planner
    its amount entirely, and everything downstream failed for want of it: a legitimate
    invoice came back refused, which is the opposite of what the system had decided.

    Verification exists to stop invented values, not invented formatting.
    """
    assert verified(written).get("amount") == written


@pytest.mark.parametrize("written", ["99999.00", "450000.00", "12345"])
def test_an_amount_that_is_not_in_the_document_is_still_dropped(written: str) -> None:
    """The guarantee this check exists for, unchanged."""
    assert "amount" not in verified(written)
