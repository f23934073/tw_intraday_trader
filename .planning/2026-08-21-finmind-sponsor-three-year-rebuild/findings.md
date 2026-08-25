# Findings & Decisions

## Requirements

- Start using today's FinMindTrade Sponsor allowance now, but proceed gradually.
- Rebuild three years of historical data after the prior database was deleted and cannot be recovered.
- Preserve resumability and avoid duplicate API usage.
- Keep acquisition separate from formal validation/OOS outcome generation.
- Continue acquiring three-year data for additional large-cap stocks, with representation across as many industries as practical.
- Base the large-cap and industry choices on current source data and use today's remaining allowance conservatively.

## Confirmed Context

- Referenced task: `確認回測與三年資料` (`01a022e1-fa1c-7833-b070-cdd217911239`).
- The previous Shioaji PostgreSQL dataset was deleted and is not recoverable.
- The previously frozen request covered the current-contract universe of 2,738 instruments from 2023-08-19 through 2026-08-18.
- FinMind Sponsor was previously credential-probed at 6,000 requests per hour.
- Sponsor minute bars use one symbol-day per request; full-market day Parquet is a Sponsor Pro path.
- Existing probes found valid one-minute bars for 2330 and 2317, while some symbols returned empty data.
- The referenced task is concurrently optimizing large-backtest memory use; this acquisition work must not overwrite its files.

## Data Quality Contract

- Intended grain: one canonical row per `(provider, symbol, timestamp)`.
- Required checks: timezone-aware timestamps, deterministic order, unique symbol-timestamps, finite positive OHLC, `low <= open/close <= high`, integral non-negative volume, regular-session bounds, and source/date provenance.
- Empty responses are observations, not successful data partitions.
- Recent or partial dates require explicit labeling; no automatic repair or fabricated bars.

## Open Questions To Resolve From Repository Evidence

- Whether the existing FinMind probe client is production-safe for paced multi-day acquisition.
- Whether the current durable repository is PostgreSQL-only or supports a local immutable fallback after database deletion.
- Whether an authoritative current-contract universe snapshot still exists outside the deleted database.
- Whether the FinMind token/credential is present in the current process environment.
- Whether FinMind exposes remaining allowance directly or only a fixed entitlement limit plus HTTP rate-limit responses.

## Phase 1 Repository Evidence

- `.env` contains a non-empty `FINMIND_API_TOKEN`; the value was not printed.
- The repository has a secret-safe immutable FinMind probe script and offline semantic reconciliation, but no general FinMind historical downloader/provider.
- The existing CLI only accepts `mock` or `shioaji` and creates database-backed durable jobs.
- Backtest configuration defaults to PostgreSQL but supports a SQLite backend; after the old PostgreSQL loss, a new local SQLite repository is a viable durable destination if migrations and job-partition persistence are confirmed.
- `HistoricalDatasetCatalog` stores immutable canonical JSONL manifests under `data/backtest`; it can remain the finalized dataset layer while database job partitions provide resumable staging.
- Existing source qualification artifacts confirm Sponsor KBar success for some controls and provider-empty observations for others, so the new path must not treat HTTP 200 as data success.
- The current worktree has broad concurrent modifications, including the historical downloader and dataset streaming path. New code should be additive where possible and must preserve those changes.
- The existing repository schema keys history partitions by `(job_id, symbol)`, explicitly meaning one complete symbol; it cannot represent Sponsor symbol-day checkpoints without a new/additive store.
- A sealed FinMind 2330 sample contains 266 rows from `09:00` through `13:30`, with `date`, `minute`, `stock_id`, OHLC, and integral `volume`; response envelope is `status=200`, `msg=success`.
- Existing canonicalization can construct `HistoricalBar` from provider `KBar`, but adding a general FinMind `MarketDataProvider` would still force the unsuitable whole-symbol checkpoint behavior.
- The backtest runtime intentionally fails closed on missing PostgreSQL; SQLite is only explicit local-dev/test. The rebuild therefore needs a clearly scoped acquisition store and must not silently claim to replace the authoritative backtest database.
- FinMind's official usage endpoint returns both current `user_count` and `api_request_limit`; the live runner can reserve capacity based on the actual account state instead of assuming 6,000 calls remain.
- Official API documentation confirms `TaiwanStockPrice` accepts a date range. One three-year daily query for a liquid calendar symbol can discover trading dates and avoid wasting KBar calls on weekends and market holidays.
- Existing sealed reconciliation proves FinMind KBar labels are interval starts except `13:30`; canonical event timestamps must add one minute except for the close label to avoid look-ahead and match Shioaji end labels.
- Sealed reconciliation also proves FinMind raw KBar volume is in common lots, not shares; the acquisition metadata must retain that unit explicitly.

## Implementation Success Criteria

- Every external KBar request commits an immutable `(job_id, symbol, session_date)` checkpoint before the next request.
- Re-running the same job never calls FinMind for `READY` or observed `EMPTY` symbol-days.
- Current FinMind usage is checked first; `max_requests` and a reserve margin jointly cap the batch.
- HTTP/payload quota exhaustion stops cleanly without corrupting the last checkpoint.
- Raw response bytes are gzip-persisted with SHA-256; normalized canonical rows are deterministically re-derived and digest-verified.
- Invalid OHLC, duplicate/non-monotonic minutes, wrong symbol/date, negative/non-integral volume, or out-of-session rows block the partition.

## Live Preflight Evidence

- Official usage endpoint returned `user_count=0`, `api_request_limit=6000`, so 6,000 requests were available before acquisition.
- Exactly one data request was spent to query `TaiwanStockPrice` for calendar symbol 2330 across the frozen range.
- The immutable calendar contains 727 trading dates from the requested `2023-08-19` through `2026-08-18` range.
- The first actionable checkpoint is `2317 / 2023-08-21`; the two-symbol pilot contains 1,454 expected symbol-days.
- After calendar sealing, the store recorded exactly one request and zero KBar partitions.

## First Completed Symbol

- 2317 now has all 727 requested trading-date observations checkpointed: 726 `READY` and one observed `EMPTY`.
- The empty observation is `2025-07-30`; this matches the publicly reported TWSE-approved 2317 trading halt for pending material information, so it is an expected no-trade session rather than a failed FinMind response.
- The 726 non-empty partitions contain 193,083 canonical bars, with 261-266 bars per session and a mean of 265.95.
- Full offline audit re-read and digest-verified all 727 raw partitions with zero integrity or normalization issues.
- Local acquisition database size after the first complete symbol is approximately 3.1 MB.

## Delayed Closing Auction Finding

- 2330/2025-03-24 returned 266 rows but no 13:25-13:30 trades; its final row was `13:33`, OHLC 972, volume 3,636 common lots.
- TWSE's closing-stabilization rule permits an affected security's close to be delayed to 13:33 when the final simulated price moves beyond the threshold.
- Contemporary market reporting confirms 2330 closed at 972 with a 3,636-lot closing sell print that day.
- This is a legitimate regular-session closing auction, not an after-hours fixed-price row. The canonical event time remains 13:33 without a one-minute shift.
- The contract remains fail-closed for any other post-13:30 label.

## Final Verified State

- Job `finmind-sponsor-93e761a34d3f3511` is `COMPLETED` with 1,454/1,454 symbol-day checkpoints across 727 trading dates.
- 2317: 726 `READY`, one expected `EMPTY`, 193,083 canonical bars.
- 2330: 727 `READY`, 193,330 canonical bars.
- Combined: 1,453 `READY`, one expected `EMPTY`, zero invalid/error partitions, 386,413 canonical bars.
- Full offline audit verified all 1,454 raw SHA-256 and canonical digests with zero issues.
- Exact FinMind usage after completion was 1,455/6,000, leaving 4,545 requests in the current allowance window.
- Local SQLite acquisition database size is approximately 6.1 MB and remains git-ignored.
- Full repository verification passed: 1,061 tests passed and 4 were skipped; focused Ruff and whitespace checks passed.
- No formal validation/OOS backtest was started and no broker/order path was touched.

## Diversified Extension Questions

- Confirm the latest usable `TaiwanStockMarketValue` observation and `TaiwanStockInfo` industry field from official FinMind data.
- Decide whether one representative per detailed industry is too sparse or too broad for today's remaining 4,545-request snapshot.
- Calculate the number of complete 727-session symbols that fit after current metadata requests and the 500-request safety reserve.

## Diversified Universe Evidence

- Official FinMind semantics were verified for `TaiwanStockInfo` and the exact-date all-market form of `TaiwanStockMarketValue`.
- Raw metadata was sealed by SHA-256; the latest usable market-value date is 2026-08-20.
- FinMind current stock info contains 603 symbols with simultaneous aggregate and detailed category rows. Aggregate `電子工業`, `化學生技醫療`, and `創新板股票` labels are removed when one detailed industry exists.
- Null-date/incomplete rows, truly ambiguous current identities, non-company categories, non-four-digit symbols, and non-positive market values are excluded.
- The resulting reproducible universe has 40 detailed-industry leaders.
- Completed 2330 represents `半導體業`; completed 2317 represents `其他電子業`.
- Live usage after eight metadata data requests was 1,463/6,000, leaving 4,537.
- With a 500-request reserve, one new calendar call, and 727 symbol-days per stock, five complete symbols fit today's tranche.
- The five highest-market-value missing-industry leaders are 2308 台達電 (`電子零組件業`), 2881 富邦金 (`金融保險`), 1303 南亞 (`塑膠工業`), 2382 廣達 (`電腦及週邊設備業`), and 2345 智邦 (`通信網路業`).
- The 6,000-request account limit is hourly rather than daily. At one request per second the downloader issues at most about 3,600 data calls per hour, so the other 33 missing industries can continue after the first tranche instead of being deferred as a presumed daily quota gap.

## Continuous Acquisition Evidence

- The first diversified job (`finmind-sponsor-c9df8c4315d30ad6`) completed all 3,635 symbol-days for 1303, 2308, 2345, 2382, and 2881; all partitions are `READY`.
- The remaining 33-industry job is `finmind-sponsor-1799dae77ae93c97` with 23,991 expected symbol-days and remains checkpoint-resumable.
- The usage endpoint can report stale availability and takes several seconds per response. Rechecking it after every small rolling release materially underuses the account allowance.
- Continuous mode now performs one initial usage check, then directly probes the data endpoint when `reserve_requests=0`; HTTP/payload 402 remains expected quota control flow and is not recorded as a provider/data failure.
- 1240 returned empty KBar responses on 2024-10-01, 2024-10-29, and 2025-01-07. Official TPEx daily closing data independently reports zero shares, zero value, and zero trades on all three dates.
- 5904 returned empty KBar responses on 2026-07-30, 2026-08-04, and 2026-08-07. Official TPEx notice `11500046541` confirms trading was suspended from 2026-07-30 through 2026-08-07 for a par-value change and share exchange.
- Full partition counts show all seven 5904 trading dates in the suspension interval are `EMPTY`, not only the three dates surfaced by periodic console reporting.
- 7610's sealed 2023-08-22 response contains a 13:31 trade. Official venue history confirms 7610 was an Emerging Stock Board company then and did not list on TWSE until 2025-09-09, so this is a mixed-session history rather than a normal-market anomaly.
- 8422 replaces 7610 for `綠能環保`: its 2026-08-20 FinMind market value is 36,836,803,986, the highest among same-industry companies with full normal TWSE/TPEx history. The override is sealed separately without changing the original current-market ranking artifact.
- Official evidence accounts for all currently observed empty partitions: corporate-information halts, par-value share exchanges, or independently reported zero-trade days.
- FinMind officially documents that repeated 4xx requests trigger a 30-minute IP ban. A too-aggressive direct-probe experiment triggered 403 at 2026-08-21 22:39:32+08:00; the downloader stopped without data corruption.
- Quota waiting now uses the oldest successful locally recorded request inside the one-hour window plus a 0.75-second safety margin. This avoids repeated quota probes while still waking at the next expected release.

