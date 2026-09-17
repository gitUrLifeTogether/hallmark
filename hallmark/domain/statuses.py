"""Lifecycle states, and the transitions that are allowed between them.

Written as explicit tables rather than scattered `if` checks. An approval that can move
from APPROVED back to PENDING, or be approved twice, is a way to pay an invoice twice, so
the legal moves are stated in one place and checked in one function.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from hallmark.domain.errors import Conflict


class RunStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_MANDATE = "AWAITING_MANDATE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ReviewStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"


RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.DRAFT: frozenset({RunStatus.AWAITING_MANDATE, RunStatus.FAILED}),
    RunStatus.AWAITING_MANDATE: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
}

#: Every decision is terminal. Nothing returns to PENDING, so an approval cannot be
#: replayed into a second payment.
APPROVAL_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}
    ),
    ApprovalStatus.APPROVED: frozenset(),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.EXPIRED: frozenset(),
}

REVIEW_TRANSITIONS: dict[ReviewStatus, frozenset[ReviewStatus]] = {
    ReviewStatus.OPEN: frozenset({ReviewStatus.COMPLETED}),
    ReviewStatus.COMPLETED: frozenset(),
}


def check_transition[S](table: Mapping[S, frozenset[S]], current: S, target: S) -> None:
    """Raise `Conflict` unless the move is permitted.

    Generic over the state type so one function serves every lifecycle, and so a run
    status cannot be checked against the approval table by mistake.

    Storage still applies a conditional write on top of this. This check gives a clear
    error; the conditional write is what makes two simultaneous approvals safe.
    """
    allowed = table.get(current)
    if allowed is None:
        raise Conflict(f"unknown state {current}")
    if target not in allowed:
        raise Conflict(f"cannot move from {current} to {target}")
