"""
UK Net Worth Benchmarker (v2.17)
================================

Visualises ONS Wealth and Assets Survey Wave 8 (2020–2022) percentile
distributions by age, with personal (and optional partner) overlays and a
transparent inference layer.

Features:
  - Benchmark chart with PCHIP-interpolated P25/P50/P75 from real ONS data
  - Personal trajectory + partner overlay + percentile-over-time chart
  - Monte Carlo projection (deterministic + stochastic + equity/bond glide path)
  - Retirement income forecast + drawdown simulator (deterministic + stochastic)
  - UK tax wrapper utilisation tracker (ISA, LISA, Pension AA + carryforward + taper)
  - ISA / accessible-wealth bridge calculator for early retirement
  - IHT exposure calculator
  - Multi-page PDF report
  - Large pytest safety net + CI

This file is the Streamlit UI orchestration layer. All chart builders live in
`charts/`, all maths in `utils/` (inference, monte_carlo, uk_tax). See
CLAUDE.md for the architecture and NEXT_STEPS.md / REVIEW_LOG.md for history.
"""

import math
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from utils.data_loader import (
    load_was_data, load_asset_class_data,
    parse_personal_csv, encode_personal_data, decode_personal_data,
)
from utils.inference import (
    interpolate_benchmarks, convert_to_individual, apply_gender_adjustment,
    adjust_for_inflation, cpi_adjust_personal,
    estimate_percentile, estimate_exact_percentile,
    build_percentile_trajectory, derive_tail_percentiles,
    build_asset_class_series, build_decile_table, apply_component_filter,
    apply_region_factor, region_factor, REGION_MEDIANS, GB_MEDIAN_WEALTH,
    DATA_YEAR, REAL_BASE_YEAR, UK_CPI,
)
# Helpers and chart builders being migrated out of app.py into charts/
from charts._helpers import (
    fmt as _fmt, fmt_delta as _fmt_delta,
    clean_note as _clean_note, safe_cagr as _safe_cagr,
    hover_template as _hover, best_gain as _best_gain,
    CAGR_MIN_START,
    TITLE_COLOUR, GRID_COLOUR, AXIS_LABEL_COLOUR, NEUTRAL_GREY,
)
from charts.asset_class import build_asset_class_chart  # noqa: F401  (replaces local builder)
from charts.heatmap     import build_heatmap            # noqa: F401  (replaces local builder)
from charts.distribution import build_distribution_chart  # noqa: F401
from charts.gains        import build_gains_chart, build_velocity_chart, build_cumulative_chart  # noqa: F401
from charts.percentile_trajectory import build_percentile_chart  # noqa: F401
from charts.whatif       import build_whatif_figure     # noqa: F401
from charts.main_figure  import build_main_figure       # noqa: F401
from charts.monte_carlo  import build_monte_carlo_chart  # noqa: F401
from utils.monte_carlo   import run_monte_carlo, probability_of_reaching  # noqa: F401
from utils.uk_tax        import (  # noqa: F401
    tapered_pension_allowance, effective_pension_allowance,
    isa_remaining, lisa_remaining, pension_relief_estimate, lisa_bonus,
    iht_payable, IHT_BANDS,
    income_tax_2025_26, tax_free_lump_sum, PENSION_LSA,
    ISA_ALLOWANCE, LISA_ALLOWANCE, PENSION_AA, TAPER_THRESHOLD,
    STATE_PENSION_AGE, life_expectancy_at,
)
from utils.data_quality  import compute_data_quality  # noqa: F401
from utils.summary        import build_summary_stats   # noqa: F401

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="UK Net Worth Benchmarker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Version + public URL — kept together so a release bump touches one block.
# Streamlit doesn't expose the host URL to the app reliably, so we hardcode it.
APP_VERSION = "v2.17"
PUBLIC_APP_URL = "https://uk-networth-benchmarker.streamlit.app"

