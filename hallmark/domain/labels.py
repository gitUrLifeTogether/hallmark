"""Provenance labels: where a value came from, and what happens when values combine.

The rule that makes the whole system work is that labels only ever *join*. There is no
function here that removes a source, and adding one would defeat the guarantee: a value
derived from untrusted content stays untrusted no matter how many times it is copied,
extracted or recombined.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final


class Source(StrEnum):
    """Where a value originated."""

    USER = "USER"
    COMPANY_DB = "COMPANY_DB"
    SYSTEM = "SYSTEM"
    EXTERNAL_EMAIL = "EXTERNAL_EMAIL"
    EXTERNAL_ATTACHMENT = "EXTERNAL_ATTACHMENT"
    WEB = "WEB"
    MODEL_READER = "MODEL_READER"


#: Sources the company controls. Anything else can be attacker-influenced.
TRUSTED_SOURCES: Final[frozenset[Source]] = frozenset(
    {Source.USER, Source.COMPANY_DB, Source.SYSTEM}
)


class Confidentiality(StrEnum):
    """How sensitive a value is. Ordered by `RANK`."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"


_RANK: Final[dict[Confidentiality, int]] = {
    Confidentiality.PUBLIC: 0,
    Confidentiality.INTERNAL: 1,
    Confidentiality.CONFIDENTIAL: 2,
}


class ValueType(StrEnum):
    """What kind of thing a value is. Drives declassification (see declassify.py)."""

    MONEY_PAISE = "MONEY_PAISE"
    DATE = "DATE"
    GSTIN = "GSTIN"
    IFSC = "IFSC"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    DOMAIN = "DOMAIN"
    INVOICE_NUMBER = "INVOICE_NUMBER"
    FREE_TEXT = "FREE_TEXT"
    DOCUMENT = "DOCUMENT"
    ENUM = "ENUM"


def join_sources(source_sets: Iterable[frozenset[Source]]) -> frozenset[Source]:
    """Union the sources of several inputs.

    Returns an empty set for no inputs, which callers must treat as a programming error
    rather than as "trusted" — see `is_trusted`, which is deliberately strict about it.
    """
    joined: set[Source] = set()
    for sources in source_sets:
        joined.update(sources)
    return frozenset(joined)


def max_confidentiality(levels: Iterable[Confidentiality]) -> Confidentiality:
    """Return the most restrictive confidentiality among the inputs."""
    return max(levels, key=lambda level: _RANK[level], default=Confidentiality.PUBLIC)


def is_trusted(sources: frozenset[Source]) -> bool:
    """True only when every source is company-controlled.

    An empty source set is **not** trusted. A value with no recorded provenance is a bug,
    and the safe reading of a bug is "we do not know where this came from".
    """
    if not sources:
        return False
    return sources <= TRUSTED_SOURCES
