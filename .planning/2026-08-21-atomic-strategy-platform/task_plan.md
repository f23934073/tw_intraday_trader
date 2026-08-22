# Task Plan: Atomic Strategy Platform

## Goal

Produce a repository-grounded, implementation-ready plan for a PostgreSQL-only, versioned atomic-strategy platform. Each independently testable condition is one registered strategy implementation; parameters and compositions are configured in the Web UI, validated server-side, persisted as immutable versions in PostgreSQL, and snapshotted by backtest and local-paper runs. This planning slice must not add broker or real-money execution.

## Current Phase

Phase 28 Atomic ORB approved; Gate G7 PASSED / MVP SCOPED GO

## Implementation Gate

Contract Review returned **APPROVE / GO** for the frozen B1–B5 contracts, and the user explicitly authorized Phase 1 implementation. The final short implementation Reviews subsequently returned **APPROVE / Gate G1 PASSED** and **APPROVE / Gate G2 PASSED** with no remaining blocking or important finding. The user explicitly authorized Phase 3 Backtest Qualification on 2026-08-22. After two remediation rounds, the final MVP Review approved Gate G3 as **PASSED / MVP CONDITIONAL GO** for a loopback, single-user, trusted-PostgreSQL, manual-review deployment. The user separately authorized Phase 4, and the final follow-up Review approved Gate G4 as **PASSED / MVP CONDITIONAL GO**. The user then authorized Phase 5; its first parameterized rolling-strategy slice and remediation received independent **APPROVE / Gate G5 PASSED / MVP SCOPED GO** on 2026-08-22.

| ID | Blocking contract | Plan status | Review status |
|---|---|---|---|
| B1 | Strategy parameters resolve to parameterized Feature Requests; feature cache/state keys include parameter digest | Accepted | REVIEWED / CLOSED |
| B2 | Shared Feature Specification with explicit Tick/BidAsk, intraday Kbar, and daily Kbar adapters; Section 22 ownership frozen | Accepted | REVIEWED / CLOSED |
| B3 | First Publish needs Draft-scoped idempotency/result mapping; all new persistence must be PostgreSQL-only | Accepted | REVIEWED / CLOSED |
| B4 | Proposed/Approved ordering, monotonic merge, and complete exit bypass matrix | Accepted | REVIEWED / CLOSED |
| B5 | Evaluation persistence uses full/bounded/aggregate/debug retention tiers instead of unbounded rows | Accepted | REVIEWED / CLOSED |

Gate rules:

- Contract Gate G0 and implementation Gates G1/G2 are passed. Gate G3 is `PASSED / MVP CONDITIONAL GO` under the frozen single-user/manual-review constraints recorded in Phase 20.
- Closed blockers are not reopened without new contradictory evidence.
- Gate G4 is `PASSED / MVP CONDITIONAL GO`; Phase 5 first slice is `APPROVED` and Gate G5 is `PASSED / MVP SCOPED GO`.
- Gate G6 is `PASSED / MVP CONDITIONAL GO`; Parameterized Local Paper is approved for the four registered ENTRY strategies. Dashboard/Momentum runtime has no cross-day hot rollover, so the single-user MVP must restart Dashboard once per trading day. Broker transport, CA, trade subscription, Shioaji orders, and real-money execution remain prohibited.
- Gate G7 is `PASSED / MVP SCOPED GO`; Atomic ORB Strategy is approved as the fifth independent ENTRY strategy. This approval does not authorize another strategy batch, push, broker transport, or real-money execution.

## Phases

### Phase 1: Requirements and current-state reconciliation

- [x] Reconcile the agreed atomic-strategy terminology with current strategy, backtest, database, and automated local-paper code.
- [x] Separate existing reusable foundations from hard-coded Momentum-specific behavior.
- [x] Record explicit scope, non-goals, compatibility constraints, and unresolved decisions.
- **Status:** complete

### Phase 2: Domain and persistence contracts

- [x] Define StrategyTemplate, StrategyVersion, StrategySet, StrategySetMember, and StrategyRunSnapshot contracts.
- [x] Separate `role`, `session_phase`, order/position action, data requirements, and runtime-mode binding.
- [x] Define immutable versioning, definition/config digests, lifecycle states, and migration compatibility.
- **Status:** complete

### Phase 3: Atomic strategy and composition contracts

- [x] Define the common strategy interface and one-file-per-strategy packaging.
- [x] Define parameter schema validation and trigger lifecycle semantics.
- [x] Define ALL, ANY, AT_LEAST_N, priority, attribution, and conflict rules; explicitly defer WEIGHTED.
- [x] Define entry, exit, filter, and independent Hard Risk Policy ownership boundaries.
- **Status:** complete

### Phase 4: Web strategy management

- [x] Define APIs for templates, parameter schemas, drafts, immutable versions, lifecycle transitions, and strategy sets.
- [x] Define Traditional Chinese UI flows for strategy editing, validation, cloning, version diff, backtest launch, approval, and the separately gated future local-paper activation.
- [x] Define permissions and audit behavior without executing database-supplied code.
- **Status:** complete

### Phase 5: Backtest integration and reproducibility

- [x] Snapshot exact strategy versions, parameters, composition, dataset, costs, engine version, and code identity for every run.
- [x] Define per-strategy and per-combination attribution, comparable metrics, and trade-level evidence.
- [x] Define out-of-sample, walk-forward, multiple-testing, and promotion gates.
- **Status:** complete

### Phase 6: Local-paper runtime integration

