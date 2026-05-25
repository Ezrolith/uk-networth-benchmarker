"""Tests for utils/monte_carlo.py and charts/monte_carlo.py."""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.monte_carlo import (  # noqa: E402
    run_monte_carlo, percentile_envelope,
    probability_of_reaching, probability_of_ruin,
)
from charts.monte_carlo import build_monte_carlo_chart  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Simulation
# ──────────────────────────────────────────────────────────────────────────────

def test_run_monte_carlo_shape():
    paths = run_monte_carlo(start_nw=100_000, years=20, n_sims=500, seed=42)
    assert paths.shape == (500, 21)


def test_run_monte_carlo_starts_at_start_nw():
    paths = run_monte_carlo(start_nw=50_000, years=10, n_sims=100, seed=1)
    assert (paths[:, 0] == 50_000).all()


def test_run_monte_carlo_deterministic_with_seed():
    """Same seed must produce identical results."""
    p1 = run_monte_carlo(start_nw=100_000, years=10, n_sims=100, seed=7)
    p2 = run_monte_carlo(start_nw=100_000, years=10, n_sims=100, seed=7)
    np.testing.assert_array_equal(p1, p2)


def test_run_monte_carlo_different_seeds_differ():
    p1 = run_monte_carlo(start_nw=100_000, years=10, n_sims=100, seed=1)
    p2 = run_monte_carlo(start_nw=100_000, years=10, n_sims=100, seed=2)
    assert not np.array_equal(p1, p2)


def test_run_monte_carlo_mean_close_to_expected():
    """With many sims and zero contribution, the median end value should be
    close to FV(start_nw, mean_return, years)."""
    paths = run_monte_carlo(
        start_nw=100_000, years=20,
        mean_return=0.05, std_return=0.10,
        n_sims=5_000, seed=42,
    )
    expected_median = 100_000 * (1.05) ** 20  # ≈ £265k
    actual_median = float(np.median(paths[:, -1]))
    # The lognormal sum of returns gives a slight bias; within ±15%.
    assert abs(actual_median - expected_median) / expected_median < 0.15


def test_run_monte_carlo_zero_volatility_is_deterministic():
    """With std_return=0, all paths must be identical."""
    paths = run_monte_carlo(
        start_nw=100_000, years=10,
        mean_return=0.05, std_return=0.0,
        n_sims=100, seed=42,
    )
    # All paths identical
    assert (paths == paths[0]).all()
    # And equal to FV
    assert paths[0, -1] == pytest.approx(100_000 * 1.05 ** 10, rel=1e-9)


def test_run_monte_carlo_with_contributions_grows_faster():
    """At same mean return, adding contributions must lift the median path."""
    p_no_save = run_monte_carlo(
        start_nw=50_000, years=20, mean_return=0.05, std_return=0.10,
        n_sims=2_000, seed=42,
    )
    p_with_save = run_monte_carlo(
        start_nw=50_000, years=20, mean_return=0.05, std_return=0.10,
        n_sims=2_000, annual_contribution=5_000, seed=42,
    )
    assert np.median(p_with_save[:, -1]) > np.median(p_no_save[:, -1])


def test_run_monte_carlo_handles_zero_start():
    """A zero starting net worth shouldn't crash — clamped to 1.0 internally."""
    paths = run_monte_carlo(start_nw=0, years=10, n_sims=10, seed=1)
    assert paths.shape == (10, 11)
    assert (paths[:, 0] == 1.0).all()


# ──────────────────────────────────────────────────────────────────────────────
# Envelope and probabilities
# ──────────────────────────────────────────────────────────────────────────────

def test_percentile_envelope_shape_and_ordering():
    paths = run_monte_carlo(start_nw=100_000, years=10, n_sims=1_000, seed=1)
    env = percentile_envelope(paths)
    assert set(env.keys()) == {10, 25, 50, 75, 90}
    for p, vals in env.items():
        assert vals.shape == (11,)
    # At every step, P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90
    for t in range(11):
        assert env[10][t] <= env[25][t] <= env[50][t] <= env[75][t] <= env[90][t]


def test_probability_of_reaching_returns_fraction():
    paths = run_monte_carlo(
        start_nw=100_000, years=20, mean_return=0.05, std_return=0.10,
        n_sims=1_000, seed=42,
    )
    p_low  = probability_of_reaching(paths, target=50_000)   # easy → ~1.0
    p_high = probability_of_reaching(paths, target=10_000_000)  # impossible → ~0
    assert 0.95 < p_low <= 1.0
    assert 0.0 <= p_high < 0.05


def test_probability_of_ruin_zero_when_growing():
    paths = run_monte_carlo(
        start_nw=100_000, years=10, mean_return=0.05, std_return=0.05,
        n_sims=500, seed=1,
    )
    # At 5% mean / 5% sigma starting from £100k, very unlikely to hit zero
    assert probability_of_ruin(paths, threshold=0) < 0.05


# ──────────────────────────────────────────────────────────────────────────────
# Chart builder
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_paths() -> np.ndarray:
    return run_monte_carlo(start_nw=100_000, years=15, n_sims=500, seed=42)


def test_monte_carlo_chart_builds(sample_paths):
    fig = build_monte_carlo_chart(sample_paths, start_age=35)
    assert fig is not None
    names = [t.name for t in fig.data]
    assert "Median outcome" in names
    assert "10th–90th percentile" in names
    assert "25th–75th percentile" in names


def test_monte_carlo_chart_with_target(sample_paths):
    fig = build_monte_carlo_chart(sample_paths, start_age=35, target=500_000)
    annotations = [a.text for a in fig.layout.annotations]
    assert any("Target" in t and "500,000" in t for t in annotations)


def test_monte_carlo_chart_sample_paths_added(sample_paths):
    fig_no = build_monte_carlo_chart(sample_paths, start_age=35, show_sample_paths=0)
    fig_yes = build_monte_carlo_chart(sample_paths, start_age=35, show_sample_paths=20)
    assert len(fig_yes.data) > len(fig_no.data)


def test_monte_carlo_chart_title_includes_sim_count_and_years(sample_paths):
    fig = build_monte_carlo_chart(sample_paths, start_age=35)
    title = fig.layout.title.text
    assert "500" in title  # n_sims
    assert "15" in title   # years
