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

## 2026-08-21 Gate G1 implementation Review findings

- Gate G1 is `NOT PASSED`; Phase 2 remains blocked.
- `AtomicBacktestResolution.run_snapshot` currently preserves canonical Feature Requests and adapter identity but not the resolved Feature Specification digest, implementation digest, or explicit as-of semantics. A later specification change can therefore make an old run semantically ambiguous.
- `AtomicStrategyCatalogService.publish()` reads the Draft and resolves the currently deployed Template before consulting durable Publish operation state. A response-loss retry fails when that strategy implementation has since been removed from the Registry.
- Review found that the shared paper-fill fixtures mixed a fixed command clock with the simulator wall clock. Commit `0bcf61c` now injects one deterministic clock into both affected fixtures; the follow-up full suite passed `1100 passed, 10 skipped`. This closes only the time-dependent regression finding, not the remaining Gate G1 blockers.
- Exact Strategy Set reads currently trust relational rows without comparing them to persisted `snapshot_json` and `snapshot_digest`; the repository must reject any drift instead of silently reinterpreting it.
- Migration acceptance must validate every new table and the required constraint/index contracts, not only a three-table subset.
- PostgreSQL test cleanup needs an executable guard before dropping the `backtest` schema; README warnings alone do not prevent a mistaken DSN from destroying a non-test schema.

## 2026-08-21 Gate G1 remediation disposition

- All three blocking findings and all three Important findings now have implementation and test coverage.
- Run snapshots use `atomic-backtest-run-snapshot-v2` and freeze each resolved Feature Specification digest, feature implementation digest, and as-of semantics.
- Durable Publish replay is PostgreSQL-first and works with an empty current Registry; different-key retries on a sealed Draft return `DRAFT_ALREADY_PUBLISHED` before Template lookup.
- Strategy Set reads fail closed on stored JSON/digest mismatch and relational projection drift.
- Migration acceptance covers all nine tables, declared constraint counts, four named indexes, and idempotent rerun.
- Destructive fixture cleanup requires a standalone `test` database-name token or an explicit sentinel.
- Final evidence is `1113 passed` with disposable PostgreSQL and `1103 passed, 10 skipped` without a DSN.

## 2026-08-21 final Gate G1 Review and Phase 2 boundary

- The final short Review returned `APPROVE / Gate G1 PASSED` with no remaining blocking or important finding.
- The reviewer independently confirmed focused `33 passed, 5 skipped`, full no-DSN `1103 passed, 10 skipped`, Python compilation, and `git diff --check`.
- The reviewer did not rerun disposable PostgreSQL because `TEST_POSTGRES_DSN` was unavailable, but accepted the previously recorded `1113 passed` PostgreSQL evidence after reviewing the relevant tests and contracts.
- Phase 2 is authorized only for historical Backtest Web Management: code-owned Template/Schema discovery, PostgreSQL Draft and immutable Publish management, exact-version Strategy Set composition, and the Backtest Launcher.
- Phase 2 must not touch Local Paper, simulation trading, Shioaji/broker order integration, or real-money execution. Those remain behind later Gates.
- Gate G2 remains open until the browser, API, PostgreSQL transaction, security, and reproducibility acceptance criteria pass.

## 2026-08-21 Phase 2 current Web seams