- [x] Plan replacement of the Momentum-specific controller dependency with registered strategy selection and shared orchestration.
- [x] Define signal deduplication, cooldown, order policy, position ownership, exits, risk, restart/recovery, and kill-switch behavior.
- [x] Preserve local-paper-only execution and Shioaji market-data-only boundaries.
- **Status:** complete

### Phase 7: Verification, rollout, and handoff

- [x] Define migrations, compatibility adapters, tests, observability, staged rollout, rollback, and Definition of Done.
- [x] Cross-check the plan against current repository behavior and existing dirty-worktree ownership.
- [x] Verify this planning slice changes planning documents only.
- **Status:** complete

### Phase 8: Pre-implementation Review remediation

- [x] Write B1 parameterized Feature Request and cache/state identity contracts into the Implementation Plan.
- [x] Replace the proposed third Feature calculator with shared Feature Specifications and explicit runtime/cadence adapters.
- [x] Separate mutable Draft, immutable Version, append-only lifecycle events, and transactional Publish revalidation.
- [x] Remove Risk from ordinary Strategy roles/composition and define an always-enforced Hard Risk Policy boundary.
- [x] Replace unbounded evaluation-row persistence with full, bounded, aggregate, and DEBUG retention tiers.
- [x] Add important contracts: exact-version membership, legacy compatibility, runtime-mode bindings, ENTRY/EXIT versus order-side ownership, local-only security, fixed composition semantics, lifecycle event loop, idempotent mutation, and a minimal backtest vertical slice.
- [x] Perform the second pre-implementation Review against the revised documents.
- [x] Record B1, B2, B5 as CLOSED and B3, B4 as remaining OPEN.
- **Status:** complete — second Review returned Request Changes

### Phase 9: B3/B4 follow-up remediation

- [x] Unify command order as TradeIntent -> Execution Policy -> ProposedOrderCommand -> Hard Risk Admission -> ApprovedOrderCommand -> Adapter.
- [x] Define deterministic monotonic policy merge for upper bounds, lower safety bounds, allowlists, blocklists, require booleans, allow booleans, and transport kill switch.
- [x] Define which entry-only controls a risk-reducing exit may bypass and which command/data/durability controls it may never bypass.
- [x] Define complete lifecycle transition table, evidence guards, RETIRED terminal behavior, and PAUSED reactivation preflight.
- [x] Define lifecycle event schema, expected_sequence, row-lock compare-and-append, idempotency conflict, projection rebuild, and quarantine behavior.
- [x] Add lifecycle GET/events/transition APIs and transactional conflict contract.
- [x] Freeze Section 22 ownership accepted by B2 Review.
- [x] Fix composition terminology drift so v1 consistently uses AT_LEAST_N and defers weighted composition.
- [x] Perform follow-up pre-implementation Review of B3/B4.
- [x] Record B3/B4 as still OPEN due to idempotency lock ordering, SQLite serialization, outbox atomicity, and incomplete declared-control matrix.
- **Status:** complete — follow-up Review returned Request Changes

### Phase 10: B3/B4 concurrency, outbox, and bypass completeness

- [x] Make the transaction-external idempotency lookup an optional fast path only and require authoritative recheck after serialization.
- [x] Ensure same-key/same-digest replay wins over stale expected_sequence; use conditional insert + in-transaction reread for unique-conflict defense.
- [x] Define PostgreSQL row-lock serialization; record that the earlier SQLite compatibility proposal is void and superseded by the PostgreSQL-only decision in Phase 11.
- [x] Require lifecycle event, state projection, and outbox row in the same transaction; define at-least-once dispatch and idempotent consumption.
- [x] Add explicit exit behavior for `max_pending_notional`, `blocked_symbols`, `blocked_strategy_versions`, `global_command_blocked_symbols`, and `allow_odd_lot`.
- [x] Add fail-closed rule: any Hard Risk check not explicitly marked bypassable cannot be bypassed by exit/flatten.
- [x] Perform next pre-implementation Review of B3/B4.
- [x] Record B4 as CLOSED and B3 as OPEN due only to first-Publish idempotency identity/result scope.
- **Status:** complete — Review returned Request Changes; user then selected PostgreSQL-only persistence

### Phase 11: PostgreSQL-only first-Publish contract

- [x] Freeze PostgreSQL as the only writer/authority for all new atomic-strategy platform persistence; prohibit SQLite fallback.
- [x] Limit any existing SQLite use to an optional one-time read-only import into PostgreSQL with count/digest reconciliation.
- [x] Define first-Publish idempotency scope as `(draft_id, idempotency_key)` rather than the not-yet-created Version ID.
- [x] Add `strategy_publish_operations` and Draft published-result references.
- [x] Define same-key replay, digest conflict, different-key `DRAFT_ALREADY_PUBLISHED`, Draft revision conflict, and concurrent version allocation.
- [x] Require Version, PUBLISHED event/state/outbox, publish-operation result, and Draft references in one PostgreSQL transaction.
- [x] Add PostgreSQL concurrent Publish and commit-after-response-loss retry tests to the plan.
- [x] Remove SQLite lifecycle runtime/retry contracts and require PostgreSQL preflight/fail-closed behavior.
- [x] Perform next pre-implementation Review of B3.
- [x] Mark B3 `REVIEWED / CLOSED`; Review found no blocking regression in B1, B2, B4, or B5.
- [x] Obtain explicit implementation authorization after the Review verdict became GO.
- **Status:** complete — APPROVE / GO; implementation authorized

### Phase 12: Implement PostgreSQL Phase 1 vertical slice

