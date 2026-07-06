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
st.sidebar.header("Freight Overlay — parameters")

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
    help="'Rolling mean' lets the baseline drift with the prevailing regime over time "
         "(same window as above). 'Fixed reference date' holds one observed index level "
         "flat as the comparison point instead — pick a date in the sidebar below once "
         "data loads.",
)
baseline_mode = "rolling" if baseline_mode_label.startswith("Rolling") else "fixed"

st.sidebar.subheader("Conc/spodumene proxy vessel")
vessel_options = {
    "Handysize (BHSI) — practical default, current through 2026-06": "BHSI",
    "Supramax (BSI) — domain-correct PRIMARY proxy, but STALE (ends 2017-03)": "BSI",
    "Capesize (BCI14) — context only, NOT the conc/spod proxy": "BCI14",
    "Dirty tanker (BIDY) — context only (crude)": "BIDY",
    "Clean tanker (BITY) — context only (refined products)": "BITY",
}
vessel_label = st.sidebar.selectbox(
    "Vessel class driving S2 shading + S4 scaler default",
    options=list(vessel_options),
    index=0,
    help="Per the vessel->commodity map, Supramax (BSI) is the PRIMARY freight proxy for "
         "concentrates/spodumene (Cu, Zn, Li) — but BSI stops 2017-03 in this dataset, "
         "9+ years before the one real freight-validation series here even starts. "
         "Handysize (BHSI) is current and covers the same conc/spod parcel-size segment "
         "per the same map, so it's the practical default; BSI stays selectable for "
         "domain/historical reference.",
)
vessel_choice = vessel_options[vessel_label]

st.sidebar.subheader("S3 — proxy-validation lead-lag")
max_lag = st.sidebar.slider(
    "Max lag for CCF (months)", min_value=3, max_value=12, value=6, step=1,
    help="The brief specifies weekly lead-lag, but every series feeding this section is "
         "verified MONTHLY in this dataset (see caveats) — cross-correlation is computed "
         "0..this many MONTHS instead, same deviation-and-document pattern as pages 2/4.",
)

