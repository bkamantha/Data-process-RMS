"""Time-window helpers for 6-month, 1-month, and 1-week drill-down."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import pandas as pd


class Period(str, Enum):
    SIX_MONTHS = "6_months"
    ONE_MONTH = "1_month"
    ONE_WEEK = "1_week"

    @property
    def label(self) -> str:
        return {
            Period.SIX_MONTHS: "Last 6 months",
            Period.ONE_MONTH: "Last 1 month",
            Period.ONE_WEEK: "Last 1 week",
        }[self]


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

    @property
    def label(self) -> str:
        return (
            f"{self.period.label} "
            f"({self.start.strftime('%d %b %Y')} – {self.end.strftime('%d %b %Y')})"
        )


def reference_end_date(frame: pd.DataFrame, end_date: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    if end_date is not None:
        return pd.Timestamp(end_date).normalize()
    if frame.empty or frame["reference_date"].isna().all():
        return pd.Timestamp.today().normalize()
    return frame["reference_date"].max().normalize()


def resolve_period(
    frame: pd.DataFrame,
    period: Period,
    end_date: datetime | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, DateWindow]:
    end = reference_end_date(frame, end_date)
    days = PERIOD_DAYS[period]
    start = end - pd.Timedelta(days=days - 1)
    mask = (frame["reference_date"] >= start) & (frame["reference_date"] <= end)
    window = DateWindow(period=period, start=start, end=end)
    return frame.loc[mask].copy(), window
