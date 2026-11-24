import stat
from pathlib import Path

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
    def __init__(self, snapshot, refresh=None, update_on_mount=False, **kw):
        Recorder.args = (snapshot, refresh, update_on_mount)
        Recorder.kw = kw
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


DEMO = "tests/fixtures/snapshot.json"


def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("demo must not touch the network or the cache")

    for name in ("update_cache", "load_cache", "save_cache"):
        if hasattr(mt.data, name):
            monkeypatch.setattr(mt.data, name, boom)
    monkeypatch.setattr(cli, "refresh", boom)


def test_demo_flag_opens_without_network(monkeypatch, recorder):
    _no_network(monkeypatch)
    assert cli.main(["--demo", DEMO]) == 0
    snap, refresh, update_on_mount = recorder.args
    assert snap["as_of_label"].startswith("Data for") and update_on_mount is False
    assert refresh is None


def test_demo_refresh_is_off(monkeypatch):
    import asyncio
    import json

    from mt.app import TerminalApp

    _no_network(monkeypatch)
    snap = json.loads(Path(DEMO).read_text())

    async def run():
        app = TerminalApp(snap, None, refresh_off_notice="Demo data \u2014 refresh off")
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.press("r")
            await pilot.pause()
            return app.snapshot["notice"]

    assert asyncio.run(run()) == "Demo data \u2014 refresh off"


@pytest.mark.parametrize("content", [None, "{not json", "[1, 2]", "{}"])
def test_demo_bad_file_exits_cleanly(tmp_path, capsys, recorder, content):
    path = tmp_path / "d.json"
    if content is not None:
        path.write_text(content)
    assert cli.main(["--demo", str(path)]) == 1
    err = capsys.readouterr().err
    assert "demo" in err.lower() and "Traceback" not in err


def test_every_topic_section_is_built_by_the_real_launch_path():
    snap = cli.snapshot_from(_cache())
    for key in ("overview", "index", "movers", "breadth", "sectors", "contributions", "stocks"):
        assert key in snap


def test_app_opens_on_the_watchlist_file_but_the_demo_keeps_it_in_memory(
    monkeypatch, recorder, tmp_path
):
    import mt.watchlist

    monkeypatch.setattr(mt.watchlist, "WATCHLIST", tmp_path / "w.json")
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: _cache())
    cli.run_app()
    assert recorder.kw["watchlist_path"] == tmp_path / "w.json"
    demo = tmp_path / "demo.json"
    demo.write_text('{"as_of": "2026-11-23"}')
    cli.run_demo(str(demo))
    assert "watchlist_path" not in recorder.kw
