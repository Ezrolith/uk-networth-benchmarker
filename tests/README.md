# Test suite

223 tests across 14 files, ~7s runtime. Run with `make test` or `pytest -v`.

## What each file covers

### Business logic (the maths the app trusts)

| File | What it covers |
|---|---|
| `test_inference.py` (18) | PCHIP interpolation, log-normal percentile fit, CPI math, individual + gender conversion, tail derivation, decile table, component filter |
| `test_data_loader.py` (17) | CSV parsing tolerance (whitespace, ISO dates, extra columns, Excel date artefacts), URL encode/decode round-trip, validation warnings |
| `test_monte_carlo.py` (24) | Simulation determinism with seeds, mean ≈ FV at low vol, zero-vol determinism, contributions grow faster, glide-path endpoints + monotone, portfolio_moments equity/bond mix, probability functions |
| `test_uk_tax.py` (43) | Pension AA + taper + carryforward, ISA/LISA (age-aware), pension relief at multiple rates, LISA bonus cap, IHT with 4 scenarios, state pension constants, life expectancy lookup |
| `test_data_quality.py` (9) | Data quality scoring: perfect/minimum/empty cases, recency/density/span criteria, score cap at 100, indicator emoji on every note |
| `test_summary.py` (9) | Summary stats table: empty input, three core rows always present, label prefix, CAGR included/omitted, best/worst single change, latest percentile, exact column shape |
| `test_charts_helpers.py` (24) | fmt edge cases incl. negatives, fmt_delta, clean_note (NaN handling), safe_cagr filters, best_gain on unsorted input |

### Chart builders (smoke + behaviour)

| File | What it covers |
|---|---|
| `test_chart_builders.py` (43) | Every chart builder in `charts/` — verifies it builds without error, has the expected traces, respects price_label / colour kwargs, handles partner overlays, log-scale yaxis switch |

### Demo data + integration

| File | What it covers |
|---|---|
| `test_demo_data.py` (8) | The 'Try with demo data' baked-in 11-year history — shape, ages consistent, monotone growth, CPI round-trip, percentile trajectory upward |

### Deploy safety net (incident-driven)

| File | What it covers |
|---|---|
| `test_app_imports.py` (6) | Parses `app.py` with `ast` and verifies every imported name resolves on its target module. Catches the "app.py references X but utils/uk_tax.py is stale" class of bug that hit on 2026-05-25 |
| `test_requirements.py` (4) | Verifies every third-party import has a `requirements.txt` entry; uses `sys.stdlib_module_names` so the stdlib allowlist auto-tracks Python version |
| `test_compile_check.py` (3) | Meta-test the `scripts/compile_check.py` gate itself — confirms it detects a deliberately-broken file and skips cache directories |
| `test_bump_version.py` (5) | Meta-test the `scripts/bump_version.py` release tooling — no-args mode, --dry doesn't modify files, invalid formats rejected, same-version is a no-op, three-part semver accepted |
| `test_data_files.py` (11) | Bundled CSVs exist, have the expected schemas, IQR ordering (P25 < P50 < P75) is intact, asset class shares sum to 100 |

## Shared infrastructure

- **`conftest.py`** — session-scoped fixtures (`benchmark`, `raw_was`, `asset_series`, `personal_history`). Building the benchmark once per session brought runtime from ~5.5s down to ~4–5s.

## Running specific subsets

```bash
# Just the business logic (fastest, no chart rendering)
pytest tests/test_inference.py tests/test_uk_tax.py tests/test_monte_carlo.py -v

# Just the deploy safety net
pytest tests/test_app_imports.py tests/test_requirements.py tests/test_compile_check.py tests/test_data_files.py -v

# Everything that touches Plotly chart building
pytest tests/test_chart_builders.py -v
```

## When adding a new test file

- Name it `test_<area>.py` so pytest auto-discovers it
- Put shared fixtures in `conftest.py`, not the test file
- Smoke tests for new charts go in `test_chart_builders.py` (keep the
  builder-test surface in one place)
- Business-logic helpers (anything new in `utils/`) should ship with their
  own test file mirroring the source module name
