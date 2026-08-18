# Findings: Project Foundation Optimization

## User requirement

- The user reviewed the plan and replied `ok`.
- The follow-up instruction is to continue without stopping. Continue the published implementation plan in verified slices rather than pausing after Phase 0.
- Preserve the market-data-only/local-paper boundary: no broker orders, CA activation, authenticated broker Simulation, or real-money capabilities.

## Current repository evidence

- The project now includes a Chinese FastAPI Dashboard, source-backed Kbars, local paper orders/positions, and Shioaji Tick+BidAsk market-data subscriptions for held and pending symbols.
- `MarketDataStore` remains a last-call-wins, latest-snapshot store and does not reject stale timestamps.
- New normalized event contracts use timezone-aware timestamps, `Decimal`, and explicit lot units, while legacy snapshot/simulation paths still use floats and less explicit volume semantics.
- `SimulationService` is process-local; orders, positions, cash, and idempotency keys disappear on restart.
- Quote-vs-Tick+BidAsk qualification contracts and bounded captures exist, but Momentum Gate G0 remains open and runtime must remain on the qualified fallback.
- The active Momentum plan already owns CandidatePool, subscription allocation, deterministic recent data, feature/signal engines, episodes, Shadow, and research promotion.
- The execution-layer plan already owns Replay clock, Journal/Risk/idempotency, shared Backtest/Replay, Shadow, broker-facing boundaries, and portfolio reconciliation.
- The current system Python lacks `pytest`; prior project progress records a `.venv` regression baseline of 100 passing tests.
- The shared worktree contains concurrent uncommitted product and Momentum changes. This plan must not rewrite or attribute those files.

## Architecture implications

- The new plan must be a cross-cutting foundation plan, not a competing strategy plan.
- The first implementation slice should establish event identity/order, DataHealth, append-only evidence, deterministic Replay, and adapter boundaries.
- HTTP refresh must remain a projection read/explicit snapshot action, not the realtime runtime clock.
- Candidate, BuyScore, Momentum, Risk, Simulation, and Presentation should remain separate bounded contexts in one repository.
- Persistence must have one authoritative write path. A storage decision is a review gate; SQLite WAL is suitable for a single-process pilot, while PostgreSQL is required before multi-process or remote deployment. Both must not become simultaneous primary journals.
- Browser modularization and SSE/WebSocket are downstream of stable projection contracts and should not precede the data foundation.
- The existing execution plan already defines `MarketEvent`, `TradeIntent`, `RiskDecision`, append-before-side-effect Journal behavior, shared Backtest/Replay semantics, Shadow, and a no-live boundary. The new foundation plan should adopt those contracts and identify the earliest common implementation slices.
- The active Momentum plan already implements or plans Scanner/CandidatePool/subscription management and normalized event contracts. Foundation work must not recreate those components; it should supply shared ingestion, health, persistence, and replay ports that Momentum consumes.
- Current `dashboard/server.py` owns provider/service/simulation globals and FastAPI lifecycle. The first boundary refactor should introduce a composition root without changing routes or payloads.
- Current API routes directly call `SimulationService`; future command handlers should depend on an application port, while HTTP remains a thin adapter.
- Current stream processing separates callback enqueueing from simulation state mutation, which is a useful pattern to preserve. The shared runtime must add bounded capacity and explicit overflow health instead of replacing it with unbounded process-local queues.
- Current `RealtimeQuoteUpdate` is a simplified compatibility DTO. Migration to normalized `TickEvent`/`BidAskEvent` must use an adapter and a dual-read compatibility window, not an immediate breaking replacement.

## Dependency order selected

1. Freeze cross-cutting contracts and one authoritative storage mode.
2. Add composition/ports without changing behavior.
3. Implement ordered ingestion and DataHealth before persistence consumers.
4. Append normalized events and decisions to the Journal before adding Replay.
5. Build deterministic Replay and migrate local paper state to journal-derived projections.
6. Add RiskGate and command application boundaries before any strategy-originated order command.
7. Complete provider qualification and run live-data Shadow.
8. Promote research hypotheses only after evidence review.
9. Modularize Dashboard transport/UI and CI after API/domain contracts stabilize.

## Storage decision proposal for review

- Preferred target: PostgreSQL is the authoritative operational Journal/projection store for persistent or multi-process mode.
- In-memory repositories remain unit-test adapters; SQLite WAL may remain an optional local-development adapter, but must not dual-write with PostgreSQL as a second source of truth.
- Credential-free raw capture artifacts remain immutable research evidence with manifest/SHA256; they are not the authoritative order/portfolio projection.

## Non-goals

- No Shioaji order API, CA activation, authenticated broker Simulation, live broker, or real-money route.
- No Momentum threshold tuning or claim of validated predictive performance.
- No microservice split, message broker, Kubernetes, or distributed event platform in the initial foundation phases.
- No replacement of the current Dashboard or Candidate/BuyScore rules in this planning task.

## Phase 0 implementation assumptions

