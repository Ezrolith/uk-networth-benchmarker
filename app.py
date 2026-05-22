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
    .methodology-note { font-size: 0.85rem; color: #64748b; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

AGE_RANGE = np.arange(16, 86)

COLOURS = {
    "p25":    "#93c5fd",   # blue-300
    "p50":    "#1d4ed8",   # blue-700
    "p75":    "#93c5fd",   # blue-300
    "band":   "rgba(147,197,253,0.18)",
    "pub":    "#1e40af",   # blue-800  (published data markers)
    "person": "#f97316",   # orange-500
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
    real_terms = st.toggle(f"Real terms ({REAL_BASE_YEAR} £)", value=False)

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
            personal_df = edited.rename(columns=lambda c: c).copy()
            personal_df["year"] = personal_df["year"].astype(int)
            personal_df["age"] = personal_df["age"].astype(int)
            personal_df["net_worth"] = personal_df["net_worth"].astype(float)
            personal_df = personal_df.sort_values("age").reset_index(drop=True)
            st.session_state.personal_rows = personal_df.to_dict("records")

    st.divider()
    st.caption(
        "Data: ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain. "
        "Individual figures and single-year interpolations are derived estimates."
    )


# ── Benchmark data pipeline ───────────────────────────────────────────────────

benchmark = _build_benchmark(basis, include_pension, real_terms)

# Adjust personal data for real terms if needed
personal_plot_df = None
if personal_df is not None and len(personal_df) > 0:
    if real_terms:
        personal_plot_df = cpi_adjust_personal(personal_df, to_year=REAL_BASE_YEAR)
    else:
        personal_plot_df = personal_df.copy()


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _fmt(value: float) -> str:
    if value >= 1_000_000:
        return f"£{value/1_000_000:.2f}m"
    if value >= 1_000:
        return f"£{value/1_000:.0f}k"
    return f"£{value:.0f}"


def _percentile_series(pct: str) -> pd.DataFrame:
    return benchmark[benchmark["percentile"] == pct].sort_values("age")


def _hover(label: str) -> str:
    return f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>"


# ── Build Plotly figure ───────────────────────────────────────────────────────

def build_figure() -> go.Figure:
    fig = go.Figure()

    p25 = _percentile_series("p25")
    p50 = _percentile_series("p50")
    p75 = _percentile_series("p75")

    # IQR shading (P25 → P75 → back)
    x_band = pd.concat([p25["age"], p75["age"].iloc[::-1]])
    y_band = pd.concat([p25["value"], p75["value"].iloc[::-1]])
    fig.add_trace(go.Scatter(
        x=x_band, y=y_band,
        fill="toself",
        fillcolor=COLOURS["band"],
        line=dict(width=0),
        name="P25–P75 range",
        hoverinfo="skip",
        showlegend=True,
    ))

    # P25 line
    fig.add_trace(go.Scatter(
        x=p25["age"], y=p25["value"],
        mode="lines",
        line=dict(color=COLOURS["p25"], width=2, dash="dash"),
        name="25th percentile",
        hovertemplate=_hover("25th percentile"),
    ))

    # P75 line
    fig.add_trace(go.Scatter(
        x=p75["age"], y=p75["value"],
        mode="lines",
        line=dict(color=COLOURS["p75"], width=2, dash="dash"),
        name="75th percentile",
        hovertemplate=_hover("75th percentile"),
    ))

    # P50 line
    fig.add_trace(go.Scatter(
        x=p50["age"], y=p50["value"],
        mode="lines",
        line=dict(color=COLOURS["p50"], width=3),
        name="Median (P50)",
        hovertemplate=_hover("Median"),
    ))

    # Published data markers (solid circles) — only household basis has these
    if basis == "Household":
        for pct_key, pct_data, label in [
            ("p25", p25, "P25 – published"),
            ("p50", p50, "P50 – published"),
            ("p75", p75, "P75 – published"),
        ]:
            pub = pct_data[pct_data["is_published"]]
            if len(pub):
                fig.add_trace(go.Scatter(
                    x=pub["age"], y=pub["value"],
                    mode="markers",
                    marker=dict(color=COLOURS["pub"], size=9, symbol="circle",
                                line=dict(color="white", width=1.5)),
                    name=label,
                    showlegend=(pct_key == "p50"),
                    hovertemplate=(
                        f"<b>{label.split('–')[0].strip()} (WAS published)</b>"
                        "<br>Age %{x}<br>£%{y:,.0f}<extra></extra>"
                    ),
                ))
    else:
        # Individual basis — add a legend note entry
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(color="rgba(0,0,0,0)", size=1),
            name="Individual figures are derived estimates",
            showlegend=True,
        ))

    # Personal overlay
    if personal_plot_df is not None and len(personal_plot_df) > 0:
        pdf = personal_plot_df.sort_values("age")
        fig.add_trace(go.Scatter(
            x=pdf["age"], y=pdf["net_worth"],
            mode="lines+markers",
            line=dict(color=COLOURS["person"], width=2.5),
            marker=dict(color=COLOURS["person"], size=9,
                        line=dict(color="white", width=1.5)),
            name="Your net worth",
            hovertemplate=(
                "<b>Your net worth</b><br>"
                "Age %{x} (year %{customdata})<br>"
                "£%{y:,.0f}<extra></extra>"
            ),
            customdata=pdf["year"],
        ))

    # Layout
    price_label = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal ({DATA_YEAR} prices)"
    basis_label = basis.lower()

    fig.update_layout(
        title=dict(
            text=f"UK net worth distribution — {basis_label} basis, {price_label}",
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
        yaxis=dict(
            title=f"Net worth (£, {price_label})",
            tickprefix="£",
            tickformat=",.0f",
            gridcolor="#e2e8f0",
            showgrid=True,
            zeroline=True,
            zerolinecolor="#cbd5e1",
        ),
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
        margin=dict(l=70, r=30, t=80, b=60),
    )

    # Age band boundary lines (subtle)
    band_boundaries = [24, 34, 44, 54, 64, 74]
    for x_val in band_boundaries:
        fig.add_vline(
            x=x_val + 0.5,
            line=dict(color="#e2e8f0", width=1, dash="dot"),
            annotation_text="",
        )

    return fig


# ── Main content ──────────────────────────────────────────────────────────────

st.title("UK Net Worth Benchmarker")
st.caption(
    "Compare your net worth against UK population distributions by age. "
    "Source: ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain."
)

# Percentile callout — shown only when personal data is loaded
if personal_plot_df is not None and len(personal_plot_df) > 0:
    latest = personal_plot_df.sort_values("age").iloc[-1]
    latest_age = float(latest["age"])
    latest_nw = float(latest["net_worth"])

    band_desc = estimate_percentile(latest_nw, round(latest_age), benchmark)
    price_note = f"{REAL_BASE_YEAR} real terms" if real_terms else f"nominal {DATA_YEAR} prices"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Your latest age", f"{latest_age:.1f}")
    with col2:
        st.metric("Net worth", _fmt(latest_nw), help=f"In {price_note}")
    with col3:
        short_band = {
            "below the 25th percentile": "Below P25",
            "between the 25th percentile and the median": "P25 – P50",
            "between the median and the 75th percentile": "P50 – P75",
            "above the 75th percentile": "Above P75",
        }.get(band_desc, band_desc.capitalize())
        st.metric("Percentile band", short_band)

    st.info(
        f"At age **{latest_age:.1f}**, your net worth of **{_fmt(latest_nw)}** "
        f"({price_note}) is **{band_desc}** on a {basis.lower()} basis in the UK."
    )

# Chart
fig = build_figure()
st.plotly_chart(fig, use_container_width=True)

# Inline notes
if basis == "Individual":
    st.caption(
        "Individual figures are derived from household data using age-specific sharing factors — "
        "see the methodology panel below for the full calculation."
    )
else:
    st.caption(
        "Filled circles on the chart mark ONS-published data points (band midpoints: ages 20, 30, 40, 50, 60, 70, 80). "
        "Connecting lines are PCHIP-interpolated estimates. Vertical dotted lines mark age-band boundaries."
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

PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) preserves the shape monotonicity
within each interval, preventing oscillation where net worth growth slows or reverses in
later life.

- **Filled circle markers** on the household chart mark the seven published data points.
- **All other ages** are interpolated estimates and should be read with that caveat.
- Ages 16–19 are held flat at the age-20 value; ages 81–85 at the age-80 value.

---

### Household → individual conversion

WAS measures wealth at the household level. The **individual basis** is a derived estimate
using age-specific sharing factors calibrated from two ONS sources:

1. **ONS Families and Households** — average household size and couple/single composition
   by age of household reference person (HRP)
2. **WAS component tables** — proportion of total wealth attributable to pension vs
   property/financial/physical wealth

The conversion logic per age band:

```
sharing_factor = pension_share × 1.0
               + (1 − pension_share) × (couple_share × 0.5 + single_share × 1.0)
```

Pension wealth is not divided because WAS tracks it per-individual.
Non-pension wealth is halved for couple households (assuming 50/50 ownership) and kept
whole for single-person households.

**Individual figures carry ±15–20% uncertainty** and should be treated as approximate.
All individual output is flagged as derived.

---

### Real vs nominal

Nominal values are in **{DATA_YEAR} prices** (approximate mid-point of the 2018–2020
survey period). Real values are CPI-adjusted to **{REAL_BASE_YEAR} prices** using the
ONS Consumer Price Index (2015 = 100).

Personal net worth entries are CPI-adjusted from their recorded year to {REAL_BASE_YEAR}
when real-terms mode is active.

---

### Pension wealth definition

WAS tracks four wealth components:

| Component | Definition |
|---|---|
| Property wealth | Gross property value minus outstanding mortgage |
| Financial wealth | Savings, investments, formal/informal loans — net of non-mortgage debt |
| Physical wealth | Vehicles, household contents, collectibles |
| Private pension wealth | DC: current fund value; DB: estimated present value using ONS annuity factors |

When **"Include pension wealth"** is toggled off, the pension component is removed from
all benchmark figures.

---

### Personal data privacy

Your net worth data is stored in **Streamlit session state only**. It is not transmitted
to any server, logged, or persisted beyond the current browser session.

---

### Known limitations

- WAS excludes Northern Ireland; figures represent Great Britain only.
- WAS excludes the very wealthiest households (top ~1–2%) due to survey under-coverage;
  P75 figures are broadly reliable but the distribution above P90 is underestimated.
- The 75+ band spans a wide age range; the age-80 midpoint is a modelling assumption.
- Wave 7 (2018–2020) predates significant house-price and inflation movements of 2021–2024;
  figures may understate current wealth levels in real terms even after CPI adjustment.
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
