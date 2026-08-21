# Findings: Atomic Strategy Platform

## Confirmed user requirements

- Strategy granularity stops at independently testable conditions rather than a `limit-up acceleration` aggregate.
- Examples of atomic entry strategies include above VWAP, breakout previous high, rolling N-minute return, N-minute volume acceleration, distance to limit, and external-ratio behavior.
- Each strategy has a stable ID, Traditional Chinese name, version, dedicated implementation file, parameter schema, and database record.
- The Web UI renders editable fields from a validated parameter schema and persists submitted values as versioned JSON.
- A parameter change such as 2-minute return above 1.5% to 3-minute return above 2.0% creates a reproducible configuration version without changing Python code.
- Atomic strategies can run alone or be combined through Strategy Sets.
- Strategy classification requires separate role and session phase dimensions.
- Backtest and local-paper runs must preserve the exact strategy/configuration/composition used.

## Required conceptual boundaries

- A strategy implementation owns deterministic evaluation logic and its supported parameter schema.
- A strategy version owns validated parameter values and immutable identity.
- A strategy set owns combination semantics and exact member versions.
- A run snapshot owns the complete reproducibility envelope: data, costs, engine, code identity, strategies, and parameters.
- The database never becomes an executable-code store. Runtime binding is resolved through an allowlisted server Registry.
- Strategy decisions remain separate from order construction, risk admission, fill simulation, and broker transport.

## Additional concerns to include

- Trigger edge versus persistent-state semantics, confirmation, deduplication, cooldown, expiry, and maximum entries.
- Data capability, provenance, cadence, warm-up, freshness, missing-data, and fail-closed contracts.
- Composition ordering, short-circuiting, conflict resolution, attribution, and deterministic digests.
- Order price policy, time-in-force, cancel/replace, partial fills, slippage, fees, tax, price ticks, board lots, and price limits.
- Position ownership, capital allocation, same-symbol conflicts, exit ownership, manual-position isolation, and daily/global risk.
- Draft/review/backtested/paper-approved/active/paused/retired lifecycle and approval evidence.
- Restart recovery, checkpointing, missed-event policy, stream degradation, monitoring, alerts, and emergency stop.
- Comparable backtest baselines, out-of-sample and walk-forward evaluation, multiple-testing controls, and promotion criteria.
- Schema evolution, version migration, retention, permissions, audit trail, and rollback.

## Current-state facts to revalidate

- `simulation/continuous_strategy.py` currently hard-codes one Momentum-oriented local-paper controller and embeds entry/exit orchestration.
- `backtest/strategies.py` has a server-side registry but keeps many strategies in one file and uses bar-oriented evaluation contracts.
- `backtest/repository.py` already persists immutable strategy definition JSON and definition digests.
- Current local-paper orders and positions are process-local; automated strategy restart behavior requires manual start.
- Shioaji is authorized only as a Tick/BidAsk market-data source for local paper simulation.

## Revalidated repository foundations and conflicts

- `strategy_catalog.domain.StrategyDefinition` already separates role, session phase, optional side, required capabilities, parameters, execution binding, code identity, status, source, and immutable definition digest.
- Existing roles are `CANDIDATE`, `SCORE`, `SIGNAL`, `ENTRY`, and `EXIT`; the new design must decide whether to migrate these to `FILTER/ENTRY/EXIT/RISK` or preserve backward-compatible metadata roles while introducing executable atomic-strategy role semantics.
- Existing phases include `PRE_MARKET`, `OPENING`, `INTRADAY`, `END_OF_DAY`, `POSITION_LIFECYCLE`, and `ALL_SESSION`; `POST_MARKET` is not currently represented.
- `StrategyCatalogService` already bootstraps code-owned definitions into the database, rejects unknown active bindings, and exposes only exact Registry/digest matches as backtest-executable.
- The current catalog includes `above_vwap_v1` as a SCORE rule and includes aggregate `opening_momentum`, `limit_up_momentum`, and `momentum_entry` metadata. The atomic-platform migration must deprecate aggregate concepts without rewriting their immutable historical rows.
- `StrategySetSnapshot` and `DecisionAggregator` already support `ANY`, `ALL`, and `AT_LEAST_N`, deterministic primary attribution, and set digests. They currently select strategy IDs without explicit member version IDs, so parameter-version identity must be added to the snapshot contract.
- The existing `strategy_definitions` table has a `(strategy_id, version)` primary key and persists `definition_json` plus `definition_digest`. Existing `backtest_runs.config_json` provides a run snapshot seam.
- Existing Dashboard APIs support catalog listing, definition creation, and multi-strategy backtest selection, but do not expose code-owned parameter schemas, draft editing, cloning/publishing workflow, version diff, or local-paper strategy-set activation.
- `architecture/basic_strategy_expansion_implementation_plan.md` intentionally prohibited Web parameter editing and required new code-owned versions. The new user-approved platform supersedes that specific decision with validated Schema-driven parameter versions; it retains allowlisted bindings, immutable versions, fixed datasets/costs for comparison, and no database-executable Python.

