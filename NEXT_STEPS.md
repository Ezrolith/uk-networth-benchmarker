# Next Steps — UK Net Worth Benchmarker

Ranked by value vs effort. Completed items archived at the bottom.

---

## Highest priority remaining

### Data accuracy (biggest single improvement available)
- [ ] **Replace approximate WAS figures with actual ONS data tables** — download WAS Wave 7 Bulletin Table 3.2 (Total Wealth by age and percentile) and transcribe exact numbers into `data/was_data.csv`. Current figures are close but not identical. This is the single change that most improves credibility.
- [ ] **Add WAS Wave 8 (2020–2022) data** — when published, update `was_data.csv`, add new rows with `data_year=2021`, and add a wave selector toggle so users can compare waves.

### Chart / UX polish
- [ ] **Mobile layout** — sidebar collapses awkwardly on small screens; consider an `st.tabs` or top-of-page expander pattern for mobile.
- [x] **Smarter milestone ETA** for negative/zero starting net worth — falls back to average annual gain when CAGR is undefined; fixes Goal/FIRE ETA and milestone tracker.

### Personal data
- [x] **Note annotations on data points** — optional `note` column in CSV and manual entry editor; notes appear in hover tooltips on the main chart.

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
