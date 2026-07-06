"""
Arb/spread economics and the cross-correlation (lead-lag) engine.

All formulas here are the textbook physical-copper-desk versions described
in Instructions_COPPER.md. Where a leg is genuinely approximate (freight,
financing rate) that is a UI-exposed slider, not a hard-coded constant —
see pages/1_Copper_East_West.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


# ---------------------------------------------------------------------------
# S2 — SHFE-LME ratio & import breakeven
# ---------------------------------------------------------------------------
def financing_cost(lme_cash: pd.Series, annual_rate: float, days: int) -> pd.Series:
    """Cost of carrying LME-cash-priced metal for `days` days at a flat
    annualized rate, simple interest, ACT/360 (standard commodity-finance
    day-count convention)."""
    return lme_cash * annual_rate * days / 360.0


def breakeven_ratio(
    lme_cash: pd.Series,
    yangshan_premium: pd.Series,
    freight: float,
    financing: pd.Series,
    vat_rebate: float,
) -> pd.Series:
    """SHFE/LME ratio at which importing refined Cu into China is exactly
    breakeven.

    SHFE domestic prices (`CECNVXAQ`/`CECNVGFA`) are quoted **VAT-inclusive**
    ("含税价") — an importer selling into SHFE collects that gross price but
    must remit 13% output VAT to the tax authority, net of whatever input
    VAT credit the import-VAT mechanism allows. So the *net* (ex-VAT)
    revenue from a SHFE sale is `SHFE_price / (1 + vat_rebate)`, not
    `SHFE_price * (1 + vat_rebate)` — dividing strips the VAT back out of
    the gross quoted price; multiplying would double-count it on top of an
    already-gross price. (An earlier revision of this file had this
    backwards — see git history / conversation for the correction.)

        SHFE_price / (1 + vat_rebate) = LME_cash + Yangshan_premium + freight + financing

    => breakeven_ratio = SHFE_price_breakeven / LME_cash
                        = [1 + (Yangshan_premium + freight + financing) / LME_cash] * (1 + vat_rebate)

    Actual ratio > breakeven_ratio => importing is profitable (ARB OPEN).
    """
    return (1.0 + (yangshan_premium + freight + financing) / lme_cash) * (1.0 + vat_rebate)


def import_margin(
    shfe_usd: pd.Series,
    lme_cash: pd.Series,
    yangshan_premium: pd.Series,
    freight: float,
    financing: pd.Series,
    vat_rebate: float,
) -> pd.Series:
    """Import margin in USD/t: net (ex-VAT) revenue from selling the
    imported metal into SHFE, minus everything it cost to land it there.

        margin = SHFE_price/(1+vat_rebate) - LME_cash - Yangshan_premium - freight - financing

    See `breakeven_ratio` docstring for why this divides rather than
    multiplies: SHFE quotes are VAT-inclusive, so dividing recovers the
    net/ex-VAT revenue the importer actually keeps.

    Positive => profitable to import => ARB OPEN.
    """
    return shfe_usd / (1.0 + vat_rebate) - lme_cash - yangshan_premium - freight - financing


# ---------------------------------------------------------------------------
# S2b — Export arb (mirror trade): buy refined Cu domestically off SHFE,
# ship out, sell into LME. The mirror image of the import trade above, with
# one economically important asymmetry: China does NOT grant an export VAT
# rebate for unwrought/refined copper (unlike most manufactured exports) —
# a deliberate policy to discourage raw-metal exports and keep refined
# copper onshore. That means an exporter who buys at the VAT-inclusive SHFE
# price is normally stuck with the *full* VAT-inclusive cost as their basis,
# not the ex-VAT price a full-rebate export would get. `export_vat_rebate`
# models what fraction of that VAT is nonetheless recovered (0 = current
# real-world policy for copper, 1 = a hypothetical full rebate).
# ---------------------------------------------------------------------------
def export_vat_rebate_series(index: pd.DatetimeIndex) -> pd.Series:
    """Time-varying export VAT rebate fraction: 1.0 (fully refunded) before
    `config.EXPORT_VAT_REBATE_CUTOFF`, 0.0 (no refund) from that date on.

    This is a real Chinese policy change, not a slider assumption — China
    eliminated the export VAT rebate for unwrought/refined copper effective
    2024-12-01. Before that date exporters got the VAT embedded in the SHFE
    purchase price refunded on export (same net cost basis as an import);
    from that date on none of it is recovered, so the full VAT-inclusive
    SHFE price becomes the exporter's cost basis. See `export_domestic_cost`.
    """
    cutoff = pd.Timestamp(config.EXPORT_VAT_REBATE_CUTOFF)
    return pd.Series(np.where(index < cutoff, 1.0, 0.0), index=index, name="export_vat_rebate")


def export_domestic_cost(
    shfe_usd: pd.Series, vat_rate: float, export_vat_rebate: float | pd.Series
) -> pd.Series:
    """Effective (VAT-adjusted) cost of acquiring metal domestically off
    SHFE for export, given only `export_vat_rebate` (0-1) of the VAT
    embedded in the quoted SHFE price is recoverable:

        cost = SHFE_price/(1+vat_rate) * [1 + vat_rate*(1 - export_vat_rebate)]

    export_vat_rebate=1 (full rebate) => cost = SHFE_price/(1+vat_rate),
    the ex-VAT price — same net cost basis as the import side.
    export_vat_rebate=0 (no rebate — the real policy for copper) => cost
    = SHFE_price, the full VAT-inclusive price, since none of the VAT paid
    on the domestic purchase is ever recovered.
    """
    return (shfe_usd / (1.0 + vat_rate)) * (1.0 + vat_rate * (1.0 - export_vat_rebate))


def export_margin(
    shfe_usd: pd.Series,
    lme_cash: pd.Series,
    export_freight: float,
    financing: pd.Series,
    vat_rate: float,
    export_vat_rebate: float | pd.Series,
    export_duty: float = 0.0,
) -> pd.Series:
    """Export margin in USD/t: net proceeds from selling into LME minus the
    (VAT-adjusted) cost of buying domestically off SHFE and shipping out.

        margin = LME_cash*(1 - export_duty) - export_freight - financing - export_domestic_cost

    `export_duty` is a placeholder for any export tariff (none is currently
    levied on refined copper cathode specifically; default 0, exposed for
    generality/future extension rather than a known current charge).

    Positive => profitable to export refined Cu out of China => EXPORT ARB OPEN.
    """
    cost = export_domestic_cost(shfe_usd, vat_rate, export_vat_rebate)
    return lme_cash * (1.0 - export_duty) - export_freight - financing - cost


def export_breakeven_ratio(
    lme_cash: pd.Series,
    export_freight: float,
    financing: pd.Series,
    vat_rate: float,
    export_vat_rebate: float | pd.Series,
    export_duty: float = 0.0,
) -> pd.Series:
    """SHFE/LME ratio (`SHFE_USD / LME_cash`) below which exporting is
    profitable — the mirror of `breakeven_ratio`, derived the same way,
    from `export_margin == 0`:

        LME_cash*(1-export_duty) - export_freight - financing
            = SHFE_price_breakeven/(1+vat_rate) * [1 + vat_rate*(1-export_vat_rebate)]

    => export_breakeven_ratio = SHFE_price_breakeven / LME_cash
         = [(1-export_duty) - (export_freight+financing)/LME_cash]
           * (1+vat_rate) / [1 + vat_rate*(1-export_vat_rebate)]

    Actual ratio < export_breakeven_ratio => exporting is profitable
    (SHFE is cheap enough relative to LME to buy domestically and sell
    abroad) — note the inequality flips vs. the import side.
    """
    vat_adj = (1.0 + vat_rate) / (1.0 + vat_rate * (1.0 - export_vat_rebate))
    return ((1.0 - export_duty) - (export_freight + financing) / lme_cash) * vat_adj


def classify_regime(
    margin_value: float,
    marginal_band: float = config.REGIME_MARGINAL_BAND,
    open_label: str = "ARB OPEN",
    closed_label: str = "ARB CLOSED",
    marginal_label: str = "MARGINAL",
) -> str:
    """OPEN / MARGINAL / CLOSED badge from a single margin value (USD/t).
    `marginal_band` is the +/- deadband around zero where the signal isn't
    strong enough to be actionable (transaction costs, data noise). Labels
    are parameterized so the same function serves the import margin
    ("ARB OPEN"/"ARB CLOSED"), the export margin ("EXPORT OPEN"/
    "EXPORT CLOSED"), and page 2's converter margin ("HEALTHY"/"UNDERWATER"/
    "BREAKEVEN") badges."""
    if margin_value is None or (isinstance(margin_value, float) and np.isnan(margin_value)):
        return "UNKNOWN"
    if margin_value > marginal_band:
        return open_label
    if margin_value < -marginal_band:
        return closed_label
    return marginal_label


# ---------------------------------------------------------------------------
# S2 companion signal / S3 backtest
# ---------------------------------------------------------------------------
# `CNMDRCCL` (the market's own implied-import-price series used in the
# first revision of this app) turned out to be broken/mis-scaled on the
# terminal (~$200/t, not a plausible outright price) and has been dropped.
# There is no independent "cost to land" series left, so the S2 import_margin
# (SHFE_USD net of LME cash + Yangshan premium + freight + financing) is the
# arb signal used throughout, including as the S3 backtest's entry trigger
# below.
def ratio_minus_breakeven(ratio: pd.Series, breakeven: pd.Series) -> pd.Series:
    """Unitless companion signal to the USD/t import margin: how far the
    actual SHFE/LME ratio sits above (positive) or below (negative) the
    breakeven ratio. Useful because it's scale-free across price regimes,
    whereas the USD/t margin isn't."""
    df = pd.concat([ratio.rename("ratio"), breakeven.rename("breakeven")], axis=1).dropna()
    return (df["ratio"] - df["breakeven"]).rename("ratio_minus_breakeven")


