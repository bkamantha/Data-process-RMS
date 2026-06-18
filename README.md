# Data-process-RMS

Hotel reservation analysis framework for RMS **Checked Out** and **Checked In** CSV exports.

## Features

- Merges both CSV files on **Res No** (guest names are excluded from the merged dataset)
- **Category usage** with reservation counts, room nights, **nights %** (share of total nights), and **average tariff**
- **Room type usage** broken down by category and room
- **Loss USD** when actual tariff is below a per-room baseline (`(baseline − tariff) × nights`)
- Editable **room baseline tariffs** via `data/room_baselines.csv` or the dashboard
- Time drill-down: **6 months**, **1 month**, and **1 week** windows (based on arrival date)

## Setup

```bash
pip install -r requirements.txt
```

On **Windows**, if `streamlit` is not recognized, use `python -m streamlit` instead (see Dashboard below), or double-click `run_dashboard.bat`.

Place your exports in `data/` (sample files are included):

- `data/Checked_Out.csv`
- `data/Checked_In.csv`
- `data/room_baselines.csv` — per-room baseline tariff (USD/night); edit or use the dashboard **Room baselines** tab

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

**Windows shortcut:** `run_analysis.bat` or `run_analysis.bat --period 1_week`

## Dashboard

```bash
python -m streamlit run app.py
```

**Windows shortcut:** double-click `run_dashboard.bat`

Use the sidebar to switch between **Last 6 months**, **Last 1 month**, and **Last 1 week**, and adjust the window end date.

## Data model

| Source | Join key | Contributes |
|--------|----------|-------------|
| Checked Out | `Res No` | Category, room, dates, billing, market segment |
| Checked In | `Res No` | Tariff, pax, travel agent, company, nationality |

Tariff averages and loss USD are computed only where tariff data exists (from Checked In). Reservations present only in Checked Out will show blank tariff and zero loss.

### Baselines & loss

| Column | Meaning |
|--------|---------|
| `nights_pct` | Room nights as % of total nights in the period |
| `baseline_tariff` | Target rate per night for that room |
| `loss_usd` | `(baseline − tariff) × nights` when tariff &lt; baseline |

Edit `data/room_baselines.csv`:

```csv
room,baseline_tariff
T212,200.00
P212,350.00
```

## Project layout

```
analysis/
  baselines.py     # Room baseline load/save and loss USD
  data_loader.py   # CSV load + merge on Res No
  metrics.py       # Category / room aggregations
  periods.py       # 6m / 1m / 1w windows
app.py             # Streamlit dashboard
run_analysis.py    # CLI entry point
data/              # Input CSV files + room_baselines.csv
```
