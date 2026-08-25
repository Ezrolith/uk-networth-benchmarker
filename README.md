# UK Net Worth Benchmarker

[![CI](https://github.com/Ezrolith/uk-networth-benchmarker/actions/workflows/ci.yml/badge.svg)](https://github.com/Ezrolith/uk-networth-benchmarker/actions/workflows/ci.yml)

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
- Wealth-component filter (Property / Pension / Financial / Physical) — the
  personal overlay switches to your wealth in that component, so the comparison
  is like-for-like
- Region filter — rescales the GB curve to a region's median wealth (ONS Wave 8,
  uniform factor; labelled as an approximation)
- Colourblind-safe palette toggle (Okabe-Ito)
- Chart-first layout with the analysis grouped into five tabs

### Personal overlay
- CSV upload or in-app table editor
- Optional `note` column on data points (shows in tooltips and report)
- Optional `liabilities` column (gross-vs-net display, debt-paydown line)
- Optional per-component columns (`property` / `pension` / `financial` /
  `physical`) for the wealth-component lens
- Auto-balancing wealth-mix sliders with a live £-makeup panel
- Partner overlay with head-to-head leaderboard
- Shareable link encoding personal data into the URL (nothing stored server-side)

### Analytics
- Continuous percentile estimate (log-normal fit to P25/P50/P75)
- Percentile trajectory chart over time
- Year-on-year gains (auto-aggregates monthly entries to annual)
- What-if projection with three CAGR scenarios + monthly savings
- Plan A vs Plan B scenario compare (net worth, implied percentile, FIRE gap)
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

Only `year`, `age` and `net_worth` are required:

```csv
year,age,net_worth,note
2020,28,12000,
2021,29,18500,
2022,30,27000,bought flat
2024,32,52000,changed job
```

Every other column is optional. `liabilities` enables the gross-vs-net display
and the debt-paydown line; the four component columns drive the wealth-component
lens (blank is *not* treated as £0, so partial data is fine):

```csv
year,age,net_worth,liabilities,property,pension,financial,physical,note
2022,30,27000,158000,12000,6000,5000,4000,bought flat
2024,32,52000,146000,30000,12000,6000,4000,changed job
```

Download the template from the sidebar, or see `data/personal_template.csv`.

## Data source

**ONS Wealth and Assets Survey Wave 8 (April 2020 – March 2022), Great Britain.**

This is still the latest published round. ONS suspended the survey's accredited-
statistics status from Round 8 while response-rate and quality issues are worked
through, and Round 9 (April 2022 – March 2024) had not been published as of
August 2026 — so the benchmark is deliberately pinned to Wave 8 rather than a
newer vintage.

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

GitHub Actions CI runs on every push (Python 3.11, 3.12, 3.13 and 3.14):
py_compile on every source file, then the full pytest suite. 3.14 is in the
matrix because Streamlit Community Cloud defaults to the newest Python that
Streamlit supports — without it, production would run an interpreter CI never
exercises. The CI gate also includes defensive tests against the most common
deploy failure modes:

- `tests/test_app_imports.py` parses `app.py` with `ast` and verifies every
  imported name resolves on its target module. Catches the
  "app.py references X but utils/uk_tax.py is stale" class of bug.
- `tests/test_requirements.py` scans every `.py` file for third-party
  imports and verifies each has a corresponding entry in `requirements.txt`.
  Catches the "forgot to add the new dep" class of bug.

## Tests

```bash
make test            # full suite, verbose (333 tests, ~30s)
make test-quick      # terse output, line-format failures only
make check           # py_compile + tests (matches CI)
```

## File structure

```
├── app.py                          Main Streamlit application (~4,100 lines)
├── requirements.txt
├── pyproject.toml                  Project metadata + pytest config
├── Makefile                        test / check / compile shortcuts
├── data/
│   ├── was_data.csv                Real ONS Wave 8 medians + derived quartiles
│   ├── was_asset_class.csv         Wave 8-aligned component shares
│   ├── personal_template.csv       Upload template (incl. optional columns)
│   └── demo_data.py                Baked-in history for 'Try with demo data'
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
│   │                                individual/gender conversion, CPI, region
│   ├── uk_tax.py                   UK tax-year rules: ISA/LISA, pension AA +
│   │                                taper, IHT, income tax, annuity assumption
│   ├── monte_carlo.py              Simulation engine + glide path
│   ├── data_quality.py             0-100 personal-data quality score
│   ├── summary.py                  Summary-statistics table builder
│   └── data_loader.py              CSV loading + share-link encode/decode
├── tests/                          333 tests, ~30s runtime
│   ├── conftest.py                 Shared session-scoped fixtures
│   ├── test_inference.py           test_uk_tax.py          test_monte_carlo.py
│   ├── test_data_loader.py         test_data_files.py      test_data_quality.py
│   ├── test_chart_builders.py      test_charts_helpers.py  test_summary.py
│   ├── test_app_imports.py         test_app_runtime.py     test_requirements.py
│   └── test_demo_data.py           test_compile_check.py   test_bump_version.py
├── scripts/                        Data refresh + release scripts
│   ├── update_was_data.py
│   ├── update_asset_class_data.py
│   ├── bump_version.py             Syncs version across app.py/pyproject/docs
│   └── compile_check.py            Whole-tree py_compile (CI + Makefile)
├── .github/workflows/ci.yml        py_compile + pytest on every push
├── .streamlit/config.toml          Blue theme
├── CLAUDE.md                       Project knowledge file
├── CHANGELOG.md                    Release-by-release change log
├── REVIEW_LOG.md                   Session-by-session audit notes
└── NEXT_STEPS.md                   Backlog
```

## Current version

**v2.19** — see `CHANGELOG.md` for the full release history and
`NEXT_STEPS.md` for the backlog.

## Tax year and market assumptions

UK tax rules are centralised in `utils/uk_tax.py` and currently reflect
**2026/27** (the `TAX_YEAR` constant). Every tax-year label in the UI
interpolates that constant, so rolling the app forward a year is a one-line
change there plus a check of the allowance values.

Two things in the codebase are *market* assumptions rather than tax rules, and
go stale on their own schedule:

- `ANNUITY_RATE_AT_65` in `utils/uk_tax.py` — recheck at least annually.
- `UK_CPI[2026]` in `utils/inference.py` — currently the June 2026 monthly
  index; replace with the published annual average in January 2027.
