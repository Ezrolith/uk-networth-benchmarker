"""
Defensive test: every third-party import in the codebase has a matching
entry in requirements.txt.

Catches the failure mode where someone adds `import foo` to a new module
but forgets to add `foo>=x.y` to requirements.txt — the local dev box has
foo from some other project, the test suite passes, but Streamlit Cloud
crashes on cold start because pip didn't install it.
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

# All Python stdlib top-level modules (Python 3.10+ provides this directly).
# Using sys.stdlib_module_names avoids maintaining a hand-rolled allowlist
# that drifts every time a test imports a new stdlib module (caught e.g.
# the missing 'subprocess' which broke the suite on its first introduction).
STDLIB = set(sys.stdlib_module_names) | {"__future__"}

# Project modules (imports of our own code shouldn't need a pip package)
PROJECT_PACKAGES = {"app", "charts", "utils", "tests", "scripts", "data"}

# Map of import name -> requirements.txt entry name (when they differ)
IMPORT_TO_REQUIREMENTS = {
    "fpdf": "fpdf2",     # the package is fpdf2 but imports as fpdf
}


def _scan_imports(py_files: list[Path]) -> set[str]:
    """
    Return the set of top-level third-party packages imported anywhere.

    Skips relative imports (e.g. `from ._helpers import fmt` inside the charts
    package) since those are project-internal and don't need a pip entry.
    """
    imports: set[str] = set()
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                # Skip relative imports (node.level > 0)
                if node.level and node.level > 0:
                    continue
                if node.module:
                    imports.add(node.module.split(".")[0])
    return imports


def _read_requirements() -> set[str]:
    """Parse requirements.txt → set of normalised package names."""
    raw = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    packages: set[str] = set()
    for line in raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip version pin (>=, ==, ~=, etc.)
        name = line.split(">")[0].split("=")[0].split("<")[0].split("~")[0]
        name = name.strip().lower()
        if name:
            packages.add(name)
    return packages


@pytest.fixture(scope="module")
def project_imports() -> set[str]:
    py_files = (
        [ROOT / "app.py"]
        + list((ROOT / "charts").glob("*.py"))
        + list((ROOT / "utils").glob("*.py"))
    )
    return _scan_imports(py_files)


@pytest.fixture(scope="module")
def declared_requirements() -> set[str]:
    return _read_requirements()


def test_every_third_party_import_is_in_requirements(project_imports, declared_requirements):
    """Every non-stdlib, non-project import must be declared in requirements.txt."""
    third_party = {
        IMPORT_TO_REQUIREMENTS.get(imp, imp).lower()
        for imp in project_imports
        if imp not in STDLIB and imp not in PROJECT_PACKAGES
    }
    missing = third_party - declared_requirements
    assert not missing, (
        f"requirements.txt is missing packages used in the code: {sorted(missing)}\n"
        f"Either add them to requirements.txt or, if the import shouldn't be there, remove it."
    )


def test_requirements_includes_known_essentials(declared_requirements):
    """A sanity check: the 6 packages we KNOW are required must be listed."""
    essentials = {"streamlit", "plotly", "pandas", "numpy", "scipy", "matplotlib", "fpdf2"}
    missing = essentials - declared_requirements
    assert not missing, (
        f"requirements.txt is missing essential packages: {sorted(missing)}"
    )


def test_requirements_file_is_well_formed():
    """Each non-blank, non-comment line should parse as `package[op][version]`."""
    raw = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(raw, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Should have a name and optionally a version specifier
        first_char_is_alpha = line[0].isalpha() or line[0] == "_"
        assert first_char_is_alpha, (
            f"requirements.txt line {i}: '{line}' doesn't start with a package name"
        )


def test_test_files_dont_pull_in_undeclared_third_party_deps():
    """
    Test files can use pytest (always available in dev) but shouldn't import
    anything else that isn't in requirements.txt — otherwise CI on a clean
    box would fail. Pytest itself is the only allowed exception.
    """
    test_files = list((ROOT / "tests").glob("test_*.py"))
    imports = _scan_imports(test_files)
    declared = _read_requirements() | {"pytest"}  # pytest installed by CI step
    third_party = {
        IMPORT_TO_REQUIREMENTS.get(imp, imp).lower()
        for imp in imports
        if imp not in STDLIB and imp not in PROJECT_PACKAGES
    }
    missing = third_party - declared
    assert not missing, (
        f"Test files use packages not in requirements.txt (or 'pytest'): {sorted(missing)}"
    )
