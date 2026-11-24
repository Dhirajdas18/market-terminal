import numpy as np
import pandas as pd

from mt.reports import unexplained_drops, weekday_gaps


def test_weekday_gaps_splits_holidays_from_index_gaps():
    idx = pd.bdate_range("2024-01-01", "2024-12-31", name="date")
    close = pd.DataFrame({"NIFTY": 100.0, "TCS": 50.0, "USDINR": 83.0}, index=idx)
    close.loc["2024-01-22", ["NIFTY", "TCS"]] = np.nan  # holiday: no NSE bar (rupee still trades)
    close.loc["2024-01-10", "NIFTY"] = np.nan  # stocks traded, index bar missing
    gaps = weekday_gaps(close, 2024, 2024)
    assert gaps.loc[2024, "holiday"] == 1 and gaps.loc[2024, "index_gap"] == 1


def test_unexplained_drops_ignores_vix_and_listed_fixes(tmp_path):
    idx = pd.bdate_range("2024-01-01", periods=4)
    adj = pd.DataFrame({"A": [100.0, 70.0, 70.0, 70.0], "B": [100.0, 100.0, 50.0, 50.0],
                        "INDIAVIX": [20.0, 10.0, 10.0, 10.0]}, index=idx)
    fixes = tmp_path / "f.csv"
    pd.DataFrame({"symbol": ["A"], "date": [idx[1].date()], "action": ["zero"],
                  "reason": [""]}).to_csv(fixes, index=False)
    hits, listed, unlisted = unexplained_drops(adj, fixes)
    assert hits == 2 and listed == 1 and unlisted == [("B", idx[2])]


def test_drops_before_a_start_fix_count_as_listed(tmp_path):
    idx = pd.bdate_range("2008-03-12", periods=4)
    adj = pd.DataFrame({"NEWCO": [2000.0, 700.0, 700.0, 700.0]}, index=idx)
    fixes = tmp_path / "f.csv"
    pd.DataFrame({"symbol": ["NEWCO"], "date": [idx[3].date()], "action": ["start"],
                  "reason": [""]}).to_csv(fixes, index=False)
    assert unexplained_drops(adj, fixes) == (1, 1, [])


def test_us_returns_align_same_date_and_previous_session():
    from mt.reports import aligned_returns

    nse = pd.to_datetime(["2024-07-01", "2024-07-02", "2024-07-03", "2024-07-05", "2024-07-08"])
    nifty = pd.Series([100.0, 101.0, 103.02, 103.02 * 0.99, 103.02 * 0.99 * 1.02], index=nse)
    # S&P: no bar on Thu 4 Jul (US holiday); each return is vs its own previous bar
    sp_dates = pd.to_datetime(
        ["2024-06-28", "2024-07-01", "2024-07-02", "2024-07-03", "2024-07-05"])
    sp = pd.Series([100.0, 110.0, 110.0 * 0.95, 110.0 * 0.95 * 1.01, 110.0 * 0.95 * 1.01 * 1.03],
                   index=sp_dates)
    out = aligned_returns(nifty, sp)
    # NIFTY Fri 5 Jul (-1%): same-date S&P (+3%), previous US session = Wed 3 Jul (+1%)
    row = out.loc["2024-07-05"]
    assert abs(row["nifty"] + 0.01) < 1e-9
    assert abs(row["same"] - 0.03) < 1e-9 and abs(row["prev"] - 0.01) < 1e-9
    # Mon 8 Jul: S&P has no bar that day, so no same-date value; previous session is Fri 5 Jul
    row = out.loc["2024-07-08"]
    assert np.isnan(row["same"]) and abs(row["prev"] - 0.03) < 1e-9
    # Wed 3 Jul: previous US session is Tue 2 Jul (-5%), strictly before the NSE date
    assert abs(out.loc["2024-07-03", "prev"] + 0.05) < 1e-9


def test_correlation_t_stat():
    from mt.reports import corr_t

    r, t, n = corr_t(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
                     pd.Series([1.0, 2.1, 2.9, 4.2, 4.8, 6.1]))
    assert n == 6 and r > 0.99 and t > 20


