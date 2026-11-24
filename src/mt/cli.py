"""Command line: `mt` opens the terminal app; `mt report <topic>` builds a topic's README charts."""

import argparse
import sys
from pathlib import Path

import pandas as pd

OUT = Path("out")
HISTORY = pd.DateOffset(years=3, days=10)  # the screens need at most ~3 years of bars


def now_ist() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Kolkata")


def snapshot_from(table: pd.DataFrame) -> dict:
    from mt import snapshot

    table = table.loc[table.index.max() - HISTORY :]
    return snapshot.build(table, now_ist())


def refresh() -> dict:
    """Download the missing days and rebuild the snapshot (raises on failure)."""
    from mt.data import update_cache

    return snapshot_from(update_cache())


def run_app() -> int:
    from mt.app import TerminalApp
    from mt.data import DownloadFailed, load_cache

    notice = None
    try:
        snap = refresh()
    except (DownloadFailed, OSError) as exc:
        table = load_cache(since=now_ist().tz_localize(None).normalize() - HISTORY)
        if table is None or table.empty:
            print(f"No cached prices and the download failed: {exc}", file=sys.stderr)
            return 1
        notice = f"Refresh failed: {exc}. Showing cached data."
        snap = snapshot_from(table)
    if notice:
        snap["notice"] = notice
    app = TerminalApp(snap, refresh)
    app.run()
    return app.return_code or 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mt", description="After-close NSE market terminal")
    sub = parser.add_subparsers(dest="cmd")
    rep = sub.add_parser("report", help="build a topic's charts and print its numbers")
    rep.add_argument("topic")
    args = parser.parse_args(argv)
    if args.cmd is None:
        return run_app()

    from mt import plots, reports

    if args.topic not in reports.REPORTS:
        parser.error(f"unknown topic {args.topic!r}; topics: {', '.join(reports.REPORTS)}")
    plots.style()
    for key, value in reports.REPORTS[args.topic](OUT).items():
        print(f"{key}: {value}")
    print(f"charts -> {OUT.resolve()}")
    return 0