- D1-D9 use the defaults recorded in `architecture/project_foundation_optimization_implementation_plan.md`; PostgreSQL is recorded as the future persistent authoritative store but Phase 0 must not introduce a database client, schema, or migration.
- CI runs only MockProvider/no-credential tests. Market-hours Shioaji qualification remains a manual/scheduled future workflow and is not activated in Phase 0.
- Phase 0 may introduce typed configuration/contract metadata with all runtime flags disabled. Existing `app.py`, Dashboard API routes, and simulation behavior must remain unchanged.

## Phase 0 implementation evidence

- `config/foundation.py` declares `foundation_v0`, the future PostgreSQL journal authority, loopback single-user exposure, polling as the initial projection transport, and a review-required capture-retention placeholder. These are immutable metadata only.
- `FoundationFeatureFlags` keeps event runtime, Journal, Replay, RiskGate, Shadow, and SSE all disabled by default; it is not imported or wired into the current runtime.
- `.github/workflows/ci.yml` runs on Python 3.11 and 3.12 and intentionally installs only the existing development extra. It has no secrets, provider credentials, Shioaji calls, or broker actions.
- `scripts/check_dashboard_js.py` extracts the current sole inline dashboard script and validates it with `node --check`; it does not start a browser or server.
- Verification on 2026-08-18: 132 tests passed, Python compilation passed, dashboard JavaScript parsing passed, GitHub Actions YAML parsed, and `git diff --check` passed.

## Phase 1 implementation findings

- The shared worktree already contains untracked `market_data/events.py`, `market_data/health.py`, and `market_data/ingestion.py` from concurrent Momentum/foundation work. They already define normalized envelopes, health state, and ordered ingestion behavior; Phase 1 must consume their public contracts rather than recreate them.
- `dashboard/server.py` currently holds three lazy module globals (provider, dashboard service, simulation service). Replacing only their construction path with a composition root can preserve every current route and payload.
- Existing dashboard API tests reset the three module globals with `monkeypatch`. The composition integration must retain those globals as a compatibility seam and rebuild when a test injects a different provider or service.
- `SimulationService` remains the current local-paper implementation. Phase 1 only exposes it through an `OrderCommandHandler` protocol; it does not alter the order flow or add persistence/risk behavior.

## Phase 2 audit findings

- The existing `MarketDataIngestor` already independently watermarks `symbol + stream_kind`, rejects session mismatch/duplicates/out-of-order data, writes Tick and BidAsk projections, and records the resulting `DataHealth` transition. `BoundedMarketEventQueue` blocks health on overflow rather than silently dropping.
- The existing `RealtimeQuoteUpdate` compatibility DTO contains only last/best prices and timestamps. It lacks lot volume, intraday high/low, aggressor totals, and five-level book data required by the canonical `TickEvent`/`BidAskEvent`; it must not be fabricated into canonical events.
- `SimulationService` currently consumes that compatibility DTO on an unbounded `SimpleQueue` for local-paper quote updates. Replacing it directly would alter existing paper-fill behavior, so the canonical path must run separately in observe-only mode until parity evidence exists.
- The next inspection must locate the raw Shioaji capture/normalization adapter and only wire a canonical source that preserves all required source fields.
- `shioaji_quote_capture.py` is a bounded, data-only qualification capture. It retains some trade/book fields for parity reports but is deliberately not the normal production callback path and does not yet supply every canonical Tick field (notably high/low and per-tick volume) as a runtime source.
- Therefore Phase 2 can safely complete the session-scoped observe-only runtime around pre-normalized `EventEnvelope` values, but must not attach it to the existing Shioaji callback until provider qualification supplies a complete raw mapping.
- Additional concurrent foundation files are now present in the shared worktree, including `market_data/clock.py`, `market_data/replay.py`, `tests/test_market_data_ingestion.py`, and `tests/test_market_data_replay.py`. They overlap later foundation phases, so this task must inspect and reuse them instead of creating parallel Clock/Replay/health implementations.
- The dashboard already contains a UI-only `renderDataHealth` function based on snapshot/simulation availability. It is not yet proof of canonical `DataHealth` projection wiring and must not be mislabeled as such.

## Phase 2 verification evidence

- `tests/test_market_data_ingestion.py` and `tests/test_market_data_replay.py` passed together (16 tests), covering queue overflow, duplicate/out-of-order/session behavior, health recovery, immutable-manifest validation, and deterministic Replay.
- The complete current regression suite passed with 165 tests, together with Python compilation and whitespace checks.
- The shared Replay path reads immutable fixture data and uses `ReplayClock`; it has no Shioaji SDK or network dependency. Existing local-paper quote processing remains separate and unchanged.

## Phase 3 journal design decision

