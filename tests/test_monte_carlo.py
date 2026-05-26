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
    _glide_allocation, _portfolio_moments,
    EQUITY_MEAN, EQUITY_SIGMA, BOND_MEAN, BOND_SIGMA,
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


def test_clamp_at_zero_prevents_negative_balances():
    """
    Decumulation with heavy withdrawals: paths should reach zero and stay there,
    not go negative and keep compounding. This catches the original correctness
    bug where a depleted pot would generate phantom 'recoveries' from negative
    returns on negative balances.
    """
    # Start with £100k, withdraw £50k/yr — should deplete fast
    paths = run_monte_carlo(
        start_nw=100_000, years=10, n_sims=50,
        mean_return=0.05, std_return=0.0,        # deterministic 5% real
        annual_contribution=-50_000, seed=1,
    )
    # No path should ever go below zero
    assert (paths >= 0).all(), "clamp_at_zero failed: negative balance found"
    # At least some paths should reach zero (they deplete with these inputs)
    assert (paths[:, -1] == 0).any(), "no paths depleted despite heavy withdrawal"


def test_clamp_at_zero_stays_at_zero_after_depletion():
    """
    Once a path hits zero, it should remain zero for all subsequent years
    (no phantom recoveries from positive returns on a £0 pot).
    """
    paths = run_monte_carlo(
        start_nw=10_000, years=20, n_sims=100,
        mean_return=0.05, std_return=0.0,
        annual_contribution=-20_000,      # depletes in <1 year
        seed=1,
    )
    # Find paths that have hit zero by year 5
    hit_zero_by_5 = paths[:, 5] == 0
    # All those paths should stay at zero in years 6-20
    later_balances = paths[hit_zero_by_5, 6:]
    assert (later_balances == 0).all(), "paths recovered from zero — clamp failed"


def test_clamp_at_zero_can_be_disabled():
    """clamp_at_zero=False allows the old unbounded behaviour for diagnostics."""
    paths = run_monte_carlo(
        start_nw=10_000, years=10, n_sims=50,
        mean_return=0.05, std_return=0.0,
        annual_contribution=-10_000,
        seed=1, clamp_at_zero=False,
    )
    # With clamp off, late-period balances should go negative
    assert (paths[:, -1] < 0).any(), "clamp_at_zero=False should allow negatives"


def test_clamp_at_zero_is_safe_for_accumulation():
    """Pure accumulation (positive contributions, no withdrawals) should be
    identical whether clamp is on or off — clamp is a no-op when balances
    are always positive."""
    p_clamp = run_monte_carlo(
        start_nw=100_000, years=10, n_sims=100,
        mean_return=0.05, std_return=0.12,
        annual_contribution=12_000, seed=1, clamp_at_zero=True,
    )
    p_no_clamp = run_monte_carlo(
        start_nw=100_000, years=10, n_sims=100,
        mean_return=0.05, std_return=0.12,
        annual_contribution=12_000, seed=1, clamp_at_zero=False,
    )
    # All paths should be positive in both modes, and identical
    assert (p_clamp >= 0).all()
    assert (p_clamp == p_no_clamp).all()


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


# ──────────────────────────────────────────────────────────────────────────────
# Glide path
# ──────────────────────────────────────────────────────────────────────────────

def test_glide_allocation_endpoints():
    """First year = start_equity, last year = end_equity."""
    w = _glide_allocation(20, 1.0, 0.4)
    assert w[0] == pytest.approx(1.0)
    assert w[-1] == pytest.approx(0.4)
    assert len(w) == 20


def test_glide_allocation_monotone():
    w = _glide_allocation(15, 1.0, 0.5)
    diffs = np.diff(w)
    assert (diffs <= 0).all()  # decreasing each year


def test_glide_allocation_handles_single_year():
    w = _glide_allocation(1, 0.9, 0.4)
    assert len(w) == 1
    assert w[0] == 0.9  # only start value used


def test_portfolio_moments_pure_equity():
    mu, sigma = _portfolio_moments(1.0)
    assert mu == pytest.approx(EQUITY_MEAN)
    assert sigma == pytest.approx(EQUITY_SIGMA)


def test_portfolio_moments_pure_bonds():
    mu, sigma = _portfolio_moments(0.0)
    assert mu == pytest.approx(BOND_MEAN)
    assert sigma == pytest.approx(BOND_SIGMA)


def test_portfolio_moments_60_40_lower_vol_than_equity():
    mu_eq,  sigma_eq  = _portfolio_moments(1.0)
    mu_60,  sigma_60  = _portfolio_moments(0.6)
    # Mixed portfolio: lower mean than pure equity, lower vol than pure equity
    assert mu_60 < mu_eq
    assert sigma_60 < sigma_eq
    # And higher than pure bonds
    assert mu_60 > BOND_MEAN
    assert sigma_60 > BOND_SIGMA


def test_run_monte_carlo_with_glide_path_shape():
    paths = run_monte_carlo(
        start_nw=100_000, years=20, n_sims=200,
        glide_path=(1.0, 0.4), seed=42,
    )
    assert paths.shape == (200, 21)


def test_run_monte_carlo_glide_path_reduces_endpoint_volatility():
    """De-risking glide should produce a TIGHTER P10-P90 spread at the end
    vs holding constant 100% equity for the same period."""
    fixed = run_monte_carlo(
        start_nw=100_000, years=30,
        mean_return=EQUITY_MEAN, std_return=EQUITY_SIGMA,
        n_sims=2_000, seed=42,
    )
    glided = run_monte_carlo(
        start_nw=100_000, years=30, n_sims=2_000,
        glide_path=(1.0, 0.4), seed=42,
    )
    spread_fixed  = np.percentile(fixed[:, -1], 90)  - np.percentile(fixed[:, -1], 10)
    spread_glided = np.percentile(glided[:, -1], 90) - np.percentile(glided[:, -1], 10)
    assert spread_glided < spread_fixed


def test_run_monte_carlo_glide_path_ignores_mean_std_args():
    """When glide_path is supplied, mean_return/std_return should not affect output."""
    p1 = run_monte_carlo(
        start_nw=100_000, years=10, n_sims=100,
        mean_return=0.20, std_return=0.50,  # nonsense values
        glide_path=(0.6, 0.6), seed=1,
    )
    p2 = run_monte_carlo(
        start_nw=100_000, years=10, n_sims=100,
        mean_return=-0.10, std_return=0.01,  # different nonsense
        glide_path=(0.6, 0.6), seed=1,
    )
    np.testing.assert_array_equal(p1, p2)
