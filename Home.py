"""
Home.py  ─  Master Inventory Dashboard
---------------------------------------
Run with:  streamlit run Home.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from data.loader import (
    load_shelfwise, load_fg,
    compute_warehouse_doi, compute_facility_summary,
    MOTHER_HUB_FACILITIES,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Inventory Command Centre",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading today's inventory data...")
def get_data():
    shelf = load_shelfwise(Path(__file__).parent / "data" /
                           next(Path(__file__).parent.glob("data/All_facility_Shelfwise*.csv")
                                .__class__.__name__ and
                                (Path(__file__).parent / "data").glob("All_facility_Shelfwise*.csv"),
                                None).__str__()
                           if list((Path(__file__).parent / "data").glob("All_facility_Shelfwise*.csv"))
                           else None)
    fg    = load_fg()
    doi   = compute_warehouse_doi(shelf, fg)
    fsum  = compute_facility_summary(shelf)
    return shelf, fg, doi, fsum

# Resolve data file paths
DATA_DIR = Path(__file__).parent / "data"

@st.cache_data(ttl=3600, show_spinner="Loading inventory data...")
def get_all_data():
    shelf_files = sorted(DATA_DIR.glob("All_facility_Shelfwise*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    fg_files    = sorted(DATA_DIR.glob("FG_INVENTORY_REPORT*.csv"),    key=lambda p: p.stat().st_mtime, reverse=True)

    if not shelf_files:
        return None, None, None, None, "No shelf-wise CSV found in data/ folder."
    if not fg_files:
        return None, None, None, None, "No FG report CSV found in data/ folder."

    shelf = load_shelfwise(shelf_files[0])
    fg    = load_fg(fg_files[0])
    doi   = compute_warehouse_doi(shelf, fg)
    fsum  = compute_facility_summary(shelf)
    return shelf, fg, doi, fsum, None

shelf, fg, doi, fsum, error = get_all_data()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📦 Inventory Command Centre")
st.caption("Master view · SL Ambient & SL Mother Hub warehouse DOI vs PAN India demand")

if error:
    st.error(f"⚠️ {error}")
    st.info("Place your CSV files in the `data/` folder and refresh.")
    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    brands = ["All"] + sorted(doi["Brand"].dropna().unique().tolist())
    sel_brand = st.selectbox("Brand", brands)

    doi_status_opts = ["All", "Critical", "At Risk", "Healthy", "Overstocked", "No Sales Data"]
    sel_status = st.selectbox("DOI Status", doi_status_opts)

    min_stock = st.number_input("Min warehouse stock", min_value=0, value=0, step=100)

    st.divider()
    st.caption(f"Shelf file: {sorted(DATA_DIR.glob('All_facility_Shelfwise*.csv'), key=lambda p: p.stat().st_mtime, reverse=True)[0].name}")
    st.caption(f"FG file: {sorted(DATA_DIR.glob('FG_INVENTORY_REPORT*.csv'), key=lambda p: p.stat().st_mtime, reverse=True)[0].name}")

# Apply filters to DOI table
doi_filtered = doi.copy()
if sel_brand != "All":
    doi_filtered = doi_filtered[doi_filtered["Brand"] == sel_brand]
if sel_status != "All":
    doi_filtered = doi_filtered[doi_filtered["DOI_Status"] == sel_status]
doi_filtered = doi_filtered[doi_filtered["MH_Stock"] >= min_stock]

# ── KPI Row ───────────────────────────────────────────────────────────────────
st.subheader("Warehouse Snapshot")
k1, k2, k3, k4, k5 = st.columns(5)

total_skus   = len(doi)
critical     = (doi["DOI_Status"] == "Critical").sum()
at_risk      = (doi["DOI_Status"] == "At Risk").sum()
healthy      = (doi["DOI_Status"] == "Healthy").sum()
overstocked  = (doi["DOI_Status"] == "Overstocked").sum()

k1.metric("Total SKUs in Warehouse", f"{total_skus:,}")
k2.metric("🔴 Critical  (≤7 days)",  f"{critical}",   delta=None)
k3.metric("🟡 At Risk   (8–14 days)", f"{at_risk}",    delta=None)
k4.metric("🟢 Healthy   (15–30 days)",f"{healthy}",    delta=None)
k5.metric("🔵 Overstocked (>30 days)",f"{overstocked}", delta=None)

st.divider()

# ── DOI Donut chart + Bar chart ───────────────────────────────────────────────
col_chart1, col_chart2 = st.columns([1, 2])

with col_chart1:
    st.subheader("DOI Distribution")
    status_counts = doi["DOI_Status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]
    color_map = {
        "Critical":      "#E24B4A",
        "At Risk":       "#EF9F27",
        "Healthy":       "#639922",
        "Overstocked":   "#378ADD",
        "No Sales Data": "#888780",
    }
    fig_donut = px.pie(
        status_counts, names="Status", values="Count",
        color="Status", color_discrete_map=color_map,
        hole=0.55,
    )
    fig_donut.update_traces(textposition="inside", textinfo="percent+label")
    fig_donut.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=280)
    st.plotly_chart(fig_donut, use_container_width=True)

with col_chart2:
    st.subheader("Top 20 SKUs — Warehouse DOI")
    top20 = (
        doi[doi["Warehouse_DOI"].notna()]
        .nsmallest(20, "Warehouse_DOI")
        [["Product_Name", "Warehouse_DOI", "MH_Stock", "PAN_India_DRR", "DOI_Status", "Brand"]]
    )
    top20["Short_Name"] = top20["Product_Name"].str[:45]
    fig_bar = px.bar(
        top20, x="Warehouse_DOI", y="Short_Name", orientation="h",
        color="DOI_Status", color_discrete_map=color_map,
        text="Warehouse_DOI",
        labels={"Warehouse_DOI": "Days of Inventory", "Short_Name": ""},
        hover_data={"MH_Stock": True, "PAN_India_DRR": ":.1f", "Brand": True},
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}d", textposition="outside")
    fig_bar.update_layout(
        yaxis={"categoryorder": "total ascending"},
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=80),
        height=380,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Facility Stock Heatmap ────────────────────────────────────────────────────
st.divider()
st.subheader("Facility-wise Stock Overview")

col_mh, col_all = st.columns([1, 2])

with col_mh:
    st.markdown("**Mother Hubs (Warehouse Stock)**")
    mh_fsum = fsum[fsum["Is_Mother_Hub"]].copy()
    mh_fsum["Utilisation"] = (
        (mh_fsum["Total_Good"] /
         (mh_fsum["Total_Good"] + mh_fsum["Total_Blocked"] + mh_fsum["Total_Damaged"] + 1))
        * 100
    ).round(1)
    st.dataframe(
        mh_fsum[["Facility", "SKU_Count", "Total_Good", "Total_Blocked", "Total_Damaged"]].rename(columns={
            "Total_Good": "Good Qty", "Total_Blocked": "Blocked",
            "Total_Damaged": "Damaged", "SKU_Count": "SKUs"
        }),
        use_container_width=True, hide_index=True,
    )

with col_all:
    st.markdown("**Top 15 Fulfillment Facilities by Stock**")
    top_fac = (
        fsum[~fsum["Is_Mother_Hub"]]
        .nlargest(15, "Total_Good")
        [["Facility", "SKU_Count", "Total_Good", "Total_Blocked", "Total_Damaged"]]
    )
    fig_fac = px.bar(
        top_fac, x="Facility", y="Total_Good",
        color="Total_Good",
        color_continuous_scale=["#B5D4F4", "#0C447C"],
        labels={"Total_Good": "Good Stock", "Facility": ""},
    )
    fig_fac.update_layout(
        showlegend=False, coloraxis_showscale=False,
        margin=dict(t=10, b=10), height=260,
        xaxis_tickangle=-35,
    )
    st.plotly_chart(fig_fac, use_container_width=True)

# ── Main DOI Table ────────────────────────────────────────────────────────────
st.divider()
st.subheader(f"Warehouse DOI Table — {len(doi_filtered)} SKUs")

def _color_status(val):
    colors = {
        "Critical":      "background-color: #FCEBEB; color: #A32D2D",
        "At Risk":       "background-color: #FAEEDA; color: #633806",
        "Healthy":       "background-color: #EAF3DE; color: #3B6D11",
        "Overstocked":   "background-color: #E6F1FB; color: #185FA5",
        "No Sales Data": "background-color: #F1EFE8; color: #5F5E5A",
    }
    return colors.get(val, "")

display_cols = {
    "SKU":               "SKU Code",
    "Product_Name":      "Product",
    "Brand":             "Brand",
    "MH_Stock":          "WH Stock",
    "PAN_India_DRR":     "PAN India DRR",
    "Warehouse_DOI":     "Warehouse DOI",
    "DOI_Status":        "Status",
}
table = doi_filtered[list(display_cols.keys())].rename(columns=display_cols).copy()
table["PAN India DRR"] = table["PAN India DRR"].round(1)
table["Warehouse DOI"] = table["Warehouse DOI"].round(1)

styled = table.style.map(_color_status, subset=["Status"])
st.dataframe(styled, use_container_width=True, hide_index=True, height=450)

# Download button
csv = doi_filtered.to_csv(index=False)
st.download_button(
    "⬇️ Download full DOI report",
    data=csv,
    file_name="warehouse_doi_report.csv",
    mime="text/csv",
)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "DOI = Warehouse Stock (SL Ambient + SL Mother Hub) ÷ PAN India DRR  |  "
    "DRR based on last 30 days sales across all B2C fulfillment depots"
)
