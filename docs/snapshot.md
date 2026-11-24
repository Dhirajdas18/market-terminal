# Snapshot schema

Every screen reads one plain dict built by `mt.snapshot.build(table, now_ist)`. It must survive
`json.dumps(snapshot, allow_nan=False)`: missing values are `null` (`None`), and screens show them as
"—". Each section is computed from the price table trimmed to `as_of`, so nothing on screen uses a later
day.

## Top level

| key | type | meaning |
|---|---|---|
| `as_of` | `"YYYY-MM-DD"` | session date: the latest day on which every NSE series has a close |
| `as_of_label` | string | header text, e.g. `"Data for Mon 23 Nov 2026"` |
| `stale` | bool | `as_of` is earlier than today's date in IST (holiday, weekend, before 16:00 IST, or a late bar) |
| `missing` | list of symbols | NSE symbols without a bar on the newest date some other NSE symbol has |
| `suspended` | list of `{"symbol", "last"}` | NSE symbols whose last bar is 3 or more sessions behind the newest date (halted or no longer quoted); they no longer hold the session back |
| `no_data` | list of symbols | constituents the last update had no Yahoo data for (renamed, merged or a long halt; at most 5, never an index or reference series): their cached bars are kept, they never hold the session back, and the header names them. More than 5, or any index/reference series, fails the update instead |
| `notice` | string or `null` | message for the header, e.g. `"Refresh failed: …"` |

Session rules (`mt.session.session_date`):

- USD/INR and the S&P 500 are on other calendars and never decide the session.
- Before 16:00 IST today's bar is dropped (unfinished).
- An all-NaN row (Yahoo on an NSE holiday) counts for nothing; the last complete day is shown.
- A row counts as an NSE session only if at least half as many NSE series have a close as on the busiest day (`mt.session.sessions`): Yahoo's one-ticker stray rows on a Saturday are not sessions for the session date, the sessions-behind count or any section.
- A stock listed recently counts from its first bar; it does not hold the session back.
- A stock 1–2 sessions behind is a late bar: the session falls back and the stock is in `missing`.
  At 3 or more sessions behind it is `suspended` and ignored. Sessions are dates on which any NSE
  series has a close (Yahoo's NIFTY series has gaps of its own).

## Sections

Later sections are added to `mt.snapshot.SECTIONS` as `(key, fn(table))` and documented here.

### `overview`

List of six rows in this order: `NIFTY`, `NIFTYBANK`, `INDIAVIX`, `USDINR`, `GOLDBEES`, `SP500`
(`mt.overview.section`; a series missing from the table is left out).

| key | type | meaning |
|---|---|---|
| `name` | string | series key |
| `date` | `"YYYY-MM-DD"` | the series' own last valid bar on or before `as_of` (earlier than `as_of` for USD/INR or the S&P 500 when their calendar has no bar that day) |
| `close` | float | close on `date` |
| `day` | float or `null` | `close` / previous valid close − 1 |
| `week` | float or `null` | `close` / last close of the previous ISO week − 1 |
| `ytd` | float or `null` | `close` / last close of the previous calendar year − 1 |
| `low52`, `high52` | float or `null` | lowest low and highest high over the 365 calendar days to `as_of` (close, if the table has no high/low) |
| `pos52` | float or `null` | `(close − low52) / (high52 − low52)`, 0 at the low and 1 at the high |

The overview tab shows the date under a tile only when it differs from `as_of`. Refreshing keeps the
selected tab.

### `index`

NIFTY's last 250 sessions that have a bar (`mt.candles.index_series`). Moving averages are computed on the
whole history in the table and then cut, so the first row already has one. Empty lists if the table has
no NIFTY or no open/high/low/close/volume.

| key | type | meaning |
|---|---|---|
| `dates` | list of `"YYYY-MM-DD"` | sessions, oldest first |
| `open`, `high`, `low`, `close` | list of float | NIFTY's bars (Yahoo's `^NSEI`) |
| `ma20`, `ma50` | list of float or `null` | trailing mean of the last 20 / 50 closes; `null` without a full window |
| `value_cr` | list of float or `null` | traded value of the 50 stocks that day: sum of close × volume, in ₹ crore (a stock with no close or volume that day is left out; `null` if none has both). Yahoo's `^NSEI` volume has no documented meaning, so it is not used. |

### `movers`

Stocks with a bar on `as_of` only (`mt.candles.movers_section`).