- [x] Add numbered PostgreSQL migration SQL for Template, Draft, Version, Publish Operation, lifecycle event/state/outbox, and exact-version Strategy Set persistence.
- [x] Add migration acceptance coverage through the existing migration runner; repository code must not create schema at runtime.
- [x] Add domain models, parameter-schema validation, Draft sealing, lifecycle transition rules, and repository ports without infrastructure imports.
- [x] Implement PostgreSQL repository transactions for Draft creation and first Publish replay/conflict semantics.
- [x] Add disposable PostgreSQL fixtures, dependency setup, configuration fail-closed checks, and README instructions.
- [x] Implement shared Feature Specifications, completed-1m adapter, and separate above-VWAP / breakout-previous-high strategy files.
- [x] Resolve exact strategy versions into a minimal backtest set/run snapshot with deterministic attribution and bounded evidence.
- [x] Run focused migration/domain/repository/strategy tests, then the relevant regression suite and static checks.
- [x] Record files changed, residual risks, and Phase 1 Gate G1 disposition.
- **Status:** implementation candidate complete, but Gate G1 was reopened by implementation Review; prior `1100 passed, 10 skipped` evidence is withdrawn because the suite is time-dependent

### Phase 13: Gate G1 implementation Review remediation

- [x] Snapshot each resolved Feature Specification digest, feature implementation digest, and explicit as-of semantics in every atomic backtest run.
- [x] Make same-key Publish replay resolve from durable PostgreSQL operation state before requiring the currently deployed Template Registry.
- [x] Replace split command/simulator clocks in the affected trade-management fixtures with one fixed Asia/Taipei clock; post-fix full regression is green.
- [x] Verify Strategy Set relational rows against persisted `snapshot_json` and `snapshot_digest` on read; fail closed on drift.
- [x] Expand migration integration coverage to all atomic-platform tables, required constraints, and named indexes.
- [x] Guard destructive PostgreSQL test cleanup with a test-database name or explicit sentinel before `DROP SCHEMA ... CASCADE`.
- [x] Run focused tests, disposable PostgreSQL contract tests, full regression, compilation, and whitespace checks.
- [x] Update Gate G1 only after a short implementation Review confirms the blockers are closed.
- **Status:** complete — final Review returned APPROVE / Gate G1 PASSED with no remaining blocking or important finding

### Phase 14: Implement Phase 2 Backtest Web Management

- [x] Record the final G1 Review verdict and Phase 2 authorization in all planning artifacts.
- [x] Reconcile the existing Dashboard/API seams with the Phase 2 Template, Draft, Version, Strategy Set, and Backtest Launcher contracts.
- [x] Expose code-owned Template/Schema read APIs and PostgreSQL-only Draft create/update/get/validate/publish/clone flows.
- [x] Expose immutable Version listing/detail/diff and exact-version Strategy Set create/list/detail flows.
- [x] Connect an exact-version Strategy Set to the existing historical Backtest Launcher and preserve the complete reproducibility snapshot.
- [x] Build the Schema-driven Traditional Chinese Dashboard flow without accepting arbitrary code, import paths, or raw executable JSON.
- [x] Enforce loopback-only mutation, mutation-origin/CSRF, idempotency, audit, and fail-closed PostgreSQL behavior.
- [x] Add domain/repository/API/frontend/browser tests and run focused plus full regression evidence.
- [x] Submit the completed slice for Gate G2 Review; do not start local-paper or broker integration.
- **Status:** implementation candidate complete — READY FOR REVIEW; Gate G2 remains NOT PASSED until an implementation Review approves it

### Phase 15: Gate G2 implementation Review remediation

- [x] Protect atomic Run cancel/retry/clone with the same loopback, Origin, CSRF, strict-input, idempotency, and audit boundary as atomic Run start.
- [x] Replace long-lived shared psycopg connections with bounded checkout-per-operation PostgreSQL adapters for Web handlers and background workers.
- [x] Make Run creation compare request/config digest, serialize concurrent same-key creation, and replay only same-key/same-digest results.
- [x] Replay the original immutable Draft mutation result rather than re-reading the current mutable Draft; preserve browser idempotency keys across response-loss retries.
- [x] Split browser clone behavior by legacy versus atomic Run and add an actual Version diff selection/rendering flow.
- [x] Forbid unknown Atomic request fields, add Strategy Set change note, durable success/conflict audit, and Audit query/UI.
- [x] Add hostile-Origin/no-CSRF, unknown-field, response-loss, same-key/different-digest, concurrent composition, audit, atomic clone, and Version diff tests.
- [x] Run the full no-DSN regression and static checks; record PostgreSQL integration tests as explicit skips when no disposable DSN is available.
- [x] Submit the remediation candidate for a short Gate G2 Review; do not start Phase 3.
- **Status:** remediation candidate complete — READY FOR REVIEW; Gate G2 remains NOT PASSED and Phase 3 remains blocked

### Phase 16: Gate G2 Host/origin and deterministic-regression remediation

- [x] Record the follow-up Review verdict: Gate G2 remains NOT PASSED and Phase 3 remains blocked.
- [x] Reproduce public `Host` token disclosure, public `Host` atomic mutation, and wrong scheme/port Origin acceptance.
- [x] Reproduce the two wall-clock/date-dependent regression failures on 2026-08-22.
- [x] Enforce loopback HTTP `Host` at the ASGI boundary, including the capabilities endpoint that returns the CSRF token.
- [x] Compare mutation Origin against the complete request origin (`scheme://host:port`) after validating the Host.
- [x] Add public-Host plus loopback-peer and wrong scheme/port negative tests.
- [x] Inject a deterministic Mock history anchor and local-paper clock into the two affected tests.
- [x] Run focused security/date tests, full regression, Python/JavaScript checks, and `git diff --check`.
- [x] Update Gate G2 evidence and submit the candidate for another short Review; do not start Phase 3.
- **Status:** complete — final Review returned APPROVE / Gate G2 PASSED with no remaining blocking or important finding

