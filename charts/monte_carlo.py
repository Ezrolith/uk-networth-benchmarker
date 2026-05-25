"""
Monte Carlo projection chart: P10/P25/P50/P75/P90 outcome bands across time,
plus optional sample paths and target line.
"""
from __future__ import annotations
import numpy as np
import plotly.graph_objects as go

from utils.monte_carlo import percentile_envelope


def build_monte_carlo_chart(
    paths: np.ndarray,
    *,
    start_age: float,
    target: float | None = None,
    show_sample_paths: int = 0,
    median_colour: str = "#1d4ed8",
    band_colours: tuple[str, str] = ("rgba(147,197,253,0.18)", "rgba(147,197,253,0.30)"),
    sample_path_colour: str = "rgba(148,163,184,0.25)",
    target_colour: str = "#f97316",
    price_label: str = "nominal 2021 prices",
) -> go.Figure:
    """
    Build the Monte Carlo outcome envelope chart.

    Parameters
    ----------
    paths : (n_sims, years+1) array of simulated net worth, as returned by
        utils.monte_carlo.run_monte_carlo.
    start_age : the user's current age (x-axis starting point).
    target : optional target net worth — drawn as a horizontal reference.
    show_sample_paths : if > 0, plot that many individual simulation paths
        underneath the envelope (capped at n_sims).
    """
    n_sims, n_steps = paths.shape
    years = n_steps - 1
    ages = np.arange(start_age, start_age + n_steps)

    env = percentile_envelope(paths, percentiles=(10, 25, 50, 75, 90))

    fig = go.Figure()

    # P10-P90 band (outer)
    fig.add_trace(go.Scatter(
        x=np.concatenate([ages, ages[::-1]]),
        y=np.concatenate([env[90], env[10][::-1]]),
        fill="toself", fillcolor=band_colours[0],
        line=dict(width=0), name="10th–90th percentile",
        hoverinfo="skip", showlegend=True,
    ))
    # P25-P75 band (inner — denser)
    fig.add_trace(go.Scatter(
        x=np.concatenate([ages, ages[::-1]]),
        y=np.concatenate([env[75], env[25][::-1]]),
        fill="toself", fillcolor=band_colours[1],
        line=dict(width=0), name="25th–75th percentile",
        hoverinfo="skip", showlegend=True,
    ))

    # Sample paths (optional, drawn faintly underneath)
    if show_sample_paths > 0:
        n_show = min(show_sample_paths, n_sims)
        # Spread the sampled paths roughly evenly through the simulation set
        sample_idx = np.linspace(0, n_sims - 1, n_show, dtype=int)
        for i, idx in enumerate(sample_idx):
            fig.add_trace(go.Scatter(
                x=ages, y=paths[idx],
                mode="lines",
                line=dict(color=sample_path_colour, width=0.8),
                showlegend=(i == 0),
                name="Sample path" if i == 0 else None,
                hoverinfo="skip",
            ))

    # Median path
    fig.add_trace(go.Scatter(
        x=ages, y=env[50],
        mode="lines",
        line=dict(color=median_colour, width=3),
        name="Median outcome",
        hovertemplate="<b>Median</b><br>Age %{x}<br>£%{y:,.0f}<extra></extra>",
    ))

    # Target line
    if target is not None and target > 0:
        fig.add_hline(
            y=target,
            line=dict(color=target_colour, width=2, dash="dash"),
            annotation_text=f"Target £{target:,.0f}",
            annotation_position="right",
            annotation=dict(
                font=dict(color=target_colour, size=11),
                bgcolor="white", bordercolor=target_colour,
                borderwidth=1, borderpad=4,
            ),
        )

    fig.update_layout(
        title=dict(
            text=f"Monte Carlo projection ({n_sims:,} simulations, {years} years)",
            font=dict(size=14, color="#1e293b"), x=0,
        ),
        xaxis=dict(title="Age", gridcolor="#e2e8f0", dtick=5, zeroline=False),
        yaxis=dict(title=f"Net worth (£, {price_label})", tickprefix="£",
                   tickformat=",.0f", gridcolor="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        height=400, margin=dict(l=70, r=80, t=60, b=60),
        hovermode="x unified",
    )
    return fig
