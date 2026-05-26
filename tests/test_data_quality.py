"""Tests for utils/data_quality.py — personal data scoring."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.data_quality import compute_data_quality  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Boundary scoring (each criterion in isolation)
# ──────────────────────────────────────────────────────────────────────────────

def _df(n_points: int, age_span: float, max_year: int) -> pd.DataFrame:
    """Helper: build a synthetic DataFrame with n points spread over age_span yrs."""
    import numpy as np
    ages = np.linspace(30, 30 + age_span, n_points)
    years = np.linspace(max_year - age_span, max_year, n_points).astype(int)
    return pd.DataFrame({
        "year": years, "age": ages,
        "net_worth": [10_000 * (i + 1) for i in range(n_points)],
    })


def test_perfect_score_10pts_10yr_recent():
    """10 points spanning 10 years, ending last year — should score 100."""
    from datetime import date
    df = _df(n_points=10, age_span=10, max_year=date.today().year - 1)
    result = compute_data_quality(df)
    assert result["score"] == 100


def test_minimum_data_low_score():
    """1 point — should be below 50 even if recent."""
    from datetime import date
    df = _df(n_points=1, age_span=0, max_year=date.today().year - 1)
    result = compute_data_quality(df)
    assert result["score"] < 50
    assert any("at least 2" in n for n in result["notes"])


def test_empty_dataframe_handled():
    """Zero rows shouldn't crash."""
    df = pd.DataFrame(columns=["year", "age", "net_worth"])
    result = compute_data_quality(df)
    assert "score" in result
    assert result["n"] == 0


def test_recency_scoring_brackets():
    """Verify the recency criterion: 'this year-1' beats 'this year-3' beats older.

    Bands are now relative to today rather than hardcoded 2024, so this test
    builds its inputs from date.today().year and stays correct as years pass.
    """
    from datetime import date
    cy = date.today().year
    very_recent = _df(10, 10, cy - 1)
    moderate    = _df(10, 10, cy - 3)
    old         = _df(10, 10, cy - 7)
    assert compute_data_quality(very_recent)["score"] > compute_data_quality(moderate)["score"]
    assert compute_data_quality(moderate)["score"]    > compute_data_quality(old)["score"]


def test_density_scoring_brackets():
    """Frequent updates score higher than sparse ones."""
    annual    = _df(10, 9,   2024)   # ~1yr gap (≤1.5)
    biannual  = _df(5, 10,   2024)   # 2.5yr gap (≤3)
    decennial = _df(2, 20,   2024)   # 20yr gap (>3)
    assert compute_data_quality(annual)["score"] > compute_data_quality(biannual)["score"]
    assert compute_data_quality(biannual)["score"] > compute_data_quality(decennial)["score"]


def test_span_scoring_brackets():
    """
    Longer-span data scores higher on the span criterion in isolation —
    holding point count and density constant by using just 2 endpoints.
    """
    # 2 points means avg_gap = age_span / 1 = age_span. So short_span has
    # the lowest density, and long_span the highest. To isolate JUST the
    # span criterion, we'd need 3+ points but that confounds density.
    # So we check the function returns the right note for each band.
    long_note  = compute_data_quality(_df(2, 15, 2024))["notes"]
    med_note   = compute_data_quality(_df(2, 7,  2024))["notes"]
    short_note = compute_data_quality(_df(2, 2,  2024))["notes"]
    assert any("10+ year history" in n for n in long_note)
    assert any("5–9 year history" in n for n in med_note)
    assert any("Less than 5 years" in n for n in short_note)


def test_score_capped_at_100():
    """Even an unrealistically perfect dataset doesn't exceed 100."""
    df = _df(n_points=50, age_span=30, max_year=2026)  # massive
    result = compute_data_quality(df)
    assert result["score"] <= 100


def test_notes_have_indicator_emoji():
    """Each note should start with one of the three visual indicators."""
    df = _df(10, 10, 2024)
    result = compute_data_quality(df)
    for note in result["notes"]:
        assert note[0] in {"✅", "🟡", "⚠️", "❌"}, f"Note missing indicator: {note}"


def test_returns_n_and_span_for_introspection():
    """The function returns extra metadata callers can use for display."""
    df = _df(7, 6, 2023)
    result = compute_data_quality(df)
    assert result["n"] == 7
    assert result["span"] == pytest.approx(6, abs=0.01)
