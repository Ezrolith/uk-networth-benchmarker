# Next Steps — UK Net Worth Benchmarker

Ranked roughly by value vs effort. Top section = v1 polish, below = v2 features.

---

## Bugs / quick wins

- [x] ~~Percentile band metric showing mangled "Btw The 25Th Percentile And Th..."~~ Fixed

---

## v1 polish

### Chart UX
- [ ] **Log scale toggle** — wealth distributions are log-normal; a log Y axis shows the lower percentiles much more clearly without the bottom half being squashed to zero
- [ ] **"You are here" annotation** — vertical dotted line + label at the user's latest age on the chart, so the eye is drawn to the right spot instantly
- [ ] **Exact percentile estimate** — instead of a band (P25–P50), interpolate to give an approximate single-figure percentile (e.g. "~38th percentile"). Needs care with methodology labelling
- [ ] **Year-over-year delta** in the metrics row — show net worth change from the previous data point, not just the latest value
- [ ] **Legend cleanup** — "P50 – published" is technical jargon to a first-time user; rename to "ONS data point" and consolidate P25/P75 published markers into one legend entry
- [ ] **Mobile layout** — sidebar collapses awkwardly on small screens; consider moving controls to an expander above the chart on mobile

### Data accuracy
- [ ] **Replace approximate WAS figures with the actual ONS data tables** — download the WAS Wave 7 Bulletins Table 3.2 (Total Wealth by age and percentile) and transcribe the exact numbers into `data/was_data.csv`. The current figures are close but not identical to the published source
- [ ] **Add P10 and P90** as optional toggle — gives a better picture of the tails without cluttering the default view

### Personal data
- [ ] **Negative net worth support** — show a horizontal zero line clearly; users in their 20s with student loans are likely below zero
- [ ] **Validate age/year consistency** on upload — warn if `year - age` implies a different birth year across rows (likely data entry error)
- [ ] **Currency input formatting** — sidebar manual entry shows raw numbers; format as £ with thousands separators

---

## v2 features

### Filters and breakdowns
- [ ] **Region filter** — WAS publishes regional breakdowns (London, North West, etc.); add a dropdown that re-scales the benchmarks
- [ ] **Asset class breakdown** — stacked area chart showing pension / property / financial / physical components by age; helps users understand *what* makes up the benchmark, not just the total
- [ ] **Gender filter** — WAS includes individual-level pension data broken down by gender; relevant for the individual basis

### Data freshness
- [ ] **WAS Wave 8 data** — Wave 8 (2020–2022) is expected to be published; update `was_data.csv` and version the source column when it lands
- [ ] **Nowcast toggle (v2 stretch)** — roll Wave 7 forward to today using: house price index (HM Land Registry), FTSE/global equity returns, OBR wage growth. Mark heavily as modelled

### Saved snapshots
- [ ] **Download results as PNG/PDF** — "Export chart" button using Plotly's built-in download, or a custom `st.download_button` wrapping a fig export
- [ ] **Shareable anonymised link** — encode personal data in a URL hash (no server storage) so users can bookmark or share their position

---

## Deployment / portfolio

- [ ] **Deploy to Streamlit Community Cloud** — repo is already on GitHub (Ezrolith/uk-networth-benchmarker); go to share.streamlit.io, connect the repo, point at `app.py`
- [ ] **Add `og:image` / social preview** — static screenshot in `/assets/` referenced in the README, makes the GitHub card look good
- [ ] **Write up the methodology as a short blog post or Notion doc** — documents the inference decisions for Multiverse portfolio purposes
- [ ] **Add a LICENSE file** — MIT is fine for a portfolio piece

---

## v3 stretch

- [ ] **"What if" projection** — forward-model the user's net worth under different contribution / investment return assumptions, overlaid against forward-projected percentiles
- [ ] **International comparison** — US SCF, Canada Survey of Financial Security — normalised to purchasing power parity; useful context but harder to keep current
- [ ] **Tax-adjusted view** — show net worth after estimated IHT / CGT exposure (very complex, requires significant methodology work)
