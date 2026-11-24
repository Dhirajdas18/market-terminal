"""The Textual app: a masthead (session date, missing symbols, notice), one tab per panel, and
two keys: q quits, r refreshes in a thread worker so the screen never waits on the network."""

from collections.abc import Callable
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Static, TabbedContent, TabPane

from mt import widgets

TEXT_2 = "#c3c2b7"
WARN = "#c98500"


def masthead(snap: dict) -> Text:
    """Header line as plain Text: symbols and notices come from outside the repo, never markup."""
    text = Text(snap["as_of_label"], style="bold")
    if snap.get("stale"):
        text.append("  (last complete NSE session)", style=TEXT_2)
    if snap.get("missing"):
        text.append(f"  ·  no bar yet: {', '.join(snap['missing'])}", style=WARN)
    if snap.get("notice"):
        text.append(f"\n{snap['notice']}", style=WARN)
    return text


class TerminalApp(App):
    CSS_PATH = Path(__file__).with_name("app.tcss")  # absolute, so subclasses elsewhere work
    TITLE = "market-terminal"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_data", "Refresh"),
    ]

    def __init__(self, snapshot: dict, refresh: Callable[[], dict] | None = None):
        super().__init__()
        self.snapshot = snapshot
        self._refresh_fn = refresh

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
                with TabPane(title):
                    yield make(self.snapshot)

    async def _show(self, snap: dict) -> None:
        self.snapshot = snap
        await self.recompose()

    def _set_notice(self, notice: str | None) -> None:
        self.snapshot = {**self.snapshot, "notice": notice}
        self.query_one("#masthead", Static).update(masthead(self.snapshot))

    def action_refresh_data(self) -> None:
        if self._refresh_fn is None:
            self._set_notice("Refresh is not available here.")
            return
        self._set_notice("Refreshing…")
        self._refresh_worker()

    @work(thread=True, exclusive=True, exit_on_error=False)
    def _refresh_worker(self) -> None:
        try:
            snap = self._refresh_fn()
        except Exception as exc:  # any failure keeps the current data on screen
            self.call_from_thread(self._set_notice, f"Refresh failed: {exc}")
            return
        self.call_from_thread(self._show, snap)
