"""One stock's risk and return numbers, and its candles, for the Watchlist and the stock view.

Returns are `data.daily_returns` of adjusted closes (known Yahoo errors repaired) on the NSE
sessions of `session.sessions`. A measure that needs a full window (250 returns for beta, vol and
drawdown, at least 250 of the last 500 for VaR) is None until the stock has it: a recent listing
shows "not enough history" instead of a number from a few days.
"""

import numpy as np
import pandas as pd

from mt import snapshot
from mt.candles import moving_average
from mt.data import INDEX, SECTORS, SYMBOLS, daily_returns
from mt.session import sessions

YEAR = 250  # sessions in a year of trading, for windows (vol is annualised by calendar time)
MONTH = 21
VAR_DAYS = 500
VAR_MIN = 250
BLUME = 0.67  # Blume's adjustment: 0.67 x measured beta + 0.33 x 1
AMOUNT = 100_000  # rupees: the VaR example is on one lakh
CANDLE_KEYS = ["dates", "open", "high", "low", "close", "ma20", "ma50"]


def _last(r: pd.Series, n: int) -> pd.Series:
    return r.dropna().iloc[-n:]


def blume_beta(r: pd.Series, r_index: pd.Series, days: int = YEAR) -> float | None:
    """0.67 x the OLS slope of `r` on `r_index` + 0.33, over the last `days` returns both have;
    None with fewer, or when the index did not move."""
    both = pd.concat([r, r_index], axis=1, join="inner").dropna().iloc[-days:]
    if len(both) < days:
        return None
    x, y = both.iloc[:, 1].to_numpy(), both.iloc[:, 0].to_numpy()
    var = float(np.var(x, ddof=1))
    if var <= 0:
        return None
    slope = float(np.cov(x, y, ddof=1)[0, 1]) / var
    return BLUME * slope + (1 - BLUME)


def annual_vol(r: pd.Series, days: int = YEAR) -> float | None:
    """Standard deviation of the last `days` returns x the square root of the returns per calendar
    year over their span (a return every calendar day gives 365.25, NSE sessions about 250); None
    with fewer returns."""
    last = _last(r, days)
    if len(last) < days:
        return None
    years = (last.index[-1] - last.index[0]).days / 365.25
    if years <= 0:
        return None
    return float(last.std(ddof=1) * np.sqrt((len(last) - 1) / years))


def max_drawdown(close: pd.Series, days: int = YEAR) -> float | None:
    """The worst fall from a peak inside the last `days` closes, as a negative fraction (0 if the
    price never fell from a high); None with fewer closes."""
    last = close.dropna().iloc[-days:]
    if len(last) < days:
        return None
    return float((last / last.cummax() - 1).min())


def var95(r: pd.Series, amount: float = AMOUNT, days: int = VAR_DAYS) -> float | None:
    """Historical one-day 95% value at risk: the 5th percentile of the last `days` returns as a
    rupee loss on `amount` (never negative); None with fewer than 250 returns."""
    last = _last(r, days)
    if len(last) < VAR_MIN:
        return None
    return max(0.0, float(-np.percentile(last.to_numpy(), 5)) * amount)


def rolling_var(r, days: int = VAR_DAYS):
    """Each day's 95% VaR as a loss fraction, from the `days` rows before it only (the day itself
    is never in its own window); NaN until 250 returns exist. Works on a Series or a frame."""
    return -r.shift(1).rolling(days, min_periods=VAR_MIN).quantile(0.05)


def breaches(r, days: int = VAR_DAYS):
    """1.0 on a day whose loss was bigger than that day's VaR, 0.0 when it was not, NaN where
    there is no VaR or no return (not scored)."""
    var = rolling_var(r, days)
    scored = var.notna() & r.notna()
    return (r < -var).astype(float).where(scored)


