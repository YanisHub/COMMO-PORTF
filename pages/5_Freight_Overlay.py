"""
Page 5 — Freight Overlay.

Theme: freight as a CROSS-BASIN REGIME OVERLAY that modulates the arb/
margin assumptions already used in pages 1 (Cu), 2 (Li), and 4 (Zn) —
not a new source of $/t route freight. Physical traders live and die on
freight; this page shows the freight regime across vessel classes, maps
each class to the commodities it actually moves, and freight-adjusts the
other pages' arb/margin sliders by a Baltic-derived scaler. See README.md
for every formula and the full scope-limit writeup.

SCOPE LIMIT (see also config.FREIGHT_DATA_CAVEATS and the in-app banner
below): the Baltic series are unitless INDEX POINTS, not USD/t on any
named route — there is no Cape C5 / Panamax route USD/t series in this
dataset, and none is fabricated here. The one real dollar-freight series
in this app is the Li CIF-FOB spread (`L4CNSPAU - LCBMAUSF`, S3/page 2),
used to validate the Baltic proxy — never the reverse.

REVISION 2026-07-06 — building this page against the actual CSVs (not
just the brief) turned up the same frequency surprise as every prior
page (all six Baltic series + the exporter-FX pairs are verified MONTHLY,
not "daily, gaps"), plus one more consequential finding: `BSI` (Supramax —
the vessel map's PRIMARY conc/spodumene proxy) stops 2017-03 in this
dataset, which is 9+ years before the one real freight-validation series
(`L4CNSPAU - LCBMAUSF`) even starts (2023-09) — ZERO temporal overlap, so
BSI cannot actually be validated here regardless of what the brief
assumes. `BHSI` (Handysize, current through 2026-06, the map's secondary
conc/spod proxy) is used as the practical default throughout; BSI stays
selectable for domain/historical reference with an explicit warning. See
config.py's REVISION note and `config.FREIGHT_DATA_CAVEATS`.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from utils import data as udata
from utils import finance as ufin

st.set_page_config(page_title="Freight Overlay", layout="wide")

VESSEL_TICKERS = ["BCI14", "BSI", "BHSI", "BIDY", "BITY"]
ALL_TICKERS = [
    "BDIY", *VESSEL_TICKERS,
    "L4CNSPAU", "LCBMAUSF",            # real $/t freight validation (from page 2)
    "CECNVXAQ", "LMCADY", "CECN0002",  # Cu import-margin leg reused for S4
    "AUDUSD", "USDZAR", "USDRUB", "USDTRY", "USDIDR", "EURUSD", "DXY", "USGGT10Y",  # S6 context
]

VESSEL_SHORT = {"BCI14": "Capesize", "BSI": "Supramax", "BHSI": "Handysize",
                 "BIDY": "Dirty tanker", "BITY": "Clean tanker"}
VESSEL_COLOR = {"BDIY": "#7f7f7f", "BCI14": "#1f77b4", "BSI": "#d62728",
                 "BHSI": "#2ca02c", "BIDY": "#8c564b", "BITY": "#9467bd"}


# ---------------------------------------------------------------------------
# small local helpers (presentation-only, kept out of utils/ — same pattern
# as pages 1-4)
# ---------------------------------------------------------------------------
def require(converted: dict, keys: list[str], section: str) -> bool:
    missing = [k for k in keys if k not in converted or converted[k].dropna().empty]
    if missing:
        for m in missing:
            desc = config.TICKERS.get(m, {}).get("desc", m)
            st.warning(f"**{section}**: {m} ({desc}) isn't available, so this section is skipped.")
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


def latest_metric(s: pd.Series | None, fmt: str = "{:,.0f} pts") -> tuple[str, str | None]:
    """(value_str, 'as of <date>' delta) for a metric — the delta doubles as
    an always-visible staleness flag (BSI's will read 2017-03 vs everything
    else's 2026-06, right on the metric itself)."""
    if s is None or s.dropna().empty:
        return "n/a", None
    s = s.dropna()
    return fmt.format(s.iloc[-1]), f"as of {s.index[-1].date()}"


# ---------------------------------------------------------------------------
# Sidebar — global parameters
# ---------------------------------------------------------------------------
st.sidebar.header("Freight Overlay controls")

st.sidebar.subheader("Regime transform")
regime_window = st.sidebar.slider(
    "Regime window (months)", min_value=12, max_value=60,
    value=config.FREIGHT_REGIME_WINDOW_DEFAULT, step=6,
    help="Trailing window for the rolling percentile/z-score regime transform "
         "(`utils.finance.freight_regime`). Every Baltic series here is verified MONTHLY, "
         "so 36 = 3Y, matching every other page's default chart window. LOW < 25th "
         "percentile of the trailing window, HIGH > 75th, else NORMAL.",
)

st.sidebar.subheader("Freight scaler baseline")
baseline_mode_label = st.sidebar.radio(
    "Baseline for freight_scaler = index / baseline",
    options=["Rolling mean (trailing)", "Fixed reference date"],
    index=0,
    help="Rolling mean lets the baseline drift with the prevailing regime over time, using "
         "the same window as above. Fixed reference date freezes one observed index level "
         "as the comparison point instead. Pick a date in the sidebar once data loads.",
)
baseline_mode = "rolling" if baseline_mode_label.startswith("Rolling") else "fixed"

st.sidebar.subheader("Conc/spodumene proxy vessel")
vessel_options = {
    "Handysize (BHSI): current data, the practical default": "BHSI",
    "Supramax (BSI): the textbook proxy, but dead since 2017": "BSI",
    "Capesize (BCI14): iron ore and coal, not concentrates": "BCI14",
    "Dirty tanker (BIDY): crude, for context only": "BIDY",
    "Clean tanker (BITY): refined products, for context only": "BITY",
}
vessel_label = st.sidebar.selectbox(
    "Vessel class driving S2 shading and the S4 scaler default",
    options=list(vessel_options),
    index=0,
    help="Supramax (BSI) is the textbook freight proxy for concentrates and spodumene "
         "(Cu, Zn, Li), but it stopped reporting in March 2017, nine years before the real "
         "freight validation series even begins. Handysize (BHSI) covers the same parcel "
         "size and is still live, which is why it's the default here. BSI stays selectable "
         "if you want the historically correct answer over the current one.",
)
vessel_choice = vessel_options[vessel_label]

st.sidebar.subheader("S3: proxy validation lead lag")
max_lag = st.sidebar.slider(
    "Max lag for CCF (months)", min_value=3, max_value=12, value=6, step=1,
    help="The brief calls for a weekly lead lag, but every series feeding this section is "
         "only verified monthly (see the caveats above), so cross correlation runs 0 to "
         "this many months instead. Same document the deviation approach as pages 2 and 4.",
)

st.sidebar.subheader("S4: Cu freight-adjusted arb (mirrors page 1)")
cu_vat_rebate = st.sidebar.slider(
    "China VAT rate (import side)", min_value=0.0, max_value=0.30, value=0.13, step=0.01,
    format="%.2f", help="Mirrors page 1's default import VAT slider. See page 1 for the full mechanics.",
)
cu_freight_base = st.sidebar.slider(
    "Base freight, one leg (USD/t)", min_value=0, max_value=150, value=40, step=5,
    help="Mirrors page 1's freight slider default. This is the BASE assumption; only the "
         "freight-ADJUSTED line in S4 moves with the Handysize/Supramax scaler below.",
)
cu_financing_rate = st.sidebar.slider(
    "Financing rate, flat annualized", min_value=0.0, max_value=0.15, value=0.05, step=0.005,
    format="%.3f", help="Mirrors page 1's default.",
)
cu_financing_days = st.sidebar.slider(
    "Financing days", min_value=0, max_value=90, value=30, step=5,
    help="Mirrors page 1's default.",
)

st.sidebar.subheader("S4: Li freight leg (mirrors page 2)")
li_freight_base = st.sidebar.slider(
    "Assumed baseline Australia to China spodumene ocean freight (USD/t)", min_value=0, max_value=150, value=30, step=5,
    help="A single assumed number, used only to build the Baltic scaled predicted freight "
         "line you'll compare against the real observed CIF/FOB freight leg in S4. This "
         "baseline is a guess. The CIF/FOB comparator next to it is observed data.",
)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
raw, converted, warnings = udata.get_dataset(tuple(ALL_TICKERS))

# All Baltic series resampled onto one canonical month-end ('ME') grid before
# anything is merged/compared — panels from different vendors stamp
# month-end dates a day or two apart (e.g. business-day '29' vs calendar
# '30'), which silently drops most rows under a raw pd.concat().dropna().
# `utils.data.resample_monthly` (.resample('ME').last().ffill()) is the
# same explicit-resample idiom every prior page uses for mixed panels.
baltic_m: dict[str, pd.Series] = {}
for tk in ["BDIY"] + VESSEL_TICKERS:
    if tk in converted and not converted[tk].dropna().empty:
        baltic_m[tk] = udata.resample_monthly(converted[tk])

regimes: dict[str, pd.DataFrame] = {
    tk: ufin.freight_regime(s, window=regime_window) for tk, s in baltic_m.items()
}

implied_freight_real = None
if require(converted, ["L4CNSPAU", "LCBMAUSF"], "S1/S3 (real implied freight)"):
    cif_m = udata.resample_monthly(converted["L4CNSPAU"])
    fob_m = udata.resample_monthly(converted["LCBMAUSF"])
    fdf = pd.concat({"cif": cif_m, "fob": fob_m}, axis=1, sort=True).dropna()
    if not fdf.empty:
        implied_freight_real = (fdf["cif"] - fdf["fob"]).rename("implied_freight_real")

vessel_series_m = baltic_m.get(vessel_choice)
baseline_default_ref = None  # set once the date range is known, below

# ---------------------------------------------------------------------------
# S1 — Header + KPI
# ---------------------------------------------------------------------------
st.title("Freight Overlay")
st.caption(
    "Freight isn't just a cost line, it can flip an arb open or closed on its own. This page "
    "reads the freight regime across Baltic vessel classes and feeds it back into the Cu, Li "
    "and Zn pages as a signal and a slider scaler."
)

st.warning(
    "`BDIY`, `BCI14`, `BSI`, `BHSI`, `BIDY` and `BITY` are unitless **index points**, "
    "not USD/t on any named route. Don't read them as freight rates. They enter this app two "
    "ways only: as a **regime signal** (rolling percentile and z score, still in index "
    "points, S1/S2), and as a unitless **scaler** applied to the USD/t freight sliders "
    "already sitting in pages 1, 2 and 4 (S4). The only real dollar freight series anywhere "
    "in this app is the Li CIF/FOB spread (`L4CNSPAU` minus `LCBMAUSF`, S3), and it exists to "
    "validate the Baltic proxy, not to be replaced by it."
)

if warnings:
    with st.expander(f"⚠ {len(warnings)} data warning(s)", expanded=True):
        for w in warnings:
            st.markdown(f"- {w}")


# global date range, bounded by whatever data we actually have
all_dates = [s.dropna().index for s in baltic_m.values()]
if implied_freight_real is not None:
    all_dates.append(implied_freight_real.dropna().index)
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


if baseline_mode == "fixed":
    ref_date_input = st.sidebar.slider(
        "Reference date (fixed baseline)",
        min_value=data_min.to_pydatetime(), max_value=data_max.to_pydatetime(),
        value=default_start.to_pydatetime(), format="YYYY-MM-DD",
        help="`freight_scaler` = index level / index level observed on this date.",
    )
    ref_date = pd.Timestamp(ref_date_input)
else:
    ref_date = None

baseline = (
    ufin.freight_baseline(vessel_series_m, mode=baseline_mode, window=regime_window, ref_date=ref_date)
    if vessel_series_m is not None else None
)
scaler_m = (
    ufin.freight_scaler(vessel_series_m, baseline)
    if vessel_series_m is not None and baseline is not None else None
)

# --- S1 KPI row 1: BDI composite + real implied freight ---------------------
kpi1 = st.columns(4)
bdi_val, bdi_delta = latest_metric(baltic_m.get("BDIY"), "{:,.0f} pts")
kpi1[0].metric("Baltic Dry Index (BDIY, composite)", bdi_val, bdi_delta, delta_color="off")

bdi_regime_df = regimes.get("BDIY")
if bdi_regime_df is not None and not bdi_regime_df["regime"].dropna().empty:
    row = bdi_regime_df.dropna(subset=["regime"]).iloc[-1]
    kpi1[1].metric("BDI regime (trailing pctile)", row["regime"],
                    f"{row['pctile']:.0f}th pctile", delta_color="off")
else:
    kpi1[1].metric("BDI regime (trailing pctile)", "n/a")

vessel_regime_df = regimes.get(vessel_choice)
if vessel_regime_df is not None and not vessel_regime_df["regime"].dropna().empty:
    row = vessel_regime_df.dropna(subset=["regime"]).iloc[-1]
    kpi1[2].metric(f"{VESSEL_SHORT[vessel_choice]} regime ({vessel_choice}, selected proxy)",
                    row["regime"], f"as of {vessel_regime_df.dropna(subset=['regime']).index[-1].date()}",
                    delta_color="off")
else:
    kpi1[2].metric(f"{VESSEL_SHORT.get(vessel_choice, vessel_choice)} regime", "n/a")

li_val, li_delta = latest_metric(implied_freight_real, "${:,.0f}/t")
kpi1[3].metric("Spod implied freight (real, CIF FOB, Australia to China)", li_val, li_delta, delta_color="off")

# --- S1 KPI row 2: one regime read per vessel class -------------------------
kpi2 = st.columns(5)
for i, tk in enumerate(VESSEL_TICKERS):
    rdf = regimes.get(tk)
    if rdf is not None and not rdf["regime"].dropna().empty:
        valid = rdf.dropna(subset=["regime"])
        row = valid.iloc[-1]
        kpi2[i].metric(f"{VESSEL_SHORT[tk]} ({tk})", row["regime"],
                        f"as of {valid.index[-1].date()}", delta_color="off")
    else:
        kpi2[i].metric(f"{VESSEL_SHORT[tk]} ({tk})", "n/a")
st.caption(
    "The date next to each reading is the observation date, not today. Supramax (BSI) will "
    "still show March 2017 here; everything else is current through June 2026."
)

st.divider()

# ---------------------------------------------------------------------------
# S2 — Freight regime panel (all 6 indices, one chart)
# ---------------------------------------------------------------------------
st.header("S2 -- Freight regime panel")
st.markdown(
    "All six Baltic indices, **rebased to 100 at the selected window's start** so vessel "
    "classes with very different absolute point levels sit on one comparable chart. "
    f"The shading marks the **{VESSEL_SHORT.get(vessel_choice, vessel_choice)} ({vessel_choice})** "
    "regime picked in the sidebar. Green means freight is cheap and the arb has room to "
    "breathe; red means freight is rich enough to eat the margin."
)
st.markdown(
    "**The vessel to commodity map is the real point of this page.** Capesize carries iron "
    "ore, coal and large dry bulk cargoes; it tracks macro bulk demand, not concentrates, so "
    "treat it as context only. Supramax carries base metal concentrates (Cu, Zn), spodumene "
    "and minor bulk, making it the primary proxy for pages 1, 2 and 4, even though it's stale "
    "here. Handysize carries smaller concentrate and spodumene parcels plus minor bulk; it's "
    "the secondary proxy on paper and the one you can actually trust today. Dirty tankers move "
    "crude and clean tankers move refined products; both are context only, since nothing in "
    "this app prices crude or products directly."
)

fig_regime = go.Figure()
for tk in ["BDIY"] + VESSEL_TICKERS:
    s = clip(baltic_m.get(tk, pd.Series(dtype=float))).dropna()
    if s.empty:
        continue
    rebased = (s / s.iloc[0]) * 100.0
    label = "BDIY (composite)" if tk == "BDIY" else f"{VESSEL_SHORT[tk]} ({tk})"
    fig_regime.add_trace(go.Scatter(x=rebased.index, y=rebased.values, name=label, line=dict(color=VESSEL_COLOR[tk])))
if vessel_regime_df is not None:
    vdf_c = vessel_regime_df.loc[(vessel_regime_df.index >= start_date) & (vessel_regime_df.index <= end_date)]
    add_regime_shading(fig_regime, vdf_c["regime"] == "LOW", color="LightGreen", opacity=0.2)
    add_regime_shading(fig_regime, vdf_c["regime"] == "HIGH", color="Crimson", opacity=0.15)
fig_regime.add_hline(y=100, line_dash="dot", line_color="gray")
fig_regime.update_layout(
    title=f"Baltic vessel-class indices, rebased to 100 at window start (shaded = {VESSEL_SHORT.get(vessel_choice, vessel_choice)} regime)",
    yaxis_title="index (100 = window start)", xaxis_title="date", hovermode="x unified",
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig_regime, width="stretch")

if vessel_choice == "BSI":
    st.warning(
        "Supramax (`BSI`) stopped reporting in March 2017 in this dataset. Pick a recent "
        "date range and the shading above simply stops; it won't extend into the current window.",
    )

st.divider()

# ---------------------------------------------------------------------------
# S4 — Freight-adjusted arb sensitivity
# ---------------------------------------------------------------------------
st.header("S3 -- Freight-adjusted arb sensitivity")
st.markdown(
    f"`freight_scaler = {vessel_choice} / baseline` ({baseline_mode_label.lower()}), applied to "
    "the existing freight sliders already in pages 1 and 2 through `utils.finance.freight_adjusted_cost`."
)

st.subheader("Cu: import margin at base freight vs freight-scaled freight (mirrors page 1)")
if scaler_m is not None and require(converted, ["CECNVXAQ", "LMCADY", "CECN0002"], "S4 (Cu leg)"):
    cu_m = pd.concat({
        "shfe": udata.resample_monthly(converted["CECNVXAQ"]),
        "lme": udata.resample_monthly(converted["LMCADY"]),
        "yangshan": udata.resample_monthly(converted["CECN0002"]),
        "scaler": scaler_m,
    }, axis=1, sort=True).dropna()
    if not cu_m.empty:
        cu_m = cu_m.loc[(cu_m.index >= start_date) & (cu_m.index <= end_date)]
    if not cu_m.empty:
        financing_cu = ufin.financing_cost(cu_m["lme"], cu_financing_rate, cu_financing_days)
        cu_m["margin_base"] = ufin.import_margin(cu_m["shfe"], cu_m["lme"], cu_m["yangshan"], cu_freight_base, financing_cu, cu_vat_rebate)
        cu_m["freight_adj"] = ufin.freight_adjusted_cost(cu_freight_base, cu_m["scaler"])
        cu_m["margin_adj"] = ufin.import_margin(cu_m["shfe"], cu_m["lme"], cu_m["yangshan"], cu_m["freight_adj"], financing_cu, cu_vat_rebate)
        cu_m["flip"] = (cu_m["margin_base"] > 0) != (cu_m["margin_adj"] > 0)

        fig_cu = go.Figure()
        fig_cu.add_trace(go.Scatter(x=cu_m.index, y=cu_m["margin_base"], name=f"Base freight (${cu_freight_base}/t flat)", line=dict(color="#7f7f7f", dash="dash")))
        fig_cu.add_trace(go.Scatter(x=cu_m.index, y=cu_m["margin_adj"], name=f"Freight-scaled ({VESSEL_SHORT[vessel_choice]} scaler)", line=dict(color="#1f77b4")))
        fig_cu.add_hline(y=0, line_dash="dot", line_color="gray")
        add_regime_shading(fig_cu, cu_m["flip"], color="Orange", opacity=0.25)
        fig_cu.update_layout(
            title="Cu import margin, base freight vs freight-scaled (shading marks the arb flipping open or closed)",
            yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig_cu, width="stretch")

        latest_cu = cu_m.dropna(subset=["margin_base", "margin_adj"])
        if not latest_cu.empty:
            row = latest_cu.iloc[-1]
            delta = row["margin_adj"] - row["margin_base"]
            st.metric(
                "Latest freight-scaling impact on Cu import margin", f"${delta:+,.0f}/t",
                f"as of {latest_cu.index[-1].date()}", delta_color="off",
                help="The freight-adjusted margin minus the base margin at the latest common "
                     "date. Freight alone is the swing factor that can flip this arb open or "
                     "closed with nothing else in the trade changing at all.",
            )
    else:
        st.caption("No overlapping dates between the Cu leg and the selected vessel scaler in this window.")
else:
    st.caption("The Cu freight leg is unavailable (a ticker or the vessel scaler is missing), so this panel is skipped.")


st.subheader("Al: freight matters less here (light touch)")
st.info(
    "Aluminium regional premia (`AMEUDDP` Rotterdam duty paid, `AUP1` US Midwest) are, per "
    "page 3, dominated by carry economics: LME contango, financing, warehouse rent, plus duty "
    "and Section 232 tariffs. `premium_fair_value()` has no ocean-freight term in it to scale "
    "in the first place. Scaling the Al page the way Cu and Li are scaled above would dress up "
    "a genuinely minor lever as a major one, so it's noted here rather than modeled, matching "
    "the brief's explicit light touch scope for aluminium.",
)

st.divider()

# ---------------------------------------------------------------------------
# S5 — Cross-commodity freight dashboard
# ---------------------------------------------------------------------------
st.header("S4 -- Cross-commodity freight dashboard")
st.markdown("The freight state of the whole physical complex at a glance, small multiples, each linked to the page it feeds.")

dash_specs = [
    ("BDIY", "Composite dry bulk, the overall regime signal", None),
    ("BCI14", "Iron ore, coal, large dry bulk (context only)", None),
    ("BSI", "Cu/Zn concentrates and spodumene, the primary proxy (stale)", ["1_Copper_East_West", "2_Lithium_Conversion_Margin", "4_Zinc_Smelter_Margin"]),
    ("BHSI", "Smaller concentrate and spodumene parcels, the practical default proxy", ["1_Copper_East_West", "2_Lithium_Conversion_Margin", "4_Zinc_Smelter_Margin"]),
    ("BIDY", "Crude (context only)", None),
    ("BITY", "Refined products (context only)", None),
]
PAGE_LABELS = {
    "1_Copper_East_West": "Page 1: Copper East West",
    "2_Lithium_Conversion_Margin": "Page 2: Lithium Conversion Margin",
    "4_Zinc_Smelter_Margin": "Page 4: Zinc Smelter Margin",
}

row1 = st.columns(3)
row2 = st.columns(3)
for slot, (tk, note, pages) in zip(row1 + row2, dash_specs):
    with slot:
        s = clip(baltic_m.get(tk, pd.Series(dtype=float))).dropna()
        label = "BDIY (composite)" if tk == "BDIY" else f"{VESSEL_SHORT[tk]} ({tk})"
        st.markdown(f"**{label}**")
        st.caption(note)
        rdf = regimes.get(tk)
        if s.empty:
            st.caption("unavailable")
        else:
            fig_mini = go.Figure(go.Scatter(x=s.index, y=s.values, line=dict(color=VESSEL_COLOR[tk]), showlegend=False))
            if rdf is not None:
                rdf_c = rdf.loc[(rdf.index >= start_date) & (rdf.index <= end_date)]
                add_regime_shading(fig_mini, rdf_c["regime"] == "HIGH", color="Crimson", opacity=0.15)
                add_regime_shading(fig_mini, rdf_c["regime"] == "LOW", color="LightGreen", opacity=0.15)
            fig_mini.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="pts")
            st.plotly_chart(fig_mini, width="stretch")
        if pages:
            for p in pages:
                st.page_link(f"pages/{p}.py", label=f"→ {PAGE_LABELS[p]}", icon="🔗")

