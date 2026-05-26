"""
Percentile-over-time trajectory chart with band shading and delta annotation.
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go

from ._helpers import (
    TITLE_COLOUR, GRID_COLOUR, AXIS_LABEL_COLOUR,
    DEFAULT_PERSON_COLOUR, DEFAULT_PARTNER_COLOUR,
    DEFAULT_BENCHMARK_BAND_COLOUR,
)


_DEFAULT_BAND_FILLS = [
    (0,   25,  "rgba(219,234,254,0.30)", "Below P25"),
    (25,  50,  "rgba(191,219,254,0.30)", "P25–P50"),
    (50,  75,  "rgba(147,197,253,0.30)", "P50–P75"),
    (75,  100, "rgba(96,165,250,0.30)",  "Above P75"),
]


def build_percentile_chart(
    traj_you: pd.DataFrame,
    *,
    traj_partner: pd.DataFrame | None = None,
    smooth: bool = False,
    person_colour: str = DEFAULT_PERSON_COLOUR,
    partner_colour: str = DEFAULT_PARTNER_COLOUR,
    reference_colour: str = DEFAULT_BENCHMARK_BAND_COLOUR,
) -> go.Figure:
    """
    Estimated percentile over time, with P25/P50/P75 reference lines, shaded
    band zones, and a `+N pts` annotation showing total change since the
    first data point.

    Parameters
    ----------
    traj_you : DataFrame with cols (age, percentile, net_worth) — required.
    traj_partner : same shape, optional second trajectory to overlay.
    smooth : if True, apply a centred rolling mean to traj_you's percentile
        (window = max(3, n//4)). Only applied when len(traj_you) >= 4.
    """
    fig = go.Figure()

    # Reference percentile lines
    for y_val, label in [(75, "P75"), (50, "Median"), (25, "P25")]:
        fig.add_hline(
            y=y_val,
            line=dict(color=reference_colour, width=1, dash="dot"),
            annotation_text=label, annotation_position="right",
            annotation=dict(font=dict(color=AXIS_LABEL_COLOUR, size=10),
                            bgcolor="rgba(0,0,0,0)"),
        )

    # Band shading
    for y0, y1, fill_col, band_name in _DEFAULT_BAND_FILLS:
        fig.add_hrect(
            y0=y0, y1=y1, fillcolor=fill_col, line_width=0,
            annotation_text=band_name if y1 == 100 else "",
            annotation_position="right",
            annotation=dict(font=dict(size=9, color="#94a3b8")),
        )

    def _add(traj: pd.DataFrame, colour: str, name: str, fill: bool):
        if smooth and len(traj) >= 4:
            traj = traj.copy()
            traj["percentile"] = traj["percentile"].rolling(
                max(3, len(traj) // 4), center=True, min_periods=1
            ).mean()
        fig.add_trace(go.Scatter(
            x=traj["age"], y=traj["percentile"],
            mode="lines+markers",
            line=dict(color=colour, width=2.5),
            marker=dict(color=colour, size=7, line=dict(color="white", width=1.5)),
            fill="tozeroy" if fill else None,
            fillcolor=f"rgba(249,115,22,0.07)" if fill else None,
            name=name,
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Age %{x:.1f}<br>~%{y:.0f}th percentile<br>"
                "Net worth: £%{customdata:,.0f}<extra></extra>"
            ),
            customdata=traj["net_worth"],
        ))

    _add(traj_you, person_colour, "You", fill=True)
    if traj_partner is not None and len(traj_partner) >= 2:
        _add(traj_partner, partner_colour, "Partner", fill=False)

    # Delta annotation for "you"
    if len(traj_you) >= 2:
        start_pct = float(traj_you.iloc[0]["percentile"])
        end_pct   = float(traj_you.iloc[-1]["percentile"])
        delta_pct = end_pct - start_pct
        sign = "+" if delta_pct >= 0 else ""
        fig.add_annotation(
            x=float(traj_you.iloc[-1]["age"]), y=end_pct,
            text=f"{sign}{delta_pct:.0f} pts",
            showarrow=True, arrowhead=2, arrowcolor=person_colour,
            ax=30, ay=-25 if delta_pct >= 0 else 25,
            font=dict(size=11, color=person_colour),
            bgcolor="white", bordercolor=person_colour, borderwidth=1, borderpad=3,
        )

    fig.update_layout(
        title=dict(text="Estimated percentile over time",
                   font=dict(size=14, color=TITLE_COLOUR), x=0),
        xaxis=dict(title="Age", gridcolor=GRID_COLOUR, dtick=5, zeroline=False),
        yaxis=dict(title="Percentile", range=[0, 100], dtick=25,
                   ticksuffix="th", gridcolor=GRID_COLOUR),
        plot_bgcolor="white", paper_bgcolor="white",
        height=290, margin=dict(l=60, r=80, t=50, b=50),
        hovermode="x unified",
    )
    return fig
