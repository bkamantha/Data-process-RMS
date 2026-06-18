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

st.subheader(report.window.label)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Period days", report.period_days)
c2.metric("Occupied nights", report.total_room_nights)
c3.metric("Vacant nights", report.total_vacant_nights)
c4.metric("Availability loss", f"${report.total_availability_loss_usd:,.2f}")
c5.metric("Total loss", f"${report.total_loss_usd:,.2f}")

tab_type, tab_avail, tab_daily, tab_breakeven, tab_detail = st.tabs(
    ["Room type summary", "Room availability", "Daily pricing", "Breakeven config", "Reservations"]
)

with tab_type:
    st.markdown(
        "**Loss due to availability** = vacant nights × breakeven. "
        "**Pricing loss** = nights sold below breakeven rate."
    )
    left, right = st.columns([1, 1])
    with left:
        st.dataframe(report.room_type_summary, use_container_width=True, hide_index=True)
    with right:
        fig = px.bar(
            report.room_type_summary,
            x="room_type",
            y="availability_loss_usd",
            color="occupancy_pct",
            title="Availability loss by room type (color = occupancy %)",
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

with tab_avail:
    st.dataframe(report.room_availability, use_container_width=True, hide_index=True)

with tab_daily:
    st.markdown("Use daily tariff vs breakeven to spot dates that need pricing changes.")
    if report.daily_pricing.empty:
        st.info("No occupied nights in this period.")
    else:
        left, right = st.columns([1, 1])
        with left:
            st.dataframe(report.daily_pricing, use_container_width=True, hide_index=True)
        with right:
            fig = px.line(
                report.daily_pricing,
                x="date",
                y="avg_tariff",
                color="room_type",
                markers=True,
                title="Daily average tariff by room type",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Compare avg_tariff to breakeven_per_night in the table to find underpriced dates.")

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
