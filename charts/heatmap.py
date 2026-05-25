"""
Stacked colour-band heatmap of the wealth distribution by age.

Shows P10 → P25 → P50 → P75 → P90 as shaded bands across the full age axis,
giving an instant read of "where the money sits" at every age. Optional
personal trajectory overlaid.
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go

from utils.inference import derive_tail_percentiles


_DEFAULT_BAND_COLOURS = ["#eff6ff", "#bfdbfe", "#93c5fd", "#3b82f6", "#1d4ed8"]
_DEFAULT_BAND_LABELS  = ["10th–25th", "25th–50th", "50th–75th", "75th–90th"]


def build_heatmap(
    benchmark: pd.DataFrame,
    *,
    personal_plot_df: pd.DataFrame | None = None,
    partner_plot_df: pd.DataFrame | None = None,
    person_colour: str = "#f97316",
    partner_colour: str = "#10b981",
    price_label: str = "nominal 2021 prices",
    band_colours: list[str] | None = None,
) -> go.Figure:
    """
    Stacked colour-band visualisation of percentiles across all ages, with
    optional personal/partner trajectories overlaid.

    Parameters
    ----------
    benchmark : DataFrame with cols (age, percentile, value) covering at least
        p25, p50, p75 — p10 and p90 will be derived if absent.
    personal_plot_df / partner_plot_df : optional personal histories to overlay.
    """
    colours = band_colours or _DEFAULT_BAND_COLOURS

    tails = derive_tail_percentiles(benchmark)
    all_bm = pd.concat([benchmark, tails]).copy()

    ages = sorted(all_bm["age"].unique())
    pct_levels = ["p10", "p25", "p50", "p75", "p90"]
    fill_labels = ["10–25", "25–50 (lower mid)", "50–75 (upper mid)", "75–90"]

    fig = go.Figure()

    prev_vals = None
    for i, pct in enumerate(pct_levels):
        pct_data = all_bm[all_bm["percentile"] == pct].sort_values("age")
        if len(pct_data) == 0:
            continue
        curr_vals = [
            float(pct_data[pct_data["age"] == a]["value"].iloc[0])
            if len(pct_data[pct_data["age"] == a]) > 0 else None
            for a in ages
        ]
        if prev_vals is not None:
            label = fill_labels[i - 1] if i - 1 < len(fill_labels) else pct
            fig.add_trace(go.Scatter(
                x=list(ages) + list(reversed(ages)),
                y=curr_vals + list(reversed(prev_vals)),
                fill="toself",
                fillcolor=colours[i - 1] if i - 1 < len(colours) else colours[-1],
                line=dict(width=0),
                name=label,
                hoverinfo="skip",
                showlegend=True,
            ))
        prev_vals = curr_vals

    def _add_traj(df: pd.DataFrame, colour: str, name: str):
        df = df.sort_values("age")
        fig.add_trace(go.Scatter(
            x=df["age"], y=df["net_worth"],
            mode="lines+markers",
            line=dict(color=colour, width=2.5),
            marker=dict(color=colour, size=7),
            name=name,
            hovertemplate="Age %{x:.1f}<br>£%{y:,.0f}<extra></extra>",
        ))

    if personal_plot_df is not None and len(personal_plot_df) > 0:
        _add_traj(personal_plot_df, person_colour, "Your net worth")
    if partner_plot_df is not None and len(partner_plot_df) > 0:
        _add_traj(partner_plot_df, partner_colour, "Partner")

    fig.update_layout(
        title=dict(
            text=f"Wealth percentile landscape by age ({price_label})",
            font=dict(size=14, color="#1e293b"), x=0,
        ),
        xaxis=dict(title="Age", range=[15, 86], dtick=5, gridcolor="#e2e8f0"),
        yaxis=dict(title="Net worth (£)", tickprefix="£", tickformat=",.0f",
                   gridcolor="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=11)),
        plot_bgcolor="white", paper_bgcolor="white",
        height=380, margin=dict(l=70, r=40, t=60, b=50),
        hovermode="x unified",
    )
    return fig
