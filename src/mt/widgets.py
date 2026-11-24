"""Screen panels. Each topic appends (tab title, fn(snapshot) -> Widget) to TABS."""

from collections.abc import Callable

import pandas as pd
from rich.text import Text
from textual.containers import Grid
from textual.widget import Widget
from textual.widgets import Static

TABS: list[tuple[str, Callable[[dict], Widget]]] = []

UP = "#199e70"  # the dark-mode green and red of mt.plots, so the app matches the charts
DOWN = "#e66767"
MUTED = "#c3c2b7"
LABELS = {
    "NIFTY": "NIFTY 50",
    "NIFTYBANK": "NIFTY Bank",
    "INDIAVIX": "India VIX",
    "USDINR": "USD/INR",
    "GOLDBEES": "Gold (GOLDBEES)",
    "SP500": "S&P 500",
}
BAR_WIDTH = 16


def num(value: float | None, digits: int = 2) -> str:
    """'24,500.00', or an em dash for a missing value."""
    return "—" if value is None else f"{value:,.{digits}f}"


def pct(value: float | None) -> str:
    """'+0.62%' with a true minus sign, or an em dash."""
    return "—" if value is None else f"{value * 100:+.2f}%".replace("-", "−")


def _signed(value: float | None, coloured: bool = True) -> Text:
    """A signed change; green/red only for prices (a VIX rise is not good news: muted)."""
    colour = MUTED if not coloured or value is None or value == 0 else (UP if value > 0 else DOWN)
    return Text(pct(value), style=colour)


def range_bar(pos: float | None) -> str:
    """A fixed-width line with a dot where the last close sits between the 52-week low and high."""
    if pos is None:
        return "─" * BAR_WIDTH
    at = round(min(max(pos, 0.0), 1.0) * (BAR_WIDTH - 1))
    return "─" * at + "●" + "─" * (BAR_WIDTH - 1 - at)


def tile_text(row: dict, as_of: str) -> Text:
    """One overview tile as plain Text (names and dates are data, never markup)."""
    name = str(row.get("name"))
    tint = name != "INDIAVIX"
    text = Text(LABELS.get(name, name), style="bold")
    text.append("\n" + num(row.get("close")))
    text.append("  ")
    text.append_text(_signed(row.get("day"), tint))
    text.append("\nweek ", style=MUTED)
    text.append_text(_signed(row.get("week"), tint))
    text.append("  YTD ", style=MUTED)
    text.append_text(_signed(row.get("ytd"), tint))
    text.append(f"\n{num(row.get('low52'))} {range_bar(row.get('pos52'))} {num(row.get('high52'))}",
                style=MUTED)
    if row.get("date") and row["date"] != as_of:
        day = pd.Timestamp(str(row["date"]))
        text.append(f"\nas of {day:%a} {day.day} {day:%b}", style=MUTED)
    return text


def overview_tab(snap: dict) -> Widget:
    rows = snap.get("overview") or []
    if not rows:
        return Static("No overview data.", classes="empty")
    return Grid(
        *(Static(tile_text(r, snap["as_of"]), classes="tile") for r in rows), id="overview"
    )


TABS.append(("Overview", overview_tab))
