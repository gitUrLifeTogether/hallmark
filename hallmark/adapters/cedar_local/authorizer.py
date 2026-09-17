"""Cedar evaluated in-process via cedarpy.

Policy `@id` annotations are the stable names used in results, tests and the console, so
they are parsed out of the policy text and matched back onto whatever cedarpy reports as
the determining policies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import cedarpy

from hallmark.ports.authorizer import AuthzRequest, Decision

_ID_ANNOTATION: Final = re.compile(r'@id\("([^"]+)"\)')


def load_policy_text(policy_dir: Path) -> str:
    """Concatenate every `.cedar` file in a directory, in a stable order."""
    files = sorted(policy_dir.glob("*.cedar"))
    if not files:
        raise FileNotFoundError(f"no .cedar policies found in {policy_dir}")
    return "\n\n".join(path.read_text(encoding="utf-8") for path in files)


def policy_ids_in_order(policy_text: str) -> list[str]:
    """The `@id` names, in the order the policies appear."""
    return _ID_ANNOTATION.findall(policy_text)


class CedarLocalAuthorizer:
    """Evaluates requests against the policy set held in memory."""

    def __init__(self, policy_text: str) -> None:
        self._policy_text = policy_text
        self._ids = policy_ids_in_order(policy_text)

    @classmethod
    def from_directory(cls, policy_dir: Path) -> CedarLocalAuthorizer:
        return cls(load_policy_text(policy_dir))

    def _resolve_policy_names(self, diagnostics: Any) -> tuple[str, ...]:
        """Turn cedarpy's internal policy ids into our `@id` names.

        cedarpy reports positional ids like `policy0` and separately offers the `@id`
        annotation for each. Falling back to the raw id keeps an unannotated policy
        visible in a decision rather than silently dropping it.
        """
        reasons = getattr(diagnostics, "reasons", None) or []
        annotations = getattr(diagnostics, "id_annotations_by_reason", None) or {}
        names = [str(annotations.get(reason, reason)) for reason in reasons]
        return tuple(dict.fromkeys(names))

    def is_authorized(self, request: AuthzRequest) -> Decision:
        payload = {
            "principal": request.principal,
            "action": request.action,
            "resource": request.resource,
            "context": request.context,
        }
        result = cedarpy.is_authorized(payload, self._policy_text, request.entities)

        allow = result.decision == cedarpy.Decision.Allow
        diagnostics = getattr(result, "diagnostics", None)
        errors = tuple(str(e) for e in (getattr(diagnostics, "errors", None) or []))

        return Decision(
            allow=allow,
            determining_policies=self._resolve_policy_names(diagnostics),
            errors=errors,
        )
