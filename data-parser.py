import json
import re
from pathlib import Path

import pandas as pd

SRC = Path("data/datacommo.xlsx")
CSV_DIR = Path("data/csv")
JSON_PATH = Path("data/tickers.json")

# Short descriptions for well-known Bloomberg tickers that don't carry an
# in-sheet description column. Extend as needed.
KNOWN_DESCRIPTIONS = {
    "LMCADS03 LME Comdty": "LME Copper 3-month price",
    "LMCADY LME Comdty": "LME Copper cash price",
    "LMAHDS03 LME Comdty": "LME Aluminum 3-month price",
    "LMAHDY LME Comdty": "LME Aluminum cash price",
    "LMCODY LME Comdty": "LME Cobalt cash price",
    "LMNIDS03 LME Comdty": "LME Nickel 3-month price",
    "CU1 COMB Comdty": "COMEX Copper generic 1st future",
    "COMXCOPR Index": "COMEX copper warehouse stocks",
    "CL1 Comdty": "WTI crude oil generic 1st futures contract",
    "W 1 Comdty": "CBOT wheat generic 1st futures contract",
    "KW1 Comdty": "Kansas HRW wheat generic 1st futures contract",
    "QS1 Comdty": "ICE low sulphur gasoil generic 1st futures contract",
    "CO1 Comdty": "ICE Brent crude oil generic 1st futures contract",
    "CHIPYOY Index": "China industrial production, year-over-year",
    "CPMINDX Index": "China manufacturing PMI",
    "CNLNNEW Index": "China new yuan loans",
    "EURUSD Curncy": "Euro / US dollar exchange rate",
    "USDZAR Curncy": "US dollar / South African rand exchange rate",
    "BHSI Index": "Baltic Handysize Index",
    "DOEASCRD Index": "US DOE weekly crude oil inventories",
    "WCIDCOMP Index": "Drewry World Container Index, composite",
    "WCIDSHRO Index": "Drewry World Container Index, Shanghai-Rotterdam",
    "WCIDROSH Index": "Drewry World Container Index, Rotterdam-Shanghai",
    "WCIDSHLA Index": "Drewry World Container Index, Shanghai-Los Angeles",
    "LMZSDS03 LME Index": "LME zinc 3-month price",
    "AUDUSD Curncy": "Australian dollar / US dollar exchange rate",
    "USDIDR Curncy": "US dollar / Indonesian rupiah exchange rate",
    "USDRUB Curncy": "US dollar / Russian ruble exchange rate",
    "USDTRY Curncy": "US dollar / Turkish lira exchange rate",
    "DXY Curncy": "US Dollar Index",
    "USGGT10Y Index": "US 10-year Treasury yield",
    "BDIY Index": "Baltic Dry Index",
    "BCI14 Index": "Baltic Capesize Index",
    "BSI Index": "Baltic Supramax Index",
}


def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\-. ]", "_", name)
    return re.sub(r"\s+", " ", name).strip()


def find_row(col0: list[str], label: str) -> int | None:
    for i, v in enumerate(col0):
        if str(v).strip() == label:
            return i
    return None


def parse_sheet(xl: pd.ExcelFile, sheet_name: str):
    raw = xl.parse(sheet_name, header=None)
    col0 = [str(v) for v in raw.iloc[:, 0]]

    security_idx = find_row(col0, "Security")
    date_idx = find_row(col0, "Date")
    if security_idx is None or date_idx is None:
        return None, None, None

    ticker = raw.iloc[security_idx, 1]
    if pd.isna(ticker):
        return None, None, None
    ticker = str(ticker).strip()

    # Description: any non-empty cell in the "Security" row, past column 1.
    description = ""
    for c in range(2, raw.shape[1]):
        val = raw.iloc[security_idx, c]
        if pd.notna(val) and str(val).strip():
            description = str(val).strip()
            break

    # Data header row (Date, PX_LAST, PX_BID, ...)
    header_vals = raw.iloc[date_idx]
    data_cols = [c for c in range(raw.shape[1]) if pd.notna(header_vals[c])]
    col_names = [str(header_vals[c]).strip() for c in data_cols]

    data = raw.iloc[date_idx + 1 :, data_cols].copy()
    data.columns = col_names
    data = data.dropna(how="all")
    data = data.dropna(subset=[col_names[0]])

    # Drop entirely-empty value columns (e.g. PX_BID never populated).
    for c in col_names[1:]:
        if data[c].isna().all():
            data = data.drop(columns=[c])

    data = data.reset_index(drop=True)
    return ticker, description, data


def main():
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    xl = pd.ExcelFile(SRC)

    tickers_info = {}
    used_filenames = set()

    for sheet_name in xl.sheet_names:
        ticker, description, data = parse_sheet(xl, sheet_name)
        if ticker is None:
            print(f"skipping sheet {sheet_name!r}: no Security/Date row found")
            continue

        if not description:
            description = KNOWN_DESCRIPTIONS.get(ticker, "")

        filename = sanitize_filename(ticker) + ".csv"
        if filename in used_filenames:
            filename = sanitize_filename(f"{ticker} {sheet_name}") + ".csv"
        used_filenames.add(filename)

        data.to_csv(CSV_DIR / filename, index=False)
        tickers_info[ticker] = description

        print(f"{sheet_name!r:25s} -> {ticker!r:30s} rows={len(data):5d} desc={description!r}")

    with open(JSON_PATH, "w") as f:
        json.dump(tickers_info, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(tickers_info)} CSV files to {CSV_DIR}/")
    print(f"Wrote ticker descriptions to {JSON_PATH}")


if __name__ == "__main__":
    main()