## Completed Cross-Industry Cohort

- The formal cohort now contains 40 industries and 40 normal-market symbols, with 7610 excluded and same-industry replacement 8422 included.
- Coverage is 29,080 symbol-days: 29,042 `READY`, 38 source-observed `EMPTY`, zero cohort `INVALID`, and 5,433,683 canonical bars.
- Every `EMPTY` group is reconciled to an official TWSE/TPEx halt, par-value/share-exchange suspension, or official zero-trade daily row.
- The original 7610 raw evidence remains outside the cohort: one five-bar Emerging Stock Board partition and one invalid 13:31 partition.

## Additional Mega-Cap Tranche

- Complete three-year histories were added for 2454, 3711, 2303, 2882, 2412, and 2383.
- 3037 is checkpointed through 2024-12-12; the next request is 3037/2024-12-13 and 406 symbol-days remain in that two-symbol job.
- The additional tranche contains 4,683 `READY` partitions, zero `EMPTY`/`INVALID`, and 1,213,884 canonical bars.
- Combined formal-plus-additional usable data is 33,763 partitions, including 33,725 `READY`, 38 expected `EMPTY`, and 6,647,567 bars.
- The last live batch started from FinMind usage 4,951/6,000 and spent exactly the remaining 1,049 requests, with no failed retry.

## Five-Minute Disposition Sessions

- Eight symbols have full-session 54-row grids at five-minute intervals: 1303, 1717, 1802, 2303, 2383, 2454, 3008, and 6446.
- These are legitimate disposition/security-control periods, not missing one-minute rows. TWSE rules allow about five-minute matching, and sampled exact periods align, including 2454 from 2026-05-07 through 2026-05-20 and 2303 from 2026-07-02 through 2026-07-16.
- An exploratory quarantine was fully reversed from sealed raw bytes without new provider requests; final audits verify the restored canonical digests.

## Final Verification

- All formal jobs and the additional mega-cap jobs passed offline raw/canonical digest audits. The only audit issue in the original source jobs is excluded 7610/2023-08-22.
- FinMind focused tests pass (`11 passed`), Ruff passes, and `git diff --check` passes.
- The repository-wide suite after midnight reports `1,110 passed, 15 skipped, 2 failed`; both failures are unrelated current-date/dynamic-MockProvider assertions and were left untouched.

## 2026-08-22 Continuation

- The user explicitly requested another continuation after the 4,951/6,000 plus 1,049-request batch was completed.
- Resume priority remains the deterministic 3037 checkpoint at 2024-12-13; no completed symbol-day should be requested again.
- After 3037 completes, the next stocks must be selected from the sealed 2026-08-20 market-value snapshot while excluding the formal 40-stock cohort and the already completed additional mega-caps.
- The next established common-stock candidates by sealed market value are 2408, 2059, 2891, 6669, 3017, 2327, and 2360. ETF 0050 is excluded.
- Although 7769 ranks between 3017 and 2327, TWSE confirms it only began listed trading on 2025-11-27; it is excluded from the three-year large-cap tranche because most requested dates predate listing.
- TWSE confirms 6669 listed in 2019 and 2059 in 2008, so both are eligible for the full frozen three-year range.
- The resumed 2383/3037 job is now complete at 1,454/1,454 `READY` partitions and 364,145 bars; offline audit reports zero issues.
- The seven-symbol job checkpointed 1,551/5,089 symbol-days before network execution became unavailable: 2059 is complete, 2327 is complete, and 2360 has 97 days through 2024-01-08.
- Partial-job audit verified all 1,551 partitions and 310,395 bars with zero digest/normalization issues.
- 2327 has seven consecutive `EMPTY` sessions from 2025-08-14 through 2025-08-22; the consecutive block and current `國巨*` name require official share-exchange/par-value suspension reconciliation before treating them as expected.
- The seven 2327 `EMPTY` sessions are expected: official TAIFEX contract-adjustment evidence cites the TWSE par-value replacement, confirms suspension from 2025-08-14 through 2025-08-22, and resumption on 2025-08-25.
- The retried seven-symbol job completed all 5,089 partitions: 5,082 `READY`, seven expected 2327 `EMPTY`, 1,172,650 bars, and zero offline-audit issues.
- Complete three-year histories were added for 2059, 2327, 2360, 2408, 2891, 3017, and 6669.
- A second cross-industry large-cap job completed 2357, 2887, and 3045 at 2,181/2,181 partitions: 2,180 `READY`, one expected `EMPTY`, 550,521 bars, and zero audit issues.
- The sole 2887 `EMPTY` is 2024-08-22. TWSE evidence confirms the stock was suspended that day for pending material information and resumed on 2024-08-23.
- The final 280 requests in the allowance window sealed a calendar and checkpointed 279 `READY` days for 1301 through 2024-10-14; the deterministic next checkpoint is 1301/2024-10-15 with 448 days remaining.
- The partial 1301 job passed offline audit across all 279 partitions and 71,851 bars with zero issues.
- Excluding the intentionally rejected 7610 Emerging Stock Board history, the database now has 57 complete three-year symbols plus partial 1301: 41,718 distinct symbol-days, 41,672 `READY`, 46 expected `EMPTY`, and 8,542,137 canonical bars.
- The successful retry window used exactly 6,000/6,000 requests: 3,538 requests completed the seven-symbol job, 2,182 completed the three-symbol job, and 280 started 1301.

## 2026-08-22 10:32 Scheduled Continuation

- The allowance preflight showed a fresh 0/6,000 window and the first request resumed exactly at 1301/2024-10-15.
- The first process added four `READY` checkpoints through 2024-10-18, then stopped cleanly on an HTTPS read timeout. Offline audit verified all 283 accumulated 1301 partitions with zero issues.
- One bounded resume began at the audited 1301/2024-10-21 checkpoint, added 16 more `READY` days through 2024-11-12, and encountered the same transport timeout.
- Repeated retries were stopped according to the scheduled safety boundary. Local accounting confirms 20 successful requests in this run; no quota-error probe was made.
- The partial 1301 job now contains 299/727 `READY`, zero `EMPTY`/`INVALID`, 77,107 bars, and zero audit issues. The exact next checkpoint is 1301/2024-11-13 with 428 symbol-days remaining.
- Aggregate usable coverage is 57 complete symbols plus partial 1301: 41,738 distinct symbol-days, 41,692 `READY`, 46 expected `EMPTY`, and 8,547,393 canonical bars.
- No additional stock job was started because provider transport failed twice before 1301 could complete.

## 2026-08-22 Manual Continuation

- The user explicitly authorized one more bounded attempt after the two transport timeouts.
- The existing 1301 job resumed exactly from `2024-11-13`, added the remaining 428 `READY` partitions, and completed at 727/727 without re-requesting the first 299 checkpoints.
- Offline audit verified all 727 raw and canonical digests, 189,882 bars, and zero issues for 1301.
- FinMind preflight reported 20/6,000 used before this attempt; the completed retry spent 428 successful data requests, leaving approximately 5,552 calls in the active window.
- From the sealed 2026-08-20 market-value and 2026-08-21 stock-info responses, the next established non-ETF tranche is 1326 台化 (`塑膠工業`), 2301 光寶科 (`電腦及週邊設備業`), 2344 華邦電 (`半導體業`), 2615 萬海 (`航運業`), 2885 元大金 (`金融保險`), 3481 群創 (`光電業`), 3653 健策 (`電子零組件業`), and 4904 遠傳 (`通信網路業`).
- All eight are absent from the 58 complete symbols, and their detailed industries are distinct within this new tranche. The lexicographic job order should complete the first seven and checkpoint roughly 462 of 727 days for 4904 after one calendar request, subject to the provider's authoritative allowance state.
- New job `finmind-sponsor-472eca821ebe93e4` sealed one calendar and added 2,420 `READY` partitions before another HTTPS transport timeout: 1326, 2301, and 2344 are complete; 2615 has 239 days through 2024-08-13; exact next pending is `2615 / 2024-08-14`.
- The job audit re-read and digest-verified all 2,420 partitions and 617,222 bars with zero issues; the job contains no `EMPTY` or `INVALID` partition.
- TWSE official disposition data explains every sub-100-bar block: 2615 used approximately five-minute matching from 2024-05-16 through 2024-05-31; 2344 used approximately five-minute matching from 2025-10-21 through 2025-11-04, approximately twenty-minute matching from 2025-11-04 through 2025-11-17, and approximately five-minute matching from 2026-01-09 through 2026-01-26.
- This manual continuation completed 2,849 successful provider requests: 428 KBar requests finished 1301, then one calendar and 2,420 KBar requests advanced the new job. One additional KBar attempt ended in transport timeout and may not count toward provider quota.
- Across the active window beginning at 10:32, local evidence records 2,869 successful requests including the earlier scheduled 20, plus three transport-failed attempts; no quota-error probe was used.
- Excluding the intentionally rejected 7610 history, aggregate usable coverage is now 61 complete symbols plus partial 2615: 44,586 partitions, 44,540 `READY`, 46 expected `EMPTY`, zero `INVALID`, and 9,277,390 bars.

## User-Directed Transport Backoff

