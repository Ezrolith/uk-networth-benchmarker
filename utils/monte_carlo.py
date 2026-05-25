"""
Monte Carlo simulation of net worth over time.

Models annual returns as normal random draws around a mean — adding the
sequence-of-returns risk that the deterministic CAGR what-if model can't show.

Output is a (n_sims, years+1) array of net-worth paths plus helper functions
to extract percentile envelopes and reach-target probabilities.
"""
from __future__ import annotations
import numpy as np


def run_monte_carlo(
    start_nw: float,
    years: int,
    mean_return: float = 0.05,
    std_return: float = 0.12,
    n_sims: int = 1_000,
    annual_contribution: float = 0.0,
    seed: int | None = None,
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
    std_return : annual standard deviation of returns (0.12 = 12pp).
        For a 60/40 equity/bond portfolio, typical real-return assumptions
        are mean ≈ 4–5%, sigma ≈ 9–11%. For 100% equity, sigma ≈ 16–18%.
    n_sims : number of independent simulation paths.
    annual_contribution : £ added each year (treated as end-of-year).
    seed : random seed for reproducibility (None = use default RNG).
    """
    if start_nw <= 0:
        # Can't compound a non-positive starting value — fall back to
        # contribution-only growth with mean return on contributions.
        start_nw = max(start_nw, 1.0)

    rng = np.random.default_rng(seed)
    # Annual return draws, shape (n_sims, years)
    returns = rng.normal(loc=mean_return, scale=std_return, size=(n_sims, years))

    # Compound forward, adding the annual contribution at end of each year
    paths = np.zeros((n_sims, years + 1), dtype=float)
    paths[:, 0] = start_nw
    for t in range(years):
        paths[:, t + 1] = paths[:, t] * (1 + returns[:, t]) + annual_contribution

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
