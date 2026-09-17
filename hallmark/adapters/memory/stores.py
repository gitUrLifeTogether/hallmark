"""In-memory implementations of every storage port.

These are the adapters M1 runs on: the whole security kernel is exercised without Docker,
which keeps the test suite fast and makes the kernel provably free of infrastructure.
"""

from __future__ import annotations

import itertools
from typing import Any

from hallmark.application.approvals import PendingAction
from hallmark.domain.lineage import LineageEdge
from hallmark.domain.statuses import ApprovalStatus
from hallmark.domain.values import Labeled
from hallmark.ports.repositories import (
    InboxEmail,
    LedgerEntry,
    Vendor,
)
from hallmark.ports.stores import DecisionRecord


class InMemoryValueStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], Labeled[Any]] = {}

    def put(self, value: Labeled[Any]) -> None:
        self._values[(value.run_id, value.handle)] = value

    def get(self, run_id: str, handle: str) -> Labeled[Any] | None:
        return self._values.get((run_id, handle))


class InMemoryLineageStore:
    def __init__(self) -> None:
        self._edges: list[LineageEdge] = []

    def add_edge(self, edge: LineageEdge) -> None:
        self._edges.append(edge)

    def edges_for_run(self, run_id: str) -> list[LineageEdge]:
        return [edge for edge in self._edges if edge.run_id == run_id]


class InMemoryDecisionStore:
    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []

    def add(self, record: DecisionRecord) -> None:
        self._records.append(record)

    def for_run(self, run_id: str) -> list[DecisionRecord]:
        return [record for record in self._records if record.run_id == run_id]


class SequentialIdGenerator:
    """Deterministic ids, so tests and lineage snapshots are reproducible."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def new_handle(self) -> str:
        return f"h_{next(self._counter):06d}"

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{next(self._counter):06d}"


class FixedClock:
    def __init__(self, now: str = "2026-09-17T00:00:00Z") -> None:
        self._now = now

    def now_iso(self) -> str:
        return self._now


class InMemoryVendorRepository:
    def __init__(self, vendors: list[Vendor]) -> None:
        self._vendors = list(vendors)

    def by_gstin(self, gstin: str) -> Vendor | None:
        target = gstin.strip().upper()
        return next((v for v in self._vendors if v.gstin.upper() == target), None)

    def by_id(self, vendor_id: str) -> Vendor | None:
        return next((v for v in self._vendors if v.vendor_id == vendor_id), None)

    def all_vendors(self) -> list[Vendor]:
        return list(self._vendors)


class InMemoryLedgerRepository:
    def __init__(self, entries: list[LedgerEntry] | None = None) -> None:
        self._entries = list(entries or [])

    def has_invoice(self, vendor_id: str, invoice_number: str) -> bool:
        target = invoice_number.strip().upper()
        return any(
            entry.vendor_id == vendor_id
            and entry.invoice_number.upper() == target
            and entry.status in {"SETTLED", "PENDING"}
            for entry in self._entries
        )

    def record(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)


class InMemoryInboxRepository:
    def __init__(self, emails: list[InboxEmail]) -> None:
        self._emails = list(emails)

    def list_emails(self) -> list[InboxEmail]:
        return list(self._emails)

    def get(self, email_id: str) -> InboxEmail | None:
        return next((e for e in self._emails if e.email_id == email_id), None)


class InMemoryApprovalStore:
    """Approvals in memory, with the same conditional transition as the real store."""

    def __init__(self) -> None:
        self._actions: dict[str, PendingAction] = {}

    def put(self, action: PendingAction) -> None:
        self._actions[action.approval_id] = action

    def get(self, approval_id: str) -> PendingAction | None:
        return self._actions.get(approval_id)

    def pending(self) -> list[PendingAction]:
        return [a for a in self._actions.values() if a.status is ApprovalStatus.PENDING]

    def transition(
        self,
        approval_id: str,
        expected: ApprovalStatus,
        target: ApprovalStatus,
        by: str,
        at: str,
    ) -> bool:
        """Move only if still in `expected`, mirroring a conditional write."""
        action = self._actions.get(approval_id)
        if action is None or action.status is not expected:
            return False
        action.status = target
        action.decided_by = by
        action.decided_at = at
        return True