- The user explicitly replaced the previous stop-after-timeout boundary: every transport timeout should now retain the exact SQLite checkpoint, wait a full 60 seconds, and retry the same job without ending the run.
- Read-only verification before the new run confirms job `finmind-sponsor-472eca821ebe93e4` remains `PAUSED` at 2,420 `READY` partitions: 1326, 2301, and 2344 are complete; 2615 has 239 days and 58,379 bars through 2024-08-13; exact next pending is `2615 / 2024-08-14`.
- This retry policy applies only to transport timeouts. Auth, quota, and data-quality results remain explicit stop/handling conditions so they are not hidden by a generic retry loop.
- The first backoff-policy resume ran without any transport timeout and spent its exact 3,150-request preflight budget, advancing the job from 2,420 to 5,570 checkpoints.
- 2615, 2885, 3481, and 3653 are now complete; 4904 has 481 `READY` days through 2025-08-12 and exact next pending `4904 / 2025-08-13`, with 246 symbol-days remaining.
- Full offline audit verified all 5,570 raw/canonical partitions and 1,373,267 bars with zero issues. Statuses are 5,558 `READY`, 12 `EMPTY`, and zero `INVALID`.
- All 12 `EMPTY` partitions belong to 3481: 2023-08-21 through 2023-08-25 and 2024-08-15 through 2024-08-23. TWSE's official capital-reduction report records 3481 resuming on 2023-08-28 and 2024-08-26 after cash-return capital reductions, which exactly accounts for both no-trade blocks.
- TWSE official disposition data also reconciles the new sparse fixed-grid sessions: 3481 used approximately five-minute matching on 2026-01-07 through 2026-01-20 and 2026-06-04 through 2026-06-17; 3653 used approximately five-minute matching on 2026-04-24 through 2026-05-08 and approximately twenty-minute matching on 2026-05-13 through 2026-05-26.
- The isolated 3653 sessions on 2025-04-07 and 2025-04-08 have 13 and 47 actual-trade minutes rather than a fixed full-session grid; they remain valid source observations and pass the canonical audit.
- A second resume used 246 newly released requests to finish 4904; the eight-symbol job is now `COMPLETED` at 5,816/5,816 partitions, 5,804 `READY`, 12 expected 3481 `EMPTY`, zero `INVALID`, and 1,435,275 bars. Full audit reports zero issues.
- The persistent continuation itself made exactly 3,396 successful KBar requests: 3,384 `READY` and 12 `EMPTY`, with no transport timeout and therefore no backoff cycle needed.
- Aggregate usable coverage excluding 7610 is now 66 complete symbols, zero partial symbols, 47,982 partitions, 47,924 `READY`, 58 expected `EMPTY`, zero `INVALID`, and 10,095,443 bars.
- The next sealed high-market-value distinct-industry pair is 3443 創意 (`半導體業`, market value 754,487,058,930) and 8046 南電 (`電子零組件業`, market value 772,167,756,965). Both are established listed common stocks and absent from the 66 complete symbols.
- Job `finmind-sponsor-8346b1f064174364` completed 3443 and 8046 at 1,454/1,454 `READY`, zero `EMPTY`/`INVALID`, 317,560 bars, and zero audit issues after using 1,455 provider requests including its calendar.
- TWSE official disposition data explains 3443's approximately five-minute grid from 2026-04-17 through 2026-04-30 and 8046's approximately five-minute grid beginning 2026-01-22 plus approximately twenty-minute grids from 2026-01-27 through 2026-02-09 and 2026-03-02 through 2026-03-13.
- The next sealed pair is 2886 兆豐金 (`金融保險`, market value 688,268,752,285) and 3231 緯創 (`電腦及週邊設備業`, market value 572,409,405,000), both established listed common stocks absent from the completed set.

## 2026-08-22 Rolling-Quota Extension

- Job `finmind-sponsor-6b42daa60752cc9d` completed 2886 and 3231 at 1,454/1,454 `READY`, 384,854 bars, and zero audit issues. It recorded 1,455 successful provider requests including one calendar.
- The continuation used every released request at durable symbol-day boundaries. When the rolling account allowance reached zero, continuous mode waited from the local successful-request ledger and resumed without a quota-error probe.
- Job `finmind-sponsor-46a7e63c76035213` completed 2884 and 5274 at 1,453 `READY`, one expected `EMPTY`, zero `INVALID`, 274,643 bars, and zero audit issues. The sole `EMPTY`, 2884/2025-11-05, exactly matches TWSE's material-information suspension; TWSE resumed the stock on 2025-11-06.
- Job `finmind-sponsor-0387052ff9cbcc7c` completed 2368 and 2395 at 1,454/1,454 `READY`, 318,461 bars, and zero audit issues.
- Job `finmind-sponsor-e6dfb9398b90b845` completed 2890 and 6223 at 1,454/1,454 `READY`, 345,633 bars, and zero audit issues. The 11-bar 6223 observation on 2025-04-07 is an actual sparse trading day and remains source-faithful.
- Job `finmind-sponsor-04661de00af43551` completed 1519, 2618, and 3665 at 2,180 `READY`, one expected `EMPTY`, zero `INVALID`, 517,182 bars, and zero audit issues.
- TWSE official data reconciles 1519's five-minute disposition blocks on 2024-02-26 through 2024-03-11, 2024-06-19 through 2024-07-04, and 2025-11-06 through 2025-11-19, plus its twenty-minute block on 2024-03-19 through 2024-04-03.
- TWSE official data reconciles 3665's five-minute disposition block on 2026-05-20 through 2026-06-02. Its sole `EMPTY` on 2026-06-10 matches an official material-information suspension, with trading resumed on 2026-06-11.
- The five jobs recorded exactly 8,002 successful provider requests: 7,997 KBar symbol-days and five calendars. No provider timeout, auth failure, invalid partition, or quota-error probe occurred; therefore the user's 60-second transport-timeout backoff was not triggered.
- Aggregate usable coverage excluding rejected 7610 is now 79 complete symbols and zero partial symbols: 57,433 distinct symbol-days, 57,373 `READY`, 60 expected `EMPTY`, zero `INVALID`, and 12,253,776 canonical bars.
- Job `finmind-sponsor-8432c448660fd2a9` completed 2880 and 4958 at 1,454/1,454 `READY`, 361,050 bars, and zero audit issues. TWSE official disposition data explains 4958's five-minute matching from 2026-05-28 through 2026-06-10.
- Job `finmind-sponsor-3599d9b896eafe5b` completed 2883 and 6488 at 1,454/1,454 `READY`, 343,061 bars, and zero audit issues.
- TPEX/TAIFEX official evidence reconciles 6488's five-minute blocks on 2025-09-23 through 2025-10-08, 2025-11-12 through 2025-11-25, and 2026-05-12 through 2026-05-25, plus its twenty-minute blocks beginning 2026-06-01 and 2026-06-22. The isolated 43-bar observation on 2025-04-10 remains a valid sparse real-trade day.
- A final one-shot job `finmind-sponsor-66b204f6b4e79082` spent the exact 546-request preflight budget: one calendar and 545 `READY` 2892 partitions through 2025-11-14. Offline audit verified 141,652 bars and zero issues.
- The deterministic next pending is `2892 / 2025-11-17`; 182 days remain for 2892 and all 727 days remain for 6274, for 909 remaining symbol-days total.
- Across the eight jobs in this rolling extension, the store records exactly 11,458 successful provider requests: 11,450 KBar partitions and eight calendars. There were no transport, auth, quota-error-probe, or data-quality failures.
- Aggregate usable coverage excluding rejected 7610 is now 83 complete symbols plus partial 2892: 60,886 distinct symbol-days, 60,826 `READY`, 60 expected `EMPTY`, zero `INVALID`, and 13,099,539 canonical bars.

## 2026-08-22 Immediate Continuation

