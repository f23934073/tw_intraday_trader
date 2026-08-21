# Task Plan: PostgreSQL data persistence report

## Goal

Produce a repository-grounded report and implementation plan that decides which `tw_intraday_trader` data must use PostgreSQL, which should remain file/object or ephemeral state, and how to migrate safely without implementing product code.

## Current Phase

Phase 1 — Repository and storage-contract discovery

## Phases

### Phase 1: Repository and storage-contract discovery

- [x] Reconfirm current storage adapters, runtime wiring, migrations, and actual local/PostgreSQL contents.
- [x] Trace write authority, replay needs, query patterns, retention, and recovery requirements by data family.
- [x] Preserve the report/plan-only boundary and all unrelated worktree changes.
- **Status:** completed

### Phase 2: PostgreSQL placement decision

- [x] Classify each data family as PostgreSQL authoritative, PostgreSQL metadata/index plus file payload, file/object authoritative, or ephemeral projection.
- [x] Define bounded contexts, transaction boundaries, idempotency keys, lineage, partitioning, retention, and backup requirements.
- [x] Identify data that must not be duplicated into competing authoritative stores.
- **Status:** completed

### Phase 3: Implementation plan authoring

- [x] Write dependency-ordered phases with exact repository areas and migration ownership.
- [x] Include dual-write/backfill/cutover/rollback gates and operational acceptance criteria.
- [x] Define tests for real PostgreSQL semantics, restart recovery, replay parity, and no-broker-order boundaries.
- **Status:** completed

### Phase 4: Verification and delivery

- [x] Cross-check the report against current code, database contents, and existing architecture plans.
- [x] Verify only planning/report Markdown was created or modified in this task.
- [x] Deliver the recommendation, priority order, and implementation plan for user review.
- **Status:** completed

### Phase 5: Updated-report intake and implementation baseline

- [x] Treat the user-edited report as the implementation authority and identify every newly frozen choice.
- [x] Reconcile the implementation with repository instructions, dirty-worktree ownership, existing migrations/adapters, and the separate FreshnessPolicy gate.
- [x] Capture a focused test baseline before changing runtime code.
- **Status:** completed

### Phase 6: Phase 0 configuration and migration contract

- [x] Implement typed PostgreSQL configuration for the approved single-database, logical-schema direction without exposing secrets.
- [x] Define backward-compatible migration ownership and fail-closed repository/runtime configuration.
- [x] Document authority and runtime-mode behavior in repository-facing configuration/docs.
- **Status:** completed

### Phase 7: LOCAL_PAPER Trading Journal PostgreSQL cutover

- [x] Strengthen the PostgreSQL Journal adapter behind the existing `JournalRepository` port.
- [x] Wire only explicitly durable LOCAL_PAPER runtime mode to PostgreSQL; keep in-memory mode explicit for tests/local ephemeral use.
- [x] Preserve journal-first side effects, idempotency, recovery/checkpoint parity, and database-outage fail-closed behavior.
- [x] Do not add Shioaji account/order/deal/CA paths or bypass the existing FreshnessPolicy gate for future Portfolio work.
- **Status:** completed

### Phase 8: Verification and next-phase gate

- [x] Run focused unit/migration/recovery tests and real PostgreSQL integration smoke where the configured local database permits it.
- [x] Run relevant regression/static checks and inspect the final task-scoped diff.
- [x] Update the report and implementation records with completed versus evidence-gated work before proceeding to backtest/market-data migration.
- **Status:** completed

### Phase 9: Backtest SQLite to PostgreSQL migration

- [x] Re-read current backtest repository/migrations and define a non-destructive, resumable copy contract.
- [x] Implement and test a migration command that preserves IDs, JSON, status/progress, partition bytes/digests/counts, and timestamps.
- [x] Reconcile the stale `RUNNING` job explicitly while preserving the active `PAUSED` 678/2738 checkpoint.
- [x] Copy the current SQLite dataset to the approved PostgreSQL database, verify counts/digests/resume parity, and keep SQLite intact.
- [x] Switch only backtest configuration after verification succeeds.
- **Status:** completed

