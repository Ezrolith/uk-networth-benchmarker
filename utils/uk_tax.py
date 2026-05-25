"""
UK tax calculations: pension annual allowance taper for high earners.

Centralises the rules so they can be unit-tested independently of the
Streamlit UI.

Allowances as of 2025/26 tax year.
"""
from __future__ import annotations


# ── 2025/26 allowances (constants) ─────────────────────────────────────────────
ISA_ALLOWANCE         = 20_000   # Annual ISA limit (cash + S&S + IF + LISA combined)
LISA_ALLOWANCE        = 4_000    # Lifetime ISA, counts inside ISA total
PENSION_AA            = 60_000   # Standard pension Annual Allowance
TAPER_THRESHOLD       = 260_000  # Adjusted income above which taper begins
TAPER_FLOOR           = 10_000   # Minimum tapered AA (reached at £360k adjusted income)
STATE_PENSION_2026_27 = 12_400   # Full new State Pension estimate for 2026/27 (£/yr)


def tapered_pension_allowance(adjusted_income: float) -> tuple[float, float]:
    """
    Compute the tapered pension annual allowance for a given adjusted income.

    For each £2 of adjusted income above £260,000, the £60,000 standard AA is
    reduced by £1, until it reaches the £10,000 floor at £360,000 of adjusted
    income.

    Returns (tapered_aa, taper_reduction).
    """
    if adjusted_income <= TAPER_THRESHOLD:
        return float(PENSION_AA), 0.0

    reduction = (adjusted_income - TAPER_THRESHOLD) / 2
    tapered   = max(TAPER_FLOOR, PENSION_AA - reduction)
    # The "official" reduction is capped at PENSION_AA - TAPER_FLOOR even if
    # mathematically larger, since we don't go below the floor.
    actual_reduction = PENSION_AA - tapered
    return float(tapered), float(actual_reduction)


def effective_pension_allowance(
    adjusted_income: float,
    carryforward_3yr_total: float = 0.0,
) -> float:
    """
    Total pension allowance available this year = tapered AA + carryforward.
    Carryforward is the sum of unused allowance from the previous 3 tax years.
    """
    tapered, _ = tapered_pension_allowance(adjusted_income)
    return tapered + max(0.0, carryforward_3yr_total)


def isa_remaining(contributed_this_year: float) -> float:
    return max(0.0, ISA_ALLOWANCE - contributed_this_year)


def lisa_remaining(contributed_this_year: float, age: int | None = None) -> float:
    """
    LISA: £4,000/yr, but unavailable for anyone over 50 (can keep paying in
    until 50 if opened before 40). Returns 0 if age > 50.
    """
    if age is not None and age > 50:
        return 0.0
    return max(0.0, LISA_ALLOWANCE - contributed_this_year)


def pension_relief_estimate(
    contribution: float,
    marginal_rate: float = 0.40,
) -> float:
    """
    Estimated income-tax relief on a pension contribution at a given marginal
    rate. UK pension relief is given automatically at the basic rate; higher-
    and additional-rate taxpayers claim the difference via Self Assessment.
    """
    if contribution <= 0:
        return 0.0
    return contribution * marginal_rate


def lisa_bonus(contribution: float) -> float:
    """LISA government bonus: 25% on contributions, up to £1,000/yr."""
    return min(contribution * 0.25, 1_000.0)