- Job `finmind-sponsor-66b204f6b4e79082` resumed exactly at `2892 / 2025-11-17`; none of its 545 sealed symbol-days was re-requested.
- The continuation spent 909 successful KBar requests and completed both 2892 and 6274 at 1,454/1,454 `READY`, zero `EMPTY`/`INVALID`, and 370,012 bars.
- The full offline audit verified every raw/canonical digest and reported zero issues. No transport timeout occurred, so the 60-second backoff was not triggered.
- The preflight showed 2,811/6,000 used and 3,189 available before the 909-request continuation, leaving rolling allowance for another diversified tranche.
- The next established high-market-value distinct-industry tranche is 3189 (`半導體業`), 5880 (`金融保險`), 2313 (`電子零組件業`), 4938 (`電腦及週邊設備業`), 2609 (`航運業`), 2404 (`其他電子業`), 2409 (`光電業`), and 1504 (`電機機械`). All are long-established listed common stocks and absent from the complete-symbol set.
- Job `finmind-sponsor-3d7b57348ab6f6d3` completed all eight symbols at 5,816/5,816 partitions: 5,815 `READY`, one expected 1504 `EMPTY`, zero `INVALID`, and 1,450,403 bars.
- Full offline audit verified all 5,816 raw/canonical digests with zero issues. The process crossed rolling-window boundaries by timestamp-scheduled waits and never encountered a transport timeout, auth failure, or data-quality stop.
- TWSE's official suspension and resumption notices explain the sole `EMPTY`: 1504 was suspended on 2025-07-30 for pending material information and resumed on 2025-07-31.
- Fixed-grid observations align to published disposition periods: 2404 used approximately five-minute matching from 2024-03-13 through 2024-03-26; 2609 from 2024-05-17 through 2024-05-30; 3189 used approximately five-minute matching from 2026-03-20 through 2026-04-08 and 2026-05-28 through 2026-06-10, then approximately twenty-minute matching from 2026-07-03 through 2026-07-16. The sparse grids remain source-faithful without interpolation.
- Aggregate usable coverage excluding rejected 7610 is now 93 complete symbols and zero partial symbols: 67,611 symbol-days, 67,550 `READY`, 61 expected `EMPTY`, zero `INVALID`, and 14,778,302 canonical bars.
- At 16:18 Asia/Taipei the local rolling ledger contained 5,817 successful requests in the preceding hour, leaving approximately 183 immediately available before subsequent timestamp-based releases.
- The next high-market-value distinct-industry set absent from the 93 complete symbols is 8299 (`半導體業`), 2801 (`金融保險`), 3044 (`電子零組件業`), 2356 (`電腦及週邊設備業`), 8069 (`光電業`), 3702 (`電子通路業`), 6139 (`其他電子業`), and 1513 (`電機機械`).
- Job `finmind-sponsor-1b20db7cd72073f0` completed all eight symbols at 5,816/5,816 `READY`, zero `EMPTY`/`INVALID`, 1,426,525 bars, and no next pending.
- Full offline audit verified all 5,816 raw/canonical partitions with zero issues. The downloader waited from the local rolling ledger and resumed at the exact `8299 / 2024-05-29` checkpoint without a quota-error probe or duplicate request.
- Fixed-grid sessions are fully reconciled: 6139 used approximately five-minute matching from 2024-04-09 through 2024-04-24; TPEx's official disposition response records 8069 at approximately five minutes from 2026-05-15 through 2026-05-28 and 8299 at approximately five minutes from 2025-09-17 through 2025-10-01, approximately twenty minutes from 2025-10-13 through 2025-10-27, and approximately five minutes from 2026-01-07 through 2026-01-20. No interpolation was performed.
- Aggregate usable coverage excluding rejected 7610 is now 101 complete symbols and zero partial symbols: 73,427 symbol-days, 73,366 `READY`, 61 expected `EMPTY`, zero `INVALID`, and 16,204,827 bars.
- From the sealed market-value and industry responses, the next established non-ETF symbols absent from the store are 2379 (`電子工業`), 5347 (`半導體業`), 2376 (`電腦及週邊設備業`), 5876 (`金融保險`), 6213 (`電子零組件業`), 2633 (`航運業`), 2347 (`電子通路業`), and 2027 (`鋼鐵工業`). Recent listing 7769 and non-normal-market candidates remain excluded.
- Job `finmind-sponsor-1b1afe9b21f9c8cc` completed the eight-symbol tranche at 5,815 `READY`, one expected `EMPTY`, zero `INVALID`, 1,391,920 bars, and no next pending. It recorded 5,817 successful provider requests including the sealed calendar.
- Full offline audit verified all 5,816 raw/canonical partitions with zero issues. No transport timeout, auth failure, quota-error probe, or data-quality stop occurred.
- The sole `EMPTY`, 5347/2024-06-05, matches the official pending-material-information suspension; trading resumed on 2024-06-06.
- TWSE's official disposition API exactly reconciles 6213's two 54-bar blocks: approximately five-minute matching from 2025-08-22 through 2025-09-04 for ten trading days, and from 2026-04-23 through 2026-05-11 for twelve trading days under the then-applicable rule.
- Aggregate usable coverage excluding rejected 7610 is now 109 complete symbols and zero partial symbols: 79,243 symbol-days, 79,181 `READY`, 62 expected `EMPTY`, zero `INVALID`, and 17,596,747 bars.
- Across Phases 25 and 26, the two eight-industry jobs recorded 11,634 successful provider requests, checkpointed 11,632 symbol-days, and produced 2,818,445 bars with zero audit issues.
- The next unused established distinct-industry set from the sealed ranking is 3034 (`電子工業`), 6415 (`半導體業`), 2324 (`電腦及週邊設備業`), 2834 (`金融保險`), 3533 (`電子零組件業`), 2049 (`電機機械`), 1102 (`水泥工業`), and 2610 (`航運業`).
- Job `finmind-sponsor-a33c2f788e5c522b` consumed the exact 183-request remainder: one sealed calendar plus 182 `READY` KBar partitions for 1102 through 2024-05-21.
- Its exact next pending is `1102 / 2024-05-22`; 5,634 symbol-days remain across the eight-symbol job. Partial audit verified all 182 partitions and 43,336 bars with zero issues.
- Aggregate usable coverage excluding rejected 7610 is now 109 complete symbols plus partial 1102: 79,425 symbol-days, 79,363 `READY`, 62 expected `EMPTY`, zero `INVALID`, and 17,640,083 bars.
- Across Phases 25 through 27, 11,817 successful requests were recorded: three calendars plus 11,814 KBar symbol-days, yielding 11,813 `READY`, one expected `EMPTY`, zero `INVALID`, and 2,861,781 bars with zero audit issues.
- Job `finmind-sponsor-a33c2f788e5c522b` completed all 5,816 symbol-days with 5,815 `READY`, one expected `EMPTY`, zero `INVALID`, 1,377,235 bars, and no next pending. Its full offline audit verified 5,816/5,816 partitions with zero issues.
- The sole `EMPTY`, 1102/2024-06-05, matches TWSE's official pending-material-information trading halt; TWSE resumed trading on 2024-06-06.
- All constrained 6415 sessions are officially reconciled. TWSE imposed approximately five-minute matching from 2026-04-24 through 2026-05-08 and from 2026-06-24 through 2026-07-07. The stored data has ten 54-bar sessions in the first period and nine 54-bar plus one 53-bar session in the second period; none fall outside the official windows.
- Aggregate usable coverage excluding rejected 7610 is now 117 complete symbols and zero partial symbols: 85,059 symbol-days, 84,996 `READY`, 63 expected `EMPTY`, zero `INVALID`, and 18,973,982 bars.
- After excluding all complete symbols and recent listings, the next established high-market-value distinct-industry set from the sealed snapshot is 3661 (`半導體業`), 3081 (`通信網路業`), 5289 (`電腦及週邊設備業`), 2492 (`電子零組件業`), 2812 (`金融保險`), 2474 (`其他電子業`), 8996 (`電機機械`), and 5434 (`電子通路業`).
- Job `finmind-sponsor-54ba31eb3cd2653b` completed its eight-symbol tranche at 5,816 `READY`, zero `EMPTY`/`INVALID`, 1,100,274 bars, 5,817 provider requests including its sealed calendar, and no next pending. Offline audit verified all 5,816 partitions with zero issues.
- Official disposition data reconciles all fixed grids in that job: TWSE records 2492's five-minute then overlapping twenty-minute periods from 2026-05-15 through 2026-08-03 and 8996's ten five-/twenty-minute periods from 2024-05-08 through 2026-07-07; TPEx records 3081's twenty-one five-/twenty-minute periods from 2024-09-04 through 2026-03-25 and 5289's overlapping five-/twenty-minute periods from 2026-03-17 through 2026-04-02. Isolated exact-54 days for 5434 and other low-liquidity observations have non-grid raw timestamps and remain source-faithful.
- Aggregate coverage after that job was 125 complete symbols and zero partial symbols: 90,875 symbol-days, 90,812 `READY`, 63 expected `EMPTY`, zero `INVALID`, and 20,074,256 bars.
- The next established distinct-industry set selected from the sealed ranking was 6770 (`半導體業`), 6442 (`通信網路業`), 3026 (`電子零組件業`), 8210 (`電腦及週邊設備業`), 6196 (`其他電子業`), 1560 (`電機機械`), 2838 (`金融保險`), and 1476 (`紡織纖維`). Recent listings 7769, 7750, 6919, and 6805 were excluded.
- Job `finmind-sponsor-de8f13a16dfaf07b` completed at 5,816 `READY`, zero `EMPTY`/`INVALID`, 1,022,458 bars, 5,817 provider requests including its sealed calendar, and no next pending. Offline audit verified every partition with zero issues.
- TWSE's official disposition API reconciles all true fixed grids in the third tranche: nine 3026 periods from 2026-04-15 through 2026-08-20, fifteen 6442 periods from 2024-02-26 through 2026-06-22, two 6770 periods from 2026-01-09 through 2026-06-15, and one 8210 period from 2025-07-21 through 2025-08-01. Exact-54 observations for 6196 have natural irregular timestamps and are not disposition grids.
- Final aggregate usable coverage excluding rejected 7610 is 133 complete symbols and zero partial symbols: 96,691 symbol-days, 96,628 `READY`, 63 expected `EMPTY`, zero `INVALID`, and 21,096,714 bars.

## 2026-08-23 Scheduled Continuation

- The automation heartbeat carried an obsolete priority checkpoint. Read-only SQLite verification shows `finmind-sponsor-eecae66e2b50523c` is already `COMPLETED`; 1301 has all 727 sessions `READY`, zero `EMPTY`/`INVALID`, and 189,882 bars.
- Re-requesting from `1301 / 2024-10-15` would duplicate sealed checkpoints, so the continuation must start with a new unused-symbol tranche instead.
- Current usable coverage excluding rejected 7610 remains 133 complete symbols and zero partial symbols: 96,691 symbol-days, 96,628 `READY`, 63 expected `EMPTY`, zero `INVALID`, and 21,096,714 bars.
- Local attempt accounting shows zero recorded FinMind requests in the preceding hour before this scheduled continuation.
- The sealed 2026-08-20 market-value response contains 2,726 rows and the sealed stock-info response contains 4,308 rows; both remain available locally, so selecting the next tranche requires no metadata API request.
- All 40 previously selected detailed-industry leaders are already included in the 133 complete-symbol set. The next continuation therefore needs within-industry depth: rank unused established common stocks by sealed market value, then choose distinct industries within the tranche.
- The corrected local join ranks the next established-looking distinct-industry shortlist as 2449 (`半導體業`), 3706 (`電腦及週邊設備業`), 6285 (`通信網路業`), 1503 (`電機機械`), 8358 (`電子零組件業`), 3324 (`其他電子類`), 9945 (`其他`), and 1229 (`食品工業`). Before acquisition, each listing date must be checked against an official TWSE/TPEx company source.
- Official TWSE evidence already confirms 2449 listed on 2001-05-09, 6285 on 2003-09-22, 1503 on 1969-12-15, and 3706 was listed through the 2013-09-12 holding-company conversion. These four comfortably predate the frozen 2023-08-19 start; the remaining candidates still require symbol-specific official checks.
- Symbol-specific TWSE company pages further confirm 9945 listed on 1992-04-30 and 1229 on 1976-07-19. The two TPEx candidates, 8358 and 3324, remain the only listing-date checks outstanding; an official 2011 TPEx trading announcement already proves 3324 predates the requested window.
- The official ISIN OTC table confirms 8358's market start date is 2010-09-27; its three-year eligibility is established. A bounded extraction is still needed to record 3324's exact date, although its official 2011 TPEx announcement already proves eligibility.
- The bounded official ISIN extraction confirms 3324 began OTC trading on 2005-05-13 and reconfirms 8358 on 2010-09-27. All eight selected symbols therefore have normal listed/OTC history predating the 2023-08-19 frozen range.
- Phase 30's selected symbols and distinct detailed industries are: 2449 (`半導體業`), 3706 (`電腦及週邊設備業`), 6285 (`通信網路業`), 1503 (`電機機械`), 8358 (`電子零組件業`), 3324 (`其他電子類`), 9945 (`其他`), and 1229 (`食品工業`).
- Job `finmind-sponsor-8253484662bd95c6` completed all 5,816 symbol-days using 5,817 successful provider requests including its calendar. Final states are 5,808 `READY`, eight `EMPTY`, zero `INVALID`, 1,313,117 bars, and no next pending.
- Full offline audit verified all 5,816 raw/canonical partitions and digests with zero issues.
- The eight source-observed `EMPTY` dates are 2449/2024-04-26 and 9945/2023-09-14 through 2023-09-22. They require official halt reconciliation before completion is final.
- True fixed full-session grids requiring official disposition reconciliation are 1503's ten 54-bar sessions from 2024-03-25 through 2024-04-09 and multiple 8358 54-/15-bar blocks from 2025-08-19 through 2026-06-18. No interpolation was performed.
- Official TWSE announcements reconcile 2449/2024-04-26: trading was suspended for pending material information and resumed on 2024-04-29.
- The official MOPS 9945 announcement filed on 2023-08-24 states that its 10% cash-capital-reduction share exchange stopped market trading from 2023-09-14 through 2023-09-22 and listed the replacement shares on 2023-09-25. This exactly reconciles all seven 9945 `EMPTY` sessions.
- TWSE's official disposition response records 1503 under approximately five-minute matching from 2024-03-25 through 2024-04-09. The ten stored 54-bar sessions match the ten trading dates in that period exactly.
- TPEx's official disposition response records all eleven 8358 periods observed in the store: five-minute periods on 2025-08-19--09-01, 2025-10-21--11-04, and 2026-04-22--05-06; twenty-minute periods on 2025-11-06--11-19, 2025-11-26--12-09, 2025-12-17--12-31, 2026-01-09--01-22, 2026-01-30--02-23, 2026-03-06--03-19, 2026-05-15--05-28, and 2026-06-05--06-18. Every stored 54-/15-bar date falls inside the corresponding official window.
- With all eight `EMPTY` dates and every fixed grid reconciled, job `finmind-sponsor-8253484662bd95c6` is fully validated: 5,816/5,816 partitions audited, 5,808 `READY`, eight expected `EMPTY`, zero `INVALID`, 1,313,117 bars, and no next pending.
- The next sealed high-market-value distinct-industry tranche is 2337 (`半導體業`), 2377 (`電腦及週邊設備業`), 2637 (`航運業`), 2855 (`金融保險業`), 3406 (`光電業`), 3491 (`通信網路業`), 6409 (`其他電子業`), and 6781 (`電子零組件業`).
- The official ISIN tables confirm all eight predate the frozen three-year window: 2337 (1995-03-15), 2377 (1998-10-31), 2637 (2010-12-01), 2855 (2002-09-16), 3406 (2005-12-20), 3491 (2008-01-03), 6409 (2014-03-31), and 6781 (2021-03-22).
- Job `finmind-sponsor-9e38dda7585f527f` used the remaining 183 requests: one sealed calendar plus 182 `READY` 2337 sessions through 2024-05-21. No `EMPTY`, `INVALID`, timeout, auth, quota, or data-quality event occurred.
- Its offline audit verified 182/182 partitions, 45,249 bars, and zero issues. Exact next pending is `2337 / 2024-05-22`; 5,634 symbol-days remain in the deterministic eight-symbol job.
- The 2026-08-23 window was used exactly: 6,000 successful provider requests, 5,998 checkpointed symbol-days, 5,990 `READY`, eight expected `EMPTY`, zero `INVALID`, and 1,358,366 new bars.
- Aggregate usable coverage excluding rejected 7610 is now 141 complete symbols plus partial 2337: 102,689 symbol-days, 102,618 `READY`, 71 expected `EMPTY`, zero `INVALID`, and 22,455,080 bars.

