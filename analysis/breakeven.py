"""Room-type breakeven rates (expenses included) for revenue and availability loss."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_BREAKEVEN_PATH = Path("data/room_type_breakeven.csv")
LEGACY_BASELINE_PATH = Path("data/room_baselines.csv")

BREAKEVEN_COLUMNS = ("room_type", "breakeven_per_night")


def load_breakeven(path: str | Path | None = None) -> pd.DataFrame:
    breakeven_path = Path(path) if path else DEFAULT_BREAKEVEN_PATH
    if not breakeven_path.exists() and LEGACY_BASELINE_PATH.exists():
        legacy = pd.read_csv(LEGACY_BASELINE_PATH, dtype={"room": str})
        if "baseline_tariff" in legacy.columns and "room" in legacy.columns:
            return pd.DataFrame(columns=list(BREAKEVEN_COLUMNS))

    if not breakeven_path.exists():
        return pd.DataFrame(columns=list(BREAKEVEN_COLUMNS))

    frame = pd.read_csv(breakeven_path)
    if "breakeven_per_night" not in frame.columns:
        raise ValueError(f"{breakeven_path} must include breakeven_per_night")

    type_col = "room_type" if "room_type" in frame.columns else "category"
    frame = frame.rename(columns={type_col: "room_type"})
    frame["breakeven_per_night"] = pd.to_numeric(frame["breakeven_per_night"], errors="coerce")
    frame["room_type"] = frame["room_type"].astype(str).str.strip()
    frame = frame.dropna(subset=["room_type", "breakeven_per_night"])
    frame = frame.drop_duplicates(subset=["room_type"], keep="last")
    return frame[list(BREAKEVEN_COLUMNS)].reset_index(drop=True)


def save_breakeven(frame: pd.DataFrame, path: str | Path | None = None) -> Path:
    breakeven_path = Path(path) if path else DEFAULT_BREAKEVEN_PATH
    breakeven_path.parent.mkdir(parents=True, exist_ok=True)
    output = frame[["room_type", "breakeven_per_night"]].copy()
    output.to_csv(breakeven_path, index=False)
    return breakeven_path


def attach_breakeven(frame: pd.DataFrame, breakeven: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if breakeven.empty:
        result["breakeven_per_night"] = pd.NA
        return result
    lookup = breakeven.rename(columns={"room_type": "category"})
    return result.merge(lookup, on="category", how="left")


def overlapping_nights(
    arrive: pd.Timestamp,
    depart: pd.Timestamp,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> int:
    """Count occupied nights that fall inside the analysis window."""
    if pd.isna(arrive) or pd.isna(depart):
        return 0

    stay_start = pd.Timestamp(arrive).normalize()
    stay_end = pd.Timestamp(depart).normalize()
    last_occupied = stay_end - pd.Timedelta(days=1)
    if last_occupied < stay_start:
        return 0

    overlap_start = max(stay_start, window_start.normalize())
    overlap_end = min(last_occupied, window_end.normalize())
    if overlap_start > overlap_end:
        return 0
    return int((overlap_end - overlap_start).days + 1)


def apply_reservation_metrics(frame: pd.DataFrame, window_start: pd.Timestamp, window_end: pd.Timestamp) -> pd.DataFrame:
    """Add per-reservation revenue and pricing loss vs breakeven for nights in window."""
    result = frame.copy()
    result["period_nights"] = result.apply(
        lambda row: overlapping_nights(row["arrive"], row["depart"], window_start, window_end),
        axis=1,
    )

    has_tariff = result["tariff"].notna() & (result["period_nights"] > 0)
    has_breakeven = result["breakeven_per_night"].notna() & (result["period_nights"] > 0)
    has_both = has_tariff & has_breakeven

    result["revenue_actual"] = 0.0
    result.loc[has_tariff, "revenue_actual"] = (
        result.loc[has_tariff, "tariff"] * result.loc[has_tariff, "period_nights"]
    )

    result["breakeven_revenue"] = 0.0
    result.loc[has_breakeven, "breakeven_revenue"] = (
        result.loc[has_breakeven, "breakeven_per_night"] * result.loc[has_breakeven, "period_nights"]
    )

    result["pricing_loss_usd"] = 0.0
    result.loc[has_both, "pricing_loss_usd"] = (
        (result.loc[has_both, "breakeven_per_night"] - result.loc[has_both, "tariff"]).clip(lower=0)
        * result.loc[has_both, "period_nights"]
    )
    return result
