"""Generate a PDF export of the full analysis report."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

if TYPE_CHECKING:
    from analysis.metrics import AnalysisReport
    from analysis.mcp_metrics import MCPSummary


def _shorten_room_type(name: str) -> str:
    return (
        str(name)
        .replace("SBG - ", "")
        .replace(" Apartment", "")
        .replace(" Suite", "")
    )


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _fig_bytes(fig) -> BytesIO:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _chart_image(fig, width: float) -> Image:
    aspect = fig.get_size_inches()
    height = width * (aspect[1] / aspect[0])
    return Image(_fig_bytes(fig), width=width, height=height)


def _pie_chart(labels: list[str], values: list[float], title: str):
    fig, ax = plt.subplots(figsize=(5.5, 4))
    if not values or sum(values) <= 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title)
        ax.axis("off")
        return fig
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title(title)
    return fig


def _bar_chart(categories: list[str], values: list[float], title: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(7, 4))
    if not categories:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title)
        ax.axis("off")
        return fig
    ax.bar(categories, values, color="#4C78A8")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    return fig


def _line_chart(dates, series: dict[str, list[float]], title: str, ylabel: str):
    fig, ax = plt.subplots(figsize=(7, 4))
    if not dates:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title)
        ax.axis("off")
        return fig
    for name, values in series.items():
        ax.plot(dates, values, marker="o", label=name)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8, loc="best")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    return fig


def _dataframe_table(frame: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> Table:
    display = frame[columns].copy()
    if max_rows is not None:
        display = display.head(max_rows)

    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda v: f"{v:,.2f}" if pd.notna(v) else "")

    data = [columns] + display.astype(str).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def build_pdf_report(report: "AnalysisReport", mcp_summary: "MCPSummary | None" = None) -> bytes:
    """Build a multi-section PDF for the full analysis report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=8,
        spaceAfter=8,
    )
    body_style = styles["BodyText"]

    story: list = []
    story.append(Paragraph("Hotel Reservation Analysis Report", title_style))
    story.append(Paragraph(report.window.label, body_style))
    story.append(Spacer(1, 0.15 * inch))

    summary_rows = [
        ["Metric", "Value"],
        ["Period days", str(report.period_days)],
        ["Reservations", str(report.total_reservations)],
        ["Occupied nights", str(report.total_room_nights)],
        ["Available nights", str(report.total_available_nights)],
        ["Vacant nights", str(report.total_vacant_nights)],
        ["Occupancy", f"{(report.total_room_nights / report.total_available_nights * 100):.1f}%"
         if report.total_available_nights else "N/A"],
        ["Availability loss", _money(report.total_availability_loss_usd)],
        ["Pricing loss", _money(report.total_pricing_loss_usd)],
        ["Total loss", _money(report.total_loss_usd)],
    ]
    summary_table = Table(summary_rows, colWidths=[2.8 * inch, 2.2 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.2 * inch))

    if mcp_summary is not None:
        story.append(Paragraph("Mathematics MCP verification", heading_style))
        mcp_rows = [
            ["Metric", "Value", "Source"],
            ["MCP connected", "Yes" if mcp_summary.mcp_available else "No", mcp_summary.mcp_url],
            ["Occupancy %", f"{mcp_summary.occupancy_pct:.2f}" if mcp_summary.occupancy_pct is not None else "N/A", mcp_summary.occupancy_source],
            ["Verified total loss", _money(mcp_summary.verified_total_loss_usd or 0), mcp_summary.verified_total_loss_source],
            ["Avg tariff", f"${mcp_summary.avg_tariff:.2f}" if mcp_summary.avg_tariff is not None else "N/A", mcp_summary.avg_tariff_source],
            ["Tariff stdev", f"{mcp_summary.tariff_stdev:.2f}" if mcp_summary.tariff_stdev is not None else "N/A", mcp_summary.tariff_stdev_source],
        ]
        mcp_table = Table(mcp_rows, colWidths=[2.0 * inch, 2.0 * inch, 2.5 * inch])
        mcp_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(mcp_table)
        story.append(Spacer(1, 0.15 * inch))

    chart_width = 3.6 * inch
    nights_fig = _pie_chart(
        ["Occupied", "Vacant"],
        [report.total_room_nights, report.total_vacant_nights],
        "Occupied vs vacant nights",
    )
    loss_labels, loss_values = [], []
    if report.total_availability_loss_usd > 0:
        loss_labels.append("Availability")
        loss_values.append(report.total_availability_loss_usd)
    if report.total_pricing_loss_usd > 0:
        loss_labels.append("Pricing")
        loss_values.append(report.total_pricing_loss_usd)
    loss_fig = _pie_chart(loss_labels, loss_values, "Total loss breakdown (USD)")

    type_summary = report.room_type_summary.copy()
    type_summary["room_type_short"] = type_summary["room_type"].map(_shorten_room_type)
    occupied_fig = _pie_chart(
        type_summary["room_type_short"].tolist(),
        type_summary["occupied_nights"].tolist(),
        "Occupied nights by room type",
    )

    chart_row = Table(
        [[_chart_image(nights_fig, chart_width), _chart_image(loss_fig, chart_width), _chart_image(occupied_fig, chart_width)]],
        colWidths=[chart_width] * 3,
    )
    story.append(chart_row)
    story.append(PageBreak())

    story.append(Paragraph("Room type summary", heading_style))
    type_cols = [
        "room_type",
        "rooms",
        "occupied_nights",
        "vacant_nights",
        "occupancy_pct",
        "avg_tariff",
        "breakeven_per_night",
        "availability_loss_usd",
        "pricing_loss_usd",
        "total_loss_usd",
    ]
    story.append(_dataframe_table(type_summary, type_cols))
    story.append(Spacer(1, 0.15 * inch))

    avail_loss_fig = _bar_chart(
        type_summary["room_type_short"].tolist(),
        type_summary["availability_loss_usd"].tolist(),
        "Availability loss by room type (USD)",
        "USD",
    )
    occupancy_fig = _bar_chart(
        type_summary["room_type_short"].tolist(),
        type_summary["occupancy_pct"].tolist(),
        "Occupancy % by room type",
        "%",
    )
    story.append(
        Table(
            [[_chart_image(avail_loss_fig, 5.2 * inch), _chart_image(occupancy_fig, 5.2 * inch)]],
            colWidths=[5.2 * inch, 5.2 * inch],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Room availability (all rooms)", heading_style))
    room_cols = [
        "room_type",
        "room",
        "occupied_nights",
        "vacant_nights",
        "occupancy_pct",
        "breakeven_per_night",
        "availability_loss_usd",
        "pricing_loss_usd",
        "total_loss_usd",
    ]
    story.append(_dataframe_table(report.room_availability, room_cols))

    top_rooms = report.room_availability.nlargest(12, "availability_loss_usd")
    if not top_rooms.empty:
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("Top rooms by availability loss", heading_style))
        top_room_fig = _bar_chart(
            top_rooms["room"].tolist(),
            top_rooms["availability_loss_usd"].tolist(),
            "Top rooms — availability loss (USD)",
            "USD",
        )
        story.append(_chart_image(top_room_fig, 7.5 * inch))

    story.append(PageBreak())
    story.append(Paragraph("Daily pricing", heading_style))

    daily = report.daily_pricing.copy()
    if daily.empty:
        story.append(Paragraph("No occupied nights in this period.", body_style))
    else:
        daily_cols = [
            "date",
            "room_type",
            "occupied_nights",
            "avg_tariff",
            "breakeven_per_night",
            "pricing_loss_usd",
            "revenue_actual",
        ]
        story.append(_dataframe_table(daily, daily_cols, max_rows=40))

        daily["date"] = pd.to_datetime(daily["date"])
        daily["room_type_short"] = daily["room_type"].map(_shorten_room_type)
        daily_total = daily.groupby("date", as_index=False).agg(
            occupied_nights=("occupied_nights", "sum"),
            pricing_loss_usd=("pricing_loss_usd", "sum"),
        )
        date_labels = daily_total["date"].dt.strftime("%d %b").tolist()
        occupied_line = _line_chart(
            date_labels,
            {"Occupied nights": daily_total["occupied_nights"].tolist()},
            "Daily occupied nights",
            "Nights",
        )
        loss_line = _line_chart(
            date_labels,
            {"Pricing loss": daily_total["pricing_loss_usd"].tolist()},
            "Daily pricing loss (USD)",
            "USD",
        )
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Table(
                [[_chart_image(occupied_line, 5.2 * inch), _chart_image(loss_line, 5.2 * inch)]],
                colWidths=[5.2 * inch, 5.2 * inch],
            )
        )

        tariff_pivot = daily.pivot_table(
            index=daily["date"].dt.strftime("%d %b"),
            columns="room_type_short",
            values="avg_tariff",
            aggfunc="mean",
        ).sort_index()
        tariff_series = {
            str(column): tariff_pivot[column].fillna(0).tolist() for column in tariff_pivot.columns
        }
        tariff_line = _line_chart(
            tariff_pivot.index.tolist(),
            tariff_series,
            "Daily average tariff by room type",
            "USD / night",
        )
        story.append(_chart_image(tariff_line, 7.5 * inch))

    doc.build(story)
    return buffer.getvalue()
