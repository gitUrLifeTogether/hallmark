"""Labeled values and the single function allowed to derive one from others.

`derive` is the only way a new value comes into existence from existing ones, which is
what makes the provenance guarantee auditable: every value's sources are the union of its
parents' sources, computed in one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hallmark.domain.labels import (
    Confidentiality,
    Source,
    ValueType,
    is_trusted,
    join_sources,
    max_confidentiality,
)


@dataclass(frozen=True)
class Labeled[T]:
    """A value carrying where it came from.

    `declassified` controls only whether the planner may see `display`. It never affects
    `sources`: being allowed to look at a number does not make the number trustworthy.
    """

    handle: str
    value: T
    vtype: ValueType
    sources: frozenset[Source]
    confidentiality: Confidentiality
    run_id: str
    op: str = "ingest"
    parents: tuple[str, ...] = ()
    declassified: bool = False
    display: str | None = None
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def trusted(self) -> bool:
        """True only if every source is company-controlled."""
        return is_trusted(self.sources)

    def redacted(self) -> str:
        """A form safe to log: handle and labels, never the value itself."""
        tags = ",".join(sorted(self.sources))
        return f"<{self.handle} {self.vtype} sources={tags} trusted={self.trusted}>"


def derive[T](
    handle: str,
    value: T,
    vtype: ValueType,
    inputs: Sequence[Labeled[Any]],
    op: str,
    run_id: str,
    created_at: str = "",
    extra_sources: frozenset[Source] | None = None,
) -> Labeled[T]:
    """Build a new labeled value from existing ones, joining their labels.

    `extra_sources` exists for operations that add provenance of their own rather than
    just passing it through. The reader uses it to stamp MODEL_READER onto everything it
    produces, so a value that passed through a manipulable model says so forever.
    """
    sources = join_sources([item.sources for item in inputs])
    if extra_sources:
        sources = sources | extra_sources

    return Labeled(
        handle=handle,
        value=value,
        vtype=vtype,
        sources=sources,
        confidentiality=max_confidentiality([item.confidentiality for item in inputs]),
        run_id=run_id,
        op=op,
        parents=tuple(item.handle for item in inputs),
        created_at=created_at,
    )