- The Dashboard is already split into browser-native ES modules; `dashboard/static/js/workspaces/backtest.js` owns the current strategy catalog and historical backtest UI, while `dashboard/static/index.html` owns layout only.
- The existing strategy drawer is a read-only legacy catalog projection. It exposes fixed metadata filters but has no atomic Template schema, Draft, Publish, immutable Version, diff, or exact-version Strategy Set management.
- The existing Backtest setup submits legacy raw strategy IDs through `/api/backtests/runs`; Phase 2 must add an exact-version Strategy Set path without breaking or silently reinterpreting the legacy path.
- The server already separates historical backtest composition from local simulation. The new atomic management service should stay on that historical seam and must not import or activate simulation/broker controllers.
- Phase 1's atomic application port currently supports Template sync, Draft create/get, durable Publish, Version get, and Strategy Set save/get. Phase 2 needs surgical list/update/validate/clone/diff methods rather than a second catalog implementation.
- The two deployed Templates already provide code-owned labels, types, defaults, ranges, units, cross-validation, feature requirements, runtime bindings, and implementation digests. The Web form can therefore be generated entirely from the server projection and must never accept a client-supplied binding or schema.
- Migration 005 already owns the PostgreSQL tables required by the first Web slice. No runtime schema creation or SQLite persistence is needed.
- The frozen API plan requires Template/schema reads; Draft create/update/validate/publish; Version detail/clone/diff; exact-version Strategy Set create/get; and Backtest launch. Every mutation needs durable idempotency and audit evidence.
- `BacktestApplicationService` currently constructs only the legacy `StrategySetSnapshot` and its worker always uses the legacy Registry/engine. An exact Strategy Set launcher must snapshot the resolved atomic set and select the resolved per-run Registry during worker execution; merely adding a browser selector would not make the atomic strategy executable.
- For the Phase 2 vertical slice, the server can keep the existing code-owned end-of-day exit as a fixed execution policy while the client supplies only an exact ENTRY `strategy_set_version_id`. This avoids an ambiguous raw atomic strategy ID and does not pretend that an atomic EXIT Template exists yet.
- The local Dashboard entrypoint already binds uvicorn to `127.0.0.1`; Phase 2 adds request-client/origin checks plus a per-process CSRF token only to the new atomic mutations.
- The initial backend slice added numbered migration 006 for durable Web mutation operation results and audit events, then extended the existing repository/application ports rather than creating a parallel strategy store.
- The first focused run after backend changes passed 11 tests and skipped 5 PostgreSQL-only tests; its sole failure was the expected migration-manifest assertion still naming migration 005 as the final file. The acceptance test has been updated to cover both 005 and 006 plus the two new tables/indexes.
- The existing dashboard can host the new workflow without a build tool: the strategy drawer now provides Schema-generated Draft editing, immutable Publish, Version cloning, and exact-version Set construction; the backtest setup exposes a separate atomic launcher and keeps the legacy selector collapsed for compatibility.
- The browser receives only labels, constraints, digests, and exact version identities. It never submits execution bindings, import paths, Python, SQL, or arbitrary strategy-definition JSON.
- JavaScript graph validation and the expanded focused suite are green: `29 passed, 5 skipped`; PostgreSQL-only tests remain skipped in the normal no-DSN mode.
- A disposable PostgreSQL 17 cluster was created under `/private/tmp`; the first sandboxed test process could not open its Unix socket, so that result is environmental and not product evidence.
- The same focused PostgreSQL suite was rerun outside the restricted sandbox and passed `15 passed`, covering migration 006, Publish concurrency/replay, Web Draft idempotency/audit, Strategy Set integrity, and PostgreSQL backtest persistence.
- The first exact Set-to-worker PostgreSQL acceptance run exposed two integration-only contract gaps: the initial fixture was irregular intraday data without `KBAR_1M`, and the launcher invented an unsupported `backtest-engine-v2-atomic` version even though atomic identity already lives in Run Snapshot v2. The fixture now contains a real dominant one-minute cadence and the launcher uses the existing deterministic `backtest-engine-v2`; the exact run completed successfully against PostgreSQL.
- Browser-facing atomic runs share the legacy retry/clone endpoints. The generic recreation path originally rebuilt raw IDs through the legacy Registry; it now detects Run Snapshot v2, reconstructs and verifies the exact Set/Registry, preserves the snapshot, and rejects atomic clone attempts that override `strategy_set`, engine, dataset identity, or snapshot evidence.
- Resource-creating Web mutations need serialization before their first durable replay lookup. Draft create and Strategy Set create now take a deterministic PostgreSQL transaction advisory lock over `(operation_scope, idempotency_key)`; a concurrent Draft test proves two requests return one Draft with one operation and one audit event.
- Browser smoke exercised Template selection, Schema-generated fields, Draft create/validate/Publish, exact Set construction, and Set visibility in the historical Backtest workspace. The launch control correctly stayed disabled in that smoke database because it contained no READY dataset; the separate PostgreSQL acceptance test covers the actual worker completion path.

## 2026-08-21 Gate G2 implementation Review findings

- Gate G2 remains `NOT PASSED`; Phase 3 is explicitly blocked.
- Atomic Run start is protected, but the shared legacy cancel/retry/clone routes accept hostile Origin requests without the atomic CSRF boundary when the target Run is atomic.
- Both the atomic Web service and background backtest worker keep a single psycopg connection for their lifetime. Psycopg cursors on one connection share transaction state, so repository operations need pool-backed checkout-per-operation or whole-transaction serialization.
- Backtest Run idempotency currently keys only on `idempotency_key`, silently replays a different config, and lacks safe concurrent unique-conflict replay.
- Draft mutation replay returns the current mutable Draft instead of the immutable operation result, so a later update changes what an old create/update replay returns.
- Browser mutation helpers generate a fresh key for each click; a response-loss retry cannot intentionally reuse the original operation key.
- The generic browser clone always sends a legacy `strategy_set` override, while the backend correctly forbids that override for atomic Runs. Version diff has an API but no usable selector/rendering flow.
- Atomic request DTOs silently ignore unknown fields. Atomic Run mutations lack actor audit; Strategy Set lacks change note; conflict audit and audit query/UI are absent.
- Reviewer evidence without PostgreSQL: focused `13 passed, 8 skipped`, full `1109 passed, 13 skipped`, JavaScript/compilation/diff checks passed. PostgreSQL was not rerun in that Review.
- The worktree also contains unrelated active FinMind history/planning changes. Preserve them and do not change `.planning/.active_plan` during this isolated remediation.
- `psycopg-pool` is already an optional PostgreSQL dependency, and `trading.PostgresJournalRepository` already demonstrates the repository convention to accept exactly one direct test connection or runtime pool. Reuse that checkout-per-transaction pattern rather than introducing a second pool abstraction.
- `_JsonBacktestRepository` centralizes every database operation through `_cursor()` and `_transaction()`, so `PostgresBacktestRepository` can provide pool-backed overrides while SQLite and direct-connection tests retain current behavior.
- The current `backtest_runs.idempotency_key` unique constraint can support atomic conflict handling with `INSERT ... ON CONFLICT DO NOTHING`, followed by a same-transaction read and `config_digest` comparison. This avoids check-then-insert and does not require a new run-operation table for the current contract.
- `_JsonBacktestRepository` currently serializes direct-connection access with an `RLock`, but pool-backed runtime should override `_cursor()` and `_transaction()` so each complete operation checks out one connection and commits/rolls back before release. The direct connection plus lock can remain for SQLite and explicit tests.
- Backtest configuration has no pool sizing settings yet, while the dependency already includes `psycopg-pool`. A small bounded runtime pool can use the existing worker count as a lower-bound signal and explicit backtest pool settings for deterministic ownership/cleanup.
- Direct `PostgresBacktestRepository(connection)` and `PostgresAtomicStrategyRepository(connection)` construction is limited to explicit PostgreSQL tests. Runtime creation occurs only in `BacktestApplicationService` and `dashboard.get_atomic_strategy_service`, so both adapters can add an optional `pool`/`owns_pool` mode without broad call-site churn.
- The backtest repository has no code path that directly consumes `_connection` outside its shared context managers. Pool overrides can therefore be surgical and leave the SQLite implementation untouched.
- Atomic DTOs are a contiguous group of Pydantic models, so a shared strict base (`ConfigDict(extra="forbid")`) can harden only the new Atomic surface without changing legacy flexible catalog requests.
- Cancel currently has no request body, retry/clone use legacy models, and all three routes dispatch before knowing whether the target Run is atomic. The handler can read the target Run first and conditionally require the atomic security/audit contract while preserving legacy compatibility.
- Browser `changeBacktestRun()` and `cloneBacktestRun()` use `backtestFetch` and body-level one-shot keys. Atomic targets are detectable from `run.config.atomic_strategy_run_snapshot`, enabling the browser to use the protected atomic mutation helper and omit legacy `strategy_set` overrides.

