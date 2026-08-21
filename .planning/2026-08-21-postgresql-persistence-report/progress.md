# Progress: PostgreSQL data persistence report

## Session: 2026-08-21 — Implementation authorization

### Phase 5: Updated-report intake and implementation baseline

- **Status:** completed
- Actions taken:
  - Received explicit authorization to begin implementation from the updated report.
  - Re-read the `planning-with-files` and `architecture-patterns` skills and the advanced bounded-context reference.
  - Restored root and isolated planning context plus session catch-up output.
  - Confirmed the worktree contains extensive pre-existing user changes; this task will use narrowly scoped edits and preserve them.
  - Identified all user-edited decisions: single database with logical schemas, evidence-based event retention, local content-addressed history payloads, `LOCAL_PAPER` only, and migration of unqualified tables into logical schemas.
  - Confirmed no repository `AGENTS.md` applies and the earlier FreshnessPolicy gate remains relevant to broker/account or broader Portfolio work.
  - Traced the current Journal port, PostgreSQL adapter, migration runner/SQL, runtime composition and shutdown lifecycle, optional psycopg dependency, and real-PostgreSQL test gate.
  - Chose the minimum first implementation seam: backward-compatible `trading` schema migration, schema-qualified adapter/lifecycle, typed durable-mode configuration, and composition injection.
  - Traced the LOCAL_PAPER command/fill/cancel event flow, deterministic fill projection, checkpoint recovery, and legacy simulator state model.
  - Found that current Journal events are sufficient for durable audit and fill-based accounting parity but not pending-order/UI hydration; full restart-safe mutation must remain gated until that contract is implemented and tested.
- Implementation target:
  - Phase 0 configuration/migration contract plus the P0 LOCAL_PAPER Trading Journal PostgreSQL cutover.
  - No Shioaji trade subscription, CA, broker order, deal, or account path.
- Baseline verification:
  - `.venv/bin/python -m pytest -q tests/test_journal.py tests/test_postgres_journal.py tests/test_runtime_composition.py tests/test_local_paper_projection.py tests/test_command_recovery.py tests/test_strategy_paper_flow.py tests/test_dashboard_simulation_api.py`
  - Result: `37 passed, 1 skipped` (`TEST_POSTGRES_DSN` not supplied).

### Phase 6: Phase 0 configuration and migration contract

- **Status:** completed
- Planned success criteria:
  - Environment parsing is typed, explicit, secret-safe, and fail-closed.
  - Fresh and legacy Journal layouts converge on the `trading` schema through a forward-only migration.
  - Existing in-memory tests remain the default; durable mode requires explicit configuration.
- Changes implemented:
  - Added typed, secret-safe `TradingPersistenceConfig` with explicit memory/PostgreSQL selection and validated pool settings.
  - Added infrastructure-only Journal factory with lazy optional imports, migration-before-pool startup, health check, and typed fail-closed initialization errors.
  - Added forward-only `002_trading_schema.sql` plus legacy migration-ledger adoption so fresh and existing public Journal tables converge on the `trading` schema.
  - Updated `PostgresJournalRepository` to use schema-qualified SQL, per-operation pool acquisition, transaction cleanup, health check, and owned-pool shutdown while preserving direct-connection tests.
  - Wired persistence selection and Journal shutdown at the composition root; injected test repositories still bypass environment selection.
  - Added environment examples, the psycopg pool optional dependency, configuration/composition tests, and real-PostgreSQL migration expectations.
  - Installed `psycopg-pool 3.3.1` in the project virtual environment.
  - Ran a live read-only PostgreSQL preflight: `public` Journal tables each have 0 rows and no `trading` copies exist, so the forward-only move has no current data conflict.
  - Applied `002_trading_schema.sql` to the configured local PostgreSQL; migration versions are `001` and `002`, the public Journal tables are gone, and the three `trading` tables exist.
  - Ran a pooled synthetic append/idempotency smoke and removed the synthetic rows; checkpoint readback must be rerun because the first output compared the expected object to itself.
- Files modified/added:
  - `config/trading_persistence.py`
  - `runtime/trading_persistence.py`
  - `runtime/composition.py`
  - `trading/migrations.py`
  - `trading/migrations/002_trading_schema.sql`
  - `trading/postgres_journal.py`
  - `.env.example`, `pyproject.toml`
  - `tests/test_trading_persistence_config.py`
  - `tests/test_runtime_composition.py`
  - `tests/test_postgres_journal.py`

