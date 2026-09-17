"""Human approval of escalated actions.

Two things here are load-bearing.

An approver's authority is checked against the amount, so an AP lead cannot approve beyond
their limit by being the one who happens to click. And approving does not execute the
action: it re-runs the whole enforcement path with `humanApproved` set, recomputing facts
from current records. A vendor blocked, or an invoice paid by someone else, between the
request and the decision must change the answer -- otherwise an approval queue becomes a
way to act on stale facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from hallmark.domain.errors import Conflict, NotFound, ValidationError
from hallmark.domain.statuses import APPROVAL_TRANSITIONS, ApprovalStatus, check_transition
from hallmark.domain.tools import ToolOutcome, ToolResult

#: What each role may approve, in paise. A controller is required above the AP limit.
AP_LEAD_LIMIT_PAISE = 20_000_000
ROLE_LIMITS: dict[str, int] = {
    "AP_LEAD": AP_LEAD_LIMIT_PAISE,
    "CONTROLLER": 10_000_000_000,
}


@dataclass
class PendingAction:
    """An action waiting for a person.

    `task_token` never leaves the backend. It is the capability to resume a paused
    workflow, so returning it to a client would hand over the ability to approve.
    """

    approval_id: str
    run_id: str
    decision_id: str
    tool: str
    amount_paise: int
    required_role: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    task_token: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    expires_at: str | None = None
    arguments: dict[str, str] = field(default_factory=dict)

    def public_view(self) -> dict[str, object]:
        """The shape a client may see. Deliberately omits the task token."""
        return {
            "approvalId": self.approval_id,
            "runId": self.run_id,
            "decisionId": self.decision_id,
            "tool": self.tool,
            "amountPaise": self.amount_paise,
            "requiredRole": self.required_role,
            "status": str(self.status),
            "decidedBy": self.decided_by,
            "decidedAt": self.decided_at,
            "expiresAt": self.expires_at,
        }


class ApprovalStore(Protocol):
    """Storage for pending actions, with a conditional status change."""

    def put(self, action: PendingAction) -> None: ...
    def get(self, approval_id: str) -> PendingAction | None: ...
    def pending(self) -> list[PendingAction]: ...
    def transition(
        self, approval_id: str, expected: ApprovalStatus, target: ApprovalStatus, by: str, at: str
    ) -> bool:
        """Move an approval, only if it is still in `expected`. False if it was not."""
        ...


def required_role_for(amount_paise: int) -> str:
    """Who has to sign off on this amount."""
    return "AP_LEAD" if amount_paise <= AP_LEAD_LIMIT_PAISE else "CONTROLLER"


def may_approve(role: str, amount_paise: int) -> bool:
    """Whether a role carries enough authority for an amount."""
    return amount_paise <= ROLE_LIMITS.get(role, 0)


class ApprovalService:
    """Records escalations and resolves them."""

    def __init__(self, store: ApprovalStore, clock: object) -> None:
        self._store = store
        self._clock = clock

    def _now(self) -> str:
        return str(self._clock.now_iso())  # type: ignore[attr-defined]

    def request(
        self,
        approval_id: str,
        run_id: str,
        decision_id: str,
        tool: str,
        amount_paise: int,
        arguments: dict[str, str],
        task_token: str | None = None,
        expires_at: str | None = None,
    ) -> PendingAction:
        """Record an action that needs a person."""
        action = PendingAction(
            approval_id=approval_id,
            run_id=run_id,
            decision_id=decision_id,
            tool=tool,
            amount_paise=amount_paise,
            required_role=required_role_for(amount_paise),
            task_token=task_token,
            expires_at=expires_at,
            arguments=arguments,
        )
        self._store.put(action)
        return action

    def decide(
        self,
        approval_id: str,
        decision: str,
        approver_id: str,
        approver_role: str,
        reauthorize: object | None = None,
    ) -> dict[str, object]:
        """Approve or reject, then re-run enforcement rather than trusting the approval.

        The re-authorization is the point. An approval is permission to *ask again with a
        human attached*, not permission to execute: the facts are recomputed, and a denial
        that no approver can lift still denies.
        """
        if decision not in {"APPROVE", "REJECT"}:
            raise ValidationError("decision must be APPROVE or REJECT")

        action = self._store.get(approval_id)
        if action is None:
            raise NotFound("no such approval")

        target = ApprovalStatus.APPROVED if decision == "APPROVE" else ApprovalStatus.REJECTED
        check_transition(APPROVAL_TRANSITIONS, action.status, target)

        if target is ApprovalStatus.APPROVED and not may_approve(
            approver_role, action.amount_paise
        ):
            raise Conflict(
                f"{approver_role} cannot approve {action.amount_paise} paise; "
                f"{action.required_role} is required"
            )

        moved = self._store.transition(
            approval_id, ApprovalStatus.PENDING, target, approver_id, self._now()
        )
        if not moved:
            # Someone else decided first. Refusing here is what stops a double payment.
            raise Conflict("this approval was already decided")

        if target is ApprovalStatus.REJECTED:
            return {"approvalId": approval_id, "status": str(target), "executed": False}

        if reauthorize is None:
            return {"approvalId": approval_id, "status": str(target), "executed": False}

        result: ToolResult = reauthorize(action)  # type: ignore[operator]
        return {
            "approvalId": approval_id,
            "status": str(target),
            "executed": result.status is ToolOutcome.EXECUTED,
            "outcome": str(result.status),
            "reasonCode": str(result.reason_code),
            "determiningPolicies": list(result.determining_policies),
        }
