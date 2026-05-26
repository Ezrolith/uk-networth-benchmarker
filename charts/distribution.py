"""
Log-normal wealth distribution density curve at a given age, with optional
markers for the user's and partner's net worth.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ._helpers import (
    fmt, TITLE_COLOUR, GRID_COLOUR,
    DEFAULT_PERSON_COLOUR, DEFAULT_PARTNER_COLOUR,
    DEFAULT_BENCHMARK_BAND_COLOUR, DEFAULT_BENCHMARK_MEDIAN_COLOUR,
)


def build_distribution_chart(
    age: int,
    benchmark: pd.DataFrame,
    *,
    user_nw: float | None = None,
    partner_nw: float | None = None,
    price_label: str = "nominal 2021",
    person_colour: str = DEFAULT_PERSON_COLOUR,
    partner_colour: str = DEFAULT_PARTNER_COLOUR,
    band_colour: str = DEFAULT_BENCHMARK_BAND_COLOUR,
    median_colour: str = DEFAULT_BENCHMARK_MEDIAN_COLOUR,
) -> go.Figure | None:
    """
    Fit a log-normal to P25/P50/P75 at the given age, plot its density curve,
    and overlay markers for the user's and partner's position.

    Returns None if benchmark is missing data for the requested age.
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

    # X range: 2nd to 98th percentile of the fitted distribution
    x_min = float(np.exp(mu + _norm.ppf(0.02) * sigma))
    x_max = float(np.exp(mu + _norm.ppf(0.98) * sigma))
    x = np.linspace(max(x_min, 1), x_max, 500)
    pdf = _lognorm.pdf(x, s=sigma, scale=np.exp(mu))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=pdf, mode="lines",
        line=dict(color=band_colour, width=2),
        fill="tozeroy", fillcolor="rgba(147,197,253,0.15)",
        name="Distribution", hoverinfo="skip",
    ))

    for val, label, colour in [
        (p25v, "P25",    band_colour),
        (p50v, "Median", median_colour),
        (p75v, "P75",    band_colour),
    ]:
        fig.add_vline(
            x=val, line=dict(color=colour, width=1.5, dash="dot"),
            annotation_text=f"{label} {fmt(val)}", annotation_position="top",
            annotation=dict(font=dict(size=10, color=colour)),
        )

    if user_nw and user_nw > 0:
        user_pct = _lognorm.cdf(user_nw, s=sigma, scale=np.exp(mu)) * 100
        fig.add_vline(
            x=user_nw, line=dict(color=person_colour, width=2.5),
            annotation_text=f"You {fmt(user_nw)} (~{user_pct:.0f}th)",
            annotation_position="top right",
            annotation=dict(font=dict(size=11, color=person_colour),
                            bgcolor="white", borderpad=3),
        )
    if partner_nw and partner_nw > 0:
        fig.add_vline(
            x=partner_nw, line=dict(color=partner_colour, width=2.5),
            annotation_text=f"Partner {fmt(partner_nw)}",
            annotation_position="top left",
            annotation=dict(font=dict(size=11, color=partner_colour),
                            bgcolor="white", borderpad=3),
        )

    fig.update_layout(
        title=dict(
            text=f"Wealth distribution at age {age_clamped} ({price_label})",
            font=dict(size=14, color=TITLE_COLOUR), x=0,
        ),
        xaxis=dict(title=f"Net worth (£, {price_label})", tickprefix="£",
                   tickformat=",.0f", gridcolor=GRID_COLOUR),
        yaxis=dict(title="Probability density", showticklabels=False,
                   gridcolor=GRID_COLOUR),
        plot_bgcolor="white", paper_bgcolor="white",
        height=300, margin=dict(l=60, r=60, t=50, b=50),
        showlegend=False,
    )
    return fig