### Phase 7: LOCAL_PAPER Trading Journal PostgreSQL cutover

- **Status:** completed
- Actions taken:
  - Wired explicit PostgreSQL selection through the composition root while retaining explicit in-memory test/local mode.
  - Added a sequence-0 checkpoint when a new LOCAL_PAPER session starts.
  - Added verified full-Journal checkpoint writes after complete immediate fills, risk rejections, later asynchronous fills, and cancellations.
  - Preserved fail-closed behavior: checkpoint failure after a recorded mutation raises a recovery warning and tells the caller not to resubmit.
  - Corrected the live checkpoint smoke to compare `latest_checkpoint()` with the expected object; roundtrip passed and all synthetic rows were removed.
  - Activated `TRADING_JOURNAL_BACKEND=postgresql` in the gitignored local `.env` without duplicating the existing DSN.
  - Verified the formal RuntimeComposition selects the pooled PostgreSQL adapter and sequence-0 checkpoint, then removed the synthetic session.
  - Added an autouse pytest boundary that forces memory mode so developer `.env` cannot make unit/API tests mutate PostgreSQL implicitly.
  - Updated trade-management shadow preflight to query `trading`, accept all current migration files, and resolve the same DSN aliases as runtime configuration.
  - Focused persistence/readiness suite passed: `61 passed, 2 skipped`.
  - Full regression passed: `1031 passed, 3 skipped`.
  - Python compilation, task-file trailing-whitespace scan, and `git diff --check` passed; Ruff is not installed in the project environment.
  - Live schema-qualified shadow preflight passed in read-only mode: all four `trading` tables found, migrations `001+002`, and all evidence row counts zero.

### Phase 8: Verification and next-phase gate

- **Status:** completed
- Gate result:
  - Durable LOCAL_PAPER audit/checkpoint slice is active and verified.
  - Full old-session pending-order/reservation/quote/UI hydration remains explicitly unclaimed and protected by the earlier Portfolio/FreshnessPolicy gate.
  - Backtest migration is independent of broker/account freshness and may proceed.

### Phase 9: Backtest SQLite to PostgreSQL migration

- **Status:** in_progress

## Session: 2026-08-21

### Phase 1: Repository and storage-contract discovery

- **Status:** completed
- **Started:** 2026-08-21
- Actions taken:
  - Preserved the explicit report/implementation-plan-only boundary.
  - Read the `planning-with-files` and `architecture-patterns` instructions and required references.
  - Restored existing planning context and confirmed another active plan must not be overwritten.
  - Reviewed prior repository storage inventory and relevant PostgreSQL raw-event lessons from a separate project as comparative evidence only.
  - Traced the trading journal schema, append/idempotency behavior, command-before-side-effect application flow, fill reducer, recovery, and checkpoint contracts.
  - Traced the canonical market-event record-before-ingest pipeline and its JSONL integrity/finalization contract.
  - Traced backtest migrations, resumable partition blobs, sealed dataset catalogs, run/result tables, and PostgreSQL adapter behavior.
  - Traced premarket and institutional content-addressed artifact stores plus Candidate Prior SQL persistence.
  - Cross-checked the portfolio architecture's mode-specific authority, database fail-closed, account locking, recovery, and projection contracts.
  - Cross-checked the canonical market pipeline's original JSONL-only scope, exact-replay semantics, same-callback shadow rule, and rollback contract.
  - Reconfirmed the active in-memory Journal/Simulation wiring, separate backtest database configuration, available PostgreSQL adapters, and market-data-only Shioaji boundary.
  - Refreshed the local storage snapshot and counted backtest, raw-event, premarket, institutional, and freshness evidence without mutating data.
  - Corrected the backtest status query against the actual schema and confirmed the date span, compressed payload size, paused download checkpoint, and stale `RUNNING` job.
- Files created/modified:
  - `.planning/2026-08-21-postgresql-persistence-report/task_plan.md`
  - `.planning/2026-08-21-postgresql-persistence-report/findings.md`
  - `.planning/2026-08-21-postgresql-persistence-report/progress.md`

### Phase 2: PostgreSQL placement decision

- **Status:** completed
- Actions taken:
  - Classified authoritative transactional facts, hybrid metadata/payload families, rebuildable projections, and data that should remain outside PostgreSQL.
  - Defined bounded contexts for trading, market data, backtest, and research/reference data.
  - Froze the no-competing-authority and database-failure fail-closed recommendations.

