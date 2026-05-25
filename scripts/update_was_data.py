"""
Rebuild data/was_data.csv from the actual ONS WAS Wave 8 (2020-2022) medians,
with P25/P75 derived by preserving the age-specific IQR ratios from the
previous approximate dataset.

Source for medians:
  ONS Wealth in Great Britain Wave 8, April 2020 to March 2022, Figure 2
  https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/
      incomeandwealth/bulletins/totalwealthingreatbritain/april2020tomarch2022
  CSV download:
  https://www.ons.gov.uk/generator?uri=...april2020tomarch2022/9384bb56&format=csv

Run from project root:
    python scripts/update_was_data.py
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

# ── Source data: ONS Wave 8 median household wealth by age band (£) ─────────
# Actual published figures, NOT approximate. Including private pension wealth.
ONS_WAVE8_MEDIAN_INCL_PENSION = {
    "16-24": 15_200,
    "25-34": 109_800,
    "35-44": 209_600,
    "45-54": 301_900,
    "55-64": 496_500,
    "65-74": 502_500,
    "75+":   373_100,
}

# Age-specific IQR ratios from the prior approximate dataset.
# These shape parameters (P25/P50 and P75/P50) are preserved while the P50
# anchor is updated to the actual ONS figure.  Older bands have narrower IQR.
P25_RATIO = {
    "16-24": 0.270, "25-34": 0.315, "35-44": 0.319, "45-54": 0.364,
    "55-64": 0.362, "65-74": 0.387, "75+":   0.417,
}
P75_RATIO = {
    "16-24": 2.959, "25-34": 2.428, "35-44": 2.164, "45-54": 2.073,
    "55-64": 1.970, "65-74": 1.948, "75+":   1.976,
}

# Approximate "excluding pension" share of total wealth at the median, by age.
# Younger: little pension → high share.  Middle: peak pension → low share.
# Older: crystallised pension → share rises again.  From prior dataset analysis.
EXCL_PENSION_SHARE = {
    "16-24": 0.716, "25-34": 0.646, "35-44": 0.640, "45-54": 0.592,
    "55-64": 0.583, "65-74": 0.748, "75+":   0.866,
}

BAND_META = {
    "16-24": (16, 24, 20),
    "25-34": (25, 34, 30),
    "35-44": (35, 44, 40),
    "45-54": (45, 54, 50),
    "55-64": (55, 64, 60),
    "65-74": (65, 74, 70),
    "75+":   (75, 89, 80),
}

DATA_YEAR = 2021  # mid-point of April 2020 to March 2022
SOURCE_INCL = "ONS Wealth in Great Britain Wave 8 (April 2020-March 2022), Figure 2 median; P25/P75 derived by IQR-ratio scaling"
SOURCE_EXCL = "ONS Wealth in Great Britain Wave 8 (April 2020-March 2022); excluding-pension series derived using age-specific component shares"


def build_rows() -> list[dict]:
    rows = []
    for band, p50_incl in ONS_WAVE8_MEDIAN_INCL_PENSION.items():
        amin, amax, mid = BAND_META[band]
        p25_incl = round(p50_incl * P25_RATIO[band])
        p75_incl = round(p50_incl * P75_RATIO[band])

        p50_excl = round(p50_incl * EXCL_PENSION_SHARE[band])
        p25_excl = round(p50_excl * P25_RATIO[band])
        p75_excl = round(p50_excl * P75_RATIO[band])

        for pct, val_incl, val_excl in [
            ("p25", p25_incl, p25_excl),
            ("p50", p50_incl, p50_excl),
            ("p75", p75_incl, p75_excl),
        ]:
            rows.append({
                "age_band": band, "age_band_min": amin, "age_band_max": amax,
                "band_midpoint": mid, "percentile": pct, "value_nominal": val_incl,
                "data_year": DATA_YEAR, "source": SOURCE_INCL, "with_pension": True,
            })
            rows.append({
                "age_band": band, "age_band_min": amin, "age_band_max": amax,
                "band_midpoint": mid, "percentile": pct, "value_nominal": val_excl,
                "data_year": DATA_YEAR, "source": SOURCE_EXCL, "with_pension": False,
            })
    return rows


if __name__ == "__main__":
    out = pd.DataFrame(build_rows())
    out = out.sort_values(["with_pension", "band_midpoint", "percentile"], ascending=[False, True, True])
    out = out.reset_index(drop=True)

    target = Path(__file__).resolve().parents[1] / "data" / "was_data.csv"
    out.to_csv(target, index=False)
    print(f"Wrote {len(out)} rows to {target}")
    print()
    print("New P50 values vs old (with pension):")
    pivot = out[(out["with_pension"]) & (out["percentile"] == "p50")][["age_band", "value_nominal"]]
    print(pivot.to_string(index=False))
