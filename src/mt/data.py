"""End-of-day bars from Yahoo Finance, kept in a local parquet cache.

The universe is today's NIFTY 50 (docs/data/nifty50.csv, a snapshot of NSE's list) plus a few
reference series. NSE series share one calendar. USD/INR and the S&P 500 trade on other
calendars, so they have bars on NSE holidays and none on some NSE days: never use them to decide
the NSE session, and drop each column's own NaN rows before computing its returns.

The table's columns are a (field, symbol) MultiIndex. Fields: open, high, low, close, adj_close,
volume. Yahoo's open/high/low/close are split-adjusted, not dividend-adjusted; returns use
adj_close.
"""

import logging
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
CONSTITUENTS = ROOT / "docs" / "data" / "nifty50.csv"
FIXES = ROOT / "docs" / "data" / "yahoo_fixes.csv"
DATA_PATH = ROOT / "data" / "prices.parquet"
YF_CACHE = Path.home() / ".config" / "market-terminal" / "yfinance"
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
MAX_UNQUOTED = 5  # constituents an update may lack (renamed, merged, long halt) and still be kept


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

    # yfinance's cookie and timezone databases go to a private dir, not ~/Library/Caches (0o644)
    YF_CACHE.mkdir(mode=0o700, parents=True, exist_ok=True)
    YF_CACHE.chmod(0o700)
    yf.set_tz_cache_location(str(YF_CACHE))
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


def tolerable(missing: list[str]) -> bool:
    """An update may go ahead without these symbols: at most MAX_UNQUOTED constituent stocks,
    never an index or reference series (NIFTY, NIFTYBANK, INDIAVIX, GOLDBEES, USD/INR, S&P 500)."""
    return 0 < len(missing) <= MAX_UNQUOTED and set(missing) <= set(SYMBOLS)


def download(
    fetch: Callable[[], pd.DataFrame],
    find_missing: Callable[[pd.DataFrame], list[str]],
    attempts: int = 4,
    tolerate: Callable[[list[str]], bool] | None = None,
) -> pd.DataFrame:
    """Call `fetch` until `find_missing` reports nothing absent; raise rather than keep a gap.

    Yahoo occasionally drops a ticker or errors, so each download gets a few tries. With
    `tolerate`, a result is also accepted when the same tolerable symbols are absent on two tries
    in a row (no longer quoted, not a chance drop)."""
    missing = ["everything"]
    for attempt in range(attempts):
        if attempt:
            time.sleep(5 * attempt)
        try:
            df = fetch()
        except Exception as exc:  # network or Yahoo error: log it and retry
            log.warning("download attempt %d failed: %s: %s", attempt + 1, type(exc).__name__, exc)
            continue
        previous, missing = missing, find_missing(df)
        if not missing:
            return df
        if tolerate is not None and missing == previous and tolerate(missing):
            log.warning("Yahoo has no data for %s; keeping their cached bars", ", ".join(missing))
            return df
    raise DownloadFailed(missing)


def load_cache(path: Path = DATA_PATH, since: pd.Timestamp | None = None) -> pd.DataFrame | None:
    """The cached table (rows from `since` on, if given), or None when there is no cache yet."""
    path = Path(path)
    if not path.exists():
        return None
    filters = [("date", ">=", pd.Timestamp(since))] if since is not None else None
    return pd.read_parquet(path, filters=filters).sort_index()


def remove_stale_temp_files(directory: Path | None = None) -> None:
    """Delete `tmp*.tmp` files a killed cache write left in the data directory."""
    directory = Path(directory) if directory is not None else DATA_PATH.parent
    for leftover in directory.glob("tmp*.tmp"):
        if leftover.is_file() and not leftover.is_symlink():
            leftover.unlink(missing_ok=True)


def _last_date(path: Path) -> pd.Timestamp | None:
    """The newest cached date, read from the date column alone (None: no cache, or unreadable)."""
    if not path.exists():
        return None
    try:
        dates = pq.read_table(path, columns=["date"])["date"]
        return pd.Timestamp(pc.max(dates).as_py()) if len(dates) else None
    except Exception as exc:  # corrupt cache file: download everything again and overwrite it
        log.warning("cache unreadable: %s: %s", type(exc).__name__, exc)
        return None


def _write_atomic(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        pq.write_table(table, tmp_path)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _fresh_table(
    fetch: Callable[..., pd.DataFrame], start: str, cache: Path | None = None
) -> tuple[pa.Table, list[str]]:
    """Download from `start`; return it as an Arrow table (the pandas frame is dropped) and the
    symbols Yahoo had no data for. Those are allowed only with a `cache` to update (see
    `tolerable`): their columns keep the cached bars on the overlap days and are empty after."""
    new = download(lambda: fetch(start), missing_symbols, tolerate=tolerable if cache else None)
    unquoted = sorted(missing_symbols(new))
    new = new.dropna(how="all").sort_index()
    if unquoted:
        fields = new.columns.get_level_values(0).unique()
        new = new.reindex(columns=new.columns.union(pd.MultiIndex.from_product([fields, unquoted])))
        old = pd.read_parquet(cache, filters=[("date", ">=", new.index.min())])
        keep = [c for c in new.columns if c[1] in unquoted and c in old.columns]
        new[keep] = old[keep].reindex(new.index)
    new = new.sort_index(axis=1)
    new.columns.names = ["field", "symbol"]
    new.index.name = "date"
    return pa.Table.from_pandas(new), unquoted


def _first_date(table: pa.Table):
    return pc.min(table["date"]).as_py()


def update_cache(
    path: Path = DATA_PATH,
    fetch: Callable[..., pd.DataFrame] = fetch,
    overlap_days: int = 7,
    since: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Bring the cache up to date and return the table from `since` on (everything if None).

    First run downloads from 2007. Later runs download from the last cached date minus
    `overlap_days`, so revised bars replace the cached ones. The merge happens in Arrow (only the
    older rows are read, never a second full pandas copy), so the app's update path holds just the
    new rows and the returned tail. Raises DownloadFailed (cache untouched) if Yahoo leaves any
    ticker out, except that an update of an existing cache goes ahead without up to MAX_UNQUOTED
    constituent stocks (`tolerable`); the returned table names them in
    `attrs["no_yahoo_data"]`."""
    path = Path(path)
    last = _last_date(path)
    start = START if last is None else (last - pd.Timedelta(days=overlap_days)).strftime("%Y-%m-%d")
    fresh, unquoted = _fresh_table(fetch, start, cache=path if last is not None else None)
    if last is not None and pq.read_schema(path).names != fresh.schema.names:
        # the ticker set changed (a NIFTY 50 rebalance): the old rows no longer fit, start over
        log.warning("cached columns differ from the current tickers: downloading everything again")
        last, (fresh, unquoted) = None, _fresh_table(fetch, START)
    if last is None:
        merged = fresh
    else:
        old = pq.read_table(path, filters=[("date", "<", _first_date(fresh))])
        merged = pa.concat_tables([old, fresh.cast(old.schema)])
        del old
    del fresh
    _write_atomic(merged, path)
    del merged
    pa.default_memory_pool().release_unused()
    table = load_cache(path, since=since)
    table.attrs["no_yahoo_data"] = unquoted
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