### Phase 3: Implementation plan authoring

- **Status:** completed
- Actions taken:
  - Authored `architecture/postgresql_data_persistence_report_and_implementation_plan.md`.
  - Defined dependency-ordered phases, backfill/cutover/rollback rules, acceptance gates, and a PostgreSQL verification matrix.

### Phase 4: Verification and delivery

- **Status:** completed
- Actions taken:
  - Re-read the complete report, checked the task-scoped worktree status, and ran whitespace validation.
  - Confirmed this task added only Markdown report/planning files and did not change runtime code, migrations, databases, configuration, or active-plan pointers.
  - Reconfirmed the pre-existing modified `.planning/.active_plan` still points to `2026-08-21-simulation-runtime-singleton-race`; this task did not overwrite it.

## Test Results

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Scope check | No product implementation | Planning files only so far | Pass |
| Current storage snapshot | Counts and sizes match read-only repository/database inspection | Confirmed | Pass |
| Report cross-check | Recommendations preserve Journal, exact-replay, broker-authority, and no-trade boundaries | Confirmed | Pass |
| Markdown whitespace | No whitespace errors in task files | `git diff --check` clean | Pass |
| Implementation baseline | Focused Journal/runtime/local-paper suite remains green before code changes | 37 passed, 1 skipped | Pass |
| Focused persistence tests | Typed config, pool lifecycle, composition, Journal/recovery tests pass | 51 passed, 2 skipped | Pass |
| Updated focused suite | Persistence plus shadow premarket schema/migration contract | 61 passed, 2 skipped | Pass |
| Full regression | Existing repository behavior remains green | 1031 passed, 3 skipped | Pass |
| Static verification | Compileall, whitespace scan, diff check | Clean | Pass |

| Backtest migration focused suite | New migration/config contracts plus existing Backtest download/resume regressions | 35 passed, 1 skipped (`TEST_POSTGRES_DSN`) | Pass |
| Backtest post-cutover focused suite | Migration plus Backtest core/download/resume/catalog regressions | 39 passed, 1 skipped | Pass |
| Post-cutover full regression | Entire repository behavior after Backtest activation | 1038 passed, 4 skipped | Pass |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-08-21 | Existing active plan belongs to another task | 1 | Used an isolated plan without changing the active-plan pointer. |
| 2026-08-21 | Broad multi-document architecture search produced truncated/noisy output | 1 | Switched to narrow, per-document contract searches. |
| 2026-08-21 | Runtime search included a non-existent `scanner` directory | 1 | Used the valid matches and limited later searches to discovered repository paths. |
| 2026-08-21 | SQLite job query referenced summary columns not present in the table | 1 | Inspect schema and query only existing fields. |
| 2026-08-21 | First implementation test run: injected Journal still parsed invalid environment; migration discovery expected only `001` | 1 | Skip environment selection when a Journal is injected and include `002_trading_schema.sql` in the contract assertion. |
| 2026-08-21 | Sandboxed pip could not resolve `psycopg-pool` | 1 | Used approved network access to install `psycopg-pool 3.3.1` into the project virtual environment. |
| 2026-08-21 | First dependency-install planning update used stale patch context | 1 | Re-read the live isolated plan and applied a smaller exact-context patch. |
| 2026-08-21 | Sandboxed local PostgreSQL preflight returned `Operation not permitted` | 1 | Re-ran with approved local-network access; read-only schema/count inspection passed. |
| 2026-08-21 | First live smoke checkpoint field compared `checkpoint == checkpoint` | 1 | Preserve valid append/idempotency evidence and run a corrected `latest_checkpoint()` comparison with a new synthetic session. |
| 2026-08-21 | Full suite: trade-management premarket fixture reported only `001`, causing `POSTGRES_MIGRATION_MISMATCH` | 1 | Align schema-qualified preflight and fixtures with the approved `trading` schema and `001+002` migration set. |
| 2026-08-21 | Combined Phase 9 backtest repository/migration read was truncated by the output limit | 1 | Continue with bounded per-file excerpts instead of one broad read. |
| 2026-08-21 | The generic `python` command was unavailable during a Phase 9 compile check | 1 | Standardize verification on `.venv/bin/python`. |
| 2026-08-21 | Two combined planning updates failed on a long table-line context | 1-2 | Switched to small single-hunk updates around short exact lines. |
| 2026-08-21 | First Backtest PostgreSQL preflight generated invalid SQL quoting | 1 | Corrected the read-only query construction and reran it successfully. |
| 2026-08-21 | Post-cutover planning update had stale context, then repeated one file twice in a patch | 1-2 | Re-read exact lines and applied one small update block per file. |

