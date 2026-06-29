"""
Interactive management dashboard — the "after".

Same engine, same numbers as the PDF, but live: pick the reporting month, watch
the KPIs, P&L waterfall, trends and budget variance update. The expander at the
bottom shows the raw human-formatted workbook the pipeline ingests, so the
before/after story is visible inside the app itself.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import report_engine as eng

st.set_page_config(page_title="Management Report", layout="wide", page_icon="📊")
INK, ACCENT = "#1F3864", "#FF4B4B"

RAW = eng.RAW_PATH
if not os.path.exists(RAW):  # self-heal on a fresh deploy
    import data_gen
    data_gen.main()

actuals = eng.load_actuals()
budget = eng.load_budget()
pnl_all = eng.pnl_by_month(actuals)
months = list(pnl_all.index)

# --- Sidebar -------------------------------------------------------------
st.sidebar.title("Reporting period")
sel = st.sidebar.select_slider(
    "As-of month", options=months, value=months[-1], format_func=lambda d: d.strftime("%b/%Y")
)
pnl = pnl_all.loc[:sel]
kpis = eng.compute_kpis(pnl, budget)
by_bu = eng.pnl_by_bu(actuals, sel)

st.sidebar.caption(
    "One engine feeds this dashboard **and** the emailable PDF "
    "(`build_report.py`) — they can never disagree."
)

# --- Header + KPIs -------------------------------------------------------
st.title("📊 Management Report — Meridian Industries S.A.")
st.caption(f"Monthly management P&L · values in BRL '000 · as of **{sel:%B %Y}**")

c = st.columns(4)
c[0].metric("Revenue", f"{kpis.revenue:,.0f}", f"{kpis.rev_mom:+.1%} MoM")
c[1].metric("EBITDA", f"{kpis.ebitda:,.0f}", f"{kpis.ebitda_margin:.1%} margin")
c[2].metric("Gross margin", f"{kpis.gross_margin:.1%}")
c[3].metric("Revenue vs budget (YTD)", f"{kpis.rev_vs_budget:+.1%}",
            help="YTD actual revenue vs the prorated full-year budget.")

st.divider()

# --- Trend + waterfall ---------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Revenue & EBITDA")
    fig = go.Figure()
    fig.add_bar(x=pnl.index, y=pnl["Revenue"], name="Revenue", marker_color=INK, opacity=0.85)
    fig.add_scatter(x=pnl.index, y=pnl["EBITDA"], name="EBITDA",
                    mode="lines+markers", line=dict(color=ACCENT, width=3))
    fig.update_layout(height=330, margin=dict(t=10, b=10), legend=dict(orientation="h"),
                      yaxis_title="BRL '000")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader(f"P&L waterfall — {sel:%b/%Y}")
    row = pnl.loc[sel]
    wf = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "total", "relative", "total"],
        x=["Revenue", "COGS", "Gross Profit", "OpEx", "EBITDA"],
        y=[row["Revenue"], -row["COGS"], 0, -row["OpEx"], 0],
        text=[f"{v:,.0f}" for v in
              [row["Revenue"], -row["COGS"], row["Gross Profit"], -row["OpEx"], row["EBITDA"]]],
        connector=dict(line=dict(color=INK)),
        decreasing=dict(marker=dict(color=ACCENT)),
        increasing=dict(marker=dict(color=INK)),
        totals=dict(marker=dict(color="#137333")),
    ))
    wf.update_layout(height=330, margin=dict(t=10, b=10), yaxis_title="BRL '000")
    st.plotly_chart(wf, use_container_width=True)

st.divider()

# --- Margin + budget + BU ------------------------------------------------
g1, g2, g3 = st.columns(3)

with g1:
    st.subheader("EBITDA margin")
    m = px.area(pnl["EBITDA Margin"], labels={"value": "", "index": ""})
    m.update_traces(line_color=ACCENT, fillcolor="rgba(255,75,75,.12)")
    m.update_layout(height=280, showlegend=False, yaxis_tickformat=".0%",
                    margin=dict(t=10, b=10))
    st.plotly_chart(m, use_container_width=True)

with g2:
    st.subheader("Revenue vs budget (YTD)")
    ytd = pnl[pnl.index.year == sel.year]
    n = len(ytd)
    rev_bud = budget.loc[budget["account"] == eng.REVENUE, "budget"].sum() * n / 12
    bar = go.Figure()
    bar.add_bar(x=["Actual", "Budget (prorated)"],
                y=[ytd["Revenue"].sum(), rev_bud],
                marker_color=[INK, "#B7BECC"])
    bar.update_layout(height=280, margin=dict(t=10, b=10), yaxis_title="BRL '000")
    st.plotly_chart(bar, use_container_width=True)

with g3:
    st.subheader(f"By business unit — {sel:%b/%Y}")
    tree = px.treemap(
        by_bu.reset_index(), path=["business_unit"], values="Revenue",
        color="EBITDA Margin", color_continuous_scale="RdYlGn",
    )
    tree.update_layout(height=280, margin=dict(t=10, b=10), coloraxis_showscale=False)
    st.plotly_chart(tree, use_container_width=True)

st.subheader("Business unit detail")
st.dataframe(
    by_bu.style.format({"Revenue": "{:,.0f}", "EBITDA": "{:,.0f}", "EBITDA Margin": "{:.1%}"}),
    use_container_width=True,
)

# --- The "before": raw ingested workbook ---------------------------------
with st.expander("🗂️ See the raw workbook this is built from (the 'before')"):
    st.caption(
        "The pipeline ingests this manually-maintained sheet — title banners, "
        "stacked business-unit blocks, months pivoted across columns — and "
        "turns it into everything above plus the PDF, on every refresh."
    )
    st.dataframe(pd.read_excel(RAW, sheet_name="P&L", header=3), use_container_width=True)
