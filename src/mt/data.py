"""End-of-day bars from Yahoo Finance, kept in a local parquet cache.

The universe is today's NIFTY 50 (docs/data/nifty50.csv, a snapshot of NSE's list) plus a few
reference series. NSE series share one calendar. USD/INR and the S&P 500 trade on other
calendars, so they have bars on NSE holidays and none on some NSE days: never use them to decide
the NSE session, and drop each column's own NaN rows before computing its returns.

The table's columns are a (field, symbol) MultiIndex. Fields: open, high, low, close, adj_close,
volume. Yahoo's open/high/low/close are split-adjusted, not dividend-adjusted; returns use
adj_close.
"""

import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONSTITUENTS = ROOT / "docs" / "data" / "nifty50.csv"
FIXES = ROOT / "docs" / "data" / "yahoo_fixes.csv"
DATA_PATH = ROOT / "data" / "prices.parquet"
START = "2007-01-01"  # includes 2008
VALID_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")
FIELDS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def _constituents(path: Path = CONSTITUENTS) -> pd.DataFrame:
    table = pd.read_csv(path)
    bad = [s for s in table["symbol"] if not VALID_SYMBOL.match(str(s))]
    if bad:
        raise ValueError(f"invalid symbols in {path.name}: {bad}")
    return table


_TABLE = _constituents()
SYMBOLS: list[str] = _TABLE["symbol"].tolist()
SECTORS: dict[str, str] = dict(_TABLE.set_index("symbol")["industry"])
INDEX = "NIFTY"
NSE_TICKERS = {f"{s}.NS": s for s in SYMBOLS} | {
    "^NSEI": "NIFTY",
    "^NSEBANK": "NIFTYBANK",
    "^INDIAVIX": "INDIAVIX",
    "GOLDBEES.NS": "GOLDBEES",
}
OFF_CALENDAR = {"INR=X": "USDINR", "^GSPC": "SP500"}
TICKERS = NSE_TICKERS | OFF_CALENDAR


class DownloadFailed(Exception):
    """Yahoo left out some symbols (or errored) on every try; nothing was written."""

    def __init__(self, missing: list[str]):
        super().__init__(f"download failed for {', '.join(missing)}")
        self.missing = missing


def error_label(exc: BaseException) -> str:
    """Short, safe text for the header: the exception type, plus the tickers for DownloadFailed."""
    if isinstance(exc, DownloadFailed):
        return f"DownloadFailed ({', '.join(exc.missing)})"
    return type(exc).__name__


def fetch(start: str, end: str | None = None) -> pd.DataFrame:
    """Download every ticker from `start` (inclusive) to `end` (exclusive, default: today)."""
    import yfinance as yf

    # threads=False: parallel downloads can lock yfinance's sqlite cache and drop a ticker
    raw = yf.download(
        list(TICKERS), start=start, end=end, auto_adjust=False, progress=False, threads=False
    )
    raw = raw[list(FIELDS)].rename(columns=FIELDS, level=0).rename(columns=TICKERS, level=1)
    raw.columns.names = ["field", "symbol"]
    raw.index = pd.DatetimeIndex(raw.index.tz_localize(None), name="date")
    return raw.sort_index(axis=1)


def missing_symbols(table: pd.DataFrame, expected: list[str] | None = None) -> list[str]:
    """Symbols with no close at all: an all-empty column or one Yahoo left out."""
    want = expected if expected is not None else list(TICKERS.values())
    fields = table.columns.get_level_values(0)
    close = table["close"] if "close" in fields else pd.DataFrame()
    return [s for s in want if s not in close.columns or close[s].isna().all()]


def download(
    fetch: Callable[[], pd.DataFrame],
    find_missing: Callable[[pd.DataFrame], list[str]],
    attempts: int = 4,
) -> pd.DataFrame:
    """Call `fetch` until `find_missing` reports nothing absent; raise rather than keep a gap.

    Yahoo occasionally drops a ticker or errors, so each download gets a few tries."""
    missing = ["everything"]
    for attempt in range(attempts):
        if attempt:
            time.sleep(5 * attempt)
        try:
            df = fetch()
        except Exception:  # noqa: S112 - network or Yahoo error: retry
            continue
        if not (missing := find_missing(df)):
            return df
    raise DownloadFailed(missing)


def load_cache(path: Path = DATA_PATH, since: pd.Timestamp | None = None) -> pd.DataFrame | None:
    """The cached table (rows from `since` on, if given), or None when there is no cache yet."""
    path = Path(path)
    if not path.exists():
        return None
    filters = [("date", ">=", pd.Timestamp(since))] if since is not None else None
    return pd.read_parquet(path, filters=filters).sort_index()


def _write_atomic(table: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        table.to_parquet(tmp_path)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def update_cache(
    path: Path = DATA_PATH,
    fetch: Callable[..., pd.DataFrame] = fetch,
    overlap_days: int = 7,
) -> pd.DataFrame:
    """Bring the cache up to date and return the whole table.

    First run downloads from 2007. Later runs download from the last cached date minus
    `overlap_days`, so revised bars replace the cached ones. Raises DownloadFailed (cache untouched)
    if Yahoo leaves any ticker out."""
    path = Path(path)
    old = load_cache(path)
    if old is None or old.empty:
        start = START
    else:
        start = (old.index.max() - pd.Timedelta(days=overlap_days)).strftime("%Y-%m-%d")
    new = download(lambda: fetch(start), missing_symbols)
    if old is None or old.empty:
        table = new
    else:
        table = pd.concat([old[~old.index.isin(new.index)], new])
    table = table.dropna(how="all").sort_index().sort_index(axis=1)
    table.columns.names = ["field", "symbol"]
    table.index.name = "date"
    _write_atomic(table, path)
    return table


def flag_adjusted_drops(
    adj: pd.DataFrame, threshold: float = 0.2
) -> list[tuple[str, pd.Timestamp]]:
    """(symbol, date) pairs where an adjusted price falls more than `threshold` in a day.

    Large caps rarely do that for real; each hit is worth checking for an unadjusted split or bonus.
    """
    moves = adj.pct_change(fill_method=None).stack()
    hits = moves[moves < -threshold]
    return [(sym, date) for date, sym in hits.index]


def daily_returns(prices: pd.DataFrame, fixes: Path = FIXES) -> pd.DataFrame:
    """Simple daily returns of adjusted closes, with known Yahoo errors repaired from
    docs/data/yahoo_fixes.csv (each with its source):
    - zero: a corporate action Yahoo did not adjust for; that day's return is set to 0.
    - blank: a bad print; the price is dropped and the previous price carried forward.
    - start: the series is not this company before the date; earlier prices are dropped.
    """
    px = prices.copy()
    table = pd.read_csv(fixes, parse_dates=["date"])
    if "action" not in table:
        table["action"] = "zero"
    for row in table[table["action"] == "start"].itertuples():
        if row.symbol in px.columns:
            px.loc[px.index < row.date, row.symbol] = float("nan")
    for row in table[table["action"] == "blank"].itertuples():
        if row.symbol in px.columns and row.date in px.index:
            px.loc[row.date, row.symbol] = float("nan")
    started = px.notna().cummax()  # forward-fill only inside a stock's own history
    px = px.ffill().where(started)
    r = px.pct_change(fill_method=None)
    for row in table[table["action"] == "zero"].itertuples():
        if row.symbol in r.columns and row.date in r.index:
            r.loc[row.date, row.symbol] = 0.0
    return r
