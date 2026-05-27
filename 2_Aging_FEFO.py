"""
pages/2_Aging_FEFO.py
Aging analysis + FEFO compliance view
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.loader import load_shelfwise

st.set_page_config(page_title="Aging & FEFO", page_icon="⏳", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"
TODAY = pd.Timestamp(datetime.today().date())

@st.cache_data(ttl=3600, show_spinner="Loading shelf data...")
def get_shelf():
    files = sorted(DATA_DIR.glob("All_facility_Shelfwise*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return load_shelfwise(files[0])

shelf = get_shelf()

st.title("⏳ Aging & FEFO Analysis")
st.caption("Expiry risk by batch · First-Expired-First-Out compliance")

if shelf is None:
    st.error("No shelf-wise CSV found in data/ folder.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    facilities = ["All"] + sorted(shelf["Facility"].unique().tolist())
    sel_fac = st.selectbox("Facility", facilities)

    inv_types = ["GOOD_INVENTORY", "BAD_INVENTORY", "All"]
    sel_inv = st.selectbox("Inventory Type", inv_types, index=0)

    show_expired = st.checkbox("Include already-expired batches", value=False)

# ── Filter ────────────────────────────────────────────────────────────────────
df = shelf[shelf["Expiry"].notna() & (shelf["Quantity"] > 0)].copy()
if sel_fac != "All":
    df = df[df["Facility"] == sel_fac]
if sel_inv != "All":
    df = df[df["Inventory_Type"] == sel_inv]
if not show_expired:
    df = df[df["Expiry"] >= TODAY]

# ── Days to Expiry + Aging Bucket ─────────────────────────────────────────────
df["Days_to_Expiry"] = (df["Expiry"] - TODAY).dt.days

def aging_bucket(d):
    if d < 0:   return "Expired"
    if d <= 30:  return "0–30 days"
    if d <= 60:  return "31–60 days"
    if d <= 90:  return "61–90 days"
    return "90+ days"

df["Aging_Bucket"] = df["Days_to_Expiry"].apply(aging_bucket)

BUCKET_ORDER  = ["Expired", "0–30 days", "31–60 days", "61–90 days", "90+ days"]
BUCKET_COLORS = {
    "Expired":    "#E24B4A",
    "0–30 days":  "#EF9F27",
    "31–60 days": "#FAC775",
    "61–90 days": "#9FE1CB",
    "90+ days":   "#1D9E75",
}

# ── KPIs ──────────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
bucket_totals = df.groupby("Aging_Bucket")["Quantity"].sum()

k1.metric("Expired (still in stock)",     f'{bucket_totals.get("Expired",    0):,}')
k2.metric("Expiring in 0–30 days",        f'{bucket_totals.get("0–30 days",  0):,}')
k3.metric("Expiring in 31–60 days",       f'{bucket_totals.get("31–60 days", 0):,}')
k4.metric("Expiring in 61–90 days",       f'{bucket_totals.get("61–90 days", 0):,}')
k5.metric("Safe stock (>90 days)",        f'{bucket_totals.get("90+ days",   0):,}')

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📊 Aging Analysis", "🧊 FEFO Compliance"])

with tab1:
    c1, c2 = st.columns([1, 2])

    with c1:
        agg = (
            df.groupby("Aging_Bucket")["Quantity"]
            .sum().reindex(BUCKET_ORDER).reset_index()
        )
        agg.columns = ["Bucket", "Quantity"]
        fig_pie = px.bar(
            agg, x="Bucket", y="Quantity",
            color="Bucket", color_discrete_map=BUCKET_COLORS,
            labels={"Quantity": "Units", "Bucket": ""},
            title="Units by Aging Bucket",
        )
        fig_pie.update_layout(showlegend=False, height=300, margin=dict(t=40,b=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        top_risk = (
            df[df["Aging_Bucket"].isin(["0–30 days", "Expired"])]
            .groupby(["SKU", "Product_Name", "Facility", "Aging_Bucket"])["Quantity"]
            .sum().reset_index()
            .nlargest(15, "Quantity")
        )
        if top_risk.empty:
            st.info("No at-risk stock found for current filters.")
        else:
            top_risk["Short_Name"] = top_risk["Product_Name"].str[:40]
            fig_risk = px.bar(
                top_risk, x="Quantity", y="Short_Name", orientation="h",
                color="Aging_Bucket", color_discrete_map=BUCKET_COLORS,
                facet_col=None,
                title="Top 15 At-Risk SKUs (Expired + 0–30 days)",
                labels={"Quantity": "Units", "Short_Name": ""},
            )
            fig_risk.update_layout(height=380, margin=dict(t=40, b=10, r=20))
            st.plotly_chart(fig_risk, use_container_width=True)

    # Detailed aging table
    st.subheader("Batch-level Aging Detail")
    aging_detail = (
        df[df["Aging_Bucket"].isin(["Expired", "0–30 days", "31–60 days"])]
        .sort_values("Days_to_Expiry")
        [["Facility","SKU","Product_Name","Batch_Code","Expiry","Days_to_Expiry","Quantity","Aging_Bucket"]]
        .rename(columns={
            "Product_Name":   "Product",
            "Days_to_Expiry": "Days Left",
            "Aging_Bucket":   "Risk Bucket",
        })
    )
    st.dataframe(aging_detail, use_container_width=True, hide_index=True, height=380)

    st.download_button(
        "⬇️ Download aging report",
        data=aging_detail.to_csv(index=False),
        file_name="aging_report.csv",
        mime="text/csv",
    )

with tab2:
    st.subheader("FEFO Compliance — Batch Pick Sequence")
    st.caption(
        "FEFO = First Expired, First Out. "
        "For each SKU + Facility, batches should be picked in ascending expiry order. "
        "This view shows how many unique batches are in stock and flags where older batches exist."
    )

    # Per SKU per facility: list all batches ordered by expiry
    fefo = (
        df[df["Inventory_Type"] == "GOOD_INVENTORY"]
        .groupby(["Facility", "SKU", "Product_Name", "Batch_Code", "Expiry"])["Quantity"]
        .sum().reset_index()
        .sort_values(["Facility", "SKU", "Expiry"])
    )

    # Flag: if there are 2+ batches for same SKU+Facility, rank them
    fefo["Batch_Rank"] = (
        fefo.groupby(["Facility", "SKU"])["Expiry"]
        .rank(method="first").astype(int)
    )
    fefo["Total_Batches"] = fefo.groupby(["Facility", "SKU"])["Batch_Code"].transform("count")

    # Show only SKUs with multiple batches (FEFO risk exists)
    multi_batch = fefo[fefo["Total_Batches"] > 1].copy()
    multi_batch["FEFO_Alert"] = multi_batch["Batch_Rank"] > 1  # older batch still in stock

    if sel_fac != "All":
        multi_batch = multi_batch[multi_batch["Facility"] == sel_fac]

    alert_count = multi_batch["FEFO_Alert"].sum()
    st.metric("SKU-Facility combinations with multiple batches", len(multi_batch["SKU"].unique()))
    st.metric("Batch positions where older stock may be overlooked", int(alert_count))

    st.dataframe(
        multi_batch[[
            "Facility", "SKU", "Product_Name", "Batch_Code",
            "Expiry", "Quantity", "Batch_Rank", "FEFO_Alert",
        ]].rename(columns={
            "Batch_Rank": "Pick Order",
            "FEFO_Alert": "Multiple Batch Alert",
        }),
        use_container_width=True,
        hide_index=True,
        height=400,
    )

    st.download_button(
        "⬇️ Download FEFO report",
        data=multi_batch.to_csv(index=False),
        file_name="fefo_compliance.csv",
        mime="text/csv",
    )
