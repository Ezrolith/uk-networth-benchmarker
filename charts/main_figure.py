"""
The main UK net worth distribution figure.

The single highest-information chart in the app:
  - P25/P50/P75 lines + IQR band shading
  - Optional P10/P90 derived tails
  - ONS-published data point markers (household basis only)
  - Wealth milestone reference lines (toggle)
  - Personal trajectory + optional partner trajectory
  - Crosshair lines at the user's latest age and net worth
  - Best-year arrow annotation
  - Birth-year cohort label
  - Age-band boundary dividers
  - Percentile edge labels at the right side
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go

from utils.inference import derive_tail_percentiles
from charts._helpers import fmt, fmt_delta, clean_note, hover_template, best_gain


_DEFAULT_COLOURS = {
    "p25":     "#93c5fd",
    "p50":     "#1d4ed8",
    "p75":     "#93c5fd",
    "band":    "rgba(147,197,253,0.15)",
    "pub":     "#1e40af",
    "person":  "#f97316",
    "partner": "#10b981",
}


def build_main_figure(
    benchmark: pd.DataFrame,
    *,
    personal_plot_df: pd.DataFrame | None = None,
    partner_plot_df: pd.DataFrame | None = None,
    log_scale: bool = False,
    show_tails: bool = False,
    show_milestones: bool = False,
    show_annotations: bool = True,
    age_min: int = 16,
    age_max: int = 85,
    latest_age: float | None = None,
    latest_nw: float | None = None,
    basis: str = "Household",
    wealth_component: str = "Total",
    price_label: str = "nominal 2021 prices",
    birth_year_reference: int = 2026,
    colours: dict[str, str] | None = None,
) -> go.Figure:
    """
    Build the headline benchmark + personal-overlay figure.

    All visual state is passed explicitly so this function is pure and
    independent of Streamlit / module-level globals.
    """
    c = {**_DEFAULT_COLOURS, **(colours or {})}

    fig = go.Figure()

    p25 = benchmark[benchmark["percentile"] == "p25"].sort_values("age")
    p50 = benchmark[benchmark["percentile"] == "p50"].sort_values("age")
    p75 = benchmark[benchmark["percentile"] == "p75"].sort_values("age")

    # ── IQR band ──────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=pd.concat([p25["age"], p75["age"].iloc[::-1]]),
        y=pd.concat([p25["value"], p75["value"].iloc[::-1]]),
        fill="toself", fillcolor=c["band"],
        line=dict(width=0), name="P25–P75 range",
        hoverinfo="skip", showlegend=True,
    ))

    # ── Optional P10 / P90 tails ──────────────────────────────────────────────
    if show_tails:
        tails = derive_tail_percentiles(benchmark)
        for pct_lbl, label in [("p10", "10th (modelled)"), ("p90", "90th (modelled)")]:
            s = tails[tails["percentile"] == pct_lbl].sort_values("age")
            if len(s):
                fig.add_trace(go.Scatter(
                    x=s["age"], y=s["value"], mode="lines",
                    line=dict(color="#bfdbfe", width=1.5, dash="dot"),
                    name=label,
                    hovertemplate=f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>",
                ))

    # ── Main percentile lines ─────────────────────────────────────────────────
    for pct_data, colour, width, dash, label in [
        (p25, c["p25"], 2, "dash",  "25th percentile"),
        (p75, c["p75"], 2, "dash",  "75th percentile"),
        (p50, c["p50"], 3, "solid", "Median (P50)"),
    ]:
        fig.add_trace(go.Scatter(
            x=pct_data["age"], y=pct_data["value"], mode="lines",
            line=dict(color=colour, width=width, dash=dash),
            name=label, hovertemplate=hover_template(label),
        ))

    # ── ONS published markers (household basis only) ──────────────────────────
    if basis == "Household":
        pub_shown = False
        for pct_data in [p25, p50, p75]:
            pub = pct_data[pct_data["is_published"]]
            if len(pub):
                fig.add_trace(go.Scatter(
                    x=pub["age"], y=pub["value"],
                    mode="markers",
                    marker=dict(color=c["pub"], size=9, symbol="circle",
                                line=dict(color="white", width=1.5)),
                    name="ONS data point", showlegend=not pub_shown,
                    hovertemplate="<b>ONS published</b><br>Age %{x}<br>£%{y:,.0f}<extra></extra>",
                ))
                pub_shown = True
    else:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color="rgba(0,0,0,0)", size=1),
            name="Individual figures are derived estimates", showlegend=True,
        ))

    # ── Milestone reference lines ─────────────────────────────────────────────
    if show_milestones and not log_scale:
        for amount, mlabel in [(100_000, "£100k"), (250_000, "£250k"),
                               (500_000, "£500k"), (1_000_000, "£1m")]:
            fig.add_hline(
                y=amount, line=dict(color="#d1d5db", width=1, dash="dot"),
                annotation_text=mlabel, annotation_position="right",
                annotation=dict(font=dict(color="#9ca3af", size=10),
                                bgcolor="rgba(0,0,0,0)"),
            )

    # ── Personal overlay ──────────────────────────────────────────────────────
    bm_at_age = benchmark.set_index(["age", "percentile"])["value"]

    def _add_personal_trace(pdf: pd.DataFrame, colour: str, name: str,
                            show_crosshair: bool, show_horiz: bool):
        pdf = pdf.sort_values("age")
        has_neg = (pdf["net_worth"] < 0).any()

        if has_neg and not log_scale:
            fig.add_hline(
                y=0, line=dict(color="#94a3b8", width=1.5),
                annotation_text="Zero", annotation_position="right",
                annotation=dict(font=dict(color="#94a3b8", size=10)),
            )

        plot = pdf[pdf["net_worth"] > 0] if log_scale else pdf
        if not len(plot):
            return

        custom = []
        for _, row in plot.iterrows():
            ar = min(round(float(row["age"])), 85)
            yr = row.get("year", "")
            try:
                cp25 = bm_at_age.loc[(ar, "p25")]
                cp50 = bm_at_age.loc[(ar, "p50")]
                cp75 = bm_at_age.loc[(ar, "p75")]
            except KeyError:
                cp25 = cp50 = cp75 = float("nan")
            note = clean_note(row) if "note" in plot.columns else ""
            note_html = f"<br><i>Note: {note}</i>" if note else ""
            custom.append([yr, cp25, cp50, cp75, note_html])

        fig.add_trace(go.Scatter(
            x=plot["age"], y=plot["net_worth"],
            mode="lines+markers",
            line=dict(color=colour, width=2.5),
            marker=dict(color=colour, size=8, line=dict(color="white", width=1.5)),
            name=name,
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Age %{x:.1f} (year %{customdata[0]})<br>"
                "£%{y:,.0f}<br>"
                "<i>Benchmark: P25 £%{customdata[1]:,.0f} · "
                "Med £%{customdata[2]:,.0f} · P75 £%{customdata[3]:,.0f}</i>"
                "%{customdata[4]}<extra></extra>"
            ),
            customdata=custom,
        ))

        # Best gain annotation
        if show_annotations:
            best = best_gain(plot)
            if best:
                bg_age, bg_amount, bg_pct = best
                bg_nw_row = plot[plot["age"] == bg_age]
                bg_nw = float(bg_nw_row["net_worth"].iloc[0]) if len(bg_nw_row) else None
                if bg_nw and bg_amount > 0:
                    fig.add_annotation(
                        x=bg_age, y=bg_nw,
                        text=f"Best year<br>{fmt_delta(bg_amount)} ({bg_pct:.0f}%)",
                        showarrow=True, arrowhead=2, arrowcolor=colour,
                        ax=30, ay=-40,
                        font=dict(size=10, color=colour),
                        bgcolor="white",
                        bordercolor=colour, borderwidth=1, borderpad=3,
                    )

        lat_age = float(plot["age"].iloc[-1])
        lat_nw  = float(plot["net_worth"].iloc[-1])

        if show_crosshair and show_annotations:
            fig.add_vline(
                x=lat_age,
                line=dict(color=colour, width=1.5, dash="dash"),
                annotation_text=f"{name.split()[0]} (age {lat_age:.1f})",
                annotation_position="top",
                annotation=dict(font=dict(color=colour, size=11),
                                bgcolor="white", bordercolor=colour,
                                borderwidth=1, borderpad=4),
            )
        if show_horiz and lat_nw > 0 and not log_scale and show_annotations:
            fig.add_hline(
                y=lat_nw, line=dict(color=colour, width=1, dash="dot"),
                annotation_text=fmt(lat_nw),
                annotation_position="right",
                annotation=dict(font=dict(color=colour, size=11),
                                bgcolor="white", borderpad=3),
            )

    if personal_plot_df is not None and len(personal_plot_df) > 0:
        _add_personal_trace(personal_plot_df, c["person"], "Your net worth",
                            show_crosshair=True, show_horiz=True)

    if partner_plot_df is not None and len(partner_plot_df) > 0:
        _add_personal_trace(partner_plot_df, c["partner"], "Partner",
                            show_crosshair=True, show_horiz=False)

    # ── Age band boundary lines ───────────────────────────────────────────────
    for x_val in [24, 34, 44, 54, 64, 74]:
        fig.add_vline(x=x_val + 0.5, line=dict(color="#e2e8f0", width=1, dash="dot"))

    # ── Right-edge percentile labels ──────────────────────────────────────────
    if not log_scale and show_annotations:
        for pct_data, label in [(p25, "P25"), (p50, "P50"), (p75, "P75")]:
            edge_row = (pct_data[pct_data["age"] == age_max]
                        if age_max in pct_data["age"].values
                        else pct_data[pct_data["age"] == pct_data["age"].max()])
            if len(edge_row):
                fig.add_annotation(
                    x=age_max, y=float(edge_row["value"].iloc[0]),
                    text=label, showarrow=False,
                    xanchor="left", xshift=5,
                    font=dict(size=10, color="#64748b"),
                )

    # ── Birth year cohort label ───────────────────────────────────────────────
    if latest_age is not None and show_annotations:
        birth_year = round(birth_year_reference - latest_age)
        fig.add_annotation(
            x=latest_age, yref="paper", y=-0.09,
            text=f"born ~{birth_year}",
            showarrow=False,
            font=dict(size=9, color="#94a3b8"),
            xanchor="center",
        )

    # ── Layout ────────────────────────────────────────────────────────────────
    yaxis_cfg = dict(
        title=f"Net worth (£, {price_label})" + (" — log scale" if log_scale else ""),
        type="log" if log_scale else "linear",
        tickprefix="£",
        **({} if log_scale else {"tickformat": ",.0f",
                                 "zeroline": True, "zerolinecolor": "#cbd5e1"}),
        gridcolor="#e2e8f0", showgrid=True,
    )

    component_suffix = (f" · {wealth_component} wealth only"
                        if wealth_component != "Total" else "")
    fig.update_layout(
        title=dict(
            text=(f"UK net worth distribution — {basis.lower()} basis, "
                  f"{price_label}{component_suffix}"),
            font=dict(size=17, color="#1e293b"), x=0,
        ),
        xaxis=dict(title="Age", range=[age_min - 0.5, age_max + 0.5],
                   dtick=5, gridcolor="#e2e8f0", showgrid=True, zeroline=False),
        yaxis=yaxis_cfg,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=12)),
        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
        height=max(380, 560 - max(0, (85 - (age_max - age_min)) * 2)),
        margin=dict(l=70, r=90, t=80, b=60),
    )
    return fig
