# Task Plan: Central No-Overnight Risk Controller implementation plan

## Goal
Produce a repository-grounded, implementation-free plan for a central no-overnight state machine that flattens only policy-managed intraday exposure, preserves fill-based evidence, persists breaches across restart, and can later be hosted by an independent watchdog without changing its core contracts.

## Current Phase
Complete

## Phases

### Phase 1: Requirements and decision intake
- [x] Read the supplied B-to-C design decision completely.
- [x] Freeze the managed-position scope and explicit non-goals.
- [x] Record the plan-only boundary.
- **Status:** complete

### Phase 2: Repository architecture mapping
- [x] Trace current order intent, command, risk, journal, fill, position, and recovery paths.
- [x] Identify the smallest ownership/horizon contract and central admission seam.
- [x] Locate persistence, scheduling, API/UI, configuration, and test integration points.
- **Status:** complete

### Phase 3: Contract and state-machine design
- [x] Define states, transitions, commands, events, invariants, and failure semantics.
- [x] Separate strategy exits from operational no-overnight exits.
- [x] Define parameterized session timing without freezing unsupported clock values.
- [x] Define the future watchdog port without adding a second execution pipeline.
- **Status:** complete

### Phase 4: Dependency-ordered implementation plan
- [x] Break work into reviewable slices with exact file areas and migrations.
- [x] Define unit, integration, restart, concurrency, and negative test matrices.
- [x] Define rollout, feature flags, observability, rollback, and acceptance gates.
- **Status:** complete

### Phase 5: Delivery
- [x] Cross-check the plan against current repository wiring and supplied constraints.
- [x] Verify no product implementation was made.
- [x] Deliver a review-ready implementation plan and wait for implementation approval.
- **Status:** complete

### Phase 6: Request Changes contract closure
- [x] Freeze immutable `account_scope_id` and `policy_family_id` across configuration, exposure, transitions, results, breaches, and Journal metadata.
- [x] Make B single-controller deployment a fail-closed ENFORCING startup invariant and remove mutable snapshot digest from semantic action uniqueness.
- [x] Wire authoritative reviewed-calendar session phase and instrument tradability into the last admission check before handler side effects.
- [x] Reconcile the empty-session and fill-derived `CONFIRMED_FLAT` definitions.
- [x] Add `last_execution_fact_journal_sequence` and revision-bound breach acknowledgement contracts.
- [x] Extend the PR slices and negative test matrix, then revalidate plan-only scope.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Implement B now and preserve a B-plus-C hosting seam | The project is not authorized for real-money production execution; independent HA/watchdog infrastructure would be premature. |
| Scope flatness to policy-managed intraday positions | Prevents accidental liquidation of AUTO_SWING and MANUAL_LONG holdings. |
| Never synthesize a fill | Preserves the Market Event to Decision to Order to Fill to Position to PnL evidence chain. |
| Require terminal execution and authoritative position reconciliation | EXIT_SUBMITTED is not evidence that exposure is closed. |
| Persist OVERNIGHT_BREACH and block later entry | Restart must not turn unresolved exposure into a healthy state. |
| Keep transition times configurable and evidence-gated | State-machine contracts can freeze before the exact clock parameters are calibrated. |
| Enforcing mode requires durable PostgreSQL | An in-memory latch cannot survive process or machine restart and therefore cannot support the promised safety claim. |
| Legacy exposures remain unclassified and excluded | Silently inferring an old manual holding as intraday could liquidate an intended long-term position. |
| Use exposure-level fill allocation | Symbol-level ownership cannot safely preserve a long-term and intraday slice of the same stock. |
| Separate strategy kill from no-overnight operation | Stopping entry generation must not stop cancellation, flattening, reconciliation, or breach detection. |
| Treat CONFIRMED_FLAT as an as-of evidence claim | A later or recovered fill can supersede it and open a durable breach; terminal UI status cannot override new facts. |
| Persist immutable account and policy-family identities | Policy rotation or restart must not strand an existing exposure or breach outside the active latch. |
| Fail ENFORCING startup unless a single controller host is proven | B excludes an execution lease, so process-local singleton construction alone is not a sufficient safety boundary. |
| Use stable semantic action keys | Snapshot/input digests remain evidence but must not allow duplicate actions for the same exposure and attempt. |
| Recheck calendar and tradability at the last admission boundary | An action planned during trading hours may execute after the market phase changes. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Existing root planning files belong to an older active workstream | Created an isolated plan under `.planning/2026-08-23-central-no-overnight-risk-controller/`; did not overwrite root planning files. |
| One large contract patch did not match the exact `NoOvernightResult` context | Inspected the current section and split the revision into smaller exact patches; no partial edit was applied. |
| Optional deployment-file shell globs had no match under Zsh | Switched to `rg --files` and explicit paths; the failed lookup was read-only. |
| A double-quoted search pattern contained Markdown backticks | Switched remaining searches to safely quoted, backtick-free patterns; no mutation occurred. |
| The planning completion helper reported 15/17 despite all visible Phase 6 boxes being complete | The helper ignores `PLAN_ID` and defaulted to the repository root plan; rerun it with the isolated `task_plan.md` path explicitly. |
