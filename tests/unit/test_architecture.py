"""The layering rules, enforced rather than documented.

Hexagonal architecture only holds while nobody points a dependency outward, and that is
easy to do by accident: reaching for a convenient class in `adapters/` from an application
service compiles, passes every other test, and quietly couples the security kernel to
infrastructure. It happened once while wiring the event publisher, which is why this exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "hallmark"

#: What each layer is allowed to import from, innermost first.
ALLOWED: dict[str, set[str]] = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "application": {"domain", "ports", "application"},
    "adapters": {"domain", "ports", "application", "adapters", "config"},
    "baseline": {"domain", "ports", "application", "adapters", "baseline"},
    # The bench composes everything in order to measure it, so it carries the same
    # permissions as a composition root rather than those of an application service.
    "bench": {"domain", "ports", "application", "adapters", "baseline", "bench", "config"},
}

#: Modules that must not appear anywhere in the pure layers, whatever the import path.
FORBIDDEN_IN_PURE = {"boto3", "botocore", "strands", "ollama", "httpx", "cedarpy", "fastapi"}
PURE_LAYERS = ("domain", "ports")


def python_files(layer: str) -> list[Path]:
    return sorted((ROOT / layer).rglob("*.py"))


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_a_layer_only_imports_from_layers_at_or_below_it(layer: str) -> None:
    violations: list[str] = []

    for path in python_files(layer):
        for module in imported_modules(path):
            if not module.startswith("hallmark."):
                continue
            target = module.split(".")[1]
            if target not in ALLOWED[layer]:
                violations.append(f"{path.relative_to(ROOT.parent)} imports {module}")

    assert violations == [], "dependencies must point inward:\n  " + "\n  ".join(violations)


@pytest.mark.parametrize("layer", PURE_LAYERS)
def test_the_pure_layers_touch_no_infrastructure(layer: str) -> None:
    """The security kernel must be testable without Docker, a cloud or a model."""
    violations: list[str] = []

    for path in python_files(layer):
        for module in imported_modules(path):
            root_name = module.split(".")[0]
            if root_name in FORBIDDEN_IN_PURE:
                violations.append(f"{path.relative_to(ROOT.parent)} imports {module}")

    assert violations == [], "the pure layers must stay free of infrastructure:\n  " + "\n  ".join(
        violations
    )


def test_only_the_composition_roots_build_aws_clients() -> None:
    """Every client comes through the guarded factory, so none can reach real AWS."""
    offenders: list[str] = []

    for path in ROOT.rglob("*.py"):
        if path.name == "config.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "boto3.client(" in text or "boto3.resource(" in text:
            offenders.append(str(path.relative_to(ROOT.parent)))

    assert offenders == [], (
        "construct clients through local_boto3_client so the LOCAL_ONLY guard applies:\n  "
        + "\n  ".join(offenders)
    )
