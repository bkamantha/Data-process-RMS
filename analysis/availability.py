"""Availability and daily pricing metrics using room-type breakeven."""

from __future__ import annotations

import pandas as pd

from analysis.breakeven import overlapping_nights


def window_day_count(window_start: pd.Timestamp, window_end: pd.Timestamp) -> int:
    return int((window_end.normalize() - window_start.normalize()).days + 1)


def build_room_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame[["category", "room"]]
        .drop_duplicates()
        .rename(columns={"category": "room_type"})
        .sort_values(["room_type", "room"])
        .reset_index(drop=True)
    )


def _occupied_nights_by_room(
    reservations: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    overlapping = reservations[
        (reservations["arrive"] <= window_end) & (reservations["depart"] > window_start)
    ].copy()
    if overlapping.empty:
        return pd.DataFrame(columns=["room_type", "room", "occupied_nights", "revenue_actual", "pricing_loss_usd"])

    overlapping["occupied_nights"] = overlapping.apply(
        lambda row: overlapping_nights(row["arrive"], row["depart"], window_start, window_end),
        axis=1,
    )
    overlapping = overlapping[overlapping["occupied_nights"] > 0]
    return (
        overlapping.groupby(["category", "room"], dropna=False)
        .agg(
            occupied_nights=("occupied_nights", "sum"),
            revenue_actual=("revenue_actual", "sum"),
            pricing_loss_usd=("pricing_loss_usd", "sum"),
        )
        .reset_index()
        .rename(columns={"category": "room_type"})
    )


def build_availability_summary(
    full_frame: pd.DataFrame,
    period_reservations: pd.DataFrame,
    breakeven: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    include_availability_loss: bool = False,
) -> pd.DataFrame:
    inventory = build_room_inventory(full_frame)
    period_days = window_day_count(window_start, window_end)
    occupied = _occupied_nights_by_room(period_reservations, window_start, window_end)

    summary = inventory.merge(occupied, on=["room_type", "room"], how="left")
    for column in ("occupied_nights", "revenue_actual", "pricing_loss_usd"):
        summary[column] = summary[column].fillna(0.0)

    summary = summary.merge(breakeven, on="room_type", how="left")
    summary["available_nights"] = period_days
    summary["vacant_nights"] = (summary["available_nights"] - summary["occupied_nights"]).clip(lower=0)
    summary["occupancy_pct"] = (
        summary["occupied_nights"] / summary["available_nights"] * 100
    ).round(1)
    summary["availability_loss_usd"] = summary["vacant_nights"] * summary["breakeven_per_night"].fillna(0)
    summary["breakeven_revenue_target"] = summary["available_nights"] * summary["breakeven_per_night"].fillna(0)
    if not include_availability_loss:
        summary["availability_loss_usd"] = 0.0
    summary["total_loss_usd"] = summary["pricing_loss_usd"] + summary["availability_loss_usd"]

    return summary.sort_values(["room_type", "room"]).reset_index(drop=True)


def build_room_type_availability(summary: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        summary.groupby("room_type", dropna=False)
        .agg(
            rooms=("room", "count"),
            available_nights=("available_nights", "sum"),
            occupied_nights=("occupied_nights", "sum"),
            vacant_nights=("vacant_nights", "sum"),
            revenue_actual=("revenue_actual", "sum"),
            breakeven_revenue_target=("breakeven_revenue_target", "sum"),
            breakeven_per_night=("breakeven_per_night", "first"),
            pricing_loss_usd=("pricing_loss_usd", "sum"),
            availability_loss_usd=("availability_loss_usd", "sum"),
            total_loss_usd=("total_loss_usd", "sum"),
        )
        .reset_index()
    )
    grouped["occupancy_pct"] = (
        grouped["occupied_nights"] / grouped["available_nights"] * 100
    ).round(1)
    total_occupied = grouped["occupied_nights"].sum()
    grouped["nights_pct"] = (
        grouped["occupied_nights"] / total_occupied * 100 if total_occupied else 0
    ).round(1)
    grouped["avg_tariff"] = (
        grouped["revenue_actual"] / grouped["occupied_nights"].replace(0, pd.NA)
    ).round(2)
    return grouped.sort_values("occupied_nights", ascending=False)


def build_daily_pricing(
    reservations: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    """Daily occupied nights, avg tariff, and loss vs breakeven for pricing review."""
    overlapping = reservations[
        (reservations["arrive"] <= window_end) & (reservations["depart"] > window_start)
    ].copy()
    if overlapping.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "room_type",
                "occupied_nights",
                "avg_tariff",
                "breakeven_per_night",
                "revenue_actual",
                "breakeven_revenue",
                "pricing_loss_usd",
            ]
        )

    rows: list[dict] = []
    for _, row in overlapping.iterrows():
        stay_start = max(pd.Timestamp(row["arrive"]).normalize(), window_start.normalize())
        stay_end = min(pd.Timestamp(row["depart"]).normalize(), window_end.normalize() + pd.Timedelta(days=1))
        current = stay_start
        while current < stay_end and current < pd.Timestamp(row["depart"]).normalize():
            rows.append(
                {
                    "date": current,
                    "room_type": row["category"],
                    "tariff": row["tariff"],
                    "breakeven_per_night": row["breakeven_per_night"],
                    "pricing_loss_usd": max(0.0, float(row["breakeven_per_night"] or 0) - float(row["tariff"] or 0))
                    if pd.notna(row["tariff"]) and pd.notna(row["breakeven_per_night"])
                    else 0.0,
                }
            )
            current += pd.Timedelta(days=1)

    daily = pd.DataFrame(rows)
    grouped = (
        daily.groupby(["date", "room_type"], dropna=False)
        .agg(
            occupied_nights=("date", "count"),
            avg_tariff=("tariff", "mean"),
            breakeven_per_night=("breakeven_per_night", "first"),
            pricing_loss_usd=("pricing_loss_usd", "sum"),
        )
        .reset_index()
    )
    grouped["revenue_actual"] = (grouped["avg_tariff"].fillna(0) * grouped["occupied_nights"]).round(2)
    grouped["breakeven_revenue"] = (grouped["breakeven_per_night"].fillna(0) * grouped["occupied_nights"]).round(2)
    grouped["avg_tariff"] = grouped["avg_tariff"].round(2)
    grouped["pricing_loss_usd"] = grouped["pricing_loss_usd"].round(2)
    return grouped.sort_values(["date", "room_type"]).reset_index(drop=True)
