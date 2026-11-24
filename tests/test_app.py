import asyncio
import json
import threading
import time
from pathlib import Path

from textual.widgets import Static

from mt import widgets
from mt.app import TerminalApp
from mt.data import DownloadFailed

SNAP = json.loads((Path(__file__).parent / "fixtures" / "snapshot.json").read_text())


def _masthead(app: TerminalApp) -> str:
    return str(app.query_one("#masthead", Static).content)


async def _settled(app: TerminalApp, pilot, timeout: float = 5.0) -> None:
    """Wait until no refresh is in flight."""
    deadline = time.monotonic() + timeout
    while app.refreshing and time.monotonic() < deadline:
        await pilot.pause(0.01)
    await pilot.pause()


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
            await _settled(app, pilot)
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
            await _settled(app, pilot)
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
            await _settled(app, pilot)
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
            await _settled(app, pilot)
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


def test_quit_during_a_slow_refresh_is_prompt_and_leaves_no_blocking_thread():
    release = threading.Event()

    def stuck_refresh():  # an in-flight HTTP call that cannot be cancelled
        release.wait(30)
        return SNAP

    app = TerminalApp(SNAP, stuck_refresh, update_on_mount=True)

    pressed = {}

    async def run():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.refreshing
            pressed["at"] = time.monotonic()
            await pilot.press("q")

    try:
        asyncio.run(run())  # includes asyncio's join of its default thread pool
        took = time.monotonic() - pressed["at"]
        # Non-daemon threads are joined at interpreter exit; none may be left waiting on the fetch.
        blocking = [t for t in threading.enumerate()
                    if t is not threading.main_thread() and not t.daemon and t.is_alive()]
        assert took < 1.0 and app.return_code == 0
        assert blocking == []
    finally:
        release.set()


def test_r_during_a_refresh_does_not_start_another():
    release = threading.Event()
    calls = []
    new = {**SNAP, "as_of": "2026-11-24", "as_of_label": "Data for Tue 24 Nov 2026",
           "missing": [], "stale": False}

    def slow_refresh():
        calls.append(1)
        release.wait(5)
        return new

    app = TerminalApp(SNAP, slow_refresh, update_on_mount=True)

    async def run():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("r")
            await pilot.press("r")
            await pilot.pause(0.1)
            release.set()
            await _settled(app, pilot)
            return _masthead(app)

    text = asyncio.run(run())
    assert len(calls) == 1
    assert "Data for Tue 24 Nov 2026" in text and "Updating…" not in text


def _tile_text(app: TerminalApp) -> str:
    return " ".join(str(w.content) for w in app.query(".tile"))


def test_overview_tab(snap_compare):
    assert snap_compare(TerminalApp(SNAP, None), terminal_size=(120, 36))


def test_overview_tiles_show_values_signs_and_own_date():
    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test(size=(120, 36)):
            return [str(w.content) for w in app.query(".tile")]

    tiles = asyncio.run(run())
    assert len(tiles) == 6
    joined = "\n".join(tiles)
    assert "+0.62%" in joined and "−3.82%" in joined and "24,500.00" in joined
    sp = next(t for t in tiles if "S&P 500" in t)
    assert "Fri 20 Nov" in sp
    assert "Fri 20 Nov" not in next(t for t in tiles if "NIFTY 50" in t)


def test_external_name_in_overview_is_not_markup():
    snap = {**SNAP, "overview": [{**SNAP["overview"][0], "name": "[bold]X[/]"}]}
    app = TerminalApp(snap, None)

    async def run():
        async with app.run_test(size=(120, 36)):
            return [w.content for w in app.query(".tile")]

    (tile,) = asyncio.run(run())
    assert "[bold]X[/]" in tile.plain


def test_refresh_keeps_the_selected_tab(monkeypatch):
    from textual.widgets import TabbedContent

    monkeypatch.setattr(
        widgets, "TABS", [*widgets.TABS, ("Second", lambda snap: Static("second panel"))]
    )
    new = {**SNAP, "as_of": "2026-11-24", "as_of_label": "Data for Tue 24 Nov 2026",
           "missing": [], "stale": False}
    app = TerminalApp(SNAP, lambda: new)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            tabs = app.query_one(TabbedContent)
            first = tabs.active
            tabs.active = [p.id for p in tabs.query("TabPane")][1]
            await pilot.pause()
            chosen = tabs.active
            await pilot.press("r")
            await _settled(app, pilot)
            await pilot.pause()
            return first, chosen, app.query_one(TabbedContent).active, _masthead(app)

    first, chosen, after, text = asyncio.run(run())
    assert chosen != first and after == chosen
    assert "Data for Tue 24 Nov 2026" in text


def test_vix_tile_changes_are_not_coloured_up_or_down():
    vix = next(r for r in SNAP["overview"] if r["name"] == "INDIAVIX")
    nifty = next(r for r in SNAP["overview"] if r["name"] == "NIFTY")

    def change_styles(row):
        text = widgets.tile_text(row, SNAP["as_of"])
        return {str(s.style) for s in text.spans if text.plain[s.start:s.end].endswith("%")}

    assert change_styles(vix).isdisjoint({widgets.UP, widgets.DOWN})
    assert widgets.UP in change_styles(nifty)
