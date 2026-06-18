"""Aggregate category, tariff, and room-type metrics."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis.periods import DateWindow, Period, resolve_period


@dataclass
class AnalysisReport:
    window: DateWindow
    total_reservations: int
    total_room_nights: int
    category_usage: pd.DataFrame
    room_type_usage: pd.DataFrame
    reservations: pd.DataFrame

    def to_dict(self) -> dict:
        return {
            "window": {
                "period": self.window.period.value,
                "label": self.window.label,
                "start": self.window.start.isoformat(),
                "end": self.window.end.isoformat(),
            },
            "total_reservations": self.total_reservations,
            "total_room_nights": int(self.total_room_nights),
            "category_usage": self.category_usage.to_dict(orient="records"),
            "room_type_usage": self.room_type_usage.to_dict(orient="records"),
        }


def _category_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        frame.groupby("category", dropna=False)
        .agg(
            reservations=("res_no", "count"),
            room_nights=("nights", "sum"),
            avg_tariff=("tariff", "mean"),
            tariff_count=("tariff", "count"),
        )
        .reset_index()
    )
    grouped["usage_pct"] = (grouped["reservations"] / grouped["reservations"].sum() * 100).round(1)
    grouped["avg_tariff"] = grouped["avg_tariff"].round(2)
    grouped = grouped.sort_values("reservations", ascending=False)
    return grouped[
        ["category", "reservations", "room_nights", "usage_pct", "avg_tariff", "tariff_count"]
    ]


def _room_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        frame.groupby(["category", "room"], dropna=False)
        .agg(
            reservations=("res_no", "count"),
            room_nights=("nights", "sum"),
            avg_tariff=("tariff", "mean"),
        )
        .reset_index()
    )
    grouped["usage_pct"] = (
        grouped["reservations"] / grouped["reservations"].sum() * 100
    ).round(1)
    grouped["avg_tariff"] = grouped["avg_tariff"].round(2)
    return grouped.sort_values(["category", "reservations"], ascending=[True, False])


def build_report(
    frame: pd.DataFrame,
    period: Period,
    end_date=None,
) -> AnalysisReport:
    filtered, window = resolve_period(frame, period, end_date=end_date)
    return AnalysisReport(
        window=window,
        total_reservations=len(filtered),
        total_room_nights=int(filtered["nights"].sum()),
        category_usage=_category_metrics(filtered),
        room_type_usage=_room_metrics(filtered),
        reservations=filtered,
    )


def build_all_period_reports(frame: pd.DataFrame, end_date=None) -> dict[Period, AnalysisReport]:
    return {period: build_report(frame, period, end_date=end_date) for period in Period}
