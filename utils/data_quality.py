"""
Data quality scoring for personal net worth history.

Produces a 0-100 score plus human-readable notes describing what makes the
input strong or weak. Used by the Summary Statistics expander to give
users feedback on whether their data is dense / recent / long-spanning
enough to support the downstream calculations.
"""
from __future__ import annotations
from datetime import date
import pandas as pd


def compute_data_quality(pdf: pd.DataFrame) -> dict:
    """
    Rate the personal data on completeness and consistency.

    Returns {"score": int 0-100, "notes": list[str], "n": int, "span": float}.

    Scoring (max 100):
        +30  ≥10 data points    (+20 for 5-9, +10 for 2-4)
        +25  most recent ≥2024  (+15 for 2022-23, +5 older)
        +25  avg gap ≤1.5 yrs   (+15 for ≤3 yrs, +5 for less frequent)
        +20  age span ≥10 yrs   (+12 for 5-9, +5 for shorter)
    """
    n = len(pdf)
    age_span = float(pdf["age"].max() - pdf["age"].min()) if n >= 2 else 0.0
    avg_gap  = age_span / (n - 1) if n >= 2 else 999.0

    score = 0
    notes: list[str] = []

    # Data point count
    if n >= 10:   score += 30; notes.append("✅ 10+ data points")
    elif n >= 5:  score += 20; notes.append("🟡 5–9 data points (10+ recommended)")
    elif n >= 2:  score += 10; notes.append("⚠️ Only 2–4 data points")
    else:                      notes.append("❌ Need at least 2 data points")

    # Recency — bands are relative to "today", not a hardcoded year, so the
    # bar moves up year-by-year without manual maintenance.
    if "year" in pdf.columns and n > 0:
        max_year = int(pdf["year"].max())
        current_year = date.today().year
        if max_year >= current_year - 1:
            score += 25; notes.append(f"✅ Data up to {max_year}")
        elif max_year >= current_year - 3:
            score += 15; notes.append(f"🟡 Data to {max_year} — add recent figures")
        else:
            score += 5;  notes.append(f"⚠️ Data older than {current_year - 3}")

    # Update frequency
    if avg_gap <= 1.5:  score += 25; notes.append("✅ Annual or more frequent updates")
    elif avg_gap <= 3:  score += 15; notes.append("🟡 Updates every 1–3 years")
    else:               score += 5;  notes.append("⚠️ Infrequent updates (gaps > 3 yrs)")

    # Span
    if age_span >= 10:  score += 20; notes.append("✅ 10+ year history")
    elif age_span >= 5: score += 12; notes.append("🟡 5–9 year history")
    else:               score += 5;  notes.append("⚠️ Less than 5 years of history")

    return {"score": min(score, 100), "notes": notes, "n": n, "span": age_span}
