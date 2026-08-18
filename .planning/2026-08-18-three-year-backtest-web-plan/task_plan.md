# Task Plan: Three-year historical backtest web workflow

## Goal

Produce an implementation-ready plan for running the repository's existing strategy over the latest three years of Taiwan market history from the web dashboard, with reproducible buy/sell simulation and trustworthy win-rate/performance evidence.

## Current Phase

Execution Phase 10 — complete

## Phases

### Phase 1: Repository and data-contract discovery

- [x] Trace the current strategy, replay, simulation, dashboard, persistence, and historical-data boundaries.
- [x] Identify what can be reused and what is missing for a credible three-year backtest.
- [x] Record current worktree constraints and preserve unrelated changes.
- **Status:** complete

### Phase 2: Backtest semantics and trust model

- [x] Define universe, date range, adjustment, trading calendar, signal timing, fill timing, fees, taxes, slippage, liquidity, and corporate-action rules.
- [x] Define metrics and validation that answer whether buy/sell rules meet a target win rate without relying on win rate alone.
- [x] Define data provenance, immutable manifests, coverage gates, and no-look-ahead controls.
- **Status:** complete

### Phase 3: Backend and storage architecture

- [x] Define domain objects, application use cases, ports/adapters, job lifecycle, persistence schema, and cancellation/recovery behavior.
- [x] Map changes to concrete repository files while reusing the existing replay and simulation seams.
- [x] Define performance and scalability strategy for all eligible symbols across three years.
- **Status:** complete

### Phase 4: Web workflow and dashboard design

- [x] Define the backtest setup form, progress/status experience, result summary, drill-down views, trade details, and export behavior.
- [x] Define API contracts and frontend state/error/accessibility behavior.
- [x] Define metric reconciliation and visible data-quality caveats.
- **Status:** complete

### Phase 5: Delivery plan and acceptance gates

- [x] Write the standalone implementation plan with dependency order, milestones, tests, migration/rollback, and Definition of Done.
- [x] Separate a usable first slice from the full three-year market-wide target.
- [x] Verify this turn changes planning documentation only.
- **Status:** complete

### Phase 6: Multi-strategy decision model

- [x] Define independently selectable entry and exit strategy sets.
- [x] Define ANY／ALL／AT_LEAST_N aggregation, conflict priority, deduplication, and deterministic attribution.
- [x] Ensure every decision, order, fill, and trade identifies all triggered strategy names and versions.
- **Status:** complete

### Phase 7: Durable experiment and comparison model

- [x] Replace local-first result storage with an authoritative PostgreSQL repository for platform mode.
- [x] Define immutable strategy versions, run lineage, baseline/challenger links, parameter diffs, and comparison metrics.
- [x] Define retention, migration, reconciliation, and reproducibility requirements.
- **Status:** complete

### Phase 8: Web multi-select and comparison workflow

- [x] Define buy/sell strategy multi-select controls and aggregation-policy validation.
- [x] Add per-trade strategy attribution and baseline-versus-adjusted comparison views.
- [x] Update API, file map, tests, gates, rollback, and Definition of Done.
- **Status:** complete

## Authorised implementation execution

The user authorised implementation on 2026-08-18 with: `process, 直接幫我做完做到Phase 8`. The phases below track code delivery; they do not replace the completed architecture-plan phases above.

### Execution Phase 0: Foundation and compatibility inventory

- [x] Inspect current provider, dashboard, runtime, simulation, migrations, and test conventions before touching overlapping files.
- [x] Define a feature-flagged backtest composition that cannot activate broker/CA/live-order paths.
- [x] Record executable verification commands and external-data constraints.
- **Status:** complete

### Execution Phase 1: Historical dataset foundation

- [x] Add immutable local historical-bar catalog, manifest, validation, and provider acquisition seam.
- [x] Support fixture/imported data immediately and provider-backed collection only through server-side jobs.
- [x] Add coverage/capability reporting with fail-closed behavior.
- **Status:** complete

### Execution Phase 2: Deterministic multi-strategy kernel

- [x] Add versioned entry/exit definitions, strategy-set snapshots, evaluations, deterministic aggregation, and no-look-ahead execution intents.
- [x] Implement baseline Gap/VWAP, Momentum-compatible, StopLoss, TakeProfit, and EOD adapters.
- [x] Add synthetic tests for aggregation, attribution, and timing.
- **Status:** complete

### Execution Phase 3: Execution, costs, and ledger

- [x] Add Decimal bar-fill model, cost model, cash/position ledger, fills, closed trades, and daily equity.
- [x] Carry decision attribution from entry through exit and prevent duplicate orders/oversell.
- **Status:** complete

### Execution Phase 4: Metrics and comparison

- [x] Add win rate, OOS split, return/drawdown/profit-factor/expectancy, strategy funnels, and comparison verdicts.
- [x] Add baseline/challenger config compatibility and trade/config deltas.
- **Status:** complete

### Execution Phase 5: Durable repository and jobs

- [x] Add repository port, local SQLite development adapter, PostgreSQL production adapter/migrations, job lifecycle, and immutable run lineage.
- [x] Add API-safe job coordination without blocking FastAPI requests.
- **Status:** complete

