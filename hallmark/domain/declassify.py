"""Deciding what the planner is allowed to *see*.

A validated number or date cannot carry an instruction, so the planner can reason about
amounts and deadlines without ever reading attacker-controlled prose. Free text, emails,
domains and documents are never shown — the planner only ever gets a handle for those.

Visibility is not trust. Declassifying a value changes nothing about its sources; it only
decides whether a `display` string accompanies the handle.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime
from typing import Any, Final

from hallmark.domain.identifiers import (
    ACCOUNT_PATTERN,
    GSTIN_PATTERN,
    IFSC_PATTERN,
    INVOICE_PATTERN,
)
from hallmark.domain.labels import ValueType
from hallmark.domain.values import Labeled

#: Types that may never be shown to the planner, whatever their provenance.
NEVER_DECLASSIFIED: Final[frozenset[ValueType]] = frozenset(
    {
        ValueType.EMAIL_ADDRESS,
        ValueType.DOMAIN,
        ValueType.FREE_TEXT,
        ValueType.DOCUMENT,
    }
)

MIN_PAISE: Final = 1
MAX_PAISE: Final = 100_000_000_000  # Rs 1,00,00,00,000 expressed in paise
DATE_WINDOW_DAYS: Final = 730  # +/- 2 years

_MONEY_PATTERN: Final = re.compile(r"^\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?$|^\d+(?:\.\d{1,2})?$")


class DeclassificationRejected(Exception):
    """The value did not pass its type's validator, so the planner will not see it."""


def _format_inr(paise: int) -> str:
    """Format paise using the Indian digit grouping (lakh/crore)."""
    rupees, remainder = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"₹{digits}.{remainder:02d}"


def parse_money_to_paise(value: Any) -> int:
    """Turn an extracted amount into integer paise, or reject it.

    The single place money is parsed. An extractor that rolled its own was stricter than
    this one without meaning to be -- it could not read "462000.00" -- and silently dropped
    the field, which left the planner to pass some other handle in the amount's place. The
    resulting enforcement error was correct but unreadable, and it cost an hour to trace.
    """
    if isinstance(value, bool):
        raise DeclassificationRejected("boolean is not an amount")
    if isinstance(value, int):
        paise = value
    else:
        text = str(value).strip().replace("₹", "").strip()
        if not _MONEY_PATTERN.match(text):
            raise DeclassificationRejected("amount is not a plain number")
        paise = int(round(float(text.replace(",", "")) * 100))
    if not MIN_PAISE <= paise <= MAX_PAISE:
        raise DeclassificationRejected("amount outside the permitted range")
    return paise


def _declassify_money(value: Any) -> str:
    return _format_inr(parse_money_to_paise(value))


def _declassify_date(value: Any, today: date | None = None) -> str:
    text = str(value).strip()
    parsed: date | None = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        raise DeclassificationRejected("date is not in a recognised format")

    reference = today or date.today()
    if abs((parsed - reference).days) > DATE_WINDOW_DAYS:
        raise DeclassificationRejected("date is implausibly far from today")
    return parsed.isoformat()


def _declassify_pattern(value: Any, pattern: re.Pattern[str], label: str) -> str:
    text = str(value).strip().upper()
    if not pattern.match(text):
        raise DeclassificationRejected(f"not a well-formed {label}")
    return text


def _declassify_account(value: Any) -> str:
    text = str(value).strip().replace(" ", "")
    if not ACCOUNT_PATTERN.match(text):
        raise DeclassificationRejected("not a well-formed account number")
    # Even when shown, the planner only sees the last four digits.
    return "X" * (len(text) - 4) + text[-4:]


def declassify_display(vtype: ValueType, value: Any, today: date | None = None) -> str:
    """Return the canonical display string, or raise `DeclassificationRejected`."""
    if vtype in NEVER_DECLASSIFIED:
        raise DeclassificationRejected(f"{vtype} is never shown to the planner")
    if vtype is ValueType.MONEY_PAISE:
        return _declassify_money(value)
    if vtype is ValueType.DATE:
        return _declassify_date(value, today)
    if vtype is ValueType.GSTIN:
        return _declassify_pattern(value, GSTIN_PATTERN, "GSTIN")
    if vtype is ValueType.IFSC:
        return _declassify_pattern(value, IFSC_PATTERN, "IFSC")
    if vtype is ValueType.INVOICE_NUMBER:
        return _declassify_pattern(value, INVOICE_PATTERN, "invoice number")
    if vtype is ValueType.ACCOUNT_NUMBER:
        return _declassify_account(value)
    if vtype is ValueType.ENUM:
        return str(value)
    raise DeclassificationRejected(f"no validator for {vtype}")


def try_declassify(labeled: Labeled[Any], today: date | None = None) -> Labeled[Any]:
    """Attach a display string when the value passes its validator.

    Returns the value unchanged on rejection: the planner simply gets a handle with no
    display, which is always a safe outcome.
    """
    try:
        display = declassify_display(labeled.vtype, labeled.value, today)
    except DeclassificationRejected:
        return labeled
    return replace(labeled, declassified=True, display=display)
