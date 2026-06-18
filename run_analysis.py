#!/usr/bin/env python3
"""Run hotel reservation analysis from Checked Out / Checked In CSV exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.baselines import DEFAULT_BASELINE_PATH, load_baselines
from analysis.data_loader import load_merged_reservations
from analysis.metrics import build_all_period_reports, build_report
from analysis.periods import Period


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hotel RMS reservation analysis")
    parser.add_argument(
        "--checked-out",
        default="data/Checked_Out.csv",
        help="Path to Checked Out CSV export",
    )
    parser.add_argument(
        "--checked-in",
        default="data/Checked_In.csv",
        help="Path to Checked In CSV export",
    )
    parser.add_argument(
        "--baselines",
        default=str(DEFAULT_BASELINE_PATH),
        help="Path to room baseline tariff CSV (room, baseline_tariff)",
    )
    parser.add_argument(
        "--period",
        choices=[p.value for p in Period],
        default=Period.SIX_MONTHS.value,
        help="Analysis window (default: 6_months)",
    )
    parser.add_argument(
        "--all-periods",
        action="store_true",
        help="Print summaries for 6-month, 1-month, and 1-week windows",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path",
    )
    return parser.parse_args()


def _print_report(report) -> None:
    print(f"\n=== {report.window.label} ===")
    print(f"Reservations: {report.total_reservations}")
    print(f"Room nights: {report.total_room_nights}")
    print(f"Total loss (USD): ${report.total_loss_usd:,.2f}")
    print("\nCategory usage (% based on room nights):")
    print(report.category_usage.to_string(index=False))
    print("\nRoom type usage:")
    print(report.room_type_usage.to_string(index=False))


def main() -> None:
    args = parse_args()
    frame = load_merged_reservations(args.checked_out, args.checked_in)
    baselines = load_baselines(args.baselines)
    print(f"Loaded {len(frame)} reservations (guest names excluded; joined on Res No)")
    print(f"Loaded {len(baselines)} room baselines from {args.baselines}")

    if args.all_periods:
        reports = build_all_period_reports(frame, baselines=baselines)
        for report in reports.values():
            _print_report(report)
        payload = {p.value: r.to_dict() for p, r in reports.items()}
    else:
        report = build_report(frame, Period(args.period), baselines=baselines)
        _print_report(report)
        payload = report.to_dict()

    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
