"""
UK 2025/26 tax-rule constants and helpers.

Centralises every UK-specific calculation so the rules can be unit-tested
independently of the Streamlit UI and refreshed in one place each new
tax year.

Covers:
- ISA total + Lifetime ISA allowances and remaining-headroom helpers
- Pension Annual Allowance, with high-earner taper (£260k+ adjusted income)
  and 3-year carryforward
- Pension tax-relief estimates at given marginal rates
- LISA government bonus (25%, capped at £1,000/yr)
- Inheritance Tax: NRB + RNRB, the four common scenario thresholds,
  iht_payable() computing taxable estate, IHT due, and after-IHT value
- State pension assumption for forecasts (2026/27 confirmed: £12,548/yr)

All money values in £. All rates as fractions (0.40 not 40).
"""
from __future__ import annotations


# ── 2025/26 allowances (constants) ─────────────────────────────────────────────
ISA_ALLOWANCE         = 20_000   # Annual ISA limit (cash + S&S + IF + LISA combined)
LISA_ALLOWANCE        = 4_000    # Lifetime ISA, counts inside ISA total
PENSION_AA            = 60_000   # Standard pension Annual Allowance
TAPER_THRESHOLD       = 260_000  # Adjusted income above which taper begins
TAPER_FLOOR           = 10_000   # Minimum tapered AA (reached at £360k adjusted income)
STATE_PENSION_2026_27 = 12_548   # Full new State Pension 2026/27: £241.30/wk × 52 (+4.8% triple lock)
STATE_PENSION_AGE      = 67      # SPA for cohorts retiring 2028+; rises to 68 from 2044
                                 # (proposed; could be brought forward). 66 for cohorts
                                 # who already qualified pre-2028.

# ── Life expectancy at retirement age (ONS 2020-22 cohort, mixed-sex) ─────────
# Approximate cohort life expectancy at each retirement age. Source: ONS
# National Life Tables, 2020-22 (UK, mixed-sex average). Used by the
# drawdown simulator to compare 'pot depletion age' against 'how long
# you're likely to live'. Treat as a rough planning anchor — actual
# longevity has a wide spread (many will live 10+ years beyond average).
LIFE_EXPECTANCY_AT_AGE = {
    55: 86, 60: 85, 65: 85, 67: 84, 70: 83, 75: 82, 80: 81,
}


def life_expectancy_at(retirement_age: int) -> int:
    """
    UK ONS cohort life expectancy at a given retirement age (mixed-sex).
    Interpolates for ages not directly in the lookup table.
    """
    if retirement_age in LIFE_EXPECTANCY_AT_AGE:
        return LIFE_EXPECTANCY_AT_AGE[retirement_age]
    # Outside the table: rough linear extrapolation from age 65 (~85),
    # losing ~0.2 years per year of late retirement
    return int(85 - max(0, retirement_age - 65) * 0.2)

# ── IHT (Inheritance Tax) thresholds 2025/26 ───────────────────────────────────
# Both nil-rate bands are frozen at these values until April 2031
# (the freeze was extended by a further year at the Autumn Budget 2025).
NIL_RATE_BAND          = 325_000  # Per person standard nil-rate band
RESIDENCE_NIL_RATE_BAND = 175_000  # Extra if main residence left to direct descendants
IHT_STANDARD_RATE      = 0.40     # Standard IHT rate above the thresholds
IHT_REDUCED_RATE       = 0.36     # Reduced rate if 10%+ of net estate left to charity

# Combined thresholds for the four common scenarios
IHT_BANDS = {
    "single":             NIL_RATE_BAND,
    "single_with_rnrb":   NIL_RATE_BAND + RESIDENCE_NIL_RATE_BAND,
    "married":            2 * NIL_RATE_BAND,
    "married_with_rnrb":  2 * NIL_RATE_BAND + 2 * RESIDENCE_NIL_RATE_BAND,
}


def iht_payable(
    gross_estate: float,
    threshold: float,
    deductions: float = 0.0,
    rate: float = IHT_STANDARD_RATE,
) -> tuple[float, float, float]:
    """
    Compute UK Inheritance Tax due on an estate.

    Returns (taxable_estate, iht_due, after_iht).
    All inputs and outputs in £.
    """
    exempt = max(0.0, threshold + max(0.0, deductions))
    taxable = max(0.0, gross_estate - exempt)
    due = taxable * rate
    after = gross_estate - due
    return taxable, due, after


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


def lisa_remaining(
    contributed_this_year: float,
    age: int | None = None,
    has_existing_lisa: bool | None = None,
) -> float:
    """
    Remaining LISA pay-in headroom for the current tax year.

    LISA rules (2025/26):
    - You can only OPEN a LISA between age 18 and 39 inclusive.
    - Once opened, you can contribute up to £4,000/yr until age 50.
    - From age 50 onwards, no new contributions (existing balance keeps growing).
    - If you reach age 40 without ever opening a LISA, you can no longer open one
      and therefore can no longer contribute.

    Parameters
    ----------
    contributed_this_year : £ already paid in this tax year.
    age : current age in years. None = assume eligible (legacy/permissive).
    has_existing_lisa : True if the user already has an open LISA. Used only
        when age is in [40, 50] — otherwise the age alone determines eligibility.
        None = assume yes (legacy/permissive default, matches prior behaviour).

    Returns 0 when contributions are not allowed at all; otherwise the £
    remaining of the £4,000 annual allowance.
    """
    if age is not None:
        if age < 18:
            return 0.0
        if age > 50:
            return 0.0
        # Between 40 and 50: only eligible if a LISA was already opened
        if age >= 40 and has_existing_lisa is False:
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
