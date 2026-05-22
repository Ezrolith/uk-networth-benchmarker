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
    interpolate_benchmarks, convert_to_individual,
    adjust_for_inflation, cpi_adjust_personal,
    estimate_percentile, estimate_exact_percentile,
    build_percentile_trajectory, derive_tail_percentiles,
    build_asset_class_series, build_decile_table,
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

COLOURS = {
    "p25":    "#93c5fd",
    "p50":    "#1d4ed8",
    "p75":    "#93c5fd",
    "band":   "rgba(147,197,253,0.18)",
    "pub":    "#1e40af",
    "person": "#f97316",   # orange
    "partner":"#10b981",   # emerald
}

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
def _build_benchmark(basis: str, include_pension: bool, real_terms: bool) -> pd.DataFrame:
    raw = _load_raw()
    filtered = raw[raw["with_pension"] == include_pension].copy()
    bm = interpolate_benchmarks(filtered, AGE_RANGE)
    if basis == "Individual":
        bm = convert_to_individual(bm)
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
            st.session_state[ss_key] = [{"year": 2024, "age": 30, "net_worth": 0}]
        edited = st.data_editor(
            pd.DataFrame(st.session_state[ss_key]),
            num_rows="dynamic", use_container_width=True,
            column_config={
                "year":      st.column_config.NumberColumn("Year",     min_value=1960, max_value=2030, step=1,    format="%d"),
                "age":       st.column_config.NumberColumn("Age",      min_value=16,   max_value=100,  step=1,    format="%d"),
                "net_worth": st.column_config.NumberColumn("Net worth (£)", min_value=-1_000_000, max_value=50_000_000, step=1_000, format="£%,d"),
            },
            key=f"{key_prefix}_editor",
        )
        if len(edited) > 0 and edited["net_worth"].abs().sum() > 0:
            result_df = edited.copy()
            result_df["year"]      = result_df["year"].astype(int)
            result_df["age"]       = result_df["age"].astype(float)
            result_df["net_worth"] = result_df["net_worth"].astype(float)
            result_df = result_df.sort_values("age").reset_index(drop=True)
            st.session_state[ss_key] = result_df.to_dict("records")

    return result_df


# ── Helpers (defined before sidebar so they're available everywhere) ───────────

def _fmt(v: float) -> str:
    if abs(v) >= 1_000_000: return f"£{v/1_000_000:.2f}m"
    if abs(v) >= 1_000:     return f"£{v/1_000:.0f}k"
    return f"£{v:.0f}"

def _fmt_delta(d: float) -> str:
    return ("+" if d >= 0 else "") + _fmt(d)


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


# ── Data pipeline ─────────────────────────────────────────────────────────────

