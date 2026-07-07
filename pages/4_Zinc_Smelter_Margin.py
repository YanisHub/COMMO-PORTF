"""
Page 4 — Zinc Smelter Margin (conc TC -> China custom-smelter margin cycle).

Smelter P&L here is a treatment-charge (TC) business, not a metal-price bet:
a China custom smelter buys concentrate paying `metal_price - TC`, so its
margin is driven by TC, not by where zinc trades. Glencore sits on BOTH
sides of this same TC — as the largest concentrate trader (earning TC when
it's high) AND as a smelter operator (Asturiana/San Juan de Nieva,
Portovesme, Nordenham, Kazzinc — squeezed when TC is low) — so S5 models
both P&Ls off one TC series to show the vertical-integration story
explicitly. See README.md for every formula and data caveat.

REVISION 2026-07-05 — building this page against the actual CSVs (not just
the brief) turned up the same kind of frequency surprise as every other
page: `Z1CNHCOF`/`Z1CNTCIM`/`LMZSDS03`/`ZNCNMQKY`/`USDRUB`/`USDTRY` are all
verified MONTHLY here, not "daily, gaps" as the brief assumed — and
`Z1CNHCOF` genuinely prints negative TC in 2026-05/06 (real data, not a
parsing artifact). See config.py's REVISION note and `config.ZINC_DATA_CAVEATS`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from utils import data as udata
from utils import finance as ufin

st.set_page_config(page_title="Zinc Smelter Margin", layout="wide")

ALL_TICKERS = [
    "Z1CNHCOF", "Z1CNTCIM", "LMZSDS03", "ZNCNMQKY", "USDRUB", "USDTRY", "DXY",
    "BHSI",  # optional freight-regime badge (page 5 back-integration), unused in any calc here
]


# ---------------------------------------------------------------------------
# small local helpers (presentation-only, kept out of utils/ — same pattern
# as pages 1-3)
# ---------------------------------------------------------------------------
def require(converted: dict, keys: list[str], section: str) -> bool:
    missing = [k for k in keys if k not in converted or converted[k].dropna().empty]
    if missing:
        for m in missing:
            desc = config.TICKERS.get(m, {}).get("desc", m)
            st.warning(f"**{section}**: data unavailable: {m} ({desc}) — section skipped.")
        return False
    return True


def add_regime_shading(fig: go.Figure, condition: pd.Series, color: str = "LightGreen", opacity: float = 0.25):
    """Shade contiguous True-runs of a boolean series as vrects."""
    cond = condition.dropna()
    if cond.empty:
        return
    in_run = False
    run_start = None
    idx = cond.index
    vals = cond.values
    for i, v in enumerate(vals):
        if v and not in_run:
            in_run = True
            run_start = idx[i]
        elif not v and in_run:
            in_run = False
            fig.add_vrect(x0=run_start, x1=idx[i], fillcolor=color, opacity=opacity, line_width=0)
    if in_run:
        fig.add_vrect(x0=run_start, x1=idx[-1], fillcolor=color, opacity=opacity, line_width=0)


# ---------------------------------------------------------------------------
# Sidebar — global parameters
# ---------------------------------------------------------------------------
st.sidebar.header("Zinc Smelter Margin — parameters")

st.sidebar.subheader("TC benchmark source")
TC_OPTIONS = {
    "Z1CNHCOF — China zinc conc TC 50% CIF (default)": "Z1CNHCOF",
    "Z1CNTCIM — China TC imported zinc conc (cross-check)": "Z1CNTCIM",
}
tc_label = st.sidebar.selectbox(
    "TC series used for the margin calc",
    options=list(TC_OPTIONS),
    index=0,
    help="Both are USD/dmt-of-concentrate China TC benchmarks — the conversion economics "
         "are consistent across them. `Z1CNTCIM` genuinely only starts 2018-11 in this dataset.",
)
tc_choice = TC_OPTIONS[tc_label]

if st.sidebar.button("🔄 Refresh USDCNY from Yahoo Finance", help="Force-refetch the cached FX series (data/csv/USDCNY.csv). Not used by any page-4 calc directly, but shared across pages."):
    warn = udata.ensure_usdcny_csv(force=True)
    udata.get_dataset.clear()
    udata.load_all_raw.clear()
    if warn:
        st.sidebar.warning(warn)
    else:
        st.sidebar.success("USDCNY refetched from Yahoo Finance.")

st.sidebar.subheader("Conc -> metal conversion")
grade = st.sidebar.slider(
    "Concentrate grade (% Zn)", min_value=0.40, max_value=0.60, value=config.ZINC_GRADE_DEFAULT, step=0.005,
    format="%.3f",
    help="Fraction of the concentrate tonne that is contained zinc metal. TC benchmarks are "
         "quoted USD/dmt of CONCENTRATE — this and `recovery` below convert that to USD/t of "
         "payable METAL: `zn_per_dmt_conc = grade * recovery`.",
)
recovery = st.sidebar.slider(
    "Smelter metallurgical recovery (%)", min_value=0.85, max_value=0.99, value=config.ZINC_RECOVERY_DEFAULT, step=0.005,
    format="%.3f",
    help="Fraction of the contained zinc in the concentrate actually recovered as payable metal "
         "at the smelter (roasting/leaching/electrowinning losses). Multiplied by grade to get "
         "`zn_per_dmt_conc` — the single most consequential conversion on this page: getting the "
         "TC-per-concentrate vs TC-per-metal distinction wrong is an instant credibility loss.",
)

st.sidebar.subheader("Free metal / price participation (legacy escalator)")
use_escalator = st.sidebar.checkbox(
    "Enable price-participation escalator", value=False,
    help="Legacy TC contract clause: smelter also receives a cut of any LME zinc price above a "
         "basis price. Modern benchmarks are typically negotiated FLAT (no escalator) — default "
         "OFF reflects that. Turn on to model the older contract style.",
)
basis_price = st.sidebar.slider(
    "Escalator basis price (USD/t LME zinc)", min_value=1500, max_value=4500, value=2800, step=50,
    help="Price-participation clause pays out only on LME zinc above this basis. Only used when "
         "the escalator is enabled above.",
)
participation_pct = st.sidebar.slider(
    "Price participation (%)", min_value=0.0, max_value=0.50, value=0.0, step=0.05,
    format="%.2f",
    help="Fraction of (LME_zinc - basis_price) paid to the smelter as extra free metal. Default "
         "0% = flat/modern TC with no escalator, even if the checkbox above is enabled — raise "
         "this to actually model the legacy mechanics.",
)

st.sidebar.subheader("By-product credit (SENSITIVITY, not data)")
acid_credit = st.sidebar.slider(
    "Sulphuric acid + minor Pb/Ag/Au credit (USD/t zinc)", min_value=-50, max_value=300, value=100, step=10,
    help="No acid-price data series is in this dataset — this is a placeholder SENSITIVITY "
         "assumption, not observed fact, and is labeled as such everywhere it's used (see S7 "
         "for how much this single slider can flip the margin sign).",
)

st.sidebar.subheader("Conversion cost")
conv_cost = st.sidebar.slider(
    "Conversion cost — energy/reagents/labor (USD/t zinc)", min_value=0, max_value=600, value=250, step=10,
    help="Indicative flat smelting cost per tonne of zinc metal produced. No public cost-curve "
         "series is used — this is a slider, not data.",
)

st.sidebar.subheader("Spot vs benchmark proxy (S4)")
bench_proxy_mode = st.sidebar.radio(
    "Benchmark proxy method",
    options=["Step-annual (Jan-held-flat)", "Rolling mean (trailing)"],
    index=0,
    help="There is no separately-negotiated annual-benchmark series in this dataset -> they are PROXIES "
         "built off the same spot series"
)
bench_window = st.sidebar.slider(
    "Rolling window (months)", min_value=3, max_value=24, value=12, step=1,
    help="Only used in 'Rolling mean' mode.",
)

st.sidebar.subheader("Curtailment signal (S6)")
curtailment_n = st.sidebar.slider(
    "Consecutive months underwater to flag curtailment risk",
    min_value=1, max_value=12, value=4, step=1,
    help="Every series feeding the margin calc is verified **monthly** in this dataset (see "
         "the data-caveats expander below) — this counts consecutive MONTHLY observations "
         "with margin < $0/t, not weeks.",
)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
raw, converted, warnings = udata.get_dataset(tuple(ALL_TICKERS))

# ---------------------------------------------------------------------------
# S1 — Header + KPI
# ---------------------------------------------------------------------------
st.title("Zinc Smelter Margin")
st.caption(
    "Zinc conc TC -> China custom-smelter margin cycle, plus the mirror trader/smelter P&L "
    "and a by-product-credit sensitivity check"
)

st.info(
    "**TC is quoted per tonne of CONCENTRATE, not metal.** `TC_per_t_zinc = TC_per_dmt_conc / "
    "(grade x recovery)` converts it. Margin is "
    "**indicative, pre-tax**: acid/by-product credit is an explicit sidebar SENSITIVITY (couldn't find acid-price series)"
    "), the annual benchmark is a spot-derived "
    "PROXY (no separately-negotiated annual series exists either). **China "
    "custom-smelter angle only** -> no EU Nyrstar/Korea Zinc"
)
st.info(
    "**Frequency note**: every zinc series on this page (`Z1CNHCOF`/`Z1CNTCIM`/`LMZSDS03`/"
    "`ZNCNMQKY`/`USDRUB`/`USDTRY`) is verified **monthly**"
)

if warnings:
    with st.expander(f"⚠ {len(warnings)} data warning(s)", expanded=True):
        for w in warnings:
            st.markdown(f"- {w}")

# global date range, bounded by whatever data we actually have
all_dates = [s.dropna().index for s in converted.values() if not s.dropna().empty]
if all_dates:
    data_min = min(idx.min() for idx in all_dates)
    data_max = max(idx.max() for idx in all_dates)
else:
    data_min, data_max = pd.Timestamp("2015-01-01"), pd.Timestamp.today()

default_years = 20
default_start = max(data_min, data_max - pd.DateOffset(years=default_years))
start_date, end_date = st.sidebar.slider(
    "Chart date range",
    min_value=data_min.to_pydatetime(),
    max_value=data_max.to_pydatetime(),
    value=(default_start.to_pydatetime(), data_max.to_pydatetime()),
    format="YYYY-MM-DD",
)
start_date, end_date = pd.Timestamp(start_date), pd.Timestamp(end_date)


def clip(s: pd.Series) -> pd.Series:
    return udata.filter_date_range(s, start_date, end_date)


# --- cross-source TC divergence guard --------------------------------------
# tc_candidates = ["Z1CNHCOF", "Z1CNTCIM"]
# latest_by_source = {}
# for tk in tc_candidates:
#     s = converted.get(tk, pd.Series(dtype=float)).dropna()
#     if not s.empty:
#         latest_by_source[tk] = s.iloc[-1]
# if len(latest_by_source) >= 2:
#     vals = list(latest_by_source.values())
#     denom = min(abs(v) for v in vals)
#     spread = max(vals) - min(vals)
#     if denom > 5 and abs(spread / denom) > 0.5:
#         detail = ", ".join(f"{k}=${v:,.1f}/dmt" for k, v in latest_by_source.items())
#         st.warning(
#             f"**Cross-source TC divergence**: latest prints diverge materially across sources "
#             f"({detail}) — likely panel/methodology differences, not necessarily a real basis "
#             f"move. Selected benchmark: **{tc_choice}**.",
#         )
#     elif denom <= 5:
#         st.caption(
#             f"Note: at least one TC source is near zero ({', '.join(f'{k}=${v:,.1f}/dmt' for k, v in latest_by_source.items())}) "
#             "— relative-spread comparison is unstable at this magnitude, skipped."
#         )

# --- core margin calc, needed by S1 KPI row, S2-S7 --------------------------
margin_df = pd.DataFrame()
if require(converted, [tc_choice, "LMZSDS03"], "S1/S2/S3/S5/S6/S7 (core margin calc)"):
    margin_df = ufin.smelter_margin(
        tc_per_dmt_conc=converted[tc_choice],
        lme_zinc=converted["LMZSDS03"],
        grade=grade,
        recovery=recovery,
        basis_price=basis_price,
        participation_pct=participation_pct,
        use_escalator=use_escalator,
        by_product_credit=acid_credit,
        conv_cost=conv_cost,
    )

kpi_cols = st.columns(6)
tc_latest = converted.get(tc_choice, pd.Series(dtype=float)).dropna()
lme_latest = converted.get("LMZSDS03", pd.Series(dtype=float)).dropna()
kpi_cols[0].metric(
    f"Spot TC ({tc_choice})",
    f"${tc_latest.iloc[-1]:,.1f}/dmt" if not tc_latest.empty else "n/a",
)
if not margin_df.empty:
    latest_row = margin_df.iloc[-1]
    kpi_cols[1].metric("TC per t zinc", f"${latest_row['tc_per_t_zinc']:,.0f}/t")
else:
    kpi_cols[1].metric("TC per t zinc", "n/a")
kpi_cols[2].metric(
    "LME zinc 3M",
    f"${lme_latest.iloc[-1]:,.0f}/t" if not lme_latest.empty else "n/a",
)
if not margin_df.empty:
    kpi_cols[3].metric("Indicative smelter margin", f"${latest_row['margin']:,.0f}/t")
    regime = ufin.classify_regime(
        latest_row["margin"],
        marginal_band=config.ZINC_MARGIN_BREAKEVEN_BAND,
        open_label="HEALTHY",
        closed_label="UNDERWATER",
        marginal_label="BREAKEVEN",
    )
else:
    kpi_cols[3].metric("Indicative smelter margin", "n/a")
    regime = "UNKNOWN"
badge_color = {"HEALTHY": "🟢", "UNDERWATER": "🔴", "BREAKEVEN": "🟡", "UNKNOWN": "⚪"}[regime]
kpi_cols[4].metric("Regime", f"{regime}")

# --- optional freight-regime badge (page 5 back-integration) ---------------
# Handysize (BHSI), not Supramax (BSI) — BSI is stale in this dataset (ends
# 2017-03); see config.FREIGHT_DATA_CAVEATS and page 5 for the full writeup.
# Import-only, degrades to "n/a" if BHSI is missing — no calc above depends on it.
freight_badge_df = ufin.freight_regime(converted["BHSI"]) if "BHSI" in converted and not converted["BHSI"].dropna().empty else None
if freight_badge_df is not None and not freight_badge_df["regime"].dropna().empty:
    frow = freight_badge_df.dropna(subset=["regime"]).iloc[-1]
    kpi_cols[5].metric(
        "Freight regime (Handysize, ctx)",
        f"{frow['pctile']:.0f}th pctile", delta_color="off",
        help="Baltic Handysize (BHSI) freight regime — context only, not used in the smelter-margin calc above. See page 5 (Freight Overlay) for the full cross-basin picture.",
    )
else:
    kpi_cols[5].metric("Freight regime (Handysize, ctx)", "n/a")

st.divider()

# ---------------------------------------------------------------------------
# S2 — TC cycle time series
# ---------------------------------------------------------------------------
st.header("S2 — TC cycle time series")
st.markdown(
    f"Spot TC (**{tc_choice}**, USD/dmt concentrate) with LME zinc 3M overlaid on a right axis. "
    "The 2019-2020 highs (conc glut) into the 2024-26 collapse toward/below zero (extreme conc "
    "tightness -> smelter squeeze) is the whole page-4 thesis in one chart."
)

if not margin_df.empty:
    mdf = margin_df.loc[(margin_df.index >= start_date) & (margin_df.index <= end_date)]

    fig_tc = go.Figure()
    fig_tc.add_trace(go.Scatter(x=mdf.index, y=mdf["tc_per_dmt"], name=f"Spot TC ({tc_choice}, USD/dmt conc)", line=dict(color="#1f77b4")))
    fig_tc.add_hline(y=0, line_dash="dot", line_color="gray")
    fig_tc.add_trace(go.Scatter(x=mdf.index, y=mdf["lme_zinc"], name="LME zinc 3M (USD/t, right axis)", yaxis="y2", line=dict(color="#7f7f7f", dash="dot")))
    fig_tc.add_vrect(
        x0="2019-04-01", x1="2020-03-31", fillcolor="LightGreen", opacity=0.15, line_width=0,
        annotation_text="2019-2020 TC highs (conc glut)", annotation_position="top left",
    )
    fig_tc.add_vrect(
        x0="2023-02-01", x1="2024-12-31", fillcolor="Crimson", opacity=0.12, line_width=0,
        annotation_text="2024 TC collapse (conc tightness)", annotation_position="top left",
    )
    fig_tc.update_layout(
        title=f"Spot TC ({tc_choice}) vs LME zinc 3M",
        yaxis_title="TC (USD/dmt conc)", xaxis_title="date", hovermode="x unified",
        yaxis2=dict(title="LME zinc 3M (USD/t)", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_tc, width='stretch')


st.divider()

# ---------------------------------------------------------------------------
# S3 — Smelter margin reconstruction
# ---------------------------------------------------------------------------
st.header("S3 — Smelter margin reconstruction")
st.markdown(
    "`margin = TC_per_t_zinc + free_metal + by_product_credit - conv_cost`, stacked and shaded "
    "**UNDERWATER** red where negative. A waterfall on a selected snapshot date breaks the "
    "same components down explicitly."
)

if not margin_df.empty:
    fig_stack = go.Figure()
    fig_stack.add_trace(go.Scatter(x=mdf.index, y=mdf["tc_per_t_zinc"], name="TC per t zinc (USD/t)", stackgroup="pos", line=dict(color="#1f77b4")))
    fig_stack.add_trace(go.Scatter(x=mdf.index, y=mdf["free_metal"], name="Free metal / escalator (USD/t)", stackgroup="pos", line=dict(color="#2ca02c")))
    fig_stack.add_trace(go.Scatter(x=mdf.index, y=mdf["by_product_credit"], name="By-product credit — SENSITIVITY (USD/t)", stackgroup="pos", line=dict(color="#9467bd")))
    fig_stack.add_trace(go.Scatter(x=mdf.index, y=-mdf["conv_cost"], name="Conversion cost (USD/t, negative)", stackgroup="neg", line=dict(color="#d62728")))
    fig_stack.add_trace(go.Scatter(x=mdf.index, y=mdf["margin"], name="Net margin (USD/t)", line=dict(color="black", width=2.5)))
    fig_stack.add_hline(y=0, line_dash="dot", line_color="gray")
    add_regime_shading(fig_stack, mdf["margin"] < 0, color="Crimson", opacity=0.15)
    fig_stack.update_layout(
        title="Indicative smelter margin, stacked components (shaded = UNDERWATER)",
        yaxis_title="USD/t zinc", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig_stack, width='stretch')


st.divider()

# ---------------------------------------------------------------------------
# S4 — Spot vs benchmark spread
# ---------------------------------------------------------------------------
st.header("S4 — Spot vs benchmark spread")
st.markdown(
    "Smelters actually run a mix of an annually-negotiated benchmark TC plus opportunistic spot "
    "purchases. This dataset has no separately-negotiated annual series, so the benchmark here "
    "is a **PROXY built off the same spot series** (see sidebar: trailing rolling "
    "mean, or a step-annual 'January-held-flat' approximation). `spot_vs_bench = TC_spot - "
    "TC_bench_proxy`; negative = spot has fallen below the (smoothed) benchmark, signaling acute, "
    "recent tightness the annual contract hasn't caught up to."
)

if require(converted, [tc_choice], "S4"):
    tc_spot = converted[tc_choice].dropna()
    if bench_proxy_mode == "Rolling mean (trailing)":
        tc_bench = ufin.rolling_benchmark_proxy(tc_spot, window=bench_window)
    else:
        tc_bench = ufin.step_annual_benchmark_proxy(tc_spot)

    df4 = pd.concat({"spot": tc_spot, "bench": tc_bench}, axis=1, sort=True).dropna()
    df4["spot_vs_bench"] = df4["spot"] - df4["bench"]
    df4c = df4.loc[(df4.index >= start_date) & (df4.index <= end_date)]

    fig_bench = go.Figure()
    fig_bench.add_trace(go.Scatter(x=df4c.index, y=df4c["spot"], name=f"Spot TC ({tc_choice}, USD/dmt)", line=dict(color="#1f77b4")))
    fig_bench.add_trace(go.Scatter(x=df4c.index, y=df4c["bench"], name="Benchmark PROXY (USD/dmt)", line=dict(color="#ff7f0e", dash="dash")))
    fig_bench.add_hline(y=0, line_dash="dot", line_color="gray")
    fig_bench.update_layout(
        title=f"Spot TC vs benchmark proxy ({bench_proxy_mode})",
        yaxis_title="USD/dmt conc", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_bench, width='stretch')

    fig_spread = go.Figure(go.Scatter(x=df4c.index, y=df4c["spot_vs_bench"], name="spot - bench_proxy (USD/dmt)", line=dict(color="#8c564b"), fill="tozeroy"))
    fig_spread.add_hline(y=0, line_dash="dot", line_color="gray")
    add_regime_shading(fig_spread, df4c["spot_vs_bench"] < 0, color="Crimson", opacity=0.2)
    fig_spread.update_layout(
        title="Spot minus benchmark-proxy TC (shaded = spot below benchmark, acute tightness)",
        yaxis_title="USD/dmt conc", xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_spread, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# S5 — Dual P&L: trader vs smelter
# ---------------------------------------------------------------------------
# st.header("S5 — Dual P&L: Trader vs Smelter (The Integrated Hedge)")
# st.markdown(
#     "Same TC series, opposite books. A concentrate **trader** buys conc from mines at the benchmark and earns "
#     "the spread selling it to smelters -> trader P&L *rises* when spot TC crashes. A **smelter** pays away the "
#     "spot TC -> smelter margin *falls* when TC is low. "
#     "A **fully integrated merchant** (e.g., Glencore) runs both books simultaneously. Because the trader's gains "
#     "perfectly offset the smelter's losses, the Spot TC effectively cancels out, leaving a stable margin dictated by the Benchmark."
# )

# if not mdf.empty:
#     # 1. TRADER: Benchmark minus Spot. (Must convert from USD/dmt to USD/t metal to match smelter!)
#     # Assuming 'yield_factor' is defined earlier as (grade * recovery), e.g., 0.50 * 0.955 = 0.4775
#     yield_factor = grade * recovery 
#     trader_pnl = ((df4["bench"] - mdf["tc_per_dmt"]) / yield_factor).rename("trader_pnl")
    
#     # 2. SMELTER: Standard margin output (already in USD/t metal)
#     smelter_pnl = mdf["margin"].rename("smelter_margin")
    
#     # 3. FULLY INTEGRATED: The sum of both books. 
#     # Notice physically how the spot TC component cancels out in the background.
#     fully_integrated = (trader_pnl + smelter_pnl).rename("fully_integrated")

#     dual = pd.concat([trader_pnl, smelter_pnl, fully_integrated], axis=1).dropna()
    
#     if not dual.empty:
#         base_trader = dual["trader_pnl"].iloc[0]
#         base_smelter = dual["smelter_margin"].iloc[0]
#         base_integrated = dual["fully_integrated"].iloc[0]
        
#         # Safe indexing (handle division by zero)
#         idx_trader = dual["trader_pnl"] - base_trader + 100 if base_trader == 0 else (dual["trader_pnl"] / abs(base_trader)) * 100
#         idx_smelter = dual["smelter_margin"] - base_smelter + 100 if base_smelter == 0 else (dual["smelter_margin"] / abs(base_smelter)) * 100
#         idx_integrated = dual["fully_integrated"] - base_integrated + 100 if base_integrated == 0 else (dual["fully_integrated"] / abs(base_integrated)) * 100

#         fig_dual = go.Figure()
#         fig_dual.add_trace(go.Scatter(x=dual.index, y=idx_trader, name="Trader P&L (Indexed)", line=dict(color="#1f77b4")))
#         fig_dual.add_trace(go.Scatter(x=dual.index, y=idx_smelter, name="Smelter Margin (Indexed)", line=dict(color="#d62728")))
#         fig_dual.add_trace(go.Scatter(x=dual.index, y=idx_integrated, name="Fully Integrated (Indexed)", line=dict(color="#2ca02c", width=3, dash="dot")))
#         fig_dual.add_hline(y=100, line_dash="dot", line_color="gray")
        
#         fig_dual.update_layout(
#             title="The Integrated Hedge: Trader gains offset Smelter losses",
#             yaxis_title="Index (100 = window start)", xaxis_title="Date", hovermode="x unified",
#             legend=dict(orientation="h", y=1.08),
#         )
#         st.plotly_chart(fig_dual, width='stretch')

# st.divider()

# ---------------------------------------------------------------------------
# S5 — Curtailment signal
# ---------------------------------------------------------------------------
st.header("S5 — Curtailment signal")
st.markdown(
    f"`consecutive_below(margin, 0, N={curtailment_n})` -> flags month that is part of a "
    f"run of **{curtailment_n}+ consecutive months** with indicative margin below $0/t. "
    "**Illustrative context only**: European smelters "
    "(e.g. Nyrstar, Glencore's own Nordenham/Portovesme) idled capacity in 2022 on power costs, "
    "and Chinese smelters have both cut runs and taken maintenance outages in 2024 on low/"
    "negative TC."
)

if not margin_df.empty:
    margin_c6 = clip(margin_df["margin"])
    if not margin_c6.empty:
        curtailment_flag = ufin.consecutive_below(margin_c6, 0.0, curtailment_n)

        fig6 = go.Figure(go.Scatter(x=margin_c6.index, y=margin_c6.values, name="Indicative margin (USD/t)", line=dict(color="#1f77b4")))
        fig6.add_hline(y=0, line_dash="dot", line_color="gray")
        add_regime_shading(fig6, curtailment_flag, color="Crimson", opacity=0.3)
        fig6.update_layout(
            title=f"Curtailment-risk regime: margin < $0/t for >= {curtailment_n} consecutive months (shaded)",
            yaxis_title="USD/t zinc", xaxis_title="date", hovermode="x unified",
        )
        st.plotly_chart(fig6, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# S6 — Sensitivity (acid credit)
# ---------------------------------------------------------------------------
st.header("S6 — Sensitivity (acid credit)")
st.markdown(
    "By-product credit (mostly sulphuric acid, plus minor Pb/Ag/Au) is the ** biggest "
    "unmodeled lever** in this China-smelter P&L -> no acid-price -> free parameter here"
    ". Below a 2D "
    "heatmap of indicative margin across a grid of **TC level x acid credit**, holding free "
    "metal and conversion cost at their current sidebar values. The point is to show that the "
    "sign of the margin can flip purely on the acid assumption at a given TC level"
)

if not margin_df.empty and not tc_latest.empty:
    tc_center = float(tc_latest.iloc[-1])
    tc_span = max(80.0, abs(tc_center) * 1.5, margin_df["tc_per_dmt"].std() * 2 if margin_df["tc_per_dmt"].std() == margin_df["tc_per_dmt"].std() else 80.0)
    tc_range = np.linspace(tc_center - tc_span, tc_center + tc_span, 13)
    acid_range = np.linspace(-50, 300, 15)
    free_metal_snapshot = float(margin_df["free_metal"].iloc[-1])

    grid = ufin.zinc_margin_sensitivity_grid(
        tc_per_dmt_range=tc_range,
        acid_credit_range=acid_range,
        grade=grade,
        recovery=recovery,
        free_metal_snapshot=free_metal_snapshot,
        conv_cost=conv_cost,
    )

    fig_heat = px.imshow(
        grid.values,
        x=[f"{v:,.0f}" for v in tc_range],
        y=[f"{v:,.0f}" for v in acid_range],
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        aspect="auto",
        labels=dict(x="TC (USD/dmt conc)", y="Acid/by-product credit (USD/t zinc)", color="Margin (USD/t)"),
    )
    fig_heat.update_layout(
        title=f"Margin sensitivity: TC x acid credit (free metal + conv. cost held at current sidebar values, {tc_choice})",
    )
    st.plotly_chart(fig_heat, width='stretch')

    breakeven_acid_now = conv_cost - free_metal_snapshot - (tc_center / ufin.zinc_per_dmt_conc(grade, recovery))
    st.metric(
        f"Acid credit needed to break even at current TC (${tc_center:,.0f}/dmt)",
        f"${breakeven_acid_now:,.0f}/t zinc",
        help="Solves margin=0 for acid_credit at the latest observed TC, holding free metal and "
             "conv. cost at current sidebar values. If this is above the acid_credit slider's "
             "current setting, the desk needs a richer acid assumption than what's currently "
             "selected just to break even.",
    )

st.divider()

# ---------------------------------------------------------------------------
# S7 — Zinc premium context (optional)
# ---------------------------------------------------------------------------
st.header("S7 — Zinc premium context (optional)")
st.markdown(
    "`ZNCNMQKY` (China zinc premium, B/L Shanghai CIF) vs LME zinc 3M: regional physical-tightness overlay: purely as context on whether Chinese "
    "physical demand is running hot alongside (or independent of) the conc-side TC squeeze."
)

if require(converted, ["ZNCNMQKY"], "S8"):
    premium = clip(converted["ZNCNMQKY"])
    lme_s8 = clip(converted.get("LMZSDS03", pd.Series(dtype=float)))

    fig8 = go.Figure()
    fig8.add_trace(go.Scatter(x=premium.index, y=premium.values, name="China zinc premium, B/L CIF (USD/t)", line=dict(color="#e377c2")))
    if not lme_s8.empty:
        fig8.add_trace(go.Scatter(x=lme_s8.index, y=lme_s8.values, name="LME zinc 3M (USD/t, right axis)", yaxis="y2", line=dict(color="#7f7f7f", dash="dot")))
        fig8.update_layout(yaxis2=dict(title="LME zinc 3M (USD/t)", overlaying="y", side="right"))
    fig8.update_layout(
        title="China zinc physical premium (B/L, CIF Shanghai) vs LME zinc 3M",
        yaxis_title="Premium (USD/t)", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig8, width='stretch')
else:
    st.caption("ZNCNMQKY unavailable — S8 degraded gracefully, rest of the page unaffected.")

st.divider()