## 2026-08-21 Gate G2 remediation findings

- Atomic cancel/retry/clone now resolve the target Run first. Atomic targets require loopback client, allowed Origin, the process CSRF token, strict request bodies, actor identity, and durable idempotency keys; legacy Runs retain their existing compatibility path.
- Runtime PostgreSQL composition now owns bounded `psycopg_pool.ConnectionPool` instances. `PostgresBacktestRepository` and `PostgresAtomicStrategyRepository` accept either one explicit test connection or one runtime pool, and pool mode checks out a connection for each complete transaction.
- `backtest_runs.idempotency_key` is now admitted with `INSERT ... ON CONFLICT DO NOTHING`; the winning row is reread in the same transaction and its `config_digest` must match. Different settings under the same key raise an explicit HTTP 409 conflict.
- Draft create/update operation results now contain a complete immutable Draft projection. A replay reconstructs that saved projection even after the mutable Draft advances to later revisions.
- Browser mutation key ownership moved to a small ES module. Network loss and 5xx retain the same operation key; a successful response or definitive 4xx clears it. A Node-executed test covers the response-loss and 5xx sequence.
- Atomic Run clone no longer sends the legacy raw `strategy_set`; it limits overrides to capital and evaluation fields accepted by the server. Strategy management now provides two Version selectors, a diff rendering flow, Strategy Set change notes, and an Audit list.
- Atomic request models inherit `ConfigDict(extra="forbid")`. Unknown fields such as `entry_strategy_ids` or `import_path` return 422 instead of being discarded.
- Migration 007 removes the audit table's one-row-per-operation restriction and adds outcome, request digest, and details so both successful/replayed operations and later conflict evidence remain queryable.
- No `TEST_POSTGRES_DSN` is configured in this workspace. The new real-PostgreSQL pool/concurrent Run tests are present and explicitly skipped; SQLite is not treated as evidence for those contracts.
- Final no-DSN evidence: `1112 passed, 15 skipped`; Python compilation, Dashboard ES module syntax, and `git diff --check` all passed.

## 2026-08-22 Gate G2 follow-up Review findings

- Gate G2 remains `NOT PASSED`; Phase 3 remains blocked.
- The atomic mutation guard validates only `request.client.host`. A loopback peer with `Host: public.example` can therefore receive the CSRF token from `/api/atomic-strategies/capabilities` and mutate an atomic Run.
- Origin validation compares only a small hostname allowlist. It does not bind scheme or effective port to the validated request origin, so `Origin: https://127.0.0.1:4443` is accepted for an HTTP request to another port.
- A local TestClient probe reproduced all three failures: public-Host capabilities `200`, public-Host retry `201`, and wrong scheme/port Origin retry `201`.
- `test_dashboard_candidate_history_uses_provider_kbars_on_demand` depends on `MockProvider`'s construction date. On Saturday 2026-08-22 its last market-day close is `105.52`, not the test's expected anchor close `105.5`.
- `test_strategy_intent_route_completes_a_local_paper_round_trip` fixes the signal date to 2026-08-21 but constructs the runtime with `SystemClock`; on 2026-08-22 the session-date guard correctly rejects it.
- Focused reproduction result: `2 failed, 2 passed`. The failures match the Review and are not accepted Gate evidence.
- The remediation must remain surgical: enforce the HTTP Host boundary before token disclosure, compare the complete origin, and inject deterministic test time/anchors. It must not start Phase 3 or change trading semantics.

## 2026-08-22 Gate G2 follow-up remediation disposition

- The ASGI HTTP boundary now rejects any non-loopback peer, non-loopback Host, or proxy forwarding header before route dispatch. The capabilities endpoint can no longer disclose the CSRF token under `Host: public.example`.
- Test-only `Host: testserver` is accepted only for TestClient's `testclient` peer; production loopback access accepts `localhost`, loopback IPv4, and loopback IPv6 authorities.
- Atomic mutations compare Origin to the validated request origin as a normalized `(scheme, hostname, effective_port)` tuple. Scheme and port mismatches fail with 403.
- `DashboardService` and `MockProvider` expose narrow time/history-anchor injection seams. The history test fixes both values to 2026-08-21, so weekend or later execution cannot change the expected last close.
- The local-paper round-trip test now supplies a fixed clock through `RuntimeComposition`; the existing session-date guard remains unchanged and continues to reject cross-session intents in production.
- Verification is green: focused `48 passed, 3 skipped`, no-DSN full `1114 passed, 15 skipped`, and disposable PostgreSQL 17 full `1129 passed`; compilation, JavaScript syntax, and whitespace checks also passed.
- The disposable PostgreSQL cluster was stopped and removed. Gate G2 remains `NOT PASSED` until a new Review explicitly approves this remediation; Phase 3 remains blocked.

