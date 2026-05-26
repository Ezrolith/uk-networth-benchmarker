"""Tests for utils/summary.py — the summary statistics table builder."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.summary import build_summary_stats

# The `benchmark` fixture is provided by conftest.py — session-scoped so it's
# computed once for the whole test run rather than rebuilt per module.


@pytest.fixture
def history() -> pd.DataFrame:
    """A clean 5-year personal history with positive growth."""
    return pd.DataFrame({
        "year": [2020, 2021, 2022, 2023, 2024],
        "age":  [30.0, 31.0, 32.0, 33.0, 34.0],
        "net_worth": [25_000.0, 50_000.0, 80_000.0, 120_000.0, 180_000.0],
    })


# ──────────────────────────────────────────────────────────────────────────────

def test_empty_dataframe_returns_empty_result(benchmark):
    result = build_summary_stats(pd.DataFrame(columns=["age", "net_worth"]), benchmark)
    assert list(result.columns) == ["Metric", "Value"]
    assert len(result) == 0


def test_single_row_no_diff_metrics_no_pandas_warning(benchmark):
    """
    With only one data point, no diff-based metrics (best gain, worst single
    change) make sense — but the function shouldn't crash or emit a pandas
    FutureWarning either.
    """
    import warnings
    one = pd.DataFrame({"year": [2024], "age": [30.0], "net_worth": [50_000.0]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # turn warnings into errors
        result = build_summary_stats(one, benchmark)
    # Core rows still present
    metrics = result["Metric"].tolist()
    assert any("age range" in m for m in metrics)
    assert any("net worth range" in m for m in metrics)
    # Diff-based rows should NOT be present
    assert not any("worst single change" in m for m in metrics)
    assert not any("best single gain" in m for m in metrics)
    # CAGR shouldn't appear for a single point either
    assert not any("CAGR" in m for m in metrics)


def test_always_includes_three_core_rows(benchmark, history):
    """Age range, net worth range, total change should always appear."""
    result = build_summary_stats(history, benchmark)
    metrics = result["Metric"].tolist()
    assert any("age range" in m for m in metrics)
    assert any("net worth range" in m for m in metrics)
    assert any("total change" in m for m in metrics)


def test_label_prefixes_every_row(benchmark, history):
    """`label` should be the prefix on every Metric."""
    result = build_summary_stats(history, benchmark, label="Partner")
    for m in result["Metric"]:
        assert m.startswith("Partner —"), f"row missing 'Partner' prefix: {m}"


def test_includes_cagr_for_meaningful_growth(benchmark, history):
    """5-yr period with 7x growth should have a CAGR row."""
    result = build_summary_stats(history, benchmark)
    cagr_rows = result[result["Metric"].str.contains("CAGR")]
    assert len(cagr_rows) == 1
    # 25k -> 180k over 4 years = ~63% CAGR
    value = cagr_rows.iloc[0]["Value"]
    assert "+" in value and "%" in value


def test_omits_cagr_for_too_short_history(benchmark):
    """A history shorter than 0.5 years shouldn't get a CAGR row."""
    short = pd.DataFrame({
        "year": [2024, 2024],
        "age":  [30.0, 30.2],
        "net_worth": [25_000.0, 30_000.0],
    })
    result = build_summary_stats(short, benchmark)
    cagr_rows = result[result["Metric"].str.contains("CAGR")]
    assert len(cagr_rows) == 0


def test_best_single_gain_row(benchmark, history):
    """
    history diffs: 25k→50k=+25k, 50k→80k=+30k, 80k→120k=+40k, 120k→180k=+60k.
    Biggest gain is +£60k landing at age 34 (the row whose NW is 180k).
    """
    result = build_summary_stats(history, benchmark)
    best_row = result[result["Metric"].str.contains("best single gain")]
    assert len(best_row) == 1
    val = best_row.iloc[0]["Value"]
    assert "34" in val           # age at which the gain landed
    assert "60k" in val          # magnitude
    assert "+50%" in val         # % change (60k / 120k = 50%)


def test_worst_single_change_with_drop(benchmark):
    """A history that includes a drop should surface the worst-change row."""
    with_drop = pd.DataFrame({
        "year": [2020, 2021, 2022, 2023],
        "age":  [30.0, 31.0, 32.0, 33.0],
        "net_worth": [50_000.0, 80_000.0, 30_000.0, 60_000.0],   # 80k → 30k = -50k drop
    })
    result = build_summary_stats(with_drop, benchmark)
    worst_row = result[result["Metric"].str.contains("worst single change")]
    assert len(worst_row) == 1
    val = worst_row.iloc[0]["Value"]
    assert "-" in val
    assert "32" in val  # age of the drop


def test_latest_percentile_row(benchmark, history):
    """The 'latest est. percentile' row should appear with a ~Nth value."""
    result = build_summary_stats(history, benchmark)
    pct_row = result[result["Metric"].str.contains("percentile")]
    assert len(pct_row) == 1
    assert "th" in pct_row.iloc[0]["Value"]


def test_returns_dataframe_with_exact_columns(benchmark, history):
    """Every output should have exactly ['Metric', 'Value'] columns."""
    result = build_summary_stats(history, benchmark)
    assert list(result.columns) == ["Metric", "Value"]
