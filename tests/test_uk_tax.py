"""
Tests for utils/uk_tax.py — UK 2025/26 tax rules.

Covers: pension AA + taper + carryforward, ISA + LISA (age-aware) remaining,
pension relief estimate, LISA bonus, and IHT (nil-rate bands, four scenario
thresholds, iht_payable function).
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.uk_tax import (  # noqa: E402
    tapered_pension_allowance, effective_pension_allowance,
    isa_remaining, lisa_remaining, pension_relief_estimate, lisa_bonus,
    iht_payable, life_expectancy_at,
    ISA_ALLOWANCE, LISA_ALLOWANCE, PENSION_AA, TAPER_THRESHOLD, TAPER_FLOOR,
    NIL_RATE_BAND, RESIDENCE_NIL_RATE_BAND, IHT_STANDARD_RATE, IHT_REDUCED_RATE,
    IHT_BANDS, STATE_PENSION_AGE, STATE_PENSION_2026_27,
    LIFE_EXPECTANCY_AT_AGE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Pension allowance taper
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("income", [0, 50_000, 100_000, 200_000, 259_999, 260_000])
def test_no_taper_below_threshold(income):
    """Standard £60k AA up to and including £260k adjusted income."""
    aa, reduction = tapered_pension_allowance(income)
    assert aa == PENSION_AA
    assert reduction == 0


def test_taper_at_280k_reduces_by_10k():
    """£280k adjusted income → £20k over threshold → £10k reduction → AA £50k."""
    aa, reduction = tapered_pension_allowance(280_000)
    assert aa == 50_000
    assert reduction == 10_000


def test_taper_reaches_floor_at_360k():
    """£360k → £100k over → £50k reduction → AA floor of £10k."""
    aa, reduction = tapered_pension_allowance(360_000)
    assert aa == TAPER_FLOOR
    assert reduction == PENSION_AA - TAPER_FLOOR


def test_taper_clamps_at_floor_for_extreme_income():
    """At £1m adjusted income, AA should still be £10k floor — not negative."""
    aa, _ = tapered_pension_allowance(1_000_000)
    assert aa == TAPER_FLOOR


def test_taper_is_continuous_at_threshold():
    """No discontinuity at £260k — both sides give £60k."""
    aa_below, _ = tapered_pension_allowance(259_999)
    aa_at,    _ = tapered_pension_allowance(260_000)
    assert aa_below == aa_at == PENSION_AA


# ──────────────────────────────────────────────────────────────────────────────
# Effective allowance (AA + carryforward)
# ──────────────────────────────────────────────────────────────────────────────

def test_effective_allowance_no_carryforward():
    assert effective_pension_allowance(100_000, 0) == PENSION_AA


def test_effective_allowance_with_carryforward():
    assert effective_pension_allowance(100_000, 30_000) == PENSION_AA + 30_000


def test_effective_allowance_tapered_plus_carryforward():
    """At £280k income (AA £50k) plus £40k carryforward = £90k total."""
    assert effective_pension_allowance(280_000, 40_000) == 90_000


def test_effective_allowance_negative_carryforward_ignored():
    """Defensive: negative carryforward shouldn't reduce the allowance."""
    assert effective_pension_allowance(100_000, -10_000) == PENSION_AA


# ──────────────────────────────────────────────────────────────────────────────
# ISA / LISA remaining
# ──────────────────────────────────────────────────────────────────────────────

def test_isa_remaining_empty():
    assert isa_remaining(0) == ISA_ALLOWANCE


def test_isa_remaining_partial():
    assert isa_remaining(5_000) == ISA_ALLOWANCE - 5_000


def test_isa_remaining_maxed():
    assert isa_remaining(20_000) == 0


def test_isa_remaining_over_max_clamps_to_zero():
    assert isa_remaining(25_000) == 0  # never negative


def test_lisa_remaining_under_age_50():
    assert lisa_remaining(0, age=30) == LISA_ALLOWANCE
    assert lisa_remaining(2_500, age=30) == 1_500


def test_lisa_remaining_at_50():
    """At 50 you can still pay in (LISA pay-in stops at 50)."""
    assert lisa_remaining(0, age=50) == LISA_ALLOWANCE


def test_lisa_remaining_over_50():
    """Over 50, no more LISA contributions allowed."""
    assert lisa_remaining(0, age=55) == 0


def test_lisa_remaining_no_age_argument():
    """Age unknown → assume eligible."""
    assert lisa_remaining(0) == LISA_ALLOWANCE


# ──────────────────────────────────────────────────────────────────────────────
# Tax relief + LISA bonus
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("contribution,rate,expected", [
    (1_000,  0.20,    200),  # basic rate
    (10_000, 0.40,  4_000),  # higher rate
    (5_000,  0.45,  2_250),  # additional rate
    (0,      0.40,      0),
    (-500,   0.40,      0),  # defensive: don't compute relief on negative
])
def test_pension_relief_estimate(contribution, rate, expected):
    assert pension_relief_estimate(contribution, rate) == expected


def test_lisa_bonus_under_cap():
    assert lisa_bonus(2_000) == 500    # 25% of £2k
    assert lisa_bonus(0)     == 0


def test_lisa_bonus_capped_at_1k():
    """LISA bonus capped at £1k/yr regardless of contribution size."""
    assert lisa_bonus(4_000) == 1_000   # 25% of £4k
    assert lisa_bonus(10_000) == 1_000  # cap still applies


