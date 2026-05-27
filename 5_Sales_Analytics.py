"""
pages/5_Sales_Analytics.py
Facility-wise DRR + DOI from actual sales orders.
Filters to COMPLETE orders only. Excludes SL PM.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.loader import (
    load_sales, load_fg, compute_sales_drr,
    EXCLUDE_FROM_DRR, PACKAGING_FACILITIES,
)

st.set_page_config(page_title="Sales Analytics", page_icon="📈", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"

COLOR_MAP = {
    "Critical":    "#E24B4A",
    "At Risk":     "#EF9F27",
    "Healthy":     "#639922",
    "Overstocked": "#378ADD",
    "No Sales":    "#888780",
}

def doi_status(v):
    if v is None or (isinstance(v, float) and v != v): return "No Sales"
    if v <= 7:  return "Critical"
    if v <= 14: return "At Risk"
    if v <= 30: return "Healthy"
    return "Overstocked"

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📈 Sales Analytics & Facility DOI")
st.caption("Based on actual dispatched orders · COMPLETE status only · SL PM excluded")

# ── Check files ───────────────────────────────────────────────────────────────
sales_files = sorted(DATA_DIR.glob("Sales_Report*.csv"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
fg_files    = sorted(DATA_DIR.glob("FG_INVENTORY_REPORT*.csv"),
                     key=lambda p: p.stat().st_mtime, reverse=True)

has_sales = bool(sales_files)
has_fg    = bool(fg_files)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    window = st.slider("DRR window (days)", 7, 90, 30)
    st.divider()
    if has_sales:
        st.success(f"Sales file: {sales_files[0].name}")
    else:
        st.warning("No Sales_Report CSV found")
    if has_fg:
        st.info(f"FG file: {fg_files[0].name}")

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Loading sales data...")
def get_sales(path):
    return load_sales(path)

@st.cache_data(ttl=3600, show_spinner="Loading FG data...")
def get_fg(path):
    return load_fg(path)

# ── INTERIM view from FG report (always shown, sales overlaid when available) ──
if not has_fg:
    st.error("FG report CSV not found in data/ folder.")
    st.stop()

fg = get_fg(str(fg_files[0]))
fg_b2c = fg[~fg["Depot_Code"].isin(EXCLUDE_FROM_DRR)].copy()

# Brand filter (set after data load)
with st.sidebar:
    brands = ["All"] + sorted(fg_b2c["Brand"].dropna().unique().tolist())
    sel_brand = st.selectbox("Brand", brands)

if sel_brand != "All":
    fg_b2c = fg_b2c[fg_b2c["Brand"] == sel_brand]

# ── KPI row ───────────────────────────────────────────────────────────────────
sales_col = "Sales_30d" if window >= 14 else "Sales_7d"
days      = 30          if window >= 14 else 7

k1, k2, k3, k4 = st.columns(4)
pan_drr = fg_b2c[sales_col].sum() / days
k1.metric("Active B2C facilities",    fg_b2c[fg_b2c[sales_col]>0]["Depot_Code"].nunique())
k2.metric(f"PAN India DRR ({days}d)", f"{pan_drr:.1f} units/day")
k3.metric("Total network stock",      f'{fg_b2c["Stock_on_Hand"].sum():,.0f}')
k4.metric("In-transit stock",         f'{fg_b2c["Stock_In_Transfer"].sum():,.0f}')

st.divider()

# ── If sales file available: full analysis ────────────────────────────────────
if has_sales:
    sales = get_sales(str(sales_files[0]))

    if sel_brand != "All" and "Brand" in sales.columns:
        sales_f = sales[sales["Brand"] == sel_brand]
    else:
        sales_f = sales

    today   = pd.Timestamp("today").normalize()
    cutoff  = today - pd.Timedelta(days=window)
    recent  = sales_f[sales_f["Date"] >= cutoff]

    # Override KPIs with real sales numbers
    real_drr = recent["Units_Sold"].sum() / window
    st.subheader("Sales KPIs — from actual orders")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Units dispatched (last {window}d)", f'{recent["Units_Sold"].sum():,.0f}')
    m2.metric("Real PAN India DRR",                  f"{real_drr:.1f} units/day")
    m3.metric("Revenue",                              f'₹{recent["Revenue"].sum():,.0f}')
    m4.metric("Active dispatch facilities",           recent["Facility"].nunique()
              if "Facility" in recent.columns else "—")

    st.divider()

    # Daily trend
    st.subheader("Daily Dispatch Trend")
    daily = (recent.groupby(recent["Date"].dt.date)["Units_Sold"]
             .sum().reset_index())
    daily.columns = ["Date","Units"]
    daily["DRR_line"] = daily["Units"].rolling(7, min_periods=1).mean()

    fig_t = px.area(daily, x="Date", y="Units",
                    color_discrete_sequence=["#B5D4F4"],
                    labels={"Units":"Units dispatched","Date":""})
    fig_t.add_scatter(x=daily["Date"], y=daily["DRR_line"],
                      mode="lines", name="7-day avg",
                      line=dict(color="#0C447C", width=2))
    fig_t.update_layout(height=240, margin=dict(t=10,b=10), showlegend=True)
    st.plotly_chart(fig_t, use_container_width=True)

    st.divider()

    # Facility DRR from sales
    st.subheader(f"Facility DRR from Sales (last {window} days)")
    fac_drr = compute_sales_drr(sales_f, window_days=window)
    fac_roll = (
        fac_drr.groupby("Facility")
        .agg(DRR=("DRR","sum"), Total_Units=("Total_Units","sum"),
             Revenue=("Revenue","sum"))
        .reset_index()
    )
    # Merge with current stock
    stock_map = fg.groupby("Depot_Name")["Stock_on_Hand"].sum().reset_index()
    stock_map.columns = ["Facility","Stock"]
    fac_roll = fac_roll.merge(stock_map, on="Facility", how="left")
    fac_roll["Stock"] = fac_roll["Stock"].fillna(0)
    fac_roll["DOI"]   = fac_roll.apply(
        lambda r: round(r["Stock"]/r["DRR"],1) if r["DRR"]>0 else None, axis=1)
    fac_roll["Status"] = fac_roll["DOI"].apply(doi_status)

    c1, c2 = st.columns(2)
    with c1:
        top = fac_roll[fac_roll["DRR"]>0].nlargest(15,"DRR")
        fig = px.bar(top, x="DRR", y="Facility", orientation="h",
                     color="Status", color_discrete_map=COLOR_MAP,
                     text="DRR", title="Top 15 Facilities by DRR",
                     labels={"DRR":"Units/day","Facility":""})
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(height=420, showlegend=False,
                          yaxis={"categoryorder":"total ascending"},
                          margin=dict(t=40,b=10,r=60))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        low = fac_roll[fac_roll["DOI"].notna()].nsmallest(15,"DOI")
        fig2 = px.bar(low, x="DOI", y="Facility", orientation="h",
                      color="Status", color_discrete_map=COLOR_MAP,
                      text="DOI", title="15 Facilities — Lowest DOI",
                      labels={"DOI":"Days of Inventory","Facility":""})
        fig2.update_traces(texttemplate="%{text:.1f}d", textposition="outside")
        fig2.update_layout(height=420, showlegend=False,
                           yaxis={"categoryorder":"total ascending"},
                           margin=dict(t=40,b=10,r=60))
        st.plotly_chart(fig2, use_container_width=True)

    # SKU breakdown
    st.divider()
    st.subheader("Top SKUs by Units Dispatched")
    sku_s = (
        recent.groupby(["SKU","Product_Name","Brand"] if "Brand" in recent.columns else ["SKU","Product_Name"])
        .agg(Units=("Units_Sold","sum"), Revenue=("Revenue","sum")).reset_index()
        .sort_values("Units", ascending=False)
    )
    sku_s["DRR"] = (sku_s["Units"] / window).round(2)

    col_a, col_b = st.columns([2,1])
    with col_a:
        top_sku = sku_s.head(20)
        top_sku["Short"] = top_sku["Product_Name"].str[:40]
        fig3 = px.bar(top_sku, x="Units", y="Short", orientation="h",
                      color="Units", color_continuous_scale=["#B5D4F4","#0C447C"],
                      title="Top 20 SKUs by units dispatched",
                      labels={"Units":"Units","Short":""})
        fig3.update_layout(height=500, coloraxis_showscale=False,
                           yaxis={"categoryorder":"total ascending"},
                           margin=dict(t=40,b=10,r=20))
        st.plotly_chart(fig3, use_container_width=True)

    with col_b:
        st.dataframe(sku_s[["SKU","Product_Name","Units","DRR","Revenue"]]
                     .rename(columns={"Product_Name":"Product","Revenue":"Revenue (₹)"})
                     .head(30),
                     use_container_width=True, hide_index=True, height=500)

    st.download_button("⬇️ Download sales analytics",
                       data=fac_roll.to_csv(index=False),
                       file_name="sales_facility_drr_doi.csv", mime="text/csv")

else:
    # ── No sales file: show FG-based facility view ────────────────────────────
    st.info(
        "**Sales Report not connected yet.**  \n"
        "Showing facility DRR from FG report as interim.  \n"
        "Add `Sales_Report_DDMMYYYY.csv` to the `data/` folder to unlock full analytics."
    )
    fac = (
        fg_b2c.groupby(["Depot_Code","Depot_Name"])
        .agg(Stock=("Stock_on_Hand","sum"), Sales=(sales_col,"sum"),
             In_Transit=("Stock_In_Transfer","sum"))
        .reset_index()
    )
    fac["DRR"]    = (fac["Sales"] / days).round(2)
    fac["DOI"]    = fac.apply(lambda r: round(r["Stock"]/r["DRR"],1) if r["DRR"]>0 else None, axis=1)
    fac["Status"] = fac["DOI"].apply(doi_status)

    c1, c2 = st.columns(2)
    with c1:
        top = fac[fac["DRR"]>0].nlargest(15,"DRR")
        fig = px.bar(top, x="DRR", y="Depot_Name", orientation="h",
                     color="Status", color_discrete_map=COLOR_MAP,
                     text="DRR", title=f"Top 15 Facilities by DRR ({days}d)",
                     labels={"DRR":"Units/day","Depot_Name":""})
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(height=420, showlegend=False,
                          yaxis={"categoryorder":"total ascending"},
                          margin=dict(t=40,b=10,r=60))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        low = fac[fac["DOI"].notna()].nsmallest(15,"DOI")
        fig2 = px.bar(low, x="DOI", y="Depot_Name", orientation="h",
                      color="Status", color_discrete_map=COLOR_MAP,
                      text="DOI", title="15 Facilities — Lowest DOI",
                      labels={"DOI":"Days of Inventory","Depot_Name":""})
        fig2.update_traces(texttemplate="%{text:.1f}d", textposition="outside")
        fig2.update_layout(height=420, showlegend=False,
                           yaxis={"categoryorder":"total ascending"},
                           margin=dict(t=40,b=10,r=60))
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(
        fac.sort_values("DOI", na_position="last")
        [["Depot_Name","Stock","DRR","DOI","Status","In_Transit"]]
        .rename(columns={"Depot_Name":"Facility","In_Transit":"In Transit"}),
        use_container_width=True, hide_index=True, height=400,
    )
    st.download_button("⬇️ Download facility DRR (FG-based)",
                       data=fac.to_csv(index=False),
                       file_name="facility_drr_fg.csv", mime="text/csv")
