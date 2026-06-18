# Data-process-RMS

Hotel reservation analysis framework for RMS **Checked Out** and **Checked In** CSV exports.

## Features

- Merges both CSV files on **Res No** (guest names are excluded from the merged dataset)
- **Category usage** with reservation counts, room nights, usage %, and **average tariff**
- **Room type usage** broken down by category and room
- Time drill-down: **6 months**, **1 month**, and **1 week** windows (based on arrival date)

## Setup

```bash
pip install -r requirements.txt
```

Place your exports in `data/` (sample files are included):

- `data/Checked_Out.csv`
- `data/Checked_In.csv`

## CLI

```bash
# Default 6-month window
python run_analysis.py

# Specific period
python run_analysis.py --period 1_week

# All three drill-down windows
python run_analysis.py --all-periods

# Export JSON
python run_analysis.py --all-periods --output reports/summary.json
```

## Dashboard

```bash
streamlit run app.py
```

Use the sidebar to switch between **Last 6 months**, **Last 1 month**, and **Last 1 week**, and adjust the window end date.

## Data model

| Source | Join key | Contributes |
|--------|----------|-------------|
| Checked Out | `Res No` | Category, room, dates, billing, market segment |
| Checked In | `Res No` | Tariff, pax, travel agent, company, nationality |

Tariff averages are computed only where tariff data exists (from Checked In). Reservations present only in Checked Out will show blank tariff.

## Project layout

```
analysis/
  data_loader.py   # CSV load + merge on Res No
  metrics.py       # Category / room aggregations
  periods.py       # 6m / 1m / 1w windows
app.py             # Streamlit dashboard
run_analysis.py    # CLI entry point
data/              # Input CSV files
```
