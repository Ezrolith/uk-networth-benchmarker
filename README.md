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
- **Monte Carlo projection** with stochastic returns (fixed N(μ,σ) or
  equity/bond glide path); shows P10/P50/P90 outcomes + probability of
  reaching target
- **Stochastic drawdown survival** — probability the pot lasts to each age
  in retirement under random returns; closes sequence-of-returns risk gap
- Wealth-distribution density curve at any age
- Decile table at user's age
- Milestone tracker (£10k → £1m) with CAGR-based ETAs
- Goal & FIRE calculators with progress bars
- Retirement income forecast (pension annuity + drawdown + state pension)
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

**ONS Wealth and Assets Survey Wave 8 (April 2020 – March 2022), Great Britain.**

`data/was_data.csv` uses the actual ONS-published median household wealth by
age band (from the Wealth in Great Britain bulletin, Figure 2). The 25th and
75th percentiles by age band are derived from the published median using
age-specific IQR ratios. Whole-population P25/P50/P75 (Table 2.4: £70,500 /
£293,700 / £662,100) cross-check the IQR approach. See the in-app
methodology panel for full details.

Reproducible refresh:
```bash
python scripts/update_was_data.py
python scripts/update_asset_class_data.py
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub
2. Go to share.streamlit.io → New app
3. Select repo + `app.py` as the entry point
4. Deploy — no secrets or environment variables needed

GitHub Actions CI runs on every push (Python 3.11 and 3.12): py_compile on
every source file, then the full pytest suite. The CI gate also includes
defensive tests against the most common deploy failure modes:

- `tests/test_app_imports.py` parses `app.py` with `ast` and verifies every
  imported name resolves on its target module. Catches the
  "app.py references X but utils/uk_tax.py is stale" class of bug.
- `tests/test_requirements.py` scans every `.py` file for third-party
  imports and verifies each has a corresponding entry in `requirements.txt`.
  Catches the "forgot to add the new dep" class of bug.

## Tests

```bash
make test            # full suite, verbose (180 tests, ~5s)
make test-quick      # terse output, line-format failures only
make check           # py_compile + tests (matches CI)
```

## File structure

```
├── app.py                          Main Streamlit application
├── requirements.txt
├── data/
│   ├── was_data.csv                Real ONS Wave 8 medians + derived quartiles
│   ├── was_asset_class.csv         Wave 8-aligned component shares
│   └── personal_template.csv
├── charts/                         Chart builders (extracted from app.py)
│   ├── _helpers.py                 fmt, hover_template, best_gain, etc.
│   ├── main_figure.py              The main benchmark + overlay chart
│   ├── asset_class.py              Stacked composition chart
│   ├── heatmap.py                  Percentile landscape
│   ├── distribution.py             Log-normal density at a chosen age
│   ├── gains.py                    Gains / velocity / cumulative
│   ├── percentile_trajectory.py    Percentile-over-time chart
│   ├── whatif.py                   Deterministic CAGR projection
│   └── monte_carlo.py              Stochastic projection (bands + paths)
├── utils/
│   ├── inference.py                Interpolation, log-normal percentiles,
│                                    individual/gender conversion, CPI
│   ├── monte_carlo.py              Simulation engine + glide path
│   └── data_loader.py              CSV loading + share-link encode/decode
├── tests/                          121 tests, ~5s runtime
│   ├── test_inference.py
│   ├── test_data_loader.py
│   ├── test_charts_helpers.py
│   ├── test_chart_builders.py
│   └── test_monte_carlo.py
├── scripts/                        Data refresh scripts
│   ├── update_was_data.py
│   └── update_asset_class_data.py
├── .github/workflows/ci.yml        py_compile + pytest on every push
├── .streamlit/config.toml          Blue theme
├── CLAUDE.md                       Project knowledge file
├── REVIEW_LOG.md                   Session-by-session audit notes
└── NEXT_STEPS.md                   Backlog
```

## Current version

**v2.3** — see NEXT_STEPS.md for change log and backlog.
