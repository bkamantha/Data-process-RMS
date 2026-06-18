"""Statistical forecasting of monthly room availability and occupancy."""

from __future__ import annotations

import calendar
from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis.availability import build_room_inventory, window_day_count
from analysis.breakeven import overlapping_nights
from analysis.periods import make_date_window, month_bounds, reference_end_date


@dataclass
class MonthlyAvailabilityForecast:
    target_month: str
    target_label: str
    method: str
    history_months: int
    available_nights: int
    predicted_occupied_nights: float
    predicted_vacant_nights: float
    predicted_occupancy_pct: float
    lower_occupied_nights: float
    upper_occupied_nights: float
    monthly_history: pd.DataFrame
    room_type_forecast: pd.DataFrame

    def to_dict(self) -> dict:
        return {
            "target_month": self.target_month,
            "target_label": self.target_label,
            "method": self.method,
            "history_months": self.history_months,
            "available_nights": self.available_nights,
            "predicted_occupied_nights": round(self.predicted_occupied_nights, 1),
            "predicted_vacant_nights": round(self.predicted_vacant_nights, 1),
            "predicted_occupancy_pct": round(self.predicted_occupancy_pct, 1),
            "lower_occupied_nights": round(self.lower_occupied_nights, 1),
            "upper_occupied_nights": round(self.upper_occupied_nights, 1),
            "monthly_history": self.monthly_history.to_dict(orient="records"),
            "room_type_forecast": self.room_type_forecast.to_dict(orient="records"),
        }


def _month_periods(frame: pd.DataFrame) -> list[pd.Period]:
    start = frame["arrive"].min().to_period("M")
    end = frame["arrive"].max().to_period("M")
    return list(pd.period_range(start, end, freq="M"))


def _occupied_nights_in_month(frame: pd.DataFrame, month: pd.Period) -> pd.DataFrame:
    month_start, month_end = month_bounds(month.year, month.month)
    window_start = pd.Timestamp(month_start)
    window_end = pd.Timestamp(month_end)

    overlapping = frame[
        (frame["arrive"] <= window_end) & (frame["depart"] > window_start)
    ].copy()
    if overlapping.empty:
        return pd.DataFrame(columns=["room_type", "room", "occupied_nights"])

    overlapping["occupied_nights"] = overlapping.apply(
        lambda row: overlapping_nights(row["arrive"], row["depart"], window_start, window_end),
        axis=1,
    )
    overlapping = overlapping[overlapping["occupied_nights"] > 0]
    return (
        overlapping.groupby(["category", "room"], dropna=False)["occupied_nights"]
        .sum()
        .reset_index()
        .rename(columns={"category": "room_type"})
    )


def build_monthly_history(frame: pd.DataFrame) -> pd.DataFrame:
    inventory = build_room_inventory(frame)
    room_count = len(inventory)
    rows: list[dict] = []

    for month in _month_periods(frame):
        month_start, month_end = month_bounds(month.year, month.month)
        window_start = pd.Timestamp(month_start)
        window_end = pd.Timestamp(month_end)
        period_days = window_day_count(window_start, window_end)
        available_nights = period_days * room_count

        occupied_by_room = _occupied_nights_in_month(frame, month)
        occupied_nights = float(occupied_by_room["occupied_nights"].sum()) if not occupied_by_room.empty else 0.0
        vacant_nights = max(0.0, available_nights - occupied_nights)
        occupancy_pct = (occupied_nights / available_nights * 100) if available_nights else 0.0

        rows.append(
            {
                "month": str(month),
                "month_start": window_start,
                "period_days": period_days,
                "rooms": room_count,
                "available_nights": available_nights,
                "occupied_nights": occupied_nights,
                "vacant_nights": vacant_nights,
                "occupancy_pct": round(occupancy_pct, 1),
            }
        )

    return pd.DataFrame(rows)


