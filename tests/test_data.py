import numpy as np
import pandas as pd
import pytest

import mt.data as data
from mt.data import (
    NSE_TICKERS,
    OFF_CALENDAR,
    SECTORS,
    SYMBOLS,
    DownloadFailed,
    daily_returns,
    load_cache,
    update_cache,
)

ALL = list(NSE_TICKERS.values()) + list(OFF_CALENDAR.values())


def _table(start: str, end: str, value: float = 100.0, symbols=ALL) -> pd.DataFrame:
    idx = pd.bdate_range(start, end, name="date")
    cols = pd.MultiIndex.from_product(
        [["adj_close", "close", "high", "low", "open", "volume"], symbols],
        names=["field", "symbol"],
    )
    return pd.DataFrame(value, index=idx, columns=cols)


class FakeFetch:
    def __init__(self, end: str = "2026-11-23", value: float = 100.0, drop: list[str] = ()):
        self.calls: list[str] = []
        self.end, self.value, self.drop = end, value, list(drop)

    def __call__(self, start: str, end: str | None = None) -> pd.DataFrame:
        self.calls.append(start)
        t = _table(start, self.end, self.value)
        return t.drop(columns=self.drop, level="symbol")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda s: None)


def test_constituent_snapshot_has_fifty_stocks_with_sectors():
    assert len(SYMBOLS) == 50 and set(SECTORS) == set(SYMBOLS)
    assert NSE_TICKERS["^NSEI"] == "NIFTY" and OFF_CALENDAR["INR=X"] == "USDINR"


def test_first_run_fetches_from_2007(tmp_path):
    fetch = FakeFetch()
    table = update_cache(tmp_path / "p.parquet", fetch=fetch)
    assert fetch.calls == ["2007-01-01"]
    assert table.index[-1] == pd.Timestamp("2026-11-23")
    assert set(table.columns.get_level_values("field")) >= {"close", "adj_close", "volume"}


def test_update_fetches_from_last_date_minus_overlap(tmp_path):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20"))
    fetch = FakeFetch(end="2026-11-23")
    update_cache(path, fetch=fetch, overlap_days=7)
    assert fetch.calls == ["2026-11-13"]


def test_overlap_rows_replaced_by_new_values(tmp_path):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20", value=100.0))
    table = update_cache(path, fetch=FakeFetch(end="2026-11-23", value=101.0))
    close = table["close"]["NIFTY"]
    assert close.loc["2026-11-12"] == 100.0  # before the overlap: kept
    assert close.loc["2026-11-13":].eq(101.0).all()  # overlap and new days: replaced
    assert not table.index.duplicated().any()
    assert load_cache(path).equals(table)


def test_missing_ticker_raises_download_failed(tmp_path):
    path = tmp_path / "p.parquet"
    with pytest.raises(DownloadFailed) as err:
        update_cache(path, fetch=FakeFetch(drop=["TCS"]))
    assert err.value.missing == ["TCS"]
    assert not path.exists()


def test_load_cache_none_without_file_and_filters_since(tmp_path):
    path = tmp_path / "p.parquet"
    assert load_cache(path) is None
    update_cache(path, fetch=FakeFetch())
    recent = load_cache(path, since=pd.Timestamp("2026-11-01"))
    assert recent.index.min() == pd.Timestamp("2026-11-02")


def _fixes(tmp_path, rows):
    p = tmp_path / "fixes.csv"
    pd.DataFrame(rows, columns=["symbol", "date", "action", "reason"]).to_csv(p, index=False)
    return p


def test_zero_blank_and_start_fixes(tmp_path):
    idx = pd.bdate_range("2020-01-01", periods=5)
    px = pd.DataFrame({"A": [100.0, 50.0, 51.0, 52.0, 53.0],  # day 1: unadjusted split -> zero
                       "B": [10.0, 1.0, 10.5, 10.6, 10.7],    # day 1: bad print -> blank
                       "C": [99.0, 98.0, 5.0, 5.1, 5.2]},     # real history starts on day 2
                      index=idx)
    fixes = _fixes(tmp_path, [["A", idx[1].date(), "zero", ""], ["B", idx[1].date(), "blank", ""],
                              ["C", idx[2].date(), "start", ""]])
    r = daily_returns(px, fixes)
    assert r.loc[idx[1], "A"] == 0.0
    assert r.loc[idx[1], "B"] == 0.0 and r.loc[idx[2], "B"] == pytest.approx(0.05)
    assert r.loc[: idx[2], "C"].isna().all() and r.loc[idx[3], "C"] == pytest.approx(0.02)
    assert np.isfinite(r.loc[idx[3]]).all()


def test_corrupt_cache_file_is_replaced_by_a_fresh_download(tmp_path):
    path = tmp_path / "p.parquet"
    path.write_bytes(b"not a parquet file")
    fetch = FakeFetch()
    table = update_cache(path, fetch=fetch)
    assert fetch.calls == ["2007-01-01"] and load_cache(path).equals(table)


def test_each_failed_attempt_is_logged(caplog):
    def fetch():
        raise ConnectionError("reset by peer")

    with caplog.at_level("WARNING", logger="mt.data"), pytest.raises(DownloadFailed):
        data.download(fetch, lambda df: [], attempts=3)
    assert caplog.text.count("ConnectionError: reset by peer") == 3


