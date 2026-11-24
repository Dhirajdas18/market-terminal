import stat
from pathlib import Path

import pandas as pd
import pytest

import mt.app
import mt.data
from mt import cli


def _cache(since=None) -> pd.DataFrame:
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

    def no_network(since=None):
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
                        lambda since=None: real_update(tmp_path / "p.parquet", fetch=fetch))
    assert cli.run_app() == 1
    err = capsys.readouterr().err
    assert "No price data yet" in err and "DownloadFailed" in err and "Traceback" not in err


def test_no_cache_and_unexpected_error_exits_1(monkeypatch, recorder, capsys):
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: None)

    def broken(since=None):
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


# --- offline behaviour, membership wiring and hardening ---


def test_offline_with_cache_opens_with_notice(monkeypatch):
    import asyncio

    from textual.widgets import Static

    monkeypatch.setattr(cli, "now_ist", lambda: pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: _cache())

    def offline(since=None):
        raise OSError("network is down")

    monkeypatch.setattr(mt.data, "update_cache", offline)
    built = {}
    real = mt.app.TerminalApp

    def make(*a, **kw):
        built["app"] = real(*a, **kw)
        built["app"].run = lambda: None
        return built["app"]

    monkeypatch.setattr(mt.app, "TerminalApp", make)
    assert cli.run_app() == 0
    app = built["app"]

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(100):
                if not app.refreshing:
                    break
                await pilot.pause(0.02)
            await pilot.pause()
            return str(app.query_one("#masthead", Static).content)

    text = asyncio.run(run())
    assert "Refresh failed: OSError" in text and "Data for Mon 23 Nov 2026" in text


def test_offline_without_cache_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: None)
    monkeypatch.setattr(cli, "setup_logging", lambda: None)

    def offline(since=None):
        raise OSError("network is down")

    monkeypatch.setattr(mt.data, "update_cache", offline)
    assert cli.main([]) == 1
    err = capsys.readouterr().err
    assert "No price data yet" in err and "Traceback" not in err


def test_refresh_puts_the_membership_banner_in_the_notice(monkeypatch):
    import mt.membership

    monkeypatch.setattr(cli, "now_ist", lambda: pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    monkeypatch.setattr(mt.data, "update_cache", _cache)
    banner = "NIFTY 50 list changed: +X"
    monkeypatch.setattr(mt.membership, "check", lambda committed, fetch, *a, **k: banner)
    assert cli.refresh()["notice"] == banner


def test_demo_and_first_download_never_check_membership(monkeypatch, recorder):
    import mt.membership

    def boom(*a, **k):
        raise AssertionError("no membership check here")

    monkeypatch.setattr(mt.membership, "check", boom)
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: None)
    monkeypatch.setattr(mt.data, "update_cache", _cache)
    assert cli.run_app() == 0
    _no_network(monkeypatch)
    assert cli.main(["--demo", DEMO]) == 0


def test_unusable_cache_is_treated_as_no_cache(monkeypatch, recorder, capsys):
    bad = pd.DataFrame({"x": [1.0]}, index=pd.DatetimeIndex(["2026-11-20"], name="date"))
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: bad)
    monkeypatch.setattr(mt.data, "update_cache", _cache)
    assert cli.run_app() == 0
    snap, _refresh, update_on_mount = recorder.args
    assert snap["as_of"] == "2026-11-23" and update_on_mount is False
    assert "Traceback" not in capsys.readouterr().err


def test_first_download_announces_itself_on_stderr(monkeypatch, recorder, capsys):
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: None)
    monkeypatch.setattr(mt.data, "update_cache", _cache)
    cli.run_app()
    assert "Downloading price history (first run, about 20 s)…" in capsys.readouterr().err