## 2026-08-22 Gate G2 final Review disposition

- Gate G2 is `PASSED`; the final Review found no remaining blocking or important issue.
- Independent evidence reconfirmed the local HTTP boundary, exact Origin comparison, deterministic clocks, no-DSN suite, disposable PostgreSQL suite, compilation, Dashboard JavaScript, and whitespace checks.
- Phase 3 Backtest Qualification is explicitly authorized. Gate G3 remains `NOT PASSED`, and Phase 4 remains blocked.
- Existing foundations available to Phase 3 include explicit OOS summary metrics, persisted baseline/challenger comparisons, immutable Atomic Run Snapshot v2, parameterized Feature Requests, and adapter/implementation identities; the implementation must compose these rather than create a parallel backtest engine.
- Existing `summarize_run()` derives OOS from the last equity date minus 365 days. That remains a display summary only; Phase 3 qualification must use the newly explicit, immutable date protocol and cannot treat the rolling display window as promotion evidence.
- Qualification comparability intentionally ignores strategy entry identity and display-only evaluation thresholds, but still requires identical dataset/digest, capital, position sizing, transaction costs, engine, and exit contract.
- Multiple-testing evidence is recorded before verdict generation. Phase 3 v1 uses daily-clustered bootstrap with Bonferroni-adjusted alpha; it never treats trades as independent observations and never auto-mutates lifecycle state.
- Qualification response-loss replay must precede current Run/Dataset validation. Otherwise a committed immutable operation could become unreplayable after a mutable dataset projection changes; the application now uses a durable fast replay followed by an authoritative advisory-lock recheck on create.
- Qualification list reads are bounded to 250 records, walk-forward windows to 50, and attempted Runs to 200. Detail evidence stores aggregate interval metrics and identity snapshots, not duplicate raw trades or Kbars.
- The real Dashboard smoke confirmed the new qualification controls are interactive and fail closed before mutation when no completed Runs exist. SQLite development mode explicitly displays that qualification evidence requires PostgreSQL while leaving the rest of the historical Backtest workspace usable.
- Full PostgreSQL regression is green, but Gate G3 remains a Review decision. No Phase 4, Local Paper, simulation, Shioaji order, broker, or real-money code belongs to this candidate.
- Final hardening verifies the current DatasetManifest content against its declared digest and the Run snapshot digest before first qualification. OOS drawdown now anchors to the last pre-OOS equity point so a loss at the start of the OOS interval cannot disappear from the guardrail.

## 2026-08-22 Gate G3 implementation Review findings

- Gate G3 remains `NOT PASSED`; Phase 4 remains blocked.
- `QualificationPolicy` currently accepts client-supplied floors weak enough to turn off every meaningful guardrail. The server must own the effective policy and must reject or ignore weaker request values rather than treating them as promotion authority.
- Window validation currently proves only chronological ordering. Qualification must bind train/validation/OOS to the immutable DatasetManifest coverage and require sufficient observations in every declared evaluation segment.
- Daily-cluster bootstrap needs a minimum number of distinct OOS dates; a degenerate one-day confidence interval is insufficient evidence, regardless of apparent return.
- Multiple-testing evidence must come from an immutable experiment-family aggregate in PostgreSQL. The server must serialize the family head, allocate monotonic attempts, and derive complete history instead of trusting client-declared attempt counts or Run IDs.
- Compare and Qualification require one shared comparability contract. It must ignore only the intended challenger Strategy Version identity while requiring the same dataset, capital, sizing, costs, engine, exit policy, Feature Request semantics, Feature implementation, adapter identity, and as-of semantics.
- Before qualification, every Run must satisfy `canonical_digest(run.config) == run.config_digest`; result, dataset, and Atomic Snapshot checks do not substitute for config identity.
- Qualification record integrity must bind row `actor_id` and `change_note` to the digested request/projection.
- The Reviewer UI must surface authoritative family history, adjusted alpha, effective server policy, all windows/folds, and exact Run/Strategy/Feature/adapter identities.
- `FeatureRequestSpec.state_key()` is not sufficient evidence by itself. The G3 claim must either be implemented at a real runtime cache/state owner or explicitly deferred.
- The current API shape embeds `attempt_number`, `planned_attempts`, `attempted_run_ids`, `alpha`, and every policy threshold under `protocol`; these fields must leave the client contract. A safe request contains a stable server-issued `family_id`, a new `hypothesis_id`, the baseline/challenger pair, and dated windows only.
- The current PostgreSQL qualification create transaction locks only the idempotency key. The family aggregate therefore needs its own row lock and attempt insertion in the same transaction as qualification persistence so two hypotheses cannot receive the same sequence or omit each other.
- Existing `compare_runs()` ignores top-level `strategy_set` but compares the complete Atomic Snapshot through the remaining config keys; existing qualification ignores the complete snapshot then rechecks only exit fields. A shared domain projection should compare stable execution fields and a normalized Atomic Snapshot with strategy-entry identity removed but Feature identities retained.
- Current PostgreSQL tests deliberately use request policy values `minimum_oos_trades=1` and `minimum_walk_forward_folds=0`; those fixtures encode the vulnerability and must be replaced with evidence that remains insufficient until server-owned floors and sufficient dated samples are present.
- Chosen family ownership: the server derives one deterministic family ID from the immutable Baseline Run ID. Creating a Challenger against that Baseline records the Run in the family ledger in the same PostgreSQL transaction as `backtest_runs`; cloning or launching another Challenger against the same Baseline cannot select a new family.
- Family alpha, planned-attempt ceiling, and qualification policy are code-owned constants. The browser submits only Baseline/Challenger, a hypothesis label, dated windows, actor, and note. Attempt sequence, complete Run history, adjusted alpha, and effective policy are server projections.
- Qualification creation will use optimistic family-head binding: evidence is built from a verified snapshot, then the insert transaction locks the family and requires the same head sequence/digest. A concurrent Challenger append forces a retry instead of saving evidence with an omitted attempt.
- The Feature `state_key()` helper has no runtime state owner in the current completed-Kbar adapter. Rather than add a speculative cache, this remediation will withdraw that Gate G3 claim and retain only the already-real Run Snapshot runtime identity evidence.