st.markdown(
    """
    <style>
    .stMetric { border-left: 4px solid #1d4ed8; padding-left: 0.75rem; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

AGE_RANGE = np.arange(16, 86)

_COLOURS_STANDARD = {
    "p25":    "#93c5fd",
    "p50":    "#1d4ed8",
    "p75":    "#93c5fd",
    "band":   "rgba(147,197,253,0.18)",
    "pub":    "#1e40af",
    "person": "#f97316",   # orange
    "partner":"#10b981",   # emerald
}

_COLOURS_CB = {           # deuteranopia-friendly (Okabe-Ito palette)
    "p25":    "#56b4e9",   # sky blue
    "p50":    "#0072b2",   # blue
    "p75":    "#56b4e9",
    "band":   "rgba(86,180,233,0.18)",
    "pub":    "#005082",
    "person": "#e69f00",   # amber
    "partner":"#009e73",   # bluish green
}

COLOURS = _COLOURS_STANDARD  # overridden below after sidebar reads cb_safe

ASSET_COLOURS = {
    "Property":  "#1d4ed8",
    "Pension":   "#7c3aed",
    "Financial": "#059669",
    "Physical":  "#d97706",
}

PLOTLY_CONFIG = {
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "uk_networth_benchmarker",
        "height": 600, "width": 1200, "scale": 2,
    },
}


# ── Shareable URL bootstrap ───────────────────────────────────────────────────
#
# Two query params recognised:
#   ?d=... → primary user's personal data
#   ?p=... → optional partner data (when the sharer had both loaded)
#
# Both are zlib+base64 personal-data tokens (see utils/data_loader.py).

_url_personal_df: pd.DataFrame | None = None
_url_partner_df:  pd.DataFrame | None = None
_url_load_error:  str | None = None
_qp = st.query_params

if "d" in _qp and "url_personal_loaded" not in st.session_state:
    try:
        _url_personal_df = decode_personal_data(_qp["d"])
        st.session_state.url_personal_df = _url_personal_df
        st.session_state.url_personal_loaded = True
    except Exception:
        _url_load_error = "Could not decode the shared link — it may be corrupted or expired."

if "p" in _qp and "url_partner_loaded" not in st.session_state:
    try:
        _url_partner_df = decode_personal_data(_qp["p"])
        st.session_state.url_partner_df = _url_partner_df
        st.session_state.url_partner_loaded = True
    except Exception:
        # Don't overwrite a more-important personal-data error
        if _url_load_error is None:
            _url_load_error = "Could not decode the partner data in the shared link."

# Restore from session state on rerun
if _url_personal_df is None and "url_personal_df" in st.session_state:
    _url_personal_df = st.session_state.url_personal_df
if _url_partner_df is None and "url_partner_df" in st.session_state:
    _url_partner_df = st.session_state.url_partner_df


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data
def _load_raw() -> pd.DataFrame:
    return load_was_data()

@st.cache_data
def _load_asset_classes() -> pd.DataFrame:
    return load_asset_class_data()

@st.cache_data
def _build_benchmark(basis: str, include_pension: bool, real_terms: bool, gender: str = "All") -> pd.DataFrame:
    raw = _load_raw()
    filtered = raw[raw["with_pension"] == include_pension].copy()
    bm = interpolate_benchmarks(filtered, AGE_RANGE)
    if basis == "Individual":
        bm = convert_to_individual(bm)
        bm = apply_gender_adjustment(bm, gender)  # "All" returns unchanged
    if real_terms:
        bm = adjust_for_inflation(bm, from_year=DATA_YEAR, to_year=REAL_BASE_YEAR)
    return bm


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _personal_data_section(
    label: str, key_prefix: str, url_df: pd.DataFrame | None = None
) -> pd.DataFrame | None:
    """Reusable personal/partner data entry widget. Returns a DataFrame or None."""
    st.subheader(label)

    # The demo-data button can't directly assign st.session_state["you_method"]
    # because that key is owned by the radio widget below — Streamlit raises
    # StreamlitAPIException for post-creation writes. Workaround: the button
    # sets a "_pending_demo" flag instead, and we honour it HERE (before the
    # radio renders) by pre-seeding the radio's initial value via session_state.
    if key_prefix == "you" and st.session_state.pop("_pending_demo_load", False):
        st.session_state["you_method"] = "Manual entry"

    method = st.radio(
        f"{label} entry",
        ["None", "Upload CSV", "Manual entry"],
        label_visibility="collapsed",
        key=f"{key_prefix}_method",
    )

    result_df: pd.DataFrame | None = url_df

    if method == "Upload CSV":
        uploaded = st.file_uploader(
            f"Upload {label.lower()} history", type=["csv"], key=f"{key_prefix}_upload"
        )
        if uploaded:
            try:
                result_df = parse_personal_csv(uploaded)
                st.success(f"{len(result_df)} data point(s) loaded.")
                # excel_serial_converted is INFO not WARNING — we already
                # repaired the years, just letting the user know.
                if "excel_serial_converted" in result_df.attrs:
                    st.info(result_df.attrs["excel_serial_converted"], icon="🔧")
                for attr in ("excel_year_warning", "birth_year_warning",
                             "implausible_age_warning"):
                    if attr in result_df.attrs:
                        st.warning(result_df.attrs[attr], icon="⚠️")
            except ValueError as exc:
                st.error(str(exc))

        template = pd.DataFrame({
            "year": [2020, 2021, 2022, 2023, 2024],
            "age":  [28, 29, 30, 31, 32],
            "net_worth":   [12000, 18500, 27000, 38000, 52000],
            "liabilities": [16000, 14000, 158000, 152000, 146000],
            "note":        ["", "", "bought flat", "", ""],
        })
        st.download_button(
            "Download CSV template",
            template.to_csv(index=False).encode(),
            "personal_template.csv", "text/csv",
            use_container_width=True, key=f"{key_prefix}_tmpl",
        )

    elif method == "Manual entry":
        st.caption("One row per year. Net worth in £.")
        ss_key = f"{key_prefix}_rows"
        if ss_key not in st.session_state:
            # Default to current year. For age: if this is the partner pane and
            # the user has already entered their own data this session, pre-fill
            # the partner's age to match the user's latest age (couples typically
            # have similar ages). Otherwise default to 30.
            from datetime import date
            _default_age = 30
            if key_prefix == "partner" and "you_rows" in st.session_state:
                _you_rows = st.session_state["you_rows"]
                if _you_rows:
                    try:
                        _default_age = int(_you_rows[-1].get("age", 30))
                    except (TypeError, ValueError):
                        pass
            st.session_state[ss_key] = [
                {"year": date.today().year, "age": _default_age,
                 "net_worth": 0, "liabilities": 0, "note": ""}
            ]
        _editor_df = pd.DataFrame(st.session_state[ss_key])
        if "liabilities" not in _editor_df.columns:
            _editor_df["liabilities"] = 0.0  # show the optional column even for older/restored data
        edited = st.data_editor(
            _editor_df,
            num_rows="dynamic", use_container_width=True,
            column_config={
                "year":      st.column_config.NumberColumn("Year",     min_value=1960, max_value=2030, step=1,    format="%d"),
                "age":       st.column_config.NumberColumn("Age",      min_value=16,   max_value=100,  step=1,    format="%d"),
                "net_worth": st.column_config.NumberColumn("Net worth (£)", min_value=-1_000_000, max_value=50_000_000, step=1_000, format="£%,d"),
                "liabilities": st.column_config.NumberColumn("Liabilities (£, optional)", min_value=0, max_value=50_000_000, step=1_000, format="£%,d",
                                                          help="Total debts at that point (mortgage, loans). Context only — net worth drives the benchmark."),
                "note":      st.column_config.TextColumn("Note (optional)", max_chars=80,
                                                          help="Short label shown in hover tooltip, e.g. 'bought house'"),
            },
            key=f"{key_prefix}_editor",
        )
        if len(edited) > 0 and edited["net_worth"].abs().sum() > 0:
            # Drop rows where any required field is missing — happens if the user
            # adds a blank row mid-edit. Without this filter, downstream charts get
            # NaN values that silently propagate (e.g. CAGR turns nan, percentile
            # estimate returns None for that point).
            cleaned = edited.dropna(subset=["year", "age", "net_worth"]).copy()
            if len(cleaned) > 0:
                cleaned["year"]      = cleaned["year"].astype(int)
                cleaned["age"]       = cleaned["age"].astype(float)
                cleaned["net_worth"] = cleaned["net_worth"].astype(float)
                cleaned["note"]      = (cleaned["note"].fillna("").astype(str)
                                        if "note" in cleaned.columns else "")
                if "liabilities" in cleaned.columns:
                    cleaned["liabilities"] = pd.to_numeric(
                        cleaned["liabilities"], errors="coerce").fillna(0.0).abs()
                cleaned = cleaned.sort_values("age").reset_index(drop=True)
                st.session_state[ss_key] = cleaned.to_dict("records")
                result_df = cleaned
            # If every row was incomplete, leave result_df at its default (None or
            # the URL-restored df) so we don't surface a half-baked dataset.

    return result_df


# ── Helpers (defined before sidebar so they're available everywhere) ───────────

# Formatting helpers (_fmt, _fmt_delta, _clean_note, _safe_cagr) and small chart utils
# (_hover, _best_gain) have moved to charts/_helpers.py — imported at top of file.


# Initialised here so sidebar goal/savings calculator can reference them safely
# (personal_plot_df and latest_nw are populated later, after sidebar renders)
latest_nw: float | None = None
personal_plot_df = None

with st.sidebar:
    st.title("Settings")

    # ── Benchmark controls ─────────────────────────────────────────────────────
    st.subheader("Benchmark")
    basis = st.radio(
        "Basis", ["Household", "Individual"],
        help="**Household** = direct from ONS WAS. **Individual** = derived — see methodology.",
    )
    include_pension  = st.toggle("Include pension wealth", value=True)
    real_terms       = st.toggle(f"Real terms ({REAL_BASE_YEAR} £)", value=False)
    region = st.selectbox(
        "Region", list(REGION_MEDIANS.keys()), index=0,
        help="Scales the GB benchmark to a region's median household wealth "
             "(ONS WAS Wave 8). Approximate — a uniform shift across all ages, "
             "since ONS doesn't publish regional medians by age.",
    )
    gender = "All"
    if basis == "Individual":
        gender = st.radio("Gender adjustment", ["All", "Male", "Female"],
                          horizontal=True,
                          help="Applies approximate WAS gender wealth-gap factors. "
                               "Male = baseline. Female ≈ 68–92% of male by age. "
                               "Derived — treat as indicative (±10–15%).")
    wealth_component = st.radio(
        "Wealth component",
        ["Total", "Property", "Pension", "Financial", "Physical"],
        horizontal=True,
        help="Filter the benchmark to a single wealth component. "
             "Uses approximate WAS asset class share proportions — derived, not published. "
             "Your personal overlay still shows total net worth.",
    )
    age_min, age_max = st.slider("Age range shown", 16, 85, (16, 85), step=1,
                                 help="Zoom in on a specific age window")

    with st.expander("Display options"):
        log_scale        = st.toggle("Log scale", value=False,
                                     help="Spreads low values — useful when data spans several orders of magnitude")
        show_tails       = st.toggle("Show P10 / P90", value=False,
                                     help="Modelled tails from log-normal fit — not published WAS data")
        show_milestones  = st.toggle("Wealth milestones", value=False,
                                     help="Reference lines at £100k, £250k, £500k and £1m")
        smooth_traj      = st.toggle("Smooth trajectory", value=False,
                                     help="Rolling average on the percentile trajectory chart")
        show_asset_class = st.toggle("Asset class breakdown", value=False,
                                     help="Stacked chart: property / pension / financial / physical at the median")
        show_annotations = st.toggle("Show chart annotations", value=True,
                                     help="Show best-gain arrows and crosshair labels — turn off for clean screenshots")
        cb_safe = st.toggle("Colourblind-safe palette", value=False,
                            help="Replaces blue/orange with a deuteranopia-friendly palette")

    st.divider()

    # ── Your data ─────────────────────────────────────────────────────────────
    if _url_load_error:
        st.error(_url_load_error)
    personal_df = _personal_data_section("Your net worth", "you", _url_personal_df)

    st.divider()
    partner_df = _personal_data_section("Partner's net worth (optional)", "partner", _url_partner_df)

    st.divider()

    # The wealth-mix editor (auto-balancing sliders) now lives in the
    # "🎚️ Adjust your wealth mix" panel directly under the main chart, where the
    # sliders sit next to the live £ breakdown so dragging and seeing the effect
    # happen in one place. personal_asset_split is defined there.

    st.divider()

    # Calculator inputs now live in the 🎯 Planning tab (so the sidebar holds only
    # display + data controls). Their values are read here from session_state,
    # with defaults matching the widgets, so earlier sections — the goal/FIRE
    # progress and weeks-to-FI in the Progress tab — work regardless of render
    # order. The Planning-tab widgets own these keys; we only read them here.
    goal_amount    = st.session_state.get("goal_amount", 500_000)
    fire_spending  = st.session_state.get("fire_spend", 30_000)
    fire_number    = fire_spending * 25  # 4% safe withdrawal rate
    retirement_age = st.session_state.get("ret_age", 65)
    pension_income = st.session_state.get("pen_income", 20_000)
    state_pension  = st.session_state.get("state_pension", 12_548)
    annual_income  = st.session_state.get("annual_income", 50_000)

    st.divider()

    # Benchmark CSV download
    with st.expander("Download benchmark data"):
        bm_dl = _build_benchmark(basis, include_pension, real_terms)
        price_lbl = f"{REAL_BASE_YEAR}_real" if real_terms else f"{DATA_YEAR}_nominal"
        st.download_button(
            "Download benchmark CSV",
            bm_dl.to_csv(index=False).encode(),
            f"uk_networth_benchmark_{basis.lower()}_{price_lbl}.csv",
            "text/csv", use_container_width=True,
        )

    st.caption(
        "Data: ONS Wealth and Assets Survey Wave 8 (2020–2022), Great Britain. "
        "Individual figures and interpolations are derived estimates."
    )


# Apply palette (must be after sidebar reads cb_safe)
COLOURS = _COLOURS_CB if cb_safe else _COLOURS_STANDARD

# Pre-initialise so sidebar goal calculator can safely reference them
latest_nw:  float | None = None
latest_age: float | None = None

# ── Data pipeline ─────────────────────────────────────────────────────────────

benchmark = _build_benchmark(basis, include_pension, real_terms, gender)
if wealth_component != "Total":
    benchmark = apply_component_filter(benchmark, wealth_component, _load_asset_classes())
if region != "Great Britain":
    benchmark = apply_region_factor(benchmark, region)

def _prep_plot_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or len(df) == 0:
        return None
    return cpi_adjust_personal(df, to_year=REAL_BASE_YEAR) if real_terms else df.copy()

personal_plot_df = _prep_plot_df(personal_df)
partner_plot_df  = _prep_plot_df(partner_df)


def _pct_series(pct: str) -> pd.DataFrame:
    return benchmark[benchmark["percentile"] == pct].sort_values("age")

# _hover and _best_gain now imported from charts/_helpers.py


# ── Main benchmark + personal chart ──────────────────────────────────────────

# build_main_figure moved to charts/main_figure.py — imported at top of file.


# build_percentile_chart moved to charts/percentile_trajectory.py.


# build_velocity_chart and build_gains_chart moved to charts/gains.py.


# build_whatif_figure moved to charts/whatif.py — imported at top of file.


# build_cumulative_chart moved to charts/gains.py — imported at top of file.


# ── Data quality score ────────────────────────────────────────────────────────

# compute_data_quality moved to utils/data_quality.py — imported at top of file.


# build_heatmap moved to charts/heatmap.py — imported at top of file.


# build_distribution_chart moved to charts/distribution.py — imported at top of file.


# build_asset_class_chart moved to charts/asset_class.py — imported at top of file.


# ── Summary statistics table ──────────────────────────────────────────────────

# build_summary_stats moved to utils/summary.py — imported at top of file.


# ── Main content ──────────────────────────────────────────────────────────────

col_hdr, col_badge = st.columns([5, 1])
with col_hdr:
    st.title("UK Net Worth Benchmarker")
    st.caption(
        "Compare your net worth against UK population distributions by age · "
        "ONS Wealth and Assets Survey Wave 8 (2020–2022), Great Britain"
    )
with col_badge:
    price_badge = f"Real {REAL_BASE_YEAR} £" if real_terms else f"Nominal {DATA_YEAR} £"
    st.markdown(
        f"<div style='text-align:right;margin-top:1rem;'>"
        f"<span style='background:#dbeafe;color:#1e40af;padding:4px 10px;"
        f"border-radius:12px;font-size:0.8rem;font-weight:600;'>{basis}</span>&nbsp;"
        f"<span style='background:#f0fdf4;color:#166534;padding:4px 10px;"
        f"border-radius:12px;font-size:0.8rem;font-weight:600;'>{price_badge}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ── Metrics ───────────────────────────────────────────────────────────────────

latest_age: float | None = None
latest_nw:  float | None = None
partner_latest_age: float | None = None

# Empty-state guidance — shown when no personal data is entered yet
if personal_plot_df is None or len(personal_plot_df) == 0:
    with st.container():
        empty_col1, empty_col2 = st.columns([3, 1])
        with empty_col1:
            st.info(
                "**Add your net worth history to get started.** "
                "Open **Your net worth** in the sidebar → choose *Upload CSV* (template provided) "
                "or *Manual entry* to type in a few rows. Even 2–3 data points unlocks the "
                "percentile, growth-rate, retirement and goal calculators below the chart.",
                icon="👋",
            )
        with empty_col2:
            st.write("")  # spacer
            if st.button("Try with demo data", use_container_width=True,
                         help="Load an 11-year sample history so you can explore every feature."):
                # Single source of truth in data/demo_data.py — imported here
                # and also verified by tests/test_demo_data.py against the same
                # constant (no risk of drift between app and test).
                #
                # IMPORTANT: we can't write to st.session_state['you_method']
                # here because the radio widget owning that key has already
                # rendered (Streamlit raises StreamlitAPIException). Instead
                # we set a one-shot flag that _personal_data_section consumes
                # on the next run BEFORE the radio is created. you_rows is
                # safe to write directly — it's owned by the data_editor
                # which hasn't rendered yet (we're not in Manual entry mode).
                from data.demo_data import DEMO_HISTORY
                st.session_state["_pending_demo_load"] = True
                st.session_state["you_rows"] = list(DEMO_HISTORY)
                st.rerun()

# Warn if real-terms mode is on and some personal data falls outside the
# CPI table (silently passed through uncorrected). Treat 'you' and 'partner'
# uniformly because both are CPI-adjusted by _prep_plot_df.
if real_terms:
    _cpi_min, _cpi_max = min(UK_CPI), max(UK_CPI)
    for _label, _df in [("your", personal_df), ("partner's", partner_df)]:
        if _df is not None and len(_df) > 0:
            _out_of_range = _df[(_df["year"] < _cpi_min) | (_df["year"] > _cpi_max)]
            if len(_out_of_range) > 0:
                _yrs = sorted(_out_of_range["year"].unique())
                st.warning(
                    f"{len(_out_of_range)} {_label} data row(s) have years outside the CPI "
                    f"table ({_cpi_min}–{_cpi_max}): {_yrs}. Those rows are shown in "
                    f"nominal terms even though real-terms mode is on.",
                    icon="⚠️",
                )

if personal_plot_df is not None and len(personal_plot_df) > 0:
    sorted_pdf = personal_plot_df.sort_values("age")
    latest     = sorted_pdf.iloc[-1]
    latest_age = float(latest["age"])
    latest_nw  = float(latest["net_worth"])
    price_note = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal {DATA_YEAR} prices"

    exact_pct = estimate_exact_percentile(latest_nw, round(latest_age), benchmark)
    band_desc = estimate_percentile(latest_nw, round(latest_age), benchmark)

    delta_str = delta_val = None
    if len(sorted_pdf) >= 2:
        delta_val = latest_nw - float(sorted_pdf.iloc[-2]["net_worth"])
        delta_str = _fmt_delta(delta_val)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Your latest age", f"{latest_age:.1f}")
    with col2:
        st.metric("Net worth", _fmt(latest_nw), delta=delta_str,
                  help=f"In {price_note}. Delta vs previous data point.")
    with col3:
        if exact_pct:
            # The log-normal model clamps at [0.5, 99.5]. Flag when the user
            # is at the edge of the model so they know to treat the figure
            # as a floor/ceiling, not a precise estimate.
            if exact_pct >= 99.0:
                pct_label = "99th+"
                pct_help  = ("You're at the top of the model's range. "
                             "Treat as 'top ~1%' — the log-normal fit can't "
                             "distinguish further at this end.")
            elif exact_pct <= 1.0:
                pct_label = "<1st"
                pct_help  = ("You're at the bottom of the model's range. "
                             "Treat as 'bottom ~1%' — the log-normal fit can't "
                             "distinguish further at this end.")
            else:
                pct_label = f"~{exact_pct:.0f}th"
                pct_help  = "Log-normal fit to P25/P50/P75 — indicative, roughly ±5–10 percentile points."
            st.metric("Est. percentile", pct_label, help=pct_help)
        else:
            short_band = {
                "below the 25th percentile":                  "Below P25",
                "between the 25th percentile and the median": "P25 – P50",
                "between the median and the 75th percentile": "P50 – P75",
                "above the 75th percentile":                  "Above P75",
            }.get(band_desc, band_desc.capitalize())
            st.metric("Percentile band", short_band)
    with col4:
        ab = benchmark[benchmark["age"] == min(round(latest_age), 85)]
        p50v = float(ab[ab["percentile"] == "p50"]["value"].iloc[0]) if len(ab[ab["percentile"]=="p50"]) else None
        p75v = float(ab[ab["percentile"] == "p75"]["value"].iloc[0]) if len(ab[ab["percentile"]=="p75"]) else None
        if p50v and p75v and p50v > 0:
            # Age-adjusted relative wealth: net_worth / benchmark_median (index = 100 at median)
            rel_wealth = latest_nw / p50v * 100
            st.metric(
                "Rel. wealth index",
                f"{rel_wealth:.0f}",
                help="Your net worth as a % of the benchmark median at your age. "
                     "100 = exactly at median. Age-adjusted so it's comparable across ages.",
            )
    with col5:
        # Own column so the 4-up metric grid stays aligned (was stacked under col4).
        if p50v and p75v:
            if latest_nw < p50v:
                st.metric("Gap to median", _fmt(p50v - latest_nw))
            elif latest_nw < p75v:
                st.metric("Gap to P75", _fmt(p75v - latest_nw))
            else:
                st.metric("Above P75 by", _fmt(latest_nw - p75v))

    # Gross-assets-vs-net-worth context when a liabilities column was supplied.
    if personal_df is not None and "liabilities" in personal_df.columns:
        _latest_raw = personal_df.sort_values("age").iloc[-1]
        _liab = float(_latest_raw.get("liabilities", 0) or 0)
        if _liab > 0:
            _nw_raw = float(_latest_raw["net_worth"])
            st.caption(
                f"💳 Latest position: **{_fmt(_nw_raw + _liab)}** gross assets − "
                f"**{_fmt(_liab)}** liabilities = **{_fmt(_nw_raw)}** net worth"
                + (" (nominal)" if real_terms else "")
                + ". Net worth is what's compared to the benchmark."
            )

    # Row 2: growth & progress
    first_age = float(sorted_pdf.iloc[0]["age"])
    first_nw  = float(sorted_pdf.iloc[0]["net_worth"])
    age_span  = latest_age - first_age

    if len(sorted_pdf) >= 2:
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            cagr = _safe_cagr(first_nw, latest_nw, age_span)
            if cagr is not None:
                double_time = (math.log(2) / math.log(1 + cagr)) if cagr > 0 else None
                dt_str = f" · doubles in {double_time:.0f} yrs" if double_time else ""
                st.metric("CAGR", f"{cagr*100:+.1f}%",
                          help=f"Compound annual growth rate from age {first_age:.1f} to {latest_age:.1f}.{dt_str}")
                if double_time:
                    st.caption(f"Doubles in ~{double_time:.0f} yrs at this rate")
            else:
                st.metric("Total change", _fmt_delta(latest_nw - first_nw),
                          help=("CAGR not shown: starting net worth below "
                                f"£{CAGR_MIN_START:,} would inflate the rate."
                                if first_nw < CAGR_MIN_START and first_nw > 0
                                else None))
        with col_b:
            if age_span > 0:
                st.metric("Avg annual gain", _fmt((latest_nw - first_nw) / age_span),
                          help=f"Simple average over {age_span:.1f} years.")
        with col_c:
            if p50v and p75v:
                if latest_nw < p50v:
                    target, from_val = p50v, max(0.0, first_nw) if first_nw < p50v else 0.0
                    mlabel = f"Progress toward median ({_fmt(p50v)})"
                elif latest_nw < p75v:
                    target, from_val = p75v, p50v
                    mlabel = f"Progress toward P75 ({_fmt(p75v)})"
                else:
                    target = None
                if target:
                    span = max(target - from_val, 1)
                    prog = min(max((latest_nw - from_val) / span, 0.0), 1.0)
                    st.caption(mlabel)
                    st.progress(prog)
                    # CAGR-based ETA
                    if age_span > 0.5 and first_nw > 0 and latest_nw > 0 and latest_nw < target:
                        cagr_proj = (latest_nw / first_nw) ** (1 / age_span) - 1
                        if cagr_proj > 0.001:
                            yrs = math.log(target / latest_nw) / math.log(1 + cagr_proj)
                            eta = latest_age + yrs
                            if eta <= 100:
                                st.caption(f"At {cagr_proj*100:.1f}% CAGR: age **{eta:.0f}** (~{yrs:.0f} yrs)")

    # Median multiples
    if p50v and p50v > 0:
        multiples = latest_nw / p50v
        multiples_str = f"**{multiples:.1f}× the median**" if multiples >= 0.1 else f"**{multiples*100:.0f}% of the median**"
    else:
        multiples_str = ""

    st.info(
        f"At age **{latest_age:.1f}**, your net worth of **{_fmt(latest_nw)}** ({price_note}) "
        f"places you {'at approximately the **' + str(round(exact_pct)) + 'th percentile** (±~5–10 pts)' if exact_pct else '**' + band_desc + '**'} "
        f"on a {basis.lower()} basis in the UK."
        + (f" Roughly **{round(exact_pct)} in 100** people your age have less wealth than you." if exact_pct else "")
        + (f" That's {multiples_str} at your age." if multiples_str else "")
        + (f" (Up {_fmt(delta_val)} from previous.)" if delta_val and delta_val > 0 else
           f" (Down {_fmt(abs(delta_val))} from previous.)" if delta_val and delta_val < 0 else "")
    )

    # Monthly savings micro-calculator
    with st.expander("Quick calculator: monthly savings impact"):
        st.caption("How much would saving an extra amount per month add to your net worth?")
        # NB: 'qc_' prefix (Quick Calculator), NOT 'mc_' — Monte Carlo elsewhere
        # uses mc_* keys, and an accidental collision on 'mc_monthly' previously
        # crashed the app with StreamlitDuplicateElementKey.
        qc_cols = st.columns(3)
        with qc_cols[0]:
            extra_monthly = st.number_input("Extra monthly saving (£)", 0, 10_000, 200, 50, key="qc_monthly")
        with qc_cols[1]:
            qc_return  = st.number_input("Annual return (%)", 0.0, 15.0, 5.0, 0.5, key="qc_return")
        with qc_cols[2]:
            qc_years   = st.number_input("Years", 1, 50, 10, 1, key="qc_years")
        if extra_monthly > 0:
            # FV of annuity: PMT * [(1+r)^n - 1] / r  where r = monthly rate
            r = (qc_return / 100) / 12
            n = qc_years * 12
            fv = extra_monthly * ((1 + r) ** n - 1) / r if r > 0 else extra_monthly * n
            total_paid = extra_monthly * n
            st.metric(
                f"Future value in {qc_years} yrs",
                _fmt(fv),
                delta=f"+{_fmt(fv - total_paid)} from returns",
                help=f"£{total_paid:,.0f} contributed; £{fv - total_paid:,.0f} from compound returns."
            )


# ── Main chart ────────────────────────────────────────────────────────────────

fig = build_main_figure(
    benchmark,
    personal_plot_df=personal_plot_df,
    partner_plot_df=partner_plot_df,
    log_scale=log_scale,
    show_tails=show_tails,
    show_milestones=show_milestones,
    show_annotations=show_annotations,
    age_min=age_min, age_max=age_max,
    latest_age=latest_age, latest_nw=latest_nw,
    basis=basis,
    wealth_component=wealth_component,
    price_label=(f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"),
    colours=COLOURS,
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

if region != "Great Britain":
    _rf = region_factor(region)
    st.info(
        f"📍 Benchmark scaled to **{region}** — ×**{_rf:.2f}** vs the GB median "
        f"(ONS WAS Wave 8: {region} median household wealth {_fmt(REGION_MEDIANS[region])} "
        f"vs GB {_fmt(GB_MEDIAN_WEALTH)}). This is a **uniform shift across all ages**, an "
        f"approximation since ONS doesn't publish regional medians by age. Your percentile is "
        f"now relative to {region}.",
        icon="📍",
    )

if wealth_component != "Total":
    st.info(
        f"Viewing **{wealth_component} wealth** component only. "
        "Benchmark scaled by component shares rescaled to ONS Wave 8 aggregates. "
        "Your personal net worth overlay shows **total** net worth — "
        "adjust your composition split in the wealth-mix panel under the chart for per-component context.",
        icon="ℹ️",
    )
elif basis == "Individual":
    st.caption("Individual figures are derived — see methodology panel.")
else:
    st.caption(
        "Filled circles = ONS published data (ages 20,30,40,50,60,70,80). "
        "Lines are PCHIP-interpolated. Dotted verticals = age-band boundaries."
    )


# ── Wealth mix: composition split + interactive editor ───────────────────────
# Auto-balancing sliders (always total 100%) co-located with a live £ breakdown,
# so dragging and seeing the effect happen in one place. personal_asset_split is
# defined unconditionally (from session_state) so the asset-class overlay, the
# SWR figure, the retirement defaults and the PDF always have it — even before
# the editor, which only renders when there's net worth to split.
_WC_KEYS = [("wc_prop", "Property",  "🏠", "#1d4ed8", 40),
            ("wc_pen",  "Pension",   "💼", "#10b981", 30),
            ("wc_fin",  "Financial", "💷", "#f97316", 20),
            ("wc_phys", "Physical",  "🚗", "#a855f7", 10)]
for _k, _name, _icon, _col, _default in _WC_KEYS:
    st.session_state.setdefault(_k, _default)


def _wc_rebalance(changed_key):
    """Keep the four composition sliders summing to 100% (integer percentages).

    Fires after the moved slider commits its value; the other widgets haven't
    re-instantiated yet, so we rewrite their session_state. The remainder is
    split proportionally; integer rounding drift goes to the largest fractions.
    """
    keys = [k for k, *_ in _WC_KEYS]
    new_val = st.session_state[changed_key]
    others = [k for k in keys if k != changed_key]
    remaining = 100 - new_val
    prev_sum = sum(st.session_state[k] for k in others)
    if prev_sum <= 0:
        base = remaining // len(others)
        extra = remaining - base * len(others)
        for i, k in enumerate(others):
            st.session_state[k] = base + (1 if i < extra else 0)
        return
    raw = {k: st.session_state[k] / prev_sum * remaining for k in others}
    floored = {k: int(raw[k]) for k in others}
    drift = remaining - sum(floored.values())
    for k in sorted(others, key=lambda k: raw[k] - floored[k], reverse=True)[:drift]:
        floored[k] += 1
    for k in others:
        st.session_state[k] = floored[k]


personal_asset_split = {
    "Property":  st.session_state["wc_prop"] / 100,
    "Pension":   st.session_state["wc_pen"]  / 100,
    "Financial": st.session_state["wc_fin"]  / 100,
    "Physical":  st.session_state["wc_phys"] / 100,
}

if latest_nw is not None and latest_nw > 0:
    with st.expander("🎚️ Adjust your wealth mix — drag a slider, the rest auto-balance", expanded=True):
        st.caption(
            "Drag any component on the left and the **other three rebalance automatically** so the "
            "mix always totals 100%. The bar and figures on the right update as you slide."
        )
        edit_col, view_col = st.columns([5, 6])
        with edit_col:
            for _k, _name, _icon, _col, _ in _WC_KEYS:
                _amt = latest_nw * st.session_state[_k] / 100
                st.slider(f"{_icon} {_name} — {_fmt(_amt)} ({st.session_state[_k]}%)",
                          0, 100, key=_k, on_change=_wc_rebalance, args=(_k,))
            st.caption("Move any slider — the others give way to keep the total at 100%.")
        with view_col:
            _mix_fig = go.Figure()
            for _k, _name, _icon, _col, _ in _WC_KEYS:
                _amt = latest_nw * personal_asset_split[_name]
                _mix_fig.add_trace(go.Bar(
                    y=["Mix"], x=[_amt], name=f"{_icon} {_name}", orientation="h",
                    marker_color=_col,
                    hovertemplate=f"{_name}: £%{{x:,.0f}} "
                                  f"({personal_asset_split[_name]*100:.0f}%)<extra></extra>",
                ))
            _mix_fig.update_layout(
                barmode="stack", height=120, showlegend=True,
                legend=dict(orientation="h", y=-0.4, font=dict(size=11)),
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(title=None, tickprefix="£", tickformat=",.0f"),
                yaxis=dict(title=None, showticklabels=False),
            )
            st.plotly_chart(_mix_fig, use_container_width=True, config=PLOTLY_CONFIG)

            # Drawable / investable wealth (same carve-out as the SWR figure):
            # excludes home equity and pre-57 pension.
            _mix_locked = latest_age is not None and latest_age < 57
            _mix_investable = (latest_nw * personal_asset_split["Financial"]
                               + latest_nw * personal_asset_split["Physical"]
                               + (0.0 if _mix_locked else latest_nw * personal_asset_split["Pension"]))
            st.success(
                f"**Drawable / investable ≈ {_fmt(_mix_investable)}** "
                f"(financial + physical{', pension locked until 57' if _mix_locked else ' + pension'}; "
                f"home equity excluded). At 4% ≈ **{_fmt(_mix_investable * 0.04)}/yr**.",
                icon="💧",
            )


if personal_plot_df is not None and len(personal_plot_df) == 1:
    st.caption(
        "👉 You've entered one data point — enough for your percentile and benchmark position. "
        "Add a **second year** to unlock growth rate, percentile trajectory, annual gains, "
        "milestones and the Monte Carlo projection in the tabs below."
    )


# ── Analysis tabs ────────────────────────────────────────────────
tab_stand, tab_prog, tab_plan, tab_tax, tab_share = st.tabs(["📊 Where you stand", "📈 Your progress", "🎯 Planning & projections", "🏛️ Tax & estate", "📋 Share & export"])

with tab_stand:
    # ── Percentile heatmap ───────────────────────────────────────────────────────

    with st.expander("Percentile landscape heatmap"):
        hm_price = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR})"
        hm_fig = build_heatmap(
            benchmark,
            personal_plot_df=personal_plot_df,
            partner_plot_df=partner_plot_df,
            person_colour=COLOURS["person"],
            partner_colour=COLOURS["partner"],
            price_label=hm_price,
        )
        st.plotly_chart(hm_fig, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption(
            "Shaded bands show which percentile tier each wealth level belongs to at each age. "
            "P10 and P90 are derived from the log-normal model; P25/P50/P75 are from WAS. "
            "Your trajectory is overlaid in orange."
        )


    # ── Decile table ─────────────────────────────────────────────────────────────

    if latest_age is not None:
        with st.expander(f"Full decile table at age {latest_age:.0f}"):
            decile_df = build_decile_table(round(latest_age), benchmark)
            if len(decile_df):
                # Format £ values
                decile_display = decile_df.copy()
                decile_display["Net worth (£)"] = decile_display["Net worth (£)"].apply(
                    lambda v: f"£{v:,.0f}"
                )
                decile_display["Source"] = decile_display["Modelled"].map(
                    {True: "Log-normal model", False: "WAS published"}
                )
                decile_display = decile_display.drop(columns=["Modelled"])

                # Highlight the user's row if we know their net worth
                st.dataframe(decile_display, use_container_width=True, hide_index=True)
                if latest_nw:
                    exact_pct_here = estimate_exact_percentile(latest_nw, round(latest_age), benchmark)
                    if exact_pct_here:
                        st.caption(
                            f"Your net worth of **{_fmt(latest_nw)}** sits at approximately "
                            f"**~{exact_pct_here:.0f}th percentile** at age {latest_age:.0f}."
                        )
                price_label_note = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal {DATA_YEAR} prices"
                st.caption(f"All values in {price_label_note}. Rows marked 'Log-normal model' are derived estimates.")


    # ── Distribution curve at user's age ─────────────────────────────────────────

    with st.expander(f"Wealth distribution curve — explore by age"):
        dist_age_default = round(latest_age) if latest_age else 40
        dist_age = st.slider("Age to show distribution for", 16, 85, dist_age_default,
                             key="dist_age_slider")
        p_nw_for_dist = float(partner_plot_df.sort_values("age").iloc[-1]["net_worth"]) \
            if partner_plot_df is not None and len(partner_plot_df) > 0 else None
        dist_price = f"{REAL_BASE_YEAR} real" if real_terms else f"nominal {DATA_YEAR}"
        dist_fig = build_distribution_chart(
            dist_age, benchmark,
            user_nw=latest_nw if dist_age == dist_age_default else None,
            partner_nw=p_nw_for_dist if dist_age == dist_age_default else None,
            price_label=dist_price,
            person_colour=COLOURS["person"],
            partner_colour=COLOURS["partner"],
        )
        if dist_fig:
            st.plotly_chart(dist_fig, use_container_width=True, config=PLOTLY_CONFIG)
            st.caption(
                "Slide to explore the distribution at any age. "
                "Your net worth is shown only at your latest recorded age. "
                "Distribution simulated from log-normal model fitted to P25/P50/P75 — "
                "tails above P90 are extrapolated."
            )


    # ── Asset class breakdown chart ───────────────────────────────────────────────

    if show_asset_class:
        asset_series = build_asset_class_series(_load_asset_classes(), benchmark, AGE_RANGE)
        if len(asset_series):
            ac_price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal {DATA_YEAR}"
            ac_fig = build_asset_class_chart(asset_series, price_label=ac_price_label)

            # Overlay user's own composition as annotation lines if latest net worth known
            if personal_asset_split and latest_nw and latest_nw > 0:
                cumulative = 0.0
                stacked_base = 0.0
                for component in ["Physical", "Financial", "Pension", "Property"]:
                    share = personal_asset_split[component]
                    component_val = latest_nw * share
                    stacked_base += component_val
                    ac_fig.add_hline(
                        y=stacked_base,
                        line=dict(color=ASSET_COLOURS[component], width=2, dash="solid"),
                        annotation_text=f"You: {component} ({share*100:.0f}%)",
                        annotation_position="left",
                        annotation=dict(font=dict(color=ASSET_COLOURS[component], size=10)),
                    )

            st.plotly_chart(ac_fig, use_container_width=True, config=PLOTLY_CONFIG)
            st.caption(
                "Component shares anchored to ONS Wave 8 aggregates (property 40%, pension 35%, financial 14%, physical 10%). "
                "Your composition (if entered) shown as horizontal lines. "
                "Property = net of mortgage · Pension = private (DB PV + DC) · "
                "Financial = savings/investments net of non-mortgage debt · Physical = vehicles/contents/valuables."
            )


with tab_prog:
    # ── Summary statistics ────────────────────────────────────────────────────────

    if personal_plot_df is not None and len(personal_plot_df) >= 2:
        with st.expander("Summary statistics"):
            frames = [build_summary_stats(personal_plot_df, benchmark, "You")]
            if partner_plot_df is not None and len(partner_plot_df) >= 2:
                frames.append(build_summary_stats(partner_plot_df, benchmark, "Partner"))
            st.dataframe(pd.concat(frames, ignore_index=True), use_container_width=True, hide_index=True)

            # Data quality score
            dq = compute_data_quality(personal_plot_df)
            st.markdown(f"**Data quality score: {dq['score']}/100**")
            st.progress(dq["score"] / 100)
            for note in dq["notes"]:
                st.caption(note)
            st.caption("Higher score = more reliable estimates. Add annual updates and extend your history to improve.")

            # Downloadable percentile history
            st.markdown("**Percentile history download**")
            traj_dl = build_percentile_trajectory(personal_plot_df, benchmark)
            if len(traj_dl):
                traj_dl_out = traj_dl.rename(columns={
                    "age": "age", "year": "year",
                    "net_worth": "net_worth_gbp", "percentile": "est_percentile",
                })
                st.download_button(
                    "Download your percentile history (CSV)",
                    traj_dl_out.to_csv(index=False).encode(),
                    "my_percentile_history.csv", "text/csv",
                    use_container_width=True,
                    help="Each data point with its estimated percentile at that age.",
                )


    # ── Percentile trajectory chart ───────────────────────────────────────────────

    if personal_plot_df is not None and len(personal_plot_df) >= 2:
        traj_you = build_percentile_trajectory(personal_plot_df, benchmark)
        traj_partner = None
        if partner_plot_df is not None and len(partner_plot_df) >= 2:
            traj_partner = build_percentile_trajectory(partner_plot_df, benchmark)
        if len(traj_you) >= 2:
            st.plotly_chart(
                build_percentile_chart(
                    traj_you,
                    traj_partner=traj_partner,
                    smooth=smooth_traj,
                    person_colour=COLOURS["person"],
                    partner_colour=COLOURS["partner"],
                ),
                use_container_width=True, config=PLOTLY_CONFIG,
            )
            st.caption(
                "Percentile via log-normal fit to P25/P50/P75 — indicative, not authoritative. "
                "Annotation shows total percentile change over the recorded period."
                + (" Rolling average applied." if smooth_traj else "")
            )


    # ── Annual gain chart ────────────────────────────────────────────────────────

    if personal_plot_df is not None and len(personal_plot_df) >= 2:
        with st.expander("Milestone tracker"):
            MILESTONES = [10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]
            s_ms = personal_plot_df.sort_values("age")
            milestone_rows = []
            for m in MILESTONES:
                # Find first row where net_worth >= m
                crossed = s_ms[s_ms["net_worth"] >= m]
                if len(crossed):
                    row = crossed.iloc[0]
                    milestone_rows.append({
                        "Milestone":    _fmt(m),
                        "Age reached":  f"{float(row['age']):.1f}",
                        "Year":         str(int(row["year"])) if "year" in row else "—",
                        "Net worth then": _fmt(float(row["net_worth"])),
                    })
                else:
                    # Not yet reached — project from current trajectory
                    first_nw_ms = float(s_ms.iloc[0]["net_worth"])
                    last_nw_ms  = float(s_ms.iloc[-1]["net_worth"])
                    asp_ms = float(s_ms.iloc[-1]["age"]) - float(s_ms.iloc[0]["age"])
                    if asp_ms > 0.5 and last_nw_ms > 0 and last_nw_ms < m:
                        yrs_ms = None
                        if first_nw_ms > 0:
                            cagr_ms = (last_nw_ms / first_nw_ms) ** (1 / asp_ms) - 1
                            if cagr_ms > 0:
                                yrs_ms = math.log(m / last_nw_ms) / math.log(1 + cagr_ms)
                        else:
                            avg_gain_ms = (last_nw_ms - first_nw_ms) / asp_ms
                            if avg_gain_ms > 0:
                                yrs_ms = (m - last_nw_ms) / avg_gain_ms
                        if yrs_ms is not None:
                            eta_ms = float(s_ms.iloc[-1]["age"]) + yrs_ms
                            if eta_ms <= 100:
                                milestone_rows.append({
                                    "Milestone":    _fmt(m),
                                    "Age reached":  f"~{eta_ms:.0f} (projected)",
                                    "Year":         "—",
                                    "Net worth then": _fmt(m),
                                })
            if milestone_rows:
                st.dataframe(pd.DataFrame(milestone_rows), use_container_width=True, hide_index=True)
                st.caption("Projected ages use your current CAGR — treat as illustrative.")
            else:
                st.info("Add more data points to see milestone tracking.")

    if personal_plot_df is not None and len(personal_plot_df) >= 2:
        with st.expander("Annual gains breakdown"):
            gc_you = build_gains_chart(personal_plot_df, colour=COLOURS["person"], name="Your net worth")
            if gc_you:
                st.plotly_chart(gc_you, use_container_width=True, config=PLOTLY_CONFIG)
            if partner_plot_df is not None and len(partner_plot_df) >= 2:
                gc_p = build_gains_chart(partner_plot_df, colour=COLOURS["partner"], name="Partner")
                if gc_p:
                    st.plotly_chart(gc_p, use_container_width=True, config=PLOTLY_CONFIG)
            st.caption("Red bars = net worth fell that period. Each bar spans the gap between consecutive data points.")

            # Velocity (% rate) chart
            vel = build_velocity_chart(personal_plot_df, colour=COLOURS["person"])
            if vel:
                st.plotly_chart(vel, use_container_width=True, config=PLOTLY_CONFIG)
            if partner_plot_df is not None and len(partner_plot_df) >= 3:
                vel_p = build_velocity_chart(partner_plot_df, colour=COLOURS["partner"])
                if vel_p:
                    st.plotly_chart(vel_p, use_container_width=True, config=PLOTLY_CONFIG)

            # Cumulative view
            cum_price = f"{REAL_BASE_YEAR} real" if real_terms else f"nominal {DATA_YEAR}"
            st.plotly_chart(
                build_cumulative_chart(
                    personal_plot_df,
                    colour=COLOURS["person"], name="You",
                    partner_pdf=partner_plot_df,
                    partner_colour=COLOURS["partner"],
                    price_label=cum_price,
                ),
                use_container_width=True, config=PLOTLY_CONFIG,
            )

            # Growth attribution
            st.markdown("**Growth attribution (rough estimate)**")
            assumed_return = st.slider("Assumed annual investment return (%)", 0.0, 12.0, 5.0, 0.5,
                                       key="attr_return",
                                       help="What % would a passive investment have returned? ~5% is a common real-return assumption.")
            s_attr = personal_plot_df.sort_values("age")
            # Mirror gains/velocity/summary aggregation: with monthly snapshots
            # the per-row attribution would otherwise be ~23 micro-periods at ~1
            # month each — unreadable and the assumed-return slider value would
            # be effectively pro-rated to a sliver per row.
            #
            # Guard: only aggregate when data spans 2+ years. For a user with one
            # year of monthly data there's no annual aggregation to do — collapsing
            # 12 rows to 1 would silently skip the whole table (len < 2 guard
            # below). Better to render the raw monthly rows than nothing.
            if ("year" in s_attr.columns
                    and s_attr["year"].nunique() > 1
                    and len(s_attr) > s_attr["year"].nunique()):
                s_attr = (s_attr.groupby("year", as_index=False).last()
                                .sort_values("year").reset_index(drop=True))
            if len(s_attr) >= 2 and float(s_attr.iloc[0]["net_worth"]) > 0:
                attr_rows = []
                for i in range(1, len(s_attr)):
                    prev = s_attr.iloc[i-1]
                    curr = s_attr.iloc[i]
                    age_gap = float(curr["age"]) - float(prev["age"])
                    nw_prev = float(prev["net_worth"])
                    nw_curr = float(curr["net_worth"])
                    if nw_prev > 0 and age_gap > 0:
                        investment_component = nw_prev * ((1 + assumed_return/100) ** age_gap - 1)
                        total_gain = nw_curr - nw_prev
                        saving_component = total_gain - investment_component
                        attr_rows.append({
                            "Period": f"Age {float(prev['age']):.1f}–{float(curr['age']):.1f}",
                            "Total gain": _fmt_delta(total_gain),
                            "Est. from returns": _fmt(max(0, investment_component)),
                            "Est. from saving": _fmt_delta(saving_component),
                        })
                if attr_rows:
                    st.dataframe(pd.DataFrame(attr_rows), use_container_width=True, hide_index=True)
                    st.caption(
                        f"'Returns' = what your opening balance at {assumed_return}% p.a. would earn each period. "
                        "'Saving' = residual (total gain minus estimated returns). "
                        "Negative saving = drawdown or assets underperformed the assumption."
                    )


    # ── Weeks to FI ──────────────────────────────────────────────────────────────

    if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
        # Use fire_number from sidebar goal calculator (fallback to 25x £30k)
        try:
            fi_target = fire_number
        except NameError:
            fi_target = 750_000

        if fi_target > 0:
            # At what weekly spending rate is current net worth ≥ 25× spending?
            # If net worth ≥ fire_number: already FI
            # Weeks of expenses covered by current net worth = nw / (annual_spending/52)
            # Or: what spending rate would make today's nw = 25× spending?
            implied_annual = latest_nw / 25
            implied_weekly = implied_annual / 52
            fi_gap = max(0, fi_target - latest_nw)

            fi_cols = st.columns(3)
            with fi_cols[0]:
                if latest_nw >= fi_target:
                    st.metric("Financial independence", "✅ Achieved",
                              help=f"Net worth ≥ FIRE number ({_fmt(fi_target)}).")
                else:
                    st.metric("FIRE gap", _fmt(fi_gap),
                              help=f"Amount needed to reach FIRE number ({_fmt(fi_target)}).")
            with fi_cols[1]:
                st.metric("Implied sustainable spending",
                          f"{_fmt(implied_weekly)}/wk",
                          help=f"£{implied_annual:,.0f}/yr — the spending level at which your net worth = 25× (4% SWR).")
            with fi_cols[2]:
                fi_pct = min(latest_nw / fi_target * 100, 100) if fi_target > 0 else 0
                st.metric("FI progress", f"{fi_pct:.0f}%",
                          help=f"{fi_pct:.1f}% of the way to your FIRE number.")

            # Liquid-vs-total: the 4% / 25× rule applies to *investable* wealth,
            # not home equity (not drawable income) or pre-57 pension (locked).
            # Surface the accessible figure when an asset split has been entered.
            st.caption(
                "⚠️ The figures above use **total** net worth. The 4% / 25× rule really applies "
                "to **investable** wealth — home equity isn't drawable income and pension is "
                "locked until age 57. The accessible figure below uses your wealth-mix split — "
                "tune it in the **🎚️ Adjust your wealth mix** panel under the chart."
            )
            if personal_asset_split is not None:
                _locked_pension = latest_age is not None and latest_age < 57
                _excl_share = personal_asset_split["Property"] + (
                    personal_asset_split["Pension"] if _locked_pension else 0.0)
                _liquid_nw = latest_nw * max(0.0, 1.0 - _excl_share)
                _liquid_annual = _liquid_nw * 0.04
                st.success(
                    f"**Investable wealth ≈ {_fmt(_liquid_nw)}** "
                    f"(excludes home equity{' and pre-57 pension' if _locked_pension else ''}). "
                    f"At 4% that sustainably funds **~{_fmt(_liquid_annual)}/yr** "
                    f"(~{_fmt(_liquid_annual / 52)}/wk) — versus {_fmt(implied_annual)}/yr "
                    f"implied by total net worth.",
                    icon="💧",
                )

    # Partner summary metric
    if partner_plot_df is not None and len(partner_plot_df) > 0:
        ps = partner_plot_df.sort_values("age")
        partner_latest_age = float(ps.iloc[-1]["age"])
        p_nw = float(ps.iloc[-1]["net_worth"])
        p_pct = estimate_exact_percentile(p_nw, round(partner_latest_age), benchmark)
        st.success(
            f"Partner · age **{partner_latest_age:.1f}** · net worth **{_fmt(p_nw)}** · "
            f"est. **~{p_pct:.0f}th percentile**" if p_pct else
            f"Partner · age **{partner_latest_age:.1f}** · net worth **{_fmt(p_nw)}**"
        )

        # Combined household callout + head-to-head leaderboard
        if personal_plot_df is not None and latest_nw is not None:
            combined = latest_nw + p_nw
            st.info(f"Combined household net worth: **{_fmt(combined)}**")

            # Head-to-head at same interpolated benchmark age
            you_pct = estimate_exact_percentile(latest_nw, round(latest_age or 0), benchmark)
            if you_pct and p_pct:
                h2h_col1, h2h_col2, h2h_col3 = st.columns(3)
                ahead_label = "You" if you_pct >= p_pct else "Partner"
                ahead_by    = abs(you_pct - p_pct)
                with h2h_col1:
                    st.metric("You — percentile", f"~{you_pct:.0f}th")
                with h2h_col2:
                    st.metric("Partner — percentile", f"~{p_pct:.0f}th")
                with h2h_col3:
                    st.metric("Ahead by", f"{ahead_by:.0f} pct pts",
                              help=f"{ahead_label} is ahead by {ahead_by:.0f} percentile points "
                                   f"(age-adjusted comparison).")


    # ── Goal / FIRE output ────────────────────────────────────────────────────────

    if personal_plot_df is not None and latest_nw is not None:
        sorted_pdf = personal_plot_df.sort_values("age")
        first_nw   = float(sorted_pdf.iloc[0]["net_worth"])
        age_span   = latest_age - float(sorted_pdf.iloc[0]["age"])

        for target_label, target_val in [
            ("your goal", goal_amount),
            ("FIRE number", fire_number),
        ]:
            if target_val > 0 and latest_nw < target_val:
                gap = target_val - latest_nw
                pct_there = min(latest_nw / target_val * 100, 100)
                cols = st.columns([2, 1])
                with cols[0]:
                    st.caption(f"Progress toward {target_label} ({_fmt(target_val)}): {pct_there:.0f}%")
                    st.progress(pct_there / 100)
                with cols[1]:
                    if age_span > 0.5 and latest_nw > 0:
                        cagr_cur = _safe_cagr(first_nw, latest_nw, age_span)
                        if cagr_cur is not None and cagr_cur > 0.001:
                            yrs = math.log(target_val / latest_nw) / math.log(1 + cagr_cur)
                            st.metric(f"ETA ({_fmt(target_val)})", f"~{yrs:.0f} yrs",
                                      help=f"At your current {cagr_cur*100:.1f}% CAGR.")
                        else:
                            avg_gain = (latest_nw - first_nw) / age_span
                            if avg_gain > 0:
                                yrs = (target_val - latest_nw) / avg_gain
                                if 0 < yrs < 60:
                                    st.metric(f"ETA ({_fmt(target_val)})", f"~{yrs:.0f} yrs",
                                              help=f"At your average gain of {_fmt(avg_gain)}/yr. "
                                                   f"(CAGR not shown for small or zero starting balances.)")

    # Log scale warning
    if log_scale and personal_plot_df is not None and (personal_plot_df["net_worth"] <= 0).any():
        st.warning(f"{(personal_plot_df['net_worth']<=0).sum()} data point(s) hidden on log scale.", icon="⚠️")


with tab_plan:
    # ── Planning inputs & calculators (moved here from the sidebar) ──────────────
    st.subheader("Goal, FIRE & savings calculators")
    st.caption("These set the targets used by the planning tools below and the "
               "goal/FIRE progress in the Progress tab.")
    with st.expander("Wealth goal & FIRE number", expanded=True):
        st.caption("Set net worth targets to track progress against.")
        goal_amount = st.number_input(
            "Target net worth (£)", 0, 10_000_000, 500_000, 10_000,
            format="%d", key="goal_amount",
            help="A custom net worth milestone you're working toward.",
        )
        fire_spending = st.number_input(
            "Annual retirement spending (£)", 0, 500_000, 30_000, 1_000,
            format="%d", key="fire_spend",
            help="Used to compute your FIRE number (25× spending, 4% SWR).",
        )
        fire_number = fire_spending * 25  # 4% safe withdrawal rate
        st.caption(f"FIRE number (25× spending, 4% SWR): **{_fmt(fire_number)}**")

    with st.expander("Retirement income & pension pot", expanded=False):
        retirement_age = st.number_input(
            "Target retirement age", 50, 80, 65, 1, key="ret_age",
        )
        pension_income = st.number_input(
            "Target annual pension income (£)", 0, 200_000, 20_000, 1_000,
            format="%d", key="pen_income",
        )
        # 2026/27 full new State Pension: £12,548/yr (£241.30/wk, +4.8% triple lock)
        state_pension = st.number_input(
            "Expected state pension (£/yr)", 0, 20_000, 12_548, 100,
            format="%d", key="state_pension",
            help="Full new State Pension 2025/26: £11,973/yr; "
                 "2026/27: £12,548/yr (£241.30/wk, +4.8% triple lock).",
        )
        if retirement_age and pension_income:
            private_needed = max(0, pension_income - state_pension)
            # Annuity rate: gilt-linked rates ~6.5% at age 65 in late 2024/25
            annuity_rate = 0.065 + (retirement_age - 65) * 0.0025
            pot_needed   = private_needed / max(annuity_rate, 0.02)
            st.caption(
                f"Private pension pot needed: **{_fmt(pot_needed)}** "
                f"(for £{private_needed:,}/yr net of state pension, "
                f"~{annuity_rate*100:.1f}% annuity rate at age {retirement_age}). "
                f"Single-life level annuity assumption — drawdown can be more flexible."
            )

    with st.expander("Savings rate calculator", expanded=False):
        st.caption("How much of your income do you need to save to hit each target? "
                   "(Now works here — it couldn't compute in the old sidebar location.)")
        annual_income = st.number_input(
            "Annual gross income (£)", 0, 1_000_000, 50_000, 1_000,
            format="%d", key="annual_income",
        )
        if annual_income > 0 and latest_nw is not None and latest_nw > 0:
            sorted_pdf2 = personal_plot_df.sort_values("age") if personal_plot_df is not None else None
            if sorted_pdf2 is not None and len(sorted_pdf2) >= 2:
                fs  = float(sorted_pdf2.iloc[0]["net_worth"])
                asp = float(sorted_pdf2.iloc[-1]["age"]) - float(sorted_pdf2.iloc[0]["age"])
                cagr_s = _safe_cagr(fs, latest_nw, asp)
                if cagr_s is not None and cagr_s > 0:
                    for tgt_label, tgt_val in [
                        ("goal", goal_amount),
                        ("FIRE number", fire_number),
                    ]:
                        if tgt_val > latest_nw:
                            yrs_s = math.log(tgt_val / latest_nw) / math.log(1 + cagr_s)
                            if 0 < yrs_s < 60:
                                savings_needed = (tgt_val - latest_nw * (1 + cagr_s) ** yrs_s) / yrs_s
                                savings_rate = max(0, savings_needed) / annual_income * 100
                                st.caption(
                                    f"To reach **{tgt_label}** ({_fmt(tgt_val)}) in "
                                    f"~{yrs_s:.0f} yrs at {cagr_s*100:.1f}% CAGR: "
                                    f"save **{savings_rate:.0f}%** of income "
                                    f"(~{_fmt(annual_income * savings_rate / 100)}/yr)."
                                )
                else:
                    st.caption(
                        f"Can't project a reliable savings rate: a starting net worth below "
                        f"£{CAGR_MIN_START:,} or flat/negative historical growth would distort "
                        f"the compound estimate."
                    )
            else:
                st.caption("Add at least 2 personal data points to enable the savings rate projection.")
        else:
            st.caption("Add your net worth data in the sidebar to enable this calculator.")

    # ── Scenario A/B compare ─────────────────────────────────────────────────────
    with st.expander("Scenario A/B compare — Plan A vs Plan B", expanded=False):
        st.caption("Set two plans side by side and compare projected net worth, percentile and "
                   "your FIRE number, starting from your latest net worth.")
        if latest_nw is None or latest_nw <= 0:
            st.info("Add your net worth data (sidebar) to use the scenario comparison.")
        else:
            def _scenario_inputs(label, prefix, d_monthly, d_ret, d_years):
                st.markdown(f"**{label}**")
                monthly = st.number_input("Monthly saving (£)", 0, 50_000, d_monthly, 100, key=f"{prefix}_monthly")
                ret     = st.number_input("Annual real return (%)", -2.0, 12.0, d_ret, 0.25, key=f"{prefix}_ret")
                years   = st.number_input("Years to project", 1, 50, d_years, 1, key=f"{prefix}_years")
                return monthly, ret / 100.0, years

            ab_in = st.columns(2)
            with ab_in[0]:
                a_monthly, a_r, a_years = _scenario_inputs("Plan A", "ab_a", 500, 4.0, 15)
            with ab_in[1]:
                b_monthly, b_r, b_years = _scenario_inputs("Plan B", "ab_b", 1_000, 6.0, 15)

            def _project_plan(monthly, r, years):
                annual = monthly * 12
                if abs(r) < 1e-9:
                    fv = latest_nw + annual * years
                else:
                    fv = latest_nw * (1 + r) ** years + annual * (((1 + r) ** years - 1) / r)
                tgt_age = latest_age + years if latest_age is not None else years
                pct = estimate_exact_percentile(fv, round(min(tgt_age, 85)), benchmark)
                return fv, tgt_age, pct

            a_fv, a_age, a_pct = _project_plan(a_monthly, a_r, a_years)
            b_fv, b_age, b_pct = _project_plan(b_monthly, b_r, b_years)

            ab_out = st.columns(2)
            with ab_out[0]:
                st.metric("Plan A — projected net worth", _fmt(a_fv),
                          help=f"At age {a_age:.0f}, {a_r*100:.1f}% real return, "
                               f"£{a_monthly:,}/mo saving.")
                if a_pct:
                    st.caption(f"≈ **{a_pct:.0f}th** percentile at age {a_age:.0f}")
            with ab_out[1]:
                st.metric("Plan B — projected net worth", _fmt(b_fv),
                          delta=f"{_fmt(b_fv - a_fv)} vs A",
                          help=f"At age {b_age:.0f}, {b_r*100:.1f}% real return, "
                               f"£{b_monthly:,}/mo saving.")
                if b_pct:
                    st.caption(f"≈ **{b_pct:.0f}th** percentile at age {b_age:.0f}")

            ab_fig = go.Figure()
            ab_fig.add_trace(go.Bar(
                x=["Plan A", "Plan B"], y=[a_fv, b_fv],
                marker_color=[COLOURS["person"], COLOURS["partner"]],
                text=[_fmt(a_fv), _fmt(b_fv)], textposition="outside",
                hovertemplate="%{x}: £%{y:,.0f}<extra></extra>",
            ))
            if fire_number and fire_number > 0:
                ab_fig.add_hline(y=fire_number, line=dict(color=NEUTRAL_GREY, width=1, dash="dash"),
                                 annotation_text=f"FIRE number {_fmt(fire_number)}",
                                 annotation_position="top left")
            ab_fig.update_layout(
                title=dict(text="Projected net worth — Plan A vs Plan B",
                           font=dict(size=14, color=TITLE_COLOUR), x=0),
                height=260, showlegend=False,
                yaxis=dict(tickprefix="£", tickformat=",.0f", gridcolor=GRID_COLOUR),
                margin=dict(l=70, r=30, t=50, b=30),
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(ab_fig, use_container_width=True, config=PLOTLY_CONFIG)

            _winner = "Plan B" if b_fv >= a_fv else "Plan A"
            _diff = abs(b_fv - a_fv)
            _msg = f"**{_winner}** ends ahead by **{_fmt(_diff)}** over the horizon."
            if fire_number and fire_number > 0:
                _hits = [n for n, fv in (("Plan A", a_fv), ("Plan B", b_fv)) if fv >= fire_number]
                _msg += (f" {' and '.join(_hits)} clear{'s' if len(_hits) == 1 else ''} the FIRE number."
                         if _hits else " Neither plan reaches the FIRE number in this horizon.")
            st.success(_msg)

    st.divider()

    # ── Retirement income summary ────────────────────────────────────────────────
    # Ties the planning inputs (state pension, retirement age, target income) together
    # with the user's projected net worth at retirement and shows estimated annual income.

    if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
        with st.expander("Retirement income forecast", expanded=False):
            st.caption(
                "Brings together your projected net worth at retirement with state pension "
                "and shows estimated annual income from three sources. "
                "All figures in **today's money (real terms)**. Indicative only — not advice."
            )
            if not real_terms:
                st.caption(
                    "⚠️ The benchmark and percentile above are currently shown in **nominal** terms "
                    "(the *Real terms* sidebar toggle is off), but this projection works in today's "
                    "money. Turn on **Real terms** in the sidebar for consistent units."
                )

            ri_col1, ri_col2, ri_col3 = st.columns(3)
            with ri_col1:
                ri_retire_age = st.number_input("Retirement age",
                    min_value=max(int(latest_age) + 1, 50), max_value=80,
                    value=int(retirement_age) if retirement_age and retirement_age > int(latest_age) else 65,
                    step=1, key="ri_retire_age",
                    help="Defaults to your pension calculator age in the sidebar.")
            with ri_col2:
                ri_real_return = st.number_input("Assumed real return on NW (%)",
                    0.0, 12.0, 4.0, 0.25, key="ri_real_return",
                    help="Annual return above inflation. Long-run UK equity has been ~5% real; a balanced 60/40 portfolio nearer 3–4%.")
            with ri_col3:
                ri_pension_share = st.slider("% of net worth in pension wrappers", 0, 100,
                    int(personal_asset_split["Pension"] * 100) if personal_asset_split else 30,
                    step=5, key="ri_pension_share",
                    help="Used to split your projected NW into the pension portion (eligible for annuity) "
                         "vs other wealth (drawn down at 4%).")

            # Project NW to retirement age using the assumed real return
            _ri_years = ri_retire_age - latest_age
            _ri_nw_at_retire = latest_nw * (1 + ri_real_return / 100) ** _ri_years

            # Split into pension / other
            _ri_pension_pot = _ri_nw_at_retire * (ri_pension_share / 100)
            _ri_other_wealth = _ri_nw_at_retire - _ri_pension_pot

            # 25% tax-free pension commencement lump sum (PCLS), capped at the Lump
            # Sum Allowance. The remaining 75% is what gets annuitised.
            _ri_pcls       = tax_free_lump_sum(_ri_pension_pot)
            _ri_annuitised = _ri_pension_pot - _ri_pcls

            # Annuity rate at retirement age (gilt-linked single-life, recent UK levels)
            _ri_ann_rate = 0.065 + (ri_retire_age - 65) * 0.0025
            _ri_annuity = _ri_annuitised * max(_ri_ann_rate, 0.02)

            # 4% draw from non-pension wealth (ISAs, GIAs, property income proxy)
            _ri_drawdown = _ri_other_wealth * 0.04

            # State pension (assume claimed from age 67+; tapered if user retires earlier)
            _ri_state_pen = state_pension if ri_retire_age >= 67 else 0

            _ri_total = _ri_annuity + _ri_drawdown + _ri_state_pen

            # Income tax (rUK 2025/26): the annuity and state pension are taxable
            # income; the 4% draw is assumed to come from ISAs/accessible wealth
            # (tax-free) and the 25% PCLS is tax-free. Net = pre-tax total − tax.
            _ri_taxable = _ri_annuity + _ri_state_pen
            _ri_tax     = income_tax_2025_26(_ri_taxable)
            _ri_net     = _ri_total - _ri_tax

            st.markdown(
                f"#### Projected income at age {ri_retire_age}  ·  "
                f"net worth ≈ {_fmt(_ri_nw_at_retire)}"
            )
            inc_c1, inc_c2, inc_c3, inc_c4 = st.columns(4)
            with inc_c1:
                st.metric("Annuity from pension", f"{_fmt(_ri_annuity)}/yr",
                          help=f"From {_fmt(_ri_annuitised)} — the 75% left after the 25% tax-free "
                               f"lump sum — at a {_ri_ann_rate*100:.1f}% annuity rate. Taxable income; "
                               "drawdown can be more flexible but rates vary with markets.")
            with inc_c2:
                st.metric("4% draw from other wealth", f"{_fmt(_ri_drawdown)}/yr",
                          help=f"From non-pension wealth {_fmt(_ri_other_wealth)} at 4% safe-withdrawal "
                               "rate. Assumed tax-free (ISA / accessible wrappers).")
            with inc_c3:
                if _ri_state_pen > 0:
                    st.metric("State pension", f"{_fmt(_ri_state_pen)}/yr",
                              help="From state pension age (currently 66, rising to 67 by 2028). Taxable.")
                else:
                    st.metric("State pension", "Not yet eligible",
                              help=f"State pension age is 66–67. You'd retire {67 - ri_retire_age:.0f}+ years before that.")
            with inc_c4:
                st.metric("Total income (pre-tax)", f"{_fmt(_ri_total)}/yr",
                          delta=f"~{_fmt(_ri_total/52)}/week",
                          help="Sum of the three sources above, before income tax.")

            # Net-of-tax + tax-free lump sum — the figures you can actually spend.
            net_c1, net_c2, net_c3 = st.columns(3)
            with net_c1:
                st.metric("Tax-free lump sum (one-off)", _fmt(_ri_pcls),
                          help="25% of your pension pot, taken tax-free at retirement (capped at the "
                               f"£{PENSION_LSA:,} Lump Sum Allowance). A one-off, not annual income.")
            with net_c2:
                st.metric("Income tax", f"−{_fmt(_ri_tax)}/yr",
                          help=f"rUK 2025/26 income tax on the taxable {_fmt(_ri_taxable)}/yr "
                               "(annuity + state pension). The 4% ISA draw and the 25% lump sum are "
                               "tax-free. Scotland differs.")
            with net_c3:
                st.metric("Net annual income", f"{_fmt(_ri_net)}/yr",
                          delta=f"~{_fmt(_ri_net/52)}/week",
                          help="Annual income after income tax — what you can actually spend.")

            # Compare to target
            try:
                _target = float(pension_income) if pension_income else 0
            except (NameError, ValueError):
                _target = 0
            if _target > 0:
                _pct = min(_ri_net / _target * 100, 999)
                _delta = _ri_net - _target
                if _delta >= 0:
                    st.success(
                        f"Your **net** income would exceed your target of {_fmt(_target)}/yr by "
                        f"**{_fmt(_delta)}/yr** ({_pct:.0f}% of target, after income tax).",
                        icon="✅",
                    )
                else:
                    st.warning(
                        f"Your **net** income would fall **{_fmt(abs(_delta))}/yr short** of your target "
                        f"of {_fmt(_target)}/yr ({_pct:.0f}% of target, after income tax). "
                        "Consider saving more, working longer, or accepting a lower income.",
                        icon="⚠️",
                    )

            st.caption(
                "**Notes.** Real return assumed constant — actual returns vary year to year. "
                "Annuity figures are level (no inflation linking) using current UK gilt-linked rates. "
                "Drawdown uses the 4% rule (Trinity Study) — for a 30-year retirement; longer horizons "
                "or higher equity exposure may require lower rates. Income tax is the rUK 2025/26 "
                "estimate (England/Wales/NI — Scotland differs) and assumes the 4% draw comes from "
                "ISAs/tax-free wrappers."
            )


    # ── ISA bridge calculator (early retirement before pension access) ────────────
    # Many UK FIRE-planners face a gap: they can stop work at e.g. 50 but private
    # pension access is locked until 57 (rising to 58 in 2028). The "bridge" is
    # how much accessible (ISA / GIA) wealth they need to cover spending from FIRE
    # age until pension access age.

    if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
        with st.expander("ISA / accessible-wealth bridge (for early retirement)"):
            st.caption(
                "If you want to retire **before pension access age** (currently 57, rising to 58 in 2028, "
                "and 10 years below state pension age thereafter), you need enough **accessible** wealth "
                "(ISA, GIA, savings — not pension) to cover spending until the pension unlocks. "
                "This calculator sizes that bridge fund."
            )
            if not real_terms:
                st.caption(
                    "⚠️ The benchmark/percentile above are **nominal** (the *Real terms* sidebar "
                    "toggle is off); the figures here are in today's money. Turn on **Real terms** "
                    "for consistent units."
                )

            ib_col1, ib_col2, ib_col3 = st.columns(3)
            with ib_col1:
                ib_fire_age = st.number_input(
                    "FIRE age (stop working)", 35, 65,
                    value=min(int(latest_age) + 15 if latest_age else 50, 60),
                    step=1, key="ib_fire_age",
                    help="Age you intend to stop drawing employment income.",
                )
            with ib_col2:
                ib_pension_age = st.number_input(
                    "Pension access age", 55, 70, 57, 1, key="ib_pension_age",
                    help="Earliest you can access private pension. 55 historically; "
                         "57 from April 2028; will rise with state pension age (10-yr gap).",
                )
            with ib_col3:
                ib_annual_spend = st.number_input(
                    "Annual spend (£, real terms)", 5_000, 500_000,
                    int(fire_spending) if fire_spending else 30_000, 1_000,
                    format="%d", key="ib_spend",
                    help="What you'll spend each year during the bridge period, in today's money.",
                )

            bridge_years = max(0, ib_pension_age - ib_fire_age)

            if bridge_years == 0:
                st.success(
                    "No bridge needed — your FIRE age is at or after pension access age. "
                    "You can draw straight from pension wrappers.",
                    icon="✅",
                )
            else:
                # Bridge calculation: use 4% SWR for the bridge period too.
                # For short horizons (< 10 yrs) it's conservative; longer horizons
                # may need higher SWR. The 25x multiplier comes from 1/0.04.
                #
                # Two approaches:
                # 1. Simple: bridge_years × annual_spend (no growth, full liquidation)
                # 2. SWR-based: spend × 25 × (bridge_years / 30)  [partial Trinity]
                #
                # For honesty, show both. The SWR method assumes the bridge fund
                # also earns ~4% real return during the bridge years.
                bridge_simple = bridge_years * ib_annual_spend
                # At constant 4% real return, FV-of-annuity factor for `bridge_years`:
                #   PV = spend × (1 - (1+r)^-n) / r, with r=0.04
                r = 0.04
                pv_factor = (1 - (1 + r) ** -bridge_years) / r if r > 0 else bridge_years
                bridge_swr = ib_annual_spend * pv_factor

                ib_m1, ib_m2, ib_m3 = st.columns(3)
                with ib_m1:
                    st.metric(
                        "Bridge years",
                        f"{bridge_years}",
                        help=f"From FIRE age {ib_fire_age} to pension access age {ib_pension_age}.",
                    )
                with ib_m2:
                    st.metric(
                        "ISA pot needed (conservative)",
                        _fmt(bridge_simple),
                        help="Years × spend. Assumes no growth on the bridge fund "
                             "(it all just runs down).",
                    )
                with ib_m3:
                    st.metric(
                        "ISA pot needed (4% real)",
                        _fmt(bridge_swr),
                        delta=_fmt(bridge_swr - bridge_simple),
                        delta_color="inverse",
                        help="PV-of-annuity at 4% real return. The bridge fund earns "
                             "while it's being drawn down, so a smaller pot is needed.",
                    )

                # ETA to bridge target (using latest_nw + CAGR if available)
                sorted_pdf_for_eta = personal_plot_df.sort_values("age")
                if len(sorted_pdf_for_eta) >= 2:
                    _fs = float(sorted_pdf_for_eta.iloc[0]["net_worth"])
                    _asp = float(sorted_pdf_for_eta.iloc[-1]["age"]) - float(sorted_pdf_for_eta.iloc[0]["age"])
                    _cagr = _safe_cagr(_fs, latest_nw, _asp)
                    if _cagr and _cagr > 0:
                        # Years to grow latest_nw → bridge_swr at current CAGR
                        if latest_nw < bridge_swr:
                            yrs_to_bridge = math.log(bridge_swr / latest_nw) / math.log(1 + _cagr)
                            eta_age = latest_age + yrs_to_bridge
                            gap_yrs = ib_fire_age - latest_age
                            if eta_age <= ib_fire_age:
                                st.success(
                                    f"At your current {_cagr*100:.1f}% CAGR you'd reach the bridge target "
                                    f"by age {eta_age:.0f} — **{gap_yrs - yrs_to_bridge:.0f} years of buffer** "
                                    f"before FIRE age {ib_fire_age}.",
                                    icon="✅",
                                )
                            else:
                                shortfall_yrs = eta_age - ib_fire_age
                                st.warning(
                                    f"At your current {_cagr*100:.1f}% CAGR you'd reach the bridge target "
                                    f"by age {eta_age:.0f} — **{shortfall_yrs:.1f} years past FIRE age {ib_fire_age}**. "
                                    "Consider extending the timeline, lowering spend, or increasing savings.",
                                    icon="⚠️",
                                )
                        else:
                            st.success(
                                f"Your current net worth of {_fmt(latest_nw)} already exceeds the bridge "
                                f"target of {_fmt(bridge_swr)}. Provided enough of it is in accessible "
                                "wrappers (ISA / GIA, not pension), you're set.",
                                icon="✅",
                            )

                # ── Second leg: pension access age → state pension age ──────────────
                # Pension wealth is now accessible, but the state pension hasn't
                # started, so you still self-fund the full spend for these years.
                leg2_years = max(0, STATE_PENSION_AGE - ib_pension_age)
                if leg2_years > 0:
                    leg2_factor = (1 - (1 + r) ** -leg2_years) / r if r > 0 else leg2_years
                    leg2_pot = ib_annual_spend * leg2_factor
                    st.markdown(
                        f"**Second leg — pension access ({ib_pension_age}) to state pension "
                        f"({STATE_PENSION_AGE})**"
                    )
                    l2c1, l2c2, l2c3 = st.columns(3)
                    with l2c1:
                        st.metric("Leg-2 years", f"{leg2_years}",
                                  help="Years drawing your own pot before the state pension starts.")
                    with l2c2:
                        st.metric("Leg-2 pot (4% real)", _fmt(leg2_pot),
                                  help="Self-funded from pension + accessible wealth, since the state "
                                       "pension isn't in payment yet. PV-of-annuity at 4% real.")
                    with l2c3:
                        st.metric("Both legs combined", _fmt(bridge_swr + leg2_pot),
                                  help=f"Leg 1 (accessible-only, to age {ib_pension_age}) + Leg 2 "
                                       f"(to state pension age {STATE_PENSION_AGE}). From the state "
                                       "pension age onward, the state pension reduces your annual need.")

                st.caption(
                    "**Assumes 4% real return during drawdown.** Leg 1 (to pension access age) must be "
                    "in accessible wrappers (ISA / GIA, not pension) — this tool doesn't verify that, so "
                    "check your ISA + GIA balance covers it. Leg 2 (pension access to state pension age) "
                    "can also draw on pension. From state pension age, the state pension reduces the "
                    "annual need."
                )



    # ── Drawdown / pot longevity simulator ───────────────────────────────────────
    # How long does your pot last in retirement under various withdrawal rates?

    if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
        with st.expander("Retirement drawdown — pot longevity", expanded=False):
            st.caption(
                "How long will your money last in retirement? Simulates drawdown from a starting "
                "pot, with annual withdrawals inflation-adjusted, against a chosen real return. "
                "Shows the age your pot is depleted — and how that compares to UK life expectancy. "
                "**All figures in today's money (real terms).** Indicative only — not advice."
            )
            if not real_terms:
                st.caption(
                    "⚠️ The benchmark/percentile above are **nominal** (the *Real terms* sidebar "
                    "toggle is off); the figures here are in today's money. Turn on **Real terms** "
                    "for consistent units."
                )

            dd_col1, dd_col2, dd_col3, dd_col4 = st.columns(4)
            with dd_col1:
                dd_start_age = st.number_input("Retirement age",
                    min_value=max(int(latest_age) + 1, 50), max_value=80,
                    value=int(retirement_age) if retirement_age and retirement_age > int(latest_age) else 65,
                    step=1, key="dd_start_age")
            with dd_col2:
                # Project NW to start age at user-chosen real return
                _dd_default_pot = int(latest_nw * 1.04 ** max(0, dd_start_age - latest_age))
                dd_start_pot = st.number_input("Starting pot at retirement (£)",
                    min_value=10_000, max_value=20_000_000,
                    value=max(10_000, _dd_default_pot), step=10_000, format="%d", key="dd_start_pot",
                    help="Pre-filled with your latest NW projected at 4% real return to your retirement age. "
                         "Edit if you want a different starting amount.")
            with dd_col3:
                dd_annual_spend = st.number_input("Annual spend (£, today's money)",
                    min_value=5_000, max_value=500_000,
                    value=int(fire_spending) if fire_spending else 30_000, step=1_000, format="%d", key="dd_spend",
                    help="Annual withdrawal in today's money. Will be inflation-adjusted each year.")
            with dd_col4:
                dd_real_return = st.number_input("Real return (%)",
                    -2.0, 10.0, 4.0, 0.25, key="dd_return",
                    help="Return above inflation on the pot during retirement. "
                         "Common assumptions: 3% for cautious, 4% balanced, 5% equity-heavy.")

            # Optional: include state pension reducing the withdrawal need
            dd_include_sp = st.checkbox("Include state pension (reduces drawdown need)",
                value=True, key="dd_sp",
                help="If checked, state pension income (from age 66/67) is subtracted from the annual "
                     "spend, so less is drawn from the pot once you qualify.")
            if dd_include_sp:
                st.caption(
                    "State pension is subtracted £-for-£ from the annual spend — a simplification that "
                    "assumes it falls within your Personal Allowance and isn't itself taxed. Drawdown "
                    "figures are pre-tax; tax on withdrawals depends on your wrapper mix (ISA "
                    "withdrawals are tax-free, pension income is taxable above the allowance)."
                )

            # Simulate
            _dd_pot = float(dd_start_pot)
            _dd_r = dd_real_return / 100
            _dd_ages = [dd_start_age]
            _dd_pots = [_dd_pot]
            _dd_runout_age = None
            _max_sim_age = 100
            _state_pen_age = STATE_PENSION_AGE  # imported from utils/uk_tax.py

            for age in range(dd_start_age, _max_sim_age):
                # Annual withdrawal in real terms (already adjusted because we work in real £)
                # Reduce by state pension from state pension age onward, if opted in
                sp = state_pension if (dd_include_sp and age >= _state_pen_age) else 0
                net_withdrawal = max(0, dd_annual_spend - sp)
                # End-of-year balance: grow first, then withdraw (mid-year would be more accurate
                # but ordering doesn't change pot longevity much for small SWRs)
                _dd_pot = _dd_pot * (1 + _dd_r) - net_withdrawal
                _dd_ages.append(age + 1)
                _dd_pots.append(max(0, _dd_pot))
                if _dd_pot <= 0 and _dd_runout_age is None:
                    _dd_runout_age = age + 1
                    break

            # Headline metric row
            dd_m1, dd_m2, dd_m3, dd_m4 = st.columns(4)
            with dd_m1:
                st.metric("Years in retirement covered",
                          f"{(_dd_runout_age - dd_start_age) if _dd_runout_age else f'≥{_max_sim_age - dd_start_age}'}")
            with dd_m2:
                if _dd_runout_age:
                    st.metric("Pot depleted at age", f"{_dd_runout_age}",
                              help="Age your pot reaches zero given the spend and real return.")
                else:
                    st.metric("Pot survives to", f"≥ age {_max_sim_age}",
                              delta="Sustainable", help="Pot still has funds at age 100.")
            with dd_m3:
                # UK ONS cohort life expectancy at this retirement age (utils/uk_tax.py)
                _le_at_retire = life_expectancy_at(dd_start_age)
                st.metric("Avg life expectancy", f"~{_le_at_retire}",
                          help="ONS cohort life expectancy at this retirement age (mixed-sex). "
                               "Many will live longer — plan for ~10 years beyond average.")
            with dd_m4:
                # Implied SWR
                _swr_implied = dd_annual_spend / dd_start_pot * 100
                st.metric("Implied withdrawal rate", f"{_swr_implied:.1f}%",
                          help="Annual spend ÷ starting pot. <4% is generally considered safe over 30+ years.")

            # Verdict
            if _dd_runout_age is None:
                st.success(f"Your pot sustains the chosen spend indefinitely at {dd_real_return:.1f}% real return.",
                           icon="✅")
            else:
                yrs_covered = _dd_runout_age - dd_start_age
                if _dd_runout_age >= _le_at_retire + 5:
                    st.info(
                        f"Pot lasts ~{yrs_covered} years, until age {_dd_runout_age}. "
                        f"That's comfortably beyond UK average life expectancy at this age (~{_le_at_retire}).",
                        icon="✅",
                    )
                elif _dd_runout_age >= _le_at_retire:
                    st.warning(
                        f"Pot lasts ~{yrs_covered} years, until age {_dd_runout_age}. "
                        f"Just covers average life expectancy (~{_le_at_retire}) — half of people will outlive this. "
                        "Consider lower spend, higher return assumption, or planning longer.",
                        icon="⚠️",
                    )
                else:
                    st.error(
                        f"Pot lasts only ~{yrs_covered} years, depleting at age {_dd_runout_age} — "
                        f"well before average life expectancy (~{_le_at_retire}). "
                        "Reduce spend, retire later, or save more.",
                        icon="🚨",
                    )

            # Drawdown chart
            _dd_fig = go.Figure()
            _dd_fig.add_trace(go.Scatter(
                x=_dd_ages, y=_dd_pots,
                mode="lines", line=dict(color=COLOURS["person"], width=2.5),
                fill="tozeroy", fillcolor="rgba(249,115,22,0.10)",
                name="Pot balance",
                hovertemplate="Age %{x}<br>£%{y:,.0f}<extra></extra>",
            ))
            _dd_fig.add_hline(y=0, line=dict(color=NEUTRAL_GREY, width=1))
            # Life expectancy marker
            _dd_fig.add_vline(x=_le_at_retire,
                line=dict(color=AXIS_LABEL_COLOUR, width=1, dash="dash"),
                annotation_text=f"Avg life exp ~{_le_at_retire}",
                annotation_position="top right",
                annotation=dict(font=dict(size=10, color=AXIS_LABEL_COLOUR)),
            )
            if _dd_runout_age:
                _dd_fig.add_vline(x=_dd_runout_age,
                    line=dict(color="#ef4444", width=1.5, dash="dot"),
                    annotation_text=f"Depleted age {_dd_runout_age}",
                    annotation_position="bottom right",
                    annotation=dict(font=dict(size=10, color="#ef4444")),
                )
            _dd_fig.update_layout(
                title=dict(text="Pot balance over retirement (real terms)",
                           font=dict(size=14, color=TITLE_COLOUR), x=0),
                xaxis=dict(title="Age", gridcolor=GRID_COLOUR, zeroline=False),
                yaxis=dict(title="Pot value (£, today's money)", tickprefix="£", tickformat=",.0f",
                           gridcolor=GRID_COLOUR),
                plot_bgcolor="white", paper_bgcolor="white",
                height=300, margin=dict(l=70, r=40, t=50, b=50), hovermode="x unified",
            )
            st.plotly_chart(_dd_fig, use_container_width=True, config=PLOTLY_CONFIG)

            # Sensitivity table: how does longevity change with different real returns?
            st.markdown("**Sensitivity: how long does the pot last at different return assumptions?**")
            sens_rows = []
            for _r_test in [1, 2, 3, 4, 5, 6]:
                _r = _r_test / 100
                _pot = float(dd_start_pot)
                _runout = None
                for age in range(dd_start_age, _max_sim_age + 1):
                    sp = state_pension if (dd_include_sp and age >= _state_pen_age) else 0
                    net_w = max(0, dd_annual_spend - sp)
                    _pot = _pot * (1 + _r) - net_w
                    if _pot <= 0 and _runout is None:
                        _runout = age + 1
                        break
                sens_rows.append({
                    "Real return": f"{_r_test}%",
                    "Pot lasts until": (f"age {_runout}" if _runout
                                         else f"≥ age {_max_sim_age} (sustainable)"),
                    "Years covered": (f"{_runout - dd_start_age}" if _runout
                                       else f"≥ {_max_sim_age - dd_start_age}"),
                })
            st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True)
            st.caption(
                "Sensitivity is one of the most important things to check — small changes in assumed "
                "real return swing the depletion age by years."
            )

            # ── Stochastic drawdown ───────────────────────────────────────────────
            st.markdown("---")
            st.markdown("**Stochastic stress test (sequence-of-returns risk)**")
            st.caption(
                "Same setup, but with **random year-to-year returns** instead of the fixed real "
                "return. Runs 1,000 simulations to compute the probability that your pot survives "
                "to each age. A bad first decade — even with the same long-run average — can deplete "
                "much faster than the deterministic model suggests."
            )

            sd_col1, sd_col2 = st.columns(2)
            with sd_col1:
                sd_sigma = st.number_input(
                    "Annual volatility (%)", 0.0, 25.0, 10.0, 0.5, key="sd_sigma",
                    help="Volatility of the retirement portfolio. Conservative 60/40 ≈ 9-10%, "
                         "balanced ≈ 11-13%, equity-heavy ≈ 14-18%.",
                )
            with sd_col2:
                sd_horizon_age = st.number_input(
                    "Plan to age", _le_at_retire, 100, max(_le_at_retire + 5, 90), 1, key="sd_horizon",
                    help="Age you want your pot to last to. The success rate is computed at this age.",
                )

            # Build simulation: withdrawals = -annual_contribution
            # Each year's net withdrawal varies if state pension kicks in mid-horizon,
            # so we run it ourselves rather than calling run_monte_carlo directly.
            sd_years = sd_horizon_age - dd_start_age
            if sd_years > 0:
                sd_rng = np.random.default_rng(seed=42)
                sd_n_sims = 1_000
                sd_returns = sd_rng.normal(
                    loc=dd_real_return / 100,
                    scale=sd_sigma / 100,
                    size=(sd_n_sims, sd_years),
                )
                sd_paths = np.zeros((sd_n_sims, sd_years + 1), dtype=float)
                sd_paths[:, 0] = float(dd_start_pot)
                for t in range(sd_years):
                    age_t = dd_start_age + t
                    sp = state_pension if (dd_include_sp and age_t >= _state_pen_age) else 0
                    net_w = max(0, dd_annual_spend - sp)
                    sd_paths[:, t + 1] = np.maximum(0, sd_paths[:, t] * (1 + sd_returns[:, t]) - net_w)
                    # Once a path hits zero it stays zero (no further negative draw)

                # Survival probability over time
                sd_alive = (sd_paths > 0).mean(axis=0)
                sd_ages_arr = np.arange(dd_start_age, dd_start_age + sd_years + 1)

                survival_at_horizon = float(sd_alive[-1])
                survival_at_le = float(sd_alive[_le_at_retire - dd_start_age]) \
                    if _le_at_retire - dd_start_age <= sd_years else 1.0

                sd_m1, sd_m2 = st.columns(2)
                with sd_m1:
                    st.metric(
                        f"Survive to avg life expectancy (~{_le_at_retire})",
                        f"{survival_at_le*100:.0f}%",
                        help=f"Probability the pot still has funds at age {_le_at_retire}.",
                    )
                with sd_m2:
                    st.metric(
                        f"Survive to age {sd_horizon_age}",
                        f"{survival_at_horizon*100:.0f}%",
                        help=f"Probability the pot still has funds at age {sd_horizon_age}.",
                    )

                # Verdict colour for the headline
                if survival_at_horizon >= 0.85:
                    st.success(
                        f"Pot has a **{survival_at_horizon*100:.0f}% probability** of surviving to "
                        f"age {sd_horizon_age} under the chosen volatility — comfortable cushion.",
                        icon="✅",
                    )
                elif survival_at_horizon >= 0.6:
                    st.warning(
                        f"Pot has a **{survival_at_horizon*100:.0f}% probability** of surviving to "
                        f"age {sd_horizon_age}. Reasonable but not safe — consider a lower spend or "
                        "more cautious assumptions.",
                        icon="⚠️",
                    )
                else:
                    st.error(
                        f"Pot has only a **{survival_at_horizon*100:.0f}% probability** of surviving "
                        f"to age {sd_horizon_age}. High risk of running out — reduce spend, retire later, "
                        "or save more.",
                        icon="🚨",
                    )

                # Survival probability chart
                sd_fig = go.Figure()
                sd_fig.add_trace(go.Scatter(
                    x=sd_ages_arr, y=sd_alive * 100,
                    mode="lines",
                    line=dict(color=COLOURS["p50"], width=3),
                    fill="tozeroy", fillcolor="rgba(29,78,216,0.10)",
                    name="Survival probability",
                    hovertemplate="Age %{x}<br>%{y:.0f}% chance pot survives<extra></extra>",
                ))
                sd_fig.add_hline(y=50, line=dict(color=NEUTRAL_GREY, width=1, dash="dot"),
                                 annotation_text="50%", annotation_position="right",
                                 annotation=dict(font=dict(size=10, color=NEUTRAL_GREY)))
                sd_fig.add_vline(x=_le_at_retire,
                                 line=dict(color=AXIS_LABEL_COLOUR, width=1, dash="dash"),
                                 annotation_text=f"Avg life exp ~{_le_at_retire}",
                                 annotation_position="top left",
                                 annotation=dict(font=dict(size=10, color=AXIS_LABEL_COLOUR)))
                sd_fig.update_layout(
                    title=dict(text="Probability the pot survives to each age",
                               font=dict(size=13, color=TITLE_COLOUR), x=0),
                    xaxis=dict(title="Age", gridcolor=GRID_COLOUR),
                    yaxis=dict(title="Survival probability (%)", ticksuffix="%",
                               range=[0, 105], gridcolor=GRID_COLOUR),
                    plot_bgcolor="white", paper_bgcolor="white",
                    height=260, margin=dict(l=60, r=40, t=50, b=50),
                    showlegend=False, hovermode="x unified",
                )
                st.plotly_chart(sd_fig, use_container_width=True, config=PLOTLY_CONFIG)



    # ── What-if projection ────────────────────────────────────────────────────────

    if personal_plot_df is not None and len(personal_plot_df) >= 1:
        with st.expander("What-if projection"):
            st.caption(
                "Forward-project your net worth from the latest data point. "
                "**By default this is a pure investment-growth projection — no further savings or contributions** "
                "(your starting balance grows by the chosen CAGR). "
                "Use the **Monthly contributions** field below to layer in ongoing saving. "
                "Illustrative only — not financial advice."
            )
            wcol1, wcol2, wcol3, wcol4 = st.columns(4)
            with wcol1:
                wi_cagr1 = st.number_input("Scenario 1 (%)", -5.0, 25.0, 3.0, 0.5, key="wi1",
                                           help="Bear case / conservative")
            with wcol2:
                wi_cagr2 = st.number_input("Scenario 2 (%)", -5.0, 25.0, 6.0, 0.5, key="wi2",
                                           help="Base case")
            with wcol3:
                wi_cagr3 = st.number_input("Scenario 3 (%)", -5.0, 25.0, 10.0, 0.5, key="wi3",
                                           help="Bull case / optimistic")
            with wcol4:
                wi_age = st.slider(
                    "Project to age",
                    min_value=max(int(latest_age) + 1 if latest_age else 31, 30),
                    max_value=85, value=min(70, 85), key="whatif_age",
                )
            wi_monthly = st.number_input(
                "Monthly contributions (£)", 0, 50_000, 0, 100, format="%d", key="wi_monthly",
                help="Optional ongoing savings, added on top of investment returns. "
                     "Applied equally to all three scenarios. Leave at 0 for a pure-growth projection.",
            )
            if wi_monthly == 0:
                st.caption("ℹ️ Projection assumes **no further contributions** — only investment growth at the CAGR above.")
            else:
                st.caption(
                    f"ℹ️ Projection includes **£{wi_monthly:,}/month** ongoing contributions "
                    f"(£{wi_monthly*12:,}/year) on top of investment growth."
                )

            scenarios = [
                (wi_cagr1 / 100, f"Scenario 1 ({wi_cagr1:+.1f}%)"),
                (wi_cagr2 / 100, f"Scenario 2 ({wi_cagr2:+.1f}%)"),
                (wi_cagr3 / 100, f"Scenario 3 ({wi_cagr3:+.1f}%)"),
            ]
            st.plotly_chart(
                build_whatif_figure(
                    personal_plot_df, benchmark, scenarios,
                    project_to_age=wi_age,
                    monthly_savings=wi_monthly,
                    actual_colour=COLOURS["person"],
                    price_label=(f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"),
                ),
                use_container_width=True, config=PLOTLY_CONFIG,
            )

            # Projected percentiles at target age for each scenario
            if latest_nw and latest_nw > 0:
                sc_cols = st.columns(3)
                for i, (cagr, sc_label) in enumerate(scenarios):
                    t = wi_age - (latest_age or 0)
                    annual_wi = wi_monthly * 12
                    if abs(cagr) < 1e-10:
                        proj_nw_at = latest_nw + annual_wi * t
                    else:
                        proj_nw_at = (latest_nw * (1 + cagr) ** t
                                      + annual_wi * ((1 + cagr) ** t - 1) / cagr)
                    proj_pct   = estimate_exact_percentile(proj_nw_at, min(wi_age, 85), benchmark)
                    with sc_cols[i]:
                        st.metric(
                            sc_label,
                            _fmt(proj_nw_at),
                            delta=f"~{proj_pct:.0f}th pct" if proj_pct else "n/a",
                            help=(f"Projected net worth at age {wi_age} with £{wi_monthly:,}/mo "
                                  "ongoing contributions on top of investment growth."
                                  if wi_monthly else
                                  f"Projected net worth at age {wi_age} from pure investment growth "
                                  "(no further contributions)."),
                        )


    # ── Monte Carlo projection ────────────────────────────────────────────────────

    if personal_plot_df is not None and len(personal_plot_df) >= 1 and latest_nw and latest_nw > 0:
        with st.expander("Monte Carlo projection (stochastic returns)"):
            st.caption(
                "Forward-project with **random returns** rather than a fixed CAGR. "
                "Each simulation samples annual returns from a normal distribution; "
                "the shaded bands show the range of likely outcomes. "
                "This captures sequence-of-returns risk that the deterministic what-if can't show."
            )

            # Mode toggle: fixed allocation vs glide path
            mc_mode = st.radio(
                "Allocation",
                ["Fixed return assumption", "Equity/bond glide path"],
                key="mc_mode", horizontal=True,
                help="Glide path uses real asset-class assumptions (equity ~5.5%/18%, "
                     "bond ~1.5%/6%) and lets you de-risk over time.",
            )

            mc_glide_path: tuple[float, float] | None = None

            if mc_mode == "Fixed return assumption":
                mc1, mc2 = st.columns(2)
                with mc1:
                    mc_mean = st.number_input(
                        "Expected real return (%)", -5.0, 15.0, 5.0, 0.5, key="mc_mean",
                        help="60/40 portfolio ≈ 4-5%, 100% equity ≈ 5-7%.",
                    )
                with mc2:
                    mc_sigma = st.number_input(
                        "Annual volatility (%)", 0.0, 30.0, 12.0, 1.0, key="mc_sigma",
                        help="60/40 portfolio ≈ 9-11%, 100% global equity ≈ 16-18%.",
                    )
            else:
                g1, g2 = st.columns(2)
                with g1:
                    gp_start = st.slider(
                        "Equity allocation now (%)", 0, 100, 90, 5, key="mc_gp_start",
                    )
                with g2:
                    gp_end = st.slider(
                        "Equity allocation at target age (%)", 0, 100, 40, 5, key="mc_gp_end",
                    )
                mc_glide_path = (gp_start / 100, gp_end / 100)
                # mc_mean / mc_sigma not used when glide path active
                mc_mean = mc_sigma = 0  # placeholder for downstream caption logic

            mc3, mc4 = st.columns(2)
            with mc3:
                mc_target_age = st.slider(
                    "Project to age",
                    min_value=max(int(latest_age) + 1 if latest_age else 31, 30),
                    max_value=85,
                    value=min(int(latest_age) + 25 if latest_age else 65, 85),
                    key="mc_target_age",
                )
            with mc4:
                mc_monthly = st.number_input(
                    "Monthly contributions (£)", 0, 50_000, 0, 100,
                    format="%d", key="mc_monthly",
                )

            mc_target_nw = st.number_input(
                "Target net worth (£) — optional",
                0, 10_000_000, int(goal_amount) if "goal_amount" in dir() and goal_amount else 500_000,
                10_000, format="%d", key="mc_target",
                help="Probability of finishing above this value will be shown below.",
            )
            mc_show_paths = st.slider(
                "Show sample paths", 0, 100, 30, 5, key="mc_show_paths",
                help="Number of individual simulation paths to overlay (0 = bands only).",
            )

            # Reroll button: lets the user see how the bands shift under a different
            # random draw. Seed defaults to 42 (deterministic UX so the chart doesn't
            # jitter on slider change), but the user can advance it to peek at
            # alternative draws — useful for understanding how much the chart shape
            # depends on the specific random sample.
            mc_seed_col1, mc_seed_col2 = st.columns([1, 4])
            with mc_seed_col1:
                if st.button("🎲 Reroll", key="mc_reroll",
                             help="Generate a different random draw with the same assumptions."):
                    st.session_state["mc_seed"] = st.session_state.get("mc_seed", 42) + 1
            with mc_seed_col2:
                _mc_seed = st.session_state.get("mc_seed", 42)
                if _mc_seed != 42:
                    st.caption(f"Seed: {_mc_seed} (rerolled). Reset by refreshing the page.")

            mc_years = max(1, mc_target_age - int(latest_age or 30))
            mc_paths = run_monte_carlo(
                start_nw=float(latest_nw),
                years=mc_years,
                mean_return=mc_mean / 100 if mc_glide_path is None else 0.05,
                std_return=mc_sigma / 100 if mc_glide_path is None else 0.12,
                n_sims=1_000,
                annual_contribution=mc_monthly * 12,
                seed=st.session_state.get("mc_seed", 42),
                glide_path=mc_glide_path,
            )

            mc_fig = build_monte_carlo_chart(
                mc_paths,
                start_age=float(latest_age or 30),
                target=mc_target_nw if mc_target_nw > 0 else None,
                show_sample_paths=mc_show_paths,
                median_colour=COLOURS["p50"],
                target_colour=COLOURS["person"],
                price_label=(f"{REAL_BASE_YEAR} real terms" if real_terms
                             else f"nominal ({DATA_YEAR} prices)"),
            )
            st.plotly_chart(mc_fig, use_container_width=True, config=PLOTLY_CONFIG)

            # Outcome summary
            final_values = mc_paths[:, -1]
            p10, p50, p90 = (float(v) for v in
                             (final_values.min() if len(final_values) < 1 else
                              (np.percentile(final_values, 10),
                               np.percentile(final_values, 50),
                               np.percentile(final_values, 90))))
            prob_target = probability_of_reaching(mc_paths, mc_target_nw) if mc_target_nw > 0 else None

            col_p10, col_p50, col_p90, col_pt = st.columns(4)
            with col_p10:
                st.metric(f"Pessimistic (P10) at age {mc_target_age}", _fmt(p10))
            with col_p50:
                st.metric(f"Median (P50) at age {mc_target_age}", _fmt(p50))
            with col_p90:
                st.metric(f"Optimistic (P90) at age {mc_target_age}", _fmt(p90))
            with col_pt:
                if prob_target is not None:
                    st.metric(
                        "Reach target",
                        f"{prob_target*100:.0f}%",
                        help=f"Fraction of simulations that finish at or above £{mc_target_nw:,}.",
                    )

            if mc_glide_path is None:
                assumption_text = f"N(μ={mc_mean:.1f}%, σ={mc_sigma:.1f}%) fixed each year"
            else:
                assumption_text = (
                    f"glide from {mc_glide_path[0]*100:.0f}% equity to {mc_glide_path[1]*100:.0f}% over "
                    f"{mc_years} yrs; portfolio mean/sigma blended from equity (5.5%/18%) and bonds (1.5%/6%)"
                )
            st.caption(
                f"1,000 simulations · {assumption_text} · random seed fixed for reproducibility. "
                "Real markets show mean reversion and fat tails — treat as a planning aid, not a forecast."
            )



with tab_tax:
    # ── UK tax wrapper utilisation tracker ────────────────────────────────────────

    if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
        with st.expander("UK tax wrapper utilisation (ISA · LISA · Pension)"):
            st.caption(
                "Track how much of each year's UK tax-advantaged wrapper allowance you're using. "
                "Pension annual allowance includes 3-year carryforward of unused capacity. "
                "**Allowances as of 2025/26.** Indicative — not tax advice."
            )
            st.caption(
                "📅 From **6 April 2027** the cash-ISA limit drops to **£12,000/yr** for under-65s "
                "(within the unchanged £20,000 overall ISA allowance); over-65s keep the full "
                "£20,000 in cash."
            )

            # Allowance constants imported from utils/uk_tax.py (tested in test_uk_tax.py).
            # Aliased here so the existing UI code reads naturally.
            TAPER_THRESHOLD_INCOME = TAPER_THRESHOLD

            tw_col1, tw_col2, tw_col3 = st.columns(3)
            with tw_col1:
                tw_isa = st.number_input(
                    "ISA contributed this year (£)", 0, 20_000, 0, 500, format="%d", key="tw_isa",
                    help="Cash, S&S, Innovative Finance and LISA combined — max £20k.",
                )
            with tw_col2:
                tw_lisa = st.number_input(
                    "Of which LISA (£)", 0, 4_000, 0, 500, format="%d", key="tw_lisa",
                    help="LISA: max £4,000/yr, counts against ISA allowance. Only available "
                         "if you're 18-50 and opened before age 40. Government 25% bonus.",
                )
                # The 40-50 gap: you can only contribute if you already have a LISA.
                # Default to True (permissive) when age is below 40 or above 50 since
                # the answer is determined by age alone in those bands.
                _show_has_lisa = (latest_age is not None and 40 <= latest_age <= 50)
                tw_has_lisa = st.checkbox(
                    "I already have an open LISA",
                    value=True,
                    key="tw_has_lisa",
                    help="LISA contributions between age 40 and 50 are only allowed if you "
                         "opened a LISA before age 40. Untick if you don't already have one.",
                    disabled=not _show_has_lisa,
                ) if _show_has_lisa else True
            with tw_col3:
                tw_pension = st.number_input(
                    "Pension contributions this year (£)", 0, 200_000, 0, 1_000,
                    format="%d", key="tw_pension",
                    help="All gross pension contributions across employer + personal pensions, "
                         "salary sacrifice, and tax-relievable personal contributions.",
                )

            # ── High-earner taper inputs ──────────────────────────────────────────
            st.markdown("**Pension taper** (for high earners)")
            tp_cols = st.columns([2, 1])
            with tp_cols[0]:
                tw_adjusted_income = st.number_input(
                    "Adjusted income (£/yr)", 0, 2_000_000, 0, 5_000,
                    format="%d", key="tw_adjusted_income",
                    help="UK 'adjusted income' is broadly taxable income + employer pension contributions. "
                         f"For income over £{TAPER_THRESHOLD_INCOME:,}, the £{PENSION_AA:,} annual allowance "
                         "reduces by £1 for every £2 over the threshold, floored at £10,000.",
                )
            # Compute tapered AA via the unit-tested helper
            tapered_aa, taper_reduction = tapered_pension_allowance(tw_adjusted_income)
            with tp_cols[1]:
                if taper_reduction > 0:
                    st.metric(
                        "Tapered AA",
                        f"£{tapered_aa:,.0f}",
                        delta=f"-£{taper_reduction:,.0f}",
                        delta_color="inverse",
                        help=f"Reduced from £{PENSION_AA:,} due to adjusted income above £{TAPER_THRESHOLD_INCOME:,}.",
                    )
                else:
                    st.metric("Tapered AA", f"£{PENSION_AA:,}", delta="No taper applied")

            st.markdown("**Pension carryforward** (use unused allowance from the previous 3 years)")
            cf_cols = st.columns(3)
            with cf_cols[0]:
                cf_3 = st.number_input("Unused 3 years ago (£)", 0, 60_000, 0, 1_000,
                                       format="%d", key="cf_3")
            with cf_cols[1]:
                cf_2 = st.number_input("Unused 2 years ago (£)", 0, 60_000, 0, 1_000,
                                       format="%d", key="cf_2")
            with cf_cols[2]:
                cf_1 = st.number_input("Unused 1 year ago (£)", 0, 60_000, 0, 1_000,
                                       format="%d", key="cf_1")
            carryforward = cf_1 + cf_2 + cf_3
            # Use tapered_aa for this year, full PENSION_AA for carryforward calculation
            # (carryforward years use that year's allowance — user can input what they had)
            effective_pension_allowance = tapered_aa + carryforward

            # Calculations — use the tested utility functions
            isa_rem     = isa_remaining(tw_isa)
            lisa_rem    = lisa_remaining(
                tw_lisa,
                age=int(latest_age) if latest_age is not None else None,
                has_existing_lisa=tw_has_lisa,
            )
            pension_rem = max(0.0, effective_pension_allowance - tw_pension)

            # LISA contribution rules at the user's age
            lisa_closed_over_50 = latest_age is not None and latest_age > 50
            lisa_blocked_no_existing = (
                latest_age is not None and 40 <= latest_age <= 50 and not tw_has_lisa
            )
            if lisa_closed_over_50 and tw_lisa > 0:
                st.warning(
                    f"You're over 50, so LISA contributions are no longer allowed. "
                    f"Existing LISA balances continue to grow, but new pay-ins stopped at 50.",
                    icon="⚠️",
                )
            elif lisa_blocked_no_existing and tw_lisa > 0:
                st.warning(
                    f"At age {int(latest_age)}, you can only contribute to a LISA if you "
                    f"already had one open (you can't open a new one after 39). The £"
                    f"{tw_lisa:,} you entered won't be eligible for the 25% bonus.",
                    icon="⚠️",
                )

            isa_pct     = tw_isa / ISA_ALLOWANCE * 100
            lisa_pct    = tw_lisa / LISA_ALLOWANCE * 100
            pension_pct = tw_pension / max(effective_pension_allowance, 1) * 100

            # Headline metrics
            st.markdown("")
            st.markdown("**Utilisation this year**")
            u_col1, u_col2, u_col3 = st.columns(3)
            with u_col1:
                st.metric(
                    "ISA",
                    f"{isa_pct:.0f}%",
                    delta=f"£{tw_isa:,} / £{ISA_ALLOWANCE:,}",
                    delta_color="off",
                    help=f"£{isa_rem:,.0f} remaining before 5 April.",
                )
                st.progress(min(tw_isa / ISA_ALLOWANCE, 1.0))
            with u_col2:
                st.metric(
                    "LISA (of ISA)",
                    f"{lisa_pct:.0f}%",
                    delta=f"£{tw_lisa:,} / £{LISA_ALLOWANCE:,}",
                    delta_color="off",
                    help=f"£{lisa_rem:,.0f} remaining. Government tops up 25% (up to £1k/yr).",
                )
                st.progress(min(tw_lisa / LISA_ALLOWANCE, 1.0))
            with u_col3:
                st.metric(
                    "Pension",
                    f"{pension_pct:.0f}%",
                    delta=f"£{tw_pension:,} / £{effective_pension_allowance:,.0f}",
                    delta_color="off",
                    help=f"£{pension_rem:,.0f} remaining (includes £{carryforward:,} carryforward).",
                )
                st.progress(min(tw_pension / max(effective_pension_allowance, 1), 1.0))

            # Smart recommendation banner — uses the tested pension_relief_estimate helper
            recs = []
            if pension_rem >= 5_000:
                relief_higher = pension_relief_estimate(pension_rem, 0.40)
                relief_basic  = pension_relief_estimate(pension_rem, 0.20)
                recs.append(
                    f"£{pension_rem:,.0f} pension headroom — adding it could save "
                    f"up to £{relief_higher:,.0f} in tax relief at 40% "
                    f"(or £{relief_basic:,.0f} at basic rate)."
                )
            if isa_rem >= 1_000:
                recs.append(
                    f"£{isa_rem:,.0f} ISA headroom — sheltered from CGT and dividend tax. "
                    f"Use it or lose it (no carryforward)."
                )
            if 0 < tw_lisa < LISA_ALLOWANCE:
                bonus_remaining = lisa_bonus(lisa_rem)
                recs.append(
                    f"£{lisa_rem:,.0f} LISA headroom — government adds 25% on top "
                    f"(up to £{bonus_remaining:,.0f} this year)."
                )

            if recs:
                st.info("**Suggestions:**\n\n" + "\n\n".join(f"- {r}" for r in recs), icon="💡")
            elif tw_isa > 0 or tw_pension > 0 or tw_lisa > 0:
                st.success(
                    "You've used all your immediate wrapper allowances for this tax year. "
                    "Consider building up carryforward for next year if you're earning above £60k.",
                    icon="✅",
                )

            # Summary table
            st.markdown("**Annual allowance reference (2025/26)**")
            pension_aa_note = (
                f"Tapered to £{tapered_aa:,.0f} at adjusted income £{tw_adjusted_income:,}"
                if taper_reduction > 0
                else f"Standard £{PENSION_AA:,} (no taper at £{tw_adjusted_income:,} adjusted income)"
            )
            ref = pd.DataFrame({
                "Wrapper": ["ISA (total)", "  └─ Lifetime ISA", "Pension AA",
                            "Pension AA + carryforward"],
                "2025/26 limit": [
                    f"£{ISA_ALLOWANCE:,}",
                    f"£{LISA_ALLOWANCE:,}",
                    f"£{tapered_aa:,.0f}",
                    f"£{effective_pension_allowance:,.0f}",
                ],
                "Notes": [
                    "Cash + S&S + IF + LISA combined",
                    "Max age 50; 25% government bonus",
                    pension_aa_note,
                    f"Includes £{carryforward:,} from prior 3 yrs",
                ],
            })
            st.dataframe(ref, use_container_width=True, hide_index=True)



    # ── IHT / estate tax calculator ───────────────────────────────────────────────

    if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
        with st.expander("Estate / inheritance tax (IHT) exposure"):
            st.caption(
                "Estimates your approximate UK inheritance tax (IHT) liability based on your current "
                "net worth. Indicative only — not tax advice. Rules as of 2025/26 "
                "(nil-rate bands frozen until April 2030)."
            )
            iht_cols = st.columns(3)
            with iht_cols[0]:
                iht_threshold = st.selectbox(
                    "NRB threshold",
                    [
                        "Single — £325k NRB",
                        "Single + RNRB — £500k (residence to descendants)",
                        "Married / civil partner — £650k (2× NRB, no RNRB)",
                        "Married + RNRB — £1m (2× NRB + 2× RNRB)",
                    ],
                    help="Nil-rate band (NRB): £325k per person. "
                         "Residence nil-rate band (RNRB): up to £175k extra if leaving a main residence to direct descendants. "
                         "Spouse exemption allows unused NRB to transfer on first death.",
                    key="iht_threshold",
                )
            with iht_cols[1]:
                iht_deductions = st.number_input(
                    "Additional deductions (£)",
                    min_value=0, max_value=5_000_000, value=0, step=10_000, format="%d",
                    help="Business property relief, agricultural relief, charitable gifts, outstanding debts, "
                         "or any other amounts that reduce the taxable estate.",
                    key="iht_deductions",
                )
            with iht_cols[2]:
                iht_rate_pct = st.number_input(
                    "Rate (%)", min_value=0, max_value=40, value=40, step=1, format="%d",
                    help="Standard rate: 40%. Reduced to 36% if 10%+ of net estate is left to charity.",
                    key="iht_rate",
                )

            # Map UI labels to scenario keys for the tested utility
            _iht_band = {
                "Single — £325k NRB":                                    IHT_BANDS["single"],
                "Single + RNRB — £500k (residence to descendants)":      IHT_BANDS["single_with_rnrb"],
                "Married / civil partner — £650k (2× NRB, no RNRB)":     IHT_BANDS["married"],
                "Married + RNRB — £1m (2× NRB + 2× RNRB)":               IHT_BANDS["married_with_rnrb"],
            }[iht_threshold]

            # If a married threshold is selected AND partner data is loaded, offer to
            # use the combined household estate. The married thresholds (£650k or £1m)
            # are the COMBINED exemption, so applying them to just one spouse's wealth
            # would understate the available headroom.
            _is_married_threshold = "Married" in iht_threshold
            _has_partner = partner_plot_df is not None and len(partner_plot_df) > 0
            gross_estate = latest_nw
            if _is_married_threshold and _has_partner:
                _partner_latest_nw = float(partner_plot_df.sort_values("age").iloc[-1]["net_worth"])
                _use_combined = st.checkbox(
                    f"Use combined household estate ({_fmt(latest_nw)} + {_fmt(_partner_latest_nw)} = "
                    f"{_fmt(latest_nw + _partner_latest_nw)})",
                    value=True, key="iht_use_combined",
                    help=(
                        "The £650k/£1m married thresholds apply to the COMBINED estate at the "
                        "second death (the first spouse passes everything to the second tax-free, "
                        "and unused NRB transfers). So the right comparison is your joint estate, "
                        "not just yours."
                    ),
                )
                if _use_combined:
                    gross_estate = latest_nw + _partner_latest_nw

            exempt_amount = _iht_band + iht_deductions
            # Use the tested utility — same math, but now centralised + tested
            taxable_estate, iht_due, after_iht = iht_payable(
                gross_estate, threshold=_iht_band, deductions=iht_deductions,
                rate=iht_rate_pct / 100,
            )
            pct_lost = iht_due / gross_estate * 100 if gross_estate > 0 else 0

            iht_m1, iht_m2, iht_m3, iht_m4 = st.columns(4)
            with iht_m1:
                st.metric("Gross estate", _fmt(gross_estate))
            with iht_m2:
                st.metric("IHT-exempt", _fmt(exempt_amount),
                          help=f"Threshold ({_fmt(_iht_band)}) + deductions ({_fmt(iht_deductions)})")
            with iht_m3:
                st.metric("IHT payable", _fmt(iht_due),
                          help=f"{_fmt(taxable_estate)} taxable @ {iht_rate_pct}%")
            with iht_m4:
                st.metric("After-IHT estate", _fmt(after_iht),
                          delta=f"−{pct_lost:.1f}% of estate",
                          delta_color="inverse",
                          help="Net amount heirs would receive (excluding admin costs, probate fees, etc.)")

            if taxable_estate == 0:
                st.success("Your estate is within the IHT threshold - no IHT payable under this scenario.")
            else:
                st.caption(
                    f"Taxable estate: {_fmt(taxable_estate)} (estate above threshold). "
                    f"Possible mitigation: gifts out of income, seven-year gifting rules, "
                    f"life insurance in trust, charitable giving."
                )
                st.caption(
                    "⚠️ From **6 April 2027** most unused pension funds fall **inside** the estate "
                    "for IHT (transfers to a spouse or charity stay exempt) — pensions will no "
                    "longer sit outside it."
                )
            st.caption(
                "Simplified estimate — does not account for taper relief, business/agricultural property relief, "
                "in-trust assets, lifetime gifts, or other exemptions. Consult a qualified advisor."
            )


with tab_share:
    # ── Share / export your data ──────────────────────────────────────────────────

    if personal_plot_df is not None and len(personal_plot_df) > 0:
        with st.expander("Share / export your data"):
            # Two columns: shareable URL on the left, CSV download on the right
            share_col1, share_col2 = st.columns([3, 2])

            with share_col1:
                st.markdown("**Shareable link**")
                try:
                    token = encode_personal_data(personal_plot_df)
                    share_url = f"{PUBLIC_APP_URL}/?d={token}"
                    # If partner data is loaded, encode it under ?p= so the receiving
                    # browser picks it up as the partner pane.
                    if partner_plot_df is not None and len(partner_plot_df) > 0:
                        p_token = encode_personal_data(partner_plot_df)
                        share_url = f"{share_url}&p={p_token}"
                    st.text_input(
                        "Data is encoded in the URL — nothing is stored on any server:",
                        value=share_url, key="share_url_box",
                    )
                    _share_note = (
                        "Anyone with this link sees your figures"
                        + (" plus your partner's" if partner_plot_df is not None
                           and len(partner_plot_df) > 0 else "")
                        + ". Share only with people you trust."
                    )
                    st.caption(_share_note)
                except Exception:
                    st.info("Share link unavailable — data may be too large to encode.")

            with share_col2:
                st.markdown("**Download as CSV**")
                _export_cols = ["year", "age", "net_worth"] + [
                    c for c in ("liabilities", "note") if c in personal_plot_df.columns]
                export_df = personal_plot_df[_export_cols].copy()
                csv_bytes = export_df.to_csv(index=False).encode("utf-8")
                from datetime import datetime as _dt
                fname = f"my_net_worth_{_dt.now():%Y-%m-%d}.csv"
                st.download_button(
                    "Download my net worth history",
                    csv_bytes, fname, "text/csv",
                    use_container_width=True,
                    help="Save what you've entered (manual entries or merged CSV) "
                         "for backup or to re-upload later.",
                )
                if partner_plot_df is not None and len(partner_plot_df) > 0:
                    _p_cols = ["year", "age", "net_worth"] + [
                        c for c in ("liabilities", "note") if c in partner_plot_df.columns]
                    p_export = partner_plot_df[_p_cols].copy()
                    p_csv = p_export.to_csv(index=False).encode("utf-8")
                    p_fname = f"partner_net_worth_{_dt.now():%Y-%m-%d}.csv"
                    st.download_button(
                        "Download partner's history",
                        p_csv, p_fname, "text/csv",
                        use_container_width=True,
                    )



# ── Methodology panel ─────────────────────────────────────────────────────────

with st.expander("Methodology and data sources", expanded=False):
    st.markdown(f"""
### Data source

**ONS Wealth and Assets Survey (WAS), Wave 8 (April 2020 – March 2022)**, Great Britain.

**Median (P50) values by age band** are the actual ONS published figures from
[Total wealth in Great Britain, April 2020 to March 2022](https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/bulletins/totalwealthingreatbritain/april2020tomarch2022),
Figure 2. The 25th and 75th percentiles by age band are not directly published; they
are derived by applying age-specific IQR ratios (P25/P50 and P75/P50) to the ONS
median. The ratios reflect typical UK wealth dispersion shape — narrower in young/old
age bands, wider in middle age.

**Whole-population** P25/P50/P75 are also published (Table 2.4): Wave 8 P25 £70,500,
P50 £293,700, P75 £662,100 — these are inside the range of our by-age figures,
which gives confidence in the IQR-ratio approach.

---

### Age interpolation

PCHIP monotone spline from band midpoints (ages 20,30,40,50,60,70,80) to single years.
Published points marked with filled circle markers on the household chart.

### Exact percentile

Log-normal distribution fitted to P25/P50/P75 per age: `mu = log(P50)`,
`sigma = (log(P75)−log(P25)) / 1.349`. CDF evaluated at user's net worth.
Indicative ±5–10 percentile points. The percentile trajectory applies this to every personal data point.

### Household → individual

Age-specific sharing factors from ONS household composition data × WAS pension-share tables.
Pension wealth is not divided (already individual in WAS). Non-pension halved for couple households.
**±15–20% uncertainty.** All individual output is flagged derived.

### Real / nominal

Nominal = {DATA_YEAR} prices. Real = CPI-adjusted to {REAL_BASE_YEAR} using ONS CPI (2015=100).
Personal entries are each adjusted from their recorded year.

### Asset class breakdown

Component shares (property/pension/financial/physical) use the Wave 7 age-band shape
rescaled so the population-weighted aggregate matches the **ONS Wave 8 published
aggregate** (property 40%, pension 35%, financial 14%, physical 10%). Values are
PCHIP-interpolated to single years, each row renormalised to 100%, then multiplied
by the P50 benchmark to give £ values per component.

This is a derived series — not a published WAS age-band component table — but it is
now anchored to the real Wave 8 aggregate at the population level.

### P10 / P90

Derived from the same log-normal model: `value = exp(mu + z×sigma)` where z = Phi⁻¹(0.10/0.90).

### UK tax wrapper utilisation

Tracks your contributions this tax year against:
- **ISA total allowance** £20,000 (2025/26) — cash, S&S, Innovative Finance and LISA combined.
- **Lifetime ISA** £4,000 — counts inside the ISA total; 25% government bonus added on top.
  LISA contribution eligibility by age is modelled: under-18s and over-50s blocked,
  and between 40-50 a checkbox asks whether you already have a LISA open (you can't
  open a new one after 39).
- **Pension Annual Allowance** £60,000 — plus carryforward from unused allowance in the
  previous 3 tax years. The high-earner taper IS modelled: for adjusted income above
  £260,000, the AA reduces by £1 for every £2 over the threshold, floored at £10,000
  (reached at £360,000 adjusted income).

Progress bars and headroom show how much you have left to contribute before 5 April.
Smart suggestions appear when headroom × marginal tax relief is material (>£1k pension,
>£0 ISA/LISA). Indicative only — pension recycling rules, salary sacrifice mechanics,
and many other details are not modelled.

### Monte Carlo projection (stochastic returns)

The deterministic what-if uses a fixed CAGR; Monte Carlo replaces that with
**1,000 simulations of random annual returns** to expose sequence-of-returns risk.

**Two modes:**

1. **Fixed return assumption** — each year's return drawn from `N(μ, σ)` where the
   user supplies μ (expected return) and σ (volatility). All years use the same
   distribution.

2. **Equity/bond glide path** — each year uses a portfolio mean/sigma derived from
   a linear glide between two equity weights. Real asset-class assumptions:
    - Equity: μ = 5.5% real, σ = 18%
    - Bonds:  μ = 1.5% real, σ = 6%
    - Equity-bond correlation: 0.10

   Portfolio variance includes the covariance term, so the resulting
   sigma is below the weighted average for any mixed allocation. Allows
   modelling "de-risk over time" (e.g. 100% equity at 30 → 60/40 at 65).

**Outputs:** P10/P50/P90 of net worth at the target age, plus the probability
of finishing at or above any chosen target (computed empirically from the
simulation paths, not a closed-form formula).

**Random seed is fixed at 42** so the same input sliders give the same
result — important for UX (sliders don't jitter the chart on rerun).

**Caveats** — returns are assumed normally distributed and independent
year-to-year. Real markets exhibit mean reversion, fat tails, and bursts of
correlated bad years. Treat as a planning aid, not a forecast.

### ISA / accessible-wealth bridge

For UK early-retirement planners: private pension access is locked until age 57
(rising to 58 in 2028, then tracking 10 years below the state pension age).
Anyone retiring earlier needs **accessible wealth** (ISA, GIA, savings — not
pension) to bridge the gap.

The calculator computes the bridge fund needed two ways:

1. **Conservative** = bridge_years × annual_spend
   Assumes no growth on the bridge fund — it just gets drawn down to zero.

2. **4% real** = annual_spend × ((1 − (1.04)^−n) / 0.04)
   PV-of-annuity at 4% real return. The bridge fund earns while being drawn,
   so a smaller pot suffices.

Where `n` = bridge years (pension access age − FIRE age).

If personal CAGR is available, the calculator also projects when you'd reach
the bridge target at your current growth rate, and compares against your
chosen FIRE age — green if you'd hit it with buffer, amber if you'd be late.

The forecast now also sizes a **second leg** from pension-access age to state
pension age (where the state pension starts to reduce your annual need), reusing
the same 4% PV-of-annuity factor, and shows the two legs combined.

**Caveat.** Does not verify that your leg-1 wealth is actually held in accessible
wrappers (ISA / GIA, not pension) — that's on you to check.

### Retirement income forecast

Projects your net worth to your chosen retirement age using a configurable real
return (default 4%), splits the result into pension wrappers vs other wealth using
your asset composition, then estimates annual income from three sources:

- **Pension annuity** = the 75% of the pension pot left after the 25% tax-free
  lump sum (PCLS, capped at the £268,275 Lump Sum Allowance) × annuity rate
  (≈6.5% at 65, single-life level gilt-linked). Drawdown can be more flexible —
  this is a conservative income proxy.
- **4% drawdown** from non-pension wealth (ISAs, GIAs, property-equivalent).
  Follows the Trinity Study 4% rule for a 30-year horizon. Assumed tax-free.
- **State pension** included from age 67 (post-2028 cohort); your input figure.

The forecast shows the **25% tax-free lump sum** separately, then a **net annual
income** after rUK 2025/26 income tax on the taxable part (annuity + state
pension); the target comparison uses the net figure. (England/Wales/NI rates —
Scotland differs; the 4% ISA draw is treated as tax-free.)

### Retirement drawdown — pot longevity

Simulates spending down a retirement pot year-by-year. Starts with a chosen pot
size, grows it at the real return, subtracts annual withdrawal (inflation-adjusted
because we work in real terms), and reports the depletion age. Compares against
ONS cohort life expectancy at the retirement age. Includes a sensitivity table
showing how the depletion age changes at real returns from 1% to 6%.

**Stochastic stress test:** Below the deterministic chart, the same setup runs
1,000 simulations with random year-to-year returns (configurable volatility).
This explicitly models sequence-of-returns risk — a bad first decade is much
worse than a bad last decade, even with the same long-run average. The output
shows the probability the pot survives to each age. **Aim for ≥85% probability
of survival** at your planning horizon for a comfortable cushion.

### Privacy

All personal data lives in browser session state or URL query params only.
No data is transmitted to or stored on any server.

### Regional variation — the Region filter

Wealth varies substantially by region. Use the **Region** selector in the sidebar to
scale the benchmark to a region's median household total wealth. The figures are ONS
WAS Wave 8 (April 2020 to March 2022) regional medians — South East and North East
match the ONS bulletin's headline numbers exactly, which cross-checks the full set:

| Region | Median household total wealth | vs GB median |
|---|---|---|
| South East | £489,800 | +67% |
| East of England | £400,700 | +36% |
| South West | £347,700 | +18% |
| Great Britain | £293,700 | — |
| Wales | £266,900 | −9% |
| East Midlands | £261,000 | −11% |
| West Midlands | £260,800 | −11% |
| Yorkshire and The Humber | £245,600 | −16% |
| London | £244,800 | −17% |
| Scotland | £239,500 | −18% |
| North West | £222,400 | −24% |
| North East | £179,900 | −39% |

Counter-intuitively, **London's median sits *below* the GB median** — high house prices
don't make the typical household wealthy when over half of London households rent and the
population skews younger (its *mean* is the highest in the country, pulled up by a wealthy
tail; the *median* household is not). ONS also flags extra uncertainty on the Round 8
London estimate (pandemic non-response).

**How the filter works (and its limit).** ONS publishes regional medians but *not* regional
medians **by age**, so the filter applies a single multiplicative factor (region median ÷
GB median) uniformly across the whole age-curve. That re-levels the benchmark to the region
while preserving the P25/P50/P75 shape, but it's a first-order approximation — real regional
premiums vary with age (typically larger for older homeowners). Treat a region-adjusted
percentile as indicative.

### Known limitations

- WAS excludes Northern Ireland; figures = Great Britain only.
- Very wealthy households (~top 1–2%) are under-represented; P75 is reliable, above P90 less so.
- Wave 8 (2020–2022) predates 2023–2026 inflation/house-price movements; real-terms adjustment is partial.
- Wave 8 is the latest published wave, but the UK statistics regulator has flagged data-quality
  caveats on recent WAS rounds — treat it as the best available source rather than a certified
  gold standard, and read single-year movements with care.
- 75+ band uses age-80 midpoint — a modelling assumption over a wide age range.
- What-if and FIRE projections are illustrative only. Not financial advice.
""")

# ── Report export ─────────────────────────────────────────────────────────────

if personal_plot_df is not None and latest_nw is not None:
    import datetime as _dt, io as _io

    _today     = _dt.date.today().isoformat()
    _price_lbl = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal {DATA_YEAR} prices"
    _s_rpt     = personal_plot_df.sort_values("age")
    _first_rpt = _s_rpt.iloc[0]
    _asp_rpt   = float(_s_rpt.iloc[-1]["age"]) - float(_first_rpt["age"])
    _fnw_rpt   = float(_first_rpt["net_worth"])
    _cagr_rpt  = _safe_cagr(_fnw_rpt, latest_nw, _asp_rpt)
    _pct_rpt   = estimate_exact_percentile(latest_nw, round(latest_age), benchmark)

    # PDF benchmark table promises P10/P90 derived values; ensure they're present
    # regardless of whether the user toggled show_tails.
    _benchmark_with_tails = pd.concat([benchmark, derive_tail_percentiles(benchmark)],
                                       ignore_index=True)
    _ab_rpt    = _benchmark_with_tails[_benchmark_with_tails["age"] == min(round(latest_age), 85)]

    def _bm(p):
        r = _ab_rpt[_ab_rpt["percentile"] == p]
        return float(r["value"].iloc[0]) if len(r) else None

    # ── PDF generator ──────────────────────────────────────────────────────────
    def _generate_pdf() -> bytes:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos  # for replacing the deprecated new_x=XPos.LMARGIN, new_y=YPos.NEXT kwarg

        BLUE  = (29, 78, 216)
        SLATE = (30, 41, 59)
        GREY  = (100, 116, 139)
        LBLUE = (219, 234, 254)
        LGREY = (248, 250, 252)

        # Render charts to PNG using matplotlib (no browser/kaleido required)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt
        import matplotlib.ticker as _mtick

        _PC = COLOURS["person"]

        def _gbp(x, _):
            if abs(x) >= 1_000_000: return f"£{x/1_000_000:.1f}m"
            if abs(x) >= 1_000:     return f"£{x/1_000:.0f}k"
            return f"£{int(x)}"

        def _save(fig):
            buf = _io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
            _plt.close(fig)
            buf.seek(0)
            return buf.read()

        def _mpl_benchmark():
            try:
                p25 = benchmark[benchmark["percentile"]=="p25"].sort_values("age")
                p50 = benchmark[benchmark["percentile"]=="p50"].sort_values("age")
                p75 = benchmark[benchmark["percentile"]=="p75"].sort_values("age")
                fig, ax = _plt.subplots(figsize=(11, 4.2))
                ax.fill_between(p25["age"], p25["value"], p75["value"],
                                alpha=0.15, color="#93c5fd", label="P25-P75 range")
                ax.plot(p25["age"], p25["value"], "#93c5fd", lw=1.4, ls="--", label="P25")
                ax.plot(p50["age"], p50["value"], "#1d4ed8", lw=2.5,            label="Median")
                ax.plot(p75["age"], p75["value"], "#93c5fd", lw=1.4, ls="--", label="P75")
                ax.plot(_s_rpt["age"], _s_rpt["net_worth"],
                        _PC, lw=2, marker="o", ms=5, label="You")
                ax.yaxis.set_major_formatter(_mtick.FuncFormatter(_gbp))
                ax.set_xlabel("Age"); ax.set_ylabel(f"Net worth ({_price_lbl})")
                ax.set_xlim(age_min - 0.5, age_max + 0.5)
                ax.legend(fontsize=8); ax.grid(True, alpha=0.25)
                ax.set_title("Net worth vs UK distribution (ONS WAS Wave 8)", fontsize=11)
                fig.tight_layout(); return _save(fig)
            except Exception:
                return None

        def _mpl_trajectory(traj):
            try:
                fig, ax = _plt.subplots(figsize=(11, 3.8))
                for pct, lbl in [(25, "P25"), (50, "Median"), (75, "P75")]:
                    ax.axhline(pct, color="#93c5fd", lw=0.8, ls=":")
                    ax.text(float(traj["age"].iloc[0]), pct + 0.8, lbl,
                            fontsize=7.5, color=AXIS_LABEL_COLOUR)
                ax.fill_between(traj["age"], traj["percentile"], alpha=0.12, color=_PC)
                ax.plot(traj["age"], traj["percentile"], _PC, lw=2, marker="o", ms=5)
                ax.set_ylim(0, 100); ax.set_xlabel("Age")
                ax.set_ylabel("Estimated percentile")
                ax.grid(True, alpha=0.25)
                ax.set_title("Percentile trajectory", fontsize=11)
                fig.tight_layout(); return _save(fig)
            except Exception:
                return None

        # Annual aggregation: collapse to one row per year when data spans
        # 2+ years with multiple rows per year. Single-year monthly data
        # falls through to raw rows so the gains chart and summary stats
        # aren't silently empty (matches the in-app gains/velocity/summary
        # behaviour after the same fix).
        if ("year" in _s_rpt.columns
                and _s_rpt["year"].nunique() > 1
                and len(_s_rpt) > _s_rpt["year"].nunique()):
            _s_ann = (_s_rpt.sort_values("age")
                       .groupby("year", as_index=False).last()
                       .sort_values("year"))
        else:
            _s_ann = _s_rpt

        def _mpl_gains():
            try:
                s = _s_ann
                if len(s) < 2: return None
                gains  = s["net_worth"].diff().dropna().values
                # Year axis only when there's exactly one row per year
                # (either natively or after aggregation). For single-year
                # monthly fallback, use age — otherwise 11 bars would
                # stack at the same year tick.
                one_per_year = ("year" in s.columns
                                and len(s) == s["year"].nunique())
                if one_per_year:
                    x_vals = s["year"].iloc[1:].astype(int).values
                    x_label = "Year"
                    title = "Year-on-year net worth change  (blue = gain, red = loss)"
                else:
                    x_vals = s["age"].iloc[1:].values
                    x_label = "Age"
                    title = "Net worth change per period  (blue = gain, red = loss)"
                colors = ["#1d4ed8" if g >= 0 else "#ef4444" for g in gains]
                fig, ax = _plt.subplots(figsize=(11, 3.5))
                ax.bar(x_vals, gains, color=colors, width=0.6)
                ax.axhline(0, color="black", lw=0.5)
                ax.yaxis.set_major_formatter(_mtick.FuncFormatter(_gbp))
                ax.set_xlabel(x_label); ax.set_ylabel("Change")
                ax.grid(True, alpha=0.25, axis="y")
                ax.set_title(title, fontsize=11)
                fig.tight_layout(); return _save(fig)
            except Exception:
                return None

        def _mpl_whatif():
            try:
                _la  = float(_s_rpt.iloc[-1]["age"])
                _lnw = float(_s_rpt.iloc[-1]["net_worth"])
                proj_ages = list(range(int(_la), wi_age + 1))
                sc_def = [(wi_cagr1/100, f"S1 {wi_cagr1:+.1f}%"),
                          (wi_cagr2/100, f"S2 {wi_cagr2:+.1f}%"),
                          (wi_cagr3/100, f"S3 {wi_cagr3:+.1f}%")]
                ann = wi_monthly * 12
                fig, ax = _plt.subplots(figsize=(11, 4))
                p50 = benchmark[benchmark["percentile"]=="p50"].sort_values("age")
                ax.plot(p50["age"], p50["value"], "#1d4ed8", lw=1.5, ls="--",
                        alpha=0.5, label="Benchmark median")
                ax.plot(_s_rpt["age"], _s_rpt["net_worth"],
                        _PC, lw=2, marker="o", ms=4, label="Actual")
                for i, (cagr, lbl) in enumerate(sc_def):
                    proj = []
                    for a in proj_ages:
                        t = a - _la
                        if abs(cagr) < 1e-10:
                            proj.append(_lnw + ann * t)
                        else:
                            proj.append(_lnw*(1+cagr)**t + ann*((1+cagr)**t - 1)/cagr)
                    ax.plot(proj_ages, proj, ["#f97316","#8b5cf6","#06b6d4"][i],
                            lw=2, ls=("solid" if i==0 else "dashed"), label=lbl)
                ax.yaxis.set_major_formatter(_mtick.FuncFormatter(_gbp))
                ax.set_xlabel("Age"); ax.set_ylabel(f"Net worth ({_price_lbl})")
                ax.legend(fontsize=8); ax.grid(True, alpha=0.25)
                ax.set_title("What-if projection", fontsize=11)
                fig.tight_layout(); return _save(fig)
            except Exception:
                return None

        def _mpl_monte_carlo():
            """
            Static PNG of the Monte Carlo projection — P10/P25/P50/P75/P90 bands
            across time, plus optional target line. Returns None if mc_paths
            isn't in scope (no personal data) or rendering fails.
            """
            try:
                _paths = mc_paths  # NameError if MC section didn't run
                _start = float(latest_age or 30)
                _ages = list(range(int(_start), int(_start) + _paths.shape[1]))

                p10 = np.percentile(_paths, 10, axis=0)
                p25 = np.percentile(_paths, 25, axis=0)
                p50 = np.percentile(_paths, 50, axis=0)
                p75 = np.percentile(_paths, 75, axis=0)
                p90 = np.percentile(_paths, 90, axis=0)

                fig, ax = _plt.subplots(figsize=(11, 4))
                # Outer band 10-90
                ax.fill_between(_ages, p10, p90, color="#dbeafe", alpha=0.7,
                                label="10th-90th percentile")
                # Inner band 25-75
                ax.fill_between(_ages, p25, p75, color="#93c5fd", alpha=0.7,
                                label="25th-75th percentile")
                # Median line
                ax.plot(_ages, p50, color="#1d4ed8", lw=2.5, label="Median outcome")

                # Target line if set
                if mc_target_nw and mc_target_nw > 0:
                    ax.axhline(mc_target_nw, color=_PC, lw=1.5, ls="--",
                               label=f"Target {_fmt(mc_target_nw)}")

                ax.yaxis.set_major_formatter(_mtick.FuncFormatter(_gbp))
                ax.set_xlabel("Age")
                ax.set_ylabel(f"Net worth ({_price_lbl})")
                ax.legend(fontsize=8, loc="upper left")
                ax.grid(True, alpha=0.25)
                ax.set_title("Monte Carlo projection - 1,000 simulations", fontsize=11)
                fig.tight_layout()
                return _save(fig)
            except Exception:
                return None

        main_png  = _mpl_benchmark()
        traj_png  = None
        if len(_s_rpt) >= 2:
            _ty = build_percentile_trajectory(personal_plot_df, benchmark)
            if len(_ty) >= 2:
                traj_png = _mpl_trajectory(_ty)
        gains_png  = _mpl_gains() if len(_s_rpt) >= 2 else None
        whatif_png = _mpl_whatif()
        mc_png     = _mpl_monte_carlo()

        # ── PDF helpers & layout ───────────────────────────────────────────────
        def _ordinal(n: int) -> str:
            n = int(n)
            if 11 <= (n % 100) <= 13:
                return f"{n}th"
            return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

        _ftxt = (
            f"UK Net Worth Benchmarker  |  ONS WAS Wave 8 (2020-2022)  |  "
            f"Not financial advice  |  {_today}"
        )

        # Subclass so fpdf2 calls footer() automatically on each page close
        class _PDF(FPDF):
            def footer(self):
                self.set_y(-14)
                self.set_font("Helvetica", "I", 7)
                self.set_text_color(*GREY)
                self.cell(148, 5, _ftxt)
                self.cell(0, 5, f"Page {self.page_no()}", align="R")

        pdf = _PDF()
        pdf.set_margins(15, 15, 15)
        pdf.set_auto_page_break(auto=True, margin=20)

        def H1(txt):
            pdf.set_font("Helvetica", "B", 14); pdf.set_text_color(*BLUE)
            pdf.cell(0, 9, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            y0 = pdf.get_y()
            pdf.set_draw_color(*BLUE); pdf.line(15, y0, 195, y0)
            pdf.set_draw_color(0, 0, 0); pdf.ln(3); pdf.set_text_color(*SLATE)

        def H2(txt):
            pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(*SLATE)
            pdf.cell(0, 7, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        def KV(label, value, lw=70):
            pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*GREY)
            pdf.cell(lw, 6, label)
            pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*SLATE)
            pdf.cell(0, 6, str(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        def SM(txt):
            pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(*GREY)
            pdf.multi_cell(0, 5, txt); pdf.set_text_color(*SLATE)

        def TH(*cols):
            pdf.set_font("Helvetica", "B", 9); pdf.set_fill_color(*LBLUE)
            pdf.set_text_color(*SLATE)
            for txt, w in cols:
                pdf.cell(w, 6.5, txt, fill=True)
            pdf.ln()

        def TR(i, *cells):
            pdf.set_fill_color(*LGREY) if i % 2 == 0 else pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(*SLATE)
            for txt, w, bold in cells:
                pdf.set_font("Helvetica", "B" if bold else "", 9)
                pdf.cell(w, 5.5, str(txt), fill=True)
            pdf.ln()

        def CHART(png_b):
            if png_b is None:
                SM("(chart unavailable)")
                return
            pdf.image(_io.BytesIO(png_b), x=15, w=180)

        # ── Page 1: Cover ──────────────────────────────────────────────────────────
        pdf.add_page()
        pdf.set_fill_color(*BLUE); pdf.rect(0, 0, 210, 52, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 22); pdf.set_y(10)
        pdf.cell(0, 13, "UK Net Worth Benchmarker", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 13)
        pdf.cell(0, 8, "Personal Report", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(219, 234, 254)
        pdf.cell(0, 7, f"Generated {_today}  |  ONS WAS Wave 8 (2020-2022)", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*SLATE)
        pdf.set_y(62)

        # ── Hero: big net worth number ─────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 34); pdf.set_text_color(*BLUE)
        pdf.cell(0, 18, _fmt(latest_nw), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 11); pdf.set_text_color(*GREY)
        pdf.cell(0, 7, f"Current net worth  |  Age {latest_age:.1f}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        # ── Three stat boxes ────────────────────────────────────────────────────
        p50v = _bm("p50")
        _stat_y = pdf.get_y()
        _stat_boxes = []
        if _pct_rpt:
            _stat_boxes.append((f"~{_ordinal(round(_pct_rpt))}", "Estimated percentile"))
        if p50v:
            _stat_boxes.append((f"{latest_nw/p50v*100:.0f}", "Wealth index (100 = median)"))
        if _cagr_rpt:
            _stat_boxes.append((f"{_cagr_rpt*100:+.1f}%", f"CAGR since age {float(_first_rpt['age']):.0f}"))

        _bw = 54  # box width mm
        _bh = 20  # box height mm
        _gap = 3
        _total_w = len(_stat_boxes) * _bw + (len(_stat_boxes)-1) * _gap
        _start_x = (210 - _total_w) / 2
        for j, (val, lbl) in enumerate(_stat_boxes):
            bx = _start_x + j * (_bw + _gap)
            pdf.set_fill_color(*LBLUE)
            pdf.rect(bx, _stat_y, _bw, _bh, 'F')
            pdf.set_xy(bx, _stat_y + 2)
            pdf.set_font("Helvetica", "B", 15); pdf.set_text_color(*BLUE)
            pdf.cell(_bw, 8, val, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_xy(bx, _stat_y + 10)
            pdf.set_font("Helvetica", "", 7); pdf.set_text_color(*GREY)
            pdf.cell(_bw, 6, lbl, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_xy(15, _stat_y + _bh + 5)
        pdf.set_text_color(*SLATE)

        # ── Settings strip ──────────────────────────────────────────────────────
        _basis_lbl = basis
        if basis == "Individual" and gender != "All":
            _basis_lbl = f"Individual ({gender})"
        pdf.ln(2)
        H1("Report settings")
        KV("Basis:", _basis_lbl)
        KV("Prices:", _price_lbl)
        KV("Pension wealth:", "Included" if include_pension else "Excluded")
        if wealth_component != "Total":
            KV("Wealth component:", wealth_component)

        if _pct_rpt:
            pdf.ln(4); H1("Key observations")
            # Find first entry with positive net worth for the percentile trend.
            # Only include this bullet if the start row is meaningfully earlier than the
            # latest row AND the percentile has actually moved (else it reads like nonsense).
            _pct_start_row = None
            for _, _r in _s_rpt.iterrows():
                if float(_r["net_worth"]) > 0:
                    _pct_start_row = _r
                    break
            _first_pct = None
            _trend_meaningful = False
            if _pct_start_row is not None:
                _start_age = float(_pct_start_row["age"])
                if abs(latest_age - _start_age) >= 0.5:  # at least 6 months apart
                    _first_pct = estimate_exact_percentile(
                        float(_pct_start_row["net_worth"]),
                        min(round(_start_age), 85), benchmark)
                    if _first_pct is not None and abs(_pct_rpt - _first_pct) >= 1:
                        _trend_meaningful = True
            p25v = _bm("p25"); p75v = _bm("p75")
            _obs = []
            if _trend_meaningful:
                _dp = _pct_rpt - _first_pct
                _dir = "risen" if _dp > 0 else "fallen"
                _sign = "+" if _dp > 0 else ""
                _obs.append(
                    f"Your percentile has {_dir} from the ~{_ordinal(round(_first_pct))} "
                    f"at age {float(_pct_start_row['age']):.0f} to the "
                    f"~{_ordinal(round(_pct_rpt))} at age {latest_age:.0f} "
                    f"({_sign}{_dp:.0f} pct pts)."
                )
            if p50v and p25v and p75v:
                if latest_nw >= p75v:
                    _obs.append(f"You are above the 75th percentile ({_fmt(p75v)}) for your age group.")
                elif latest_nw >= p50v:
                    _obs.append(
                        f"You are above the median ({_fmt(p50v)}) for your age group, "
                        f"with {_fmt(p75v - latest_nw)} to go to reach the 75th percentile."
                    )
                elif latest_nw >= p25v:
                    _obs.append(
                        f"You are between the 25th percentile ({_fmt(p25v)}) and the median "
                        f"({_fmt(p50v)}) for your age group."
                    )
                else:
                    _obs.append(f"You are below the 25th percentile ({_fmt(p25v)}) for your age group.")
            if _cagr_rpt and _cagr_rpt > 0 and p50v and latest_nw < p50v:
                try:
                    _yrs_med = math.log(p50v / latest_nw) / math.log(1 + _cagr_rpt)
                    if 0 < _yrs_med < 40:
                        _obs.append(
                            f"At your current growth rate you would reach the median "
                            f"in ~{_yrs_med:.0f} years (age {latest_age + _yrs_med:.0f})."
                        )
                except Exception:
                    pass
            for ob in _obs:
                pdf.set_font("Helvetica", "", 9.5); pdf.set_text_color(*SLATE)
                pdf.multi_cell(0, 5.5, ob)
                pdf.ln(1)

        # ── Page 2: Benchmark context & growth ─────────────────────────────────
        pdf.add_page()
        H1(f"Benchmark comparison at age {latest_age:.0f}")
        _basis_desc = "individuals" if basis == "Individual" else "households"
        pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*GREY)
        pdf.multi_cell(0, 5.5,
            f"ONS WAS Wave 8 (2020-2022) wealth thresholds for UK {_basis_desc} aged "
            f"{latest_age:.0f}, compared to your current net worth of {_fmt(latest_nw)}.")
        pdf.ln(3)
        TH(("Percentile", 35), ("Benchmark", 45), ("Your position", 100))
        for i, (pk, pl) in enumerate([("p10","P10"),("p25","P25"),("p50","Median"),
                                       ("p75","P75"),("p90","P90")]):
            v = _bm(pk)
            if v is None: continue
            diff = latest_nw - v
            pos = f"above by {_fmt(abs(diff))}" if diff >= 0 else f"below by {_fmt(abs(diff))}"
            TR(i, (pl, 35, pk=="p50"), (_fmt(v), 45, pk=="p50"), (pos, 100, False))
        pdf.set_font("Helvetica", "I", 7.5); pdf.set_text_color(*GREY)
        pdf.cell(0, 5, "P25, P50, P75: published ONS data.  "
                 "P10, P90: derived from log-normal model (indicative).", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*SLATE)

        pdf.ln(4); H1("Growth history")
        KV("Period:", f"Age {float(_first_rpt['age']):.1f} to {latest_age:.1f}  ({_asp_rpt:.1f} years)")
        KV("Starting net worth:", _fmt(_fnw_rpt))
        KV("Current net worth:", _fmt(latest_nw))
        KV("Total change:", _fmt_delta(latest_nw - _fnw_rpt))
        if _cagr_rpt:
            KV("CAGR:", f"{_cagr_rpt*100:+.2f}% per year")
            if _cagr_rpt > 0:
                KV("Doubling time:", f"~{math.log(2)/math.log(1+_cagr_rpt):.0f} years at this rate")
        if len(_s_rpt) >= 2:
            _g = _s_rpt["net_worth"].diff()
            _ib, _iw = _g.idxmax(), _g.idxmin()
            if not pd.isna(_ib):
                KV("Best period:", f"{_fmt_delta(_g[_ib])}  (age {float(_s_rpt.loc[_ib,'age']):.1f})")
            if not pd.isna(_iw):
                KV("Worst period:", f"{_fmt_delta(_g[_iw])}  (age {float(_s_rpt.loc[_iw,'age']):.1f})")

        # ── Page 3: Net worth history ───────────────────────────────────────────
        pdf.add_page()
        H1("Net worth history")
        pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*GREY)
        pdf.multi_cell(0, 5.5,
            "Each row shows your net worth at a point in time with the change from the previous "
            "entry and an estimated percentile. Percentiles are indicative (+/-5-10 pct pts).")
        pdf.ln(3)
        TH(("Age", 22), ("Year", 22), ("Net worth", 42), ("Change", 38), ("~Percentile", 40))
        _prev_nw = None
        for i, (_, rd) in enumerate(_s_rpt.iterrows()):
            a_d  = float(rd["age"]); nw_d = float(rd["net_worth"])
            p_d  = estimate_exact_percentile(nw_d, min(round(a_d), 85), benchmark)
            yr_d = str(int(rd["year"])) if "year" in rd.index else ""
            note_d = _clean_note(rd)
            chg = _fmt_delta(nw_d - _prev_nw) if _prev_nw is not None else "-"
            _prev_nw = nw_d
            TR(i, (f"{a_d:.1f}", 22, False), (yr_d, 22, False),
               (_fmt(nw_d), 42, False), (chg, 38, False),
               (f"~{_ordinal(round(p_d))}" if p_d else "n/a", 40, False))
            if note_d:
                pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(*GREY)
                pdf.cell(22, 4.5, ""); pdf.cell(0, 4.5, f"  Note: {note_d}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*SLATE)

        # ── Page 4: Main chart ─────────────────────────────────────────────────
        pdf.add_page(); H1("Net worth vs UK distribution")
        SM(
            f"Your net worth plotted against the P25, median and P75 benchmarks for UK "
            f"{_basis_desc} at each age. The shaded band shows the interquartile range. "
            f"Lines are PCHIP-interpolated from ONS WAS Wave 8 (2020-2022) age-band data."
        )
        pdf.ln(3); CHART(main_png)

        # ── Page 5: Percentile trajectory ──────────────────────────────────────
        if traj_png:
            pdf.add_page(); H1("Percentile trajectory")
            _pct_note = (f" Your current estimate is the ~{_ordinal(round(_pct_rpt))} percentile."
                         if _pct_rpt else "")
            SM(
                f"Your estimated percentile rank at each data point.{_pct_note} "
                f"A rising line means your wealth is growing faster than the typical UK {_basis_desc[:-1]}. "
                f"Derived from a log-normal model fitted to P25/P50/P75 - indicative +/-5-10 pct pts."
            )
            pdf.ln(3); CHART(traj_png)

        # ── Page 6: Annual gains ────────────────────────────────────────────────
        if gains_png:
            pdf.add_page(); H1("Year-on-year gains")
            SM(
                "Net change in wealth for each calendar year, using the last recorded "
                "entry per year. Multiple entries within the same year are consolidated "
                "so monthly updates do not fragment the chart. "
                "Blue = net worth increased; red = fell."
            )
            pdf.ln(3); CHART(gains_png)
            # Summary stats (annual basis)
            try:
                _gvals = _s_ann["net_worth"].diff().dropna()
                if len(_gvals) > 0:
                    _pos = int((_gvals > 0).sum())
                    _ibx = _gvals.idxmax(); _iwx = _gvals.idxmin()
                    # Year labels only when there's exactly one row per year
                    # (after any aggregation). Single-year monthly fallback
                    # labels by age — "Best year: +£X (2024)" would otherwise
                    # repeat the same year on every row.
                    _one_per_year = ("year" in _s_ann.columns
                                     and len(_s_ann) == _s_ann["year"].nunique())
                    if _one_per_year:
                        _yrs_col = "year"
                        _best_label, _worst_label = "Best year:", "Worst year:"
                        _period_label = "Positive years:"
                        _fmt_val = lambda v: f"{int(v)}"
                    else:
                        _yrs_col = "age"
                        _best_label, _worst_label = "Best period:", "Worst period:"
                        _period_label = "Positive periods:"
                        _fmt_val = lambda v: f"age {float(v):.1f}"
                    pdf.ln(5)
                    pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*BLUE)
                    pdf.cell(0, 6, "Summary statistics", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.set_draw_color(*BLUE)
                    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
                    pdf.ln(3); pdf.set_draw_color(0, 0, 0)
                    KV(_period_label, f"{_pos} of {len(_gvals)}  ({100*_pos/len(_gvals):.0f}%)")
                    KV("Average gain:", _fmt_delta(float(_gvals.mean())))
                    if not pd.isna(_ibx):
                        KV(_best_label, f"{_fmt_delta(float(_gvals[_ibx]))}  "
                           f"({_fmt_val(_s_ann.loc[_ibx, _yrs_col])})")
                    if not pd.isna(_iwx):
                        KV(_worst_label, f"{_fmt_delta(float(_gvals[_iwx]))}  "
                           f"({_fmt_val(_s_ann.loc[_iwx, _yrs_col])})")
            except Exception:
                pass

        # ── Page 7: What-if projection ─────────────────────────────────────────
        if whatif_png:
            pdf.add_page(); H1("What-if projection")
            _cagr_note = (f" Your historical CAGR is {_cagr_rpt*100:+.1f}%."
                          if _cagr_rpt else "")
            _contrib_note = (
                f" Includes ongoing contributions of £{wi_monthly:,}/month "
                f"(£{wi_monthly*12:,}/year) on top of investment growth."
                if wi_monthly > 0 else
                " Assumes no further contributions - only investment growth at the chosen CAGR."
            )
            SM(
                f"Projected net worth from age {latest_age:.0f} to {wi_age} under three CAGR "
                f"scenarios, alongside the benchmark median. Starting net worth: {_fmt(latest_nw)}."
                f"{_contrib_note}{_cagr_note} Illustrative only - not financial advice."
            )
            pdf.ln(3); CHART(whatif_png)
            # Projected values table
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*SLATE)
            pdf.cell(0, 6, f"Projected values at age {wi_age}:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            TH(("Scenario", 90), (f"Net worth at age {wi_age}", 50), ("vs benchmark median", 40))
            _ann = wi_monthly * 12
            _p50_at_wi = None
            _p50_wi_rows = benchmark[
                (benchmark["percentile"]=="p50") & (benchmark["age"]==min(wi_age,85))]
            if len(_p50_wi_rows):
                _p50_at_wi = float(_p50_wi_rows["value"].iloc[0])
            for _si, (_cagr_v, _lbl) in enumerate([
                (wi_cagr1/100, f"S1 +{wi_cagr1:.1f}% (conservative)"),
                (wi_cagr2/100, f"S2 +{wi_cagr2:.1f}% (base case)"),
                (wi_cagr3/100, f"S3 +{wi_cagr3:.1f}% (optimistic)"),
            ]):
                try:
                    _t = wi_age - latest_age
                    if _t <= 0: continue
                    if abs(_cagr_v) < 1e-10:
                        _proj = latest_nw + _ann * _t
                    else:
                        _proj = latest_nw*(1+_cagr_v)**_t + _ann*((1+_cagr_v)**_t - 1)/_cagr_v
                    _vs_med = ""
                    if _p50_at_wi:
                        _diff = _proj - _p50_at_wi
                        _vs_med = f"{'above' if _diff>=0 else 'below'} by {_fmt(abs(_diff))}"
                    TR(_si, (_lbl, 90, False),
                       (_fmt(_proj), 50, _si==1),
                       (_vs_med, 40, False))
                except Exception:
                    pass

        # ── Page 8: Monte Carlo (if MC was run) ────────────────────────────────
        # mc_png is set if _mpl_monte_carlo() succeeded; that function only
        # needs `mc_paths` in scope. The text below is defensive — every other
        # mc_* variable can be missing and we still render the page using
        # sensible fallbacks (defined here, not via NameError catches).
        if mc_png:
            # Pull every MC variable up-front with safe defaults. Using
            # locals().get() / globals().get() avoids NameError on any
            # individual missing name.
            _g = globals()
            _mc_glide_path  = _g.get("mc_glide_path", None)
            _mc_mean        = _g.get("mc_mean", 5.0)
            _mc_sigma       = _g.get("mc_sigma", 12.0)
            _mc_monthly     = _g.get("mc_monthly", 0)
            _mc_target_age  = _g.get("mc_target_age",
                                     int(latest_age) + len(mc_paths[0]) - 1
                                     if mc_paths is not None and len(mc_paths[0]) else 65)
            _mc_target_nw   = _g.get("mc_target_nw", 0)

            try:
                pdf.add_page(); H1("Monte Carlo projection")
                if _mc_glide_path is None:
                    _mc_desc = (f"fixed N(mu={_mc_mean:.1f}%, sigma={_mc_sigma:.1f}%) "
                                f"each year")
                else:
                    _mc_desc = (f"equity/bond glide path from {_mc_glide_path[0]*100:.0f}% "
                                f"to {_mc_glide_path[1]*100:.0f}% equity")
                _mc_contrib = (f" Includes £{_mc_monthly:,}/month ongoing contributions."
                               if _mc_monthly > 0 else
                               " No further contributions.")
                SM(
                    f"1,000 simulations from age {int(latest_age)} to age {_mc_target_age}, "
                    f"using {_mc_desc}.{_mc_contrib} "
                    f"The bands show the range of likely outcomes - real markets show mean "
                    f"reversion and fat tails, so treat as a planning aid, not a forecast."
                )
                pdf.ln(3); CHART(mc_png)

                # Outcome summary table
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*SLATE)
                pdf.cell(0, 6, f"Outcomes at age {_mc_target_age}:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)
                _mc_final = mc_paths[:, -1]
                _mc_p10 = float(np.percentile(_mc_final, 10))
                _mc_p50 = float(np.percentile(_mc_final, 50))
                _mc_p90 = float(np.percentile(_mc_final, 90))
                TH(("Outcome", 90), (f"Net worth at age {_mc_target_age}", 90))
                TR(0, ("Pessimistic (10th percentile)",        90, False),
                       (_fmt(_mc_p10),                          90, False))
                TR(1, ("Median outcome (50th percentile)",     90, False),
                       (_fmt(_mc_p50),                          90, True))
                TR(2, ("Optimistic (90th percentile)",         90, False),
                       (_fmt(_mc_p90),                          90, False))

                # Probability of hitting target, if set
                if _mc_target_nw and _mc_target_nw > 0:
                    pdf.ln(4)
                    pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*SLATE)
                    _pt = probability_of_reaching(mc_paths, _mc_target_nw)
                    _ratio = "succeed" if _pt >= 0.5 else "fall short"
                    pdf.multi_cell(
                        0, 5.5,
                        f"Probability of reaching {_fmt(_mc_target_nw)} target: "
                        f"{_pt*100:.0f}%. In {1000:,} simulations, "
                        f"{int(_pt*1000):,} reach the target and "
                        f"{int((1-_pt)*1000):,} {_ratio}."
                    )
            except Exception as _mc_err:
                # Page partially rendered - add a footnote so the failure is
                # visible to the user instead of silently disappearing.
                pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(*GREY)
                pdf.multi_cell(0, 4.5, f"(Monte Carlo details incomplete: {type(_mc_err).__name__})")

        # ── Page 9: Goals (if set) ─────────────────────────────────────────────
        try:
            if goal_amount > 0 or fire_number > 0:
                pdf.add_page(); H1("Goals & financial independence")
                KV("Target net worth:", _fmt(goal_amount))
                KV("FIRE number (25x annual spending):", _fmt(fire_number))
                try: KV("Annual retirement spending:", f"GBP {fire_spending:,}")
                except NameError: pass

                def _pbar(pct_val, colour=BLUE):
                    """Draw a simple horizontal progress bar."""
                    bx = pdf.l_margin; by = pdf.get_y()
                    bw = 180; bh = 7
                    pdf.set_fill_color(*LGREY); pdf.rect(bx, by, bw, bh, "F")
                    fill_w = max(2, min(bw, bw * pct_val / 100))
                    pdf.set_fill_color(*colour); pdf.rect(bx, by, fill_w, bh, "F")
                    pdf.set_font("Helvetica", "B", 8); pdf.set_text_color(255, 255, 255)
                    if fill_w > 14:
                        pdf.set_xy(bx + 3, by + 0.8)
                        pdf.cell(fill_w - 3, bh - 1, f"{pct_val:.0f}%", align="L")
                    pdf.set_xy(bx, by + bh + 3); pdf.set_text_color(*SLATE)

                for tgt_lbl, tgt_v in [("Target net worth", goal_amount),
                                        ("FIRE number", fire_number)]:
                    if tgt_v <= 0: continue
                    pct_t = min(latest_nw / tgt_v * 100, 100)
                    pdf.ln(3); H2(f"{tgt_lbl}")
                    pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*GREY)
                    pdf.cell(0, 5, f"{_fmt(latest_nw)} of {_fmt(tgt_v)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(1); _pbar(pct_t)
                    if tgt_v > latest_nw:
                        KV("  Remaining gap:", _fmt(tgt_v - latest_nw))
                        if _cagr_rpt and _cagr_rpt > 0:
                            try:
                                yrs_t = math.log(tgt_v / latest_nw) / math.log(1 + _cagr_rpt)
                                if 0 < yrs_t < 80:
                                    KV("  ETA at current CAGR:",
                                       f"~{yrs_t:.0f} years  (age {latest_age + yrs_t:.0f})")
                            except Exception: pass
                        elif _asp_rpt > 0.5:
                            try:
                                _avg_ann = (latest_nw - _fnw_rpt) / _asp_rpt
                                if _avg_ann > 0:
                                    _yrs_avg = (tgt_v - latest_nw) / _avg_ann
                                    if 0 < _yrs_avg < 80:
                                        KV("  ETA (avg annual gain):",
                                           f"~{_yrs_avg:.0f} years  (age {latest_age + _yrs_avg:.0f})")
                            except Exception: pass
                    else:
                        pdf.set_font("Helvetica", "B", 9)
                        pdf.set_text_color(16, 185, 129)
                        pdf.cell(0, 6, "  Goal achieved!", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                        pdf.set_text_color(*SLATE)

                if fire_number > 0:
                    _fi_pct = min(latest_nw/fire_number*100, 100)
                    pdf.ln(3); H2("Financial independence tracker")
                    pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*GREY)
                    pdf.cell(0, 5, f"{_fmt(latest_nw)} of {_fmt(fire_number)} FIRE target", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(1); _pbar(_fi_pct, colour=(16, 185, 129))
                    KV("Sustainable spending at current NW:",
                       f"{_fmt(latest_nw/25/52)}/week  ({_fmt(latest_nw/25)}/yr)")
                    if fire_number > latest_nw:
                        KV("FIRE gap:", _fmt(fire_number - latest_nw))

        except (NameError, Exception): pass

        # ── Page 9: Retirement income forecast ─────────────────────────────────
        try:
            _retire_age_pdf = int(retirement_age) if retirement_age else 65
            if _retire_age_pdf > latest_age and latest_nw > 0:
                pdf.add_page(); H1("Retirement income forecast")
                SM(
                    f"Projected annual income at age {_retire_age_pdf} from your net worth, split "
                    "into annuity (pension wrappers) + 4% drawdown (other wealth) + state pension. "
                    "Real terms (today's money). Indicative only - not financial advice."
                )
                pdf.ln(3)
                # Project NW at 4% real return as a baseline
                _yrs_to_retire = _retire_age_pdf - latest_age
                _nw_at_retire = latest_nw * (1.04 ** _yrs_to_retire)
                # Pension share comes from personal_asset_split if set, else 30%
                try:
                    _pen_share = personal_asset_split["Pension"] if personal_asset_split else 0.30
                except NameError:
                    _pen_share = 0.30
                _pen_pot = _nw_at_retire * _pen_share
                _other  = _nw_at_retire - _pen_pot
                _pcls_pdf = tax_free_lump_sum(_pen_pot)  # 25% tax-free, capped at the LSA
                _ann_rate_pdf = 0.065 + (_retire_age_pdf - 65) * 0.0025
                _annuity_pdf  = (_pen_pot - _pcls_pdf) * max(_ann_rate_pdf, 0.02)
                _draw_pdf     = _other * 0.04
                _sp_pdf       = state_pension if (_retire_age_pdf >= 67 and state_pension) else 0
                _total_pdf    = _annuity_pdf + _draw_pdf + _sp_pdf
                _tax_pdf      = income_tax_2025_26(_annuity_pdf + _sp_pdf)
                _net_pdf      = _total_pdf - _tax_pdf

                KV("Projected net worth at retirement:", _fmt(_nw_at_retire))
                KV("  Assumed real return until retirement:", "4.0% per year")
                KV("  Pension wrappers (annuity source):", f"{_fmt(_pen_pot)}  ({_pen_share*100:.0f}%)")
                KV("  Other wealth (4% drawdown source):", _fmt(_other))
                KV("  Tax-free lump sum (25%, one-off):", _fmt(_pcls_pdf))
                pdf.ln(3)

                pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*BLUE)
                pdf.cell(0, 6, "Estimated annual income at retirement", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_draw_color(*BLUE); pdf.line(15, pdf.get_y(), 195, pdf.get_y())
                pdf.ln(3); pdf.set_draw_color(0, 0, 0)
                TH(("Source", 90), ("Annual income", 50), ("Per week", 40))
                rows_inc = [
                    ("Pension annuity (on 75% after tax-free cash)", _annuity_pdf, False),
                    ("4% drawdown from other wealth", _draw_pdf, False),
                    ("State pension", _sp_pdf, False),
                    ("Total (pre-tax)", _total_pdf, True),
                    ("Less income tax", -_tax_pdf, False),
                    ("Net annual income", _net_pdf, True),
                ]
                for _idx, (lbl_inc, val_inc, bold) in enumerate(rows_inc):
                    TR(_idx, (lbl_inc, 90, bold),
                       (f"{_fmt(val_inc)}/yr", 50, bold),
                       (f"{_fmt(val_inc/52)}/wk", 40, bold))

                # Compare against target
                try:
                    _target_pdf = float(pension_income) if pension_income else 0
                except (NameError, ValueError):
                    _target_pdf = 0
                if _target_pdf > 0:
                    pdf.ln(3)
                    _gap = _net_pdf - _target_pdf
                    if _gap >= 0:
                        pdf.set_text_color(16, 185, 129)
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.cell(0, 6, f"Net income exceeds target ({_fmt(_target_pdf)}/yr) by {_fmt(_gap)}/yr.",
                                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    else:
                        pdf.set_text_color(217, 119, 6)
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.cell(0, 6, f"Net income short of target ({_fmt(_target_pdf)}/yr) by {_fmt(abs(_gap))}/yr.",
                                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.set_text_color(*SLATE)

                pdf.ln(4)
                SM(
                    "Assumptions: 4% real return on NW until retirement; "
                    f"annuity at {_ann_rate_pdf*100:.1f}% (gilt-linked level annuity, single life) "
                    "on the 75% left after the 25% tax-free lump sum; "
                    "4% safe withdrawal from non-pension wealth; state pension from age 67. "
                    "Income tax is the rUK 2025/26 estimate on annuity + state pension "
                    "(4% draw assumed tax-free from ISAs; Scotland differs)."
                )
        except Exception: pass

        # ── Final page: Methodology & disclaimer ───────────────────────────────
        pdf.add_page()
        H1("Methodology & data sources")
        pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*SLATE)
        for para in [
            ("Benchmark data: ONS Wealth and Assets Survey (WAS) Wave 8, covering April 2020 to March 2022. "
             "The survey provides P25, P50 and P75 total wealth by age band for UK households "
             "and individuals. Values are approximate reproductions of published tables."),
            ("Interpolation: PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) converts "
             "the published 10-year age bands to single-year estimates from age 16 to 85."),
            ("Percentile estimation: The exact percentile for a given net worth at a given age is "
             "estimated via a log-normal distribution fitted to the P25, P50 and P75 values. "
             "Estimates carry uncertainty of approximately +/-5 to 10 percentile points."),
            ("Real-terms adjustment: Where selected, all figures are CPI-adjusted to 2026 prices "
             "using an estimated adjustment factor of ~1.26 (CPI index ~141.7, base 2015=100)."),
            ("Individual basis: Household totals are converted using WAS-derived sharing factors. "
             "Gender-adjusted benchmarks use published WAS male/female wealth ratios."),
        ]:
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5.5, para)
            pdf.ln(2)

        pdf.ln(3)
        H1("Disclaimer")
        pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*SLATE)
        for para in [
            ("This report is produced for personal information and illustration only. "
             "It does not constitute financial advice. Benchmark data reflect April 2020 to March 2022 survey "
             "conditions and may not represent current wealth distributions."),
            ("Projections assume constant growth rates and do not account for tax, inflation, "
             "market volatility, or changes in personal circumstances. "
             "Past growth does not guarantee future returns."),
            ("Please consult a qualified financial adviser before making investment or "
             "retirement decisions."),
            ("Data: Office for National Statistics, Wealth and Assets Survey Wave 8 "
             "(April 2020 to March 2022). Reproduced under the Open Government Licence v3.0."),
        ]:
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5.5, para)
            pdf.ln(2)

        return bytes(pdf.output())

    # ── Download buttons ───────────────────────────────────────────────────────
    st.markdown("**Export report**")
    rpt_col1, rpt_col2 = st.columns(2)

    with rpt_col1:
        if st.button("Generate PDF report", type="secondary", use_container_width=True,
                     help="Renders all active charts and assembles a multi-page PDF (~5 seconds)."):
            with st.spinner("Rendering charts and building PDF..."):
                try:
                    st.session_state["_pdf_bytes"] = _generate_pdf()
                    st.session_state["_pdf_date"]  = _today
                except ImportError:
                    st.error("PDF export requires fpdf2. Add `fpdf2>=2.7.0` to requirements.txt.")
                except Exception as _e:
                    st.error(f"PDF generation failed: {_e}")

        if st.session_state.get("_pdf_bytes"):
            st.download_button(
                f"Download PDF (generated {st.session_state.get('_pdf_date', '')})",
                st.session_state["_pdf_bytes"],
                f"networth_report_{_today}.pdf",
                "application/pdf",
                use_container_width=True,
            )

    with rpt_col2:
        # Lightweight text report as fallback — also useful for piping into LLMs
        # or any other text-based tooling that doesn't render PDF.
        _ab_rpt2 = benchmark[benchmark["age"] == min(round(latest_age), 85)]
        _lines = [
            "# UK Net Worth Benchmarker — Personal Report",
            f"Generated: {_today}",
            f"Settings: {basis} basis, {_price_lbl}, {'with' if include_pension else 'without'} pension",
            "", "## Snapshot",
            f"- Age: {latest_age:.1f}",
            f"- Net worth: {_fmt(latest_nw)}",
            f"- Estimated percentile: {'~'+str(round(_pct_rpt))+'th' if _pct_rpt else 'n/a'}",
            "", "## Growth",
            f"- Period: age {float(_first_rpt['age']):.1f} to {latest_age:.1f} ({_asp_rpt:.1f} yrs)",
            f"- Change: {_fmt(_fnw_rpt)} to {_fmt(latest_nw)} ({_fmt_delta(latest_nw-_fnw_rpt)})",
        ]
        if _cagr_rpt:
            _lines.append(f"- CAGR: {_cagr_rpt*100:+.2f}%")

        # Benchmark
        _lines += ["", f"## Benchmark at age {latest_age:.0f}"]
        for _pk, _pl in [("p25","P25"),("p50","Median"),("p75","P75")]:
            _v = _bm(_pk)
            if _v: _lines.append(f"- {_pl}: {_fmt(_v)}")

        # Partner section (if loaded)
        if partner_plot_df is not None and len(partner_plot_df) > 0:
            _p_sorted = partner_plot_df.sort_values("age")
            _p_last = _p_sorted.iloc[-1]
            _p_age, _p_nw = float(_p_last["age"]), float(_p_last["net_worth"])
            _p_pct = estimate_exact_percentile(_p_nw, round(_p_age), benchmark)
            _lines += ["", "## Partner",
                       f"- Age: {_p_age:.1f}",
                       f"- Net worth: {_fmt(_p_nw)}",
                       f"- Estimated percentile: "
                       f"{'~'+str(round(_p_pct))+'th' if _p_pct else 'n/a'}",
                       f"- Combined household: {_fmt(latest_nw + _p_nw)}"]

        # Goals section (if any are set)
        _goals_lines = []
        try:
            if goal_amount > 0:
                _goals_lines.append(
                    f"- Target net worth: {_fmt(goal_amount)} "
                    f"({'reached' if latest_nw >= goal_amount else _fmt(goal_amount-latest_nw)+' to go'})"
                )
        except NameError:
            pass
        try:
            if fire_number > 0:
                _goals_lines.append(
                    f"- FIRE number (25x £{fire_spending:,}/yr spend): {_fmt(fire_number)} "
                    f"({'reached' if latest_nw >= fire_number else _fmt(fire_number-latest_nw)+' to go'})"
                )
        except NameError:
            pass
        if _goals_lines:
            _lines += ["", "## Goals"] + _goals_lines

        # Data quality score
        try:
            _dq = compute_data_quality(personal_plot_df)
            _lines += ["", "## Data quality",
                       f"- Score: {_dq['score']}/100",
                       f"- Data points: {_dq['n']}, span: {_dq['span']:.1f} yrs"]
        except Exception:
            pass

        _lines += ["", "---",
                   f"Data: ONS WAS Wave 8 (2020-2022). Generated by {APP_VERSION}. Not financial advice."]
        st.download_button(
            "Download text report (.md)",
            "\n".join(_lines).encode(),
            f"networth_report_{_today}.md",
            "text/markdown",
            use_container_width=True,
        )

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    f"<div style='text-align:center; color:#94a3b8; font-size:0.8rem; line-height:1.6;'>"
    f"UK Net Worth Benchmarker {APP_VERSION} · ONS WAS Wave 8 (2020–2022) · "
    f"Built with Streamlit & Plotly<br>"
    f"Indicative figures only — not financial advice. "
    f"See the methodology panel above for sources and assumptions."
    f"</div>",
    unsafe_allow_html=True,
)
