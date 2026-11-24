"""NIFTY candles with moving averages, traded value, the day's movers and unusual volume.

Volume ruling: Yahoo's ^NSEI volume has no documented meaning, so the bars under the NIFTY chart
are the traded value of the 50 stocks (close x volume, in rupees crore) instead.

Unusual volume divides today's volume by the mean of the previous 20 days, today left out. A
volume of 0 is treated as no print. Movers use daily_returns, which repairs known Yahoo errors.
"""

import numpy as np
import pandas as pd

from mt import snapshot
from mt.data import INDEX, SYMBOLS, daily_returns

CRORE = 1e7
SESSIONS = 250  # NIFTY sessions kept in the snapshot
TOP = 5
INDEX_KEYS = ["dates", "open", "high", "low", "close", "ma20", "ma50", "value_cr"]


def moving_average(close: pd.Series, n: int) -> pd.Series:
    """Trailing mean of the last `n` values; NaN until a full window exists."""
    return close.rolling(n, min_periods=n).mean()


def gap(open_: pd.Series, close: pd.Series) -> pd.Series:
    """Open / previous close − 1, where previous close is the last valid close before the day."""
    return open_ / close.ffill().shift(1) - 1


def unusual_volume(volume: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Today's volume / mean of the previous `n` days (today excluded); NaN with fewer than `n`
    prior sessions with a volume print."""
    vol = volume.where(volume > 0)
    traded = vol.dropna(how="all")  # rows where nothing traded (holidays) are not sessions
    ratio = traded / traded.shift(1).rolling(n, min_periods=n).mean()
    return ratio.replace([np.inf, -np.inf], np.nan).reindex(volume.index)


def traded_value(close: pd.DataFrame, volume: pd.DataFrame) -> pd.Series:
    """Sum over the stocks of close x volume, in rupees crore; a stock missing either is left out
    of that day's sum, and a day with no stock at all is NaN."""
    value = (close * volume.where(volume > 0)).sum(axis=1, min_count=1)
    return value / CRORE


def movers(day_ret: pd.Series, k: int = TOP) -> dict[str, list[dict]]:
    """The `k` biggest gainers and losers; a stock with no return that day is skipped."""
    ret = day_ret.dropna()
    return {
        "gainers": [{"symbol": s, "ret": float(r)} for s, r in ret.nlargest(k).items()],
        "losers": [{"symbol": s, "ret": float(r)} for s, r in ret.nsmallest(k).items()],
    }


def index_series(table: pd.DataFrame, symbols: list[str] | None = None, n: int = SESSIONS) -> dict:
    """The last `n` sessions with a NIFTY bar: OHLC, 20- and 50-day averages (computed on the whole
    table, then cut, so the first bar already has one) and the stocks' traded value."""
    fields = set(table.columns.get_level_values(0))
    if not {"open", "high", "low", "close", "volume"} <= fields or INDEX not in table["close"]:
        return {k: [] for k in INDEX_KEYS}
    names = [s for s in (symbols if symbols is not None else SYMBOLS) if s in table["close"]]
    ohlc = table[["open", "high", "low", "close"]].xs(INDEX, axis=1, level=1).dropna()
    ma20 = moving_average(ohlc["close"], 20)
    ma50 = moving_average(ohlc["close"], 50)
    value = traded_value(table["close"][names], table["volume"][names]).reindex(ohlc.index)
    cut = ohlc.index[-n:]
    return {
        "dates": [f"{d:%Y-%m-%d}" for d in cut],
        **{f: ohlc.loc[cut, f].to_numpy() for f in ["open", "high", "low", "close"]},
        "ma20": ma20.loc[cut].to_numpy(),
        "ma50": ma50.loc[cut].to_numpy(),
        "value_cr": value.loc[cut].to_numpy(),
    }


def movers_section(table: pd.DataFrame, symbols: list[str] | None = None) -> dict:
    """Gainers, losers and the highest volume ratios on the last day of the (trimmed) table, for
    stocks that have a bar that day."""
    fields = set(table.columns.get_level_values(0))
    names = [s for s in (symbols if symbols is not None else SYMBOLS) if s in table["close"]]
    if not names or not {"adj_close", "volume"} <= fields:
        return {"gainers": [], "losers": [], "unusual": []}
    day = table.index.max()
    has_bar = table["close"][names].loc[day].notna()
    ret = daily_returns(table["adj_close"][names]).loc[day].where(has_bar)
    ratio = unusual_volume(table["volume"][names]).loc[day].where(has_bar).dropna()
    top = ratio.nlargest(TOP)
    return {
        **movers(ret),
        "unusual": [
            {
                "symbol": s,
                "ratio": float(r),
                "ret": None if pd.isna(ret[s]) else float(ret[s]),
            }
            for s, r in top.items()
        ],
    }


snapshot.SECTIONS.append(("index", index_series))
snapshot.SECTIONS.append(("movers", movers_section))