### Phase 9: Backtest SQLite to PostgreSQL migration

- **Status:** completed
- Actions taken:
  - Confirmed the application port covers normal backtest operations but not a full administrative export/import surface.
  - Confirmed the shared DB-API implementation currently uses unqualified SQL, so PostgreSQL schema ownership must be introduced without altering SQLite behavior.
  - Identified a dual-authority hazard: after migrations, the PostgreSQL adapter's shared schema bootstrap would recreate public tables unless its session is bound to the `backtest` schema.
  - Confirmed the forward-only migration must preserve the legacy `001`-`003` ledger, move ten public Backtest tables, and bind PostgreSQL sessions to `backtest, public`.
  - Confirmed stale download work can be reconciled to `PAUSED` without losing its partition checkpoint; already-paused work needs no transformation.
  - Checked file ownership: the adapter/migration/config targets are clean, while existing download implementation files have user changes and will remain untouched.
  - Selected the repository's existing opt-in PostgreSQL test pattern for destructive schema tests; the configured developer database will only receive non-destructive live copy/readback operations.
  - Added the forward-only `004_backtest_schema.sql`, logical-schema migration ledger, PostgreSQL `search_path`, and explicit backtest backend selection while retaining the legacy URL behavior.
  - Reconfirmed the actual SQLite schema before designing field conversion and verification.
  - Implemented a separate non-destructive migration service and CLI: read-only SQLite snapshot, batch/idempotent inserts, deterministic stale-job reconciliation, per-table count/content digests, and source-file immutability check.
  - Extended the test-environment boundary so the eventual local Backtest cutover cannot redirect ordinary tests into PostgreSQL during collection.
  - Added unit contracts for schema discovery, backend selection, stale-job reconciliation, and JSON/TIMESTAMPTZ/BYTEA digest normalization, plus an opt-in real PostgreSQL end-to-end migration test.
  - Reviewed the migration implementation and strengthened the source immutability gate to cover the SQLite WAL as well as the main database file.
  - Live read-only PostgreSQL preflight found no Backtest tables in either `public` or `backtest`, so the destination has no existing Backtest authority conflict.
  - Ran the live non-destructive copy: 22 strategy definitions, 6 jobs, and 678 compressed history partitions moved; all ten source/destination table counts and normalized content digests matched.
  - Reconciled stale job `dataset-job-08ebb8bd70394c3787ee22b6cd4176fe` to `PAUSED` only in PostgreSQL; source SQLite SHA-256 remained `cff72389331fe0b56fe828ef87d02cf157d17bdf08703f12e7caccf9874871fc` at 201,535,488 bytes.
  - PostgreSQL readback confirmed 18,187,718 bars, 200,010,553 compressed bytes, 2023-08-21 through 2026-08-18 coverage, migration versions `001`-`004`, and both resumable checkpoints.
  - Activated `BACKTEST_DATABASE_BACKEND=postgresql` in the gitignored local `.env` without duplicating the DSN.
  - Formal runtime smoke selected `PostgresBacktestRepository` and read back 6 jobs plus all 678 partitions for the preserved paused checkpoint.
  - Post-cutover focused regression passed 39 tests with only the explicit `TEST_POSTGRES_DSN` destructive integration test skipped.
  - Full post-cutover regression passed 1,038 tests with 4 explicit skips; compileall remained clean.
  - Re-ran the live migration against the populated destination; all ten table counts/digests remained identical, proving idempotent cutover behavior.
  - Updated the report and README with the logical-schema contract, migration command, measured live evidence, rollback archive rule, and remaining Market Event/Artifact gates.
  - Final whitespace validation is clean; task-scoped status review preserves unrelated dirty worktree changes.
  - Confirmed package inclusion for Backtest SQL migrations and live absence of competing public Backtest tables after runtime startup.

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 10, documenting verified cutover evidence and the remaining market-event/artifact gates |
| Where am I going? | Finish documentation/static review without inventing market retention values or widening broker scope |
| What's the goal? | Implement the approved PostgreSQL persistence plan in dependency order without expanding broker scope |
| What have I learned? | See `findings.md` in this plan directory |
| What have I done? | Completed and verified both the LOCAL_PAPER Journal cutover and the Backtest SQLite-to-PostgreSQL migration |
