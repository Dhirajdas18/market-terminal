"""Which trading day the screens show.

A day counts only when every NSE series has a valid close on it. Yahoo can return an all-NaN row
for today on an NSE holiday, publish some stocks' bars before others, or hand out a live bar during
market hours; each of those falls back to the last complete day.
"""

import pandas as pd

from mt.data import OFF_CALENDAR

IST = "Asia/Kolkata"
CLOSE_HOUR = 16  # bars before 16:00 IST are unfinished (NSE closes 15:30, plus settling time)


def sessions(close: pd.DataFrame) -> pd.DataFrame:
    """The rows of `close` that are NSE trading days: at least half as many stocks with a close as
    on the busiest day. Drops holiday rows (all NaN) and stray prints Yahoo gives one ticker on a
    non-trading day (a Saturday with one close), which would otherwise count as a session and a
    missing bar for every other stock. Off-calendar series are ignored in the count and kept."""
    count = close.drop(columns=list(OFF_CALENDAR.values()), errors="ignore").notna().sum(axis=1)
    return close[(count > 0) & (count >= count.max() / 2)]


def trim(table: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """The table up to and including the session date, so no screen sees later data."""
    return table.loc[:as_of]


def _naive_ist(now: pd.Timestamp) -> pd.Timestamp:
    now = pd.Timestamp(now)
    return now.tz_convert(IST).tz_localize(None) if now.tzinfo is not None else now


SUSPENDED_AFTER = 3  # sessions without a bar before a stock stops holding the date back


def session_info(
    close: pd.DataFrame, now_ist: pd.Timestamp, ignore: list[str] = ()
) -> tuple[pd.Timestamp, list[str], list[tuple[str, pd.Timestamp]]]:
    """(session date, NSE symbols with a late bar, suspended (symbol, last bar date)).

    `close` is a date x symbol frame. Off-calendar series (USD/INR, S&P 500) are ignored. A symbol
    one or two sessions behind the newest date is late and holds the date back; one at least
    SUSPENDED_AFTER sessions behind is suspended (halted, or no longer quoted) and does not.
    Sessions are `sessions(close)`: the dates most NSE series trade on. Symbols in `ignore`
    (Yahoo no longer quotes them) never hold the date back and are in neither list."""
    now = _naive_ist(now_ist)
    nse = close.drop(columns=[*OFF_CALENDAR.values(), *ignore], errors="ignore")
    if now.hour < CLOSE_HOUR:
        nse = nse.loc[nse.index.normalize() < now.normalize()]
    nse = sessions(nse.dropna(axis=1, how="all"))
    if nse.empty:
        raise ValueError("no NSE closes before the session cut-off")
    last = nse.apply(pd.Series.last_valid_index)
    days = nse.index
    behind = len(days) - 1 - days.get_indexer(last)
    stale = last[behind >= SUSPENDED_AFTER]
    live = last[behind < SUSPENDED_AFTER]
    missing = sorted(live.index[live < live.max()])
    suspended = sorted((sym, pd.Timestamp(day)) for sym, day in stale.items())
    return pd.Timestamp(live.min()), missing, suspended


def session_date(close: pd.DataFrame, now_ist: pd.Timestamp) -> tuple[pd.Timestamp, list[str]]:
    """(session date, NSE symbols without a bar on the newest date some other symbol has);
    suspended symbols are left out (see session_info)."""
    as_of, missing, _ = session_info(close, now_ist)
    return as_of, missing
