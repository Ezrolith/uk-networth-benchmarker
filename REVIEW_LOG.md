# Audit & Improvement Log — Session 6

**Goal:** Identify improvements to move the app toward "leading UK financial
planning tool for net worth and retirement". Preserve all current content;
tidy is fine.

**Started from:** v2.4 (post Session 5 audit).

---

## Methodology

1. Walk through the live app journey from a real user's perspective (cold start, no data).
2. Generate fresh PDFs for representative personas and inspect visually.
3. Compare the feature set against what a "leading" planning tool offers
   (drawdown modelling, tax wrappers, state pension forecast, sequence-of-returns
   risk, etc.).
4. Categorise findings by impact × effort; ship the highest-value items.

---

## Findings

### A. User journey gaps (cold start — no personal data yet)

- **A1.** No clear call-to-action — landing shows the benchmark chart but the
  big "what to do next" is buried in the sidebar. A new visitor has to scroll
  the long sidebar to find the upload widget.
- **A2.** Sample / demo data not offered. Could populate a fake persona to let
  users explore before entering their own figures.

### B. Sidebar information architecture

- **B1.** Sidebar is long: 10+ display toggles, two personal data sections,
  wealth composition expander, goal calculator (with 4 sub-tools nested),
  benchmark download. Mixing display options with personal data and
  calculators.
- **B2.** Display toggles (log scale, P10/P90, milestones, smooth, asset class,
  annotations, colourblind) could be folded into a single "Display options"
  expander to declutter.
- **B3.** Goal calculator combines four distinct things (target NW, FIRE, pension
  pot, savings rate) into one expander — confusing because the dependencies
  between them aren't visible.

### C. Retirement planning — the biggest gap vs a "leading" tool

- **C1.** **No drawdown / decumulation modelling.** Currently only FIRE = 25×
  (which is the 4% rule) but no actual simulation of "if I retire at 60 with
  £X and withdraw £Y/yr, when does my pot run out?". This is the central
  question a retirement planning tool answers.
- **C2.** **No retirement income view.** A user can input state pension and
  target pension income, but the app never shows "your projected total annual
  income at retirement = state pension £X + DB pension £Y + drawdown £Z".
- **C3.** **No sequence-of-returns illustration.** Order of returns matters
  during decumulation — a stochastic or "bad early years" scenario would be
  genuinely useful.
- **C4.** **Inflation assumption is implicit.** "Real terms 2026 £" is a
  toggle but during what-if projection it's not clear whether the projected
  values are real or nominal. Same for FIRE.
- **C5.** **No tax wrapper guidance.** UK has ISA (£20k/yr), Pension AA
  (£60k/yr), LISA (£4k/yr), and various tapers. Tracking utilisation is a
  core planning function.

### D. Calculation quality

- **D1.** Pension pot estimator uses annuity rate `0.05 + (age-65) × 0.002` —
  conservative. Recent UK gilt-linked annuity rates at 65 have been closer to
  6.5–7% in 2024/25.
- **D2.** State pension default is £11,500/yr (2024/25). 2025/26 was £11,973;
  2026/27 will be ~£12.4k. Should update default to current.
- **D3.** Sustainable spending shown as `nw / 25 / 52` weekly — implies 4% SWR
  but doesn't account for tax. Real after-tax sustainable spend is lower
  for amounts above the Personal Allowance.

### E. Polish / consistency

- **E1.** Methodology mentions "Region filter is planned for v2" — stale, we're
  on v2.4.
- **E2.** Caption "Indicative only" repeated many times — slight variation
  would feel more thoughtful.
- **E3.** Some expander captions use bold markdown, others don't — could be consistent.
- **E4.** No "last updated" or "version" visible to a casual viewer except the
  small footer.

### F. PDF report

- **F1.** Already strong post-Session 5. One small thing: the "Goals" page
  doesn't show the retirement income summary that would tie it together.
- **F2.** PDF doesn't include a drawdown chart (if we add C1).

### G. Already strong areas (preserve)

- Benchmark visualisation
- PCHIP interpolation
- Multi-page PDF report
- IHT calculator
- Asset class breakdown
- Percentile trajectory
- Year-on-year gains chart
- Share-link encoding
- Data quality score
- Methodology transparency

---

## Implementation plan (this session)

