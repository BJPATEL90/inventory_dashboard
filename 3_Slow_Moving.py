"""
pages/3_Slow_Moving.py
Slow-moving and dead stock analysis
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.loader import load_fg, EXCLUDE_FROM_DRR

st.set_page_config(page_title="Slow Moving", page_icon="🐢", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"

@st.cache_data(ttl=3600)
def get_fg():
    files = sorted(DATA_DIR.glob("FG_INVENTORY_REPORT*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return load_fg(files[0])

fg = get_fg()

st.title("🐢 Slow-Moving & Dead Stock")
st.caption("SKUs with low velocity relative to current stock · Risk of write-off or markdowns")

if fg is None:
    st.error("No FG report CSV in data/ folder.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Thresholds")
    slow_doi_threshold   = st.slider("Slow moving: DOI above (days)", 30, 180, 90)
    dead_stock_threshold = st.slider("Dead stock: zero sales in last N days",
                                      7, 60, 30)
    st.header("Filters")
    brands = ["All"] + sorted(fg["Brand"].dropna().unique().tolist())
    sel_brand = st.selectbox("Brand", brands)

# ── Build SKU summary ─────────────────────────────────────────────────────────
df = fg[~fg["Depot_Code"].isin(EXCLUDE_FROM_DRR)].copy()
if sel_brand != "All":
    df = df[df["Brand"] == sel_brand]

sku = (
    df.groupby(["SKU","Product_Name","Brand","Category"])
    .agg(
        Stock    = ("Stock_on_Hand", "sum"),
        Sales_30d= ("Sales_30d", "sum"),
        Sales_7d = ("Sales_7d",  "sum"),
        Inv_Value= ("Inv_Value",  "sum"),
    )
    .reset_index()
)

sku["DRR_30d"] = sku["Sales_30d"] / 30
sku["DOI"]     = sku.apply(
    lambda r: round(r["Stock"] / r["DRR_30d"], 1) if r["DRR_30d"] > 0 else None,
    axis=1,
)

def classify(row):
    if row["Stock"] == 0:
        return "No Stock"
    if row["Sales_30d"] == 0 and row["Stock"] > 0:
        return "Dead Stock"
    if row["DOI"] is not None and row["DOI"] > slow_doi_threshold:
        return "Slow Moving"
    return "Normal"

sku["Classification"] = sku.apply(classify, axis=1)

# ── KPIs ──────────────────────────────────────────────────────────────────────
dead  = sku[sku["Classification"] == "Dead Stock"]
slow  = sku[sku["Classification"] == "Slow Moving"]
norml = sku[sku["Classification"] == "Normal"]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Dead Stock SKUs",        f'{len(dead)}',  help="Stock > 0, zero sales in 30 days")
k2.metric("Slow-Moving SKUs",       f'{len(slow)}',  help=f"DOI > {slow_doi_threshold} days")
k3.metric("Dead Stock Value (₹)",   f'₹{dead["Inv_Value"].sum():,.0f}')
k4.metric("Slow-Moving Value (₹)",  f'₹{slow["Inv_Value"].sum():,.0f}')

st.divider()

tab_dead, tab_slow, tab_all = st.tabs(["💀 Dead Stock", "🐢 Slow Moving", "📋 All SKUs"])

with tab_dead:
    if dead.empty:
        st.success("No dead stock found!")
    else:
        fig = px.bar(
            dead.nlargest(20, "Stock"),
            x="Stock", y="Product_Name", orientation="h",
            color="Inv_Value",
            color_continuous_scale=["#FAEEDA", "#E24B4A"],
            labels={"Stock": "Units on Hand", "Product_Name": "", "Inv_Value": "Value (₹)"},
            title="Top 20 Dead Stock SKUs by Units",
            hover_data={"Brand": True, "Sales_30d": True},
        )
        fig.update_layout(height=400, yaxis={"categoryorder": "total ascending"}, margin=dict(t=40,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            dead[["SKU","Product_Name","Brand","Stock","Sales_30d","DOI","Inv_Value"]]
            .sort_values("Inv_Value", ascending=False)
            .rename(columns={"Product_Name":"Product","Inv_Value":"Value (₹)"}),
            use_container_width=True, hide_index=True,
        )

with tab_slow:
    if slow.empty:
        st.success(f"No slow-moving stock found above {slow_doi_threshold}-day threshold.")
    else:
        fig2 = px.scatter(
            slow, x="DRR_30d", y="DOI",
            size="Stock", color="Inv_Value",
            color_continuous_scale=["#FAEEDA", "#E24B4A"],
            hover_data={"Product_Name": True, "Brand": True, "Stock": True},
            labels={"DRR_30d": "Daily Run Rate", "DOI": "Days of Inventory", "Inv_Value": "Value (₹)"},
            title="Slow-Moving: Velocity vs DOI (bubble = stock size)",
        )
        fig2.update_layout(height=380, margin=dict(t=40,b=10))
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(
            slow.sort_values("DOI", ascending=False)
            [["SKU","Product_Name","Brand","Stock","DRR_30d","DOI","Inv_Value"]]
            .rename(columns={"Product_Name":"Product","DRR_30d":"DRR","Inv_Value":"Value (₹)"}),
            use_container_width=True, hide_index=True,
        )

with tab_all:
    color_map = {
        "Dead Stock":   "#E24B4A",
        "Slow Moving":  "#EF9F27",
        "Normal":       "#639922",
        "No Stock":     "#888780",
    }
    counts = sku["Classification"].value_counts().reset_index()
    counts.columns = ["Classification", "Count"]
    fig3 = px.bar(counts, x="Classification", y="Count",
                  color="Classification", color_discrete_map=color_map,
                  title="SKU Classification Breakdown")
    fig3.update_layout(showlegend=False, height=280, margin=dict(t=40,b=10))
    st.plotly_chart(fig3, use_container_width=True)

    st.dataframe(
        sku.sort_values("DOI", na_position="last")
        [["SKU","Product_Name","Brand","Stock","DRR_30d","DOI","Classification","Inv_Value"]]
        .rename(columns={"Product_Name":"Product","DRR_30d":"DRR","Inv_Value":"Value (₹)"}),
        use_container_width=True, hide_index=True, height=400,
    )
    st.download_button(
        "⬇️ Download slow-moving report",
        data=sku.to_csv(index=False),
        file_name="slow_moving_report.csv",
        mime="text/csv",
    )