## 2026-08-23 Manual Rolling-Quota Resume

- Read-only status verification preserved the exact `2337 / 2024-05-22` boundary with 182 pre-existing `READY` checkpoints and 45,249 bars before live continuation.
- The continuous resume spent 5,634 new KBar requests without repeating those 182 partitions and completed deterministic job `finmind-sponsor-9e38dda7585f527f`.
- Final job state is 5,814 `READY`, two source-observed `EMPTY`, zero `INVALID`, 1,091,073 bars, and `next_pending=null` across all 5,816 expected symbol-days.
- Full offline audit re-read and verified every raw/canonical partition and digest with zero issues.
- Complete per-symbol coverage is: 2337 177,563 bars; 2377 181,834; 2637 170,085; 2855 133,276; 3406 136,688; 3491 128,964 across 725 `READY` plus two `EMPTY`; 6409 59,936; and 6781 102,727.
- The two `EMPTY` dates are 3491/2024-03-13 and 3491/2026-07-15. Both require official TPEx halt/zero-trade reconciliation before the phase can be closed.
- True fixed-grid candidates requiring official reconciliation are concentrated in 2337, 3491, and 6781. Isolated exact-54/15 counts in 2855 and 6409 may be natural low-liquidity observations and must be classified by raw timestamp spacing rather than row count alone.
- No transport timeout, auth error, quota-error probe, or data-quality stop occurred; the 60-second backoff was not triggered.
- TPEx's official historical suspension data records 3491 suspended from 2024-03-13 and resumed on 2024-03-14, then suspended from 2026-07-15 and resumed on 2026-07-16. Both `EMPTY` partitions are therefore expected one-day trading halts rather than missing provider data.
- TWSE's official disposition data reconciles 2337's constrained grids: approximately five-minute matching on 2026-01-12--01-23, 2026-03-19--04-01, and 2026-06-03--06-16, with an overlapping approximately twenty-minute measure on 2026-03-24--04-08. The stored 54-/15-bar sessions follow the effective periods.
- TWSE's official disposition data reconciles 6781's approximately five-minute period on 2024-11-13--11-26, overlapping approximately twenty-minute period on 2024-11-18--11-29, and approximately twenty-minute period on 2024-12-09--12-20. The stored 54-/15-bar sessions match those periods.
- TPEx's official disposition data reconciles all true 3491 fixed grids: five-minute periods on 2024-05-28--06-11, 2025-12-18--2026-01-02, and 2026-05-26--06-08, plus twenty-minute periods on 2026-01-23--02-05, 2026-02-05--03-02, 2026-03-04--03-17, and 2026-03-12--03-25.
- After excluding all 149 complete symbols, rejected 7610, ETFs, and recent listings, the next sealed-snapshot distinct-industry tranche is 6515 (`半導體業`), 2353 (`電腦及週邊設備業`), 2467 (`電子零組件業`), 2354 (`其他電子業`), 4979 (`通信網路業`), 9910 (`運動休閒`), 3167 (`電機機械`), and 2634 (`航運業`).
- Official exchange company records confirm every selected stock predates the frozen 2023-08-19 start: 6515 (2021-01-20), 2353 (1996-09-18), 2467 (2001-09-17), 2354 (1996-10-08), 4979 (2011-12-12), 9910 (1992-02-18), 3167 (2013-10-21), and 2634 (2014-08-25).
- New job `finmind-sponsor-3b89b912c38e836b` spent the exact 366-request preflight allowance: one calendar plus 365 `READY` 2353 partitions through 2025-02-24. The provider reported 5,634/6,000 used before this job, so the two acquisitions together consumed exactly 6,000 successful requests without a quota-error probe.
- Partial offline audit verified 365/365 raw and canonical digests, 96,267 bars, and zero issues. Exact next pending is `2353 / 2025-02-25`; 5,451 symbol-days remain in the eight-symbol job.
- Raw timestamp-gap inspection confirms every isolated exact-54/15 observation outside official disposition periods is a natural sparse trading session: 2855/2024-01-25, 3491/2025-04-10, all twelve such 6409 dates, and all eight pre-disposition 6781 dates have irregular trade-minute intervals rather than five-/twenty-minute grids.
- Aggregate usable coverage excluding rejected 7610 is now 149 complete symbols plus partial 2353: 108,688 symbol-days, 108,615 `READY`, 73 expected `EMPTY`, zero `INVALID`, and 23,597,171 canonical bars.
- Rolling usage-preflight continuation then consumed only newly released allowance and completed job `finmind-sponsor-3b89b912c38e836b` at 5,816/5,816 `READY`, zero `EMPTY`/`INVALID`, 1,192,051 bars, 5,817 recorded requests including one calendar, and no next pending.
- Full offline audit verified all 5,816 raw and canonical digests with zero issues. Per-symbol bars are 2353 191,651; 2354 181,601; 2467 124,331; 2634 181,312; 3167 113,428; 4979 165,303; 6515 108,760; and 9910 125,665.
- TWSE official disposition periods reconcile 2467's five-minute grids on 2024-07-08--07-23 and 2026-03-05--03-18 plus its twenty-minute grid on 2026-04-15--04-28. Stored counts are 52--54 and 14--15 because no-trade intervals remain absent.
- TWSE official disposition periods reconcile 3167's five-minute grids on 2024-09-25--10-11 (extended through 10-15 by market closures), 2025-09-10--09-23, and 2026-02-24--03-10; overlapping twenty-minute periods cover 2026-03-17 through 2026-08-13, followed by a two-minute period on 2026-08-11--08-17. Stored observations follow the effective frequencies without interpolation.
- TPEx official disposition periods reconcile 4979's twenty-minute grids on 2023-08-31--09-13 and five-minute grid on 2023-11-01--11-14, plus five-/twenty-/two-minute periods from 2026-03-03 through 2026-08-20. The frozen-window 2023-08-21 twenty-minute grid is the one-day extension of the 2023-08-03--08-18 period after the 2023-08-03 typhoon market closure.
- TWSE official disposition periods reconcile 6515's five-minute periods on 2025-09-04--09-17 and 2026-03-26--04-10; source counts vary from 35--54 because only actual matching minutes are retained.
- Exact-54/15 observations outside official periods are natural sparse trading days, confirmed by irregular raw timestamp gaps: 2467/2023-10-25 and 3167/2023-10-13, 2023-10-17, and 2023-11-01.
- Aggregate usable coverage excluding rejected 7610 is now 157 complete symbols and zero partial symbols: 114,139 symbol-days, 114,066 `READY`, 73 expected `EMPTY`, zero `INVALID`, and 24,692,955 canonical bars.
- After excluding all 157 complete symbols and recent/mixed-market entries, the next sealed-snapshot distinct-industry tranche is 6239 (`半導體業`), 2385 (`電子零組件業`), 2455 (`通信網路業`), 6691 (`其他電子業`), 3005 (`電腦及週邊設備業`), 2915 (`貿易百貨`), 2645 (`航運業`), and 2845 (`金融保險業`).
- Official TWSE company pages confirm all eight have normal listed history covering the frozen window: 6239 (2004-11-08), 2385 (1999-01-05), 2455 (2002-01-24), 6691 (2022-01-03), 3005 (2002-02-25), 2915 (1977-07-20), 2645 (2023-03-14), and 2845 (1998-11-27).
- Job `finmind-sponsor-f9728f6f8f43c270` used the exact final 183-request preflight allowance: one calendar plus 182 `READY` 2385 partitions through 2024-05-21. Exact next pending is `2385 / 2024-05-22`; 5,634 symbol-days remain.
- Partial audit verified 182/182 raw and canonical digests, 43,903 bars, and zero issues. SQLite `quick_check` returned `ok`.
- This manual continuation recorded exactly 11,634 successful provider requests: 5,634 KBar calls completed the prior job, 5,817 requests completed the second eight-industry job, and 183 requests advanced the third job. They checkpointed 11,632 symbol-days: 11,630 `READY`, two expected `EMPTY`, zero `INVALID`, and 2,281,778 bars.
- Final aggregate usable coverage excluding rejected 7610 is 157 complete symbols plus partial 2385: 114,321 symbol-days, 114,248 `READY`, 73 expected `EMPTY`, zero `INVALID`, and 24,736,858 canonical bars.

## 2026-08-23 Checkpoint-Safe Continuation

