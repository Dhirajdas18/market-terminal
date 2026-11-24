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
