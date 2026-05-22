# Next Steps — UK Net Worth Benchmarker

Ranked by value vs effort. Completed items archived at the bottom.

---

## v1 polish — remaining

### Data accuracy
- [ ] **Replace approximate WAS figures with the actual ONS data tables** — download WAS Wave 7 Bulletin Table 3.2 and transcribe exact numbers into `data/was_data.csv`. This is the single biggest data quality improvement available.
- [ ] **Add WAS Wave 8 (2020-2022) data** — update `was_data.csv` and version the source column when published.

### Chart UX
- [ ] **Mobile layout** — sidebar collapses awkwardly on small screens.

### Personal data
- [ ] **Currency input formatting** — sidebar manual entry shows raw integers; format as £ with thousands separators.
- [ ] **Smarter milestone ETA** — current projection is linear; a CAGR-based compound projection would be more realistic.

---

## v2 features

### Filters and breakdowns
- [ ] **Region filter** — WAS publishes regional breakdowns (London, North West, etc.). High value, requires additional data prep.
- [ ] **Asset class breakdown** — stacked area chart showing pension / property / financial / physical components by age.
- [ ] **Gender filter** — WAS includes individual-level pension data by gender; relevant for the individual basis.

### Saved snapshots
- [ ] **Dedicated PNG export button** — using `fig.to_image()` with kaleido for more control over styling than the modebar.

---

## v3 stretch

- [ ] **"What if" projection** — forward-model net worth under different contribution / return assumptions against forward-projected benchmark percentiles.
- [ ] **International comparison** — US SCF, Canada SFS — normalised to PPP.
- [ ] **Tax-adjusted view** — net worth after estimated IHT / CGT exposure.

---

## Completed

- [x] Log scale toggle
- [x] "You are here" vertical age line + horizontal net worth crosshair
- [x] Exact percentile estimate via log-normal fit
- [x] Percentile trajectory chart (secondary chart)
- [x] Trajectory smoothing (rolling average toggle)
- [x] CAGR, average annual gain, delta vs previous data point
- [x] Milestone progress bar toward median / P75
- [x] Milestone ETA projection (linear, at current annual gain)
- [x] Wealth milestone reference lines (PS100k, PS250k, PS500k, PS1m toggle)
- [x] P10/P90 toggle (log-normal derived)
- [x] Hover shows benchmark P25/P50/P75 alongside personal net worth
- [x] Zero reference line when personal data contains negatives
- [x] Shareable URL (personal data encoded into query param, no server storage)
- [x] Benchmark CSV download (sidebar, respects current settings)
- [x] Birth-year consistency validation on CSV upload
- [x] Excel date-artifact year detection (separate from birth-year check)
- [x] Legend renamed "ONS data point"
- [x] Plotly modebar + PNG export at 2x resolution
- [x] Percentile band metric display fix
- [x] CSV parser handles Excel date-formatted years and decimal ages
- [x] Deployment to Streamlit Community Cloud
