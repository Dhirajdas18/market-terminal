"""README findings, one function per topic: `mt report <topic>` writes charts to out/."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mt import breadth, candles, plots
from mt.data import (
    FIXES,
    NSE_TICKERS,
    OFF_CALENDAR,
    SYMBOLS,
    daily_returns,
    flag_adjusted_drops,
    load_cache,
)

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


def spike_reversals(
    ret: pd.DataFrame,
    index_ret: pd.Series,
    up: float = 0.15,
    back: float = 0.12,
    index_max: float = 0.02,
) -> list[tuple[str, pd.Timestamp]]:
    """(symbol, date) where a stock moved more than `up` in a day and the next day moved more than
    `back` the other way, while the index moved less than `index_max` on the first day: the shape
    of a bad print that corrects itself."""
    quiet = index_ret.abs().reindex(ret.index) < index_max
    nxt = ret.shift(-1)
    hit = (ret.abs() > up) & (nxt.abs() > back) & (np.sign(ret) != np.sign(nxt))
    hit = hit.where(quiet, False)
    return [(sym, day) for (day, sym), flag in hit.stack().items() if flag]


def cluster_ols(
    y: np.ndarray, X: np.ndarray, groups: np.ndarray
) -> tuple[np.ndarray, np.ndarray, int]:
    """OLS of y on X with standard errors clustered by `groups` (CR1 small-sample factor).

    Returns (coefficients, t-statistics, n). Rows on the same date share market-wide moves, so
    treating them as independent would overstate t."""
    n, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ y
    resid = y - X @ coef
    scores = pd.DataFrame(X * resid[:, None]).groupby(np.asarray(groups)).sum().to_numpy()
    g = len(scores)
    meat = scores.T @ scores
    cov = xtx_inv @ meat @ xtx_inv * (g / (g - 1)) * ((n - 1) / (n - k))
    return coef, coef / np.sqrt(np.diag(cov)), n


def next_day_table(ret: pd.DataFrame, volume: pd.DataFrame, top: float = 0.9) -> pd.DataFrame:
    """One row per stock-day: `top` = the stock's volume ratio (today / mean of the previous 20
    sessions) ranks in the top decile of that day's stocks, `today` and `next` = absolute return
    that day and the next session. Everything on a row is known by that day except `next`."""
    ratio = candles.unusual_volume(volume)
    rank = ratio.rank(axis=1, pct=True)
    frame = pd.DataFrame(
        {
            "top": (rank > top).stack(),
            "today": ret.abs().stack(),
            "next": ret.abs().shift(-1).stack(),
        }
    )
    frame = frame[ratio.stack().reindex(frame.index).notna()].dropna()
    frame.index.names = ["date", "symbol"]
    return frame.reset_index()


def _pct(value: float, digits: int = 2, sign: bool = False) -> str:
    """'1.93%' (or '+0.50%') with a true minus sign."""
    return f"{value * 100:{'+' if sign else ''}.{digits}f}%".replace("-", "−")


def _t(value: float) -> str:
    return f"{value:.1f}".replace("-", "−")


def _gap_chart(gap: pd.Series, out_dir: Path) -> None:
    edge = 0.02  # gaps beyond +-2% share the end bins
    width = 0.0025
    bins = np.arange(-edge, edge + width / 2, width)
    counts, _ = np.histogram(gap.clip(-edge + width / 2, edge - width / 2), bins=bins)
    centres = (bins[:-1] + bins[1:]) / 2
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(centres * 100, counts, width=width * 100 * 0.9, color=plots.SERIES[0])
    ticks = np.arange(-2, 2.1, 0.5)
    ax.set_xticks(ticks, [f"{t:+.1f}%".replace("-", "−") if t else "0" for t in ticks], fontsize=8)
    ax.set_ylabel("sessions")
    ax.set_xlabel("open vs previous close (outer bars include everything beyond ±2%)")
    ax.grid(axis="x", visible=False)
    within = float((gap.abs() < 0.005).mean())
    ax.set_title(
        f"NIFTY opening gap, {gap.index[0]:%Y}–{gap.index[-1]:%Y}\n"
        f"{_pct(within, 0)} of {len(gap):,} sessions open within ±0.5% of the previous close"
    )
    plots.save(fig, out_dir, "candles_gaps")


def _volume_chart(rows: dict[str, dict], title: str, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(rows))
    top = [r["top"] * 100 for r in rows.values()]
    other = [r["other"] * 100 for r in rows.values()]
    ax.bar(x - 0.2, top, 0.4, color=plots.SERIES[0], label="top-decile volume day")
    ax.bar(x + 0.2, other, 0.4, color=plots.SERIES[1], label="all other days")
    ax.set_xticks(x, list(rows), fontsize=9)
    ax.set_ylabel("mean absolute return the next session (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", fontsize=8, ncols=2)
    ax.set_title(title)
    plots.save(fig, out_dir, "candles_volume")


def report_candles(out_dir: Path) -> dict:
    """NIFTY's opening-gap distribution, and whether a stock's next-session move is larger after
    a day of unusual volume (top decile of that day's volume ratios, prior 20 sessions only)."""
    table = _table()
    nifty = table[["open", "close"]].xs("NIFTY", axis=1, level=1).dropna()
    gap = candles.gap(nifty["open"], nifty["close"]).dropna()
    abs_gap = gap.abs()
    out: dict = {
        "NIFTY sessions with a gap": f"{len(gap):,} ({gap.index[0]:%Y-%m-%d} to "
        f"{gap.index[-1]:%Y-%m-%d})",
        "median |gap|": _pct(float(abs_gap.median()), 3),
        "|gap| < 0.25%, < 0.5%, < 1%": tuple(_pct(float((abs_gap < b).mean()), 1) for b in
                                                (0.0025, 0.005, 0.01)),
        "|gap| > 2%": f"{int((abs_gap > 0.02).sum())} sessions",
        "gap up (open above previous close)": _pct(float((gap > 0).mean()), 1),
        "biggest gap up": f"{gap.idxmax():%Y-%m-%d} {_pct(float(gap.max()), 1, True)}",
        "biggest gap down": f"{gap.idxmin():%Y-%m-%d} {_pct(float(gap.min()), 1, True)}",
    }
    _gap_chart(gap, out_dir)

    close = table["close"][SYMBOLS]
    sessions = close.dropna(how="all").index
    ret = daily_returns(table["adj_close"][SYMBOLS].loc[sessions]).where(
        close.loc[sessions].notna()
    )
    index_ret = table["adj_close"]["NIFTY"].dropna().pct_change().reindex(sessions)
    quiet = spike_reversals(ret, index_ret)
    anywhere = spike_reversals(ret, pd.Series(0.0, index=sessions))
    out["spike-and-reverse days (>15% then >12% back, NIFTY < 2%)"] = (
        [f"{s} {d:%Y-%m-%d}" for s, d in quiet] or "none"
    )
    out["same, ignoring the NIFTY condition"] = [f"{s} {d:%Y-%m-%d}" for s, d in anywhere] or "none"

    rows = next_day_table(ret, table["volume"][SYMBOLS].loc[sessions])
    mid = rows["date"].sort_values().iloc[len(rows) // 2]
    parts = {
        f"first half\n{rows['date'].min():%Y}–{mid:%Y}": rows[rows["date"] < mid],
        f"second half\n{mid:%Y}–{rows['date'].max():%Y}": rows[rows["date"] >= mid],
        "whole sample": rows,
    }
    result = {}
    for name, part in parts.items():
        flag = part["top"].to_numpy(dtype=float)
        y = part["next"].to_numpy()
        coef, t, _ = cluster_ols(y, np.column_stack([np.ones(len(part)), flag]), part["date"])
        result[name] = {
            "top": float(part.loc[part["top"], "next"].mean()),
            "other": float(part.loc[~part["top"], "next"].mean()),
            "diff": float(coef[1]),
            "t": float(t[1]),
            "n": len(part),
            "n_top": int(part["top"].sum()),
            "days": int(part["date"].nunique()),
        }
    whole = parts["whole sample"]
    coef, t, _ = cluster_ols(
        whole["next"].to_numpy(),
        np.column_stack(
            [np.ones(len(whole)), whole["top"].to_numpy(dtype=float), whole["today"].to_numpy()]
        ),
        whole["date"],
    )
    w = result["whole sample"]
    out["stock-days (top decile)"] = f"{w['n']:,} ({w['n_top']:,}) on {w['days']:,} dates"
    for name, r in result.items():
        out[f"next-day |return|, {name.splitlines()[0]}"] = (
            f"top decile {_pct(r['top'])}, others {_pct(r['other'])}, difference "
            f"{_pct(r['diff'], 2, True)} (t {_t(r['t'])}, clustered by date)"
        )
    out["difference after controlling for today's |return|"] = (
        f"{_pct(float(coef[1]), 3, True)} (t {_t(float(t[1]))}); today's |return| coefficient "
        f"{coef[2]:.3f}"
    )
    first, second = list(result.values())[:2]
    _volume_chart(
        {k.replace("\n", " "): v for k, v in result.items()},
        f"Next-session move: {_pct(w['top'])} after a top-decile volume day, "
        f"{_pct(w['other'])} otherwise\n"
        f"difference {_pct(w['diff'], 2, True)} (t {_t(w['t'])}); halves "
        f"{_pct(first['diff'], 2, True)} and {_pct(second['diff'], 2, True)}\n"
        f"with the day's own move held fixed: {_pct(float(coef[1]), 2, True)} "
        f"(t {_t(float(t[1]))})",
        out_dir,
    )
    return out


def _breadth_charts(pct: pd.Series, res: dict, out_dir: Path) -> None:
    split = pd.Timestamp(res["split"])
    fig, ax = plt.subplots(figsize=(10, 4.6))
    line = pct.loc[res["train_first"] :].dropna() * 100
    ax.plot(line.index, line.to_numpy(), color=plots.SERIES[0], linewidth=0.8)
    thr = res["breadth"]["threshold"] * 100
    ax.plot([line.index[0], line.index[-1]], [thr, thr], color=plots.TEXT_2, linewidth=0.9,
            linestyle="--")
    ax.axvline(split, color=plots.TEXT_2, linewidth=0.8)
    ax.text(split, 99, " scored from here", fontsize=8, va="top", color=plots.TEXT_2)
    ax.text(line.index[0], thr + 2, f"training median {thr:.0f}%", fontsize=8, color=plots.TEXT_2,
            bbox={"facecolor": plots.SURFACE, "edgecolor": "none", "pad": 1.5})
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("stocks above their 50-day average")
    ax.grid(axis="x", visible=False)
    ax.set_title(
        f"Share of today's NIFTY 50 above their 50-day average, {line.index[0]:%Y}–"
        f"{line.index[-1]:%Y}\nthreshold from {line.index[0]:%Y}–{split.year - 1} only: "
        f"the median, {thr:.0f}%"
    )
    plots.save(fig, out_dir, "breadth_history")

    fig, ax = plt.subplots(figsize=(10, 4.6))
    groups = [("% above 50-day avg", res["breadth"]), ("NIFTY vs its 50-day avg", res["nifty"])]
    x = np.arange(len(groups))
    ax.bar(x - 0.2, [g["high"]["mean"] * 100 for _, g in groups], 0.4, color=plots.SERIES[0],
           label="signal above its training median")
    ax.bar(x + 0.2, [g["low"]["mean"] * 100 for _, g in groups], 0.4, color=plots.SERIES[1],
           label="signal at or below it")
    ax.set_xticks(x, [name for name, _ in groups], fontsize=9)
    ax.axhline(res["all_mean"] * 100, color=plots.TEXT_2, linewidth=0.8, linestyle="--")
    for xs, key in ((x - 0.2, "high"), (x + 0.2, "low")):
        for xi, (_, g) in zip(xs, groups, strict=True):
            ax.text(xi, g[key]["mean"] * 100 + 0.02, _pct(g[key]["mean"], 2, True), ha="center",
                    fontsize=9, color=plots.TEXT)
    ax.set_ylim(0, 1.55)
    ax.set_ylabel("mean NIFTY return over the next 20 sessions (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=8, ncols=2)
    b, n = res["breadth"], res["nifty"]
    ax.set_title(
        f"Scored {res['first_day'][:4]}–{res['last_day'][:4]}: mean NIFTY return over the next 20 "
        f"sessions\nhigh minus low, breadth: {_pct(b['diff'], 2, True)} (t {_t(b['diff_t'])})\n"
        f"high minus low, NIFTY vs its average: {_pct(n['diff'], 2, True)} (t {_t(n['diff_t'])})"
        f"; dashed line, all days: {_pct(res['all_mean'])}"
    )
    plots.save(fig, out_dir, "breadth_returns")


def report_breadth(out_dir: Path) -> dict:
    """Day counts as the Breadth tab shows them, then the out-of-sample check: does the share of
    stocks above their 50-day average say anything about NIFTY's next 20 sessions beyond NIFTY's
    own position against its 50-day average? Thresholds from 2008-2016, scored 2017 on."""
    table = _table()
    close = breadth.fixed_close(table["close"][SYMBOLS])
    hist = breadth.history(close)
    pct = hist["pct_above50"]
    nifty = table["close"]["NIFTY"]
    res = breadth.oos_check(pct, nifty)
    res["split"] = "2017-01-01"
    now = breadth.above_ma(close)
    ext = breadth.new_highs_lows(close)
    stocks = hist.loc[res["train_first"] :, "of"]
    out: dict = {
        "latest": f"{close.dropna(how='all').index[-1]:%Y-%m-%d}: {now['count']} of {now['of']} "
        f"above 50-day average, {ext['highs']} of {ext['of']} at a 250-day high, "
        f"{ext['lows']} at a low",
        "stocks in the 50-day measure": f"{int(stocks.iloc[0])} on {res['train_first']}, "
        f"{int(stocks.max())} at most",
        "share above, min / median / max": tuple(
            _pct(float(v), 0) for v in (pct.min(), pct.median(), pct.max())
        ),
        "training days (2008-2016)": f"{res['train_days']:,} from {res['train_first']}",
        "scored sessions": f"{res['n']:,} ({res['first_day']} to {res['last_day']}); all-days "
        f"mean next-20-session return {_pct(res['all_mean'])}, up {_pct(res['all_hit'], 1)}",
    }
    for key, label, fmt in (
        ("breadth", "% above 50-day, threshold", lambda v: _pct(v, 1)),
        ("nifty", "NIFTY vs 50-day average, threshold", lambda v: _pct(v, 2, True)),
        ("above_zero", "NIFTY above its 50-day average, cut-off", lambda v: "0"),
    ):
        r = res[key]
        out[f"{label} {fmt(r['threshold'])}"] = "; ".join(
            f"{name}: {r[name]['n']:,} days, up {_pct(r[name]['hit'], 1)}, mean "
            f"{_pct(r[name]['mean'], 2, True)} (t {_t(r[name]['t'])})"
            for name in ("high", "low")
        ) + f"; difference {_pct(r['diff'], 2, True)} (t {_t(r['diff_t'])})"
    j = res["joint"]
    out["both flags in one regression"] = (
        f"breadth {_pct(j['breadth'], 2, True)} (t {_t(j['breadth_t'])}), NIFTY vs average "
        f"{_pct(j['nifty'], 2, True)} (t {_t(j['nifty_t'])})"
    )
    out["days the two flags agree"] = _pct(res["agree"], 0)
    out["standard errors"] = "Newey-West, 19 lags (20-session returns overlap by 19)"
    out["sample"] = "today's 50 members applied to past years: survivorship-biased, an upper bound"
    _breadth_charts(pct, res, out_dir)
    return out


REPORTS = {
    "data": report_data,
    "overview": report_overview,
    "candles": report_candles,
    "breadth": report_breadth,
}
