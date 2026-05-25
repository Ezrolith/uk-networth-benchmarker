"""
Smoke test for the top-level import chain in app.py.

The deployment incident on 2026-05-25 was an ImportError on Streamlit Cloud
that local development couldn't see because the test suite only exercised
utils + charts in isolation. This test imports every name app.py imports
in the order it imports them — so if app.py picks up a name that doesn't
exist in the target module (or vice versa), CI catches it before deploy.

It does NOT exercise Streamlit itself or render anything — just the import
chain. That's by design: it must work in CI without a display server.
"""
from __future__ import annotations
import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_charts_package_imports_cleanly():
    """All charts.* modules import without error and expose their builders."""
    # Force a fresh import (in case a previous test cached an older version)
    for mod in list(sys.modules):
        if mod.startswith("charts"):
            del sys.modules[mod]

    import charts  # noqa: F401
    expected = {
        "build_main_figure", "build_asset_class_chart", "build_heatmap",
        "build_distribution_chart", "build_gains_chart", "build_velocity_chart",
        "build_cumulative_chart", "build_percentile_chart",
        "build_whatif_figure", "build_monte_carlo_chart",
        "fmt", "fmt_delta", "clean_note", "safe_cagr",
        "hover_template", "best_gain",
    }
    actual = set(dir(charts))
    missing = expected - actual
    assert not missing, f"charts/__init__.py missing exports: {sorted(missing)}"


def test_utils_uk_tax_exports_all_names_used_by_app():
    """
    The exact import block from app.py — if any name is missing, this test
    fails IN CI BEFORE the deploy hits the user. The 2026-05-25 deployment
    incident was caused by this kind of mismatch slipping through.
    """
    for mod in list(sys.modules):
        if mod.startswith("utils"):
            del sys.modules[mod]

    from utils.uk_tax import (  # noqa: F401
        tapered_pension_allowance, effective_pension_allowance,
        isa_remaining, lisa_remaining, pension_relief_estimate, lisa_bonus,
        iht_payable, IHT_BANDS, IHT_STANDARD_RATE,
        ISA_ALLOWANCE, LISA_ALLOWANCE, PENSION_AA, TAPER_THRESHOLD,
    )

    # Sanity: the imported callables actually work
    aa, _ = tapered_pension_allowance(0)
    assert aa == PENSION_AA
    assert iht_payable(0, IHT_BANDS["single"])[1] == 0


def test_utils_monte_carlo_exports_all_names_used_by_app():
    """Same defensive test for utils.monte_carlo."""
    for mod in list(sys.modules):
        if mod.startswith("utils"):
            del sys.modules[mod]

    from utils.monte_carlo import (  # noqa: F401
        run_monte_carlo, probability_of_reaching,
    )


def test_utils_data_loader_exports_all_names_used_by_app():
    """Defensive test for utils.data_loader."""
    for mod in list(sys.modules):
        if mod.startswith("utils"):
            del sys.modules[mod]

    from utils.data_loader import (  # noqa: F401
        load_was_data, load_asset_class_data,
        parse_personal_csv, encode_personal_data, decode_personal_data,
    )


def test_utils_inference_exports_all_names_used_by_app():
    """Defensive test for utils.inference."""
    for mod in list(sys.modules):
        if mod.startswith("utils"):
            del sys.modules[mod]

    from utils.inference import (  # noqa: F401
        interpolate_benchmarks, convert_to_individual, apply_gender_adjustment,
        adjust_for_inflation, cpi_adjust_personal,
        estimate_percentile, estimate_exact_percentile,
        build_percentile_trajectory, derive_tail_percentiles,
        build_asset_class_series, build_decile_table, apply_component_filter,
        DATA_YEAR, REAL_BASE_YEAR, UK_CPI,
    )


def test_app_imports_block_resolves():
    """
    The ultimate guard: actually parse app.py's top-level imports and check
    that every name resolves. This catches any future drift between app.py
    and the underlying modules — the exact failure mode of the 2026-05-25
    deployment incident.

    Doesn't execute app.py (which would launch Streamlit) — just resolves
    the import statements at the top of the file.
    """
    import ast

    with open(ROOT / "app.py", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    failures = []

    for node in tree.body:
        # Only check module-level ImportFrom of project modules
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module is None:
            continue
        if not (node.module.startswith("charts") or node.module.startswith("utils")):
            continue

        # Try the import
        try:
            mod = importlib.import_module(node.module)
        except ImportError as e:
            failures.append(f"{node.module}: {e}")
            continue

        # Verify each imported name exists on the module
        for alias in node.names:
            if not hasattr(mod, alias.name):
                failures.append(f"{node.module}.{alias.name} (line {node.lineno})")

    assert not failures, (
        "app.py imports names that don't exist in target modules:\n  "
        + "\n  ".join(failures)
    )
