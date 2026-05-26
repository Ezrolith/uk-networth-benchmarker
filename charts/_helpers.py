"""
Formatting and small utility helpers used across chart builders.

These are deliberately decoupled from Streamlit and module-level state so they
can be unit-tested in isolation and re-used in PDF generation.
"""
from __future__ import annotations
import pandas as pd

# ── Shared style constants ─────────────────────────────────────────────────────
# Colours that appear in every chart's layout — kept here so a single edit
# changes the whole package. Individual chart builders can still override.
#
# Names follow Tailwind palette conventions.
TITLE_COLOUR    = "#1e293b"   # slate-800
GRID_COLOUR     = "#e2e8f0"   # slate-200
AXIS_LABEL_COLOUR = "#64748b" # slate-500
ZERO_LINE_COLOUR  = "#cbd5e1" # slate-300

# Default colour roles (these match the app's COLOURS["person"]/COLOURS["partner"]
# in standard mode; the cb_safe palette overrides at call sites).
DEFAULT_PERSON_COLOUR  = "#f97316"   # orange-500
DEFAULT_PARTNER_COLOUR = "#10b981"   # emerald-500
DEFAULT_BENCHMARK_MEDIAN_COLOUR = "#1d4ed8"   # blue-700
DEFAULT_BENCHMARK_BAND_COLOUR   = "#93c5fd"   # blue-300

# Status colours
NEGATIVE_COLOUR = "#ef4444"   # red-500 — bars/segments representing losses
NEUTRAL_GREY    = "#94a3b8"   # slate-400 — zero lines, neutral text

# CAGR is only meaningful if the starting balance is non-trivial.
# Tiny starts (e.g. £100 → £8k) compute as 100%+ CAGR but tell us nothing useful.
CAGR_MIN_START = 5_000


def fmt(v: float) -> str:
    """Format a £ value compactly. Handles negatives correctly (-£12k, not £-12k)."""
    neg = v < 0
    av = abs(v)
    if av >= 1_000_000:
        s = f"£{av/1_000_000:.2f}m"
    elif av >= 1_000:
        s = f"£{av/1_000:.0f}k"
    else:
        s = f"£{av:.0f}"
    return f"-{s}" if neg else s


def fmt_delta(d: float) -> str:
    """Format as a signed delta string: '+£12k' or '-£3k'."""
    return ("+" if d >= 0 else "") + fmt(d)


def clean_note(row) -> str:
    """Extract a row's note as a clean string. Treats NaN, 'nan', and blanks as empty."""
    if not hasattr(row, "index") or "note" not in row.index:
        return ""
    val = row.get("note")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def safe_cagr(start_nw: float, end_nw: float, years: float) -> float | None:
    """Return CAGR if meaningful, else None. Filters out trivial starts and negative ends."""
    if years is None or years <= 0.5:
        return None
    if start_nw is None or end_nw is None:
        return None
    if start_nw < CAGR_MIN_START or end_nw <= 0:
        return None
    return (end_nw / start_nw) ** (1 / years) - 1


def hover_template(label: str) -> str:
    """Standard hover format for benchmark percentile lines."""
    return f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>"


def best_gain(pdf: pd.DataFrame) -> tuple[float, float, float] | None:
    """
    Return (age_at_gain, gain_amount, pct_gain) for the biggest single YoY jump.

    Matches the gains/velocity chart aggregation: when the input has multiple
    rows per calendar year (monthly/quarterly snapshots), data is collapsed
    to one row per year (the last observation of each year) before computing
    diffs. Without this the "Best year" annotation on the main chart and the
    Summary-stats "best single gain" row would silently report the largest
    *monthly* delta, contradicting the year-over-year framing of the chart
    and this function's own docstring.
    """
    if len(pdf) < 2:
        return None
    s = pdf.sort_values("age")
    if "year" in s.columns and len(s) > s["year"].nunique():
        s = s.groupby("year", as_index=False).last().sort_values("year")
        if len(s) < 2:
            return None
    gains = s["net_worth"].diff()
    pct_gains = s["net_worth"].pct_change()
    idx = gains.idxmax()
    if pd.isna(idx):
        return None
    return float(s.loc[idx, "age"]), float(gains[idx]), float(pct_gains[idx] * 100)
