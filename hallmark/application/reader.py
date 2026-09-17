"""The quarantined reader: reads untrusted content, holds no tools.

The reader is assumed to be fully manipulable. Its prompt tells it to extract rather than
obey, but that is for usefulness, not safety. Two things keep a manipulated reader from
mattering:

1. Everything it produces is stamped MODEL_READER and keeps the source's labels, so no
   extracted field can ever look trusted.
2. Every extracted string must actually appear in the source text. A reader that invents
   an account number, or is talked into emitting one from an instruction rather than from
   the invoice, has that field dropped.

Normalisation deliberately strips zero-width and Unicode tag characters before comparing,
so text hidden with invisible characters is compared on what it really says.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Protocol

from hallmark.domain.labels import Source, ValueType

#: Characters used to hide or disguise text: zero-width, BOM, and the Unicode tag block.
_INVISIBLE = re.compile(r"[​-‏⁠-⁯﻿\U000e0000-\U000e007f]")
_WHITESPACE = re.compile(r"\s+")
_SEPARATORS = re.compile(r"[,\s₹]")


def normalize(text: str) -> str:
    """Fold text to a form suitable for substring comparison."""
    folded = unicodedata.normalize("NFKC", text)
    folded = _INVISIBLE.sub("", folded)
    folded = _WHITESPACE.sub(" ", folded)
    return folded.strip().lower()


def normalize_number(text: str) -> str:
    """Strip grouping separators and currency marks so 4,62,000 matches 462000."""
    return _SEPARATORS.sub("", normalize(text))


@dataclass
class InvoiceExtraction:
    """The strict shape the reader must fill. Anything else is rejected."""

    vendor_name: str | None = None
    gstin: str | None = None
    invoice_number: str | None = None
    amount: str | None = None
    due_date: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None


@dataclass
class VerifiedExtraction:
    """Fields that survived verification, plus what was dropped and why."""

    fields: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


#: Which extracted field maps to which value type.
FIELD_TYPES: dict[str, ValueType] = {
    "vendor_name": ValueType.FREE_TEXT,
    "gstin": ValueType.GSTIN,
    "invoice_number": ValueType.INVOICE_NUMBER,
    "amount": ValueType.MONEY_PAISE,
    "due_date": ValueType.DATE,
    "bank_account": ValueType.ACCOUNT_NUMBER,
    "ifsc": ValueType.IFSC,
}

#: Fields compared with separators removed, because humans write amounts many ways.
_NUMERIC_FIELDS = frozenset({"amount", "bank_account"})


class ReaderModel(Protocol):
    """Fills `InvoiceExtraction` from untrusted text. No tools, ever."""

    def extract(self, source_text: str) -> InvoiceExtraction: ...


def verify_fields_in_source(extraction: InvoiceExtraction, source_text: str) -> VerifiedExtraction:
    """Drop any field whose value does not occur in the source text.

    This is the check that makes hidden-character tricks visible: both sides are
    normalised the same way, so text the attacker disguised is compared on its real
    content rather than its raw bytes.
    """
    haystack = normalize(source_text)
    numeric_haystack = normalize_number(source_text)
    result = VerifiedExtraction()

    for name in FIELD_TYPES:
        raw = getattr(extraction, name, None)
        if raw is None or str(raw).strip() == "":
            continue

        candidate = str(raw)
        if name in _NUMERIC_FIELDS:
            found = normalize_number(candidate) in numeric_haystack
        else:
            found = normalize(candidate) in haystack

        if found:
            result.fields[name] = candidate
        else:
            result.dropped.append(name)
            result.warnings.append("FIELD_NOT_FOUND_IN_SOURCE")

    return result


def reader_sources(source_labels: frozenset[Source]) -> frozenset[Source]:
    """Everything the reader emits carries its input's labels plus MODEL_READER."""
    return source_labels | {Source.MODEL_READER}


def extract_and_verify(
    model: ReaderModel, source_text: str
) -> tuple[VerifiedExtraction, dict[str, Any]]:
    """Run the reader and verify its output against the source."""
    try:
        extraction = model.extract(source_text)
    except Exception:
        failed = VerifiedExtraction(warnings=["EXTRACTION_FAILED"])
        return failed, {}

    verified = verify_fields_in_source(extraction, source_text)
    return verified, {"raw": extraction}
