# Changelog

All notable changes to UK Net Worth Benchmarker.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
see `REVIEW_LOG.md` for session-by-session audit notes and rationale.

---

## [2.15] — June 2026 (Session 9, part 8)

Scenario A/B compare.

### Added
- **Plan A vs Plan B** projection at the top of the Planning tab: set two plans
  (monthly saving, annual real return, horizon) and compare projected net worth,
  the implied percentile at the horizon age, and each plan against your FIRE
  number — side-by-side metrics + a comparison bar chart + a verdict. Reuses the
  log-normal percentile model and an FV-of-annuity projection. 297 tests green.

---

## [2.14] — June 2026 (Session 9, part 7)

Sidebar declutter: the planning calculators moved into the 🎯 Planning tab.

### Changed
- The three calculators (**Wealth goal & FIRE number**, **Retirement income &
  pension pot**, **Savings rate**) now sit at the top of the Planning tab
  instead of the sidebar. The sidebar keeps display + benchmark + data controls.
- Their input values are read in the early sections from `session_state` (with
  widget-matching defaults), so the goal/FIRE progress and weeks-to-FI in the
  Progress tab keep working regardless of tab render order. The widgets own the
  keys; the early sections only read them — no Session-State write warning.

### Fixed
- The **savings-rate calculator now actually computes.** In the sidebar it read
  `latest_nw`, which is always `None` at sidebar render time, so it permanently
  showed "add your net worth data". In the Planning tab (where `latest_nw` is
  set) it works as intended. 297 tests, green.

---

## [2.13] — June 2026 (Session 9, part 6)

Liabilities everywhere: share URL + a debt-paydown line on the gains chart.

### Added
- **Liabilities round-trip through the share URL.** `encode_personal_data`
  includes the optional liabilities column when it carries non-zero data (kept
  out otherwise so the common case stays compact); `decode_personal_data` is
  backward-compatible with older tokens that have no liabilities key.
- **Debt-paydown line on the annual-gains chart.** When liabilities data is
  present, `build_gains_chart` overlays a dotted line of the year-on-year
  reduction in liabilities (debt paid down) alongside the net-worth-change bars.

### Fixed
- `build_gains_chart` now coerces its `showlegend` flag to a Python `bool`
  (plotly rejects numpy bools) — would otherwise have raised once the manual /
  demo flow began attaching an all-zero liabilities column. Caught by the
  AppTest render suite before it could ship.

### Tests
- +3 data-loader URL round-trip tests (liabilities round-trips, all-zero
  omitted, old-token backward compat) and +2 gains-chart tests (debt line
  present / absent). 297 tests, green.

---

## [2.12] — June 2026 (Session 9, part 5)

Interactive wealth-mix editor — play with your composition in real time.

### Changed
- **Auto-balancing composition sliders.** The sidebar "Your wealth composition"
  is now four sliders (Property / Pension / Financial / Physical) that always
  total 100% — move one and the other three rebalance proportionally (integer
  rounding drift handed to the largest fractional parts, via an `on_change`
  callback). Replaces the four number-inputs and their "must total 100%"
  warning. `personal_asset_split` is therefore always set, so the
  investable-wealth SWR figure and the asset-class overlay always populate.

### Added
- **Live £-makeup panel** under the main chart: a horizontal stacked bar plus
  per-component £ metrics splitting your latest net worth, then your
  **drawable / investable** subtotal (financial + physical + accessible
  pension; home equity excluded) and what it funds at 4%. Updates in real time
  as you drag the sliders.

292 tests green (the auto-balance callback is exercised by the AppTest render suite).

---

## [2.11] — June 2026 (Session 9, part 4)

Liquid-vs-total spending realism, plain-language explainers, and an optional
liabilities column.

### Fixed
- **The 4% / 25× FIRE figures no longer silently assume all net worth is
  drawable.** The "Implied sustainable spending" and FI-progress metrics still
  show the total-NW figure, but now carry a caveat and — when a wealth-
  composition split has been entered — an **investable-wealth** figure that
  excludes home equity (not income-producing) and pre-57 pension (locked). This
  stops the tool overstating FIRE readiness for property-heavy households (the
  audit flagged a 2–3× overstatement).

### Added
- **Plain-language explainers**: the headline banner now says "roughly N in 100
  people your age have less wealth than you", and the investable-wealth note
  spells out "at 4% this sustainably funds ~£X/yr".
- **Optional `liabilities` column** in the personal CSV / manual entry. When
  present, the app shows a `gross assets − liabilities = net worth` breakdown
  under the headline metrics, and the column round-trips through CSV
  upload/download. Net worth remains the only benchmark input. CSV template
  (bundled + in-app) and the manual-entry editor updated.
  - Not yet encoded in the share URL, and the time-series debt-paydown line in
    the gains chart is a deliberate follow-up.