## 2026-08-22 Gate G3 remediation disposition

- All four blocking findings are addressed in the implementation candidate: server-owned qualification floors and coverage, PostgreSQL-authoritative family history, one shared comparability contract, and fail-closed Run config identity.
- The three important findings are addressed: Feature runtime state is explicitly deferred rather than claimed, the Reviewer UI exposes the complete qualification protocol/evidence, and row actor/change note are bound to integrity verification.
- Adversarial coverage includes weakened-policy requests, one-day OOS clustering, out-of-manifest windows, mismatched Feature adapters, stale Run config digests, actor/change-note tampering, concurrent family attempts, response-loss replay, and shared compare/qualification semantics.
- Gate G3 is still a Review decision. This candidate must not start Phase 4 or change Local Paper, simulation, broker, or real-money execution.

## 2026-08-22 Gate G3 follow-up Review findings

- Gate G3 remains `NOT PASSED`; Phase 4 remains blocked.
- Walk-forward validation compares folds only with each other. It must also require every fold OOS to end before the final Primary OOS begins, otherwise the same observations can satisfy both stability and final evaluation.
- A family derived from `baseline_run_id` is not a research identity: rerunning an identical Baseline creates a new ID and resets the Bonferroni attempt budget. The stable identity must bind the exact Baseline strategy/config, Dataset, costs, Feature/adapter semantics, and qualification protocol independently of Run ID.
- Run identity currently verifies only `digest(config_json) == config_digest`. It must additionally require row `dataset_id` and `dataset_digest` to equal the corresponding immutable config snapshot values before compare, family append, or qualification.
- Family snapshot digest currently includes mutable post-qualification linkage but stores no matching canonical body. Either the snapshot body must be persisted immutably or the digest projection must exclude mutable linkage; read verification and Reviewer UI must make current/historical linkage explicit.
- Review independently confirmed the prior server-owned policy, coverage floors, shared comparability, family locking/sequencing, actor/change-note integrity, and Phase 5 Feature-state deferral remain correct.
- Chosen aggregate identity: `research_baseline_digest` is a canonical server projection of the Baseline dataset/config/cost/engine/exit contract plus the complete exact Atomic Strategy Set, Feature Request/specification/implementation/as-of evidence, adapter identity, and fixed qualification policy/protocol semantics. It excludes Run ID and display/change metadata, so an equivalent Baseline rerun maps to the same deterministic family.
- `baseline_run_id` remains the canonical first evidence Run stored on the family, not the family identity. A Challenger launched from an equivalent Baseline may reuse the existing family only after both Runs pass the stable identity and shared comparability checks.
- Chosen snapshot repair: persist the exact pre-qualification `family_snapshot_json` beside its digest in the immutable qualification row. Detail reads also compute a current family projection, so historical evidence remains reconstructable while current hypothesis/qualification linkage stays visible.
- Challenger config will bind `research_baseline_digest` next to the server-derived family ID. Repository admission recomputes it from the selected completed Baseline under the same transaction and rejects caller/config drift.
- The stable Baseline projection includes the entire verified Atomic Snapshot and ordinary execution/data config, excluding only lineage, family IDs, change notes, and display-only evaluation thresholds. This prevents a new family when the same Baseline is rerun with a different Run ID or note while keeping exact Strategy Version and Feature semantics in identity.

## 2026-08-22 Gate G3 identity/isolation remediation disposition

- Qualification protocol now rejects every Walk-forward fold unless `fold.oos_end < primary.oos_start`; the exact 30-day Primary OOS reuse exploit is covered by a negative test.
- Experiment family identity is derived from an immutable research-baseline projection: exact Strategy Version/Feature/config/cost/adapter identity plus the fixed server research protocol. Equivalent completed Baseline Runs therefore resolve to one PostgreSQL family, one locked head, and one attempt budget.
- One `verify_run_identity()` contract now checks canonical config digest plus Run-row/config Dataset ID and digest equality. Compare, Baseline selection, Challenger creation, qualification, and every family attempt use it and fail closed on PostgreSQL row tampering.
- Migration 010 persists the stable research identity/protocol and immutable `family_snapshot_json`. Qualification reads verify its canonical digest; detail reads expose a separate current-family snapshot so later hypothesis/qualification linkages do not rewrite historical evidence.
- The Reviewer UI shows research-baseline identity, stored historical linkage, current linkage, and both snapshot digests. Static UI tests cover these labels; browser smoke covered fixed-policy visibility and Fold `2 -> 3 -> 2` interaction.
- Final evidence: no-DSN focused `31 passed, 10 skipped`, PostgreSQL focused `8 passed`, no-DSN full `1157 passed, 20 skipped`, disposable PostgreSQL 17 full `1177 passed`, plus compilation, Dashboard JavaScript syntax, browser smoke, and whitespace checks.
- Gate G3 remains `NOT PASSED` pending a fresh Review. Phase 4, Local Paper, simulation trading, Shioaji/broker orders, and real-money execution remain blocked.

## 2026-08-22 Phase 4 Local Paper Runtime initial reconciliation

