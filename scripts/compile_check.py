"""
py_compile every .py file under the project root.

Used by `make compile` and the CI workflow to ensure no syntax errors slip
through. Walks the whole tree so new modules are picked up automatically
without anyone having to remember to update a list.

Skips __pycache__ and .pytest_cache; everything else is fair game.
"""
from __future__ import annotations
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", "venv", ".venv"}


def main() -> int:
    errors: list[str] = []
    checked = 0

    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        checked += 1
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{p.relative_to(ROOT)}: {e.msg}")

    if errors:
        print(f"Compile errors in {len(errors)} of {checked} files:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"All {checked} .py files compile cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
