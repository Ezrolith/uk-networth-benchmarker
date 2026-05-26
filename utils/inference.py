"""
Inference utilities: age interpolation, individual conversion, CPI adjustment.

All derived calculations are documented here so the methodology panel in the app
can describe them accurately.
"""

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

# ── Individual conversion factors ────────────────────────────────────────────
#
# WAS publishes household-level wealth. To estimate individual wealth we apply
# an age-specific sharing factor derived from two ONS sources:
#   1. Household composition by age of HRP (ONS: Families and Households)
#   2. Proportion of total wealth that is pension-based (WAS wave 7 component tables)
#
# Pension wealth is already tracked per-individual in WAS, so it does not get
# divided. For non-pension wealth the factor reflects average household size
# weighted by the couple vs single composition.
#
# Formula per age band:
#   sharing_factor = pension_share + (1 - pension_share) × (couple_share × 0.5 + single_share)
#
# where single_share = 1 - couple_share and couple_share is the fraction of
# households headed by someone in that age band that are couple households.
#
# These are point estimates; treat individual figures as approximate (±15–20%).

# ── Gender adjustment factors ─────────────────────────────────────────────────
#
# WAS Wave 7 shows a persistent gender wealth gap, driven primarily by pension wealth.
# Women in each age band hold approximately the following fraction of male individual
# wealth (WAS individual-level tables, pension + financial components):
#
# These are approximate ratios from WAS analysis. The gap is smallest for property
# (jointly owned) and largest for pension (career/salary differences).

_GENDER_FACTOR_FEMALE = {   # female wealth as fraction of male wealth, by midpoint
    20: 0.92,   # small gap at start of career
    30: 0.82,   # career break / part-time impacts start to appear
    40: 0.72,   # widest pension gap (peak career-break years)
    50: 0.68,   # cumulative pension gap dominates
    60: 0.70,   # DB pension equalisation via survivor benefits begins
    70: 0.75,   # widowed women inherit some of gap back
    80: 0.80,   # greater female longevity, more single-female households
}
# Male is taken as the baseline (factor = 1.0)

def apply_gender_adjustment(df: pd.DataFrame, gender: str) -> pd.DataFrame:
    """
    Adjust individual-basis benchmark values for gender.

    The individual conversion (`convert_to_individual`) produces a gender-averaged
    benchmark (both sexes combined).  This function shifts that to a male or female
    individual view while preserving the all-gender average:

      Male factor   = 2 / (1 + fom)          — above the combined average
      Female factor = 2 × fom / (1 + fom)    — below the combined average
      Average of both = 1.0  ✓

    where fom = female wealth as a fraction of male wealth at that age
    (from _GENDER_FACTOR_FEMALE).  The Male/Female ratio equals the original 1/fom.

    'All' returns df unchanged.  Only meaningful when basis == 'Individual'.
    Treat as approximate (±10–15%).
    """
    if gender == "All":
        return df
    midpoints = sorted(_GENDER_FACTOR_FEMALE)
    fom_vals  = [_GENDER_FACTOR_FEMALE[m] for m in midpoints]
    interp    = PchipInterpolator(midpoints, fom_vals, extrapolate=True)
    df   = df.copy()
    ages = df["age"].values.astype(float)
    fom  = np.clip(interp(ages), 0.5, 1.1)   # female-of-male ratio, bounded

    if gender == "Female":
        scalar = 2.0 * fom / (1.0 + fom)
    else:  # "Male"
        scalar = 2.0 / (1.0 + fom)

    df["value"] = df["value"] * scalar
    df["is_published"] = False
    return df


_INDIVIDUAL_FACTORS_BY_MIDPOINT = {
    20: 0.71,   # few couples, little pension → mostly single, divide by ~1.4
    30: 0.63,   # growing couples, modest pension
    40: 0.55,   # peak family size, substantial but not dominant pension
    50: 0.57,   # similar couple share, pension growing as fraction
    60: 0.61,   # empty-nesters, large pension fraction
    70: 0.66,   # more widowed singles, pension/property mix
    80: 0.76,   # majority single-person households
}

# ── UK CPI (2015 = 100) ───────────────────────────────────────────────────────
# Annual average ONS CPI. Extended to 2025 using OBR central forecast.
UK_CPI = {
    2000: 79.3,  2001: 80.9,  2002: 81.9,  2003: 83.5,
    2004: 84.8,  2005: 87.0,  2006: 89.4,  2007: 91.5,
    2008: 95.4,  2009: 95.2,  2010: 97.9,  2011: 101.9,
    2012: 104.5, 2013: 106.4, 2014: 107.1, 2015: 100.0,
    2016: 101.0, 2017: 103.6, 2018: 106.0, 2019: 108.5,
    2020: 108.5, 2021: 111.8, 2022: 121.9, 2023: 132.0,
    2024: 136.2, 2025: 139.0, 2026: 141.7,  # 2026 estimated: ~1.9% from 2025 (OBR March 2025 forecast)
}

