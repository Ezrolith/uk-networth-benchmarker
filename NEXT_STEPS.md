# Next Steps — UK Net Worth Benchmarker

Ranked by value vs effort. Completed items archived at the bottom.

---

## Highest priority remaining

### New features (high value, moderate effort)
- [ ] **Side-by-side scenario compare** — "Plan A vs Plan B" view of two retirement configurations side-by-side.
- [ ] **Pension AA taper for high earners** — currently the wrapper tracker shows the standard £60k; add an income input so we can compute the £10k tapered allowance for adjusted income over £260k.
- [ ] **ISA bridge calculator** — model the "save in ISA until 55+, then access tax-free" strategy that bridges between FIRE-able age and pension access age.

### Chart / UX polish
- [ ] **Mobile layout** — sidebar collapses awkwardly on small screens; consider an `st.tabs` or top-of-page expander pattern for mobile.

### Data accuracy (next refresh)
- [ ] **Add WAS Wave 7 (2018–2020) as a historical comparison** — `was_data.csv` currently holds Wave 8 only. Adding Wave 7 with a wave selector toggle would let users compare distributions across the COVID period.

---

## v2 features

### Filters
- [ ] **Region filter** — WAS publishes regional breakdowns (London vs rest of UK). High value, requires adding regional data to `was_data.csv`.
- [x] **Wealth type filter** — sidebar radio (Total / Property / Pension / Financial / Physical) scales benchmark via PCHIP-interpolated WAS asset class shares; chart title and info banner update accordingly.

### Export
- [x] **Proper PDF report** — multi-page PDF with matplotlib charts (benchmark, trajectory, gains, what-if), data history table, benchmark context, and goals summary. Uses matplotlib/fpdf2 — no Chrome required.

---

## v3 stretch

- [ ] **International comparison** — US SCF, Canada SFS, normalised to PPP. Useful context, harder to keep current.
- [x] **Tax-adjusted view** — IHT exposure calculator: configurable NRB/RNRB/married threshold, shows taxable estate, IHT payable, after-IHT value and % lost.
- [x] **Forward projection with savings contributions** — what-if model now accepts a monthly savings contribution; uses FV-of-annuity formula alongside CAGR; projected percentile metrics reflect contributions.

---

## Completed ✓

### Session 1 (initial build, May 2026)
- [x] Core app: P25/P50/P75 benchmark chart, household/individual toggle, real/nominal, pension toggle
- [x] Personal CSV upload (handles Excel date-formatted years, decimal ages)
- [x] PCHIP interpolation from WAS age bands to single years
- [x] Methodology panel with full source documentation
- [x] ONS data point markers on household chart
- [x] Deploy to Streamlit Community Cloud
- [x] GitHub repo (Ezrolith/uk-networth-benchmarker, private)

