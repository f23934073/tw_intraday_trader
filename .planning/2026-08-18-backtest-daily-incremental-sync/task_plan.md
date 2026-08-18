# Task Plan: Backtest Daily Incremental Sync

## Goal
After the Taiwan market closes, automatically fetch only new/recent Shioaji Kbars, checkpoint the delta in the backtest database, and seal a new immutable dataset while preserving every prior dataset and reproducible backtest run.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm that completed historical datasets are immutable snapshots and do not update automatically.
- [x] Trace dataset manifests, repository contracts, server lifespan, and current worker ownership.
- [x] Identify safe incremental merge, scheduling, idempotency, and shutdown contracts.
- [x] Document discoveries in findings.md.
- **Status:** complete

### Phase 2: Incremental-sync design and tests
- [x] Define a framework-free incremental sync application service over Provider, repository, and dataset catalog ports.
- [x] Define a single-owner Asia/Taipei after-close scheduler with durable per-session idempotency.
- [x] Add failing tests for delta-only fetch, overlap deduplication, immutable versioning, no-op sessions, scheduler timing, and restart behavior.
- **Status:** complete

### Phase 3: Incremental dataset implementation
- [x] Add delta job creation/resume and database checkpoint metadata.
- [x] Merge a READY base dataset with per-symbol delta partitions without mutating the base.
- [x] Preserve existing full-download behavior and repository adapters.
- **Status:** complete

### Phase 4: After-close scheduler and runtime wiring
- [x] Add configuration for enabled flag, Asia/Taipei close time, overlap, and polling cadence.
- [x] Wire one scheduler into FastAPI lifespan with clean stop and no browser-triggered Provider calls.
- [x] Expose read-only status needed to verify last attempt/result.
- [x] Update Traditional Chinese dashboard/docs only where necessary for observability.
- **Status:** complete

### Phase 5: Verification and delivery
- [x] Run focused tests, full regression, compile/static checks, and whitespace checks.
- [x] Run a deterministic MockProvider smoke proving first full seed then next-day incremental version.
- [x] Document operating requirements and recovery behavior.
- [x] Deliver exact verification steps to the user.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Default schedule is 14:30 Asia/Taipei on weekdays | It is after regular trading close and avoids UTC/local-time ambiguity. |
| Keep historical datasets immutable | Existing backtest runs must continue to resolve the exact bars and checksum they used. |
| Scheduler calls an application service, not Shioaji or SQL directly | Preserves existing ports/adapters and permits deterministic tests. |
| Overlap at least the latest stored trading date | Re-fetching and timestamp deduplication repair partial/final-minute changes without downloading three years. |
| Never auto-start a second full seed while another download/sync job is active | Prevents duplicate Provider quota usage and races. |
| Use immutable parent-plus-delta dataset layers | Prevents a daily rewrite/copy of the complete three-year dataset. |
| If no READY Provider dataset exists, scheduler reports waiting and does not create a full seed | The current full resumable download remains an explicit bootstrap step. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Session catch-up reported unsynced context from the current long-running task | Captured the current request in this isolated plan and preserved all existing worktree changes. |
| New focused test initially fails to import `IncrementalHistoricalSync` | Expected red phase; implement the new application service and scheduler next. |
| Application integration tests initially fail to import `IncrementalSyncDeferred` | Expected red phase for worker submission and active-job deferral. |
| Deferred scheduler branch passed `error_message` twice through `**base` | Rebuilt the snapshot with one merged mapping and added a regression test. |
| Sandbox denied binding the isolated Uvicorn smoke server to 127.0.0.1:8011 | Re-ran the same bounded local command with approved local-server permission, then shut it down cleanly. |
