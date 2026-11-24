"""The Textual app: a masthead (session date, missing symbols, notice), one tab per panel, and
two keys: q quits, r refreshes in a thread worker so the screen never waits on the network."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Static, TabbedContent, TabPane

from mt import watchlist, widgets
from mt.data import SYMBOLS, error_label

log = logging.getLogger(__name__)

TEXT_2 = "#c3c2b7"
WARN = "#c98500"


def _pane_id(title: str) -> str:
    return "tab-" + "".join(c if c.isalnum() else "-" for c in title.lower())


def masthead(snap: dict) -> Text:
    """Header line as plain Text: symbols and notices come from outside the repo, never markup."""
    text = Text(snap["as_of_label"], style="bold")
    if snap.get("stale"):
        text.append("  (last complete NSE session)", style=TEXT_2)
    if snap.get("missing"):
        text.append(f"  ·  no bar yet: {', '.join(snap['missing'])}", style=WARN)
    if snap.get("suspended"):
        names = ", ".join(f"{s['symbol']} (last {s['last']})" for s in snap["suspended"])
        text.append(f"  ·  suspended: {names}", style=TEXT_2)
    if snap.get("notice"):
        text.append(f"\n{snap['notice']}", style=WARN)
    return text


class TerminalApp(App):
    CSS_PATH = Path(__file__).with_name("app.tcss")  # absolute, so subclasses elsewhere work
    TITLE = "market-terminal"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_data", "Refresh"),
        Binding("y", "show_year", "1 year"),
        Binding("y", "fit_width", "Fit width"),
        Binding("a", "add_stock", "Add stock"),
        Binding("d", "remove_stock", "Remove"),
        Binding("down", "focus_table", "Pick a stock"),
    ]

    def __init__(
        self,
        snapshot: dict,
        refresh: Callable[[], dict] | None = None,
        update_on_mount: bool = False,
        refresh_off_notice: str = "Refresh is not available here.",
        watchlist_path: Path | None = None,
    ):
        """`refresh` downloads and returns a new snapshot (run in a thread worker). With
        `update_on_mount` the app shows `snapshot` (the cache) at once, then refreshes.
        `watchlist_path` is the watchlist file; None keeps the list in memory only (demo and
        tests), seeded from the snapshot's optional "watchlist" list."""
        super().__init__()
        self.snapshot = snapshot
        self._watchlist_path = watchlist_path
        self.watchlist: list[str] = self._initial_watchlist()
        self._ui_stale = False
        self._refresh_fn = refresh
        self._update_on_mount = update_on_mount
        self._refreshing = False
        self._refresh_off_notice = refresh_off_notice

    def _initial_watchlist(self) -> list[str]:
        if self._watchlist_path is not None:
            return watchlist.load(self._watchlist_path, known=SYMBOLS)
        seed = self.snapshot.get("watchlist")
        return watchlist.validate(seed, list(self.snapshot.get("stocks") or {}))

    def on_mount(self) -> None:
        # Any screen on top (stock view, add-stock picker, ^p palette) defers a finished refresh;
        # it is drawn when the main screen is active again.
        self.screen_change_signal.subscribe(self, self._screen_changed)
        if self._update_on_mount and self._refresh_fn is not None:
            self.action_refresh_data()

    def compose(self) -> ComposeResult:
        yield Static(masthead(self.snapshot), id="masthead")
        with Vertical(id="body"):
            yield from self._panels()
        yield Footer()

    def _panels(self):
        if not widgets.TABS:
            yield Static("No panels yet.", id="empty")
            return
        with TabbedContent():
            for title, make in widgets.TABS:
                with TabPane(title, id=_pane_id(title)):
                    yield make({**self.snapshot, "watchlist": self.watchlist})

    def _chart_state(self) -> bool | None:
        """None when the Chart tab is not the active one, else whether it shows the year."""
        panels = self.query(widgets.ChartPanel)
        if not panels or self._active_tab() != _pane_id("Chart"):
            return None
        return panels.first().full

    def _active_tab(self) -> str | None:
        """The id of the shown tab pane; None when another screen (the stock view, a picker) is on
        top. App.query always searches the main screen, so the stack is checked first."""
        if len(self.screen_stack) > 1:
            return None
        tabs = self.query(TabbedContent)
        return tabs.first().active if tabs else None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "add_stock":
            return self._active_tab() == _pane_id("Watchlist")
        if action == "remove_stock":
            return self._active_tab() == _pane_id("Watchlist") and bool(self.watchlist)
        if action == "focus_table":  # from the tab bar, go down into the tab's stock table
            return self._symbol_table() is not None and not isinstance(self.focused, DataTable)
        if action not in ("show_year", "fit_width"):
            return True
        state = self._chart_state()  # one key, two labels: show only the one that applies
        return state is not None and state == (action == "fit_width")

    def _symbol_table(self) -> DataTable | None:
        active = self._active_tab()
        if active is None:
            return None
        tables = self.query_one(f"#{active}").query("DataTable.symbols")
        return tables.first() if tables else None

    def action_focus_table(self) -> None:
        table = self._symbol_table()
        if table is not None:
            table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.has_class("symbols") and event.row_key.value:
            self.push_screen(widgets.StockScreen(str(event.row_key.value)))

    def close_stock(self) -> None:
        """Leave the stock view (a refresh that finished meanwhile is drawn by _screen_changed)."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def _screen_changed(self, screen) -> None:
        if self._ui_stale and screen is self.screen_stack[0]:
            self._ui_stale = False
            self.call_later(self._recompose_tabs)

    async def _recompose_tabs(self) -> None:
        tabs = self.query(TabbedContent)
        keep = tabs.first().active if tabs else None
        await self.recompose()
        tabs = self.query(TabbedContent)
        if keep and tabs and tabs.first().active != keep:
            tabs.first().active = keep

    def action_add_stock(self) -> None:
        stocks = self.snapshot.get("stocks") or {}
        choices = [
            (sym, stocks[sym].get("sector")) for sym in sorted(stocks) if sym not in self.watchlist
        ]
        self.push_screen(widgets.PickStock(choices), self._added)

    def _added(self, symbol: str | None) -> None:
        if symbol and symbol not in self.watchlist:
            self.watchlist = [*self.watchlist, symbol]
            self._watchlist_changed()

    def action_remove_stock(self) -> None:
        panels = self.query(widgets.WatchlistPanel)
        symbol = panels.first().highlighted() if panels else None
        if symbol in self.watchlist:
            self.watchlist = [s for s in self.watchlist if s != symbol]
            self._watchlist_changed()

    def _watchlist_changed(self) -> None:
        for panel in self.query(widgets.WatchlistPanel):
            panel.set_symbols(self.watchlist)
        self.refresh_bindings()
        if self._watchlist_path is None:
            return
        try:
            watchlist.save(self.watchlist, self._watchlist_path)
        except OSError as exc:  # the list stays for this session
            log.warning("watchlist not saved: %s: %s", type(exc).__name__, exc)
            self._set_notice(f"Watchlist not saved: {type(exc).__name__}")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self.refresh_bindings()

    def _set_year(self, full: bool) -> None:
        for panel in self.query(widgets.ChartPanel):
            if panel.full != full:
                panel.toggle_year()
        self.refresh_bindings()

    def action_show_year(self) -> None:
        self._set_year(True)

    def action_fit_width(self) -> None:
        self._set_year(False)

    @property
    def refreshing(self) -> bool:
        """A download is in flight (r is ignored until it finishes)."""
        return self._refreshing

    async def _show(self, snap: dict) -> None:
        self._refreshing = False
        self.snapshot = snap
        if len(self.screen_stack) > 1:  # another screen is on top: redraw when the main one is back
            self._ui_stale = True
            return
        await self._recompose_tabs()

    def _failed(self, label: str) -> None:
        self._refreshing = False
        self._set_notice(f"Refresh failed: {label}")

    def _set_notice(self, notice: str | None) -> None:
        self.snapshot = {**self.snapshot, "notice": notice}
        self.screen_stack[0].query_one("#masthead", Static).update(masthead(self.snapshot))

    def action_refresh_data(self) -> None:
        if self._refresh_fn is None:
            self._set_notice(self._refresh_off_notice)
            return
        if self._refreshing:  # one download at a time: no second writer, no stale delivery
            return
        self._refreshing = True
        self._set_notice("Updating…")
        # A daemon thread, not a Textual thread worker: those run in asyncio's default executor,
        # whose non-daemon threads are joined on exit, so q would wait for an in-flight download.
        threading.Thread(target=self._refresh_thread, name="mt-refresh", daemon=True).start()

    def _refresh_thread(self) -> None:
        try:
            snap = self._refresh_fn()
        except Exception as exc:  # any failure keeps the current data on screen
            log.warning("refresh failed: %s: %s", type(exc).__name__, exc)
            self._deliver(self._failed, error_label(exc))
            return
        self._deliver(self._show, snap)

    def _deliver(self, callback, *args) -> None:
        if not self.is_running:  # the app has already closed: drop the result
            log.info("refresh finished after quit; result dropped")
            return
        try:
            self.call_from_thread(callback, *args)
        except RuntimeError:  # closed between the check and the call
            log.info("refresh finished after quit; result dropped")
