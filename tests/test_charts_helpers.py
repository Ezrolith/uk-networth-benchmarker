"""Unit tests for charts/_helpers.py — the formatting layer."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from charts._helpers import fmt, fmt_delta, clean_note, safe_cagr, best_gain, hover_template  # noqa: E402


# ── fmt ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (0,            "£0"),
    (500,          "£500"),
    (1_000,        "£1k"),
    (12_345,       "£12k"),
    (999_999,      "£1000k"),
    (1_000_000,    "£1.00m"),
    (1_234_567,    "£1.23m"),
    (-100,         "-£100"),
    (-12_345,      "-£12k"),
    (-2_500_000,   "-£2.50m"),
])
def test_fmt_formats_correctly(value, expected):
    assert fmt(value) == expected


@pytest.mark.parametrize("delta,expected", [
    (1_000,   "+£1k"),
    (12_345,  "+£12k"),
    (-3_000,  "-£3k"),
    (0,       "+£0"),
])
def test_fmt_delta(delta, expected):
    assert fmt_delta(delta) == expected


# ── clean_note ─────────────────────────────────────────────────────────────────

def test_clean_note_empty_cases():
    s = pd.Series({"age": 30, "net_worth": 50_000})  # no note column
    assert clean_note(s) == ""

    s = pd.Series({"note": None})
    assert clean_note(s) == ""

    s = pd.Series({"note": float("nan")})
    assert clean_note(s) == ""

    s = pd.Series({"note": "  "})
    assert clean_note(s) == ""

    s = pd.Series({"note": "nan"})
    assert clean_note(s) == ""


def test_clean_note_extracts_real_notes():
    s = pd.Series({"note": "bought flat"})
    assert clean_note(s) == "bought flat"

    s = pd.Series({"note": "  changed job  "})
    assert clean_note(s) == "changed job"


# ── safe_cagr ──────────────────────────────────────────────────────────────────

def test_safe_cagr_returns_none_for_short_period():
    assert safe_cagr(10_000, 20_000, years=0.3) is None


def test_safe_cagr_returns_none_for_tiny_start():
    assert safe_cagr(100, 50_000, years=5) is None


def test_safe_cagr_returns_none_for_zero_or_negative_end():
    assert safe_cagr(10_000, 0, years=5) is None
    assert safe_cagr(10_000, -1_000, years=5) is None


def test_safe_cagr_computes_correctly():
    # Doubling over 7.27 years = ~10% CAGR
    result = safe_cagr(50_000, 100_000, years=7.27)
    assert result == pytest.approx(0.10, abs=0.005)

    # 5x over 10 years = ~17.5% CAGR
    result = safe_cagr(10_000, 50_000, years=10)
    assert result == pytest.approx(0.1746, abs=0.01)


# ── best_gain ──────────────────────────────────────────────────────────────────

def test_best_gain_finds_biggest_jump():
    pdf = pd.DataFrame({
        "age":       [30, 31, 32, 33],
        "net_worth": [10_000, 15_000, 70_000, 75_000],
    })
    result = best_gain(pdf)
    assert result is not None
    age, gain, pct = result
    assert age == 32
    assert gain == pytest.approx(55_000)
    assert pct == pytest.approx((70_000 - 15_000) / 15_000 * 100, abs=0.1)


def test_best_gain_returns_none_for_single_point():
    pdf = pd.DataFrame({"age": [30], "net_worth": [10_000]})
    assert best_gain(pdf) is None


def test_best_gain_handles_unsorted_input():
    pdf = pd.DataFrame({
        "age":       [33, 30, 32, 31],
        "net_worth": [75_000, 10_000, 70_000, 15_000],
    })
    result = best_gain(pdf)
    assert result is not None
    age, _, _ = result
    assert age == 32  # still finds the right gain after sorting


def test_best_gain_aggregates_monthly_to_annual():
    """With monthly snapshots, best_gain should report the biggest annual jump,
    not the biggest single-month delta — matching the gains chart aggregation."""
    rows = []
    # 2024: net worth grows 50k → 62k (annual gain £12k)
    # but biggest single month is +£3k
    for month in range(1, 13):
        rows.append({"year": 2024, "age": 30 + month / 12, "net_worth": 50_000 + month * 1_000})
    # 2025: net worth jumps 62k → 100k (annual gain £38k, the winner)
    # biggest single month is +£5k (Jan)
    rows.append({"year": 2025, "age": 31 + 1/12, "net_worth": 67_000})
    for month in range(2, 13):
        rows.append({"year": 2025, "age": 31 + month / 12, "net_worth": 67_000 + (month - 1) * 3_000})
    pdf = pd.DataFrame(rows)
    result = best_gain(pdf)
    assert result is not None
    _, gain, _ = result
    # Annual gain is £38k (62k → 100k), not a monthly delta (~£5k)
    assert gain > 30_000


def test_best_gain_no_aggregation_when_one_row_per_year():
    """With one row per year, behaviour is unchanged from before the fix."""
    pdf = pd.DataFrame({
        "year":      [2020, 2021, 2022, 2023],
        "age":       [30, 31, 32, 33],
        "net_worth": [10_000, 15_000, 70_000, 75_000],
    })
    result = best_gain(pdf)
    assert result is not None
    age, gain, _ = result
    assert age == 32
    assert gain == pytest.approx(55_000)


# ── hover_template ─────────────────────────────────────────────────────────────

def test_hover_template_basic():
    out = hover_template("Median")
    assert "Median" in out
    assert "%{x}" in out
    assert "£%{y:,.0f}" in out
