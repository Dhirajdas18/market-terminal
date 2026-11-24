"""Which trading day the screens show.

A day counts only when every NSE series has a valid close on it. Yahoo can return an all-NaN row
for today on an NSE holiday, publish some stocks' bars before others, or hand out a live bar during
market hours; each of those falls back to the last complete day.
"""

import pandas as pd

from mt.data import OFF_CALENDAR

IST = "Asia/Kolkata"
CLOSE_HOUR = 16  # bars before 16:00 IST are unfinished (NSE closes 15:30, plus settling time)


def _naive_ist(now: pd.Timestamp) -> pd.Timestamp:
    now = pd.Timestamp(now)
    return now.tz_convert(IST).tz_localize(None) if now.tzinfo is not None else now


def session_date(close: pd.DataFrame, now_ist: pd.Timestamp) -> tuple[pd.Timestamp, list[str]]:
    """(session date, NSE symbols without a bar on the newest date some other symbol has).

    `close` is a date x symbol frame. Off-calendar series (USD/INR, S&P 500) are ignored."""
    now = _naive_ist(now_ist)
    nse = close.drop(columns=list(OFF_CALENDAR.values()), errors="ignore")
    if now.hour < CLOSE_HOUR:
        nse = nse.loc[nse.index.normalize() < now.normalize()]
    nse = nse.dropna(axis=1, how="all")
    if nse.empty:
        raise ValueError("no NSE closes before the session cut-off")
    last = nse.apply(pd.Series.last_valid_index)
    as_of = last.min()
    missing = sorted(last.index[last < last.max()])
    return pd.Timestamp(as_of), missing
