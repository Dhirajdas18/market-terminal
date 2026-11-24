"""The watchlist: a short list of NIFTY 50 symbols in ~/.config/market-terminal/watchlist.json.

The file is untrusted input: it must be a JSON list of known symbols, anything else is dropped.
Writes are atomic (a temp file in the same directory, then a rename) and private (0o700 dir,
0o600 file).
"""

import json
import re
import tempfile
from pathlib import Path

WATCHLIST = Path.home() / ".config" / "market-terminal" / "watchlist.json"
MAX_BYTES = 64 * 1024
VALID_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")


def load(path: Path = WATCHLIST, *, known: list[str]) -> list[str]:
    """The saved symbols that are in `known`, in file order without repeats; `[]` for a missing,
    unreadable, oversized or malformed file."""
    try:
        path = Path(path)
        if path.stat().st_size > MAX_BYTES:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # missing, unreadable, bad UTF-8 or bad JSON
        return []
    return validate(data, known)


def validate(data: object, known: list[str]) -> list[str]:
    """`data` as a list of known, well-formed symbols without repeats; `[]` if it is not a list."""
    if not isinstance(data, list):
        return []
    allowed = set(known)
    out: list[str] = []
    for item in data:
        valid = isinstance(item, str) and VALID_SYMBOL.match(item) and item in allowed
        if valid and item not in out:
            out.append(item)
    return out


def save(symbols: list[str], path: Path = WATCHLIST) -> None:
    """Write the list atomically with owner-only permissions."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as tmp:
        tmp_path = Path(tmp.name)
        json.dump(list(symbols), tmp)
    try:
        tmp_path.chmod(0o600)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)
