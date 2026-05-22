# UK Net Worth Benchmarker

An interactive web app showing UK net worth distributions (P25 / median / P75) by age,
with personal overlay and a transparent inference layer.

## Quick start

```bash
# Install dependencies (Python 3.11+ recommended)
pip install -r requirements.txt

# Run locally
streamlit run app.py
```

Open http://localhost:8501 in your browser.

## Features (v1)

- **Age axis 16–85**, interactive zoom
- **P25 / median / P75** lines with shaded interquartile band
- **Household vs individual** toggle (individual is derived — see methodology panel)
- **Nominal vs real (2024 £)** toggle using ONS CPI
- **With/without pension wealth** toggle
- **Personal net worth overlay** — CSV upload or manual entry table
- **Percentile callout** — see which band your latest net worth sits in
- **Methodology panel** — all inferences documented, nothing hidden
- **Published data markers** — solid circles distinguish WAS observations from interpolated values

## Personal data CSV format

```csv
year,age,net_worth
2020,28,12000
2021,29,18500
2024,32,52000
```

Download the template from the sidebar.

## Data source

ONS Wealth and Assets Survey Wave 7 (2018–2020), Great Britain.
The figures in `data/was_data.csv` are approximations of published WAS percentile tables.
For research use, replace with primary ONS data tables.

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub
2. Go to share.streamlit.io → New app
3. Select repo + `app.py` as the entry point
4. Deploy — no secrets or environment variables needed

## Project plan

See the project plan document for the full v1–v3 roadmap, methodology decisions, and
data-source gap analysis.

## File structure

```
├── app.py                  Main Streamlit application
├── requirements.txt
├── data/
│   ├── was_data.csv        WAS Wave 7 benchmark data (tidy format)
│   └── personal_template.csv
├── utils/
│   ├── inference.py        Interpolation, individual conversion, CPI adjustment
│   └── data_loader.py      CSV loading helpers
└── .streamlit/
    └── config.toml         Theme
```
