"""Load and merge Checked Out / Checked In CSV exports by reservation number."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

DATE_FORMAT = "%d %b %Y"

CHECKED_OUT_COLUMNS = {
    "Res No": "res_no",
    "Category": "category",
    "Room": "room",
    "Guest Status": "guest_status",
    "Market Segment": "market_segment",
    "Arrive": "arrive",
    "Depart": "depart",
    "Main Bill Amount": "main_bill_amount",
    "Bill To": "bill_to",
    "Extra Bill Amount": "extra_bill_amount",
    "Settlement": "settlement",
}

CHECKED_IN_COLUMNS = {
    "Res No": "res_no",
    "Category": "category",
    "Room": "room",
    "Market Segment": "market_segment",
    "Guest Status": "guest_status",
    "Arrive": "arrive",
    "Depart": "depart",
    "Pax": "pax",
    "Travel Agent": "travel_agent",
    "Company": "company",
    "Tariff": "tariff",
    "Nationality": "nationality",
}


@dataclass(frozen=True)
class LoaderConfig:
    checked_out_path: Path
    checked_in_path: Path


def _parse_dates(frame: pd.DataFrame) -> pd.DataFrame:
    for column in ("arrive", "depart"):
        frame[column] = pd.to_datetime(frame[column], format=DATE_FORMAT, errors="coerce")
    frame["nights"] = (frame["depart"] - frame["arrive"]).dt.days.clip(lower=0)
    return frame


def _read_checked_out(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"Res No": str})
    frame = frame.rename(columns={k: v for k, v in CHECKED_OUT_COLUMNS.items() if k in frame.columns})
    frame = frame.drop(columns=[c for c in frame.columns if c.lower() == "guest" or c.startswith("Unnamed")], errors="ignore")
    for column in ("main_bill_amount", "extra_bill_amount"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return _parse_dates(frame)


def _read_checked_in(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"Res No": str})
    frame = frame.rename(columns={k: v for k, v in CHECKED_IN_COLUMNS.items() if k in frame.columns})
    frame = frame.drop(columns=[c for c in frame.columns if c.lower() == "guest"], errors="ignore")
    if "tariff" in frame.columns:
        frame["tariff"] = pd.to_numeric(frame["tariff"], errors="coerce")
    return _parse_dates(frame)


def load_merged_reservations(
    checked_out_path: str | Path,
    checked_in_path: str | Path,
) -> pd.DataFrame:
    """
    Merge exports on Res No. Guest names are excluded from the merged dataset.
    Checked-in rows contribute tariff and pax; checked-out rows supply billing fields.
    """
    out = _read_checked_out(Path(checked_out_path))
    inn = _read_checked_in(Path(checked_in_path))

    tariff_cols = [c for c in ("tariff", "pax", "travel_agent", "company", "nationality") if c in inn.columns]
    inn_subset = inn[["res_no", *tariff_cols]].drop_duplicates(subset=["res_no"])

    merged = out.merge(inn_subset, on="res_no", how="left", suffixes=("", "_in"))

    guest_columns = [c for c in merged.columns if c.lower() == "guest"]
    merged = merged.drop(columns=guest_columns)

    for column in ("category", "room", "market_segment", "guest_status", "arrive", "depart", "nights"):
        in_column = f"{column}_in"
        if in_column in merged.columns:
            merged[column] = merged[column].fillna(merged[in_column])
            merged = merged.drop(columns=[in_column])

    merged["has_tariff"] = merged["tariff"].notna()
    merged["reference_date"] = merged["arrive"]
    merged = merged.sort_values(["arrive", "res_no"]).reset_index(drop=True)
    return merged


def reservation_ids(frame: pd.DataFrame) -> Iterable[str]:
    return frame["res_no"].astype(str).tolist()
