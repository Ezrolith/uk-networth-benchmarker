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
No secrets or env vars needed. scipy + plotly install takes ~2 min on first cold start.

## File structure

```
app.py                    Main Streamlit app — all UI, chart builders, rendering
requirements.txt          streamlit, plotly, pandas, numpy, scipy
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
                          decile table, gender adjustment
  data_loader.py          CSV loading + shareable URL encode/decode helpers
.streamlit/config.toml    Blue theme (primaryColor #1d4ed8)
NEXT_STEPS.md             Prioritised enhancement backlog
```

## Key architectural decisions

**Single-file app** — all UI in `app.py`, all maths in `utils/`. No separate pages or routes.

**Caching** — `@st.cache_data` on all heavy computations with primitive-type keys (basis,
include_pension, real_terms, gender as strings/bools). DataFrames never used as cache keys.

**Benchmark pipeline** — `_build_benchmark(basis, include_pension, real_terms, gender)`:
1. Load `was_data.csv` → filter by `with_pension`
2. PCHIP interpolate from 7 band midpoints to single years (16-85)
3. If Individual: apply household→individual sharing factors
4. If Female: apply gender adjustment factors
5. If real_terms: CPI-adjust from 2019 to 2024

**Log-normal percentile model** — P25/P50/P75 at any age imply a log-normal distribution
via `mu = log(P50)`, `sigma = (log(P75)-log(P25))/1.349`. Used for:
- `estimate_exact_percentile()` — continuous percentile for user's net worth
- `derive_tail_percentiles()` — P10/P90 optional toggle
- `build_decile_table()` — full decile table at user's age
- `build_distribution_chart()` — interactive density curve

**Personal data privacy** — session state + optional URL query param encoding (zlib+base64).
No server transmission. Data lost on tab close unless shared URL is copied.

**Partner comparison** — all personal/partner logic runs through the same pipeline via
`_personal_data_section()` helper; uses COLOURS["partner"] (emerald green) throughout.

## Sidebar toggles (quick reference)

| Toggle | Effect |
|---|---|
| Household / Individual | Switches benchmark; Individual applies sharing factors |
| Gender (Individual only) | All / Male / Female — applies WAS gender gap factors |
| Include pension wealth | Adds/removes private pension component |
| Real terms (2024 £) | CPI-adjusts benchmark AND personal data |
| Log scale | Y-axis log; hides negative personal values |
| Show P10/P90 | Derived tails (log-normal model) |
| Wealth milestones | £100k/£250k/£500k/£1m reference lines |
| Smooth trajectory | Rolling average on percentile chart |
| Asset class breakdown | Stacked area: property/pension/financial/physical |
| Show annotations | Toggle all arrows/crosshairs (off = clean for screenshots) |

## Expanders (charts section)

- Summary statistics — CAGR, best/worst year, percentile, per person
  - Percentile history CSV download
- Wealth distribution curve — interactive slider, log-normal density
- Percentile trajectory — how percentile moved over time (+ partner overlay)
- Annual gains breakdown — bar chart + velocity (%) chart
- What-if projection — 3 scenarios, projected percentile at target age
- Asset class breakdown — stacked area (shown if toggle is on)
- Full decile table — P10-P90 at user's age (published vs modelled)
- Share your chart — URL with personal data encoded in query param
- Download benchmark data — CSV export of current benchmark

## Data source note

`data/was_data.csv` contains **approximations** of WAS Wave 7 published tables.
For production accuracy, replace with values from ONS WAS Wave 7 Bulletin Table 3.2.
URL: ons.gov.uk → Wealth and Assets Survey → Wave 7 (2018 to 2020)

## Current version

v2 — major feature expansion (May 2026). See NEXT_STEPS.md for backlog.

## Workflow

- Always commit to GitHub after changes (Streamlit auto-deploys)
- Bump version note in CLAUDE.md when making significant changes
- Run `python -m py_compile app.py utils/inference.py utils/data_loader.py` before committing
