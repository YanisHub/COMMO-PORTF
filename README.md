# Commodity Physical Desk Monitor

A multi-page Streamlit app modeling physical-commodity-desk logic: arb
windows, premia lead-lag, and tightness signals. Page 1 is the **Copper
East-West Arb Monitor** — SHFE-LME import arb, Yangshan premium lead-lag
vs SHFE destocking, and a US scrap-discount tightness cross-check. Page 4
is the **Zinc Smelter Margin** monitor — concentrate TC converted into a
China custom-smelter margin cycle, the mirror trader/smelter P&L off one
TC series, a curtailment-risk signal, and an acid-credit sensitivity
check. Page 5 is the **Freight Overlay** monitor — Baltic vessel-class
indices as a cross-basin freight regime signal + a scaler on the freight
assumptions already used in pages 1/4, with a vessel-to-commodity map.

Built for **correctness and clarity over UI polish**: every displayed
number carries an explicit unit, every non-trivial assumption is called
out in the app itself (warning banners) and here.

> **2026-07-04 revision**: a terminal check found this page's first pass
> had gotten a couple of things wrong. `CU1` was assumed to be COMEX,
> quoted USD/lb — it's actually the **SHFE** 1st future, already USD/t.
> `CNMDRCCL`, `CECNWQMM`, and `COPRUSPM` turned out to be broken, stale,
> or otherwise unusable and have been dropped. See "Dropped tickers"
> below and the in-app expander on the page itself.

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

