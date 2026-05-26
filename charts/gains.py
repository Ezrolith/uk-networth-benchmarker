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
    DEFAULT_PERSON_COLOUR, DEFAULT_PARTNER_COLOUR,
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
    colour: str = DEFAULT_PERSON_COLOUR,
    name: str = "Your net worth",
) -> go.Figure | None:
    """
    Bar chart: net worth change per period. Negative bars rendered red.
    Returns None if fewer than 2 data points.

    If the input has multiple rows per calendar year (e.g. monthly snapshots),
    the data is aggregated to annual using the last row of each year. This
    keeps the chart readable when users have dense data and matches the PDF
    report's behaviour (no on-screen vs PDF visual inconsistency).
    """
    s = pdf.sort_values("age").copy()

    # Annual aggregation if monthly/quarterly data spans 2+ years.
    # Single-year monthly data has no annual aggregation to do — collapsing
    # 12 rows to 1 would zero the gain bars; keep the raw monthly bars instead.
    use_year_axis = False
    if ("year" in s.columns
            and s["year"].nunique() > 1
            and len(s) > s["year"].nunique()):
        s = s.groupby("year", as_index=False).last().sort_values("year")
        use_year_axis = True

    s["gain"] = s["net_worth"].diff()
    s["pct_gain"] = s["net_worth"].pct_change() * 100
    s = s.dropna(subset=["gain"])
    if len(s) < 1:
        return None

    bar_colours = [colour if g >= 0 else NEGATIVE_COLOUR for g in s["gain"]]
    # X axis: years (integer ticks) when we aggregated, age (continuous) otherwise
    x_values = s["year"].astype(int) if use_year_axis else s["age"]
    x_label  = "Year" if use_year_axis else "Age"
    x_hover  = "%{x}" if use_year_axis else "%{x:.1f}"

    fig = go.Figure(go.Bar(
        x=x_values, y=s["gain"],
        marker_color=bar_colours,
        name=name,
        hovertemplate=(
            f"<b>{x_label} {x_hover}</b><br>"
            "Gain: £%{y:,.0f}<br>"
            "Change: %{customdata:.1f}%<extra></extra>"
        ),
        customdata=s["pct_gain"],
    ))
    fig.add_hline(y=0, line=dict(color=ZERO_LINE_COLOUR, width=1))
    title_suffix = " (aggregated to annual)" if use_year_axis else ""
    fig.update_layout(
        title=dict(text=f"Net worth change per period — {name}{title_suffix}",
                   font=dict(size=14, color=TITLE_COLOUR), x=0),
        xaxis=dict(title=x_label, gridcolor=GRID_COLOUR, zeroline=False),
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
    colour: str = DEFAULT_PERSON_COLOUR,
) -> go.Figure | None:
    """
    % growth rate per period — shows acceleration/deceleration.
    Returns None if fewer than 2 valid periods.

    Matches `build_gains_chart`: when the input has multiple rows per
    calendar year (monthly/quarterly snapshots), data is aggregated to
    annual via the last row of each year so the two charts stay
    visually consistent.
    """
    s = pdf.sort_values("age").copy()

    # Annual aggregation if monthly/quarterly data spans 2+ years.
    # Single-year monthly data has no annual % growth to compute; fall through
    # to raw rows rather than collapsing to one row and returning None.
    use_year_axis = False
    if ("year" in s.columns
            and s["year"].nunique() > 1
            and len(s) > s["year"].nunique()):
        s = s.groupby("year", as_index=False).last().sort_values("year")
        use_year_axis = True

    s["pct_change"] = s["net_worth"].pct_change() * 100
    s = s.dropna(subset=["pct_change"])
    if len(s) < 1:
        return None

    bar_colours = [colour if v >= 0 else NEGATIVE_COLOUR for v in s["pct_change"]]
    x_values = s["year"].astype(int) if use_year_axis else s["age"]
    x_label  = "Year" if use_year_axis else "Age"
    x_hover  = "%{x}" if use_year_axis else "%{x:.1f}"

    fig = go.Figure(go.Bar(
        x=x_values, y=s["pct_change"],
        marker_color=bar_colours,
        hovertemplate=f"<b>{x_label} {x_hover}</b><br>%{{y:.1f}}% growth<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=ZERO_LINE_COLOUR, width=1))
    title_suffix = " (annual)" if use_year_axis else ""
    fig.update_layout(
        title=dict(text=f"Wealth velocity (% growth per period){title_suffix}",
                   font=dict(size=13, color=TITLE_COLOUR), x=0),
        xaxis=dict(title=x_label, gridcolor=GRID_COLOUR, zeroline=False),
        yaxis=dict(title="% change", ticksuffix="%", gridcolor=GRID_COLOUR),
        plot_bgcolor="white", paper_bgcolor="white",
        height=200, margin=dict(l=60, r=20, t=40, b=40),
        showlegend=False,
    )
    return fig


def build_cumulative_chart(
    pdf: pd.DataFrame,
    *,
    colour: str = DEFAULT_PERSON_COLOUR,
    name: str = "Your net worth",
    partner_pdf: pd.DataFrame | None = None,
    partner_colour: str = DEFAULT_PARTNER_COLOUR,
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
