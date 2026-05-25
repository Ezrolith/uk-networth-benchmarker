"""
Formatting and small utility helpers used across chart builders.

These are deliberately decoupled from Streamlit and module-level state so they
can be unit-tested in isolation and re-used in PDF generation.
"""
from __future__ import annotations
import pandas as pd

# CAGR is only meaningful if the starting balance is non-trivial.
# Tiny starts (e.g. £100 → £8k) compute as 100%+ CAGR but tell us nothing useful.
_CAGR_MIN_START = 5_000


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
    if start_nw < _CAGR_MIN_START or end_nw <= 0:
        return None
    return (end_nw / start_nw) ** (1 / years) - 1


def hover_template(label: str) -> str:
    """Standard hover format for benchmark percentile lines."""
    return f"<b>{label}</b><br>Age %{{x}}<br>£%{{y:,.0f}}<extra></extra>"


def best_gain(pdf: pd.DataFrame) -> tuple[float, float, float] | None:
    """Return (age_at_gain, gain_amount, pct_gain) for the biggest single YoY jump."""
    if len(pdf) < 2:
        return None
    s = pdf.sort_values("age")
    gains = s["net_worth"].diff()
    pct_gains = s["net_worth"].pct_change()
    idx = gains.idxmax()
    if pd.isna(idx):
        return None
    return float(s.loc[idx, "age"]), float(gains[idx]), float(pct_gains[idx] * 100)
