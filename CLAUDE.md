# Claude Project Knowledge — UK Net Worth Benchmarker

## What this is

A Streamlit web app that visualises UK household and individual net worth distributions
(P25/P50/P75 and derived tails) by age, using ONS Wealth and Assets Survey data.
Users overlay their own historical net worth (and optionally a partner's) to see where
they sit in the distribution, track percentile progress over time, and run projections.

Portfolio piece for Multiverse; hosted on Streamlit Community Cloud.

## Run locally

```bash
cd "C:\Users\Peter\OneDrive\Documents\Claude\Projects\Networth Tracker"
pip install -r requirements.txt
streamlit run app.py
# → http://localhost:8501
```

## GitHub

- **Repo:** https://github.com/Ezrolith/uk-networth-benchmarker (private)
- **Default branch:** master
- **Auto-deploys:** Streamlit Community Cloud on every push to master

## Deploy

share.streamlit.io → connect Ezrolith/uk-networth-benchmarker → entry point `app.py`.
No secrets or env vars needed. scipy + kaleido + plotly install takes ~3 min on first cold start.

## File structure

```
app.py                    Main Streamlit app — all UI, chart builders, rendering (~1800 lines)
requirements.txt          streamlit, plotly, pandas, numpy, scipy, kaleido
data/
  was_data.csv            ONS WAS Wave 7 (2018-2020) approximate percentiles (42 rows)
                          Schema: age_band, band_midpoint, percentile (p25/p50/p75),
                                  value_nominal, data_year, source, with_pension (bool)
  was_asset_class.csv     Approximate WAS Wave 7 component share proportions by age band
                          Schema: age_band, band_midpoint, property_pct, pension_pct,
                                  financial_pct, physical_pct, source, data_year
  personal_template.csv   CSV template for user net worth upload
utils/
  inference.py            All maths: interpolation, individual/gender conversion, CPI,
                          log-normal percentile model, tail derivation, asset class series,
                          decile table, build_percentile_trajectory, build_distribution_chart
  data_loader.py          CSV loading, URL encode/decode (zlib+base64), data quality utils
.streamlit/config.toml    Blue theme (primaryColor #1d4ed8)
NEXT_STEPS.md             Full backlog with completed items archived
```

## Key architectural decisions

**Single-file app** — all UI in `app.py`, all maths in `utils/`. No separate pages or routes.

**Caching** — `@st.cache_data` on all heavy computations with primitive-type keys:
`_build_benchmark(basis, include_pension, real_terms, gender)`. DataFrames never used as cache keys.

**Benchmark pipeline** — `_build_benchmark(basis, include_pension, real_terms, gender)`:
1. Load `was_data.csv` → filter by `with_pension`
2. PCHIP interpolate from 7 band midpoints to single years (16–85)
3. If Individual: apply household→individual sharing factors (`_INDIVIDUAL_FACTORS_BY_MIDPOINT`)
4. If Female: apply gender adjustment factors (`_GENDER_FACTOR_FEMALE`)
5. If real_terms: CPI-adjust from 2019 to 2026 (`REAL_BASE_YEAR = 2026`)

**Log-normal percentile model** — P25/P50/P75 at any age imply a log-normal via
`mu = log(P50)`, `sigma = (log(P75)−log(P25))/1.349`. Used throughout:
- `estimate_exact_percentile()` — continuous ~Nth percentile display
- `derive_tail_percentiles()` — P10/P90 optional toggle
- `build_decile_table()` — P10–P90 table at user's age
- `build_distribution_chart()` — interactive log-normal density curve
- `build_whatif_figure()` — projected percentile at target age per scenario

**Colour palettes** — two palettes switchable at runtime via `cb_safe` sidebar toggle:
- Standard: blue benchmark (#1d4ed8), orange personal (#f97316), emerald partner (#10b981)
- Colourblind-safe (Okabe-Ito): blue (#0072b2), amber (#e69f00), bluish-green (#009e73)
`COLOURS` dict is reassigned after sidebar so all chart builders pick up the active palette.

**Personal data privacy** — session state + optional URL query param (zlib+base64, ~100 chars
for a typical history). No server transmission. Lost on tab close unless URL is copied.

**Partner comparison** — both people run through the identical pipeline via the reusable
`_personal_data_section(label, key_prefix)` helper. Partner uses COLOURS["partner"] throughout.

**Variable initialisation** — `latest_nw` and `latest_age` are set to `None` before the
sidebar block so goal/savings calculator widgets can safely reference them.

## Sidebar controls (quick reference)

| Control | Effect |
|---|---|
| Household / Individual | Switches benchmark basis |
| Gender (Individual only) | All / Male / Female — WAS-derived gender gap factors |
| Include pension wealth | Adds/removes private pension component |
| Real terms (2026 £) | CPI-adjusts benchmark AND personal data to 2026 prices |
| Log scale | Log Y-axis; negative personal values hidden with warning |
| Show P10 / P90 | Derived tails via log-normal model |
| Wealth milestones | £100k / £250k / £500k / £1m reference lines |
| Smooth trajectory | Rolling average on percentile trajectory chart |
| Asset class breakdown | Stacked area: property / pension / financial / physical |
| Show annotations | Toggle arrows + crosshairs (off = clean for screenshots) |
| Colourblind-safe palette | Okabe-Ito deuteranopia-friendly colours |
| Age range slider | Zoom x-axis (16–85); does not discard data |
| Your wealth composition | Enter own property/pension/financial/physical % split |
| Goal calculator | Target net worth, FIRE number, pension pot estimator, savings rate |
| Partner's net worth | Second person's data (same upload/manual options) |
| Download benchmark data | CSV of current benchmark respecting all settings |

## Expanders (main content area)

| Expander | Content |
|---|---|
| Summary statistics | CAGR, best/worst year, percentile — per person; data quality score; percentile history CSV download |
| Quick calculator | Monthly savings FV of annuity |
| Percentile landscape heatmap | Stacked colour bands (P10–P90) across all ages |
| Wealth distribution curve | Interactive age slider; log-normal density with user/partner markers |
| Full decile table at age X | P10–P90 table (published vs log-normal model) |
| Share your chart | URL with personal data encoded |
| Percentile trajectory | How percentile moved over time; partner overlay; band shading |
| Milestone tracker | Table of when each £milestone was/will be crossed |
| Annual gains breakdown | Bar chart + velocity (%) chart + cumulative area + growth attribution |
| What-if projection | 3 CAGR scenarios; projected net worth + percentile at target age |
| Asset class breakdown | Stacked area (shown if toggle is on); personal composition overlay |
| Text report download | Dated .md snapshot of key stats |

## Data source note

`data/was_data.csv` contains **approximations** of WAS Wave 7 published tables.
For production accuracy, replace with values from:
- ONS WAS Wave 7 Bulletin: Table 3.2 — Total Wealth by percentile and age band
- URL: ons.gov.uk → Wealth and Assets Survey → Wave 7 (2018 to 2020)

## Current version

**v2.1** (May 2026) — full feature set. See NEXT_STEPS.md for remaining backlog.

## Workflow

- Always commit to GitHub after changes (Streamlit auto-deploys on push to master)
- Run `python -m py_compile app.py utils/inference.py utils/data_loader.py` before committing
- Bump version string `APP_VERSION` in `app.py` footer for significant releases
- Bump version note in CLAUDE.md to match
