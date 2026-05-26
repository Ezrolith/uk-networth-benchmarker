# Scripts

A mix of data-refresh scripts (ONS-sourced) and developer-workflow scripts
(compile, release). Run all from the project root.

## Developer-workflow scripts

### `compile_check.py`

Whole-tree `py_compile` sanity check. Called by both `make compile` and
GitHub Actions CI. Walks every `.py` file under the project root (skipping
`__pycache__`, `.pytest_cache`, `.git`, `venv`) and reports any syntax errors.

```bash
python scripts/compile_check.py
```

Exits 0 on success, 1 with a list of failing files otherwise. Auto-picks up
new modules without anyone updating a list.

### `bump_version.py`

Single-command release version bump. Updates `APP_VERSION` in `app.py` and
`version` in `pyproject.toml` in one go, then prints a reminder of the
follow-up steps (CHANGELOG, CLAUDE.md, commit, tag).

```bash
python scripts/bump_version.py             # show current version
python scripts/bump_version.py 2.7 --dry   # show planned changes
python scripts/bump_version.py 2.7         # apply
```

Or via `make`: `make version`, then `python scripts/bump_version.py X.Y`.

## Data refresh scripts

Reproducible scripts that rebuild the project's two data files from ONS sources.

## `update_was_data.py`

Rebuilds `data/was_data.csv` from real ONS Wave 8 published medians by age band.

```bash
python scripts/update_was_data.py
```

**Source:** ONS *Wealth in Great Britain, April 2020 to March 2022*, Figure 2.
The seven published medians (one per age band 16–24 through 75+) are encoded
inline in the script. P25 and P75 by age band are derived by applying preserved
IQR ratios from the prior approximate dataset to the new medians.

To refresh from a future Wave 9 release: edit `ONS_WAVE8_MEDIAN_INCL_PENSION`
to the new medians, bump `DATA_YEAR` to the wave midpoint, update `SOURCE_INCL`
/ `SOURCE_EXCL` labels, and re-run. The IQR ratios will scale the new medians
into a complete P25/P50/P75 series by age.

## `update_asset_class_data.py`

Rebuilds `data/was_asset_class.csv` so the population-weighted aggregate
component shares match ONS Wave 8 published figures (property 40%, pension
35%, financial 14%, physical 10%).

```bash
python scripts/update_asset_class_data.py
```

The age-band relative shape is preserved (younger = more financial-weighted,
older = more property/pension-weighted). The script multiplicatively rescales
each component column by `target_aggregate / current_aggregate`, then
renormalises each row to sum to 100%.

## `was_total_wealth.xlsx`

The actual ONS Wave 8 dataset, downloaded from
[ons.gov.uk](https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/datasets/totalwealthwealthingreatbritain)
on 2026-05-25. Kept in the repo for data provenance — the file lets anyone
verify the figures in `data/was_data.csv` against the original ONS source
without needing internet access.

Table 2.4 contains whole-population P25/P50/P75 used as a cross-check in the
methodology panel. Table 2.11 contains distribution by age band (in fixed
wealth bins), which we don't use directly because we already have the
age-banded medians from Figure 2.

## Adding a new data source

If you add a new dataset (e.g. WAS Wave 9, or a regional breakdown), please:

1. Create a new script `update_<name>_data.py` following the same pattern
   (one constant per data point, transparent rescaling logic, sorted output).
2. Run `python -m pytest tests/` before committing — `test_inference.py`
   verifies the data passes through PCHIP interpolation cleanly.
3. Update `NEXT_STEPS.md` to mark the wave/region migration complete.
