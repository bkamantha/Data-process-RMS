#!/usr/bin/env python3
"""Run hotel reservation analysis from Checked Out / Checked In CSV exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.breakeven import DEFAULT_BREAKEVEN_PATH, load_breakeven
from analysis.data_loader import load_merged_reservations
from analysis.forecast import forecast_next_month
from analysis.metrics import build_all_period_reports, build_report
from analysis.math_mcp import DEFAULT_MATHEMATICS_MCP_URL, MathematicsMCPClient
from analysis.mcp_metrics import enrich_report_with_mcp
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
    parser.add_argument("--pdf", help="Optional PDF report output path")
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable Mathematics MCP and use local calculations only",
    )
    parser.add_argument(
        "--availability-loss",
        action="store_true",
        help="Include availability loss USD (vacant nights × breakeven). Off by default.",
    )
    parser.add_argument(
        "--forecast",
        action="store_true",
        help="Print next-month availability statistical forecast",
    )
    return parser.parse_args()


def _print_report(report) -> None:
    print(f"\n=== {report.window.label} ===")
    print(f"Period days: {report.period_days}")
    print(f"Reservations (overlapping period): {report.total_reservations}")
    print(f"Occupied nights: {report.total_room_nights}")
    print(f"Available nights: {report.total_available_nights}")
    print(f"Vacant nights: {report.total_vacant_nights}")
    print(f"Occupancy: {report.occupancy_pct}%")
    print(f"Pricing loss (below breakeven): ${report.total_pricing_loss_usd:,.2f}")
    if report.include_availability_loss:
        print(f"Availability loss (vacant nights): ${report.total_availability_loss_usd:,.2f}")
        print(f"Total loss: ${report.total_loss_usd:,.2f}")
    print("\nRoom type summary:")
    print(report.room_type_summary.to_string(index=False))
    print("\nTop rooms by vacant nights:")
    top = report.room_availability.nlargest(10, "vacant_nights")
    if report.include_availability_loss:
        print("\nTop rooms by availability loss:")
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
        report = build_report(
            frame,
            period=Period(args.period),
            breakeven=breakeven,
            include_availability_loss=args.availability_loss,
        )
        _print_report(report)
        payload = report.to_dict()

    use_mcp = not args.no_mcp
    mcp_summary = enrich_report_with_mcp(report, use_mcp=use_mcp) if not args.all_periods else None
    if mcp_summary is not None:
        print(
            f"\nMathematics MCP ({DEFAULT_MATHEMATICS_MCP_URL}): "
            f"connected={mcp_summary.mcp_available}, "
            f"occupancy={mcp_summary.occupancy_pct}%, "
            f"verified_total_loss=${mcp_summary.verified_total_loss_usd:,.2f}"
        )
        payload["mcp_summary"] = mcp_summary.to_dict()

    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")

    if args.pdf and not args.all_periods:
        pdf_path = Path(args.pdf)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(build_pdf_report(report, mcp_summary=mcp_summary))
        print(f"Wrote {args.pdf}")

    if args.forecast:
        fc = forecast_next_month(frame)
        print(f"\n=== Forecast: {fc.target_label} ===")
        print(f"Method: {fc.method} ({fc.history_months} months history)")
        print(f"Available nights: {fc.available_nights}")
        print(f"Predicted occupied nights: {fc.predicted_occupied_nights:,.1f}")
        print(f"Predicted vacant nights: {fc.predicted_vacant_nights:,.1f}")
        print(f"Predicted occupancy: {fc.predicted_occupancy_pct:.1f}%")
        print(f"95% interval: {fc.lower_occupied_nights:,.1f} – {fc.upper_occupied_nights:,.1f} occupied nights")
        if not fc.room_type_forecast.empty:
            print("\nBy room type:")
            print(fc.room_type_forecast.to_string(index=False))


if __name__ == "__main__":
    main()
