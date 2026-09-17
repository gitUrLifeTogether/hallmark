"""Value objects validate on construction, and account numbers refuse to print."""

from __future__ import annotations

import pytest

from hallmark.domain.errors import ValidationError
from hallmark.domain.identifiers import (
    AccountNumber,
    Domain,
    EmailAddress,
    Gstin,
    Ifsc,
    InvoiceNumber,
)


def test_an_account_number_never_prints_in_full() -> None:
    """The main reason this type exists: keeping a destination out of the logs.

    A traceback, a log line or an f-string interpolation all go through str or repr, so
    masking there covers the ways an account would otherwise escape by accident.
    """
    account = AccountNumber("911020033456")

    assert str(account) == "XXXXXXXX3456"
    assert repr(account) == "AccountNumber(XXXXXXXX3456)"
    assert f"paying {account}" == "paying XXXXXXXX3456"
    assert "911020033456" not in f"{account!r} {account!s} {account}"


def test_the_full_account_is_still_available_for_comparison() -> None:
    """Masking is for display; matching against the vendor master must stay exact."""
    assert AccountNumber("911020033456").value == "911020033456"
    assert AccountNumber("911020033456") == AccountNumber("911 020 033 456")
    assert AccountNumber("911020033456") != AccountNumber("889900771234")


@pytest.mark.parametrize("bad", ["12345678", "notdigits", "", "9110200334561234567890"])
def test_malformed_account_numbers_are_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        AccountNumber(bad)


def test_identifiers_are_canonicalised() -> None:
    assert Gstin("27fghij5678k1z3").value == "27FGHIJ5678K1Z3"
    assert Ifsc(" icic0004567 ").value == "ICIC0004567"
    assert InvoiceNumber("inv-sm-2291").value == "INV-SM-2291"
    assert Domain("@Suryodayametals.Example").value == "suryodayametals.example"
    assert EmailAddress("Billing@Suryodayametals.Example").value == (
        "billing@suryodayametals.example"
    )


def test_an_email_address_exposes_its_domain() -> None:
    assert EmailAddress("billing@suryodayametals.example").domain == Domain(
        "suryodayametals.example"
    )


@pytest.mark.parametrize(
    ("factory", "bad"),
    [
        (Gstin, "NOTAGSTIN"),
        (Gstin, "27FGHIJ5678K1Y3"),
        (Ifsc, "ICIC004567"),
        (Ifsc, "1CIC0004567"),
        (InvoiceNumber, "inv sm 2291; drop"),
        (InvoiceNumber, ""),
        (Domain, "no-dot"),
        (EmailAddress, "not-an-address"),
        (EmailAddress, "two@@at.example"),
    ],
)
def test_malformed_identifiers_are_refused(factory: type, bad: str) -> None:
    with pytest.raises(ValidationError):
        factory(bad)
