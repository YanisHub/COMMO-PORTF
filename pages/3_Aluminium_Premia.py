"""
Page 3 — Aluminium Premia Fair-Value & Carry.

Regional Al premia (Rotterdam duty-paid, US Midwest) vs a carry-component
fair value driven by LME contango, financing, and warehouse rent, plus the
classic 2009-14 warehouse-queue cash-and-carry trade. See README.md for
every formula and every data caveat found while wiring this page up.

REVISION 2026-07-04 — building this page against the actual CSVs (not just
the brief) turned up a few things worth recording, same spirit as page 1's
CU1 correction: `AMEUDDP`/`USGGT10Y`/`DXY`/`EURUSD` are natively MONTHLY
here (not daily), and `IPAITI*` (IAI production) stops at 2014-12-31 (11+
years stale). See config.py's REVISION note and `ALUMINIUM_DATA_CAVEATS`.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from utils import data as udata
from utils import finance as ufin

st.set_page_config(page_title="Aluminium Premia & Carry", layout="wide")

ALL_TICKERS = [
    "LMAHDY", "LMAHDS03", "AUP1", "AMEUDDP", "USGGT10Y", "DXY", "EURUSD",
    "IPAITITL", "IPAITIEU", "IPAITINA", "IPAITIAS", "IPAITIAF", "IPAITILA", "IPAITIOC",
]
IAI_REGIONAL = {
    "IPAITIEU": "Europe", "IPAITINA": "North America", "IPAITIAS": "Asia",
    "IPAITIAF": "Africa", "IPAITILA": "Latin America", "IPAITIOC": "Oceania",
}


# ---------------------------------------------------------------------------
# small local helpers (presentation-only, kept out of utils/ — same pattern
# as pages/1_Copper_East_West.py)
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
st.sidebar.header("Aluminium Premia — parameters")

st.sidebar.subheader("Financing rate")
fin_rate_mode = st.sidebar.radio(
    "Financing rate source",
    options=["USGGT10Y + spread", "Flat override"],
    index=0,
    help="`USGGT10Y + spread` uses the US 10Y yield (verified MONTHLY in this dataset, "
         "forward-filled onto the daily LME grid) plus a spread as a financing-rate proxy. "
         "`Flat override` ignores USGGT10Y entirely and uses a single flat rate.",
)
fin_spread = st.sidebar.slider(
    "Spread over USGGT10Y", min_value=0.0, max_value=0.05, value=0.015, step=0.0025,
    format="%.4f",
    help="Added to USGGT10Y (converted from % to a decimal rate) to proxy a real-world "
         "financing rate (LIBOR/SOFR + credit spread). Only used in 'USGGT10Y + spread' mode.",
)
flat_rate = st.sidebar.slider(
    "Flat financing rate (override)", min_value=0.0, max_value=0.15, value=0.055, step=0.005,
    format="%.3f",
    help="Used only in 'Flat override' mode — ignores USGGT10Y entirely.",
)

st.sidebar.subheader("Warehouse rent (no public series)")
daily_rent = st.sidebar.slider(
    "Warehouse rent (USD/t/day)", min_value=0.05, max_value=2.0, value=0.45, step=0.05,
    help="Indicative flat warehouse rent — roughly $13/t/month at the default 0.45/day. "
         "There is no public series for LME warehouse rent (a notoriously opaque, "
         "negotiated cost during the 2009-14 warehouse-queue era) — this is a slider, "
         "not data.",
)
carry_days = st.sidebar.slider(
    "Carry horizon (days)", min_value=30, max_value=365, value=90, step=15,
    help="Days of carry assumed for the financing and rent legs, ACT/360 day count "
         "on financing.",
)

st.sidebar.subheader("Lead/context")
show_fx_context = st.sidebar.checkbox(
    "Show DXY/EURUSD macro context (S2)", value=False,
    help="DXY and EURUSD are loaded and verified but not part of the FV/carry formulas — "
         "shown only as optional macro context for why USD-denominated premia might move.",
)
show_iai = st.sidebar.checkbox(
    "Show IAI production context (S6, historical only)", value=False,
    help="IAI production series stop at 2014-12-31 in this dataset (11+ years stale) — "
         "shown over their own native range, not overlaid against current premia.",
)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
raw, converted, warnings = udata.get_dataset(tuple(ALL_TICKERS))

# ---------------------------------------------------------------------------
# S1 — Header + KPI row
# ---------------------------------------------------------------------------
st.title("Aluminium Premia Fair-Value & Carry")
st.caption(
    "Regional Al premia (Rotterdam duty-paid, US Midwest) vs carry-component fair value, "
    "plus the classic warehouse cash-and-carry trade"
)

st.info(
    "**Fair value is carry-component only**: `FV_premium = financing_cost + warehouse_rent "
    "− contango` prices just the cost-to-carry piece. Actual regional premia also embed "
    "duty, freight, regional supply/demand, and (for the US Midwest premium specifically) "
    "Section 232 tariffs — `premium_richness = actual − FV` is where that residual, physical "
    "signal lives. Rotterdam duty-paid is the cleaner carry proxy; the US Midwest premium "
    "(`AUP1`) has tariffs baked directly into the print, so it is shown for context but not "
    "compared to FV directly (see S2/S3).",
    icon="ℹ️",
)
st.info(
    "**Frequency note**: `AMEUDDP` (Rotterdam) and `USGGT10Y` (financing proxy) are verified "
    "**monthly** in this dataset (not daily) — forward-filled onto the daily LME grid "
    "wherever they feed a calc, explicitly, not silently. Indicative and pre-tax throughout.",
    icon="🗓️",
)

if warnings:
    with st.expander(f"⚠ {len(warnings)} data warning(s) — read before trusting the numbers", expanded=True):
        for w in warnings:
            st.markdown(f"- {w}")

with st.expander("Data caveats found while wiring up this page (see config.py REVISION note)"):
    for tk, note in config.ALUMINIUM_DATA_CAVEATS.items():
        st.markdown(f"- **{tk}**: {note}")

all_dates = [s.dropna().index for s in converted.values() if not s.dropna().empty]
if all_dates:
    data_min = min(idx.min() for idx in all_dates)
    data_max = max(idx.max() for idx in all_dates)
else:
    data_min, data_max = pd.Timestamp("2015-01-01"), pd.Timestamp.today()

default_years = 3
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


# --- core calc, needed by S1 KPI row, S3, S4, S5 --------------------------
core_tickers = ["LMAHDY", "LMAHDS03", "AUP1", "AMEUDDP", "USGGT10Y"]
df = pd.DataFrame()
if require(converted, core_tickers, "S1/S3/S4/S5 (core carry calc)"):
    df = pd.concat(
        {
            "lme_cash": converted["LMAHDY"],
            "lme_3m": converted["LMAHDS03"],
            "mwp": converted["AUP1"],
            "rotterdam": converted["AMEUDDP"],
            "ust10y": converted["USGGT10Y"],
        },
        axis=1, sort=True,
    ).ffill().dropna(subset=["lme_cash", "lme_3m"])

    df["contango"] = df["lme_3m"] - df["lme_cash"]

    if fin_rate_mode == "USGGT10Y + spread":
        df["fin_rate"] = df["ust10y"] / 100.0 + fin_spread
    else:
        df["fin_rate"] = flat_rate

    df["financing_cost"] = ufin.financing_cost(df["lme_cash"], df["fin_rate"], carry_days)
    warehouse_rent_value = daily_rent * carry_days
    df["breakeven_contango"] = ufin.breakeven_contango(df["financing_cost"], warehouse_rent_value)
    df["fv_premium"] = ufin.premium_fair_value(df["financing_cost"], warehouse_rent_value, df["contango"])
    df["carry_pnl"] = ufin.carry_pnl(df["contango"], df["financing_cost"], warehouse_rent_value)
else:
    warehouse_rent_value = daily_rent * carry_days

kpi_cols = st.columns(6)
mwp_latest = converted.get("AUP1", pd.Series(dtype=float)).dropna()
rot_latest = converted.get("AMEUDDP", pd.Series(dtype=float)).dropna()
cash_latest = converted.get("LMAHDY", pd.Series(dtype=float)).dropna()
m3_latest = converted.get("LMAHDS03", pd.Series(dtype=float)).dropna()

kpi_cols[0].metric("MW premium (AUP1)", f"${mwp_latest.iloc[-1]:,.0f}/t" if not mwp_latest.empty else "n/a")
kpi_cols[1].metric("Rotterdam DP (AMEUDDP)", f"${rot_latest.iloc[-1]:,.0f}/t" if not rot_latest.empty else "n/a")
kpi_cols[2].metric(
    "LME cash / 3M",
    f"${cash_latest.iloc[-1]:,.0f} / ${m3_latest.iloc[-1]:,.0f}" if not cash_latest.empty and not m3_latest.empty else "n/a",
)

if not df.empty:
    latest = df.dropna(subset=["contango", "carry_pnl", "breakeven_contango"]).iloc[-1]
    contango_now, carry_now, breakeven_now = latest["contango"], latest["carry_pnl"], latest["breakeven_contango"]
    regime = ufin.classify_carry_regime(contango_now, breakeven_now)
    kpi_cols[3].metric("Contango (3M−cash)", f"${contango_now:,.0f}/t")
    kpi_cols[4].metric(f"Carry P&L ({carry_days}d)", f"${carry_now:,.0f}/t")
else:
    regime = "UNKNOWN"
    kpi_cols[3].metric("Contango (3M−cash)", "n/a")
    kpi_cols[4].metric(f"Carry P&L ({carry_days}d)", "n/a")

badge_color = {"CONTANGO-CARRY ATTRACTIVE": "🟢", "BACKWARDATION": "🔴", "NEUTRAL": "🟡", "UNKNOWN": "⚪"}[regime]
kpi_cols[5].metric("Regime", f"{badge_color} {regime}")

st.divider()

# ---------------------------------------------------------------------------
# S2 — Regional premia panel
# ---------------------------------------------------------------------------
st.header("S2 — Regional premia panel")
st.markdown(
    "US Midwest (`AUP1`, daily) and Rotterdam duty-paid (`AMEUDDP`, **monthly**) on the same "
    "USD/t axis, plus their spread. Divergence is driven by US Section 232 tariffs "
    "(10%+ from 2018, escalated further in 2025), regional supply/demand, and freight arb "
    "between the two pools — **not** by a single global aluminium price. This page covers "
    "**EU and US only**; a Japan MJP premium series isn't in the verified data list, so "
    "it's out of scope rather than silently omitted."
)

if require(converted, ["AUP1", "AMEUDDP"], "S2"):
    mwp = clip(converted["AUP1"])
    rot = clip(converted["AMEUDDP"])

    fig_prem = go.Figure()
    fig_prem.add_trace(go.Scatter(x=mwp.index, y=mwp.values, name="MW premium (AUP1, USD/t, daily)", line=dict(color="#1f77b4")))
    fig_prem.add_trace(go.Scatter(x=rot.index, y=rot.values, name="Rotterdam DP (AMEUDDP, USD/t, monthly)", line=dict(color="#2ca02c")))

    for x0, label in [("2018-03-01", "2018 S232 tariff"), ("2025-01-01", "2025 tariff escalation")]:
        fig_prem.add_vline(x=x0, line_dash="dot", line_color="gray")
        fig_prem.add_annotation(x=x0, y=1.0, yref="paper", text=label, showarrow=False, yshift=10, font=dict(size=10))
    fig_prem.add_vrect(x0="2021-09-01", x1="2022-06-01", fillcolor="Orange", opacity=0.15, line_width=0,
                        annotation_text="2021-22 EU energy premium spike", annotation_position="top left")

    fig_prem.update_layout(
        title="US Midwest vs Rotterdam Al premium (USD/t)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_prem, width='stretch')

    if not df.empty:
        spread = clip(df["mwp"] - df["rotterdam"])
        fig_spread = go.Figure(go.Scatter(x=spread.index, y=spread.values, name="MWP − Rotterdam (USD/t)", line=dict(color="#9467bd"), fill="tozeroy"))
        fig_spread.add_hline(y=0, line_dash="dot", line_color="gray")
        fig_spread.update_layout(
            title="MWP − Rotterdam spread (USD/t) — Rotterdam forward-filled onto the daily MWP grid",
            yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        )
        st.plotly_chart(fig_spread, width='stretch')

    if show_fx_context and require(converted, ["DXY"], "S2 (DXY/EURUSD context)"):
        dxy = clip(converted["DXY"])
        fig_fx = go.Figure(go.Scatter(x=dxy.index, y=dxy.values, name="DXY (monthly)", line=dict(color="#7f7f7f")))
        fig_fx.update_layout(
            title="US Dollar Index (macro context only — not used in FV/carry calc)",
            yaxis_title="index", xaxis_title="date", hovermode="x unified",
        )
        st.plotly_chart(fig_fx, width='stretch')
        st.caption(
            "USD-priced aluminium is costlier in local-currency terms for non-US buyers when "
            "the dollar is strong, which can dampen regional demand at the margin — a "
            "qualitative macro backdrop, not a modeled input to FV or richness."
        )

st.divider()

# ---------------------------------------------------------------------------
# S3 — Premium vs fair value
# ---------------------------------------------------------------------------
st.header("S3 — Premium vs fair value")
st.markdown(
    "`FV_premium` (carry-component only) vs the **Rotterdam** duty-paid premium — the "
    "cleanest carry proxy of the two, since `AUP1` has US tariffs baked directly into the "
    "print and isn't a clean carry-only comparison. Both are shown at Rotterdam's native "
    "**monthly** cadence (FV resampled down, not Rotterdam forward-filled up) so the chart "
    "doesn't imply daily precision Rotterdam doesn't have. "
    "`premium_richness = actual − FV`: shaded **RICH** where physical S/D (plus duty/freight) "
    "push the premium above pure carry economics, **CHEAP** where it's carry-justified or below."
)

if not df.empty and require(converted, ["AMEUDDP"], "S3"):
    fv_monthly = clip(udata.resample_monthly(df["fv_premium"], how="last"))
    rot_monthly = clip(converted["AMEUDDP"])

    fig_fv = go.Figure()
    fig_fv.add_trace(go.Scatter(x=rot_monthly.index, y=rot_monthly.values, name="Rotterdam DP actual (USD/t)", line=dict(color="#2ca02c")))
    fig_fv.add_trace(go.Scatter(x=fv_monthly.index, y=fv_monthly.values, name="FV_premium (carry-only, USD/t)", line=dict(color="#d62728", dash="dash")))
    fig_fv.update_layout(
        title="Rotterdam actual vs carry-component fair value (USD/t, monthly)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_fv, width='stretch')

    richness = ufin.premium_richness(converted["AMEUDDP"], udata.resample_monthly(df["fv_premium"], how="last"))
    richness_clipped = clip(richness)
    if not richness_clipped.empty:
        fig_rich = go.Figure(go.Scatter(x=richness_clipped.index, y=richness_clipped.values, name="premium_richness (USD/t)", line=dict(color="#8c564b")))
        fig_rich.add_hline(y=0, line_dash="dot", line_color="gray")
        add_regime_shading(fig_rich, richness_clipped > 0, color="LightGreen", opacity=0.2)
        add_regime_shading(fig_rich, richness_clipped < 0, color="LightSalmon", opacity=0.2)
        fig_rich.update_layout(
            title="premium_richness = Rotterdam actual − FV_premium (shaded green=RICH, salmon=CHEAP)",
            yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        )
        st.plotly_chart(fig_rich, width='stretch')

        latest_rich = richness_clipped.dropna()
        if not latest_rich.empty:
            sign_label = "RICH (physical S/D beyond carry)" if latest_rich.iloc[-1] > 0 else "CHEAP (carry-justified or below)"
            st.metric("Latest premium_richness", f"${latest_rich.iloc[-1]:,.0f}/t", help=sign_label)

st.divider()

# ---------------------------------------------------------------------------
# S4 — Carry trade
# ---------------------------------------------------------------------------
st.header("S4 — Carry trade (the 2009-14 warehouse-queue trade)")
st.markdown(
    "`carry_pnl = contango − financing_cost − warehouse_rent`. During 2009-14, Goldman "
    "Sachs, Glencore, and Trafigura ran exactly this trade at scale through LME-licensed "
    "warehouses (notably Detroit): buy cash metal, sell it forward, and store it for the "
    "duration. Positive carry pulls metal into warehouses and out of the available "
    "(deliverable) pool — less metal reaching consumers pushes physical premia up further, "
    "which historically **reinforced** the trade rather than closing it, since higher premia "
    "didn't affect the LME cash/3M spread the trade itself depends on."
)

if not df.empty:
    carry_clipped = clip(df["carry_pnl"])
    fig_carry = go.Figure(go.Scatter(x=carry_clipped.index, y=carry_clipped.values, name="carry_pnl (USD/t)", line=dict(color="#2ca02c"), fill="tozeroy"))
    fig_carry.add_hline(y=0, line_dash="dot", line_color="gray")
    add_regime_shading(fig_carry, carry_clipped > 0, color="LightGreen", opacity=0.25)
    fig_carry.update_layout(
        title=f"Carry P&L, {carry_days}d horizon (shaded = PROFITABLE-CARRY)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_carry, width='stretch')

    st.subheader("Waterfall — carry P&L breakdown on a selected date")
    wf_date_input = st.slider(
        "Waterfall snapshot date",
        min_value=start_date.to_pydatetime(), max_value=end_date.to_pydatetime(),
        value=end_date.to_pydatetime(), format="YYYY-MM-DD",
    )
    wf_ts = pd.Timestamp(wf_date_input)
    df_valid = df.dropna(subset=["contango", "financing_cost", "carry_pnl"])
    if not df_valid.empty:
        nearest_idx = df_valid.index[df_valid.index <= wf_ts]
        snap_date = nearest_idx[-1] if len(nearest_idx) else df_valid.index[0]
        row = df_valid.loc[snap_date]
        fig_wf = go.Figure(go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "relative", "total"],
            x=["Contango", "− Financing", "− Warehouse rent", "Net carry P&L"],
            y=[row["contango"], -row["financing_cost"], -warehouse_rent_value, 0],
            connector=dict(line=dict(color="gray")),
        ))
        fig_wf.update_layout(
            title=f"Carry P&L waterfall, snapshot {snap_date.date()} (USD/t)",
            yaxis_title="USD/t",
        )
        st.plotly_chart(fig_wf, width='stretch')
        st.caption(
            f"Snapshot: contango ${row['contango']:,.0f}/t − financing ${row['financing_cost']:,.0f}/t "
            f"− rent ${warehouse_rent_value:,.0f}/t = net ${row['carry_pnl']:,.0f}/t "
            f"(nearest available date to {wf_date_input.date()}: {snap_date.date()})."
        )

st.divider()

# ---------------------------------------------------------------------------
# S5 — Contango/financing regime
# ---------------------------------------------------------------------------
st.header("S5 — Contango/financing regime")
st.markdown(
    "LME cash vs 3M term structure (shaded green = contango, salmon = backwardation), plus "
    "the financing-cost-driven breakeven: `breakeven_contango = financing_cost + warehouse_rent`. "
    "Carry is only viable when the actual contango sits above that line — higher rates "
    "(`USGGT10Y` + spread, or the flat override) widen the breakeven and make carry harder "
    "to clear."
)

if not df.empty:
    cash_c = clip(df["lme_cash"])
    m3_c = clip(df["lme_3m"])
    contango_c = clip(df["contango"])

    fig_term = go.Figure()
    fig_term.add_trace(go.Scatter(x=cash_c.index, y=cash_c.values, name="LME cash (USD/t)", line=dict(color="#1f77b4")))
    fig_term.add_trace(go.Scatter(x=m3_c.index, y=m3_c.values, name="LME 3M (USD/t)", line=dict(color="#ff7f0e")))
    add_regime_shading(fig_term, contango_c > 0, color="LightGreen", opacity=0.2)
    add_regime_shading(fig_term, contango_c < 0, color="LightSalmon", opacity=0.2)
    fig_term.update_layout(
        title="LME Al cash vs 3M (shaded green=contango, salmon=backwardation)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_term, width='stretch')

    breakeven_c = clip(df["breakeven_contango"])
    fig_breakeven = go.Figure()
    fig_breakeven.add_trace(go.Scatter(x=contango_c.index, y=contango_c.values, name="Actual contango (USD/t)", line=dict(color="#2ca02c")))
    fig_breakeven.add_trace(go.Scatter(x=breakeven_c.index, y=breakeven_c.values, name="Breakeven contango = financing + rent (USD/t)", line=dict(color="#d62728", dash="dash")))
    add_regime_shading(fig_breakeven, contango_c > breakeven_c, color="LightGreen", opacity=0.2)
    fig_breakeven.update_layout(
        title="Actual contango vs breakeven contango (shaded = carry viable)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_breakeven, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# S6 — Supply context (optional, degrades gracefully)
# ---------------------------------------------------------------------------
st.header("S6 — Supply context (optional)")
st.markdown(
    "IAI primary aluminium production, total + regional, monthly (×1000 → t, explicit "
    "resample). **Data caveat**: every `IPAITI*` series in this dataset stops at "
    "**2014-12-31** — 11+ years stale as of today. It is shown below over its own native "
    "range, not overlaid against the current premia charted above, since the two don't "
    "overlap in time. The well-known 2022 EU smelter curtailment narrative (energy-cost-driven "
    "capacity cuts feeding the EU premium spike shaded in S2) is **general market knowledge**, "
    "not something visible in this stale dataset — stated here as qualitative context only."
)

if show_iai:
    if require(converted, ["IPAITITL"], "S6"):
        total_prod = converted["IPAITITL"].dropna()
        st.caption(
            f"IAI total production series covers {total_prod.index.min().date()} to "
            f"{total_prod.index.max().date()} — shown in full below (not clipped to the "
            "sidebar date range, which defaults to the last 3 years and would be empty)."
        )
        yoy = total_prod.pct_change(12) * 100

        fig_iai = go.Figure()
        fig_iai.add_trace(go.Scatter(x=total_prod.index, y=total_prod.values, name="IAI total production (t/month)", line=dict(color="#1f77b4")))
        fig_iai.add_trace(go.Scatter(x=yoy.index, y=yoy.values, name="YoY change (%)", yaxis="y2", line=dict(color="#d62728", dash="dot")))
        fig_iai.update_layout(
            title="IAI primary aluminium production, total (STALE — ends 2014-12)",
            yaxis_title="t/month", xaxis_title="date", hovermode="x unified",
            yaxis2=dict(title="YoY change (%)", overlaying="y", side="right"),
        )
        st.plotly_chart(fig_iai, width='stretch')

        available_regions = [tk for tk in IAI_REGIONAL if tk in converted and not converted[tk].dropna().empty]
        if available_regions:
            fig_regional = go.Figure()
            for tk in available_regions:
                s = converted[tk].dropna()
                fig_regional.add_trace(go.Scatter(x=s.index, y=s.values, name=f"{IAI_REGIONAL[tk]} ({tk})"))
            fig_regional.update_layout(
                title="IAI primary aluminium production by region (STALE — ends 2014-12)",
                yaxis_title="t/month", xaxis_title="date", hovermode="x unified",
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_regional, width='stretch')
else:
    st.caption("Toggle **'Show IAI production context'** in the sidebar to render this section.")

st.divider()
st.caption(
    "Aluminium Premia Fair-Value & Carry — page 3 of the Commodity Physical Desk Monitor. "
    "See README.md for every formula and unit-conversion assumption."
)