### Phase 17: Implement Phase 3 Backtest Qualification

- [x] Record the final G2 Review verdict and Phase 3 authorization in all planning artifacts.
- [x] Reconcile existing explicit OOS metrics, comparison persistence, atomic Run Snapshots, Feature Requests, and adapter identities with the Phase 3 contracts.
- [x] Freeze a deterministic qualification protocol with explicit train/validation/OOS boundaries, walk-forward folds, baseline/challenger comparability, and multiple-testing history.
- [x] Add PostgreSQL-only immutable qualification evidence, digest integrity, idempotent mutation, audit, and migration acceptance coverage.
- [x] Implement qualification application services that fail closed on non-comparable or incomplete Runs and never mutate Strategy lifecycle state automatically.
- [x] Preserve parameterized Feature Request/runtime adapter identity in qualification evidence; explicitly defer a real rolling Feature state/cache owner to Phase 5 instead of claiming the helper is runtime integration.
- [x] Add strict local-only API and a Schema-driven Traditional Chinese Web flow for creating and reviewing qualification evidence.
- [x] Add focused domain/PostgreSQL/API/browser tests, run full regression/static checks, and record Gate G3 evidence.
- [x] Submit the completed Phase 3 slice for implementation Review; do not start Phase 4.
- **Status:** implementation candidate complete — READY FOR REVIEW; Gate G3 NOT PASSED and Phase 4 remains blocked

### Phase 18: Gate G3 qualification-semantics remediation

- [x] Record the Request Changes verdict and keep Gate G3/Phase 4 closed.
- [x] Replace request-controlled qualification thresholds with a server-owned policy floor and require meaningful train/validation/OOS coverage plus independent OOS dates.
- [x] Add a PostgreSQL authoritative experiment-family ledger with monotonic attempt history and family-head serialization.
- [x] Make compare and qualification share one comparability contract, including explicit Feature adapter/runtime identities while permitting the intended Strategy Version difference.
- [x] Verify `digest(run.config) == run.config_digest` before qualification and bind actor/change note to the qualification integrity digest.
- [x] Remove the unsupported G3 runtime-state claim and explicitly defer the real Feature state/cache owner to Phase 5; no speculative cache was added.
- [x] Expand the Reviewer UI to display authoritative family history, adjusted alpha, fixed policy, windows, folds, and complete Run/Feature/adapter identities.
- [x] Add adversarial domain/PostgreSQL/API/UI tests and rerun focused, no-DSN, disposable PostgreSQL, compilation, JavaScript, browser, and whitespace verification.
- [x] Submit the remediated Phase 3 candidate for a short Review; do not start Phase 4.
- **Status:** remediation candidate complete — READY FOR REVIEW; Gate G3 NOT PASSED; Phase 4 remains blocked

### Phase 19: Gate G3 identity/isolation remediation

- [x] Record the follow-up Request Changes verdict and keep Gate G3/Phase 4 closed.
- [x] Reject every Walk-forward fold whose OOS overlaps the Primary OOS; cover the exact overlap exploit.
- [x] Replace Baseline Run ID family ownership with a stable server-derived research-baseline identity so equivalent Baseline Runs share one attempt budget.
- [x] Introduce one fail-closed Run identity verifier covering config digest plus row/config Dataset ID and digest equality; apply it to Baseline, Challenger, compare, and all family attempts.
- [x] Make the family snapshot digest reconstructable by persisting the immutable canonical snapshot body or using a stable projection; expose current/historical hypothesis qualification linkage.
- [x] Add domain/PostgreSQL/API/UI adversarial tests for overlap, equivalent Baseline family reuse, Dataset-row tampering, and snapshot reconstruction.
- [x] Run focused no-DSN and disposable PostgreSQL tests, full regressions, compilation, JavaScript, browser, and whitespace checks.
- [x] Submit the second remediation candidate for short Review; do not start Phase 4.
- **Status:** second remediation candidate complete — READY FOR REVIEW; Gate G3 NOT PASSED; Phase 4 remains blocked

### Phase 20: Gate G3 MVP conditional approval

- [x] Record the final Review verdict as `Gate G3: PASSED / MVP CONDITIONAL GO` for loopback, single-user, trusted-PostgreSQL, manual-review use only.
- [x] Preserve `REVIEW_ONLY_NO_LIFECYCLE_MUTATION`; Qualification may recommend human review but may not auto-promote, mutate lifecycle, or start Local Paper.
- [x] Freeze the current qualification policy and experiment-family contract; require an explicit migration plan for legacy `baseline_run_id` uniqueness before any contract upgrade.
- [x] Add the manual governance rule that equal `bars_sha256` plus an equal research contract is one research Dataset, regardless of Dataset ID or repackaging, and may not reset the attempt budget.
- [x] Register Dataset stable research identity and canonical Baseline revalidation as Phase 3 hardening backlog required before multi-user, external-network, auto-promotion, or real-trading scope.
- [x] Mark Phase 4 `ELIGIBLE` while retaining the separate explicit-authorization requirement; do not begin implementation in this phase.
- **Status:** complete — Gate G3 PASSED / MVP CONDITIONAL GO; Phase 4 ELIGIBLE but NOT AUTHORIZED

### Phase 21: Implement Phase 4 Local Paper Runtime