DATA_YEAR = 2021  # mid-point of WAS Wave 8 (April 2020 to March 2022)
REAL_BASE_YEAR = 2026


def interpolate_benchmarks(band_data: pd.DataFrame, age_range: np.ndarray) -> pd.DataFrame:
    """
    Interpolate WAS age-band data to single-year ages using PCHIP monotone spline.

    PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) preserves shape
    monotonicity within each interval, preventing the oscillation artifacts that
    plain cubic splines produce when wealth flattens in later life.

    Returns a tidy DataFrame with columns:
        age, percentile, with_pension, value, is_published
    where is_published=True only at band midpoints.
    """
    results = []
    published_ages = set(band_data["band_midpoint"].unique())

    for (percentile, with_pension), group in band_data.groupby(["percentile", "with_pension"]):
        group = group.sort_values("band_midpoint")
        midpoints = group["band_midpoint"].values.astype(float)
        values = group["value"].values.astype(float)

        interp = PchipInterpolator(midpoints, values, extrapolate=True)

        # Evaluate; clamp extrapolation to nearest endpoint value
        raw_values = interp(age_range.astype(float))
        clamp_low = values[0]
        clamp_high = values[-1]

        for age, val in zip(age_range, raw_values):
            if age < midpoints[0]:
                val = clamp_low
            elif age > midpoints[-1]:
                val = clamp_high
            val = max(0.0, float(val))

            results.append({
                "age": int(age),
                "percentile": percentile,
                "with_pension": bool(with_pension),
                "value": val,
                "is_published": int(age) in published_ages,
            })

    return pd.DataFrame(results)


def convert_to_individual(df: pd.DataFrame) -> pd.DataFrame:
    """
    Scale household wealth to individual basis using age-specific sharing factors.

    All individual-basis output is flagged is_published=False because it is
    always a derived estimate, regardless of whether the household input was
    a published data point.
    """
    midpoints = sorted(_INDIVIDUAL_FACTORS_BY_MIDPOINT)
    factor_values = [_INDIVIDUAL_FACTORS_BY_MIDPOINT[m] for m in midpoints]
    factor_interp = PchipInterpolator(midpoints, factor_values, extrapolate=True)

    df = df.copy()
    ages = df["age"].values.astype(float)
    factors = np.clip(factor_interp(ages), 0.4, 1.0)
    df["value"] = df["value"] * factors
    df["is_published"] = False  # individual is always inferred
    return df


def adjust_for_inflation(
    df: pd.DataFrame,
    from_year: int = DATA_YEAR,
    to_year: int = REAL_BASE_YEAR,
) -> pd.DataFrame:
    """CPI-adjust values from from_year prices to to_year prices."""
    if from_year == to_year:
        return df
    if from_year not in UK_CPI or to_year not in UK_CPI:
        raise ValueError(f"CPI data not available for {from_year} or {to_year}")
    factor = UK_CPI[to_year] / UK_CPI[from_year]
    df = df.copy()
    df["value"] = df["value"] * factor
    return df


def cpi_adjust_personal(
    personal_df: pd.DataFrame,
    to_year: int = REAL_BASE_YEAR,
) -> pd.DataFrame:
    """
    CPI-adjust personal net worth entries from their recorded year to to_year.
    Each row uses its own 'year' column as the from_year.
    """
    df = personal_df.copy()
    adjusted = []
    for _, row in df.iterrows():
        from_year = int(row["year"])
        nw = float(row["net_worth"])
        if from_year in UK_CPI and to_year in UK_CPI:
            nw = nw * UK_CPI[to_year] / UK_CPI[from_year]
        adjusted.append(nw)
    df["net_worth"] = adjusted
    return df


def estimate_percentile(net_worth: float, age: int, benchmark: pd.DataFrame) -> str:
    """Return a human-readable percentile band for a given net worth at a given age."""
    age_clamped = min(int(age), 85)
    age_data = benchmark[benchmark["age"] == age_clamped]

    def get_val(pct: str) -> float:
        rows = age_data[age_data["percentile"] == pct]["value"]
        return float(rows.iloc[0]) if len(rows) else np.nan

    p25 = get_val("p25")
    p50 = get_val("p50")
    p75 = get_val("p75")

    if np.isnan(p25):
        return "unknown"
    if net_worth < 0:
        return "below zero (negative net worth)"
    if net_worth < p25:
        return "below the 25th percentile"
    if net_worth < p50:
        return "between the 25th percentile and the median"
    if net_worth < p75:
        return "between the median and the 75th percentile"
    return "above the 75th percentile"


