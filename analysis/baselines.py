"""Per-room baseline tariff configuration for loss (USD) calculations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_BASELINE_PATH = Path("data/room_baselines.csv")

BASELINE_COLUMNS = ("room", "baseline_tariff")
OPTIONAL_CATEGORY_COLUMN = "category"


def load_baselines(path: str | Path | None = None) -> pd.DataFrame:
    baseline_path = Path(path) if path else DEFAULT_BASELINE_PATH
    if not baseline_path.exists():
        return pd.DataFrame(columns=list(BASELINE_COLUMNS))

    frame = pd.read_csv(baseline_path, dtype={"room": str})
    if "baseline_tariff" not in frame.columns:
        raise ValueError(f"{baseline_path} must include a baseline_tariff column")

    frame["baseline_tariff"] = pd.to_numeric(frame["baseline_tariff"], errors="coerce")
    frame["room"] = frame["room"].astype(str).str.strip()
    frame = frame.dropna(subset=["room", "baseline_tariff"])
    frame = frame.drop_duplicates(subset=["room"], keep="last")
    return frame[list(BASELINE_COLUMNS)].reset_index(drop=True)


def save_baselines(frame: pd.DataFrame, path: str | Path | None = None) -> Path:
    baseline_path = Path(path) if path else DEFAULT_BASELINE_PATH
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    output = frame[["room", "baseline_tariff"]].copy()
    output.to_csv(baseline_path, index=False)
    return baseline_path


def merge_baselines(frame: pd.DataFrame, baselines: pd.DataFrame) -> pd.DataFrame:
    if baselines.empty:
        result = frame.copy()
        result["baseline_tariff"] = pd.NA
        return result
    return frame.merge(baselines, on="room", how="left")


def apply_loss_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add revenue and loss USD columns at reservation level."""
    result = frame.copy()
    has_tariff = result["tariff"].notna() & (result["nights"] > 0)
    has_both = has_tariff & result["baseline_tariff"].notna()

    result["revenue_actual"] = 0.0
    result.loc[has_tariff, "revenue_actual"] = (
        result.loc[has_tariff, "tariff"] * result.loc[has_tariff, "nights"]
    )

    result["revenue_baseline"] = 0.0
    result.loc[has_both, "revenue_baseline"] = (
        result.loc[has_both, "baseline_tariff"] * result.loc[has_both, "nights"]
    )

    result["loss_usd"] = 0.0
    result.loc[has_both, "loss_usd"] = (
        (result.loc[has_both, "baseline_tariff"] - result.loc[has_both, "tariff"])
        .clip(lower=0)
        * result.loc[has_both, "nights"]
    )
    return result
