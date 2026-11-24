import json

import numpy as np
import pandas as pd
import pytest

from mt import snapshot, stock


def _dates(n: int, freq: str = "B") -> pd.DatetimeIndex:
    return pd.date_range(end="2026-11-23", periods=n, freq=freq, name="date")


def _table(n: int = 400, new_days: int | None = None, seed: int = 3) -> pd.DataFrame:
    """RELIANCE and NIFTY on `n` sessions; JIOFIN listed `new_days` sessions ago (if given)."""
    idx = _dates(n)
    rng = np.random.default_rng(seed)
    nifty = 1.0 + rng.normal(0.0003, 0.01, n)
    rel = 1.0 + 1.2 * (nifty - 1.0) + rng.normal(0, 0.005, n)
    px = pd.DataFrame(
        {"NIFTY": 20000 * nifty.cumprod(), "RELIANCE": 1000 * rel.cumprod()}, index=idx
    )
    if new_days is not None:
        new = pd.Series(np.nan, index=idx)
        new.iloc[-new_days:] = 100 * (1.0 + rng.normal(0, 0.01, new_days)).cumprod()
        px["JIOFIN"] = new
    cols = {}
    for field, scale in (("close", 1.0), ("adj_close", 1.0), ("open", 0.99), ("high", 1.02),
                         ("low", 0.97)):
        for sym in px:
            cols[(field, sym)] = px[sym] * scale
    cols.update({("volume", sym): pd.Series(1e6, index=idx) for sym in px})
    out = pd.DataFrame(cols)
    out.columns.names = ["field", "symbol"]
    return out


def test_blume_shrinks_toward_one():
    rng = np.random.default_rng(1)
    idx = _dates(300)
    r_index = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    assert stock.blume_beta(2.0 * r_index, r_index) == pytest.approx(1.67)
    assert stock.blume_beta(0.0 * r_index, r_index) == pytest.approx(0.33)


def test_blume_needs_a_full_window_of_common_returns():
    rng = np.random.default_rng(1)
    idx = _dates(300)
    r_index = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    r = 2.0 * r_index
    assert stock.blume_beta(r.iloc[-249:], r_index) is None
    r.iloc[::2] = np.nan  # 150 common returns left
    assert stock.blume_beta(r, r_index) is None


def test_blume_is_none_when_the_index_does_not_move():
    idx = _dates(300)
    assert stock.blume_beta(pd.Series(0.01, index=idx), pd.Series(0.0, index=idx)) is None


def test_new_listing_gets_none_not_nan():
    table = _table(new_days=100)
    row = stock.row("JIOFIN", table)
    json.dumps(row, allow_nan=False)  # raises on NaN
    assert row["beta"] is None and row["vol"] is None and row["var95"] is None
    assert row["mdd"] is None and row["y1"] is None
    assert row["close"] == pytest.approx(table["close"]["JIOFIN"].iloc[-1], abs=0.005)
    assert row["m1"] is not None  # 21 sessions exist


def test_full_history_row_has_every_measure():
    row = stock.row("RELIANCE", _table())
    assert set(row) == {"close", "day", "m1", "y1", "vol", "beta", "mdd", "var95", "sector"}
    assert all(row[k] is not None for k in row)
    assert row["sector"] == "Oil Gas & Consumable Fuels"
    assert 0.9 < row["beta"] < 1.7 and row["mdd"] <= 0 and row["var95"] > 0


def test_one_and_twelve_month_returns_compound_the_daily_returns():
    idx = _dates(300)
    rise = pd.Series(100 * 1.001 ** np.arange(300), index=idx)
    table = _table(300)
    for field in ("close", "adj_close"):
        table[(field, "RELIANCE")] = rise
    row = stock.row("RELIANCE", table)
    assert row["day"] == pytest.approx(0.001)
    assert row["m1"] == pytest.approx(1.001**21 - 1, abs=1e-4)
    assert row["y1"] == pytest.approx(1.001**250 - 1, abs=1e-4)
    assert row["mdd"] == 0


def test_a_stock_without_todays_bar_has_no_day_return():
    table = _table()
    table.loc[table.index[-1], [("close", "RELIANCE"), ("adj_close", "RELIANCE")]] = np.nan
    row = stock.row("RELIANCE", table)
    assert row["day"] is None
    assert row["close"] == pytest.approx(table["close"]["RELIANCE"].iloc[-2], abs=0.005)


def test_max_drawdown_is_the_worst_fall_from_a_peak():
    close = pd.Series([100.0] * 100 + [150.0] * 50 + [90.0] * 50 + [120.0] * 100)
    assert stock.max_drawdown(close) == pytest.approx(90 / 150 - 1)
    assert stock.max_drawdown(close.iloc[:249]) is None


