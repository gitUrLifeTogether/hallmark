"""The audit trail: how every value and decision came to be.

Each labeled value is a node, each parent relation an edge, and every enforcement
decision a node linked to the arguments it judged. Asking "why was this blocked?" is
then a graph walk, not a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EdgeKind(StrEnum):
    """Why one node points at another."""

    DERIVE = "derive"
    #: An untrusted key chose which trusted record got loaded. The record is trusted, but
    #: the *choice* was influenced, so it is recorded separately rather than hidden.
    SELECTION = "selection"
    ARG = "arg"
    DECISION = "decision"


@dataclass(frozen=True)
class LineageEdge:
    """A directed edge from one handle to another."""

    edge_id: str
    run_id: str
    source_handle: str
    target_handle: str
    kind: EdgeKind
    label: str = ""


@dataclass
class LineageGraph:
    """An in-memory graph supporting ancestor queries."""

    edges: list[LineageEdge] = field(default_factory=list)

    def add(self, edge: LineageEdge) -> None:
        self.edges.append(edge)

    def parents_of(self, handle: str) -> list[LineageEdge]:
        return [edge for edge in self.edges if edge.target_handle == handle]

    def ancestors_of(self, handle: str) -> list[LineageEdge]:
        """Every edge reachable backwards from `handle`.

        Traversal is cycle-safe; provenance graphs are acyclic by construction, but a
        corrupted store should not hang the console.
        """
        seen: set[str] = set()
        collected: list[LineageEdge] = []
        frontier = [handle]

        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            for edge in self.parents_of(current):
                collected.append(edge)
                frontier.append(edge.source_handle)

        return collected

    def root_sources(self, handle: str) -> set[str]:
        """Handles with no parents that `handle` ultimately derives from."""
        ancestors = self.ancestors_of(handle)
        candidates = {edge.source_handle for edge in ancestors}
        return {item for item in candidates if not self.parents_of(item)}
