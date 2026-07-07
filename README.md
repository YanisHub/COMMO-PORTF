# Commodity Physical Desk Monitor

A multi-page Streamlit app modeling physical-commodity-desk logic: arb
windows, premia lead-lag, and tightness signals. Page 2 is the **Lithium
Conversion Margin** monitor — spodumene-to-carbonate Chinese converter
P&L, tracking the 2023-25 lithium crash into margin compression and a
curtailment-risk signal. Page 3 is the **Aluminium Premia Fair-Value &
Carry** monitor — Rotterdam/US Midwest premia vs a carry-component fair
value, and the classic 2009-14 warehouse cash-and-carry trade.

Built for **correctness and clarity over UI polish**: every displayed
number carries an explicit unit, every non-trivial assumption is called
out in the app itself (warning banners) and here.

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

## Project structure

```
streamlit_app.py                        # landing page, nav explainer
pages/2_Lithium_Conversion_Margin.py    # page 2 (S1-S6)
pages/3_Aluminium_Premia.py             # page 3 (S1-S6)
utils/data.py                 # load_ticker_raw, get_dataset, to_usd_per_tonne,
                               # resample_weekly/monthly, ensure_usdcny_csv
utils/finance.py              # cross_corr, peak_lag, classify_regime, contango,
                               # breakeven_contango, premium_fair_value, carry_pnl,
                               # premium_richness, classify_carry_regime,
                               # converter_margin, consecutive_below
config.py                     # ticker -> CSV file map + unit metadata (single source of truth),
                               # ALUMINIUM_DATA_CAVEATS, LITHIUM_DATA_CAVEATS
data/csv/                     # Bloomberg-export CSVs, one per ticker (+ cached USDCNY.csv)
requirements.txt
```

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
| `USDCNY` | CNY spot (fetched from Yahoo Finance, cached to CSV) | CNY per USD | daily |

### Data caveats found while wiring this page up

Recorded in `config.LITHIUM_DATA_CAVEATS` and surfaced in an in-app
expander on the page itself:

- **Every spod/carbonate series + `AUDUSD` are monthly, not daily.** The
  brief's data table said "daily, gaps"; inspecting the CSVs directly
  showed one month-end print per month for all of them (effectively zero
  gaps against a month-end calendar — a single missing month in `SVPA`).
  The whole page treats these as monthly: no daily resample is attempted,
  and the S6 curtailment slider counts **consecutive months**, not weeks.
  `USDCNY` is the one genuinely daily series here (fetched via
  `utils.data.ensure_usdcny_csv`), which is what its CNY/t→USD/t conversion
  relies on.
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

## Unit discipline (page 2)

- `L4CNMJGO` is the only CNY/t series here — converted via
  `to_usd_per_tonne()`'s existing `cny_t` path (÷ `USDCNY`, same-day
  forward-filled). Every other series is already USD/t (factor 1).
- CNY/t and USD/t are never mixed silently — the one CNY/t series is
  converted before it touches any calc, and the conversion is flagged in
  the S1 warnings expander whenever `USDCNY` is unavailable.
- All conversions live in `config.TICKERS` + `utils/data.to_usd_per_tonne()`
  — no magnitude-guessing, same as page 3.

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
(`utils.finance.classify_regime` with page-2-specific labels and a wide
deadband):

- **HEALTHY** — margin > `config.LITHIUM_MARGIN_BREAKEVEN_BAND` ($100/t).
- **BREAKEVEN** — within the ±$100/t deadband (wide, since lithium
  conversion margins run in the hundreds-to-thousands of USD/t — the band
  absorbs assumption noise around `conversion_ratio`/`conv_cost`, not just
  data noise).
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
smoothed over).

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
— a generic three-state classifier with configurable labels/deadband, so
this page's HEALTHY/BREAKEVEN/UNDERWATER vocabulary doesn't require its
own bespoke classification logic.

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
  grid wherever they feed a calculation (financing rate, richness) —
  stated explicitly in-app (S1 frequency-note banner), not a silent
  frequency mismatch.
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
  in-app, never silent.
- All conversions live in `config.TICKERS` + `utils/data.to_usd_per_tonne()`
  — no magnitude-guessing.

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

Default chart date range is the last 3 years, same convention as page 2.

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
see S1 above for the three states. Unlike `classify_regime`'s symmetric
deadband around zero, this is a genuinely three-way classification with
two different thresholds (zero, and the breakeven line), matching the
brief's badge wording directly.

## Known limitations (page 3)

- `fin_rate` and `warehouse_rent` are sliders, not real financing/rent
  curves — `USGGT10Y` is a proxy, not an actual borrowing rate, and
  there is no public LME warehouse-rent series at all.
- `FV_premium` prices the carry component only; it is never a complete
  model of the quoted premium (duty, freight, regional S/D, and tariffs
  are real and excluded by construction — see "Core economics").
- IAI production data is 11+ years stale in this dataset; S6 is a
  historical-only supply reference, not a current-conditions panel.