def test_max_drawdown_looks_only_at_the_last_250_sessions():
    close = pd.Series([200.0] * 10 + [100.0] * 250)  # the peak is older than the window
    assert stock.max_drawdown(close) == 0


def test_var_is_fifth_percentile_loss():
    r = pd.Series(np.linspace(-0.05, 0.05, 500), index=_dates(500))
    assert stock.var95(r) == pytest.approx(4_500, abs=1)
    assert stock.var95(r, amount=200_000) == pytest.approx(9_000, abs=2)


def test_var_needs_250_returns_and_uses_the_last_500():
    r = pd.Series(np.linspace(-0.05, 0.05, 249), index=_dates(249))
    assert stock.var95(r) is None
    calm = pd.Series(0.001, index=_dates(600))
    calm.iloc[:50] = -0.5  # older than 500 days: ignored
    assert stock.var95(calm) == 0  # a loss is never reported as negative


def test_vol_annualised_by_calendar_days():
    rng = np.random.default_rng(2)
    values = rng.normal(0, 0.01, 250)
    daily = pd.Series(values, index=_dates(250, "D"))  # a return every calendar day
    sd = float(np.std(values, ddof=1))
    assert stock.annual_vol(daily) == pytest.approx(sd * np.sqrt(365.25))
    sessions = pd.Series(values, index=_dates(250, "B"))
    assert stock.annual_vol(sessions) == pytest.approx(sd * np.sqrt(252), rel=0.03)
    assert stock.annual_vol(sessions) != pytest.approx(sd * np.sqrt(252), rel=1e-6)
    assert stock.annual_vol(sessions.iloc[:100]) is None


def test_section_has_compact_candles_for_every_stock():
    section = snapshot.clean(stock.stocks_section(_table(new_days=100)))
    assert set(section) == {"RELIANCE", "JIOFIN"}  # NIFTY is not one of the 50
    c = section["RELIANCE"]["candles"]
    assert list(c) == ["dates", "open", "high", "low", "close", "ma20", "ma50"]
    assert len(c["dates"]) == len(c["close"]) == 250
    assert c["dates"][-1] == "2026-11-23"
    assert all(round(v, 2) == v for v in c["close"])
    assert len(section["JIOFIN"]["candles"]["dates"]) == 100
    assert section["JIOFIN"]["candles"]["ma50"][0] is None
    json.dumps(section, allow_nan=False)


def test_section_without_prices_is_empty():
    assert stock.stocks_section(pd.DataFrame(columns=pd.MultiIndex.from_arrays([[], []]))) == {}


def test_backtest_var_uses_only_returns_before_the_day():
    rng = np.random.default_rng(5)
    r = pd.Series(rng.normal(0, 0.01, 700), index=_dates(700))
    base = stock.rolling_var(r)
    r2 = r.copy()
    r2.iloc[600] = -0.5  # a crash on day 600 must not touch day 600's own VaR
    again = stock.rolling_var(r2)
    assert again.iloc[600] == base.iloc[600]
    assert again.iloc[601] > base.iloc[601]  # but it is in the window from the next day
    assert base.iloc[:250].isna().all() and base.iloc[250:].notna().all()


def test_a_breach_is_a_loss_bigger_than_the_days_var():
    r = pd.Series(np.linspace(-0.05, 0.05, 600), index=_dates(600))
    var = stock.rolling_var(r)
    flags = stock.breaches(r)
    loss = -r
    assert flags.iloc[300] == (loss.iloc[300] > var.iloc[300])
    assert np.isnan(flags.iloc[10])  # no VaR yet: not scored


def test_breach_rate_is_near_five_percent_for_stable_returns():
    rng = np.random.default_rng(9)
    r = pd.DataFrame(rng.normal(0, 0.01, (3000, 10)), index=_dates(3000))
    rate = float(np.nanmean(stock.breaches(r).to_numpy()))
    assert rate == pytest.approx(0.05, abs=0.006)


def test_breaches_rise_when_volatility_jumps():
    rng = np.random.default_rng(9)
    calm = rng.normal(0, 0.005, 600)
    wild = rng.normal(0, 0.02, 100)
    r = pd.Series(np.concatenate([calm, wild]), index=_dates(700))
    flags = stock.breaches(r)
    assert flags.iloc[600:].mean() > 0.2


def test_kupiec_matches_a_known_value():
    # 25 breaches in 500 at p = 5% is exactly on target: LR 0, p 1
    lr, p = stock.kupiec(25, 500)
    assert lr == pytest.approx(0, abs=1e-9) and p == pytest.approx(1)
    lr, p = stock.kupiec(50, 500)  # 10%: well off
    assert lr > 15 and p < 0.001
    assert stock.kupiec(0, 500)[1] < 0.001  # zero breaches is also off target