streamlit run streamlit_app.py
```

## Data

Data is read from `data/csv/`, one Bloomberg-export CSV per ticker
(`Date, PX_LAST[, PX_BID, ...]`). The loader (`utils/data.py`) is
ticker-agnostic and:

- warns (doesn't crash) if a ticker's file is missing or unparseable —
  the relevant page section shows "data unavailable: X" and the rest of
  the page still renders;
- tolerates NaN gaps and mixed frequencies (daily/weekly/monthly) per
  ticker;
- fetches `USDCNY` from Yahoo Finance (`yfinance`, ticker `CNY=X`) the
  first time it's needed and caches it to `data/csv/USDCNY.csv` in the
  same `(Date, PX_LAST)` schema as the Bloomberg exports — after that it
  just loads like any other ticker. A sidebar button
  ("🔄 Refresh USDCNY from Yahoo Finance") forces a refetch without
  deleting the file by hand. If there's no network access, the fetch
  fails gracefully with a warning and the FX-dependent series are left
  unconverted (flagged, not silently wrong).

## Data schema & ticker registry

`config.py` is the single source of truth for the ticker → CSV filename
map and unit metadata (`TICKERS` dict). `utils/data.py` and
`utils/finance.py` read from it instead of hard-coding conversions
anywhere else. Every ticker's unit/frequency below has been verified on
the Bloomberg terminal (not just assumed from the field name).

| Ticker | Description | Raw unit | Frequency |
|---|---|---|---|
| `LMCADY` | LME Cu cash | USD/t | daily |
| `LMCADS03` | LME Cu 3M | USD/t | daily |
| `CU1` | **SHFE** Cu 1st future — NOT COMEX | USD/t (already — no lb conversion) | daily |
| `SHFCCOPD` | SHFE Cu deliverable warehouse stocks | t | weekly |
| `SHFCCOPO` | SHFE Cu on-warrant stocks | t | weekly |
| `COMXCOPR` | COMEX Cu warehouse stocks | short tons | daily |
| `CECN0002` | Yangshan premium, warehouse-warrant vs LME spot | USD/t | monthly |
| `CECN0001` | Yangshan premium, B/L vs LME spot | USD/t | monthly |
| `CECNVGFA` | China electrolytic Cu grade 1 incl. SXEW, Shanghai spot (alt SHFE price source) | CNY/t | monthly |
| `CECNVXAQ` | China refined Cu grade 1 99.95% spot (primary SHFE price source) | CNY/t | monthly |
| `CNIVCORE` | China imports Cu ores & concentrates | **thousands of t** (×1000 to reach t) | monthly |
| `CBB1SPOT` | NA #1 Cu bare bright scrap spot | USD/lb | monthly |
| `USDCNY` | CNY spot | CNY per USD, fetched from Yahoo Finance | daily |

### Dropped tickers

Verified broken/stale on the terminal and removed from this page entirely
(see `config.DROPPED_TICKERS` and the in-app expander):

| Ticker | Why dropped |
|---|---|
| `CNMDRCCL` | Implied China import price ex-Chile — values ~$200/t, an order of magnitude below a plausible outright copper price. Broken/mis-scaled, unusable. |
| `CECNWQMM` | China Cu cathode premium, Shanghai — only covers 2015-2018. Stale. |
| `COPRUSPM` | NA #1 Cu bare bright scrap spot (alt source) — stops updating in 2020. Stale. |

**Consequence for the arb logic**: with `CNMDRCCL` gone, S3's "import arb
window" is no longer built from an independent implied-import-price
series — it's rebuilt around the S2 import margin (see below). The scrap
section (S5) uses `CBB1SPOT` only.

## Unit discipline

All conversions live in `utils/data.to_usd_per_tonne()` and read an
explicit `factor` (and `kind`) per ticker from `config.py` — no
magnitude-based guessing. (An earlier revision of this app used a
magnitude-detection heuristic for tickers whose quoting convention hadn't
been verified yet; now that every ticker has been checked on the
terminal, that heuristic was replaced with hard-coded, documented
factors — guessing would only hide a wrong `factor` instead of surfacing
it.)

- `CU1` (SHFE, already USD/t): **factor = 1** — do **NOT** apply the old
  COMEX-style ×2204.62 lb→t conversion. This was the first version's
  central mistake: it assumed `CU1` was COMEX, quoted USD/lb.
- `COMXCOPR` short tons → metric t: **×0.907185**
- `CBB1SPOT` USD/lb → USD/t: **×2204.62**
- `CECNVGFA` / `CECNVXAQ` CNY/t → USD/t: **÷ USDCNY** (same-day, forward-filled)
- `CNIVCORE` thousands of t → t: **×1000**

**Every one of these decisions is surfaced as an in-app note** whenever a
conversion involves an external dependency (FX) or a non-trivial factor —
see the S1 "data warning(s)" expander. A verified factor-1 pass-through
(e.g. `LMCADY`, `CU1`) isn't flagged as a banner since there's no
assumption left to surface; the ticker table above documents it instead.

## S1/S2 formulas — header KPIs, SHFE-LME ratio & import breakeven

```
SHFE_USD = <selected source> / USDCNY   # CECNVXAQ (default) or CECNVGFA, CNY/t -> USD/t
ratio     = SHFE_USD / LMCADY
```

The SHFE price source is a **sidebar selector** (`CECNVXAQ` primary,
`CECNVGFA` as an alternate cross-check) — every chart downstream of
`SHFE_USD` (S1-S4) uses whichever is selected, labeled in the chart
titles.

Import breakeven: importing refined Cu into China is profitable when

```
SHFE_price / (1 + vat_rebate) >= LME_cash + Yangshan_premium + freight + financing
```

**Why divide, not multiply**: SHFE domestic quotes (`CECNVXAQ`/`CECNVGFA`)
are **VAT-inclusive** ("含税价") — an importer selling into SHFE collects
the gross quoted price but must remit output VAT to the tax authority.
Dividing by `(1 + vat_rebate)` strips that VAT back out of the gross
quote to get the net revenue the importer actually keeps. (An earlier
revision of this app had this backwards — multiplying by `(1+vat_rebate)`
on top of an already-gross, VAT-inclusive price effectively double-counted
the VAT, which inflated the import margin roughly 17x over: a $200/t
breakeven-ish margin showed up as +$3,487/t. Multiplying would be correct
if `SHFE_price` were quoted **ex-VAT** — it isn't.)

Rearranged to a breakeven ratio (`utils.finance.breakeven_ratio`):

```
breakeven_ratio = [1 + (Yangshan_premium + freight + financing) / LME_cash] * (1 + vat_rebate)
```

Actual `ratio > breakeven_ratio` ⇒ ARB OPEN (shaded green in the chart).

Import margin, USD/t (`utils.finance.import_margin`):

```
margin = SHFE_USD / (1 + vat_rebate) - LME_cash - Yangshan_premium - freight - financing
```

- **`vat_rebate`** (sidebar slider, default 13%): China levies a 13%
  import VAT on refined copper. The rebate *mechanics* (how much of that
  VAT is actually recoverable, and under what import/bonded-warehouse
  regime) are more nuanced than a flat rate and vary by importer status
  — this is an **import VAT** treatment, explicitly **not** an
  export-VAT-rebate (a different, commonly-conflated mechanism in trade
  commentary — see S2b for the export side). Treat the slider as an
  approximation of the net VAT drag, not a precise customs computation.
- **`freight`** (sidebar slider, default $40/t): flat indicative
  freight, shared between the import leg (S2, origin → China) and the
  export leg (S2b, China → destination) — real freight isn't actually
  symmetric between the two directions, but this keeps the UI simple.
- **`financing`** = `LME_cash × financing_rate × financing_days / 360`
  (`utils.finance.financing_cost`) — flat annualized LIBOR/SOFR-proxy rate
  (sidebar slider, default 5%) × days of carry (sidebar slider, default
  30), ACT/360 day count. No real interest-rate series is used —
  indicative only, both exposed as sliders per the brief.

The S1 KPI row (LME cash, SHFE cathode USD, import margin, Yangshan
warrant premium, regime badge) reads directly off this S2 calculation —
there's no separate KPI-only computation path.

**FX-source flag**: `SHFE_USD` depends on `USDCNY`, which is sourced from
**Yahoo Finance**, not Bloomberg. Every chart that depends on `SHFE_USD`
is downstream of that FX source — flagged once, prominently, in S1.

## S2b — Export arb (mirror trade)

The reverse physical trade: buy refined copper domestically off SHFE,
ship it out, and sell into LME. This mirrors S2's structure but with one
economically important asymmetry, which is why it isn't just
`-import_margin`:

**China grants no export VAT rebate for unwrought/refined copper.** Most
manufactured Chinese exports get some or all of their input VAT refunded
on export (the standard "zero-rated export" mechanism) — but refined
copper cathode is specifically excluded, a deliberate policy to
discourage raw-metal exports and keep copper onshore for domestic
manufacturing. That means an exporter who buys at the VAT-inclusive SHFE
price is normally stuck with that **full gross price** as their cost
basis, not the ex-VAT price a fully-rebated export would get.

`utils.finance.export_domestic_cost` models this on a sliding scale via
`export_vat_rebate` (0-1, sidebar slider, **default 0%** = current real
policy for copper; 100% = a hypothetical full-rebate regime):

```
export_domestic_cost = SHFE_USD/(1+vat_rebate) * [1 + vat_rebate*(1 - export_vat_rebate)]
```

At `export_vat_rebate=1` this collapses to `SHFE_USD/(1+vat_rebate)` (the
same ex-VAT cost basis as the import side); at `export_vat_rebate=0` (the
default) it collapses to `SHFE_USD` (full VAT-inclusive price, no relief).

Export margin, USD/t (`utils.finance.export_margin`):

```
export_margin = LME_cash*(1 - export_duty) - freight - financing - export_domestic_cost
```

Export breakeven ratio (`utils.finance.export_breakeven_ratio`, mirroring
`breakeven_ratio`):

```
export_breakeven_ratio = [(1-export_duty) - (freight+financing)/LME_cash] * (1+vat_rebate) / [1 + vat_rebate*(1-export_vat_rebate)]
```

Actual `ratio < export_breakeven_ratio` ⇒ exporting is profitable — note
the inequality **flips** relative to the import side (exporting wants
SHFE cheap relative to LME, not rich). `export_duty` is a placeholder
slider (default 0%) for any export tariff; none is currently known/levied
on refined copper cathode specifically, so it's exposed for generality
rather than modeling a known charge. `financing` reuses the same rate/days
sliders as S2, applied to the SHFE-based cost (the capital actually tied
up buying domestically) rather than LME cash.

Import and export arb are, by construction (ignoring transaction costs),
mutually exclusive — the ratio can't simultaneously clear the import
breakeven (above) and the export breakeven (below) at once. Seeing both
regimes CLOSED simultaneously is the normal/expected state: it just means
the ratio sits in the no-arb band between the two breakevens.

## S3 — Import arb window (rebuilt, no `CNMDRCCL`)

With the implied-import-price series (`CNMDRCCL`) dropped as broken,
there's no independent "cost to land" series left to build a separate
arb signal from. S3 reuses the S2 import margin directly:

```
import_arb = import_margin
```

Positive ⇒ profitable to import ⇒ expect the Yangshan premium to rise and
SHFE stocks to fall with a lag (tested in S4). Zero-crossings are marked
on the chart as open/close signals. A second, unitless companion chart
(`utils.finance.ratio_minus_breakeven`) shows `ratio - breakeven_ratio`,
which is comparable across price regimes in a way the USD/t margin isn't.

## S4 — Lead-lag engine (`utils.finance.cross_corr`)

Tests: **arb opens → Yangshan premium spikes 2-4 weeks later → SHFE stocks
destock.**

- `import_arb` and the target series (`CECN0002`, `SHFCCOPD`, and
  optionally `SHFCCOPO` — sidebar checkbox, on by default, a tighter
  "readily deliverable" proxy than total deliverable stocks) are
  resampled to weekly (`utils.data.resample_weekly`, forward-filling
  lower-frequency inputs onto the weekly grid) and then differenced to
  make them stationary.
- `cross_corr(x, y, max_lag)` computes `corr(x_t, y_{t+lag})` for
  `lag = 0..max_lag` (sidebar slider, default 8 weeks): lag *k* means "x
  today vs. y *k* weeks later," i.e. **x leads y by k weeks**. NaNs are
  dropped pairwise per lag, not globally, so a gap in one series doesn't
  zero out the whole window.
- The peak-magnitude lag/correlation is reported in a summary table
  (`utils.finance.peak_lag`) for each target series: expected sign
  **positive** for the Yangshan-premium CCF (arb opening should
  coincide with/precede a premium spike), expected sign **negative** for
  the stock CCFs (arb opening should precede destocking).

**Caveat, stated in-app**: this is in-sample correlation on a limited
history, not a proven causal relationship. Peak-lag estimates are
sensitive to the sample window, resampling choice, and the stationarity
transform. Treat it as a starting hypothesis for desk review, not a
mechanical trading signal.

## S5 — Scrap discount (tightness alt-signal, monthly)

```
scrap_discount = (CU1_usd_t - scrap_usd_t) / CU1_usd_t
```

`CBB1SPOT` (NA #1 bare-bright scrap, USD/lb → USD/t) is natively
**monthly**. `CU1` (SHFE, daily, already USD/t) is resampled to
month-end (`utils.data.resample_monthly`) to align — this is an explicit
resample, stated in the UI, not a silent frequency mismatch. When refined
copper is tight, scrap gets bid up as a cathode substitute and the
discount compresses (or goes negative) — an alternative, US-sourced
tightness gauge to the China-based SHFE/LME arb. Bare-bright scrap and
SHFE cathode are imperfect substitutes (grade, logistics, financing
differ), so this is a directional cross-check, not a directly tradeable
arb. `scrap_discount` is also run through the same `cross_corr` lead-lag
engine against `import_arb`, both resampled to monthly — the UI reports
the observation count at the peak lag and states explicitly that this is
a small-sample result (short history × monthly frequency), not a
statistically robust one.

## S6 — Stocks panel

`SHFCCOPD` (SHFE deliverable, tonnes), `SHFCCOPO` (SHFE on-warrant,
tonnes), and `COMXCOPR` (COMEX, short tons × 0.907185 → metric tonnes)
plotted on a dual axis, with the S3 arb-open shading overlaid to visually
check whether destocking follows the arb signal. An optional secondary
panel (checkbox) shows `CNIVCORE` (China Cu ore & concentrate imports,
×1000 → t, monthly) as demand-pull context.

## Regime badge

`utils.finance.classify_regime(margin)`: `margin > +20` USD/t ⇒ **ARB
OPEN**, `margin < -20` ⇒ **ARB CLOSED**, otherwise **MARGINAL** (deadband
absorbs data noise/transaction-cost friction around zero). The S1 KPI
badge and S3's shading both use this same import-margin-derived signal.

## Project structure

```
streamlit_app.py                        # landing page, nav explainer
pages/1_Copper_East_West.py             # page 1 (S1, S2, S2b, S3-S6)
pages/4_Zinc_Smelter_Margin.py          # page 4 (S1-S8)
pages/5_Freight_Overlay.py              # page 5 (S1-S6)
utils/data.py                 # load_ticker_raw, get_dataset, to_usd_per_tonne,
                               # resample_weekly/monthly, ensure_usdcny_csv
