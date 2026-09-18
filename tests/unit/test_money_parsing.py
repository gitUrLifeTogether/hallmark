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
        "462000.00 INR",
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
