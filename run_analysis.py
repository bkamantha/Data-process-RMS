#!/usr/bin/env python3
"""Run hotel reservation analysis from Checked Out / Checked In CSV exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.breakeven import DEFAULT_BREAKEVEN_PATH, load_breakeven
from analysis.data_loader import load_merged_reservations
from analysis.metrics import build_all_period_reports, build_report
from analysis.pdf_report import build_pdf_report
from analysis.periods import Period


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hotel RMS reservation analysis")
    parser.add_argument("--checked-out", default="data/Checked_Out.csv")
    parser.add_argument("--checked-in", default="data/Checked_In.csv")
    parser.add_argument(
        "--breakeven",
        default=str(DEFAULT_BREAKEVEN_PATH),
        help="Path to room type breakeven CSV (room_type, breakeven_per_night)",
    )
    parser.add_argument(
        "--period",
        choices=[p.value for p in Period],
        default=Period.SIX_MONTHS.value,
    )
    parser.add_argument("--all-periods", action="store_true")
    parser.add_argument("--output", help="Optional JSON output path")
    return parser.parse_args()


def _print_report(report) -> None:
    print(f"\n=== {report.window.label} ===")
    print(f"Period days: {report.period_days}")
    print(f"Reservations (overlapping period): {report.total_reservations}")
    print(f"Occupied nights: {report.total_room_nights}")
    print(f"Available nights: {report.total_available_nights}")
    print(f"Vacant nights: {report.total_vacant_nights}")
    print(f"Pricing loss (below breakeven): ${report.total_pricing_loss_usd:,.2f}")
    print(f"Availability loss (vacant nights): ${report.total_availability_loss_usd:,.2f}")
    print(f"Total loss: ${report.total_loss_usd:,.2f}")
    print("\nRoom type summary:")
    print(report.room_type_summary.to_string(index=False))
    print("\nTop availability loss by room:")
    top = report.room_availability.nlargest(10, "availability_loss_usd")
    print(top.to_string(index=False))


def main() -> None:
    args = parse_args()
    frame = load_merged_reservations(args.checked_out, args.checked_in)
    breakeven = load_breakeven(args.breakeven)
    print(f"Loaded {len(frame)} reservations (guest names excluded; joined on Res No)")
    print(f"Loaded {len(breakeven)} room type breakeven rates from {args.breakeven}")

    if args.all_periods:
        reports = build_all_period_reports(frame, breakeven=breakeven)
        for report in reports.values():
            _print_report(report)
        payload = {p.value: r.to_dict() for p, r in reports.items()}
    else:
        report = build_report(frame, Period(args.period), breakeven=breakeven)
        _print_report(report)
        payload = report.to_dict()

    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
