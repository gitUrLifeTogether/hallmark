"""Tool declarations and the fixed vocabulary of results the planner may receive.

Everything the planner reads back from a tool is an enum, a boolean, an identifier or a
declassified display string. No untrusted text is ever echoed back, including in errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ToolOutcome(StrEnum):
    """What happened to a consequential call."""

    EXECUTED = "EXECUTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    DENIED = "DENIED"


class ReasonCode(StrEnum):
    """The complete set of reasons a call can come back unhappy."""

    OK = "OK"
    ARG_MUST_BE_HANDLE = "ARG_MUST_BE_HANDLE"
    UNKNOWN_HANDLE = "UNKNOWN_HANDLE"
    ACCOUNT_NOT_FROM_VENDOR_MASTER = "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    VENDOR_NOT_VERIFIED = "VENDOR_NOT_VERIFIED"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    ABOVE_AUTO_APPROVE_LIMIT = "ABOVE_AUTO_APPROVE_LIMIT"
    ABOVE_MANDATE_CAP = "ABOVE_MANDATE_CAP"
    ACTION_NOT_IN_MANDATE = "ACTION_NOT_IN_MANDATE"
    VENDOR_BLOCKED = "VENDOR_BLOCKED"
    RECIPIENT_NOT_TRUSTED = "RECIPIENT_NOT_TRUSTED"
    CONFIDENTIAL_TO_EXTERNAL = "CONFIDENTIAL_TO_EXTERNAL"
    POLICY_DENIED = "POLICY_DENIED"
    ENFORCEMENT_ERROR = "ENFORCEMENT_ERROR"


class FlagReason(StrEnum):
    """Why a human was asked to look at something."""

    SUSPICIOUS_BANK_CHANGE = "SUSPICIOUS_BANK_CHANGE"
    DUPLICATE = "DUPLICATE"
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    ABOVE_LIMIT = "ABOVE_LIMIT"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    OTHER = "OTHER"


class ExtractionWarning(StrEnum):
    """Why a field the reader produced was not kept."""

    FIELD_NOT_FOUND_IN_SOURCE = "FIELD_NOT_FOUND_IN_SOURCE"
    FIELD_FAILED_VALIDATION = "FIELD_FAILED_VALIDATION"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


@dataclass(frozen=True)
class ToolSpec:
    """How a tool must be called, and whether Cedar judges it."""

    name: str
    consequential: bool
    handle_required_args: frozenset[str] = frozenset()
    literal_allowed_args: frozenset[str] = frozenset()
    cedar_action: str | None = None


@dataclass(frozen=True)
class ToolResult:
    """What a consequential tool hands back to the planner."""

    status: ToolOutcome
    reason_code: ReasonCode = ReasonCode.OK
    determining_policies: tuple[str, ...] = ()
    suggested_next: tuple[str, ...] = ()
    txn_id: str | None = None
    approval_id: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
