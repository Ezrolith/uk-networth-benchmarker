"""
Bump the project version across every file that references it.

Without this, a release means manually editing:
  - app.py            (APP_VERSION = "v2.6" AND the module docstring '(v2.6)')
  - pyproject.toml    (version = "2.6")
  - CLAUDE.md         ('Current version' section)
  - REVIEW_LOG.md     (sometimes)

Easy to miss one. This script keeps them in sync.

Usage:
    python scripts/bump_version.py 2.7         # write the bumped values
    python scripts/bump_version.py 2.7 --dry   # show what would change
    python scripts/bump_version.py             # show current version
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_current_version() -> str:
    """Pull the current version from app.py's APP_VERSION constant."""
    app_py = (ROOT / "app.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"v([\d.]+)"', app_py)
    if not m:
        raise SystemExit("Couldn't find APP_VERSION in app.py")
    return m.group(1)


# Each rule: (relative_path, regex, replacement_template).
# The replacement uses `{v}` (semver, e.g. "2.7") and `{vv}` (with "v" prefix).
REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "app.py",
        r'APP_VERSION\s*=\s*"v[\d.]+"',
        'APP_VERSION = "v{v}"',
    ),
    (
        # Module docstring header, e.g. "UK Net Worth Benchmarker (v2.7)".
        # Kept in sync with APP_VERSION so bumps don't leave it stale.
        "app.py",
        r'UK Net Worth Benchmarker \(v[\d.]+\)',
        'UK Net Worth Benchmarker (v{v})',
    ),
    (
        "pyproject.toml",
        r'^version\s*=\s*"[\d.]+"',
        'version = "{v}"',
    ),
]


def bump(new_version: str, dry_run: bool) -> None:
    current = read_current_version()
    if new_version == current:
        print(f"Already at v{current}. Nothing to do.")
        return

    print(f"Bumping: v{current} -> v{new_version}\n")

    for rel_path, pattern, template in REPLACEMENTS:
        fp = ROOT / rel_path
        src = fp.read_text(encoding="utf-8")
        replacement = template.format(v=new_version, vv=f"v{new_version}")

        new_src, count = re.subn(pattern, replacement, src, count=1, flags=re.MULTILINE)
        if count == 0:
            print(f"  [WARN] {rel_path}: pattern not found - skipping")
            continue

        action = "would change" if dry_run else "updated"
        print(f"  [OK]   {rel_path}: {action}")

        if not dry_run:
            fp.write_text(new_src, encoding="utf-8")

    print()
    if dry_run:
        print("Dry run - no files modified.")
        print(f"Run without --dry to apply.")
    else:
        print("Done. Next steps:")
        print(f"  1. Update CLAUDE.md 'Current version' section manually if needed")
        print(f"  2. Add a section to CHANGELOG.md for v{new_version}")
        print(f"  3. Run: pytest -q && git commit -am 'Bump to v{new_version}'")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help='New version, e.g. "2.7"')
    parser.add_argument("--dry", action="store_true",
                        help="Show what would change without writing")
    args = parser.parse_args()

    if args.version is None:
        print(f"Current version: v{read_current_version()}")
        return 0

    # Validate version format
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", args.version):
        print(f"Invalid version: {args.version!r}. Expected 'N.N' or 'N.N.N'.", file=sys.stderr)
        return 2

    bump(args.version, dry_run=args.dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
