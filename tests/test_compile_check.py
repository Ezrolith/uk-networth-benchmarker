"""
Tests for scripts/compile_check.py — the CI compile-check helper itself.

If this script silently fails to detect a syntax error, the deploy safety
net loses one layer. So we verify it actually catches a bad file by
writing a temp file with a deliberate SyntaxError and running the script.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compile_check.py"


def test_compile_check_passes_on_clean_tree():
    """The current project tree should compile cleanly (sanity check)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "compile cleanly" in result.stdout


def test_compile_check_detects_syntax_error():
    """
    Place a deliberately broken .py file at the project root, run the script,
    and verify it exits 1 with a useful error message.
    """
    bad_file = ROOT / "_temp_broken_for_test.py"
    try:
        # SyntaxError: unbalanced parens
        bad_file.write_text("def broken(:\n    pass\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 but got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "_temp_broken_for_test.py" in result.stdout
        assert "Compile errors" in result.stdout
    finally:
        # Always clean up — even if the assertions above fail
        if bad_file.exists():
            bad_file.unlink()


def test_compile_check_skips_cache_dirs():
    """
    A broken .py file inside __pycache__ or .pytest_cache must NOT trigger
    a failure (those are tooling-managed and we don't author them).
    """
    cache_dir = ROOT / "__pycache__"
    cache_dir.mkdir(exist_ok=True)
    bad_file = cache_dir / "_temp_broken_in_cache.py"
    try:
        bad_file.write_text("def broken(:\n    pass\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, cwd=ROOT,
        )
        # Should still pass — the cache file is skipped
        assert result.returncode == 0, (
            f"Cache file caused failure: stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    finally:
        if bad_file.exists():
            bad_file.unlink()
