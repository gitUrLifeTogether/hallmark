"""Property tests for the rule that labels only ever join.

A worked example can only show that the cases someone thought of behave. These generate
arbitrary derivation trees and assert the guarantee holds across all of them, which is
the closest thing to a proof this codebase can run in CI.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from hallmark.domain.labels import (
    TRUSTED_SOURCES,
    Confidentiality,
    Source,
    ValueType,
    is_trusted,
    max_confidentiality,
)
from hallmark.domain.values import Labeled, derive

sources = st.sampled_from(list(Source))
source_sets = st.frozensets(sources, min_size=1, max_size=4)
confidentialities = st.sampled_from(list(Confidentiality))


def make_leaf(index: int, srcs: frozenset[Source], conf: Confidentiality) -> Labeled[Any]:
    return Labeled(
        handle=f"h_{index}",
        value=index,
        vtype=ValueType.FREE_TEXT,
        sources=srcs,
        confidentiality=conf,
        run_id="run-1",
    )


leaves = st.builds(
    make_leaf,
    st.integers(min_value=0, max_value=999),
    source_sets,
    confidentialities,
)


@given(st.lists(leaves, min_size=1, max_size=6))
def test_derived_sources_are_exactly_the_union_of_inputs(inputs: list[Labeled[Any]]) -> None:
    result = derive("h_out", 1, ValueType.FREE_TEXT, inputs, "join", "run-1")
    expected: set[Source] = set()
    for item in inputs:
        expected |= item.sources
    assert result.sources == frozenset(expected)


@given(st.lists(leaves, min_size=1, max_size=6))
def test_a_derived_value_never_loses_a_source(inputs: list[Labeled[Any]]) -> None:
    result = derive("h_out", 1, ValueType.FREE_TEXT, inputs, "join", "run-1")
    for item in inputs:
        assert item.sources <= result.sources


@given(st.lists(leaves, min_size=1, max_size=6))
def test_trusted_output_implies_every_input_was_trusted(inputs: list[Labeled[Any]]) -> None:
    """The guarantee: nothing untrusted can be laundered into a trusted value."""
    result = derive("h_out", 1, ValueType.FREE_TEXT, inputs, "join", "run-1")
    if result.trusted:
        assert all(item.trusted for item in inputs)


@given(st.lists(leaves, min_size=1, max_size=6))
def test_one_untrusted_input_taints_the_result(inputs: list[Labeled[Any]]) -> None:
    result = derive("h_out", 1, ValueType.FREE_TEXT, inputs, "join", "run-1")
    if any(not item.trusted for item in inputs):
        assert not result.trusted


@given(st.lists(leaves, min_size=1, max_size=6))
def test_confidentiality_never_decreases(inputs: list[Labeled[Any]]) -> None:
    result = derive("h_out", 1, ValueType.FREE_TEXT, inputs, "join", "run-1")
    assert result.confidentiality == max_confidentiality(i.confidentiality for i in inputs)


@given(st.lists(leaves, min_size=1, max_size=4), st.lists(leaves, min_size=1, max_size=4))
def test_deriving_twice_still_carries_the_original_sources(
    first: list[Labeled[Any]], second: list[Labeled[Any]]
) -> None:
    """Labels survive being passed through several steps, not just one."""
    middle = derive("h_mid", 1, ValueType.FREE_TEXT, first, "join", "run-1")
    final = derive("h_out", 2, ValueType.FREE_TEXT, [middle, *second], "join", "run-1")
    for item in first:
        assert item.sources <= final.sources


@given(source_sets)
def test_trust_requires_every_source_to_be_company_controlled(srcs: frozenset[Source]) -> None:
    assert is_trusted(srcs) == (srcs <= TRUSTED_SOURCES)


def test_a_value_with_no_provenance_is_not_trusted() -> None:
    """Unknown provenance reads as untrusted, because a bug must not grant trust."""
    assert is_trusted(frozenset()) is False


@given(st.lists(leaves, min_size=1, max_size=5))
def test_reader_output_is_never_trusted(inputs: list[Labeled[Any]]) -> None:
    """Anything a model produced carries MODEL_READER, which is not a trusted source."""
    result = derive(
        "h_out",
        1,
        ValueType.FREE_TEXT,
        inputs,
        "reader_extract",
        "run-1",
        extra_sources=frozenset({Source.MODEL_READER}),
    )
    assert Source.MODEL_READER in result.sources
    assert not result.trusted
