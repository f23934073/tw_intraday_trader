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
- An earlier coverage hypothesis treated the shared 2025-08-18 start date at 00633L as legacy truncation. A clean, paced live refetch reproduced the same approximate one-year coverage and nonzero counts for 00633L through 00636, so start-date coincidence alone is not evidence of corruption.
- The shared-one-year detector is therefore a false positive and causes every resume to replay already successful symbols from 00633L.
- The live run also exposed a separate recoverable failure: `ShioajiTimeoutError` from `api/v1/data/kbars` after 30 seconds currently aborts the entire job instead of retrying the individual request.
- A reliable resume needs two independent signals: the first known legacy empty partition for repairing the old quota-damaged tail, and an explicit current-symbol marker for retrying an interrupted request without replaying unrelated valid partitions.
- Local SDK inspection confirmed Shioaji 1.7.2 exposes `kbars(..., timeout=30000, ...)` and `shioaji.ShioajiTimeoutError`; the corrected Provider uses 60,000 ms plus three bounded attempts.
- The active old process continued normally after the pasted timeout and reached 88/2738 during verification. It remains an old in-memory process, so the new retry behavior takes effect on its next restart.
- A read-only live resume calculation now preserves 408 existing partitions and selects the first legacy empty symbol 1240, not 00633L.
- Simulating an old-client timeout at the same 88/2738 checkpoint selects 00696B as the exact retry symbol, preserves 407 valid checkpoints, and then continues legacy-tail repair at 1240.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add a small provider usage value object | Keeps SDK-specific response shapes out of backtest code. |
| Reserve a configurable safety margin before the daily byte cap | A single 30-day Kbar response can consume meaningful traffic; exact payload size is not known in advance. |
| Pause rather than fail a durable job on quota/rate/ambiguous empty | The condition is recoverable after reset and existing checkpoints remain valid. |
| Reprocess all partitions at and after the first transient-empty checkpoint | Later partitions may be partially populated even when their own error field is empty. |
| Do not infer corruption from a shared one-year start date | The paced live refetch reproduced the same upstream coverage, invalidating the earlier inference. |
| Do not delete database rows during repair | Upsert can atomically replace suspect rows after successful refetch. |
| Exit the CLI with temporary-failure code 75 on an automatic pause | The process closes its Shioaji connection cleanly and can be resumed after the documented 08:00 reset without a traceback. |
| Retry timeout failures per Kbar request, then pause at the exact symbol | This absorbs transient 30-second failures and keeps restart behavior deterministic when retries are exhausted. |
| Use 60-second requests with three attempts and 2/5-second backoff | This is bounded, remains under the shared rolling request limiter, and avoids turning one transient SDK timeout into a failed full-market job. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Exact account usage was not queried during diagnosis | Avoided opening another Shioaji session while the old downloader was still running; use the observed cutoff plus official behavior, and add usage checks to the fixed process. |
| The original truncation detector was based on correlation rather than a provider contract | Live re-download falsified it; Phase 6 removes it and adds regression coverage for legitimate one-year availability. |

## Resources
- https://sinotrade.github.io/zh/tutor/limit/
- https://sinotrade.github.io/zh/tutor/market_data/historical/
- `backtest/historical_download.py`
- `backtest/dataset.py`
- `market_data/provider.py`
- `tests/test_backtest_history_download.py`
