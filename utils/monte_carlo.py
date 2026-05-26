"""
Monte Carlo simulation of net worth over time.

Models annual returns as normal random draws around a mean — adding the
sequence-of-returns risk that the deterministic CAGR what-if model can't show.

Output is a (n_sims, years+1) array of net-worth paths plus helper functions
to extract percentile envelopes and reach-target probabilities.
"""
from __future__ import annotations
import numpy as np


# ── Asset class assumptions ───────────────────────────────────────────────────
# Long-run real-return assumptions used by the glide path.
# Equity:  global equity, post-inflation. UK academic 100-yr real ≈ 5%, modern
#          forward-looking estimates 4–6%.
# Bonds :  developed-market sovereign + IG, real. Lower expected, lower vol.
EQUITY_MEAN, EQUITY_SIGMA = 0.055, 0.18
BOND_MEAN,   BOND_SIGMA   = 0.015, 0.06
# Correlation between equity and bond returns: historically modestly positive
# (~0.1-0.3 over long periods). Used only when glide-path is active.
EQUITY_BOND_CORR = 0.10


def _glide_allocation(years: int, start_equity_pct: float, end_equity_pct: float) -> np.ndarray:
    """
    Linear glide path of equity weight from start to end over `years` years.
    Returns an array of length `years` giving the equity fraction in each year.
    """
    if years <= 0:
        return np.array([])
    if years == 1:
        return np.array([start_equity_pct])
    return np.linspace(start_equity_pct, end_equity_pct, years)


def _portfolio_moments(equity_weight: float) -> tuple[float, float]:
    """
    Expected mean and std of a (equity_weight, 1-equity_weight) portfolio
    using EQUITY_MEAN/SIGMA, BOND_MEAN/SIGMA, EQUITY_BOND_CORR.
    """
    w_e, w_b = equity_weight, 1 - equity_weight
    mu = w_e * EQUITY_MEAN + w_b * BOND_MEAN
    var = (w_e**2 * EQUITY_SIGMA**2 + w_b**2 * BOND_SIGMA**2
           + 2 * w_e * w_b * EQUITY_SIGMA * BOND_SIGMA * EQUITY_BOND_CORR)
    return mu, float(np.sqrt(var))


def run_monte_carlo(
    start_nw: float,
    years: int,
    mean_return: float = 0.05,
    std_return: float = 0.12,
    n_sims: int = 1_000,
    annual_contribution: float = 0.0,
    seed: int | None = None,
    glide_path: tuple[float, float] | None = None,
    clamp_at_zero: bool = True,
) -> np.ndarray:
    """
    Run `n_sims` independent paths of net worth over `years` years.

    Returns a (n_sims, years+1) ndarray where column 0 is start_nw and column t
    is the simulated net worth at the end of year t.

    Parameters
    ----------
    start_nw : starting net worth (£).
    years : number of years to project.
    mean_return : expected annual return as a fraction (0.05 = 5% real).
        IGNORED if glide_path is supplied.
    std_return : annual standard deviation of returns (0.12 = 12pp).
        IGNORED if glide_path is supplied.
    n_sims : number of independent simulation paths.
    annual_contribution : £ added each year (treated as end-of-year). Pass a
        NEGATIVE value to model withdrawals (decumulation).
    seed : random seed for reproducibility (None = use default RNG).
    glide_path : optional (start_equity_pct, end_equity_pct) tuple. When supplied,
        each year uses a portfolio mean/sigma derived from a linear glide between
        the two equity weights, using EQUITY_/BOND_ asset-class assumptions.
        e.g. (1.0, 0.4) = 100% equity now, gliding to 60/40 over the horizon.
    clamp_at_zero : if True (default), paths that fall to or below zero stay at
        zero — modelling pot depletion correctly. Set False if you actually want
        negative balances to compound (rarely correct; useful only for diagnostic
        unbounded simulations).
    """
    if start_nw <= 0:
        start_nw = max(start_nw, 1.0)

    rng = np.random.default_rng(seed)

    if glide_path is None:
        # Single fixed-allocation portfolio
        returns = rng.normal(loc=mean_return, scale=std_return, size=(n_sims, years))
    else:
        start_eq, end_eq = glide_path
        weights = _glide_allocation(years, start_eq, end_eq)
        returns = np.empty((n_sims, years), dtype=float)
        for t, w in enumerate(weights):
            mu_t, sigma_t = _portfolio_moments(w)
            returns[:, t] = rng.normal(loc=mu_t, scale=sigma_t, size=n_sims)

    paths = np.zeros((n_sims, years + 1), dtype=float)
    paths[:, 0] = start_nw
    for t in range(years):
        # Apply return to current balance, then end-of-year contribution.
        # Clamp at zero so a depleted pot doesn't keep compounding into the negative.
        new_balance = paths[:, t] * (1 + returns[:, t]) + annual_contribution
        if clamp_at_zero:
            np.maximum(new_balance, 0.0, out=new_balance)
        paths[:, t + 1] = new_balance

    return paths


def percentile_envelope(
    paths: np.ndarray,
    percentiles: tuple[int, ...] = (10, 25, 50, 75, 90),
) -> dict[int, np.ndarray]:
    """
    Compute percentile bands across simulations at each timestep.

    Returns {p: array_of_length_years_plus_1} for each percentile in `percentiles`.
    """
    return {p: np.percentile(paths, p, axis=0) for p in percentiles}


def probability_of_reaching(paths: np.ndarray, target: float) -> float:
    """
    Fraction of simulations whose *final* value reaches `target` or above.
    """
    if paths.size == 0:
        return 0.0
    final = paths[:, -1]
    return float((final >= target).mean())


def probability_of_ruin(paths: np.ndarray, threshold: float = 0.0) -> float:
    """
    Fraction of simulations that fall to `threshold` or below at any point.
    Useful when modelling decumulation rather than accumulation.
    """
    if paths.size == 0:
        return 0.0
    hit_floor = (paths <= threshold).any(axis=1)
    return float(hit_floor.mean())