# ──────────────────────────────────────────────────────────────────────────────
# IHT (Inheritance Tax)
# ──────────────────────────────────────────────────────────────────────────────

def test_iht_bands_dict_matches_constants():
    """The four named scenarios should match their math."""
    assert IHT_BANDS["single"]            == NIL_RATE_BAND
    assert IHT_BANDS["single_with_rnrb"]  == NIL_RATE_BAND + RESIDENCE_NIL_RATE_BAND
    assert IHT_BANDS["married"]           == 2 * NIL_RATE_BAND
    assert IHT_BANDS["married_with_rnrb"] == 2 * NIL_RATE_BAND + 2 * RESIDENCE_NIL_RATE_BAND
    assert IHT_BANDS["married_with_rnrb"] == 1_000_000  # The famous £1m


def test_iht_payable_below_threshold_is_zero():
    """Estate below NRB → no IHT due."""
    taxable, due, after = iht_payable(300_000, threshold=NIL_RATE_BAND)
    assert taxable == 0
    assert due == 0
    assert after == 300_000


def test_iht_payable_at_threshold_exactly_zero():
    """Estate equal to threshold → no IHT due."""
    taxable, due, after = iht_payable(NIL_RATE_BAND, threshold=NIL_RATE_BAND)
    assert taxable == 0
    assert due == 0


def test_iht_payable_single_above_nrb():
    """Single, £500k estate, £325k NRB, 40% → 40% × £175k = £70k IHT due."""
    taxable, due, after = iht_payable(500_000, threshold=NIL_RATE_BAND)
    assert taxable == 175_000
    assert due == 70_000
    assert after == 430_000


def test_iht_payable_married_with_rnrb_1m():
    """The famous £1m family threshold — £1.5m estate, £200k IHT due."""
    taxable, due, after = iht_payable(1_500_000, threshold=IHT_BANDS["married_with_rnrb"])
    assert taxable == 500_000
    assert due == 200_000
    assert after == 1_300_000


def test_iht_payable_with_deductions():
    """Deductions (charitable gifts, business relief, etc.) reduce the taxable estate."""
    taxable, due, _ = iht_payable(
        500_000, threshold=NIL_RATE_BAND, deductions=50_000,
    )
    # Exempt = 325 + 50 = 375k → taxable = 500 - 375 = 125k → due = 50k
    assert taxable == 125_000
    assert due == 50_000


def test_iht_payable_reduced_rate():
    """36% rate (10%+ charitable gift) reduces IHT due."""
    _, due_full, _ = iht_payable(1_000_000, threshold=NIL_RATE_BAND, rate=IHT_STANDARD_RATE)
    _, due_red,  _ = iht_payable(1_000_000, threshold=NIL_RATE_BAND, rate=IHT_REDUCED_RATE)
    assert due_red < due_full
    # Specifically: taxable = 675k → 40% = 270k, 36% = 243k
    assert due_full == 270_000
    assert due_red  == 243_000


def test_iht_payable_zero_estate_safe():
    """Zero or negative estate produces no IHT and doesn't crash."""
    taxable, due, after = iht_payable(0, threshold=NIL_RATE_BAND)
    assert taxable == due == 0
    assert after == 0


# ──────────────────────────────────────────────────────────────────────────────
# State pension constants
# ──────────────────────────────────────────────────────────────────────────────

def test_state_pension_age_currently_67():
    """SPA for cohorts retiring 2028+ is 67. Bump this assertion when it changes."""
    assert STATE_PENSION_AGE == 67


def test_state_pension_amount_realistic():
    """2026/27 estimate should be in a plausible band given recent triple-lock uprating."""
    # 2024/25 was £11,502. 2025/26 was £11,973. 2026/27 estimate ~£12,400.
    # If this assertion fails because the figure was refreshed, just update it.
    assert 11_500 <= STATE_PENSION_2026_27 <= 13_500


# ──────────────────────────────────────────────────────────────────────────────
# Life expectancy at retirement age
# ──────────────────────────────────────────────────────────────────────────────

def test_life_expectancy_lookup_table_covers_common_ages():
    """The table should have at least the standard retirement ages."""
    for age in (55, 60, 65, 67, 70, 75, 80):
        assert age in LIFE_EXPECTANCY_AT_AGE, f"age {age} missing from lookup"


def test_life_expectancy_at_known_ages():
    """Verify the function returns the exact lookup value for ages in the table."""
    assert life_expectancy_at(65) == 85
    assert life_expectancy_at(67) == 84
    assert life_expectancy_at(60) == 85


def test_life_expectancy_at_extrapolates_outside_table():
    """For ages not in the table, the function should still return a reasonable value."""
    # Age 62 is between 60 (LE 85) and 65 (LE 85) — should fall back to extrapolation
    le = life_expectancy_at(62)
    assert 80 < le <= 90, f"life_expectancy_at(62) = {le}, outside plausible range"


def test_life_expectancy_monotone_non_increasing():
    """Cohort life expectancy should weakly decrease (or stay the same) as
    retirement age rises — older retirees are starting from a later baseline."""
    ages = sorted(LIFE_EXPECTANCY_AT_AGE.keys())
    values = [LIFE_EXPECTANCY_AT_AGE[a] for a in ages]
    for a, b in zip(values, values[1:]):
        assert a >= b, f"Life expectancy not monotone non-increasing: {values}"