def threshold_ratio(breakeven_ratio: pd.Series, threshold: float) -> pd.Series:
    """Breakeven ratio scaled up by `threshold` (e.g. 0.05 = breakeven + 5%) —
    a buffer above pure breakeven used as the S3 backtest's entry signal, to
    absorb transaction costs/slippage the core margin calc doesn't model."""
    return breakeven_ratio * (1.0 + threshold)


# ---------------------------------------------------------------------------
# S3 — Threshold backtest (rebuilt: no CNMDRCCL, reuses S2 ratio/breakeven)
# ---------------------------------------------------------------------------
def run_import_backtest(
    df: pd.DataFrame,
    threshold: float,
    hold_days: int,
    max_concurrent: int,
    freight: float,
    financing_rate: float,
    vat_rebate: float,
) -> pd.DataFrame:
    """Backtest the S2 threshold entry signal (SHFE/LME ratio above breakeven
    ratio + `threshold`) as a rolling ladder of import-arb positions, capped
    at `max_concurrent` simultaneously open, each held `hold_days` calendar
    days.

    `df` must carry columns: ratio, breakeven_ratio, shfe_usd, lme_cash,
    yangshan (exactly what S2's `df2`/`df2v` already builds).

    Entries: whenever the signal is on and fewer than `max_concurrent`
    positions are open, one new position opens that day. As long as the
    signal stays on, new positions keep opening whenever a slot frees up
    (a rolling ladder) rather than only once per contiguous signal run.
    Positions still open at the end of the sample are closed (marked) at
    the last available date so no capital is left off the equity curve.

    Two P&L variants per position, both USD/t (one unit, no notional/sizing
    modeled), sharing the same entry-day LME cash / Yangshan / freight cost
    base but differing in how the SHFE sale leg is treated:

    - `hedged_pnl`: the SHFE sale leg is hedged via futures at entry, so the
      margin is locked in the moment the position opens (entry-day SHFE
      price), financed over `hold_days` — realized `hold_days` later
      regardless of what spot does in between.
    - `unhedged_pnl`: the LME purchase leg is fixed at entry (metal is
      bought and shipped) but the SHFE sale leg is left open — physical
      copper is only actually sold into SHFE at the exit date, at whatever
      SHFE price then prevails.

    Returns a DataFrame with columns: entry_date, exit_date, hedged_pnl,
    unhedged_pnl — one row per closed position, unsorted (caller should
    sort by exit_date before cumsum-ing into an equity curve).
    """
    required = ["ratio", "breakeven_ratio", "shfe_usd", "lme_cash", "yangshan"]
    d = df[required].dropna()
    empty = pd.DataFrame(columns=["entry_date", "exit_date", "hedged_pnl", "unhedged_pnl"])
    if d.empty or hold_days <= 0 or max_concurrent <= 0:
        return empty

    signal = (d["ratio"] > threshold_ratio(d["breakeven_ratio"], threshold)).to_numpy()
    dates = d.index
    n = len(d)

    def _close(entry_i: int, exit_i: int) -> dict:
        shfe_entry = d["shfe_usd"].iloc[entry_i]
        shfe_exit = d["shfe_usd"].iloc[exit_i]
        lme_entry = d["lme_cash"].iloc[entry_i]
        yang_entry = d["yangshan"].iloc[entry_i]
        fin = financing_cost(lme_entry, financing_rate, hold_days)
        cost_base = lme_entry + yang_entry + freight + fin
        return {
            "entry_date": dates[entry_i],
            "exit_date": dates[exit_i],
            "hedged_pnl": shfe_entry / (1.0 + vat_rebate) - cost_base,
            "unhedged_pnl": shfe_exit / (1.0 + vat_rebate) - cost_base,
        }

    open_positions: list[dict] = []
    trades: list[dict] = []
    for i in range(n):
        still_open = []
        for pos in open_positions:
            if i >= pos["exit_i"]:
                trades.append(_close(pos["entry_i"], pos["exit_i"]))
            else:
                still_open.append(pos)
        open_positions = still_open

        if signal[i] and len(open_positions) < max_concurrent:
            target = dates[i] + pd.Timedelta(days=hold_days)
            exit_i = int(np.searchsorted(dates.values, target.to_datetime64()))
            exit_i = min(max(exit_i, i + 1), n - 1)
            open_positions.append({"entry_i": i, "exit_i": exit_i})

    for pos in open_positions:
        trades.append(_close(pos["entry_i"], pos["exit_i"]))

    return pd.DataFrame(trades) if trades else empty


