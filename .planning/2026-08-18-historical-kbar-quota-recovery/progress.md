# Progress Log

## Session: 2026-08-18

### Current Status
- **Phase:** complete
- **Started:** 2026-08-18

### Actions Taken
- Diagnosed the live database and identified the first empty partition and suspect tail.
- Compared the observed 9.3-million-bar cutoff with official Shioaji traffic and request limits.
- Confirmed current resume logic incorrectly treats empty and later partial partitions as complete.
- Created an isolated implementation plan so existing project planning records remain untouched.
- Audited the CLI, downloader, provider, repository, incremental sync, existing tests, and README entry points.
- Completed the implementation boundary: no migration or deletion; pause on transient empties/quota, provider pacing, and suspect-tail replay.
- Added red-phase regression tests for quota pause, empty-response pause, legacy suspect-tail replay, request pacing, and normalized usage.
- Implemented provider-neutral usage normalization, a 40-calls/10-seconds rolling limiter, a 16 MiB daily-traffic reserve, post-empty usage recheck, durable pause semantics, and legacy suspect-tail replay.
- Added clean CLI pause output with the exact resume command and documented reset/recovery behavior.
- Initially confirmed the zero-only boundary at 1240, then superseded it after detecting earlier systematic one-year truncation.
- Expanded legacy recovery after finding systematic nonzero truncation before 1240; added a focused detector/test for five consecutive symbols sharing the one-year boundary.
- Verified the final live recovery boundary is 00633L: preserve 28 partitions / 1,417,229 bars and revalidate the remaining saved tail.
- Made the computed resume boundary visible in CLI output, then reran the complete verification suite.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Database anomaly profile | Legitimate sparse symbols or clear failure boundary | Continuous zero tail from 1240; 1336 partially populated | Fail reproduced |
| Official behavior comparison | Determine whether provider can return empty on quota | Official docs confirm empty market-data responses on traffic exhaustion | Confirmed |
| Focused baseline | Existing downloader, provider, Kbar, and incremental tests pass before edits | 16 passed | Pass |
| New regression tests before implementation | Tests should fail on missing safety contracts | Collection failed on missing `HistoricalDownloadPaused` and `MarketDataLimitReached` | Expected fail |
| First focused implementation run | New safety tests pass without weakening Provider identity | 22 passed, 1 fixture failure because seed and incremental Provider class names differed | Fixture corrected |
| Focused final regression | Downloader, Shioaji usage/limiter, charts, and incremental sync | 23 passed | Pass |
| Focused regression after truncation recovery | Downloader, usage/limiter, charts, and incremental sync | 24 passed | Pass |
| Static checks | Python compile and whitespace validation | Passed | Pass |
| Live final resume boundary | Preserve validated prefix and replay rate/quota-damaged tail | Preserve 28 symbols / 1,417,229 bars; retry from 00633L | Pass |
| Full regression | Entire repository test suite | 319 passed, 1 skipped | Pass |
| CLI smoke | Help command and temporary-pause exit path imports | Passed | Pass |

### Errors
| Error | Resolution |
|-------|------------|
| `ps` denied by sandbox | Relied on durable job progress and did not attempt to stop user process. |

## Session: 2026-08-19

### Current Status
- **Phase:** complete
- **Started:** 2026-08-19

### Actions Taken
- Captured a real `ShioajiTimeoutError` after 00636 and confirmed an ordinary resume replayed 00633L through 00636.
- Compared the clean paced refetch with the earlier database partitions and invalidated the shared-one-year truncation heuristic.
- Scoped the correction to bounded request retry, exact current-symbol resume state, and preservation of the legitimate nonzero partitions before the first legacy empty checkpoint.
- Added a 60-second Shioaji Kbar timeout, three bounded attempts, 2/5-second backoff, and a normalized temporary-unavailable error.
- Persisted a current-symbol marker before each full-history fetch and a retry-symbol marker on pause/failure/interruption.
- Replaced the shared-one-year detector with exact-symbol retry plus first-legacy-empty-tail repair.
- Updated CLI guidance and README recovery semantics for timeout versus daily traffic exhaustion.
- Verified the active job read-only: ordinary repaired resume starts at 1240; a simulated old-client timeout at 88/2738 retries 00696B exactly.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| New timeout/resume tests before implementation | Missing contracts fail collection | Missing temporary error and retry helper caused 2 collection errors | Expected fail |
| Focused provider/downloader regression | Timeout retry, exact resume, legitimate one-year coverage | 17 passed | Pass |
| Provider + full/incremental download regression | Shared Provider behavior remains compatible | 29 passed | Pass |
| Static checks | Compile and whitespace validation | Passed | Pass |
| Full regression | Entire repository test suite | 326 passed, 1 skipped | Pass |
| Live read-only resume calculation | No replay from 00633L | Resume boundary 1240; simulated old timeout target 00696B | Pass |

### Errors
| Error | Resolution |
|-------|------------|
| `api/v1/data/kbars` timed out after 30 seconds | In progress: add bounded provider retry and durable pause after retry exhaustion. |
| Resume selected 00633L after it had just been saved successfully | In progress: remove the false-positive coverage heuristic and persist the exact interrupted symbol. |
| Read-only live resume check imported `HistoricalInstrument` from `backtest.domain` | Corrected the diagnostic-only import to `backtest.dataset`; production code was unaffected. |
