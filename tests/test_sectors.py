import json

import numpy as np
import pandas as pd
import pytest

from mt import sectors
from mt.snapshot import build

NOW = pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata")


def _returns(rows=61, names=("A", "B", "C"), seed=1) -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-11-23", periods=rows, name="date")
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(0, 0.01, (rows, len(names))), index=idx, columns=list(names))


def _index(R: pd.DataFrame, w: dict[str, float]) -> pd.Series:
    return sum(R[k] * v for k, v in w.items())


def test_nnls_recovers_known_weights():
    R = _returns()
    w = sectors.nnls_weights(R, _index(R, {"A": 0.5, "B": 0.3, "C": 0.2}))
    assert w["A"] == pytest.approx(0.5, abs=1e-6)
    assert w["B"] == pytest.approx(0.3, abs=1e-6)
    assert w["C"] == pytest.approx(0.2, abs=1e-6)


def test_nnls_ignores_today():
    R = _returns()
    r_index = _index(R, {"A": 0.5, "B": 0.3, "C": 0.2})
    base = sectors.nnls_weights(R, r_index)
    R2, r2 = R.copy(), r_index.copy()
    R2.iloc[-1] = [0.09, -0.08, 0.07]
    r2.iloc[-1] = -0.05
    pd.testing.assert_series_equal(base, sectors.nnls_weights(R2, r2))


def test_nnls_uses_only_the_window_before_today():
    R = _returns(rows=100)
    r_index = _index(R, {"A": 0.5, "B": 0.3, "C": 0.2})
    r_index.iloc[:30] = 0.5  # nonsense older than the 60-session window
    w = sectors.nnls_weights(R, r_index)
    assert w["A"] == pytest.approx(0.5, abs=1e-6)


def test_weights_are_never_negative_and_sum_to_one():
    R = _returns(names=("A", "B", "C", "D"))
    r_index = _index(R, {"A": 0.7, "B": 0.5, "C": -0.2})  # an unreachable negative weight
    w = sectors.nnls_weights(R, r_index)
    assert (w.dropna() >= 0).all() and w.sum() == pytest.approx(1.0)


def test_short_history_stock_not_estimated():
    R = _returns(names=("A", "B", "C", "NEW"))
    R.loc[R.index[:-20], "NEW"] = np.nan  # 19 returns before today
    w = sectors.nnls_weights(R, _index(R, {"A": 0.5, "B": 0.3, "C": 0.2}))
    assert np.isnan(w["NEW"]) and w.drop("NEW").sum() == pytest.approx(1.0)
    c = sectors.contributions(w, R.iloc[-1], 24000.0)
    assert bool(c.loc["NEW", "not_estimated"]) and np.isnan(c.loc["NEW", "points"])
    assert c.index[-1] == "NEW"  # unestimated rows sort last


def test_nnls_with_fewer_rows_than_the_window_estimates_nothing():
    R = _returns(rows=40)
    assert sectors.nnls_weights(R, _index(R, {"A": 1.0})).isna().all()


def test_points_sum_to_index_move_for_exact_weights():
    R = _returns()
    w = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
    r_index = _index(R, w.to_dict())
    c = sectors.contributions(w, R.iloc[-1], 24000.0)
    check = sectors.daily_check(c, 24000.0 * (1 + r_index.iloc[-1]), 24000.0)
    assert check["sum_points"] == pytest.approx(check["actual_points"], abs=1e-6)
    assert list(c.index) == list(c["points"].abs().sort_values(ascending=False).index)


def test_hdfc_example_adds_about_37_points():
    c = sectors.contributions(pd.Series({"HDFCBANK": 0.13}), pd.Series({"HDFCBANK": 0.012}), 24000)
    assert c.loc["HDFCBANK", "points"] == pytest.approx(37.44)


def test_sector_returns_equal_weight_with_count():
    ret = pd.Series({"A": 0.02, "B": 0.04, "C": -0.01, "D": np.nan, "E": np.nan})
    sec = {"A": "Banks", "B": "Banks", "C": "IT", "D": "IT", "E": "Power"}
    out = sectors.sector_returns(ret, sec)
    assert out.loc["Banks", "ret"] == pytest.approx(0.03) and out.loc["Banks", "n"] == 2
    assert out.loc["IT", "ret"] == pytest.approx(-0.01)
    assert out.loc["IT", "n"] == 1  # the NaN stock is not counted
    assert "Power" not in out.index  # no stock with a return
    assert list(out.index) == ["Banks", "IT"]  # best first


