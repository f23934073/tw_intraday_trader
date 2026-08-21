# Task Plan: Atomic Strategy Platform

## Goal

Produce a repository-grounded, implementation-ready plan for a PostgreSQL-only, versioned atomic-strategy platform. Each independently testable condition is one registered strategy implementation; parameters and compositions are configured in the Web UI, validated server-side, persisted as immutable versions in PostgreSQL, and snapshotted by backtest and local-paper runs. This planning slice must not add broker or real-money execution.

## Current Phase

Phase 12 complete — Gate G1 PASSED; Phase 2 not started

## Implementation Gate

Contract Review returned **APPROVE / GO**. B1–B5 are `REVIEWED / CLOSED`, and the user explicitly authorized Phase 1 implementation. Phase 2 Web management and Phase 4 local-paper integration remain outside this slice.

| ID | Blocking contract | Plan status | Review status |
|---|---|---|---|
| B1 | Strategy parameters resolve to parameterized Feature Requests; feature cache/state keys include parameter digest | Accepted | REVIEWED / CLOSED |
| B2 | Shared Feature Specification with explicit Tick/BidAsk, intraday Kbar, and daily Kbar adapters; Section 22 ownership frozen | Accepted | REVIEWED / CLOSED |
| B3 | First Publish needs Draft-scoped idempotency/result mapping; all new persistence must be PostgreSQL-only | Accepted | REVIEWED / CLOSED |
| B4 | Proposed/Approved ordering, monotonic merge, and complete exit bypass matrix | Accepted | REVIEWED / CLOSED |
| B5 | Evaluation persistence uses full/bounded/aggregate/debug retention tiers instead of unbounded rows | Accepted | REVIEWED / CLOSED |

Gate rules:

- Contract Gate G0 is passed; implementation must still satisfy the Phase 1 migration, persistence, determinism, compatibility, and regression gates.
- Closed blockers are not reopened without new contradictory evidence.
- The authorization covers Phase 1 only; it does not authorize Web management, local-paper integration, simulation changes, broker orders, or real-money execution.

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
- **Status:** complete — Gate G1 PASSED; Phase 2 Web management not started

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

## Non-goals

- Phase 1 product-code implementation is authorized; later Web/local-paper phases retain their own Gates.
- No new atomic-strategy platform writes, fallback, or runtime authority in SQLite.
- No arbitrary code or import path execution from database values.
- No Shioaji broker order API, CA activation, trade callback, or real-money mode.
- No claim that backtest strategies already have live Tick/BidAsk parity.
- No network-exposed unauthenticated strategy-management mutation API.
- No unbounded per-evaluation database persistence.
