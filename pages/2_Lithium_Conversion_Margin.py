"""
Page 2 — Lithium Conversion Margin (spodumene -> battery-grade Li2CO3).

Chinese-converter P&L: SC6 (6% Li2O) spodumene concentrate CIF is roasted/
leached/purified into 99.5% battery-grade Li2CO3, sold domestically. Tracks
the 2023-25 lithium crash flowing through into converter margin compression
and, per S6, a curtailment-risk regime. See README.md for the full formula
reference, the stoichiometry rationale behind `conversion_ratio`, and every
excluded cost (by-products, tax, the LiOH route).

REVISION 2026-07-05 — every spod/carbonate series + AUDUSD verified
**monthly** in this dataset (month-end prints), not "daily, gaps" as the
initial brief assumed; `LCBMAUSF` verified as spodumene FOB Australia, NOT
lithium carbonate as the generic ticker catalog (`data/tickers.json`)
labels it (value range and CIF-vs-FOB tracking both confirm spodumene).
See config.py's REVISION note and `config.LITHIUM_DATA_CAVEATS`.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from utils import data as udata
from utils import finance as ufin

st.set_page_config(page_title="Lithium Conversion Margin", layout="wide")

ALL_TICKERS = [
    "L4CNSPI", "SVPA", "LICNSPDU", "L4CNSPAU", "L4CNMJGO", "LCBMAUSF",
    "AUDUSD", "BDIY", "BSI", "BHSI",  # BHSI: optional freight-regime badge (page 5 back-integration)
]
REFERENCE_GRADE = 6.0  # % Li2O — the grade every spod series here is benchmarked at


# ---------------------------------------------------------------------------
# small local helpers (presentation-only, kept out of utils/ on purpose —
# same convention as pages 1 and 3)
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
st.sidebar.header("Lithium Conversion Margin — parameters")

st.sidebar.subheader("Spodumene CIF benchmark (S1-S3, S6)")
SPOD_OPTIONS = {
    "L4CNSPI — China spod CIF index (default)": "L4CNSPI",
    "LICNSPDU — Li2O 6% min CIF (cross-check)": "LICNSPDU",
    "L4CNSPAU — AU-origin CIF (cross-check)": "L4CNSPAU",
    "SVPA — Fastmarkets future (data starts 2024-10 only)": "SVPA",
}
spod_label = st.sidebar.selectbox(
    "Spodumene CIF series used for the margin calc",
    options=list(SPOD_OPTIONS),
    index=0,
    help="All four are SC6/6% Li2O CIF China spodumene series. "
         "`SVPA` (Fastmarkets future) genuinely "
         "only starts 2024-10 in this dataset",
)
spod_choice = SPOD_OPTIONS[spod_label]

if st.sidebar.button("🔄 Refresh USDCNY from Yahoo Finance", help="Force-refetch the cached FX series (data/csv/USDCNY.csv)."):
    warn = udata.ensure_usdcny_csv(force=True)
    udata.get_dataset.clear()
    udata.load_all_raw.clear()
    if warn:
        st.sidebar.warning(warn)
    else:
        st.sidebar.success("USDCNY refetched from Yahoo Finance.")

st.sidebar.subheader("Conversion economics")
conversion_ratio = st.sidebar.slider(
    "Conversion ratio (t SC6 spod / t Li2CO3)", min_value=6.5, max_value=9.5, value=8.0, step=0.1,
    help="Stoichiometric baseline: a 6% Li2O concentrate contains 60 kg Li2O per tonne. "
         "MW Li2O = 29.88, MW Li2CO3 = 73.89, and Li is conserved 1:1 between the two "
         "(2 Li per formula unit each), so 60 kg Li2O -> 60 x (73.89/29.88) = 148.4 kg "
         "Li2CO3 at 100% recovery -> 1/0.1484 = 6.74 t concentrate per t carbonate, "
         "theoretical maximum. Real roast/leach/purification recovery of ~85-90% pushes "
         "this to ~7.5-8.5 t/t in practice -> the 8.0 default corresponds to ~84% "
         "effective recovery"
)
conv_cost = st.sidebar.slider(
    "Conversion cost — roast/reagents/energy/labor (USD/t Li2CO3)",
    min_value=0, max_value=5000, value=2200, step=100,
    help="Indicative flat processing cost per tonne of Li2CO3 produced. No public cost-curve "
         "series is used",
)
grade_pct = st.sidebar.slider(
    "Actual concentrate grade traded (% Li2O)",
    min_value=3.0, max_value=7.0, value=REFERENCE_GRADE, step=0.1,
    help=f"All spod series on this page are quoted/benchmarked at {REFERENCE_GRADE:.1f}% Li2O "
         "(SC6). If the grade actually traded differs (e.g. lower-grade lepidolite feedstock), "
         f"the effective conversion ratio is scaled by {REFERENCE_GRADE:.1f}/grade: a lower "
         "grade needs proportionally more tonnes of concentrate per tonne of carbonate output. "
         "Leave at 6.0 to use conversion_ratio unscaled.",
)
freight_inland = st.sidebar.slider(
    "Inland freight, port -> converter (USD/t Li2CO3)",
    min_value=0, max_value=200, value=40, step=5,
    help="Indicative inland logistics cost moving CIF-landed concentrate to the Chinese "
         "conversion plant (e.g. Jiangxi/Sichuan) —> separate from the S4 ocean CIF-FOB "
         "freight leg, which is observed from data, not a slider.",
)
other_cost = st.sidebar.slider(
    "Other / unmodeled costs (USD/t Li2CO3)",
    min_value=0, max_value=500, value=0, step=25,
    help="Catch-all buffer for costs not otherwise modeled (packaging, minor logistics, "
         "yield-loss buffer beyond conversion_ratio). Defaults to 0 —> add only if you want "
         "to stress-test a thinner margin.",
)

st.sidebar.subheader("Curtailment signal (S6)")
curtailment_n = st.sidebar.slider(
    "Consecutive months underwater to flag curtailment risk",
    min_value=1, max_value=12, value=4, step=1,
    help="Every series feeding the margin calc is verified **monthly** in this dataset (see "
         "the data-caveats expander below) —> this counts consecutive MONTHLY observations "
         "with margin < $0/t, not weeks.",
)

st.sidebar.subheader("S4 freight-leg overlay")
FREIGHT_OVERLAY_OPTIONS = {
    "None": None,
    "BDIY — Baltic Dry Index": "BDIY",
    "BSI — Baltic Supramax (STALE, ends 2017-03)": "BSI",
}
freight_overlay_label = st.sidebar.selectbox(
    "Optional Baltic freight-index overlay",
    options=list(FREIGHT_OVERLAY_OPTIONS),
    index=0,
    help="Neither series is used in any calc — purely a visual freight-rate backdrop for S4. "
         "Degrades gracefully (a caption, not a crash) if the chosen series has no data in the "
         "selected date range.",
)
freight_overlay_ticker = FREIGHT_OVERLAY_OPTIONS[freight_overlay_label]


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
raw, converted, warnings = udata.get_dataset(tuple(ALL_TICKERS))

# ---------------------------------------------------------------------------
# S1 — Header + KPI
# ---------------------------------------------------------------------------
st.title("Lithium Conversion Margin")
st.caption(
    "Spodumene -> battery-grade Li2CO3: Chinese converter P&L, tracking the 2023-25 "
    "lithium crash into margin compression and (S6) a curtailment-risk signal"
)

st.info(
    "`USDCNY` is fetched from **Yahoo Finance** (`CNY=X`)",
)
st.info(
    "**Frequency note**: every spodumene/carbonate series here + `AUDUSD` are verified "
    "**monthly** (month-end prints) in this dataset -> the margin calc, S2-S6 "
    "charts, and the S6 curtailment slider are all in months, not weeks.",
)
st.info(
    "**Carbonate route only** (99.5% battery-grade `L4CNMJGO`); the LiOH (hydroxide) route "
    "is out of scope. Margin is **indicative, pre-by-product, pre-tax**: by-products, VAT/"
    "income tax, and plant-specific yield are excluded"
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

default_years = 13
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


# --- cross-source spod divergence + SVPA guard ----------------------------
spod_candidates = ["L4CNSPI", "LICNSPDU", "L4CNSPAU", "SVPA"]
latest_by_source = {}
for tk in spod_candidates:
    s = converted.get(tk, pd.Series(dtype=float)).dropna()
    if not s.empty:
        latest_by_source[tk] = s.iloc[-1]

if len(latest_by_source) >= 2:
    vals = list(latest_by_source.values())
    spread_pct = (max(vals) - min(vals)) / min(vals) * 100 if min(vals) else 0.0
    if spread_pct > 8:
        detail = ", ".join(f"{k}=${v:,.0f}/t" for k, v in latest_by_source.items())
        st.warning(
            f"**Cross-source spodumene divergence**: latest CIF quotes diverge by "
            f"{spread_pct:.0f}% across sources ({detail}) — likely index-methodology/timing "
            f"differences between panels, not necessarily a real basis move. Selected "
            f"benchmark: **{spod_choice}**.",
        )

if spod_choice == "SVPA" and "SVPA" in converted and not converted["SVPA"].dropna().empty:
    svpa_min = converted["SVPA"].dropna().index.min()
    if start_date < svpa_min:
        st.info(
            f"**SVPA guard**: `SVPA` data starts {svpa_min.date()} — the margin calc and every "
            f"chart below will show a gap before that date rather than a backfilled value.",
        )

# --- core margin calc, needed by S1 KPI row, S2, S3, S6 --------------------
margin_df = pd.DataFrame()
if require(converted, [spod_choice, "L4CNMJGO"], "S1/S2/S3/S6 (core margin calc)"):
    margin_df = ufin.converter_margin(
        carbonate_usd=converted["L4CNMJGO"],
        spod_usd=converted[spod_choice],
        conversion_ratio=conversion_ratio,
        conv_cost=conv_cost,
        grade_pct=grade_pct,
        freight_inland=freight_inland,
        other_cost=other_cost,
        reference_grade=REFERENCE_GRADE,
    )

kpi_cols = st.columns(6)
carb_latest = converted.get("L4CNMJGO", pd.Series(dtype=float)).dropna()
spod_latest = converted.get(spod_choice, pd.Series(dtype=float)).dropna()
kpi_cols[0].metric(
    "Li carbonate 99.5% DEL",
    f"${carb_latest.iloc[-1]:,.0f}/t" if not carb_latest.empty else "n/a",
)
kpi_cols[1].metric(
    f"Spodumene CIF ({spod_choice})",
    f"${spod_latest.iloc[-1]:,.0f}/t" if not spod_latest.empty else "n/a",
)
if not margin_df.empty:
    latest_row = margin_df.iloc[-1]
    kpi_cols[2].metric("Spod cost / t carbonate", f"${latest_row['spod_cost']:,.0f}/t")
    kpi_cols[3].metric("Gross margin (indicative)", f"${latest_row['margin']:,.0f}/t")
    regime = ufin.classify_regime(
        latest_row["margin"],
        marginal_band=config.LITHIUM_MARGIN_BREAKEVEN_BAND,
        open_label="HEALTHY",
        closed_label="UNDERWATER",
        marginal_label="BREAKEVEN",
    )
else:
    kpi_cols[2].metric("Spod cost / t carbonate", "n/a")
    kpi_cols[3].metric("Gross margin (indicative)", "n/a")
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
        "Freight regime (Handysize, ctx)", ufin.freight_regime_badge(frow["regime"]),
        f"{frow['pctile']:.0f}th pctile", delta_color="off",
        help="Baltic Handysize (BHSI) freight regime — context only, not used in the conversion-margin calc above. See page 5 (Freight Overlay) for the full cross-basin picture.",
    )
else:
    kpi_cols[5].metric("Freight regime (Handysize, ctx)", "n/a")

st.divider()

# ---------------------------------------------------------------------------
# S2 — Conversion margin time series
# ---------------------------------------------------------------------------
st.header("S2 — Conversion margin time series")
st.markdown(
    f"`gross_margin = carbonate_USD − spod_cost_per_t_LC − conv_cost − freight_inland − other`, "
    f"using the **{spod_choice}** benchmark. Knowing that `spod_cost_per_t_LC = conv_ratio * (reference_grade/actual_grade_pct).`"
)

if not margin_df.empty:
    mdf = margin_df.loc[(margin_df.index >= start_date) & (margin_df.index <= end_date)]

    fig_stack = go.Figure()
    fig_stack.add_trace(go.Scatter(
        x=mdf.index, y=mdf["carbonate_usd"], name="Li carbonate DEL (USD/t)",
        line=dict(color="#2ca02c"),
    ))
    fig_stack.add_trace(go.Scatter(
        x=mdf.index, y=mdf["spod_cost"], name=f"Spod cost / t carbonate ({spod_choice}, USD/t)",
        line=dict(color="#d62728"),
    ))
    fig_stack.add_trace(go.Scatter(
        x=mdf.index, y=mdf["spod_cost"] + conv_cost + freight_inland + other_cost, name=f"Spod cost / t carbonate ({spod_choice}, USD/t) + conv cost + freight inland + other cost",
        line=dict(color='#2770d6'),
    ))
    fig_stack.update_layout(
        title="Carbonate price vs spodumene cost per tonne of carbonate",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_stack, width='stretch')

    fig_margin = go.Figure(go.Scatter(
        x=mdf.index, y=mdf["margin"], name="Gross margin (USD/t)",
        line=dict(color="#1f77b4"), fill="tozeroy",
    ))
    margin_pct_s2 = (mdf["margin"] / mdf["carbonate_usd"] * 100).dropna()
    if not margin_pct_s2.empty:
        fig_margin.add_trace(go.Scatter(
            x=margin_pct_s2.index, y=margin_pct_s2.values, name="Margin (% of carbonate price)",
            yaxis="y2", line=dict(color="#9467bd", dash="dot"),
        ))
    fig_margin.add_hline(y=0, line_dash="dot", line_color="gray")
    add_regime_shading(fig_margin, mdf["margin"] < 0, color="Crimson", opacity=0.2)
    fig_margin.add_vrect(
        x0="2023-01-01", x1="2024-01-01", fillcolor="Gray", opacity=0.08, line_width=0,
        annotation_text="2023-24 lithium crash", annotation_position="top left",
    )
    fig_margin.update_layout(
        title="Indicative converter gross margin, USD/t Li2CO3 (shaded = UNDERWATER)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        yaxis2=dict(title="margin (% of carbonate price)", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_margin, width='stretch')

    latest_margin_clipped = mdf["margin"].dropna()
    if not latest_margin_clipped.empty:
        headline = (
            "**Margin has flipped negative** —> consistent with the curtailment thesis tested in S6."
            if latest_margin_clipped.iloc[-1] < 0
            else "Margin is currently positive under the selected assumptions."
        )
        st.caption(headline)

st.divider()

# ---------------------------------------------------------------------------
# S3 — Margin decomposition
# ---------------------------------------------------------------------------
st.header("S3 — Margin decomposition")
st.markdown(
    "Waterfall on a selected date: carbonate revenue minus spod cost, conversion cost, and "
    "freight/other, down to net margin. Second view: margin as a **% of carbonate price** "
    "(compression ratio) over time -> scale-free -> comparable across the 2022 boom and "
    "the 2023-25 crash despite huge price variation"
)

if not margin_df.empty:
    wf_date_input = st.slider(
        "Waterfall snapshot date",
        min_value=start_date.to_pydatetime(), max_value=end_date.to_pydatetime(),
        value=end_date.to_pydatetime(), format="YYYY-MM-DD",
        key="s3_waterfall_date",
    )
    wf_ts = pd.Timestamp(wf_date_input)
    mdf_valid = margin_df.dropna(subset=["carbonate_usd", "spod_cost", "margin"])
    mdf_valid = mdf_valid.loc[(mdf_valid.index >= start_date) & (mdf_valid.index <= end_date)]
    if not mdf_valid.empty:
        nearest_idx = mdf_valid.index[mdf_valid.index <= wf_ts]
        snap_date = nearest_idx[-1] if len(nearest_idx) else mdf_valid.index[0]
        row = mdf_valid.loc[snap_date]
        fig_wf = go.Figure(go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "relative", "relative", "total"],
            x=["Carbonate DEL", "− Spod cost", "− Conversion cost", "− Freight+other", "Net margin"],
            y=[row["carbonate_usd"], -row["spod_cost"], -conv_cost, -(freight_inland + other_cost), 0],
            connector=dict(line=dict(color="gray")),
        ))
        fig_wf.update_layout(
            title=f"Margin waterfall, snapshot {snap_date.date()} (USD/t, {spod_choice} benchmark)",
            yaxis_title="USD/t",
        )
        st.plotly_chart(fig_wf, width='stretch')
        st.caption(
            f"Snapshot: carbonate ${row['carbonate_usd']:,.0f}/t − spod cost ${row['spod_cost']:,.0f}/t "
            f"− conversion ${conv_cost:,.0f}/t − freight+other ${freight_inland + other_cost:,.0f}/t "
            f"= net ${row['margin']:,.0f}/t (nearest available month to {wf_date_input.date()}: {snap_date.date()})."
        )

    # margin_pct = (margin_df["margin"] / margin_df["carbonate_usd"] * 100).rename("margin_pct")
    # margin_pct_c = clip(margin_pct)
    # if not margin_pct_c.empty:
    #     fig_pct = go.Figure(go.Scatter(x=margin_pct_c.index, y=margin_pct_c.values, name="Margin (% of carbonate price)", line=dict(color="#9467bd")))
    #     fig_pct.add_hline(y=0, line_dash="dot", line_color="gray")
    #     add_regime_shading(fig_pct, margin_pct_c < 0, color="Crimson", opacity=0.2)
    #     fig_pct.update_layout(
    #         title="Margin compression ratio: gross margin as % of carbonate price",
    #         yaxis_title="%", xaxis_title="date", hovermode="x unified",
    #     )
    #     st.plotly_chart(fig_pct, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# S4 — FOB vs CIF = freight leg
# ---------------------------------------------------------------------------
st.header("S4 — FOB vs CIF = freight leg")
st.markdown(
    "`LCBMAUSF` (spodumene FOB Australia) vs `L4CNSPAU` (China 6% spod CIF **from Australia**)."
    "Since the freight leg only makes sense compared against an AU-origin CIF "
    "print: `implied_freight = spod_CIF − spod_FOB_AU`, i.e. AU→China ocean freight + insurance "
    "+ timing. Real ocean freight+insurance can never be negative, so negative prints are "
    "diagnostic of a cross-panel mismatch -> not a market signal"
)

CIF_INCEPTION_END = pd.Timestamp("2023-12-31")

if require(converted, ["LCBMAUSF", "L4CNSPAU"], "S4"):
    df4 = pd.concat(
        {"fob": converted["LCBMAUSF"], "cif": converted["L4CNSPAU"]}, axis=1, sort=True
    ).dropna()
    df4["implied_freight"] = df4["cif"] - df4["fob"]

    cif_start = converted["L4CNSPAU"].dropna().index.min()
    if cif_start >= pd.Timestamp("2023-01-01"):
        post_inception = df4.loc[df4.index > CIF_INCEPTION_END, "implied_freight"]
        st.warning(
            f"**Index-inception artifact, {cif_start.date()}-{CIF_INCEPTION_END.date()}**: "
            f"`L4CNSPAU` only starts {cif_start.date()} in this dataset (`LCBMAUSF` runs back "
            "to 2018). Its first few prints land right in the middle of the crash's steepest "
            "leg (AU FOB fell ~58% in 3 months). A newly-launched assessment with thin panel "
            "participation, on top of a market moving hundreds of USD/t per month, is enough to "
            "produce the large negative spread seen there without any real negative freight. "
            + (
                f"Excluding that window, implied freight centers positive (mean "
                f"${post_inception.mean():,.0f}/t, median ${post_inception.median():,.0f}/t) — a "
                "plausible AU→China rate, with the remaining occasional small negative months "
                "reading as ordinary cross-panel noise (differing assessment cutoff dates / "
                "methodology between two independently-run indices)"
                if not post_inception.empty else ""
            ),
        )

    df4c = df4.loc[(df4.index >= start_date) & (df4.index <= end_date)]

    fig_fobcif = go.Figure()
    fig_fobcif.add_trace(go.Scatter(x=df4c.index, y=df4c["fob"], name="FOB Australia (LCBMAUSF, USD/t)", line=dict(color="#1f77b4")))
    fig_fobcif.add_trace(go.Scatter(x=df4c.index, y=df4c["cif"], name="CIF China, AU-origin (L4CNSPAU, USD/t)", line=dict(color="#ff7f0e")))
    fig_fobcif.update_layout(
        title="Spodumene FOB Australia vs CIF China (AU-origin), USD/t",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_fobcif, width='stretch')

    median_abs_freight = df4c["implied_freight"].abs().median()
    if median_abs_freight > 0:
        spike_mask = df4c["implied_freight"].abs() > 3 * median_abs_freight
    else:
        spike_mask = pd.Series(False, index=df4c.index)
    anomaly_mask = (df4c["implied_freight"] < 0) | spike_mask
    anomalies = df4c.loc[anomaly_mask]

    fig_freight = go.Figure(go.Scatter(
        x=df4c.index, y=df4c["implied_freight"], name="Implied freight (USD/t)",
        line=dict(color="#2ca02c"), fill="tozeroy",
    ))
    fig_freight.add_hline(y=0, line_dash="dot", line_color="gray")
    if cif_start >= pd.Timestamp("2023-01-01") and cif_start <= CIF_INCEPTION_END:
        fig_freight.add_vrect(
            x0=cif_start, x1=CIF_INCEPTION_END, fillcolor="Orange", opacity=0.15, line_width=0,
            annotation_text="CIF index inception (thin panel)", annotation_position="top left",
        )
    if not anomalies.empty:
        fig_freight.add_trace(go.Scatter(
            x=anomalies.index, y=anomalies["implied_freight"], mode="markers",
            name="anomaly (neg/spike)", marker=dict(size=9, color="black", symbol="x"),
        ))

    if freight_overlay_ticker and require(converted, [freight_overlay_ticker], f"S4 freight overlay ({freight_overlay_ticker})"):
        if freight_overlay_ticker == "BSI":
            st.warning("`BSI` is stale in this dataset (ends 2017-03) — shown for historical reference only; it will not appear if the chart window is more recent.", icon="⚠️")
        overlay_s = clip(converted[freight_overlay_ticker])
        if overlay_s.dropna().empty:
            st.caption(f"{freight_overlay_ticker} has no observations in the selected date range — degraded gracefully, chart shown without it.")
        else:
            fig_freight.add_trace(go.Scatter(
                x=overlay_s.index, y=overlay_s.values, name=f"{freight_overlay_ticker} (index, right axis)",
                yaxis="y2", line=dict(color="#7f7f7f", dash="dot"),
            ))
            fig_freight.update_layout(yaxis2=dict(title=f"{freight_overlay_ticker} (index points)", overlaying="y", side="right"))

    fig_freight.update_layout(
        title="Implied AU->China freight leg (CIF − FOB, USD/t)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
    )
    st.plotly_chart(fig_freight, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# S5 — Producer squeeze (FX)
# ---------------------------------------------------------------------------
st.header("S5 — Producer squeeze (FX)")
st.markdown(
    "`FOB_AUD = LCBMAUSF / AUDUSD` same spodumene FOB price restated in AUD, the "
    "currency AU miners' costs are mostly denominated in. When AUD weakens alongside a falling "
    "USD spodumene price, AU producer revenue in local-currency terms falls by less than the "
    "USD price suggests -> cushioning miners and helping explain why AU mines (Greenbushes) ran "
    "longer through the crash than Chinese converters, whose margin is a pure USD/CNY spread."
)

if require(converted, ["LCBMAUSF", "AUDUSD"], "S5"):
    df5 = pd.concat(
        {"fob_usd": converted["LCBMAUSF"], "audusd": converted["AUDUSD"]}, axis=1, sort=True
    ).dropna()
    df5["fob_aud"] = df5["fob_usd"] / df5["audusd"]
    df5c = df5.loc[(df5.index >= start_date) & (df5.index <= end_date)]

    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(x=df5c.index, y=df5c["fob_usd"], name="FOB Australia (USD/t)", line=dict(color="#1f77b4")))
    fig5.add_trace(go.Scatter(x=df5c.index, y=df5c["fob_aud"], name="FOB Australia (AUD/t)", yaxis="y2", line=dict(color="#d62728")))
    fig5.update_layout(
        title="Spodumene FOB Australia: USD/t vs AUD/t",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        yaxis2=dict(title="AUD/t", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig5, width='stretch')

    if not margin_df.empty:
        merged = pd.concat({"margin": margin_df["margin"], "fob_aud": df5["fob_aud"]}, axis=1, sort=True).dropna()
        merged_c = merged.loc[(merged.index >= start_date) & (merged.index <= end_date)]
        if len(merged_c) >= 3:
            fig_corr = go.Figure()
            fig_corr.add_trace(go.Scatter(x=merged_c.index, y=merged_c["margin"], name="China converter margin (USD/t)", line=dict(color="#1f77b4")))
            fig_corr.add_trace(go.Scatter(x=merged_c.index, y=merged_c["fob_aud"], name="AU producer FOB (AUD/t, right axis)", yaxis="y2", line=dict(color="#d62728")))
            fig_corr.update_layout(
                title="Converter margin (China) vs producer FOB (AU) — opposite P&Ls up/down the chain",
                yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
                yaxis2=dict(title="AUD/t", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.08),
            )
            st.plotly_chart(fig_corr, width='stretch')

            st.markdown(
                "**Lead-lag (cross-correlation)**: `Δmargin` vs `Δfob_aud`, both differenced "
                "(monthly) to make them stationary, swept over lags of -6..+6 months. Positive "
                "lag k means margin **leads** fob_aud by k months; negative lag means margin "
                "**lags** it."
            )
            margin_diff = merged["margin"].diff().dropna()
            fob_aud_diff = merged["fob_aud"].diff().dropna()
            ccf_lead = ufin.cross_corr(margin_diff, fob_aud_diff, max_lag=6)
            ccf_lag = ufin.cross_corr(fob_aud_diff, margin_diff, max_lag=6)
            ccf_full = pd.concat([
                ccf_lag.assign(lag=lambda d: -d["lag"]).iloc[:0:-1],  # negative lags, excluding 0
                ccf_lead,  # lag 0..6
            ], ignore_index=True).sort_values("lag").reset_index(drop=True)
            lag_peak, corr_peak = ufin.peak_lag(ccf_full)

            colors = ["#d62728" if l == lag_peak else "#1f77b4" for l in ccf_full["lag"]]
            fig_ccf = go.Figure(go.Bar(x=ccf_full["lag"], y=ccf_full["corr"], marker_color=colors))
            fig_ccf.update_layout(
                title="CCF: Δconverter margin vs Δproducer FOB_AUD (China vs AU)",
                xaxis_title="lag, months (margin leads fob_aud →)", yaxis_title="correlation",
            )
            st.plotly_chart(fig_ccf, width='stretch')

            if lag_peak is not None:
                n_obs_peak = ccf_full.loc[ccf_full["lag"] == lag_peak, "n_obs"].iloc[0]
                st.metric(
                    "Peak lead-lag: Δmargin vs Δfob_aud",
                    f"lag {lag_peak:+d}mo, corr {corr_peak:+.2f} (n={n_obs_peak} months)",
                    help="Expect negative correlation near lag 0 over the crash: China converter "
                         "margin down at the same time AU producer FOB_AUD revenue holds up "
                         "better than the raw USD price — opposite ends of the same supply chain. "
                         "A peak away from lag 0 would suggest one side systematically leads the "
                         "other rather than moving together contemporaneously.",
                )
            st.caption(
                "Caveat: in-sample correlation on a limited (monthly) history — peak-lag "
                "estimates are sensitive to the sample window and differencing choice."
            )

st.divider()

# ---------------------------------------------------------------------------
# S6 — Curtailment signal
# ---------------------------------------------------------------------------
st.header("S6 — Curtailment signal")
st.markdown(
    f"`consecutive_below(margin, 0, N={curtailment_n})` — flags every month that is part of a "
    f"run of **{curtailment_n}+ consecutive months** with gross margin below $0/t. This is the "
    "mechanical link to the curtailment thesis: converters running underwater for a sustained "
    "stretch have an economic incentive to cut run-rates."
)

if not margin_df.empty:
    margin_c6 = clip(margin_df["margin"])
    if not margin_c6.empty:
        curtailment_flag = ufin.consecutive_below(margin_c6, 0.0, curtailment_n)

        fig6 = go.Figure(go.Scatter(x=margin_c6.index, y=margin_c6.values, name="Gross margin (USD/t)", line=dict(color="#1f77b4")))
        fig6.add_hline(y=0, line_dash="dot", line_color="gray")
        add_regime_shading(fig6, curtailment_flag, color="Crimson", opacity=0.3)
        fig6.update_layout(
            title=f"Curtailment-risk regime: margin < $0/t for >= {curtailment_n} consecutive months (shaded)",
            yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        )
        st.plotly_chart(fig6, width='stretch')

        latest_flag = curtailment_flag.dropna()
        if not latest_flag.empty and bool(latest_flag.iloc[-1]):
            st.error(
                f"**Curtailment-risk regime ACTIVE** as of {latest_flag.index[-1].date()} — margin "
                f"has been underwater for >= {curtailment_n} consecutive months under the selected assumptions.",
            )
        else:
            st.caption("Not currently in a curtailment-risk regime under the selected threshold and assumptions.")

    st.markdown(
        "**Illustrative 2024 supply response** (qualitative context only): widely-reported industry events coinciding with the margin "
        "compression shown above include Albemarle/IGO's **Greenbushes** trimming output "
        "guidance, Chinese **lepidolite** converters around **Yichun, Jiangxi** curtailing "
        "high-cost production, and **CATL's Jianxiawo** lepidolite mine pausing operations. "
    )

st.divider()