def _table(rows=90, symbols=("AAAA", "BBBB", "CCCC")) -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-11-23", periods=rows, name="date")
    rng = np.random.default_rng(5)
    r = pd.DataFrame(rng.normal(0, 0.01, (rows, len(symbols))), index=idx, columns=list(symbols))
    r.iloc[0] = 0
    close = 100 * (1 + r).cumprod()
    w = dict(zip(symbols, (0.5, 0.3, 0.2), strict=False))
    nifty = 20000 * (1 + _index(r, w)).cumprod()
    cols = {}
    for field in ("close", "adj_close"):
        for s in symbols:
            cols[(field, s)] = close[s]
        cols[(field, "NIFTY")] = nifty
    out = pd.DataFrame(cols)
    out.columns.names = ["field", "symbol"]
    return out


def test_section_has_sectors_and_contributions_and_serialises(monkeypatch):
    sec = {"AAAA": "Banks", "BBBB": "Banks", "CCCC": "IT"}
    names = list(sec)
    monkeypatch.setattr(sectors, "SECTORS", sec)
    monkeypatch.setattr(sectors, "SYMBOLS", names)
    table = _table()
    table[("close", "NEWCO")] = np.nan
    table.loc[table.index[-10:], ("close", "NEWCO")] = 50.0
    table = table.sort_index(axis=1)
    sec["NEWCO"] = "IT"
    names.append("NEWCO")
    snap = build(table, NOW)
    json.dumps(snap, allow_nan=False)
    assert {s["name"] for s in snap["sectors"]} == {"Banks", "IT"}
    assert all(set(s) == {"name", "ret", "n"} for s in snap["sectors"])
    c = snap["contributions"]
    assert set(c) == {"top", "not_estimated", "sum_points", "actual_points"}
    assert c["not_estimated"] == ["NEWCO"]
    assert {t["symbol"] for t in c["top"]} == {"AAAA", "BBBB", "CCCC"}
    assert c["sum_points"] == pytest.approx(c["actual_points"], rel=1e-3, abs=1.0)


def test_contributions_section_is_empty_without_nifty_but_sectors_remain(monkeypatch):
    sec = {"AAAA": "Banks", "BBBB": "Banks", "CCCC": "IT"}
    monkeypatch.setattr(sectors, "SECTORS", sec)
    monkeypatch.setattr(sectors, "SYMBOLS", list(sec))
    table = _table().drop(columns=[("close", "NIFTY"), ("adj_close", "NIFTY")])
    assert sectors.contributions_section(table) == {}
    assert len(sectors.sectors_section(table)) == 2


def test_sectors_section_survives_a_table_whose_last_row_has_no_stock_closes(monkeypatch):
    monkeypatch.setattr(sectors, "SECTORS", {"AAAA": "Banks"})
    monkeypatch.setattr(sectors, "SYMBOLS", ["AAAA"])
    table = _table(symbols=("AAAA",))
    table.loc[table.index[-1], ("close", "AAAA")] = np.nan
    assert sectors.sectors_section(table) == []


def _closes_from(R: pd.DataFrame, w: dict[str, float]) -> pd.DataFrame:
    close = 100 * (1 + R).cumprod()
    close["NIFTY"] = 20000 * (1 + _index(R, w)).cumprod()
    return close


def test_rolling_tracking_is_near_zero_error_for_exact_weights_and_uses_prior_days_only():
    R = _returns(rows=200, seed=9)
    w = {"A": 0.5, "B": 0.3, "C": 0.2}
    close = _closes_from(R, w)
    out = sectors.rolling_tracking(close, start=str(close.index[100].date()))
    assert len(out) == 100 and out["n_est"].eq(3).all()
    assert (out["est_pts"] - out["actual_pts"]).abs().max() < 1e-4
    # change one day's index close: that day's estimate must not move
    day = close.index[150]
    bumped = close.copy()
    bumped.loc[day:, "NIFTY"] *= 1.03
    again = sectors.rolling_tracking(bumped, start=str(close.index[100].date()))
    assert again.loc[day, "est_ret"] == pytest.approx(out.loc[day, "est_ret"], abs=1e-12)
    assert again.loc[day, "actual_ret"] != out.loc[day, "actual_ret"]


def test_rolling_tracking_skips_days_without_an_index_return():
    R = _returns(rows=200, seed=9)
    close = _closes_from(R, {"A": 0.5, "B": 0.3, "C": 0.2})
    close.loc[close.index[150], "NIFTY"] = np.nan
    out = sectors.rolling_tracking(close, start=str(close.index[100].date()))
    assert close.index[150] not in out.index and close.index[151] not in out.index
