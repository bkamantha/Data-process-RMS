# Data-process-RMS

Hotel reservation analysis framework for RMS **Checked Out** and **Checked In** CSV exports.

## Features

- Merges both CSV files on **Res No** (guest names excluded); **Conference Rooms** excluded
- **Room-type breakeven** rates (expenses already included) per category
- **Availability loss** = vacant nights × breakeven — measures revenue lost from empty rooms in the period
- **Pricing loss** = nights sold below breakeven rate
- **Daily pricing** view by date and room type to improve rates
- Time drill-down: **6 months**, **1 month**, **1 week**

## Setup

```bash
pip install -r requirements.txt
```

On **Windows**, use `python -m streamlit run app.py` or double-click `run_dashboard.bat`.

Place your exports in `data/`:

- `data/Checked_Out.csv`
- `data/Checked_In.csv`
- `data/room_type_breakeven.csv` — breakeven USD/night per room type

## CLI

```bash
python run_analysis.py --period 1_week
python run_analysis.py --all-periods
python run_analysis.py --period 1_month --output reports/summary.json
```

**Windows:** `run_analysis.bat --period 1_week`

## Dashboard

```bash
python -m streamlit run app.py
```

**Sidebar options:**
- **Input source:** default files, upload CSV, or enter file paths
- **Date range:** presets (6m / 1m / 1w), pick a week, pick a month, or custom calendar range
- **Download:** full report as **PDF** or availability data as **CSV**

## Breakeven & loss model

Each **room type** (category) has a `breakeven_per_night` — your minimum rate to cover all expenses.

| Metric | Formula |
|--------|---------|
| `available_nights` | period days × number of physical rooms |
| `vacant_nights` | available − occupied nights in period |
| `availability_loss_usd` | vacant nights × breakeven |
| `pricing_loss_usd` | (breakeven − tariff) × nights when tariff &lt; breakeven |
| `total_loss_usd` | availability loss + pricing loss |

Edit `data/room_type_breakeven.csv`:

```csv
room_type,breakeven_per_night
SBG - One Bedroom Apartment,120.00
SBG - Two Bedroom Apartment,180.00
```

Or use the dashboard **Breakeven config** tab.

## Project layout

```
analysis/
  breakeven.py      # Room-type breakeven load/save
  availability.py   # Vacant nights & daily pricing
  data_loader.py    # CSV load + merge on Res No
  metrics.py        # Report builder
  periods.py        # 6m / 1m / 1w windows
app.py
run_analysis.py
data/
```