- [x] Record the explicit Phase 4 authorization and preserve the no-broker/no-real-money boundary.
- [x] Reconcile `continuous_strategy.py`, `strategy_flow.py`, `Journal`, `RiskGate`, `SimulationService`, quote adapters, persistence, and Dashboard controls against the frozen Phase 4 contract.
- [x] Replace Momentum-specific Web orchestration with an exact-version Strategy Set/Pipeline resolver while retaining the legacy direct-controller compatibility seam and existing feature/execution owners.
- [x] Enforce `TradeIntent -> Execution Policy -> ProposedOrderCommand -> Hard Risk -> ApprovedOrderCommand -> Simulation Adapter` without any broker command port; persist proposal/snapshot/policy/decision/approval digests.
- [x] Add deterministic ownership, signal deduplication, continuous fixed exit monitoring, kill switch, checkpoint/recovery, and fail-closed stale/missing evidence behavior.
- [x] Keep the generic paper runner `STOPPED` by default and require an explicit local start; preserve Shioaji as market-data-only.
- [x] Add focused domain/application/API/UI tests plus restart, stale quote, duplicate signal, risk rejection, owner isolation, kill-switch and position lifecycle coverage.
- [x] Run focused and full regression, disposable PostgreSQL, Python/JavaScript checks, browser smoke, and `git diff --check`; prepare the candidate for Gate G4 Review.
- **Status:** implementation candidate ready for Review — Gate G4 NOT PASSED; broker/real-money execution prohibited

### Phase 22: Gate G4 lifecycle, effective-risk, and owner-isolation remediation

- [x] Record the Request Changes verdict and keep Gate G4/Phase 5 closed.
- [x] Require every exact-set member to be `PAPER_APPROVED` at activation and snapshot lifecycle sequence, event ID, and projection digest.
- [x] Remove the raw `strategy_id/version` HTTP intent bypass or route it through exact-set activation.
- [x] Merge operator daily-loss with the system ceiling as `min(system, operator)` in the per-run Hard Risk Policy and persist the effective-policy evidence.
- [x] Reject cross-owner same-symbol pending reservations and revalidate owner compatibility atomically at fill time.
- [x] Make ALL preserve BLOCKED/INSUFFICIENT whenever any member is unavailable, including mixed NOT_TRIGGERED cases.
- [x] Add adversarial lifecycle, raw-API, effective-policy, pending/fill ownership, composition, recovery, and audit tests.
- [x] Run focused/full/disposable-PostgreSQL/static verification and prepare the remediation candidate for short G4 re-review.
- **Status:** remediation candidate ready for short Review — Gate G4 NOT PASSED; Phase 5 and broker/real-money execution prohibited

### Phase 23: Gate G4 quote-readiness and side-effect-free restart remediation

- [x] Record the follow-up Request Changes verdict and keep Gate G4/Phase 5 closed.
- [x] Add a bounded, owner-scoped quote watch before Hard Risk so the first exact-set entry can receive canonical Tick/BidAsk evidence without an existing order or position.
- [x] Split activation into a pure Effective Hard Risk preview/checkpoint-validation stage and a commit/install stage so failed restart cannot mutate installed risk policy.
- [x] Add streaming first-entry and failed-restart side-effect regression tests using the real Local Paper flow.
- [x] Run focused/full/static verification and prepare the candidate for a short G4 re-review.
- **Status:** follow-up remediation candidate ready for short Review — Gate G4 NOT PASSED; Phase 5 and broker/real-money execution prohibited

### Phase 24: Gate G4 MVP conditional approval

- [x] Record the final independent Review as `Gate G4: PASSED / MVP CONDITIONAL GO` with no Blocking or new Important finding.
- [x] Mark Phase 5 `ELIGIBLE but NOT AUTHORIZED`; do not start strategy expansion or any broker/real-money work.
- [x] Preserve stop/kill-switch durable actor/idempotency audit as mandatory hardening before multi-user, external-network, auto-promotion, or real-money scope.
- [x] Record independent evidence: remediation tests `70 passed` and `git diff --check` passed; PostgreSQL `1201 passed` remains candidate-provided evidence not rerun by the reviewer.
- **Status:** complete — Gate G4 PASSED / MVP CONDITIONAL GO; Phase 5 ELIGIBLE but NOT AUTHORIZED

### Phase 25: Phase 5 parameterized rolling strategies

- [x] Record explicit Phase 5 authorization while preserving Gate G5 and the no-broker/no-real-money boundary.
- [x] Reconcile the current Feature Registry/state owners, strategy Registry, parameter schemas, backtest adapter, Web forms, and Local Paper capability declarations for rolling return and volume acceleration.
- [x] Implement parameterized rolling-return as one independent strategy file with parameter-derived Feature Request identity, deterministic evaluation, and explicit runtime availability.
- [x] Implement parameterized volume-acceleration as one independent strategy file with parameter-derived Feature Request identity, deterministic evaluation, and explicit runtime availability.
- [x] Register both strategies in the code-owned allowlist and expose their schemas through the existing Web/PostgreSQL Draft/Publish flow without adding arbitrary code execution.
- [x] Add schema, Feature Request/state identity, golden evaluation, backtest snapshot, Web/API, and supported-runtime tests; fail closed where a runtime Feature adapter is unavailable.
- [x] Run focused/full/disposable-PostgreSQL/static/browser verification and prepare the first Phase 5 slice for Gate G5 Review.
- **Status:** approved — Gate G5 PASSED / MVP SCOPED GO; broker/real-money execution prohibited

### Phase 26: Gate G5 rolling-state and volume-gap remediation

