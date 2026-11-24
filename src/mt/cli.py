"""Command line: `mt` opens the terminal app; `mt report <topic>` builds a topic's README charts."""

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

OUT = Path("out")
CONFIG_DIR = Path.home() / ".config" / "market-terminal"
log = logging.getLogger("mt.cli")
DEMO_MAX_BYTES = 5 * 1024 * 1024
HISTORY = pd.DateOffset(years=3, days=10)  # the screens need at most ~3 years of bars


def _since() -> pd.Timestamp:
    return now_ist().tz_localize(None).normalize() - HISTORY


def now_ist() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Kolkata")


def snapshot_from(table: pd.DataFrame, no_data: list[str] = ()) -> dict:
    from mt import (  # noqa: F401 - importing registers their sections
        breadth,
        candles,
        overview,
        sectors,
        snapshot,
        stock,
    )

    table = table.loc[table.index.max() - HISTORY :]
    return snapshot.build(table, now_ist(), no_data)


def _download() -> dict:
    from mt.data import update_cache

    table = update_cache(since=_since())
    return snapshot_from(table, table.attrs.get("no_yahoo_data", []))


def refresh() -> dict:
    """Download the missing days and rebuild the snapshot (raises on failure). Runs in the app's
    update thread, so the once-a-day NIFTY 50 membership check goes here, not on the UI thread."""
    from mt import membership
    from mt.data import SYMBOLS

    snap = _download()
    try:
        snap["notice"] = membership.check(set(SYMBOLS), membership.fetch_nse, membership.STAMP)
    except Exception as exc:  # a banner problem must never lose the downloaded data
        log.warning("membership check failed: %s: %s", type(exc).__name__, exc)
    return snap


def setup_logging(config_dir: Path = CONFIG_DIR) -> Path:
    """Send the package's log to a private file (never to the screen while the app runs)."""
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_dir.chmod(0o700)
    path = config_dir / "mt.log"
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("mt")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return path


def run_app() -> int:
    """Open on the cache at once and update it inside the app; with no cache, download first."""
    from mt import watchlist
    from mt.app import TerminalApp
    from mt.data import DATA_PATH, error_label, load_cache, remove_stale_temp_files

    file = watchlist.WATCHLIST  # read now, so a test can point it elsewhere

    try:
        remove_stale_temp_files(DATA_PATH.parent)
    except OSError as exc:
        log.warning("stale temp files not removed: %s: %s", type(exc).__name__, exc)
    since = _since()
    try:
        table = load_cache(since=since)
    except Exception as exc:  # unreadable cache: treat as none, the download rewrites it
        log.warning("cache unreadable: %s: %s", type(exc).__name__, exc)
        table = None
    snap = None
    if table is not None and not table.empty:
        try:
            snap = snapshot_from(table)
        except Exception as exc:  # unusable cache (wrong shape, no valid session): as if none
            log.warning("cache unusable: %s: %s", type(exc).__name__, exc)
    if snap is None:
        print("Downloading price history (first run, about 20 s)\u2026", file=sys.stderr)
        try:
            snap = _download()
        except Exception as exc:
            log.warning("first download failed: %s: %s", type(exc).__name__, exc)
            print(
                f"No price data yet and the download failed: {error_label(exc)}. "
                "Check the connection and run `uv run mt` again.",
                file=sys.stderr,
            )
            return 1
        app = TerminalApp(snap, refresh, watchlist_path=file)
    else:
        app = TerminalApp(snap, refresh, update_on_mount=True, watchlist_path=file)
    app.run()
    return app.return_code or 0


def run_demo(path: str) -> int:
    """Open the app on a snapshot JSON file: no network, no cache, no refresh."""
    from mt.app import TerminalApp
    from mt.snapshot import strip_controls

    try:
        if Path(path).stat().st_size > DEMO_MAX_BYTES:
            raise ValueError("file too large (over 5 MB)")
        # untrusted file: no control characters (terminal escape sequences) reach the screen
        snap = strip_controls(json.loads(Path(path).read_text(encoding="utf-8")))
        if not isinstance(snap, dict) or "as_of" not in snap:
            raise ValueError('not a snapshot (expected an object with "as_of")')
    except (OSError, ValueError, RecursionError) as exc:  # unreadable, bad or too nested
        print(f"Cannot open demo file {path}: {exc}", file=sys.stderr)
        return 1
    app = TerminalApp(snap, None, refresh_off_notice="Demo data \u2014 refresh off")
    app.run()
    return app.return_code or 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mt", description="After-close NSE market terminal")
    sub = parser.add_subparsers(dest="cmd")
    rep = sub.add_parser("report", help="build a topic's charts and print its numbers")
    rep.add_argument("topic")
    parser.add_argument("--demo", metavar="PATH", help="open the app on a snapshot JSON file")
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo(args.demo)
    if args.cmd is None:
        setup_logging()
        return run_app()

    from mt import plots, reports

    if args.topic not in reports.REPORTS:
        parser.error(f"unknown topic {args.topic!r}; topics: {', '.join(reports.REPORTS)}")
    plots.style()
    for key, value in reports.REPORTS[args.topic](OUT).items():
        print(f"{key}: {value}")
    print(f"charts -> {OUT.resolve()}")
    return 0
