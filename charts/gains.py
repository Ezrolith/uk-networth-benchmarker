"""
Personal-trajectory charts: gains, velocity, cumulative.

All three operate on a tidy personal history DataFrame with at least
`age` and `net_worth` columns.
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go

from ._helpers import (
    TITLE_COLOUR, GRID_COLOUR,
    NEGATIVE_COLOUR,           # red used on loss bars
    NEUTRAL_GREY as ZERO_LINE_COLOUR,  # grey used on zero line — alias for readability
)


def _hex_to_rgba(hex_colour: str, alpha: float = 0.12) -> str:
    """Convert a #rrggbb hex string to rgba(...) for fill colours."""
    if not hex_colour.startswith("#") or len(hex_colour) != 7:
        return hex_colour
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def build_gains_chart(
    pdf: pd.DataFrame,
    *,
    colour: str = "#f97316",
    name: str = "Your net worth",
) -> go.Figure | None:
    """
    Bar chart: net worth change per period. Negative bars rendered red.
    Returns None if fewer than 2 data points.
    """
    s = pdf.sort_values("age").copy()
    s["gain"] = s["net_worth"].diff()
    s["pct_gain"] = s["net_worth"].pct_change() * 100
    s = s.dropna(subset=["gain"])
    if len(s) < 1:
        return None

    bar_colours = [colour if g >= 0 else NEGATIVE_COLOUR for g in s["gain"]]
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
    fig.add_hline(y=0, line=dict(color=ZERO_LINE_COLOUR, width=1))
    fig.update_layout(
        title=dict(text=f"Net worth change per period — {name}",
                   font=dict(size=14, color=TITLE_COLOUR), x=0),
        xaxis=dict(title="Age", gridcolor=GRID_COLOUR, zeroline=False),
        yaxis=dict(title="Change (£)", tickprefix="£", tickformat=",.0f",
                   gridcolor=GRID_COLOUR),
        plot_bgcolor="white", paper_bgcolor="white",
        height=240, margin=dict(l=70, r=40, t=50, b=50),
        showlegend=False,
    )
    return fig


def build_velocity_chart(
    pdf: pd.DataFrame,
    *,
    colour: str = "#f97316",
) -> go.Figure | None:
    """
    % growth rate per period — shows acceleration/deceleration.
    Returns None if fewer than 2 valid periods.
    """
    s = pdf.sort_values("age").copy()
    s["pct_change"] = s["net_worth"].pct_change() * 100
    s = s.dropna(subset=["pct_change"])
    if len(s) < 1:
        return None

    bar_colours = [colour if v >= 0 else NEGATIVE_COLOUR for v in s["pct_change"]]
    fig = go.Figure(go.Bar(
        x=s["age"], y=s["pct_change"],
        marker_color=bar_colours,
        hovertemplate="<b>Age %{x:.1f}</b><br>%{y:.1f}% growth<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=ZERO_LINE_COLOUR, width=1))
    fig.update_layout(
        title=dict(text="Wealth velocity (% growth per period)",
                   font=dict(size=13, color=TITLE_COLOUR), x=0),
        xaxis=dict(title="Age", gridcolor=GRID_COLOUR, zeroline=False),
        yaxis=dict(title="% change", ticksuffix="%", gridcolor=GRID_COLOUR),
        plot_bgcolor="white", paper_bgcolor="white",
        height=200, margin=dict(l=60, r=20, t=40, b=40),
        showlegend=False,
    )
    return fig


def build_cumulative_chart(
    pdf: pd.DataFrame,
    *,
    colour: str = "#f97316",
    name: str = "Your net worth",
    partner_pdf: pd.DataFrame | None = None,
    partner_colour: str = "#10b981",
    price_label: str = "nominal 2021",
) -> go.Figure:
    """Filled-area chart showing net worth over age — pure cumulative view."""
    fig = go.Figure()

    def _add(df: pd.DataFrame, col: str, nm: str):
        s = df.sort_values("age")
        fig.add_trace(go.Scatter(
            x=s["age"], y=s["net_worth"],
            mode="lines+markers",
            line=dict(color=col, width=2.5),
            marker=dict(color=col, size=6),
            fill="tozeroy",
            fillcolor=_hex_to_rgba(col),
            name=nm,
            hovertemplate=(
                f"<b>{nm}</b><br>Age %{{x:.1f}}<br>£%{{y:,.0f}}<extra></extra>"
            ),
        ))

    _add(pdf, colour, name)
    if partner_pdf is not None and len(partner_pdf) >= 2:
        _add(partner_pdf, partner_colour, "Partner")

    fig.update_layout(
        title=dict(text=f"Net worth over time ({price_label})",
                   font=dict(size=14, color=TITLE_COLOUR), x=0),
        xaxis=dict(title="Age", gridcolor=GRID_COLOUR, zeroline=False),
        yaxis=dict(title="Net worth (£)", tickprefix="£", tickformat=",.0f",
                   gridcolor=GRID_COLOUR),
        plot_bgcolor="white", paper_bgcolor="white",
        height=260, margin=dict(l=70, r=40, t=50, b=50),
        hovermode="x unified",
    )
    return fig