# ---------------------------------------------------------------------------
# S4 — Lead-lag engine
# ---------------------------------------------------------------------------
def cross_corr(x: pd.Series, y: pd.Series, max_lag: int = 8) -> pd.DataFrame:
    """Cross-correlation of x against y at lags 0..max_lag, where lag k
    means "x today vs y k periods later" (x leads y by k periods).

    Both inputs should already be stationary (e.g. weekly diff/pct-change)
    and share a compatible index. NaNs are dropped pairwise per lag so a
    gap in one series doesn't zero out the whole window.

    Returns a DataFrame with columns [lag, corr, n_obs].
    """
    x = x.dropna()
    y = y.dropna()
    rows = []
    for lag in range(0, max_lag + 1):
        y_shifted = y.shift(-lag)
        pair = pd.concat([x.rename("x"), y_shifted.rename("y")], axis=1).dropna()
        if len(pair) >= 3:
            corr = pair["x"].corr(pair["y"])
        else:
            corr = np.nan
        rows.append({"lag": lag, "corr": corr, "n_obs": len(pair)})
    return pd.DataFrame(rows)


def peak_lag(ccf: pd.DataFrame) -> tuple[int | None, float | None]:
    """Lag with the largest-magnitude correlation in a cross_corr() table."""
    valid = ccf.dropna(subset=["corr"])
    if valid.empty:
        return None, None
    row = valid.loc[valid["corr"].abs().idxmax()]
    return int(row["lag"]), float(row["corr"])


