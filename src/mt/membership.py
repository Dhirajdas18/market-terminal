"""Once a day, compare docs/data/nifty50.csv with NSE's published NIFTY 50 list.

Runs in the background update thread only. The NSE file is untrusted: HTTPS, a 15 s timeout, the
read capped at 1 MB, `Symbol` and `Industry` columns required, at most 100 rows, every symbol
checked against the same pattern as the committed list. Any failure is logged and skipped.
"""

import csv
import io
import logging
import re
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
MAX_BYTES = 1024 * 1024
MAX_ROWS = 100
TIMEOUT = 15
STAMP = Path.home() / ".config" / "market-terminal" / "membership.stamp"
VALID_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")


def fetch_nse() -> set[str]:
    """NSE's current NIFTY 50 symbols (raises on any network error or malformed file)."""
    req = urllib.request.Request(URL, headers={"User-Agent": "market-terminal/0.1"})  # noqa: S310 - fixed https URL
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("NSE list larger than 1 MB")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    if not rows or not {"Symbol", "Industry"} <= set(rows[0]):
        raise ValueError("NSE list has no Symbol/Industry columns")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"NSE list has {len(rows)} rows")
    symbols = {(row["Symbol"] or "").strip() for row in rows}
    bad = [s for s in symbols if not VALID_SYMBOL.match(s)]
    if bad:
        raise ValueError("NSE list has an invalid symbol")
    return symbols


def _write_stamp(stamp: Path, day: str) -> None:
    stamp.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        "w", dir=stamp.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(day)
    try:
        tmp_path.chmod(0o600)
        tmp_path.replace(stamp)
    finally:
        tmp_path.unlink(missing_ok=True)


def check(
    committed: set[str],
    fetch: Callable[[], set[str]],
    stamp: Path = STAMP,
    today: str | None = None,
) -> str | None:
    """A banner naming added and dropped symbols, or None (same list, already checked today, or
    any error). Only a successful fetch is stamped, so a blocked one is tried again."""
    day = today or f"{pd.Timestamp.now(tz='Asia/Kolkata'):%Y-%m-%d}"
    try:
        if Path(stamp).read_text(encoding="utf-8").strip() == day:
            return None
    except OSError:
        pass
    try:
        live = fetch()
    except Exception as exc:
        log.warning("membership check skipped: %s: %s", type(exc).__name__, exc)
        return None
    try:
        _write_stamp(Path(stamp), day)
    except OSError as exc:
        log.warning("membership stamp not written: %s: %s", type(exc).__name__, exc)
    added, dropped = sorted(live - committed), sorted(committed - live)
    if not added and not dropped:
        return None
    parts = []
    if added:
        parts.append("+" + ",".join(added))
    if dropped:
        parts.append("−" + ",".join(dropped))
    return f"NIFTY 50 list changed: {' '.join(parts)}; update docs/data/nifty50.csv"
