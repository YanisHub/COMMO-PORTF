# Commodity Physical Desk Monitor

A multi-page Streamlit app modeling physical-commodity-desk logic: arb
windows, premia lead-lag, and tightness signals. Page 1 is the **Copper
East-West Arb Monitor** — SHFE-LME import arb, Yangshan premium lead-lag
vs SHFE destocking, and a US scrap-discount tightness cross-check. Page 2
is the **Lithium Conversion Margin** monitor — spodumene-to-carbonate
Chinese converter P&L, tracking the 2023-25 lithium crash into margin
compression and a curtailment-risk signal. Page 3 is the **Aluminium
Premia Fair-Value & Carry** monitor — Rotterdam/US Midwest premia vs a
carry-component fair value, and the classic 2009-14 warehouse
cash-and-carry trade. Page 4 is the **Zinc Smelter Margin** monitor —
concentrate TC converted into a China custom-smelter margin cycle, the
mirror trader/smelter P&L off one TC series, a curtailment-risk signal,
and an acid-credit sensitivity check. Page 5 is the **Freight Overlay**
monitor — Baltic vessel-class indices as a cross-basin freight regime
signal + a scaler on the freight assumptions already used in pages 1/2/4,
with a vessel-to-commodity map and a proxy-validation check against the
one real dollar-freight series in this app.

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
pages/2_Lithium_Conversion_Margin.py    # page 2 (S1-S6)
pages/3_Aluminium_Premia.py             # page 3 (S1-S6)
pages/4_Zinc_Smelter_Margin.py          # page 4 (S1-S8)
pages/5_Freight_Overlay.py              # page 5 (S1-S6)
utils/data.py                 # load_ticker_raw, get_dataset, to_usd_per_tonne,
                               # resample_weekly/monthly, ensure_usdcny_csv
utils/finance.py              # cross_corr, peak_lag, import_margin, breakeven_ratio,
                               # export_margin, export_breakeven_ratio, export_domestic_cost,
                               # ratio_minus_breakeven, scrap_discount, classify_regime,
                               # contango, breakeven_contango, premium_fair_value, carry_pnl,
                               # premium_richness, classify_carry_regime, converter_margin,
                               # consecutive_below, zinc_per_dmt_conc, tc_per_tonne_zinc,
                               # smelter_margin, rolling_benchmark_proxy, freight_regime,
                               # freight_regime_badge, freight_baseline, freight_scaler,
                               # freight_adjusted_cost
config.py                     # ticker -> CSV file map + unit metadata (single source of truth),
                               # DROPPED_TICKERS, ALUMINIUM_DATA_CAVEATS, LITHIUM_DATA_CAVEATS,
                               # ZINC_DATA_CAVEATS, VESSEL_COMMODITY_MAP, FREIGHT_DATA_CAVEATS
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

---

# Page 2 — Lithium Conversion Margin

Theme: the spodumene->Li carbonate conversion step is the Chinese
converter's P&L (not the miner's, not the battery maker's). This page
prices that margin and tracks how the 2023-25 lithium crash compressed it
— including, per S6, an illustrative curtailment-risk signal.

## Data schema & ticker registry (page 2)

Every ticker/unit/frequency below was checked directly against the CSVs
in `data/csv/` before being wired up. Two things diverged materially from
the initial brief (see "Data caveats" below): every spod/carbonate series
turned out to be **monthly**, not daily, and `LCBMAUSF` turned out to be
mislabeled in the generic ticker catalog.

| Ticker | Description | Raw unit | Frequency (verified) |
|---|---|---|---|
| `L4CNSPI` | China spodumene conc CIF index, SC6 (default S1 benchmark) | USD/t | **monthly** |
| `SVPA` | Spodumene CIF China, Fastmarkets future | USD/t | **monthly**, starts 2024-10 only |
| `LICNSPDU` | China spodumene Li2O 6% min CIF (cross-check) | USD/t | **monthly** |
| `L4CNSPAU` | China 6% spod conc from Australia, CIF (AU-origin; also the S4 CIF comparator) | USD/t | **monthly** |
| `L4CNMJGO` | China Li carbonate 99.5% battery-grade, DEL | CNY/t (÷ USDCNY → USD/t) | **monthly** |
| `LCBMAUSF` | Spodumene 6% FOB Australia (Benchmark Minerals) | USD/t | **monthly** |
| `AUDUSD` | AUD/USD spot | USD per AUD | **monthly** |
| `USDCNY` | CNY spot (fetched from Yahoo Finance, cached, reused from page 1) | CNY per USD | daily |
| `BDIY` | Baltic Dry Index (optional S4 freight-proxy overlay) | index points | monthly |
| `BSI` | Baltic Supramax Index (optional S4 overlay — **stale**, ends 2017-03) | index points | monthly |

### Data caveats found while wiring this page up

Recorded in `config.LITHIUM_DATA_CAVEATS` and surfaced in an in-app
expander on the page itself:

