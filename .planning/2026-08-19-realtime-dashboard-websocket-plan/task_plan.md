# Task Plan: Realtime Dashboard WebSocket migration

## Goal
Implement and verify a cursor-safe HTTP bootstrap plus WebSocket projection stream for all observed-symbol intraday indicators, with bounded fan-out, reconnect/resync, and HTTP polling fallback.

## Current Phase
Complete

## Phases

### Phase 1: Requirements and current-flow discovery
- [x] Freeze the requested initial HTTP snapshot plus WebSocket delta model.
- [x] Trace current frontend polling, HTTP APIs, Momentum runtime, and lifecycle ownership.
- [x] Record correctness, consistency, reconnect, and backpressure constraints.
- **Status:** complete

### Phase 2: Architecture evaluation
- [x] Compare snapshot-plus-WebSocket options against the current code.
- [x] Define authoritative snapshot, revision/cursor, event envelope, and resync semantics.
- [x] Define connection lifecycle, heartbeat, backpressure, and bounded fan-out behavior.
- **Status:** complete

### Phase 3: Implementation-plan authoring
- [x] Write dependency-ordered backend, frontend, observability, and test phases.
- [x] Map each phase to concrete repository files and API contracts.
- [x] Define rollout, fallback, and rollback gates without implementing product code.
- **Status:** complete

### Phase 4: Plan verification
- [x] Verify first-load consistency and no lost-update race.
- [x] Verify reconnect, stale-tab, slow-client, and process-restart scenarios are covered.
- [x] Confirm the plan preserves market-data-only and no-broker-order boundaries.
- **Status:** complete

### Phase 5: Delivery
- [x] Deliver the evaluation, recommended architecture, staged plan, and acceptance criteria.
- [x] Confirm no product-code implementation was made.
- **Status:** complete

### Phase 6: Implementation baseline and stream contract
- [x] Capture focused/full test baseline without altering existing unrelated changes.
- [x] Add runtime WebSocket/test dependencies and validated stream configuration.
- [x] Add contract tests for revision, replay, coalescing, and cursor gaps.
- **Status:** complete

### Phase 7: Backend atomic projection and WebSocket hub
- [x] Add a service-owned candidate refresh worker plus bounded projection watcher so Provider scans do not stall browser fan-out.
- [x] Add atomic/cached stream snapshots, bounded replay, client lifecycle, and WebSocket route.
- [x] Preserve clean FastAPI shutdown and single-process runtime semantics.
- **Status:** complete

### Phase 8: Browser bootstrap, delta merge, reconnect, and fallback
- [x] Fetch one complete snapshot, then connect with `stream_id + since_revision`.
- [x] Apply ordered projection deltas without browser-side strategy calculations.
- [x] Verify heartbeat, reconnect, generation guards, visibility recovery, and polling fallback.
- **Status:** complete

### Phase 9: Verification, documentation, and delivery
- [x] Run focused hub/API/runtime/UI tests and full regression/static checks.
- [x] Verify bounded replay, lost-update recovery, no normal-path polling, and no broker-order changes.
- [x] Update README and deliver the implemented result without committing unrelated files.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep an HTTP bootstrap snapshot and add WebSocket projection events | HTTP is simple for complete initial state; WebSocket removes repeated full polling during the session. |
| Plan only in this turn | The user asked for evaluation and an implementation plan, not implementation. |
| Use an isolated planning session | The worktree contains concurrent plans and product changes that must remain untouched. |
| Use revision replay rather than a best-effort socket handoff | It closes the HTTP-to-WebSocket lost-update window and gives deterministic gap handling. |
| Start with 500 ms coalescing | It is four times more responsive than current polling while providing safer bandwidth and render load for up to 100 symbols. |
| Implement after explicit user approval | The user replied 「好, 幫我處理」 after reviewing the plan. |
| Use a 500 ms projection watcher plus service-owned candidate worker in v1 | It preserves push-only browser transport without letting full-market scans or socket I/O block Shioaji callbacks and fan-out. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| First implementation-session planning patch used a malformed multi-file patch delimiter | Reissued the updates with valid separate file sections; no product file was affected. |
| First Phase 6-8 progress patch did not match Markdown list prefixes | Re-read the isolated plan and applied the update against the exact current text. |
