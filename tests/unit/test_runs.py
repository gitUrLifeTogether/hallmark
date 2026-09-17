"""Run lifecycle, and the mandate the planner is never allowed to write."""

from __future__ import annotations

import pytest

from hallmark.adapters.memory.stores import FixedClock, SequentialIdGenerator
from hallmark.application.runs import Run, RunService, draft_mandate
from hallmark.domain.errors import Conflict, NotFound, ValidationError
from hallmark.domain.mandate import PAY_VENDOR, SEND_EMAIL, Mandate
from hallmark.domain.statuses import RunStatus

HERO_REQUEST = (
    "Process this week's vendor invoices. Pay anything under ₹5,00,000 "
    "from existing vendors. Flag anything unusual for me."
)


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def put(self, run: Run) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[Run]:
        return list(self._runs.values())


@pytest.fixture
def service() -> RunService:
    return RunService(InMemoryRunStore(), SequentialIdGenerator(), FixedClock())


def test_the_hero_request_drafts_the_expected_cap() -> None:
    """₹5,00,000 is 50,000,000 paise. Getting this wrong changes what can be paid."""
    mandate = draft_mandate(HERO_REQUEST)

    assert mandate.max_amount_paise == 50_000_000
    assert PAY_VENDOR in mandate.allowed_actions
    assert mandate.auto_approve_limit_paise <= mandate.max_amount_paise


def test_amounts_are_parsed_deterministically_not_guessed() -> None:
    assert draft_mandate("pay up to Rs 2,00,000").max_amount_paise == 20_000_000
    assert draft_mandate("pay up to INR 1000").max_amount_paise == 100_000
    assert draft_mandate("pay invoices").max_amount_paise == 50_000_000, "a safe default"


def test_two_amounts_become_a_cap_and_an_auto_approve_limit() -> None:
    mandate = draft_mandate("Pay under ₹5,00,000, anything over ₹2,00,000 ask me first")
    assert mandate.max_amount_paise == 50_000_000
    assert mandate.auto_approve_limit_paise == 20_000_000


def test_sending_email_is_only_allowed_when_the_request_mentions_it() -> None:
    assert SEND_EMAIL not in draft_mandate("pay the invoices").allowed_actions
    assert SEND_EMAIL in draft_mandate("pay the invoices and email the vendors").allowed_actions


def test_a_new_run_waits_for_its_mandate(service: RunService) -> None:
    run = service.create("ananya", HERO_REQUEST, "hero")
    assert run.status is RunStatus.AWAITING_MANDATE
    assert run.mandate is not None, "a draft is proposed for the user to confirm"


def test_a_run_cannot_act_before_the_mandate_is_confirmed(service: RunService) -> None:
    """Acting on an unconfirmed scope would be acting before the user agreed."""
    run = service.create("ananya", HERO_REQUEST, "hero")
    with pytest.raises(Conflict):
        service.require_running(run.run_id)


def test_confirming_the_mandate_lets_the_run_proceed(service: RunService) -> None:
    run = service.create("ananya", HERO_REQUEST, "hero")
    edited = Mandate(frozenset({PAY_VENDOR}), 30_000_000, 10_000_000)

    confirmed = service.confirm_mandate(run.run_id, edited)
    assert confirmed.status is RunStatus.RUNNING
    assert service.require_running(run.run_id).mandate == edited


def test_the_user_can_tighten_the_mandate_before_confirming(service: RunService) -> None:
    """The confirmed mandate is what binds, not the draft."""
    run = service.create("ananya", HERO_REQUEST, "hero")
    assert run.mandate is not None and run.mandate.max_amount_paise == 50_000_000

    service.confirm_mandate(run.run_id, Mandate(frozenset({PAY_VENDOR}), 1_000_000, 500_000))
    assert service.get(run.run_id).mandate.max_amount_paise == 1_000_000


def test_a_mandate_cannot_be_confirmed_twice(service: RunService) -> None:
    run = service.create("ananya", HERO_REQUEST, "hero")
    mandate = Mandate(frozenset({PAY_VENDOR}), 30_000_000, 10_000_000)
    service.confirm_mandate(run.run_id, mandate)

    with pytest.raises(Conflict):
        service.confirm_mandate(run.run_id, Mandate(frozenset({PAY_VENDOR}), 99_000_000, 1))


def test_an_auto_approve_limit_above_the_cap_is_refused() -> None:
    with pytest.raises(ValidationError):
        Mandate(frozenset({PAY_VENDOR}), 10_000_000, 20_000_000)


@pytest.mark.parametrize("bad", ["", "   "])
def test_an_empty_request_is_refused(service: RunService, bad: str) -> None:
    with pytest.raises(ValidationError):
        service.create("ananya", bad, "hero")


def test_an_unknown_mode_is_refused(service: RunService) -> None:
    with pytest.raises(ValidationError):
        service.create("ananya", HERO_REQUEST, "hero", mode="SOMETHING_ELSE")


def test_an_unknown_run_is_not_found(service: RunService) -> None:
    with pytest.raises(NotFound):
        service.get("run-missing")


def test_a_completed_run_is_terminal(service: RunService) -> None:
    run = service.create("ananya", HERO_REQUEST, "hero")
    service.confirm_mandate(run.run_id, Mandate(frozenset({PAY_VENDOR}), 30_000_000, 10_000_000))
    service.complete(run.run_id, {"EXECUTED": 16})

    with pytest.raises(Conflict):
        service.complete(run.run_id, {"EXECUTED": 99})
