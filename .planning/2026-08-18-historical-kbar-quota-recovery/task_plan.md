# Task Plan: Historical Kbar quota recovery

## Goal
Make the resumable three-year Shioaji Kbar downloader stop safely before quota/rate failures, never checkpoint transient empty responses as complete, and repair the existing job without discarding valid partitions.

## Current Phase
Complete

## Phases

### Phase 1: Requirements and current-contract audit
- [x] Confirm the zero-Kbar pattern and provider limits.
- [x] Inspect downloader, provider, CLI, repository, tests, and documentation contracts.
- [x] Record the minimum safe change and backward-compatibility constraints.
- **Status:** complete

### Phase 2: Reproduction tests
- [x] Add tests for quota-aware pause and empty-response handling.
- [x] Add a regression test that rewinds an existing job from its first suspect partition.
- [x] Add deterministic rate-limiter tests without real sleeping.
- **Status:** complete

### Phase 3: Surgical implementation
- [x] Expose normalized Shioaji usage information without leaking SDK types.
- [x] Pace Kbar calls below the official request ceiling.
- [x] Pause the durable job before quota exhaustion and on ambiguous empty responses.
- [x] Requeue the existing suspect tail while retaining valid checkpoints.
- **Status:** complete

### Phase 4: CLI and documentation
- [x] Make pause/resume output actionable.
- [x] Document daily-cap behavior, recovery command, and 08:00 reset semantics.
- **Status:** complete

### Phase 5: Verification and delivery
- [x] Run focused downloader/provider tests.
- [x] Run the full regression suite and static checks.
- [x] Inspect the live database read-only to show what the fixed resume will retry.
- **Status:** complete

### Phase 6: Live-run timeout and resume correction
- [x] Capture the real Shioaji 30-second Kbar timeout and repeated-resume behavior.
- [x] Add bounded timeout retry with backoff and a normalized recoverable provider error.
- [x] Persist the exact in-progress symbol so resume retries it without replaying valid partitions.
- [x] Remove the invalid shared-one-year truncation heuristic while retaining legacy empty-tail repair.
- [x] Add regression tests, update recovery documentation, and verify the live resume boundary read-only.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Preserve every non-suspect partition | The database already contains more than nine million bars that should not be downloaded again. |
| Treat provider empties as ambiguous until checked | Shioaji explicitly returns empty values when traffic is exhausted; empty cannot mean successful completion by itself. |
| Rewind from the first transient-empty partition | This also repairs later partial partitions such as 1336, which had no error flag but was downloaded after the first quota failure. |
| Keep quota/rate policy at the provider/downloader boundary | Browser code and strategy code must not know Shioaji SDK details. |
| Use injected clock/sleep in tests | Rate-limit behavior must be deterministic and fast. |
| Treat a shared one-year start as valid provider coverage unless another failure marker exists | A clean paced live refetch reproduced the same coverage, disproving the earlier truncation inference. |
| Persist a retry-symbol marker at recoverable interruption | Existing partitions may predate the current attempt, so job progress alone cannot always identify the symbol that failed. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Sandboxed `ps` was denied during diagnosis | Used durable job timestamps and database progress as process evidence; no process mutation was attempted. |
| Initial query assumed a non-existent `historical_download_jobs` table | Read the schema and used `backtest_jobs` plus `backtest_history_partitions`. |
| New regression tests initially failed during import because the planned pause/limit types did not exist | Expected red phase; implement the narrow provider and downloader contracts next. |
| Incremental quota test used a different Provider subclass than the seed dataset | Kept production identity enforcement intact; changed the fixture to toggle quota exhaustion on one Provider instance. |
| Incremental quota test omitted its new `pytest` import | Added the missing test-only import. |
| Live download raised `ShioajiTimeoutError` after 30 seconds and aborted the whole job | Phase 6 adds bounded per-request retry and converts exhaustion into a durable resumable pause. |
| Resume repeatedly restarted at 00633L after successfully saving it | Remove the invalid shared-one-year detector and use explicit current-symbol retry state instead. |