Ordered by impact × effort.

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | Drawdown / decumulation simulator | Medium | **High** — closes biggest gap |
| 2 | Retirement income summary (state + private + draw) | Low | **High** — answers the "what will I live on?" question |
| 3 | Update state pension default + annuity rate | Trivial | Med |
| 4 | Sidebar reorganisation (Display options expander) | Low | Med |
| 5 | Empty-state landing tips | Low | Med |
| 6 | Inflation note clearer on what-if and FIRE | Trivial | Med |
| 7 | Update methodology stale notes | Trivial | Low |
| 8 | Add drawdown chart + summary to PDF | Low (after #1) | Med |

---

## Implemented this session (v2.5)

### New: Retirement income forecast (in-app + PDF)
- New expander in the main flow that brings together the user's projected NW
  at retirement age, their pension share, state pension, and the assumed real
  return, then shows estimated annual income from three sources side-by-side:
  - Pension annuity (using gilt-linked rate ~6.5% at 65)
  - 4% safe-withdrawal drawdown from non-pension wealth
  - State pension (from age 67+)
- Compares the total against the user's target pension income with success /
  warning banner.
- New page in the PDF report with a full income breakdown table.

### New: Retirement drawdown — pot longevity simulator
- New expander that simulates spending down a retirement pot year-by-year.
- Headline metrics: years covered, depletion age, life-expectancy comparison,
  implied withdrawal rate.
- Pot-balance chart with life-expectancy and depletion markers.
- Sensitivity table showing depletion age at real returns from 1% to 6%.
- Optional state pension overlay (reduces drawdown need from age 67).
- Verdict banner colour-coded by whether the pot covers life expectancy.
- Documents sequence-of-returns risk and how to stress-test.

### Polish & quick wins
- **State pension default** updated: £11,500 (2024/25) → £12,400 (2026/27 estimate).
- **Annuity rate assumption** updated from 5% to 6.5% at age 65 to reflect 2024/25
  UK gilt-linked annuity rates. Affects pension pot estimator and retirement income.
- **Sidebar tidy**: log scale, P10/P90, milestones, smooth trajectory, asset class,
  annotations, colourblind palette toggles all moved into a "Display options"
  expander. The age range slider stays prominent.
- **Empty-state guidance**: friendly "Add your net worth history to get started"
  banner shown on cold start, pointing the user at the sidebar.
- **Methodology**: added sections describing the retirement income forecast and
  drawdown simulator. Removed stale "Region filter is planned for v2" line.
- **Version**: bumped APP_VERSION to v2.5.

---

## Not done this session (queued for the backlog)

- **Tax wrapper tracking** (ISA / Pension AA / LISA utilisation) — meaningful
  feature for UK planning but needs UI design.
- **Side-by-side scenario compare** — "Plan A vs Plan B" view of two
  retirement configurations.
- **Mobile layout** — sidebar still feels heavy on mobile despite the tidy.
- **Region filter** — needs expanded regional WAS data.
- **Wave 7 historical comparison toggle** — current `was_data.csv` is Wave 8
  only; adding Wave 7 with a selector would show COVID-era distribution shift.

---

# Session 7 (May 2026, v2.6) — quality foundations + Monte Carlo

**Started from:** v2.5 (post Session 6 retirement push).

## Methodology

1. Recognised the highest credibility risk: every quoted figure came from an
   *approximate* dataset. Fixed by fetching real ONS Wave 8 data.
2. Added a test suite + CI so future sessions can refactor safely.
3. Closed the largest analytical gap from Session 6's backlog: Monte Carlo
   / sequence-of-returns risk.
4. Refactored `app.py` (3,105 lines, 23 functions, all UI + maths mixed) into a
   `charts/` package so future sessions can move faster.

## Implemented

### Quality foundations (no user-visible change, but enabling)
- **85 → 121 tests** across 5 test files: `test_inference.py` (PCHIP, log-normal
  fit, CPI, individual+gender conversion, decile table, component filter),
  `test_data_loader.py` (CSV parsing, Excel-date year extraction, URL encode/
  decode, validation warnings), `test_charts_helpers.py` (fmt edge cases incl.
  negatives, safe_cagr filters, best_gain sorting), `test_chart_builders.py`
  (43 smoke tests on every chart builder), `test_monte_carlo.py` (24 tests
  on simulation + glide path + chart).
- **GitHub Actions CI** — py_compile + pytest on every push/PR, matrix Py
  3.11 + 3.12. No more silent deploys of broken code.

### Real data
- **Replaced approximate WAS figures with ONS Wave 8 medians** — downloaded
  Figure 2 CSV directly from ons.gov.uk via WebFetch (April 2020 to March
  2022). P25/P75 derived from the median using preserved IQR ratios.
  `scripts/update_was_data.py` is reproducible.
- **Refreshed asset class shares to Wave 8 aggregates** — was off by ~7pp on
  financial wealth. Now matches the published aggregate (property 40%,
  pension 35%, financial 14%, physical 10%) while preserving age-band shape.
- DATA_YEAR 2019 → 2021 (Wave 8 midpoint). All labels updated.

### Code organisation
- Extracted all 8 chart builders from app.py into `charts/`:
  `_helpers.py`, `main_figure.py`, `asset_class.py`, `heatmap.py`,
  `distribution.py`, `gains.py`, `percentile_trajectory.py`, `whatif.py`,
  `monte_carlo.py`. Each builder takes its dependencies (colours, data,
  labels) as explicit keyword args.
- Split the bundled Goal Calculator into three focused expanders.
- app.py: 3,105 → 2,562 lines (-17%).

### New feature: Monte Carlo
- `utils/monte_carlo.py` — `run_monte_carlo()` with normal-distribution
  annual returns, `percentile_envelope()`, `probability_of_reaching()`,
  `probability_of_ruin()`. Seeded for reproducible UX.
- **Equity/bond glide path option**: linear glide between two equity weights,
  with portfolio variance correctly including the equity-bond covariance.
  Models the real-world de-risking pattern of long-horizon investors.
- **Stochastic drawdown** added to the existing Retirement drawdown expander:
  1,000 simulations with random returns to compute the probability the pot
  survives to each age. Colour-coded verdict at ≥85% / ≥60% / <60% survival.

### New feature: UK tax wrapper tracker
- `utils/uk_tax.py` — tested module with `tapered_pension_allowance`,
  `effective_pension_allowance`, `isa_remaining`, `lisa_remaining`,
  `pension_relief_estimate`, `lisa_bonus`. All 2025/26 UK constants
  exported.
- In-app expander showing ISA/LISA/Pension AA utilisation with progress
  bars + headroom. Smart-suggestion banner identifies where headroom ×
  marginal tax relief is material. Reference table at the bottom shows
  current limits with the user's tapered AA reflected.
- **Pension AA taper for high earners** (£260k+ adjusted income): £1
  reduction per £2 over threshold, floored at £10k from £360k onward.

### New feature: ISA / accessible-wealth bridge
- Sizes the bridge fund needed by early retirees to cover spending from
  FIRE age until pension access age (currently 57, rising to 58 in 2028,
  then 10-yr gap to state pension age).
- Two pot sizings: conservative no-growth and 4% real return PV-of-annuity.
- ETA projection: at current CAGR, when would the user reach the target?
  Green if buffer before FIRE age, amber if shortfall.

### Polish
- **'Try with demo data' button** on the empty-state banner — one click
  loads an 11-year sample history (2016-2026, ages 25-35) including note
  annotations so first-time users can explore every feature.
- **CSV download for personal + partner data** — round-trips with the
  upload schema (year, age, net_worth, note); "Share your chart" expander
  is now "Share / export your data" with both URL + CSV columns.
- Methodology panel rewritten: documents the ONS Wave 8 source, distinguishes
  published medians from derived quartiles, adds sections on Monte Carlo
  (both modes), UK tax wrappers, ISA bridge, and stochastic drawdown.
- `tests/conftest.py` extracted with session-scoped fixtures — test runtime
  dropped from 5.5s to 4.2s.

## Outcome

- **150 tests passing** (~4s runtime).
- **32 commits**, all pushed.
- App version: v2.5 → v2.6.
- Real WAS data now powers every quoted figure.
- All chart builders are isolated and unit-tested.
- Monte Carlo closes the sequence-of-returns risk gap that was the largest
  remaining analytical limitation.
- Tax wrapper tracker + taper + ISA bridge fill out the UK-specific
  planning surface.
- CSV export closes the data round-trip (upload + edit + export).
