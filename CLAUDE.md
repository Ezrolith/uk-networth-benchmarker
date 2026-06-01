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
app.py                    Main Streamlit app — UI, sidebar, rendering, plus build_main_figure
                          (the last builder not yet in charts/). ~2,650 lines.
requirements.txt          streamlit, plotly, pandas, numpy, scipy, matplotlib, fpdf2
data/
  was_data.csv            ONS WAS Wave 8 (Apr 2020 – Mar 2022) — real published P50 by age,
                          P25/P75 derived from IQR ratios (42 rows)
                          Schema: age_band, band_midpoint, percentile (p25/p50/p75),
                                  value_nominal, data_year, source, with_pension (bool)
  was_asset_class.csv     Wave 7 age-band shape rescaled to ONS Wave 8 aggregates
                          (property 40%, pension 35%, financial 14%, physical 10%)
                          Schema: age_band, band_midpoint, property_pct, pension_pct,
                                  financial_pct, physical_pct, source, data_year
  personal_template.csv   CSV template for user net worth upload
                          (year, age, net_worth, liabilities [optional], note)
charts/                   All chart builders (extraction complete — see __init__.py)
  _helpers.py             fmt, fmt_delta, clean_note, safe_cagr, best_gain, hover_template
  main_figure.py          THE main benchmark + personal overlay chart
  asset_class.py          Stacked area: median wealth composition by age
  heatmap.py              Percentile landscape (P10–P90 bands across all ages)
  distribution.py         Log-normal density curve at a chosen age
  gains.py                Three builders: gains bars, velocity bars, cumulative area
  percentile_trajectory.py How estimated percentile has changed over time
  whatif.py               Forward projection: CAGR scenarios + monthly savings
  monte_carlo.py          Stochastic projection: band envelope + sample paths
utils/
  inference.py            All maths: interpolation, individual/gender conversion, CPI,
                          log-normal percentile model, tail derivation, asset class series,
                          decile table, build_percentile_trajectory
  data_loader.py          CSV loading, URL encode/decode (zlib+base64)
  monte_carlo.py          run_monte_carlo + envelope + probability functions
  uk_tax.py               All UK 2025/26 tax + demographic constants and helpers:
                          - Pension AA taper for £260k+ adjusted income
                          - effective_pension_allowance (AA + carryforward)
                          - isa_remaining / lisa_remaining (age-aware)
                          - pension_relief_estimate / lisa_bonus
                          - iht_payable + IHT_BANDS (4 scenarios up to £1m)
                          - life_expectancy_at(retirement_age) (ONS 2020-22)
                          - STATE_PENSION_AGE, STATE_PENSION_2026_27 (£12,548)
                          - income_tax_2025_26 (rUK bands + PA taper / 60% trap)
                          - tax_free_lump_sum (25% PCLS, capped at LSA £268,275)
                          - All constants exported (ISA_ALLOWANCE, PENSION_AA,
                            NIL_RATE_BAND, RESIDENCE_NIL_RATE_BAND, etc.)
  data_quality.py         compute_data_quality(pdf) → 0–100 score + notes list
                          for personal data completeness/recency/density/span
  summary.py              build_summary_stats(pdf, benchmark, label) → table
                          DataFrame for the Summary Statistics expander
scripts/
  compile_check.py        Whole-tree py_compile (used by CI + Makefile)
  update_was_data.py      Rebuilds was_data.csv from ONS Wave 8 published medians
  update_asset_class_data.py  Rescales was_asset_class.csv to Wave 8 aggregates
