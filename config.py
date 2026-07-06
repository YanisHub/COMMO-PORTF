"""
Single source of truth for ticker -> CSV file mapping and unit metadata.

Every other module (utils/data.py, utils/finance.py, pages/*) reads unit
assumptions from TICKERS below instead of hard-coding conversion factors.
That way a unit fix only has to happen in one place.

REVISION 2026-07-04 — verified against the Bloomberg terminal directly:
the first pass of this app got two things wrong that are worth recording
so nobody "fixes" them back:

- `CU1` is the SHFE (Shanghai Futures Exchange) generic 1st-future copper
  price, already in USD/t — NOT COMEX, and NOT USD/lb. The first version
  of this app assumed COMEX/USD/lb and ran a magnitude-based auto-detect
  to guess the right conversion; that heuristic happened to land on "skip
  the conversion" by luck, but for the wrong reason. It's now a hard-coded
  factor of 1, like any other already-USD/t ticker.
- `CNMDRCCL` (used for the old S3) turned out to be broken/mis-scaled
  (~$200/t, not a plausible outright import price) and has been dropped
  entirely, along with `CECNWQMM` (only covers 2015-18) and `COPRUSPM`
  (stops updating in 2020). S3 is rebuilt around the S2 import-margin
  series instead of an implied-import-price series. See README.md.

`CBB1SPOT` unit is now also confirmed (USD/lb, monthly) — no more
auto-detection needed there either. The unit registry below uses a single
explicit `factor` per ticker (multiply raw value by `factor` to reach the
target unit), which is far less error-prone than the old magnitude-guessing
approach once the true convention is actually known.

REVISION 2026-07-04 — page 3 (Aluminium Premia) tickers, checked directly
against the CSVs before wiring them up:

- `AMEUDDP`, `USGGT10Y`, `DXY`, and `EURUSD` are all natively **monthly**
  in this dataset (~150-355 rows spanning years, one obs/month), not
  daily as the initial brief assumed. `LMAHDY`/`LMAHDS03`/`AUP1` are
  genuinely daily. Page 3 forward-fills the monthly series onto the daily
  LME grid where they feed a calc (financing rate, richness), the same
  `pd.concat(...).ffill()` idiom page 1 uses for SHFE vs LME, and states
  this explicitly rather than pretending everything is daily.
- `IPAITITL`/`IPAITIEU`/`IPAITINA`/`IPAITIAS`/`IPAITIAF`/`IPAITILA`/
  `IPAITIOC` (IAI production) stop at **2014-12-31** in this dataset —
  11+ years stale as of today. S6 shows them over their own native range
  with that limitation called out; there is no real overlap with the
  premia shown elsewhere on the page to overlay meaningfully.
- `AUP1` (CME MW premium, USD/lb, confirmed) has an anomalous stretch of
  ~11-12.5 (vs. a normal 0.06-0.35 range) from 2013-03 to 2013-08 — most
  likely a units/contract-roll artifact from that era. It's outside any
  default chart window (falls before the page's 3Y default and before
  the 2018 tariff annotation), so it's left in rather than silently
  dropped, per "no dropped tickers" — flagged here instead.
- `AUP1`'s huge 2025-26 run-up (0.24 in 2025-01 to 1.15 USD/lb by
  2026-06) is genuine tariff-shock data, not an error — it lines up with
  the "2025 tariff moves" the brief asks S2 to annotate.

REVISION 2026-07-05 — page 2 (Lithium Conversion Margin) tickers, checked
directly against the CSVs before wiring them up:

- Every spodumene/carbonate series (`L4CNSPI`, `SVPA`, `LICNSPDU`,
  `L4CNSPAU`, `L4CNMJGO`, `LCBMAUSF`) and `AUDUSD` are natively
  **monthly** (month-end prints) in this dataset, not "daily, gaps" as
  the initial brief assumed. There are effectively zero gaps against a
  month-end calendar (one single missing month in `SVPA`). The page
  treats these as monthly throughout — no daily resample is attempted —
  and the curtailment-signal slider (S6) is labeled in **months**, not
  weeks, since there's no weekly grid to count against. `USDCNY` is the
  one series in this set that's genuinely daily (reused from page 1's
  Yahoo-fetch loader), which is what its cny_t conversions rely on
  (reindex + ffill onto whatever monthly date the CNY/t series prints
  on).
- `SVPA` (Fastmarkets spodumene CIF future) genuinely only starts
  2024-10-31 in this dataset — confirmed by direct inspection, not just
  the brief's say-so. Selecting it as the S1 benchmark clips the chart
  start to its first observation and shows a banner; it is never
  backfilled or NaN-padded to look like a longer history.
- `LCBMAUSF`: the generic ticker catalog (`data/tickers.json`) labels
  this "Benchmark Minerals Lithium Carbonate FOB Australia," which would
  put it two orders of magnitude away from every other series here (Li
  carbonate ran ~$5.6k-80.6k/t over this history per `L4CNMJGO`/USDCNY,
  vs. spodumene concentrate at ~$375-6.4k/t). Its actual value range
  (375-6401) and its close, noisy tracking of the CIF spodumene series
  (`L4CNSPI`, spread mean ~-$18/t, std ~$272/t — a plausible CIF-vs-FOB
  freight/basis spread, not a 10-20x price gap) both confirm it is
  **spodumene 6% FOB Australia**, matching the brief, not lithium
  carbonate. Treated as spodumene FOB throughout; the tickers.json label
  is generic/wrong and not repeated in this app.
- `BDIY` (Baltic Dry Index) is carried over from the freight-page ticker
  list as page 2's optional S4 freight-proxy overlay, current through
  2026-06. `BSI` (Baltic Supramax) is also available but stops at
  2017-03 — 9+ years stale — so it's offered in the same selector purely
  as a labeled historical curiosity, never defaulted to, with an explicit
  staleness caveat if picked.

REVISION 2026-07-06 -- page 5 (Freight Overlay) tickers, checked directly
against the CSVs before wiring them up:

- `BCI14`/`BSI`/`BHSI`/`BIDY`/`BITY` (the four additional Baltic vessel-
  class indices beyond `BDIY`) are all natively **monthly** (month-end
  prints) in this dataset, not "daily, gaps" as the brief assumed -- the
  same finding as every prior page. `USDZAR`/`USDIDR` (added for page 5's
  optional exporter-FX context) are monthly too.
- `BCI14` (Capesize) genuinely only starts 2014-04 in this dataset --
  shorter history than the other Baltic series, but comfortably covers
  the page's default 3Y window.
- `BSI` (Supramax) is the domain-correct PRIMARY freight proxy for
  concentrate/spodumene per the vessel->commodity map (see
  `VESSEL_COMMODITY_MAP` below) -- but it stops 2017-03 in this dataset,
  9+ years before the one real dollar-freight series this app can check
  it against (`L4CNSPAU - LCBMAUSF`, which only exists 2023-09 onward).
  The two series have **zero temporal overlap** -- BSI cannot actually be
  validated in this dataset, full stop, regardless of what the brief
  assumes. `BHSI` (Handysize), the map's secondary conc/spod proxy, is
  current through 2026-06 and is used as the PRACTICAL default proxy on
  page 5 instead -- BSI remains selectable for domain-reference/historical
  context with an explicit staleness+no-overlap warning. See
  `FREIGHT_DATA_CAVEATS` and page 5's S3 for the (weak/inconclusive, all
  correlations shown as-observed) proxy-validation result against `BHSI`.
"""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "csv"