- The referenced backtest-memory task is complete and explicitly left deleted-database recovery stopped; FinMind Sponsor acquisition remains a separate data-only path.
- Read-only SQLite verification at 13:55 Asia/Taipei confirms job `finmind-sponsor-f9728f6f8f43c270` is `PAUSED` only because its prior batch budget was reached.
- The sealed calendar still contains 727 sessions and the symbols remain `2385, 2455, 2645, 2845, 2915, 3005, 6239, 6691`.
- Exactly 182 `READY` partitions exist for 2385 from 2023-08-21 through 2024-05-21, containing 43,903 bars; there are no `EMPTY` or `INVALID` partitions in this job.
- The request ledger contains one calendar attempt plus 182 KBar attempts, and the exact first uncheckpointed partition is `2385 / 2024-05-22`.
- SQLite `quick_check` is `ok`; no provider request was made during this verification.
- Seven positive official usage-preflight batches resumed only uncheckpointed partitions and completed job `finmind-sponsor-f9728f6f8f43c270`: 5,816/5,816 `READY`, zero `EMPTY`/`INVALID`, 1,213,278 bars, and no next pending.
- The completed per-symbol bar totals are 2385 174,033; 2455 163,481; 2645 128,700; 2845 153,846; 2915 144,742; 3005 172,471; 6239 177,117; and 6691 98,888.
- Full offline audit re-read all 5,816 raw/canonical partitions and digests with zero issues.
- TWSE official disposition data reconciles every true fixed grid: 2455 was matched about every five minutes from 2026-03-02 through 03-13 and about every twenty minutes during 04-13--04-24, 05-06--05-19, 05-27--06-09, and 06-22--07-03; 6239 was matched about every five minutes from 2026-05-29 through 06-11.
- No transport timeout, auth error, quota-error probe, provider stop, or data-quality failure occurred, so the 60-second transport backoff was not triggered.
- After excluding all 165 complete symbols, rejected 7610, ETFs, and recent listings, the next sealed-snapshot distinct-industry tranche is 3529 (`半導體業`), 3023 (`電子零組件業`), 6121 (`電腦及週邊設備業`), 3363 (`通信網路業`), 3030 (`其他電子業`), 6005 (`金融保險`), 2606 (`航運業`), and 2006 (`鋼鐵工業`).
- Official ISIN tables confirm full frozen-window eligibility: 2006 (1988-07-13), 2606 (1990-12-08), 3023 (2002-08-26), 3030 (2002-10-29), 3363 (2011-02-25), 3529 (2011-01-24), 6005 (2005-11-21), and 6121 (2001-11-27).
- New job `finmind-sponsor-cbd9954018dc7546` spent its exact 366-request preflight allowance: one calendar plus 365 `READY` 2006 partitions through 2025-02-24. Partial audit verified 365/365 partitions, 69,568 bars, and zero issues; exact next pending is `2006 / 2025-02-25`.
- This continuation used exactly 6,000 successful provider requests: 5,634 KBar calls completed the prior job and 366 requests advanced the new job. They checkpointed 5,999 new `READY` symbol-days, zero `EMPTY`/`INVALID`, and 1,238,943 new bars.
- Aggregate usable coverage excluding rejected 7610 is now 165 complete symbols plus partial 2006: 120,320 symbol-days, 120,247 `READY`, 73 expected `EMPTY`, zero `INVALID`, and 25,975,801 canonical bars. SQLite `quick_check` is `ok`.

## 2026-08-23 Second Checkpoint-Safe Continuation

- Read-only SQLite verification at 15:26 Asia/Taipei confirms job `finmind-sponsor-cbd9954018dc7546` remains `PAUSED` with exactly 365 `READY` 2006 partitions through 2025-02-24, 69,568 bars, one sealed calendar, and exact next pending `2006 / 2025-02-25`.
- SQLite `quick_check` is `ok`; the job's `updated_at` remains 14:50, so the 15:32 heartbeat has not advanced the checkpoint.
- The local process-list diagnostic is unavailable because `pgrep` cannot access `sysmond`; the imminent heartbeat must therefore be moved before starting the manual writer to guarantee single-writer operation.
- The active manual writer resumed only from `2006 / 2025-02-25`. Three positive official-usage preflights consumed exactly 6,000 successful requests in this turn: 5,451 KBar calls completed job `finmind-sponsor-cbd9954018dc7546`, then one calendar plus 548 KBar calls started the next deterministic tranche.
- Completed job `finmind-sponsor-cbd9954018dc7546` has 5,816/5,816 `READY`, zero `EMPTY`/`INVALID`, 1,103,824 bars, and a full 5,816/5,816 offline audit with zero issues.
- New job `finmind-sponsor-ffbf4a85539d9edc` contains symbols 1785, 2371, 2486, 2889, 3105, 3163, 6414, and 8039. Its first 548 partitions are all `READY`, contain 125,394 bars, audit cleanly, and end at 1785/2025-11-19; the exact next pending partition is `1785 / 2025-11-20`.
- The next tranche uses eight distinct industries and all symbols predate the frozen window according to the official ISIN tables: 1785 (2005-01-31), 2371 (1962-02-09), 2486 (2001-09-19), 2889 (2002-03-26), 3105 (2011-12-13), 3163 (2012-12-03), 6414 (2014-03-28), and 8039 (2009-12-17). Candidate 6472 was excluded because its current TWSE date, 2023-12-19, did not independently prove pre-window TPEx history.
- Current aggregate usable coverage excluding rejected 7610 is 173 complete symbols plus partial 1785: 126,319 symbol-days, 126,246 `READY`, 73 expected `EMPTY`, zero `INVALID`, and 27,135,451 canonical bars. SQLite `quick_check` is `ok`.
- The official TPEx disposal page initializes its report with `pattern: API_PATTERN` and `action: "bulletin/disposal"`; TPEx's own `main.js` defines `API_PATTERN="/www/{LANG}/{ACTION}"`. The authoritative Traditional-Chinese POST endpoint is therefore `/www/zh-tw/bulletin/disposal`, with page-native fields `startDate`, `endDate`, `type`, `code`, `reason`, `measure`, and `order`.
- Diagnostic note: the first referenced-task read used an unsupported `turnLimit=20`; the app accepts at most 10, and retrying with 10 succeeded. Initial sandboxed TPEx `curl` attempts could not resolve DNS; the same read-only requests succeeded after the required network approval.
- TPEx's official disposal response reconciles all true 3363 fixed grids through 21 five-/twenty-minute periods. They span 2024-03-05--03-20, 2024-05-28--06-11, 2024-06-24--07-05, the closure-extended 2024-07-16--07-31 period, 2024-10-14--10-25, successive twenty-minute periods from 2024-11-05 through 2025-06-23, 2025-08-19--09-01, 2025-09-09--09-22, 2025-12-05--12-18, and three 2026 periods ending 2026-05-08. Stored 54-/15-bar observations fall inside those official windows; no interpolation is needed.
- TPEx's official disposal response reconciles both 3529 five-minute blocks: 2026-02-26--03-12 and 2026-04-22--05-06. Every stored exact-54 session for 3529 falls inside those periods.
- TWSE's official disposition response records 3030 under approximately five-minute matching from 2026-05-08 through 2026-05-21, exactly covering its nine stored 54-bar sessions. The two other exact-54 observations, 3030/2023-11-23 and 3030/2023-11-29, are natural sparse sessions: their raw minute gaps vary broadly (1--25 and 1--27 minutes, respectively), whereas 3030/2026-05-08 has 52 five-minute gaps plus one ten-minute no-trade gap.

## 2026-08-23 16:32 Scheduled Continuation

- Live SQLite verification at the scheduled trigger confirms job `finmind-sponsor-ffbf4a85539d9edc` is still `PAUSED` at exactly 548/5,816 checkpoints, all `READY`, with 125,394 bars and exact next pending `1785 / 2025-11-20`.
- The sealed 727-session calendar and first 548 1785 partitions remain unchanged; the request ledger contains one calendar plus 548 KBar attempts. Offline audit verified 548/548 partitions with zero issues and SQLite `quick_check` is `ok`.
- The broad worktree still contains unrelated user/concurrent changes; only the isolated acquisition planning files and ignored SQLite acquisition store remain in scope.
- After completing the active job, the local sealed 2026-08-20 join reports 181 complete usable symbols. Recent listings 7769, 7750, 6919, 6805, 2646, 2258, and 6944 remain ineligible for a full frozen-window history; the next established-looking distinct-industry set is 8021, 3211, 8112, 6278, 2597, 2850, 4763, and 9917.
- Fresh read-only copies of the official TWSE ISIN listed and OTC tables were acquired for the eight symbol-specific listing-date checks; no FinMind metadata request was spent.
- Official ISIN rows confirm all eight next-tranche candidates predate the frozen start: 8021 (2008-01-21), 3211 (2004-11-08), 8112 (2007-12-31), 6278 (2010-08-24), 2597 (2010-03-26), 2850 (2000-05-22), 4763 (2015-11-09), and 9917 (1993-12-08). They are eligible for the requested full three-year normal-market history.
- TPEx's official disposal response exactly reconciles 1785's ten 54-bar sessions to approximately five-minute matching from 2026-04-16 through 2026-04-29, and 3105's 53/54-bar block to approximately five-minute matching from 2026-03-03 through 2026-03-16.
- TWSE's official disposition response reconciles all true 2486 grids: five-minute matching on 2024-06-20--07-03 and 2026-01-30--02-23, plus twenty-minute matching on 2024-07-09--07-22 and three 2026 periods covering 03-20--05-20.
- TPEx's official disposition response reconciles all true 3163 grids: five-minute periods on 2025-11-04--11-19, 2025-12-16--2026-01-02, and 2026-06-22--07-03; consecutive twenty-minute periods cover 2026-01-12--05-20. The response also records a two-minute period beginning 2026-08-13, explaining the denser constrained observations near the frozen range end.
- TWSE's official disposition response reconciles 8039's ten-session five-minute block from 2024-08-30 through 2024-09-12. Raw timestamp inspection classifies the isolated exact-count observations on 2023-10-13, 2023-12-08, and 2023-12-19 as naturally sparse: their gaps range irregularly across 1--29, 1--21, and 1--21 minutes rather than forming fixed grids.
- Official TWSE ordinary-share capital-reduction records for 2371 identify the 2025 reduction and the 2025-06-23 replacement-share restart. The related MOPS announcement specifies that old shares stopped trading from 2025-06-12 through 2025-06-20; those seven trading dates exactly match the seven preserved `EMPTY` checkpoints.
- Raw timestamp inspection also classifies 6414/2025-05-27 (53 bars, irregular 1--19 minute gaps) and 3163/2025-04-07 (21 bars, irregular 1--44 minute gaps) as natural sparse sessions, not provider downsampling or disposition grids.
- Positive official-usage preflight batches spent exactly 5,268 new KBar requests to complete job `finmind-sponsor-ffbf4a85539d9edc` without repeating its calendar or first 548 partitions. Final state is 5,809 `READY`, seven expected `EMPTY`, zero `INVALID`, 1,250,046 bars, and no next pending.
- Full offline audit verified 5,816/5,816 partitions and digests with zero issues. The seven `EMPTY` dates, every official five-/twenty-/two-minute period, and all isolated exact-count sparse sessions are now reconciled without interpolation or repair.
- After excluding all 181 complete usable symbols, rejected 7610, ETFs, recent listings, and unproven candidates, the next eligible distinct-industry set is 8021 (`其他電子業`), 3211 (`電腦及週邊設備業`), 8112 (`電子通路業`), 6278 (`光電業`), 2597 (`建材營造`), 2850 (`金融保險`), 4763 (`化學工業`), and 9917 (`其他`). Official ISIN dates confirm full frozen-window eligibility for all eight.
- Deterministic job `finmind-sponsor-d561ed5fd6d7a9bd` used the final 732 positive-preflight requests: one calendar plus 731 `READY` KBar partitions. It completed all 727 dates for 2597 and checkpointed the first four 2850 dates through 2023-08-24; exact next pending is `2850 / 2023-08-25`.
- Partial audit verified 731/731 partitions, 65,404 bars, and zero issues. Across the scheduled continuation, exactly 6,000 successful provider requests checkpointed 5,999 symbol-days: 5,992 `READY`, seven expected `EMPTY`, zero `INVALID`, and 1,190,056 new bars.
- Aggregate usable coverage excluding rejected 7610 is now 182 complete symbols plus partial 2850: 132,318 symbol-days, 132,238 `READY`, 80 expected `EMPTY`, zero `INVALID`, and 28,325,507 canonical bars. Including the two quarantined 7610 partitions, the physical store has 132,320 partitions, one `INVALID`, and 28,325,512 bars. SQLite `quick_check` is `ok`.

