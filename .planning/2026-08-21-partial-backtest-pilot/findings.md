# Findings & Decisions

## Requirements

- Backtest the stocks whose downloaded history is genuinely usable now.
- Keep downloading the remaining market through the same Shioaji job over later allowance resets.
- Do not mix exploratory results into the formal institutional evaluation protocol.
- Do not inspect or materialize validation/holdout outcomes through this pilot.

## Confirmed Starting State

- Durable job: `dataset-download-f914feaddea04e37b3cbdcfce2b0179b`.
- Frozen request: current-contract universe, 2,738 instruments, 2023-08-19 through 2026-08-18.
- Sealed observation artifacts cover indices 0–677: 678 observed partitions, 670 non-empty, 8 provider-unavailable observations.
- The next exact retry symbol is `2101`; the job paused on a recoverable Shioaji rate-limit condition.
- Existing artifacts explicitly prohibit formal coverage claims, research eligibility, population freeze, outcome generation, and holdout execution.

## Working Eligibility Rule

- Read only non-empty partitions with no error marker.
- Require coverage to reach the pilot start and end boundaries after trading-calendar tolerance is applied.
- Clip bars to an explicit in-sample interval before sealing.
- Keep the symbol set deterministic and bounded to avoid the current engine's full-materialization memory risk.
- Emit a new immutable dataset id and register it as `research_eligible=false`, with `EXPLORATORY_PARTIAL_UNIVERSE`, `SURVIVORSHIP_BIASED_CURRENT_CONTRACTS`, and `FORMAL_HOLDOUT_PROHIBITED` issues.

## Issues Encountered

| Issue | Resolution |
|---|---|
| The configured DSN reaches `localhost:5090/tw_intraday_trader`, but the database does not exist at the listener now occupying that port | Treat this as infrastructure drift, not market-data loss; no database mutation was attempted. |
| The active `tsg-single-db` container was created at 2026-08-21 06:33 UTC and contains only `postgres` and `thortron_core`, with no `backtest` schema | It is unrelated to this repository's migrated authority; do not stop it implicitly. |
| `data/backtest/backtest.sqlite3` is now a 148 KiB empty local-dev database | It cannot replace the previously measured 201,535,488-byte migration source or the PostgreSQL copy. |

## Implemented Pilot Contract

- `backtest/exploratory_pilot.py` plans and seals a new deterministic dataset id from the source job, date interval, selected symbols, and source partition checksums.
- Default selection is 12 evenly spaced eligible symbols from the observed job order; explicit symbols are also supported but must all pass the gate.
- The builder rechecks gzip payload SHA-256, clips every bar to 2023-08-21 through 2024-12-31 by default, and verifies endpoint coverage again from decoded rows.
- The resulting manifest is always `research_eligible=false` and contains explicit prohibitions for formal validation and holdout use.
- The source job is never updated or finalized by the pilot builder.
