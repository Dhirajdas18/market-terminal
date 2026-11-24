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
