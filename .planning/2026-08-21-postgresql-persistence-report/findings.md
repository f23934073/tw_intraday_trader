# Findings: PostgreSQL data persistence report

## Requirements

- Decide which current and future data should be persisted in PostgreSQL.
- Cover historical data, intraday information, orders, fills, positions, and adjacent research/evidence data.
- Produce a reviewable report and implementation plan only.
- Ground recommendations in the current checkout and current storage contents.
- The user has now explicitly authorized implementation from the updated report.
- User-edited decisions freeze the first implementation direction as one PostgreSQL database with logical schemas (`ok`) and Portfolio scope as `LOCAL_PAPER` only.
- User also approved evidence-based market-event retention (no guessed 30/90-day value), keeping history payloads in the local content-addressed directory, and migrating existing unqualified tables into logical schemas.
- The report's old "本次不實作" section and `Review requested` status are now stale relative to the user's explicit implementation authorization and should be revised as implementation documentation.
- The earlier FreshnessPolicy gate still prohibits inventing thresholds or implementing broker/account-backed Portfolio behavior. The first slice can safely implement database configuration, logical schema migration, the existing Journal adapter, and explicit LOCAL_PAPER durability wiring without adding broker/account reads.
- No repository `AGENTS.md` files were found. Existing global/root planning state belongs to other active work and remains untouched.

## Initial Evidence

- Historical backtest metadata, resumable Kbar partitions, and future run results already use a `BacktestRepository` with SQLite and PostgreSQL adapters.
- Current local history is in `data/backtest/backtest.sqlite3`; it contains resumable partitions but no sealed dataset or backtest runs.
- Dashboard scan state, history cache, Momentum state, local-paper orders, positions, quotes, and journal are process-local memory.
- Raw market-event capture currently writes JSONL session directories under `records/market_events`.
- Premarket context and institutional research use immutable content-addressed files.
- A separate PostgreSQL journal schema exists, but the current Dashboard composition injects `InMemoryJournalRepository`; the verified PostgreSQL evidence tables are empty.
- Shioaji remains market-data-only with `subscribe_trade=False`; there is no real broker order/deal/account ingestion path.
- Current 2026-08-21 snapshot: `data/backtest` is about 208 MB and contains 6 jobs, 678 history partitions, and 18,187,718 bars, but zero sealed datasets, runs, results, decisions, or trades.
- Those 678 partitions cover 2023-08-21 through 2026-08-18 and store about 190.74 MiB of compressed payload. The current resumable download is `PAUSED` at 678/2738; a separate older job is still marked `RUNNING` at 407/2738 despite no recent progress and needs explicit reconciliation during migration.
- Current raw market-event capture is about 5.3 MB across 6 sessions: 3 `FINALIZED` and 3 `INCOMPLETE`. Incomplete sessions must not be imported as complete replay evidence.
- Current file artifacts are modest but already distinct evidence families: `data/premarket` about 5.4 MB/129 files, `research/institutional_evaluation` about 5.4 MB/126 files, and `research/captures/freshness_quote` about 4.3 MB/7 files.

## Repository Findings

