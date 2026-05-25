"""
Smoke tests for chart builder functions extracted to charts/.

These don't render the figure — they just verify it builds without error
and contains the expected traces / structure. The goal is to catch broken
imports, missing dependencies, and signature regressions during refactor.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.data_loader import load_was_data, load_asset_class_data  # noqa: E402
from utils.inference import interpolate_benchmarks, build_asset_class_series  # noqa: E402

from charts.asset_class import build_asset_class_chart  # noqa: E402
from charts.heatmap import build_heatmap  # noqa: E402
from charts.distribution import build_distribution_chart  # noqa: E402
from charts.gains import build_gains_chart, build_velocity_chart, build_cumulative_chart  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def benchmark() -> pd.DataFrame:
    raw = load_was_data()
    filtered = raw[raw["with_pension"] == True]
    return interpolate_benchmarks(filtered, np.arange(16, 86))


@pytest.fixture(scope="module")
def asset_series(benchmark: pd.DataFrame) -> pd.DataFrame:
    return build_asset_class_series(load_asset_class_data(), benchmark, np.arange(16, 86))


@pytest.fixture
def personal_history() -> pd.DataFrame:
    return pd.DataFrame({
        "year": [2020, 2022, 2024, 2026],
        "age":  [30.0, 32.0, 34.0, 36.0],
        "net_worth": [25_000.0, 60_000.0, 110_000.0, 175_000.0],
    })


# ──────────────────────────────────────────────────────────────────────────────
# Asset class chart
# ──────────────────────────────────────────────────────────────────────────────

def test_asset_class_chart_builds(asset_series):
    fig = build_asset_class_chart(asset_series)
    assert fig is not None
    # Four stacked components
    trace_names = [t.name for t in fig.data]
    assert {"Property", "Pension", "Financial", "Physical"}.issubset(trace_names)
    # All traces have stackgroup set
    for t in fig.data:
        assert t.stackgroup == "one"


def test_asset_class_chart_price_label_in_title(asset_series):
    fig = build_asset_class_chart(asset_series, price_label="2026 real terms")
    assert "2026 real terms" in fig.layout.yaxis.title.text


def test_asset_class_chart_empty_series_handled():
    empty = pd.DataFrame(columns=["age", "component", "value_gbp", "value_pct"])
    fig = build_asset_class_chart(empty)
    assert fig is not None
    assert len(fig.data) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Heatmap
# ──────────────────────────────────────────────────────────────────────────────

def test_heatmap_builds_without_personal_data(benchmark):
    fig = build_heatmap(benchmark)
    assert fig is not None
    # Should have at least 4 band fills (P10-25, 25-50, 50-75, 75-90)
    assert len(fig.data) >= 4


def test_heatmap_builds_with_personal_data(benchmark, personal_history):
    fig = build_heatmap(benchmark, personal_plot_df=personal_history)
    assert fig is not None
    # Should have band fills + a personal trace
    trace_names = [t.name for t in fig.data]
    assert "Your net worth" in trace_names


def test_heatmap_builds_with_partner(benchmark, personal_history):
    partner = personal_history.copy()
    partner["net_worth"] = partner["net_worth"] * 1.2
    fig = build_heatmap(
        benchmark,
        personal_plot_df=personal_history,
        partner_plot_df=partner,
    )
    trace_names = [t.name for t in fig.data]
    assert "Your net worth" in trace_names
    assert "Partner" in trace_names


def test_heatmap_uses_custom_colours(benchmark, personal_history):
    fig = build_heatmap(
        benchmark,
        personal_plot_df=personal_history,
        person_colour="#ff00ff",
    )
    # Find the personal trace and check its line colour
    personal_trace = next(t for t in fig.data if t.name == "Your net worth")
    assert personal_trace.line.color == "#ff00ff"


def test_heatmap_title_includes_price_label(benchmark):
    fig = build_heatmap(benchmark, price_label="2026 real terms")
    assert "2026 real terms" in fig.layout.title.text


# ──────────────────────────────────────────────────────────────────────────────
# Distribution chart
# ──────────────────────────────────────────────────────────────────────────────

def test_distribution_chart_builds(benchmark):
    fig = build_distribution_chart(40, benchmark)
    assert fig is not None
    # Should at least have the density curve trace
    assert len(fig.data) >= 1
    assert "Distribution" in [t.name for t in fig.data]


def test_distribution_chart_with_user_marker(benchmark):
    fig = build_distribution_chart(40, benchmark, user_nw=200_000)
    assert fig is not None
    # User marker is added as a vline annotation, not a trace — check shapes/annotations
    annotations = [a.text for a in fig.layout.annotations]
    assert any("You" in t for t in annotations)


def test_distribution_chart_with_partner(benchmark):
    fig = build_distribution_chart(40, benchmark, user_nw=200_000, partner_nw=180_000)
    annotations = [a.text for a in fig.layout.annotations]
    assert any("Partner" in t for t in annotations)


def test_distribution_chart_returns_none_at_invalid_age(benchmark):
    # Force a bad benchmark where age has zero values
    bad = benchmark.copy()
    bad.loc[bad["age"] == 40, "value"] = 0
    fig = build_distribution_chart(40, bad)
    assert fig is None


def test_distribution_chart_clamps_age_over_85(benchmark):
    fig = build_distribution_chart(95, benchmark)
    assert fig is not None
    assert "85" in fig.layout.title.text  # title shows the clamped age


# ──────────────────────────────────────────────────────────────────────────────
# Gains / velocity / cumulative
# ──────────────────────────────────────────────────────────────────────────────

def test_gains_chart_builds(personal_history):
    fig = build_gains_chart(personal_history)
    assert fig is not None
    assert len(fig.data) == 1  # single bar trace
    bar = fig.data[0]
    # Should have 3 bars (4 data points → 3 diffs)
    assert len(bar.x) == 3


def test_gains_chart_colours_negatives_red():
    pdf = pd.DataFrame({
        "year": [2020, 2021, 2022],
        "age":  [30.0, 31.0, 32.0],
        "net_worth": [50_000.0, 30_000.0, 80_000.0],   # one drop, one gain
    })
    fig = build_gains_chart(pdf, colour="#0000ff")
    bar = fig.data[0]
    # Bar 0: gain from 50k→30k = -20k (negative, should be red)
    # Bar 1: gain from 30k→80k = +50k (positive, should be blue)
    assert bar.marker.color[0] == "#ef4444"
    assert bar.marker.color[1] == "#0000ff"


def test_gains_chart_returns_none_for_single_point():
    pdf = pd.DataFrame({"age": [30.0], "net_worth": [50_000.0]})
    assert build_gains_chart(pdf) is None


def test_velocity_chart_builds(personal_history):
    fig = build_velocity_chart(personal_history)
    assert fig is not None
    # Y axis is % change
    assert fig.layout.yaxis.ticksuffix == "%"


def test_velocity_chart_returns_none_for_single_point():
    pdf = pd.DataFrame({"age": [30.0], "net_worth": [50_000.0]})
    assert build_velocity_chart(pdf) is None


def test_cumulative_chart_builds(personal_history):
    fig = build_cumulative_chart(personal_history)
    assert fig is not None
    assert len(fig.data) == 1
    assert fig.data[0].fill == "tozeroy"


def test_cumulative_chart_with_partner(personal_history):
    partner = personal_history.copy()
    partner["net_worth"] = partner["net_worth"] * 1.2
    fig = build_cumulative_chart(personal_history, partner_pdf=partner)
    assert len(fig.data) == 2
    names = [t.name for t in fig.data]
    assert "Partner" in names


def test_cumulative_chart_price_label_in_title(personal_history):
    fig = build_cumulative_chart(personal_history, price_label="2026 real")
    assert "2026 real" in fig.layout.title.text
