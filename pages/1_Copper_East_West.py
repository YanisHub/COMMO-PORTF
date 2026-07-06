"""
Page 1 — Copper East-West Arb Monitor.

Physical-copper-desk logic: SHFE-LME import arb, Yangshan premium
lead-lag vs SHFE destocking, and a scrap-discount tightness cross-check.
See README.md for the full formula reference and every economic
assumption.

REVISION 2026-07-04 — `CNMDRCCL`, `CECNWQMM`, and `COPRUSPM` were dropped
after a terminal check found them broken/stale (see config.DROPPED_TICKERS
and README.md). S3 is rebuilt around the S2 import margin instead of an
implied-import-price series; `SHFCCOPO` (on-warrant stocks) was added.
`CU1` is the SHFE 1st future (already USD/t) — NOT COMEX/USD-per-lb.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from utils import data as udata
from utils import finance as ufin

st.set_page_config(page_title="Copper East-West Arb", layout="wide")

ALL_TICKERS = [
    "LMCADY", "LMCADS03", "CU1", "SHFCCOPD", "SHFCCOPO", "COMXCOPR",
    "CECN0002", "CECN0001", "CECNVGFA", "CECNVXAQ", "CNIVCORE", "CBB1SPOT",
    "BHSI",  # optional freight-regime badge (page 5 back-integration), unused in any calc here
]


# ---------------------------------------------------------------------------
# small local helpers (presentation-only, kept out of utils/ on purpose)
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
st.sidebar.header("Copper East-West — parameters")

st.sidebar.subheader("SHFE price source")
price_source_label = st.sidebar.selectbox(
    "SHFE refined Cu price series",
    options=["CECNVXAQ (primary — grade 1 99.95% spot)", "CECNVGFA (alt — grade 1 incl. SXEW)"],
    index=0,
    help="Both are CNY/t spot series for refined copper in Shanghai, converted to USD/t "
         "via USDCNY. CECNVXAQ is the primary source; CECNVGFA is offered as a cross-check.",
)
price_source = "CECNVXAQ" if price_source_label.startswith("CECNVXAQ") else "CECNVGFA"

if st.sidebar.button("🔄 Refresh USDCNY from Yahoo Finance", help="Force-refetch the cached FX series (data/csv/USDCNY.csv)."):
    warn = udata.ensure_usdcny_csv(force=True)
    udata.get_dataset.clear()
    udata.load_all_raw.clear()
    if warn:
        st.sidebar.warning(warn)
    else:
        st.sidebar.success("USDCNY refetched from Yahoo Finance.")

st.sidebar.subheader("Import economics")
vat_rebate = st.sidebar.slider(
    "China VAT rate (import side)", min_value=0.0, max_value=0.30, value=0.13, step=0.01,
    format="%.2f",
    help="China levies 13% VAT on refined copper. SHFE domestic quotes "
         "(`CECNVXAQ`/`CECNVGFA`) are **VAT-inclusive** — an importer selling into "
         "SHFE nets `SHFE_price / (1+VAT)`, not the gross quote itself. This is an "
         "IMPORT VAT treatment, not an export-VAT-rebate — the two are often "
         "conflated in trade commentary. Treat this slider as an approximation "
         "of the net VAT drag on the import economics, not a precise customs "
         "computation.",
)
freight = st.sidebar.slider(
    "Freight, one leg (USD/t)", min_value=0, max_value=150, value=40, step=5,
    help="Indicative flat freight assumption, used for both the import leg "
         "(origin → China, S2) and the export leg (China → destination, S2b). "
         "Real freight varies by route, contract, and bunker costs and isn't "
         "actually symmetric — this is a simplification.",
)
financing_rate = st.sidebar.slider(
    "Financing rate, flat annualized", min_value=0.0, max_value=0.15, value=0.05, step=0.005,
    format="%.3f",
    help="LIBOR/SOFR-proxy flat annualized rate used for the financing leg. "
         "No real rate series is used — indicative only.",
)
financing_days = st.sidebar.slider(
    "Financing days", min_value=0, max_value=90, value=30, step=5,
    help="Days of carry assumed between purchase and sale, ACT/360 day count.",
)

st.sidebar.subheader("Export economics (S2b)")
st.sidebar.caption(
    f"Export VAT rebate is no longer a slider — China eliminated the export VAT "
    f"rebate for refined copper on **{config.EXPORT_VAT_REBATE_CUTOFF}**. The model "
    "uses 100% rebate before that date and 0% from that date on (see vertical line "
    "on the S2b charts)."
)
export_duty = st.sidebar.slider(
    "Export duty", min_value=0.0, max_value=0.20, value=0.0, step=0.01,
    format="%.2f",
    help="Placeholder for any export tariff on refined Cu cathode. No such duty is "
         "currently known/levied — default 0%, exposed for generality.",
)

st.sidebar.subheader("Lead-lag engine")
max_lag = st.sidebar.slider(
    "Max lag for CCF (weeks)", min_value=4, max_value=12, value=8, step=1,
    help="Cross-correlation is computed from lag 0 to this many weeks.",
)
include_on_warrant = st.sidebar.checkbox(
    "Include SHFCCOPO (on-warrant) in lead-lag", value=True,
    help="On-warrant stocks are a tighter measure of readily-deliverable availability "
         "than total deliverable stocks (SHFCCOPD).",
)

st.sidebar.subheader("Date range")
default_years = 3


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
raw, converted, warnings = udata.get_dataset(tuple(ALL_TICKERS))

# ---------------------------------------------------------------------------
# S1 — Header + arb regime summary
# ---------------------------------------------------------------------------
st.title("Copper East-West Arb")
st.caption(
    "SHFE-LME import arb, Yangshan premium lead-lag, and scrap-discount tightness"
)

st.info(
    "`USDCNY` is fetched from **Yahoo Finance** (`CNY=X`)"
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


# --- S2 core calc, needed by S1 KPI row, S3, S4, S5 -----------------------
shfe_usd = converted.get(price_source)
lme_cash = converted.get("LMCADY")
yangshan = converted.get("CECN0002")

df2 = pd.DataFrame()
import_arb = None
if require(converted, [price_source, "LMCADY", "CECN0002"], "S1/S2 (import margin)"):
    df2 = pd.concat(
        {"shfe_usd": shfe_usd, "lme_cash": lme_cash, "yangshan": yangshan}, axis=1, sort=True
    ).ffill().dropna(subset=["lme_cash"])
    df2["ratio"] = df2["shfe_usd"] / df2["lme_cash"]
    financing = ufin.financing_cost(df2["lme_cash"], financing_rate, financing_days)
    df2["breakeven_ratio"] = ufin.breakeven_ratio(df2["lme_cash"], df2["yangshan"], freight, financing, vat_rebate)
    df2["margin"] = ufin.import_margin(df2["shfe_usd"], df2["lme_cash"], df2["yangshan"], freight, financing, vat_rebate)
    df2["arb_open"] = df2["margin"] > 0
    import_arb = df2["margin"].rename("import_arb")  # S3: import arb window = S2 import margin

kpi_cols = st.columns(6)
kpi_cols[0].metric(
    "LME Cu cash",
    f"${lme_cash.dropna().iloc[-1]:,.0f}/t" if lme_cash is not None and not lme_cash.dropna().empty else "n/a",
)
kpi_cols[1].metric(
    f"SHFE cathode USD ({price_source})",
    f"${shfe_usd.dropna().iloc[-1]:,.0f}/t" if shfe_usd is not None and not shfe_usd.dropna().empty else "n/a",
)
if import_arb is not None and not import_arb.dropna().empty:
    latest_margin = import_arb.dropna().iloc[-1]
    kpi_cols[2].metric("Import margin (S2/S3)", f"${latest_margin:,.0f}/t")
    regime = ufin.classify_regime(latest_margin)
else:
    kpi_cols[2].metric("Import margin (S2/S3)", "n/a")
    regime = "UNKNOWN"
kpi_cols[3].metric(
    "Yangshan warrant premium",
    f"${yangshan.dropna().iloc[-1]:,.0f}/t" if yangshan is not None and not yangshan.dropna().empty else "n/a",
)
kpi_cols[4].metric("Arb regime", f"{regime}")

# --- optional freight-regime badge (page 5 back-integration) ---------------
# Handysize (BHSI), not Supramax (BSI) — BSI is stale in this dataset (ends
# 2017-03); see config.FREIGHT_DATA_CAVEATS and page 5 for the full writeup.
# Import-only, degrades to "n/a" if BHSI is missing — no calc above depends on it.
freight_badge_df = ufin.freight_regime(converted["BHSI"]) if "BHSI" in converted and not converted["BHSI"].dropna().empty else None
if freight_badge_df is not None and not freight_badge_df["regime"].dropna().empty:
    frow = freight_badge_df.dropna(subset=["regime"]).iloc[-1]
    kpi_cols[5].metric(
        "Freight regime (Handysize, ctx)", ufin.freight_regime_badge(frow["regime"]),
        f"{frow['pctile']:.0f}th pctile", delta_color="off",
        help="Baltic Handysize (BHSI) freight regime — context only, not used in the import-margin calc above. See page 5 (Freight Overlay) for the full cross-basin picture.",
    )
else:
    kpi_cols[5].metric("Freight regime (Handysize, ctx)", "n/a")

st.divider()

# ---------------------------------------------------------------------------
# S2 — SHFE-LME ratio & import breakeven
# ---------------------------------------------------------------------------
st.header("S2 — SHFE-LME ratio & import breakeven")
st.markdown(
    f"Core physical trade: China imports refined copper when the SHFE price "
    f"(eg source: **{price_source}**) that is quoted **VAT-inclusive**, "
    "so the importer's net take is `SHFE_price / (1+VAT)` and covers LME cash plus "
    "the Yangshan premium, freight, and financing."
)

if not df2.empty:
    df2v = df2.loc[(df2.index >= start_date) & (df2.index <= end_date)].copy()

    ratio_chart_slot = st.empty()

    threshold_pct = st.slider(
        "Threshold margin above breakeven", min_value=0.0, max_value=0.30, value=0.05, step=0.01,
        format="%.2f",
        help="Buffer above pure breakeven the ratio must clear before the S3 backtest "
             "treats the arb as 'open enough' to trade — absorbs transaction "
             "costs/slippage the core margin calc doesn't otherwise model. Shaded in "
             "purple below (nested inside the green ARB OPEN region) and used as the S3 "
             "backtest's entry signal.",
    )
    df2v["threshold_ratio"] = ufin.threshold_ratio(df2v["breakeven_ratio"], threshold_pct)
    df2v["above_threshold"] = df2v["ratio"] > df2v["threshold_ratio"]

    fig_ratio = go.Figure()
    fig_ratio.add_trace(go.Scatter(x=df2v.index, y=df2v["ratio"], name="SHFE/LME ratio", line=dict(color="#1f77b4")))
    fig_ratio.add_trace(go.Scatter(x=df2v.index, y=df2v["breakeven_ratio"], name="Breakeven ratio = (1 + (Yangshan prem + Freight + Financing) / LME_CASH) * (1 + VAT)", line=dict(color="#d62728", dash="dash")))
    fig_ratio.add_trace(go.Scatter(x=df2v.index, y=df2v["threshold_ratio"], name=f"Breakeven + {threshold_pct:.0%} threshold", line=dict(color="#9467bd", dash="dot")))
    add_regime_shading(fig_ratio, df2v["arb_open"], color="LightGreen", opacity=0.25)
    add_regime_shading(fig_ratio, df2v["above_threshold"], color="Purple", opacity=0.20)
    fig_ratio.update_layout(
        title=f"SHFE/LME ratio vs import breakeven (green = ARB OPEN, purple = above threshold, source: {price_source})",
        yaxis_title="ratio (dimensionless)", xaxis_title="date",
        hovermode="x unified", legend=dict(orientation="h", y=1.08),
    )
    ratio_chart_slot.plotly_chart(fig_ratio, width='stretch')


    fig_margin = go.Figure()
    fig_margin.add_trace(go.Scatter(x=df2v.index, y=df2v["margin"], name="Import margin", line=dict(color="#2ca02c"), fill="tozeroy"))
    fig_margin.add_hline(y=0, line_dash="dot", line_color="gray")
    add_regime_shading(fig_margin, df2v["above_threshold"], color="Purple", opacity=0.20)
    fig_margin.update_layout(
        title=f"Import margin = SHFE_USD/(1+VAT) − LME_cash − Yangshan − freight − financing (purple = above breakeven+{threshold_pct:.0%})",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_margin, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# S2b — Export arb (mirror trade): buy refined Cu off SHFE domestically,
# ship out, sell into LME. See utils.finance's S2b comment block for the
# VAT-rebate asymmetry (China doesn't rebate export VAT for copper).
# ---------------------------------------------------------------------------
st.header("S2b — Export arb (mirror trade)")
st.markdown(
    " `LME Copper Cash` represents  Grade  A Copper with minimum copper purity of `99.9935%`."
    " `CECNVXAQ` requires a minimum purity of only `99.95%`"
    "-> Export trade requires refinment: therefore, this section is purely informative"
)
st.markdown(
    f"Reverse physical trade: buy refined copper domestically off SHFE, ship it out, "
    f"and sell into LME. China eliminated the export VAT rebate for unwrought/refined "
    f"copper effective `{config.EXPORT_VAT_REBATE_CUTOFF}`."
    "Before that date the VAT embedded in the SHFE purchase price was refunded on export: it's not the case anymore."
)

if not df2.empty:
    df2v = df2v.copy()
    export_vat_rebate = ufin.export_vat_rebate_series(df2v.index)
    export_financing = ufin.financing_cost(df2v["shfe_usd"], financing_rate, financing_days)
    df2v["export_margin"] = ufin.export_margin(
        df2v["shfe_usd"], df2v["lme_cash"], freight, export_financing, vat_rebate, export_vat_rebate, export_duty
    )
    df2v["export_breakeven_ratio"] = ufin.export_breakeven_ratio(
        df2v["lme_cash"], freight, export_financing, vat_rebate, export_vat_rebate, export_duty
    )
    df2v["export_open"] = df2v["ratio"] < df2v["export_breakeven_ratio"]
    vat_cutoff = pd.Timestamp(config.EXPORT_VAT_REBATE_CUTOFF)

    export_kpi_cols = st.columns(2)
    latest_export_margin = df2v["export_margin"].dropna()
    if not latest_export_margin.empty:
        export_regime = ufin.classify_regime(
            latest_export_margin.iloc[-1], open_label="EXPORT OPEN", closed_label="EXPORT CLOSED"
        )
        export_kpi_cols[0].metric("Export margin (S2b)", f"${latest_export_margin.iloc[-1]:,.0f}/t")
        export_kpi_cols[1].metric("Export regime", f"{export_regime}")

    fig_ratio_x = go.Figure()
    fig_ratio_x.add_trace(go.Scatter(x=df2v.index, y=df2v["ratio"], name="SHFE/LME ratio", line=dict(color="#1f77b4")))
    fig_ratio_x.add_trace(go.Scatter(x=df2v.index, y=df2v["export_breakeven_ratio"], name="Export breakeven ratio", line=dict(color="#ff7f0e", dash="dash")))
    add_regime_shading(fig_ratio_x, df2v["export_open"], color="Orange", opacity=0.2)
    fig_ratio_x.add_vline(x=vat_cutoff.timestamp() * 1000, line_dash="dash", line_color="black",
                           annotation_text="export VAT rebate eliminated", annotation_position="top")
    fig_ratio_x.update_layout(
        title=f"SHFE/LME ratio vs export breakeven (shaded = EXPORT OPEN, source: {price_source})",
        yaxis_title="ratio (dimensionless)", xaxis_title="date",
        hovermode="x unified", legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_ratio_x, width='stretch')

    fig_export_margin = go.Figure()
    fig_export_margin.add_trace(go.Scatter(x=df2v.index, y=df2v["export_margin"], name="Export margin", line=dict(color="#ff7f0e"), fill="tozeroy"))
    fig_export_margin.add_hline(y=0, line_dash="dot", line_color="gray")
    fig_export_margin.add_vline(x=vat_cutoff.timestamp() * 1000, line_dash="dash", line_color="black",
                                 annotation_text="export VAT rebate eliminated", annotation_position="top")
    fig_export_margin.update_layout(
        title="Export margin = LME_cash·(1−duty) − freight − financing − SHFE_domestic_cost(VAT-adj.)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_export_margin, width='stretch')

    st.caption(
        "Import and export arb are mutually "
        "exclusive: with a symmetric freight/financing assumption, the ratio can't be "
        "simultaneously above the import breakeven and below the export breakeven. Can be both simultaneously" \
        "CLOSED if the ratio is sitting in the no-arb band. "
    )

st.divider()

# ---------------------------------------------------------------------------
# S3 — Threshold backtest (rebuilt: no CNMDRCCL, reuses S2 ratio/breakeven/threshold)
# ---------------------------------------------------------------------------
st.header("S3 — Threshold backtest")
st.markdown(
    "Backtests the S2 entry signal, `SHFE/LME ratio` above `breakeven + threshold`,"
    "rolling ladder of import-arb positions, capped at a max number "
    "concurrently open, each held for a fixed number of days. Two P&L variants: "
    "`fully hedged` (SHFE sale leg locked in via futures at entry -> margin fixed the "
    "moment the position opens) and `unhedged` (SHFE leg left open, only actually sold "
    "at the exit date -> exposed to spot moves during the hold period)."
)

if not df2.empty and "above_threshold" in df2v.columns:
    bt_cols = st.columns(2)
    hold_days = bt_cols[0].slider(
        "Position hold period (days)", min_value=5, max_value=180, value=30, step=5,
        help="Calendar days each position is held once opened. The backtest's financing "
             "cost uses this figure (not the S2 financing-days slider above), since it's "
             "the actual holding period being simulated.",
    )
    max_concurrent = bt_cols[1].slider(
        "Max concurrent positions", min_value=1, max_value=10, value=3, step=1,
        help="Cap on simultaneously open positions. While the threshold signal stays on, "
             "new positions keep opening as slots free up (a rolling ladder), up to this cap.",
    )

    trades = ufin.run_import_backtest(
        df2v, threshold_pct, hold_days, max_concurrent, freight, financing_rate, vat_rebate,
    )

    if trades.empty:
        st.info("No positions triggered in this window at the current threshold/date range.")
    else:
        trades = trades.sort_values("exit_date").reset_index(drop=True)
        trades["cum_hedged"] = trades["hedged_pnl"].cumsum()
        trades["cum_unhedged"] = trades["unhedged_pnl"].cumsum()

        fig_bt = go.Figure()
        fig_bt.add_trace(go.Scatter(
            x=trades["exit_date"], y=trades["cum_hedged"], name="Fully hedged equity (cum. USD/t)",
            line=dict(color="#2ca02c"), mode="lines+markers",
        ))
        fig_bt.add_trace(go.Scatter(
            x=trades["exit_date"], y=trades["cum_unhedged"], name="Unhedged equity (cum. USD/t)",
            line=dict(color="#d62728"), mode="lines+markers",
        ))
        fig_bt.add_hline(y=0, line_dash="dot", line_color="gray")
        fig_bt.update_layout(
            title=(f"Backtest equity curves — entries when ratio > breakeven+{threshold_pct:.0%}, "
                   f"{hold_days}d hold, max {max_concurrent} concurrent"),
            yaxis_title="Cumulative P&L (USD/t, 1 unit/position)", xaxis_title="exit date",
            hovermode="x unified",
        )
        st.plotly_chart(fig_bt, width='stretch')

        stat_cols = st.columns(4)
        stat_cols[0].metric("Closed positions", f"{len(trades)}")
        stat_cols[1].metric("Hedged total P&L", f"${trades['hedged_pnl'].sum():,.0f}/t")
        stat_cols[2].metric("Unhedged total P&L", f"${trades['unhedged_pnl'].sum():,.0f}/t")
        stat_cols[3].metric("Unhedged win rate", f"{(trades['unhedged_pnl'] > 0).mean():.0%}")

        with st.expander(f"Trade log ({len(trades)} positions)"):
            st.dataframe(
                trades[["entry_date", "exit_date", "hedged_pnl", "unhedged_pnl"]],
                width='stretch', hide_index=True,
            )

        st.info(
            "**Caveat**: no transaction costs, slippage, position sizing/notional, or "
            "margin/funding calls are modeled, "
            "Yangshan premium and freight treated as locked at entry in both "
            "variants"
        )
elif import_arb is None:
    st.warning("**S3**: data unavailable — import margin (S2) could not be computed.")

st.divider()

# ---------------------------------------------------------------------------
# S4 — Lead-lag engine
# ---------------------------------------------------------------------------
st.header("S4 — Lead-lag engine")
st.markdown(
    "**Hypothesis**: arb opens → Yangshan premium spikes 2-4 weeks later → SHFE stocks "
    "destock. Tested with a cross-correlation function on weekly-resampled, "
    "differenced (stationary) series."
    " **Results**: Non significant results. As we lack granularity for `Yangshan Premium` and `SHFE stock`, `.ffill()` impacts the calculation of the cross-correl"
)

stock_tickers_needed = ["SHFCCOPD"] + (["SHFCCOPO"] if include_on_warrant else [])
if import_arb is not None and require(converted, ["CECN0002"] + stock_tickers_needed, "S4"):
    arb_w = udata.resample_weekly(import_arb, how="last").diff().dropna()
    prem_w = udata.resample_weekly(converted["CECN0002"], how="last").diff().dropna()

    ccf_prem = ufin.cross_corr(arb_w, prem_w, max_lag=max_lag)
    lag_p, corr_p = ufin.peak_lag(ccf_prem)

    stock_ccfs = {}
    for stk in stock_tickers_needed:
        stock_w = udata.resample_weekly(converted[stk], how="last").diff().dropna()
        ccf = ufin.cross_corr(arb_w, stock_w, max_lag=max_lag)
        stock_ccfs[stk] = (ccf,) + ufin.peak_lag(ccf)

    n_charts = 1 + len(stock_ccfs)
    cols = st.columns(n_charts)

    with cols[0]:
        colors = ["#d62728" if l == lag_p else "#1f77b4" for l in ccf_prem["lag"]]
        fig_ccf1 = go.Figure(go.Bar(x=ccf_prem["lag"], y=ccf_prem["corr"], marker_color=colors))
        fig_ccf1.update_layout(
            title="CCF: Δimport_arb → ΔYangshan premium (CECN0002)",
            xaxis_title="lag (weeks, arb leads)", yaxis_title="correlation",
        )
        st.plotly_chart(fig_ccf1, width='stretch')

    stock_names = {"SHFCCOPD": "SHFE deliverable stocks", "SHFCCOPO": "SHFE on-warrant stocks"}
    for i, (stk, (ccf, lag_s, corr_s)) in enumerate(stock_ccfs.items(), start=1):
        with cols[i]:
            colors = ["#d62728" if l == lag_s else "#1f77b4" for l in ccf["lag"]]
            fig = go.Figure(go.Bar(x=ccf["lag"], y=ccf["corr"], marker_color=colors))
            fig.update_layout(
                title=f"CCF: Δimport_arb → Δ{stock_names[stk]} ({stk})",
                xaxis_title="lag (weeks, arb leads)", yaxis_title="correlation",
            )
            st.plotly_chart(fig, width='stretch')

    summary_rows = [{
        "series": "ΔYangshan premium (CECN0002)",
        "peak lag (weeks)": lag_p,
        "peak correlation": corr_p,
        "expected sign": "positive",
        "n obs at peak": ccf_prem.loc[ccf_prem["lag"] == lag_p, "n_obs"].iloc[0] if lag_p is not None else None,
    }]
    for stk, (ccf, lag_s, corr_s) in stock_ccfs.items():
        summary_rows.append({
            "series": f"Δ{stock_names[stk]} ({stk})",
            "peak lag (weeks)": lag_s,
            "peak correlation": corr_s,
            "expected sign": "negative",
            "n obs at peak": ccf.loc[ccf["lag"] == lag_s, "n_obs"].iloc[0] if lag_s is not None else None,
        })
    st.dataframe(pd.DataFrame(summary_rows), width='stretch', hide_index=True)

    st.info(
        "**Caveat**: In-sample correlation on a limited history, peak-lag estimates are sensitive to the sample window, resampling "
        "choice, and stationarity transform."
    )

st.divider()

# ---------------------------------------------------------------------------
# S5 — Scrap discount (tightness alt-signal, monthly)
# ---------------------------------------------------------------------------
st.header("S5 — Scrap discount (tightness alt-signal, monthly)")
st.markdown(
    "Bare-bright scrap vs LME cathode: `scrap_discount = (LMCADY_usd_t − scrap_usd_t) / LMCADY_usd_t`. "
    "`CBB1SPOT` (scrap) is natively **monthly**, `LMCADY` is "
    "resampled to month-end to align. When refined copper is tight, "
    "scrap gets bid up as a cathode substitute and the discount compresses."
)

if require(converted, ["LMCADY", "CBB1SPOT"], "S5"):
    lme_monthly = udata.resample_monthly(converted["LMCADY"], how="last")
    scrap_monthly = converted["CBB1SPOT"]  # already monthly natively
    discount = ufin.scrap_discount(lme_monthly, scrap_monthly)
    discount_clipped = clip(discount) * 100  # as %

    fig_scrap = go.Figure()
    fig_scrap.add_trace(go.Scatter(x=discount_clipped.index, y=discount_clipped.values, name="Scrap discount (%)", line=dict(color="#ff7f0e")))
    fig_scrap.update_layout(yaxis_title="scrap discount (%)")
    lme_clip = clip(converted.get("LMCADY", pd.Series(dtype=float)))
    if not lme_clip.empty:
        fig_scrap.add_trace(go.Scatter(x=lme_clip.index, y=lme_clip.values, name="LME cash (USD/t)", yaxis="y2", line=dict(color="#7f7f7f", dash="dot")))
        fig_scrap.update_layout(
            yaxis2=dict(title="LME cash (USD/t)", overlaying="y", side="right"),
        )
    fig_scrap.update_layout(
        title="Scrap discount to LME cathode (monthly), vs LME cash (daily)",
        xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_scrap, width='stretch')

    st.caption(
        "Note: bare-bright scrap and LME-grade cathode are imperfect substitutes (grade, "
        "logistics, financing differ) -> directional tightness cross-check, not an "
        "arbitrage that's directly tradeable at these levels."
    )

    if import_arb is not None:
        arb_monthly = udata.resample_monthly(import_arb, how="last").diff().dropna()
        disc_monthly_diff = udata.resample_monthly(discount, how="last").diff().dropna()
        ccf_scrap = ufin.cross_corr(arb_monthly, disc_monthly_diff, max_lag=min(max_lag, 6))
        lag_sc, corr_sc = ufin.peak_lag(ccf_scrap)
        n_obs_peak = ccf_scrap.loc[ccf_scrap["lag"] == lag_sc, "n_obs"].iloc[0] if lag_sc is not None else 0
        if lag_sc is not None:
            st.metric(
                "Peak lead-lag: Δimport_arb (China) → Δscrap_discount (US), monthly",
                f"lag {lag_sc}mo, corr {corr_sc:+.2f} (n={n_obs_peak})",
                help="Positive lag/negative corr would suggest China tightness (arb open) "
                     "precedes US scrap discount compression a few months later.",
            )

st.divider()

# ---------------------------------------------------------------------------
# S6 — Stocks panel
# ---------------------------------------------------------------------------
st.header("S6 — Stocks panel")
st.markdown(
    "SHFE deliverable (`SHFCCOPD`) + on-warrant (`SHFCCOPO`) + COMEX (`COMXCOPR`, converted "
    "from short tons) stocks, with the S2 arb-open and above-threshold shading overlaid to "
    "check whether destocking follows the arb signal."
)

if require(converted, ["SHFCCOPD", "SHFCCOPO", "COMXCOPR"], "S6"):
    shfe_deliv = clip(converted["SHFCCOPD"])
    shfe_warrant = clip(converted["SHFCCOPO"])
    comex_stock = clip(converted["COMXCOPR"])

    fig_stock = go.Figure()
    fig_stock.add_trace(go.Scatter(x=shfe_deliv.index, y=shfe_deliv.values, name="SHFE deliverable (t)", line=dict(color="#1f77b4")))
    fig_stock.add_trace(go.Scatter(x=shfe_warrant.index, y=shfe_warrant.values, name="SHFE on-warrant (t)", line=dict(color="#17becf")))
    fig_stock.add_trace(go.Scatter(x=comex_stock.index, y=comex_stock.values, name="COMEX stocks (t, ex short tons)", yaxis="y2", line=dict(color="#2ca02c")))

    if import_arb is not None:
        arb_open_bool = (clip(import_arb) > 0)
        add_regime_shading(fig_stock, arb_open_bool, color="LightGreen", opacity=0.2)
    if not df2.empty and "above_threshold" in df2v.columns:
        add_regime_shading(fig_stock, df2v["above_threshold"], color="Purple", opacity=0.15)

    fig_stock.update_layout(
        title="SHFE (deliverable + on-warrant) + COMEX copper warehouse stocks (green = import arb open, purple = above threshold, S2/S3)",
        yaxis_title="SHFE stocks (t)",
        yaxis2=dict(title="COMEX stocks (t)", overlaying="y", side="right"),
        xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_stock, width='stretch')

    show_concentrate = st.checkbox("Show CNIVCORE (Cu concentrate imports, demand-pull context)", value=False)
    if show_concentrate and require(converted, ["CNIVCORE"], "S6 (CNIVCORE panel)"):
        conc = clip(converted["CNIVCORE"])
        fig_conc = go.Figure(go.Scatter(x=conc.index, y=conc.values, name="China Cu ore & concentrate imports (t, monthly)", line=dict(color="#e377c2")))
        fig_conc.update_layout(
            title="China copper ore & concentrate imports (monthly, demand-pull context)",
            yaxis_title="t/month", xaxis_title="date", hovermode="x unified",
        )
        st.plotly_chart(fig_conc, width='stretch')

st.divider()
