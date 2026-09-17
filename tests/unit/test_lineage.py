"""The audit trail has to answer "why was this blocked?" without hand-waving."""

from __future__ import annotations

from hallmark.domain.labels import Confidentiality, Source, ValueType
from hallmark.domain.lineage import EdgeKind, LineageEdge, LineageGraph
from hallmark.domain.values import Labeled, derive


def leaf(handle: str, source: Source) -> Labeled[str]:
    return Labeled(
        handle=handle,
        value="x",
        vtype=ValueType.FREE_TEXT,
        sources=frozenset({source}),
        confidentiality=Confidentiality.INTERNAL,
        run_id="run-1",
    )


def test_a_blocked_payment_traces_back_to_the_email_it_came_from() -> None:
    """The chain the console draws: decision, argument, extraction, original message."""
    graph = LineageGraph()
    email = leaf("h_email", Source.EXTERNAL_EMAIL)
    account = derive(
        "h_account", "889900771234", ValueType.ACCOUNT_NUMBER, [email], "reader_extract", "run-1"
    )

    graph.add(
        LineageEdge("e1", "run-1", email.handle, account.handle, EdgeKind.DERIVE, "reader_extract")
    )
    graph.add(LineageEdge("e2", "run-1", account.handle, "dec_1", EdgeKind.ARG, "account"))

    ancestors = graph.ancestors_of("dec_1")
    assert {edge.source_handle for edge in ancestors} == {"h_account", "h_email"}
    assert graph.root_sources("dec_1") == {"h_email"}


def test_selection_edges_are_recorded_separately_from_derivation() -> None:
    """A trusted record chosen using untrusted input keeps that fact visible."""
    graph = LineageGraph()
    graph.add(LineageEdge("e1", "run-1", "h_gstin", "h_vendor", EdgeKind.SELECTION, "gstin"))

    edges = graph.parents_of("h_vendor")
    assert len(edges) == 1
    assert edges[0].kind is EdgeKind.SELECTION


def test_traversal_terminates_on_a_cycle() -> None:
    """A corrupted store should not hang the console."""
    graph = LineageGraph()
    graph.add(LineageEdge("e1", "run-1", "a", "b", EdgeKind.DERIVE))
    graph.add(LineageEdge("e2", "run-1", "b", "a", EdgeKind.DERIVE))

    assert len(graph.ancestors_of("a")) == 2


def test_an_unknown_handle_has_no_ancestors() -> None:
    assert LineageGraph().ancestors_of("h_nothing") == []
