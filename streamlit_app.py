"""
Commodity Physical Desk Monitor — landing page.

Multi-page Streamlit app. Each page is a standalone physical-trade monitor
built on the shared utils/data.py and utils/finance.py modules (ticker
loading, unit conversion, arb/lead-lag math).
"""

import streamlit as st

st.set_page_config(page_title="Commodity Physical Portfolio", layout="wide")

st.title("Commodity Physical Portfolio")
st.markdown(
    """
Portfolio project modeling physical-commodity-desk logic: arb windows, premia
lead-lag, and tightness signals across metals. You can review any non-trivial assumptions in the README.md file.

### Pages

- **1 — Copper East-West Arb Monitor** —> SHFE-LME import arb,
  Yangshan premium lead-lag vs SHFE destocking, and a US scrap-discount
  tightness cross-check.
- **2 — Lithium Conversion Margin** —> spodumene-to-carbonate
  Chinese converter margin, the 2023-25 crash into margin compression, a
  spodumene FOB-vs-CIF freight leg, and a curtailment-risk signal.
- **3 — Aluminium Premia Fair-Value & Carry** -> Rotterdam/US
  Midwest premia vs a carry-component fair value (LME contango, financing,
  warehouse rent), and the classic 2009-14 warehouse cash-and-carry trade.
- **4 — Zinc Smelter Margin**  -> conc TC-to-metal conversion into
  a China custom-smelter margin cycle, the dual trader/smelter P&L off one
  TC series, a curtailment-risk signal, and an acid-credit sensitivity check.
- **5 — Freight Overlay** -> Baltic vessel-class indices as a
  cross-basin freight regime signal, a vessel-to-commodity map (Supramax/
  Handysize for conc & spodumene, not Capesize), a proxy-validation check
  against the one real dollar-freight series in this app, and a freight
  scaler that feeds back into pages 1/2/4's arb/margin assumptions.

Use the sidebar to navigate between pages.
"""
)

st.caption("Data is read from `data/csv/`.")