- No executable Journal, migration, PostgreSQL dependency, or restart-projection implementation exists in the current worktree. This makes a small shared Journal contract a non-overlapping next slice.
- The existing `runtime.ports.JournalRecord` is only a Phase-1 placeholder. Phase 3 must replace it with a single `trading.journal` contract rather than add a second record type.
- PostgreSQL is the approved persistent authority, but the local environment has no supplied database DSN. The adapter will be optional (`postgres` extra), persistence will remain disabled by default, and real database tests will run only with an explicit `TEST_POSTGRES_DSN` (provided by CI's isolated service).
- Success criteria for this slice: append order is stable; same record/key retry returns its original sequence; conflicting reuse fails closed; checkpoints cannot move backward; migrations are forward-only; no current simulation route imports or calls the adapter.

## Local-paper recovery design

- The current `SimulationService` maintains orders, positions, cash, and idempotency maps in process memory, uses floating-point money, and mutates state directly. Replacing it in this slice would change browser behavior and quote-worker timing.
- The safe migration step is an independent Decimal-based Journal reducer that recognizes normalized local-paper fill records, rebuilds cash/positions/realized PnL deterministically, validates a recorded checkpoint digest at the exact Journal sequence, and remains unused by the current routes.
- This reducer must ignore unrelated Journal records while still advancing its observed global Journal sequence; only a future adapter may emit local-paper fill records from the existing simulator after parity verification.
- The existing simulator's read payload includes all fields needed for a full-fill observation (`order_id`, normalized symbol/name/side, `filled_price`, `filled_quantity`, and `updated_at`). A one-way converter can therefore create deterministic Journal fill records only after a simulator result is already `FILLED`; it must return no record for submitted/rejected/cancelled orders and must not be wired into the command route yet.

## Packaging verification finding

- The system-Python wheel build successfully included the Journal SQL migration, but its local setuptools process created a root `build/` artifact and refreshed tracked `tw_intraday_trader.egg-info` metadata. The build directory is disposable agent-created output; the metadata changes must be inspected before keeping only entries required by the new `trading` package and optional PostgreSQL extra.

## Phase 13 risk-context finding

- `DataHealthSnapshot` is already a canonical, immutable read projection with a stable state value. A `runtime` adapter can safely translate that state into the framework-free `RiskSnapshot` without making either the RiskGate or the Dashboard depend directly on provider callbacks.
- `STARTING`, `DEGRADED`, and `BLOCKED` must all remain non-healthy. The existing RiskGate already treats any state other than `HEALTHY` as `DATA_HEALTH_UNHEALTHY`, so the adapter needs no alternate thresholds or duplicate health policy.
- Portfolio, market-status, tradability, pending-order, and book-age evidence does not exist in the canonical DataHealth projection. It remains caller-owned and must be passed explicitly instead of inferred from the legacy simulator or a provider snapshot.

## Phase 16 provider qualification audit

- `market_data.quote_qualification` already provides a deterministic, fail-closed Quote-versus-Tick+BidAsk report. Missing criteria, source capture, derived digests, or reconnect continuity produces `INCOMPLETE`; no source mode can be selected optimistically from partial data.
- The Momentum architecture record explicitly keeps Gate G0 open: the observed 8039 capture had no callbacks and the short 2330 sample is insufficient. The runtime must remain on the Tick+BidAsk fallback; no live capture or source-mode change is justified by this static audit.
- `market_data.shioaji_quote_capture` is already data-only and uses a credential-free JSON artifact contract. Further implementation must avoid duplicating its capture/normalization ownership; only deterministic reporting or artifact validation is potentially in scope.
- The capture CLI intentionally evaluates with `criteria=None`, so every new artifact is preliminary and cannot select a provider mode. Two existing capture JSON files are present, but their contents still need an offline integrity/shape validation before they can be used as review evidence.
- The architecture requires immutable artifact manifests with SHA-256, row counts, schema version, and time bounds. The current capture writer serializes the evidence but does not emit a separate deterministic manifest; an offline validator is a non-overlapping hardening opportunity.
- Offline validation now confirms the current 2330 and 8039 artifact byte digests and bounded metadata. Both stay `INCOMPLETE`; these immutable facts are useful review evidence but do not grant Quote-mode selection.
- Offline rehydration now reconstructs the existing typed capture contracts and can pass them to the established evaluator. It validates Decimal-compatible fields, timezone-aware timestamps, source/symbol identity, and reconnect shape before evaluation; no default criteria or provider-mode decision was added.

## Final verified foundation boundary

- The no-credential foundation now has an immutable Journal/optional PostgreSQL contract, deterministic local-paper reducer/checkpoints, RiskGate inputs/evidence, command recovery classification, DataHealth-to-risk adaptation, and offline capture integrity/replay tools. The existing Dashboard and `SimulationService` route path remains intentionally compatible and unchanged.
- Final local evidence: 238 passed, 1 explicitly skipped PostgreSQL test without an injected DSN; compilation, Dashboard JavaScript parsing, whitespace, and wheel content checks passed. The wheel contains every new runtime/trading/market-data module and migration SQL.
- The next implementation steps need a reviewed external decision rather than more local scaffolding: market-hours provider qualification must close G0 before source-mode change, and Dashboard command migration needs a canonical live DataHealth/session/RiskSnapshot owner before the legacy simulator route can be safely replaced.