- **Every spod/carbonate series + `AUDUSD` are monthly, not daily.** The
  brief's data table said "daily, gaps"; inspecting the CSVs directly
  showed one month-end print per month for all of them (effectively zero
  gaps against a month-end calendar — a single missing month in `SVPA`).
  The whole page treats these as monthly: no daily resample is attempted,
  and the S6 curtailment slider counts **consecutive months**, not weeks.
  `USDCNY` is the one genuinely daily series here (reused from page 1's
  Yahoo-fetch loader), which is what its CNY/t→USD/t conversion relies on.
- **`SVPA` genuinely starts 2024-10-31** in this dataset. Selecting it as
  the S1 benchmark clips the effective chart start to that date and shows
  an in-app guard banner — never backfilled or NaN-padded to look like a
  longer history.
- **`LCBMAUSF` is mislabeled in the generic ticker catalog**
  (`data/tickers.json` calls it "Lithium Carbonate FOB Australia"). Its
  actual value range (~$375-6,401/t) and its close, noisy tracking of the
  CIF spodumene series (mean spread ≈ -$18/t, std ≈ $272/t vs. `L4CNSPI`
  — a plausible CIF-vs-FOB basis, not a 10-20x price gap) both confirm
  it's **spodumene 6% FOB Australia**, matching the brief, not carbonate
  (which ran ~$5,600-80,600/t over the same history per
  `L4CNMJGO`/USDCNY — two orders of magnitude away). Treated as spodumene
  throughout this app.
- **`BSI` stops at 2017-03** — 9+ years stale. Offered in the S4 freight
  overlay selector for completeness, never as the default, with an
  in-app staleness warning if picked.

## Unit discipline (page 2)

- `L4CNMJGO` is the only CNY/t series here — converted via
  `to_usd_per_tonne()`'s existing `cny_t` path (÷ `USDCNY`, same-day
  forward-filled), identical mechanism to page 1's SHFE conversion. Every
  other series is already USD/t (factor 1).
- CNY/t and USD/t are never mixed silently — the one CNY/t series is
  converted before it touches any calc, and the conversion is flagged in
  the S1 warnings expander whenever `USDCNY` is unavailable.
- All conversions live in `config.TICKERS` + `utils/data.to_usd_per_tonne()`
  — no magnitude-guessing, same as pages 1 and 3.

## Core economics

```
carbonate_USD      = L4CNMJGO / USDCNY                    # DEL, USD/t
effective_ratio    = conversion_ratio * (6.0 / grade_pct)  # grade adjustment
spod_cost_per_t_LC = spod_CIF_USD * effective_ratio         # t spod per t carbonate
gross_margin       = carbonate_USD − spod_cost_per_t_LC − conv_cost
                       − freight_inland − other_cost
```

(`utils.finance.converter_margin`, used identically across S1-S3 and S6.)

- **`conversion_ratio`** (sidebar slider, min 6.5, max 9.5, **default
  8.0**): t of SC6 (6% Li2O) spodumene concentrate needed per t of
  battery-grade Li2CO3. Stoichiometric derivation: a 6% Li2O concentrate
  contains 60 kg Li2O per tonne. MW Li2O = 29.88, MW Li2CO3 = 73.89, and
  lithium is conserved 1:1 between the two formulas (2 Li atoms per
  formula unit, both sides), so 60 kg Li2O → 60 × (73.89/29.88) = 148.4 kg
  Li2CO3 at 100% recovery → **6.74 t concentrate per t carbonate**,
  theoretical maximum. Real-world roast/leach/purification recovery of
  ~85-90% pushes this to **~7.5-8.5 t/t** in practice; the 8.0 default
  corresponds to ~84% effective recovery. This is the single most
  consequential, most-scrutinized assumption on the page — flagged as
  such in its own tooltip.
- **`grade_pct`** (sidebar slider, default 6.0, range 3.0-7.0): all spod
  series on this page are benchmarked at 6% Li2O. If the concentrate
  actually traded is a different grade (e.g. lower-grade lepidolite
  feedstock, relevant to the S6 Yichun narrative), `effective_ratio`
  scales `conversion_ratio` by `6.0/grade_pct` — a lower grade needs
  proportionally more tonnes of concentrate per tonne of carbonate
  output.
- **`conv_cost`** (sidebar slider, default $2,200/t Li2CO3): indicative
  flat roast/reagent/energy/labor cost. No public cost-curve series is
  used — a slider, not data.
- **`freight_inland`** (sidebar slider, default $40/t): indicative inland
  logistics moving CIF-landed concentrate to the Chinese conversion plant
  (Jiangxi/Sichuan) — distinct from the S4 ocean CIF-FOB freight leg,
  which is *observed* from data, not a slider.
- **`other_cost`** (sidebar slider, default $0/t): catch-all buffer for
  unmodeled costs, off by default.
- **Label discipline**: the margin is explicitly **indicative, pre-by-
  product, pre-tax** everywhere it's shown — by-products (e.g. tantalum
  credits some converters get), VAT/income tax, and plant-specific yield
  variation are all excluded. This is the **carbonate route only**
  (99.5% battery-grade `L4CNMJGO`); the LiOH (hydroxide) route is
  explicitly out of scope, stated in-app.

## S1 — Header / KPI

