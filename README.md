# Market terminal

[![CI](https://github.com/Dhirajdas18/market-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/Dhirajdas18/market-terminal/actions/workflows/ci.yml)

A small terminal app to open after the NSE close and review the day: today's NIFTY 50 plus a few
reference series (NIFTY Bank, India VIX, USD/INR, gold, S&P 500), end-of-day bars from Yahoo Finance kept
in a local cache. It runs only while open: no background jobs, no polling, network only at launch and on
`r`.

<img src="docs/img/app_header.svg" alt="The app's header showing Data for Mon 23 Nov 2026, last complete NSE session, with INFY and TCS named as having no bar yet" width="720">

## Features

- [x] Data pipeline: Yahoo end-of-day bars since 2007 in a local parquet cache, updated incrementally;
  session date that handles NSE holidays, late bars and the 16:00 IST cut-off; snapshot schema; app
  skeleton with refresh and quit

## Usage

```bash
uv sync
uv run mt                  # first run downloads 2007 onwards (~20 s) before opening
uv run mt report data      # README chart -> out/, numbers printed
uv run pytest
```

Later launches open on the cached data in about 0.4 s (Apple Silicon Mac, script start to first screen with Textual's
headless runner) and fetch the last week from Yahoo in the background; the header says "Updating…" until the
new data is in, or "Refresh failed: <error type>" with the cached data still on screen. Errors go to
`~/.config/market-terminal/mt.log`.

Keys: `r` refresh (runs in the background; the screen keeps the current data if it fails), `q` quit.
The header always states which day is shown, e.g. "Data for Mon 23 Nov 2026", names any stock
whose bar for a newer day has not arrived, and lists stocks with no bar for 3 or more sessions as
suspended.

## Findings

### 1. Yahoo has no NIFTY bar on 11 to 19 weekdays a year, and on 21 more weekdays from 2008 to 2019 it had stock bars but no index bar; of 21 one-day drops over 20%, 9 are known data errors and 12 checked out as real moves

<a href="docs/img/data_gaps.png"><picture><source media="(prefers-reduced-motion: reduce)" srcset="docs/img/data_gaps.png"><img src="docs/img/data_gaps.gif" alt="Weekdays per year from 2008 to 2025 with no NIFTY bar on Yahoo, split into days with no NSE bar at all and days when stocks traded but the index bar is missing" width="720"></picture></a>

Weekdays from 2008 to 2025 with no `^NSEI` close on Yahoo, split by whether any NSE series in the table
(the 50 stocks, NIFTY Bank, India VIX, GOLDBEES) has a bar that day.

- **No NSE bar at all:** 11 to 19 weekdays a year, median 15. These are NSE holidays, plus any day
  Yahoo lost for every ticker.
- **Index bar missing on a trading day:** 21 weekdays in 10 of the years from 2008 to 2019; none from
  2020 to 2025. The app treats a missing NIFTY bar like any other late bar: it shows the last day every
  NSE series has and names NIFTY in the header.
- **Bad-print scan:** 21 one-day drops of more than 20% in the adjusted closes (India VIX left out).
  9 are covered by `docs/data/yahoo_fixes.csv` (unadjusted corporate actions and prices from before a
  listing). The other 12 were checked one by one and kept as real moves:
  - 6 fell on days NIFTY itself fell 5.9% to 13.0%: Kotak Mahindra Bank on 24 Oct 2008 (NIFTY
    −12.2%); Axis Bank, Bajaj Finance, Bajaj Finserv and Shriram Finance on 23 Mar 2020 (−13.0%);
    Adani Ports on 4 Jun 2024 (−5.9%).
  - 5 match same-day news reports of the fall: Adani Enterprises on 29 Jul 2011, 26 Apr 2017 and
    1–2 Feb 2023, and Infosys on 12 Apr 2013 (−21.3%, the day of its annual guidance).
  - Bajaj Finance on 8 Oct 2008 (−20.0%) closed at the day's low on 17 times the previous day's volume;
    no news report was found.

  None of the 12 has a split or bonus on Yahoo's corporate-action list, and none returned to the
  previous price the next day.

## Design

- `src/mt/data.py`: tickers, Yahoo download with retries (`DownloadFailed` names any missing ticker and
  leaves the cache untouched), incremental cache update with a 7-day overlap written atomically, cache
  load with a date filter, daily returns with known Yahoo errors repaired from
  `docs/data/yahoo_fixes.csv`.
- `src/mt/session.py`: which trading day to show.
- `src/mt/snapshot.py`: one plain dict that every screen reads; schema in [docs/snapshot.md](docs/snapshot.md).
- `src/mt/app.py`, `widgets.py`, `app.tcss`: the Textual app; colours from the chart tokens in `plots.py`.
- `src/mt/reports.py`: README findings, reproducible with `mt report <topic>`.

Price data is not committed: `data/` is a local cache. Constituents are a snapshot of NSE's NIFTY 50
list in `docs/data/nifty50.csv`; using today's members over past years is survivorship-biased.

MIT licence.
