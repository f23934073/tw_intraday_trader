# Shioaji equity Kbar — G0 qualification evidence

This directory contains the exact raw SDK Kbar samples and the offline G0
qualification result captured on 2026-08-19 for symbol `2330`.  It is data-only
evidence; it does not create a daily dataset, register SMA strategies, or place
orders.

`fixtures/` retains every raw value's Python type, `repr`, and `str` before the
normal Provider converts prices to `float`. `qualification/` is regenerated
from those fixtures without Shioaji credentials or network access:

```sh
.venv/bin/python scripts/qualify_shioaji_daily_kbar_g0.py
```

The captured Provider request has no interval parameter and returned 266
intraday rows for 2026-08-18 (09:01–13:30 Asia/Taipei), so it is not an explicit
daily source. The historic rows have complete time coverage and repeated query
digests agree. A separate raw capture includes `Amount`: all 266 rows prove
that `Amount / (Volume * 1000)` is within the respective bar's high/low range.
This establishes `Volume` as a common-lot value for the captured session.

`twse_daily_reconciliation.json` compares the resulting regular-session OHLC
with the raw official TWSE `STOCK_DAY` row after market close. All four prices
match exactly, so the official report supplies the otherwise missing completion
proof and `qualification_result.json` selects `DERIVED_FINALIZED_SESSION_V1`.
Official total volume/amount do not match the observed 09:01–13:30 source
aggregate: the report includes other published transaction scopes. The derived
contract therefore retains `SHIOAJI_REGULAR_SESSION_COMMON_LOTS_V1`, rather
than claiming an all-session official-volume series.

The 2026-08-19 partial capture's final raw timestamp resolves to 12:17 while
the local query was recorded at 12:16. The report preserves this as
`TIMESTAMP_AFTER_CAPTURE_TIME`; it may be a bar-end label or a clock difference,
but its semantic has not been declared by the Provider and is not guessed here.

The session contract records the official TWSE 2026 holiday-schedule URL,
retrieval time, source digest, and listed non-trading dates. It also models the
regular session as 09:00–13:30 with official interruption allowances. This is
only session-resolution evidence; it does not establish corporate-action
adjustment or formal research eligibility.