Carbonate USD/t, the selected spodumene CIF benchmark (sidebar selector:
`L4CNSPI` default / `LICNSPDU` / `L4CNSPAU` / `SVPA` guarded to 2024-10+),
spod-cost-per-tonne-carbonate, gross margin, and a three-way regime badge
(`utils.finance.classify_regime`, reused from page 1 with page-2-specific
labels and a wider deadband):

- **HEALTHY** — margin > `config.LITHIUM_MARGIN_BREAKEVEN_BAND` ($100/t).
- **BREAKEVEN** — within the ±$100/t deadband (wider than page 1's $20/t
  copper-arb band, since lithium conversion margins run in the
  hundreds-to-thousands of USD/t — the band absorbs assumption noise
  around `conversion_ratio`/`conv_cost`, not just data noise).
- **UNDERWATER** — margin < -$100/t.

Also on S1: a **cross-source spodumene divergence** check (compares the
latest print across whichever of `L4CNSPI`/`LICNSPDU`/`L4CNSPAU`/`SVPA`
have data, warns above an 8% spread — illiquid Chinese spodumene indices
genuinely do diverge this much during volatile periods) and the **SVPA
guard** described above. Default chart date range is the last 3 years,
same convention as pages 1 and 3.

## S2 — Conversion margin time series

Carbonate price and spod-cost-per-tonne-carbonate are overlaid with the
area between them shaded, so the margin squeeze is mechanically visible
as the two lines converge — then `gross_margin` is charted directly
below, shaded red where **UNDERWATER** (< $0/t), with the 2023-24 lithium
crash window annotated. A one-line headline states whether the margin has
flipped negative, tying directly into the S6 curtailment thesis.

## S3 — Margin decomposition

