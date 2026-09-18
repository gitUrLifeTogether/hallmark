"""The domain event seam.

Events carry handles, enums and policy ids, never values. The console renders them live,
and anything derived from untrusted content would otherwise reach a browser with no
provenance attached to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class EventType(StrEnum):
    """The fixed vocabulary of things worth telling the console about."""

    RUN_REQUESTED = "RunRequested"
    RUN_STARTED = "RunStarted"
    MANDATE_DRAFTED = "MandateDrafted"
    MANDATE_CONFIRMED = "MandateConfirmed"
    TOOL_CALLED = "ToolCalled"
    VALUE_CREATED = "ValueCreated"
    READER_EXTRACTED = "ReaderExtracted"
    FIELD_REJECTED = "FieldRejected"
    POLICY_EVALUATED = "PolicyEvaluated"
    ACTION_EXECUTED = "ActionExecuted"
    ACTION_PENDING = "ActionPending"
    ACTION_HARD_DENIED = "ActionHardDenied"
    APPROVAL_REQUESTED = "ApprovalRequested"
    APPROVAL_DECIDED = "ApprovalDecided"
    REVIEW_OPENED = "ReviewOpened"
    RUN_COMPLETED = "RunCompleted"


@dataclass(frozen=True)
class DomainEvent:
    """One thing that happened, in a shape the console can render directly."""

    type: EventType
    run_id: str
    at: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventPublisher(Protocol):
    """Publishes domain events. Never blocks a decision."""

    def publish(self, event: DomainEvent) -> None: ...


class RecordingEventPublisher:
    """A publisher that keeps events in memory and sends them nowhere.

    Lives beside the port rather than in `adapters/` on purpose. The enforcement point
    needs a default for runs with no console attached, and importing an adapter to get one
    would point a dependency outward. It has no I/O, so it belongs on this side of the
    boundary.
    """

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)

    def of_type(self, event_type: EventType | str) -> list[DomainEvent]:
        return [e for e in self.events if str(e.type) == str(event_type)]
