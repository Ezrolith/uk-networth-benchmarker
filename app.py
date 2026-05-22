"""
UK Net Worth Benchmarker
------------------------
Visualises ONS Wealth and Assets Survey percentile distributions by age,
with personal (and optional partner) overlay and a transparent inference layer.
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
    DATA_YEAR, REAL_BASE_YEAR,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="UK Net Worth Benchmarker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

_url_personal_df: pd.DataFrame | None = None
_url_load_error: str | None = None
_qp = st.query_params
if "d" in _qp and "url_personal_loaded" not in st.session_state:
    try:
        _url_personal_df = decode_personal_data(_qp["d"])
        st.session_state.url_personal_df = _url_personal_df
        st.session_state.url_personal_loaded = True
    except Exception:
        _url_load_error = "Could not decode the shared link — it may be corrupted or expired."
elif "url_personal_df" in st.session_state:
    _url_personal_df = st.session_state.url_personal_df


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
                for attr in ("excel_year_warning", "birth_year_warning"):
                    if attr in result_df.attrs:
                        st.warning(result_df.attrs[attr], icon="⚠️")
            except ValueError as exc:
                st.error(str(exc))

        template = pd.DataFrame({
            "year": [2020, 2021, 2022, 2023, 2024],
            "age":  [28, 29, 30, 31, 32],
            "net_worth": [12000, 18500, 27000, 38000, 52000],
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
            st.session_state[ss_key] = [{"year": 2024, "age": 30, "net_worth": 0, "note": ""}]
        edited = st.data_editor(
            pd.DataFrame(st.session_state[ss_key]),
            num_rows="dynamic", use_container_width=True,
            column_config={
                "year":      st.column_config.NumberColumn("Year",     min_value=1960, max_value=2030, step=1,    format="%d"),
                "age":       st.column_config.NumberColumn("Age",      min_value=16,   max_value=100,  step=1,    format="%d"),
                "net_worth": st.column_config.NumberColumn("Net worth (£)", min_value=-1_000_000, max_value=50_000_000, step=1_000, format="£%,d"),
                "note":      st.column_config.TextColumn("Note (optional)", max_chars=80,
                                                          help="Short label shown in hover tooltip, e.g. 'bought house'"),
            },
            key=f"{key_prefix}_editor",
        )
        if len(edited) > 0 and edited["net_worth"].abs().sum() > 0:
            result_df = edited.copy()
            result_df["year"]      = result_df["year"].astype(int)
            result_df["age"]       = result_df["age"].astype(float)
            result_df["net_worth"] = result_df["net_worth"].astype(float)
            result_df["note"]      = result_df["note"].fillna("").astype(str) if "note" in result_df.columns else ""
            result_df = result_df.sort_values("age").reset_index(drop=True)
            st.session_state[ss_key] = result_df.to_dict("records")

    return result_df


# ── Helpers (defined before sidebar so they're available everywhere) ───────────

def _fmt(v: float) -> str:
    neg = v < 0; av = abs(v)
    if av >= 1_000_000: s = f"£{av/1_000_000:.2f}m"
    elif av >= 1_000:   s = f"£{av/1_000:.0f}k"
    else:               s = f"£{av:.0f}"
    return f"-{s}" if neg else s

def _fmt_delta(d: float) -> str:
    return ("+" if d >= 0 else "") + _fmt(d)

def _clean_note(row) -> str:
    """Extract a row's note as a clean string. Treats NaN, 'nan', and blanks as empty."""
    if "note" not in row.index:
        return ""
    val = row.get("note")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

# CAGR is only meaningful if the starting balance is non-trivial.
# Tiny starts (e.g. £100 → £8k) compute as 100%+ CAGR but tell us nothing useful.
_CAGR_MIN_START = 5_000

def _safe_cagr(start_nw: float, end_nw: float, years: float) -> float | None:
    """Return CAGR if it would be meaningful, else None."""
    if years is None or years <= 0.5:
        return None
    if start_nw is None or end_nw is None:
        return None
    if start_nw < _CAGR_MIN_START or end_nw <= 0:
        return None
    return (end_nw / start_nw) ** (1 / years) - 1


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

    age_min, age_max = st.slider("Age range shown", 16, 85, (16, 85), step=1,
                                 help="Zoom in on a specific age window")

    st.divider()

    # ── Your data ─────────────────────────────────────────────────────────────
    if _url_load_error:
        st.error(_url_load_error)
    personal_df = _personal_data_section("Your net worth", "you", _url_personal_df)

    st.divider()
    partner_df = _personal_data_section("Partner's net worth (optional)", "partner")

    st.divider()

    # ── Personal asset composition ────────────────────────────────────────────
    with st.expander("Your wealth composition (optional)"):
        st.caption("Enter your approximate split — shown on the asset class chart.")
        pa_prop = st.number_input("Property %",    0, 100, 40, key="pa_prop")
        pa_pen  = st.number_input("Pension %",     0, 100, 30, key="pa_pen")
        pa_fin  = st.number_input("Financial %",   0, 100, 20, key="pa_fin")
        pa_phys = st.number_input("Physical %",    0, 100, 10, key="pa_phys")
        pa_total = pa_prop + pa_pen + pa_fin + pa_phys
        if pa_total != 100:
            st.warning(f"Percentages sum to {pa_total}% — should be 100%.")
        personal_asset_split = {
            "Property": pa_prop / 100,
            "Pension":  pa_pen  / 100,
            "Financial":pa_fin  / 100,
            "Physical": pa_phys / 100,
        } if pa_total == 100 else None

    st.divider()

    # ── Goal / FIRE calculator ─────────────────────────────────────────────────
    with st.expander("Goal calculator"):
        st.caption("Set a net worth target and see your trajectory toward it.")
        goal_amount = st.number_input("Target net worth (£)", min_value=0,
                                      max_value=10_000_000, value=500_000, step=10_000,
                                      format="%d", key="goal_amount")
        fire_spending = st.number_input("Annual retirement spending (£, for FIRE estimate)",
                                        min_value=0, max_value=500_000, value=30_000,
                                        step=1_000, format="%d", key="fire_spend")
        fire_number = fire_spending * 25  # 4% safe withdrawal rate
        st.caption(f"FIRE number (25× spending, 4% SWR): **{_fmt(fire_number)}**")

        st.markdown("**Pension pot estimator**")
        retirement_age = st.number_input("Target retirement age", 50, 80, 65, 1, key="ret_age")
        pension_income = st.number_input("Target annual pension income (£)", 0, 200_000, 20_000, 1_000,
                                          format="%d", key="pen_income")
        state_pension  = st.number_input("Expected state pension (£/yr)", 0, 15_000, 11_500, 100,
                                          format="%d", key="state_pension",
                                          help="Full new State Pension 2024/25: ~£11,500/yr")
        if retirement_age and pension_income:
            private_needed = max(0, pension_income - state_pension)
            # Use annuity rate approximation: 5% for age 65, adjusting for early/late retirement
            annuity_rate = 0.05 + (retirement_age - 65) * 0.002
            pot_needed   = private_needed / max(annuity_rate, 0.02)
            st.caption(
                f"Private pension pot needed: **{_fmt(pot_needed)}** "
                f"(for £{private_needed:,}/yr net of state pension, "
                f"~{annuity_rate*100:.1f}% annuity rate at age {retirement_age})"
            )

        st.markdown("**Savings rate calculator**")
        annual_income = st.number_input(
            "Annual gross income (£)", 0, 1_000_000, 50_000, 1_000,
            format="%d", key="annual_income",
            help="Used to estimate required savings rate to reach your goal."
        )
        if annual_income > 0 and latest_nw is not None and latest_nw > 0:
            for tgt_label, tgt_val in [("goal", goal_amount), ("FIRE number", fire_number)]:
                if tgt_val > latest_nw:
                    # At current CAGR: years to target; savings needed = (target - compound_growth) / years
                    # Simplified: use CAGR from personal data if available
                    sorted_pdf2 = personal_plot_df.sort_values("age") if personal_plot_df is not None else None
                    if sorted_pdf2 is not None and len(sorted_pdf2) >= 2:
                        fs = float(sorted_pdf2.iloc[0]["net_worth"])
                        asp = float(sorted_pdf2.iloc[-1]["age"]) - float(sorted_pdf2.iloc[0]["age"])
                        if asp > 0.5 and fs > 0 and latest_nw > 0:
                            cagr_s = (latest_nw / fs) ** (1 / asp) - 1
                            if cagr_s > 0:
                                yrs_s = math.log(tgt_val / latest_nw) / math.log(1 + cagr_s)
                                if 0 < yrs_s < 60:
                                    savings_needed = (tgt_val - latest_nw * (1 + cagr_s) ** yrs_s) / yrs_s
                                    # savings_needed may be negative if compound growth alone gets there
                                    savings_rate = max(0, savings_needed) / annual_income * 100
                                    st.caption(
                                        f"To reach **{tgt_label}** ({_fmt(tgt_val)}) in "
                                        f"~{yrs_s:.0f} yrs at {cagr_s*100:.1f}% CAGR: "
                                        f"save **{savings_rate:.0f}%** of income "
                                        f"(~{_fmt(annual_income * savings_rate / 100)}/yr)."
                                    )

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
        "Data: ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain. "
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

