"""
UK Net Worth Benchmarker
------------------------
Visualises ONS Wealth and Assets Survey percentile distributions by age,
with an interactive personal overlay and a transparent inference layer.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from utils.data_loader import load_was_data, parse_personal_csv
from utils.inference import (
    interpolate_benchmarks,
    convert_to_individual,
    adjust_for_inflation,
    cpi_adjust_personal,
    estimate_percentile,
    estimate_exact_percentile,
    build_percentile_trajectory,
    derive_tail_percentiles,
    DATA_YEAR,
    REAL_BASE_YEAR,
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
    "person": "#f97316",
}

PLOTLY_CONFIG = {
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "uk_networth_benchmarker",
        "height": 600,
        "width": 1200,
        "scale": 2,
    },
}


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def _load_raw() -> pd.DataFrame:
    return load_was_data()


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

with st.sidebar:
    st.title("Settings")

    st.subheader("Benchmark")
    basis = st.radio(
        "Basis",
        ["Household", "Individual"],
        help=(
            "**Household** figures are direct from ONS WAS. "
            "**Individual** is derived — see methodology for the sharing-factor approach."
        ),
    )
    include_pension = st.toggle("Include pension wealth", value=True)
    real_terms      = st.toggle(f"Real terms ({REAL_BASE_YEAR} £)", value=False)
    log_scale       = st.toggle("Log scale", value=False,
                                help="Spreads out low values — useful when your data spans a wide range")
    show_tails      = st.toggle("Show P10 / P90", value=False,
                                help="Derived tails: modelled from the log-normal fit, not published WAS data")

    st.divider()
    st.subheader("Your net worth")
    input_method = st.radio(
        "Data entry",
        ["None", "Manual entry", "Upload CSV"],
        label_visibility="collapsed",
    )

    personal_df: pd.DataFrame | None = None

    if input_method == "Upload CSV":
        uploaded = st.file_uploader("Upload your net worth history", type=["csv"])
        if uploaded:
            try:
                personal_df = parse_personal_csv(uploaded)
                st.success(f"{len(personal_df)} data point(s) loaded.")
                if "birth_year_warning" in personal_df.attrs:
                    st.warning(personal_df.attrs["birth_year_warning"], icon="⚠️")
            except ValueError as exc:
                st.error(str(exc))

        template = pd.DataFrame({
            "year":      [2020, 2021, 2022, 2023, 2024],
            "age":       [28, 29, 30, 31, 32],
            "net_worth": [12000, 18500, 27000, 38000, 52000],
        })
        st.download_button(
            "Download CSV template",
            template.to_csv(index=False).encode(),
            "personal_template.csv",
            "text/csv",
            use_container_width=True,
        )

    elif input_method == "Manual entry":
        st.caption("Add one row per year. Net worth in £.")
        if "personal_rows" not in st.session_state:
            st.session_state.personal_rows = [
                {"year": 2024, "age": 30, "net_worth": 0}
            ]
        edited = st.data_editor(
            pd.DataFrame(st.session_state.personal_rows),
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "year":      st.column_config.NumberColumn("Year",     min_value=1960, max_value=2030, step=1,    format="%d"),
                "age":       st.column_config.NumberColumn("Age",      min_value=16,   max_value=100,  step=1,    format="%d"),
                "net_worth": st.column_config.NumberColumn("Net worth (£)", min_value=-1_000_000, max_value=50_000_000, step=1_000, format="£%d"),
            },
            key="personal_editor",
        )
        if len(edited) > 0 and edited["net_worth"].abs().sum() > 0:
            personal_df = edited.copy()
            personal_df["year"]      = personal_df["year"].astype(int)
            personal_df["age"]       = personal_df["age"].astype(float)
            personal_df["net_worth"] = personal_df["net_worth"].astype(float)
            personal_df = personal_df.sort_values("age").reset_index(drop=True)
            st.session_state.personal_rows = personal_df.to_dict("records")

    st.divider()
    st.caption(
        "Data: ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain. "
        "Individual figures and single-year interpolations are derived estimates."
    )


# ── Benchmark & personal data pipeline ───────────────────────────────────────

benchmark = _build_benchmark(basis, include_pension, real_terms)

personal_plot_df: pd.DataFrame | None = None
if personal_df is not None and len(personal_df) > 0:
    personal_plot_df = (
        cpi_adjust_personal(personal_df, to_year=REAL_BASE_YEAR)
        if real_terms else personal_df.copy()
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"£{value/1_000_000:.2f}m"
    if abs(value) >= 1_000:
        return f"£{value/1_000:.0f}k"
    return f"£{value:.0f}"


def _fmt_delta(delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    return f"{sign}{_fmt(delta)}"


def _percentile_series(pct: str) -> pd.DataFrame:
    return benchmark[benchmark["percentile"] == pct].sort_values("age")


def _hover(label: str) -> str:
    return f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>"


# ── Main benchmark chart ──────────────────────────────────────────────────────

def build_main_figure(
    log_scale: bool,
    show_tails: bool,
    latest_age: float | None,
    latest_nw: float | None,
) -> go.Figure:
    fig = go.Figure()

    p25 = _percentile_series("p25")
    p50 = _percentile_series("p50")
    p75 = _percentile_series("p75")

    # IQR shading
    fig.add_trace(go.Scatter(
        x=pd.concat([p25["age"], p75["age"].iloc[::-1]]),
        y=pd.concat([p25["value"], p75["value"].iloc[::-1]]),
        fill="toself",
        fillcolor=COLOURS["band"],
        line=dict(width=0),
        name="P25–P75 range",
        hoverinfo="skip",
        showlegend=True,
    ))

    # Optional P10 / P90 tails (derived from log-normal fit — not published data)
    if show_tails:
        tails = derive_tail_percentiles(benchmark)
        for pct_label, label in [("p10", "10th percentile (modelled)"), ("p90", "90th percentile (modelled)")]:
            tail_s = tails[tails["percentile"] == pct_label].sort_values("age")
            if len(tail_s):
                fig.add_trace(go.Scatter(
                    x=tail_s["age"], y=tail_s["value"],
                    mode="lines",
                    line=dict(color="#bfdbfe", width=1.5, dash="dot"),
                    name=label,
                    hovertemplate=f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>",
                ))

    # Percentile lines
    for pct_data, colour, width, dash, label in [
        (p25, COLOURS["p25"], 2, "dash",  "25th percentile"),
        (p75, COLOURS["p75"], 2, "dash",  "75th percentile"),
        (p50, COLOURS["p50"], 3, "solid", "Median (P50)"),
    ]:
        fig.add_trace(go.Scatter(
            x=pct_data["age"], y=pct_data["value"],
            mode="lines",
            line=dict(color=colour, width=width, dash=dash),
            name=label,
            hovertemplate=_hover(label),
        ))

    # Published WAS data point markers (household only)
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
                    name="ONS data point",
                    showlegend=not pub_shown,
                    hovertemplate=(
                        "<b>ONS published</b><br>Age %{x}<br>£%{y:,.0f}<extra></extra>"
                    ),
                ))
                pub_shown = True
    else:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color="rgba(0,0,0,0)", size=1),
            name="Individual figures are derived estimates",
            showlegend=True,
        ))

    # Personal overlay
    if personal_plot_df is not None and len(personal_plot_df) > 0:
        pdf = personal_plot_df.sort_values("age")

        # Zero line — only when personal data contains negative values
        if (pdf["net_worth"] < 0).any() and not log_scale:
            fig.add_hline(
                y=0,
                line=dict(color="#94a3b8", width=1.5),
                annotation_text="Zero",
                annotation_position="right",
                annotation=dict(font=dict(color="#94a3b8", size=10)),
            )

        if log_scale:
            pdf = pdf[pdf["net_worth"] > 0]

        if len(pdf):
            # Build rich customdata: [year, p25, p50, p75] per row
            ages_rounded = pdf["age"].apply(lambda a: min(round(a), 85)).values
            bm_at_age = benchmark.set_index(["age", "percentile"])["value"]
            custom = []
            for yr, ar in zip(pdf["year"], ages_rounded):
                try:
                    c_p25 = bm_at_age.loc[(ar, "p25")]
                    c_p50 = bm_at_age.loc[(ar, "p50")]
                    c_p75 = bm_at_age.loc[(ar, "p75")]
                except KeyError:
                    c_p25 = c_p50 = c_p75 = float("nan")
                custom.append([yr, c_p25, c_p50, c_p75])

            fig.add_trace(go.Scatter(
                x=pdf["age"], y=pdf["net_worth"],
                mode="lines+markers",
                line=dict(color=COLOURS["person"], width=2.5),
                marker=dict(color=COLOURS["person"], size=8,
                            line=dict(color="white", width=1.5)),
                name="Your net worth",
                hovertemplate=(
                    "<b>Your net worth</b><br>"
                    "Age %{x:.1f} (year %{customdata[0]})<br>"
                    "£%{y:,.0f}<br>"
                    "<i>Benchmark: P25 £%{customdata[1]:,.0f} · "
                    "Med £%{customdata[2]:,.0f} · "
                    "P75 £%{customdata[3]:,.0f}</i><extra></extra>"
                ),
                customdata=custom,
            ))

    # Crosshair: vertical "you are here" line
    if latest_age is not None:
        fig.add_vline(
            x=latest_age,
            line=dict(color=COLOURS["person"], width=1.5, dash="dash"),
            annotation_text=f"You (age {latest_age:.1f})",
            annotation_position="top",
            annotation=dict(
                font=dict(color=COLOURS["person"], size=12),
                bgcolor="white",
                bordercolor=COLOURS["person"],
                borderwidth=1,
                borderpad=4,
            ),
        )

    # Crosshair: horizontal "current net worth" line (linear scale only — log adds clutter)
    if latest_nw is not None and latest_nw > 0 and not log_scale:
        fig.add_hline(
            y=latest_nw,
            line=dict(color=COLOURS["person"], width=1, dash="dot"),
            annotation_text=_fmt(latest_nw),
            annotation_position="right",
            annotation=dict(
                font=dict(color=COLOURS["person"], size=11),
                bgcolor="white",
                borderpad=3,
            ),
        )

    # Age band boundary markers (subtle vertical dotted lines)
    for x_val in [24, 34, 44, 54, 64, 74]:
        fig.add_vline(
            x=x_val + 0.5,
            line=dict(color="#e2e8f0", width=1, dash="dot"),
        )

    # Layout
    price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"

    if log_scale:
        yaxis_cfg = dict(
            title=f"Net worth (£, {price_label}) — log scale",
            type="log",
            tickprefix="£",
            gridcolor="#e2e8f0",
            showgrid=True,
            zeroline=False,
        )
    else:
        yaxis_cfg = dict(
            title=f"Net worth (£, {price_label})",
            type="linear",
            tickprefix="£",
            tickformat=",.0f",
            gridcolor="#e2e8f0",
            showgrid=True,
            zeroline=True,
            zerolinecolor="#cbd5e1",
        )

    fig.update_layout(
        title=dict(
            text=f"UK net worth distribution — {basis.lower()} basis, {price_label}",
            font=dict(size=17, color="#1e293b"),
            x=0,
        ),
        xaxis=dict(
            title="Age",
            range=[15, 86],
            dtick=5,
            gridcolor="#e2e8f0",
            showgrid=True,
            zeroline=False,
        ),
        yaxis=yaxis_cfg,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            font=dict(size=12),
        ),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=560,
        margin=dict(l=70, r=80, t=80, b=60),
    )

    return fig


# ── Percentile trajectory chart ───────────────────────────────────────────────

def build_percentile_chart(traj: pd.DataFrame) -> go.Figure:
    """Secondary chart: estimated percentile vs age over the user's lifetime."""
    fig = go.Figure()

    # Reference lines at P25, median, P75
    for y_val, label in [(75, "P75"), (50, "Median"), (25, "P25")]:
        fig.add_hline(
            y=y_val,
            line=dict(color="#93c5fd", width=1, dash="dot"),
            annotation_text=label,
            annotation_position="right",
            annotation=dict(font=dict(color="#64748b", size=10), bgcolor="rgba(0,0,0,0)"),
        )

    # Filled area + line
    fig.add_trace(go.Scatter(
        x=traj["age"], y=traj["percentile"],
        mode="lines+markers",
        line=dict(color=COLOURS["person"], width=2.5),
        marker=dict(color=COLOURS["person"], size=7,
                    line=dict(color="white", width=1.5)),
        fill="tozeroy",
        fillcolor="rgba(249,115,22,0.08)",
        name="Your percentile",
        hovertemplate=(
            "<b>Age %{x:.1f}</b><br>"
            "~%{y:.0f}th percentile<br>"
            "Net worth: £%{customdata:,.0f}<extra></extra>"
        ),
        customdata=traj["net_worth"],
    ))

    fig.update_layout(
        title=dict(
            text="Your estimated percentile over time",
            font=dict(size=14, color="#1e293b"),
            x=0,
        ),
        xaxis=dict(
            title="Age",
            gridcolor="#e2e8f0",
            dtick=5,
            zeroline=False,
        ),
        yaxis=dict(
            title="Percentile",
            range=[0, 100],
            dtick=25,
            ticksuffix="th",
            gridcolor="#e2e8f0",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=260,
        margin=dict(l=60, r=80, t=50, b=50),
        showlegend=False,
        hovermode="x unified",
    )

    return fig


# ── Main content ──────────────────────────────────────────────────────────────

st.title("UK Net Worth Benchmarker")
st.caption(
    "Compare your net worth against UK population distributions by age. "
    "Source: ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain."
)

# ── Metrics row ───────────────────────────────────────────────────────────────

latest_age: float | None = None
latest_nw:  float | None = None

if personal_plot_df is not None and len(personal_plot_df) > 0:
    sorted_pdf = personal_plot_df.sort_values("age")
    latest      = sorted_pdf.iloc[-1]
    latest_age  = float(latest["age"])
    latest_nw   = float(latest["net_worth"])

    price_note  = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal {DATA_YEAR} prices"

    # Exact percentile estimate via log-normal fit
    exact_pct   = estimate_exact_percentile(latest_nw, round(latest_age), benchmark)
    band_desc   = estimate_percentile(latest_nw, round(latest_age), benchmark)

    # Delta from previous data point
    delta_str   = None
    delta_val   = None
    if len(sorted_pdf) >= 2:
        prev_nw  = float(sorted_pdf.iloc[-2]["net_worth"])
        delta_val = latest_nw - prev_nw
        delta_str = _fmt_delta(delta_val)

    # ── Row 1: snapshot ────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Your latest age", f"{latest_age:.1f}")
    with col2:
        st.metric(
            "Net worth",
            _fmt(latest_nw),
            delta=delta_str,
            help=f"In {price_note}. Delta vs previous data point.",
        )
    with col3:
        if exact_pct is not None:
            st.metric(
                "Est. percentile",
                f"~{exact_pct:.0f}th",
                help="Estimated from a log-normal distribution fitted to P25/P50/P75. Indicative only.",
            )
        else:
            short_band = {
                "below the 25th percentile":              "Below P25",
                "between the 25th percentile and the median": "P25 – P50",
                "between the median and the 75th percentile": "P50 – P75",
                "above the 75th percentile":              "Above P75",
            }.get(band_desc, band_desc.capitalize())
            st.metric("Percentile band", short_band)
    with col4:
        age_bench = benchmark[benchmark["age"] == min(round(latest_age), 85)]
        p50_val   = age_bench[age_bench["percentile"] == "p50"]["value"]
        p75_val   = age_bench[age_bench["percentile"] == "p75"]["value"]
        p50v      = float(p50_val.iloc[0]) if len(p50_val) else None
        p75v      = float(p75_val.iloc[0]) if len(p75_val) else None
        if p50v and p75v:
            if latest_nw < p50v:
                st.metric("Gap to median", _fmt(p50v - latest_nw),
                          help="How much more to reach the P50 benchmark at your age.")
            elif latest_nw < p75v:
                st.metric("Gap to P75", _fmt(p75v - latest_nw),
                          help="How much more to reach the 75th percentile benchmark at your age.")
            else:
                st.metric("Above P75 by", _fmt(latest_nw - p75v),
                          help="How far above the 75th percentile you sit.")

    # ── Row 2: growth & milestone progress ────────────────────────────────────
    if len(sorted_pdf) >= 2:
        first      = sorted_pdf.iloc[0]
        first_age  = float(first["age"])
        first_nw   = float(first["net_worth"])
        age_span   = latest_age - first_age

        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            if age_span > 0.5 and first_nw > 0 and latest_nw > 0:
                cagr = (latest_nw / first_nw) ** (1 / age_span) - 1
                st.metric(
                    "CAGR",
                    f"{cagr * 100:+.1f}%",
                    help=f"Compound annual growth rate from age {first_age:.1f} to {latest_age:.1f}.",
                )
            else:
                total_change = latest_nw - first_nw
                st.metric("Total change", _fmt_delta(total_change))
        with col_b:
            ann_abs = (latest_nw - first_nw) / age_span if age_span > 0 else None
            if ann_abs is not None:
                st.metric(
                    "Avg annual gain",
                    _fmt(ann_abs),
                    help=f"Simple average annual change over {age_span:.1f} years.",
                )
        with col_c:
            # Progress bar toward next benchmark milestone
            if p50v and p75v:
                if latest_nw < p50v:
                    target    = p50v
                    from_val  = max(0.0, first_nw) if first_nw < p50v else 0.0
                    label     = f"Progress toward median (£{p50v:,.0f})"
                elif latest_nw < p75v:
                    target    = p75v
                    from_val  = p50v
                    label     = f"Progress toward P75 (£{p75v:,.0f})"
                else:
                    target = label = from_val = None

                if target:
                    span   = max(target - from_val, 1)
                    prog   = min(max((latest_nw - from_val) / span, 0.0), 1.0)
                    st.caption(label)
                    st.progress(prog)

    st.info(
        f"At age **{latest_age:.1f}**, your net worth of **{_fmt(latest_nw)}** "
        f"({price_note}) places you "
        f"{'at approximately the **' + str(round(exact_pct)) + 'th percentile**' if exact_pct else '**' + band_desc + '**'}"
        f" on a {basis.lower()} basis in the UK."
        + (f" (Up {_fmt(delta_val)} from your previous recorded figure.)" if delta_val and delta_val > 0 else
           f" (Down {_fmt(abs(delta_val))} from your previous recorded figure.)" if delta_val and delta_val < 0 else "")
    )

# Warn if log scale hides personal data points
if log_scale and personal_plot_df is not None and (personal_plot_df["net_worth"] <= 0).any():
    n_hidden = (personal_plot_df["net_worth"] <= 0).sum()
    st.warning(
        f"{n_hidden} data point(s) with zero or negative net worth are hidden on the log scale.",
        icon="⚠️",
    )

# ── Main chart ────────────────────────────────────────────────────────────────

fig = build_main_figure(log_scale, show_tails, latest_age, latest_nw)
st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

# Inline note
if basis == "Individual":
    st.caption(
        "Individual figures are derived from household data using age-specific sharing factors — "
        "see the methodology panel below."
    )
else:
    st.caption(
        "Filled circles mark ONS-published data points (band midpoints: ages 20, 30, 40, 50, 60, 70, 80). "
        "Connecting lines are PCHIP-interpolated estimates. Dotted vertical lines mark age-band boundaries."
    )

# ── Percentile trajectory chart ───────────────────────────────────────────────

if personal_plot_df is not None and len(personal_plot_df) >= 2:
    traj = build_percentile_trajectory(personal_plot_df, benchmark)
    if len(traj) >= 2:
        st.plotly_chart(
            build_percentile_chart(traj),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        st.caption(
            "Percentile estimated by fitting a log-normal distribution to the P25/P50/P75 benchmarks at each age. "
            "Treat as indicative — log-normality is an approximation."
        )


# ── Methodology panel ─────────────────────────────────────────────────────────

with st.expander("Methodology and data sources", expanded=False):
    st.markdown(f"""
### Data source

Benchmark data is drawn from the **ONS Wealth and Assets Survey (WAS), Wave 7 (2018–2020)**,
published by the Office for National Statistics. WAS is a longitudinal survey of around 20,000
private households in Great Britain (England, Scotland, Wales — Northern Ireland excluded).

> **Transparency note:** The figures used here are approximations of published WAS Wave 7
> percentile tables, included for illustrative purposes. For research or policy use, consult
> the primary ONS data tables at [ons.gov.uk](https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/bulletins/wealthingreatbritainwave7/2018to2020).

---

### Age band → single year interpolation

WAS publishes wealth in 10-year age bands: 16–24, 25–34, 35–44, 45–54, 55–64, 65–74, 75+.
To produce single-year estimates, we apply **PCHIP monotone cubic spline interpolation**
anchored at band midpoints (ages 20, 30, 40, 50, 60, 70, 80).

PCHIP preserves shape monotonicity, preventing oscillation where net worth growth slows
or reverses in later life. **Filled circle markers** on the household chart mark published
data points; all other ages are interpolated estimates.

---

### Exact percentile estimation

The "Est. percentile" metric fits a **log-normal distribution** to the three benchmark
percentiles (P25, P50, P75) at the user's age:

```
mu    = log(P50)                          [median of log-normal = e^mu]
sigma = (log(P75) − log(P25)) / 1.3490   [from the normal z-score Phi(0.6745) = 0.75]
```

The user's net worth is then located on this distribution's CDF. Log-normality is a
reasonable approximation for wealth distributions but is a modelling assumption — treat
the result as indicative (±5–10 percentile points), not authoritative.

The **percentile trajectory chart** applies this calculation to every personal data point,
showing how the user's relative position has changed over time.

---

### Household → individual conversion

WAS measures wealth at the household level. The **individual basis** is a derived estimate
using age-specific sharing factors calibrated from ONS household composition data and
WAS pension-share component tables.

Pension wealth is not divided (WAS tracks it per-individual). Non-pension wealth is
halved for couple households and kept whole for single-person households.

**Individual figures carry ±15–20% uncertainty.** All individual output is flagged as derived.

---

### Real vs nominal

Nominal values are in **{DATA_YEAR} prices**. Real values are CPI-adjusted to **{REAL_BASE_YEAR}**
using the ONS Consumer Price Index (2015 = 100). Personal net worth entries are each
CPI-adjusted from their recorded year when real-terms mode is active.

---

### Pension wealth

WAS tracks four components: property wealth (net of mortgage), financial wealth (net of
non-mortgage debt), physical wealth, and private pension wealth (DC: fund value; DB:
present value using ONS annuity factors). Toggle "Include pension wealth" to exclude
the pension component from all figures.

---

### Personal data privacy

Your data is held in **Streamlit session state only** — not transmitted, logged, or stored
beyond the current browser session.

---

### Known limitations

- WAS excludes Northern Ireland; figures represent Great Britain only.
- WAS under-covers the very wealthiest households (~top 1–2%); P75 is broadly reliable
  but the distribution above P90 is underestimated.
- The 75+ band spans a wide range; age-80 midpoint is a modelling assumption.
- Wave 7 (2018–2020) predates significant house-price and inflation movements of 2021–2024.
""")


# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    "<div style='text-align:center; color:#94a3b8; font-size:0.8rem;'>"
    "UK Net Worth Benchmarker · Data: ONS WAS Wave 7 (2018–2020) · "
    "Built with Streamlit &amp; Plotly"
    "</div>",
    unsafe_allow_html=True,
)
