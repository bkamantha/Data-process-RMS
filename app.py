"""Interactive dashboard for hotel reservation analysis."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis.breakeven import DEFAULT_BREAKEVEN_PATH, load_breakeven, save_breakeven
from analysis.data_loader import load_merged_reservations
from analysis.math_mcp import DEFAULT_MATHEMATICS_MCP_URL, MathematicsMCPClient
from analysis.mcp_metrics import enrich_report_with_mcp
from analysis.metrics import build_report, distinct_room_types
from analysis.periods import (
    DateRangeMode,
    DateWindow,
    Period,
    make_date_window,
    month_bounds,
    reference_end_date,
    reference_start_date,
    resolve_preset_window,
)

DEFAULT_OUT = Path("data/Checked_Out.csv")
DEFAULT_IN = Path("data/Checked_In.csv")

st.set_page_config(page_title="RMS Reservation Analysis", layout="wide")
st.title("Hotel Reservation Analysis")
st.caption("Breakeven-based revenue & availability loss across the selected period")


@st.cache_data
def load_data_from_paths(checked_out: str, checked_in: str) -> pd.DataFrame:
    return load_merged_reservations(checked_out, checked_in)


@st.cache_data
def load_data_from_uploads(checked_out_bytes: bytes, checked_in_bytes: bytes) -> pd.DataFrame:
    return load_merged_reservations(BytesIO(checked_out_bytes), BytesIO(checked_in_bytes))


@st.cache_data
def load_breakeven_data(path: str) -> pd.DataFrame:
    return load_breakeven(path)


@st.cache_data
def load_breakeven_from_upload(content: bytes) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(content))
    type_col = "room_type" if "room_type" in frame.columns else "category"
    frame = frame.rename(columns={type_col: "room_type"})
    frame["breakeven_per_night"] = pd.to_numeric(frame["breakeven_per_night"], errors="coerce")
    return frame.dropna(subset=["room_type", "breakeven_per_night"])[["room_type", "breakeven_per_night"]]


def _shorten_room_type(name: str) -> str:
    return name.replace("SBG - ", "").replace(" Apartment", "").replace(" Suite", "")


def _parse_date_range(selection) -> tuple[date, date] | None:
    if isinstance(selection, tuple) and len(selection) == 2:
        return selection[0], selection[1]
    if isinstance(selection, date):
        return selection, selection
    return None


with st.sidebar:
    st.header("Data files")
    file_source = st.radio(
        "Input source",
        options=["Default files", "Upload CSV", "Enter file path"],
        index=0,
    )

    checked_out_path = str(DEFAULT_OUT)
    checked_in_path = str(DEFAULT_IN)
    breakeven_path = str(DEFAULT_BREAKEVEN_PATH)
    uploaded_out = uploaded_in = uploaded_breakeven = None

    if file_source == "Upload CSV":
        uploaded_out = st.file_uploader("Checked Out CSV", type=["csv"])
        uploaded_in = st.file_uploader("Checked In CSV", type=["csv"])
        uploaded_breakeven = st.file_uploader(
            "Room type breakeven CSV (optional)",
            type=["csv"],
            help="Uses data/room_type_breakeven.csv if not uploaded",
        )
        if not uploaded_out or not uploaded_in:
            st.info("Upload both Checked Out and Checked In CSV files to continue.")
            st.stop()
    elif file_source == "Enter file path":
        checked_out_path = st.text_input("Checked Out CSV path", value=str(DEFAULT_OUT))
        checked_in_path = st.text_input("Checked In CSV path", value=str(DEFAULT_IN))
        breakeven_path = st.text_input("Breakeven CSV path", value=str(DEFAULT_BREAKEVEN_PATH))
        if not Path(checked_out_path).exists() or not Path(checked_in_path).exists():
            st.error("One or more file paths do not exist.")
            st.stop()
    else:
        checked_out_path = str(DEFAULT_OUT)
        checked_in_path = str(DEFAULT_IN)
        breakeven_path = str(DEFAULT_BREAKEVEN_PATH)
        if not Path(checked_out_path).exists() or not Path(checked_in_path).exists():
            st.error("Default CSV files not found in data/. Use upload or enter a path.")
            st.stop()

    if file_source == "Upload CSV":
        frame = load_data_from_uploads(uploaded_out.getvalue(), uploaded_in.getvalue())
        if uploaded_breakeven:
            breakeven = load_breakeven_from_upload(uploaded_breakeven.getvalue())
        else:
            breakeven = load_breakeven_data(breakeven_path) if Path(breakeven_path).exists() else pd.DataFrame(
                columns=["room_type", "breakeven_per_night"]
            )
    else:
        frame = load_data_from_paths(checked_out_path, checked_in_path)
        breakeven = load_breakeven_data(breakeven_path) if Path(breakeven_path).exists() else load_breakeven(breakeven_path)

    data_min = reference_start_date(frame).date()
    data_max = reference_end_date(frame).date()
    st.metric("Reservations loaded", len(frame))
    st.metric("Room types", frame["category"].nunique())
    st.caption(f"Data dates: {data_min.strftime('%d %b %Y')} – {data_max.strftime('%d %b %Y')}")

    st.header("Date range")
    range_mode = st.radio(
        "Selection mode",
        options=list(DateRangeMode),
        format_func=lambda m: {
            DateRangeMode.PRESET: "Preset (6m / 1m / 1w)",
            DateRangeMode.WEEK: "Pick a week (calendar)",
            DateRangeMode.MONTH: "Pick a month (calendar)",
            DateRangeMode.CUSTOM: "Custom range (calendar)",
        }[m],
        index=0,
    )

    analysis_window: DateWindow | None = None

    if range_mode == DateRangeMode.PRESET:
        period = st.radio(
            "Preset period",
            options=[Period.SIX_MONTHS, Period.ONE_MONTH, Period.ONE_WEEK],
            format_func=lambda p: p.label,
            index=0,
        )
        end_date = st.date_input(
            "Window end date",
            value=data_max,
            min_value=data_min,
            max_value=data_max,
        )
        analysis_window = resolve_preset_window(frame, period, end_date=end_date)

    elif range_mode == DateRangeMode.WEEK:
        st.caption("Click start and end on the calendar to define a week (or any 7-day span).")
        week_selection = st.date_input(
            "Select week",
            value=(data_max, data_max),
            min_value=data_min,
            max_value=data_max,
            selection_mode="range",
        )
        parsed = _parse_date_range(week_selection)
        if parsed is None:
            st.warning("Select a start and end date on the calendar.")
            st.stop()
        week_start, week_end = parsed
        analysis_window = make_date_window(week_start, week_end, range_mode=DateRangeMode.WEEK)

    elif range_mode == DateRangeMode.MONTH:
        st.caption("Pick any date in the month — the full calendar month is used.")
        month_anchor = st.date_input(
            "Select month",
            value=data_max.replace(day=1),
            min_value=data_min,
            max_value=data_max,
        )
        month_start, month_end = month_bounds(month_anchor.year, month_anchor.month)
        clamped_start = max(month_start.date(), data_min)
        clamped_end = min(month_end.date(), data_max)
        analysis_window = make_date_window(clamped_start, clamped_end, range_mode=DateRangeMode.MONTH)

    else:
        st.caption("Click two dates on the calendar for your custom range.")
        custom_selection = st.date_input(
            "Select date range",
            value=(data_min, data_max),
            min_value=data_min,
            max_value=data_max,
            selection_mode="range",
        )
        parsed = _parse_date_range(custom_selection)
        if parsed is None:
            st.warning("Select a start and end date on the calendar.")
            st.stop()
        custom_start, custom_end = parsed
        analysis_window = make_date_window(custom_start, custom_end, range_mode=DateRangeMode.CUSTOM)

    st.header("Mathematics MCP")
    use_mcp = st.checkbox("Use Mathematics MCP for calculations", value=True)
    mcp_url = st.text_input("MCP URL", value=DEFAULT_MATHEMATICS_MCP_URL)

    st.header("Loss metrics")
    include_availability_loss = st.checkbox(
        "Include availability loss (USD)",
        value=False,
        help="Off by default. Uses vacant nights × breakeven. Usually dominates pricing loss and looks ~100% on charts.",
    )

report = build_report(
    frame,
    window=analysis_window,
    breakeven=breakeven,
    include_availability_loss=include_availability_loss,
)
mcp_client = MathematicsMCPClient(url=mcp_url) if use_mcp else None
mcp_summary = enrich_report_with_mcp(report, client=mcp_client, use_mcp=use_mcp)
if mcp_summary.mcp_available:
    st.sidebar.success("Mathematics MCP connected")
else:
    st.sidebar.warning("Mathematics MCP unavailable — using local fallback")
type_summary = report.room_type_summary.copy()
type_summary["room_type_short"] = type_summary["room_type"].map(_shorten_room_type)

st.subheader(report.window.label)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Period days", report.period_days)
c2.metric("Occupied nights", report.total_room_nights)
c3.metric("Occupancy", f"{report.occupancy_pct}%")
c4.metric("Vacant nights", report.total_vacant_nights)
if include_availability_loss:
    c5.metric("Total loss", f"${report.total_loss_usd:,.2f}")
else:
    c5.metric("Pricing loss", f"${report.total_pricing_loss_usd:,.2f}")

if include_availability_loss:
    st.caption(
        f"Availability loss: ${report.total_availability_loss_usd:,.2f} · "
        f"Pricing loss: ${report.total_pricing_loss_usd:,.2f}"
    )

if mcp_summary.occupancy_pct is not None:
    st.caption(
        f"Mathematics MCP ({mcp_url}): occupancy **{mcp_summary.occupancy_pct:.1f}%** "
        f"({mcp_summary.occupancy_source}), "
        f"verified total loss **${mcp_summary.verified_total_loss_usd:,.2f}** "
        f"({mcp_summary.verified_total_loss_source})"
        + (
            f", avg tariff **${mcp_summary.avg_tariff:.2f}** (σ={mcp_summary.tariff_stdev:.2f})"
            if mcp_summary.avg_tariff is not None
            else ""
        )
    )

st.markdown("### Overview")
oc1, oc2, oc3 = st.columns(3)

with oc1:
    nights_pie = pd.DataFrame(
        {
            "status": ["Occupied", "Vacant"],
            "nights": [report.total_room_nights, report.total_vacant_nights],
        }
    )
    fig = px.pie(
        nights_pie,
        values="nights",
        names="status",
        title="Occupied vs vacant nights",
        color="status",
        color_discrete_map={"Occupied": "#2ecc71", "Vacant": "#e74c3c"},
    )
    fig.update_traces(textposition="inside", textinfo="percent+value")
    st.plotly_chart(fig, use_container_width=True)

with oc2:
    if include_availability_loss:
        loss_pie = pd.DataFrame(
            {
                "loss_type": ["Availability loss", "Pricing loss"],
                "amount": [report.total_availability_loss_usd, report.total_pricing_loss_usd],
            }
        )
        loss_pie = loss_pie[loss_pie["amount"] > 0]
        if loss_pie.empty:
            st.info("No loss recorded in this period.")
        else:
            fig = px.pie(
                loss_pie,
                values="amount",
                names="loss_type",
                title="Total loss breakdown (USD)",
                color="loss_type",
                color_discrete_map={"Availability loss": "#e67e22", "Pricing loss": "#9b59b6"},
            )
            fig.update_traces(textposition="inside", textinfo="percent+label+value")
            st.plotly_chart(fig, use_container_width=True)
    else:
        fig = px.pie(
            type_summary[type_summary["pricing_loss_usd"] > 0] if type_summary["pricing_loss_usd"].sum() > 0 else type_summary,
            values="pricing_loss_usd" if type_summary["pricing_loss_usd"].sum() > 0 else "occupied_nights",
            names="room_type_short",
            title="Pricing loss by room type (USD)" if type_summary["pricing_loss_usd"].sum() > 0 else "Occupied nights by room type",
            hole=0.35,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

with oc3:
    occupied_by_type = type_summary[type_summary["occupied_nights"] > 0]
    fig = px.pie(
        occupied_by_type,
        values="occupied_nights",
        names="room_type_short",
        title="Occupied nights by room type",
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

tab_type, tab_avail, tab_daily, tab_breakeven, tab_detail = st.tabs(
    ["Room type summary", "Room availability", "Daily pricing", "Breakeven config", "Reservations"]
)

with tab_type:
    if include_availability_loss:
        st.markdown(
            "**Loss due to availability** = vacant nights × breakeven. "
            "**Pricing loss** = nights sold below breakeven rate."
        )
    else:
        st.markdown(
            "Showing **occupancy** and **pricing loss** (rates below breakeven). "
            "Enable availability loss in the sidebar to include vacant-night USD impact."
        )
    tc1, tc2 = st.columns(2)
    with tc1:
        if include_availability_loss:
            fig = px.pie(
                type_summary[type_summary["availability_loss_usd"] > 0],
                values="availability_loss_usd",
                names="room_type_short",
                title="Availability loss by room type (USD)",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)
        else:
            fig = px.line(
                type_summary.sort_values("room_type"),
                x="room_type_short",
                y="occupancy_pct",
                markers=True,
                title="Occupancy % by room type",
                labels={"room_type_short": "Room type", "occupancy_pct": "Occupancy %"},
            )
            fig.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)
    with tc2:
        if include_availability_loss:
            fig = px.line(
                type_summary.sort_values("room_type"),
                x="room_type_short",
                y="occupancy_pct",
                markers=True,
                title="Occupancy % by room type",
                labels={"room_type_short": "Room type", "occupancy_pct": "Occupancy %"},
            )
            fig.update_layout(xaxis_tickangle=-30)
            fig.add_hline(y=100, line_dash="dot", line_color="gray", annotation_text="100%")
        else:
            fig = px.bar(
                type_summary,
                x="room_type_short",
                y="pricing_loss_usd",
                title="Pricing loss by room type (USD)",
                labels={"pricing_loss_usd": "USD", "room_type_short": "Room type"},
            )
            fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    tc3, tc4 = st.columns(2)
    with tc3:
        rate_melt = type_summary.melt(
            id_vars=["room_type_short"],
            value_vars=["avg_tariff", "breakeven_per_night"],
            var_name="rate_type",
            value_name="rate",
        )
        rate_melt["rate_type"] = rate_melt["rate_type"].map(
            {"avg_tariff": "Avg tariff", "breakeven_per_night": "Breakeven"}
        )
        fig = px.line(
            rate_melt.sort_values("room_type_short"),
            x="room_type_short",
            y="rate",
            color="rate_type",
            markers=True,
            title="Avg tariff vs breakeven by room type",
            labels={"rate": "USD / night", "room_type_short": "Room type"},
        )
        fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)
    with tc4:
        if include_availability_loss:
            loss_melt = type_summary.melt(
                id_vars=["room_type_short"],
                value_vars=["availability_loss_usd", "pricing_loss_usd"],
                var_name="loss_type",
                value_name="amount",
            )
            loss_melt["loss_type"] = loss_melt["loss_type"].map(
                {
                    "availability_loss_usd": "Availability",
                    "pricing_loss_usd": "Pricing",
                }
            )
            fig = px.bar(
                loss_melt,
                x="room_type_short",
                y="amount",
                color="loss_type",
                title="Loss comparison by room type (USD)",
                barmode="stack",
                labels={"room_type_short": "Room type", "amount": "USD"},
                color_discrete_map={"Availability": "#e67e22", "Pricing": "#9b59b6"},
            )
        else:
            fig = px.bar(
                type_summary,
                x="room_type_short",
                y="vacant_nights",
                title="Vacant nights by room type",
                labels={"vacant_nights": "Nights", "room_type_short": "Room type"},
                color_discrete_sequence=["#e74c3c"],
            )
        fig.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(report.room_type_summary, use_container_width=True, hide_index=True)

with tab_avail:
    top_rooms = report.room_availability.nlargest(12, "availability_loss_usd")
    ac1, ac2 = st.columns(2)
    with ac1:
        fig = px.pie(
            top_rooms[top_rooms["availability_loss_usd"] > 0],
            values="availability_loss_usd",
            names="room",
            title="Top rooms — availability loss share (USD)",
            hole=0.3,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    with ac2:
        fig = px.pie(
            top_rooms,
            values="vacant_nights",
            names="room",
            title="Top rooms — vacant nights share",
            hole=0.3,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    ac3, ac4 = st.columns(2)
    with ac3:
        fig = px.line(
            report.room_availability.sort_values("occupancy_pct"),
            x="room",
            y="occupancy_pct",
            color="room_type",
            markers=True,
            title="Occupancy % by room",
            labels={"occupancy_pct": "Occupancy %", "room": "Room"},
        )
        fig.update_layout(xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with ac4:
        nights_melt = report.room_availability.melt(
            id_vars=["room"],
            value_vars=["occupied_nights", "vacant_nights"],
            var_name="night_type",
            value_name="nights",
        )
        nights_melt["night_type"] = nights_melt["night_type"].map(
            {"occupied_nights": "Occupied", "vacant_nights": "Vacant"}
        )
        fig = px.line(
            nights_melt.sort_values("room"),
            x="room",
            y="nights",
            color="night_type",
            markers=True,
            title="Occupied vs vacant nights per room",
            labels={"nights": "Nights", "room": "Room"},
            color_discrete_map={"Occupied": "#2ecc71", "Vacant": "#e74c3c"},
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(report.room_availability, use_container_width=True, hide_index=True)

with tab_daily:
    st.markdown("Use daily tariff vs breakeven to spot dates that need pricing changes.")
    if report.daily_pricing.empty:
        st.info("No occupied nights in this period.")
    else:
        daily = report.daily_pricing.copy()
        daily["date"] = pd.to_datetime(daily["date"])
        daily["room_type_short"] = daily["room_type"].map(_shorten_room_type)

        dc1, dc2 = st.columns(2)
        with dc1:
            rate_daily = daily.melt(
                id_vars=["date", "room_type_short"],
                value_vars=["avg_tariff", "breakeven_per_night"],
                var_name="rate_type",
                value_name="rate",
            )
            rate_daily["rate_type"] = rate_daily["rate_type"].map(
                {"avg_tariff": "Avg tariff", "breakeven_per_night": "Breakeven"}
            )
            fig = px.line(
                rate_daily,
                x="date",
                y="rate",
                color="room_type_short",
                line_dash="rate_type",
                markers=True,
                title="Daily tariff vs breakeven by room type",
                labels={"rate": "USD / night", "date": "Date"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with dc2:
            daily_total = (
                daily.groupby("date", as_index=False)
                .agg(occupied_nights=("occupied_nights", "sum"), pricing_loss_usd=("pricing_loss_usd", "sum"))
            )
            fig = px.line(
                daily_total,
                x="date",
                y="occupied_nights",
                markers=True,
                title="Daily occupied nights (all room types)",
                labels={"occupied_nights": "Nights", "date": "Date"},
            )
            fig.update_traces(line_color="#3498db")
            st.plotly_chart(fig, use_container_width=True)

        dc3, dc4 = st.columns(2)
        with dc3:
            fig = px.line(
                daily_total,
                x="date",
                y="pricing_loss_usd",
                markers=True,
                title="Daily pricing loss below breakeven (USD)",
                labels={"pricing_loss_usd": "Loss (USD)", "date": "Date"},
            )
            fig.update_traces(line_color="#9b59b6")
            st.plotly_chart(fig, use_container_width=True)
        with dc4:
            fig = px.line(
                daily,
                x="date",
                y="occupied_nights",
                color="room_type_short",
                markers=True,
                title="Daily occupied nights by room type",
                labels={"occupied_nights": "Nights", "date": "Date"},
            )
            st.plotly_chart(fig, use_container_width=True)

        dc5, dc6 = st.columns(2)
        with dc5:
            if daily["pricing_loss_usd"].sum() > 0:
                fig = px.pie(
                    daily,
                    values="pricing_loss_usd",
                    names="room_type_short",
                    title="Pricing loss share by room type (USD)",
                    hole=0.35,
                )
            else:
                fig = px.pie(
                    daily,
                    values="occupied_nights",
                    names="room_type_short",
                    title="Occupied nights share by room type",
                    hole=0.35,
                )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)
        with dc6:
            fig = px.pie(
                type_summary[type_summary["vacant_nights"] > 0],
                values="vacant_nights",
                names="room_type_short",
                title="Vacant nights share by room type",
                hole=0.35,
                color_discrete_sequence=px.colors.sequential.Reds_r,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(report.daily_pricing, use_container_width=True, hide_index=True)

with tab_breakeven:
    st.markdown(
        "Set **breakeven per night (USD)** for each room type. "
        "All operating expenses should already be included in this number."
    )
    catalog = distinct_room_types(frame).merge(breakeven, on="room_type", how="left")
    catalog["breakeven_per_night"] = catalog["breakeven_per_night"].fillna(0.0)
    edited = st.data_editor(
        catalog,
        use_container_width=True,
        hide_index=True,
        column_config={
            "room_type": st.column_config.TextColumn("Room type", disabled=True),
            "breakeven_per_night": st.column_config.NumberColumn(
                "Breakeven USD / night",
                min_value=0.0,
                step=5.0,
                format="%.2f",
            ),
        },
        key="breakeven_editor",
    )
    if st.button("Save breakeven rates"):
        saved_path = save_breakeven(edited, breakeven_path)
        load_breakeven_data.clear()
        load_breakeven_from_upload.clear()
        st.success(f"Saved breakeven rates to {saved_path}")
        st.rerun()

with tab_detail:
    display_cols = [
        "res_no",
        "category",
        "room",
        "arrive",
        "depart",
        "period_nights",
        "tariff",
        "breakeven_per_night",
        "revenue_actual",
        "breakeven_revenue",
        "pricing_loss_usd",
        "market_segment",
        "pax",
    ]
    visible = [c for c in display_cols if c in report.reservations.columns]
    st.dataframe(
        report.reservations[visible].sort_values("arrive", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

dl1, dl2 = st.columns(2)
with dl1:
    try:
        from analysis.pdf_report import build_pdf_report

        pdf_bytes = build_pdf_report(report, mcp_summary=mcp_summary)
        st.download_button(
            "Download full report (PDF)",
            data=pdf_bytes,
            file_name=f"report_{report.window.start.strftime('%Y%m%d')}_{report.window.end.strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
        )
    except ModuleNotFoundError:
        st.warning("Install PDF dependencies: `pip install reportlab matplotlib`")
with dl2:
    st.download_button(
        "Download availability report (CSV)",
        data=report.room_availability.to_csv(index=False).encode("utf-8"),
        file_name=f"availability_{report.window.start.strftime('%Y%m%d')}_{report.window.end.strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
