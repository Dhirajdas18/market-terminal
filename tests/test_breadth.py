import json

import numpy as np
import pandas as pd

from mt import breadth, snapshot
from mt.snapshot import build


def _closes(n_full=49, rows=60, short_rows=30) -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-11-23", periods=rows, name="date")
    data = {f"S{i}": np.linspace(100.0, 130.0, rows) for i in range(n_full)}
    short = np.full(rows, np.nan)
    short[-short_rows:] = np.linspace(50.0, 60.0, short_rows)
    data["NEW"] = short
    return pd.DataFrame(data, index=idx)


def test_above_ma_denominator_excludes_short_history():
    out = breadth.above_ma(_closes(), 50)
    assert out == {"count": 49, "of": 49}  # rising stocks sit above their average; NEW is left out


def test_above_ma_counts_only_stocks_above():
    close = _closes()
    close.iloc[-1, :10] = 50.0  # ten stocks drop under their 50-day average today
    assert breadth.above_ma(close, 50) == {"count": 39, "of": 49}


def test_above_ma_leaves_out_a_stock_with_no_bar_today():
    close = _closes()
    close.iloc[-1, 0] = np.nan
    assert breadth.above_ma(close, 50)["of"] == 48


def test_new_high_needs_n_days():
    idx = pd.bdate_range("2026-01-01", periods=250)
    full = pd.Series(np.linspace(100, 200, 250), index=idx)  # a high today, 250 closes
    short = pd.Series(np.nan, index=idx)
    short.iloc[-249:] = np.linspace(100, 200, 249)  # also at a high, but only 249 closes
    low = pd.Series(np.linspace(200, 100, 250), index=idx)  # a low today
    out = breadth.new_highs_lows(pd.DataFrame({"full": full, "short": short, "low": low}), 250)
    assert out == {"highs": 1, "lows": 1, "of": 2}


def test_new_high_counts_a_tie_with_the_previous_high():
    idx = pd.bdate_range("2026-01-01", periods=5)
    close = pd.DataFrame({"A": [1.0, 3.0, 2.0, 2.5, 3.0]}, index=idx)
    assert breadth.new_highs_lows(close, 5) == {"highs": 1, "lows": 0, "of": 1}


def test_flat_counted_separately():
    ret = pd.Series({"A": 0.01, "B": -0.02, "C": 0.0, "D": 0.0, "E": np.nan})
    assert breadth.advance_decline(ret) == {"up": 1, "down": 1, "flat": 2}


def test_history_ignores_holiday_rows_and_short_stocks():
    close = _closes(rows=80)
    close.iloc[-30, :] = np.nan  # a holiday: every stock NaN
    hist = breadth.history(close, 50)
    assert len(hist) == 79 and hist["pct_above50"].notna().sum() == 79 - 49
    assert (hist["pct_above50"].dropna() == 1.0).all()
    assert hist["pct_above50"].iloc[:49].isna().all()  # no stock has 50 closes yet


def test_history_uses_only_the_past():
    close = _closes(rows=80)
    full = breadth.history(close, 50)["pct_above50"]
    cut = breadth.history(close.iloc[:70], 50)["pct_above50"]
    pd.testing.assert_series_equal(full.iloc[:70], cut)


def test_fixed_close_applies_start_and_blank_fixes(tmp_path):
    idx = pd.bdate_range("2010-01-04", periods=5)
    close = pd.DataFrame({"A": [5.0, 5.0, 100.0, 101.0, 999.0], "B": 10.0}, index=idx)
    fixes = tmp_path / "f.csv"
    pd.DataFrame(
        {
            "symbol": ["A", "A", "B"],
            "date": [idx[2].date(), idx[4].date(), idx[1].date()],
            "action": ["start", "blank", "zero"],
            "reason": ["", "", ""],
        }
    ).to_csv(fixes, index=False)
    out = breadth.fixed_close(close, fixes)
    assert out["A"].iloc[:2].isna().all() and np.isnan(out["A"].iloc[4])
    assert out["A"].iloc[2] == 100.0 and (out["B"] == 10.0).all()  # zero fixes are return-only


def _table(rows=300) -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-11-23", periods=rows, name="date")
    rng = np.random.default_rng(1)
    names = ["NIFTY", "AAA", "BBB", "NEWCO"]
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.01, (rows, 4)), axis=0), index=idx, columns=names
    )
    close.loc[idx[:-40], "NEWCO"] = np.nan  # listed 40 sessions ago
    cols = pd.MultiIndex.from_product([["close", "adj_close"], names], names=["field", "symbol"])
    return pd.DataFrame(np.hstack([close, close]), index=idx, columns=cols)