### Execution Phase 6: API surface

- [x] Add feature-flagged dataset, strategy-set, run, result, attribution, clone, and comparison endpoints.
- [x] Add controller/API contract tests and stable error responses.
- **Status:** complete

### Execution Phase 7: Web workspace

- [x] Add historical-backtest navigation, setup controls, job list/progress, result dashboard, and trade drill-down.
- [x] Add entry/exit multi-select and aggregation controls with Chinese labels.
- **Status:** complete

### Execution Phase 8: End-to-end verification and operational handoff

- [x] Add comparison UI, browser/static checks, focused tests, and README operation/verification instructions.
- [x] Run deterministic local fixture backtest end-to-end; document the remaining credential/quota gate for real three-year acquisition.
- **Status:** complete

### Execution Phase 9: Unified catalog single/multi-strategy integration

- [x] Reconcile the unified strategy catalog with the server-side executable backtest registry.
- [x] Make entry and exit controls explicitly support one or many selected strategies, with selected counts and valid aggregation inputs.
- [x] Add API, domain, and UI contracts proving both single-strategy and multi-strategy runs.
- [x] Run focused and full-suite verification without consuming provider quota or placing orders.
- **Status:** complete

### Execution Phase 10: Standalone resumable historical-data download

- [x] Inspect the current browser job, provider windows, dataset files, and database catalog contract.
- [x] Add a server-independent CLI that persists progress, supports safe restart, and registers a READY dataset in SQLite or PostgreSQL.
- [x] Ensure partial downloads remain recoverable and final sealing remains checksum-verified and immutable.
- [x] Add focused CLI/resume tests and document exact commands for Shioaji and MockProvider.
- [x] Run focused and full-suite verification without downloading live data during tests.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|---|---|
| Keep this as a plan-only turn | The user explicitly requested an implementation plan before coding. |
| Use an isolated planning directory | The repository has another active planning task and concurrent uncommitted work. |
| Treat win rate as one metric, not the sole pass criterion | A high win rate can still lose money when losses are larger than wins or costs are omitted. |
| Keep provider/data access and strategy execution server-side | The existing dashboard contract and auditability require the browser to submit jobs and read projections only. |
| Deliver full-market Kbar backtest before claiming exact live Momentum parity | Shioaji historical Kbars can support a bar-based all-market run, while historical L1 does not contain the live five-level BidAsk stream. |
| Preserve the current HighVolume formula in the first legacy strategy version | Replacing it with RVOL would measure a different strategy; RVOL receives a separate strategy id. |
| Separate Signal Study from Portfolio Simulation | Strategy hit rate and capital-constrained account performance answer different questions and must not share a denominator. |
| Use immutable Parquet for historical market data and PostgreSQL for authoritative platform records | Large market history remains outside the operational database, while durable runs, evidence joins, lineage, and concurrent comparison queries require platform-grade persistence. |
| Model entry and exit as separate versioned strategy sets | A selected buy condition and a selected sell condition have different lifecycle roles and must be attributable independently. |
| Default aggregation to ANY while supporting ALL and AT_LEAST_N | The user explicitly wants a trade when any selected strategy reaches its condition, while preserving stricter combinations as configuration. |
| Persist platform-mode run history in PostgreSQL | Durable run lineage, evidence joins, concurrent reads, and baseline/challenger comparison are platform concerns; SQLite remains a development/test adapter only. |
| Implement a fixture/imported-data path before live three-year acquisition | The product and its no-look-ahead/accounting semantics can be tested without provider credentials; actual market-wide three-year acquisition remains a separately observable quota/coverage gate. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| None | — | — |
| Fixture smoke used a shell-local temp variable that was not exported | 1 | Re-run the application smoke with Python `TemporaryDirectory`, which owns the fixture path directly. |
| API-style string monetary inputs reached `BacktestRunConfig` without Decimal normalization | 2 | Normalize all monetary/rate fields in the frozen config value object's `__post_init__`. |
| `fastapi.testclient` could not collect because this environment lacks its optional HTTP client package | 3 | Retain controller-level API contracts without adding a test-only network dependency; browser and local HTTP smoke cover route serving. |
| Result projections used random fill/trade identifiers, breaking repeated-run digests | 4 | Derive order, fill, and trade identifiers from immutable decision/event identities; verify ten repeated runs have one digest. |
| The documented direct JSONL import command could not import project packages | 5 | Insert the resolved project root before importing project modules; verify `--help` and the import contract. |
| Referenced-task read requested `turnLimit=30`, above the tool maximum of 10 | 6 | Re-read the task with `turnLimit=10`; the task had only five turns and returned no next page. |
| The shell does not expose a `python` command | 7 | Use the repository's `.venv/bin/python` for compilation and tests. |
| Sandbox denied binding the local verification server to `127.0.0.1:8012` | 8 | Re-run the narrowly scoped Uvicorn command with approved local-server permission and `PROVIDER=mock`; stop it after browser verification. |
| `sqlite3 -readonly` could not open the WAL-mode isolated smoke database | 9 | Re-read the same temporary database normally; it contained only generated fixture data and the query confirmed COMPLETED, two partitions, and 522 bars. |
