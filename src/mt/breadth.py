"""Market breadth: how many of the 50 stocks take part in the move, not only what NIFTY did.

Every count says how many stocks it could be computed for. A stock with too little history for a
measure (a recent listing: fewer than 50 closes for the 50-day average, fewer than 250 for the
250-day high and low) is left out of that measure and of its denominator, as is a stock with no
bar on the day. A stock with a missing close inside a window also drops out until the window is
clear. Rows that are not trading days (see session.sessions) are dropped before any window is taken.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from mt import snapshot
from mt.data import FIXES, SYMBOLS, daily_returns
from mt.session import sessions

MA_DAYS = 50
HIGH_DAYS = 250  # sessions in the high/low window: about one 52-week year
SPARK_SESSIONS = 250


def fixed_close(close: pd.DataFrame, fixes: Path = FIXES) -> pd.DataFrame:
    """Closes with Yahoo's known bad history removed: `start` drops prices before the date, `blank`
    drops that day's print. (`zero` fixes concern returns across an unadjusted corporate action.)"""
    px = close.copy()
    table = pd.read_csv(fixes, parse_dates=["date"])
    if "action" not in table:
        return px
    for row in table[table["action"] == "start"].itertuples():
        if row.symbol in px.columns:
            px.loc[px.index < row.date, row.symbol] = np.nan
    for row in table[table["action"] == "blank"].itertuples():
        if row.symbol in px.columns and row.date in px.index:
            px.loc[row.date, row.symbol] = np.nan
    return px


def advance_decline(day_ret: pd.Series) -> dict[str, int]:
    """Stocks up, down and unchanged on the day; a stock with no return is not counted."""
    ret = day_ret.dropna()
    return {
        "up": int((ret > 0).sum()),
        "down": int((ret < 0).sum()),
        "flat": int((ret == 0).sum()),
    }