# ---------------------------------------------------------------------------
# S5 — Scrap discount
# ---------------------------------------------------------------------------
def scrap_discount(cathode_usd_t: pd.Series, scrap_usd_t: pd.Series) -> pd.Series:
    """Scrap discount to cathode, as a fraction of cathode price:

        scrap_discount = (cathode_usd_t - scrap_usd_t) / cathode_usd_t

    `cathode_usd_t` should be `LMCADY` (LME cash), the global refined
    benchmark a US bare-bright scrap processor is actually substituting
    against — NOT `CU1` (SHFE), which is a China-domestic, VAT-inclusive
    quote and has no direct bearing on a US scrap/cathode decision. An
    earlier revision of this page used CU1 here, inherited from a period
    when CU1 was believed to be the COMEX future (a genuinely US-market
    price); once CU1 was corrected to SHFE (see config.py's revision
    note), the formula should have been repointed at a US/global price and
    wasn't — this is that fix.

    Compresses toward 0 (or goes negative) when refined metal is tight and
    scrap gets bid up as a substitute — an alternative tightness gauge to
    the SHFE/LME arb.
    """
    df = pd.concat([cathode_usd_t.rename("cathode"), scrap_usd_t.rename("scrap")], axis=1).dropna()
    return ((df["cathode"] - df["scrap"]) / df["cathode"]).rename("scrap_discount")


# ---------------------------------------------------------------------------
# Page 3 — Aluminium premia / carry economics
#
# `financing_cost()` above (LME cash x annual_rate x days/360) is reused
# as-is for the aluminium carry leg — same ACT/360 day-count convention,
# just applied to LMAHDY instead of LMCADY. Everything below is the
# carry-component-only fair value described in Instructions_AL.md: it
# prices the cost of financing + storing metal forward vs. the contango
# on offer, NOT the full regional premium (duty, freight, and regional
# supply/demand are real components of the actual premium that this
# fair value deliberately excludes — see `premium_fair_value` docstring).
# ---------------------------------------------------------------------------
def contango(lme_3m: pd.Series, lme_cash: pd.Series) -> pd.Series:
    """LME 3M minus cash, USD/t. Positive = contango, negative = backwardation."""
    df = pd.concat([lme_3m.rename("m3"), lme_cash.rename("cash")], axis=1).dropna()
    return (df["m3"] - df["cash"]).rename("contango")


