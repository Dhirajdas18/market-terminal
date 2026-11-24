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

YEAR = 250  # sessions in the snapshot: about one year
MIN_SHOWN = 60
AXIS_COLUMNS = 10  # panel columns taken by the y-axis labels and the frame


def window_size(width: int, available: int, full: bool) -> int:
    """Sessions to draw: all of them up to a year when `full`, else one candle per plot column
    (never fewer than 60, never more than a year or than exist)."""
    if full:
        return min(YEAR, available)
    return min(available, YEAR, max(MIN_SHOWN, width - AXIS_COLUMNS))


def span_label(n: int, available: int, full: bool) -> str:
    """Chart title span: say "1 year" only when a full year of sessions is shown."""
    if not full:
        return f"last {n} sessions"
    return "1 year" if n >= YEAR else f"all {n} sessions"


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


def draw_candles(plot: TokenPlot, idx: dict, n: int, span: str) -> None:
    """NIFTY candles with the 20- and 50-day averages for the last `n` sessions."""
    plt = plot.plt
    plt.clear_figure()
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
    plt.title(f"NIFTY 50 · {span}, with 20- and 50-day average")
    plot.refresh()


def draw_value(plot: TokenPlot, idx: dict, n: int) -> None:
    """Traded value of the 50 stocks, bars under the candles (its own axis: no second y-axis)."""
    plt = plot.plt
    plt.clear_figure()
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
    plot.refresh()


class ChartPanel(Vertical):
    """Builds its two plots the first time the tab is shown, not at startup. The span is as many
    sessions as fit the width (redrawn on resize); `y` toggles the whole year."""

    def __init__(self, idx: dict):
        super().__init__(id="chart")
        self._idx = idx
        self._built = False
        self.full = False
        self.shown = 0
        self._drawn_full = False

    def on_show(self, event: events.Show) -> None:
        if not self._built:
            self._built = True
            self._candles = TokenPlot(id="candles")
            self._value = TokenPlot(id="traded-value")
            self.mount(self._candles, self._value)
            self.redraw()

    def on_resize(self, event: events.Resize) -> None:
        if self._built:
            self.redraw()

    def toggle_year(self) -> None:
        self.full = not self.full
        if self._built:
            self.redraw()

    def redraw(self) -> None:
        n = window_size(self.size.width, len(self._idx["dates"]), self.full)
        if n == self.shown and self._drawn_full == self.full:
            return
        self.shown, self._drawn_full = n, self.full
        draw_candles(self._candles, self._idx, n, span_label(n, len(self._idx["dates"]), self.full))
        draw_value(self._value, self._idx, n)


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


def _count(value: int | None, of: int | None) -> str:
    """'30 of 47', or an em dash for a missing count."""
    return "—" if value is None or of is None else f"{value} of {of}"


def breadth_text(b: dict) -> Text:
    """The breadth counts as plain Text, each with the number of stocks it could be computed for."""
    above = b.get("above50") or {}
    of = above.get("of")
    share = "" if not of or above.get("count") is None else f" ({above['count'] / of:.0%})"
    text = Text(f"{_count(above.get('count'), of)} above 50-day average{share}", style="bold")
    day = [b.get(k) for k in ("up", "down", "flat")]
    shown = "—" if None in day else sum(day)
    text.append(
        f"\n{_c(b.get('up'))} up, {_c(b.get('down'))} down, {_c(b.get('flat'))} unchanged"
        f" (of {shown} stocks with a bar today)"
    )
    of52 = b.get("of52")
    text.append(
        f"\n{_count(b.get('highs'), of52)} at a 250-day high, "
        f"{_count(b.get('lows'), of52)} at a 250-day low",
    )
    text.append(
        "\nA stock is counted only with enough history (50 closes for the average, 250 for the "
        "high and low) and a bar today.",
        style=MUTED,
    )
    return text


def _c(value: int | None) -> str:
    return "—" if value is None else str(value)


def draw_spark(plot: TokenPlot, spark: dict) -> None:
    """The share of stocks above their 50-day average, one point per session (0 to 100%)."""
    plt = plot.plt
    plt.clear_figure()
    dates = spark["dates"]
    pts = [(i, v * 100) for i, v in enumerate(spark["pct"]) if v is not None]
    if pts:
        plt.plot(*zip(*pts, strict=True), color=_rgb(ACCENT), marker="braille")
    plt.plot([0, max(len(dates) - 1, 1)], [50, 50], color=_rgb(MUTED), marker="braille")
    plt.ylim(0, 100)
    plt.yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    pos = tick_positions(len(dates))
    plt.xticks(pos, [_short(dates[i]) for i in pos])
    plt.grid(False, False)
    plt.title(f"% of stocks above 50-day average · {len(dates)} sessions, line at 50%")
    plot.refresh()


