# Claude Project Knowledge — UK Net Worth Benchmarker

## What this is

A Streamlit web app that visualises UK household and individual net worth distributions
(P25 / median / P75) by age, using ONS Wealth and Assets Survey data. Users can overlay
their own historical net worth to see where they sit in the distribution.

Portfolio piece for Multiverse; hosted on Streamlit Community Cloud.

## Run locally

```bash
cd "C:\Users\Peter\OneDrive\Documents\Claude\Projects\Networth Tracker"
pip install -r requirements.txt
streamlit run app.py
# → http://localhost:8501
```

## GitHub

- **Repo:** https://github.com/Ezrolith/uk-networth-benchmarker
- **Visibility:** Private
- **Default branch:** master

## Deploy

Streamlit Community Cloud → share.streamlit.io → connect Ezrolith/uk-networth-benchmarker → entry point `app.py`. No secrets or env vars needed.

## File structure

```
app.py                  Main Streamlit app — all UI and chart logic
requirements.txt        streamlit, plotly, pandas, numpy, scipy
data/
  was_data.csv          ONS WAS Wave 7 (2018–2020) approximate percentiles — 42 rows
                        Schema: age_band, age_band_min, age_band_max, band_midpoint,
                                percentile (p25/p50/p75), value_nominal, data_year,
                                source, with_pension (bool)
  personal_template.csv CSV template for user net worth upload
utils/
  inference.py          PCHIP interpolation, individual conversion, CPI adjustment
  data_loader.py        CSV loading helpers
.streamlit/config.toml  Blue theme (primaryColor #1d4ed8)
NEXT_STEPS.md           Prioritised enhancement backlog
```

## Key architectural decisions

**Single-file app pattern** — all UI in `app.py`, all maths in `utils/`. No separate pages.
Heavy computation is wrapped in `@st.cache_data` with primitive-type parameters so Streamlit
can cache it without hashing DataFrames.

**Data layer** — `data/was_data.csv` is the single source of truth for benchmark figures.
It's tidy format (one row per age_band × percentile × with_pension combination). To update
to a new WAS wave, add rows to this file and update `data_year`; no code changes needed.

**Inference layer** — everything derived from published data is clearly documented:
- Age-band → single year: PCHIP spline in `utils/inference.py:interpolate_benchmarks()`
- Household → individual: age-specific sharing factors in `_INDIVIDUAL_FACTORS_BY_MIDPOINT`
- Nominal → real: ONS CPI in `UK_CPI` dict; `DATA_YEAR = 2019`, `REAL_BASE_YEAR = 2024`

**Personal data** — held in Streamlit session state only. Never transmitted or stored.

## Data source note

The figures in `data/was_data.csv` are **approximations** of WAS Wave 7 published tables,
used for the initial build. For production accuracy, replace with values from the primary
ONS data tables:
- WAS Wave 7 Bulletin: Table 3.2 — Total Wealth by percentile and age band
- URL: ons.gov.uk → Wealth and Assets Survey → Wave 7 (2018 to 2020)

## Current version

v1 — MVP complete (May 2026). See NEXT_STEPS.md for the full enhancement backlog.

## Workflow

- Always commit to GitHub after changes
- Bump version note in CLAUDE.md when making significant changes
- Streamlit Community Cloud auto-deploys on push to master once connected
