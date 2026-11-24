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


def _open_tab(app: TerminalApp, title: str) -> None:
    from textual.widgets import TabbedContent

    app.query_one(TabbedContent).active = widgets_pane(title)


def widgets_pane(title: str) -> str:
    from mt.app import _pane_id

    return _pane_id(title)


def test_chart_tab(snap_compare):
    async def go(pilot):
        _open_tab(pilot.app, "Chart")
        await pilot.pause()
        await pilot.pause()

    assert snap_compare(TerminalApp(SNAP, None), run_before=go, terminal_size=(120, 36))


def test_movers_tab(snap_compare):
    async def go(pilot):
        _open_tab(pilot.app, "Movers")
        await pilot.pause()

    assert snap_compare(TerminalApp(SNAP, None), run_before=go, terminal_size=(120, 36))


def test_chart_is_built_only_when_its_tab_is_shown():
    from textual_plotext import PlotextPlot

    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            before = len(app.query(PlotextPlot))
            _open_tab(app, "Chart")
            await pilot.pause()
            await pilot.pause()
            return before, [p.id for p in app.query(PlotextPlot)]

    before, after = asyncio.run(run())
    assert before == 0
    assert after == ["candles", "traded-value"]


def test_chart_titles_say_what_the_bars_are():
    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Chart")
            await pilot.pause()
            await pilot.pause()
            from textual_plotext import PlotextPlot

            return {p.id: p.plt.build() for p in app.query(PlotextPlot)}

    built = asyncio.run(run())
    assert "Traded value of NIFTY 50 stocks (₹ cr)" in built["traded-value"]
    assert "MA20" in built["candles"] and "MA50" in built["candles"]


def test_movers_tables_show_signed_changes_and_ratio():
    from textual.widgets import DataTable

    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Movers")
            await pilot.pause()
            out = {}
            for ident in ("gainers", "losers", "unusual"):
                t = app.query_one(f"#{ident}", DataTable)
                out[ident] = [[str(c) for c in t.get_row_at(i)] for i in range(t.row_count)]
            return out

    out = asyncio.run(run())
    assert out["gainers"][0] == ["AAAA", "+4.12%"]
    assert out["losers"][0] == ["FFFF", "−5.18%"]
    assert out["unusual"][0] == ["FFFF", "4.6×", "−5.18%"]
    assert out["unusual"][2][2] == "—"  # a missing return shows a dash


