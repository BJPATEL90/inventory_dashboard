"""
pages/1_Inventory_Health.py
DOI + DRR health per SKU and per facility
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.loader import load_fg, MOTHER_HUB_DEPOT_CODES, EXCLUDE_FROM_DRR

st.set_page_config(page_title="Inventory Health", page_icon="📊", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"

@st.cache_data(ttl=3600, show_spinner="Loading FG data...")
def get_fg():
    files = sorted(DATA_DIR.glob("FG_INVENTORY_REPORT*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return load_fg(files[0])

fg = get_fg()

st.title("📊 Inventory Health")
st.caption("DOI & DRR per facility · PAN India vs facility-level view")

if fg is None:
    st.error("No FG report CSV found in data/ folder.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    brands = ["All"] + sorted(fg["Brand"].dropna().unique().tolist())
    sel_brand = st.selectbox("Brand", brands)
    show_zero = st.checkbox("Hide depots with zero stock & zero sales", value=True)
    drr_window = st.radio("DRR Window", ["30-day DRR", "7-day DRR"], index=0)

drr_col  = "DRR_30d"  if drr_window == "30-day DRR" else "DRR_7d"
doi_col  = "DOI_30d"  if drr_window == "30-day DRR" else "DOI_7d"
sales_col= "Sales_30d" if drr_window == "30-day DRR" else "Sales_7d"

# ── Filter ────────────────────────────────────────────────────────────────────
df = fg[~fg["Depot_Code"].isin(EXCLUDE_FROM_DRR)].copy()
if sel_brand != "All":
    df = df[df["Brand"] == sel_brand]
if show_zero:
    df = df[(df["Stock_on_Hand"] > 0) | (df[sales_col] > 0)]

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total depots",         f'{df["Depot_Code"].nunique():,}')
k2.metric("Total stock on hand",  f'{df["Stock_on_Hand"].sum():,.0f}')
k3.metric(f"PAN India {drr_window}", f'{df[drr_col].sum():.1f} units/day')
k4.metric("Total in-transit",     f'{df["Stock_In_Transfer"].sum():,.0f}')

st.divider()

# ── DOI by Facility ───────────────────────────────────────────────────────────
st.subheader(f"Facility DOI — {drr_window}")

# Compute per-facility DOI: stock / facility's own DRR
fac_health = (
    df.groupby(["Depot_Code", "Depot_Name"])
    .agg(
        Stock=("Stock_on_Hand", "sum"),
        Sales=( sales_col, "sum"),
        In_Transit=("Stock_In_Transfer", "sum"),
    )
    .reset_index()
)
fac_health["DRR"]  = fac_health["Sales"] / (30 if drr_window == "30-day DRR" else 7)
fac_health["DOI"]  = fac_health.apply(
    lambda r: round(r["Stock"] / r["DRR"], 1) if r["DRR"] > 0 else None, axis=1
)

def doi_status(v):
    if v is None: return "No Sales"
    if v <= 7: return "Critical"
    if v <= 14: return "At Risk"
    if v <= 30: return "Healthy"
    return "Overstocked"

color_map = {
    "Critical":    "#E24B4A",
    "At Risk":     "#EF9F27",
    "Healthy":     "#639922",
    "Overstocked": "#378ADD",
    "No Sales":    "#888780",
}
fac_health["Status"] = fac_health["DOI"].apply(doi_status)

top_fac = fac_health[fac_health["DOI"].notna()].nsmallest(20, "DOI")
fig_fac = px.bar(
    top_fac, x="DOI", y="Depot_Name", orientation="h",
    color="Status", color_discrete_map=color_map,
    text="DOI",
    labels={"DOI": "Days of Inventory", "Depot_Name": ""},
    title="20 Facilities with Lowest DOI",
)
fig_fac.update_traces(texttemplate="%{text:.1f}d", textposition="outside")
fig_fac.update_layout(
    yaxis={"categoryorder": "total ascending"},
    showlegend=True, height=440,
    margin=dict(t=40, b=10, r=60),
)
st.plotly_chart(fig_fac, use_container_width=True)

st.divider()

# ── SKU-level DRR table ───────────────────────────────────────────────────────
st.subheader("SKU-level DRR & DOI")

sku_health = (
    df.groupby(["SKU", "Product_Name", "Brand"])
    .agg(
        Total_Stock = ("Stock_on_Hand", "sum"),
        Total_Sales = (sales_col, "sum"),
        Total_Transit=("Stock_In_Transfer","sum"),
        Depots_Active=("Depot_Code","nunique"),
    )
    .reset_index()
)
sku_health["DRR"] = (sku_health["Total_Sales"] / (30 if drr_window=="30-day DRR" else 7)).round(2)
sku_health["DOI"] = sku_health.apply(
    lambda r: round(r["Total_Stock"] / r["DRR"], 1) if r["DRR"] > 0 else None, axis=1
)
sku_health["Status"] = sku_health["DOI"].apply(doi_status)

col_tbl, col_scatter = st.columns([3, 2])

with col_tbl:
    st.dataframe(
        sku_health.sort_values("DOI", na_position="last")
        [["SKU","Product_Name","Brand","Total_Stock","DRR","DOI","Status"]]
        .rename(columns={
            "Product_Name":"Product","Total_Stock":"Stock",
            "Depots_Active":"Active Depots",
        }),
        use_container_width=True, hide_index=True, height=420,
    )

with col_scatter:
    plot_data = sku_health[sku_health["DOI"].notna() & (sku_health["DRR"] > 0)]
    fig_sc = px.scatter(
        plot_data, x="DRR", y="DOI",
        color="Status", color_discrete_map=color_map,
        size="Total_Stock", size_max=30,
        hover_data={"Product_Name": True, "Brand": True},
        labels={"DRR": "Daily Run Rate (units/day)", "DOI": "Days of Inventory"},
        title="Stock vs Velocity",
    )
    fig_sc.add_hline(y=7,  line_dash="dot", line_color="#E24B4A", annotation_text="Critical (7d)")
    fig_sc.add_hline(y=14, line_dash="dot", line_color="#EF9F27", annotation_text="At Risk (14d)")
    fig_sc.add_hline(y=30, line_dash="dot", line_color="#639922", annotation_text="Healthy (30d)")
    fig_sc.update_layout(height=420, margin=dict(t=40, b=10))
    st.plotly_chart(fig_sc, use_container_width=True)

st.download_button(
    "⬇️ Download health report",
    data=sku_health.to_csv(index=False),
    file_name="inventory_health.csv",
    mime="text/csv",
)
