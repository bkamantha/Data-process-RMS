"""Aggregate category, tariff, room-type metrics, and baseline loss (USD)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis.baselines import apply_loss_columns, load_baselines, merge_baselines
from analysis.periods import DateWindow, Period, resolve_period


@dataclass
class AnalysisReport:
    window: DateWindow
    total_reservations: int
    total_room_nights: int
    total_loss_usd: float
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
            "total_loss_usd": round(self.total_loss_usd, 2),
            "category_usage": self.category_usage.to_dict(orient="records"),
            "room_type_usage": self.room_type_usage.to_dict(orient="records"),
        }


def _nights_pct(nights: pd.Series, total_nights: int) -> pd.Series:
    if total_nights <= 0:
        return pd.Series(0.0, index=nights.index)
    return (nights / total_nights * 100).round(1)


def _category_metrics(frame: pd.DataFrame, total_nights: int) -> pd.DataFrame:
    grouped = (
        frame.groupby("category", dropna=False)
        .agg(
            reservations=("res_no", "count"),
            room_nights=("nights", "sum"),
            avg_tariff=("tariff", "mean"),
            avg_baseline=("baseline_tariff", "mean"),
            tariff_count=("tariff", "count"),
            loss_usd=("loss_usd", "sum"),
            revenue_actual=("revenue_actual", "sum"),
            revenue_baseline=("revenue_baseline", "sum"),
        )
        .reset_index()
    )
    grouped["nights_pct"] = _nights_pct(grouped["room_nights"], total_nights)
    grouped["avg_tariff"] = grouped["avg_tariff"].round(2)
    grouped["avg_baseline"] = grouped["avg_baseline"].round(2)
    grouped["loss_usd"] = grouped["loss_usd"].round(2)
    grouped = grouped.sort_values("room_nights", ascending=False)
    return grouped[
        [
            "category",
            "reservations",
            "room_nights",
            "nights_pct",
            "avg_tariff",
            "avg_baseline",
            "loss_usd",
            "revenue_actual",
            "revenue_baseline",
            "tariff_count",
        ]
    ]


def _room_metrics(frame: pd.DataFrame, total_nights: int) -> pd.DataFrame:
    grouped = (
        frame.groupby(["category", "room"], dropna=False)
        .agg(
            reservations=("res_no", "count"),
            room_nights=("nights", "sum"),
            avg_tariff=("tariff", "mean"),
            baseline_tariff=("baseline_tariff", "first"),
            loss_usd=("loss_usd", "sum"),
            revenue_actual=("revenue_actual", "sum"),
            revenue_baseline=("revenue_baseline", "sum"),
        )
        .reset_index()
    )
    grouped["nights_pct"] = _nights_pct(grouped["room_nights"], total_nights)
    grouped["avg_tariff"] = grouped["avg_tariff"].round(2)
    grouped["loss_usd"] = grouped["loss_usd"].round(2)
    grouped["revenue_actual"] = grouped["revenue_actual"].round(2)
    grouped["revenue_baseline"] = grouped["revenue_baseline"].round(2)
    return grouped.sort_values(["category", "room_nights"], ascending=[True, False])


def build_report(
    frame: pd.DataFrame,
    period: Period,
    end_date=None,
    baselines: pd.DataFrame | None = None,
    baseline_path: str | None = None,
) -> AnalysisReport:
    if baselines is None:
        baselines = load_baselines(baseline_path)

    enriched = apply_loss_columns(merge_baselines(frame, baselines))
    filtered, window = resolve_period(enriched, period, end_date=end_date)
    total_nights = int(filtered["nights"].sum())

    return AnalysisReport(
        window=window,
        total_reservations=len(filtered),
        total_room_nights=total_nights,
        total_loss_usd=float(filtered["loss_usd"].sum()),
        category_usage=_category_metrics(filtered, total_nights),
        room_type_usage=_room_metrics(filtered, total_nights),
        reservations=filtered,
    )


def build_all_period_reports(
    frame: pd.DataFrame,
    end_date=None,
    baselines: pd.DataFrame | None = None,
    baseline_path: str | None = None,
) -> dict[Period, AnalysisReport]:
    if baselines is None:
        baselines = load_baselines(baseline_path)
    return {
        period: build_report(frame, period, end_date=end_date, baselines=baselines)
        for period in Period
    }


def distinct_rooms(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame[["category", "room"]]
        .drop_duplicates()
        .sort_values(["category", "room"])
        .reset_index(drop=True)
    )
