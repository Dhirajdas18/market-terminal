"""Overview strip: last close, day / week / year-to-date change and 52-week position per series.

Each series is read up to the session date and uses its own last valid bar, so USD/INR and the
S&P 500 (other calendars) carry their own date instead of borrowing the NSE one.
"""

import pandas as pd

from mt import snapshot

SERIES = ["NIFTY", "NIFTYBANK", "INDIAVIX", "USDINR", "GOLDBEES", "SP500"]
WINDOW = pd.Timedelta(days=365)


def _valid(close: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """Valid closes up to and including `as_of` (later rows are dropped)."""
    return close.loc[:as_of].dropna()


def period_returns(close: pd.Series, as_of) -> dict:
    """Day, week and year-to-date change of the last valid close on or before `as_of`.

    day: vs the previous valid close. week: vs the last close of the previous ISO week.
    ytd: vs the last close of the previous calendar year. None where there is no such close."""
    s = _valid(close, pd.Timestamp(as_of))
    out: dict[str, float | None] = {"day": None, "week": None, "ytd": None}
    if s.empty:
        return out
    last_day, last = s.index[-1], float(s.iloc[-1])
    if len(s) > 1:
        out["day"] = last / float(s.iloc[-2]) - 1
    iso = s.index.isocalendar()
    this_week = (iso["year"].iloc[-1], iso["week"].iloc[-1])
    before_week = s[(iso["year"] * 100 + iso["week"]) < this_week[0] * 100 + this_week[1]]
    if not before_week.empty:
        out["week"] = last / float(before_week.iloc[-1]) - 1
    before_year = s[s.index.year < last_day.year]
    if not before_year.empty:
        out["ytd"] = last / float(before_year.iloc[-1]) - 1
    return out


def range_52w(close: pd.Series, high: pd.Series, low: pd.Series, as_of) -> dict:
    """Lowest low and highest high over the 365 calendar days ending `as_of`, and where the last
    close sits between them (0 at the low, 1 at the high; None when the range is flat)."""
    as_of = pd.Timestamp(as_of)
    s = _valid(close, as_of)
    start = as_of - WINDOW
    hi = high.loc[start:as_of].dropna()
    lo = low.loc[start:as_of].dropna()
    if s.empty or hi.empty or lo.empty:
        return {"low": None, "high": None, "pos": None}
    top, bottom, last = float(hi.max()), float(lo.min()), float(s.iloc[-1])
    pos = (last - bottom) / (top - bottom) if top > bottom else None
    return {"low": bottom, "high": top, "pos": pos}


def item(name: str, table: pd.DataFrame, as_of) -> dict:
    """The overview row for one series (a column of `table`'s close/high/low fields)."""
    as_of = pd.Timestamp(as_of)
    close = table["close"][name]
    high = table["high"][name] if "high" in table.columns.get_level_values(0) else close
    low = table["low"][name] if "low" in table.columns.get_level_values(0) else close
    valid = _valid(close, as_of)
    rng = range_52w(close, high, low, as_of)
    return {
        "name": name,
        "date": f"{valid.index[-1]:%Y-%m-%d}" if len(valid) else None,
        "close": float(valid.iloc[-1]) if len(valid) else None,
        **period_returns(close, as_of),
        "low52": rng["low"],
        "high52": rng["high"],
        "pos52": rng["pos"],
    }


def section(table: pd.DataFrame) -> list[dict]:
    """Snapshot section: one row per series present in the (already trimmed) table."""
    present = set(table["close"].columns)
    return [item(n, table, table.index.max()) for n in SERIES if n in present]


snapshot.SECTIONS.append(("overview", section))