- [x] Record the independent Request Changes verdict and keep Gate G5 plus all later strategy batches closed.
- [x] Evict completed-Kbar rolling state at every session transition so retained state is bounded by the active session rather than total run history.
- [x] Propagate session lifecycle through the existing engine -> Registry -> atomic adapter -> completed-Kbar adapter boundary without adding another state or market-data pipeline.
- [x] Freeze volume baseline semantics as a newest contiguous complete-window prefix; only the oldest warm-up suffix may be unavailable, while any middle/newer gap fails closed.
- [x] Update Feature Specification and Web parameter help to match the frozen volume-gap semantics.
- [x] Add multi-session boundedness, allowed oldest-warmup, and middle-gap golden regressions.
- [x] Run focused/full/static verification, update Gate evidence, and submit the candidate for a short G5 re-review; do not begin the next strategy batch.
- **Status:** complete — independent Review approved Gate G5 / MVP SCOPED GO; later strategies and broker/real-money execution are not part of this Gate

### Phase 27: Parameterized Local Paper Tick features

- [x] Commit the approved Phase 5 first slice without `.planning/.active_plan`, FinMind, live-trading, or odd-lot changes.
- [x] Record current completion: the Phase 5 slice is complete, while the two rolling strategies remain backtest-only until a real parameterized Local Paper adapter exists.
- [x] Reconcile exact-version Feature Requests with the existing canonical FeatureEngine/Tick store and Local Paper projection; do not introduce a third market-data or rolling-state pipeline.
- [x] Define request-aware Local Paper Feature contracts, runtime identities, session reset, exact completed-Kbar anchors, freshness, and volume-gap semantics matching the approved specifications.
- [x] Activate only the exact Feature Requests required by the selected PAPER_APPROVED Strategy Set and bind them into the activation snapshot/evidence.
- [x] Add Local Paper runtime bindings for rolling return and volume acceleration only after real request-aware values are available; unsupported/drifted requests must fail closed.
- [x] Add golden tests for 2m/3m separation, session reset, freshness, volume middle-gap rejection, activation replay, and exact-set composition.
- [x] Run focused/full/PostgreSQL-when-relevant/static verification and submit a Gate G6 candidate; do not add another strategy batch or broker execution.
- [x] Record independent Review approval, document the daily Dashboard restart limitation, and update the Local Paper strategy list to all four ENTRY strategies.
- **Status:** complete — Gate G6 PASSED / MVP CONDITIONAL GO; Parameterized Local Paper approved, broker/real-money execution prohibited

### Phase 28: Atomic opening-range breakout strategy

- [x] Reconcile distance-to-limit, external-ratio, ORB, and indicator candidates against actual Backtest plus Local Paper data capabilities.
- [x] Select ORB as the next complete slice because both runtimes have canonical completed 1-minute Kbars; defer distance-to-limit and external-ratio until truthful historical evidence exists.
- [x] Add one `opening_range_breakout_entry` implementation file with code-owned Web schema and parameter-derived Feature Request.
- [x] Add a shared completed-Kbar opening-range formula and Feature Specification with exact 09:00 continuity, warm-up, as-of, and implementation identity.
- [x] Connect the exact request to the existing Backtest adapter and existing Local Paper FeatureEngine projection without another market-data/state pipeline.
- [x] Add golden tests for parameter validation, exact range continuity, breakout/no-breakout, Backtest snapshot identity, Local Paper request evidence, and registry/Web exposure.
- [x] Run focused/full/static verification and submit a Gate G7 implementation candidate; do not add distance-to-limit, external-ratio, broker, CA, trade subscription, or real-money work.
- [x] Change the ORB boundary from `>=` to strict `>` so equality at zero buffer cannot create an ENTRY signal.
- [x] Add equality and strictly-above threshold regressions, then rerun focused/full/static verification.
- [x] Record independent Review approval and preserve the G7 scope boundary.
- **Status:** complete — Gate G7 PASSED / MVP SCOPED GO; Atomic ORB approved, broker/real-money prohibited

## Decisions Made

| Decision | Rationale |
|---|---|
| Treat each independently testable condition as an atomic strategy | Enables standalone backtests, reuse, and explicit composition. |
| Remove `limit-up acceleration` as an aggregate strategy concept | Its prior evidence rules become independent strategies such as above-VWAP, breakout, rolling return, volume acceleration, distance-to-limit, and external-ratio strategies. |
| Keep executable Python in an allowlisted Registry | The database supplies definitions, versions, parameters, and compositions; it must never supply arbitrary executable code. |
| Model template, version, set, and run snapshot separately | Preserves flexibility while keeping historical runs reproducible. |
| Separate `role` from `session_phase` | `ENTRY/EXIT/FILTER/CONTEXT` and `PRE_MARKET/OPENING/INTRADAY/END_OF_DAY/POST_MARKET` are independent dimensions; Risk is not a strategy role. |
| Separate Draft, immutable Version, and lifecycle event | Parameter changes create a new version; current status is an append-only projection and cannot rewrite historical meaning. |
| Resolve parameterized Feature Requests from exact versions | A Web change from 2m to 3m must build a different feature window and cache/state identity, not only save different JSON. |
| Share Feature Specifications, not one universal calculator | Tick/BidAsk, intraday Kbar, and daily Kbar need explicit adapters and may have declared non-parity. |
| Keep Risk outside Strategy Set composition | Hard Risk is always enforced and cannot be optimized away or weakened by user parameters. |
| Separate proposed and approved commands | Risk needs normalized quantity and price; only a command carrying approval evidence may reach an adapter. |
| Merge risk settings monotonically | Numeric, set, and boolean rules make “Web/DB can only tighten” executable and testable. |
| Use compare-and-append lifecycle events | Expected sequence, row lock, idempotency, and rebuild rules prevent concurrent lifecycle forks. |
| Recheck idempotency after serialization | Concurrent duplicate requests must replay the first success instead of becoming stale-sequence conflicts. |
| Use PostgreSQL as the sole atomic-platform database | One authoritative transactional store avoids backend-specific lifecycle semantics and fallback drift. |
| Scope first Publish idempotency to the Draft | Publish creates the Version ID, so retries require stable Draft operation/result mapping. |
| Persist lifecycle outbox atomically | Event, projection, and notification evidence survive or roll back together. |
| Default unlisted exit checks to no bypass | New RiskPolicy fields cannot silently weaken exit safety semantics. |
| Use bounded evaluation retention | Preserve trade and trigger evidence while aggregating ordinary non-triggers and bounding DEBUG traces. |
| Reference exact strategy version IDs in new sets | New runs are reproducible; legacy raw-ID snapshots remain readable without rewriting old digests. |
| Start with a backtest-only vertical slice | Validates the architecture with above-VWAP and breakout before Web breadth or local-paper integration. |
| Use the same cost, execution, capital, and exit assumptions for comparative entry-strategy research | Makes individual and combined strategy comparisons meaningful. |
| Keep real broker execution out of scope | Current authorization is local paper simulation with Shioaji market data only. |

