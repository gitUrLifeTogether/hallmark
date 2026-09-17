"""Refuse commits that mention the private working spec.

The spec this project is built from is a private document. It is never committed, so any
reference to it inside the repository is a dangling pointer for anyone else reading the
code: they cannot open the thing being cited. Design decisions are recorded inline in
docs/ instead.

Two patterns are rejected:

* the spec's filename, in any casing, and
* bare section markers like "s0.0.1" written with the section sign, which name no file
  but plainly refer to a document that is not here.

Run by pre-commit on staged files. Exit code 1 blocks the commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SPEC_FILENAME = re.compile(r"claude\.md", re.IGNORECASE)
SECTION_MARKER = re.compile(r"§\s*\d")

#: This checker necessarily contains the patterns it looks for.
SELF = Path(__file__).name


def offending_lines(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if SPEC_FILENAME.search(line) or SECTION_MARKER.search(line):
            hits.append((number, line.strip()))
    return hits


def main(argv: list[str]) -> int:
    failures: list[str] = []

    for name in argv:
        path = Path(name)
        if path.name == SELF or not path.is_file():
            continue
        for number, line in offending_lines(path):
            failures.append(f"  {path}:{number}: {line[:100]}")

    if failures:
        print("Reference to the private working spec found in:")
        print("\n".join(failures))
        print(
            "\nThe spec is not in this repository, so nobody reading the code can follow\n"
            "the pointer. Write the point out in full, or record it in docs/decisions.md."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
