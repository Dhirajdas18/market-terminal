"""Screen panels. Each topic appends (tab title, fn(snapshot) -> Widget) to TABS."""

from collections.abc import Callable

import pandas as pd
from rich.text import Text
from textual import events
from textual.containers import Grid, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static
from textual_plotext import PlotextPlot

TABS: list[tuple[str, Callable[[dict], Widget]]] = []

UP = "#199e70"  # the dark-mode green and red of mt.plots, so the app matches the charts
DOWN = "#e66767"
MUTED = "#c3c2b7"
ACCENT = "#3987e5"
AMBER = "#c98500"
SURFACE = "#1a1a19"
RAISED = "#242422"
GRID = "#2e2d2b"
TEXT = "#f0efec"
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

SHOWN_SESSIONS = 120  # candles drawn: about five months, one or two to a terminal column


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


class TokenPlot(PlotextPlot):
    """A plotext plot painted with the app's colour tokens instead of the Textual theme's."""

    def render(self):
        self.plt.plotsize(self.size.width, self.size.height)
        self.plt._set_size(self.size.width, self.size.height)  # as PlotextPlot.render does
        self.plt.canvas_color(_rgb(SURFACE))
        self.plt.axes_color(_rgb(SURFACE))
        self.plt.ticks_color(_rgb(MUTED))
        return Text.from_ansi(self.plt.build())


def tick_positions(count: int, wanted: int = 6) -> list[int]:
    """Evenly spread indexes (always including the last) at which to print a date label."""
    if count <= 1:
        return list(range(count))
    step = max(1, (count - 1) // (wanted - 1))
    return sorted(set(range(count - 1, -1, -step)))


def y_ticks(lo: float, hi: float, count: int = 5) -> tuple[list[float], list[str]]:
    """Round y-axis positions and their labels ('24,500'), instead of plotext's long decimals."""
    step = (hi - lo) / (count - 1)
    pos = [lo + step * i for i in range(count)]
    return pos, [f"{v:,.0f}" for v in pos]


def _tail(values: list, n: int) -> list:
    return values[-n:]


def _short(date: str) -> str:
    day = pd.Timestamp(date)
    return f"{day.day} {day:%b %y}"


def candle_plot(idx: dict, n: int = SHOWN_SESSIONS) -> TokenPlot:
    """NIFTY candles with the 20- and 50-day averages."""
    plot = TokenPlot(id="candles")
    plt = plot.plt
    dates = _tail(idx["dates"], n)
    x = list(range(len(dates)))
    data = {
        "Open": _tail(idx["open"], n),
        "High": _tail(idx["high"], n),
        "Low": _tail(idx["low"], n),
        "Close": _tail(idx["close"], n),
    }
    plt.candlestick(x, data, colors=[_rgb(UP), _rgb(DOWN)])
    for key, colour in (("ma20", ACCENT), ("ma50", AMBER)):
        ma = _tail(idx[key], n)
        pts = [(i, v) for i, v in zip(x, ma, strict=True) if v is not None]
        if pts:
            plt.plot(
                *zip(*pts, strict=True),
                color=_rgb(colour),
                marker="braille",
                label=key.replace("ma", "MA"),
            )
    pos = tick_positions(len(dates))
    plt.xticks(pos, [_short(dates[i]) for i in pos])
    plt.yticks(*y_ticks(min(data["Low"]), max(data["High"])))
    plt.grid(False, False)
    plt.title("NIFTY 50 daily candles, 20- and 50-day average")
    return plot


def value_plot(idx: dict, n: int = SHOWN_SESSIONS) -> TokenPlot:
    """Traded value of the 50 stocks, bars under the candles (its own axis: no second y-axis)."""
    plot = TokenPlot(id="traded-value")
    plt = plot.plt
    dates = _tail(idx["dates"], n)
    value = _tail(idx["value_cr"], n)
    pts = [(i, v) for i, v in enumerate(value) if v is not None]
    if pts:
        xs, ys = zip(*pts, strict=True)
        plt.bar(xs, ys, color=_rgb(MUTED), width=0.7)
        plt.yticks(*y_ticks(0, max(ys), 3))
    plt.grid(False, False)
    pos = tick_positions(len(dates))
    plt.xticks(pos, [_short(dates[i]) for i in pos])
    plt.title("Traded value of NIFTY 50 stocks (₹ cr)")
    return plot


class ChartPanel(Vertical):
    """Builds its two plots the first time the tab is shown, not at startup."""

    def __init__(self, idx: dict):
        super().__init__(id="chart")
        self._idx = idx
        self._built = False

    def on_show(self, event: events.Show) -> None:
        if not self._built:
            self._built = True
            self.mount(candle_plot(self._idx), value_plot(self._idx))


def chart_tab(snap: dict) -> Widget:
    idx = snap.get("index") or {}
    if not idx.get("dates"):
        return Static("No NIFTY candles.", classes="empty")
    return ChartPanel(idx)


def _mover_table(title: str, columns: list[str], rows: list[list[Text]], ident: str) -> Vertical:
    table = DataTable(cursor_type="none", zebra_stripes=False, id=ident)
    table.add_columns(*columns)
    for row in rows:
        table.add_row(*row)
    parts: list[Widget] = [Static(title, classes="subtitle"), table]
    if not rows:
        parts.append(Static("None.", classes="empty"))
    return Vertical(*parts, classes="movers-box")


def _symbol(sym: str) -> Text:
    return Text(str(sym))


def _times(ratio: float | None) -> Text:
    return Text("—" if ratio is None else f"{ratio:.1f}×", justify="right")


def movers_tab(snap: dict) -> Widget:
    mv = snap.get("movers") or {}
    if not mv:
        return Static("No movers data.", classes="empty")

    def moves(rows):
        return [[_symbol(r["symbol"]), _signed(r["ret"])] for r in rows]

    unusual = [
        [_symbol(r["symbol"]), _times(r["ratio"]), _signed(r.get("ret"))]
        for r in mv.get("unusual", [])
    ]
    return Horizontal(
        _mover_table("Top gainers", ["Stock", "Day"], moves(mv.get("gainers", [])), "gainers"),
        _mover_table("Top losers", ["Stock", "Day"], moves(mv.get("losers", [])), "losers"),
        _mover_table(
            "Unusual volume (today ÷ mean of the previous 20 days)",
            ["Stock", "Volume", "Day"],
            unusual,
            "unusual",
        ),
        id="movers",
    )


TABS.append(("Chart", chart_tab))
TABS.append(("Movers", movers_tab))
