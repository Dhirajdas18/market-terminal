"""Sector moves and who moved NIFTY.

NIFTY is a price index, so everything here uses price returns from `close` (split-adjusted, not
dividend-adjusted), with the unadjusted corporate actions in docs/data/yahoo_fixes.csv set to a
zero return. NSE does not publish daily weights for free, so each stock's weight is estimated from
the 60 sessions before the day: the non-negative weights that best reproduce NIFTY's daily returns
from the stocks' (scipy's nnls), scaled to sum to 1. The day's contribution is weight x the stock's
return x NIFTY's previous close, in index points. The day being explained is never in the fit.
"""

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from mt import snapshot
from mt.data import INDEX, SECTORS, SYMBOLS, daily_returns
from mt.session import sessions

WINDOW = 60  # sessions of returns used to estimate the weights
TOP = 10


def sector_returns(day_ret: pd.Series, sectors: dict[str, str]) -> pd.DataFrame:
    """Equal-weight mean day return per sector (`ret`) and the stocks it used (`n`), best sector
    first. A stock with no return is not counted; a sector with none is left out."""
    frame = pd.DataFrame({"ret": day_ret, "sector": pd.Series(sectors)}).dropna(subset=["sector"])
    grouped = frame.dropna(subset=["ret"]).groupby("sector")["ret"]
    out = pd.DataFrame({"ret": grouped.mean(), "n": grouped.count()})
    return out.sort_values("ret", ascending=False)


def nnls_weights(R: pd.DataFrame, r_index: pd.Series, window: int = WINDOW) -> pd.Series:
    """Estimated weights from the `window` sessions before the last row of `R` (the last row is
    the day being explained and is not used). A stock without `window` valid returns in that span
    gets NaN; so does everything if there are fewer than `window` rows before the last. Days with
    no index return are skipped in the fit. Weights are non-negative and sum to 1."""
    nan = pd.Series(np.nan, index=R.columns, dtype=float)
    span = R.iloc[:-1].iloc[-window:]
    if len(span) < window:
        return nan
    have = span.notna().sum() >= window
    target = r_index.reindex(span.index)
    rows = target.notna().to_numpy()
    if not have.any() or not rows.any():
        return nan
    coef, _ = nnls(span.loc[rows, have].to_numpy(), target[rows].to_numpy())
    if coef.sum() <= 0:
        return nan
    out = nan.copy()
    out[have] = coef / coef.sum()
    return out


def contributions(weights: pd.Series, day_ret: pd.Series, prev_close_nifty: float) -> pd.DataFrame:
    """Per stock: `weight`, `points` (weight x return x NIFTY's previous close; NaN without a
    weight or a return) and `not_estimated` (no weight yet). Sorted by |points|, NaN last."""
    out = pd.DataFrame({"weight": weights, "ret": day_ret.reindex(weights.index)})
    out["points"] = out["weight"] * out["ret"] * prev_close_nifty
    out["not_estimated"] = out["weight"].isna()
    out["_abs"] = out["points"].abs()
    out = out.sort_values("_abs", ascending=False, na_position="last", kind="stable")
    return out[["points", "weight", "not_estimated"]]


def daily_check(contrib: pd.DataFrame, nifty_close: float, prev_close_nifty: float) -> dict:
    """The estimates' total against what NIFTY actually moved, both in index points."""
    return {
        "sum_points": float(contrib["points"].sum()),
        "actual_points": float(nifty_close - prev_close_nifty),
    }


def rolling_tracking(
    close: pd.DataFrame, start: str = "2010-01-01", window: int = WINDOW
) -> pd.DataFrame:
    """How well the estimates add up, day by day and out of sample. `close` holds the stocks and
    NIFTY. Each day's weights come only from the `window` sessions before it. One row per session
    from `start` with an index return (days after a missing NIFTY bar have none): `est_ret` and
    `actual_ret` (sum of weight x return, NIFTY's own return), the same in index points
    (`est_pts`, `actual_pts`), `eq_pts` (the equal-weight average stock return x NIFTY's previous
    close, the plain baseline) and `n_est` (stocks with a weight)."""
    px = sessions(close)
    stocks = px.drop(columns=INDEX)
    r = daily_returns(stocks)
    r_index = px[INDEX].pct_change(fill_method=None)
    prev = px[INDEX].shift(1)
    first = int(px.index.searchsorted(pd.Timestamp(start)))
    rows = []
    for t in range(max(first, window + 1), len(px)):
        if np.isnan(r_index.iloc[t]):
            continue
        w = nnls_weights(r.iloc[t - window : t + 1], r_index.iloc[t - window : t + 1], window)
        today = r.iloc[t]
        est = float((w * today).sum())  # NaN weights and NaN returns add nothing
        eq = float(today.mean()) if today.notna().any() else np.nan
        rows.append(
            (
                px.index[t],
                est,
                r_index.iloc[t],
                est * prev.iloc[t],
                r_index.iloc[t] * prev.iloc[t],
                eq * prev.iloc[t],
                int(w.notna().sum()),
            )
        )
    cols = ["est_ret", "actual_ret", "est_pts", "actual_pts", "eq_pts", "n_est"]
    return pd.DataFrame(rows, columns=["date", *cols]).set_index("date")


def _stock_names(table: pd.DataFrame) -> list[str]:
    return [s for s in SYMBOLS if s in table["close"]]


def _price_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Price returns per session (non-trading rows dropped first)."""
    return daily_returns(sessions(close))


def sectors_section(table: pd.DataFrame) -> list[dict]:
    """Snapshot `sectors`: equal-weight return and stock count per sector, on the last day."""
    names = _stock_names(table)
    if not names:
        return []
    close = table["close"][names]
    day = table.index.max()
    ret = _price_returns(close).reindex(close.index).loc[day].where(close.loc[day].notna())
    out = sector_returns(ret, {s: SECTORS[s] for s in names})
    return [{"name": n, "ret": r.ret, "n": int(r.n)} for n, r in out.iterrows()]


def contributions_section(table: pd.DataFrame) -> dict:
    """Snapshot `contributions` for the last day; {} when NIFTY has no close for it and the
    session before. `not_estimated` lists stocks with a bar today but no weight yet."""
    names = _stock_names(table)
    if not names or INDEX not in table["close"]:
        return {}
    close = sessions(table["close"][[*names, INDEX]])
    day = close.index[-1]
    if len(close) < 2 or close[INDEX].iloc[-2:].isna().any():
        return {}
    r = daily_returns(close[names])
    r_index = close[INDEX].pct_change(fill_method=None)
    weights = nnls_weights(r, r_index)
    today = r.loc[day].where(close.loc[day, names].notna())
    prev = float(close[INDEX].iloc[-2])
    table_ = contributions(weights.reindex(names), today, prev)
    table_ = table_[today.reindex(table_.index).notna()]
    check = daily_check(table_, float(close[INDEX].iloc[-1]), prev)
    estimated = table_[~table_["not_estimated"]]
    rows = [
        {"symbol": s, "points": row.points, "weight": row.weight}
        for s, row in estimated.iterrows()
    ]
    return {
        "top": rows[:TOP],
        "all": rows,  # every stock with a weight, for the sector view
        "not_estimated": sorted(table_.index[table_["not_estimated"]]),
        **check,
    }


snapshot.SECTIONS.append(("sectors", sectors_section))
snapshot.SECTIONS.append(("contributions", contributions_section))
