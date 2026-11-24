"""The snapshot: one plain dict that every screen reads (schema in docs/snapshot.md).

`build` picks the session date, trims the table to it (so nothing sees later data) and runs each
section in SECTIONS. A later live mode would replace only this producer.
"""

import math
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


def build(table: pd.DataFrame, now_ist: pd.Timestamp) -> dict:
    as_of, missing, suspended = session_info(table["close"], now_ist)
    trimmed = trim(table, as_of)
    snap: dict[str, Any] = {
        "as_of": f"{as_of:%Y-%m-%d}",
        "as_of_label": label(as_of),
        "stale": bool(as_of.normalize() < _naive_ist(now_ist).normalize()),
        "missing": missing,
        "suspended": [{"symbol": sym, "last": f"{day:%Y-%m-%d}"} for sym, day in suspended],
        "notice": None,
    }
    for key, fn in SECTIONS:
        snap[key] = fn(trimmed)
    return clean(snap)


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
