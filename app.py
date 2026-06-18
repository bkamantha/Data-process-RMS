"""Interactive dashboard for hotel reservation analysis."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis.data_loader import load_merged_reservations
from analysis.metrics import build_report
from analysis.periods import Period, reference_end_date

DEFAULT_OUT = Path("data/Checked_Out.csv")
DEFAULT_IN = Path("data/Checked_In.csv")

st.set_page_config(page_title="RMS Reservation Analysis", layout="wide")
st.title("Hotel Reservation Analysis")
st.caption("Checked Out + Checked In CSVs merged on Res No (guest names excluded)")


@st.cache_data
def load_data(checked_out: str, checked_in: str) -> pd.DataFrame:
    return load_merged_reservations(checked_out, checked_in)


with st.sidebar:
    st.header("Inputs")
    checked_out_path = st.text_input("Checked Out CSV", value=str(DEFAULT_OUT))
    checked_in_path = st.text_input("Checked In CSV", value=str(DEFAULT_IN))

    if not Path(checked_out_path).exists() or not Path(checked_in_path).exists():
        st.error("One or both CSV paths do not exist.")
        st.stop()

    frame = load_data(checked_out_path, checked_in_path)
    ref_end = reference_end_date(frame)
    st.metric("Reservations loaded", len(frame))
    st.metric("With tariff data", int(frame["has_tariff"].sum()))

    st.header("Time drill-down")
    period = st.radio(
        "Period",
        options=list(Period),
        format_func=lambda p: p.label,
        index=0,
    )
    end_date = st.date_input("Window end date", value=ref_end.date())

report = build_report(frame, period, end_date=end_date)

st.subheader(report.window.label)
col1, col2, col3 = st.columns(3)
col1.metric("Reservations", report.total_reservations)
col2.metric("Room nights", report.total_room_nights)
col3.metric(
    "Avg tariff (where available)",
    f"${report.reservations['tariff'].mean():.2f}"
    if report.reservations["tariff"].notna().any()
    else "N/A",
)

tab_category, tab_room, tab_detail = st.tabs(["Category usage", "Room type usage", "Reservation detail"])

with tab_category:
    left, right = st.columns([1, 1])
    with left:
        st.dataframe(report.category_usage, use_container_width=True, hide_index=True)
    with right:
        fig = px.bar(
            report.category_usage,
            x="category",
            y="reservations",
            color="avg_tariff",
            title="Reservations by category (color = avg tariff)",
            labels={"reservations": "Reservations", "avg_tariff": "Avg tariff"},
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
            y="reservations",
            color="category",
            title="Top room types by reservations",
        )
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

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