def estimate_exact_percentile(
    net_worth: float, age: int, benchmark: pd.DataFrame
) -> float | None:
    """
    Estimate a continuous percentile (0–100) for a net worth at a given age.

    Fits a log-normal distribution to the three published percentiles (P25, P50, P75)
    at the requested age, then evaluates the CDF.

    Log-normality is a reasonable approximation for wealth distributions but is a
    modelling assumption — treat results as indicative, not authoritative. Label as
    "estimated" in all user-facing text.

    Returns None if the fit cannot be computed (missing data, non-positive net worth,
    or degenerate quantiles).
    """
    from scipy.stats import norm as _norm

    age_clamped = min(int(age), 85)
    age_data = benchmark[benchmark["age"] == age_clamped]

    def get_val(pct: str) -> float | None:
        rows = age_data[age_data["percentile"] == pct]["value"]
        return float(rows.iloc[0]) if len(rows) else None

    p25v = get_val("p25")
    p50v = get_val("p50")
    p75v = get_val("p75")

    if any(v is None or v <= 0 for v in [p25v, p50v, p75v]):
        return None
    if net_worth <= 0:
        return None

    # Log-normal parameters from quantiles:
    #   mu  = log(median)           [median of log-normal = e^mu]
    #   sigma = (log(P75) - log(P25)) / (2 × 0.6745)
    #         because Phi(0.6745) = 0.75 by definition of the normal z-score
    mu = np.log(p50v)
    sigma = (np.log(p75v) - np.log(p25v)) / (2 * 0.6745)

    if sigma <= 0:
        return None

    z = (np.log(net_worth) - mu) / sigma
    return float(np.clip(_norm.cdf(z) * 100, 0.5, 99.5))


def derive_tail_percentiles(benchmark: pd.DataFrame) -> pd.DataFrame:
    """
    Derive P10 and P90 series from the log-normal fit used for exact percentile estimation.

    Since WAS only publishes P25/P50/P75, tail percentiles are modelled — clearly an
    inference. The same log-normal parameters (mu, sigma) are computed per age, then
    the 10th and 90th quantiles of that distribution are returned.

    Returns a tidy DataFrame with the same schema as the benchmark but with
    percentile values 'p10' and 'p90', and is_published=False for all rows.
    """
    from scipy.stats import norm as _norm

    results = []
    for age in benchmark["age"].unique():
        age_data = benchmark[benchmark["age"] == age]
        for with_pension in [True, False]:
            sub = age_data[age_data["with_pension"] == with_pension]

            def get_val(pct: str) -> float | None:
                rows = sub[sub["percentile"] == pct]["value"]
                return float(rows.iloc[0]) if len(rows) else None

            p25v = get_val("p25")
            p50v = get_val("p50")
            p75v = get_val("p75")

            if any(v is None or v <= 0 for v in [p25v, p50v, p75v]):
                continue

            mu    = np.log(p50v)
            sigma = (np.log(p75v) - np.log(p25v)) / (2 * 0.6745)
            if sigma <= 0:
                continue

            for pct_label, z_score in [("p10", _norm.ppf(0.10)), ("p90", _norm.ppf(0.90))]:
                value = float(np.exp(mu + z_score * sigma))
                results.append({
                    "age":          int(age),
                    "percentile":   pct_label,
                    "with_pension": with_pension,
                    "value":        value,
                    "is_published": False,
                })

    return pd.DataFrame(results)