| key | type | meaning |
|---|---|---|
| `gainers`, `losers` | list of `{"symbol", "ret"}` | 5 biggest and smallest day returns (adjusted close, Yahoo errors repaired from `docs/data/yahoo_fixes.csv`); a stock with no return is skipped |
| `unusual` | list of `{"symbol", "ratio", "ret"}` | 5 highest ratios of today's volume to the mean of the previous 20 sessions (today left out; a volume of 0 counts as missing; fewer than 20 prior sessions gives no ratio); `ret` is `null` if missing |

### `breadth`

Counts for the stocks that have a bar on `as_of` (`mt.breadth.section`); `{}` if the table has no
close or adjusted close. Every count says how many stocks it was computed for: a stock with too little history
for a measure, no bar today, or a missing close inside the window is left out of that measure and its
denominator. Non-trading rows (all stocks NaN, or fewer than half as many stocks as the busiest day)
are dropped before any window. Closes have the `start` and `blank` rows of `docs/data/yahoo_fixes.csv` applied.

| key | type | meaning |
|---|---|---|
| `up`, `down`, `flat` | int | stocks with a day return above, below and equal to 0 (adjusted close, Yahoo errors repaired); a stock with no return is not counted |
| `above50` | `{"count", "of"}` | stocks whose close is above the mean of their last 50 closes (today included, strictly above), out of stocks with 50 closes and a bar today |
| `highs`, `lows` | int | stocks whose close is at or above (at or below) the previous 249 closes |
| `of52` | int | stocks with 250 closes and a bar today: the denominator of `highs` and `lows` |
| `spark` | `{"dates", "pct"}` | the last 250 sessions; `pct` is the share (0 to 1) of stocks above their 50-day average that day, `null` until a stock has 50 closes |

### `sectors`

List of `{"name", "ret", "n"}`, best sector first (`mt.sectors.sectors_section`): `ret` is the equal-weight
mean day return (price return from `close`, `zero` fixes of `docs/data/yahoo_fixes.csv` applied) of the sector's
stocks with a bar on `as_of`, `n` the number of stocks in that mean. A sector with no stock return is left out.

### `contributions`

`{}` if NIFTY has no close on `as_of` and the session before (`mt.sectors.contributions_section`).

| key | type | meaning |
|---|---|---|
| `top` | list of `{"symbol", "points", "weight"}` | the 10 stocks with the largest \|points\|: weight x day return x NIFTY's previous close; `weight` (0 to 1) is estimated by non-negative least squares on the 60 sessions before `as_of` (`as_of` itself not used) |
| `all` | list of `{"symbol", "points", "weight"}` | the same for every stock with a weight, in the same order (`top` is its first 10); the sector view reads it |
| `not_estimated` | list of symbols | stocks with a bar today but fewer than 60 valid returns in that span: no weight, no points |
| `sum_points` | float | sum of the points of all stocks with a weight |
| `actual_points` | float | NIFTY's close minus its previous close |

### `stocks`

`{symbol: {...}}` for each of the 50 with a close (`mt.stock.stocks_section`); `{}` if the table has no open, high, low, close or adjusted close. Returns are `daily_returns` of adjusted closes (known Yahoo errors repaired) on NSE sessions only, and a day without a bar for the stock has no return. A measure that needs a full window is `null` until the stock has it.

| key | type | meaning |
|---|---|---|
| `close` | float | last valid close (2 decimals, split-adjusted) |
| `day` | float or null | return on `as_of`; `null` if the stock has no bar that day |
| `m1`, `y1` | float or null | compounded return of the last 21 / 250 returns; `null` with fewer |
| `vol` | float or null | standard deviation of the last 250 returns x the square root of returns per calendar year over their span; `null` with fewer than 250 |
| `beta` | float or null | 0.67 x the OLS slope against NIFTY + 0.33, over the last 250 returns both have; `null` with fewer, or if NIFTY did not move |
| `mdd` | float or null | worst fall from a peak over the last 250 closes (negative or 0); `null` with fewer |
| `var95` | float or null | historical 5th-percentile one-day loss in rupees on 1,00,000 over the last 500 returns (0 or more); `null` with fewer than 250 |
| `sector` | string or null | NSE industry from `docs/data/nifty50.csv` |
| `candles` | object | `dates`, `open`, `high`, `low`, `close`, `ma20`, `ma50`: parallel arrays of the last 250 sessions the stock has (fewer for a recent listing), prices to 2 decimals; the averages use the whole history and are `null` until a full window exists |

### `watchlist` (demo files only)

Optional list of symbols. A live snapshot never has it: the app reads `~/.config/market-terminal/watchlist.json`. `mt --demo` seeds an in-memory watchlist from this key (symbols not in `stocks` are dropped) and never reads or writes the real file.