benchmark = _build_benchmark(basis, include_pension, real_terms)

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
            custom.append([yr, cp25, cp50, cp75])

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
                "Med £%{customdata[2]:,.0f} · P75 £%{customdata[3]:,.0f}</i><extra></extra>"
            ),
            customdata=custom,
        ))

        # Best gain annotation
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

        if show_crosshair:
            fig.add_vline(x=lat_age,
                line=dict(color=colour, width=1.5, dash="dash"),
                annotation_text=f"{name.split()[0]} (age {lat_age:.1f})",
                annotation_position="top",
                annotation=dict(font=dict(color=colour, size=11),
                    bgcolor="white", bordercolor=colour, borderwidth=1, borderpad=4),
            )
        if show_horiz and lat_nw > 0 and not log_scale:
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

    price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"

    yaxis_cfg = dict(
        title=f"Net worth (£, {price_label})" + (" — log scale" if log_scale else ""),
        type="log" if log_scale else "linear",
        tickprefix="£",
        **({} if log_scale else {"tickformat": ",.0f", "zeroline": True, "zerolinecolor": "#cbd5e1"}),
        gridcolor="#e2e8f0", showgrid=True,
    )

    fig.update_layout(
        title=dict(
            text=f"UK net worth distribution — {basis.lower()} basis, {price_label}",
            font=dict(size=17, color="#1e293b"), x=0,
        ),
        xaxis=dict(title="Age", range=[age_min - 0.5, age_max + 0.5],
                   dtick=5, gridcolor="#e2e8f0", showgrid=True, zeroline=False),
        yaxis=yaxis_cfg,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=12)),
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
        height=560, margin=dict(l=70, r=90, t=80, b=60),
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

    fig.update_layout(
        title=dict(text="Estimated percentile over time", font=dict(size=14, color="#1e293b"), x=0),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", dtick=5, zeroline=False),
        yaxis=dict(title="Percentile", range=[0, 100], dtick=25,
                   ticksuffix="th", gridcolor="#e2e8f0"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=270, margin=dict(l=60, r=80, t=50, b=50),
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
) -> go.Figure:
    """Forward-project net worth under one or more CAGR scenarios."""
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
    for i, (cagr, sc_label) in enumerate(scenarios):
        proj_nw = [latest_nw * (1 + cagr) ** (a - latest_age) for a in proj_ages]
        fig.add_trace(go.Scatter(
            x=proj_ages, y=proj_nw, mode="lines",
            line=dict(color=scenario_colours[i % len(scenario_colours)], width=2,
                      dash="dash" if i > 0 else "solid"),
            name=sc_label,
            hovertemplate=f"<b>{sc_label}</b><br>Age %{{x:.1f}}<br>£%{{y:,.0f}}<extra></extra>",
        ))

    sc_title = " vs ".join(f"{c*100:.1f}%" for c, _ in scenarios)
    price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"
    fig.update_layout(
        title=dict(text=f"What-if: {sc_title} CAGR from age {latest_age:.1f}",
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

    if age_span > 0.5 and nw_start > 0 and nw_end > 0:
        cagr = (nw_end / nw_start) ** (1 / age_span) - 1
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
            if age_span > 0.5 and first_nw > 0 and latest_nw > 0:
                cagr = (latest_nw / first_nw) ** (1 / age_span) - 1
                st.metric("CAGR", f"{cagr*100:+.1f}%",
                          help=f"Compound annual growth rate from age {first_age:.1f} to {latest_age:.1f}.")
            else:
                st.metric("Total change", _fmt_delta(latest_nw - first_nw))
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

    st.info(
        f"At age **{latest_age:.1f}**, your net worth of **{_fmt(latest_nw)}** ({price_note}) "
        f"places you {'at approximately the **' + str(round(exact_pct)) + 'th percentile**' if exact_pct else '**' + band_desc + '**'} "
        f"on a {basis.lower()} basis in the UK."
        + (f" (Up {_fmt(delta_val)} from your previous recorded figure.)" if delta_val and delta_val > 0 else
           f" (Down {_fmt(abs(delta_val))} from your previous recorded figure.)" if delta_val and delta_val < 0 else "")
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

    # Combined household callout (only when both loaded)
    if personal_plot_df is not None and latest_nw is not None:
        combined = latest_nw + p_nw
        st.info(f"Combined household net worth: **{_fmt(combined)}**")

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
                if age_span > 0.5 and first_nw > 0 and latest_nw > 0:
                    cagr_cur = (latest_nw / first_nw) ** (1 / age_span) - 1
                    if cagr_cur > 0.001:
                        yrs = math.log(target_val / latest_nw) / math.log(1 + cagr_cur)
                        st.metric(f"ETA ({_fmt(target_val)})", f"~{yrs:.0f} yrs",
                                  help=f"At your current {cagr_cur*100:.1f}% CAGR.")

# Log scale warning
if log_scale and personal_plot_df is not None and (personal_plot_df["net_worth"] <= 0).any():
    st.warning(f"{(personal_plot_df['net_worth']<=0).sum()} data point(s) hidden on log scale.", icon="⚠️")

# ── Summary statistics ────────────────────────────────────────────────────────

if personal_plot_df is not None and len(personal_plot_df) >= 2:
    with st.expander("Summary statistics"):
        frames = [build_summary_stats(personal_plot_df, benchmark, "You")]
        if partner_plot_df is not None and len(partner_plot_df) >= 2:
            frames.append(build_summary_stats(partner_plot_df, benchmark, "Partner"))
        st.dataframe(pd.concat(frames, ignore_index=True), use_container_width=True, hide_index=True)

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
    log_scale, show_tails, show_milestones,
    age_min, age_max,
    latest_age, latest_nw, partner_latest_age,
)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

if basis == "Individual":
    st.caption("Individual figures are derived — see methodology panel.")
else:
    st.caption(
        "Filled circles = ONS published data (ages 20,30,40,50,60,70,80). "
        "Lines are PCHIP-interpolated. Dotted verticals = age-band boundaries."
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

# ── What-if projection ────────────────────────────────────────────────────────

if personal_plot_df is not None and len(personal_plot_df) >= 1:
    with st.expander("What-if projection"):
        st.caption(
            "Forward-project your net worth from the latest data point under a chosen growth rate, "
            "overlaid against the benchmark. Descriptive only — not financial advice."
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

        scenarios = [
            (wi_cagr1 / 100, f"Scenario 1 ({wi_cagr1:+.1f}%)"),
            (wi_cagr2 / 100, f"Scenario 2 ({wi_cagr2:+.1f}%)"),
            (wi_cagr3 / 100, f"Scenario 3 ({wi_cagr3:+.1f}%)"),
        ]
        st.plotly_chart(
            build_whatif_figure(personal_plot_df, benchmark, scenarios, wi_age, COLOURS["person"]),
            use_container_width=True, config=PLOTLY_CONFIG,
        )

        # Projected percentiles at target age for each scenario
        if latest_nw and latest_nw > 0:
            sc_cols = st.columns(3)
            for i, (cagr, sc_label) in enumerate(scenarios):
                proj_nw_at = latest_nw * (1 + cagr) ** (wi_age - (latest_age or 0))
                proj_pct   = estimate_exact_percentile(proj_nw_at, min(wi_age, 85), benchmark)
                with sc_cols[i]:
                    st.metric(
                        sc_label,
                        _fmt(proj_nw_at),
                        delta=f"~{proj_pct:.0f}th pct" if proj_pct else "n/a",
                        help=f"Projected net worth at age {wi_age}.",
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

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    "<div style='text-align:center; color:#94a3b8; font-size:0.8rem;'>"
    "UK Net Worth Benchmarker · ONS WAS Wave 7 (2018–2020) · Streamlit + Plotly"
    "</div>",
    unsafe_allow_html=True,
)
