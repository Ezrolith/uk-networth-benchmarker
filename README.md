# UK Net Worth Benchmarker

An interactive web app showing UK net worth distributions (P25 / median / P75)
by age, with personal overlay, a transparent inference layer, and a polished
multi-page PDF report.

Live: https://uk-networth-benchmarker.streamlit.app

## Quick start

```bash
# Install dependencies (Python 3.11+ recommended)
pip install -r requirements.txt

# Run locally
streamlit run app.py
```

Open http://localhost:8501 in your browser.

## Features

### Benchmark display
- Age axis 16–85, P25 / median / P75 lines with shaded interquartile band
- Optional derived P10 / P90 tails (log-normal model)
- Household vs Individual basis (with gender adjustment for Individual)
- Nominal vs real-terms (2026 £) using ONS CPI
- With/without pension wealth toggle
- Wealth-component filter (Property / Pension / Financial / Physical)
- Colourblind-safe palette toggle (Okabe-Ito)

### Personal overlay
- CSV upload or in-app table editor
- Optional `note` column on data points (shows in tooltips and report)
- Partner overlay with head-to-head leaderboard
- Shareable link encoding personal data into the URL (nothing stored server-side)

### Analytics
- Continuous percentile estimate (log-normal fit to P25/P50/P75)
- Percentile trajectory chart over time
- Year-on-year gains (auto-aggregates monthly entries to annual)
- What-if projection with three CAGR scenarios + monthly savings
- Wealth-distribution density curve at any age
- Decile table at user's age
- Milestone tracker (£10k → £1m) with CAGR-based ETAs
- Goal & FIRE calculators with progress bars
- IHT exposure calculator (configurable thresholds and reliefs)
- Data-quality score for the personal history

### PDF report
- 9-page report: cover (hero number + stat boxes + observations) ·
  benchmark comparison + growth history · data history with change column ·
  4 chart pages with explanatory paragraphs · goals page with visual progress bars ·
  methodology + disclaimer
- Generated server-side via `fpdf2` + `matplotlib` (no Chrome required)

## Personal data CSV format

```csv
year,age,net_worth,note
2020,28,12000,
2021,29,18500,
2022,30,27000,bought flat
2024,32,52000,changed job
```

Download the template from the sidebar.

## Data source

ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain. The figures in
`data/was_data.csv` are approximations of published WAS percentile tables. For
research use, replace with primary ONS data tables.

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub
2. Go to share.streamlit.io → New app
3. Select repo + `app.py` as the entry point
4. Deploy — no secrets or environment variables needed

## File structure

```
├── app.py                    Main Streamlit application
├── requirements.txt
├── data/
│   ├── was_data.csv          WAS Wave 7 benchmark data (tidy format)
│   ├── was_asset_class.csv   Approximate WAS component shares by age band
│   └── personal_template.csv
├── utils/
│   ├── inference.py          Interpolation, individual conversion, CPI,
│                              log-normal percentile model, asset-class series
│   └── data_loader.py        CSV loading and share-link encode/decode
├── .streamlit/
│   └── config.toml           Blue theme
├── CLAUDE.md                 Project knowledge file
└── NEXT_STEPS.md             Backlog
```

## Current version

**v2.3** — see NEXT_STEPS.md for change log and backlog.
