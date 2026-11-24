"""Command line: `mt` opens the terminal app; `mt report <topic>` builds a topic's README charts."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

OUT = Path("out")
CONFIG_DIR = Path.home() / ".config" / "market-terminal"
log = logging.getLogger("mt.cli")
HISTORY = pd.DateOffset(years=3, days=10)  # the screens need at most ~3 years of bars


def now_ist() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Kolkata")


def snapshot_from(table: pd.DataFrame) -> dict:
    from mt import overview, snapshot  # noqa: F401 - importing overview registers its section

    table = table.loc[table.index.max() - HISTORY :]
    return snapshot.build(table, now_ist())


def refresh() -> dict:
    """Download the missing days and rebuild the snapshot (raises on failure)."""
    from mt.data import update_cache

    return snapshot_from(update_cache())


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
    from mt.app import TerminalApp
    from mt.data import error_label, load_cache

    since = now_ist().tz_localize(None).normalize() - HISTORY
    try:
        table = load_cache(since=since)
    except Exception as exc:  # unreadable cache: treat as none, the download rewrites it
        log.warning("cache unreadable: %s: %s", type(exc).__name__, exc)
        table = None
    if table is None or table.empty:
        try:
            snap = refresh()
        except Exception as exc:
            log.warning("first download failed: %s: %s", type(exc).__name__, exc)
            print(
                f"No cached prices and the download failed: {error_label(exc)}. "
                "Check the connection and run `uv run mt` again.",
                file=sys.stderr,
            )
            return 1
        app = TerminalApp(snap, refresh)
    else:
        app = TerminalApp(snapshot_from(table), refresh, update_on_mount=True)
    app.run()
    return app.return_code or 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mt", description="After-close NSE market terminal")
    sub = parser.add_subparsers(dest="cmd")
    rep = sub.add_parser("report", help="build a topic's charts and print its numbers")
    rep.add_argument("topic")
    args = parser.parse_args(argv)
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
