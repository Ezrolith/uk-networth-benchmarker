# Changelog

All notable changes to UK Net Worth Benchmarker.
Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
see `REVIEW_LOG.md` for session-by-session audit notes and rationale.

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
- pytest suite from 0 → **185 tests** (~6s runtime).
- GitHub Actions CI on every push (Python 3.11 + 3.12).
- `tests/test_app_imports.py` — parses `app.py` with `ast` and verifies
  every imported name resolves. Catches the deploy incident class of bug.
- `tests/test_requirements.py` — verifies every third-party import has a
  corresponding entry in `requirements.txt`. Uses `sys.stdlib_module_names`
  so the stdlib allowlist auto-tracks Python version differences.
- `tests/test_compile_check.py` — meta-tests the CI compile gate itself.
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