- `trading/migrations/001_journal.sql` already provides the right canonical spine for trading facts: immutable session metadata, append-only records, global sequence, per-session record identity, scoped idempotency uniqueness, JSONB payloads, and projection checkpoints.
- `OrderApplicationService` records the risk decision and complete risk snapshot before invoking the side-effect adapter. Handler failure and later terminal outcomes are also journal events, so PostgreSQL cutover should reuse this port rather than invent an ORM-owned command path.
- `LocalPaperProjection` proves positions, cash, and realized PnL can be rebuilt from journal fills and validated against a checkpoint digest. Therefore portfolio tables are read models, not a second write authority.
- Current `PostgresJournalRepository` commits each append separately. A production cutover needs explicit unit-of-work boundaries where required, connection pooling, retry classification, and operational health checks; it must not retry an already-applied simulator/broker side effect blindly.
- The canonical market-data pipeline is explicitly record-before-ingest and closes admission on recorder failure. This contract is stronger than the current file location and is suitable for a PostgreSQL recorder adapter.
- Current JSONL market journals preserve full canonical envelopes, lifecycle incidents, deterministic dispositions, contiguous indexes, SHA-256, projection digests, and FINALIZED/INCOMPLETE state. Any PostgreSQL schema must preserve all of those semantics, not merely Tick prices.
- The original P1 canonical-pipeline scope deliberately excluded a PostgreSQL event store and named JSONL as the local research/shadow authority. A PostgreSQL rollout is therefore a new adapter/cutover phase, not a silent reinterpretation of the already approved P1 plan.
- Exact-replay cutover already requires old authority, same-callback shadow evidence, digest comparison, and explicit cutover. The PostgreSQL plan should reuse that gate and must not open a second Shioaji subscription owner for comparison.
- Market ingress and disposition rows are naturally related but have different query shapes. PostgreSQL should retain a session-local monotonic record index and a unique event identity, then index session/date/symbol/stream/event time without replacing the canonical payload contract.
- Backtest storage already separates database metadata/results from sealed immutable dataset files. PostgreSQL is a clear fit for jobs, dataset catalog rows, strategy definitions, runs, decisions, trades, equity curves, comparisons, and idempotent job claims.
- `backtest_history_partitions.bars_payload` is a resumable checkpoint blob. It is acceptable as a transitional/local design, but indefinite multi-dataset BYTEA accumulation would duplicate sealed `bars.jsonl` payloads and bloat backups. A production design should store partition payloads in content-addressed object/file storage and retain URI, digest, row count, and lifecycle in PostgreSQL; temporary BYTEA can remain a first cut with cleanup after seal.
- Sealed historical Kbar datasets are immutable, streaming-verified artifacts. They should remain outside row-oriented operational tables unless a separate analytical-query requirement justifies a normalized bar store.
- Premarket raw/context/reconciliation artifacts are content-addressed, digest-validated, append-only files. PostgreSQL should index artifact identity, session, status, lineage, and active/latest resolution, while the canonical payload remains file/object content.
- Institutional raw source bytes have the same immutable content-addressed character. Normalized institutional flow rows and validated partition manifests are queryable facts and should move to PostgreSQL; raw response bytes should remain object/file payloads with a PostgreSQL catalog.
- Candidate Prior already has SQLite/PostgreSQL repositories and strong deterministic identity/parity checks. Its artifacts and ranked entries belong in PostgreSQL once used by a shared runtime, while their EXPLORATORY and execution-disabled checks must remain enforced.
- The runtime composition still defaults to `InMemoryJournalRepository` and `SimulationService`; merely having `PostgresJournalRepository` and SQL migrations does not make PostgreSQL the active durability path.
- `RuntimeComposition.create()` already accepts a `JournalRepository` port and routes manual/strategy LOCAL_PAPER commands through `LocalPaperCommandService`; the smallest cutover is infrastructure configuration plus repository injection, not a new domain service.
- Runtime shutdown currently closes the simulation and provider but not a database-backed Journal, so a durable adapter needs an explicit lifecycle boundary.
- `PostgresJournalRepository` currently owns one externally supplied connection, uses unqualified public-table SQL, commits each repository method, and has no health/close API. Existing application code relies on journal-first append semantics, so retries must stay outside any possibly applied side effect.
- The current migration runner and `001_journal.sql` create the migration ledger and Journal tables in the default schema. A backward-compatible `002` migration plus a schema-qualified adapter can move already-created public tables into the approved `trading` logical schema without rewriting the recorded `001` migration.
- `tests/test_postgres_journal.py` already provides a real PostgreSQL gate through explicit `TEST_POSTGRES_DSN`; its cleanup and assertions must be updated for schema-qualified objects and expanded to cover migration from the legacy public layout.
- PostgreSQL remains an optional dependency (`postgres` extra with psycopg 3.2+). Runtime configuration must fail clearly when durable mode is requested without that extra, rather than silently using memory.
- `LocalPaperCommandService` already writes `order_command.v1` before simulator mutation, then records fills/rejections and cancellation intent/outcome. It does not currently record an acknowledged-but-pending `SUBMITTED` outcome, and it keeps command correlation in process memory.
- `LocalPaperProjection` can deterministically rebuild cash, positions, and realized PnL from fill records and verify a checkpoint, but it intentionally does not rebuild the legacy `SimulationService` order book, reservations, quote state, or idempotency maps.
- Therefore merely switching the Journal adapter makes evidence durable but does not satisfy full restart recovery of pending orders/UI state. The first slice must state this honestly; a later recovery slice needs an explicit simulator hydration contract and additional immutable order lifecycle records before durable runtime can claim restart-safe mutation.
- Existing config patterns use immutable dataclasses with `from_environment()` validation. A new trading persistence config should follow that pattern, default to explicit memory mode, require a DSN for PostgreSQL mode, and never infer broker capabilities from the DSN.
- Live preflight against the configured local PostgreSQL confirmed the legacy layout is unambiguous and empty: all three Journal tables exist only in `public`, each with 0 rows; no corresponding `trading` table exists. The approved forward-only schema move therefore has no dual-authority/data-merge conflict in this environment.
- Live migration applied only `002_trading_schema.sql`, retained both migration ledger versions, removed the public Journal-table authority, and exposed all three tables under `trading` as intended.
- A pooled synthetic Journal smoke proved append and idempotent replay (`record_count=1`, retry idempotent) and removed its synthetic rows. Its first printed checkpoint boolean accidentally compared the object to itself, so checkpoint readback still requires a corrected live assertion before being counted as evidence.
- The corrected live smoke proved `latest_checkpoint()` roundtrip through the pool-backed adapter; the synthetic session was removed afterward. PostgreSQL sequences correctly remained monotonic after row cleanup.
- Strategy flow writes an intent record before the command/fill records. Replaying the complete bounded LOCAL_PAPER session when writing a checkpoint safely includes these non-fill sequence steps; a fill-only incremental tracker would miss them unless every writer shared one projection coordinator.
- The repository's gitignored `.env` already provides only the legacy `PostgreSQL_DSN` key, and `app.py` loads it before dashboard composition. Adding only `TRADING_JOURNAL_BACKEND=postgresql` activates the new adapter without duplicating or exposing the DSN.
- Dashboard composition is lazy and the FastAPI lifespan closes it, so the pool lifecycle is owned by the existing composition shutdown path. Backtest initialization remains separate and will not inherit `DATABASE_URL` until its later migration phase.
- The formal composition smoke with the gitignored durable-mode flag selected `PostgresJournalRepository`, created a sequence-0 checkpoint with `journal_backend=POSTGRESQL` and `restart_policy=NEW_LOCAL_PAPER_SESSION`, closed the pool, and removed the synthetic session.
- Because `app.py` loads developer `.env` during many tests, the suite needs an autouse test boundary that forces `TRADING_JOURNAL_BACKEND=memory`; explicit config and PostgreSQL integration tests still override/inject their own adapter and do not accidentally mutate a developer database.
- Full-suite regression found one expected contract drift in the separate trade-management premarket readiness artifact: its test fixture still advertised only `001_journal.sql`, while the CLI now correctly discovers both `001` and `002`. The readiness preflight also needs schema-qualified table discovery/counts so it validates the new `trading` authority rather than public names.
- After aligning the readiness contract with `trading` and `001+002`, the focused suite passed 61 tests (2 explicit PostgreSQL-test skips) and the complete repository suite passed 1,031 tests (3 skips).
- The updated live shadow preflight confirmed the final state in a read-only transaction: tables `journal_records`, `journal_schema_migrations`, `journal_sessions`, and `projection_checkpoints`; migrations `001_journal.sql` and `002_trading_schema.sql`; all three evidence counts zero.
- Backtest database selection is independently controlled by `BACKTEST_DATABASE_URL`, while trading evidence uses a separate PostgreSQL DSN convention. Implementation should normalize typed configuration and schema ownership without putting secrets into artifacts or reports.
- All inspected Shioaji market-data paths keep `subscribe_trade=False`; this persistence plan must not be interpreted as authorization to activate broker account/order/deal capabilities.
- The approved portfolio architecture already freezes the intended authority split: PostgreSQL Journal is the complete accounting/order authority for `LOCAL_PAPER`; in broker-backed modes the broker remains execution/account authority while PostgreSQL provides audit, idempotency, recovery, reconciliation evidence, and local projections.
- Portfolio mutations must fail closed when PostgreSQL is unavailable. Browser caches or the in-memory simulator must never become an emergency write fallback.
- Orders, fills, cash ledger entries, reservations, account revisions, reconciliation state, and lifecycle events need one account-level transaction boundary. Order/position summary tables are indexed projections from those facts, not independent command stores.
- The Backtest port exposes job/dataset/partition/run/result/comparison operations, while `_JsonBacktestRepository` currently emits unqualified table names and owns one direct DB-API connection. Logical-schema cutover therefore needs an adapter-level PostgreSQL qualification mechanism without changing SQLite SQL.
- The shared repository already supports partition-by-partition payload iteration and idempotent upserts, but it does not expose a complete administrative export/import contract. A migration command should use explicit source/destination table mappings and verification rather than pretending the public application port covers every row family.
- `PostgresBacktestRepository` currently applies forward migrations and then re-applies the shared unqualified `_SCHEMA`; without a PostgreSQL `search_path` or qualification fix, a new logical-schema migration would silently recreate competing public tables.
- The PostgreSQL adapter owns a direct connection rather than a pool. The narrow cutover can keep that lifecycle while setting `search_path` to `backtest, public` after forward migrations; SQLite remains unchanged because only the PostgreSQL adapter applies that session setting.
- PostgreSQL migrations `001`-`003` are public/unqualified and the legacy migration ledger is also public. A forward-only `004` must move all ten Backtest tables, while the runner first creates `backtest.backtest_schema_migrations` and copies legacy ledger entries so an installed database does not replay old migrations against the wrong authority.
- `BACKTEST_DATABASE_URL` is independently selected and the current application switches based on its URL prefix. For this single-database deployment, an explicit backtest backend flag can reuse the existing secret aliases only after copy verification, avoiding a duplicated DSN in `.env` and preventing accidental early cutover.
- Job status already supports `PAUSED`; the download/resume code treats it as a resumable terminal state. The stale source `RUNNING` row can therefore be deterministically copied as `PAUSED` with its checkpoint preserved, while the existing `PAUSED` row remains byte/field equivalent.
- The Backtest repository, PostgreSQL adapter, migration runner, and config files are not part of the user's pre-existing dirty edits. `backtest/historical_download.py` and `scripts/download_backtest_history.py` are dirty, so Phase 9 must avoid touching them and add a separate migration command.
- Existing PostgreSQL Journal tests provide a safe pattern for legacy-public-to-logical-schema migration coverage, but Backtest currently has no PostgreSQL migration/integration tests. Phase 9 needs both pure migration-contract tests and an opt-in `TEST_POSTGRES_DSN` integration test to avoid using the developer database destructively.
- The live SQLite schema exactly matches the ten-table Backtest contract and stores JSON/timestamps as TEXT plus partition payloads as BLOB. The copy layer must normalize JSON for PostgreSQL JSONB and parse only the four TIMESTAMPTZ columns introduced by migrations (`strategy_definitions` and `backtest_history_partitions` created/updated timestamps).
- The migration can be safely resumable with `ON CONFLICT DO NOTHING` only if every run finishes with a full ordered row digest comparison; an interrupted partial copy is allowed to remain, but it is never eligible for cutover until counts and normalized content digests match across all ten tables.
- Because `app.py` loads the developer `.env` during test collection, the Backtest cutover flag requires the same explicit test isolation already used for the Journal. Setting SQLite before test-module imports prevents a local workstation's PostgreSQL selection from leaking into unit/API tests.
- A stable SQLite snapshot also requires detecting WAL changes, not only hashing the main `.sqlite3` file. The migration now fingerprints both the main file and any `-wal` file before/after copy so concurrent source writes block cutover.
- Live read-only preflight found zero Backtest tables in both `public` and `backtest`; the configured single PostgreSQL database is an empty Backtest destination and does not require a merge/conflict decision.
- Live copy completed in 17 seconds. PostgreSQL parity passed for all ten tables; non-empty families are 22 `strategy_definitions`, 6 `backtest_jobs`, and 678 `backtest_history_partitions`. The source file stayed unchanged at 201,535,488 bytes with SHA-256 `cff72389331fe0b56fe828ef87d02cf157d17bdf08703f12e7caccf9874871fc`.
- PostgreSQL readback confirms 18,187,718 bars, 200,010,553 compressed payload bytes, and coverage from 2023-08-21 through 2026-08-18. The 407/2738 stale job is now `PAUSED`; the 678/2738 active checkpoint remains `PAUSED` with its exact progress/message.
- The local `.env` already activates PostgreSQL only for the Trading Journal. Backtest can now be cut over by adding the backend flag alone; the existing shared DSN remains secret and does not need duplication.
- After enabling the local Backtest flag, formal composition selected `PostgresBacktestRepository`, returned all 6 jobs, preserved the active paused progress `0.24762600438276114`, and returned all 678 partition checkpoints. The test suite remains isolated on SQLite.
- A second live run against the already-populated PostgreSQL destination produced the same ten table counts and digests, demonstrating that conflict-safe inserts plus full verification are operationally idempotent rather than only theoretically resumable.
- Package data already includes `backtest/migrations/*.sql`, so `004_backtest_schema.sql` ships with installed builds. Final live inspection after composition startup confirms no `public` copies of jobs, partitions, or strategy definitions were recreated; only `backtest.*` authority exists.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Separate authoritative facts from rebuildable projections | Prevents projection tables from becoming conflicting write authorities. |
| Keep large immutable artifacts eligible for file/object payload storage | PostgreSQL should index lineage and status without necessarily storing every raw byte twice. |
| Require real PostgreSQL integration tests | SQLite and mock DB behavior do not prove PostgreSQL transaction, conflict, JSONB, or partition behavior. |
| Reuse the existing Journal and MarketEventRecorder ports | The domain/application layers already avoid database imports; PostgreSQL belongs in adapters and composition. |
| Treat journal records as canonical and position/order screens as projections | Restart recovery and replay parity are already expressed in the repository's reducer/checkpoint design. |
| Use PostgreSQL as artifact catalog, not universal blob warehouse | Large immutable historical/raw source payloads have stronger content-addressed file semantics and cheaper archival/verification outside OLTP tables. |
| Put normalized institutional facts in PostgreSQL | Candidate generation needs indexed, point-in-time queries over market/session/symbol and validated lineage. |
| Treat PostgreSQL market-event persistence as a new adapter phase | The existing P1 contract intentionally scoped the event store to JSONL and preserved precise replay/failure semantics that the new adapter must prove before authority cutover. |
| Preserve the existing `JournalRepository` port | Configuration/composition should select the adapter; application/domain code must not import psycopg or SQL. |
| Migrate with a new forward-only SQL file | Do not edit the already-recorded `001` semantics; a new migration can move legacy public tables and fresh-install tables to `trading`. |
| Separate durable evidence cutover from full simulator recovery | Persisting Journal records is safe now; enabling restart-safe order mutation requires additional lifecycle events and hydration semantics rather than pretending the fill-only reducer restores pending state. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Repository has broad unrelated dirty changes | Limit this task to a new isolated planning directory and one new architecture report. |
| One broad architecture search exceeded useful output limits | Split review into narrowly scoped, per-file contract searches and record only decision-relevant evidence. |
| A targeted runtime search included one non-existent `scanner` path | Kept the valid results and restricted subsequent searches to paths returned by `rg --files`. |
| First detailed job-status query assumed non-existent summary columns | Inspect the actual SQLite table definition before issuing the narrower read-only query. |
| One combined Phase 9 read exceeded the available output budget | Inspect each backtest adapter and migration in bounded excerpts before changing the storage contract. |

## Resources

- `runtime/composition.py`
- `trading/journal.py`
- `trading/postgres_journal.py`
- `backtest/repository.py`
- `backtest/postgres_repository.py`
- `market_data/journal.py`
- `premarket/artifacts.py`
- `institutional_data/artifacts.py`
- `architecture/postgresql_data_persistence_report_and_implementation_plan.md`

## Visual/Browser Findings

- None; this task is repository and database-contract analysis.
