"""
Ticker-agnostic loading and unit conversion.

Design notes
------------
- Every loader returns data AND a list of human-readable warning strings.
  Callers (pages) are expected to surface those warnings in the UI rather
  than swallow them — "no silent assumptions" is a hard requirement for
  this desk-facing app.
- Real Bloomberg exports are treated as untrusted: missing files, NaN gaps,
  and unexpected magnitudes must degrade gracefully, never crash the app.
- Unit conversion is a single explicit `factor` per ticker (config.py),
  looked up and applied directly — no magnitude-based guessing. That
  approach was used in an earlier revision for tickers whose quoting
  convention hadn't been verified yet; now that every ticker has been
  checked on the terminal, guessing would only hide a wrong `factor` in
  config.py instead of surfacing it. See config.py's revision note.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import config


# ---------------------------------------------------------------------------
# Raw loading
# ---------------------------------------------------------------------------
def _read_bloomberg_csv(path: Path) -> pd.Series:
    """Read a Bloomberg-export-style CSV (cols: Date, PX_LAST[, PX_BID, ...])
    or a plain (date, value) CSV, and return a sorted Series named 'value'
    indexed by Date."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    date_col = "Date" if "Date" in df.columns else "date"
    value_col = "PX_LAST" if "PX_LAST" in df.columns else "value"
    df[date_col] = pd.to_datetime(df[date_col])
    s = df.set_index(date_col)[value_col].astype(float)
    s.index.name = "date"
    s.name = "value"
    return s.sort_index()


def load_ticker_raw(ticker: str) -> tuple[pd.Series | None, str | None]:
    """Load the raw (unconverted) series for one ticker.

    Returns (series, warning). series is None if the ticker/file is
    missing or unreadable — caller must handle that and keep going.
    """
    meta = config.TICKERS.get(ticker)
    if meta is None:
        return None, f"'{ticker}' is not a registered ticker in config.py"

    path = config.DATA_DIR / meta["file"]
    if not path.exists():
        return None, f"data unavailable: {ticker} ({meta['desc']}) — file not found: {path.name}"

    try:
        s = _read_bloomberg_csv(path)
    except Exception as exc:  # noqa: BLE001 - real exports are unpredictable
        return None, f"data unavailable: {ticker} — failed to parse {path.name} ({exc})"

    if s.dropna().empty:
        return None, f"data unavailable: {ticker} — file has no non-null observations"

    return s, None


# ---------------------------------------------------------------------------
# USDCNY: fetched from Yahoo Finance once, then cached to CSV like any other
# ticker ("next times just load it like any other ticker"). A forced
# refetch is supported (sidebar button / --refresh-fx-equivalent) for when
# the cached FX series goes stale.
# ---------------------------------------------------------------------------
def ensure_usdcny_csv(force: bool = False) -> str | None:
    """Make sure data/csv/USDCNY.csv exists. Fetch from Yahoo Finance on
    first run (or when force=True) and cache it in the same (Date, PX_LAST)
    schema as the Bloomberg exports. Returns a warning string on failure,
    else None."""
    path = config.DATA_DIR / config.TICKERS["USDCNY"]["file"]
    if path.exists() and not force:
        return None

    try:
        import yfinance as yf

        hist = yf.download("CNY=X", period="max", progress=False, auto_adjust=False)
        if hist is None or hist.empty:
            return "USDCNY: Yahoo Finance returned no data — CNY/t series will be left unconverted."

        close = hist["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        out = pd.DataFrame({"Date": close.index.tz_localize(None) if close.index.tz else close.index,
                             "PX_LAST": close.values})
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        out.to_csv(path, index=False)
        return None
    except Exception as exc:  # noqa: BLE001 - no network, package missing, etc.
        return f"USDCNY: fetch from Yahoo Finance failed ({exc}) — CNY/t series will be left unconverted."


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------
def to_usd_per_tonne(
    ticker: str, raw: pd.Series, usdcny: pd.Series | None = None
) -> tuple[pd.Series, str | None]:
    """Convert a raw series to USD/t (or the natural tonnes unit for stock
    series) using the verified factor/kind in config.py. Returns
    (converted_series, note); note is only non-None when something about
    the conversion needs flagging (e.g. missing FX), not on every call —
    a verified factor-1 pass-through isn't an "assumption" worth a banner.
    """
    meta = config.TICKERS[ticker]
    kind = meta["kind"]
    factor = meta.get("factor", 1.0)

    if kind in ("usd_t", "short_ton", "lb"):
        return raw * factor, None

    if kind == "cny_t":
        if usdcny is None or usdcny.dropna().empty:
            return raw, f"{ticker}: USDCNY unavailable — series left in CNY/t, NOT converted to USD/t."
        fx = usdcny.reindex(raw.index).ffill()
        converted = raw / fx
        return converted, f"{ticker}: converted CNY/t → USD/t using same-day USDCNY (forward-filled)."

    if kind == "fx":
        return raw, None

    return raw, None


