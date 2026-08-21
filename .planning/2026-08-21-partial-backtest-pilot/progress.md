# Progress Log

## Session: 2026-08-21

### Current Status

- **Phase:** 4 — Live pilot and continuation
- **Status:** blocked by external database entry

### Actions Taken

- Confirmed the user's staged decision: no FinMind Pro upgrade now; use complete Shioaji partitions for exploratory backtesting and continue the original job later.
- Read the root planning records and session catch-up output.
- Read the historical-quota recovery and quota-status plans without changing their active-plan pointer.
- Confirmed the downloader already persists each symbol atomically, pauses safely, and retains an exact retry marker.
- Confirmed the formal institutional acquisition artifacts prohibit using the incomplete coverage job for formal outcomes or holdout work.
- The first PostgreSQL inspection attempt found no listener; a later read-only listener check shows the configured local port is now present, so one authoritative reconnect is pending.
- The reconnect reached a newly created unrelated PostgreSQL container. The configured `tw_intraday_trader` database and `backtest` schema are absent there; the container was not stopped or changed.
- Confirmed the local SQLite file is an empty local-dev database with zero jobs and partitions, so it cannot be used as an authority fallback.
- Added `backtest/exploratory_pilot.py`, `scripts/build_exploratory_backtest_pilot.py`, and `tests/test_exploratory_backtest_pilot.py` without editing the existing downloader or active plan.
- The pilot builder enforces the 2024-12-31 ceiling, deterministic bounded selection, payload checksum verification, date clipping, endpoint revalidation, and formal validation/holdout prohibition.
- Focused pilot/downloader regression passed: 18 tests.
- Complete repository regression passed: 1,049 tests with 4 explicit skips.
- Python compilation, CLI help, and task-scoped whitespace checks passed.

### Next

- Restore the original PostgreSQL/tunnel entry that contains the migrated 678 partitions.
- Run the pilot CLI against that authority, then resume Shioaji only when both the database and Provider allowance are available.