### Tests
- 4 round-trip tests in `test_data_loader` (liabilities parsed, optional,
  currency-stripped, coerced to a non-negative magnitude). 292 tests, green.

---

## [2.10] — June 2026 (Session 9, part 3)

Information architecture: the main content is reorganised into tabs with the
benchmark chart shown first.

### Changed
- **Chart-first.** The benchmark + personal-overlay chart now renders directly
  under the headline metrics, instead of below ~1,000 lines of calculators (it
  previously sat in the middle of the page at ~line 1880).
- **Tabbed main content.** The analysis sections are grouped into five
  `st.tabs`: *Where you stand* (heatmap, decile table, distribution curve,
  asset-class breakdown), *Your progress* (summary stats, percentile trajectory,
  annual gains, weeks-to-FI, goal/FIRE), *Planning & projections* (retirement
  income, ISA bridge, drawdown, what-if, Monte Carlo), *Tax & estate* (wrapper
  utilisation, IHT) and *Share & export*. Tabs lazy-render, cutting initial
  load. Methodology stays as a full-width reference panel below the tabs.
- **Headline metric grid fixed**: the "Gap to median / P75" metric now has its
  own column (`st.columns(5)`) instead of stacking under the relative-wealth
  index and breaking the 4-up alignment.

### Added
- Single-data-point hint under the chart: a one-row user is told that a second
  year unlocks growth, trajectory, gains, milestones and Monte Carlo.

### Notes
- Sidebar calculators (goal/FIRE, retirement pot, savings rate) were
  deliberately left in the sidebar — they define variables consumed by the
  metric row *above* the tabs, so moving them risks variable-ordering bugs;
  deferred to a focused follow-up.
- Restructure performed via a one-shot transform with boundary assertions and
  validated by the full suite (288 tests, incl. the AppTest render /
  duplicate-key integration checks). Execution order preserved; the only
  multi-line markdown block (methodology) was never re-indented.

---

## [2.9] — June 2026 (Session 9, part 2)

Retirement income realism — the audit's #1-ranked feature. Turns the
"pre-tax indicative" retirement figures into net spendable income.

### Added
- **Income tax on retirement income.** New `income_tax_2025_26()` in
  `utils/uk_tax.py` (rUK 2025/26: £12,570 personal allowance with the
  £1-per-£2 taper above £100k — the 60% trap — and the 20/40/45% bands).
  The Retirement income forecast now shows a **Net annual income** metric
  after income tax on the taxable part (annuity + state pension); the 4% ISA
  draw is treated as tax-free. The target comparison uses the net figure, so
  it no longer overstates success.
- **25% tax-free pension lump sum (PCLS).** New `tax_free_lump_sum()` (25% of
  the pot, capped at the £268,275 Lump Sum Allowance). The forecast annuitises
  only the remaining 75% and shows the tax-free lump sum as its own one-off
  line — previously it annuitised 100% of the pot, overstating annuity income.
- **Second bridge leg** (pension-access age → state-pension age) inside the ISA
  bridge expander, reusing the 4% PV-of-annuity factor and showing both legs
  combined. Replaces the old "you may still need a second bridge" caveat.
- **Drawdown tax caveat**: the state-pension £-for-£ offset note now flags that
  it assumes the state pension sits within the Personal Allowance, and that
  drawdown figures are pre-tax (wrapper-dependent).
- PDF report Page 9 (retirement income) mirrors all of the above: tax-free
  lump sum line, income-tax row, net-income row, net-vs-target verdict.

### Tests
- 10 new tests in `test_uk_tax.py` for the income-tax bands, the 60%
  personal-allowance trap, monotonicity, and the PCLS cap. 288 tests, green.

---

## [2.8] — June 2026 (Session 9)

Data-accuracy, correctness and honesty pass — every quoted figure re-grounded
against current published sources. No new feature surface. Driven by a verified
multi-dimension audit (51 findings, 25 quantitative claims web/code-checked).

### Fixed — data currency
- **CPI table rebuilt from real ONS annual averages** (series D7BT, 2015=100).
  The previous table spliced a different pre-2015 base onto the 2015=100 series
  (a fake ~7% deflation step at 2014→2015) and stalled 2020 at the 2019 value
  (implied 0% inflation in 2020). Both corrected: 2000–2025 now match published
  annual averages, 2026 is a documented estimate. Affects every real-terms figure.
- **State pension 2026/27 → £12,548** (£241.30/wk, +4.8% triple lock; was a
  £12,400 estimate). Sidebar default + help updated.