# ---------------------------------------------------------------------------
# Bulk loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_all_raw(tickers: list[str]) -> tuple[dict[str, pd.Series], list[str]]:
    """Load raw (unconverted) series for a list of tickers.
    Missing/broken tickers are skipped with a warning, never raise."""
    series: dict[str, pd.Series] = {}
    warnings: list[str] = []

    if "USDCNY" in tickers:
        w = ensure_usdcny_csv()
        if w:
            warnings.append(w)

    for tk in tickers:
        s, w = load_ticker_raw(tk)
        if s is not None:
            series[tk] = s
        if w:
            warnings.append(w)
    return series, warnings


@st.cache_data(show_spinner=False)
def get_dataset(
    tickers: tuple[str, ...],
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], list[str]]:
    """Single entry point pages should call: loads real data for `tickers`
    (always including USDCNY) and returns (raw, converted_usd_t, warnings)."""
    tickers = list(dict.fromkeys(list(tickers) + ["USDCNY"]))
    raw, warnings = load_all_raw(tickers)

    usdcny = raw.get("USDCNY")
    converted: dict[str, pd.Series] = {}
    for tk in tickers:
        if tk not in raw:
            continue
        c, note = to_usd_per_tonne(tk, raw[tk], usdcny=usdcny)
        converted[tk] = c
        if note:
            warnings.append(note)
    return raw, converted, warnings


# ---------------------------------------------------------------------------
# Resampling / alignment helpers
# ---------------------------------------------------------------------------
def resample_series(series: pd.Series, rule: str, how: str = "last") -> pd.Series:
    """Resample to an arbitrary frequency (e.g. 'W-FRI', 'ME'). Lower-
    frequency inputs are forward-filled onto the target grid so mixed-
    frequency series (daily prices, weekly stocks, monthly scrap/premia)
    can be compared explicitly rather than silently misaligned."""
    s = series.dropna()
    if s.empty:
        return s
    if how == "last":
        out = s.resample(rule).last()
    elif how == "mean":
        out = s.resample(rule).mean()
    else:
        raise ValueError(f"unknown how={how!r}")
    return out.ffill()


def resample_weekly(series: pd.Series, how: str = "last") -> pd.Series:
    """Resample to a weekly (W-FRI) grid — used for the S4 lead-lag engine."""
    return resample_series(series, "W-FRI", how=how)


def resample_monthly(series: pd.Series, how: str = "last") -> pd.Series:
    """Resample to a month-end grid — used for the S5 scrap discount, which
    is natively monthly (CBB1SPOT)."""
    return resample_series(series, "ME", how=how)


def align_frame(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Outer-join a dict of series into one DataFrame on the date index."""
    return pd.DataFrame(series)


def filter_date_range(series: pd.Series, start, end) -> pd.Series:
    return series.loc[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
