"""
Rescale data/was_asset_class.csv so its weighted-average component shares
match the ONS Wave 8 (April 2020 - March 2022) published aggregates while
preserving the relative shape of each age band.

ONS Wave 8 aggregate composition of household wealth (Great Britain):
    Net property wealth   40%
    Private pension       35%
    Financial wealth      14%
    Physical wealth       10%

Source: Total wealth in Great Britain, April 2020 to March 2022 (ONS bulletin)
https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/
    incomeandwealth/bulletins/totalwealthingreatbritain/april2020tomarch2022

Method:
  1. Compute current weighted-average per component (using rough household-count
     weights per age band).
  2. Multiply each cell by (target_agg / current_agg).
  3. Renormalise each row to sum to 100%.

This preserves the relative differences between age bands (younger = more
financial-weighted, older = more property/pension-weighted) while pulling
the population aggregate to the published Wave 8 numbers.

Run from project root:
    python scripts/update_asset_class_data.py
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

# Target aggregate component shares (Wave 8 published, %)
TARGET_AGG = {
    "property_pct":  40.0,
    "pension_pct":   35.0,
    "financial_pct": 14.0,
    "physical_pct":  10.0,
}

# Approximate household-count weights per age band (millions of GB households)
# Used only to compute the current weighted aggregate so we can derive
# rescaling factors. Source: ONS Households by age of HRP (rounded).
HOUSEHOLD_WEIGHTS = {
    "16-24": 0.5, "25-34": 2.8, "35-44": 4.5, "45-54": 5.0,
    "55-64": 5.0, "65-74": 5.0, "75+": 4.5,
}


def rescale(in_path: Path, out_path: Path) -> None:
    df = pd.read_csv(in_path)
    components = list(TARGET_AGG)

    total_w = sum(HOUSEHOLD_WEIGHTS.values())
    current_agg = {
        c: sum(df[df.age_band == band][c].iloc[0] * HOUSEHOLD_WEIGHTS[band]
               for band in HOUSEHOLD_WEIGHTS) / total_w
        for c in components
    }

    factors = {c: TARGET_AGG[c] / current_agg[c] for c in components}
    print("Multiplicative rescaling factors:")
    for c, f in factors.items():
        print(f"  {c:>14}: {current_agg[c]:5.1f}% -> {TARGET_AGG[c]:5.1f}%  (x{f:.3f})")

    # Apply factors and renormalise row to 100%
    out = df.copy()
    for c in components:
        out[c] = out[c] * factors[c]
    row_sums = out[components].sum(axis=1)
    for c in components:
        out[c] = (out[c] / row_sums * 100).round(1)

    # Update source label
    out["source"] = (
        "Wave 7 age-band shape rescaled to match ONS Wave 8 aggregate components "
        "(property 40%, pension 35%, financial 14%, physical 10%)"
    )
    out["data_year"] = 2021

    out.to_csv(out_path, index=False)

    # Verify weighted average is now close to target
    print("\nVerification (post-rescaling weighted averages):")
    for c in components:
        wavg = sum(out[out.age_band == band][c].iloc[0] * HOUSEHOLD_WEIGHTS[band]
                   for band in HOUSEHOLD_WEIGHTS) / total_w
        print(f"  {c:>14}: {wavg:5.2f}% (target {TARGET_AGG[c]}%)")

    print(f"\nWrote {out_path}")
    print("\nNew table:")
    print(out[["age_band", "property_pct", "pension_pct",
               "financial_pct", "physical_pct"]].to_string(index=False))


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    rescale(root / "data" / "was_asset_class.csv",
            root / "data" / "was_asset_class.csv")