## Recommended Defaults Pending Next Review

1. Use a mutable Draft entity; transactional Publish creates an immutable Version and append-only lifecycle event.
2. v1 supports ALL, ANY, and AT_LEAST_N with the blocked/insufficient semantics frozen in the Implementation Plan; defer WEIGHTED.
3. v1 allows one automatic Strategy Set owner per symbol and isolates manual positions; Hard Risk remains outside composition.
4. The first implementation slice is completed 1-minute Kbar backtest only; local-paper Tick/BidAsk requires a later Review and explicit authorization, with no parity claim.
5. Migrate above-VWAP and breakout previous high first; add rolling return and volume acceleration only after parameterized Feature Request isolation is proven.
6. Keep Dashboard mutations loopback-only single-user until authentication, RBAC, CSRF/origin protection, and security tests exist.
7. Persist full details for triggered/trading events, bounded unavailable samples, aggregate non-triggers, and only bounded/expiring DEBUG traces.
8. Use the Section 7.3 lifecycle transition table; RETIRED is terminal and PAUSED -> ACTIVE requires new preflight evidence.
9. Use ProposedOrderCommand as RiskGate input and allow only ApprovedOrderCommand at the adapter boundary.
10. Merge Hard Risk policy with min/max/intersection/union/OR/AND rules; reject any override that cannot be proven stricter.
11. Recheck lifecycle idempotency after acquiring PostgreSQL row lock; same key/digest replay precedes expected-sequence validation.
12. Store all new atomic-platform records in PostgreSQL only; reject SQLite configuration and never fallback when PostgreSQL is unavailable.
13. Insert lifecycle event, state projection, and outbox row in one transaction; dispatch only committed outbox rows.
14. Treat any exit/flatten Risk check not explicitly listed as bypassable as non-bypassable.
15. Scope first Publish to `(draft_id, idempotency_key)` and persist the resulting Version/Event mapping with Draft published references.

## Second Review Evidence

- Verdict supplied on 2026-08-21: Request Changes / NO-GO.
- B1, B2, and B5 were accepted as CLOSED; B3 and B4 remain OPEN.
- Focused baseline reported by the reviewer: `31 passed in 0.63s`. This confirms the existing baseline only and does not close B3/B4 contract blockers.
- No product or trading code was modified by that Review.

## Follow-up Review Evidence

- Verdict supplied on 2026-08-21: Request Changes / NO-GO; B1, B2, B5 remain CLOSED and B3, B4 remain OPEN.
- Previous lifecycle/schema/API, Proposed/Approved ordering, monotonic merge, and composition terminology fixes were accepted as improved.
- Remaining findings: lock-order idempotency replay race, missing SQLite serialization contract, incomplete exit matrix coverage, and non-atomic outbox wording.
- No tests were rerun in this Review; `31 passed in 0.63s` remains prior baseline evidence only.
- The Review did not modify source planning files or product code.

## Latest Review and User Decision

- Review verdict: Approve / GO at contract level. B1–B5 are `REVIEWED / CLOSED`.
- Accepted fixes: transition lock ordering, transactional outbox, PostgreSQL serialization, complete Exit bypass matrix, and prior composition/command contracts.
- B3 accepted: Draft-scoped Publish identity/result mapping, Draft row lock, replay/conflict matrix, Draft sealing, and atomic PostgreSQL persistence.
- User decision supersedes the SQLite compatibility proposal: do not store in SQLite; all new platform persistence must use PostgreSQL.
- Non-blocking implementation notes: add explicit numbered migration SQL and disposable PostgreSQL test fixture/dependency/README work.
- The Review did not rerun tests; `31 passed in 0.63s` remains prior baseline evidence only. The user then explicitly authorized implementation.

## Latest Implementation Review

