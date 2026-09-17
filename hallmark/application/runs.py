"""Starting a run, confirming its mandate, and reporting what it did.

The mandate is the one part of a run the planner never supplies. It is drafted from the
user's words, shown to them, confirmed by them, and then read back from storage at every
decision. A planner that could state its own spending limit would make the limit
decorative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from hallmark.domain.errors import Conflict, NotFound, ValidationError
from hallmark.domain.mandate import PAY_VENDOR, SEND_EMAIL, Mandate
from hallmark.domain.statuses import RUN_TRANSITIONS, RunStatus, check_transition

#: Fallbacks when the request names no figure. Conservative on purpose: a run that pays
#: less than the user intended is an inconvenience, the reverse is an incident.
DEFAULT_MAX_PAISE = 50_000_000
DEFAULT_AUTO_APPROVE_PAISE = 20_000_000

_AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)


@dataclass
class Run:
    """One pass over an inbox."""

    run_id: str
    user_id: str
    request_text: str
    inbox_fixture_id: str
    mode: str = "HALLMARK"
    status: RunStatus = RunStatus.DRAFT
    mandate: Mandate | None = None
    counts: dict[str, int] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""

    def public_view(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "userId": self.user_id,
            "inboxFixtureId": self.inbox_fixture_id,
            "mode": self.mode,
            "status": str(self.status),
            "counts": dict(self.counts),
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "mandate": (
                {
                    "allowedActions": sorted(self.mandate.allowed_actions),
                    "maxAmountPaise": self.mandate.max_amount_paise,
                    "autoApproveLimitPaise": self.mandate.auto_approve_limit_paise,
                }
                if self.mandate
                else None
            ),
        }


class RunStore(Protocol):
    def put(self, run: Run) -> None: ...
    def get(self, run_id: str) -> Run | None: ...
    def list_runs(self) -> list[Run]: ...


def draft_mandate(request_text: str) -> Mandate:
    """Turn the user's words into a proposed scope, in code rather than by asking a model.

    Amounts are parsed deterministically. A model drafting a spending limit from prose is
    exactly the kind of thing that should not be trusted, and the user confirms the result
    before anything runs regardless.
    """
    amounts = [
        int(round(float(match.replace(",", "")) * 100)) for match in _AMOUNT.findall(request_text)
    ]
    lowered = request_text.lower()

    actions = set()
    if any(word in lowered for word in ("pay", "remit", "settle", "invoice")):
        actions.add(PAY_VENDOR)
    if any(word in lowered for word in ("email", "reply", "notify", "write")):
        actions.add(SEND_EMAIL)
    if not actions:
        actions.add(PAY_VENDOR)

    cap = max(amounts) if amounts else DEFAULT_MAX_PAISE
    auto = min(amounts) if len(amounts) > 1 else min(DEFAULT_AUTO_APPROVE_PAISE, cap)

    return Mandate(
        allowed_actions=frozenset(actions),
        max_amount_paise=cap,
        auto_approve_limit_paise=auto,
    )


class RunService:
    """Creates runs and moves them through their lifecycle."""

    def __init__(self, store: RunStore, ids: Any, clock: Any) -> None:
        self._store = store
        self._ids = ids
        self._clock = clock

    def create(
        self, user_id: str, request_text: str, inbox_fixture_id: str, mode: str = "HALLMARK"
    ) -> Run:
        """Draft a run and its proposed mandate. Nothing executes until it is confirmed."""
        if not request_text.strip():
            raise ValidationError("a request is required")
        if mode not in {"HALLMARK", "BASELINE"}:
            raise ValidationError("mode must be HALLMARK or BASELINE")

        run = Run(
            run_id=self._ids.new_id("run"),
            user_id=user_id,
            request_text=request_text,
            inbox_fixture_id=inbox_fixture_id,
            mode=mode,
            status=RunStatus.AWAITING_MANDATE,
            mandate=draft_mandate(request_text),
            started_at=self._clock.now_iso(),
        )
        self._store.put(run)
        return run

    def confirm_mandate(self, run_id: str, mandate: Mandate) -> Run:
        """Accept the user's edited mandate and let the run proceed."""
        run = self._store.get(run_id)
        if run is None:
            raise NotFound("no such run")

        check_transition(RUN_TRANSITIONS, run.status, RunStatus.RUNNING)
        run.mandate = mandate
        run.status = RunStatus.RUNNING
        self._store.put(run)
        return run

    def complete(self, run_id: str, counts: dict[str, int]) -> Run:
        run = self._store.get(run_id)
        if run is None:
            raise NotFound("no such run")

        check_transition(RUN_TRANSITIONS, run.status, RunStatus.COMPLETED)
        run.status = RunStatus.COMPLETED
        run.counts = counts
        run.completed_at = self._clock.now_iso()
        self._store.put(run)
        return run

    def get(self, run_id: str) -> Run:
        run = self._store.get(run_id)
        if run is None:
            raise NotFound("no such run")
        return run

    def require_running(self, run_id: str) -> Run:
        """Fetch a run that is allowed to act.

        A run still awaiting its mandate must not be able to reach a consequential tool,
        which would be a way to act before the user agreed to the scope.
        """
        run = self.get(run_id)
        if run.status is not RunStatus.RUNNING:
            raise Conflict(f"run is {run.status}, not RUNNING")
        if run.mandate is None:
            raise Conflict("run has no confirmed mandate")
        return run