st.sidebar.subheader("S4 — Cu freight-adjusted arb (mirrors page 1)")
cu_vat_rebate = st.sidebar.slider(
    "China VAT rate (import side)", min_value=0.0, max_value=0.30, value=0.13, step=0.01,
    format="%.2f", help="Mirrors page 1's default import-VAT slider — see page 1 for the full mechanics.",
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

st.sidebar.subheader("S4 — Li freight leg (mirrors page 2)")
li_freight_base = st.sidebar.slider(
    "Assumed baseline AU->China spod ocean freight (USD/t)", min_value=0, max_value=150, value=30, step=5,
    help="An assumed baseline used ONLY to build the Baltic-scaled PREDICTED freight line "
         "compared against the REAL observed CIF-FOB freight leg in S4 — this one number is "
         "indicative, not data; the CIF-FOB comparator itself is observed.",
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
    "Cross-basin freight regime across Baltic vessel classes, mapped to the commodities each "
    "one actually moves, feeding back into pages 1/2/4 as a regime signal + freight-slider scaler."
)

st.warning(
    "**SCOPE LIMIT**: `BDIY`/`BCI14`/`BSI`/`BHSI`/`BIDY`/`BITY` are unitless **index points**, "
    "NOT USD/t on any named route — no Cape C5 / Panamax route USD/t series exists in this "
    "dataset, and none is fabricated here. Freight enters this app as (a) a **regime signal** "
    "(rolling percentile/z-score, still in index points, S1/S2) and (b) a unitless **scaler** "
    "applied to the existing USD/t freight sliders already in pages 1/2/4 (S4) — a dollar "
    "figure only ever re-enters by scaling an EXISTING slider assumption, never a new "
    "fabricated per-route number. The one real dollar-freight series anywhere in this app is "
    "the Li CIF-FOB spread (`L4CNSPAU - LCBMAUSF`, S3), used to validate the Baltic proxy — "
    "never the reverse.",
    icon="⚠️",
)

if warnings:
    with st.expander(f"⚠ {len(warnings)} data warning(s)", expanded=True):
        for w in warnings:
            st.markdown(f"- {w}")

with st.expander("Data caveats found while wiring up this page (see config.py REVISION note)"):
    for tk, note in config.FREIGHT_DATA_CAVEATS.items():
        st.markdown(f"- **{tk}**: {note}")

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
    kpi1[1].metric("BDI regime (trailing pctile)", ufin.freight_regime_badge(row["regime"]),
                    f"{row['pctile']:.0f}th pctile", delta_color="off")
else:
    kpi1[1].metric("BDI regime (trailing pctile)", "n/a")

vessel_regime_df = regimes.get(vessel_choice)
if vessel_regime_df is not None and not vessel_regime_df["regime"].dropna().empty:
    row = vessel_regime_df.dropna(subset=["regime"]).iloc[-1]
    kpi1[2].metric(f"{VESSEL_SHORT[vessel_choice]} regime ({vessel_choice}, selected proxy)",
                    ufin.freight_regime_badge(row["regime"]), f"as of {vessel_regime_df.dropna(subset=['regime']).index[-1].date()}",
                    delta_color="off")
else:
    kpi1[2].metric(f"{VESSEL_SHORT.get(vessel_choice, vessel_choice)} regime", "n/a")

li_val, li_delta = latest_metric(implied_freight_real, "${:,.0f}/t")
kpi1[3].metric("Spod implied freight (real, CIF-FOB AU->China)", li_val, li_delta, delta_color="off")

# --- S1 KPI row 2: one regime badge per vessel class ------------------------
kpi2 = st.columns(5)
for i, tk in enumerate(VESSEL_TICKERS):
    rdf = regimes.get(tk)
    if rdf is not None and not rdf["regime"].dropna().empty:
        valid = rdf.dropna(subset=["regime"])
        row = valid.iloc[-1]
        kpi2[i].metric(f"{VESSEL_SHORT[tk]} ({tk})", ufin.freight_regime_badge(row["regime"]),
                        f"as of {valid.index[-1].date()}", delta_color="off")
    else:
        kpi2[i].metric(f"{VESSEL_SHORT[tk]} ({tk})", "n/a")
st.caption(
    "Dates shown are the OBSERVATION date behind each badge, not today — `BSI` (Supramax) "
    "will read 2017-03 here (stale), everything else 2026-06."
)

st.divider()

# ---------------------------------------------------------------------------
# S2 — Freight regime panel (all 6 indices, one chart)
# ---------------------------------------------------------------------------
st.header("S2 — Freight regime panel")
st.markdown(
    "All six Baltic indices, **rebased to 100 at the selected window's start** so vessel "
    "classes with very different absolute point levels are visually comparable on one chart. "
    f"Shaded: the **{VESSEL_SHORT.get(vessel_choice, vessel_choice)} ({vessel_choice})** regime "
    "selected in the sidebar — green = LOW (cheap freight, arb-friendly), red = HIGH (rich "
    "freight, margin-compressing)."
)
st.markdown(
    "**Vessel -> commodity map** (the domain-knowledge core of this page): "
    "**Capesize** -> iron ore/coal/large dry-bulk (context, macro bulk demand — NOT the conc "
    "proxy). **Supramax** -> base-metal concentrates (Cu, Zn), spodumene, minor bulk — the "
    "PRIMARY proxy for pages 1/2/4, though stale here. **Handysize** -> smaller conc/spod "
    "parcels, minor bulk — the secondary (and here, practical/current) proxy. **Dirty tanker** "
    "-> crude, **Clean tanker** -> refined products (both context only — no crude/products "
    "page in this app)."
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
        "`BSI` (Supramax) is stale in this dataset (ends 2017-03) — the shading above will "
        "not extend into the current window if the selected date range is recent.",
        icon="⚠️",
    )

st.divider()

# ---------------------------------------------------------------------------
# S3 — Proxy validation (credibility anchor — reported as-observed)
# ---------------------------------------------------------------------------
st.header("S3 — Proxy validation: does Baltic track the real dollar freight leg?")
st.markdown(
    "The ONLY real dollar-freight series in this app: `implied_freight_real = L4CNSPAU - "
    "LCBMAUSF` (China CIF spodumene, AU-origin, minus FOB Australia — page 2's S4). Compared "
    "here against `BSI` (Supramax, the map's PRIMARY conc/spod proxy) and `BHSI` (Handysize, "
    "the practical default), both resampled to the same month-end grid, differenced for "
    "stationarity, and run through the same `cross_corr` lead-lag engine pages 1/4 use."
)

if implied_freight_real is not None:
    ifr_c = clip(implied_freight_real)
    fig_val = go.Figure()
    fig_val.add_trace(go.Scatter(x=ifr_c.index, y=ifr_c.values, name="Real implied freight (CIF-FOB, USD/t)", line=dict(color="#2ca02c")))
    for tk in ["BSI", "BHSI"]:
        s = clip(baltic_m.get(tk, pd.Series(dtype=float))).dropna()
        if not s.empty:
            fig_val.add_trace(go.Scatter(x=s.index, y=s.values, name=f"{VESSEL_SHORT[tk]} ({tk}, index pts, right axis)",
                                          yaxis="y2", line=dict(color=VESSEL_COLOR[tk], dash="dot")))
    fig_val.update_layout(
        title="Real implied freight (USD/t) vs Supramax/Handysize (index pts)",
        yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
        yaxis2=dict(title="index points", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_val, width="stretch")

    summary_rows = []
    for tk in ["BSI", "BHSI"]:
        s = baltic_m.get(tk)
        if s is None:
            continue
        pair = pd.concat({"x": implied_freight_real, "y": s}, axis=1, sort=True).dropna()
        n_overlap = len(pair)
        if n_overlap < 5:
            summary_rows.append({"series": f"{VESSEL_SHORT[tk]} ({tk})", "n overlap (months)": n_overlap,
                                  "peak lag (months)": None, "peak correlation": None,
                                  "note": "insufficient/zero overlap with the real freight series — cannot be validated in this dataset"})
            continue
        x_diff = pair["x"].diff().dropna()
        y_diff = pair["y"].diff().dropna()
        ccf = ufin.cross_corr(x_diff, y_diff, max_lag=min(max_lag, n_overlap // 3))
        lag, corr = ufin.peak_lag(ccf)
        summary_rows.append({"series": f"{VESSEL_SHORT[tk]} ({tk})", "n overlap (months)": n_overlap,
                              "peak lag (months)": lag, "peak correlation": corr, "note": ""})
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

    n_bhsi = len(pd.concat({"x": implied_freight_real, "y": baltic_m.get("BHSI", pd.Series(dtype=float))}, axis=1, sort=True).dropna())
    st.info(
        f"**Reported as-observed, not oversold**: `BSI` has essentially zero temporal overlap "
        f"with `implied_freight_real` in this dataset (BSI ends 2017-03; the CIF-FOB spread "
        f"only starts 2023-09) — it genuinely cannot be validated here. `BHSI` does overlap "
        f"(n={n_bhsi} months) but the correlation is weak and lag-unstable at this sample "
        f"size — this dataset does **not** cleanly confirm 'Baltic tracks real spod freight' "
        f"as a strong empirical result; treat the Baltic scaler in S4 as a reasonable "
        f"*directional* proxy under the vessel-map's domain logic, not as something this "
        f"sample statistically proves. In-sample correlation ≠ causation either way, and "
        f"CIF-FOB embeds insurance/timing basis on top of pure freight.",
        icon="ℹ️",
    )
else:
    st.warning("**S3**: real implied freight unavailable (L4CNSPAU/LCBMAUSF) — section skipped.")

st.divider()

# ---------------------------------------------------------------------------
# S4 — Freight-adjusted arb sensitivity
# ---------------------------------------------------------------------------
st.header("S4 — Freight-adjusted arb sensitivity")
st.markdown(
    f"`freight_scaler = {vessel_choice} / baseline` ({baseline_mode_label.lower()}), applied to "
    "the EXISTING freight sliders already in pages 1 and 2 via `utils.finance.freight_adjusted_cost` "
    "— reusing `import_margin()` from `utils/finance.py` with the adjusted freight argument, not "
    "duplicating the formula."
)

st.subheader("Cu — import margin at base vs freight-scaled freight (mirrors page 1)")
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
            title="Cu import margin: base freight vs freight-scaled (shaded = arb flips OPEN<->CLOSED)",
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
                help="margin_adj - margin_base at the latest common date. Freight is the "
                     "swing factor that can flip an arb open<->closed even with everything "
                     "else unchanged — that's the point of this panel.",
            )
    else:
        st.caption("No overlapping dates between the Cu leg and the selected vessel scaler in this window.")
else:
    st.caption("Cu freight leg unavailable (missing ticker or vessel scaler) — panel skipped.")

st.subheader("Li — Baltic-scaled prediction vs real CIF-FOB freight (mirrors page 2 S4)")
if scaler_m is not None and implied_freight_real is not None:
    li_df = pd.concat({"real": implied_freight_real, "scaler": scaler_m}, axis=1, sort=True).dropna()
    li_df = li_df.loc[(li_df.index >= start_date) & (li_df.index <= end_date)]
    if not li_df.empty:
        li_df["predicted"] = ufin.freight_adjusted_cost(li_freight_base, li_df["scaler"])
        fig_li = go.Figure()
        fig_li.add_trace(go.Scatter(x=li_df.index, y=li_df["real"], name="Real implied freight (CIF-FOB, USD/t)", line=dict(color="#2ca02c")))
        fig_li.add_trace(go.Scatter(x=li_df.index, y=li_df["predicted"], name=f"Baltic-scaled prediction (${li_freight_base}/t baseline x {VESSEL_SHORT[vessel_choice]} scaler)", line=dict(color="#d62728", dash="dash")))
        fig_li.update_layout(
            title="Li spod freight: real (CIF-FOB) vs Baltic-scaled prediction",
            yaxis_title="USD/t", xaxis_title="date", hovermode="x unified",
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig_li, width="stretch")
        st.caption(
            "This is a comparison of an assumed-baseline x Baltic-scaler PREDICTION against "
            "the real observed CIF-FOB spread — not a recomputation of the page-2 converter "
            "margin. Large/persistent divergence here says more about the assumed baseline "
            "and index-basis mismatch (S3 caveats) than about a real freight move."
        )
    else:
        st.caption("No overlapping dates between the real freight leg and the selected vessel scaler in this window.")
else:
    st.caption("Li freight leg unavailable (missing real freight series or vessel scaler) — panel skipped.")

st.subheader("Al — freight less central (light touch)")
st.info(
    "Aluminium regional premia (`AMEUDDP` Rotterdam duty-paid, `AUP1` US Midwest) are, per "
    "page 3, dominated by **carry economics** (LME contango, financing, warehouse rent) plus "
    "duty and Section 232 tariffs — `premium_fair_value()` has no explicit ocean-freight term "
    "to scale in the first place. Freight-scaling the Al page the way Cu/Li are scaled above "
    "would therefore misrepresent a genuinely minor lever as a major one — noted here, not "
    "modeled, per the brief's explicit 'light touch' scope for aluminium.",
    icon="ℹ️",
)

st.divider()

# ---------------------------------------------------------------------------
# S5 — Cross-commodity freight dashboard
# ---------------------------------------------------------------------------
st.header("S5 — Cross-commodity freight dashboard")
st.markdown("One-glance freight state of the physical complex, small-multiples, each linked to the page it feeds.")

dash_specs = [
    ("BDIY", "Composite dry-bulk — overall regime signal", None),
    ("BCI14", "Iron ore, coal, large dry-bulk (context only)", None),
    ("BSI", "Cu/Zn concentrates, spodumene — PRIMARY proxy (STALE)", ["1_Copper_East_West", "2_Lithium_Conversion_Margin", "4_Zinc_Smelter_Margin"]),
    ("BHSI", "Smaller conc/spod parcels — practical default proxy", ["1_Copper_East_West", "2_Lithium_Conversion_Margin", "4_Zinc_Smelter_Margin"]),
    ("BIDY", "Crude (context only)", None),
    ("BITY", "Refined products (context only)", None),
]
PAGE_LABELS = {
    "1_Copper_East_West": "Page 1 — Copper East-West",
    "2_Lithium_Conversion_Margin": "Page 2 — Lithium Conversion Margin",
    "4_Zinc_Smelter_Margin": "Page 4 — Zinc Smelter Margin",
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
st.header("S6 — Macro/FX context (optional, qualitative, clearly secondary)")
st.markdown(
    "Freight vs macro/financing backdrop (`DXY`, `USGGT10Y`) and exporter FX (`USDZAR` South "
    "Africa, `USDRUB` Russia, `USDIDR` Indonesia, `AUDUSD`/`EURUSD` for completeness) as flow-cost "
    "context. **Qualitative only — none of this feeds any calc on this page or elsewhere in the "
    "app.**"
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
                st.caption(f"{tk} unavailable — degraded gracefully.")

    st.subheader("Exporter FX context")
    fx_cols = st.columns(3)
    fx_specs = [("USDZAR", "South Africa (dry-bulk exporter)"), ("USDRUB", "Russia (dry-bulk/tanker exporter)"), ("USDIDR", "Indonesia (dry-bulk exporter)")]
    for col, (tk, ctx) in zip(fx_cols, fx_specs):
        with col:
            if tk in converted and not converted[tk].dropna().empty:
                fx_s = clip(udata.resample_monthly(converted[tk]))
                fig_fx = go.Figure(go.Scatter(x=fx_s.index, y=fx_s.values, line=dict(color="#9467bd"), showlegend=False))
                fig_fx.update_layout(title=f"{tk} — {ctx}", height=220, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_fx, width="stretch")
            else:
                st.caption(f"{tk} unavailable — degraded gracefully.")
else:
    st.caption("BDIY unavailable — S6 skipped.")

st.divider()
st.caption(
    "Freight Overlay — page 5 of the Commodity Physical Desk Monitor. See README.md for every "
    "formula, the vessel->commodity map rationale, the scaler logic, and the proxy-validation caveat."
)
