"""Time-window helpers for presets and calendar-based custom ranges."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

import pandas as pd


class Period(str, Enum):
    SIX_MONTHS = "6_months"
    ONE_MONTH = "1_month"
    ONE_WEEK = "1_week"
    CUSTOM = "custom"

    @property
    def label(self) -> str:
        return {
            Period.SIX_MONTHS: "Last 6 months",
            Period.ONE_MONTH: "Last 1 month",
            Period.ONE_WEEK: "Last 1 week",
            Period.CUSTOM: "Custom range",
        }[self]


class DateRangeMode(str, Enum):
    PRESET = "preset"
    WEEK = "week"
    MONTH = "month"
    CUSTOM = "custom"


PERIOD_DAYS = {
    Period.SIX_MONTHS: 183,
    Period.ONE_MONTH: 30,
    Period.ONE_WEEK: 7,
}


@dataclass(frozen=True)
class DateWindow:
    period: Period
    start: pd.Timestamp
    end: pd.Timestamp
    range_mode: DateRangeMode = DateRangeMode.PRESET

    @property
    def label(self) -> str:
        span = f"{self.start.strftime('%d %b %Y')} – {self.end.strftime('%d %b %Y')}"
        if self.range_mode == DateRangeMode.WEEK:
            return f"Selected week ({span})"
        if self.range_mode == DateRangeMode.MONTH:
            return f"Selected month ({span})"
        if self.range_mode == DateRangeMode.CUSTOM:
            return f"Custom range ({span})"
        return f"{self.period.label} ({span})"


def reference_end_date(frame: pd.DataFrame, end_date: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    if end_date is not None:
        return pd.Timestamp(end_date).normalize()
    if frame.empty or frame["reference_date"].isna().all():
        return pd.Timestamp.today().normalize()
    return frame["reference_date"].max().normalize()


def reference_start_date(frame: pd.DataFrame) -> pd.Timestamp:
    if frame.empty or frame["reference_date"].isna().all():
        return pd.Timestamp.today().normalize()
    return frame["reference_date"].min().normalize()


def month_bounds(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    last_day = calendar.monthrange(year, month)[1]
    start = pd.Timestamp(year=year, month=month, day=1).normalize()
    end = pd.Timestamp(year=year, month=month, day=last_day).normalize()
    return start, end


def normalize_range_start_end(
    start: date | datetime | pd.Timestamp,
    end: date | datetime | pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts < start_ts:
        start_ts, end_ts = end_ts, start_ts
    return start_ts, end_ts


def make_date_window(
    start: date | datetime | pd.Timestamp,
    end: date | datetime | pd.Timestamp,
    *,
    range_mode: DateRangeMode,
    period: Period = Period.CUSTOM,
) -> DateWindow:
    start_ts, end_ts = normalize_range_start_end(start, end)
    return DateWindow(period=period, start=start_ts, end=end_ts, range_mode=range_mode)


def resolve_preset_window(
    frame: pd.DataFrame,
    period: Period,
    end_date: datetime | pd.Timestamp | None = None,
) -> DateWindow:
    end = reference_end_date(frame, end_date)
    days = PERIOD_DAYS[period]
    start = end - pd.Timedelta(days=days - 1)
    return DateWindow(period=period, start=start, end=end, range_mode=DateRangeMode.PRESET)


def resolve_period(
    frame: pd.DataFrame,
    period: Period,
    end_date: datetime | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, DateWindow]:
    window = resolve_preset_window(frame, period, end_date=end_date)
    mask = (frame["reference_date"] >= window.start) & (frame["reference_date"] <= window.end)
    return frame.loc[mask].copy(), window