- **IHT nil-rate-band freeze → April 2031** (extended at Autumn Budget 2025;
  was April 2030).

### Fixed — correctness
- The goal/FIRE ETA and savings-rate calculators now route their CAGR through
  the shared `safe_cagr` guard, so a tiny starting balance (e.g. £2k) no longer
  produces a fantasy triple-digit CAGR and a too-good ETA — they fall back to the
  average-gain estimate. (The ISA-bridge ETA already did this; the codebase was
  inconsistent about applying its own rule.)
- Regional methodology table corrected: it previously claimed London was the
  wealthiest region (+30–40%). Per ONS WAS Wave 8 the **South East** is highest
  (£489,800) and **London's median sits below the GB median** (£293,700) — high
  prices ≠ high median wealth where over half of households rent. Speculative
  per-region premiums replaced with ONS-confirmed anchors only; no precise
  (high-uncertainty) London figure quoted.

### Added — honesty / forward-looking flags
- Headline percentile now carries its ±~5–10 point uncertainty in the metric
  help and the summary banner (was buried in Methodology only).
- Nominal/real reconciliation note on the retirement-income, ISA-bridge and
  drawdown panels when the *Real terms* toggle is off.
- Cash-ISA £12,000 under-65 limit from 6 April 2027 flagged in the tax-wrapper
  panel; unused pensions entering the IHT estate from 6 April 2027 flagged in the
  IHT panel (and dropped from the "outside estate" mitigation list).
- WAS accreditation/data-quality caveat added to Methodology limitations.

### Tooling
- `scripts/bump_version.py` now also syncs the module docstring version (it had
  drifted to v2.6 while `APP_VERSION` was v2.7). New `test_bump_version` guard
  asserts docstring == `APP_VERSION`.
- New `test_inference` guard asserts `UK_CPI` is a clean, non-decreasing 2015=100
  series (locks the stalled-2020 and base-splice fixes).

---

## [2.7] — May 2026 (Session 8)

Post-deploy-fix continuation of Session 7. ~60 commits of bug fixes,
defensive additions, and real UX wins. Notable items:

### Bug fixes
- `run_monte_carlo`: depleted paths now clamp at zero (was compounding into
  the negative — broke decumulation analysis)
- `build_summary_stats`: pandas FutureWarning + pending crash on single-row
  input (idxmin on all-NaN diff)
- CSV parser: helpful errors for empty file and headers-only file
- Manual entry: drop NaN rows before downstream processing
- `data_quality` recency bands now relative to today (was hardcoded 2024)
- Manual entry default year now `date.today().year`, not 2024

### New features
- **PDF Monte Carlo page** — band chart, outcome stats, probability of target
- **Monte Carlo 'Reroll' button** — step through alternative random draws
- **Shareable URL includes partner data** under `?p=`
- **IHT combined household estate toggle** when married threshold + partner
- **LISA 40-50 gap modelled** with `has_existing_lisa` flag + UI checkbox
- **Text report enriched** with partner snapshot, goals, data quality

### Refactor / polish
- Style constants centralised in `charts/_helpers.py`; all 9 chart files migrated
- `STATE_PENSION_AGE`, `LIFE_EXPECTANCY_AT_AGE` extracted to `utils/uk_tax.py`
- `compute_data_quality` → `utils/data_quality.py` + 9 tests
- `build_summary_stats` → `utils/summary.py` + 9 tests
- `apply_component_filter` validates input with clear `ValueError`
- Manual entry partner age defaults to user's age when known
- `data/__init__.py` re-exports `DEMO_HISTORY`
- conftest gains `partner_history` fixture, 3 inline copies removed

### Tooling
- `scripts/compile_check.py` + tests; CI calls it
- `scripts/bump_version.py` + 5 tests; `make version` / `make pre-release` targets
- `tests/test_app_imports.py` — 6 tests verifying every imported name resolves
- `tests/test_requirements.py` — 4 tests pinning third-party deps to requirements.txt
- `tests/test_data_files.py` — 11 tests on bundled CSV integrity
- `.gitattributes` LF policy, `pyproject.toml` pytest config

Total: 0 → 238 tests, ~7s runtime, all green.

---

## [2.6] — May 2026 (Session 7)

Quality + UK-specific planning depth + safety nets.

### Added — data & analytics
- **Real ONS Wave 8 (April 2020–March 2022) data** in `data/was_data.csv` —
  actual published medians by age band; P25/P75 derived using preserved IQR
  ratios. Reproducible via `scripts/update_was_data.py`.