def kupiec(breached: int, n: int, p: float = 0.05) -> tuple[float, float]:
    """Kupiec's proportion-of-failures test: (likelihood ratio, p-value) for `breached` breaches in
    `n` days against a target rate `p`. Treats the days as independent."""
    from scipy.stats import chi2

    def loglik(q: float) -> float:
        out = 0.0
        if n - breached:
            out += (n - breached) * np.log(1 - q)
        if breached:
            out += breached * np.log(q)
        return out

    lr = -2 * (loglik(p) - loglik(breached / n))
    lr = max(lr, 0.0)
    return float(lr), float(chi2.sf(lr, 1))


def _prepare(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series] | None:
    """(closes on NSE sessions, returns of each stock, NIFTY's returns) or None without prices."""
    fields = set(table.columns.get_level_values(0))
    if not {"close", "adj_close"} <= fields or INDEX not in table["close"]:
        return None
    close = sessions(table["close"])
    names = [s for s in SYMBOLS if s in close and s in table["adj_close"]]
    adj = table["adj_close"].loc[close.index]
    r = daily_returns(adj[names]).where(close[names].notna())
    r_index = adj[INDEX].pct_change(fill_method=None)
    return close, r, r_index


def _num(value: float | None, digits: int = 4) -> float | None:
    return None if value is None or not np.isfinite(value) else round(float(value), digits)


def _row(symbol: str, close: pd.DataFrame, r: pd.DataFrame, r_index: pd.Series) -> dict:
    px, ret = close[symbol].dropna(), r[symbol]
    today = close.index[-1]
    month, year = _last(ret, MONTH), _last(ret, YEAR)
    return {
        "close": None if px.empty else _num(px.iloc[-1], 2),
        "day": _num(ret.get(today)),
        "m1": _num((1 + month).prod() - 1) if len(month) == MONTH else None,
        "y1": _num((1 + year).prod() - 1) if len(year) == YEAR else None,
        "vol": _num(annual_vol(ret)),
        "beta": _num(blume_beta(ret, r_index), 2),
        "mdd": _num(max_drawdown(px)),
        "var95": _num(var95(ret), 0),
        "sector": SECTORS.get(symbol),
    }


def row(symbol: str, table: pd.DataFrame) -> dict:
    """`{close, day, m1, y1, vol, beta, mdd, var95, sector}` for one stock as of the table's last
    session (m1 = 21 sessions, y1 = 250); each is None when the stock lacks the history. Plain
    Python values, so it serialises with allow_nan=False."""
    prepared = _prepare(table)
    if prepared is None or symbol not in prepared[1]:
        return {}
    return _row(symbol, *prepared)


def candles(table: pd.DataFrame, symbol: str, close: pd.DataFrame, n: int = YEAR) -> dict:
    """The stock's last `n` sessions of open, high, low, close (to 2 decimals, the exchange's
    precision) and the 20- and 50-day averages, computed on the whole history and then cut."""
    ohlc = table[["open", "high", "low", "close"]].xs(symbol, axis=1, level=1)
    ohlc = ohlc.loc[ohlc.index.intersection(close.index)].dropna()
    ma = {k: moving_average(ohlc["close"], w) for k, w in (("ma20", 20), ("ma50", 50))}
    cut = ohlc.index[-n:]
    return {
        "dates": [f"{d:%Y-%m-%d}" for d in cut],
        **{f: ohlc.loc[cut, f].to_numpy().round(2) for f in ["open", "high", "low", "close"]},
        **{k: v.loc[cut].to_numpy().round(2) for k, v in ma.items()},
    }


def stocks_section(table: pd.DataFrame) -> dict:
    """`{symbol: {...row, candles}}` for each of the 50 with a close in the (trimmed) table."""
    prepared = _prepare(table)
    fields = set(table.columns.get_level_values(0))
    if prepared is None or not {"open", "high", "low"} <= fields:
        return {}
    close, r, r_index = prepared
    return {
        s: {**_row(s, close, r, r_index), "candles": candles(table, s, close)}
        for s in r.columns
        if close[s].notna().any()
    }


snapshot.SECTIONS.append(("stocks", stocks_section))
