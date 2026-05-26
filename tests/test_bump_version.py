"""Tests for scripts/bump_version.py — the release-version bumper."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bump_version.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    """Run bump_version.py with the given args and return the result."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_no_args_shows_current_version():
    """With no args, the script should print 'Current version: vN.N'."""
    result = _run()
    assert result.returncode == 0
    assert "Current version:" in result.stdout


def test_dry_run_doesnt_modify_files():
    """--dry should show planned changes without writing."""
    app_py = ROOT / "app.py"
    pyproject = ROOT / "pyproject.toml"
    before = (app_py.read_bytes(), pyproject.read_bytes())

    result = _run("9.9", "--dry")
    assert result.returncode == 0
    assert "would change" in result.stdout
    assert "Dry run" in result.stdout

    after = (app_py.read_bytes(), pyproject.read_bytes())
    assert before == after, "--dry must not write any files"


def test_invalid_version_format_rejected():
    """Non-semver input like 'banana' or '2' should be rejected."""
    for bad in ("banana", "2", "v2.7", "2.7.x"):
        result = _run(bad)
        assert result.returncode == 2, f"expected rejection of {bad!r}, got rc={result.returncode}"
        assert "Invalid version" in result.stderr


def test_same_version_is_noop():
    """If the supplied version equals the current one, the script no-ops."""
    # First find current version
    current_result = _run()
    # Output looks like "Current version: v2.6\n"
    current = current_result.stdout.strip().split("v")[-1]
    # Try to "bump" to the same version
    result = _run(current)
    assert result.returncode == 0
    assert "Already at" in result.stdout


def test_accepts_three_part_semver():
    """Format 'N.N.N' should also be valid (dry-run only)."""
    result = _run("2.7.1", "--dry")
    assert result.returncode == 0
    assert "would change" in result.stdout
