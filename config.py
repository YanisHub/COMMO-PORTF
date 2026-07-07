"""
Single source of truth for ticker -> CSV file mapping and unit metadata.

Every other module (utils/data.py, utils/finance.py, pages/*) reads unit
assumptions from TICKERS below instead of hard-coding conversion factors.
That way a unit fix only has to happen in one place.

REVISION 2026-07-04 — page 3 (Aluminium Premia) tickers, checked directly
against the CSVs before wiring them up:

- `AMEUDDP`, `USGGT10Y`, `DXY`, and `EURUSD` are all natively **monthly**
  in this dataset (~150-355 rows spanning years, one obs/month), not
  daily as the initial brief assumed. `LMAHDY`/`LMAHDS03`/`AUP1` are
  genuinely daily. Page 3 forward-fills the monthly series onto the daily
  LME grid where they feed a calc (financing rate, richness), and states
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
  weeks, since there's no weekly grid to count against.
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
#   "fx"       - FX rate itself, not a commodity price series
# factor: multiplicative constant applied to the raw value (for "usd_t",
#   "short_ton", "lb" kinds). Ignored for "cny_t" (FX division instead) and
#   "fx".
# freq: nominal native frequency of the series ("D", "W", "M") — used by
#   the resample helpers and surfaced in the UI so nobody mixes a monthly
#   series into a daily chart without knowing it.
TICKERS = {
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
}

# Default regime-classification deadband (see utils.finance.classify_regime).
# Pages override this explicitly with their own band where the margin scale
# differs (e.g. LITHIUM_MARGIN_BREAKEVEN_BAND below).
REGIME_MARGINAL_BAND = 20  # |margin| <= this => MARGINAL

# Page 2 (Lithium) HEALTHY / BREAKEVEN / UNDERWATER badge deadband, USD/t of
# Li2CO3. Wider than REGIME_MARGINAL_BAND above because conversion margins
# here run in the hundreds-to-thousands of USD/t — this absorbs
# slider/assumption noise (conversion_ratio, conv_cost) around zero, not
# just data noise.
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
}

# Default regime-transform thresholds (utils.finance.freight_regime /
# freight_regime_badge) — kept as the functions' fallback defaults even
# though no page in this build calls them directly.
FREIGHT_REGIME_WINDOW_DEFAULT = 36
FREIGHT_LOW_PCT = 25.0
FREIGHT_HIGH_PCT = 75.0