- **Asset class shares rescaled** to match ONS Wave 8 published aggregates
  (property 40%, pension 35%, financial 14%, physical 10%). Age-band shape
  preserved.
- **Monte Carlo projection** with stochastic returns: fixed `N(μ, σ)` or
  equity/bond glide path. 1,000 simulations per run, seeded for reproducible
  UX. Outputs P10/P50/P90 + probability of reaching target.
- **Stochastic drawdown / pot survival** — sequence-of-returns risk
  modelling inside the retirement drawdown expander.
- **UK tax wrapper tracker** — ISA (£20k), LISA (£4k, age-aware), Pension AA
  (£60k) with 3-year carryforward and high-earner taper (£260k+ adjusted
  income reduces AA by £1 per £2, floored at £10k).
- **IHT calculator** with four scenario thresholds up to £1m (married with
  RNRB); reduced 36% rate for charitable estates.
- **ISA / accessible-wealth bridge** calculator for early-retirement planners.
- **'Try with demo data'** button on the empty-state banner — one-click
  load of an 11-year sample history.
- **CSV export** for personal + partner data (round-trips with upload).

### Changed — architecture
- All 8 chart builders extracted from `app.py` into a `charts/` package
  (`_helpers.py`, `main_figure.py`, `asset_class.py`, `heatmap.py`,
  `distribution.py`, `gains.py`, `percentile_trajectory.py`, `whatif.py`,
  `monte_carlo.py`). Each builder takes dependencies as explicit kwargs.
- UK tax rules consolidated in `utils/uk_tax.py` (constants + helpers,
  37 dedicated tests).
- Demo data extracted to `data/demo_data.py` as single source of truth.
- `app.py`: 3,105 → ~2,750 lines (-12%).

### Added — quality + safety nets
- pytest suite from 0 → **218 tests** across 13 files (~7s runtime).
- GitHub Actions CI on every push (Python 3.11 + 3.12).
- `tests/test_app_imports.py` — parses `app.py` with `ast` and verifies
  every imported name resolves. Catches the deploy incident class of bug.
- `tests/test_requirements.py` — verifies every third-party import has a
  corresponding entry in `requirements.txt`. Uses `sys.stdlib_module_names`
  so the stdlib allowlist auto-tracks Python version differences.
- `tests/test_compile_check.py` — meta-tests the CI compile gate itself.
- `tests/test_data_files.py` — bundled CSVs exist, schemas intact, IQR
  ordering preserved (P25 < P50 < P75 per band), component shares sum to 100.
- `tests/test_data_quality.py` — 9 tests on the data quality scorer.
- `tests/test_summary.py` — 9 tests on the summary stats table builder.
- `scripts/compile_check.py` — single source of truth for whole-tree
  syntax checking; called by both CI and `make compile`.
- `Makefile` with `install`, `test`, `compile`, `run`, `check`, `data`,
  `data-only`, `clean` targets.
- `pyproject.toml` with pytest configuration.
- `.gitattributes` enforcing LF line endings in the repo.
- `tests/conftest.py` with session-scoped shared fixtures (test runtime
  reduced from 5.5s to 4.7s on the same suite).

### Fixed
- CSV parser tolerates whitespace in column headers and ISO date formats
  without warnings; ignores extra columns gracefully.
- `lisa_remaining` is now age-aware (returns 0 for users over 50).
- Real-terms mode warns when personal data years fall outside the CPI table
  (was silently passing through uncorrected).
- IHT caption updated from "Rules as of 2024/25" to "2025/26 (frozen until
  April 2030)".
- Percentile metric shows "99th+" / "<1st" for the clamped ends of the
  log-normal model range, not a misleading exact number.
- Footer disclaimer added: "Indicative figures only — not financial advice".

### Infrastructure
- Live URL now flows from a single `PUBLIC_APP_URL` constant.
- `APP_VERSION` and `PUBLIC_APP_URL` co-located near the top of `app.py`
  for one-block release bumps.
- README has a CI status badge and a Tests section.

---

## [2.5] — May 2026 (Session 6)

Retirement income forecast + drawdown / pot longevity simulator.
See `REVIEW_LOG.md` for the full Session 6 audit and implementation notes.

## [2.4] — May 2026 (Session 5)

Audit + polish: fixed 3 crashes, suppressed nonsense outputs, refreshed README.

## [2.3] — May 2026 (Session 4)

PDF report complete overhaul: cover page, page numbers, chart pages with
descriptions, goals page with visual progress bars.

## [2.2 and earlier]

Initial build, real-time benchmark visualisation, percentile trajectory,
what-if projection, IHT calculator, gender adjustment, colourblind palette.
See `NEXT_STEPS.md` archive section for the full feature timeline.
