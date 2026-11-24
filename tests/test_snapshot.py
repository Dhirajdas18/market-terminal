import json

import numpy as np
import pandas as pd

from mt import snapshot
from mt.snapshot import build, clean


def _table(end: str) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=5, name="date")
    cols = pd.MultiIndex.from_product([["close", "adj_close"], ["NIFTY", "TCS"]],
                                      names=["field", "symbol"])
    return pd.DataFrame(100.0, index=idx, columns=cols)


def test_snapshot_states_stale_date():
    snap = build(_table("2026-11-23"), pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    assert snap["as_of"] == "2026-11-23"
    assert snap["stale"] is True
    assert snap["as_of_label"] == "Data for Mon 23 Nov 2026"
    assert snap["missing"] == [] and snap["notice"] is None


def test_snapshot_same_day_is_not_stale():
    snap = build(_table("2026-11-23"), pd.Timestamp("2026-11-23 18:00", tz="Asia/Kolkata"))
    assert snap["stale"] is False


def test_sections_see_only_data_up_to_the_session(monkeypatch):
    table = _table("2026-11-24")
    table.loc["2026-11-24", ("close", "TCS")] = np.nan
    monkeypatch.setattr(snapshot, "SECTIONS", [("probe", lambda t: str(t.index.max().date()))])
    snap = build(table, pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    assert snap["missing"] == ["TCS"] and snap["probe"] == "2026-11-23"


def test_clean_makes_strict_json():
    out = json.dumps(clean({"x": float("nan"), "y": np.float64(1)}), allow_nan=False)
    assert out == '{"x": null, "y": 1.0}'


def test_clean_handles_nested_numpy_and_timestamps():
    obj = {"a": [np.int64(2), np.inf, np.bool_(True)], "d": pd.Timestamp("2026-11-23")}
    assert clean(obj) == {"a": [2, None, True], "d": "2026-11-23"}