def _prep_plot_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or len(df) == 0:
        return None
    return cpi_adjust_personal(df, to_year=REAL_BASE_YEAR) if real_terms else df.copy()

personal_plot_df = _prep_plot_df(personal_df)
partner_plot_df  = _prep_plot_df(partner_df)


def _pct_series(pct: str) -> pd.DataFrame:
    return benchmark[benchmark["percentile"] == pct].sort_values("age")

def _hover(label: str) -> str:
    return f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>"

def _best_gain(pdf: pd.DataFrame) -> tuple[float, float, float] | None:
    """Return (age_at_gain, gain_amount, pct_gain) for the biggest single YoY jump."""
    if len(pdf) < 2:
        return None
    s = pdf.sort_values("age")
    gains = s["net_worth"].diff()
    pct_gains = s["net_worth"].pct_change()
    idx = gains.idxmax()
    if pd.isna(idx):
        return None
    return float(s.loc[idx, "age"]), float(gains[idx]), float(pct_gains[idx] * 100)


# ── Main benchmark + personal chart ──────────────────────────────────────────

def build_main_figure(
    log_scale: bool, show_tails: bool, show_milestones: bool,
    show_annotations: bool,
    age_min: int, age_max: int,
    latest_age: float | None, latest_nw: float | None,
    partner_latest_age: float | None = None,
) -> go.Figure:
    fig = go.Figure()

    p25 = _pct_series("p25")
    p50 = _pct_series("p50")
    p75 = _pct_series("p75")

    # IQR shading
    fig.add_trace(go.Scatter(
        x=pd.concat([p25["age"], p75["age"].iloc[::-1]]),
        y=pd.concat([p25["value"], p75["value"].iloc[::-1]]),
        fill="toself", fillcolor=COLOURS["band"],
        line=dict(width=0), name="P25–P75 range",
        hoverinfo="skip", showlegend=True,
    ))

    # P10/P90 tails
    if show_tails:
        tails = derive_tail_percentiles(benchmark)
        for pct_lbl, label in [("p10", "10th (modelled)"), ("p90", "90th (modelled)")]:
            s = tails[tails["percentile"] == pct_lbl].sort_values("age")
            if len(s):
                fig.add_trace(go.Scatter(
                    x=s["age"], y=s["value"],
                    mode="lines",
                    line=dict(color="#bfdbfe", width=1.5, dash="dot"),
                    name=label,
                    hovertemplate=f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>",
                ))

    # P25, P75, P50 lines
    for pct_data, colour, width, dash, label in [
        (p25, COLOURS["p25"], 2, "dash",  "25th percentile"),
        (p75, COLOURS["p75"], 2, "dash",  "75th percentile"),
        (p50, COLOURS["p50"], 3, "solid", "Median (P50)"),
    ]:
        fig.add_trace(go.Scatter(
            x=pct_data["age"], y=pct_data["value"],
            mode="lines",
            line=dict(color=colour, width=width, dash=dash),
            name=label, hovertemplate=_hover(label),
        ))

    # ONS published markers
    if basis == "Household":
        pub_shown = False
        for pct_data in [p25, p50, p75]:
            pub = pct_data[pct_data["is_published"]]
            if len(pub):
                fig.add_trace(go.Scatter(
                    x=pub["age"], y=pub["value"],
                    mode="markers",
                    marker=dict(color=COLOURS["pub"], size=9, symbol="circle",
                                line=dict(color="white", width=1.5)),
                    name="ONS data point", showlegend=not pub_shown,
                    hovertemplate="<b>ONS published</b><br>Age %{x}<br>£%{y:,.0f}<extra></extra>",
                ))
                pub_shown = True
    else:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
            marker=dict(color="rgba(0,0,0,0)", size=1),
            name="Individual figures are derived estimates", showlegend=True,
        ))

    # Milestone reference lines
    if show_milestones and not log_scale:
        for amount, label in [(100_000,"£100k"),(250_000,"£250k"),(500_000,"£500k"),(1_000_000,"£1m")]:
            fig.add_hline(y=amount, line=dict(color="#d1d5db", width=1, dash="dot"),
                annotation_text=label, annotation_position="right",
                annotation=dict(font=dict(color="#9ca3af", size=10), bgcolor="rgba(0,0,0,0)"),
            )

    # ── Personal overlay ──────────────────────────────────────────────────────
    bm_at_age = benchmark.set_index(["age", "percentile"])["value"]

    def _add_personal_trace(
        pdf: pd.DataFrame, colour: str, name: str,
        show_crosshair: bool, show_horiz: bool
    ):
        pdf = pdf.sort_values("age")
        has_neg = (pdf["net_worth"] < 0).any()

        if has_neg and not log_scale:
            fig.add_hline(y=0, line=dict(color="#94a3b8", width=1.5),
                annotation_text="Zero", annotation_position="right",
                annotation=dict(font=dict(color="#94a3b8", size=10)),
            )

        plot = pdf[pdf["net_worth"] > 0] if log_scale else pdf
        if not len(plot):
            return

        # Build enriched hover customdata
        custom = []
        for _, row in plot.iterrows():
            ar = min(round(float(row["age"])), 85)
            yr = row.get("year", "")
            try:
                cp25 = bm_at_age.loc[(ar, "p25")]
                cp50 = bm_at_age.loc[(ar, "p50")]
                cp75 = bm_at_age.loc[(ar, "p75")]
            except KeyError:
                cp25 = cp50 = cp75 = float("nan")
            note = _clean_note(row) if "note" in plot.columns else ""
            note_html = f"<br><i>Note: {note}</i>" if note else ""
            custom.append([yr, cp25, cp50, cp75, note_html])

        fig.add_trace(go.Scatter(
            x=plot["age"], y=plot["net_worth"],
            mode="lines+markers",
            line=dict(color=colour, width=2.5),
            marker=dict(color=colour, size=8, line=dict(color="white", width=1.5)),
            name=name,
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Age %{x:.1f} (year %{customdata[0]})<br>"
                "£%{y:,.0f}<br>"
                "<i>Benchmark: P25 £%{customdata[1]:,.0f} · "
                "Med £%{customdata[2]:,.0f} · P75 £%{customdata[3]:,.0f}</i>"
                "%{customdata[4]}<extra></extra>"
            ),
            customdata=custom,
        ))

        # Best gain annotation (suppressed when show_annotations=False)
        if show_annotations:
            best = _best_gain(plot)
            if best:
                bg_age, bg_amount, bg_pct = best
                bg_nw = float(plot[plot["age"] == bg_age]["net_worth"].iloc[0]) if bg_age in plot["age"].values else None
                if bg_nw and bg_amount > 0:
                    fig.add_annotation(
                        x=bg_age, y=bg_nw,
                        text=f"Best year<br>{_fmt_delta(bg_amount)} ({bg_pct:.0f}%)",
                        showarrow=True, arrowhead=2, arrowcolor=colour,
                        ax=30, ay=-40,
                        font=dict(size=10, color=colour),
                        bgcolor="white",
                        bordercolor=colour, borderwidth=1, borderpad=3,
                    )

        lat_age = float(plot["age"].iloc[-1])
        lat_nw  = float(plot["net_worth"].iloc[-1])

        if show_crosshair and show_annotations:
            fig.add_vline(x=lat_age,
                line=dict(color=colour, width=1.5, dash="dash"),
                annotation_text=f"{name.split()[0]} (age {lat_age:.1f})",
                annotation_position="top",
                annotation=dict(font=dict(color=colour, size=11),
                    bgcolor="white", bordercolor=colour, borderwidth=1, borderpad=4),
            )
        if show_horiz and lat_nw > 0 and not log_scale and show_annotations:
            fig.add_hline(y=lat_nw,
                line=dict(color=colour, width=1, dash="dot"),
                annotation_text=_fmt(lat_nw),
                annotation_position="right",
                annotation=dict(font=dict(color=colour, size=11), bgcolor="white", borderpad=3),
            )

    if personal_plot_df is not None and len(personal_plot_df) > 0:
        _add_personal_trace(personal_plot_df, COLOURS["person"], "Your net worth",
                            show_crosshair=True, show_horiz=True)

    if partner_plot_df is not None and len(partner_plot_df) > 0:
        _add_personal_trace(partner_plot_df, COLOURS["partner"], "Partner",
                            show_crosshair=True, show_horiz=False)

    # Age band boundary lines
    for x_val in [24, 34, 44, 54, 64, 74]:
        fig.add_vline(x=x_val + 0.5, line=dict(color="#e2e8f0", width=1, dash="dot"))

    # Percentile end-of-chart labels (right edge)
    if not log_scale and show_annotations:
        for pct_data, label in [(p25, "P25"), (p50, "P50"), (p75, "P75")]:
            edge_row = pct_data[pct_data["age"] == age_max] if age_max in pct_data["age"].values \
                       else pct_data[pct_data["age"] == pct_data["age"].max()]
            if len(edge_row):
                fig.add_annotation(
                    x=age_max, y=float(edge_row["value"].iloc[0]),
                    text=label, showarrow=False,
                    xanchor="left", xshift=5,
                    font=dict(size=10, color="#64748b"),
                )

    # Birth year label (cohort context) — at the user's latest age
    if latest_age is not None and show_annotations:
        birth_year = round(2025 - latest_age)
        fig.add_annotation(
            x=latest_age, yref="paper", y=-0.09,
            text=f"born ~{birth_year}",
            showarrow=False,
            font=dict(size=9, color="#94a3b8"),
            xanchor="center",
        )

    price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"

    yaxis_cfg = dict(
        title=f"Net worth (£, {price_label})" + (" — log scale" if log_scale else ""),
        type="log" if log_scale else "linear",
        tickprefix="£",
        **({} if log_scale else {"tickformat": ",.0f", "zeroline": True, "zerolinecolor": "#cbd5e1"}),
        gridcolor="#e2e8f0", showgrid=True,
    )

    component_suffix = f" · {wealth_component} wealth only" if wealth_component != "Total" else ""
    fig.update_layout(
        title=dict(
            text=f"UK net worth distribution — {basis.lower()} basis, {price_label}{component_suffix}",
            font=dict(size=17, color="#1e293b"), x=0,
        ),
        xaxis=dict(title="Age", range=[age_min - 0.5, age_max + 0.5],
                   dtick=5, gridcolor="#e2e8f0", showgrid=True, zeroline=False),
        yaxis=yaxis_cfg,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=12)),
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
        height=max(380, 560 - max(0, (85 - (age_max - age_min)) * 2)),  # taller when zoomed in
        margin=dict(l=70, r=90, t=80, b=60),
    )
    return fig