A `go.Waterfall` (Plotly's built-in waterfall trace, reused directly —
same approach as page 3's carry-P&L waterfall) breaks down the margin on
a sidebar-selected snapshot date: `carbonate → −spod_cost →
−conversion_cost → −(freight_inland+other) → net`. A second, scale-free
view plots `margin / carbonate_USD × 100` (margin as a % of carbonate
price) over time — comparable across the ~10x carbonate price swing
between the 2022 boom and the 2023-25 crash in a way the absolute USD/t
margin isn't.

## S4 — FOB vs CIF = freight leg

```
implied_freight = spod_CIF_AU − spod_FOB_AU
```

Compares `LCBMAUSF` (FOB Australia) against **`L4CNSPAU`** specifically
(China CIF, AU-origin) — the best like-for-like match on origin — used
here regardless of whichever benchmark is selected in S1's sidebar
selector, since the freight leg only makes sense against an AU-origin
CIF print. Negative or spiking values are flagged as likely
index-basis/timing mismatches between the two panels rather than genuine
negative freight (marked with an `x` marker on the chart, not silently
smoothed over). An optional Baltic freight-index overlay (`BDIY` or
`BSI`, sidebar selector, default off) plots on a secondary axis for
visual context only — not used in any calc. `BSI` triggers an explicit
staleness warning if selected (see "Data caveats"); an empty overlay
series degrades to a caption, never a crash.

## S5 — Producer squeeze (FX)

```
FOB_AUD = LCBMAUSF / AUDUSD
```

The same spodumene FOB price restated in AUD, the currency AU miners'
costs are mostly denominated in. Plotted against the USD price on a dual
axis: AUD weakness cushions AU producer revenue in local-currency terms
even as the USD price falls, one reason AU mines (Greenbushes) ran longer
through the 2023-25 crash than Chinese converters — whose margin is a
pure USD/CNY spread with no equivalent FX cushion. A second chart
overlays the S1-S3 converter margin (China) against `FOB_AUD` (Australia)
and reports their correlation — opposite ends of the same supply chain,
expected to move in opposite directions as the crash squeezes the
converter and cushions (relatively) the miner.

## S6 — Curtailment signal

`utils.finance.consecutive_below(margin, threshold=0, n=N)` — a new,
generic reusable helper (not page-2-specific: it just flags run-lengths
of a boolean condition, so it works at any periodicity). `N` is a sidebar
slider, default **4 months** (relabeled from the brief's "4 weeks" since
the underlying data is monthly, not weekly — see "Data caveats"). Shades
every month that is part of a run of `N`+ consecutive sub-zero-margin
months as a **curtailment-risk regime**, with a banner if the regime is
currently active.

Below the chart: an **illustrative, qualitative-only** note on the 2024
supply response — Albemarle/IGO's Greenbushes trimming output guidance,
Chinese lepidolite converters around Yichun, Jiangxi curtailing high-cost
production, and CATL's Jianxiawo lepidolite mine pausing operations. This
is general market knowledge cited for narrative context; **no tonnages
are fabricated or derived from any series on this page**, per the brief's
explicit instruction.

## Regime badge (page 2)

`utils.finance.classify_regime(margin, marginal_band=config.LITHIUM_MARGIN_BREAKEVEN_BAND, open_label="HEALTHY", closed_label="UNDERWATER", marginal_label="BREAKEVEN")`
— the same function used for page 1's ARB OPEN/CLOSED badge, extended
with a `marginal_label` parameter (default `"MARGINAL"`, so page 1's call
sites are unaffected) so it can serve a third vocabulary without
duplicating the classification logic.

## Known limitations (page 2)

- `conversion_ratio`, `conv_cost`, `freight_inland`, and `other_cost` are
  sliders, not real cost-curve data — no public series exists for
  Chinese converter processing costs at this granularity.
- The margin is pre-by-product and pre-tax throughout; by-product
  credits, VAT, and income tax are real and excluded by construction.
- The S4/S5 economics assume `L4CNSPAU`/`LCBMAUSF` are directly
  comparable index panels; in practice, panelist mix and reporting timing
  differ, which is exactly what the S4 anomaly flagging is there to
  surface rather than hide.
- All spod/carbonate data is monthly — there is no way to see intra-month
  moves on this page, unlike pages 1 and 3's daily LME/SHFE series.

---

# Page 3 — Aluminium Premia Fair-Value & Carry

Theme: regional Al premia (Rotterdam duty-paid, US Midwest) represent real
physical-Al-trader P&L (Glencore is a major physical Al trader). This page
compares actual premia to a carry-component fair value derived from LME
contango, financing, and warehouse rent, and models the classic 2009-14
LME warehouse cash-and-carry trade.

## Data schema & ticker registry (page 3)

Every ticker/unit/frequency below was checked directly against the CSVs
in `data/csv/` before being wired up — not just assumed from the brief.
Two things diverged from the initial assumptions (see "Data caveats"
below): `AMEUDDP`/`USGGT10Y`/`DXY`/`EURUSD` turned out to be monthly, not
daily, and `IPAITI*` (IAI production) turned out to stop at 2014-12-31.

| Ticker | Description | Raw unit | Frequency (verified) |
|---|---|---|---|
| `LMAHDY` | LME Aluminium cash | USD/t | daily |
| `LMAHDS03` | LME Aluminium 3-month | USD/t | daily |
| `AUP1` | CME US Midwest Al transaction premium (Platts MW), generic 1st future | USD/lb | daily |
| `AMEUDDP` | Rotterdam Al ingot premium, duty-paid in-warehouse (ARA) | USD/t | **monthly** |
| `USGGT10Y` | US 10Y Treasury yield (financing-rate proxy) | % | **monthly** |
| `DXY` | US Dollar Index (macro context only) | index | **monthly** |
| `EURUSD` | EUR/USD spot (macro context only) | USD per EUR | **monthly** |
| `IPAITITL` | IAI primary Al production, total | 1000 t (×1000 → t) | monthly, **stops 2014-12** |
| `IPAITIEU`/`NA`/`AS`/`AF`/`LA`/`OC` | IAI primary Al production, by region | 1000 t (×1000 → t) | monthly, **stops 2014-12** |

### Data caveats found while wiring this page up

Recorded in `config.ALUMINIUM_DATA_CAVEATS` and surfaced in an in-app
expander on the page itself:

- **`AMEUDDP` / `USGGT10Y` / `DXY` / `EURUSD` are monthly, not daily.**
  The brief assumed all four were daily; inspecting the CSVs directly
  showed one observation per month (~150-355 rows across the full
  history) for all four. The page forward-fills them onto the daily LME
  grid wherever they feed a calculation (financing rate, richness),
  using the same `pd.concat(...).ffill()` idiom page 1 uses for SHFE vs
  LME — stated explicitly in-app (S1 frequency-note banner), not a
  silent frequency mismatch.
- **`IPAITI*` (IAI production) stops at 2014-12-31** — 11+ years stale as
  of today. There is no real time overlap with the premia charted
  elsewhere on the page, so S6 shows IAI production over its own native
  range with that limitation called out, rather than pretending it's a
  current supply signal.
- **`AUP1` has an anomalous ~11-12.5 USD/lb stretch from 2013-03 to
  2013-08** (vs. a normal 0.06-0.35 range elsewhere in the series) —
  most likely a units/contract-roll artifact from that era. Left in
  rather than dropped (`AUP1` is not in `config.DROPPED_TICKERS`) since
  it predates every default chart window on this page (falls before the
  3-year default and before the 2018 tariff annotation) — flagged here
  instead of silently patched.
- **`AUP1`'s 2025-26 run-up (0.24 USD/lb in 2025-01 to 1.15 by 2026-06)
  is genuine data**, not an error — it's the "2025 tariff moves" the
  brief asks S2 to annotate, and it shows up exactly where expected.

## Unit discipline (page 3)

- **`AUP1` is confirmed USD/lb → ×2204.62 (`config.LB_TO_TONNE`) → USD/t.**
  Getting this scale wrong (e.g. treating it as already USD/t) would be
  an instant, obvious credibility loss — a $1.15/lb premium would read
  as $1.15/t instead of ~$2,535/t.
- **IAI series are ×1000 (`config.KT_TO_TONNE`)** — quoted in thousands
  of tonnes, converted to tonnes. Always an explicit resample/conversion
  in-app, never silent (same principle as `CNIVCORE` on page 1).
- All conversions live in `config.TICKERS` + `utils/data.to_usd_per_tonne()`
  — no magnitude-guessing, same as page 1.

## Core economics

Carry-component fair value of the regional premium (`utils.finance`):

```
contango           = LMAHDS03 − LMAHDY                      # USD/t, + = contango
financing_cost     = LMAHDY × fin_rate × days / 360         # ACT/360, on the CASH metal value
warehouse_rent     = daily_rent × days                       # sidebar slider, no public series
breakeven_contango = financing_cost + warehouse_rent
FV_premium          = financing_cost + warehouse_rent − contango   # carry component ONLY
carry_pnl           = contango − financing_cost − warehouse_rent   # cash-and-carry trade P&L
premium_richness    = actual_premium − FV_premium
```

- **`fin_rate`** (sidebar): either `USGGT10Y/100 + spread` (spread slider,
  default 1.5%) or a flat override rate (slider, default 5.5%). `USGGT10Y`
  is monthly and forward-filled onto the daily grid — see "Data caveats."
- **`warehouse_rent`**: `daily_rent` (slider, default $0.45/t/day ≈
  $13/t/month) × `carry_days` (slider, default 90). There is no public
  series for LME warehouse rent — famously opaque and individually
  negotiated during the 2009-14 warehouse-queue era — so this is
  necessarily a slider, not data, with a tooltip saying so.
- **Financing is charged on the cash metal value (`LMAHDY`), not on the
  premium** — the trader is financing the metal itself, not the premium
  on top of it.
- **`FV_premium` is indicative and carry-component only.** Actual
  regional premia also embed duty, freight, regional supply/demand, and
  — for `AUP1` specifically — Section 232 tariffs. `premium_richness`
  (`actual − FV`) is where that excluded richness shows up; it is the
  physical signal, never claimed to be "explained" by FV_premium. This
  is why **Rotterdam duty-paid (`AMEUDDP`), not `AUP1`, is compared to
  FV_premium in S3** — `AUP1` has tariffs baked directly into the print,
  making it a poor pure-carry proxy even though it's shown for context
  throughout.
- **Contango sign is explicit**: `LMAHDS03 − LMAHDY`, positive = contango.
  A positive `contango` above the `breakeven_contango` line is what
  makes the carry trade profitable — below it (or in backwardation),
  carry P&L is negative.

## S1 — Header / KPI

MW premium (`AUP1` × 2204.62), Rotterdam DP (`AMEUDDP`), LME cash + 3M,
contango, `carry_pnl` at the sidebar's carry horizon, and a three-way
regime badge (`utils.finance.classify_carry_regime`):

- **BACKWARDATION** — 3M < cash; no cash-and-carry is possible at all.
- **CONTANGO-CARRY ATTRACTIVE** — contango exceeds `breakeven_contango`.
- **NEUTRAL** — contango is positive but doesn't clear the breakeven.

Default chart date range is the last 3 years, same convention as page 1.

## S2 — Regional premia panel

`AUP1` (daily) and `AMEUDDP` (monthly) plotted on the same USD/t axis,
plus their spread (`MWP − Rotterdam`, computed on the ffilled daily grid,
labeled as such). Annotated qualitatively: the 2018 Section 232 tariff,
the 2021-22 EU energy-price-driven premium spike, and the 2025 tariff
escalation (which the `AUP1` data itself shows starting almost exactly
in 2025-01 — see "Data caveats"). **EU and US only** — there is no Japan
MJP premium series in the verified ticker list, so it's explicitly out
of scope rather than silently missing. `DXY`/`EURUSD` are available as an
optional macro-context overlay (sidebar checkbox) — loaded and verified,
but not part of any FV/carry formula.

## S3 — Premium vs fair value

`FV_premium` vs the **Rotterdam** premium (both resampled to Rotterdam's
native monthly cadence — `FV_premium` resampled down, not Rotterdam
forward-filled up, so the chart doesn't imply daily precision Rotterdam
doesn't have). `premium_richness = actual − FV` is shaded **RICH**
(physical S/D pushing the premium above pure carry economics) vs
**CHEAP** (carry-justified or below). `AUP1` is deliberately not used
here — see "Core economics" for why.

## S4 — Carry trade (differentiator)

Models the 2009-14 LME warehouse-queue trade run at scale by Goldman
Sachs, Glencore, and Trafigura (notably through Detroit-area warehouses):
buy cash metal, sell forward, finance and store it. `carry_pnl = contango
− financing_cost − warehouse_rent`, shaded **PROFITABLE-CARRY** where
positive. A `go.Waterfall` chart (Plotly's built-in waterfall trace —
reused directly rather than a custom helper) breaks down `carry_pnl` on a
sidebar-selected date: `contango → −financing → −warehouse_rent → net`.
Narrative: positive carry pulls metal into warehouses and out of the
deliverable pool — less metal reaching consumers pushes premia up
further, which historically reinforced the trade instead of closing it
(higher premia don't affect the LME cash/3M spread the trade depends on).

## S5 — Contango/financing regime

LME cash vs 3M term structure, shaded green (contango) / salmon
(backwardation). A second chart overlays actual contango against
`breakeven_contango = financing_cost + warehouse_rent`, shaded where
carry is viable (contango above the line). Higher rates (`USGGT10Y` +
spread, or the flat override) widen the breakeven and make carry harder
to clear — stated explicitly in-app.

## S6 — Supply context (optional, degrades gracefully)

IAI total (`IPAITITL`) + regional (`IPAITIEU`/`NA`/`AS`/`AF`/`LA`/`OC`)
primary aluminium production, monthly, ×1000 → t (explicit resample/
conversion). Behind a sidebar checkbox, off by default. Because every
`IPAITI*` series stops at 2014-12-31, this section shows production over
its own native range rather than clipped to the page's (recent) default
date range — clipping would render an empty chart. The 2022 EU smelter
curtailment narrative (energy-cost-driven capacity cuts feeding the EU
premium spike shaded in S2) is stated as general market knowledge only,
since it isn't visible in this stale dataset — the page does not claim
the chart shows something it doesn't.

## Regime badge (page 3)

`utils.finance.classify_carry_regime(contango, breakeven_contango)` —
see S1 above for the three states. Unlike page 1's `classify_regime`
(symmetric deadband around zero), this is a genuinely three-way
classification with two different thresholds (zero, and the breakeven
line), matching the brief's badge wording directly.

## Known limitations (page 3)

- `fin_rate` and `warehouse_rent` are sliders, not real financing/rent
  curves — `USGGT10Y` is a proxy, not an actual borrowing rate, and
  there is no public LME warehouse-rent series at all.
- `FV_premium` prices the carry component only; it is never a complete
  model of the quoted premium (duty, freight, regional S/D, and tariffs
  are real and excluded by construction — see "Core economics").
- IAI production data is 11+ years stale in this dataset; S6 is a
  historical-only supply reference, not a current-conditions panel.

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
| `DXY` | US Dollar Index (reused from page 3, optional context) | index | **monthly** |

### Data caveats found while wiring this page up

Recorded in `config.ZINC_DATA_CAVEATS` and surfaced in an in-app expander
on the page itself:

- **Every zinc series here is monthly, not "daily, gaps" as the brief
  assumed.** One observation per month across the full history for all
  six tickers — the whole page (including the S6 curtailment slider) is
  in months, same precedent as page 2.
- **`LMZSDS03` is a month-end-only index export in this dataset** —
  unlike `LMCADS03`/`LMAHDS03` (the copper/aluminium LME 3-month series,
  genuinely daily with 4000+ rows), this file has 355 rows spanning
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
`config.ZINC_MARGIN_BREAKEVEN_BAND = $40/t`, tighter than page 2's
lithium band since TC-driven zinc margins run in the low hundreds
USD/t, not thousands). A cross-source guard flags material divergence
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
explicitly on a sidebar-selected snapshot date, same pattern as page 3's
carry-P&L waterfall.

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

`utils.finance.consecutive_below(margin, 0, N)` (reused from page 2),
sidebar slider default N=4 **months** (verified-monthly data, not weeks —
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
— same three-way HEALTHY/BREAKEVEN/UNDERWATER wording as page 2's
lithium converter margin, with a narrower $40/t deadband appropriate to
zinc's lower-magnitude margin swings.

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
arb/margin assumptions already used in pages 1 (Cu), 2 (Li), and 4 (Zn) —
not a new source of $/t route freight. Physical traders live and die on
freight; this page shows the freight regime across Baltic vessel classes,
maps each class to the commodities it actually moves, and freight-adjusts
the other pages' existing freight sliders by a Baltic-derived scaler.

**Scope limit, stated up front (also banner-level in-app)**: the Baltic
series are unitless **index points**, not USD/t on any named route — there
is no Cape C5 / Panamax route USD/t series in this dataset, and none is
fabricated here. Freight enters the app two ways only: (a) a **regime
signal** (rolling percentile/z-score, still in index points) and (b) a
unitless **scaler** applied to the existing USD/t freight sliders already
in pages 1/2/4. A dollar figure only ever re-enters by scaling an
*existing* slider assumption — never a new fabricated per-route number.
The one real dollar-freight series anywhere in this app is the Li CIF-FOB
spread (`L4CNSPAU - LCBMAUSF`, page 2's S4), used here to validate the
Baltic proxy, never the reverse.

## Data schema & ticker registry (page 5)

Every ticker/unit/frequency below was checked directly against the CSVs
in `data/csv/` before being wired up. Same finding as every prior page:
everything here is monthly, not daily — plus one more consequential
finding specific to this page (see "Data caveats" below).

| Ticker | Description | Raw unit | Frequency (verified) |
|---|---|---|---|
| `BDIY` | Baltic Dry Index — dry-bulk composite | index pts | **monthly** |
| `BCI14` | Baltic Capesize Index — iron ore/coal, large dry-bulk | index pts | **monthly**, starts 2014-04 |
| `BSI` | Baltic Supramax Index — Cu/Zn conc, spodumene, minor bulk (map's PRIMARY conc/spod proxy) | index pts | **monthly**, **stale — ends 2017-03** |
| `BHSI` | Baltic Handysize Index — smaller conc/spod parcels, minor bulk (practical default proxy here) | index pts | **monthly**, current through 2026-06 |
| `BIDY` | Baltic Dirty Tanker Index — crude (context only) | index pts | **monthly** |
| `BITY` | Baltic Clean Tanker Index — refined products (context only) | index pts | **monthly** |
| `L4CNSPAU` / `LCBMAUSF` | China spod CIF (AU-origin) / spod FOB Australia — reused from page 2 for the ONE real $/t freight series (`CIF - FOB`) | USD/t | **monthly** |
| `CECNVXAQ` / `LMCADY` / `CECN0002` | SHFE cathode / LME cash / Yangshan premium — reused from page 1 for the S4 Cu freight-scaled margin | CNY/t (÷USDCNY) / USD/t / USD/t | **monthly** (resampled here; daily natively on page 1) |
| `AUDUSD` / `USDZAR` / `USDRUB` / `USDTRY` / `USDIDR` / `EURUSD` / `DXY` / `USGGT10Y` | S6 macro/exporter-FX context only | FX/%/index | **monthly** |

### Data caveats found while wiring this page up

Recorded in `config.FREIGHT_DATA_CAVEATS` and surfaced in an in-app
expander on the page itself:

- **All six Baltic series are monthly, not "daily, gaps" as the brief
  assumed** — same finding as pages 2/3/4. The regime window, S3 lead-lag,
  and the scaler are all in months, not weeks.
- **`BSI` (Supramax) — the vessel map's domain-correct PRIMARY conc/spod
  proxy — is stale in this dataset (ends 2017-03) and has ZERO temporal
  overlap with the one real freight-validation series** (`L4CNSPAU -
  LCBMAUSF`, which only starts 2023-09). It genuinely cannot be validated
  here, regardless of what the brief assumes. `BHSI` (Handysize, current
  through 2026-06, the map's secondary conc/spod proxy) is used as the
  **practical default** throughout page 5 and in the back-integrated
  badges on pages 1/2/4; `BSI` remains selectable for domain/historical
  reference with an explicit staleness+no-overlap warning.
- **`BCI14` (Capesize) starts 2014-04** in this dataset — shorter history
  than the other Baltic series, but comfortably covers the page's default
  3Y window.
- **Cross-panel month-end date mismatch**: `L4CNSPAU`/`LCBMAUSF` and the
  Baltic series stamp month-end dates a day or two apart (e.g. calendar
  '30' vs business-day '29'), which silently drops most rows under a raw
  `pd.concat().dropna()`. Every monthly comparison on this page resamples
  through `utils.data.resample_monthly` (`.resample('ME').last().ffill()`)
  onto one canonical grid first — the same explicit-resample idiom used
  throughout pages 1/3 for mixed-frequency series, just applied here to
  fix a mixed-*day-of-month* issue rather than a mixed-frequency one.

## Vessel → commodity map (`config.VESSEL_COMMODITY_MAP`)

The domain-knowledge core of this page — encoded in `config.py`, not
buried in page logic, so it stays the single source of truth:

```
Capesize   (BCI14) -> iron ore, coal, large dry-bulk       — context only
Supramax   (BSI)   -> base-metal concentrates (Cu, Zn),     — PRIMARY proxy for
                       spodumene, minor bulk                  pages 1/2/4 (STALE here)
Handysize  (BHSI)  -> smaller conc/spod parcels, minor bulk — practical default proxy
Dirty tanker (BIDY)-> crude                                 — context only
Clean tanker (BITY)-> refined products                      — context only
```

Cu/Zn concentrate and spodumene move on Supramax/Handysize freight, **not**
Capesize (which is big iron-ore/coal bulk — a different physical trade
lane entirely). Getting this backwards — treating Capesize as the metals
freight proxy because it's the largest, most-watched Baltic sub-index —
would be an instant credibility loss on a page whose entire purpose is
mapping vessel classes to the right commodities.

## Core logic

**Regime transform** (`utils.finance.freight_regime`, reusable — importable
by pages 1/2/4):

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
                                                                  # page-1/2 slider default
```

Both baseline modes are a sidebar selector. `freight_$t_adj` feeds S4,
which calls `utils.finance.import_margin()` (page 1) directly with the
adjusted freight argument instead of duplicating the formula.

**Proxy validation**:

```
implied_freight_real = L4CNSPAU - LCBMAUSF     # USD/t, real AU->China spod freight (page 2's S4)
```

Correlated (monthly, differenced for stationarity) against `BSI`/`BHSI`
via the same `cross_corr`/`peak_lag` engine pages 1/4 use. This is the
credibility-anchor exercise the brief calls for — see S3 for why it's
reported as a weak/inconclusive result in this dataset rather than a
clean confirmation.

## S1 — Header / KPI

Regime badge per vessel class (Capesize/Supramax/Handysize/Dirty/Clean —
`utils.finance.freight_regime_badge`), BDI level + trailing percentile,
the real spod implied-freight $/t, and the scope-limit banner. Every
metric's delta shows its *observation date*, not "today" — `BSI`'s badge
visibly reads 2017-03 while everything else reads 2026-06, so staleness
is self-evident on the metric itself rather than only in a footnote.
Default chart date range is the last 3 years, same convention as pages 1-4.

## S2 — Freight regime panel

All six Baltic indices rebased to 100 at the selected window's start (so
vessel classes with very different absolute point levels are visually
comparable), with the sidebar-selected vessel's LOW/HIGH regime shaded
green/red across the whole panel. The vessel→commodity legend and the
"why Supramax/Handysize, not Capesize" rationale are restated directly
under the chart.

## S3 — Proxy validation (credibility anchor, reported as-observed)

`implied_freight_real` (CIF-FOB, page 2's real dollar freight) plotted
against `BSI` and `BHSI` on a dual axis, plus a peak-lag/correlation
summary table (`cross_corr`/`peak_lag`, monthly, differenced). **Actual
result in this dataset**: `BSI` has zero temporal overlap with the real
freight series (BSI ends 2017-03; the CIF-FOB spread only starts
2023-09) and genuinely cannot be validated here. `BHSI` does overlap
(n≈34 months) but the correlation is weak (~0.06-0.2 depending on lag)
and lag-unstable at this sample size — this dataset does **not** cleanly
confirm "Baltic tracks the real spod-freight leg" as a strong empirical
result. The page states this plainly rather than oversell it: the Baltic
scaler used in S4 is a reasonable *directional* proxy under the vessel
map's domain logic, not something this sample statistically proves.
Caveats stated in-app: index-basis mismatch between panels, CIF-FOB
embeds insurance+timing on top of pure freight, and in-sample correlation
≠ causation regardless of the result.

## S4 — Freight-adjusted arb sensitivity

- **Cu** (mirrors page 1): `import_margin()` recomputed at the page's flat
  base-freight slider vs the same freight scaled by the selected vessel
  (Handysize by default). Both lines charted together, shaded wherever
  the sign of the margin flips (arb OPEN↔CLOSED) purely from the freight
  scaling — with everything else held fixed. A metric reports the latest
  $/t swing directly.
- **Li** (mirrors page 2's S4): an assumed baseline freight rate x the
  Baltic scaler (a *prediction*) plotted against the real observed
  CIF-FOB freight leg (`implied_freight_real`). This is a comparison of
  prediction vs observation, not a recomputation of the converter margin
  — large divergence says more about the assumed baseline and the S3
  index-basis mismatch than about a real freight move.
- **Al**: explicitly **light touch** — `premium_fair_value()` (page 3) has
  no explicit ocean-freight term to begin with (Al regional premia are
  carry/duty/tariff-dominated), so freight-scaling it the way Cu/Li are
  scaled would misrepresent a minor lever as a major one. Noted, not
  modeled, per the brief's explicit scope call.
- **Zn**: not included in S4 — the smelter-margin formula (`smelter_margin`,
  page 4) has no freight term either (it's a TC/treatment-charge business,
  not a freight-exposed physical-arb business), so there is no margin leg
  to freight-adjust.

## S5 — Cross-commodity freight dashboard

Small multiples — one mini-chart per Baltic series (composite + 5 vessel
classes), each with its own regime shading, a one-line commodity/role
caption, and (for Supramax/Handysize) `st.page_link` buttons straight to
pages 1/2/4 — a one-glance "freight state of the physical complex."

## S6 — Macro/FX context (optional, degrades gracefully)

BDI vs `DXY`/`USGGT10Y` (bulk demand/financing backdrop) and exporter FX
(`USDZAR` South Africa, `USDRUB` Russia, `USDIDR` Indonesia, plus
`AUDUSD`/`EURUSD`) as flow-cost context — qualitative only, explicitly
stated as feeding no calc anywhere in the app. Each panel degrades to a
caption (not a crash) if its ticker is unavailable.

## Back-integration into pages 1/2/4

`utils.finance.freight_regime()` and `freight_regime_badge()` are
reusable, importable functions (not page-5-specific), so pages 1, 2, and
4 each load `BHSI` and render one extra "Freight regime (Handysize, ctx)"
KPI column in their existing S1 header row. This is purely additive and
import-only — it does not feed into any margin/arb calc on those pages,
degrades to "n/a" if `BHSI` is unavailable, and uses Handysize rather than
the map's nominal-primary Supramax for the same staleness reason
documented above.

## Known limitations (page 5)

- Baltic indices are index points, never converted to $/t — there is no
  named-route dollar freight series in this dataset, and this page does
  not fabricate one.
- `BSI` (the vessel map's domain-correct primary conc/spod proxy) cannot
  be validated against the real freight series in this dataset at all
  (zero overlap); `BHSI`'s validation result is weak/inconclusive, not a
  confirmed empirical finding — stated plainly in S3 rather than glossed
  over.
- The S4 Cu/Li freight sliders (base freight, baseline AU→China rate)
  mirror but do not read page 1/2's live sidebar state — they are
  independent widgets with matching defaults, not a cross-page-linked
  parameter.
- The Al and Zn pages are deliberately excluded from the S4 recompute (see
  S4 above) rather than forced into a freight-scaling frame that doesn't
  fit their economics.
