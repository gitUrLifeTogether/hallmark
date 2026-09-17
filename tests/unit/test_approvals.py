"""Approval behaviour: who may approve, and what approving actually does."""

from __future__ import annotations

import pytest

from hallmark.adapters.memory.stores import FixedClock, InMemoryApprovalStore
from hallmark.application.approvals import (
    ApprovalService,
    PendingAction,
    may_approve,
    required_role_for,
)
from hallmark.domain.errors import Conflict, NotFound, ValidationError
from hallmark.domain.statuses import ApprovalStatus
from hallmark.domain.tools import ReasonCode, ToolOutcome, ToolResult

UNDER_AP_LIMIT = 15_000_000
OVER_AP_LIMIT = 38_000_000


def build(amount: int = UNDER_AP_LIMIT) -> tuple[ApprovalService, InMemoryApprovalStore]:
    store = InMemoryApprovalStore()
    service = ApprovalService(store, FixedClock())
    service.request(
        approval_id="apr_1",
        run_id="run-1",
        decision_id="dec_1",
        tool="pay_vendor",
        amount_paise=amount,
        arguments={"account": "h_acc"},
        task_token="token-abc",
    )
    return service, store


def executed(_: PendingAction) -> ToolResult:
    return ToolResult(ToolOutcome.EXECUTED, ReasonCode.OK, ("pay-permit-within-mandate",))


def still_denied(_: PendingAction) -> ToolResult:
    return ToolResult(
        ToolOutcome.DENIED,
        ReasonCode.ACCOUNT_NOT_FROM_VENDOR_MASTER,
        ("pay-account-must-be-master",),
    )


def test_the_required_role_depends_on_the_amount() -> None:
    assert required_role_for(UNDER_AP_LIMIT) == "AP_LEAD"
    assert required_role_for(OVER_AP_LIMIT) == "CONTROLLER"
    assert may_approve("AP_LEAD", UNDER_AP_LIMIT) is True
    assert may_approve("AP_LEAD", OVER_AP_LIMIT) is False
    assert may_approve("CONTROLLER", OVER_AP_LIMIT) is True
    assert may_approve("JUDGE", 1) is False, "an unknown role approves nothing"


def test_an_ap_lead_cannot_approve_above_their_limit() -> None:
    service, store = build(OVER_AP_LIMIT)
    with pytest.raises(Conflict):
        service.decide("apr_1", "APPROVE", "ananya", "AP_LEAD", executed)

    assert store.get("apr_1").status is ApprovalStatus.PENDING, "a refusal must not consume it"


def test_a_controller_can_approve_the_same_amount() -> None:
    service, _ = build(OVER_AP_LIMIT)
    result = service.decide("apr_1", "APPROVE", "vikram", "CONTROLLER", executed)
    assert result["executed"] is True


def test_approving_re_runs_enforcement_rather_than_executing_directly() -> None:
    """The guarantee: approval is permission to ask again, not permission to act.

    Here the re-check still denies, because the destination account did not come from the
    vendor master. The approval is recorded, and nothing executes.
    """
    service, store = build()
    result = service.decide("apr_1", "APPROVE", "ananya", "AP_LEAD", still_denied)

    assert result["executed"] is False
    assert result["reasonCode"] == "ACCOUNT_NOT_FROM_VENDOR_MASTER"
    assert store.get("apr_1").status is ApprovalStatus.APPROVED


def test_the_second_of_two_simultaneous_approvals_is_refused() -> None:
    """Both succeeding would re-run enforcement twice and could pay twice."""
    service, _ = build()
    calls: list[str] = []

    def counting(action: PendingAction) -> ToolResult:
        calls.append(action.approval_id)
        return executed(action)

    first = service.decide("apr_1", "APPROVE", "ananya", "AP_LEAD", counting)
    assert first["executed"] is True

    with pytest.raises(Conflict):
        service.decide("apr_1", "APPROVE", "vikram", "CONTROLLER", counting)

    assert calls == ["apr_1"], "enforcement must run exactly once"


def test_a_rejected_approval_cannot_later_be_approved() -> None:
    service, _ = build()
    service.decide("apr_1", "REJECT", "ananya", "AP_LEAD")

    with pytest.raises(Conflict):
        service.decide("apr_1", "APPROVE", "ananya", "AP_LEAD", executed)


def test_rejecting_never_executes() -> None:
    service, store = build()
    calls: list[str] = []

    def should_not_run(action: PendingAction) -> ToolResult:
        calls.append("ran")
        return executed(action)

    result = service.decide("apr_1", "REJECT", "ananya", "AP_LEAD", should_not_run)
    assert result["executed"] is False
    assert calls == []
    assert store.get("apr_1").status is ApprovalStatus.REJECTED


def test_an_unknown_approval_is_not_found() -> None:
    service, _ = build()
    with pytest.raises(NotFound):
        service.decide("apr_missing", "APPROVE", "ananya", "AP_LEAD", executed)


@pytest.mark.parametrize("bad", ["approve", "yes", "", "MAYBE"])
def test_only_approve_or_reject_are_accepted(bad: str) -> None:
    service, _ = build()
    with pytest.raises(ValidationError):
        service.decide("apr_1", bad, "ananya", "AP_LEAD", executed)


def test_the_task_token_is_never_in_the_client_view() -> None:
    """Handing over the token would hand over the ability to resume the workflow."""
    service, store = build()
    view = store.get("apr_1").public_view()

    assert store.get("apr_1").task_token == "token-abc", "the backend still holds it"
    assert "token-abc" not in str(view), "but it never reaches a client"
    assert not any("token" in key.lower() for key in view)
