"""Domain value objects that validate on construction.

`AccountNumber` masks itself in `str` and `repr` so a destination account cannot leak
into a log line, a traceback or an error message by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from hallmark.domain.errors import ValidationError

GSTIN_PATTERN: Final = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_PATTERN: Final = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT_PATTERN: Final = re.compile(r"^[0-9]{9,18}$")
INVOICE_PATTERN: Final = re.compile(r"^[A-Z0-9/\-]{1,24}$")
DOMAIN_PATTERN: Final = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
EMAIL_PATTERN: Final = re.compile(r"^[^@\s]+@[a-z0-9.-]+\.[a-z]{2,}$")


@dataclass(frozen=True)
class Gstin:
    """An Indian GST identification number, uppercased and format-checked."""

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().upper()
        if not GSTIN_PATTERN.match(canonical):
            raise ValidationError("not a well-formed GSTIN")
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Ifsc:
    """An Indian bank branch code."""

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().upper()
        if not IFSC_PATTERN.match(canonical):
            raise ValidationError("not a well-formed IFSC")
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AccountNumber:
    """A bank account number that refuses to print itself in full.

    Comparison still uses the full value, so `accountMatchesVendorMaster` stays exact;
    only the human-readable forms are masked.
    """

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().replace(" ", "")
        if not ACCOUNT_PATTERN.match(canonical):
            raise ValidationError("not a well-formed account number")
        object.__setattr__(self, "value", canonical)

    @property
    def masked(self) -> str:
        """Last four digits only, e.g. `XXXXXX4821`."""
        return "X" * max(len(self.value) - 4, 0) + self.value[-4:]

    def __str__(self) -> str:
        return self.masked

    def __repr__(self) -> str:
        return f"AccountNumber({self.masked})"


@dataclass(frozen=True)
class InvoiceNumber:
    """A vendor invoice reference, uppercased."""

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().upper()
        if not INVOICE_PATTERN.match(canonical):
            raise ValidationError("not a well-formed invoice number")
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Domain:
    """A lowercased DNS domain."""

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().lower().lstrip("@")
        if not DOMAIN_PATTERN.match(canonical):
            raise ValidationError("not a well-formed domain")
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EmailAddress:
    """A lowercased email address."""

    value: str

    def __post_init__(self) -> None:
        canonical = self.value.strip().lower()
        if not EMAIL_PATTERN.match(canonical):
            raise ValidationError("not a well-formed email address")
        object.__setattr__(self, "value", canonical)

    @property
    def domain(self) -> Domain:
        return Domain(self.value.split("@", 1)[1])

    def __str__(self) -> str:
        return self.value