def build_decile_table(age: int, benchmark: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all deciles (10th–90th) at the given age using the log-normal model,
    plus the published P25/P50/P75 for reference.

    Returns a DataFrame with columns: percentile_label, value, is_modelled.
    """
    from scipy.stats import norm as _norm

    age_clamped = min(int(age), 85)
    age_data = benchmark[benchmark["age"] == age_clamped]

    def get_val(pct: str) -> float | None:
        rows = age_data[age_data["percentile"] == pct]["value"]
        return float(rows.iloc[0]) if len(rows) else None

    p25v = get_val("p25")
    p50v = get_val("p50")
    p75v = get_val("p75")

    if any(v is None or v <= 0 for v in [p25v, p50v, p75v]):
        return pd.DataFrame()

    mu    = np.log(p50v)
    sigma = (np.log(p75v) - np.log(p25v)) / (2 * 0.6745)

    published = {25: p25v, 50: p50v, 75: p75v}
    rows = []
    for pct in [10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90]:
        if pct in published:
            val = published[pct]
            modelled = False
        else:
            z   = _norm.ppf(pct / 100)
            val = float(np.exp(mu + z * sigma))
            modelled = True
        rows.append({"Percentile": f"P{pct}", "Net worth (£)": val, "Modelled": modelled})
    return pd.DataFrame(rows)


def build_asset_class_series(
    asset_df: pd.DataFrame,
    benchmark: pd.DataFrame,
    age_range: np.ndarray,
) -> pd.DataFrame:
    """
    Interpolate asset class component shares and combine with the P50 benchmark
    to produce £ values per component at each single year of age.

    Returns a tidy DataFrame with columns: age, component, value_pct, value_gbp.
    All figures are inferred — derived by multiplying the P50 benchmark by
    approximate component share proportions from WAS Wave 7.
    """
    midpoints = asset_df["band_midpoint"].values.astype(float)
    components = ["property_pct", "pension_pct", "financial_pct", "physical_pct"]
    labels     = {"property_pct": "Property", "pension_pct": "Pension",
                  "financial_pct": "Financial", "physical_pct": "Physical"}

    # Interpolate each component share to single years
    share_series: dict[str, np.ndarray] = {}
    for col in components:
        vals = asset_df[col].values.astype(float) / 100.0
        interp = PchipInterpolator(midpoints, vals, extrapolate=True)
        raw = interp(age_range.astype(float))
        share_series[col] = np.clip(raw, 0.0, 1.0)

    # Normalise so shares sum to 1.0 at each age
    total = sum(share_series.values())
    share_series = {k: v / np.maximum(total, 1e-9) for k, v in share_series.items()}

    # Get P50 benchmark values (with pension = True)
    p50 = benchmark[(benchmark["percentile"] == "p50") & (benchmark["with_pension"] == True)
                    ].set_index("age")["value"]

    rows = []
    for i, age in enumerate(age_range):
        p50_val = p50.get(int(age), np.nan)
        if np.isnan(p50_val):
            continue
        for col in components:
            rows.append({
                "age":       int(age),
                "component": labels[col],
                "value_pct": share_series[col][i] * 100,
                "value_gbp": share_series[col][i] * p50_val,
            })
    return pd.DataFrame(rows)


_COMPONENT_COL = {
    "Property":  "property_pct",
    "Pension":   "pension_pct",
    "Financial": "financial_pct",
    "Physical":  "physical_pct",
}

def apply_component_filter(
    bm: pd.DataFrame,
    component: str,
    asset_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Scale a benchmark DataFrame so its values represent a single wealth component
    rather than total wealth, using PCHIP-interpolated WAS asset class shares.

    component must be one of 'Property', 'Pension', 'Financial', 'Physical', or 'Total'.
    Returns bm unchanged if component == 'Total'.
    Shares are normalised so they sum to 1 at each age (same as build_asset_class_series).

    Raises ValueError if component is not one of the recognised values — failing
    fast rather than producing a confusing KeyError downstream.
    """
    if component == "Total":
        return bm

    if component not in _COMPONENT_COL:
        valid = sorted(["Total"] + list(_COMPONENT_COL.keys()))
        raise ValueError(
            f"Unknown component {component!r}. Expected one of: {', '.join(valid)}"
        )

    col = _COMPONENT_COL[component]
    midpoints = asset_df["band_midpoint"].values.astype(float)
    all_cols = list(_COMPONENT_COL.values())

    interps = {
        c: PchipInterpolator(midpoints, asset_df[c].values.astype(float) / 100.0, extrapolate=True)
        for c in all_cols
    }

    bm = bm.copy()
    ages = bm["age"].values.astype(float)
    component_shares = np.clip(interps[col](ages), 0.0, None)
    total_shares = sum(np.clip(interps[c](ages), 0.0, None) for c in all_cols)
    normalised = component_shares / np.maximum(total_shares, 1e-9)
    bm["value"] = bm["value"].values * normalised
    return bm


def build_percentile_trajectory(
    personal_df: pd.DataFrame, benchmark: pd.DataFrame
) -> pd.DataFrame:
    """
    Compute estimated percentile at each personal data point.
    Returns a DataFrame with columns: age, year, net_worth, percentile.
    Rows where the percentile cannot be estimated (e.g. negative NW) are dropped.
    Returns an empty typed DataFrame if no rows qualify.
    """
    rows = []
    for _, row in personal_df.iterrows():
        age = float(row["age"])
        nw = float(row["net_worth"])
        pct = estimate_exact_percentile(nw, round(age), benchmark)
        if pct is not None:
            rows.append({
                "age":        age,
                "year":       row.get("year", ""),
                "net_worth":  nw,
                "percentile": pct,
            })
    if not rows:
        return pd.DataFrame(columns=["age", "year", "net_worth", "percentile"])
    return pd.DataFrame(rows).sort_values("age").reset_index(drop=True)
