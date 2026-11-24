import numpy as np
import pandas as pd

from mt.session import session_date

EVENING = pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata")
STOCKS = [f"S{i:02d}" for i in range(48)] + ["INFY", "TCS"]


def _close(end: str, symbols=("NIFTY", *STOCKS), periods: int = 30) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=periods, name="date")
    data = np.linspace(100, 110, periods)[:, None] * np.ones(len(symbols))
    return pd.DataFrame(data, index=idx, columns=list(symbols))


def D(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def test_session_is_last_common_date():
    assert session_date(_close("2026-11-23"), EVENING) == (D("2026-11-23"), [])


def test_all_nan_today_row_is_a_holiday():
    close = _close("2026-11-24")
    close.loc["2026-11-24"] = np.nan
    assert session_date(close, EVENING) == (D("2026-11-23"), [])


def test_off_calendar_series_do_not_set_the_session():
    close = _close("2026-11-24")
    close.loc["2026-11-24"] = np.nan
    close["USDINR"] = 84.0  # Yahoo's rupee series has a bar on the NSE holiday
    assert session_date(close, EVENING) == (D("2026-11-23"), [])


def test_partial_day_falls_back_and_names_symbols():
    close = _close("2026-11-24")
    close.loc["2026-11-24", ["TCS", "INFY"]] = np.nan
    assert session_date(close, EVENING) == (D("2026-11-23"), ["INFY", "TCS"])


def test_unfinished_bar_dropped_before_1600_ist():
    now = pd.Timestamp("2026-11-23 15:45", tz="Asia/Kolkata")
    assert session_date(_close("2026-11-23"), now) == (D("2026-11-20"), [])


def test_bar_kept_after_1600_ist():
    now = pd.Timestamp("2026-11-23 16:05", tz="Asia/Kolkata")
    assert session_date(_close("2026-11-23"), now) == (D("2026-11-23"), [])


def test_recent_listing_does_not_block():
    close = _close("2026-11-23")
    close["NEWCO"] = np.nan
    close.iloc[-10:, close.columns.get_loc("NEWCO")] = 50.0
    assert session_date(close, EVENING) == (D("2026-11-23"), [])
