"""
What-if projection: forward-project net worth under one or more CAGR
scenarios, optionally with monthly contributions. Overlay on the benchmark.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ._helpers import (
    TITLE_COLOUR, GRID_COLOUR,
    DEFAULT_PERSON_COLOUR,
    DEFAULT_BENCHMARK_BAND_COLOUR, DEFAULT_BENCHMARK_MEDIAN_COLOUR,
)


DEFAULT_SCENARIO_COLOURS = ["#f97316", "#8b5cf6", "#06b6d4"]  # orange, violet, cyan


def build_whatif_figure(
    pdf: pd.DataFrame,
    benchmark: pd.DataFrame,
    scenarios: list[tuple[float, str]],
    *,
    project_to_age: int,
    monthly_savings: float = 0.0,
    actual_colour: str = DEFAULT_PERSON_COLOUR,
    price_label: str = "nominal 2021 prices",
    scenario_colours: list[str] | None = None,
) -> go.Figure:
    """
    Plot historical net worth + one or more forward-projected paths against the
    P25/P50/P75 benchmark.

    Parameters
    ----------
    pdf : personal history with at least (age, net_worth).
    scenarios : list of (cagr_fraction, label) tuples — e.g. [(0.05, "5% real")].
    project_to_age : forecast horizon (years on the x-axis).
    monthly_savings : optional monthly £ contribution; modelled as an FV-of-
        annuity layered on top of the compound growth from current NW.
    """
    colours = scenario_colours or DEFAULT_SCENARIO_COLOURS

    s = pdf.sort_values("age")
    latest_age = float(s.iloc[-1]["age"])
    latest_nw  = float(s.iloc[-1]["net_worth"])
    proj_ages  = np.arange(latest_age, project_to_age + 1, 1.0)

    fig = go.Figure()

    p25 = benchmark[benchmark["percentile"] == "p25"].sort_values("age")
    p50 = benchmark[benchmark["percentile"] == "p50"].sort_values("age")
    p75 = benchmark[benchmark["percentile"] == "p75"].sort_values("age")

    # Benchmark IQR band + lines
    fig.add_trace(go.Scatter(
        x=pd.concat([p25["age"], p75["age"].iloc[::-1]]),
        y=pd.concat([p25["value"], p75["value"].iloc[::-1]]),
        fill="toself", fillcolor="rgba(147,197,253,0.15)",
        line=dict(width=0), name="P25–P75 range", hoverinfo="skip",
    ))
    for pct_data, dash, label in [
        (p25, "dash",  "P25"),
        (p50, "solid", "Median"),
        (p75, "dash",  "P75"),
    ]:
        fig.add_trace(go.Scatter(
            x=pct_data["age"], y=pct_data["value"], mode="lines",
            line=dict(
                color=DEFAULT_BENCHMARK_BAND_COLOUR if label != "Median" else DEFAULT_BENCHMARK_MEDIAN_COLOUR,
                width=2 if label != "Median" else 3,
                dash=dash,
            ),
            name=label,
            hovertemplate=f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>",
        ))

    # Historical personal data
    fig.add_trace(go.Scatter(
        x=s["age"], y=s["net_worth"], mode="lines+markers",
        line=dict(color=actual_colour, width=2.5),
        marker=dict(color=actual_colour, size=7, line=dict(color="white", width=1.5)),
        name="Actual",
        hovertemplate="<b>Actual</b><br>Age %{x:.1f}<br>£%{y:,.0f}<extra></extra>",
    ))

    # Forward projections
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
            line=dict(
                color=colours[i % len(colours)],
                width=2,
                dash="dash" if i > 0 else "solid",
            ),
            name=sc_label,
            hovertemplate=f"<b>{sc_label}</b><br>Age %{{x:.1f}}<br>£%{{y:,.0f}}<extra></extra>",
        ))

    sc_title = " vs ".join(f"{c*100:.1f}%" for c, _ in scenarios)
    contrib_note = (
        f"+£{monthly_savings:,.0f}/mo contributions"
        if monthly_savings > 0 else "no further contributions"
    )
    fig.update_layout(
        title=dict(
            text=(f"What-if: {sc_title} CAGR from age {latest_age:.1f}  "
                  f"<span style='font-size:11px;color:#64748b'>· {contrib_note}</span>"),
            font=dict(size=14, color=TITLE_COLOUR), x=0,
        ),
        xaxis=dict(title="Age", range=[15, project_to_age + 1], dtick=5,
                   gridcolor=GRID_COLOUR, zeroline=False),
        yaxis=dict(title=f"Net worth (£, {price_label})", tickprefix="£",
                   tickformat=",.0f", gridcolor=GRID_COLOUR),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        height=400, margin=dict(l=70, r=40, t=60, b=60),
        hovermode="x unified",
    )
    return fig
