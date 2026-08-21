# Task Plan: Shioaji quota status badge

## Goal
Expose Shioaji market-data usage through the dashboard backend and show a clear red badge in the upper-right status area when the daily traffic allowance is exhausted.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm the exhausted-quota state and desired upper-right placement.
- [x] Trace the current status pills, dashboard refresh lifecycle, Provider usage adapter, and test seams.
- [x] Record the smallest truthful API/UI contract.
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Define usage payload, fail-closed threshold, refresh cadence, and Mock behavior.
- [x] Add failing backend and frontend contract tests.
- **Status:** complete

### Phase 3: Implementation
- [x] Add a read-only provider-usage endpoint without market-data polling or broker capabilities.
- [x] Add the upper-right exhausted-quota badge and bounded browser refresh.
- [x] Update user-facing documentation if the operating contract changes.
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Pass focused API/service/static UI tests.
- [x] Run full regression, JavaScript syntax, Python compilation, and whitespace checks.
- [x] Browser-smoke both healthy/unsupported and exhausted states.
- **Status:** complete

### Phase 5: Delivery
- [x] Reconcile plan, findings, and progress with verified behavior.
- [x] Deliver the behavior, validation evidence, and any remaining limitation.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep the badge read-only and independent of strategy/simulation state | Usage visibility must not create any execution authority. |
| Query `api.usage()` through the existing Provider adapter | Reuses normalized usage fields without exposing Shioaji SDK objects to the browser. |
| Do not use Snapshot/Kbar to test the badge | The exhausted state must be visible without consuming more market-data quota. |
| Return provider, supported, exhausted, connections, used, limit, and remaining fields | Gives the browser a complete display contract without SDK types or inference from empty market data. |
| Refresh usage at startup, after manual scan, on visibility return, and every 60 seconds | Keeps the warning current without joining high-frequency quote polling. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial combined patch targeted an outdated `realtime_candidate_snapshot` signature | Re-read the local contexts and applied the same scoped changes against the current dirty worktree. |