### Session 2 (iterative enhancements, May 2026)
- [x] Log scale toggle
- [x] "You are here" vertical age line + horizontal net worth crosshair
- [x] Exact percentile estimate (~48th) via log-normal fit to P25/P50/P75
- [x] Percentile trajectory chart with band shading (Below P25 / P25–P50 / P50–P75 / Above P75)
- [x] Trajectory smoothing (rolling average toggle)
- [x] CAGR metric + doubling time caption
- [x] Average annual gain metric
- [x] Delta vs previous data point on net worth metric
- [x] Milestone progress bar toward median / P75
- [x] Milestone ETA projection (CAGR-compound)
- [x] Milestone tracker table (crossed vs projected for £10k–£1m)
- [x] Wealth milestone reference lines toggle (£100k / £250k / £500k / £1m)
- [x] P10/P90 toggle (log-normal derived tails)
- [x] Hover shows benchmark P25/P50/P75 inline alongside personal net worth
- [x] Zero reference line when personal data contains negatives
- [x] Shareable URL (personal data zlib+base64 encoded in query param)
- [x] Benchmark CSV download (sidebar, respects current settings)
- [x] Birth-year consistency validation on CSV upload
- [x] Excel date-artifact year detection
- [x] Legend renamed "ONS data point"
- [x] Plotly modebar + PNG export (2× resolution)
- [x] Percentile band metric display fix
- [x] Partner comparison mode (emerald green overlay, same pipeline)
- [x] Head-to-head leaderboard (age-adjusted percentile comparison)
- [x] Combined household net worth banner
- [x] Age range slider (zoom x-axis without discarding data)
- [x] Summary statistics expander (CAGR, best/worst year, percentile per person)
- [x] Data quality score (0–100, with per-criterion notes)
- [x] Percentile history CSV download
- [x] Best single-year gain annotation (arrow on main chart)
- [x] Percentile delta annotation on trajectory chart
- [x] Annual gains bar chart + wealth velocity (% growth) chart
- [x] Cumulative wealth area chart
- [x] Growth attribution table (returns vs savings split, adjustable return assumption)
- [x] What-if projection (3 independent CAGR scenarios, projected percentile per scenario)
- [x] Asset class breakdown stacked area chart (property/pension/financial/physical)
- [x] Personal asset composition overlay (user enters own % split)
- [x] Goal / FIRE calculator (target net worth, spending, FIRE number)
- [x] Savings rate calculator (% income to save to hit target)
- [x] Pension pot estimator (annuity-based, state pension offset)
- [x] FI tracker row (FIRE gap, implied weekly spending, FI progress %)
- [x] Monthly savings compound calculator (FV of annuity)
- [x] Relative wealth index (net worth / benchmark median × 100)
- [x] Median multiples display (X.Xx the median)
- [x] FIRE goal & pension progress bars with CAGR-ETA
- [x] Percentile heatmap (stacked colour bands across all ages)
- [x] Wealth distribution curve (interactive age slider, log-normal density)
- [x] Decile table (P10–P90 at user's age, published vs modelled)
- [x] Header badges (Household/Individual pill, Real/Nominal pill)
- [x] Annotation toggle (clean-screenshot mode)
- [x] Colourblind-safe palette toggle (Okabe-Ito)
- [x] Gender adjustment filter (Individual basis only, WAS-derived factors)
- [x] P25/P50/P75 edge labels on main chart
- [x] Birth-year cohort annotation below x-axis
- [x] Text report download (.md, dated)
- [x] kaleido added to requirements for PNG export
- [x] Real terms base year updated 2024 → 2026 (2026 CPI estimated ~141.7)
- [x] Sidebar crash fix (latest_nw pre-initialised before sidebar block)
- [x] App version string in footer (v2.1)
- [x] CLAUDE.md fully updated to reflect v2 architecture

### Session 3 (May 2026)
- [x] Note annotations on data points (optional column in CSV + manual entry; renders in hover tooltip)
- [x] Smarter milestone ETA for zero/negative starting NW (avg-gain fallback)
- [x] Forward projection with savings contributions (monthly £ input, FV-of-annuity formula)
- [x] Duplicate encode/decode helpers removed from data_loader.py
- [x] Wealth type filter (Property / Pension / Financial / Physical) scales benchmark by WAS component shares

### Session 7 (May 2026) — quality & data foundations + charts/ refactor

**Quality:**
- [x] **pytest suite (85 tests)** — `tests/test_inference.py` (18 tests on PCHIP interpolation, log-normal percentile fit, CPI math, individual + gender conversion, tail derivation, decile table, component filter), `tests/test_data_loader.py` (12 tests on CSV parsing, Excel-date year extraction, validation warnings, URL encode/decode round-trip, static loader schemas), `tests/test_charts_helpers.py` (24 tests on fmt edge cases, clean_note, safe_cagr filters, best_gain sorting), `tests/test_chart_builders.py` (31 smoke tests on asset_class, heatmap, distribution, gains, velocity, cumulative, percentile_trajectory, whatif builders).
- [x] **GitHub Actions CI** — `.github/workflows/ci.yml` runs on push/PR to master; matrix on Python 3.11 + 3.12; py_compile + pytest. Broken deploys caught before they ship.
- [x] **`.gitignore`** updated to exclude `.claude/`, `.pytest_cache/`, `.coverage`.

**Data:**
- [x] **Real ONS Wave 8 wealth data** (biggest credibility win) — `data/was_data.csv` now uses actual ONS-published median household wealth by age band from the Wealth in Great Britain bulletin (April 2020 to March 2022, Figure 2). Downloaded directly from ons.gov.uk. P25 and P75 are derived from the published median using preserved age-specific IQR ratios. `scripts/update_was_data.py` documents the derivation and is rerunnable.
- [x] **Asset class data refreshed** — `data/was_asset_class.csv` rescaled so the population-weighted aggregate matches ONS Wave 8 published shares (property 40%, pension 35%, financial 14%, physical 10%). Was previously off by ~7pp on financial. `scripts/update_asset_class_data.py` makes this reproducible.
- [x] **DATA_YEAR: 2019 → 2021** — Wave 8 midpoint. Nominal/real labels updated everywhere.
- [x] **Methodology panel rewritten** — distinguishes "ONS-published medians" from "derived quartiles", links to the ONS source, notes cross-check with the whole-population Table 2.4. All asset-class "approximate Wave 7" language replaced with the Wave 8 anchor description.

**Charts package extraction** (app.py: 3,105 → 2,486 lines; -20% in one session):
- [x] `charts/_helpers.py` — fmt, fmt_delta, clean_note, safe_cagr, best_gain, hover_template. Decoupled from Streamlit and module state.
- [x] `charts/asset_class.py` — build_asset_class_chart with price_label parameter.
- [x] `charts/heatmap.py` — build_heatmap; partner overlay added (was missing in original).
- [x] `charts/distribution.py` — build_distribution_chart with explicit price_label + colours.
- [x] `charts/gains.py` — build_gains_chart, build_velocity_chart, build_cumulative_chart. All three return None for single-point input (was silent empty figure).
- [x] `charts/percentile_trajectory.py` — build_percentile_chart with explicit colour params, band shading, delta annotation.
- [x] `charts/whatif.py` — build_whatif_figure refactored to take project_to_age / monthly_savings / actual_colour / price_label / scenario_colours as keyword args.
- [x] `charts/main_figure.py` — build_main_figure fully extracted; all dependencies (benchmark, personal_plot_df, partner_plot_df, colours, basis, wealth_component, age range, latest_*, etc.) passed explicitly. Migration complete.
- [x] **Sidebar Goal calculator split** — was one bundled expander with four sub-tools; now three focused expanders: "Wealth goal & FIRE number", "Retirement income & pension pot", "Savings rate calculator". Savings calculator gives helpful guidance when no personal data or non-positive CAGR.

**New feature: UK tax wrapper tracker — v2.6:**
- [x] In-app expander "UK tax wrapper utilisation (ISA · LISA · Pension)": inputs for current-year ISA + LISA + pension contributions, plus carryforward unused pension allowance from the previous 3 years. Outputs 3 progress bars with % utilisation, headroom amounts, and a smart-suggestion banner highlighting where the user has material capacity left and the tax relief it would unlock. 2025/26 allowances: ISA £20k, LISA £4k, Pension AA £60k.

**New feature: Monte Carlo (accumulation + decumulation) — v2.6:**
- [x] `utils/monte_carlo.py` — run_monte_carlo with normal-distribution annual returns, percentile_envelope, probability_of_reaching, probability_of_ruin. Seeded for reproducible UX.
- [x] `charts/monte_carlo.py` — band envelope (P10-P90 outer, P25-P75 inner) + median path + optional sample paths + target line.
- [x] App expander "Monte Carlo projection (stochastic returns)": sliders for expected return, volatility, target age, monthly contribution, target NW, number of sample paths. Outputs P10/P50/P90 final values + probability of reaching target.
- [x] **Equity/bond glide path option**: linear glide from start_equity_pct to end_equity_pct. Asset class assumptions: equity 5.5%/18%, bonds 1.5%/6%, equity-bond correlation 0.10. Portfolio variance includes the covariance term. UI radio toggles between fixed N(μ,σ) and glide-path mode.
- [x] **Stochastic drawdown** (inside the existing Retirement drawdown expander): 1,000 simulations with random returns of the pot during retirement. Shows probability of surviving to each age + colour-coded verdict (≥85% comfortable, ≥60% warning, <60% high risk). State pension correctly reduces withdrawal need from age 67.
- [x] 24 dedicated tests in tests/test_monte_carlo.py — shape, seeding determinism, mean ≈ FV at low vol, zero-vol determinism, contributions, envelope ordering, probability calculations, glide-path endpoints/monotonicity/single-year, portfolio_moments equity/bond/60-40, glide reduces P10-P90 spread, glide ignores mean/std args, chart smoke tests.

### Session 6 (May 2026) — retirement planning push (v2.5)
- [x] **Retirement income forecast** (new) — combines projected NW at retirement, pension share, state pension, annuity rate, and 4% drawdown into a single annual-income view with target comparison. In-app expander + PDF page.
- [x] **Drawdown / pot longevity simulator** (new) — year-by-year decumulation simulation with depletion age, life-expectancy comparison, sensitivity table over 1-6% real returns, optional state pension overlay, pot-balance chart, verdict banner. Closes the biggest gap vs leading retirement tools.
- [x] State pension default £11,500 → £12,400 (2026/27 estimate); help text updated.
- [x] Annuity rate assumption 5% → 6.5% at age 65 (UK gilt-linked rates).
- [x] Sidebar: 7 display toggles moved into a "Display options" expander; age range slider stays prominent.
- [x] Empty-state guidance: friendly banner pointing first-time users at the sidebar upload widget.
- [x] Methodology panel updated with retirement income + drawdown sections; stale "v2" region note removed.
- [x] REVIEW_LOG.md created with full Session 6 audit (findings, plan, results).

### Session 5 (May 2026) — audit & polish (v2.4)
- [x] Fix: `build_percentile_trajectory` crashed on empty/all-negative input — now returns typed empty DataFrame
- [x] Fix: PDF data history showed "Note: nan" on every row without a note (NaN-string ambiguity) — new `_clean_note()` helper
- [x] Fix: single-entry users saw "Your percentile has fallen from the ~50th at age 35 to the ~50th at age 35 (0 pct pts)" — trend bullet now requires meaningful age span AND ≥1 pct pt change
- [x] Fix: PDF benchmark table claimed P10/P90 via footnote but didn't show them — tail percentiles now appended to the benchmark before generating the report
- [x] Fix: tiny starting NW (£1.5k → £8k) produced absurd +133% CAGR and "reach median in ~1 year" projection — new `_safe_cagr()` helper requires starting NW ≥ £5,000; affects cover, summary stats, PDF
- [x] Remove dead code: unused `compute_twr()` function (~25 lines)
- [x] Update README: outdated v1 feature list + 2024 base year → current v2.4 feature set and 2026 base
- [x] Bump APP_VERSION → v2.4

### Session 4 (May 2026)
- [x] PDF report complete overhaul — fpdf2 FPDF subclass footer (fixes blank pages permanently), page numbers
- [x] Cover page redesign: large hero net worth, stat boxes (percentile, wealth index, CAGR), Key observations narrative
- [x] Key observations: percentile journey (from first positive NW entry to now), benchmark position, ETA to median
- [x] Benchmark comparison table with P10–P90, footnote distinguishing published vs log-normal-modelled values
- [x] Data history table: added Change column, correct ordinal suffixes (33rd/43rd/52nd not 33th/43th/52th)
- [x] Chart pages: each has a descriptive paragraph explaining what to read
- [x] Trajectory page: states current percentile in description
- [x] Gains chart: aggregated to calendar-year (last entry per year) — fixes mess when user has monthly entries; x-axis shows year integers
- [x] Gains page summary stats: Positive years, Average annual gain, Best/Worst year with year label
- [x] What-if page: projected values table (S1/S2/S3 net worth at target age vs benchmark median)
- [x] Goals page: visual progress bars (blue for targets, green for FI tracker); ETA with arrival age; avg-gain fallback when CAGR undefined
- [x] Methodology & Disclaimer final page
- [x] _fmt() negative sign fix: -£12k not £-12k (affects whole app)
- [x] App version string bumped to v2.3