# ---------------------------------------------------------------------------
# Conversion constants
# ---------------------------------------------------------------------------
LB_TO_TONNE = 2204.62          # 1 metric tonne = 2204.62 lb
SHORT_TON_TO_TONNE = 0.907185  # 1 US short ton = 0.907185 metric tonnes
KT_TO_TONNE = 1000.0           # IAI production series are quoted in thousands of tonnes

# ---------------------------------------------------------------------------
# Ticker registry
# ---------------------------------------------------------------------------
# unit: unit of the RAW value as found in the CSV (verified on the terminal)
# kind: how utils.data.to_usd_per_tonne() should treat the series:
#   "usd_t"    - already USD/t (or already the correct tonnes unit), factor
#                applied directly, no FX or magnitude-guessing involved
#   "short_ton"- warehouse stock in US short tons -> metric tonnes
#   "cny_t"    - CNY/t, needs division by USDCNY to get USD/t
#   "lb"       - USD/lb -> USD/t via factor
#   "fx"       - FX rate itself, not a copper series
# factor: multiplicative constant applied to the raw value (for "usd_t",
#   "short_ton", "lb" kinds). Ignored for "cny_t" (FX division instead) and
#   "fx".
# freq: nominal native frequency of the series ("D", "W", "M") — used by
#   the resample helpers and surfaced in the UI so nobody mixes a monthly
#   series into a daily chart without knowing it.
TICKERS = {
    "LMCADY": {
        "file": "LMCADY LME Comdty.csv",
        "desc": "LME Copper cash",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "D",
    },
    "LMCADS03": {
        "file": "LMCADS03 LME Comdty.csv",
        "desc": "LME Copper 3-month",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "D",
    },
    "CU1": {
        "file": "CU1 COMB Comdty.csv",
        "desc": "SHFE Copper generic 1st future",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,  # SHFE, already USD/t — do NOT apply a lb conversion
        "freq": "D",
    },
    "SHFCCOPD": {
        "file": "SHFCCOPD Index.csv",
        "desc": "SHFE Cu deliverable warehouse stocks",
        "unit": "t",
        "kind": "usd_t",  # not a price, but factor=1 pass-through fits the same path
        "factor": 1.0,
        "freq": "W",
    },
    "SHFCCOPO": {
        "file": "SHFCCOPO Index.csv",
        "desc": "SHFE Cu on-warrant stocks",
        "unit": "t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "W",
    },
    "COMXCOPR": {
        "file": "COMXCOPR Index.csv",
        "desc": "COMEX Cu warehouse stocks",
        "unit": "short tons",
        "kind": "short_ton",
        "factor": SHORT_TON_TO_TONNE,
        "freq": "D",
    },
    "CECN0002": {
        "file": "CECN0002 Index.csv",
        "desc": "Yangshan premium, warehouse-warrant vs LME spot",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "CECN0001": {
        "file": "CECN0001 Index.csv",
        "desc": "Yangshan premium, B/L vs LME spot",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "CECNVGFA": {
        "file": "CECNVGFA SMET Index.csv",
        "desc": "China electrolytic Cu grade 1 incl SXEW, Shanghai spot (alt SHFE price source)",
        "unit": "CNY/t",
        "kind": "cny_t",
        "factor": 1.0,
        "freq": "M",
    },
    "CECNVXAQ": {
        "file": "CECNVXAQ SMMC Index.csv",
        "desc": "China refined Cu grade 1 99.95% spot (primary SHFE price source)",
        "unit": "CNY/t",
        "kind": "cny_t",
        "factor": 1.0,
        "freq": "M",
    },
    "CNIVCORE": {
        "file": "CNIVCORE Index.csv",
        "desc": "China imports Cu ores & concentrates",
        "unit": "t",
        "kind": "usd_t",
        "factor": 1000.0,  # source is in thousands of tonnes
        "freq": "M",
    },
    "CBB1SPOT": {
        "file": "CBB1SPOT SCMO Index.csv",
        "desc": "NA #1 Cu bare bright scrap spot",
        "unit": "USD/lb",
        "kind": "lb",
        "factor": LB_TO_TONNE,
        "freq": "M",
    },
    "USDCNY": {
        "file": "USDCNY.csv",
        "desc": "USD/CNY spot (fetched from Yahoo Finance, cached to CSV)",
        "unit": "CNY per USD",
        "kind": "fx",
        "factor": 1.0,
        "freq": "D",
    },
    # -----------------------------------------------------------------
    # Page 3 — Aluminium Premia
    # -----------------------------------------------------------------
    "LMAHDY": {
        "file": "LMAHDY LME Comdty.csv",
        "desc": "LME Aluminium cash",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "D",
    },
    "LMAHDS03": {
        "file": "LMAHDS03 LME Comdty.csv",
        "desc": "LME Aluminium 3-month",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "D",
    },
    "AUP1": {
        "file": "AUP1 Comdty.csv",
        "desc": "CME US Midwest aluminium transaction premium (Platts MW), generic 1st future",
        "unit": "USD/lb",
        "kind": "lb",
        "factor": LB_TO_TONNE,  # confirmed USD/lb — wrong scale here is instant credibility loss
        "freq": "D",
    },
    "AMEUDDP": {
        "file": "AMEUDDP HARA Index.csv",
        "desc": "Rotterdam Al ingot premium, duty-paid in-warehouse (Amsterdam-Rotterdam-Antwerp)",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",  # verified monthly on inspection, not daily as originally assumed
    },
    "USGGT10Y": {
        "file": "USGGT10Y Index.csv",
        "desc": "US 10Y Treasury yield (financing-rate proxy)",
        "unit": "%",
        "kind": "usd_t",  # pass-through, factor=1 — not literally USD/t, see desc
        "factor": 1.0,
        "freq": "M",  # verified monthly on inspection, not daily as originally assumed
    },
    "DXY": {
        "file": "DXY Curncy.csv",
        "desc": "US Dollar Index (macro context only — not used in the FV/carry calc)",
        "unit": "index",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",  # verified monthly on inspection, not daily as originally assumed
    },
    "EURUSD": {
        "file": "EURUSD Curncy.csv",
        "desc": "EUR/USD spot (macro context only — not used in the FV/carry calc)",
        "unit": "USD per EUR",
        "kind": "fx",
        "factor": 1.0,
        "freq": "M",  # verified monthly on inspection, not daily as originally assumed
    },
    "IPAITITL": {
        "file": "IPAITITL Index.csv",
        "desc": "IAI primary aluminium production, total (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    "IPAITIEU": {
        "file": "IPAITIEU Index.csv",
        "desc": "IAI primary aluminium production, Europe (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    "IPAITINA": {
        "file": "IPAITINA Index.csv",
        "desc": "IAI primary aluminium production, North America (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    "IPAITIAS": {
        "file": "IPAITIAS Index.csv",
        "desc": "IAI primary aluminium production, Asia (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    "IPAITIAF": {
        "file": "IPAITIAF Index.csv",
        "desc": "IAI primary aluminium production, Africa (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    "IPAITILA": {
        "file": "IPAITILA Index.csv",
        "desc": "IAI primary aluminium production, Latin America (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    "IPAITIOC": {
        "file": "IPAITIOC Index.csv",
        "desc": "IAI primary aluminium production, Oceania (STALE — data ends 2014-12)",
        "unit": "t",
        "kind": "usd_t",
        "factor": KT_TO_TONNE,
        "freq": "M",
    },
    # -----------------------------------------------------------------
    # Page 2 — Lithium Conversion Margin
    # All spod/carbonate series + AUDUSD verified MONTHLY in this
    # dataset (see REVISION 2026-07-05 note above), not daily as the
    # initial brief assumed.
    # -----------------------------------------------------------------
    "L4CNSPI": {
        "file": "L4CNSPI Index.csv",
        "desc": "China spodumene conc CIF index, SC6 (default S1 benchmark)",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "SVPA": {
        "file": "SVPA Comdty.csv",
        "desc": "Spodumene CIF China, Fastmarkets future — data starts 2024-10 only",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "LICNSPDU": {
        "file": "LICNSPDU AMTL Index.csv",
        "desc": "China spodumene Li2O 6% min CIF (cross-check vs L4CNSPI)",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "L4CNSPAU": {
        "file": "L4CNSPAU SMMC Index.csv",
        "desc": "China 6% spodumene conc from Australia, CIF (AU-origin cross-check; "
                "also the S4 CIF comparator for LCBMAUSF FOB Australia)",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "L4CNMJGO": {
        "file": "L4CNMJGO AMTL Index.csv",
        "desc": "China Li carbonate 99.5% battery-grade, DEL — CNY/t, converted via USDCNY",
        "unit": "CNY/t",
        "kind": "cny_t",
        "factor": 1.0,
        "freq": "M",
    },
    "LCBMAUSF": {
        "file": "LCBMAUSF Index.csv",
        "desc": "Spodumene 6% FOB Australia (Benchmark Minerals) — verified spodumene, "
                "NOT lithium carbonate despite the generic tickers.json label; see "
                "REVISION 2026-07-05 note above",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "AUDUSD": {
        "file": "AUDUSD Curncy.csv",
        "desc": "AUD/USD spot (verified monthly in this dataset)",
        "unit": "USD per AUD",
        "kind": "fx",
        "factor": 1.0,
        "freq": "M",
    },
    "BDIY": {
        "file": "BDIY Index.csv",
        "desc": "Baltic Dry Index (freight-rate proxy, index points — not a price) — "
                "optional S4 overlay, current through 2026-06",
        "unit": "index",
        "kind": "usd_t",  # pass-through, factor=1 — not literally USD/t, see desc
        "factor": 1.0,
        "freq": "M",
    },
    "BSI": {
        "file": "BSI Index.csv",
        "desc": "Baltic Supramax Index (STALE — dataset ends 2017-03) — optional S4 "
                "overlay, historical only",
        "unit": "index",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    # -----------------------------------------------------------------
    # Page 4 — Zinc Smelter Margin
    # ALL FIVE tickers below (plus DXY, reused from page 3) are verified
    # MONTHLY (month-end prints) in this dataset, not "daily, gaps" as the
    # initial brief assumed — see REVISION 2026-07-05 note below. TC is a
    # genuine two-sided quantity that goes negative in real data (Z1CNHCOF
    # prints -60 USD/dmt in 2026-06) — worth knowing when reading the S2
    # "spot TC below zero = extreme conc tightness" regime.
    # -----------------------------------------------------------------
    "Z1CNHCOF": {
        "file": "Z1CNHCOF AMTL Index.csv",
        "desc": "China zinc conc TC 50% CIF, spot benchmark (default TC source)",
        "unit": "USD/dmt conc",
        "kind": "usd_t",  # pass-through factor=1 — NOT per-tonne-of-metal, see smelter_margin()
        "factor": 1.0,
        "freq": "M",
    },
    "Z1CNTCIM": {
        "file": "Z1CNTCIM SMMC Index.csv",
        "desc": "China TC imported zinc conc (cross-check/alt source) — data starts 2018-11",
        "unit": "USD/dmt conc",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "LMZSDS03": {
        "file": "LMZSDS03 LME Index.csv",
        "desc": "LME zinc 3-month",
        "unit": "USD/t",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",  # verified monthly in this dataset — unlike LMCADS03/LMAHDS03 (daily),
                        # this file is a month-end-only index export, not the daily contract feed
    },
    "ZNCNMQKY": {
        "file": "ZNCNMQKY SMET Index.csv",
        "desc": "China zinc premium, B/L Shanghai CIF (regional physical premium, NOT a "
                "CNY cathode price) — context only, not part of the margin core",
        "unit": "USD/t",  # verified: values (~90-140) are a USD/t premium, not CNY/t
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "USDRUB": {
        "file": "USDRUB Curncy.csv",
        "desc": "USD/RUB spot (optional macro/FX context — Kazzinc/Russia angle)",
        "unit": "RUB per USD",
        "kind": "fx",
        "factor": 1.0,
        "freq": "M",
    },
    "USDTRY": {
        "file": "USDTRY Curncy.csv",
        "desc": "USD/TRY spot (optional macro/FX context)",
        "unit": "TRY per USD",
        "kind": "fx",
        "factor": 1.0,
        "freq": "M",
    },
    # -----------------------------------------------------------------
    # Page 5 — Freight Overlay
    # `BDIY`/`BSI` already registered above (page 2). The four remaining
    # Baltic vessel-class indices + the two exporter-FX pairs below are
    # all verified MONTHLY in this dataset — see REVISION 2026-07-06 note
    # at the top of this file. NONE of these are converted to $/t: Baltic
    # indices are unitless index points, kept as points end-to-end (see
    # utils.finance's page-5 section and Instructions_FREIGHT.md).
    # -----------------------------------------------------------------
    "BCI14": {
        "file": "BCI14 Index.csv",
        "desc": "Baltic Capesize Index (iron ore/coal, large dry-bulk) — CONTEXT only, not "
                "the conc/spod proxy; starts 2014-04 in this dataset",
        "unit": "index",
        "kind": "usd_t",  # pass-through, factor=1 — index points, never $/t
        "factor": 1.0,
        "freq": "M",
    },
    "BHSI": {
        "file": "BHSI Index.csv",
        "desc": "Baltic Handysize Index (smaller conc/spodumene parcels, minor bulk) — "
                "practical default conc/spod freight proxy on page 5 (Supramax/BSI is stale)",
        "unit": "index",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "BIDY": {
        "file": "BIDY Index.csv",
        "desc": "Baltic Dirty Tanker Index (crude) — context only, no crude-oil page in this app",
        "unit": "index",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "BITY": {
        "file": "BITY Index.csv",
        "desc": "Baltic Clean Tanker Index (refined products) — context only, no "
                "refined-products page in this app",
        "unit": "index",
        "kind": "usd_t",
        "factor": 1.0,
        "freq": "M",
    },
    "USDZAR": {
        "file": "USDZAR Curncy.csv",
        "desc": "USD/ZAR spot (optional macro/exporter-FX context — South Africa dry-bulk "
                "exports)",
        "unit": "ZAR per USD",
        "kind": "fx",
        "factor": 1.0,
        "freq": "M",
    },
    "USDIDR": {
        "file": "USDIDR Curncy.csv",
        "desc": "USD/IDR spot (optional macro/exporter-FX context — Indonesia dry-bulk exports)",
        "unit": "IDR per USD",
        "kind": "fx",
        "factor": 1.0,
        "freq": "M",
    },
}

# Tickers verified on the terminal to be broken/unusable/stale and dropped
# from the app entirely. Kept here (rather than just deleted) so the reason
# is documented and nobody re-adds them by copy-pasting the old list.
DROPPED_TICKERS = {
    "CECNWQMM": "China Cu cathode premium, Shanghai — only covers 2015-2018, stale.",
    "CNMDRCCL": "Implied China import price ex-Chile — values ~$200/t, broken/mis-scaled, unusable.",
    "COPRUSPM": "NA #1 Cu bare bright scrap spot (alt source) — stops updating in 2020.",
}

# Regime classification thresholds for the ARB OPEN / MARGINAL / CLOSED badge
# Applied to the import margin in USD/t (see utils.finance.classify_regime).
REGIME_MARGINAL_BAND = 20  # |margin| <= this => MARGINAL

# China eliminated the export VAT rebate for unwrought/refined copper effective
# this date — a real policy change, not a slider assumption. Before it, the
# VAT embedded in the SHFE purchase price was refunded on export; from this
# date on, none of it is. See utils.finance.export_vat_rebate_series (S2b).
EXPORT_VAT_REBATE_CUTOFF = "2024-12-01"

# Page 2 (Lithium) HEALTHY / BREAKEVEN / UNDERWATER badge deadband, USD/t of
# Li2CO3. Wider than the copper REGIME_MARGINAL_BAND above because conversion
# margins here run in the hundreds-to-thousands of USD/t (vs. copper's ~$20/t
# import-arb band) — this absorbs slider/assumption noise (conversion_ratio,
# conv_cost) around zero, not just data noise.
LITHIUM_MARGIN_BREAKEVEN_BAND = 100.0

# Data caveats specific to page 3 (Aluminium Premia), surfaced in-app so
# nobody mistakes a data artifact for a market signal. See the REVISION
# note at the top of this file for detail.
ALUMINIUM_DATA_CAVEATS = {
    "AMEUDDP/USGGT10Y/DXY/EURUSD": "verified monthly in this dataset, not daily — "
        "forward-filled onto the daily LME grid wherever they feed a calc.",
    "IPAITI*": "IAI production series stop at 2014-12-31 in this dataset (11+ years "
        "stale) — shown over their own native range in S6, not overlaid against "
        "current premia.",
    "AUP1": "an anomalous ~11-12.5 USD/lb stretch from 2013-03 to 2013-08 (vs. a "
        "normal 0.06-0.35 range) is left in the series rather than dropped — it "
        "predates every default chart window on this page.",
}

# Data caveats specific to page 2 (Lithium Conversion Margin), surfaced in-app
# so nobody mistakes a data-frequency or ticker-labeling artifact for a market
# signal. See the REVISION 2026-07-05 note at the top of this file for detail.
LITHIUM_DATA_CAVEATS = {
    "L4CNSPI/SVPA/LICNSPDU/L4CNSPAU/L4CNMJGO/LCBMAUSF/AUDUSD": "verified monthly "
        "(month-end prints) in this dataset, not daily as the initial brief "
        "assumed — every calc and the S6 curtailment slider are in months, not "
        "weeks/days.",
    "SVPA": "genuinely starts 2024-10-31 in this dataset — selecting it as the "
        "S1 benchmark clips the chart to its available range rather than "
        "backfilling.",
    "LCBMAUSF": "the generic ticker catalog labels this \"Lithium Carbonate FOB "
        "Australia,\" but its value range and close tracking of the CIF "
        "spodumene series confirm it is actually spodumene 6% FOB Australia — "
        "treated as spodumene here, not carbonate.",
    "BSI": "stale — this dataset's Baltic Supramax series ends 2017-03. Offered "
        "in the S4 freight-proxy selector for completeness only, never as the "
        "default, with an in-app staleness warning if selected.",
}

# See the REVISION 2026-07-05 (page 4) note further below, next to
# ZINC_DATA_CAVEATS, for the detailed write-up of what was checked on the
# CSVs before wiring up the zinc tickers (all monthly, LMZSDS03's file is a
# month-end-only export unlike the daily copper/aluminium LME series, and
# Z1CNHCOF genuinely prints negative TC in 2026).

# Page 4 (Zinc Smelter Margin) HEALTHY / BREAKEVEN / UNDERWATER badge
# deadband, USD/t of zinc metal. Smaller than the lithium band since TC-based
# smelter margins run in the low hundreds USD/t, not thousands.
ZINC_MARGIN_BREAKEVEN_BAND = 40.0

# China custom-smelter conc->metal stoichiometry defaults (S1 sliders).
ZINC_GRADE_DEFAULT = 0.50       # concentrate grade, fraction Zn (50%)
ZINC_RECOVERY_DEFAULT = 0.955   # smelter metallurgical recovery, fraction

# REVISION 2026-07-05 — page 4 (Zinc Smelter Margin) tickers, checked
# directly against the CSVs before wiring them up:
#
# - `Z1CNHCOF`, `Z1CNTCIM`, `LMZSDS03`, `ZNCNMQKY`, `USDRUB`, `USDTRY` (and
#   `DXY`, reused from page 3) are all natively **monthly** (month-end
#   prints) in this dataset — NOT "daily, gaps" as the initial brief
#   assumed. `LMZSDS03` in particular is notable: unlike `LMCADS03`/
#   `LMAHDS03` (the copper/aluminium LME 3M series, genuinely daily, 4000+
#   rows), the zinc LME file here is a month-end-only index export (355
#   rows spanning 1997-2026, one obs/month) — confirmed by direct
#   inspection, not assumed from the "LME Comdty" vs "LME Index" filename
#   difference alone. The whole page — including the S6 curtailment
#   slider — is therefore in MONTHS, matching page 2's precedent.
# - `Z1CNHCOF` genuinely prints negative TC (-60 to -65 USD/dmt) in
#   2026-05/06 — real data, not a parsing artifact, and exactly the "TC
#   near/below zero = extreme conc tightness" regime the brief's S2
#   describes.
# - `ZNCNMQKY` verified as a genuine USD/t premium (values ~90-140 over
#   its history) — NOT a CNY/t cathode price, confirming the brief's
#   hedge ("verify unit; likely USD/t premium"). Treated as regional
#   physical-premium context (S8), not part of the TC/margin core.
ZINC_DATA_CAVEATS = {
    "Z1CNHCOF/Z1CNTCIM/LMZSDS03/ZNCNMQKY/USDRUB/USDTRY": "verified monthly "
        "(month-end prints) in this dataset, not daily as the initial brief "
        "assumed — every calc and the S6 curtailment slider are in months, "
        "not weeks.",
    "LMZSDS03": "unlike the copper/aluminium LME 3M series (genuinely daily), "
        "this dataset's zinc LME file is a month-end-only index export (355 "
        "rows, 1997-2026) — confirmed by direct inspection.",
    "Z1CNHCOF": "genuinely prints negative TC (-60 to -65 USD/dmt) in "
        "2026-05/06 — real data confirming the 'extreme conc tightness' "
        "regime, not a parsing error.",
    "ZNCNMQKY": "confirmed a genuine USD/t physical premium (B/L basis), not "
        "a CNY/t cathode price — shown as regional context (S8) only, never "
        "folded into the TC/margin core.",
}

# ---------------------------------------------------------------------------
# Page 5 — Freight Overlay
# ---------------------------------------------------------------------------
# Vessel class -> commodity map (domain-knowledge core of page 5). `BDIY`
# (Baltic Dry Index) is the dry-bulk COMPOSITE across all vessel classes —
# shown as the headline "overall dry-bulk regime" signal, not itself tied to
# one commodity. The five entries below are the individual vessel classes.
# Getting Supramax/Handysize (not Capesize) right as the conc/spodumene proxy
# is the single most important domain fact on this page — Capesize is big
# iron-ore/coal bulk, a completely different physical trade lane.
VESSEL_COMMODITY_MAP = {
    "BCI14": {
        "vessel": "Capesize",
        "commodity": "Iron ore, coal, large dry-bulk cargoes",
        "role": "Context only — macro bulk-demand signal. NOT the conc/spodumene proxy "
                "despite being the largest, most-watched Baltic sub-index.",
        "pages": [],
    },
    "BSI": {
        "vessel": "Supramax",
        "commodity": "Base-metal concentrates (Cu, Zn), spodumene, minor bulk",
        "role": "PRIMARY freight proxy for pages 1 (Cu), 2 (Li spodumene), 4 (Zn conc) per "
                "the vessel map — but STALE in this dataset (ends 2017-03, 9+ years stale, "
                "zero overlap with the real freight-validation series). Handysize (BHSI) is "
                "used as the practical default instead; see FREIGHT_DATA_CAVEATS.",
        "pages": ["1_Copper_East_West", "2_Lithium_Conversion_Margin", "4_Zinc_Smelter_Margin"],
    },
    "BHSI": {
        "vessel": "Handysize",
        "commodity": "Smaller concentrate/spodumene parcels, minor bulk",
        "role": "Secondary conc/spodumene proxy per the vessel map — used as the PRACTICAL "
                "default proxy on this page since it is current (through 2026-06) where "
                "Supramax (BSI) is not.",
        "pages": ["1_Copper_East_West", "2_Lithium_Conversion_Margin", "4_Zinc_Smelter_Margin"],
    },
    "BIDY": {
        "vessel": "Dirty tanker",
        "commodity": "Crude oil",
        "role": "Context only — no crude-oil page in this app.",
        "pages": [],
    },
    "BITY": {
        "vessel": "Clean tanker",
        "commodity": "Refined products",
        "role": "Context only — no refined-products page in this app.",
        "pages": [],
    },
}

# Regime transform defaults (utils.finance.freight_regime). Window is in
# PERIODS of whatever frequency the input series actually is — every Baltic
# series here is verified monthly (see REVISION note), so the default of 36
# periods = 3Y, matching every other page's default chart window.
FREIGHT_REGIME_WINDOW_DEFAULT = 36
FREIGHT_LOW_PCT = 25.0
FREIGHT_HIGH_PCT = 75.0

# Data caveats specific to page 5 (Freight Overlay), surfaced in-app so
# nobody mistakes a Baltic index point for a dollar freight rate, or treats
# a stale series as current. See the REVISION 2026-07-06 note above.
FREIGHT_DATA_CAVEATS = {
    "BDIY/BCI14/BSI/BHSI/BIDY/BITY": "verified MONTHLY (month-end prints) in this dataset, "
        "not \"daily, gaps\" as the initial brief assumed — same finding as every prior page. "
        "The regime window, S3 lead-lag, and scaler are all in months, not weeks.",
    "BSI": "genuinely stops 2017-03 in this dataset (9+ years stale) — despite being the "
        "domain-correct PRIMARY conc/spodumene proxy per the vessel map, it has ZERO temporal "
        "overlap with the one real dollar-freight series this app can validate it against "
        "(L4CNSPAU - LCBMAUSF, which only starts 2023-09). Handysize (BHSI, current through "
        "2026-06) is used as the practical default proxy instead; BSI remains selectable for "
        "domain/historical reference with an explicit staleness warning.",
    "BCI14": "starts 2014-04 in this dataset (Capesize) — shorter history than the other "
        "Baltic series but comfortably covers the page's default 3Y window.",
    "Index points (all six Baltic series)": "unitless INDEX POINTS, not USD/t on any named "
        "route — no Cape C5 / Panamax route USD/t series exists in this dataset. Never "
        "converted to a dollar figure. Freight enters the app as (a) a regime signal "
        "(rolling percentile/z-score) and (b) a unitless SCALER applied to the existing "
        "USD/t freight sliders already in pages 1/2/4. The one real dollar freight series in "
        "this app is the Li CIF-FOB spread (L4CNSPAU - LCBMAUSF) — used here to validate the "
        "Baltic proxy, never fabricated the other way around.",
}
