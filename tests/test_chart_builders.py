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

from charts.asset_class import build_asset_class_chart  # noqa: E402
from charts.heatmap import build_heatmap  # noqa: E402
from charts.distribution import build_distribution_chart  # noqa: E402
from charts.gains import build_gains_chart, build_velocity_chart, build_cumulative_chart  # noqa: E402
from charts.percentile_trajectory import build_percentile_chart  # noqa: E402
from charts.whatif import build_whatif_figure  # noqa: E402
from charts.main_figure import build_main_figure  # noqa: E402


# Fixtures (benchmark, asset_series, personal_history) live in tests/conftest.py


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


# ──────────────────────────────────────────────────────────────────────────────
# Percentile trajectory
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def trajectory_df() -> pd.DataFrame:
    return pd.DataFrame({
        "age":        [30.0, 32.0, 34.0, 36.0],
        "percentile": [15.0, 28.0, 45.0, 62.0],
        "net_worth":  [25_000.0, 60_000.0, 110_000.0, 175_000.0],
    })


def test_percentile_chart_builds(trajectory_df):
    fig = build_percentile_chart(trajectory_df)
    assert fig is not None
    # At least one trace ("You")
    assert "You" in [t.name for t in fig.data]


def test_percentile_chart_delta_annotation(trajectory_df):
    fig = build_percentile_chart(trajectory_df)
    # The "+47 pts" annotation (from 15 to 62)
    annotations = [a.text for a in fig.layout.annotations if a.text]
    assert any("47" in t and "pts" in t for t in annotations)


def test_percentile_chart_with_partner(trajectory_df):
    partner = trajectory_df.copy()
    partner["percentile"] = partner["percentile"] + 10
    fig = build_percentile_chart(trajectory_df, traj_partner=partner)
    names = [t.name for t in fig.data]
    assert "You" in names
    assert "Partner" in names


def test_percentile_chart_band_zones_present(trajectory_df):
    fig = build_percentile_chart(trajectory_df)
    # Band hrects are in layout.shapes
    assert len(fig.layout.shapes) >= 4  # at least 4 band shading rectangles


def test_percentile_chart_smoothing_applies():
    # Make a noisy trajectory that smoothing should flatten
    df = pd.DataFrame({
        "age":        [30.0, 31, 32, 33, 34, 35, 36, 37],
        "percentile": [20.0, 80, 25, 75, 30, 70, 35, 65],  # zigzag
        "net_worth":  [10_000] * 8,
    })
    fig_raw    = build_percentile_chart(df, smooth=False)
    fig_smooth = build_percentile_chart(df, smooth=True)
    # The smoothed trace should have less extreme values than raw
    raw_y    = fig_raw.data[0].y
    smooth_y = fig_smooth.data[0].y
    assert max(smooth_y) < max(raw_y) or min(smooth_y) > min(raw_y)


# ──────────────────────────────────────────────────────────────────────────────
# What-if projection
# ──────────────────────────────────────────────────────────────────────────────

def test_whatif_builds_single_scenario(benchmark, personal_history):
    fig = build_whatif_figure(
        personal_history, benchmark,
        scenarios=[(0.05, "5%")], project_to_age=65,
    )
    assert fig is not None
    # Should have benchmark band + 3 percentile lines + actual + 1 scenario = 6 traces
    assert len(fig.data) >= 6
    names = [t.name for t in fig.data]
    assert "Actual" in names
    assert "5%" in names


def test_whatif_multiple_scenarios(benchmark, personal_history):
    fig = build_whatif_figure(
        personal_history, benchmark,
        scenarios=[(0.03, "3%"), (0.05, "5%"), (0.08, "8%")],
        project_to_age=65,
    )
    names = [t.name for t in fig.data]
    assert "3%" in names and "5%" in names and "8%" in names


def test_whatif_projection_with_savings_grows_faster(benchmark, personal_history):
    """At same CAGR, +£500/mo contributions must produce a higher endpoint."""
    no_save = build_whatif_figure(
        personal_history, benchmark,
        scenarios=[(0.05, "5%")], project_to_age=65, monthly_savings=0.0,
    )
    with_save = build_whatif_figure(
        personal_history, benchmark,
        scenarios=[(0.05, "5%")], project_to_age=65, monthly_savings=500.0,
    )
    # Pull the scenario trace y-values (last trace in each)
    no_save_end = no_save.data[-1].y[-1]
    with_save_end = with_save.data[-1].y[-1]
    assert with_save_end > no_save_end


def test_whatif_zero_cagr_is_linear(benchmark, personal_history):
    """At cagr=0 with savings, the projection should be linear (constant slope)."""
    fig = build_whatif_figure(
        personal_history, benchmark,
        scenarios=[(0.0, "0%")], project_to_age=65, monthly_savings=1_000.0,
    )
    y = list(fig.data[-1].y)
    # Differences should all be ~equal (£12,000/year)
    diffs = [y[i+1] - y[i] for i in range(len(y) - 1)]
    assert all(abs(d - diffs[0]) < 1 for d in diffs)