- Verdict supplied on 2026-08-21: Request Changes; Gate G1 must return to `NOT PASSED`, and Phase 2 must not start.
- Blocking findings: incomplete Feature Specification identity/as-of snapshot, Publish replay coupled to the current Template Registry, and time-dependent full-regression failures after Asia/Taipei 20:00.
- Important findings accepted into Phase 13: Strategy Set snapshot integrity verification, full migration table/constraint/index acceptance, and a code-level guard before destructive PostgreSQL test schema cleanup.
- Reviewer evidence: focused `16 passed, 5 skipped`; full `8 failed, 1092 passed, 10 skipped`; compilation and whitespace passed. The eight failures invalidate the prior full-regression Gate evidence.
- PostgreSQL DSN was not configured for that Review, so real PostgreSQL tests must be rerun before G1 can be reconsidered.
- At the packaging-follow-up checkpoint, commit `0bcf61c` had closed only the wall-clock fixture finding and the other five Phase 13 items were still open. The later remediation disposition above supersedes that checkpoint.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| The root planning files belong to an active Freshness Calibration phase | 1 | Created an isolated atomic-strategy planning directory instead of overwriting the active plan. |
| A verification search pattern used shell backticks around `RISK`, causing an unintended command-substitution warning | 1 | No files were changed by the command; repeated the check with a safely quoted search pattern. |
| The stale-text validation matched the remediation checklist because it repeated the obsolete composition term | 1 | Reworded the checklist using only the frozen v1 terminology, then reran the validation. |
| Initial combined GO/planning patch expected the wrong isolated progress-file title | 1 | No file changed; split the update into exact-context patches and recorded the mismatch. |
| Focused test command used unavailable global `pytest` executable | 1 | No tests ran; switch to the repository `.venv/bin/python -m pytest` entrypoint. |
| Combined atomic backtest fixture expected breakout before its configured 09:02 entry window | 1 | Production behavior was correct; moved the fixture's breakout close to 09:02 and retained the explicit time guard. |
| Disposable PostgreSQL `initdb` found only Homebrew `libpq` without the `postgres` server binary | 1 | No database was created; inspect existing local server/Docker image, otherwise retain explicit integration-test skip rather than touching a developer database. |
| Optional Ruff check was unavailable in the project virtual environment | 1 | Do not download new tooling; use compileall, focused/full pytest, import-boundary checks, and whitespace/static validation already available in the repository. |
| Combined service/repository/test patch had an invalid patch hunk delimiter | 1 | No file changed; split the change into three exact-context patches. |
| Full regression expected migration 004 to remain the last file after adding migration 005 | 1 | Updated the existing ordered migration manifest assertion to include `005_atomic_strategy_platform.sql`. |
| Combined schema-digest patch used an outdated SQL placeholder context | 1 | No file changed; split DDL, domain, repository, adapter, and fixture updates into exact-context patches. |
| Disposable PostgreSQL could not allocate shared memory inside the filesystem sandbox | 1 | Re-ran only the disposable server lifecycle with approved local-process permissions; no existing database was accessed. |
| First disposable PostgreSQL cluster defaulted to SQL_ASCII and returned TEXT as bytes | 1 | Stopped it and recreated the disposable cluster explicitly with UTF8 before accepting any database test evidence. |
| Sandbox could not connect to the disposable PostgreSQL Unix socket | 1 | Re-ran only the focused pytest process with approved socket access; the UTF8 suite then passed. |
| Full PostgreSQL regression compared `regclass` display text that changes with `search_path` | 1 | Changed the existing migration assertion to verify relation presence/absence booleans instead of presentation formatting. |
| First semantic `regclass` assertion patch introduced excess indentation | 1 | Collection caught it before tests ran; corrected only the affected SQL/assert block and reran compilation/focused tests. |
| One final escalated pytest process failed to launch with a transient `No such file or directory` process error | 1 | Verified the workspace and virtualenv still existed, then retried the identical bounded pytest command successfully. |
| A temporary-directory verification loop used zsh's special `path` variable and hid `rg` for that subprocess | 1 | The shell exited without file changes; reran with the task-specific `candidate_dir` variable. |
| Phase 4 registry inspection requested non-existent `strategy_catalog/registry.py` | 1 | No file changed; the executable allowlist owner is `atomic_strategies/registry.py`, while catalog metadata lives in `strategy_catalog/drafts.py` and the PostgreSQL repository. |
| Phase 4 source search assumed a top-level `momentum/` package | 1 | No file changed; the live Momentum projection and canonical FeatureEngine integration are owned by `dashboard/momentum.py`. |
| Initial Phase 5 inspection requested non-existent `atomic_strategies/contracts.py` and top-level strategy modules | 1 | No file changed; corrected the inspection to `atomic_strategies/protocol.py` and `atomic_strategies/entries/*.py`. |
| Combined G6 documentation patch targeted README twice, which `apply_patch` rejected | 1 | No file changed; split the documentation update so each file is targeted once. |
| Initial Phase 28 ORB golden suite could not import the not-yet-created strategy module | 1 | Expected test-first failure; implement the one-file ORB strategy and shared Feature path, then rerun the same suite. |
| First ORB product run reached the live projection test but its new fixture omitted required store retention | 1 | Production code was not implicated; configure the test stores with the same bounded Tick/bar retention contract as the runtime and rerun. |
| Focused Atomic regression still asserted the pre-ORB four-strategy allowlist | 1 | Update the allowlist regression to require the fifth independent ORB implementation and its concrete class. |
| First full Phase 28 regression found the Web API contract still fixed to four Templates | 1 | Product output correctly exposed ORB; update the API regression to require all five code-owned Templates, then rerun the full suite. |

## Non-goals

- Phase 1 product-code implementation is authorized; later Web/local-paper phases retain their own Gates.
- No new atomic-strategy platform writes, fallback, or runtime authority in SQLite.
- No arbitrary code or import path execution from database values.
- No Shioaji broker order API, CA activation, trade callback, or real-money mode.
- No claim that backtest strategies already have live Tick/BidAsk parity.
- No network-exposed unauthenticated strategy-management mutation API.
- No unbounded per-evaluation database persistence.
