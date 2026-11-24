import json

import numpy as np
import pandas as pd

from mt import candles, snapshot
from mt.snapshot import build


def test_ma_needs_full_window():
    close = pd.Series(np.arange(1.0, 11.0))
    ma = candles.moving_average(close, 5)
    assert ma.iloc[:4].isna().all()
    assert ma.iloc[4] == 3.0 and ma.iloc[9] == 8.0


def test_unusual_volume_excludes_today():
    vol = pd.DataFrame({"A": [100.0] * 20 + [300.0]})
    ratio = candles.unusual_volume(vol, 20)
    assert ratio["A"].iloc[-1] == 3.0  # 300 / mean of the 20 days before it, not including it
    assert ratio["A"].iloc[:20].isna().all()  # fewer than 20 prior days


def test_unusual_volume_ignores_zero_and_missing_days():
    vol = pd.DataFrame({"A": [100.0] * 10 + [0.0] + [100.0] * 9 + [200.0]})
    assert np.isnan(candles.unusual_volume(vol, 20)["A"].iloc[-1])  # a 0 is no volume print


def test_unusual_volume_skips_rows_where_nothing_traded():
    vol = pd.DataFrame({"A": [100.0] * 10 + [np.nan] + [100.0] * 10 + [300.0]})  # a holiday row
    assert candles.unusual_volume(vol, 20)["A"].iloc[-1] == 3.0


def test_gap_uses_previous_close():
    open_ = pd.Series([100.0, 103.0, 99.0])
    close = pd.Series([101.0, 98.0, 100.0])
    gap = candles.gap(open_, close)
    assert np.isnan(gap.iloc[0])
    assert abs(gap.iloc[1] - (103 / 101 - 1)) < 1e-12
    assert abs(gap.iloc[2] - (99 / 98 - 1)) < 1e-12


def test_gap_skips_a_missing_bar():
    open_ = pd.Series([100.0, np.nan, 99.0])
    close = pd.Series([101.0, np.nan, 100.0])
    gap = candles.gap(open_, close)
    assert abs(gap.iloc[2] - (99 / 101 - 1)) < 1e-12  # vs the last valid close


def test_movers_ignore_nan():
    ret = pd.Series({"A": 0.05, "B": np.nan, "C": -0.04, "D": 0.01, "E": -0.01})
    out = candles.movers(ret, k=2)
    assert [m["symbol"] for m in out["gainers"]] == ["A", "D"]
    assert [m["symbol"] for m in out["losers"]] == ["C", "E"]
    assert out["gainers"][0] == {"symbol": "A", "ret": 0.05}


def test_traded_value_in_crore():
    close = pd.DataFrame({"A": [100.0, 200.0], "B": [50.0, np.nan]})
    vol = pd.DataFrame({"A": [1e5, 1e5], "B": [2e5, 2e5]})
    tv = candles.traded_value(close, vol)
    assert tv.iloc[0] == (100 * 1e5 + 50 * 2e5) / 1e7  # 2.0 crore
    assert tv.iloc[1] == 200 * 1e5 / 1e7  # a missing close drops that stock


def _table(rows=400):
    idx = pd.bdate_range("2025-01-01", periods=rows, name="date")
    rng = np.random.default_rng(1)
    cols = {}
    for f in ["open", "high", "low", "close", "adj_close"]:
        base = 100 + np.cumsum(rng.normal(0, 1, rows))
        cols[(f, "NIFTY")] = base
        cols[(f, "AAA")] = base
        cols[(f, "BBB")] = base * 2
    for s in ["NIFTY", "AAA", "BBB"]:
        cols[("volume", s)] = np.full(rows, 1e6)
    t = pd.DataFrame(cols, index=idx)
    t.columns = pd.MultiIndex.from_tuples(t.columns, names=["field", "symbol"])
    return t


def test_index_series_cut_after_ma():
    out = candles.index_series(_table(400), symbols=["AAA", "BBB"])
    assert len(out["dates"]) == 250
    assert out["ma50"][0] is not None and out["ma20"][0] is not None  # warmed up before the cut
    assert not np.isnan(out["ma50"]).any()


def test_index_series_skips_days_without_a_nifty_bar_and_labels_value():
    t = _table(300)
    t.loc[t.index[100], [("close", "NIFTY"), ("open", "NIFTY")]] = np.nan
    out = candles.index_series(t, symbols=["AAA", "BBB"])
    assert str(t.index[100].date()) not in out["dates"]
    first_close = t["close"][["AAA", "BBB"]].iloc[-250:].iloc[-1]
    expect = (first_close * 1e6).sum() / 1e7
    assert abs(out["value_cr"][-1] - expect) < 1e-9


def test_snapshot_has_index_and_movers_as_strict_json():
    assert {"index", "movers"} <= dict(snapshot.SECTIONS).keys()
    t = _table(400)
    snap = build(t, pd.Timestamp("2026-11-23 18:00", tz="Asia/Kolkata"))
    json.dumps(snap, allow_nan=False)
    assert set(snap["index"]) == {
        "dates", "open", "high", "low", "close", "ma20", "ma50", "value_cr"}
    assert set(snap["movers"]) == {"gainers", "losers", "unusual"}