utils/finance.py              # cross_corr, peak_lag, import_margin, breakeven_ratio,
                               # export_margin, export_breakeven_ratio, export_domestic_cost,
                               # ratio_minus_breakeven, scrap_discount, classify_regime,
                               # consecutive_below, zinc_per_dmt_conc, tc_per_tonne_zinc,
                               # smelter_margin, rolling_benchmark_proxy, freight_regime,
                               # freight_regime_badge, freight_baseline, freight_scaler,
                               # freight_adjusted_cost
config.py                     # ticker -> CSV file map + unit metadata (single source of truth),
                               # DROPPED_TICKERS, ZINC_DATA_CAVEATS, VESSEL_COMMODITY_MAP,
                               # FREIGHT_DATA_CAVEATS
data/csv/                     # Bloomberg-export CSVs, one per ticker (+ cached USDCNY.csv)
requirements.txt
```

## Known limitations (page 1)

- Freight and financing are flat, indicative sliders — not real curves.
- The lead-lag CCF is in-sample and sample-size-limited, especially for
  the monthly-frequency legs (`CECN0002`, and the whole of S5) once
  resampled and differenced.
- `USDCNY` is Yahoo Finance-sourced (spot FX proxy), not a Bloomberg CNH/CNY
  onshore-vs-offshore-specific series — adequate for this app's purposes
  but flagged explicitly rather than presented as Bloomberg-grade FX.

# Page 4 — Zinc Smelter Margin

Theme: zinc concentrate treatment charges (TC) drive a China custom
smelter's P&L — smelters are paid a discount off the metal price to
process concentrate into refined metal, so a smelter's margin moves with
TC, not with where zinc itself trades. Glencore sits on both sides of the
same TC: it's the largest independent concentrate trader (earns TC when
it's high) **and** a smelter operator (Asturiana/San Juan de Nieva,
Portovesme, Nordenham, Kazzinc — squeezed when TC is low). This page
reconstructs the TC-to-metal conversion, the resulting smelter margin
cycle, and both sides of that opposing trader/smelter P&L off one TC
series.

## Data schema & ticker registry (page 4)

Every ticker/unit/frequency below was checked directly against the CSVs
in `data/csv/` before being wired up — not just assumed from the brief.
Same finding as pages 2/3: everything here is monthly, not daily.

| Ticker | Description | Raw unit | Frequency (verified) |
|---|---|---|---|
| `Z1CNHCOF` | China zinc conc TC 50% CIF (default TC benchmark) | USD/dmt conc | **monthly** |
| `Z1CNTCIM` | China TC imported zinc conc (cross-check) — starts 2018-11 | USD/dmt conc | **monthly** |
| `LMZSDS03` | LME zinc 3-month | USD/t | **monthly** (see caveat below) |
| `ZNCNMQKY` | China zinc premium, B/L Shanghai CIF (regional physical premium) | USD/t | **monthly** |
| `USDRUB` | USD/RUB spot (optional macro/FX context) | RUB per USD | **monthly** |
| `USDTRY` | USD/TRY spot (optional macro/FX context) | TRY per USD | **monthly** |
| `DXY` | US Dollar Index (optional context) | index | **monthly** |

### Data caveats found while wiring this page up

Recorded in `config.ZINC_DATA_CAVEATS` and surfaced in an in-app expander
on the page itself:

- **Every zinc series here is monthly, not "daily, gaps" as the brief
  assumed.** One observation per month across the full history for all
  six tickers — the whole page (including the S6 curtailment slider) is
  in months.
- **`LMZSDS03` is a month-end-only index export in this dataset** —
  unlike `LMCADS03` (the copper LME 3-month series, genuinely daily with
  4000+ rows), this file has 355 rows spanning
  1997-2026, one print per month. Confirmed by direct inspection (listing
  every 2020 observation showed exactly 12 month-end prints), not
  inferred from the "LME Comdty" vs "LME Index" filename difference
  alone.
- **`Z1CNHCOF` genuinely prints negative TC** (-60 to -65 USD/dmt in
  2026-05/06) — real data, not a parsing artifact, and exactly the "TC
  near/below zero = extreme concentrate tightness" regime S2 describes.
- **`ZNCNMQKY` confirmed as a genuine USD/t physical premium** (values
  ~90-140 across its history) — not a CNY/t cathode price, resolving the
  brief's own hedge ("verify unit; likely USD/t premium"). Shown as
  regional context (S8) only, never folded into the TC/margin core.

## Unit discipline (page 4)

- **TC benchmarks are quoted USD/dmt of CONCENTRATE, not metal.**
  Converting requires the concentrate grade and the smelter's
  metallurgical recovery: `zn_per_dmt_conc = grade * recovery` tonnes of
  payable zinc are recovered per dmt of concentrate treated, so
  `TC_per_t_zinc = TC_per_dmt_conc / zn_per_dmt_conc` — **dividing**, not
  multiplying. Getting this backwards is an instant, obvious credibility
  loss (see "Core economics" below for the worked example).
- All conversions live in `config.TICKERS` + `utils/data.to_usd_per_tonne()`
  — no magnitude-guessing, same as pages 1-3.
- `by_product_credit` (acid + minor Pb/Ag/Au) has **no backing data
  series in this dataset** — it is always presented as an explicit
  sidebar SENSITIVITY, never as an observed number (see S7).

## Core economics

China custom smelter, conc -> SHG zinc (`utils.finance`):

```
zn_per_dmt_conc  = grade * recovery                          # ~0.50 * 0.955 ~= 0.4775 t Zn / dmt conc
TC_per_t_zinc    = TC_per_dmt_conc / zn_per_dmt_conc
free_metal       = max(0, LME_zinc - basis_price) * participation_pct   [if escalator enabled, else 0]
margin           = TC_per_t_zinc + free_metal + by_product_credit - conv_cost
```

- **`grade`** (sidebar slider, default 0.50) and **`recovery`** (default
  0.955): a tonne of 50%-grade concentrate contains 0.50 t of contained
  zinc, of which the smelter actually recovers ~95.5% as payable metal —
  so 1 dmt of concentrate yields ~0.4775 t of payable zinc.
  Worked example: at TC = $100/dmt conc, `TC_per_t_zinc = 100 / 0.4775
  ~= $209/t zinc` — a materially bigger number than the raw TC headline,
  which is exactly the point of doing this conversion explicitly rather
  than eyeballing the USD/dmt print as if it were USD/t metal.
- **`free_metal` / price-participation escalator**: a legacy TC clause
  paying the smelter a cut of any LME zinc price above a basis price.
  Modern benchmarks are typically negotiated **flat** (no escalator) —
  the sidebar checkbox defaults to **off** (`participation_pct` also
  defaults to 0%), reflecting that. Turning it on and raising the
  participation slider models the older contract style; a tooltip on
  each control spells out the contractual mechanics.
- **`by_product_credit`** (sulphuric acid, plus minor Pb/Ag/Au credits):
  **no public acid-price series exists in this dataset** — this is
  always a sidebar SENSITIVITY slider (default ~$100/t zinc), never
  presented as fact. S7 stress-tests it directly against TC level in a
  2D heatmap, since it's the single biggest unmodeled lever in this P&L.
- **`conv_cost`** (energy/reagents/labor, default $250/t zinc): indicative
  flat smelting cost — a slider, not a cost-curve series.
- Margin is **indicative and pre-tax** throughout; the benchmark/spot mix
  (S4) is a proxy, not a negotiated annual number; and this page is a
  **China custom-smelter angle only** — the EU annual-benchmark system
  (Nyrstar/Korea Zinc) is out of scope, stated explicitly in-app.

## S1 — Header / KPI

Spot TC (selectable: `Z1CNHCOF` default / `Z1CNTCIM` cross-check),
`TC_per_t_zinc`, LME zinc 3M, indicative smelter margin, and a
HEALTHY/BREAKEVEN/UNDERWATER badge (`utils.finance.classify_regime` with
`config.ZINC_MARGIN_BREAKEVEN_BAND = $40/t`, wider than page 1's copper
band since TC-driven zinc margins run in the low hundreds USD/t). A
cross-source guard flags material divergence
between `Z1CNHCOF` and `Z1CNTCIM` (skipped near zero, where relative-
spread comparisons become unstable). Default chart date range is the
last 3 years, same convention as pages 1-3.

## S2 — TC cycle time series

Spot TC (USD/dmt concentrate) with LME zinc 3M overlaid on a right axis,
annotated with the 2021 highs (concentrate glut) and the 2024-26 collapse
toward/below zero (extreme concentrate tightness -> smelter squeeze) —
the whole page-4 thesis in one chart. An in-app alert fires whenever the
latest spot TC print is at or below zero.

## S3 — Smelter margin reconstruction

`margin = TC_per_t_zinc + free_metal + by_product_credit - conv_cost`,
stacked (positive components stacked above zero, conversion cost stacked
below) with the net margin line overlaid, shaded **UNDERWATER** red where
negative. A `go.Waterfall` breaks the same four components down
explicitly on a sidebar-selected snapshot date.

## S4 — Spot vs benchmark spread

There is no separately-negotiated annual TC benchmark series in this
dataset, so the "benchmark" here is an explicit **PROXY** built off the
same spot series — selectable in the sidebar between a trailing rolling
mean (`utils.finance.rolling_benchmark_proxy`, default 12-month window)
and a step-annual approximation (`step_annual_benchmark_proxy`, holding
each year's first observed print flat through December, mimicking how
real annual benchmarks are negotiated once and then held fixed).
`spot_vs_bench = TC_spot - TC_bench_proxy`; shaded where negative (spot
below the smoothed benchmark — acute, recent tightness the annual
contract hasn't caught up to). Caveat stated in-app: this proxy is not a
negotiated annual number, and the EU annual-benchmark system is
out-of-scope on this page.

## S5 — Dual P&L: trader vs smelter (differentiator)

Same TC series, opposite books: a concentrate trader buys conc from mines
and earns the TC selling it on to smelters (trader P&L rises with TC); a
smelter pays the TC away as its raw-material discount (margin is
squeezed when TC is low). Both plotted indexed to 100 at the selected
window's start so the mirror-image shape is visible despite very
different natural units (trader P&L per dmt concentrate vs smelter
margin per t zinc). Text calls out that Glencore runs both books at once
(largest independent concentrate trader, and a smelter operator via
Asturiana/San Juan de Nieva, Portovesme, Nordenham, and Kazzinc) — so on
a net basis it captures margin somewhere along the chain almost
regardless of which way TC moves. The correlation stat shown is
explicitly caveated as mechanical (both series share the same TC input
with the same sign before conversion cost/credits are netted in) rather
than a novel empirical finding — the "opposing books" story is about
*where in the chain* the TC dollar lands, not a negative correlation
between the two series.

## S6 — Curtailment signal

`utils.finance.consecutive_below(margin, 0, N)`, sidebar slider default
N=4 **months** (verified-monthly data, not weeks —
see "Data caveats"), shaded **curtailment-risk**. Text is explicitly
illustrative, no fabricated tonnages: European smelters (Nyrstar,
Glencore's own Nordenham/Portovesme) idled capacity in 2022 on power
costs, and Chinese smelters both cut run-rates and took maintenance
outages in 2024 on low/negative TC — cited as narrative context, not
derived from the chart.

## S7 — Sensitivity (acid credit)

The single biggest unmodeled lever in this P&L, stress-tested directly:
`utils.finance.zinc_margin_sensitivity_grid` builds a 2D heatmap of
indicative margin across a grid of **TC level x acid/by-product credit**,
holding free metal and conversion cost at their current sidebar values.
A companion metric solves `margin = 0` for the acid credit needed to
break even at the latest observed TC. The point: the sign of the margin
can flip purely on the acid assumption at a given TC level — demonstrating
the swing factor actually driving China smelter economics, not just
reciting the TC headline.

## S8 — Zinc premium context (optional)

`ZNCNMQKY` (verified genuine USD/t physical premium, B/L basis — not a
CNY cathode price) vs LME zinc 3M: a regional physical-tightness overlay.
Explicitly **not part of the TC/margin core** — shown only as context on
whether Chinese physical demand is running hot alongside (or independent
of) the concentrate-side TC squeeze. Degrades gracefully (a caption, not
a crash) if the ticker is unavailable.

## Regime badge (page 4)

`utils.finance.classify_regime(margin, marginal_band=config.ZINC_MARGIN_BREAKEVEN_BAND,
open_label="HEALTHY", closed_label="UNDERWATER", marginal_label="BREAKEVEN")`
— same three-way HEALTHY/BREAKEVEN/UNDERWATER wording as page 1's ARB
OPEN/MARGINAL/CLOSED badge, with a wider $40/t deadband appropriate to
TC-driven margin swings.

## Known limitations (page 4)

- `by_product_credit`, `conv_cost`, the escalator basis/participation,
  and `grade`/`recovery` are all sliders, not observed data — there is no
  public acid-price series, cost-curve series, or contract-terms feed in
  this dataset.
- The S4 "benchmark" is a spot-derived proxy (rolling mean or step-
  annual), not a real negotiated annual TC number — this dataset has no
  independent annual-benchmark series to compare against.
- China custom-smelter angle only; the EU annual-benchmark system
  (Nyrstar, Korea Zinc) is out of scope and stated as such in-app.
- Margin is indicative and pre-tax; S6's curtailment narrative is
  qualitative context, not derived from any tonnage data on this page.
- All figures are indicative and pre-tax.

---

# Page 5 — Freight Overlay

Theme: freight as a **cross-basin regime overlay** that modulates the
arb/margin assumptions already used in pages 1 (Cu) and 4 (Zn) — not a
new source of $/t route freight. Physical traders live and die on
freight; this page shows the freight regime across Baltic vessel classes,
maps each class to the commodities it actually moves, and freight-adjusts
the other pages' existing freight sliders by a Baltic-derived scaler.

**Scope limit, stated up front (also banner-level in-app)**: the Baltic
series are unitless **index points**, not USD/t on any named route — there
is no Cape C5 / Panamax route USD/t series in this dataset, and none is
fabricated here. Freight enters the app two ways only: (a) a **regime
signal** (rolling percentile/z-score, still in index points) and (b) a
unitless **scaler** applied to the existing USD/t freight slider already
in page 1. A dollar figure only ever re-enters by scaling an *existing*
slider assumption — never a new fabricated per-route number.

## Data schema & ticker registry (page 5)

Every ticker/unit/frequency below was checked directly against the CSVs
in `data/csv/` before being wired up. Same finding as every prior page:
everything here is monthly, not daily.

| Ticker | Description | Raw unit | Frequency (verified) |
|---|---|---|---|
| `BDIY` | Baltic Dry Index — dry-bulk composite | index pts | **monthly** |
| `BCI14` | Baltic Capesize Index — iron ore/coal, large dry-bulk | index pts | **monthly**, starts 2014-04 |
| `BSI` | Baltic Supramax Index — Cu/Zn concentrates, minor bulk (map's PRIMARY concentrate proxy) | index pts | **monthly**, **stale — ends 2017-03** |
| `BHSI` | Baltic Handysize Index — smaller concentrate parcels, minor bulk (practical default proxy here) | index pts | **monthly**, current through 2026-06 |
| `BIDY` | Baltic Dirty Tanker Index — crude (context only) | index pts | **monthly** |
| `BITY` | Baltic Clean Tanker Index — refined products (context only) | index pts | **monthly** |
| `CECNVXAQ` / `LMCADY` / `CECN0002` | SHFE cathode / LME cash / Yangshan premium — reused from page 1 for the S3 Cu freight-scaled margin | CNY/t (÷USDCNY) / USD/t / USD/t | **monthly** (resampled here; daily natively on page 1) |
| `AUDUSD` / `USDZAR` / `USDRUB` / `USDTRY` / `USDIDR` / `EURUSD` / `DXY` / `USGGT10Y` | S5 macro/exporter-FX context only | FX/%/index | **monthly** |

### Data caveats found while wiring this page up

Recorded in `config.FREIGHT_DATA_CAVEATS` and surfaced in an in-app
expander on the page itself:

- **All six Baltic series are monthly, not "daily, gaps" as the brief
  assumed** — same finding as every prior page. The regime window and
  the scaler are all in months, not weeks.
- **`BSI` (Supramax) — the vessel map's domain-correct PRIMARY concentrate
  proxy — is stale in this dataset (ends 2017-03)**, 9+ years stale.
  `BHSI` (Handysize, current through 2026-06, the map's secondary
  concentrate proxy) is used as the **practical default** throughout
  page 5 and in the back-integrated badges on pages 1/4; `BSI` remains
  selectable for domain/historical reference with an explicit staleness
  warning.
- **`BCI14` (Capesize) starts 2014-04** in this dataset — shorter history
  than the other Baltic series, but comfortably covers the page's default
  3Y window.

## Vessel → commodity map (`config.VESSEL_COMMODITY_MAP`)

The domain-knowledge core of this page — encoded in `config.py`, not
buried in page logic, so it stays the single source of truth:

```
Capesize   (BCI14) -> iron ore, coal, large dry-bulk    — context only
Supramax   (BSI)   -> base-metal concentrates (Cu, Zn), — PRIMARY proxy for
                       minor bulk                          pages 1/4 (STALE here)