class BreadthPanel(Vertical):
    """The counts at once; the sparkline is built the first time the tab is shown."""

    def __init__(self, b: dict):
        super().__init__(id="breadth")
        self._b = b
        self._built = False

    def compose(self):
        yield Static(breadth_text(self._b), id="breadth-counts")

    def on_show(self, event: events.Show) -> None:
        if not self._built and (self._b.get("spark") or {}).get("dates"):
            self._built = True
            self._spark = TokenPlot(id="breadth-spark")
            self.mount(self._spark)
            draw_spark(self._spark, self._b["spark"])


def breadth_tab(snap: dict) -> Widget:
    b = snap.get("breadth") or {}
    if not b:
        return Static("No breadth data.", classes="empty")
    return BreadthPanel(b)


TABS.append(("Breadth", breadth_tab))


HEAT_FULL = 0.02  # a sector move of this size or more gets the full colour
BAR_CELLS = 12


def heat_colour(ret: float | None) -> str:
    """Cell background for a sector return: the grid grey at 0, blending to the chart green (up)
    or red (down) at ±HEAT_FULL and beyond. A missing value is grey."""
    base = _rgb(GRID)
    if ret is None or ret == 0:
        return GRID
    target = _rgb(UP if ret > 0 else DOWN)
    t = min(abs(ret) / HEAT_FULL, 1.0)
    return "#" + "".join(f"{round(b + (g - b) * t):02x}" for b, g in zip(base, target, strict=True))


def pts(value: float | None, digits: int = 0) -> str:
    """'+84' or '−52.3' index points with a true minus sign; an em dash when missing."""
    return "—" if value is None else f"{value:+.{digits}f}".replace("-", "−")


def summary_text(c: dict) -> Text:
    """'Sum of estimates: +84 pts · NIFTY moved: +91 pts', plus how the estimate is made."""
    est, actual = c.get("sum_points"), c.get("actual_points")
    text = Text(
        f"Sum of estimates: {pts(est)}{'' if est is None else ' pts'} · "
        f"NIFTY moved: {pts(actual)}{'' if actual is None else ' pts'}",
        style="bold",
    )
    text.append(
        "\nWeights are estimated from the previous 60 sessions (NIFTY's daily weights are not "
        "public), so the sum differs from the real move.",
        style=MUTED,
    )
    return text


def heat_table(rows: list[dict]) -> DataTable:
    table = DataTable(cursor_type="none", zebra_stripes=False, id="sector-heat")
    table.add_column("Sector")
    table.add_column("Day", width=9)
    table.add_column("Stocks", width=6)
    for r in rows:
        ret = r.get("ret")
        cell = Text(pct(ret), style=f"{TEXT} on {heat_colour(ret)}", justify="center")
        table.add_row(Text(str(r["name"])), cell, Text(str(r.get("n", "—")), justify="right"))
    return table


def contribution_table(c: dict) -> DataTable:
    table = DataTable(cursor_type="none", zebra_stripes=False, id="contributions")
    table.add_columns("Stock", "Points", "Weight", "")
    top = c.get("top") or []
    biggest = max((abs(r["points"]) for r in top if r.get("points") is not None), default=0)
    for r in top:
        p, w = r.get("points"), r.get("weight")
        cells = round(abs(p) / biggest * BAR_CELLS) if p is not None and biggest else 0
        bar = Text("█" * cells, style=UP if (p or 0) > 0 else DOWN)
        weight = "—" if w is None else f"{w * 100:.1f}%"
        table.add_row(
            _symbol(r["symbol"]),
            Text(pts(p, 1), justify="right"),
            Text(weight, justify="right"),
            bar,
        )
    for sym in c.get("not_estimated") or []:
        table.add_row(_symbol(sym), Text("weight not estimated yet", style=MUTED), "", "")
    return table


def sectors_tab(snap: dict) -> Widget:
    rows, c = snap.get("sectors") or [], snap.get("contributions") or {}
    if not rows and not c:
        return Static("No sector data.", classes="empty")
    parts: list[Widget] = []
    if c:
        parts.append(Static(summary_text(c), id="sectors-summary"))
    boxes: list[Widget] = []
    if rows:
        boxes.append(
            Vertical(
                Static("Sectors: average day return of their stocks", classes="subtitle"),
                heat_table(rows),
                classes="sector-box",
            )
        )
    if c:
        boxes.append(
            Vertical(
                Static("Who moved NIFTY (index points, top 10)", classes="subtitle"),
                contribution_table(c),
                classes="sector-box",
            )
        )
    parts.append(Horizontal(*boxes, id="sector-boxes"))
    return Vertical(*parts, id="sectors")


TABS.append(("Sectors", sectors_tab))