- `simulation/continuous_strategy.py` is still a Momentum-specific polling controller: it hard-codes `momentum_acceleration_local_paper`, accepts only `OPENING_MOMENTUM`/`LIMIT_UP_MOMENTUM`, and keeps consumed signal digests only in process memory.
- `simulation/strategy_flow.py` already provides a useful application boundary: it journals a versioned `StrategyPaperIntent` before calling `LocalPaperCommandService`, and duplicate intent IDs are idempotent while payload drift conflicts.
- The existing Local Paper stack already has Journal, command/risk/simulator, checkpoint/recovery, quote freshness, ownership, and Dashboard controls. Phase 4 should converge these components instead of adding a new execution or persistence path.
- Frozen Gate G4 still requires an explicit Proposed -> Hard Risk -> Approved type/state boundary, exact-version runtime binding, generic Filter/Entry/Exit evaluation, persistent per-run strategy state, default STOPPED/manual start, continuous position monitoring, and restart reconciliation.
- Scope remains local simulation only. Shioaji may supply Tick/BidAsk market data but no broker adapter, CA, trade subscription, or real-money transport may be introduced.
- Both deployed atomic entry templates currently expose only `BACKTEST_KBAR_1M`; no `LOCAL_PAPER_TICK_BIDASK` binding exists, so an exact-version activation must fail closed until a real paper adapter is implemented and its identity is added to the code-owned Template.
- `LocalPaperCommandService` already constructs a normalized `OrderCommand`, calls the pure `RiskGate`, journals the decision, and only then invokes `LocalPaperSimulationCommandAdapter`. The missing Gate G4 contract is explicit Proposed/Approved type identity: the handler still accepts the same `OrderCommand` object that existed before admission.
- Existing Strategy Set snapshots are exact-version and same-stage only. Phase 4 needs a narrow Pipeline value object that references optional FILTER, required ENTRY, optional EXIT sets plus code-owned execution/risk bindings; it should not mutate `ExactStrategySetSnapshot` into a mixed-stage object.
- The existing Momentum dashboard projection is generated by the canonical `FeatureEngine` and already serializes `price`, `vwap`, and `previous_intraday_high` with status/source timestamps. A Local Paper atomic adapter can normalize that projection and call the existing pure strategy kernels without recomputing features.
- The current automated-strategy Web form exposes only stop-loss, take-profit, and daily-loss fields. It cannot select an exact ENTRY Strategy Set and therefore cannot satisfy activation identity or reject unavailable runtime bindings at the Web boundary.
- Existing continuous-controller tests cover stale data, ownership, exits, retry exhaustion, duplicate signal consumption, and default/manual lifecycle. They provide a strong compatibility suite, but the Momentum-specific candidate contract must be replaced with atomic evaluation/composition evidence.
- Phase 4 now has a narrow `simulation/atomic_runtime.py` seam rather than another execution pipeline. It resolves an exact ENTRY Strategy Set, revalidates every Strategy Version/template/schema/configuration/implementation identity, requires the code-owned `LOCAL_PAPER_TICK_BIDASK` binding, and derives a deterministic immutable pipeline snapshot.
- The paper Feature adapter consumes the existing Momentum dashboard's canonical `FeatureEngine` projection (`price`, `vwap`, `previous_intraday_high`) and does not recalculate market features. It composes ANY/ALL/AT_LEAST_N only at the strategy-decision boundary and preserves per-version evidence plus primary attribution.
- Both existing atomic entry Templates now declare an explicit Local Paper binding. Because this changes Template identity, already-published versions based on the old Template correctly fail activation and must be republished before use; they are not silently reinterpreted.
- Initial atomic paper runtime unit evidence is green: `4 passed` covers exact-version resolution, ANY attribution, ALL non-trigger, stale projection rejection, and identity drift fail-closed behavior.

## 2026-08-22 Phase 4 candidate disposition

- The implementation converges the existing FeatureEngine projection, Journal-first strategy intent path, RiskGate, SimulationService and Dashboard controller; there is still one market-data and one execution path.
- `LocalPaperPipelineSnapshot` binds the required exact ENTRY Strategy Set plus code-owned Feature adapter, Execution Policy, Hard Risk Policy and fixed Exit Policy identities. FILTER and atomic EXIT sets are not fabricated before real strategies/runtime bindings exist; the fixed stop-loss/take-profit/EOD lifecycle remains explicit in the snapshot.
- Existing immutable Strategy Versions published before the new Local Paper runtime binding have a different Template digest. Activation rejects them and requires a newly published version rather than changing their meaning.
- `ProposedOrderCommand` and `ApprovedOrderCommand` are different runtime types. The approval evidence binds proposal, Risk snapshot, effective policy and decision digests, and the Simulation adapter rejects a Proposed command.
- Durable controller checkpoints are content-addressed Journal records scoped by exact owner and pipeline digest. Recovery restores signal dedup state but never restores quote freshness; a new live Tick/BidAsk is still required after restart.
- Web mutations reuse the accepted loopback Host/proxy boundary, exact Origin comparison and CSRF token. The form cannot start without a PostgreSQL exact Strategy Set selection.
- Final evidence is green: focused `55 passed`, no-DSN full `1166 passed, 20 skipped`, disposable PostgreSQL 17 full `1186 passed`, plus compilation, JavaScript syntax, browser smoke and whitespace checks.
- Gate G4 remains a Review decision. Phase 5, broker integration and real-money execution remain blocked.

## 2026-08-22 Gate G4 Review findings

