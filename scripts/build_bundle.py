"""Stage each function's deployment bundle.

SAM packages only what sits under a function's `CodeUri`, and the handlers import the
shared kernel. A Lambda layer is the tidier way to share it and is what the production
design would use, but the local emulator attaches a layer without making its contents
importable, so the shared packages are copied into each bundle instead. The template keeps
the layer definition alongside, so moving back is a one-line change once that works.

The Cedar policies travel with the code. They are the enforcement rules; a function
authorizing against a stale copy would be worse than one that fails to start.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = ROOT / ".bundle"

#: Handler directory -> bundle name.
FUNCTIONS = {"api": ROOT / "handlers" / "api"}

#: Shared packages every function needs.
SHARED = ("hallmark", "policies", "fixtures")

EXCLUDE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache", ".ruff_cache"
)


def _force_remove(func, path, _exc):
    """Clear the read-only bit and retry, which is what Windows usually needs."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path, attempts: int = 5) -> None:
    """Delete a directory, tolerating a sync client holding a handle open.

    A file sync client can hold a file briefly and make the delete fail. That matters more
    than it sounds: a failed rebuild leaves the previous bundle in place and the deploy
    then ships stale code while reporting success. Failing loudly here is the only way the
    caller learns the artifacts are not what they think.
    """
    for attempt in range(attempts):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onexc=_force_remove)
            return
        except (PermissionError, OSError):
            if attempt == attempts - 1:
                raise
            time.sleep(1.5)


def build_one(name: str, handler_dir: Path) -> int:
    target = BUNDLE_ROOT / name
    target.mkdir(parents=True)

    for item in handler_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, target / item.name)

    for package in SHARED:
        source = ROOT / package
        if not source.is_dir():
            print(f"missing source directory: {package}", file=sys.stderr)
            return 0
        shutil.copytree(source, target / package, ignore=EXCLUDE)

    return sum(1 for _ in target.rglob("*.py"))


def main() -> int:
    remove_tree(BUNDLE_ROOT)

    for name, handler_dir in FUNCTIONS.items():
        if not handler_dir.is_dir():
            print(f"missing handler directory: {handler_dir}", file=sys.stderr)
            return 1
        count = build_one(name, handler_dir)
        if count == 0:
            return 1
        print(f"staged bundle '{name}' with {count} python files")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
