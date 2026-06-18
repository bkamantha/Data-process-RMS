"""Hotel reservation analysis framework for RMS CSV exports."""

from analysis.availability import build_availability_summary, build_daily_pricing
from analysis.breakeven import DEFAULT_BREAKEVEN_PATH, load_breakeven, save_breakeven
from analysis.data_loader import load_merged_reservations
from analysis.metrics import AnalysisReport, build_report, build_all_period_reports, distinct_room_types
from analysis.periods import (
    DateRangeMode,
    DateWindow,
    Period,
    make_date_window,
    month_bounds,
    resolve_period,
    resolve_preset_window,
)

__all__ = [
    "load_merged_reservations",
    "load_breakeven",
    "save_breakeven",
    "DEFAULT_BREAKEVEN_PATH",
    "distinct_room_types",
    "AnalysisReport",
    "build_report",
    "build_all_period_reports",
    "build_availability_summary",
    "build_daily_pricing",
    "Period",
    "DateRangeMode",
    "DateWindow",
    "make_date_window",
    "month_bounds",
    "resolve_period",
    "resolve_preset_window",
]
