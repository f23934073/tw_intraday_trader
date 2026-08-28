# Task Plan: Durable Kill Switch implementation plan

## Goal

Produce a repository-grounded, implementation-free plan that a separate Codex task can use to make the Local Paper Kill Switch durable, auditable, restart-safe, and fail-closed without enabling broker or real-money execution.

## Current Phase

Complete

## Phases

### Phase 1: Current-state discovery

- [x] Trace the current Kill Switch lifecycle, API, Dashboard, strategy-loop, Journal, checkpoint, and recovery paths.
- [x] Identify existing persistence contracts and migrations that should be reused.
- [x] Record current gaps, concurrency risks, and authority boundaries.
- **Status:** complete

### Phase 2: Contract and architecture design

- [x] Define durable state, commands, events, idempotency, actor audit, revision, and recovery semantics.
- [x] Define fail-closed behavior for startup, database failure, concurrent operations, and ambiguous results.
- [x] Define API/UI compatibility, migration, and rollback boundaries.
- **Status:** complete

### Phase 3: Implementation-plan authoring

- [x] Write a dependency-ordered implementation plan with exact source areas and PR-sized phases.
- [x] Specify tests, PostgreSQL UAT, acceptance criteria, rollout gates, and non-goals.
- [x] Add a ready-to-paste prompt for opening a separate task.
- **Status:** complete

### Phase 4: Verification and delivery

- [x] Cross-check every current-state claim against source.
- [x] Verify that only planning documentation changed and no trading code was implemented.
- [x] Restore the pre-existing active-plan pointer and deliver the plan path.
- **Status:** complete

## Key Questions

1. Which process currently owns the Kill Switch, and which paths consult it before creating an automated BUY intent?
2. Which existing Journal/checkpoint interfaces can persist the state without creating a parallel persistence pipeline?
3. What exact evidence proves an engage/reset command is durable, authorized, idempotent, and recovered after restart?
4. How should startup behave when durable state is missing, corrupt, stale, or unavailable?
5. Which tests require PostgreSQL rather than an in-memory substitute?

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Scope this plan to durable Kill Switch control only | Tax, fee, and slippage modeling has different ownership and verification and should be a separate task. |
| Keep this turn implementation-free | The user explicitly requested an implementation plan for a new independent task. |
| Preserve LOCAL_PAPER_SIMULATION and no-broker boundaries | Persistence hardening must not add broker-order authority. |
| Reuse the canonical Trading Journal and recovery path | Avoid a second control-state store that could disagree after restart. |
| Use a stable global control Journal session with append-only transitions | Trading-session rotation must not clear the switch, and replay must remain authoritative without a new SQL store. |
| Introduce `RECOVERY_REQUIRED` as a blocking state | Journal/replay ambiguity must not silently appear disengaged. |
| Require exact revision for reset, but allow engage/reaffirm without expected revision | Emergency engage must remain easy and monotonic-safe; clearing a newer incident must be impossible from stale UI state. |
| Add a final automated-intent admission guard | Controller polling alone cannot close engage/submit races. |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| One `apply_patch` tried to delete and re-add the same files in a single patch | 1 | Split deletion and addition into separate `apply_patch` operations. |
| `check-complete.sh` was invoked with `PLAN_ID`, but this version accepts an explicit plan-file argument | 1 | Read the script and rerun it with the isolated `task_plan.md` path. |

## Notes

- The existing main worktree is dirty with unrelated user changes; inspect read-only and edit only isolated planning files plus the final plan document.
- The PR-NO-006 frozen worktree must not be changed before its scheduled trading-session evidence capture.
