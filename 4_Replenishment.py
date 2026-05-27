"""
pages/4_Replenishment.py
Auto-generated replenishment suggestions per SKU
based on Warehouse DOI vs configurable safety threshold
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.loader import load_shelfwise, load_fg, compute_warehouse_doi

st.set_page_config(page_title="Replenishment", page_icon="🔁", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"

@st.cache_data(ttl=3600, show_spinner="Computing replenishment needs...")
def get_data():
    shelf_files = sorted(DATA_DIR.glob("All_facility_Shelfwise*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    fg_files    = sorted(DATA_DIR.glob("FG_INVENTORY_REPORT*.csv"),    key=lambda p: p.stat().st_mtime, reverse=True)
    if not shelf_files or not fg_files:
        return None
    shelf = load_shelfwise(shelf_files[0])
    fg    = load_fg(fg_files[0])
    doi   = compute_warehouse_doi(shelf, fg)
    return doi, fg

result = get_data()

st.title("🔁 Replenishment Suggestions")
st.caption("SKUs where warehouse DOI is below your reorder threshold · Action list for supply chain team")

if result is None:
    st.error("CSV files not found in data/ folder.")
    st.stop()

doi, fg = result

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Replenishment Settings")
    reorder_doi   = st.slider("Reorder when DOI below (days)", 5, 45, 14)
    target_doi    = st.slider("Replenish to target DOI (days)", 14, 90, 30)
    lead_time     = st.slider("Assumed lead time (days)", 1, 30, 7)
    st.header("Filters")
    brands = ["All"] + sorted(doi["Brand"].dropna().unique().tolist())
    sel_brand = st.selectbox("Brand", brands)

# ── Compute suggestions ───────────────────────────────────────────────────────
df = doi.copy()
if sel_brand != "All":
    df = df[df["Brand"] == sel_brand]

# Only SKUs with sales data and below reorder threshold
reorder = df[
    df["Warehouse_DOI"].notna() &
    (df["Warehouse_DOI"] <= reorder_doi) &
    (df["PAN_India_DRR"] > 0)
].copy()

# How many units to order = (target_doi + lead_time - current_doi) * DRR
reorder["Suggested_Order_Qty"] = (
    (target_doi + lead_time - reorder["Warehouse_DOI"]) * reorder["PAN_India_DRR"]
).clip(lower=0).round(0).astype(int)

reorder["Cover_after_Order_DOI"] = (
    (reorder["MH_Stock"] + reorder["Suggested_Order_Qty"]) /
    reorder["PAN_India_DRR"]
).round(1)

reorder["Priority"] = reorder["Warehouse_DOI"].apply(
    lambda d: "🔴 Urgent" if d <= 7 else "🟡 Soon"
)

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1, k2, k3 = st.columns(3)
k1.metric("SKUs needing replenishment", len(reorder))
k2.metric("🔴 Urgent (≤7 days)",        (reorder["Warehouse_DOI"] <= 7).sum())
k3.metric("🟡 Soon (8–14 days)",        (reorder["Warehouse_DOI"].between(8, reorder_doi)).sum())

st.divider()

if reorder.empty:
    st.success(f"✅ All SKUs have more than {reorder_doi} days of warehouse stock. No replenishment needed right now.")
else:
    # ── Chart ─────────────────────────────────────────────────────────────────
    top = reorder.nsmallest(20, "Warehouse_DOI")
    top["Short_Name"] = top["Product_Name"].str[:42]

    fig = px.bar(
        top, x="Warehouse_DOI", y="Short_Name", orientation="h",
        color="Priority",
        color_discrete_map={"🔴 Urgent": "#E24B4A", "🟡 Soon": "#EF9F27"},
        text="Warehouse_DOI",
        labels={"Warehouse_DOI": "Current Warehouse DOI (days)", "Short_Name": ""},
        title=f"Top 20 SKUs requiring replenishment (reorder < {reorder_doi} days)",
    )
    fig.update_traces(texttemplate="%{text:.1f}d", textposition="outside")
    fig.add_vline(x=reorder_doi, line_dash="dot", line_color="#888780",
                  annotation_text=f"Reorder trigger ({reorder_doi}d)")
    fig.update_layout(
        yaxis={"categoryorder": "total ascending"},
        showlegend=True, height=420,
        margin=dict(t=40, b=10, r=80),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Action table ──────────────────────────────────────────────────────────
    st.subheader("Replenishment Action List")
    st.caption(f"Suggested order = units needed to reach {target_doi} days cover, allowing for {lead_time}-day lead time")

    display = reorder[[
        "Priority", "SKU", "Product_Name", "Brand",
        "MH_Stock", "PAN_India_DRR", "Warehouse_DOI",
        "Suggested_Order_Qty", "Cover_after_Order_DOI",
    ]].sort_values(["Priority", "Warehouse_DOI"]).rename(columns={
        "Product_Name":        "Product",
        "MH_Stock":            "WH Stock Now",
        "PAN_India_DRR":       "PAN DRR",
        "Warehouse_DOI":       "Current DOI",
        "Suggested_Order_Qty": "Order Qty",
        "Cover_after_Order_DOI": "DOI after Order",
    })
    display["PAN DRR"] = display["PAN DRR"].round(1)

    st.dataframe(display, use_container_width=True, hide_index=True, height=440)

    st.download_button(
        "⬇️ Download replenishment list",
        data=display.to_csv(index=False),
        file_name="replenishment_suggestions.csv",
        mime="text/csv",
    )