def breakeven_contango(financing: pd.Series | float, warehouse_rent: float) -> pd.Series | float:
    """Contango needed to exactly cover financing + rent — the carry
    breakeven line. Actual contango above this => carry trade viable."""
    return financing + warehouse_rent


def premium_fair_value(financing: pd.Series | float, warehouse_rent: float, contango_: pd.Series) -> pd.Series:
    """Carry-COMPONENT-ONLY fair value of the regional premium, USD/t:

        FV_premium = financing_cost + warehouse_rent - contango

    This is deliberately partial: actual regional premia (Rotterdam DP,
    MW) also embed duty, freight, and regional supply/demand (plus, for
    MW specifically, Section 232 tariffs — see README). `FV_premium`
    prices only the carry piece; the residual (`premium_richness`) is
    where the physical signal lives. Never present FV_premium as if it
    explained the full quoted premium.
    """
    return financing + warehouse_rent - contango_


def carry_pnl(contango_: pd.Series, financing: pd.Series | float, warehouse_rent: float) -> pd.Series:
    """Cash-and-carry trade P&L, USD/t: buy cash metal, sell 3M forward,
    finance and warehouse it for the horizon.

        carry_pnl = contango - financing_cost - warehouse_rent

    Positive => profitable to buy-and-store (the classic 2009-14 LME
    warehouse trade); the metal gets locked away rather than delivered
    to consumers, which is itself part of why regional premia rose during
    that period (see README S4).
    """
    return contango_ - financing - warehouse_rent


def premium_richness(actual_premium: pd.Series, fv_premium: pd.Series) -> pd.Series:
    """actual - FV_premium. Positive ("RICH") => physical S/D and/or
    duty/freight/tariff are pushing the premium above what carry economics
    alone justify. Negative ("CHEAP") => premium is carry-justified or
    below it. This residual, not FV_premium itself, is the physical
    tightness signal."""
    df = pd.concat([actual_premium.rename("actual"), fv_premium.rename("fv")], axis=1).dropna()
    return (df["actual"] - df["fv"]).rename("premium_richness")


def classify_carry_regime(contango_value: float, breakeven_value: float) -> str:
    """Three-way regime badge for the carry trade:

    - `BACKWARDATION`: 3M < cash — no carry trade is possible at all,
      since a forward sale would lock in a loss on the metal leg alone.
    - `CONTANGO-CARRY ATTRACTIVE`: contango exceeds the financing+rent
      breakeven — cash-and-carry is profitable.
    - `NEUTRAL`: contango is positive but doesn't clear the breakeven —
      carry isn't (yet) worth doing.
    """
    if contango_value is None or (isinstance(contango_value, float) and np.isnan(contango_value)):
        return "UNKNOWN"
    if contango_value < 0:
        return "BACKWARDATION"
    if breakeven_value is not None and not (isinstance(breakeven_value, float) and np.isnan(breakeven_value)) and contango_value > breakeven_value:
        return "CONTANGO-CARRY ATTRACTIVE"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Page 2 — Lithium conversion margin (spodumene -> battery-grade Li2CO3)
#
# Chinese converter P&L: buy SC6 (6% Li2O) spodumene concentrate CIF, roast/
# leach/purify it into 99.5% battery-grade Li2CO3, sell the carbonate
# domestically. See Instructions_LITHIUM.md and README.md for the
# stoichiometry rationale behind `conversion_ratio`.
# ---------------------------------------------------------------------------
def converter_margin(
    carbonate_usd: pd.Series,
    spod_usd: pd.Series,
    conversion_ratio: float,
    conv_cost: float,
    grade_pct: float,
    freight_inland: float = 0.0,
    other_cost: float = 0.0,
    reference_grade: float = 6.0,
) -> pd.DataFrame:
    """Indicative converter gross margin, USD/t of Li2CO3 produced.

        effective_ratio    = conversion_ratio * (reference_grade / grade_pct)
        spod_cost_per_t_LC = spod_usd * effective_ratio
        gross_margin       = carbonate_usd - spod_cost_per_t_LC - conv_cost
                              - freight_inland - other_cost

    `conversion_ratio` (t of SC6 concentrate per t of Li2CO3, slider default
    8.0) is quoted at the `reference_grade` (6% Li2O, the grade every series
    on this page is benchmarked at). If the concentrate grade actually traded
    differs from 6%, `effective_ratio` scales it up/down: a lower-grade
    concentrate has less Li2O per tonne, so proportionally more tonnes of
    concentrate are needed per tonne of carbonate output, and vice versa.

    Pre-by-product, pre-tax, indicative only — see README "Core economics"
    for the stoichiometric derivation of the ~7.5-8.5 t/t range and every
    excluded cost (by-products, tax, the LiOH route).

    Returns a DataFrame (aligned, dropna'd) with columns: carbonate_usd,
    spod_usd, effective_ratio, spod_cost, margin.
    """
    df = pd.concat(
        {"carbonate_usd": carbonate_usd, "spod_usd": spod_usd}, axis=1, sort=True
    ).dropna()
    effective_ratio = conversion_ratio * (reference_grade / grade_pct)
    df["effective_ratio"] = effective_ratio
    df["spod_cost"] = df["spod_usd"] * effective_ratio
    df["margin"] = (
        df["carbonate_usd"] - df["spod_cost"] - conv_cost - freight_inland - other_cost
    )
    return df


