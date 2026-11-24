"""README findings, one function per topic: `mt report <topic>` writes charts to out/."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mt import plots
from mt.data import FIXES, NSE_TICKERS, OFF_CALENDAR, flag_adjusted_drops, load_cache

VOL_INDEX = "INDIAVIX"  # a volatility index halves for real; not a bad-print candidate


def _table() -> pd.DataFrame:
    table = load_cache()
    if table is None:
        raise SystemExit("no cached prices yet: run `uv run mt` once to download them")
    return table


def weekday_gaps(close: pd.DataFrame, first: int, last: int) -> pd.DataFrame:
    """Per year, weekdays with no NIFTY bar, split into `holiday` (no NSE series has a bar) and
    `index_gap` (some NSE series traded, NIFTY's bar is missing)."""
    nse = close.drop(columns=list(OFF_CALENDAR.values()), errors="ignore")
    traded = nse.dropna(how="all").index
    nifty = nse["NIFTY"].dropna().index
    rows = {}
    for year in range(first, last + 1):
        weekdays = pd.bdate_range(f"{year}-01-01", f"{year}-12-31")
        no_nifty = weekdays.difference(nifty)
        gap = no_nifty.intersection(traded)
        rows[year] = {"holiday": len(no_nifty) - len(gap), "index_gap": len(gap)}
    return pd.DataFrame.from_dict(rows, orient="index")


def unexplained_drops(
    adj: pd.DataFrame, fixes: Path = FIXES
) -> tuple[int, int, list[tuple[str, pd.Timestamp]]]:
    """(one-day >20% drops, how many are listed in the fixes file, the unlisted (symbol, date))."""
    hits = flag_adjusted_drops(adj.drop(columns=[VOL_INDEX], errors="ignore"))
    table = pd.read_csv(fixes, parse_dates=["date"])
    known = set(zip(table["symbol"], table["date"], strict=True))
    unlisted = [h for h in hits if h not in known]
    return len(hits), len(hits) - len(unlisted), unlisted


def report_data(out_dir: Path) -> dict:
    """How complete Yahoo's end-of-day NSE data is: weekdays per year with no NIFTY bar, and the
    one-day crashes the bad-print scan flags."""
    table = _table()
    close = table["close"]
    last_full = close["NIFTY"].dropna().index.max().year - 1
    gaps = weekday_gaps(close, 2008, last_full)

    fig, ax = plt.subplots(figsize=(10, 4.6))
    years = gaps.index.to_numpy()
    ax.bar(years, gaps["holiday"], color=plots.SERIES[0], label="no NSE bar at all (holiday)")
    ax.bar(
        years,
        gaps["index_gap"],
        bottom=gaps["holiday"],
        color=plots.SERIES[1],
        label="stocks traded, NIFTY bar missing",
    )
    ax.set_xticks(years, [f"{y}" for y in years], fontsize=8)
    ax.set_ylabel("weekdays")
    ax.set_ylim(0, 26)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=8, ncols=2)
    total_gap = int(gaps["index_gap"].sum())
    ax.set_title(
        f"Weekdays with no NIFTY bar on Yahoo, 2008–{last_full}\n"
        f"{gaps['holiday'].min()} to {gaps['holiday'].max()} holidays a year, plus {total_gap} "
        "trading days with no index bar"
    )
    plots.save(fig, out_dir, "data_gaps")

    nse = list(NSE_TICKERS.values())
    hits, listed, unlisted = unexplained_drops(table["adj_close"][nse])
    by_day = pd.Series([d for _, d in unlisted]).value_counts()
    return {
        "holidays a year (min, median, max)": (
            int(gaps["holiday"].min()),
            float(np.median(gaps["holiday"])),
            int(gaps["holiday"].max()),
        ),
        "weekdays stocks traded but NIFTY has no bar": total_gap,
        "years with such gaps": [int(y) for y in gaps.index[gaps["index_gap"] > 0]],
        "one-day drops > 20% (excl. India VIX)": hits,
        "listed in yahoo_fixes.csv": listed,
        "not listed": [f"{s} {d:%Y-%m-%d}" for s, d in unlisted],
        "busiest unlisted day": f"{by_day.index[0]:%Y-%m-%d} ({by_day.iloc[0]} stocks)"
        if len(by_day)
        else None,
    }


REPORTS = {"data": report_data}