## 2026-08-23 23:20 Manual Continuation

- Official usage preflight returned a fresh 0/6,000 window. Resuming only uncheckpointed dates spent 5,085 KBar requests and completed job `finmind-sponsor-d561ed5fd6d7a9bd` without repeating its calendar or 731 prior partitions.
- Final job state is 5,809 `READY`, seven `EMPTY`, zero `INVALID`, 958,955 bars, and no next pending. Full offline audit verified 5,816/5,816 partitions and digests with zero issues; SQLite `quick_check` is `ok`.
- All seven new `EMPTY` observations belong to 4763 from 2025-06-19 through 2025-06-27. They are preserved source-faithfully pending official suspension/share-exchange reconciliation.
- Fixed-grid candidates are concentrated in 3211, 6278, and 8021, with isolated exact-count observations in 2597, 2850, and 9917. Official disposition intervals and raw timestamp gaps must distinguish true five-/twenty-minute controls from natural sparse sessions.
- After excluding 189 complete usable symbols, rejected 7610, ETFs, recent listings, and incomplete-history candidates, the next sealed-snapshot distinct-industry tranche is 6531 (`半導體業`), 3042 (`電子零組件業`), 5522 (`建材營造`), 1477 (`紡織纖維`), 9941 (`其他`), 2206 (`汽車工業`), 2312 (`其他電子業`), and 8926 (`油電燃氣業`).
- Official TWSE/ISIN records confirm all eight predate the frozen start: 6531 (2016-05-31), 3042 (2002-08-26), 5522 (2007-08-06), 1477 (2003-01-21), 9941 (2001-09-17), 2206 (1996-07-29), 2312 (1989-11-07), and 8926 (2003-08-25).
- TWSE's official June 2025 daily record has no 4763 prints from 2025-06-19 through 2025-06-27 and marks the 2025-06-30 restart as a face-value-change resumption. The associated MOPS disclosure records a TWD 10-to-1 face-value change and exactly the same seven-session trading stop, so all seven `EMPTY` checkpoints are expected.
- TPEx's official disposition response reconciles 3211's 2024-11-15 through 2024-11-28 period to approximately five-minute matching. TWSE's official response likewise reconciles 6278's 2026-04-20 through 2026-05-04 block to five-minute matching.
- TWSE's official disposition responses reconcile every true 8021 grid: five-minute matching on 2025-08-11--08-22, 2026-01-26--02-06, and 2026-04-15--04-28; twenty-minute matching on 2025-08-26--09-08, 2026-04-27--05-11, 2026-05-26--06-08, 2026-06-16--06-30, and 2026-07-03--07-16. The final observed 2026-07-17 grid is the tenth trading session after the non-trading 2026-07-10 date and is covered by the official extension rule.
- Raw timestamp gaps classify the remaining isolated exact-count observations as natural sparse trading rather than fixed grids: 2597 varies across 1--77 minutes, 2850 across 1--36, 9917 across 1--34, 3211/2023-09-05 across 1--19, and the two 8021 2023 dates across 1--42. No rows were interpolated or repaired.

## 2026-08-24 Rolling-Window Continuation

- Deterministic job `finmind-sponsor-e7bed6eb88f4fd81` started with zero checkpoints. Its initial official usage preflight returned 5,085/6,000 used and an exact 915-request remainder; later resumes used only newly released positive allowance.
- The completed job has 5,816 `READY`, zero `EMPTY`, zero `INVALID`, 1,117,083 bars, and no next pending. Offline audit verified 5,816/5,816 partitions and digests with zero issues; SQLite `quick_check` is `ok`.
- Per-symbol bar totals are 1477 157,061; 2206 130,119; 2312 176,520; 3042 150,006; 5522 112,799; 6531 154,573; 8926 121,722; and 9941 114,283.
- TWSE's official disposition records reconcile all true grids: 2312's five-minute period on 2026-01-20--02-02; 3042's overlapping five-minute 2026-04-16--04-29 and twenty-minute 2026-04-21--05-05 periods; 6531's five-minute periods on 2026-04-27--05-11 and 2026-08-03--08-14, followed by the official two-minute second disposition beginning 2026-08-11.
- Raw timestamp gaps classify the three 5522 isolated 54-row dates as natural sparse trading with irregular 1--50-minute gaps, and 9941/2025-04-28 likewise has irregular 1--41-minute gaps. No bars were interpolated or repaired.
- After excluding 197 complete usable symbols, rejected 7610, ETFs, and recent/unproven listings, the next distinct-industry tranche is 3260 (`半導體業`), 1815 (`電子零組件業`), 1319 (`汽車工業`), 1210 (`食品工業`), 1773 (`化學工業`), 2352 (`電腦及週邊設備業`), 2540 (`建材營造`), and 3563 (`光電業`).
- Official ISIN rows confirm all eight predate the frozen start: 3260 (2004-10-08), 1815 (2006-01-23), 1319 (1994-12-12), 1210 (1978-05-20), 1773 (2009-02-27), 2352 (1996-07-22), 2540 (1989-12-26), and 3563 (2019-04-02).
- New job `finmind-sponsor-51388b566e74d689` used one calendar plus 1,097 KBar requests. It completed 1210 at 727 `READY` and 140,137 bars, then checkpointed 370 `READY` 1319 dates through 2025-03-04 with 89,136 bars; exact next pending is `1319 / 2025-03-05`.
- Partial-job audit verified 1,097/1,097 partitions and 229,273 bars with zero issues. It contains no `EMPTY`, `INVALID`, or exact 15/54-row fixed-grid observations.
- Aggregate usable coverage excluding quarantined 7610 is now 198 complete symbols plus partial 1319: 144,316 partitions, 144,229 `READY`, 87 expected `EMPTY`, zero `INVALID`, and 30,565,414 canonical bars.
- Across this manual continuation, exactly 12,000 successful requests checkpointed 11,998 symbol-days: 11,991 `READY`, seven officially expected 4763 `EMPTY`, zero `INVALID`, and 2,239,907 bars. No timeout, auth, provider, quota-error probe, or data-quality failure occurred. `execution_enabled=false` and all order, account, broker, commit, and push paths remained untouched.
- Two bounded Codex automation-manager updates failed to return, and the Computer Use fallback is prohibited from controlling the Codex app. The persisted `finmind` automation remains the obsolete 16:32 one-shot for job `finmind-sponsor-ffbf4a85539d9edc`; it is not a valid continuation schedule and was not hand-edited.

## 2026-08-24 Checkpoint-Safe Continuation

- Positive official preflight reported a fresh 0/6,000 window. Resuming only uncheckpointed dates spent 4,719 KBar requests and completed job `finmind-sponsor-51388b566e74d689` without repeating its calendar or first 1,097 partitions.
- Final job state is 5,809 `READY`, seven expected `EMPTY`, zero `INVALID`, 1,125,746 bars, and no next pending. Full offline audit verified all 5,816 raw/canonical partitions and digests with zero issues; SQLite `quick_check` is `ok`.
- The six 2352 `EMPTY` dates from 2025-09-25 through 2025-10-03 match its official cash-capital-reduction share-exchange trading stop; replacement shares resumed on 2025-10-07. The 3260 `EMPTY` on 2025-10-01 matches TPEx's official pending-material-information suspension.
- TPEx official disposition records reconcile 1815's five-minute periods on 2025-08-19--09-01 and 2026-03-06--03-19, and 3260's overlapping five-/twenty-minute period on 2026-01-02--01-22 plus its five-minute period on 2026-03-19--04-01.
- TWSE/TPEx report no disposition period for the isolated exact-count observations in 1773, 2540, and 3563. Raw timestamp gaps are irregular from 1--36, 1--32, and 1--61 minutes respectively, so they are natural sparse sessions rather than provider downsampling.
- Per-symbol coverage is 1210 140,137 bars; 1319 174,006; 1773 78,441; 1815 180,819; 2352 173,082 across 721 `READY` plus six expected `EMPTY`; 2540 99,402; 3260 173,981 across 726 `READY` plus one expected `EMPTY`; and 3563 105,878.
- Aggregate usable coverage excluding quarantined 7610 is now 205 complete symbols: 149,035 partitions, 148,941 `READY`, 94 expected `EMPTY`, zero `INVALID`, and 31,461,887 canonical bars.
- The next sealed-snapshot distinct-industry tranche is 1722 (`化學工業`), 2923 (`建材營造`), 3714 (`光電業`), 9921 (`運動休閒`), 5903 (`居家生活類`), 9933 (`其他`), 8415 (`鋼鐵工業`), and 2464 (`其他電子業`). Official listing dates are 1998-03-24, 2012-12-07, 2021-01-06, 1994-12-29, 2002-02-25, 1993-05-28, 2016-09-07, and 2001-09-17 respectively, all before the frozen start.

## 2026-08-24 Remaining-Positive-Allowance Completion