Handysize  (BHSI)  -> smaller concentrate parcels,      — practical default proxy
                       minor bulk
Dirty tanker (BIDY)-> crude                             — context only
Clean tanker (BITY)-> refined products                  — context only
```

Cu/Zn concentrate moves on Supramax/Handysize freight, **not** Capesize
(which is big iron-ore/coal bulk — a different physical trade lane
entirely). Getting this backwards — treating Capesize as the metals
freight proxy because it's the largest, most-watched Baltic sub-index —
would be an instant credibility loss on a page whose entire purpose is
mapping vessel classes to the right commodities.

## Core logic

**Regime transform** (`utils.finance.freight_regime`, reusable — importable
by pages 1/4):

```
pctile  = trailing rank of today's value within its own last `window` periods (0-100)
zscore  = (value - rolling_mean) / rolling_std, same window
regime  = LOW (pctile < 25) / NORMAL / HIGH (pctile > 75)
```

`window` defaults to 36 (months) = 3Y, a sidebar slider. Using a
*trailing* percentile (not a whole-sample one) keeps the regime signal
meaningful even though the Baltic indices' own base/methodology has
shifted over their multi-decade history — a trailing window never
compares today against a 1990s base level.

**Freight scaler** (the integration — `utils.finance.freight_baseline` +
`freight_scaler` + `freight_adjusted_cost`):

```
baseline        = rolling-mean(vessel_index, window)   OR   vessel_index observed on a fixed ref date
freight_scaler  = vessel_index / baseline                       # unitless
freight_$t_adj  = base_freight_$t * freight_scaler               # base_freight_$t = the EXISTING
                                                                  # page-1 slider default
