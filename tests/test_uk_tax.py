"""Tests for utils/uk_tax.py — UK 2025/26 tax wrapper rules."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.uk_tax import (  # noqa: E402
    tapered_pension_allowance, effective_pension_allowance,
    isa_remaining, lisa_remaining, pension_relief_estimate, lisa_bonus,
    ISA_ALLOWANCE, LISA_ALLOWANCE, PENSION_AA, TAPER_THRESHOLD, TAPER_FLOOR,
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
