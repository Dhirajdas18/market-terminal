import asyncio
import json
from pathlib import Path

from textual.widgets import Static

from mt.app import TerminalApp

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


def test_refresh_failure_sets_notice():
    def refresh():
        raise RuntimeError("Yahoo [bold]offline")

    app = TerminalApp(SNAP, refresh)

    async def run():
        async with app.run_test() as pilot:
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            return _masthead(app)

    text = asyncio.run(run())
    assert "Refresh failed: Yahoo [bold]offline" in text  # shown as plain text, not markup
    assert "Data for Mon 23 Nov 2026" in text  # old data still on screen


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