def test_spike_reversal_needs_a_big_move_a_big_reversal_and_a_quiet_index():
    from mt.reports import spike_reversals

    idx = pd.bdate_range("2024-01-01", periods=6)
    ret = pd.DataFrame(
        {
            "A": [0.0, 0.18, -0.13, 0.0, 0.0, 0.0],  # spike and reverse
            "B": [0.0, 0.18, 0.02, 0.0, 0.0, 0.0],  # spike, no reversal
            "C": [0.0, 0.0, 0.0, 0.16, -0.13, 0.0],  # spike and reverse, but the index fell 5%
        },
        index=idx,
    )
    index = pd.Series([0.0, 0.0, 0.0, -0.05, 0.0, 0.0], index=idx)
    assert spike_reversals(ret, index) == [("A", idx[1])]


def test_clustered_t_is_smaller_than_plain_t_when_dates_share_a_shock():
    from mt.reports import cluster_ols

    rng = np.random.default_rng(0)
    dates = np.repeat(np.arange(40), 25)
    shock = np.repeat(rng.normal(0, 1, 40), 25)  # everything on a date moves together
    flag = np.repeat((rng.random(40) < 0.5).astype(float), 25)  # a market-wide, per-date flag
    y = 0.2 * flag + shock + rng.normal(0, 0.3, len(dates))
    X = np.column_stack([np.ones(len(dates)), flag])
    coef, t_cluster, n = cluster_ols(y, X, dates)
    _, t_plain, _ = cluster_ols(y, X, np.arange(len(dates)))  # one cluster per row
    assert n == 1000 and abs(coef[1] - 0.2) < 1.0
    assert abs(t_cluster[1]) < abs(t_plain[1])


def test_next_day_table_uses_only_prior_volume_and_next_return():
    from mt.reports import next_day_table

    idx = pd.bdate_range("2024-01-01", periods=24)
    names = [f"S{i}" for i in range(10)]
    vol = pd.DataFrame(100.0, index=idx, columns=names)
    vol.loc[idx[21], "S3"] = 500.0  # S3 trades 5x its usual volume on day 21
    ret = pd.DataFrame(0.01, index=idx, columns=names)
    ret.loc[idx[22], "S3"] = -0.04
    out = next_day_table(ret, vol)
    row = out[(out["date"] == idx[21]) & (out["symbol"] == "S3")].iloc[0]
    assert row["top"] and abs(row["today"] - 0.01) < 1e-12 and abs(row["next"] - 0.04) < 1e-12
    assert out[out["date"] == idx[21]]["top"].sum() == 1
    assert out["date"].max() == idx[22]  # the last day has no next-day return


def test_tracking_stats_share_within_and_error_against_the_move():
    from mt.reports import _tracking_stats

    err = pd.Series([1.0, -4.0, 20.0, -2.0])
    actual = pd.Series([10.0, -20.0, 40.0, 0.0])  # a zero move has no relative error
    st = _tracking_stats(err, actual)
    assert st["within"] == 0.75 and st["median"] == 3.0
    assert abs(st["rel_median"] - 0.2) < 1e-12  # relative errors 0.1, 0.2, 0.5
    assert abs(st["rel_total"] - 27 / 70) < 1e-12


def test_var_backtest_counts_breaches_by_year_and_stock():
    from mt.reports import var_backtest

    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2009-01-01", "2013-12-31", name="date")
    r = pd.DataFrame(rng.normal(0, 0.01, (len(idx), 3)), index=idx, columns=["A", "B", "C"])
    res = var_backtest(r, start="2011-01-01")
    assert res["flags"].index[0] >= pd.Timestamp("2011-01-01")
    assert res["k"] == sum(k for k, _ in res["by_year"].values())
    assert res["n"] == sum(n for _, n in res["by_year"].values())
    assert res["k"] == sum(k for k, _ in res["per_stock"].values())
    assert set(res["by_year"]) == {2011, 2012, 2013}
    assert abs(res["k"] / res["n"] - 0.05) < 0.015
