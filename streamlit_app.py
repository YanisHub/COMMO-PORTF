"""
Commodity Physical Desk Monitor — landing page.

Multi-page Streamlit app. Each page is a standalone physical-trade monitor
built on the shared utils/data.py and utils/finance.py modules (ticker
loading, unit conversion, arb/lead-lag math).
"""

import streamlit as st

st.set_page_config(page_title="Commodity Physical Desk Monitor", layout="wide")

st.title("Commodity Physical Desk Monitor")
st.markdown(
    """
Portfolio project modeling physical-commodity-desk logic: arb windows, premia
lead-lag, and tightness signals across metals. Built for correctness and
clarity over UI polish — every displayed number carries an explicit unit,
and every non-trivial assumption is documented in-app and in `README.md`.

### Pages

- **1 — Copper East-West Arb Monitor** *(live)* — SHFE-LME import arb,
  Yangshan premium lead-lag vs SHFE destocking, and a US scrap-discount
  tightness cross-check.
- **4 — Zinc Smelter Margin** *(live)* — conc TC-to-metal conversion into
  a China custom-smelter margin cycle, the dual trader/smelter P&L off one
  TC series, a curtailment-risk signal, and an acid-credit sensitivity check.
- **5 — Freight Overlay** *(live)* — Baltic vessel-class indices as a
  cross-basin freight regime signal, a vessel-to-commodity map (Supramax/
  Handysize for concentrates, not Capesize), and a freight scaler that
  feeds back into pages 1 and 4's arb/margin assumptions.

Use the sidebar to navigate between pages.
"""
)

st.caption("Data is read from `data/csv/`.")