def test_app_path_update_never_loads_the_full_table(tmp_path, monkeypatch):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20"))
    real = data.load_cache

    def only_tail(p=data.DATA_PATH, since=None):
        if since is None:
            raise AssertionError("full-table pandas load")
        return real(p, since)

    monkeypatch.setattr(data, "load_cache", only_tail)
    fetch = FakeFetch(end="2026-11-23")
    tail = update_cache(path, fetch=fetch, since=pd.Timestamp("2026-11-01"))
    assert fetch.calls == ["2026-11-13"]
    assert tail.index.min() == pd.Timestamp("2026-11-02")
    assert tail.index.max() == pd.Timestamp("2026-11-23")
    monkeypatch.undo()
    full = load_cache(path)
    assert full.index.max() == pd.Timestamp("2026-11-23") and not full.index.duplicated().any()
    assert full.index.min() == pd.Timestamp("2007-01-01")


def test_merge_keeps_old_rows_and_replaces_the_overlap(tmp_path):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20", value=100.0))
    later = FakeFetch(end="2026-11-23", value=101.0)
    update_cache(path, fetch=later, since=pd.Timestamp("2026-11-01"))
    close = load_cache(path)["close"]["NIFTY"]
    assert close.loc["2026-11-12"] == 100.0 and close.loc["2026-11-13":].eq(101.0).all()
    assert list(path.parent.glob("*.tmp")) == []


def test_yfinance_caches_live_in_a_private_dir(tmp_path, monkeypatch):
    import stat
    import sys
    import types

    seen = {}
    fake = types.SimpleNamespace(
        set_tz_cache_location=lambda d: seen.setdefault("dir", d),
        download=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    monkeypatch.setattr(data, "YF_CACHE", tmp_path / "cfg" / "yfinance")
    with pytest.raises(RuntimeError):
        data.fetch("2026-01-01")
    assert seen["dir"] == str(tmp_path / "cfg" / "yfinance")
    assert stat.S_IMODE((tmp_path / "cfg" / "yfinance").stat().st_mode) == 0o700


def _write_cache(path, table):
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.Table.from_pandas(table), path)


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_changed_ticker_set_triggers_a_full_redownload(tmp_path, change):
    path = tmp_path / "p.parquet"
    old = _table("2026-11-02", "2026-11-20")
    if change == "extra":
        old = pd.concat([old, _table("2026-11-02", "2026-11-20", symbols=["OLDCO"])], axis=1)
    else:
        old = old.drop(columns=["TCS"], level="symbol")
    _write_cache(path, old.sort_index(axis=1))
    fetch = FakeFetch(end="2026-11-23")
    tail = update_cache(path, fetch=fetch, since=pd.Timestamp("2026-11-01"))
    assert fetch.calls == ["2026-11-13", "2007-01-01"]
    want = sorted(_table("2026-11-23", "2026-11-23").columns)
    assert sorted(tail.columns) == want and sorted(load_cache(path).columns) == want
    assert load_cache(path).index.min() == pd.Timestamp("2007-01-01")


def test_matching_columns_keep_the_incremental_path(tmp_path):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20"))
    fetch = FakeFetch(end="2026-11-23")
    update_cache(path, fetch=fetch, since=pd.Timestamp("2026-11-01"))
    assert fetch.calls == ["2026-11-13"]


# --- a few constituents Yahoo no longer quotes (renamed, merged, long halt) ---


def test_up_to_five_unquoted_constituents_keep_their_cached_history(tmp_path):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20", value=100.0))
    gone = ["TCS", "INFY", "TITAN", "ITC", "SBIN"]
    fetch = FakeFetch(end="2026-11-23", value=101.0, drop=gone)
    table = update_cache(path, fetch=fetch)
    assert table.attrs["no_yahoo_data"] == sorted(gone)
    close = load_cache(path)["close"]
    assert close["TCS"].loc["2026-11-13":"2026-11-20"].eq(100.0).all()  # cached overlap kept
    assert close["TCS"].loc["2026-11-23":].isna().all()
    assert close["NIFTY"].loc["2026-11-13":].eq(101.0).all()
    assert len(fetch.calls) == 2  # one retry in case Yahoo dropped them by chance


def test_six_unquoted_constituents_still_fail_and_leave_the_cache(tmp_path):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20"))
    before = load_cache(path)
    gone = ["TCS", "INFY", "TITAN", "ITC", "SBIN", "HDFCBANK"]
    with pytest.raises(DownloadFailed):
        update_cache(path, fetch=FakeFetch(end="2026-11-23", drop=gone))
    assert load_cache(path).equals(before)


@pytest.mark.parametrize(
    "series", ["NIFTY", "NIFTYBANK", "INDIAVIX", "GOLDBEES", "USDINR", "SP500"]
)
def test_a_missing_index_or_reference_series_still_fails(tmp_path, series):
    path = tmp_path / "p.parquet"
    update_cache(path, fetch=FakeFetch(end="2026-11-20"))
    with pytest.raises(DownloadFailed) as err:
        update_cache(path, fetch=FakeFetch(end="2026-11-23", drop=[series]))
    assert err.value.missing == [series]


def test_first_run_never_accepts_an_unquoted_constituent(tmp_path):
    with pytest.raises(DownloadFailed):
        update_cache(tmp_path / "p.parquet", fetch=FakeFetch(drop=["TCS"]))


def test_full_download_reports_no_unquoted_symbols(tmp_path):
    table = update_cache(tmp_path / "p.parquet", fetch=FakeFetch())
    assert table.attrs["no_yahoo_data"] == []
