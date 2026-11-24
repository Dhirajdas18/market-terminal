import json

import numpy as np
import pandas as pd

from mt import overview, snapshot
from mt.snapshot import build


def _series(values, start):
    idx = pd.bdate_range(start, periods=len(values), name="date")
    return pd.Series(values, index=idx, dtype=float)


def test_week_uses_previous_week_last_close():
    close = _series([100, 101, 102, 103, 104, 110], "2026-11-16")  # Mon 16 .. Mon 23
    r = overview.period_returns(close, pd.Timestamp("2026-11-23"))
    assert abs(r["week"] - (110 / 104 - 1)) < 1e-12  # vs Fri 20, not vs Mon 16
    assert abs(r["day"] - (110 / 104 - 1)) < 1e-12


def test_ytd_from_last_close_of_previous_year():
    idx = pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02", "2026-11-23"])
    close = pd.Series([90.0, 100.0, 105.0, 120.0], index=idx)
    r = overview.period_returns(close, pd.Timestamp("2026-11-23"))
    assert abs(r["ytd"] - 0.2) < 1e-12


def test_returns_are_none_without_history():
    close = _series([100.0], "2026-11-23")
    assert overview.period_returns(close, pd.Timestamp("2026-11-23")) == {
        "day": None, "week": None, "ytd": None}


def test_range_position_is_one_at_new_high():
    close = _series([100, 105, 110], "2026-11-19")
    high, low = close + 1, close - 1
    high.iloc[-1] = close.iloc[-1]  # closed on its high
    out = overview.range_52w(close, high, low, pd.Timestamp("2026-11-23"))
    assert out["pos"] == 1.0 and out["high"] == 110 and out["low"] == 99


def test_range_ignores_bars_older_than_365_days():
    idx = pd.to_datetime(["2025-01-02", "2026-06-01", "2026-11-23"])
    close = pd.Series([500.0, 100.0, 150.0], index=idx)
    out = overview.range_52w(close, close, close, pd.Timestamp("2026-11-23"))
    assert out["high"] == 150 and out["low"] == 100 and out["pos"] == 1.0


def _table():
    idx = pd.bdate_range("2026-11-02", "2026-11-23", name="date")
    cols = pd.MultiIndex.from_product(
        [["open", "high", "low", "close", "adj_close"],
         ["NIFTY", "NIFTYBANK", "INDIAVIX", "USDINR", "GOLDBEES", "SP500"]],
        names=["field", "symbol"])
    base = pd.DataFrame(np.linspace(100, 110, len(idx))[:, None] * np.ones(len(cols)),
                        index=idx, columns=cols)
    base.loc["2026-11-23", [("close", "SP500"), ("high", "SP500"), ("low", "SP500")]] = np.nan
    return base


def test_off_calendar_uses_own_last_date():
    table = _table()
    table.loc["2026-11-24", :] = 1.0  # dated after as_of: dropped, not shown
    as_of = pd.Timestamp("2026-11-23")
    sp = overview.item("SP500", table, as_of)
    assert sp["date"] == "2026-11-20"
    assert sp["close"] == table.loc["2026-11-20", ("close", "SP500")]
    assert overview.item("NIFTY", table, as_of)["date"] == "2026-11-23"
    names = [i["name"] for i in overview.section(table.loc[:"2026-11-23"])]
    assert names == ["NIFTY", "NIFTYBANK", "INDIAVIX", "USDINR", "GOLDBEES", "SP500"]


def test_snapshot_overview_is_strict_json():
    table = _table()
    assert "overview" in dict(snapshot.SECTIONS)
    snap = build(table, pd.Timestamp("2026-11-23 18:00", tz="Asia/Kolkata"))
    json.dumps(snap, allow_nan=False)
    assert set(snap["overview"][0]) == {
        "name", "date", "close", "day", "week", "ytd", "low52", "high52", "pos52"}