def _above(close: pd.DataFrame, n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(close > its trailing n-close mean, whether that comparison exists), per day and stock."""
    ma = close.rolling(n, min_periods=n).mean()
    valid = ma.notna() & close.notna()
    return (close > ma) & valid, valid


def above_ma(close: pd.DataFrame, n: int = MA_DAYS) -> dict[str, int]:
    """Stocks whose last close is above their n-day average of closes (today included), out of
    the stocks that have n closes and a bar today."""
    above, valid = _above(sessions(close), n)
    return {"count": int(above.iloc[-1].sum()), "of": int(valid.iloc[-1].sum())}


def new_highs_lows(close: pd.DataFrame, n: int = HIGH_DAYS) -> dict[str, int]:
    """Stocks whose last close is at or above the highest (at or below the lowest) of the n-1
    closes before it, out of the stocks with n closes and a bar today."""
    px = sessions(close)
    prev = px.shift(1).rolling(n - 1, min_periods=n - 1)
    today = px.iloc[-1]
    valid = prev.max().iloc[-1].notna() & today.notna()
    return {
        "highs": int((today >= prev.max().iloc[-1])[valid].sum()),
        "lows": int((today <= prev.min().iloc[-1])[valid].sum()),
        "of": int(valid.sum()),
    }


def history(close: pd.DataFrame, n: int = MA_DAYS) -> pd.DataFrame:
    """Per session: `above` and `of` (as in above_ma) and `pct_above50` = above / of (NaN while
    no stock has n closes). Each row uses only closes up to that day."""
    above, valid = _above(sessions(close), n)
    out = pd.DataFrame({"above": above.sum(axis=1), "of": valid.sum(axis=1)})
    out["pct_above50"] = (out["above"] / out["of"].where(out["of"] > 0)).astype(float)
    return out


def section(table: pd.DataFrame, symbols: list[str] | None = None) -> dict:
    """The snapshot's `breadth` entry for the last day of the (trimmed) table."""
    fields = set(table.columns.get_level_values(0))
    names = [s for s in (symbols if symbols is not None else SYMBOLS) if s in table["close"]]
    if not names or not {"close", "adj_close"} <= fields:
        return {}
    close = fixed_close(table["close"][names])
    day = table.index.max()
    ret = daily_returns(table["adj_close"][names]).loc[day].where(close.loc[day].notna())
    extremes = new_highs_lows(close)
    pct = history(close)["pct_above50"].iloc[-SPARK_SESSIONS:]
    return {
        **advance_decline(ret),
        "above50": above_ma(close),
        "highs": extremes["highs"],
        "lows": extremes["lows"],
        "of52": extremes["of"],
        "spark": {"dates": [f"{d:%Y-%m-%d}" for d in pct.index], "pct": pct.to_numpy()},
    }


def newey_west(y: np.ndarray, X: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """OLS of y on X (rows in time order) with Newey-West (Bartlett) standard errors.
    Returns (coefficients, t-statistics). `lags` = 19 for 20-day returns that overlap by 19 days."""
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ y
    scores = X * (y - X @ coef)[:, None]
    meat = scores.T @ scores
    for lag in range(1, lags + 1):
        cross = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / (lags + 1)) * (cross + cross.T)
    cov = xtx_inv @ meat @ xtx_inv
    return coef, coef / np.sqrt(np.diag(cov))


def _state_stats(y: np.ndarray, high: np.ndarray, lags: int) -> dict:
    """Mean next-return and hit rate in each state; t of each mean against 0 from one regression
    on the whole sample (the other state's rows contribute nothing), so overlap is handled."""
    dummies = np.column_stack([high, ~high]).astype(float)
    coef, t = newey_west(y, dummies, lags)
    out = {}
    for i, name in enumerate(["high", "low"]):
        mask = high if name == "high" else ~high
        out[name] = {
            "n": int(mask.sum()),
            "hit": float((y[mask] > 0).mean()),
            "mean": float(coef[i]),
            "t": float(t[i]),
        }
    d_coef, d_t = newey_west(y, np.column_stack([np.ones(len(y)), high.astype(float)]), lags)
    return {**out, "diff": float(d_coef[1]), "diff_t": float(d_t[1])}


def oos_check(
    pct: pd.Series,
    nifty: pd.Series,
    split: str = "2017-01-01",
    train_start: str = "2008-01-01",
    horizon: int = 20,
    lags: int = 19,
) -> dict:
    """Does % of stocks above their 50-day average say anything about NIFTY's next `horizon`
    sessions, beyond NIFTY's own position against its 50-day average?

    Each signal's threshold is its median over the sessions from `train_start` to before `split`;
    sessions from `split` on are scored, so no fitted number sees the days it is tested on. A day is
    `high` when the signal is above its threshold. The baseline signal is NIFTY's close / its
    50-day average − 1 (needs no stock data); `above_zero` is the plain above-or-below version.
    `joint` regresses the next return on both high flags together."""
    close = nifty.dropna()
    frame = pd.DataFrame(
        {
            "breadth": pct.reindex(close.index),
            "dist": close / close.rolling(MA_DAYS, min_periods=MA_DAYS).mean() - 1,
            "next": close.shift(-horizon) / close - 1,
        }
    )
    cut = pd.Timestamp(split)
    train = frame[(frame.index >= pd.Timestamp(train_start)) & (frame.index < cut)]
    test = frame[frame.index >= cut].dropna()
    y = test["next"].to_numpy()
    out: dict = {
        "n": len(test),
        "first_day": f"{test.index[0]:%Y-%m-%d}",
        "last_day": f"{test.index[-1]:%Y-%m-%d}",
        "train_days": int(train["breadth"].notna().sum()),
        "train_first": f"{train['breadth'].dropna().index[0]:%Y-%m-%d}",
        "all_mean": float(y.mean()),
        "all_hit": float((y > 0).mean()),
    }
    thresholds = {k: float(train[k].median()) for k in ("breadth", "dist")}
    flags = {k: (test[k] > thr).to_numpy() for k, thr in thresholds.items()}
    for key, flag in (("breadth", "breadth"), ("nifty", "dist")):
        out[key] = {"threshold": thresholds[flag], **_state_stats(y, flags[flag], lags)}
    out["above_zero"] = {"threshold": 0.0, **_state_stats(y, (test["dist"] > 0).to_numpy(), lags)}
    X = np.column_stack([np.ones(len(y)), flags["breadth"], flags["dist"]]).astype(float)
    coef, t = newey_west(y, X, lags)
    out["joint"] = {
        "breadth": float(coef[1]),
        "breadth_t": float(t[1]),
        "nifty": float(coef[2]),
        "nifty_t": float(t[2]),
    }
    both = flags["breadth"] & flags["dist"]
    out["agree"] = float((flags["breadth"] == flags["dist"]).mean())
    out["both_high"] = float(both.mean())
    return out


snapshot.SECTIONS.append(("breadth", section))
