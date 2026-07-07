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

- **2 — Lithium Conversion Margin** *(live)* — spodumene-to-carbonate
  Chinese converter margin, the 2023-25 crash into margin compression, a
  spodumene FOB-vs-CIF freight leg, and a curtailment-risk signal.
- **3 — Aluminium Premia Fair-Value & Carry** *(live)* — Rotterdam/US
  Midwest premia vs a carry-component fair value (LME contango, financing,
  warehouse rent), and the classic 2009-14 warehouse cash-and-carry trade.

Use the sidebar to navigate between pages.
"""
)

st.caption("Data is read from `data/csv/`.")
