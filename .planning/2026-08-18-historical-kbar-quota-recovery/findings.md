# Findings & Decisions

## Requirements
- Fix the historical Kbar downloader after it persisted a long run of zero-bar symbols.
- Preserve successful checkpoints and make the existing job safely resumable.
- Prevent recurrence through traffic/rate protection and fail-closed empty handling.

## Research Findings
- Job `dataset-download-f914feaddea04e37b3cbdcfce2b0179b` first persisted an empty partition at symbol 1240 on 2026-08-18 16:42:32 +08:00.
- Before that partition the database contained 9,302,612 bars. Seven 64-bit Kbar arrays are approximately 496.8 MiB, closely matching Shioaji's 500 MB minimum daily traffic tier.
- 1301, 1303, 1402, and other actively traded stocks were persisted with zero bars, so this is not legitimate market sparsity.
- Symbol 1336 was persisted with only 390 bars from 2026-08-10 through 2026-08-14 after the first empty partition, proving later non-empty partitions can still be incomplete/suspect.
- Official Shioaji documentation says traffic exhaustion makes `ticks`, `snapshots`, and `kbars` return empty values. Traffic resets at 08:00 on trading days.
- Official request ceiling is 50 market-data calls per 10 seconds. The downloader currently performs back-to-back 30-day Kbar calls with no explicit pacing.
- One three-year symbol is split chronologically into about 37 API calls.
- The current downloader considers every saved partition complete, including `bar_count=0` partitions with `error_message='資料來源未回傳 Kbar'`.
- Therefore an ordinary resume skips all existing zero partitions, and it also skips partial 1336 because that partition has no error message.
- The current Shioaji SDK is 1.7.2 and exposes `api.usage()` according to official docs.
- The standalone CLI already closes the Provider and preserves a job ID on `KeyboardInterrupt`, but it only has an explicit user-interrupt path; a recoverable quota pause currently falls through to `FAILED`.
- The after-close incremental sync shares the same Provider Kbar method, so provider-level pacing protects both full backfills and daily updates.
- Incremental zero bars can be legitimate on holidays or for unchanged symbols. Empty-response handling therefore cannot globally reject every empty result; it must combine usage state with full-download suspect-tail semantics.
- The repository already atomically upserts one symbol partition, so suspect partitions can be repaired in place without a delete operation or schema migration.
- The current CLI documentation warns against concurrent web and CLI downloads but does not mention the daily byte cap, `api.usage()`, automatic pause, or suspect-tail replay.
- The user stopped the old process successfully: the durable job is `PAUSED` at 542/2738 with no job-level error.
- The initial zero-only check would have preserved 408 symbols and restarted at 1240, but the later coverage check superseded that boundary.
- A later coverage check found an earlier, different legacy failure signature: starting at 00633L, many unrelated established symbols share the exact 2025-08-18 start date although the request began on 2023-08-19. This is consistent with the old unpaced client continuing through a temporary request suspension and only recovering for the final year.
- The recovery boundary must therefore be earlier than the first zero. Detecting five consecutive partitions near the same one-year boundary after at least five full-coverage partitions distinguishes this systemic truncation from clusters of genuinely new listings.
- Running the implemented detector against the live job selects 00633L at zero-based index 28. It preserves 28 partitions containing 1,417,229 bars and revalidates all later saved partitions in place.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add a small provider usage value object | Keeps SDK-specific response shapes out of backtest code. |
| Reserve a configurable safety margin before the daily byte cap | A single 30-day Kbar response can consume meaningful traffic; exact payload size is not known in advance. |
| Pause rather than fail a durable job on quota/rate/ambiguous empty | The condition is recoverable after reset and existing checkpoints remain valid. |
| Reprocess all partitions at and after the first transient-empty checkpoint | Later partitions may be partially populated even when their own error field is empty. |
| Also detect the legacy shared one-year truncation boundary | Nonzero bar counts alone did not prove three-year coverage; several old products were checkpointed with exactly one year after request-rate suspension. |
| Do not delete database rows during repair | Upsert can atomically replace suspect rows after successful refetch. |
| Exit the CLI with temporary-failure code 75 on an automatic pause | The process closes its Shioaji connection cleanly and can be resumed after the documented 08:00 reset without a traceback. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Exact account usage was not queried during diagnosis | Avoided opening another Shioaji session while the old downloader was still running; use the observed cutoff plus official behavior, and add usage checks to the fixed process. |

## Resources
- https://sinotrade.github.io/zh/tutor/limit/
- https://sinotrade.github.io/zh/tutor/market_data/historical/
- `backtest/historical_download.py`
- `backtest/dataset.py`
- `market_data/provider.py`
- `tests/test_backtest_history_download.py`