- Exact-version identity is insufficient for Paper activation: every member lifecycle projection must be `PAPER_APPROVED` at activation, and the activation snapshot needs the projection sequence/event/digest so later lifecycle changes do not erase what was admitted.
- `POST /api/simulation/strategy-intents` accepts caller-supplied raw strategy identity and therefore bypasses exact-set lifecycle admission. The safest MVP boundary is to remove this HTTP mutation; internal Journal-first intent submission remains available behind the resolved controller.
- The controller's operator daily-loss precheck and the command service's fixed RiskPolicy are two different authorities. The run must construct one effective policy using the monotonic minimum and the command approval digest must bind that exact policy.
- `same_side_pending_order=False` prevents Hard Risk from observing existing pending orders. More importantly, fill-time position aggregation currently trusts the first fill's owner. Reservation admission and fill mutation both need a single owner-compatibility invariant.
- ALL has an availability invariant independent of ordinary false predicates: any BLOCKED member yields BLOCKED and otherwise any INSUFFICIENT member yields INSUFFICIENT, even when another member is NOT_TRIGGERED.
- Review evidence kept Gate G4 NOT PASSED despite the prior green regression because the missing negative paths were not covered. These findings require adversarial tests before re-review.

## 2026-08-22 Gate G4 remediation disposition

- Paper activation now uses one PostgreSQL transaction to lock and revalidate the immutable Strategy Set, every member Version, the lifecycle projection, and its referenced last event. Projection and event digests are both verified, and only exact `PAPER_APPROVED` projections are admitted into the Pipeline snapshot.
- The browser no longer has a raw strategy-intent mutation route. Exact-set controller evaluation is the only HTTP-reachable source of automated BUY/SELL intents.
- Effective Hard Risk is an activation-owned policy: `max_daily_loss=min(system ceiling, operator limit)`. Activation, command, RiskSnapshot, RiskDecision digest and runtime checkpoint preserve a single digest-linked evidence chain; restart rejects a different policy digest while leaving the controller stopped.
- Local Paper order reservation rejects a same-symbol BUY owned by a different manual/strategy owner under the simulator lock. Fill repeats the owner comparison before position aggregation, covering restored or corrupted pending state.
- ALL composition now gives unavailable evidence precedence after the all-triggered case: BLOCKED first, then INSUFFICIENT_DATA, then ordinary NOT_TRIGGERED.
- Journal record fingerprint includes server `occurred_at`, so durable activation replay cannot simply append the same request with a new timestamp. The flow now resolves the operation by scope/key and compares canonical payload content; same content replays the original sequence, while different content conflicts.
- Nested checkpoint payloads are immutable mapping projections in the Journal. Rebuild now canonicalizes from the stored `payload_json`, avoiding non-serializable nested `mappingproxy` values.
- Start activation records actor/config/idempotency durably. Stop and kill-switch actor/idempotency operations remain an explicit process-local MVP Important limitation and are documented; this is not represented as complete multi-user audit.
- Gate G4 is still an independent Review decision. Phase 5, broker integration and real-money execution remain blocked.

## 2026-08-22 Gate G4 follow-up Review findings

- First exact-set BUY admission has a circular dependency: fresh-book Hard Risk runs before an order exists, but quote subscriptions were derived only from positions and active orders. A bounded owner-scoped watch must join the existing subscription reconciliation before evaluation; Risk must still consume the same canonical SimulationService BidAsk snapshot.
- Runtime activation currently installs the Effective Hard Risk Policy before controller checkpoint validation. A drift rejection therefore leaves a policy side effect even though the controller remains stopped. The correct boundary is pure policy preview, checkpoint validation against the preview digest, then durable activation and policy installation.
- The accepted lifecycle, effective daily-loss, cross-owner fill isolation, raw-route removal, ALL availability precedence, and activation replay remediations remain closed.
- Gate G4 remains `NOT PASSED`; Phase 5 and all broker/real-money scope remain unauthorized pending remediation and re-review.

## 2026-08-22 Gate G4 follow-up remediation disposition

- Quote readiness is now an explicit resource boundary, not an order side effect. Each owner can watch one candidate symbol; replacing or clearing that watch reconciles through the existing provider subscription set and never creates an order. Hard Risk still uses `SimulationService.risk_snapshot()` from the same BidAsk state.
- The first evaluation intentionally records `WAITING_BOOK` without consuming the strategy decision digest. Once a complete fresh BidAsk arrives, the same decision can enter the normal Journal -> Proposed -> Hard Risk -> Approved -> Simulation flow.
- Effective Risk preview is deterministic and mutation-free. Controller recovery uses the preview digest, while `activate_run()` verifies the expected digest before Journal/install. A checkpoint drift therefore occurs before any new policy or activation operation is committed.
- Subscription reconciliation is serialized across watch/order/position owners, preventing an older provider sync from overwriting a newer desired set. Preview/commit digest conflict also fails before either activation Journal append or policy install.
- Focused/full/PostgreSQL/static evidence is green (`112`, `1180 + 21 skipped`, `1201`). Gate G4 remains a separate Review decision and Phase 5 remains unauthorized.

## 2026-08-22 Gate G4 final Review disposition

- Final verdict is `APPROVE`: Gate G4 is `PASSED / MVP CONDITIONAL GO`, with no remaining Blocking or new Important finding.
- The Review independently confirmed WAITING_BOOK-before-order, one-symbol owner watch, merged subscription ownership, fresh-book Hard Risk re-admission, watch release, subscription race convergence, and side-effect-free restart/digest-conflict rejection.
- Phase 5 is only `ELIGIBLE`; implementation remains unauthorized. Broker order, CA, trade subscription, and real-money capabilities remain prohibited.
- Stop/kill-switch durable actor/idempotency audit is accepted as a single-machine MVP hardening backlog, not a completed multi-user control.