def test_whatif_title_includes_cagr_and_contrib_note(benchmark, personal_history):
    fig = build_whatif_figure(
        personal_history, benchmark,
        scenarios=[(0.05, "5%")], project_to_age=65, monthly_savings=500.0,
    )
    title = fig.layout.title.text
    assert "5.0%" in title
    assert "500" in title  # monthly contribution note


# ──────────────────────────────────────────────────────────────────────────────
# Main figure
# ──────────────────────────────────────────────────────────────────────────────

def test_main_figure_minimal_no_personal(benchmark):
    """Builds with just a benchmark — no personal data, no settings."""
    fig = build_main_figure(benchmark)
    assert fig is not None
    names = [t.name for t in fig.data]
    # Benchmark trio + IQR band + ONS markers (defaults to Household)
    assert "Median (P50)" in names
    assert "25th percentile" in names
    assert "75th percentile" in names
    assert "P25–P75 range" in names


def test_main_figure_with_personal(benchmark, personal_history):
    fig = build_main_figure(benchmark, personal_plot_df=personal_history)
    names = [t.name for t in fig.data]
    assert "Your net worth" in names


def test_main_figure_with_partner(benchmark, personal_history):
    partner = personal_history.copy()
    partner["net_worth"] = partner["net_worth"] * 1.1
    fig = build_main_figure(
        benchmark,
        personal_plot_df=personal_history,
        partner_plot_df=partner,
    )
    names = [t.name for t in fig.data]
    assert "Your net worth" in names
    assert "Partner" in names


def test_main_figure_tails_toggle(benchmark):
    fig_off = build_main_figure(benchmark, show_tails=False)
    fig_on  = build_main_figure(benchmark, show_tails=True)
    names_on = [t.name for t in fig_on.data]
    # P10/P90 tails only added when show_tails=True
    assert any("10th (modelled)" in n for n in names_on)
    assert len(fig_on.data) > len(fig_off.data)


def test_main_figure_milestone_lines(benchmark):
    fig = build_main_figure(benchmark, show_milestones=True, log_scale=False)
    # Milestone lines appear as shapes/annotations — verify £1m text present
    annotations = [a.text for a in fig.layout.annotations]
    assert any("£1m" in t for t in annotations)


def test_main_figure_milestones_hidden_on_log_scale(benchmark):
    fig = build_main_figure(benchmark, show_milestones=True, log_scale=True)
    annotations = [a.text for a in fig.layout.annotations]
    # On log scale, milestone lines suppress to avoid clutter
    assert not any("£1m" in t for t in annotations)


def test_main_figure_annotations_off_strips_crosshair(benchmark, personal_history):
    fig = build_main_figure(
        benchmark, personal_plot_df=personal_history,
        latest_age=36.0, latest_nw=175_000,
        show_annotations=False,
    )
    annotations = [a.text or "" for a in fig.layout.annotations]
    # No "You (age" crosshair label when annotations are off
    assert not any("You (age" in t for t in annotations)


def test_main_figure_individual_basis_drops_ons_markers(benchmark, personal_history):
    fig = build_main_figure(
        benchmark, personal_plot_df=personal_history,
        basis="Individual",
    )
    names = [t.name for t in fig.data]
    # Individual basis: ONS markers removed, replaced by a derived-figures note
    assert "ONS data point" not in names
    assert any("derived estimates" in n for n in names)


def test_main_figure_age_range_clamping(benchmark):
    fig = build_main_figure(benchmark, age_min=30, age_max=60)
    # x-axis range honours the request (with 0.5 padding on each side)
    xrange = fig.layout.xaxis.range
    assert xrange[0] == 29.5
    assert xrange[1] == 60.5


def test_main_figure_log_scale_changes_yaxis(benchmark):
    fig_lin = build_main_figure(benchmark, log_scale=False)
    fig_log = build_main_figure(benchmark, log_scale=True)
    assert fig_lin.layout.yaxis.type == "linear"
    assert fig_log.layout.yaxis.type == "log"


def test_main_figure_wealth_component_in_title(benchmark):
    fig = build_main_figure(benchmark, wealth_component="Property")
    assert "Property wealth only" in fig.layout.title.text


def test_main_figure_handles_negative_personal_data(benchmark):
    """Adds a zero reference line when personal data contains negatives."""
    pdf = pd.DataFrame({
        "year": [2020, 2024],
        "age":  [25.0, 30.0],
        "net_worth": [-5_000.0, 25_000.0],
    })
    fig = build_main_figure(benchmark, personal_plot_df=pdf)
    # Plotly Layout.shapes is a tuple of horizontal/vertical lines from add_hline/vline
    shape_y0 = [s.y0 for s in fig.layout.shapes if s.type == "line"]
    assert 0 in shape_y0  # the zero reference line
