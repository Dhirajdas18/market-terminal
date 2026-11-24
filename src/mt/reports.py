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
    """(one-day >20% drops, how many the fixes file covers, the uncovered (symbol, date)).

    A drop is covered by a row on its own date, or by a `start` row dated after it (those prices
    are not this company and are dropped)."""
    hits = flag_adjusted_drops(adj.drop(columns=[VOL_INDEX], errors="ignore"))
    table = pd.read_csv(fixes, parse_dates=["date"])
    known = set(zip(table["symbol"], table["date"], strict=True))
    starts = table[table["action"] == "start"].groupby("symbol")["date"].max()
    unlisted = [
        (s, d) for s, d in hits if (s, d) not in known and not (s in starts and d < starts[s])
    ]
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
        "covered by yahoo_fixes.csv": listed,
        "not covered": [f"{s} {d:%Y-%m-%d}" for s, d in unlisted],
        "busiest uncovered day": f"{by_day.index[0]:%Y-%m-%d} ({by_day.iloc[0]} stocks)"
        if len(by_day)
        else None,
    }


def aligned_returns(nifty: pd.Series, sp500: pd.Series) -> pd.DataFrame:
    """Per NSE session: `nifty` day return, `same` = S&P 500 return on the same calendar date
    (NaN when the US was shut), `prev` = S&P return of the last US session strictly before it.

    `nifty` is indexed by NSE sessions (NaN where its own bar is missing, so a gap never merges
    two days into one return). S&P returns are each vs its own previous bar."""
    nifty_ret = nifty.pct_change(fill_method=None)
    sp_ret = sp500.dropna().pct_change(fill_method=None).dropna()
    same = sp_ret.reindex(nifty.index)
    at = sp_ret.index.searchsorted(nifty.index, side="left") - 1  # last US date before the NSE date
    prev = pd.Series(
        np.where(at >= 0, sp_ret.to_numpy()[np.clip(at, 0, None)], np.nan), index=nifty.index
    )
    return pd.DataFrame({"nifty": nifty_ret, "same": same, "prev": prev})


def corr_t(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    """(correlation, t-statistic r*sqrt((n-2)/(1-r^2)), n) over the days both have a value."""
    pair = pd.concat([x, y], axis=1).dropna()
    n = len(pair)
    r = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    return r, r * float(np.sqrt((n - 2) / (1 - r * r))), n


def report_overview(out_dir: Path, first_year: int = 2010) -> dict:
    """Does NIFTY's day return line up better with the previous US session or with the S&P 500
    return dated the same day? Both on the same NSE sessions, 2010 on."""
    table = _table()
    close = table["close"]
    nse = close.drop(columns=list(OFF_CALENDAR.values()), errors="ignore")
    sessions = nse.dropna(how="all").index
    nifty = close["NIFTY"].reindex(sessions)
    data = aligned_returns(nifty, close["SP500"])
    data = data.loc[f"{first_year}-01-01":].dropna()  # one common sample for both comparisons
    r_same, t_same, n_same = corr_t(data["nifty"], data["same"])
    r_prev, t_prev, n_prev = corr_t(data["nifty"], data["prev"])

    years = sorted(set(data.index.year))
    by_year = pd.DataFrame(
        {
            "same": [corr_t(g["nifty"], g["same"])[0] for _, g in data.groupby(data.index.year)],
            "prev": [corr_t(g["nifty"], g["prev"])[0] for _, g in data.groupby(data.index.year)],
        },
        index=years,
    )
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(years))
    ax.bar(x - 0.2, by_year["prev"], 0.4, color=plots.SERIES[0], label="previous US session")
    ax.bar(x + 0.2, by_year["same"], 0.4, color=plots.SERIES[1], label="S&P 500 on the same date")
    ax.set_xticks(x, [str(y) for y in years], fontsize=8)
    ax.set_ylabel("correlation with NIFTY's day return")
    ax.axhline(0, color=plots.TEXT_2, linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=8, ncols=2)
    ax.set_title(
        f"NIFTY day return vs S&P 500, {years[0]}–{years[-1]}\n"
        f"correlation {r_prev:.3f} with the previous US session, {r_same:.3f} with the same date"
    )
    plots.save(fig, out_dir, "overview_sp500")
    return {
        "NSE sessions from": f"{first_year} (n = {n_same} with both)",
        "corr, previous US session": round(r_prev, 3),
        "t-stat, previous US session": round(t_prev, 1),
        "corr, same date": round(r_same, 3),
        "t-stat, same date": round(t_same, 1),
        "years where previous > same": f"{int((by_year['prev'] > by_year['same']).sum())} of "
        f"{len(years)}",
        "by year (prev, same)": {
            int(y): (round(float(r.prev), 2), round(float(r.same), 2))
            for y, r in by_year.iterrows()
        },
    }


REPORTS = {"data": report_data, "overview": report_overview}
