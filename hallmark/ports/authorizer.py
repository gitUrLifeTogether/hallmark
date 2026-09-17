"""The authorization seam.

Keeping this a Protocol is what lets the same `.cedar` files be evaluated in-process today
and by a hosted policy service later without the enforcement code noticing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AuthzRequest:
    """One question for the policy engine."""

    principal: str
    action: str
    resource: str
    context: dict[str, Any] = field(default_factory=dict)
    entities: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    """The answer, plus which policies drove it."""

    allow: bool
    determining_policies: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class Authorizer(Protocol):
    """Evaluates an `AuthzRequest` against the policy set."""

    def is_authorized(self, request: AuthzRequest) -> Decision: ...
