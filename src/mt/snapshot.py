"""The snapshot: one plain dict that every screen reads (schema in docs/snapshot.md).

`build` picks the session date, trims the table to it (so nothing sees later data) and runs each
section in SECTIONS. A later live mode would replace only this producer.
"""

import math
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from mt.session import _naive_ist, session_info, trim

# (key, fn(table trimmed to the session date) -> JSON-able value); each topic appends its section.
SECTIONS: list[tuple[str, Callable[[pd.DataFrame], Any]]] = []


def label(day: pd.Timestamp) -> str:
    """'Data for Mon 23 Nov 2026'."""
    return f"Data for {day:%a} {day.day} {day:%b %Y}"


def build(table: pd.DataFrame, now_ist: pd.Timestamp, no_data: list[str] = ()) -> dict:
    """`no_data`: constituents the last update had no Yahoo data for (their cached bars stay)."""
    as_of, missing, suspended = session_info(table["close"], now_ist, ignore=list(no_data))
    trimmed = trim(table, as_of)
    snap: dict[str, Any] = {
        "as_of": f"{as_of:%Y-%m-%d}",
        "as_of_label": label(as_of),
        "stale": bool(as_of.normalize() < _naive_ist(now_ist).normalize()),
        "missing": missing,
        "suspended": [{"symbol": sym, "last": f"{day:%Y-%m-%d}"} for sym, day in suspended],
        "no_data": sorted(no_data),
        "notice": None,
    }
    for key, fn in SECTIONS:
        snap[key] = fn(trimmed)
    return clean(snap)


# C0 and C1 control characters except \n: ESC alone can start an OSC/CSI sequence (clipboard
# writes, window titles, cursor moves) that Rich and Textual pass through to the terminal.
_CONTROL = re.compile("[\x00-\x09\x0b-\x1f\x7f-\x9f]")


def strip_controls(obj: Any) -> Any:
    """A copy of a JSON-like value with control characters removed from every string and key."""
    if isinstance(obj, str):
        return _CONTROL.sub("", obj)
    if isinstance(obj, dict):
        return {strip_controls(k): strip_controls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_controls(v) for v in obj]
    return obj


def clean(obj: Any) -> Any:
    """A copy that survives json.dumps(..., allow_nan=False): NaN/inf -> None, numpy -> Python,
    dates -> ISO strings."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [clean(v) for v in obj.tolist()]
    if isinstance(obj, pd.Timestamp | datetime | date):
        return f"{obj:%Y-%m-%d}"
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj
