import stat

import pandas as pd
import pytest

import mt.app
import mt.data
from mt import cli


def _cache() -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-11-23", periods=30, name="date")
    cols = pd.MultiIndex.from_product([["close", "adj_close"], ["NIFTY", "TCS"]],
                                      names=["field", "symbol"])
    return pd.DataFrame(100.0, index=idx, columns=cols)


class Recorder:
    def __init__(self, snapshot, refresh=None, update_on_mount=False):
        Recorder.args = (snapshot, refresh, update_on_mount)
        self.return_code = 0

    def run(self):
        pass


@pytest.fixture
def recorder(monkeypatch):
    monkeypatch.setattr(mt.app, "TerminalApp", Recorder)
    monkeypatch.setattr(cli, "now_ist", lambda: pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    return Recorder


def test_warm_cache_opens_at_once_and_updates_in_the_app(monkeypatch, recorder):
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: _cache())

    def no_network():
        raise AssertionError("launch must not wait on the download")

    monkeypatch.setattr(mt.data, "update_cache", no_network)
    assert cli.run_app() == 0
    snap, refresh, update_on_mount = recorder.args
    assert snap["as_of"] == "2026-11-23" and update_on_mount is True and refresh is cli.refresh


def test_no_cache_and_failing_fetch_exits_1_without_traceback(monkeypatch, recorder, capsys,
                                                               tmp_path):
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: None)
    monkeypatch.setattr(mt.data.time, "sleep", lambda s: None)
    real_update = mt.data.update_cache

    def fetch(start, end=None):
        raise ValueError("bad response")

    monkeypatch.setattr(mt.data, "update_cache",
                        lambda: real_update(tmp_path / "p.parquet", fetch=fetch))
    assert cli.run_app() == 1
    err = capsys.readouterr().err
    assert "No cached prices" in err and "DownloadFailed" in err and "Traceback" not in err


def test_no_cache_and_unexpected_error_exits_1(monkeypatch, recorder, capsys):
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: None)

    def broken():
        raise ValueError("parquet engine missing")

    monkeypatch.setattr(mt.data, "update_cache", broken)
    assert cli.run_app() == 1
    assert "ValueError" in capsys.readouterr().err


def test_log_file_is_private(tmp_path):
    path = cli.setup_logging(tmp_path / "cfg")
    assert stat.S_IMODE((tmp_path / "cfg").stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