def _fit_forecast(values: np.ndarray) -> tuple[float, float, float, str]:
    """Return (point forecast, lower, upper, method name)."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0, "no_data"
    if n == 1:
        v = float(values[0])
        return v, v, v, "single_month"

    y = values.astype(float)
    x = np.arange(n, dtype=float)

    # Emphasise recent months (last 3) for short hotel booking history
    recent_n = min(3, n)
    recent = y[-recent_n:]
    recent_weights = np.linspace(0.6, 1.0, recent_n)
    wma_recent = float(np.average(recent, weights=recent_weights))

    # Damped month-on-month extrapolation from last two months
    mom = float(y[-1] - y[-2]) if n >= 2 else 0.0
    momentum_forecast = float(y[-1] + 0.75 * mom)

    slope, intercept = np.polyfit(x[-min(4, n) :], y[-min(4, n) :], 1)
    trend_forecast = float(intercept + slope * n)

    point = 0.50 * momentum_forecast + 0.30 * wma_recent + 0.20 * trend_forecast
    method = "recent_weighted_ma + momentum + trend"

    if n >= 4:
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing

            model = ExponentialSmoothing(y, trend="add", seasonal=None, initialization_method="estimated")
            fit = model.fit(optimized=True)
            ets_forecast = float(fit.forecast(1)[0])
            point = 0.75 * point + 0.25 * ets_forecast
            method = "blend(recent_momentum, holt_linear)"
        except Exception:
            pass

    if n >= 3:
        fitted = intercept + slope * x[-min(4, n) :]
        residuals = y[-min(4, n) :] - fitted
    else:
        residuals = y - np.mean(y)
    std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
    lower = max(0.0, point - 1.96 * std)
    upper = point + 1.96 * std
    return point, lower, upper, method


def _next_month_after(frame: pd.DataFrame) -> pd.Period:
    last = reference_end_date(frame).to_period("M")
    return last + 1


def forecast_next_month(frame: pd.DataFrame) -> MonthlyAvailabilityForecast:
    history = build_monthly_history(frame)
    if history.empty:
        target = _next_month_after(frame)
        return MonthlyAvailabilityForecast(
            target_month=str(target),
            target_label=target.strftime("%B %Y"),
            method="no_data",
            history_months=0,
            available_nights=0,
            predicted_occupied_nights=0.0,
            predicted_vacant_nights=0.0,
            predicted_occupancy_pct=0.0,
            lower_occupied_nights=0.0,
            upper_occupied_nights=0.0,
            monthly_history=history,
            room_type_forecast=pd.DataFrame(),
        )

    target = _next_month_after(frame)
    month_start, month_end = month_bounds(target.year, target.month)
    window_start = pd.Timestamp(month_start)
    window_end = pd.Timestamp(month_end)
    period_days = window_day_count(window_start, window_end)
    room_count = int(history["rooms"].iloc[-1])
    available_nights = period_days * room_count

    occupied_series = history["occupied_nights"].to_numpy()
    point, lower, upper, method = _fit_forecast(occupied_series)
    point = float(np.clip(point, 0, available_nights))
    lower = float(np.clip(lower, 0, available_nights))
    upper = float(np.clip(upper, 0, available_nights))
    vacant = max(0.0, available_nights - point)
    occupancy_pct = (point / available_nights * 100) if available_nights else 0.0

    room_type_history_rows: list[dict] = []
    for month in _month_periods(frame):
        occupied_by_room = _occupied_nights_in_month(frame, month)
        if occupied_by_room.empty:
            continue
        by_type = occupied_by_room.groupby("room_type")["occupied_nights"].sum().reset_index()
        by_type["month"] = str(month)
        room_type_history_rows.extend(by_type.to_dict(orient="records"))

    room_type_history = pd.DataFrame(room_type_history_rows)
    room_type_forecast_rows: list[dict] = []
    if not room_type_history.empty:
        inventory = build_room_inventory(frame)
        rooms_per_type = inventory.groupby("room_type")["room"].count()
        for room_type, group in room_type_history.groupby("room_type"):
            type_values = group.sort_values("month")["occupied_nights"].to_numpy()
            type_point, type_lower, type_upper, _ = _fit_forecast(type_values)
            type_rooms = int(rooms_per_type.get(room_type, 1))
            type_available = period_days * type_rooms
            type_point = float(np.clip(type_point, 0, type_available))
            type_vacant = max(0.0, type_available - type_point)
            room_type_forecast_rows.append(
                {
                    "room_type": room_type,
                    "rooms": type_rooms,
                    "available_nights": type_available,
                    "predicted_occupied_nights": round(type_point, 1),
                    "predicted_vacant_nights": round(type_vacant, 1),
                    "predicted_occupancy_pct": round(type_point / type_available * 100, 1) if type_available else 0.0,
                    "lower_occupied_nights": round(type_lower, 1),
                    "upper_occupied_nights": round(min(type_upper, type_available), 1),
                }
            )

    return MonthlyAvailabilityForecast(
        target_month=str(target),
        target_label=target.strftime("%B %Y"),
        method=method,
        history_months=len(history),
        available_nights=available_nights,
        predicted_occupied_nights=point,
        predicted_vacant_nights=vacant,
        predicted_occupancy_pct=occupancy_pct,
        lower_occupied_nights=lower,
        upper_occupied_nights=upper,
        monthly_history=history,
        room_type_forecast=pd.DataFrame(room_type_forecast_rows).sort_values(
            "predicted_occupied_nights", ascending=False
        ),
    )