# ---------------------------------------------------------------------------
# Page 4 — Zinc Smelter Margin (China custom smelter, conc -> SHG zinc)
#
# TC benchmarks are quoted USD/dmt of CONCENTRATE, not per tonne of
# contained metal — see Instructions_ZINC.md "CORE ECONOMICS". Converting
# between the two requires the concentrate grade and the smelter's
# metallurgical recovery: a tonne of 50%-grade concentrate contains 0.50 t
# of contained Zn, of which only `recovery` (~95.5%) is actually recovered
# as payable metal, so `zn_per_dmt_conc = grade * recovery` tonnes of
# payable zinc are extracted per dmt of concentrate treated. Getting this
# backwards (dividing metal by TC instead of TC by zn_per_dmt_conc, or
# skipping the recovery factor) is exactly the kind of error that reads as
# "didn't understand the business" — see README "Core economics" for the
# worked numeric example.
# ---------------------------------------------------------------------------
def zinc_per_dmt_conc(grade: float, recovery: float) -> float:
    """Tonnes of payable Zn metal recovered per dmt of concentrate treated."""
    return grade * recovery


def tc_per_tonne_zinc(tc_per_dmt_conc: pd.Series | float, grade: float, recovery: float) -> pd.Series | float:
    """Convert a TC benchmark quoted USD/dmt CONCENTRATE to USD/t of
    contained/payable METAL: `TC_per_t_zinc = TC_per_dmt_conc / (grade * recovery)`.
    Dividing (not multiplying) is what actually up-scales a per-concentrate
    charge into a per-metal-tonne charge, since each dmt of concentrate only
    yields `grade * recovery` tonnes of payable metal."""
    return tc_per_dmt_conc / zinc_per_dmt_conc(grade, recovery)


def free_metal_participation(
    lme_zinc: pd.Series | float, basis_price: float, participation_pct: float, use_escalator: bool
) -> pd.Series | float:
    """Legacy TC price-participation ("escalator") clause: smelter receives
    an extra `participation_pct` of any LME zinc price above `basis_price`,
    on top of the flat TC. Modern benchmarks are typically negotiated FLAT
    (no escalator) — `use_escalator=False` (participation_pct effectively 0)
    is the default/modern case; toggling it on models the older contract
    style. `max(0, LME - basis) * participation_pct`, floored at zero since
    the clause is one-directional (smelter never pays back if price falls
    below basis)."""
    if not use_escalator:
        return lme_zinc * 0.0 if isinstance(lme_zinc, pd.Series) else 0.0
    return (lme_zinc - basis_price).clip(lower=0.0) * participation_pct if isinstance(lme_zinc, pd.Series) \
        else max(0.0, lme_zinc - basis_price) * participation_pct


def smelter_margin(
    tc_per_dmt_conc: pd.Series,
    lme_zinc: pd.Series,
    grade: float,
    recovery: float,
    basis_price: float,
    participation_pct: float,
    use_escalator: bool,
    by_product_credit: float,
    conv_cost: float,
) -> pd.DataFrame:
    """Indicative China custom-smelter margin, USD/t of zinc metal produced:

        TC_per_t_zinc   = TC_per_dmt_conc / (grade * recovery)
        free_metal      = max(0, LME_zinc - basis_price) * participation_pct   [if escalator on, else 0]
        margin          = TC_per_t_zinc + free_metal + by_product_credit - conv_cost

    `by_product_credit` (sulphuric acid, minor Pb/Ag/Au credits) has no
    public data series backing it in this dataset — it is always a
    sidebar-slider SENSITIVITY, never presented as observed fact (see S7).
    Pre-tax, indicative only — see README "Core economics" for every
    excluded item.

    Returns a DataFrame (aligned, dropna'd) with columns: tc_per_dmt,
    lme_zinc, tc_per_t_zinc, free_metal, by_product_credit, conv_cost, margin.
    """
    df = pd.concat(
        {"tc_per_dmt": tc_per_dmt_conc, "lme_zinc": lme_zinc}, axis=1, sort=True
    ).dropna()
    df["tc_per_t_zinc"] = tc_per_tonne_zinc(df["tc_per_dmt"], grade, recovery)
    df["free_metal"] = free_metal_participation(df["lme_zinc"], basis_price, participation_pct, use_escalator)
    df["by_product_credit"] = by_product_credit
    df["conv_cost"] = conv_cost
    df["margin"] = df["tc_per_t_zinc"] + df["free_metal"] + by_product_credit - conv_cost
    return df


