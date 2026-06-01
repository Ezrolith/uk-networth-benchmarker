"""
Tests for the inference layer (utils/inference.py).

These cover the maths the app trusts: PCHIP interpolation, log-normal percentile
fit, CPI adjustment, household→individual sharing, and gender adjustment. Catching
silent breakage here is the highest-value test surface.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.inference import (  # noqa: E402
    convert_to_individual,
    apply_gender_adjustment,
    adjust_for_inflation,
    cpi_adjust_personal,
    estimate_exact_percentile,
    estimate_percentile,
    derive_tail_percentiles,
    build_percentile_trajectory,
    build_decile_table,
    apply_component_filter,
    UK_CPI,
)

# Fixtures (raw_was, benchmark) live in tests/conftest.py


# ──────────────────────────────────────────────────────────────────────────────
# Interpolation
# ──────────────────────────────────────────────────────────────────────────────

def test_interpolation_covers_full_age_range(benchmark: pd.DataFrame):
    for pct in ("p25", "p50", "p75"):
        ages = benchmark[benchmark["percentile"] == pct]["age"].sort_values().unique()
        assert ages.min() == 16
        assert ages.max() == 85
        assert len(ages) == 70  # 16..85 inclusive


def test_interpolation_passes_through_band_midpoints(raw_was, benchmark):
    """At each WAS band midpoint, interpolated value must equal published value."""
    pub = raw_was[raw_was["with_pension"] == True]
    for _, row in pub.iterrows():
        age = int(row["band_midpoint"])
        pct = row["percentile"]
        interp_val = benchmark[
            (benchmark["age"] == age) & (benchmark["percentile"] == pct)
        ]["value"].iloc[0]
        # load_was_data() renames value_nominal -> value
        assert interp_val == pytest.approx(row["value"], rel=1e-6)


def test_interpolation_preserves_ordering(benchmark: pd.DataFrame):
    """At every age, P25 < P50 < P75."""
    for age in range(16, 86):
        p25 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p25")]["value"].iloc[0]
        p50 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p50")]["value"].iloc[0]
        p75 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p75")]["value"].iloc[0]
        assert p25 < p50 < p75, f"Percentile ordering broken at age {age}"


# ──────────────────────────────────────────────────────────────────────────────
# Log-normal percentile model
# ──────────────────────────────────────────────────────────────────────────────

def test_exact_percentile_recovers_quartiles_approximately(benchmark: pd.DataFrame):
    """
    A net worth equal to P50 must land exactly at the 50th percentile (mu = log(P50)
    means CDF(P50) = 0.5 by construction). P25 and P75 are recovered approximately
    because the WAS data has positive skew that isn't perfect log-normal — the
    methodology panel acknowledges ±5–10 percentile points indicative accuracy.
    """
    age = 40
    p25 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p25")]["value"].iloc[0]
    p50 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p50")]["value"].iloc[0]
    p75 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p75")]["value"].iloc[0]

    # Median is exact by construction
    assert estimate_exact_percentile(p50, age, benchmark) == pytest.approx(50, abs=0.5)
    # Quartiles within indicative tolerance per documented methodology
    assert estimate_exact_percentile(p25, age, benchmark) == pytest.approx(25, abs=5)
    assert estimate_exact_percentile(p75, age, benchmark) == pytest.approx(75, abs=5)


def test_exact_percentile_monotone_in_net_worth(benchmark):
    """At fixed age, higher net worth → higher percentile."""
    age = 40
    values = [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]
    pcts = [estimate_exact_percentile(v, age, benchmark) for v in values]
    for a, b in zip(pcts, pcts[1:]):
        assert a < b


def test_exact_percentile_returns_none_for_zero_or_negative(benchmark):
    assert estimate_exact_percentile(0, 40, benchmark) is None
    assert estimate_exact_percentile(-1000, 40, benchmark) is None


def test_string_percentile_band_labels(benchmark):
    age = 40
    p50 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p50")]["value"].iloc[0]
    assert "median" in estimate_percentile(p50 * 0.7, age, benchmark)
    assert "above the 75th" in estimate_percentile(p50 * 5, age, benchmark)
    assert "below zero" in estimate_percentile(-1, age, benchmark)


# ──────────────────────────────────────────────────────────────────────────────
# CPI adjustment
# ──────────────────────────────────────────────────────────────────────────────

def test_cpi_adjustment_matches_index_ratio(benchmark):
    """Real-terms value should equal nominal × (CPI_to / CPI_from)."""
    nominal = benchmark.copy()
    real = adjust_for_inflation(nominal, from_year=2019, to_year=2026)
    expected_ratio = UK_CPI[2026] / UK_CPI[2019]
    sample = nominal[(nominal["age"] == 40) & (nominal["percentile"] == "p50")]["value"].iloc[0]
    real_sample = real[(real["age"] == 40) & (real["percentile"] == "p50")]["value"].iloc[0]
    assert real_sample == pytest.approx(sample * expected_ratio, rel=1e-6)


def test_cpi_adjustment_is_identity_when_same_year(benchmark):
    out = adjust_for_inflation(benchmark, from_year=2019, to_year=2019)
    pd.testing.assert_series_equal(out["value"], benchmark["value"])


def test_personal_cpi_adjustment_per_row():
    personal = pd.DataFrame({
        "year": [2019, 2026],
        "age":  [30.0, 37.0],
        "net_worth": [50_000.0, 50_000.0],
    })
    out = cpi_adjust_personal(personal, to_year=2026)
    # 2019 entry should scale up; 2026 entry should be unchanged
    assert out.iloc[0]["net_worth"] == pytest.approx(50_000 * UK_CPI[2026] / UK_CPI[2019], rel=1e-6)
    assert out.iloc[1]["net_worth"] == pytest.approx(50_000, rel=1e-6)


def test_cpi_table_is_clean_2015_base_series():
    """UK_CPI must be a clean ONS annual-average series on the 2015=100 base.

    Guards two historical bugs:
    - 2020 was stalled at the 2019 value (a fake 0% inflation year).
    - Pre-2015 values were spliced from a different base, making the index
      *fall* ~6.6% at 2014→2015 (an impossible year-on-year deflation).
    """
    years = sorted(UK_CPI)
    assert UK_CPI[2015] == pytest.approx(100.0)  # the index base year
    for earlier, later in zip(years, years[1:]):
        assert UK_CPI[later] >= UK_CPI[earlier], f"UK_CPI fell from {earlier} to {later}"
    assert UK_CPI[2020] > UK_CPI[2019], "2020 must not duplicate 2019 (stalled-CPI bug)"


# ──────────────────────────────────────────────────────────────────────────────
# Individual + gender conversions
# ──────────────────────────────────────────────────────────────────────────────

def test_individual_basis_reduces_values(benchmark):
    """Per the sharing-factor model, individual values must be ≤ household values."""
    ind = convert_to_individual(benchmark)
    for age in range(20, 81, 10):
        h = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p50")]["value"].iloc[0]
        i = ind[(ind["age"] == age) & (ind["percentile"] == "p50")]["value"].iloc[0]
        assert i < h, f"Individual not lower than household at age {age}"


def test_gender_all_is_passthrough(benchmark):
    ind = convert_to_individual(benchmark)
    out = apply_gender_adjustment(ind, "All")
    pd.testing.assert_frame_equal(out.reset_index(drop=True), ind.reset_index(drop=True))


def test_gender_male_and_female_bracket_combined(benchmark):
    """At any age, Female < combined < Male — and their mean equals the combined value."""
    ind = convert_to_individual(benchmark)
    male   = apply_gender_adjustment(ind, "Male")
    female = apply_gender_adjustment(ind, "Female")
    for age in (30, 50, 70):
        c = ind[(ind["age"] == age) & (ind["percentile"] == "p50")]["value"].iloc[0]
        m = male[(male["age"] == age) & (male["percentile"] == "p50")]["value"].iloc[0]
        f = female[(female["age"] == age) & (female["percentile"] == "p50")]["value"].iloc[0]
        assert f < c < m, f"Female/Male bracket broken at age {age}"
        assert (m + f) / 2 == pytest.approx(c, rel=0.02)


# ──────────────────────────────────────────────────────────────────────────────
# Derived series: tails, trajectory, deciles, components
# ──────────────────────────────────────────────────────────────────────────────

def test_derive_tail_percentiles_orderly(benchmark):
    tails = derive_tail_percentiles(benchmark)
    for age in (30, 50, 70):
        p10 = tails[(tails["age"] == age) & (tails["percentile"] == "p10")]["value"].iloc[0]
        p90 = tails[(tails["age"] == age) & (tails["percentile"] == "p90")]["value"].iloc[0]
        p25 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p25")]["value"].iloc[0]
        p75 = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p75")]["value"].iloc[0]
        assert p10 < p25 < p75 < p90


def test_build_percentile_trajectory_shape(benchmark):
    # Use the actual P50 at age 40 from the benchmark, so this test stays
    # correct whenever the underlying WAS figures are refreshed.
    p50_at_40 = benchmark[(benchmark["age"] == 40) & (benchmark["percentile"] == "p50")]["value"].iloc[0]
    personal = pd.DataFrame({
        "age":       [30.0, 35.0, 40.0],
        "year":      [2020, 2025, 2030],
        "net_worth": [25_000.0, 75_000.0, p50_at_40],
    })
    traj = build_percentile_trajectory(personal, benchmark)
    assert len(traj) == 3
    assert set(traj.columns) >= {"age", "percentile", "net_worth"}
    # The 40-year-old at the P50 value should be exactly the 50th percentile
    assert traj.iloc[-1]["percentile"] == pytest.approx(50, abs=0.5)


def test_decile_table_contains_eleven_rows(benchmark):
    """build_decile_table returns P10, P20, P25, P30, ..., P75, P80, P90 = 11 rows."""
    table = build_decile_table(age=40, benchmark=benchmark)
    assert len(table) == 11
    # Monotone in value
    values = list(table["Net worth (£)"])
    assert values == sorted(values)
    # Published markers (P25/P50/P75) flagged as not modelled
    published = table[table["Percentile"].isin(["P25", "P50", "P75"])]
    assert (published["Modelled"] == False).all()
    # Modelled values flagged correctly
    modelled = table[~table["Percentile"].isin(["P25", "P50", "P75"])]
    assert (modelled["Modelled"] == True).all()


def test_component_filter_scales_down(benchmark):
    """Filtering to Property should produce values strictly less than Total."""
    asset_df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "was_asset_class.csv")
    filtered = apply_component_filter(benchmark, "Property", asset_df)
    for age in (30, 50, 70):
        full = benchmark[(benchmark["age"] == age) & (benchmark["percentile"] == "p50")]["value"].iloc[0]
        part = filtered[(filtered["age"] == age) & (filtered["percentile"] == "p50")]["value"].iloc[0]
        assert 0 < part < full


def test_component_filter_total_is_passthrough(benchmark):
    asset_df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "was_asset_class.csv")
    out = apply_component_filter(benchmark, "Total", asset_df)
    pd.testing.assert_series_equal(out["value"].reset_index(drop=True),
                                    benchmark["value"].reset_index(drop=True))


def test_component_filter_rejects_unknown_component(benchmark):
    """Unknown component names should fail with a clear ValueError, not KeyError."""
    asset_df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "was_asset_class.csv")
    with pytest.raises(ValueError, match="Unknown component"):
        apply_component_filter(benchmark, "Crypto", asset_df)


def test_component_filter_error_lists_valid_options(benchmark):
    """The error message should list every valid component name to help the caller."""
    asset_df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "was_asset_class.csv")
    try:
        apply_component_filter(benchmark, "BadName", asset_df)
    except ValueError as exc:
        msg = str(exc)
        for valid in ("Total", "Property", "Pension", "Financial", "Physical"):
            assert valid in msg, f"valid component {valid!r} not listed in error"
