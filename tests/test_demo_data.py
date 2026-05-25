"""
Smoke tests for the demo data flow.

The 'Try with demo data' button in app.py loads a baked-in 11-year history
into session state. This file verifies the demo data shape and that it
processes correctly through the full inference + chart pipeline — so a
regression in the demo data structure would be caught by CI, not by a user
clicking the button and getting an error.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.inference import (
    cpi_adjust_personal, estimate_exact_percentile,
    build_percentile_trajectory,
)


# Single source of truth — both app.py and this test import from here, so
# tests automatically track any changes to the demo data without manual sync.
from data.demo_data import DEMO_HISTORY


@pytest.fixture
def demo_df() -> pd.DataFrame:
    return pd.DataFrame(DEMO_HISTORY)


def test_demo_data_has_11_rows(demo_df):
    assert len(demo_df) == 11


def test_demo_data_spans_2016_to_2026(demo_df):
    assert demo_df["year"].min() == 2016
    assert demo_df["year"].max() == 2026


def test_demo_data_ages_consistent(demo_df):
    """Age should increase by 1 each year — no birth-year warning should trigger."""
    implied_birth = demo_df["year"] - demo_df["age"]
    assert implied_birth.min() == implied_birth.max() == 1991


def test_demo_data_monotone_growth(demo_df):
    """Net worth should grow each year — no negative gains in the demo."""
    diffs = demo_df["net_worth"].diff().dropna()
    assert (diffs > 0).all()


def test_demo_data_cpi_adjusts_cleanly(demo_df):
    """CPI adjustment to 2026 should work for every demo row (all years in table)."""
    adjusted = cpi_adjust_personal(demo_df, to_year=2026)
    assert len(adjusted) == 11
    # 2026 row should be unchanged
    last = adjusted[adjusted["year"] == 2026].iloc[0]
    original_last = demo_df[demo_df["year"] == 2026].iloc[0]
    assert last["net_worth"] == pytest.approx(original_last["net_worth"])
    # Earlier rows should be inflated upward
    early = adjusted[adjusted["year"] == 2016].iloc[0]
    original_early = demo_df[demo_df["year"] == 2016].iloc[0]
    assert early["net_worth"] > original_early["net_worth"]


def test_demo_data_produces_valid_percentile_at_each_point(demo_df):
    """Every demo data point should produce a valid percentile estimate."""
    from utils.data_loader import load_was_data
    from utils.inference import interpolate_benchmarks
    import numpy as np

    raw = load_was_data()
    benchmark = interpolate_benchmarks(raw[raw["with_pension"] == True], np.arange(16, 86))

    for _, row in demo_df.iterrows():
        pct = estimate_exact_percentile(
            float(row["net_worth"]), int(row["age"]), benchmark,
        )
        assert pct is not None, f"Demo row at age {row['age']} produced no percentile"
        assert 0 <= pct <= 100, f"Percentile {pct} out of range at age {row['age']}"


def test_demo_data_trajectory_is_upward(demo_df):
    """The demo's percentile trajectory should generally improve over time."""
    from utils.data_loader import load_was_data
    from utils.inference import interpolate_benchmarks
    import numpy as np

    raw = load_was_data()
    benchmark = interpolate_benchmarks(raw[raw["with_pension"] == True], np.arange(16, 86))

    traj = build_percentile_trajectory(demo_df, benchmark)
    assert len(traj) == 11
    # The demo is designed to track upward — final percentile should be
    # meaningfully higher than the starting one.
    assert traj.iloc[-1]["percentile"] > traj.iloc[0]["percentile"]
    # Final value should be at or above median for age 35
    assert traj.iloc[-1]["percentile"] >= 50  # demo retiree-track example


def test_demo_data_note_column_present(demo_df):
    """The 'note' column is part of the demo so users see the hover-annotation feature."""
    assert "note" in demo_df.columns
    # At least 3 notes should be non-empty (first job, bought flat, promotion, married)
    non_empty_notes = demo_df[demo_df["note"] != ""]
    assert len(non_empty_notes) >= 3
