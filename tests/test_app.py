import asyncio
import json
import threading
from pathlib import Path

from textual.widgets import Static

from mt.app import TerminalApp
from mt.data import DownloadFailed

SNAP = json.loads((Path(__file__).parent / "fixtures" / "snapshot.json").read_text())


def _masthead(app: TerminalApp) -> str:
    return str(app.query_one("#masthead", Static).content)


def test_header_shows_date(snap_compare):
    assert snap_compare(TerminalApp(SNAP, None), terminal_size=(120, 36))


def test_q_quits():
    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test() as pilot:
            assert "Data for Mon 23 Nov 2026" in _masthead(app)
            assert "INFY, TCS" in _masthead(app)
            await pilot.press("q")

    asyncio.run(run())
    assert app.return_code == 0


def test_refresh_failure_sets_notice(caplog):
    def refresh():
        raise ValueError("Yahoo [bold]offline")

    app = TerminalApp(SNAP, refresh)

    async def run():
        async with app.run_test() as pilot:
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            return _masthead(app)

    text = asyncio.run(run())
    assert "Refresh failed: ValueError" in text and "[bold]" not in text
    assert "Data for Mon 23 Nov 2026" in text  # old data still on screen
    assert "ValueError: Yahoo [bold]offline" in caplog.text


def test_launch_shows_cache_first_then_the_update():
    release = threading.Event()
    new = {**SNAP, "as_of": "2026-11-24", "as_of_label": "Data for Tue 24 Nov 2026",
           "missing": [], "stale": False}

    def slow_refresh():
        release.wait(5)
        return new

    app = TerminalApp(SNAP, slow_refresh, update_on_mount=True)

    async def run():
        async with app.run_test() as pilot:
            await pilot.pause()
            first = _masthead(app)
            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            return first, _masthead(app)

    first, after = asyncio.run(run())
    assert "Data for Mon 23 Nov 2026" in first and "Updating…" in first
    assert "Data for Tue 24 Nov 2026" in after and "Updating…" not in after


def test_launch_update_failure_keeps_cache_and_names_the_error():
    def refresh():
        raise DownloadFailed(["TCS"])

    app = TerminalApp(SNAP, refresh, update_on_mount=True)

    async def run():
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            return _masthead(app)

    text = asyncio.run(run())
    assert "Data for Mon 23 Nov 2026" in text and "Refresh failed: DownloadFailed (TCS)" in text


def test_refresh_success_replaces_snapshot():
    new = {**SNAP, "as_of": "2026-11-24", "as_of_label": "Data for Tue 24 Nov 2026",
           "missing": [], "stale": False}
    app = TerminalApp(SNAP, lambda: new)

    async def run():
        async with app.run_test() as pilot:
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            return _masthead(app)

    text = asyncio.run(run())
    assert "Data for Tue 24 Nov 2026" in text and "INFY" not in text


def test_header_lists_suspended_stocks():
    app = TerminalApp({**SNAP, "suspended": [{"symbol": "YESBANK", "last": "2026-11-10"}]}, None)

    async def run():
        async with app.run_test():
            return _masthead(app)

    assert "suspended: YESBANK (last 2026-11-10)" in asyncio.run(run())