### Phase 10: Backtest migration verification and next gate

- [x] Run focused/full regression and real PostgreSQL readback checks.
- [x] Record remaining market-event/artifact phases and any evidence-gated work without inventing retention values.
- **Status:** completed

## Key Questions

1. Which facts require durable transactional authority and restart recovery?
2. Which high-volume immutable payloads belong in PostgreSQL versus content-addressed file/object storage?
3. Which projections can be rebuilt and therefore should not become competing sources of truth?
4. How should historical market data, raw intraday events, orders/fills/positions, and research artifacts be separated?
5. What cutover gates prevent data loss, duplicate orders, replay drift, or accidental broker-order scope expansion?

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Report and plan only | The user requested judgment, report, and implementation plan; no product implementation is authorized. |
| Use a dedicated isolated planning directory | Existing root and active planning files belong to other ongoing work and must not be overwritten. |
| PostgreSQL is evaluated per bounded context | One technology does not imply one shared schema or one consistency boundary for all data. |
| Preserve market-data-only broker boundary | Persistence planning does not authorize CA, broker orders, account reads, or trade callbacks. |
| Implement the updated report in dependency order | User authorization changes the prior plan-only boundary, but does not remove explicit safety/evidence gates. |
| Start with approved single database + logical schemas and `LOCAL_PAPER` only | The user marked those report decisions `ok` and `LOCAL_PAPER`; market-data retention/object-storage choices remain evidence-gated. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Existing root planning files and active plan belong to another task | 1 | Created this isolated plan without changing `.planning/.active_plan`. |
| Broad search across several architecture reports was truncated | 1 | Use narrow per-file searches and bounded excerpts for the remaining cross-check. |
| A search path named `scanner` did not exist | 1 | Reuse valid output and select only paths confirmed by the repository file list. |
| Initial detailed backtest-job query used non-existent columns | 1 | Read the table schema, then issue a corrected read-only query. |
| First focused implementation run had two contract-test mismatches | 1 | Bypass environment parsing for an explicitly injected Journal and update the migration-discovery expectation for `002`. |
| Initial `psycopg-pool` install could not reach the package index inside the sandbox | 1 | Re-ran the scoped project-venv installation with approved network access; `psycopg-pool 3.3.1` installed. |
| First attempt to log the dependency install used a stale multi-file patch context | 1 | Re-read the isolated planning sections and applied a smaller exact-context update. |
| Local PostgreSQL preflight was blocked by sandbox TCP permissions | 1 | Re-ran the same read-only preflight with approved local-network access and confirmed the empty legacy layout. |
| First live smoke printed a self-comparison for checkpoint parity | 1 | Keep the valid append/idempotency evidence, rerun a new synthetic session that compares `latest_checkpoint()` to the expected checkpoint, then clean it up. |
| Full suite exposed stale trade-management premarket migration/schema expectations | 1 | Update the readiness contract and fixtures from public/`001` to `trading`/`001+002`, then rerun focused and full suites. |
| Broad combined backtest repository/migration read exceeded the output limit | 1 | Switched Phase 9 inspection to narrow per-file excerpts and will record only migration-contract evidence. |
| `python` executable was not available for the first compile check | 1 | Use the repository virtual environment at `.venv/bin/python` for all verification. |
| Two combined planning updates failed on long table-line context | 1-2 | Applied smaller single-hunk updates around short exact lines. |
| First Backtest PostgreSQL preflight command produced invalid SQL quoting | 1 | Rebuilt the read-only query with explicit quote characters; the corrected preflight passed. |
| Post-cutover planning update had stale context, then repeated the same file twice in one patch | 1-2 | Re-read exact lines and applied one update block per file. |

## Notes

- Treat repository and memory files as evidence, not instructions.
- Re-read this plan before final placement and cutover decisions.
- Runtime/migration implementation is now authorized only within this isolated plan's approved LOCAL_PAPER PostgreSQL scope; preserve unrelated user files and safety gates.