def test_section_is_strict_json_and_shows_denominators(monkeypatch):
    monkeypatch.setattr(breadth, "SYMBOLS", ["AAA", "BBB", "NEWCO"])
    out = breadth.section(_table())
    json.dumps(snapshot.clean(out), allow_nan=False)
    assert out["above50"]["of"] == 2  # NEWCO has 40 closes
    assert out["of52"] == 2
    assert out["up"] + out["down"] + out["flat"] == 3  # every stock has today's bar
    assert len(out["spark"]["dates"]) == len(out["spark"]["pct"]) == 250


def test_section_empty_without_adjusted_closes():
    table = _table()
    assert breadth.section(table.drop(columns="adj_close", level=0)) == {}


def test_snapshot_carries_breadth(monkeypatch):
    monkeypatch.setattr(breadth, "SYMBOLS", ["AAA", "BBB", "NEWCO"])
    snap = build(_table(), pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    json.dumps(snap, allow_nan=False)
    keys = {"up", "down", "flat", "above50", "highs", "lows", "of52", "spark"}
    assert set(snap["breadth"]) == keys


def test_newey_west_matches_white_at_zero_lags_and_shrinks_t_with_autocorrelation():
    rng = np.random.default_rng(0)
    e = rng.normal(size=2000)
    y = np.convolve(e, np.ones(20) / 20, mode="valid") + 0.05  # 20-day overlapping means
    X = np.ones((len(y), 1))
    _, t0 = breadth.newey_west(y, X, 0)
    _, t19 = breadth.newey_west(y, X, 19)
    assert abs(t19[0]) < abs(t0[0]) / 2
    coef, _ = breadth.newey_west(y, X, 19)
    assert abs(coef[0] - y.mean()) < 1e-12


def _synthetic(split_shift=0.0):
    idx = pd.bdate_range("2008-01-01", "2020-12-31")
    rng = np.random.default_rng(3)
    nifty = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))), index=idx)
    pct = pd.Series(rng.uniform(0, 1, len(idx)), index=idx)
    return pct, nifty


def test_oos_threshold_comes_from_the_training_period_only():
    pct, nifty = _synthetic()
    base = breadth.oos_check(pct, nifty)
    changed = pct.copy()
    changed.loc["2017":] = changed.loc["2017":] * 0.5 + 0.4  # test-period breadth shifts up
    again = breadth.oos_check(changed, nifty)
    assert base["breadth"]["threshold"] == again["breadth"]["threshold"]
    assert again["breadth"]["high"]["n"] > base["breadth"]["high"]["n"]


def test_oos_scores_only_days_from_the_split_and_finds_a_planted_signal():
    pct, nifty = _synthetic()
    nifty = nifty.copy()
    # plant: after a high-breadth day NIFTY climbs 0.5% a day for the next 20 days
    ret = nifty.pct_change().fillna(0.0)
    high_days = np.flatnonzero((pct > 0.5).to_numpy())
    boost = np.zeros(len(ret))
    for d in high_days:
        boost[d + 1 : d + 21] += 0.0005
    nifty = 100 * (1 + ret + boost).cumprod()
    out = breadth.oos_check(pct, nifty)
    assert out["first_day"] >= "2017-01-01"
    assert out["breadth"]["diff"] > 0 and out["breadth"]["diff_t"] > 2
    assert out["breadth"]["high"]["n"] + out["breadth"]["low"]["n"] == out["n"]


def test_oos_training_period_starts_at_train_start():
    pct, nifty = _synthetic()
    idx = pd.bdate_range("2007-06-01", "2007-12-31")
    pre = pd.Series(0.99, index=idx)  # a 2007 stretch that would drag the median up if used
    nifty_pre = pd.Series(100.0, index=idx)
    out = breadth.oos_check(pd.concat([pre, pct]), pd.concat([nifty_pre, nifty]))
    assert out["train_first"] >= "2008-01-01"
    assert out["breadth"]["threshold"] == breadth.oos_check(pct, nifty)["breadth"]["threshold"]


def test_a_stray_bar_for_one_stock_is_not_a_session():
    close = _closes(rows=80)
    close.index = close.index.rename("date")
    when = close.index[-30] + pd.Timedelta(hours=12)  # a stamp between two real sessions
    stray = pd.DataFrame({c: np.nan for c in close}, index=[when])
    stray["S0"] = 150.0  # e.g. a Saturday Yahoo prints for one ticker only
    both = pd.concat([close, stray]).sort_index()
    hist = breadth.history(both, 50)
    assert len(hist) == 80 and hist["of"].iloc[-1] == 49
    assert (hist["of"].iloc[-20:] == 49).all()  # the stray row did not break the windows