tests/
  test_inference.py       21 tests on inference layer (incl. CPI-series sanity)
  test_data_loader.py     27 tests on CSV parsing (incl. Excel serial dates,
                          implausible-age warnings, optional liabilities column)
                          + URL encode/decode
  test_charts_helpers.py  24 tests on formatting helpers
  test_chart_builders.py  45 smoke tests on chart builders (incl. main_figure
                          and gains-chart annual aggregation)
  test_monte_carlo.py     28 tests on simulation, glide path, envelope,
                          probabilities, chart
  test_uk_tax.py          59 tests on pension taper, ISA/LISA remaining,
                          relief estimates, LISA bonus, IHT payable + bands,
                          state pension + life expectancy, income tax bands +
                          PA taper, tax-free lump sum cap
  test_demo_data.py       8 tests verifying the demo data shape, CPI round-trip,
                          and percentile trajectory upward
  test_data_quality.py    9 tests on the 0–100 data quality scorer
  test_summary.py         10 tests on build_summary_stats (incl. single-row
                          edge case)
  test_app_imports.py     6 defensive tests that parse app.py's import block
                          with `ast` and verify every imported name exists in
                          its target module. Catches the 2026-05-25 deploy
                          incident class of bug (app.py references X but
                          utils/uk_tax.py is stale) in CI.
  test_app_runtime.py     15 Streamlit AppTest integration tests — app loads
                          without exception, demo button flow, no duplicate
                          widget keys, share URL bootstrap, Excel-serial CSV
                          end-to-end, PDF Monte Carlo page presence.
  test_requirements.py    4 tests verifying requirements.txt covers every
                          third-party import in the codebase and is well-formed.
                          Catches the other deploy failure mode (forgot to add
                          a new dep to requirements.txt).
  test_data_files.py      11 tests verifying data/*.csv schemas + invariants
  test_compile_check.py   3 tests around scripts/compile_check.py
  test_bump_version.py    5 tests around the version-bump script
  conftest.py             Session-scoped shared fixtures (benchmark, raw_was,
                          asset_series, personal_history)
                          (292 tests total, ~28s runtime)
.github/workflows/ci.yml  pytest + py_compile on push/PR (Py 3.11, 3.12, 3.13)
.streamlit/config.toml    Blue theme (primaryColor #1d4ed8)
NEXT_STEPS.md             Full backlog with completed items archived
REVIEW_LOG.md             Session-by-session audit notes
```

## Key architectural decisions

**Single-file app** — all UI in `app.py`, all maths in `utils/`. No separate pages or
routes. The main content area is organised into five `st.tabs` (the benchmark chart +
headline metrics render above the tabs; methodology renders as a full-width panel below
them). Sections still execute top-to-bottom — tabs are display grouping only, so they read
globals from the head and define their own locals.

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
| Wealth component | Total / Property / Pension / Financial / Physical — scales benchmark by WAS component shares |
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

`data/was_data.csv` now contains the **actual ONS-published medians** by age band
from Wealth in Great Britain, April 2020 to March 2022 (Wave 8, Figure 2). P25 and
P75 are derived from the published median using age-specific IQR ratios — these
are derived not published. The whole-population published quartiles (Table 2.4:
P25 £70,500, P50 £293,700, P75 £662,100) sit inside the by-age range, which
cross-checks the IQR-ratio approach.

`data/was_asset_class.csv` shares are rescaled so the population-weighted
aggregate matches Wave 8 published shares (40/35/14/10). Reproducible via
`scripts/update_was_data.py` and `scripts/update_asset_class_data.py`.

## Testing

```bash
python -m pytest tests/ -v          # 292 tests, ~28s
python -m pytest tests/test_inference.py    # just the maths
python -m py_compile app.py utils/inference.py utils/data_loader.py
```

CI runs the same on every push (`.github/workflows/ci.yml`, matrix on Py 3.11 + 3.12 + 3.13).

## Current version

**v2.12** (June 2026) — Session 9 (part 5): **interactive wealth-mix editor**.
The sidebar composition input is now four **auto-balancing sliders** that always
sum to 100% (move one, the others rebalance via an `on_change` callback). A live
**£-makeup panel** under the main chart splits your net worth across components
(horizontal bar + per-component metrics) and shows the drawable/investable
subtotal and its 4% income, updating as you slide. `personal_asset_split` is now
always set. 292 tests green. See CHANGELOG.md.

**v2.11** (June 2026) — Session 9 (part 4): **spending realism + liabilities**.
The 4%/25× FIRE figures now flag that they use *total* net worth and, when a
wealth-composition split is entered, show an **investable-wealth** figure that
excludes home equity and pre-57 pension (stops overstating FIRE readiness).
Plain-language explainers added ("roughly N in 100 people your age have less";
"at 4% this funds ~£X/yr"). New **optional `liabilities`** CSV / manual-entry
column with a gross-vs-net display and CSV round-trip (net worth stays the
benchmark input). +4 data-loader tests, 292 green. See CHANGELOG.md.

**v2.10** (June 2026) — Session 9 (part 3): **information architecture**. The
benchmark chart now renders first (under the headline metrics), and the analysis
sections are grouped into five `st.tabs` (📊 Where you stand · 📈 Your progress ·
🎯 Planning & projections · 🏛️ Tax & estate · 📋 Share & export), with methodology
as a reference panel below. Fixed the headline metric grid (`st.columns(5)` so
"Gap to median" gets its own column) and added a single-data-point hint. Sidebar
calculators deliberately left in place (they feed the metric row above the tabs —
variable-ordering risk). 288 tests green. See CHANGELOG.md.

**v2.9** (June 2026) — Session 9 (part 2): **retirement income realism**. New
`income_tax_2025_26()` + `tax_free_lump_sum()` in utils/uk_tax.py. The
Retirement income forecast now models the 25% tax-free pension lump sum
(annuitising only the remaining 75%) and shows a **net-of-tax** annual income
(rUK 2025/26) alongside pre-tax; the target check uses the net figure. Added a
second bridge leg (pension access → state pension), a drawdown tax caveat, and
mirrored it all in the PDF report. +10 uk_tax tests, 288 green. See CHANGELOG.md.

**v2.8** (June 2026) — Session 9: data-accuracy, correctness & honesty pass
(no new features). CPI table rebuilt from real ONS annual averages — fixes a
pre-2015 base-splice (a fake ~7% deflation at 2014→2015) and a stalled-2020
value that skewed every real-terms figure; state pension 2026/27 → £12,548;
IHT freeze → April 2031; goal/FIRE ETA + savings-rate CAGR now routed through
`safe_cagr` (no more fantasy CAGR on tiny starts); regional methodology table
corrected (South East is the wealthiest region; London's median sits *below*
the GB median); percentile ±5–10pt uncertainty surfaced; nominal/real notes on
the projection panels; cash-ISA-£12k and pensions-in-IHT-estate (both 6 Apr
2027) flagged; `bump_version.py` now syncs the module docstring too. 278 tests,
all green. See CHANGELOG.md for the full v2.8 entry.

**v2.7** (May 2026) — Session 8 added the PDF Monte Carlo page, MC
'Reroll' button, IHT combined household estate toggle, LISA 40-50 gap
modelling, shareable URL with partner data, enriched text report, manual
entry NaN handling, dynamic recency scoring, and a substantial defensive
layer (24 new tests across test_app_imports, test_requirements,
test_data_files, test_compile_check, test_bump_version). All chart files
migrated to shared style constants. Bug fix: `run_monte_carlo` clamps
depleted paths at zero. 238 tests, all green. See CHANGELOG.md for the
full v2.7 entry.

**v2.6** (May 2026) — Session 7 added:
- Full charts/ package extraction (all 8 builders out of app.py)
- pytest suite: 170 tests, ~5s runtime, with shared fixtures in conftest.py
- GitHub Actions CI on Py 3.11 + 3.12
- Real ONS Wave 8 data + Wave 8-aligned asset class shares
- Monte Carlo projection with stochastic returns + equity/bond glide path
- Stochastic drawdown / pot survival probability (sequence-of-returns risk)
- UK tax rules consolidated in `utils/uk_tax.py`: pension AA + taper +
  carryforward, ISA + LISA (age-aware), pension relief, LISA bonus,
  IHT with 4 scenarios up to £1m
- ISA / accessible-wealth bridge calculator (early retirement)
- 'Try with demo data' empty-state button + CSV download
- CSV parser robustness (whitespace, ISO dates, extra columns)
- CPI out-of-range warning when real-terms mode is on
- Footer disclaimer

app.py: 3,105 → 2,737 lines (-12%). charts/: 0 → 8 builders.
utils/: +monte_carlo +uk_tax. tests/: 0 → 170 tests across 6 files.

See NEXT_STEPS.md and REVIEW_LOG.md for the full session log.

## Workflow

- Always commit to GitHub after changes (Streamlit auto-deploys on push to master)
- Run `python -m pytest tests/ -q` before committing — should be all green
- Run `python -m py_compile app.py utils/inference.py utils/data_loader.py` if you skipped tests
- Bump version string `APP_VERSION` in `app.py` footer for significant releases
- Bump version note in CLAUDE.md to match