- Deterministic job `finmind-sponsor-4cb46283cc3a19e3` covers 1722, 2464, 2923, 3714, 5903, 8415, 9921, and 9933 over the same 727-session frozen calendar.
- The first positive preflight exposed 1,273 requests. One calendar plus 761 KBar responses were checkpointed before an uncaught peer connection reset; the exact durable next pending was `2464 / 2023-10-11`.
- After the user-directed full 60-second backoff, the same command received a fresh positive 6,000-request window and spent only the remaining 5,055 KBar requests. It did not request the calendar or first 761 symbol-days again.
- Final state is `COMPLETED`: 5,813 `READY`, three expected `EMPTY`, zero `INVALID`, 824,597 bars, 5,817 recorded successful requests including the calendar, and `next_pending=null`.
- Per-symbol coverage is 1722 136,488 bars; 2464 153,601; 2923 17,487; 3714 145,023; 5903 22,341 across 725 `READY` plus two expected `EMPTY`; 8415 52,014; 9921 135,321; and 9933 162,322 across 726 `READY` plus one expected `EMPTY`.
- Full offline audit verified 5,816/5,816 raw and canonical partitions with zero issues. The request ledger is one `CALENDAR READY`, 5,813 `KBAR READY`, and three `KBAR EMPTY`; SQLite `quick_check` is `ok`.
- TPEx's official 5903 monthly table reports normal-market OHLC as `--` on 2023-09-15 and 2023-09-20, exactly matching the two empty regular-minute partitions. TPEx's official 2023 halt table contains no 5903 suspension, so these are source-faithful no-normal-OHLC sessions rather than missing requests.
- TWSE announced 9933 suspended from 2025-05-13 for pending material information and resumed it on 2025-05-14, exactly reconciling its single `EMPTY`.
- TWSE's official disposition response places 3714 under approximately five-minute matching from 2026-04-20 through 2026-05-04. Its ten stored sessions are all 54 bars with fixed five-minute timing, so no interpolation or repair is required.
- TWSE records the same 2026-04-20--05-04 five-minute disposition for low-liquidity 2923. Other exact 15/54-count dates for 2923 and all such dates for 2464, 5903, and 8415 have irregular raw gaps; official queries show no corresponding disposition for 2464, 5903, or 8415, so those isolated counts are natural sparse trading.
- Aggregate usable coverage excluding quarantined 7610 is now 213 complete symbols: 154,851 partitions, 154,754 `READY`, 97 expected `EMPTY`, zero `INVALID`, and 32,286,484 canonical bars.
- Across Phases 38 and 39, 10,536 successful provider responses were recorded: 4,719 resumed KBar calls completed the prior job, then 5,817 successful requests completed the new job. The peer-reset request received no response and is not represented as a successful provider request.

## 2026-08-24 Final Released Allowance

- After excluding 213 complete symbols and recent/ineligible listings, the next sealed-snapshot distinct-industry tranche is 2539 (`建材營造`), 4766 (`化學工業`), 1409 (`紡織纖維`), 6116 (`光電業`), 9939 (`其他`), 2015 (`鋼鐵工業`), 8070 (`電子通路業`), and 3596 (`通信網路業`).
- The official TWSE ISIN table lists them on 1997-07-16, 2018-11-28, 1973-08-31, 2004-09-06, 2001-03-02, 1992-05-25, 2007-12-31, and 2009-03-11 respectively, all before the frozen 2023-08-19 start.
- Deterministic job `finmind-sponsor-3709bd4ca4276f5b` was created with zero provider requests. Its official preflight reported 5,057/6,000 used and exactly 943 remaining requests; all 943 were spent without a quota-error probe as one calendar plus 942 KBar calls.
- The partial job has 942 `READY`, zero `EMPTY`/`INVALID`, 141,906 bars, and exact next pending `2015 / 2024-07-09`. It fully completes 1409 at 727 partitions and 126,595 bars, then checkpoints 215 dates of 2015 through 2024-07-08 with 15,311 bars.
- Offline audit verified 942/942 raw and canonical partitions with zero issues; SQLite `quick_check` is `ok`.
- TWSE's official disposition response records 1409 under approximately five-minute matching from 2026-06-04 through 2026-06-17. The stored block contains nine 54-bar sessions and one 53-bar session with fixed five-minute timing plus missing-trade gaps, which is consistent and requires no repair.
- TWSE reports no disposition for 2015 in the acquired interval. Its isolated 2023-09-19 and 2023-11-09 54-bar sessions have irregular 1--26-minute raw gaps, so they are natural sparse trading rather than provider downsampling.
- Aggregate usable coverage excluding quarantined 7610 is now 214 complete symbols plus partial 2015: 155,793 partitions, 155,696 `READY`, 97 expected `EMPTY`, zero `INVALID`, and 32,428,390 canonical bars.
- Across Phases 38--40, this continuation recorded 11,479 successful provider responses and checkpointed 11,476 symbol-days. No quota-error probe was sent; the only transport interruption was the single peer reset handled by the full 60-second backoff and exact resume.

## 2026-08-24 Stale-Heartbeat Reconciliation and Continued Acquisition

- Live SQLite superseded the obsolete heartbeat prompt: job `finmind-sponsor-ffbf4a85539d9edc` was already `COMPLETED` at 5,816 checkpoints, while the actual paused job was `finmind-sponsor-3709bd4ca4276f5b` at exact next pending `2015 / 2024-07-09`.
- Resuming the actual job spent exactly 4,874 KBar requests. It did not request the sealed calendar, any of 1409's 727 partitions, or the first 215 dates of 2015 again.
- Job `finmind-sponsor-3709bd4ca4276f5b` is now `COMPLETED`: 5,816 `READY`, zero `EMPTY`/`INVALID`, 945,324 bars, and `next_pending=null`. Offline audit verified all 5,816 raw/canonical partitions with zero issues.
- Per-symbol bar totals are 1409 126,595; 2015 63,835; 2539 89,474; 3596 137,798; 4766 91,177; 6116 155,904; 8070 151,719; and 9939 128,822.
- TWSE's official disposition response exactly reconciles 6116's ten five-minute sessions on 2026-01-12--01-23, three five-minute sessions on 2026-06-01--06-03, and nine twenty-minute sessions on 2026-06-05--06-17. The overlapping second disposition changed matching from approximately five to twenty minutes starting 2026-06-04.
- TWSE returns no disposition rows for 2015, 2539, or 4766 in the frozen interval. Their exact 54-/15-row observations have irregular raw timestamp gaps, so they are natural sparse trading rather than provider downsampling. The already reconciled 1409 disposition block remains unchanged.
- After excluding 221 complete symbols plus recent/ineligible entries, the next sealed-snapshot distinct-industry set is 6789 (`半導體業`), 3090 (`電子零組件業`), 1736 (`運動休閒`), 4583 (`電機機械`), 6592 (`其他`), 3019 (`光電業`), 2504 (`建材營造`), and 2851 (`金融保險`).
- The official TWSE company dataset lists these eight on 2022-06-30, 2007-12-31, 2003-01-09, 2022-05-09, 2019-12-09, 2002-08-26, 1978-03-14, and 2000-07-06 respectively; all predate 2023-08-19.
- New deterministic job `finmind-sponsor-991a2e7af862a395` used two authoritative positive-preflight releases: first one calendar plus 213 KBar requests from a 214-request balance, then 483 additional KBar requests after the rolling window released them. It now has 696 `READY`, zero `EMPTY`/`INVALID`, 93,587 bars, and exact next pending `1736 / 2026-07-06`.
- Partial-job audit verified 696/696 partitions with zero issues. Its two 54-row dates have irregular 1--39-minute gaps, and TWSE returns no disposition rows for 1736, so both are natural sparse sessions.
- This heartbeat recorded 5,571 successful provider responses: 5,570 checkpointed `READY` symbol-days plus one new calendar, zero `EMPTY`, zero `INVALID`, and 897,005 new bars. Aggregate usable coverage excluding 7610 is 221 complete symbols plus partial 1736: 161,363 partitions, 161,266 `READY`, 97 expected `EMPTY`, zero `INVALID`, and 33,325,395 bars. SQLite `quick_check` is `ok`.
- The Codex automation manager's view, update, and delete operations did not return and were terminated after bounded waits. The persisted `finmind` one-shot remains stale; it was not hand-edited and must not be used as a future acquisition authority.

## 2026-08-25 Checkpoint-Safe Completion and Remaining Allowance

- The first live continuation of `finmind-sponsor-991a2e7af862a395` preserved 1,559 `READY` partitions and exact next pending `2851 / 2024-01-19` when a transport timeout ended the detached process. More than the required 60 seconds elapsed before the same deterministic command resumed, and no completed symbol-day or sealed calendar was requested again.
- The resumed process spent 4,257 successful KBar requests and completed the job. Across this user continuation, 5,120 new symbol-days were checkpointed as 5,119 `READY` plus one expected `EMPTY`, adding 822,530 bars; one separate failed transport attempt remains in the request ledger.
- Final job state is `COMPLETED`: 5,815 `READY`, one expected `EMPTY`, zero `INVALID`, 916,117 bars, and no next pending. Full offline audit verified 5,816/5,816 raw and canonical partitions with zero issues; SQLite `quick_check` is `ok`.
- Per-symbol coverage is 1736 97,798 bars; 2504 152,336; 2851 103,167; 3019 157,199; 3090 120,605 across 726 `READY` plus one expected `EMPTY`; 4583 68,770; 6592 77,478; and 6789 138,764.
- The sole `3090 / 2025-07-15` `EMPTY` matches the official material-information suspension and next-day resumption. Official disposition periods reconcile 3019's 2024-12-23--2025-01-08 five-minute block, 3090's 2026 five-/twenty-minute blocks, and 4583's 2024-09-03--09-16 five-minute block. All other isolated exact-count dates have irregular raw gaps and require no interpolation.
- After that completion, usable coverage excluding quarantined 7610 was 229 complete symbols: 166,483 partitions, 166,385 `READY`, 98 expected `EMPTY`, zero `INVALID`, and 34,147,925 bars.
- Re-ranking the sealed market-value/current-industry snapshots selected established unused symbols 3532 (`半導體業`), 6670 (`運動休閒`), 2211 (`鋼鐵工業`), 2498 (`通信網路業`), 5371 (`光電業`), 3010 (`電子通路業`), 1215 (`食品工業`), and 2903 (`貿易百貨`) across eight distinct industries. Official TWSE/TPEx listing dates all predate the frozen 2023-08-19 start.
- Deterministic job `finmind-sponsor-5631808b9766f955` was created without provider access. Its official preflight reported 4,257/6,000 used and exactly 1,743 remaining requests; all 1,743 were spent without a quota-error probe as one calendar plus 1,742 KBar calls.
- The partial job completes 1215 at 727 `READY` and 97,163 bars, completes 2211 at 727 `READY` and 117,992 bars, and checkpoints 288 `READY` dates of 2498 through 2024-10-25 with 68,447 bars. It has zero `EMPTY`/`INVALID`, 283,602 bars, and exact next pending `2498 / 2024-10-28`.
- Offline audit verified all 1,742 partial partitions with zero issues; SQLite `quick_check` is `ok`. TWSE returns no disposition rows for 1215, while its isolated 53-/54-bar dates have irregular 1--30-minute raw gaps, so they are natural sparse sessions rather than fixed provider downsampling.
- Aggregate usable coverage excluding 7610 is now 231 complete symbols plus partial 2498: 168,225 partitions, 168,127 `READY`, 98 expected `EMPTY`, zero `INVALID`, and 34,431,527 canonical bars.
- Preserved `execution_enabled=false`, all unrelated worktree changes, and every order/account/broker/commit/push boundary.