# ── Percentile trajectory chart ───────────────────────────────────────────────

def build_percentile_chart(
    traj_you: pd.DataFrame,
    traj_partner: pd.DataFrame | None = None,
    smooth: bool = False,
) -> go.Figure:
    fig = go.Figure()

    for y_val, label in [(75, "P75"), (50, "Median"), (25, "P25")]:
        fig.add_hline(y=y_val, line=dict(color="#93c5fd", width=1, dash="dot"),
            annotation_text=label, annotation_position="right",
            annotation=dict(font=dict(color="#64748b", size=10), bgcolor="rgba(0,0,0,0)"),
        )

    def _add_traj(traj: pd.DataFrame, colour: str, name: str, fill: bool = False):
        if smooth and len(traj) >= 4:
            traj = traj.copy()
            traj["percentile"] = traj["percentile"].rolling(
                max(3, len(traj)//4), center=True, min_periods=1
            ).mean()
        fig.add_trace(go.Scatter(
            x=traj["age"], y=traj["percentile"],
            mode="lines+markers",
            line=dict(color=colour, width=2.5),
            marker=dict(color=colour, size=7, line=dict(color="white", width=1.5)),
            fill="tozeroy" if fill else None,
            fillcolor="rgba(249,115,22,0.07)" if fill else None,
            name=name,
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Age %{x:.1f}<br>~%{y:.0f}th percentile<br>"
                "Net worth: £%{customdata:,.0f}<extra></extra>"
            ),
            customdata=traj["net_worth"],
        ))

    _add_traj(traj_you, COLOURS["person"], "You", fill=True)
    if traj_partner is not None and len(traj_partner) >= 2:
        _add_traj(traj_partner, COLOURS["partner"], "Partner")

    # Delta annotation for "you"
    if len(traj_you) >= 2:
        start_pct = float(traj_you.iloc[0]["percentile"])
        end_pct   = float(traj_you.iloc[-1]["percentile"])
        delta_pct = end_pct - start_pct
        sign = "+" if delta_pct >= 0 else ""
        fig.add_annotation(
            x=float(traj_you.iloc[-1]["age"]), y=end_pct,
            text=f"{sign}{delta_pct:.0f} pts",
            showarrow=True, arrowhead=2, arrowcolor=COLOURS["person"],
            ax=30, ay=-25 if delta_pct >= 0 else 25,
            font=dict(size=11, color=COLOURS["person"]),
            bgcolor="white", bordercolor=COLOURS["person"], borderwidth=1, borderpad=3,
        )

    # Percentile band shading (background zones)
    band_fills = [
        (0,  25, "rgba(219,234,254,0.3)", "Below P25"),
        (25, 50, "rgba(191,219,254,0.3)", "P25–P50"),
        (50, 75, "rgba(147,197,253,0.3)", "P50–P75"),
        (75, 100,"rgba(96,165,250,0.3)",  "Above P75"),
    ]
    for y0, y1, fill_col, band_name in band_fills:
        fig.add_hrect(y0=y0, y1=y1, fillcolor=fill_col, line_width=0,
                      annotation_text=band_name if y1 == 100 else "",
                      annotation_position="right",
                      annotation=dict(font=dict(size=9, color="#94a3b8")))

    fig.update_layout(
        title=dict(text="Estimated percentile over time", font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", dtick=5, zeroline=False),
        yaxis=dict(title="Percentile", range=[0, 100], dtick=25,
                   ticksuffix="th", gridcolor="#e2e8f0"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=290, margin=dict(l=60, r=80, t=50, b=50),
        hovermode="x unified",
    )
    return fig


# ── Wealth velocity chart ────────────────────────────────────────────────────

def build_velocity_chart(pdf: pd.DataFrame, colour: str) -> go.Figure:
    """Rolling % growth rate per period — shows acceleration/deceleration."""
    s = pdf.sort_values("age").copy()
    s["pct_change"] = s["net_worth"].pct_change() * 100
    s = s.dropna(subset=["pct_change"])
    if len(s) < 2:
        return None

    bar_colours = [colour if v >= 0 else "#ef4444" for v in s["pct_change"]]
    fig = go.Figure(go.Bar(
        x=s["age"], y=s["pct_change"],
        marker_color=bar_colours,
        hovertemplate="<b>Age %{x:.1f}</b><br>%{y:.1f}% growth<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color="#94a3b8", width=1))
    fig.update_layout(
        title=dict(text="Wealth velocity (% growth per period)", font=dict(size=13, color="#1e293b"), x=0),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(title="% change", ticksuffix="%", gridcolor="#e2e8f0"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=200, margin=dict(l=60, r=20, t=40, b=40),
        showlegend=False,
    )
    return fig


# ── Annual gain bar chart ────────────────────────────────────────────────────

def build_gains_chart(pdf: pd.DataFrame, colour: str, name: str) -> go.Figure:
    s = pdf.sort_values("age").copy()
    s["gain"] = s["net_worth"].diff()
    s["pct_gain"] = s["net_worth"].pct_change() * 100
    s = s.dropna(subset=["gain"])

    bar_colours = [colour if g >= 0 else "#ef4444" for g in s["gain"]]

    fig = go.Figure(go.Bar(
        x=s["age"], y=s["gain"],
        marker_color=bar_colours,
        name=name,
        hovertemplate=(
            "<b>Age %{x:.1f}</b><br>"
            "Gain: £%{y:,.0f}<br>"
            "Change: %{customdata:.1f}%<extra></extra>"
        ),
        customdata=s["pct_gain"],
    ))
    fig.add_hline(y=0, line=dict(color="#94a3b8", width=1))
    fig.update_layout(
        title=dict(text=f"Net worth change per period — {name}", font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(title="Change (£)", tickprefix="£", tickformat=",.0f", gridcolor="#e2e8f0"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=240, margin=dict(l=70, r=40, t=50, b=50),
        showlegend=False,
    )
    return fig


# ── What-if projection ────────────────────────────────────────────────────────

def build_whatif_figure(
    pdf: pd.DataFrame, benchmark: pd.DataFrame,
    scenarios: list[tuple[float, str]],   # [(cagr, label), ...]
    project_to_age: int,
    colour: str,
    monthly_savings: float = 0.0,
) -> go.Figure:
    """Forward-project net worth under one or more CAGR scenarios, optionally with monthly contributions."""
    s = pdf.sort_values("age")
    latest_age = float(s.iloc[-1]["age"])
    latest_nw  = float(s.iloc[-1]["net_worth"])
    proj_ages  = np.arange(latest_age, project_to_age + 1, 1.0)

    fig = go.Figure()

    p25 = benchmark[benchmark["percentile"] == "p25"].sort_values("age")
    p50 = benchmark[benchmark["percentile"] == "p50"].sort_values("age")
    p75 = benchmark[benchmark["percentile"] == "p75"].sort_values("age")

    fig.add_trace(go.Scatter(
        x=pd.concat([p25["age"], p75["age"].iloc[::-1]]),
        y=pd.concat([p25["value"], p75["value"].iloc[::-1]]),
        fill="toself", fillcolor="rgba(147,197,253,0.15)",
        line=dict(width=0), name="P25–P75 range", hoverinfo="skip",
    ))
    for pct_data, dash, label in [(p25,"dash","P25"),(p50,"solid","Median"),(p75,"dash","P75")]:
        fig.add_trace(go.Scatter(
            x=pct_data["age"], y=pct_data["value"], mode="lines",
            line=dict(color="#93c5fd" if label != "Median" else "#1d4ed8",
                      width=2 if label != "Median" else 3, dash=dash),
            name=label, hovertemplate=f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>",
        ))

    # Historical personal data
    fig.add_trace(go.Scatter(
        x=s["age"], y=s["net_worth"], mode="lines+markers",
        line=dict(color=colour, width=2.5),
        marker=dict(color=colour, size=7, line=dict(color="white", width=1.5)),
        name="Actual", hovertemplate="<b>Actual</b><br>Age %{x:.1f}<br>£%{y:,.0f}<extra></extra>",
    ))

    # One trace per scenario
    scenario_colours = ["#f97316", "#8b5cf6", "#06b6d4"]  # orange, violet, cyan
    annual_saving = monthly_savings * 12
    for i, (cagr, sc_label) in enumerate(scenarios):
        proj_nw = []
        for a in proj_ages:
            t = a - latest_age
            if abs(cagr) < 1e-10:
                proj_nw.append(latest_nw + annual_saving * t)
            else:
                proj_nw.append(
                    latest_nw * (1 + cagr) ** t
                    + annual_saving * ((1 + cagr) ** t - 1) / cagr
                )
        fig.add_trace(go.Scatter(
            x=proj_ages, y=proj_nw, mode="lines",
            line=dict(color=scenario_colours[i % len(scenario_colours)], width=2,
                      dash="dash" if i > 0 else "solid"),
            name=sc_label,
            hovertemplate=f"<b>{sc_label}</b><br>Age %{{x:.1f}}<br>£%{{y:,.0f}}<extra></extra>",
        ))

    sc_title = " vs ".join(f"{c*100:.1f}%" for c, _ in scenarios)
    contrib_note = (f"+£{monthly_savings:,.0f}/mo contributions"
                    if monthly_savings > 0 else "no further contributions")
    price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"
    fig.update_layout(
        title=dict(text=f"What-if: {sc_title} CAGR from age {latest_age:.1f}  "
                        f"<span style='font-size:11px;color:#64748b'>· {contrib_note}</span>",
                   font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", range=[15, project_to_age + 1], dtick=5,
                   gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(title=f"Net worth (£, {price_label})", tickprefix="£",
                   tickformat=",.0f", gridcolor="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        height=400, margin=dict(l=70, r=40, t=60, b=60), hovermode="x unified",
    )
    return fig


# ── Cumulative wealth chart ───────────────────────────────────────────────────

def build_cumulative_chart(
    pdf: pd.DataFrame, colour: str, name: str,
    partner_pdf: pd.DataFrame | None = None,
) -> go.Figure:
    """Area chart showing net worth level over age — pure cumulative view."""
    fig = go.Figure()

    def _hex_rgba(hex_col: str, alpha: float = 0.12) -> str:
        h = hex_col.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    def _add(df, col, nm, fill_mode):
        s = df.sort_values("age")
        fig.add_trace(go.Scatter(
            x=s["age"], y=s["net_worth"],
            mode="lines+markers",
            line=dict(color=col, width=2.5),
            marker=dict(color=col, size=6),
            fill=fill_mode,
            fillcolor=_hex_rgba(col) if col.startswith("#") else col,
            name=nm,
            hovertemplate=f"<b>{nm}</b><br>Age %{{x:.1f}}<br>£%{{y:,.0f}}<extra></extra>",
        ))

    _add(pdf, colour, name, "tozeroy")
    if partner_pdf is not None and len(partner_pdf) >= 2:
        _add(partner_pdf, COLOURS["partner"], "Partner", "tozeroy")

    price_lbl = f"{REAL_BASE_YEAR} real" if real_terms else f"nominal {DATA_YEAR}"
    fig.update_layout(
        title=dict(text=f"Net worth over time ({price_lbl})",
                   font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", zeroline=False),
        yaxis=dict(title="Net worth (£)", tickprefix="£", tickformat=",.0f",
                   gridcolor="#e2e8f0"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=260, margin=dict(l=70, r=40, t=50, b=50),
        hovermode="x unified",
    )
    return fig


# ── Data quality score ────────────────────────────────────────────────────────

def compute_data_quality(pdf: pd.DataFrame) -> dict:
    """Rate the personal data on completeness and consistency (0-100 score)."""
    n = len(pdf)
    age_span = float(pdf["age"].max() - pdf["age"].min()) if n >= 2 else 0
    avg_gap  = age_span / (n - 1) if n >= 2 else 999

    score = 0
    notes = []

    if n >= 10:    score += 30; notes.append("✅ 10+ data points")
    elif n >= 5:   score += 20; notes.append("🟡 5–9 data points (10+ recommended)")
    elif n >= 2:   score += 10; notes.append("⚠️ Only 2–4 data points")
    else:          notes.append("❌ Need at least 2 data points")

    if "year" in pdf.columns:
        max_year = int(pdf["year"].max())
        if max_year >= 2024:   score += 25; notes.append("✅ Data up to 2024/25")
        elif max_year >= 2022: score += 15; notes.append("🟡 Data to 2022–23 — add recent figures")
        else:                  score += 5;  notes.append("⚠️ Data older than 2022")

    if avg_gap <= 1.5:  score += 25; notes.append("✅ Annual or more frequent updates")
    elif avg_gap <= 3:  score += 15; notes.append("🟡 Updates every 1–3 years")
    else:               score += 5;  notes.append("⚠️ Infrequent updates (gaps > 3 yrs)")

    if age_span >= 10:  score += 20; notes.append("✅ 10+ year history")
    elif age_span >= 5: score += 12; notes.append("🟡 5–9 year history")
    else:               score += 5;  notes.append("⚠️ Less than 5 years of history")

    return {"score": min(score, 100), "notes": notes, "n": n, "span": age_span}


# ── Percentile heatmap ───────────────────────────────────────────────────────

def build_heatmap(benchmark: pd.DataFrame) -> go.Figure:
    """
    Colour-coded grid: age (x) × net worth level (y), shaded by which
    percentile band the cell falls in. Gives an instant read of the
    wealth landscape across all ages.
    """
    from utils.inference import derive_tail_percentiles

    tails = derive_tail_percentiles(benchmark)
    all_bm = pd.concat([benchmark, tails]).copy()

    ages = sorted(all_bm["age"].unique())
    pct_levels = ["p10", "p25", "p50", "p75", "p90"]
    labels     = ["10th", "25th", "50th (median)", "75th", "90th"]
    colours    = ["#eff6ff", "#bfdbfe", "#93c5fd", "#3b82f6", "#1d4ed8"]

    fig = go.Figure()

    prev_vals = None
    for i, (pct, label, colour) in enumerate(zip(pct_levels, labels, colours)):
        pct_data = all_bm[all_bm["percentile"] == pct].sort_values("age")
        if len(pct_data) == 0:
            continue
        curr_vals = [float(pct_data[pct_data["age"] == a]["value"].iloc[0])
                     if len(pct_data[pct_data["age"] == a]) > 0 else None for a in ages]

        if prev_vals:
            fig.add_trace(go.Scatter(
                x=list(ages) + list(reversed(ages)),
                y=curr_vals + list(reversed(prev_vals)),
                fill="toself",
                fillcolor=colour,
                line=dict(width=0),
                name=label,
                hoverinfo="skip",
                showlegend=True,
            ))
        prev_vals = curr_vals

    # User's trajectory
    if personal_plot_df is not None and len(personal_plot_df) > 0:
        pdf = personal_plot_df.sort_values("age")
        fig.add_trace(go.Scatter(
            x=pdf["age"], y=pdf["net_worth"],
            mode="lines+markers",
            line=dict(color=COLOURS["person"], width=2.5),
            marker=dict(color=COLOURS["person"], size=7),
            name="Your net worth",
            hovertemplate="Age %{x:.1f}<br>£%{y:,.0f}<extra></extra>",
        ))

    price_note = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR})"
    fig.update_layout(
        title=dict(text=f"Wealth percentile landscape by age ({price_note})",
                   font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", range=[15, 86], dtick=5, gridcolor="#e2e8f0"),
        yaxis=dict(title=f"Net worth (£)", tickprefix="£", tickformat=",.0f",
                   gridcolor="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=11)),
        plot_bgcolor="white", paper_bgcolor="white",
        height=380, margin=dict(l=70, r=40, t=60, b=50),
        hovermode="x unified",
    )
    return fig


# ── Distribution histogram at user's age ─────────────────────────────────────

def build_distribution_chart(
    age: int, benchmark: pd.DataFrame,
    user_nw: float | None = None,
    partner_nw: float | None = None,
) -> go.Figure | None:
    """
    Simulate the log-normal wealth distribution at a given age and plot it as a
    density curve, with vertical lines for P25/P50/P75 and the user's position.
    """
    from scipy.stats import norm as _norm, lognorm as _lognorm

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

    mu    = np.log(p50v)
    sigma = (np.log(p75v) - np.log(p25v)) / (2 * 0.6745)

    # X range: P2 to P98
    x_min = float(np.exp(mu + _norm.ppf(0.02) * sigma))
    x_max = float(np.exp(mu + _norm.ppf(0.98) * sigma))
    x = np.linspace(max(x_min, 1), x_max, 500)
    pdf = _lognorm.pdf(x, s=sigma, scale=np.exp(mu))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=pdf, mode="lines",
        line=dict(color="#93c5fd", width=2),
        fill="tozeroy", fillcolor="rgba(147,197,253,0.15)",
        name="Distribution", hoverinfo="skip",
    ))

    for val, label, colour in [
        (p25v, "P25", "#93c5fd"), (p50v, "Median", "#1d4ed8"), (p75v, "P75", "#93c5fd")
    ]:
        fig.add_vline(x=val, line=dict(color=colour, width=1.5, dash="dot"),
            annotation_text=f"{label} {_fmt(val)}", annotation_position="top",
            annotation=dict(font=dict(size=10, color=colour)),
        )

    if user_nw and user_nw > 0:
        user_pct = _lognorm.cdf(user_nw, s=sigma, scale=np.exp(mu)) * 100
        fig.add_vline(x=user_nw, line=dict(color=COLOURS["person"], width=2.5),
            annotation_text=f"You {_fmt(user_nw)} (~{user_pct:.0f}th)",
            annotation_position="top right",
            annotation=dict(font=dict(size=11, color=COLOURS["person"]),
                            bgcolor="white", borderpad=3),
        )
    if partner_nw and partner_nw > 0:
        fig.add_vline(x=partner_nw, line=dict(color=COLOURS["partner"], width=2.5),
            annotation_text=f"Partner {_fmt(partner_nw)}",
            annotation_position="top left",
            annotation=dict(font=dict(size=11, color=COLOURS["partner"]),
                            bgcolor="white", borderpad=3),
        )

    price_note = f"{REAL_BASE_YEAR} real" if real_terms else f"nominal {DATA_YEAR}"
    fig.update_layout(
        title=dict(text=f"Wealth distribution at age {age_clamped} ({price_note})",
                   font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title=f"Net worth (£, {price_note})", tickprefix="£", tickformat=",.0f",
                   gridcolor="#e2e8f0"),
        yaxis=dict(title="Probability density", showticklabels=False, gridcolor="#e2e8f0"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=300, margin=dict(l=60, r=60, t=50, b=50),
        showlegend=False,
    )
    return fig


# ── Asset class chart ─────────────────────────────────────────────────────────

def build_asset_class_chart(series: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for component in ["Physical", "Financial", "Pension", "Property"]:
        sub = series[series["component"] == component].sort_values("age")
        fig.add_trace(go.Scatter(
            x=sub["age"], y=sub["value_gbp"],
            mode="lines", stackgroup="one", name=component,
            line=dict(width=0.5, color=ASSET_COLOURS[component]),
            hovertemplate=(
                f"<b>{component}</b><br>Age %{{x}}<br>"
                "£%{y:,.0f} (~%{customdata:.0f}%)<extra></extra>"
            ),
            customdata=sub["value_pct"],
        ))
    fig.update_layout(
        title=dict(text="Median wealth composition by age (approx, WAS Wave 7)",
                   font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", dtick=5, zeroline=False),
        yaxis=dict(title="Net worth (£, nominal 2019)", tickprefix="£",
                   tickformat=",.0f", gridcolor="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        height=320, margin=dict(l=70, r=80, t=60, b=50), hovermode="x unified",
    )
    return fig


# ── Summary statistics table ──────────────────────────────────────────────────

def build_summary_stats(
    pdf: pd.DataFrame, bm: pd.DataFrame, label: str = "You"
) -> pd.DataFrame:
    s = pdf.sort_values("age")
    first, last = s.iloc[0], s.iloc[-1]
    age_span = float(last["age"]) - float(first["age"])
    nw_start = float(first["net_worth"])
    nw_end   = float(last["net_worth"])

    rows: list[dict] = [
        {"Metric": f"{label} — age range",       "Value": f"{first['age']:.1f} → {last['age']:.1f}  ({age_span:.1f} yrs)"},
        {"Metric": f"{label} — net worth range",  "Value": f"{_fmt(nw_start)} → {_fmt(nw_end)}"},
        {"Metric": f"{label} — total change",     "Value": _fmt_delta(nw_end - nw_start)},
    ]

    cagr = _safe_cagr(nw_start, nw_end, age_span)
    if cagr is not None:
        rows.append({"Metric": f"{label} — CAGR", "Value": f"{cagr*100:+.2f}%"})

    best = _best_gain(s)
    if best:
        bg_age, bg_amt, bg_pct = best
        rows.append({"Metric": f"{label} — best single gain",
                     "Value": f"{_fmt_delta(bg_amt)} ({bg_pct:+.0f}%) at age {bg_age:.1f}"})

    worst_idx = s["net_worth"].diff().idxmin()
    if worst_idx is not None and not pd.isna(worst_idx):
        wl = float(s["net_worth"].diff()[worst_idx])
        wa = float(s.loc[worst_idx, "age"])
        rows.append({"Metric": f"{label} — worst single change",
                     "Value": f"{_fmt_delta(wl)} at age {wa:.1f}"})

    pct = estimate_exact_percentile(nw_end, round(float(last["age"])), bm)
    if pct:
        rows.append({"Metric": f"{label} — latest est. percentile", "Value": f"~{pct:.0f}th"})

    return pd.DataFrame(rows)


# ── Main content ──────────────────────────────────────────────────────────────

col_hdr, col_badge = st.columns([5, 1])
with col_hdr:
    st.title("UK Net Worth Benchmarker")
    st.caption(
        "Compare your net worth against UK population distributions by age · "
        "ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain"
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

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Your latest age", f"{latest_age:.1f}")
    with col2:
        st.metric("Net worth", _fmt(latest_nw), delta=delta_str,
                  help=f"In {price_note}. Delta vs previous data point.")
    with col3:
        if exact_pct:
            st.metric("Est. percentile", f"~{exact_pct:.0f}th",
                      help="Log-normal fit to P25/P50/P75. Indicative only.")
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
        if p50v and p75v:
            # Age-adjusted relative wealth: net_worth / benchmark_median (index = 100 at median)
            if p50v > 0:
                rel_wealth = latest_nw / p50v * 100
                st.metric(
                    "Rel. wealth index",
                    f"{rel_wealth:.0f}",
                    help="Your net worth as a % of the benchmark median at your age. "
                         "100 = exactly at median. Age-adjusted so it's comparable across ages.",
                )
            if latest_nw < p50v:
                st.metric("Gap to median", _fmt(p50v - latest_nw))
            elif latest_nw < p75v:
                st.metric("Gap to P75", _fmt(p75v - latest_nw))
            else:
                st.metric("Above P75 by", _fmt(latest_nw - p75v))

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
                                f"£{_CAGR_MIN_START:,} would inflate the rate."
                                if first_nw < _CAGR_MIN_START and first_nw > 0
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
        f"places you {'at approximately the **' + str(round(exact_pct)) + 'th percentile**' if exact_pct else '**' + band_desc + '**'} "
        f"on a {basis.lower()} basis in the UK."
        + (f" That's {multiples_str} at your age." if multiples_str else "")
        + (f" (Up {_fmt(delta_val)} from previous.)" if delta_val and delta_val > 0 else
           f" (Down {_fmt(abs(delta_val))} from previous.)" if delta_val and delta_val < 0 else "")
    )

    # Monthly savings micro-calculator
    with st.expander("Quick calculator: monthly savings impact"):
        st.caption("How much would saving an extra amount per month add to your net worth?")
        mc_cols = st.columns(3)
        with mc_cols[0]:
            extra_monthly = st.number_input("Extra monthly saving (£)", 0, 10_000, 200, 50, key="mc_monthly")
        with mc_cols[1]:
            mc_return  = st.number_input("Annual return (%)", 0.0, 15.0, 5.0, 0.5, key="mc_return")
        with mc_cols[2]:
            mc_years   = st.number_input("Years", 1, 50, 10, 1, key="mc_years")
        if extra_monthly > 0:
            # FV of annuity: PMT * [(1+r)^n - 1] / r  where r = monthly rate
            r = (mc_return / 100) / 12
            n = mc_years * 12
            fv = extra_monthly * ((1 + r) ** n - 1) / r if r > 0 else extra_monthly * n
            total_paid = extra_monthly * n
            st.metric(
                f"Future value in {mc_years} yrs",
                _fmt(fv),
                delta=f"+{_fmt(fv - total_paid)} from returns",
                help=f"£{total_paid:,.0f} contributed; £{fv - total_paid:,.0f} from compound returns."
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
                    if first_nw > 0:
                        cagr_cur = (latest_nw / first_nw) ** (1 / age_span) - 1
                        if cagr_cur > 0.001:
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
                                               f"(CAGR unavailable — started from zero or negative.)")

# Log scale warning
if log_scale and personal_plot_df is not None and (personal_plot_df["net_worth"] <= 0).any():
    st.warning(f"{(personal_plot_df['net_worth']<=0).sum()} data point(s) hidden on log scale.", icon="⚠️")

# ── IHT / estate tax calculator ───────────────────────────────────────────────

if personal_plot_df is not None and latest_nw is not None and latest_nw > 0:
    with st.expander("Estate / inheritance tax (IHT) exposure"):
        st.caption(
            "Estimates your approximate UK inheritance tax (IHT) liability based on your current "
            "net worth. Indicative only — not tax advice. Rules as of 2024/25."
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

        _iht_band = {
            "Single — £325k NRB": 325_000,
            "Single + RNRB — £500k (residence to descendants)": 500_000,
            "Married / civil partner — £650k (2× NRB, no RNRB)": 650_000,
            "Married + RNRB — £1m (2× NRB + 2× RNRB)": 1_000_000,
        }[iht_threshold]

        gross_estate   = latest_nw
        exempt_amount  = _iht_band + iht_deductions
        taxable_estate = max(0, gross_estate - exempt_amount)
        iht_payable    = taxable_estate * (iht_rate_pct / 100)
        after_iht      = gross_estate - iht_payable
        pct_lost       = iht_payable / gross_estate * 100 if gross_estate > 0 else 0

        iht_m1, iht_m2, iht_m3, iht_m4 = st.columns(4)
        with iht_m1:
            st.metric("Gross estate", _fmt(gross_estate))
        with iht_m2:
            st.metric("IHT-exempt", _fmt(exempt_amount),
                      help=f"Threshold ({_fmt(_iht_band)}) + deductions ({_fmt(iht_deductions)})")
        with iht_m3:
            st.metric("IHT payable", _fmt(iht_payable),
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
                f"life insurance in trust, pension wealth (outside estate), charitable giving."
            )
        st.caption(
            "Simplified estimate — does not account for taper relief, business/agricultural property relief, "
            "in-trust assets, lifetime gifts, or other exemptions. Consult a qualified advisor."
        )

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

# ── Main chart ────────────────────────────────────────────────────────────────

fig = build_main_figure(
    log_scale, show_tails, show_milestones, show_annotations,
    age_min, age_max,
    latest_age, latest_nw, partner_latest_age,
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

if wealth_component != "Total":
    st.info(
        f"Viewing **{wealth_component} wealth** component only. "
        "Benchmark scaled by approximate WAS Wave 7 asset class shares (derived). "
        "Your personal net worth overlay shows **total** net worth — "
        "enter your composition split in the sidebar for per-component context.",
        icon="ℹ️",
    )
elif basis == "Individual":
    st.caption("Individual figures are derived — see methodology panel.")
else:
    st.caption(
        "Filled circles = ONS published data (ages 20,30,40,50,60,70,80). "
        "Lines are PCHIP-interpolated. Dotted verticals = age-band boundaries."
    )

# ── Percentile heatmap ───────────────────────────────────────────────────────

with st.expander("Percentile landscape heatmap"):
    hm_fig = build_heatmap(benchmark)
    st.plotly_chart(hm_fig, use_container_width=True, config=PLOTLY_CONFIG)
    st.caption(
        "Shaded bands show which percentile tier each wealth level belongs to at each age. "
        "P10 and P90 are derived from the log-normal model; P25/P50/P75 are from WAS. "
        "Your trajectory is overlaid in orange."
    )

# ── Share link ────────────────────────────────────────────────────────────────

if personal_plot_df is not None and len(personal_plot_df) > 0:
    with st.expander("Share your chart"):
        try:
            token = encode_personal_data(personal_plot_df)
            share_url = f"https://uk-networth-benchmarker.streamlit.app/?d={token}"
            st.text_input(
                "Copy this link (data encoded in the URL — nothing stored on any server):",
                value=share_url, key="share_url_box",
            )
            st.caption("Anyone with this link can see your figures. Share only with people you trust.")
        except Exception:
            st.info("Share link unavailable — data may be too large to encode.")

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
    dist_fig = build_distribution_chart(
        dist_age, benchmark,
        user_nw=latest_nw if dist_age == dist_age_default else None,
        partner_nw=p_nw_for_dist if dist_age == dist_age_default else None,
    )
    if dist_fig:
        st.plotly_chart(dist_fig, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption(
            "Slide to explore the distribution at any age. "
            "Your net worth is shown only at your latest recorded age. "
            "Distribution simulated from log-normal model fitted to P25/P50/P75 — "
            "tails above P90 are extrapolated."
        )

# ── Percentile trajectory chart ───────────────────────────────────────────────

if personal_plot_df is not None and len(personal_plot_df) >= 2:
    traj_you = build_percentile_trajectory(personal_plot_df, benchmark)
    traj_partner = None
    if partner_plot_df is not None and len(partner_plot_df) >= 2:
        traj_partner = build_percentile_trajectory(partner_plot_df, benchmark)
    if len(traj_you) >= 2:
        st.plotly_chart(
            build_percentile_chart(traj_you, traj_partner, smooth=smooth_traj),
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
        st.plotly_chart(
            build_gains_chart(personal_plot_df, COLOURS["person"], "Your net worth"),
            use_container_width=True, config=PLOTLY_CONFIG,
        )
        if partner_plot_df is not None and len(partner_plot_df) >= 2:
            st.plotly_chart(
                build_gains_chart(partner_plot_df, COLOURS["partner"], "Partner"),
                use_container_width=True, config=PLOTLY_CONFIG,
            )
        st.caption("Red bars = net worth fell that period. Each bar spans the gap between consecutive data points.")

        # Velocity (% rate) chart
        vel = build_velocity_chart(personal_plot_df, COLOURS["person"])
        if vel:
            st.plotly_chart(vel, use_container_width=True, config=PLOTLY_CONFIG)
        if partner_plot_df is not None and len(partner_plot_df) >= 3:
            vel_p = build_velocity_chart(partner_plot_df, COLOURS["partner"])
            if vel_p:
                st.plotly_chart(vel_p, use_container_width=True, config=PLOTLY_CONFIG)

        # Cumulative view
        st.plotly_chart(
            build_cumulative_chart(personal_plot_df, COLOURS["person"], "You", partner_plot_df),
            use_container_width=True, config=PLOTLY_CONFIG,
        )

        # Growth attribution
        st.markdown("**Growth attribution (rough estimate)**")
        assumed_return = st.slider("Assumed annual investment return (%)", 0.0, 12.0, 5.0, 0.5,
                                   key="attr_return",
                                   help="What % would a passive investment have returned? ~5% is a common real-return assumption.")
        s_attr = personal_plot_df.sort_values("age")
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
            build_whatif_figure(personal_plot_df, benchmark, scenarios, wi_age, COLOURS["person"],
                                monthly_savings=wi_monthly),
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

# ── Asset class breakdown chart ───────────────────────────────────────────────

if show_asset_class:
    asset_series = build_asset_class_series(_load_asset_classes(), benchmark, AGE_RANGE)
    if len(asset_series):
        ac_fig = build_asset_class_chart(asset_series)

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
            "Benchmark: approximate WAS Wave 7 component shares at the median. "
            "Your composition (if entered) shown as horizontal lines. "
            "Property = net of mortgage · Pension = private (DB PV + DC) · "
            "Financial = savings/investments net of non-mortgage debt · Physical = vehicles/contents/valuables."
        )

# ── Methodology panel ─────────────────────────────────────────────────────────

with st.expander("Methodology and data sources", expanded=False):
    st.markdown(f"""
### Data source

**ONS Wealth and Assets Survey (WAS), Wave 7 (2018–2020)**, Great Britain (~20,000 households).

> **Transparency note:** Figures in `data/was_data.csv` are approximations of the published
> WAS percentile tables. For research use, consult
> [ons.gov.uk](https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/bulletins/wealthingreatbritainwave7/2018to2020) directly.

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

Component shares (property/pension/financial/physical) are approximate WAS Wave 7 proportions
at the median, interpolated to single years and normalised. £ values = share × P50.
All derived — not published WAS component tables.

### P10 / P90

Derived from the same log-normal model: `value = exp(mu + z×sigma)` where z = Phi⁻¹(0.10/0.90).

### Privacy

All personal data lives in browser session state or URL query params only.
No data is transmitted to or stored on any server.

### Regional variation

WAS publishes regional breakdowns but this tool currently shows GB-wide figures only.
Wealth varies substantially by region — approximate median total wealth premiums vs GB median
(WAS Wave 7):

| Region | Approx. premium vs GB median |
|---|---|
| London | +30–40% |
| South East | +20–30% |
| East of England | +10–20% |
| South West | ±5% |
| East Midlands / West Midlands | −5 to −10% |
| Yorkshire / Humber | −10 to −15% |
| North West | −10 to −15% |
| North East | −20 to −25% |
| Wales | −15 to −20% |
| Scotland | −5 to +5% |

If you live in London or the South East, you are likely comparing against a benchmark
that understates your peers' wealth; in the North or Wales, it overstates it.
A region filter is planned for v2.

### Known limitations

- WAS excludes Northern Ireland; figures = Great Britain only.
- Very wealthy households (~top 1–2%) are under-represented; P75 is reliable, above P90 less so.
- Wave 7 predates 2021–2024 inflation/house-price movements; real-terms adjustment is partial.
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
                ax.set_title("Net worth vs UK distribution (ONS WAS Wave 7)", fontsize=11)
                fig.tight_layout(); return _save(fig)
            except Exception:
                return None

        def _mpl_trajectory(traj):
            try:
                fig, ax = _plt.subplots(figsize=(11, 3.8))
                for pct, lbl in [(25, "P25"), (50, "Median"), (75, "P75")]:
                    ax.axhline(pct, color="#93c5fd", lw=0.8, ls=":")
                    ax.text(float(traj["age"].iloc[0]), pct + 0.8, lbl,
                            fontsize=7.5, color="#64748b")
                ax.fill_between(traj["age"], traj["percentile"], alpha=0.12, color=_PC)
                ax.plot(traj["age"], traj["percentile"], _PC, lw=2, marker="o", ms=5)
                ax.set_ylim(0, 100); ax.set_xlabel("Age")
                ax.set_ylabel("Estimated percentile")
                ax.grid(True, alpha=0.25)
                ax.set_title("Percentile trajectory", fontsize=11)
                fig.tight_layout(); return _save(fig)
            except Exception:
                return None

        # Annual aggregation: last entry per calendar year, used by gains chart + summary
        if "year" in _s_rpt.columns:
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
                years  = (s["year"].iloc[1:].astype(int).values
                          if "year" in s.columns else s["age"].iloc[1:].values)
                colors = ["#1d4ed8" if g >= 0 else "#ef4444" for g in gains]
                fig, ax = _plt.subplots(figsize=(11, 3.5))
                ax.bar(years, gains, color=colors, width=0.6)
                ax.axhline(0, color="black", lw=0.5)
                ax.yaxis.set_major_formatter(_mtick.FuncFormatter(_gbp))
                ax.set_xlabel("Year"); ax.set_ylabel("Change")
                ax.grid(True, alpha=0.25, axis="y")
                ax.set_title("Year-on-year net worth change  (blue = gain, red = loss)", fontsize=11)
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

        main_png  = _mpl_benchmark()
        traj_png  = None
        if len(_s_rpt) >= 2:
            _ty = build_percentile_trajectory(personal_plot_df, benchmark)
            if len(_ty) >= 2:
                traj_png = _mpl_trajectory(_ty)
        gains_png  = _mpl_gains() if len(_s_rpt) >= 2 else None
        whatif_png = _mpl_whatif()

        # ── PDF helpers & layout ───────────────────────────────────────────────
        def _ordinal(n: int) -> str:
            n = int(n)
            if 11 <= (n % 100) <= 13:
                return f"{n}th"
            return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

        _ftxt = (
            f"UK Net Worth Benchmarker  |  ONS WAS Wave 7 (2018-2020)  |  "
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
            pdf.cell(0, 9, txt, ln=True)
            y0 = pdf.get_y()
            pdf.set_draw_color(*BLUE); pdf.line(15, y0, 195, y0)
            pdf.set_draw_color(0, 0, 0); pdf.ln(3); pdf.set_text_color(*SLATE)

        def H2(txt):
            pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(*SLATE)
            pdf.cell(0, 7, txt, ln=True)

        def KV(label, value, lw=70):
            pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*GREY)
            pdf.cell(lw, 6, label)
            pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*SLATE)
            pdf.cell(0, 6, str(value), ln=True)

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
        pdf.cell(0, 13, "UK Net Worth Benchmarker", align="C", ln=True)
        pdf.set_font("Helvetica", "", 13)
        pdf.cell(0, 8, "Personal Report", align="C", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(219, 234, 254)
        pdf.cell(0, 7, f"Generated {_today}  |  ONS WAS Wave 7 (2018-2020)", align="C", ln=True)
        pdf.set_text_color(*SLATE)
        pdf.set_y(62)

        # ── Hero: big net worth number ─────────────────────────────────────────
        pdf.set_font("Helvetica", "B", 34); pdf.set_text_color(*BLUE)
        pdf.cell(0, 18, _fmt(latest_nw), align="C", ln=True)
        pdf.set_font("Helvetica", "", 11); pdf.set_text_color(*GREY)
        pdf.cell(0, 7, f"Current net worth  |  Age {latest_age:.1f}", align="C", ln=True)
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
            pdf.cell(_bw, 8, val, align="C", ln=False)
            pdf.set_xy(bx, _stat_y + 10)
            pdf.set_font("Helvetica", "", 7); pdf.set_text_color(*GREY)
            pdf.cell(_bw, 6, lbl, align="C", ln=False)
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
            f"ONS WAS Wave 7 (2018-2020) wealth thresholds for UK {_basis_desc} aged "
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
                 "P10, P90: derived from log-normal model (indicative).", ln=True)
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
                pdf.cell(22, 4.5, ""); pdf.cell(0, 4.5, f"  Note: {note_d}", ln=True)
                pdf.set_text_color(*SLATE)

        # ── Page 4: Main chart ─────────────────────────────────────────────────
        pdf.add_page(); H1("Net worth vs UK distribution")
        SM(
            f"Your net worth plotted against the P25, median and P75 benchmarks for UK "
            f"{_basis_desc} at each age. The shaded band shows the interquartile range. "
            f"Lines are PCHIP-interpolated from ONS WAS Wave 7 (2018-2020) age-band data."
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
                    _yrs_col = "year" if "year" in _s_ann.columns else "age"
                    pdf.ln(5)
                    pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*BLUE)
                    pdf.cell(0, 6, "Summary statistics", ln=True)
                    pdf.set_draw_color(*BLUE)
                    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
                    pdf.ln(3); pdf.set_draw_color(0, 0, 0)
                    KV("Positive years:", f"{_pos} of {len(_gvals)}  ({100*_pos/len(_gvals):.0f}%)")
                    KV("Average annual gain:", _fmt_delta(float(_gvals.mean())))
                    if not pd.isna(_ibx):
                        KV("Best year:", f"{_fmt_delta(float(_gvals[_ibx]))}  "
                           f"({int(_s_ann.loc[_ibx, _yrs_col])})")
                    if not pd.isna(_iwx):
                        KV("Worst year:", f"{_fmt_delta(float(_gvals[_iwx]))}  "
                           f"({int(_s_ann.loc[_iwx, _yrs_col])})")
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
            pdf.cell(0, 6, f"Projected values at age {wi_age}:", ln=True)
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

        # ── Page 8: Goals (if set) ─────────────────────────────────────────────
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
                    pdf.cell(0, 5, f"{_fmt(latest_nw)} of {_fmt(tgt_v)}", ln=True)
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
                        pdf.cell(0, 6, "  Goal achieved!", ln=True)
                        pdf.set_text_color(*SLATE)

                if fire_number > 0:
                    _fi_pct = min(latest_nw/fire_number*100, 100)
                    pdf.ln(3); H2("Financial independence tracker")
                    pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*GREY)
                    pdf.cell(0, 5, f"{_fmt(latest_nw)} of {_fmt(fire_number)} FIRE target", ln=True)
                    pdf.ln(1); _pbar(_fi_pct, colour=(16, 185, 129))
                    KV("Sustainable spending at current NW:",
                       f"{_fmt(latest_nw/25/52)}/week  ({_fmt(latest_nw/25)}/yr)")
                    if fire_number > latest_nw:
                        KV("FIRE gap:", _fmt(fire_number - latest_nw))

        except (NameError, Exception): pass

        # ── Final page: Methodology & disclaimer ───────────────────────────────
        pdf.add_page()
        H1("Methodology & data sources")
        pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*SLATE)
        for para in [
            ("Benchmark data: ONS Wealth and Assets Survey (WAS) Wave 7, covering 2018 to 2020. "
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
             "It does not constitute financial advice. Benchmark data reflect 2018-2020 survey "
             "conditions and may not represent current wealth distributions."),
            ("Projections assume constant growth rates and do not account for tax, inflation, "
             "market volatility, or changes in personal circumstances. "
             "Past growth does not guarantee future returns."),
            ("Please consult a qualified financial adviser before making investment or "
             "retirement decisions."),
            ("Data: Office for National Statistics, Wealth and Assets Survey Wave 7. "
             "Reproduced under the Open Government Licence v3.0."),
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
                     help="Renders all active charts and assembles a multi-page PDF (~20 seconds)."):
            with st.spinner("Rendering charts and building PDF — this takes about 20 seconds..."):
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
        # Lightweight text report as fallback
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
        _lines += ["", f"## Benchmark at age {latest_age:.0f}"]
        for _pk, _pl in [("p25","P25"),("p50","Median"),("p75","P75")]:
            _v = _bm(_pk)
            if _v: _lines.append(f"- {_pl}: {_fmt(_v)}")
        _lines += ["", "---",
                   "Data: ONS WAS Wave 7 (2018-2020). Not financial advice."]
        st.download_button(
            "Download text report (.md)",
            "\n".join(_lines).encode(),
            f"networth_report_{_today}.md",
            "text/markdown",
            use_container_width=True,
        )

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
APP_VERSION = "v2.4"
st.markdown(
    f"<div style='text-align:center; color:#94a3b8; font-size:0.8rem;'>"
    f"UK Net Worth Benchmarker {APP_VERSION} · ONS WAS Wave 7 (2018–2020) · Streamlit + Plotly"
    f"</div>",
    unsafe_allow_html=True,
)
