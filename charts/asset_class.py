"""Stacked area chart: median wealth composition by age."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go


DEFAULT_ASSET_COLOURS = {
    "Property":  "#1d4ed8",
    "Pension":   "#7c3aed",
    "Financial": "#059669",
    "Physical":  "#d97706",
}


def build_asset_class_chart(
    series: pd.DataFrame,
    *,
    price_label: str = "nominal 2021 prices",
    asset_colours: dict[str, str] | None = None,
    title: str = "Median wealth composition by age",
    subtitle: str = "Component shares: approx WAS Wave 7; median anchor: ONS Wave 8",
) -> go.Figure:
    """
    Stacked area chart showing how property / pension / financial / physical wealth
    compose the median household total wealth at each age.

    `series` must have columns: age, component, value_gbp, value_pct
    (produced by utils.inference.build_asset_class_series)
    """
    colours = asset_colours or DEFAULT_ASSET_COLOURS

    fig = go.Figure()
    # Order matters for stacking — bottom to top
    for component in ["Physical", "Financial", "Pension", "Property"]:
        sub = series[series["component"] == component].sort_values("age")
        if len(sub) == 0:
            continue
        fig.add_trace(go.Scatter(
            x=sub["age"], y=sub["value_gbp"],
            mode="lines", stackgroup="one", name=component,
            line=dict(width=0.5, color=colours[component]),
            hovertemplate=(
                f"<b>{component}</b><br>Age %{{x}}<br>"
                "£%{y:,.0f} (~%{customdata:.0f}%)<extra></extra>"
            ),
            customdata=sub["value_pct"],
        ))

    fig.update_layout(
        title=dict(
            text=f"{title}<br><sub style='font-size:11px;color:#64748b'>{subtitle}</sub>",
            font=dict(size=14, color="#1e293b"), x=0,
        ),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", dtick=5, zeroline=False),
        yaxis=dict(
            title=f"Net worth (£, {price_label})",
            tickprefix="£", tickformat=",.0f", gridcolor="#e2e8f0",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        height=340, margin=dict(l=70, r=80, t=80, b=50), hovermode="x unified",
    )
    return fig
