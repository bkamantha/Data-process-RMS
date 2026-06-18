"""Aggregate category, tariff, breakeven, and availability loss metrics."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from analysis.availability import (
    build_availability_summary,
    build_daily_pricing,
    build_room_type_availability,
    window_day_count,
)
from analysis.breakeven import apply_reservation_metrics, attach_breakeven, load_breakeven
from analysis.periods import DateRangeMode, DateWindow, Period, resolve_preset_window


@dataclass
class AnalysisReport:
    window: DateWindow
    period_days: int
    total_reservations: int
    total_room_nights: int
    total_available_nights: int
    total_vacant_nights: int
    total_pricing_loss_usd: float
    total_availability_loss_usd: float
    total_loss_usd: float
    room_type_summary: pd.DataFrame
    room_availability: pd.DataFrame
    daily_pricing: pd.DataFrame
    reservations: pd.DataFrame
    include_availability_loss: bool = False

    @property
    def occupancy_pct(self) -> float:
        if self.total_available_nights <= 0:
            return 0.0
        return round(self.total_room_nights / self.total_available_nights * 100, 1)

    def to_dict(self) -> dict:
        return {
            "window": {
                "period": self.window.period.value,
                "label": self.window.label,
                "start": self.window.start.isoformat(),
                "end": self.window.end.isoformat(),
            },
            "period_days": self.period_days,
            "total_reservations": self.total_reservations,
            "total_room_nights": int(self.total_room_nights),
            "total_available_nights": int(self.total_available_nights),
            "total_vacant_nights": int(self.total_vacant_nights),
            "total_pricing_loss_usd": round(self.total_pricing_loss_usd, 2),
            "total_availability_loss_usd": round(self.total_availability_loss_usd, 2),
            "total_loss_usd": round(self.total_loss_usd, 2),
            "include_availability_loss": self.include_availability_loss,
            "occupancy_pct": self.occupancy_pct,
            "room_type_summary": self.room_type_summary.to_dict(orient="records"),
            "room_availability": self.room_availability.to_dict(orient="records"),
            "daily_pricing": self.daily_pricing.to_dict(orient="records"),
        }


def _reservations_in_window(frame: pd.DataFrame, window: DateWindow) -> pd.DataFrame:
    return frame[
        (frame["arrive"] <= window.end) & (frame["depart"] > window.start)
    ].copy()


def build_report(
    frame: pd.DataFrame,
    period: Period | DateWindow | None = None,
    *,
    window: DateWindow | None = None,
    end_date=None,
    breakeven: pd.DataFrame | None = None,
    breakeven_path: str | None = None,
    include_availability_loss: bool = False,
) -> AnalysisReport:
    if breakeven is None:
        breakeven = load_breakeven(breakeven_path)

    # Backward compatibility: older callers passed Period as the `window` argument.
    if isinstance(window, Period):
        period = window
        window = None
    if isinstance(period, DateWindow):
        window = period
        period = None
    if period is None:
        period = Period.SIX_MONTHS

    enriched = attach_breakeven(frame, breakeven)
    if window is None:
        window = resolve_preset_window(enriched, period, end_date=end_date)
    elif not isinstance(window, DateWindow):
        raise TypeError(f"window must be a DateWindow, got {type(window).__name__}")
    period_days = window_day_count(window.start, window.end)

    period_reservations = _reservations_in_window(enriched, window)
    period_reservations = apply_reservation_metrics(period_reservations, window.start, window.end)

    room_availability = build_availability_summary(
        full_frame=enriched,
        period_reservations=period_reservations,
        breakeven=breakeven,
        window_start=window.start,
        window_end=window.end,
        include_availability_loss=include_availability_loss,
    )
    room_type_summary = build_room_type_availability(room_availability)
    daily_pricing = build_daily_pricing(period_reservations, window.start, window.end)

    total_occupied = int(room_availability["occupied_nights"].sum())
    return AnalysisReport(
        window=window,
        period_days=period_days,
        total_reservations=len(period_reservations),
        total_room_nights=total_occupied,
        total_available_nights=int(room_availability["available_nights"].sum()),
        total_vacant_nights=int(room_availability["vacant_nights"].sum()),
        total_pricing_loss_usd=float(room_availability["pricing_loss_usd"].sum()),
        total_availability_loss_usd=float(room_availability["availability_loss_usd"].sum()),
        total_loss_usd=float(room_availability["total_loss_usd"].sum()),
        room_type_summary=room_type_summary,
        room_availability=room_availability,
        daily_pricing=daily_pricing,
        reservations=period_reservations,
        include_availability_loss=include_availability_loss,
    )


def build_all_period_reports(
    frame: pd.DataFrame,
    end_date=None,
    breakeven: pd.DataFrame | None = None,
    breakeven_path: str | None = None,
) -> dict[Period, AnalysisReport]:
    if breakeven is None:
        breakeven = load_breakeven(breakeven_path)
    preset_periods = [p for p in Period if p != Period.CUSTOM]
    return {
        period: build_report(
            frame,
            period,
            end_date=end_date,
            breakeven=breakeven,
        )
        for period in preset_periods
    }


def distinct_room_types(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame[["category"]]
        .drop_duplicates()
        .rename(columns={"category": "room_type"})
        .sort_values("room_type")
        .reset_index(drop=True)
    )
