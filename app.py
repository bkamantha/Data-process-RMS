"""Interactive dashboard for hotel reservation analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis.baselines import DEFAULT_BASELINE_PATH, load_baselines, save_baselines
from analysis.data_loader import load_merged_reservations
from analysis.metrics import build_report, distinct_rooms
from analysis.periods import Period, reference_end_date

DEFAULT_OUT = Path("data/Checked_Out.csv")
DEFAULT_IN = Path("data/Checked_In.csv")

st.set_page_config(page_title="RMS Reservation Analysis", layout="wide")
st.title("Hotel Reservation Analysis")
st.caption("Checked Out + Checked In CSVs merged on Res No (guest names excluded)")


@st.cache_data
def load_data(checked_out: str, checked_in: str) -> pd.DataFrame:
    return load_merged_reservations(checked_out, checked_in)


@st.cache_data
def load_baseline_data(path: str) -> pd.DataFrame:
    return load_baselines(path)


with st.sidebar:
    st.header("Inputs")
    checked_out_path = st.text_input("Checked Out CSV", value=str(DEFAULT_OUT))
    checked_in_path = st.text_input("Checked In CSV", value=str(DEFAULT_IN))
    baseline_path = st.text_input("Room baselines CSV", value=str(DEFAULT_BASELINE_PATH))

    if not Path(checked_out_path).exists() or not Path(checked_in_path).exists():
        st.error("One or both CSV paths do not exist.")
        st.stop()

    frame = load_data(checked_out_path, checked_in_path)
    baselines = load_baseline_data(baseline_path)
    ref_end = reference_end_date(frame)
    st.metric("Reservations loaded", len(frame))
    st.metric("With tariff data", int(frame["has_tariff"].sum()))
    st.metric("Rooms with baseline", len(baselines))

    st.header("Time drill-down")
    period = st.radio(
        "Period",
        options=list(Period),
        format_func=lambda p: p.label,
        index=0,
    )
    end_date = st.date_input("Window end date", value=ref_end.date())

report = build_report(frame, period, end_date=end_date, baselines=baselines)

st.subheader(report.window.label)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Reservations", report.total_reservations)
col2.metric("Room nights", report.total_room_nights)
col3.metric(
    "Avg tariff (where available)",
    f"${report.reservations['tariff'].mean():.2f}"
    if report.reservations["tariff"].notna().any()
    else "N/A",
)
col4.metric("Total loss (USD)", f"${report.total_loss_usd:,.2f}")

tab_category, tab_room, tab_baselines, tab_detail = st.tabs(
    ["Category usage", "Room type usage", "Room baselines", "Reservation detail"]
)

with tab_category:
    left, right = st.columns([1, 1])
    with left:
        st.dataframe(report.category_usage, use_container_width=True, hide_index=True)
    with right:
        fig = px.bar(
            report.category_usage,
            x="category",
            y="room_nights",
            color="loss_usd",
            title="Room nights by category (color = loss USD)",
            labels={"room_nights": "Room nights", "loss_usd": "Loss USD"},
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

with tab_room:
    left, right = st.columns([1, 1])
    with left:
        st.dataframe(report.room_type_usage, use_container_width=True, hide_index=True)
    with right:
        top_rooms = report.room_type_usage.head(20)
        fig = px.bar(
            top_rooms,
            x="room",
            y="room_nights",
            color="loss_usd",
            title="Top rooms by nights (color = loss USD)",
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

with tab_baselines:
    st.markdown(
        "Set a **baseline tariff (USD per night)** for each room. "
        "**Loss USD** = `(baseline − actual tariff) × nights` when tariff is below baseline."
    )
    room_catalog = distinct_rooms(frame).merge(baselines, on="room", how="left")
    room_catalog["baseline_tariff"] = room_catalog["baseline_tariff"].fillna(0.0)
    edited = st.data_editor(
        room_catalog[["category", "room", "baseline_tariff"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "category": st.column_config.TextColumn("Category", disabled=True),
            "room": st.column_config.TextColumn("Room", disabled=True),
            "baseline_tariff": st.column_config.NumberColumn(
                "Baseline USD / night",
                min_value=0.0,
                step=5.0,
                format="%.2f",
            ),
        },
        key="baseline_editor",
    )
    if st.button("Save baselines"):
        to_save = edited[["room", "baseline_tariff"]].copy()
        saved_path = save_baselines(to_save, baseline_path)
        load_baseline_data.clear()
        st.success(f"Saved baselines to {saved_path}")
        st.rerun()

with tab_detail:
    display_cols = [
        "res_no",
        "category",
        "room",
        "market_segment",
        "guest_status",
        "arrive",
        "depart",
        "nights",
        "tariff",
        "baseline_tariff",
        "revenue_actual",
        "revenue_baseline",
        "loss_usd",
        "pax",
        "travel_agent",
        "company",
        "main_bill_amount",
        "settlement",
    ]
    visible = [c for c in display_cols if c in report.reservations.columns]
    st.dataframe(
        report.reservations[visible].sort_values("arrive", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

st.download_button(
    "Download period CSV (no guest names)",
    data=report.reservations.to_csv(index=False).encode("utf-8"),
    file_name=f"reservations_{period.value}.csv",
    mime="text/csv",
)
