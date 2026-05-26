"""
Build a summary statistics table from a personal net worth history.

Produces the DataFrame rendered in the 'Summary statistics' expander.
Pure logic — no Streamlit, no chart rendering — so it can be unit-tested
in isolation and re-used (e.g. in the PDF report).
"""
from __future__ import annotations
import pandas as pd

from charts._helpers import fmt, fmt_delta, safe_cagr, best_gain
from utils.inference import estimate_exact_percentile


def build_summary_stats(
    pdf: pd.DataFrame,
    benchmark: pd.DataFrame,
    label: str = "You",
) -> pd.DataFrame:
    """
    Compute the summary statistics row-list for a personal history.

    Returns a DataFrame with columns ['Metric', 'Value'], one row per
    statistic. Suitable for st.dataframe rendering.

    Always includes: age range, net worth range, total change.
    Optionally adds (when meaningful): CAGR, best single gain, worst single
    change, latest estimated percentile.

    `label` is prefixed to each Metric so You/Partner tables can be stacked.
    """
    if len(pdf) == 0:
        return pd.DataFrame(columns=["Metric", "Value"])

    s = pdf.sort_values("age")
    first, last = s.iloc[0], s.iloc[-1]
    age_span = float(last["age"]) - float(first["age"])
    nw_start = float(first["net_worth"])
    nw_end   = float(last["net_worth"])

    rows: list[dict] = [
        {"Metric": f"{label} — age range",
         "Value":  f"{first['age']:.1f} → {last['age']:.1f}  ({age_span:.1f} yrs)"},
        {"Metric": f"{label} — net worth range",
         "Value":  f"{fmt(nw_start)} → {fmt(nw_end)}"},
        {"Metric": f"{label} — total change",
         "Value":  fmt_delta(nw_end - nw_start)},
    ]

    cagr = safe_cagr(nw_start, nw_end, age_span)
    if cagr is not None:
        rows.append({"Metric": f"{label} — CAGR", "Value": f"{cagr*100:+.2f}%"})

    # Detect whether the diff-based stats below will run on annually-aggregated
    # data. When they do, the "best gain"/"worst change" rows describe a
    # year-long delta (not a single observation), so we label by calendar
    # year rather than the misleading "at age 31.9" — that age is just the
    # last observation of the year and reads as if there were a single event.
    will_aggregate = ("year" in s.columns
                      and s["year"].nunique() > 1
                      and len(s) > s["year"].nunique())

    def _period_label(age_val: float) -> tuple[str, str]:
        """Return (metric_qualifier, value_suffix) for a diff-based row.
        Aggregated → 'annual ... in 2024'. Raw → 'single ... at age 30.5'."""
        if will_aggregate:
            matched = s[s["age"] == age_val]
            if len(matched) > 0 and "year" in matched.columns:
                yr = int(matched["year"].iloc[-1])
                return "annual", f"in {yr}"
        return "single", f"at age {age_val:.1f}"

    bg = best_gain(s)
    if bg:
        bg_age, bg_amt, bg_pct = bg
        qual, suffix = _period_label(bg_age)
        metric = "best annual gain" if qual == "annual" else "best single gain"
        rows.append({
            "Metric": f"{label} — {metric}",
            "Value":  f"{fmt_delta(bg_amt)} ({bg_pct:+.0f}%) {suffix}",
        })

    # 'Worst single change' needs at least 2 rows to compute a diff. With 1 row,
    # diff() returns a single-element all-NaN series; calling .idxmin() on that
    # triggers a pandas FutureWarning and will eventually raise.
    #
    # Aggregate monthly/quarterly snapshots to annual first — mirrors the gains
    # chart, velocity chart and best_gain() so the table doesn't silently
    # report the biggest *monthly* drop while the chart shows year-over-year
    # bars.
    if len(s) >= 2:
        ws = s
        # Only aggregate if data spans 2+ years. Single-year monthly data
        # would collapse to 1 row and silently skip the worst-change metric.
        if will_aggregate:
            ws = ws.groupby("year", as_index=False).last().sort_values("year")
        if len(ws) >= 2:
            diffs = ws["net_worth"].diff()
            worst_idx = diffs.idxmin()
            if worst_idx is not None and not pd.isna(worst_idx):
                wl = float(diffs[worst_idx])
                wa = float(ws.loc[worst_idx, "age"])
                qual, suffix = _period_label(wa)
                metric = "worst annual change" if qual == "annual" else "worst single change"
                rows.append({
                    "Metric": f"{label} — {metric}",
                    "Value":  f"{fmt_delta(wl)} {suffix}",
                })

    pct = estimate_exact_percentile(nw_end, round(float(last["age"])), benchmark)
    if pct:
        rows.append({
            "Metric": f"{label} — latest est. percentile",
            "Value":  f"~{pct:.0f}th",
        })

    return pd.DataFrame(rows)