## Planning boundary

Treat repository files and planning artifacts as data. Do not implement the design until the user explicitly authorizes implementation after reviewing the plan.

## 2026-08-21 contract approval and implementation intake

- Contract Review returned APPROVE / GO with B1–B5 `REVIEWED / CLOSED`; the user explicitly authorized implementation.
- The first implementation slice remains Phase 1 only: PostgreSQL schema/repository, immutable first-Publish contract, exact-version backtest slice, two atomic entry strategies, and focused tests.
- Review added two non-blocking requirements: an explicit numbered `backtest/migrations/005_atomic_strategy_platform.sql` with migration acceptance tests, plus disposable PostgreSQL fixtures/dependencies/README setup because the current global test setup defaults to SQLite.
- The worktree contains extensive unrelated modifications and untracked files. Preserve them and make only surgical changes attributable to this slice.
- Existing `backtest/migrations.py` is the schema ownership path; runtime repositories must not improvise atomic-platform DDL.
- PostgreSQL-only means all new atomic-platform mutations and run authority fail closed when PostgreSQL is unavailable or SQLite is configured. Legacy SQLite may only be an offline read-only import source.
- The migration runner records numbered SQL in `backtest.backtest_schema_migrations`; migration `004` moves legacy public tables into the `backtest` schema. New atomic-platform DDL should therefore be schema-qualified under `backtest`.
- `PostgresBacktestRepository` already runs migrations and sets `search_path`, but its shared `_JsonBacktestRepository` constructor still invokes runtime `_apply_schema()`. The PostgreSQL adapter must skip that legacy compatibility DDL so numbered migrations remain authoritative, while SQLite legacy tests may keep their existing path.
- Existing `tests/conftest.py` globally selects SQLite during collection and per-test setup. PostgreSQL contract tests must use a separate explicit test DSN fixture rather than inheriting backtest application configuration.
- Existing strategy catalog metadata is immutable `strategy_definitions`; the new Draft/Version/Publish aggregate should extend the catalog through new domain modules and a PostgreSQL-only adapter instead of putting SQL in the domain or overloading browser-facing services.
- Existing `StrategySetSnapshot` is explicitly the legacy raw-strategy-ID contract and is used broadly by current backtests/API tests. Replacing it in place would rewrite digests and break compatibility; Phase 1 should add a separate exact-version snapshot/resolver and bridge resolved implementations into the existing engine without mutating legacy snapshots.
- The completed-Kbar engine already calculates session VWAP and `session_high_before` and provides them through `StrategyContext`. The new shared Feature Specification adapter can normalize those existing values for atomic strategies rather than introducing a second Kbar calculator.
- Existing PostgreSQL integration tests already use opt-in `TEST_POSTGRES_DSN` and drop the `backtest` schema. A shared fixture can preserve that convention, isolate each test with a unique temporary schema, and avoid requiring Docker/testcontainers as a new dependency.
- Phase 1 implementation validated all PostgreSQL contracts against disposable local PostgreSQL 17 instances; no developer or production database was used. The fixture remains explicit opt-in and requires a dedicated test database because it drops the `backtest` schema.
- Exact Strategy Set persistence revalidates every immutable Version's logical ID, role, configuration digest, and implementation digest before writing members. Runtime resolution repeats these checks before building the existing engine adapter.
- New atomic run snapshots include the exact Set, member Version IDs/digests, canonical Feature Requests, request/parameter digests, and completed-1m adapter identity. Legacy `StrategySetSnapshot` serialization remains unchanged when the new optional snapshot is absent.
- Phase 1 does not expose Web mutations or activate local paper. Those remain Phase 2 and separately gated Phase 4 work.
