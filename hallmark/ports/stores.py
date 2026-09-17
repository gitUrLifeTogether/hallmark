"""Storage and infrastructure seams.

The planner never touches these. Only tool wrappers resolve handles to values, which is
what keeps untrusted content out of the planner's context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from hallmark.domain.lineage import LineageEdge
from hallmark.domain.values import Labeled


class ValueStore(Protocol):
    """Holds labeled values; hands them back by handle."""

    def put(self, value: Labeled[Any]) -> None: ...
    def get(self, run_id: str, handle: str) -> Labeled[Any] | None: ...


class LineageStore(Protocol):
    """Records nodes and edges of the provenance graph."""

    def add_edge(self, edge: LineageEdge) -> None: ...
    def edges_for_run(self, run_id: str) -> list[LineageEdge]: ...


@dataclass
class DecisionRecord:
    """One enforcement decision, kept for the audit trail and the console."""

    decision_id: str
    run_id: str
    tool: str
    args_handles: dict[str, str]
    facts: dict[str, Any]
    allow: bool
    outcome: str
    determining_policies: tuple[str, ...] = ()
    reason_code: str = "OK"
    latency_ms: int = 0
    created_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class DecisionStore(Protocol):
    """Holds decisions for a run."""

    def add(self, record: DecisionRecord) -> None: ...
    def for_run(self, run_id: str) -> list[DecisionRecord]: ...


class IdGenerator(Protocol):
    """Makes handles and ids. A seam so tests can be deterministic."""

    def new_handle(self) -> str: ...
    def new_id(self, prefix: str) -> str: ...


class Clock(Protocol):
    """Supplies the current time as an ISO-8601 string."""

    def now_iso(self) -> str: ...