def rolling_benchmark_proxy(tc: pd.Series, window: int = 12) -> pd.Series:
    """Trailing rolling-mean proxy for the (unavailable in this dataset)
    negotiated annual TC benchmark — smooths the spot series over `window`
    periods (months, given page 4's verified-monthly data)."""
    return tc.rolling(window, min_periods=max(3, window // 2)).mean().rename("tc_bench_proxy")


def step_annual_benchmark_proxy(tc: pd.Series) -> pd.Series:
    """Alternative annual-benchmark proxy: holds the first observed TC print
    of each calendar year flat through the rest of that year, mimicking how
    real annual TC benchmarks are negotiated once (typically around January)
    and then held fixed for the year, rather than moving with spot."""
    return tc.groupby(tc.index.year).transform("first").rename("tc_bench_proxy")


def zinc_margin_sensitivity_grid(
    tc_per_dmt_range: np.ndarray,
    acid_credit_range: np.ndarray,
    grade: float,
    recovery: float,
    free_metal_snapshot: float,
    conv_cost: float,
) -> pd.DataFrame:
    """2D sensitivity table: indicative smelter margin (USD/t zinc) across a
    grid of TC level (USD/dmt conc, columns) x by-product/acid credit
    (USD/t zinc, rows). `free_metal_snapshot` and `conv_cost` are held fixed
    at their current slider/latest-data values — this table isolates the
    TC x acid-credit sensitivity specifically, since acid credit is the
    single biggest unmodeled lever in the China smelter P&L (see S7)."""
    tc_per_t_zinc = tc_per_dmt_range / zinc_per_dmt_conc(grade, recovery)
    margin_matrix = (
        tc_per_t_zinc[np.newaxis, :] + free_metal_snapshot + acid_credit_range[:, np.newaxis] - conv_cost
    )
    return pd.DataFrame(margin_matrix, index=acid_credit_range, columns=tc_per_dmt_range)


# ---------------------------------------------------------------------------
# Page 5 — Freight Overlay (reusable: importable by pages 1/2/4 for a small
# freight-regime badge — see each page's S1 header).
#
# Baltic indices are unitless INDEX POINTS, not USD/t on any named route —
# no Cape C5/Panamax route USD/t series exists in this dataset (see
# Instructions_FREIGHT.md "SCOPE HONESTY" and config.FREIGHT_DATA_CAVEATS).
# Freight therefore enters the rest of the app two ways, both below: (a) a
# REGIME signal (`freight_regime`, rolling percentile + z-score, still in
# index points) and (b) a unitless SCALER (`freight_scaler`) applied to the
# existing USD/t freight sliders already in pages 1/2/4 — a dollar figure
# only ever re-enters via `freight_adjusted_cost`, which scales an existing
# slider assumption, never fabricates a new one.
# ---------------------------------------------------------------------------
def freight_regime(
    index: pd.Series,
    window: int = config.FREIGHT_REGIME_WINDOW_DEFAULT,
    low_pct: float = config.FREIGHT_LOW_PCT,
    high_pct: float = config.FREIGHT_HIGH_PCT,
) -> pd.DataFrame:
    """Rolling trailing-window percentile + z-score regime transform for a
    Baltic (or any) index-points series.

    `pctile` is the rank of the LATEST observation within its own trailing
    `window` periods (not a whole-sample percentile) — "how rich/cheap is
    freight right now relative to its recent history," which is what a desk
    means by a freight regime, and which stays meaningful even across a
    series whose underlying index base/methodology has shifted over its
    multi-decade history (a trailing window never compares today against a
    1990s base level).

    Returns a DataFrame (index = `index`'s dropna'd dates) with columns:
    value, pctile (0-100), zscore, regime (LOW / NORMAL / HIGH / UNKNOWN).
    LOW = pctile < low_pct, HIGH = pctile > high_pct, else NORMAL; UNKNOWN
    wherever the trailing window doesn't yet have enough observations.
    """
    s = index.dropna()
    if s.empty:
        return pd.DataFrame(columns=["value", "pctile", "zscore", "regime"])
    min_periods = max(6, window // 3)

    def _trailing_pctile(arr: np.ndarray) -> float:
        last = arr[-1]
        return 100.0 * (arr <= last).sum() / len(arr)

    pctile = s.rolling(window, min_periods=min_periods).apply(_trailing_pctile, raw=True)
    roll_mean = s.rolling(window, min_periods=min_periods).mean()
    roll_std = s.rolling(window, min_periods=min_periods).std()
    zscore = (s - roll_mean) / roll_std

    regime = pd.Series(np.where(pctile.isna(), "UNKNOWN", "NORMAL"), index=s.index)
    regime[pctile < low_pct] = "LOW"
    regime[pctile > high_pct] = "HIGH"

    return pd.DataFrame({"value": s, "pctile": pctile, "zscore": zscore, "regime": regime})


FREIGHT_REGIME_BADGE_ICON = {"LOW": "🟢 LOW", "NORMAL": "🟡 NORMAL", "HIGH": "🔴 HIGH", "UNKNOWN": "⚪ UNKNOWN"}


def freight_regime_badge(regime: str | None) -> str:
    """Icon-prefixed label for a `freight_regime()` regime string — shared
    across page 5's own KPI row and the small back-integrated badge on
    pages 1/2/4, so the LOW/NORMAL/HIGH vocabulary and colors stay
    identical everywhere it appears."""
    return FREIGHT_REGIME_BADGE_ICON.get(regime, FREIGHT_REGIME_BADGE_ICON["UNKNOWN"])


def freight_baseline(
    index: pd.Series,
    mode: str = "rolling",
    window: int = config.FREIGHT_REGIME_WINDOW_DEFAULT,
    ref_date: pd.Timestamp | None = None,
) -> pd.Series | float:
    """Baseline level for `freight_scaler`, in one of two user-selectable
    modes (sidebar selector on page 5):

    - `mode="rolling"` (default): trailing rolling mean, `window` periods —
      the baseline itself drifts with the prevailing regime over time.
    - `mode="fixed"`: the single index level observed on/before `ref_date` —
      holds one reference level flat, for "freight vs a specific known
      period" comparisons instead of a moving baseline.

    Returns NaN (fixed mode, no data on/before ref_date) rather than raising —
    callers already guard on empty/NaN series throughout this app.
    """
    s = index.dropna()
    if mode == "fixed":
        if ref_date is None or s.empty:
            return float("nan")
        eligible = s.loc[s.index <= pd.Timestamp(ref_date)]
        return float(eligible.iloc[-1]) if not eligible.empty else float("nan")
    min_periods = max(6, window // 3)
    return s.rolling(window, min_periods=min_periods).mean()


def freight_scaler(index: pd.Series, baseline: pd.Series | float) -> pd.Series:
    """freight_scaler = index / baseline — unitless, computed entirely on
    the Baltic index's OWN history (never mixed with a dollar figure here).
    `baseline` is either a rolling-mean series (`freight_baseline` above,
    reindexed onto `index`'s dates) or a single fixed reference level. A
    zero/NaN baseline yields NaN at that point, not a division error.
    """
    s = index.dropna()
    b = baseline.reindex(s.index) if isinstance(baseline, pd.Series) else pd.Series(baseline, index=s.index)
    return (s / b.replace(0, np.nan)).rename("freight_scaler")


def freight_adjusted_cost(base_freight_usd_t: float, scaler: pd.Series) -> pd.Series:
    """freight_$t_adj = base_freight_$t x freight_scaler — the ONLY point a
    dollar figure re-enters the freight-regime logic. `base_freight_usd_t`
    is an EXISTING $/t slider default already in pages 1/2/4 (not a new
    fabricated per-route dollar freight); this just modulates it by the
    unitless Baltic regime multiplier computed above.
    """
    return (scaler * base_freight_usd_t).rename("freight_adj_usd_t")


def consecutive_below(series: pd.Series, threshold: float, n: int) -> pd.Series:
    """Boolean series, same index as `series`: True at every point that is
    part of a run of >= n consecutive observations strictly below
    `threshold`. Used for page 2's curtailment-risk regime (margin < 0 for
    N consecutive periods) but generic — works on any periodicity, since it
    just counts run-length of a boolean condition rather than assuming a
    calendar frequency.
    """
    below = series < threshold
    run_id = (~below).cumsum()
    run_length = below.groupby(run_id).cumsum()
    return run_length >= n
