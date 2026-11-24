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
| `notice` | string or `null` | message for the header, e.g. `"Refresh failed: …"` |

Session rules (`mt.session.session_date`):

- USD/INR and the S&P 500 are on other calendars and never decide the session.
- Before 16:00 IST today's bar is dropped (unfinished).
- An all-NaN row (Yahoo on an NSE holiday) counts for nothing; the last complete day is shown.
- A stock listed recently counts from its first bar; it does not hold the session back.

## Sections

Later sections are added to `mt.snapshot.SECTIONS` as `(key, fn(table))` and documented here.
