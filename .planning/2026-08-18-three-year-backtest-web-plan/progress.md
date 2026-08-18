# Progress: Three-year historical backtest web workflow

## Session: 2026-08-18

- Started a plan-only task for a web-executable, three-year Taiwan-stock strategy backtest.
- Read the planning, architecture, and dashboard skill guidance.
- Restored relevant repository memory and confirmed another planning task is active.
- Created an isolated planning directory without changing `.planning/.active_plan`.
- Inventoried repository files, package configuration, README contracts, and dirty-worktree state.
- Confirmed the existing replay is signal-oriented and the existing local paper simulator is not yet a cost-aware historical portfolio backtester.
- Traced the immutable replay manifest, event normalization, Momentum feature/signal/state path, and its current alert-only/risk-blocked output.
- Traced the local simulator, dashboard interaction model, and on-demand Kbar path; recorded why none can be scaled directly into a trustworthy market-wide three-year run.
- Traced Candidate, scoring, exit, runtime, journal, and architecture-plan contracts; identified the missing historical timing and complete-strategy definition.
- Verified current official Shioaji historical coverage and request/traffic constraints, plus current Taiwan transaction-cost/corporate-action concerns, for the data and cost-model gates.
- Authored `architecture/three_year_backtest_web_implementation_plan.md` with data profiles, strategy semantics, execution/cost rules, metrics, job/API/UI contracts, scale rollout, tests, rollback, file map, and Definition of Done.
- Cross-checked that the first legacy strategy preserves current HighVolume logic and that Momentum capability limitations are explicit.
- Completed all planning phases without implementing product behavior.

## Extension session: multi-strategy and experiment history

- Captured the new requirements: entry/exit strategies must be multi-select, every simulated buy/sell must show the triggering strategy name(s), and all runs must persist for later effectiveness comparison.
- Reopened the isolated plan with Phases 6–8; product implementation remains out of scope for this turn.
- Extended the standalone plan with independent entry/exit strategy sets, ANY／ALL／AT_LEAST_N aggregation, one-decision/order deduplication, and complete per-trade strategy attribution.
- Replaced the local-first persistence target with PostgreSQL for platform runs while retaining immutable Parquet market data and SQLite only for dev/test.
- Added experiment lineage, baseline/challenger cloning, comparability guards, KPI/trade/config diffs, clustered delta confidence intervals, and a Web comparison workflow.
- Updated APIs, database tables/constraints, file map, implementation phases, test matrix, migration/rollback, and Definition of Done.
- Completed the plan-only extension without implementing product behavior.

## Implementation authorisation: 2026-08-18

- User authorised direct implementation through the architecture plan's Phase 8.
- Reopened the isolated plan with execution phases 0–8 while preserving the repository's separate active planning task and all unrelated dirty worktree changes.
- Restored session context and inspected the active FastAPI, provider, local-simulation, PostgreSQL migration, dependency, UI, and test seams.
- Confirmed the backtest feature can use the existing provider Kbar contract without crossing into SimulationService, Shioaji order APIs, CA, or trade subscriptions.
- Implemented the isolated `backtest/` bounded context: immutable JSONL datasets/manifests, checksums, provider-backed background acquisition, imported-data support, and coverage labels.
- Implemented versioned entry/exit strategies, ANY/ALL/AT_LEAST_N aggregation, next-bar Decimal fills, costs, daily equity, OOS metrics, strategy attribution, immutable SQLite/PostgreSQL persistence, clone lineage, and comparison projections.
- Added the FastAPI backtest namespace and a top-level Traditional-Chinese historical-backtest workspace with dataset preparation, multi-select strategies, progress, cancellation/retry, result drill-down Kbars, CSV export, and baseline/challenger comparison.
- Verified source compilation, browser JavaScript syntax, five focused backtest/API contracts, ten-run deterministic output/digest equality, full suite (`287 passed, 1 skipped`), and a local server/browser smoke at `127.0.0.1:8011`.
- The local-browser smoke only read the live dashboard and backtest capability/strategy endpoints. It did not start a historical acquisition or create an order. The existing dashboard snapshot path did log in to the configured Shioaji simulation provider; no order API was called.
- Added `scripts/import_backtest_dataset.py` so reviewed date-effective JSONL data can be sealed and registered without a browser upload, then immediately selected by the Web workspace. Its direct documented invocation and import contract are verified.

## Unified catalog selector session: 2026-08-18

- Read the referenced strategy-inventory task and verified its claims against the current checkout.
- Confirmed the historical run contract already stores independent entry/exit strategy-id arrays and supports ANY, ALL, and AT_LEAST_N aggregation.
- Started Execution Phase 9 to reconcile catalog metadata with executable bindings and make single/multi selection explicit and testable in the Web workflow.
- Added fail-closed catalog/runtime reconciliation: catalog-only strategies remain visible in the strategy catalog with an unavailable reason, while the backtest selector receives only exact server-side executable ENTRY/EXIT definitions.
- Added immutable strategy-set validation for empty, duplicate, and unknown-priority ids so duplicate selections cannot inflate aggregation counts.
- Added selected-count badges, explicit single/multi copy, dynamic `AT_LEAST_N` enabling/max/clamping, and client-side policy validation to the historical-backtest form.
- Added domain, API, catalog, and static-UI tests. API fixture runs cover one-entry/one-exit and two-entry/two-exit configurations.
- Verified focused tests (`12 passed`), browser interaction with MockProvider, JavaScript syntax, whitespace, and the full suite (`295 passed, 1 skipped`).
- Stopped the temporary local server after validation; no Provider dataset download or order submission occurred.

## Standalone historical downloader session: 2026-08-18

- User reported that the browser-triggered three-year download takes too long and requested a script that persists the result for later backtests.
- Reopened the historical-backtest plan as Execution Phase 10 and preserved the separate active-plan pointer and unrelated dirty worktree changes.
- Started inventorying the current provider collector, immutable JSONL data store, SQLite/PostgreSQL catalog, and existing import script before implementation.
- Added database schema and repository methods for gzip-compressed, checksum-addressed per-symbol history partitions in both SQLite (`BLOB`) and PostgreSQL (`BYTEA`).
- Added a streaming dataset sealer so finalization reads one database partition at a time instead of rebuilding the previous all-symbol in-memory list.
- Added `ResumableHistoricalDownloader` and `scripts/download_backtest_history.py`; the CLI prints a durable job id, checkpoints after each symbol, supports `--resume`, and explicitly closes the data-only Provider.
- Enabled SQLite WAL and a bounded busy timeout so the dashboard can continue reading while the standalone downloader commits short partition transactions.
- Verified Python compilation and the CLI help contract before adding behavioral tests.
- Added failure/resume contracts proving an already checkpointed symbol is skipped after a transient provider error; added a complete two-symbol dataset registration contract.
- Added README commands for limited Shioaji validation, all-current-symbol download, `--resume`, SQLite/PostgreSQL selection, and the warning not to run Web and CLI acquisition concurrently.
- Ran an isolated Mock CLI end to end: two database partitions, 522 Kbars, checksum-valid immutable dataset, READY registration, and idempotent completed-job resume.
- Reduced final sealing memory to constant session counters plus one decompressed symbol partition at a time.
- Completed Python compilation, focused tests (`3 passed`), full suite (`299 passed, 1 skipped`), and whitespace validation without making any live Provider request.