def test_start_deletes_stale_temp_files_only_in_the_data_dir(monkeypatch, recorder, tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    stale, keep1, keep2 = d / "tmpab12cd.tmp", d / "prices.parquet", d / "notes.tmp"
    for f in (stale, keep1, keep2):
        f.write_text("x")
    monkeypatch.setattr(mt.data, "DATA_PATH", d / "prices.parquet")
    monkeypatch.setattr(mt.data, "load_cache", lambda since=None: _cache())
    cli.run_app()
    assert not stale.exists() and keep1.exists() and keep2.exists()


def test_demo_nested_json_and_big_files_exit_cleanly(tmp_path, capsys, recorder):
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200_000 + "]" * 200_000)
    assert cli.main(["--demo", str(deep)]) == 1
    big = tmp_path / "big.json"
    big.write_text('{"as_of": "x", "pad": "' + "a" * (5 * 1024 * 1024) + '"}')
    assert cli.main(["--demo", str(big)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "too large" in err and err.count("Cannot open demo file") == 2


def _fresh(monkeypatch):
    import mt.membership

    monkeypatch.setattr(cli, "now_ist", lambda: pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    monkeypatch.setattr(mt.data, "update_cache", _cache)
    return mt.membership


def test_membership_failure_never_loses_the_downloaded_snapshot(monkeypatch):
    membership = _fresh(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("banner broke")

    monkeypatch.setattr(membership, "check", boom)
    snap = cli.refresh()
    assert snap["as_of"] == "2026-11-23" and snap["notice"] is None


def test_binary_stamp_file_still_delivers_the_snapshot(monkeypatch, tmp_path):
    membership = _fresh(monkeypatch)
    stamp = tmp_path / "stamp"
    stamp.write_bytes(b"\xff\xfe\x00bad")
    monkeypatch.setattr(membership, "STAMP", stamp)
    monkeypatch.setattr(membership, "fetch_nse", lambda: set(mt.data.SYMBOLS))
    assert cli.refresh()["as_of"] == "2026-11-23"


def test_unwritable_stamp_dir_still_delivers_the_snapshot(monkeypatch, tmp_path):
    membership = _fresh(monkeypatch)
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    monkeypatch.setattr(membership, "STAMP", ro / "sub" / "stamp")
    monkeypatch.setattr(membership, "fetch_nse", lambda: set(mt.data.SYMBOLS))
    try:
        assert cli.refresh()["as_of"] == "2026-11-23"
    finally:
        ro.chmod(0o700)


def test_refresh_without_some_constituents_names_them_and_still_checks_membership(monkeypatch):
    import mt.membership

    def partial(since=None):
        table = _cache()
        table.loc["2026-11-23", ("close", "TCS")] = float("nan")  # Yahoo no longer quotes TCS
        table.loc["2026-11-23", ("adj_close", "TCS")] = float("nan")
        table.attrs["no_yahoo_data"] = ["TCS"]
        return table

    checked = []
    monkeypatch.setattr(cli, "now_ist", lambda: pd.Timestamp("2026-11-24 20:00", tz="Asia/Kolkata"))
    monkeypatch.setattr(mt.data, "update_cache", partial)
    monkeypatch.setattr(
        mt.membership, "check", lambda committed, fetch, *a, **k: checked.append(1) or "banner"
    )
    snap = cli.refresh()
    assert snap["no_data"] == ["TCS"] and checked == [1] and snap["notice"] == "banner"
    assert snap["as_of"] == "2026-11-23" and snap["missing"] == []  # TCS does not hold it back


def test_full_refresh_has_an_empty_no_data_list(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(mt.membership, "check", lambda *a, **k: None)
    assert cli.refresh()["no_data"] == []


def test_demo_file_control_characters_never_reach_the_terminal(monkeypatch, recorder, tmp_path):
    import json

    _no_network(monkeypatch)
    snap = json.loads(Path(DEMO).read_text())
    osc52 = "\x1b]52;c;Y3VybCBldmlsLnNofHNoCg==\x07"
    snap["notice"] = f"hello{osc52}\x1b]0;pwn\x1b\\ world\nsecond line"
    snap["missing"] = [f"TCS{osc52}"]
    snap["stocks"] = {f"\x9b{k}": v for k, v in snap["stocks"].items()}
    bad = tmp_path / "evil.json"
    bad.write_text(json.dumps(snap))
    assert cli.main(["--demo", str(bad)]) == 0
    loaded = recorder.args[0]
    dumped = json.dumps(loaded, ensure_ascii=False)
    assert "\x1b" not in dumped and "\x07" not in dumped and "\x9b" not in dumped
    assert loaded["notice"].endswith(" world\nsecond line")  # newlines are kept
