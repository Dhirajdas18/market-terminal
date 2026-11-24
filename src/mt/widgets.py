"""Screen panels. Each topic appends (tab title, fn(snapshot) -> Widget) to TABS."""

from collections.abc import Callable

from textual.widget import Widget

TABS: list[tuple[str, Callable[[dict], Widget]]] = []
