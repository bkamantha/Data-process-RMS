"""Interactive dashboard for hotel reservation analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis.breakeven import DEFAULT_BREAKEVEN_PATH, load_breakeven, save_breakeven
from analysis.data_loader import load_merged_reservations
from analysis.metrics import build_report, distinct_room_types
from analysis.periods import Period, reference_end_date

DEFAULT_OUT = Path("data/Checked_Out.csv")
DEFAULT_IN = Path("data/Checked_In.csv")

st.set_page_config(page_title="RMS Reservation Analysis", layout="wide")
st.title("Hotel Reservation Analysis")
st.caption("Breakeven-based revenue & availability loss across the selected period")


@st.cache_data
def load_data(checked_out: str, checked_in: str) -> pd.DataFrame:
    return load_merged_reservations(checked_out, checked_in)


@st.cache_data
def load_breakeven_data(path: str) -> pd.DataFrame:
    return load_breakeven(path)


def _shorten_room_type(name: str) -> str:
    return name.replace("SBG - ", "").replace(" Apartment", "").replace(" Suite", "")


with st.sidebar:
    st.header("Inputs")
    checked_out_path = st.text_input("Checked Out CSV", value=str(DEFAULT_OUT))
    checked_in_path = st.text_input("Checked In CSV", value=str(DEFAULT_IN))
    breakeven_path = st.text_input("Room type breakeven CSV", value=str(DEFAULT_BREAKEVEN_PATH))

    if not Path(checked_out_path).exists() or not Path(checked_in_path).exists():
        st.error("One or both CSV paths do not exist.")
        st.stop()

    frame = load_data(checked_out_path, checked_in_path)
    breakeven = load_breakeven_data(breakeven_path)
    ref_end = reference_end_date(frame)
    st.metric("Reservations loaded", len(frame))
    st.metric("Room types", frame["category"].nunique())

    st.header("Time drill-down")
    period = st.radio(
        "Period",
        options=list(Period),
        format_func=lambda p: p.label,
        index=0,
    )
    end_date = st.date_input("Window end date", value=ref_end.date())

report = build_report(frame, period, end_date=end_date, breakeven=breakeven)
type_summary = report.room_type_summary.copy()
type_summary["room_type_short"] = type_summary["room_type"].map(_shorten_room_type)

st.subheader(report.window.label)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Period days", report.period_days)
c2.metric("Occupied nights", report.total_room_nights)
c3.metric("Vacant nights", report.total_vacant_nights)
c4.metric("Availability loss", f"${report.total_availability_loss_usd:,.2f}")
c5.metric("Total loss", f"${report.total_loss_usd:,.2f}")

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
    st.markdown(
        "**Loss due to availability** = vacant nights × breakeven. "
        "**Pricing loss** = nights sold below breakeven rate."
    )
    tc1, tc2 = st.columns(2)
    with tc1:
        fig = px.pie(
            type_summary[type_summary["availability_loss_usd"] > 0],
            values="availability_loss_usd",
            names="room_type_short",
            title="Availability loss by room type (USD)",
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    with tc2:
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

st.download_button(
    "Download availability report CSV",
    data=report.room_availability.to_csv(index=False).encode("utf-8"),
    file_name=f"availability_{period.value}.csv",
    mime="text/csv",
)