def test_movers_symbol_is_not_markup():
    from textual.widgets import DataTable

    mv = {"gainers": [{"symbol": "[bold]X[/]", "ret": 0.01}], "losers": [], "unusual": []}
    app = TerminalApp({**SNAP, "movers": mv}, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Movers")
            await pilot.pause()
            return str(app.query_one("#gainers", DataTable).get_row_at(0)[0])

    assert asyncio.run(run()) == "[bold]X[/]"


def test_window_fits_the_width_and_year_shows_250():
    assert widgets.window_size(120, 250, full=False) == 110  # one candle per plot column
    assert widgets.window_size(400, 250, full=False) == 250  # capped at a year
    assert widgets.window_size(40, 250, full=False) == 60  # never fewer than 60
    assert widgets.window_size(120, 90, full=False) == 90  # only what exists
    assert widgets.window_size(120, 250, full=True) == 250


def _shown(width: int, presses: tuple[str, ...] = ()):
    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test(size=(width, 36)) as pilot:
            _open_tab(app, "Chart")
            await pilot.pause()
            await pilot.pause()
            counts = [app.query_one(widgets.ChartPanel).shown]
            for key in presses:
                await pilot.press(key)
                await pilot.pause()
                counts.append(app.query_one(widgets.ChartPanel).shown)
            titles = [p.plt.build() for p in app.query(widgets.TokenPlot)]
            return counts, titles

    return asyncio.run(run())


def test_y_toggles_between_width_fitted_and_year():
    (fit, year, back), _ = _shown(120, ("y", "y"))
    assert fit == widgets.window_size(120, 250, full=False) and fit < 250
    assert year == 250  # the fixture has 250 sessions, the cap
    assert back == fit


def test_wider_terminal_shows_more_sessions():
    (narrow,), _ = _shown(90)
    (wide,), _ = _shown(120)
    assert narrow < wide


def test_chart_title_states_the_span():
    (_, _), titles = _shown(120, ("y",))
    assert "NIFTY 50 · 1 year" in titles[0]
    (fit,), titles = _shown(120)
    assert f"NIFTY 50 · last {fit} sessions" in titles[0]


def test_span_label_never_claims_a_year_it_lacks():
    assert widgets.span_label(250, 250, True) == "1 year"
    assert widgets.span_label(130, 130, True) == "all 130 sessions"
    assert widgets.span_label(100, 250, False) == "last 100 sessions"


def _y_entries(app):
    return {b.binding.description for k, b in app.active_bindings.items() if k == "y"}


def test_y_binding_only_on_chart_tab_and_label_follows_state():
    app = TerminalApp(SNAP, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            out = {}
            for tab in ("Overview", "Movers"):
                _open_tab(app, tab)
                await pilot.pause()
                await pilot.press("y")
                await pilot.pause()
                out[tab] = (_y_entries(app), app.query_one(widgets.ChartPanel).full)
            _open_tab(app, "Chart")
            await pilot.pause()
            await pilot.pause()
            out["fit"] = _y_entries(app)
            await pilot.press("y")
            await pilot.pause()
            out["year"] = (_y_entries(app), app.query_one(widgets.ChartPanel).full)
            return out

    out = asyncio.run(run())
    assert out["Overview"] == (set(), False) and out["Movers"] == (set(), False)
    assert out["fit"] == {"1 year"}
    assert out["year"] == ({"Fit width"}, True)


def test_breadth_tab(snap_compare):
    async def go(pilot):
        _open_tab(pilot.app, "Breadth")
        await pilot.pause()
        await pilot.pause()

    assert snap_compare(TerminalApp(SNAP, None), run_before=go, terminal_size=(120, 36))


def _breadth_view(snap: dict):
    from textual_plotext import PlotextPlot

    app = TerminalApp(snap, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            before = len(app.query(PlotextPlot))
            _open_tab(app, "Breadth")
            await pilot.pause()
            await pilot.pause()
            text = str(app.query_one("#breadth-counts", Static).content)
            plots = {p.id: p.plt.build() for p in app.query(PlotextPlot)}
            return before, text, plots

    return asyncio.run(run())


def test_breadth_tab_states_every_count_with_its_denominator():
    before, text, plots = _breadth_view(SNAP)
    assert before == 0  # the sparkline is built when the tab is first shown
    assert "30 of 47 above 50-day average" in text
    assert "3 of 45" in text and "0 of 45" in text
    assert "30 up" in text and "16 down" in text and "2 unchanged" in text
    assert "% of stocks above 50-day average" in plots["breadth-spark"]


def test_breadth_tab_handles_missing_values_and_empty_section():
    snap = json.loads(json.dumps(SNAP))
    snap["breadth"]["above50"] = {"count": None, "of": None}
    _, text, _ = _breadth_view(snap)
    assert text.startswith("— above 50-day average")
    snap["breadth"] = {}
    app = TerminalApp(snap, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Breadth")
            await pilot.pause()
            return [str(s.content) for s in app.query(Static) if s.has_class("empty")]

    assert "No breadth data." in asyncio.run(run())


def test_sectors_tab(snap_compare):
    async def go(pilot):
        _open_tab(pilot.app, "Sectors")
        await pilot.pause()
        await pilot.pause()

    assert snap_compare(TerminalApp(SNAP, None), run_before=go, terminal_size=(120, 36))


def _sectors_view(snap: dict):
    from textual.widgets import DataTable

    app = TerminalApp(snap, None)

    def cells(table):
        return [[str(c.plain if hasattr(c, "plain") else c) for c in table.get_row_at(i)]
                for i in range(table.row_count)]

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Sectors")
            await pilot.pause()
            header = str(app.query_one("#sectors-summary", Static).content)
            heat = app.query_one("#sector-heat", DataTable)
            contrib = app.query_one("#contributions", DataTable)
            first, last = heat.get_row_at(0)[1], heat.get_row_at(heat.row_count - 1)[1]
            styles = [first.style, last.style]
            return header, cells(heat), cells(contrib), [str(s) for s in styles]

    return asyncio.run(run())


def test_sectors_tab_prints_values_counts_and_the_daily_check():
    header, heat, contrib, styles = _sectors_view(SNAP)
    assert header.startswith("Sum of estimates: +84 pts · NIFTY moved: +91 pts")
    assert heat[0][0] == "Information Technology" and heat[0][1] == "+1.87%" and heat[0][2] == "2"
    assert heat[-1][1] == "−2.41%"  # true minus sign
    assert "on #" in styles[0] and "on #" in styles[1] and styles[0] != styles[1]
    assert contrib[0][0] == "RELIANCE" and contrib[0][1] == "−52.3"
    assert contrib[0][2] == "9.0%"
    assert [r[0] for r in contrib[-2:]] == ["COALINDIA", "JIOFIN"]
    assert contrib[-1][1] == "weight not estimated yet"


def test_sectors_tab_zero_is_grey_and_missing_values_are_dashes():
    from mt.widgets import heat_colour

    assert heat_colour(0.0) == "#2e2d2b" and heat_colour(None) == "#2e2d2b"
    assert heat_colour(0.05) == heat_colour(0.02) != heat_colour(0.01)
    snap = json.loads(json.dumps(SNAP))
    snap["contributions"]["sum_points"] = None
    snap["contributions"]["top"][0]["points"] = None
    header, _, contrib, _ = _sectors_view(snap)
    assert header.startswith("Sum of estimates: — · NIFTY moved: +91 pts")
    assert contrib[0][1] == "—"


def test_sectors_tab_empty_section():
    snap = {**SNAP, "sectors": [], "contributions": {}}
    app = TerminalApp(snap, None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Sectors")
            await pilot.pause()
            return [str(s.content) for s in app.query(Static) if s.has_class("empty")]

    assert "No sector data." in asyncio.run(run())


# --- Watchlist and stock view -------------------------------------------------------------

def _wl_app(tmp_path=None, snap=None, saved=None):
    """An app whose watchlist lives in tmp_path (never the real config directory)."""
    path = None
    if tmp_path is not None:
        path = tmp_path / "watchlist.json"
        if saved is not None:
            path.write_text(json.dumps(saved))
    return TerminalApp(snap or SNAP, None, watchlist_path=path), path


def _cells(table) -> list[list[str]]:
    return [[str(c.plain if hasattr(c, "plain") else c) for c in table.get_row_at(i)]
            for i in range(table.row_count)]


def _texts(app) -> str:
    return " ".join(str(s.content) for s in app.query(Static))


def test_watchlist_tab(snap_compare):
    async def go(pilot):
        _open_tab(pilot.app, "Watchlist")
        await pilot.pause()
        await pilot.pause()

    assert snap_compare(TerminalApp(SNAP, None), run_before=go, terminal_size=(120, 36))


def test_stock_view(snap_compare):
    async def go(pilot):
        _open_tab(pilot.app, "Watchlist")
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

    assert snap_compare(TerminalApp(SNAP, None), run_before=go, terminal_size=(120, 36))


def test_watchlist_rows_show_numbers_and_dashes_for_a_new_listing():
    from textual.widgets import DataTable

    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            return _cells(app.query_one("#watchlist-table", DataTable))

    rows = asyncio.run(run())
    assert [r[0] for r in rows] == ["HDFCBANK", "RELIANCE", "LT", "JIOFIN"]  # the demo seed
    assert rows[1][1:] == ["1,400.00", "−2.41%", "−4.62%", "+2.93%", "16.3%", "0.97"]
    assert rows[3][1:] == ["310.00", "+0.04%", "−5.42%", "—", "—", "—"]


def test_empty_watchlist_says_how_to_add():
    app, _ = _wl_app(snap={**SNAP, "watchlist": []})

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            return _texts(app)

    assert "Press a to add" in asyncio.run(run())


def test_file_with_unknown_and_junk_symbols_still_opens(tmp_path):
    from textual.widgets import DataTable

    app, _ = _wl_app(tmp_path, saved=["RELIANCE", "GONE", "[bold]x", 7])

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            return _cells(app.query_one("#watchlist-table", DataTable))

    assert [r[0] for r in asyncio.run(run())] == ["RELIANCE"]


def test_corrupt_file_opens_an_empty_watchlist(tmp_path):
    app, path = _wl_app(tmp_path)
    path.write_text("{oops")

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            return app.watchlist

    assert asyncio.run(run()) == []


def test_a_then_enter_adds_the_stock_and_writes_the_file(tmp_path):
    from textual.widgets import DataTable

    app, path = _wl_app(tmp_path, saved=["RELIANCE"])

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("down", "enter")  # BHARTIARTL is first, COALINDIA second
            await pilot.pause()
            await pilot.pause()
            return app.watchlist, _cells(app.query_one("#watchlist-table", DataTable))

    held, rows = asyncio.run(run())
    assert held == ["RELIANCE", "COALINDIA"]
    assert [r[0] for r in rows] == ["RELIANCE", "COALINDIA"]
    assert json.loads(path.read_text()) == ["RELIANCE", "COALINDIA"]
    assert (path.stat().st_mode & 0o777) == 0o600


def test_picker_lists_only_stocks_not_yet_watched_and_escape_cancels(tmp_path):
    from textual.widgets import OptionList

    app, path = _wl_app(tmp_path, saved=["RELIANCE"])

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            ids = [o.id for o in app.screen.query_one(OptionList).options]
            await pilot.press("escape")
            await pilot.pause()
            return ids, app.watchlist, len(app.screen_stack)

    ids, held, depth = asyncio.run(run())
    assert "RELIANCE" not in ids and ids[0] == "BHARTIARTL" and len(ids) == 11
    assert held == ["RELIANCE"] and depth == 1
    assert json.loads(path.read_text()) == ["RELIANCE"]


def test_d_removes_the_highlighted_row_and_writes_the_file(tmp_path):
    from textual.widgets import DataTable

    app, path = _wl_app(tmp_path, saved=["RELIANCE", "LT", "ITC"])

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            await pilot.press("down", "down", "d")  # focus the table, then LT
            await pilot.pause()
            await pilot.pause()
            return app.watchlist, _cells(app.query_one("#watchlist-table", DataTable))

    held, rows = asyncio.run(run())
    assert held == ["RELIANCE", "ITC"] and [r[0] for r in rows] == ["RELIANCE", "ITC"]
    assert json.loads(path.read_text()) == ["RELIANCE", "ITC"]


def test_a_and_d_only_on_the_watchlist_tab():
    app, _ = _wl_app()

    def keys():
        return {k for k in ("a", "d") if k in app.active_bindings}

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            out = {}
            for tab in ("Overview", "Movers", "Sectors", "Watchlist"):
                _open_tab(app, tab)
                await pilot.pause()
                await pilot.pause()
                out[tab] = keys()
            return out

    out = asyncio.run(run())
    assert out["Overview"] == out["Movers"] == out["Sectors"] == set()
    assert out["Watchlist"] == {"a", "d"}


def test_a_failed_save_names_the_error_and_keeps_the_list(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    app = TerminalApp(SNAP, None, watchlist_path=blocker / "sub" / "watchlist.json")

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            await pilot.press("a", "enter")
            await pilot.pause()
            await pilot.pause()
            return _masthead(app), app.watchlist

    text, held = asyncio.run(run())
    assert "Watchlist not saved" in text
    assert "BHARTIARTL" in held  # still shown for this session


def _stock_screen_text(app) -> str:
    return " ".join(str(s.content) for s in app.screen.query(Static))


def test_enter_on_a_sectors_row_opens_the_stock_and_escape_closes_it():
    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Sectors")
            await pilot.pause()
            before = len(app.screen_stack)
            await pilot.press("down", "enter")
            await pilot.pause()
            await pilot.pause()
            opened = (
                len(app.screen_stack),
                _stock_screen_text(app),
                len(app.screen.query(widgets.TokenPlot)),
            )
            await pilot.press("escape")
            await pilot.pause()
            return before, opened, len(app.screen_stack)

    before, (depth, text, plots), after = asyncio.run(run())
    assert (before, depth, after) == (1, 2, 1)
    assert "RELIANCE" in text and "Oil Gas & Consumable Fuels" in text
    assert "Beta" in text and "0.97" in text and "16.3%" in text and "−10.2%" in text
    assert "₹1,612" in text and "₹1,00,000" in text
    assert plots == 1


def test_enter_on_a_movers_row_opens_a_stock_that_is_not_in_the_snapshot():
    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Movers")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            return _stock_screen_text(app)

    assert "No data for AAAA in this snapshot" in asyncio.run(run())


def test_enter_on_a_watchlist_row_opens_a_new_listing_with_dashes_and_a_reason():
    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            await pilot.press("down", "down", "down", "down", "enter")  # JIOFIN, row 4
            await pilot.pause()
            await pilot.pause()
            return _stock_screen_text(app)

    text = asyncio.run(run())
    assert "JIOFIN" in text and "Beta" in text and "not enough history" in text
    assert "None" not in text and "NaN" not in text and " nan" not in text


def test_stock_view_is_not_built_until_a_row_is_opened(monkeypatch):
    built = []
    real = widgets.StockScreen.__init__

    def spy(self, symbol):
        built.append(symbol)
        real(self, symbol)

    monkeypatch.setattr(widgets.StockScreen, "__init__", spy)
    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            for tab in ("Movers", "Sectors", "Watchlist"):
                _open_tab(app, tab)
                await pilot.pause()
            assert built == []
            await pilot.press("down", "enter")
            await pilot.pause()

    asyncio.run(run())
    assert built == ["HDFCBANK"]


def test_stock_view_text_from_the_snapshot_is_not_markup():
    snap = json.loads(json.dumps(SNAP))
    snap["stocks"]["RELIANCE"]["sector"] = "[bold red]Oil[/] & Gas"
    app, _ = _wl_app(snap=snap)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Sectors")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            return _stock_screen_text(app)

    assert "[bold red]Oil[/] & Gas" in asyncio.run(run())


def test_refresh_while_a_stock_is_open_keeps_it_and_updates_the_screen_beneath():
    new = {**SNAP, "as_of_label": "Data for Tue 24 Nov 2026"}
    app = TerminalApp(SNAP, lambda: new, watchlist_path=None)

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Sectors")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            await pilot.press("r")
            await _settled(app, pilot)
            during = (len(app.screen_stack), _stock_screen_text(app))
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            return during, _masthead(app), len(app.screen_stack)

    (depth, text), masthead, after = asyncio.run(run())
    assert depth == 2 and "RELIANCE" in text
    assert "Tue 24 Nov 2026" in masthead and after == 1


def test_candles_in_the_stock_view_use_the_chart_drawing_code():
    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Sectors")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            await pilot.pause()
            plot = app.screen.query_one(widgets.TokenPlot)
            return plot.plt._title if hasattr(plot.plt, "_title") else str(plot.plt.build())

    assert "RELIANCE · last" in asyncio.run(run())


def test_indian_grouping_of_rupees():
    assert widgets.inr(1_00_000) == "₹1,00,000"
    assert widgets.inr(2300) == "₹2,300"
    assert widgets.inr(12_34_567) == "₹12,34,567"
    assert widgets.inr(950.4) == "₹950"


def test_tab_keys_do_nothing_while_the_stock_view_is_open():
    app, _ = _wl_app()

    async def run():
        async with app.run_test(size=(120, 36)) as pilot:
            _open_tab(app, "Watchlist")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()
            keys = {k for k in ("a", "d", "y", "down") if k in app.active_bindings}
            await pilot.press("a", "d", "y")
            await pilot.pause()
            return keys, len(app.screen_stack), app.watchlist

    keys, depth, held = asyncio.run(run())
    assert keys == set() and depth == 2 and held == ["HDFCBANK", "RELIANCE", "LT", "JIOFIN"]
