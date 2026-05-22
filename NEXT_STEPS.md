# Next Steps — UK Net Worth Benchmarker

Ranked by value vs effort. Completed items archived at the bottom.

---

## v1 polish — remaining

### Data accuracy
- [ ] **Replace approximate WAS figures with the actual ONS data tables** — download WAS Wave 7 Bulletin Table 3.2 (Total Wealth by age and percentile) and transcribe exact numbers into `data/was_data.csv`. Current figures are close but not identical to the published source. This is the single biggest data quality improvement available.
- [ ] **Add WAS Wave 8 (2020–2022) data** — expected to be published; update `was_data.csv` and version the source column

### Chart UX
- [ ] **Mobile layout** — sidebar collapses awkwardly on small screens; consider moving controls to an expander above the chart on mobile
- [ ] **Annotate chart with net worth milestones** — subtle horizontal reference lines at £100k, £250k, £500k, £1m (optional toggle to avoid clutter)
- [ ] **Smooth the trajectory chart** — add a LOESS or rolling average option for users with many data points where the line is noisy

### Personal data
- [ ] **Currency input formatting** — sidebar manual entry shows raw integers; format as £ with thousands separators for readability

---

## v2 features

### Filters and breakdowns
- [ ] **Region filter** — WAS publishes regional breakdowns (London, North West, etc.); dropdown that re-scales the benchmarks. High value, but requires additional data prep
- [ ] **Asset class breakdown** — stacked area chart showing pension / property / financial / physical components by age; helps users understand *what* makes up the benchmark
- [ ] **Gender filter** — WAS includes individual-level pension data broken down by gender; relevant for the individual basis

### Saved snapshots
- [ ] **Download results as PNG/PDF** — Plotly modebar download is now active; a dedicated button using `st.download_button` wrapping `fig.to_image()` would give more control over styling
- [ ] **Shareable URL** — encode personal data in a URL hash (no server storage); users can bookmark or share their position

---

## v3 stretch

- [ ] **"What if" projection** — forward-model net worth under different contribution / investment return assumptions, overlaid against forward-projected benchmark percentiles
- [ ] **International comparison** — US SCF, Canada Survey of Financial Security — normalised to PPP; useful context, harder to keep current
- [ ] **Tax-adjusted view** — net worth after estimated IHT / CGT exposure

---

## Deployment

- [ ] **Deploy to Streamlit Community Cloud** — repo is at Ezrolith/uk-networth-benchmarker (private); go to share.streamlit.io, connect repo, entry point `app.py`, no secrets needed

---

## Completed ✓

- [x] Log scale toggle
- [x] "You are here" vertical age line
- [x] Horizontal crosshair at current net worth
- [x] Exact percentile estimate via log-normal fit (replacing coarse band)
- [x] Percentile trajectory chart (secondary chart below main)
- [x] CAGR metric
- [x] Average annual gain metric
- [x] Milestone progress bar (toward median / P75)
- [x] Year-over-year delta on net worth metric
- [x] Gap-to-next-milestone metric (col 4)
- [x] P10/P90 optional toggle (derived from log-normal model)
- [x] Hover shows benchmark P25/P50/P75 alongside personal net worth
- [x] Zero reference line when personal data contains negatives
- [x] Birth-year consistency validation on CSV upload
- [x] Legend renamed "ONS data point" (was "P50 – published")
- [x] Plotly modebar + PNG export at 2× resolution
- [x] Percentile band metric display fix (was mangled by .title())
- [x] CSV parser handles Excel date-formatted years and decimal ages