## 2026-08-22 Phase 5 authorization and first-slice scope

- Phase 5 is now explicitly authorized. The Implementation Plan fixes the first order as parameterized rolling return followed by parameterized volume acceleration; more complex indicators/exits remain deferred.
- Each strategy must remain an independently publishable/versioned Template with its own file and schema. Parameters must resolve to distinct Feature Requests/state identities rather than alter only saved JSON.
- Runtime support must be declared from real Feature adapter availability. Unsupported Local Paper semantics must fail closed rather than inherit backtest Kbar behavior or claim Tick/BidAsk parity.
- Gate G5 remains a Review decision; no broker or real-money scope is introduced.

## 2026-08-22 Phase 5 current-state reconciliation

- The deployed allowlist currently has two independent ENTRY files under `atomic_strategies/entries/`: above VWAP and breakout previous high. Their Templates declare static Feature requirements and both backtest/local-paper bindings.
- `FeatureSpecificationRegistry` currently contains only `vwap_session_v1` and `previous_intraday_high_v1`. `CompletedOneMinuteKbarFeatureAdapter` only projects VWAP and previous high from aggregate engine context; it has no rolling-price/rolling-volume state owner yet.
- `resolve_feature_requests(template)` currently resolves only Template-static request parameters and cannot derive a Feature Request window from an immutable Strategy Version's validated parameters. Phase 5 must add an explicit parameter-to-request resolver rather than merely save `window_minutes` in JSON.
- Existing parameter identity tests already reserve `rolling_return_v1` examples, but the Feature is intentionally absent from the Registry. The first Phase 5 slice must turn that identity helper into an actual runtime-owned Feature path and add golden behavior tests.
- The existing strategy-management Web is already schema-driven and persists Draft/Version/Strategy Set data through the generic PostgreSQL catalog, so Phase 5 does not need strategy-specific tables or hard-coded form fields. Registering code-owned Templates and schemas is the persistence/Web integration point.
- The completed-Kbar engine evaluates after applying the current completed bar. A parameterized backtest adapter can therefore use per-request, per-symbol, per-session rolling state keyed by `FeatureRequestSpec.state_key`; it must reset at every engine run so replaying the same resolved Registry stays deterministic.
- `rolling_return_v1` preserves the frozen formula by comparing the current completed close with the exact completed bar at `as_of - window_minutes`; a missing/gapped anchor is `INSUFFICIENT_DATA`, not a nearest-price guess.
- `rolling_volume_ratio_v1` uses the frozen current window and median of prior non-overlapping windows. On completed 1-minute Kbars, every accepted window must contain the expected contiguous bar count; missing windows remain unavailable and the configured minimum complete baseline count is enforced.
- The current Local Paper projection exposes only legacy fixed 2-minute Tick features. Advertising arbitrary 3-minute versions as Local Paper compatible would be false. The first Phase 5 slice will declare the two new Templates `BACKTEST_KBAR_1M` only; exact-set Local Paper activation will fail closed until a parameterized Tick adapter is separately implemented and tested.

## 2026-08-22 Gate G5 Review findings

- Independent Review kept Gate G5 `NOT PASSED` because `CompletedKbarFeatureState` retains one state entry per session for the entire Run; each deque is bounded, but the state-key map is not bounded across multi-session history.
- The remediation will make the engine's ordered session boundary explicit through the existing Registry and adapter ports. The completed-Kbar state owner will evict the previous session before accepting bars from the next session, bounding retained state to the current session's request/symbol set.
- The volume baseline currently skips any incomplete window and can replace a missing middle window with an older complete window. This contradicts the published fail-closed continuity claim.
- Frozen remediation semantics: baseline windows are examined newest to oldest; accepted windows must form a contiguous newest prefix. Missing windows are allowed only as the oldest warm-up suffix, and any complete older window after a missing newer window proves a middle gap and returns `INSUFFICIENT_DATA`.
- Gate G5 and the next strategy batch remain closed until boundedness/gap golden tests and the full regression evidence pass. Local Paper parameterized Tick support, broker transport, CA, trade subscription, and real-money execution remain outside scope.
- The engine now announces each ordered session through the existing Registry/application port. The atomic adapter forwards that boundary to the completed-Kbar adapter, which clears the prior session map before new state keys are created; direct adapter use performs the same idempotent session check.
- The 100-session regression keeps `active_state_count == 1` for one symbol/request on every transition, demonstrating retention is bounded by the active session rather than historical session count.
- The volume golden pair proves the precise boundary: at 09:09, four newest complete 2-minute baselines plus one unavailable oldest warm-up window produce ratio `1`; at 09:11, a missing 09:05 Kbar creates a middle gap and returns `baseline_volume_windows_non_contiguous` instead of ratio `2`.
- `rolling_volume_ratio_v1` now carries a v2 implementation digest and explicit non-suffix missing/warm-up semantics. The schema-driven Web help exposes the same rule, preventing a persisted parameter from implying that arbitrary 4-of-5 windows are accepted.

## 2026-08-22 Gate G5 final disposition

- Independent Review returned `APPROVE`; both session-state boundedness and volume-gap semantics blockers are closed with no new Blocking or Important finding.
- Gate G5 is formally `PASSED / MVP SCOPED GO`, and the Phase 5 first slice is approved.
- Reviewer evidence: focused `36 passed, 8 skipped`, full no-DSN `1193 passed, 22 skipped`, and `git diff --check` passed. PostgreSQL was correctly not rerun because this remediation changed no database contract or migration.
- The disposition remains scoped: it does not authorize a later strategy batch, parameterized Local Paper Tick adapter, broker integration, or real-money execution.