st.divider()

# ---------------------------------------------------------------------------
# S6 — Macro/FX context (optional, degrades gracefully)
# ---------------------------------------------------------------------------
st.header("S5 -- Macro/FX context (optional, qualitative, clearly secondary)")
st.markdown(
    "Freight against the macro and financing backdrop (`DXY`, `USGGT10Y`) and exporter FX "
    "(`USDZAR` South Africa, `USDRUB` Russia, `USDIDR` Indonesia, plus `AUDUSD`/`EURUSD` for "
    "completeness) as flow cost context. **This is qualitative only: none of it feeds any "
    "calculation on this page or anywhere else in the app.**"
)

bdi_c = clip(baltic_m.get("BDIY", pd.Series(dtype=float))).dropna()
if not bdi_c.empty:
    macro_cols = st.columns(2)
    for col, tk, tk_label in zip(macro_cols, ["DXY", "USGGT10Y"], ["US Dollar Index", "US 10Y yield (%)"]):
        with col:
            if tk in converted and not converted[tk].dropna().empty:
                m = clip(udata.resample_monthly(converted[tk]))
                fig_m = go.Figure()
                fig_m.add_trace(go.Scatter(x=bdi_c.index, y=bdi_c.values, name="BDIY (pts)", line=dict(color="#7f7f7f")))
                fig_m.add_trace(go.Scatter(x=m.index, y=m.values, name=f"{tk_label} ({tk}, right axis)", yaxis="y2", line=dict(color="#1f77b4", dash="dot")))
                fig_m.update_layout(
                    title=f"BDIY vs {tk_label}", yaxis_title="BDIY (pts)", xaxis_title="date",
                    yaxis2=dict(title=tk_label, overlaying="y", side="right"), hovermode="x unified",
                    legend=dict(orientation="h", y=1.1),
                )
                st.plotly_chart(fig_m, width="stretch")
            else:
                st.caption(f"{tk} isn't available here, so this tile is left blank.")

    st.subheader("Exporter FX context")
    fx_cols = st.columns(3)
    fx_specs = [("USDZAR", "South Africa (dry bulk exporter)"), ("USDRUB", "Russia (dry bulk/tanker exporter)"), ("USDIDR", "Indonesia (dry bulk exporter)")]
    for col, (tk, ctx) in zip(fx_cols, fx_specs):
        with col:
            if tk in converted and not converted[tk].dropna().empty:
                fx_s = clip(udata.resample_monthly(converted[tk]))
                fig_fx = go.Figure(go.Scatter(x=fx_s.index, y=fx_s.values, line=dict(color="#9467bd"), showlegend=False))
                fig_fx.update_layout(title=f"{tk}, {ctx}", height=220, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_fx, width="stretch")
            else:
                st.caption(f"{tk} isn't available here, so this tile is left blank.")
else:
    st.caption("BDIY isn't available, so S6 is skipped entirely.")

st.divider()