```

Both baseline modes are a sidebar selector. `freight_$t_adj` feeds S3,
which calls `utils.finance.import_margin()` (page 1) directly with the
adjusted freight argument instead of duplicating the formula.

## S1 — Header / KPI

Regime badge per vessel class (Capesize/Supramax/Handysize/Dirty/Clean —
`utils.finance.freight_regime_badge`), BDI level + trailing percentile,
and the scope-limit banner. Every metric's delta shows its *observation
date*, not "today" — `BSI`'s badge visibly reads 2017-03 while everything
else reads 2026-06, so staleness is self-evident on the metric itself
rather than only in a footnote. Default chart date range is the last 3
years, same convention as pages 1/4.

## S2 — Freight regime panel

All six Baltic indices rebased to 100 at the selected window's start (so
vessel classes with very different absolute point levels are visually
comparable), with the sidebar-selected vessel's LOW/HIGH regime shaded
green/red across the whole panel. The vessel→commodity legend and the
"why Supramax/Handysize, not Capesize" rationale are restated directly
under the chart.

## S3 — Freight-adjusted arb sensitivity

- **Cu** (mirrors page 1): `import_margin()` recomputed at the page's flat
  base-freight slider vs the same freight scaled by the selected vessel
  (Handysize by default). Both lines charted together, shaded wherever
  the sign of the margin flips (arb OPEN↔CLOSED) purely from the freight
  scaling — with everything else held fixed. A metric reports the latest
  $/t swing directly.
- **Zn**: not scaled here — the smelter-margin formula (`smelter_margin`,
  page 4) has no freight term to begin with (it's a TC/treatment-charge
  business, not a freight-exposed physical-arb business), so there is no
  margin leg to freight-adjust. Noted rather than modeled.

## S4 — Cross-commodity freight dashboard

Small multiples — one mini-chart per Baltic series (composite + 5 vessel
classes), each with its own regime shading, a one-line commodity/role
caption, and (for Supramax/Handysize) `st.page_link` buttons straight to
pages 1/4 — a one-glance "freight state of the physical complex."

## S5 — Macro/FX context (optional, degrades gracefully)

BDI vs `DXY`/`USGGT10Y` (bulk demand/financing backdrop) and exporter FX
(`USDZAR` South Africa, `USDRUB` Russia, `USDIDR` Indonesia, plus
`AUDUSD`/`EURUSD`) as flow-cost context — qualitative only, explicitly
stated as feeding no calc anywhere in the app. Each panel degrades to a
caption (not a crash) if its ticker is unavailable.

## Back-integration into pages 1/4

`utils.finance.freight_regime()` and `freight_regime_badge()` are
reusable, importable functions (not page-5-specific), so pages 1 and 4
each load `BHSI` and render one extra "Freight regime (Handysize, ctx)"
KPI column in their existing S1 header row. This is purely additive and
import-only — it does not feed into any margin/arb calc on those pages,
degrades to "n/a" if `BHSI` is unavailable, and uses Handysize rather than
the map's nominal-primary Supramax for the same staleness reason
documented above.

## Known limitations (page 5)

- Baltic indices are index points, never converted to $/t — there is no
  named-route dollar freight series in this dataset, and this page does
  not fabricate one.
- `BSI` (the vessel map's domain-correct primary concentrate proxy) is
  9+ years stale in this dataset; `BHSI` is used as the practical default
  proxy instead throughout.
- The S3 Cu freight slider (base freight) mirrors but does not read page
  1's live sidebar state — it is an independent widget with a matching
  default, not a cross-page-linked parameter.
- The Zn page is deliberately excluded from the S3 recompute (see S3
  above) rather than forced into a freight-scaling frame that doesn't fit
  its economics.
