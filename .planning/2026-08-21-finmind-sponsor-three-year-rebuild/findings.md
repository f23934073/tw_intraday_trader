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

## 2026-08-25 Fresh-Window Completion

- Official usage preflight returned a fresh 0/6,000 window. Job `finmind-sponsor-5631808b9766f955` resumed exactly at `2498 / 2024-10-28`, spent 4,074 KBar requests, and completed all 4,074 remaining symbol-days without repeating its calendar or first 1,742 checkpoints.
- Final state is `COMPLETED`: 5,815 `READY`, one `6670 / 2025-03-11` `EMPTY`, zero `INVALID`, 1,002,981 bars, and no next pending. Full offline audit verified all 5,816 raw/canonical partitions with zero issues; SQLite `quick_check` is `ok`.
- Per-symbol bars are 1215 97,163; 2211 117,992; 2498 176,286; 2903 137,128; 3010 113,339; 3532 111,658; 5371 166,763; and 6670 82,652 across 726 `READY` plus one `EMPTY`.
- Aggregate usable coverage excluding quarantined 7610 is 237 complete symbols: 172,299 partitions, 172,200 `READY`, 99 `EMPTY`, zero `INVALID`, and 35,150,906 bars.
- The sole new `EMPTY` and all true fixed-grid intervals remain pending official exchange reconciliation before the phase is closed. No timeout, auth, provider, quota-error probe, or data-quality stop occurred.
- TWSE's official 2025-03-10 announcement states that 6670 was suspended beginning 2025-03-11 pending material information, exactly matching the job's sole `EMPTY` date.
- TWSE's official disposition response records 3532 at approximately five-minute matching on 2026-04-16--04-29 and approximately twenty-minute matching on 2026-05-11--05-22, 2026-05-29--06-11, 2026-06-22--07-03, and 2026-07-31--08-13. Every consecutive stored 54-/15-/14-bar block falls inside those periods.
- TWSE returns zero disposition rows for 3010 and 6670 over the frozen interval; their isolated exact-count dates therefore require irregular raw-gap confirmation rather than disposition classification.
- Raw timestamp inspection confirms all isolated exact-count dates outside 3532's official periods are natural sparse sessions: 3010 gaps vary 1--24 minutes, isolated 3532 dates vary 1--34 minutes, and 6670 dates vary 1--76 minutes. None forms a fixed five-/twenty-minute full-session grid.
- TWSE daily evidence shows 6670 trading normally again on 2025-03-12, so the one-day `EMPTY` is fully reconciled as an expected material-information suspension. No partition needs repair, interpolation, or re-request.
- After excluding 237 complete symbols and higher-ranked recent listings, the next sealed-snapshot distinct-industry tranche is 2548 (`建材營造`), 8033 (`其他`), 5234 (`光電業`), 1434 (`紡織纖維`), 1314 (`塑膠工業`), 1609 (`電器電纜`), 2897 (`金融保險`), and 1904 (`造紙工業`).
- TWSE OpenAPI lists all eight before 2023-08-19: 2548 (2002-08-26), 8033 (2007-06-21), 5234 (2012-07-16), 1434 (1985-12-24), 1314 (1991-07-12), 1609 (1988-12-12), 2897 (2017-05-05), and 1904 (1971-09-10).
- Deterministic job `finmind-sponsor-9ab5c7b3040ee001` was created in status-only mode with zero provider requests.

## 2026-08-25 Remaining-Allowance Spend and Audit

- Official preflight for job `finmind-sponsor-9ab5c7b3040ee001` reported 4,074/6,000 used and exactly 1,926 remaining. The downloader spent all 1,926 successful requests as one new calendar plus 1,925 checkpointed KBar symbol-days, with no quota-error probe, timeout, auth, provider, or data-quality failure.
- The paused job has 1,924 `READY`, one expected `EMPTY`, zero `INVALID`, 405,504 bars, 3,891 remaining symbol-days, and exact next pending `1609 / 2025-07-30`. It completes 1314 at 726 `READY` plus one `EMPTY` and 177,767 bars, completes 1434 at 727 `READY` and 113,973 bars, and checkpoints 471 `READY` dates of 1609 through 2025-07-29 with 113,764 bars.
- Offline audit verified all 1,925 raw and canonical partitions and digests with zero issues. SQLite `quick_check` is `ok`; the request ledger is one `CALENDAR READY`, 1,924 `KBAR READY`, and one `KBAR EMPTY`.
- TWSE's official daily record reports zero shares, zero value, zero trades, and no OHLC for `1314 / 2026-04-08`, followed by normal trading on 2026-04-09. The `EMPTY` partition is therefore expected and requires no re-request.
- There are no exact 14/15/53/54-row observations in this partial job. TWSE returns no disposition rows for 1434, and its only <=60-row dates have irregular raw gaps: 48 bars with 1--33-minute gaps on 2023-10-06, 57 bars with 1--26-minute gaps on 2023-11-01, and 60 bars with 1--22-minute gaps on 2024-12-26. These are natural sparse sessions, not fixed provider grids.
- Aggregate usable coverage excluding quarantined 7610 is now 239 complete symbols plus partial 1609: 174,224 partitions, 174,124 `READY`, 100 expected `EMPTY`, zero `INVALID`, and 35,556,410 bars. The physical store additionally retains two quarantined 7610 partitions, including one `INVALID`.

## 2026-08-25 Checkpoint-Safe 918-Request Resume

- Live SQLite preserved exact next pending `1609 / 2025-07-30`. Official preflight then reported 5,082/6,000 used and exactly 918 remaining; all 918 positive requests were spent as checkpointed KBar symbol-days without re-requesting the sealed calendar or any prior partition.
- Every new response was `READY`, adding 918 partitions and 149,857 bars. The batch completed the remaining 256 dates of 1609 and checkpointed 662 dates of 1904 through 2026-05-15; exact next pending is `1904 / 2026-05-18`.
- Current job state is 2,842 `READY`, one expected `EMPTY`, zero `INVALID`, 555,361 bars, and 2,973 remaining symbol-days. Completed job symbols are 1314, 1434, and 1609; 1904 is partial at 662/727 `READY` and 87,726 bars.
- Full offline audit verified 2,843/2,843 raw/canonical partitions and digests with zero issues. The ledger is one `CALENDAR READY`, 2,842 `KBAR READY`, and one `KBAR EMPTY`; SQLite `quick_check` is `ok`.
- The job still has no exact 14/15/53/54-row observations. TWSE returns zero disposition records for 1904 in the frozen interval; its two <=60-row dates are natural sparse sessions with irregular raw timing: 56 bars and 1--24-minute gaps on 2025-04-28, and 52 bars with 1--26-minute gaps on 2025-07-09.
- Aggregate usable coverage excluding quarantined 7610 is now 240 complete symbols plus partial 1904: 175,142 partitions, 175,042 `READY`, 100 expected `EMPTY`, zero `INVALID`, and 35,706,267 bars.

## 2026-08-25 Official-Preflight Continuous Continuation

- Source review found that the existing CLI switched from official usage checks to direct data-endpoint quota probes after its first continuous batch. The narrow correction removes that switch: every batch now uses `FinMindApiClient.usage()`, zero allowance waits and polls usage only, and the focused safety regression passes (`13 passed`; Ruff and diff checks clean).
- Live SQLite reconfirmed exact next pending `1904 / 2026-05-18`. The corrected process received a fresh official 0/6,000 preflight and spent 2,973 KBar requests to complete job `finmind-sponsor-9ab5c7b3040ee001` without repeating its calendar or 2,843 prior checkpoints.
- The completed job has 5,815 `READY`, one expected 1314 `EMPTY`, zero `INVALID`, 1,055,449 bars, and no next pending. Offline audit verified 5,816/5,816 partitions with zero issues; SQLite `quick_check` is `ok`.
- TWSE official disposition data reconciles 5234's 2024-09-23--10-08 five-minute block and all fourteen 8033 five-/twenty-minute periods. Isolated 2548 and 2849-style exact counts remain subject to raw-gap inspection rather than row-count-only classification.
- After excluding 245 complete symbols and recent/mixed-market candidates, selected established distinct-industry symbols 1227, 1808, 2023, 2101, 2393, 2849, 6561, and 9907. Official TWSE/ISIN dates range from 1963 through 2018 and all predate the frozen start.
- Job `finmind-sponsor-903cd4725564e012` completed across official-positive rolling batches at 5,802 `READY`, fourteen `EMPTY`, zero `INVALID`, 761,026 bars, and no next pending. Audit verified all 5,816 partitions with zero issues; SQLite `quick_check` is `ok`.
- The fourteen `EMPTY` partitions are two exact capital-reduction share-exchange stops: 1808 from 2025-11-13 through 2025-11-21 with trading resuming 2025-11-24, and 2101 from 2025-09-04 through 2025-09-12 with trading resuming 2025-09-15. No re-request or repair is required.
- Raw timestamp inspection covered all 88 exact 14/15/53/54-row partitions in this job: none has a uniform five- or twenty-minute grid. The 1808/2101 observations and the low-liquidity 2849/6561 observations all have irregular gaps, so they are natural sparse trading rather than disposition downsampling and need no interpolation or re-request.
- Selected the next established distinct-industry tranche 1232, 1608, 2103, 2501, 3033, 3576, 5388, and 9958; official TWSE listing dates range from 1967 through 2009 and all cover the frozen interval.
- Continuous job `finmind-sponsor-613c0e5e393c6f98` completed with 5,816 `READY`, zero `EMPTY`/`INVALID`, 1,004,519 bars, and no next pending. Offline audit verified 5,816/5,816 raw/canonical partitions with zero issues; SQLite `quick_check` is `ok`.
- Per-symbol bar totals are 1232 22,848; 1608 144,139; 2103 102,962; 2501 122,003; 3033 145,732; 3576 153,569; 5388 160,317; and 9958 152,949. TWSE officially records 3576 under approximately five-minute matching from 2026-03-04 through 2026-03-17, exactly reconciling its consecutive 53-/54-row block including missing-trade gaps. The other 65 exact-count observations across 1232, 2103, 2501, and 9958 have irregular raw gaps and no official disposition rows.
- After excluding 261 complete symbols and recent listings, selected the next established distinct-industry tranche 1231, 1440, 2014, 2439, 2727, 2836, 2905, and 5534. TWSE official listing dates range from 1988 through 2012, all before the frozen 2023-08-19 start.
- New deterministic job `finmind-sponsor-92b76345b3c5e396` sealed one 727-date calendar and is continuously consuming only official-positive rolling releases. It completed all 727 dates of 1231 and advanced into 1440 without any `EMPTY`, `INVALID`, transport, auth, or data-quality error; live SQLite remains the checkpoint authority while it runs.
- Job `finmind-sponsor-92b76345b3c5e396` subsequently completed at 5,815 `READY`, one expected `2905 / 2025-11-05` `EMPTY`, zero `INVALID`, 803,879 bars, and no next pending. Full offline audit verified 5,816/5,816 partitions with zero issues; SQLite `quick_check` is `ok`.
- TWSE official evidence identifies the sole EMPTY as a one-day suspension for pending material information, with trading resuming 2025-11-06. All 42 exact 14/15/53/54-row observations in the completed job have irregular one-minute-origin raw gaps; TWSE reports no disposition periods for the affected symbols, so no repair or interpolation is required.
- Aggregate usable coverage excluding quarantined 7610 reached 269 complete symbols: 195,563 partitions, 195,448 `READY`, 115 expected `EMPTY`, zero `INVALID`, and 38,775,779 canonical bars. Across the four jobs continued or created in this phase, 20,424 new successful provider responses checkpointed 20,406 `READY` plus fifteen expected `EMPTY` symbol-days and added 3,069,512 bars.
- After dynamically excluding all 269 complete symbols and recent listings, selected established distinct-industry symbols 1419, 2535, 2820, 3029, 3362, 5009, 5530, and 9911. Official TWSE/TPEx dates range from 1977 through 2005 and all predate the frozen start; recent 6739 was explicitly excluded.
- Live job `finmind-sponsor-19a1bd13b0ec5d2d` sealed one calendar and remains attached under official-positive-only continuous polling. A live snapshot found 2,727 `READY`, seven expected 2535 capital-reduction `EMPTY`, zero `INVALID`, and exact next pending `3029 / 2025-11-27`; the writer advanced further while a 2,753-partition offline audit completed with zero issues.
- The seven 2535 EMPTY dates are the exact 2023-10-19--10-27 trading-day block during its official cash-capital-reduction share replacement; new shares resumed trading on 2023-10-30. No re-request is required.
- Job `finmind-sponsor-19a1bd13b0ec5d2d` completed with 5,808 `READY`, eight expected `EMPTY`, zero `INVALID`, 720,511 bars, and a 5,816/5,816 zero-issue audit. The additional `5009 / 2023-12-21` `EMPTY` is its official one-day material-information suspension.
- TWSE confirms 1419's 2025-05-26--06-09 approximately five-minute disposition. TPEx confirms all four 3362 fixed-grid blocks, including twenty-minute matching in 2023, two five-minute periods in 2023/2024, and the 2026 period whose matching interval changed under the new rule. All other exact-count dates are naturally irregular.
- The next established eight-industry job `finmind-sponsor-63d57c95485b7225` completed with 5,810 `READY`, six expected `EMPTY`, zero `INVALID`, 774,492 bars, and a 5,816/5,816 zero-issue audit. SQLite `quick_check` is `ok`.
- All six 9937 `EMPTY` dates reconcile to TWSE daily rows with small odd-lot share/trade counts but `--` for open, high, low, and close; FinMind's regular-session KBar therefore correctly contains no row. They require no re-request.
- All 108 exact 14/15/53/54-row observations across 1104, 2704, 5864, and 9937 have irregular raw timestamp gaps. The two sparse 9937 observations without a one-minute gap still vary across non-grid intervals such as 5, 6, 7, 18, 31, and 42 minutes. Official TWSE/TPEx responses contain zero disposition periods for all four symbols.
- Aggregate usable coverage excluding quarantined 7610 is now 285 complete symbols, 207,195 partitions, 207,066 `READY`, 129 expected `EMPTY`, zero `INVALID`, and 40,270,782 bars.
- The next established distinct-industry set is 6456 (`光電業`), 6177 (`建材營造`), 2480 (`資訊服務業`), 3234 (`通信網路業`), 5284 (`其他`), 2106 (`橡膠工業`), 5007 (`鋼鐵工業`), and 8096 (`電子通路業`). Official listing dates range from 1990-12-20 through 2017-03-09, establishing full frozen-window eligibility.
- New job `finmind-sponsor-bea0aa382a988bb0` sealed one calendar; the last live snapshot has 295 `READY`, zero `EMPTY`/`INVALID`, and exact next pending `2106 / 2024-11-07`. The first 200 partitions passed a 200/200 zero-issue partial audit with 21,171 bars, and the continuous writer is polling official usage only.

## 2026-08-25 18:02 Live Heartbeat Reconciliation

- Live SQLite proves stale job `finmind-sponsor-ffbf4a85539d9edc` is `COMPLETED` at 5,809 `READY`, seven expected `EMPTY`, zero `INVALID`, and 1,250,046 bars; it must not be resumed from the obsolete 1785 checkpoint.
- Unified writer session 65623 remains active and continues official-usage-only acquisition for `finmind-sponsor-bea0aa382a988bb0`; no second writer was started.
- A durable live snapshot reached 1,053/5,816 checkpoints, all `READY`, with exact next pending `2480 / 2024-12-20`; 2106 is complete and 2480 is partial.
- An offline audit snapshot verified 1,040/1,040 partitions and 89,876 bars with zero issues. SQLite `quick_check` is `ok`; the writer advanced another thirteen checkpoints while the audit/report was prepared.
- Aggregate usable coverage at the audited snapshot, excluding quarantined 7610, is 286 complete symbols plus one partial symbol: 208,235 partitions, 208,106 `READY`, 129 expected `EMPTY`, zero `INVALID`, and 40,360,658 bars.
- The partial job currently has no `EMPTY` or `INVALID`. Its 14/15/53/54-row observations are retained source-faithfully for official disposition/raw-gap classification after the deterministic job completes; no interpolation or repair was performed.
- The existing `finmind` automation was updated through the app manager and read back successfully. Its next heartbeat is scheduled for 19:02 Asia/Taipei and now targets only the live `bea0aa382a988bb0` job/checkpoint, with explicit single-writer protection.
- Final heartbeat handoff snapshot: the same writer is `RUNNING` at 1,446/5,816 `READY`, zero `EMPTY`/`INVALID`, exact next pending `2480 / 2026-08-07`, and 4,370 remaining symbol-days. A later 1,389/1,389 offline audit verified 119,188 bars with zero issues before the writer advanced again.

## 2026-08-25 19:02 Completion, Reconciliation, and Next Tranche

- Unified session 65623 exited normally after completing `finmind-sponsor-bea0aa382a988bb0`: one calendar plus 5,816 KBar responses, 5,814 `READY`, two `EMPTY`, zero `INVALID`, 755,369 bars, and no next pending.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues; SQLite `quick_check` is `ok`.
- The two `EMPTY` partitions are `5007 / 2023-08-25` and `5007 / 2023-11-07`. TWSE official daily rows report 108 shares/3 trades and 64 shares/6 trades respectively, but `--` for open, high, low, and close. They are expected no-regular-OHLC sessions, not missing provider data.
- Raw-gap classification inspected all 218 exact 14/15/53/54-row partitions: 133 are irregular natural sparse sessions, 72 are five-minute grids, and 13 are twenty-minute grids.
- TPEx official disposition data reconciles all true 3234 grids to four five-minute periods: 2024-05-03--05-16, 2024-10-14--10-25, 2026-02-26--03-12, and 2026-04-15--04-28.
- TWSE official disposition data reconciles 5284's 2024-02-23--03-08 and 6456's 2026-04-21--05-05 five-minute periods.
- TPEx official disposition data reconciles 8096's five-minute periods on 2025-02-10--02-21, 2026-02-03--02-25, and 2026-06-24--07-07 plus twenty-minute periods on 2025-02-14--02-27 and 2026-07-16--07-29. Overlapping dates correctly follow the stricter effective interval.
- Aggregate usable coverage excluding quarantined 7610 is now 293 complete symbols, zero partial symbols, 213,011 partitions, 212,880 `READY`, 131 expected `EMPTY`, zero `INVALID`, and 41,026,151 bars.
- The next established distinct-industry tranche is 1313 (`塑膠工業`), 2374 (`光電業`), 2543 (`建材營造`), 2832 (`金融保險`), 3028 (`電子通路業`), 4906 (`通信網路業`), 5478 (`文化創意業`), and 9925 (`其他`).
- Official listing dates are 1989-03-27, 1995-01-16, 1999-10-15, 1997-09-30, 2002-08-26, 2003-06-30, 2001-03-29, and 1995-12-09 respectively; all cover the frozen 2023-08-19 start.
- Status-only creation of `finmind-sponsor-4b3f3a6045f8fa25` made zero provider requests. The single live writer then sealed a 727-session calendar from an official 1,295-request positive preflight and advanced to 132 `READY`, zero `EMPTY`/`INVALID`, 16,365 bars, and exact next pending `1313 / 2024-03-08`.
- Partial audit verified 132/132 partitions with zero issues. The existing automation was updated and read back for a 20:02 Asia/Taipei single-writer checkpoint review.
- Final heartbeat snapshot advanced to 238/5,816 `READY`, zero `EMPTY`/`INVALID`, 32,141 bars, exact next pending `1313 / 2024-08-13`, and a 238/238 zero-issue audit while session 36269 remained active.

## 2026-08-25 20:02 Completion, Reconciliation, and Next Writer

- Unified session 36269 exited normally after completing deterministic job `finmind-sponsor-4b3f3a6045f8fa25`. The complete job has 5,808 `READY`, eight expected `EMPTY`, zero `INVALID`, 816,694 canonical bars, and no next pending; its request ledger contains one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. SQLite `quick_check` is `ok`.
- Seven `2832` EMPTY dates span 2025-10-22 through 2025-10-31. TWSE's official reduction report records a cash-return capital reduction and 2025-11-03 resumption, exactly accounting for the stopped sessions. `5478 / 2023-12-21` matches TPEx's official monthly row with zero volume, zero trades, and `--` for every OHLC field. No re-request or repair is required.
- Raw timestamp inspection classified all 114 exact 14/15/53/54-row partitions: 79 irregular natural sparse sessions, 25 five-minute grids, and ten twenty-minute grids. TWSE officially reconciles all twelve 2374 five-minute sessions on 2024-05-23--06-07 and all ten 2543 five-minute sessions on 2023-11-21--12-04. TPEx officially reconciles 5478's three five-minute sessions on 2023-12-04--12-06 and ten twenty-minute sessions on 2023-12-07--12-20.
- Per-symbol results are 1313 727 READY / 113,095 bars; 2374 727 / 167,352; 2543 727 / 153,100; 2832 720 READY plus seven EMPTY / 50,484; 3028 727 / 92,087; 4906 727 / 157,737; 5478 726 READY plus one EMPTY / 45,808; and 9925 727 / 37,031.
- Aggregate usable coverage excluding quarantined 7610 is now 301 complete symbols and zero partial symbols: 218,827 partitions, 218,688 `READY`, 139 expected `EMPTY`, zero `INVALID`, and 41,842,845 bars.
- The next sealed-snapshot distinct-industry leaders are 2426 (`光電業`), 2515 (`建材營造`), 6024 (`金融保險`), 9940 (`其他`), 3048 (`電子通路業`), 9908 (`油電燃氣業`), 1905 (`造紙工業`), and 3380 (`通信網路業`). Their official TWSE listing dates range from 1975-02-07 through 2017-10-16 and all predate the frozen start.
- New deterministic job `finmind-sponsor-92f5d638b5e2a786` sealed one 727-date calendar and is the only attached writer. It consumes only official-positive usage releases with checkpoint-first writes; a live 283/5,816 partition snapshot passed a 283/283 zero-issue partial audit with 55,005 bars and no `EMPTY` or `INVALID` while acquisition continued.
- The existing `finmind` heartbeat was updated through the app manager and read back successfully. Its next one-shot run is 21:02 Asia/Taipei and now targets only the new job with explicit single-writer, positive-preflight, 60-second timeout-backoff, and no-trading boundaries.
- Final durable handoff snapshot reached 581/5,816 `READY`, zero `EMPTY`/`INVALID`, 92,590 bars, and exact next pending `1905 / 2026-01-08`. The same attached writer had just received a 5,462-request official-positive batch and remained active; it must not be duplicated.

## 2026-08-25 21:02 Completion, Grid Reconciliation, and Next Writer

- Unified session 3882 exited normally after completing deterministic job `finmind-sponsor-92f5d638b5e2a786`. The final job contains 5,816 `READY`, zero `EMPTY`, zero `INVALID`, 778,262 bars, and no next pending; the completing batch used 5,279 positive-preflight requests.
- Full offline audit verified 5,816/5,816 raw and canonical partitions with zero issues. The verified event range is 2023-08-21 09:01 through 2026-08-18 13:30 Asia/Taipei, and SQLite `quick_check` is `ok`.
- Raw timestamp inspection found 159 exact 14/15/53/54-row observations: 107 irregular natural sparse sessions, 33 five-minute grids, and 19 twenty-minute grids. TWSE officially reconciles 1905's ten-session 2026-04-02--04-17 five-minute period, 2515's 2025-11-05--11-18 five-minute period, 3048's 2025-09-02--09-15 five-minute period, and all of 2426's consecutive 2026 five-/twenty-minute disposition periods. No interpolation or repair is required.
- Aggregate usable coverage excluding quarantined 7610 is now 309 complete symbols: 224,643 partitions, 224,504 `READY`, 139 expected `EMPTY`, zero `INVALID`, and 42,621,107 bars.
- Industry-coverage ranking plus market value selected 1304 (`塑膠工業`), 1909 (`造紙工業`), 2108 (`橡膠工業`), 2731 (`觀光餐旅`), 3551 (`綠能環保類`), 6016 (`金融業`), 6183 (`資訊服務業`), and 8908 (`油電燃氣業`). Sealed official TWSE/TPEx company data gives listing dates from 1972-05-20 through 2013-09-24, all before the frozen start; recent 1623/4441 and mixed-market 7610 remain excluded.
- New deterministic job `finmind-sponsor-02b4a95947f469ef` is the only attached writer. Its first official usage preflight released 183 requests, followed by a further positive release of 106; it checkpoints every symbol-day before continuing and has shown no transport, auth, provider, quota, or data-quality error.
- The existing `finmind` heartbeat was updated through the Codex app manager and read back. Its next one-shot run is 22:02 Asia/Taipei and protects the current job, single-writer rule, positive-usage-only policy, and all no-trading boundaries.

## 2026-08-25 22:02 Completion, Official EMPTY Reconciliation, and Next Writer

- Unified session 38949 remained the only writer and exited normally after completing deterministic job `finmind-sponsor-02b4a95947f469ef`. The job has 5,813 `READY`, three expected `EMPTY`, zero `INVALID`, 640,877 bars, and no next pending; its request ledger contains one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. The event range is 2023-08-21 09:01 through 2026-08-18 13:30 Asia/Taipei, and SQLite `quick_check` is `ok`.
- Official TWSE daily data reports `1909 / 2026-08-12` at zero shares, zero value, zero trades, and no OHLC. Official TPEx monthly tables report `8908 / 2025-07-29` and `2025-10-02` with only one and two lots respectively but `--` for open, high, low, and close. All three `EMPTY` checkpoints are expected no-regular-OHLC observations; no re-request is needed.
- Raw timestamp inspection classified all 165 exact 14/15/53/54-row partitions as irregular natural sparse sessions. There is no five- or twenty-minute fixed grid in this job, so no disposition repair or interpolation is needed.
- Per-symbol results are 1304 727 READY / 125,260 bars; 1909 726 READY plus one EMPTY / 105,750; 2108 727 / 73,450; 2731 727 / 113,210; 3551 727 / 99,991; 6016 727 / 93,562; 6183 727 / 12,756; and 8908 725 READY plus two EMPTY / 16,898.
- Aggregate usable coverage excluding quarantined 7610 is now 317 complete symbols: 230,459 partitions, 230,317 `READY`, 142 expected `EMPTY`, zero `INVALID`, and 43,261,984 bars.
- Industry-coverage ranking plus market value selected 1103 (`水泥工業`), 1810 (`玻璃陶瓷`), 1903 (`造紙工業`), 2753 (`觀光餐旅`), 6021 (`金融業`), 6231 (`資訊服務業`), 8390 (`綠能環保類`), and 9924 (`居家生活`). Sealed official TWSE/TPEx company records give listing dates from 1963-12-09 through 2021-09-09, all before the frozen start.
- New deterministic job `finmind-sponsor-a8934cc8956881c4` is the only attached writer. Its first official usage preflight released 183 requests; it checkpoints each symbol-day before continuing and showed no transport, auth, provider, quota, or data-quality error during the live partial audit.
- The existing `finmind` heartbeat was updated through the Codex app manager and read back. Its next one-shot run is 23:02 Asia/Taipei and protects the current job, single-writer rule, positive-usage-only policy, and all no-trading boundaries.

## 2026-08-25 23:02 Completion, Official Reconciliation, and Next Writer

- Unified session 27519 exited normally after completing deterministic job `finmind-sponsor-a8934cc8956881c4`. Final states are 5,803 `READY`, thirteen expected `EMPTY`, zero `INVALID`, 544,495 bars, and no next pending; its request ledger contains one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. The event range is 2023-08-21 09:01 through 2026-08-18 13:30 Asia/Taipei, and SQLite `quick_check` is `ok`.
- TPEx official monthly daily-close tables reconcile all seven 6021 `EMPTY` sessions to rows without regular OHLC. Six have zero volume; `2025-09-26` also has no OHLC despite the provider's non-price activity fields. No re-request is required.
- The six 9924 `EMPTY` dates from 2025-09-25 through 2025-10-03 exactly match its disclosed cash-capital-reduction share-exchange trading stop; replacement shares resumed trading on 2025-10-07. TWSE's official daily tables contain no stock rows during the stop.
- Raw timestamp inspection classified all 178 exact 14/15/53/54-row observations: 147 irregular natural sparse sessions, 24 five-minute grids, and seven twenty-minute grids. All true grids belong to 6231 and exactly match TPEx's official 2023-12-29--2024-01-16, 2024-05-31--06-14, 2024-07-11--07-24, and 2024-09-16--09-30 disposition periods.
- Per-symbol results are 1103 727 READY / 41,847 bars; 1810 727 / 101,566; 1903 727 / 52,632; 2753 727 / 52,493; 6021 720 READY plus seven EMPTY / 23,522; 6231 727 / 113,931; 8390 727 / 103,970; and 9924 721 READY plus six EMPTY / 54,534.
- Aggregate usable coverage excluding quarantined 7610 is now 325 complete symbols: 236,275 partitions, 236,120 `READY`, 155 expected `EMPTY`, zero `INVALID`, and 43,806,479 bars.
- Industry-coverage ranking selected 8924 (`運動休閒類`), 6508 (`農業科技業`), 3086 (`文化創意業`), 1809 (`玻璃陶瓷`), 6629 (`居家生活類`), 2908 (`貿易百貨`), 2104 (`橡膠工業`), and 9926 (`油電燃氣業`). Sealed official TWSE/TPEx company tables give listing dates from 1986-07-15 through 2019-06-06, all before the frozen start.
- New deterministic job `finmind-sponsor-1ef906d2ec154185` sealed one 727-session calendar and is the only attached writer. It consumes only official-positive releases and had 195 `READY`, zero `EMPTY`/`INVALID`, 26,293 bars, and exact next pending `1809 / 2024-06-11` at the audited snapshot.
- Partial offline audit verified 195/195 partitions with zero issues and SQLite `quick_check=ok`. The existing `finmind` heartbeat was updated and read back for 00:02 Asia/Taipei with explicit single-writer, positive-preflight, timeout-backoff, and no-trading boundaries.

## 2026-08-26 00:02 Provider-Safe Pause and Audited Checkpoint

- Unified session 4350 remained the sole writer and advanced deterministic job `finmind-sponsor-1ef906d2ec154185` to 1,805 durable `READY` partitions, zero `EMPTY`, zero `INVALID`, and 214,829 bars before one FinMind HTTP 502 response. The downloader classified the stop as `PROVIDER`, persisted job status `PAUSED`, and exited without retrying the same provider error.
- Exact live authority is `2908 / 2025-02-05` with 4,011 symbol-days remaining. 1809 and 2104 are complete at 727/727 dates; 2908 is partial at 351 dates through 2025-02-04; 3086, 6508, 6629, 8924, and 9926 have not started. Since the preceding handoff, 1,430 KBar requests completed and one additional KBar attempt received HTTP 502; the total job ledger is one calendar plus 1,806 KBar attempts.
- Offline audit verified 1,805/1,805 raw/canonical partitions and all 214,829 bars with zero issues. SQLite `quick_check` is `ok`, and no checkpointed date was requested again.
- Raw inspection found 41 exact 14/15/53/54-row observations: 21 irregular natural sparse sessions, thirteen five-minute grids, and seven twenty-minute grids. Every true grid belongs to 1809.
- TWSE's official `/announcement/punish` response records 1809 at approximately five-minute matching from 2024-02-26, approximately twenty-minute matching from 2024-03-01, and approximately five-minute matching from 2026-05-13 through 2026-05-26. These periods exactly reconcile all thirteen stored five-minute and seven stored twenty-minute sessions; no interpolation, repair, or re-request is needed.
- Complete usable coverage outside quarantined 7610 is now 327 symbols, 237,729 partitions, 237,574 `READY`, 155 expected `EMPTY`, zero `INVALID`, and 44,011,578 bars. This includes newly completed 1809 and 2104; 2908 remains partial and is excluded from the complete-symbol aggregate.
- The existing `finmind` heartbeat was updated for 01:02 Asia/Taipei. It requires proving that no writer is active, then may resume only this deterministic job after the full cooldown from live SQLite, using official positive usage preflight and the same no-trading boundaries.

## 2026-08-26 01:15 Completion, Official Reconciliation, and Next Writer

- Session 4350 was no longer attached and live SQLite remained exactly at 1,805 `READY`, zero `EMPTY`/`INVALID`, 214,829 bars, and `2908 / 2025-02-05`. After more than the full 60-second cooldown, the same deterministic command resumed without re-requesting the sealed calendar or any checkpointed symbol-day.
- The resumed batch used exactly 4,011 successful KBar requests and completed job `finmind-sponsor-1ef906d2ec154185`. Final states are 5,750 `READY`, 66 expected `EMPTY`, zero `INVALID`, 346,358 bars, and no next pending; the attempt ledger contains one calendar plus 5,817 KBar attempts, including the earlier single HTTP 502 failure.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. SQLite `quick_check` is `ok`.
- Per-symbol results are 1809 727 READY / 104,654 bars; 2104 727 / 100,445; 2908 727 / 24,245; 3086 720 READY plus seven EMPTY / 49,385; 6508 727 / 16,684; 6629 715 READY plus twelve EMPTY / 16,225; 8924 727 / 28,348; and 9926 680 READY plus 47 EMPTY / 6,372.
- TPEx's official share-conversion notice exactly explains 3086's seven-date 2026-04-09--04-17 trading stop. TPEx monthly official daily tables show all twelve 6629 dates with no OHLC. TWSE monthly official daily tables show all 47 9926 dates with OHLC `--`; four have zero shares and 43 have only non-price activity. All 66 EMPTY partitions are therefore expected and require no retry.
- Raw timestamp inspection classified 237 exact 14/15/53/54-row observations: 216 irregular natural sparse sessions, fourteen five-minute grids, and seven twenty-minute grids. The twenty 1809 grids were already reconciled to TWSE disposition periods; the remaining five-minute grid at `3086 / 2024-01-11` exactly matches TPEx's official 2024-01-11--01-24 five-minute disposition period. No repair or interpolation is required.
- Aggregate usable coverage excluding quarantined 7610 is now 333 complete symbols, 242,091 partitions, 241,870 `READY`, 221 expected `EMPTY`, zero `INVALID`, and 44,152,837 bars.
- Industry-coverage ranking selected 6578 (`農業科技業`), 6180 (`文化創意業`), 8482 (`居家生活`), 1110 (`水泥工業`), 6015 (`金融業`), 2723 (`觀光餐旅`), 6790 (`造紙工業`), and 3147 (`資訊服務業`). Sealed official company snapshots list all eight between 1994-10-22 and 2021-09-29, before the frozen start.
- Deterministic job `finmind-sponsor-a94adbad11a795af` was created in status-only mode with zero provider requests. Sole writer session 29235 received an official-positive allowance of 1,989 requests, sealed one calendar, and remains `RUNNING`.
- The latest bounded audit verified 431/431 partitions and 24,726 bars with zero issues while acquisition continued. A preceding status-only boundary was 420 `READY`, zero `EMPTY`/`INVALID`, exact next pending `1110 / 2025-05-19`; SQLite `quick_check` remained `ok`.
- The final handoff status advanced to 727 `READY`, zero `EMPTY`/`INVALID`, 1110 complete, exact next pending `2723 / 2023-08-21`, and 5,089 symbol-days remaining. Session 29235 remained attached and healthy.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 03:15 Asia/Taipei with explicit protection for job `finmind-sponsor-a94adbad11a795af`, session 29235, official-positive preflight, timeout backoff, and all no-trading boundaries.

## 2026-08-26 03:23 Completion, Official Reconciliation, and Next Writer

- Session 29235 remained the only writer. After consuming the rest of the initial release, two small releases of eight and three requests, and a later official-positive batch of 4,000, it completed deterministic job `finmind-sponsor-a94adbad11a795af` without re-requesting the sealed calendar or any checkpointed symbol-day.
- Since the previous 727-partition handoff, exactly 5,089 KBar responses were checkpointed. Final job state is 5,766 `READY`, 50 expected `EMPTY`, zero `INVALID`, 453,741 bars, no next pending, and one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. SQLite `quick_check` is `ok`.
- Per-symbol results are 1110 727 READY / 37,125 bars; 2723 727 / 66,717; 3147 727 / 89,097; 6015 727 / 67,461; 6180 727 / 97,945; 6578 727 / 41,711; 6790 727 / 42,907; and 8482 677 READY plus 50 EMPTY / 10,778.
- TWSE official `STOCK_DAY` rows reconcile every 8482 EMPTY date from 2023-08-30 through 2026-08-05: all 50 have `--` for open, high, low, and close; 25 have zero shares and 25 contain only non-price activity. No re-request or repair is required.
- Raw timestamp inspection classified all 170 exact 14/15/53/54-row observations: 141 irregular natural sparse sessions, thirteen five-minute grids, and sixteen twenty-minute grids. Every true grid belongs to 3147. TPEx officially records five-minute matching on 2025-04-29--05-15 and 2026-06-08--06-22, plus overlapping stricter twenty-minute matching on 2026-06-11--06-25 and 2026-07-06--07-17; these periods exactly explain every grid.
- Aggregate usable coverage excluding quarantined 7610 is now 341 complete symbols, 247,907 partitions, 247,636 `READY`, 271 expected `EMPTY`, zero `INVALID`, and 44,606,578 bars.
- The next established low-coverage tranche is 5902 (`居家生活類`), 1806 (`玻璃陶瓷`), 4171 (`農業科技業`), 5263 (`文化創意業`), 2913 (`貿易百貨`), 6026 (`金融業`), 1108 (`水泥工業`), and 4953 (`資訊服務業`). Sealed official listing dates range from 1962-02-09 through 2016-01-27, all before the frozen start.
- Deterministic job `finmind-sponsor-e4f09907ed83d1b4` was created in status-only mode with zero provider requests. Sole writer session 23235 received an official-positive allowance of 2,183 requests, sealed one calendar, and remains `RUNNING`.
- A live partial snapshot has 163 `READY`, zero `EMPTY`/`INVALID`, 14,080 bars, exact next pending `1108 / 2024-04-24`, and 5,653 symbol-days remaining. Partial audit verified 163/163 partitions with zero issues and SQLite `quick_check=ok`.
- The final status-only handoff advanced to 506 `READY`, zero `EMPTY`/`INVALID`, exact next pending `1108 / 2025-09-17`, and 5,310 symbol-days remaining. Session 23235 remained attached and healthy.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 05:48 Asia/Taipei with explicit protection for job `finmind-sponsor-e4f09907ed83d1b4`, session 23235, official-positive preflight, timeout backoff, and all no-trading boundaries.

## 2026-08-26 05:48 Completion, Official Reconciliation, and Next Writer

- Session 23235 remained the only writer and exited normally after completing deterministic job `finmind-sponsor-e4f09907ed83d1b4`. Since the previous 506-partition handoff, exactly 5,310 KBar responses were checkpointed without re-requesting the sealed calendar or any prior symbol-day.
- Final job state is 5,808 `READY`, eight expected `EMPTY`, zero `INVALID`, 479,946 bars, no next pending, and one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. SQLite `quick_check` is `ok`.
- Per-symbol results are 1108 727 READY / 42,944 bars; 1806 727 / 72,832; 2913 727 / 107,961; 4171 727 / 32,404; 4953 727 / 81,916; 5263 726 READY plus one EMPTY / 53,079; 5902 720 READY plus seven EMPTY / 10,852; and 6026 727 / 77,958.
- TPEx official daily-close rows reconcile all eight EMPTY dates: `5263 / 2026-01-21` and seven 5902 dates from 2024-10-16 through 2026-04-27 all have zero volume and no OHLC. No re-request or repair is required.
- Raw timestamp inspection classified 179 exact 14/15/53/54-row observations: 178 irregular natural sparse sessions and one five-minute grid. The sole grid, `4171 / 2025-10-31`, exactly matches TPEx's official 2025-10-31--11-13 five-minute disposition period.
- Aggregate usable coverage excluding quarantined 7610 is now 349 complete symbols, 253,723 partitions, 253,444 `READY`, 279 expected `EMPTY`, zero `INVALID`, and 45,086,524 bars.
- The next established distinct-industry tranche is 9934 (`居家生活`), 1817 (`玻璃陶瓷`), 6101 (`文化創意業`), 2102 (`橡膠工業`), 8917 (`油電燃氣業`), 4419 (`觀光餐旅`), 6020 (`金融業`), and 1109 (`水泥工業`). Sealed official listing dates range from 1979-07-16 through 2013-10-24, all before the frozen start.
- Deterministic job `finmind-sponsor-303a4e6207a3385b` was created in status-only mode with zero provider requests. Sole writer session 54912 received a fresh official-positive allowance of 6,000 requests, sealed one calendar, and remains `RUNNING`.
- A live partial snapshot has 244 `READY`, zero `EMPTY`/`INVALID`, 14,127 bars, exact next pending `1109 / 2024-08-21`, and 5,572 symbol-days remaining. Partial audit verified 244/244 partitions with zero issues and SQLite `quick_check=ok`.
- The final status-only handoff advanced to 451 `READY`, zero `EMPTY`/`INVALID`, exact next pending `1109 / 2025-07-02`, and 5,365 symbol-days remaining. Session 54912 remained attached and healthy.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 06:35 Asia/Taipei with explicit protection for job `finmind-sponsor-303a4e6207a3385b`, session 54912, official-positive preflight, timeout backoff, and all no-trading boundaries.

## 2026-08-26 06:35 Completion, Official Reconciliation, and Next Writer

- Session 54912 remained the only writer and exited normally after completing deterministic job `finmind-sponsor-303a4e6207a3385b`. Since the previous 451-partition handoff, exactly 5,365 KBar responses were checkpointed without re-requesting the sealed calendar or any prior symbol-day.
- Final job state is 5,709 `READY`, 107 expected `EMPTY`, zero `INVALID`, 227,014 bars, no next pending, and one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. The event range is 2023-08-21 09:01 through 2026-08-18 13:30 Asia/Taipei, and SQLite `quick_check` is `ok`.
- Per-symbol results are 1109 727 READY / 29,346 bars; 1817 727 / 23,505; 2102 726 READY plus one EMPTY / 45,254; 4419 703 READY plus 24 EMPTY / 4,984; 6020 726 READY plus one EMPTY / 5,078; 6101 727 / 37,420; 8917 646 READY plus 81 EMPTY / 4,675; and 9934 727 / 76,752.
- Official TWSE/TPEx monthly daily tables reconcile all 107 EMPTY dates: 100 have zero volume and no OHLC, while seven have non-price activity but still no OHLC. No retry or repair is required.
- Raw timestamp inspection classified all 198 exact 14/15/53/54-row observations as irregular natural sparse sessions. There are no five- or twenty-minute fixed grids in this job.
- Aggregate usable coverage excluding quarantined 7610 is now 357 complete symbols, 259,539 partitions, 259,153 `READY`, 386 expected `EMPTY`, zero `INVALID`, and 45,313,538 bars.
- The next established distinct-industry tranche is 6728 (`居家生活類`), 2910 (`貿易百貨`), 1906 (`造紙工業`), 1307 (`塑膠工業`), 6112 (`資訊服務業`), 2031 (`鋼鐵工業`), 6189 (`電子通路業`), and 2852 (`金融保險`). Sealed official listing dates range from 1976-04-26 through 2020-12-25, all before the frozen start.
- Deterministic job `finmind-sponsor-2f1359a59f6f020a` was created in status-only mode with zero provider requests. Sole writer session 41184 received an official-positive batch of 183 requests, sealed one calendar, then consumed seven more rolling-positive KBar requests before waiting for the next official release.
- A bounded audit verified 189/189 `READY` partitions and 19,938 bars with zero issues; exact next pending is `1307 / 2024-05-31`, 5,627 symbol-days remain, and SQLite `quick_check=ok`.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 07:45 Asia/Taipei with explicit protection for job `finmind-sponsor-2f1359a59f6f020a`, session 41184, official-positive preflight, timeout backoff, and all no-trading boundaries.

## 2026-08-26 07:45 Completion, Official Reconciliation, and Next Writer

- Session 41184 remained the only writer and exited normally after completing deterministic job `finmind-sponsor-2f1359a59f6f020a`. Since the previous 189-partition handoff, exactly 5,627 KBar responses were checkpointed without re-requesting the sealed calendar or any prior symbol-day.
- Final job state is 5,808 `READY`, eight expected `EMPTY`, zero `INVALID`, 529,741 bars, no next pending, and one calendar plus 5,816 KBar responses.
- Full offline audit verified 5,816/5,816 raw/canonical partitions and digests with zero issues. The event range is 2023-08-21 09:01 through 2026-08-18 13:30 Asia/Taipei, and SQLite `quick_check` is `ok`.
- Per-symbol results are 1307 727 READY / 103,717 bars; 1906 727 / 16,624; 2031 727 / 103,071; 2852 727 / 54,209; 2910 720 READY plus seven EMPTY / 6,996; 6112 727 / 116,136; 6189 727 / 115,616; and 6728 726 READY plus one EMPTY / 13,372.
- Official TWSE/TPEx monthly daily tables reconcile all eight EMPTY dates: three have zero volume and no OHLC, while five have non-price activity but still no OHLC. No retry or repair is required.
- Raw timestamp inspection classified all 208 exact 14/15/53/54-row observations as irregular natural sparse sessions. There are no five- or twenty-minute fixed grids in this job.
- Aggregate usable coverage excluding quarantined 7610 is now 365 complete symbols, 265,355 partitions, 264,961 `READY`, 394 expected `EMPTY`, zero `INVALID`, and 45,843,279 bars.
- The next established distinct-industry tranche is 2062 (`居家生活`), 8446 (`文化創意業`), 8927 (`油電燃氣業`), 2107 (`橡膠工業`), 1268 (`觀光餐旅`), 2906 (`貿易百貨`), 5403 (`資訊服務業`), and 4306 (`塑膠工業`). Sealed official listing dates range from 1989-12-26 through 2017-09-27, all before the frozen start. Candidate 6028 was excluded because its official listing date is 2026-03-30.
- Deterministic job `finmind-sponsor-4d9501078e3a36dd` was created in status-only mode with zero provider requests. Sole writer session 68331 received an official-positive batch of 373 requests, sealed one calendar, and remains `RUNNING` while consuming only later positive releases.
- A bounded audit verified 616/616 `READY` partitions and 15,850 bars with zero issues. The later read-only boundary reached 705 `READY`, zero `EMPTY`/`INVALID`, 17,366 bars, exact next pending `1268 / 2026-07-20`, and 5,111 symbol-days remaining; SQLite `quick_check=ok`.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 08:55 Asia/Taipei with explicit protection for job `finmind-sponsor-4d9501078e3a36dd`, session 68331, official-positive preflight, timeout backoff, and all no-trading boundaries.
- The final read-only handoff advanced to 948 `READY`, zero `EMPTY`/`INVALID`, 33,687 bars, exact next pending `2062 / 2024-07-17`, and 4,868 symbol-days remaining; session 68331 remained attached and healthy.
## 2026-08-26 08:55 Transport Recovery, Full Reconciliation, and Next Tranche

- Sole writer session 68331 advanced `finmind-sponsor-4d9501078e3a36dd` to 3,880 durable partitions and then exited on `ConnectionResetError: [Errno 54] Connection reset by peer`. Its last successful checkpoint was `2026-08-26T08:40:00.900011+08:00`, leaving exact next pending `5403 / 2024-08-22`; the failed transport attempt created no partition or attempt-ledger row.
- More than fifteen minutes had elapsed before recovery. The 3,880-partition boundary passed a 3,880/3,880 offline audit with 287,475 bars and zero issues, and SQLite `quick_check=ok`.
- Sole recovery session 73197 received an official-positive preflight of 3,111 requests and used exactly 1,936 KBar requests to finish the existing deterministic job. No calendar or checkpointed symbol-day was repeated.
- Final job state is 5,808 `READY`, eight expected `EMPTY`, zero `INVALID`, 412,283 bars, and no next pending. Full offline audit passed 5,816/5,816 partitions with zero issues; event bounds are 2023-08-21 09:01 through 2026-08-18 13:30 Asia/Taipei and SQLite `quick_check=ok`.
- Per-symbol results are 1268 727 READY / 17,815 bars; 2062 727 / 72,648; 2107 720 READY plus seven EMPTY / 41,285; 2906 727 / 42,195; 4306 727 / 100,691; 5403 727 / 27,579; 8446 727 / 36,855; and 8927 726 READY plus one EMPTY / 73,215.
- TPEx official daily data confirms the sole 8927 EMPTY has zero volume and no OHLC. TWSE official `TWTAUU` identifies 2107's 2023-09-07 through 2023-09-15 missing block as the trading stop before a cash-capital-reduction (`退還股款`) resumption on 2023-09-18. No EMPTY requires retry or repair.
- Raw timestamp inspection classified all 201 exact 14/15/53/54-row observations as irregular natural sparse sessions. There are no fixed five- or twenty-minute grids in this job.
- Aggregate usable coverage excluding quarantined 7610 is now 373 complete symbols, 271,171 partitions, 270,769 `READY`, 402 expected `EMPTY`, zero `INVALID`, and 46,255,562 bars.
- The next established distinct-industry tranche is 1308 (`塑膠工業`), 2114 (`橡膠工業`), 2729 (`觀光餐旅`), 2945 (`貿易百貨`), 3546 (`文化創意業`), 6163 (`資訊服務業`), 8433 (`居家生活類`), and 9918 (`油電燃氣業`). Sealed official listing dates range from 1986-06-20 through 2021-11-30, all before the frozen start.
- Deterministic job `finmind-sponsor-ec68ea09b56c8162` was created in status-only mode with zero provider requests. Sole writer session 67947 sealed one 727-day calendar, received an official-positive batch of 3,609 requests, and continues checkpoint-first acquisition.
- The final bounded handoff audit passed 758/758 `READY` partitions and 103,346 bars with zero issues. Stock 1308 is complete; exact next pending is `2114 / 2023-10-04`, with 5,058 symbol-days remaining and SQLite `quick_check=ok`.
- From the prior 948-partition handoff, this heartbeat checkpointed 4,868 KBar responses to complete the prior job: 2,932 before the transport reset and 1,936 after recovery. The new job then added one calendar plus 758 KBar checkpoints, for 5,627 successful provider requests in this heartbeat; no quota-error probe was used.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 09:55 Asia/Taipei with explicit single-writer, checkpoint, timeout-backoff, official-positive-only, and no-trading boundaries.

## 2026-08-26 09:55 Single-Writer Monitoring and Partial Reconciliation

- Sole continuous writer session 67947 remained attached throughout this heartbeat. It reached 4,081 partitions, waited without probing when official usage reported no positive allowance, then resumed automatically as rolling-positive batches became available. No duplicate writer or repeated calendar was created.
- The final audited handoff boundary is 4,767/5,816 partitions: 4,750 `READY`, 17 expected `EMPTY`, zero `INVALID`, and 323,353 bars. Exact next pending is `8433 / 2025-04-25`, with 1,049 symbol-days remaining; 1308, 2114, 2729, 2945, 3546, and 6163 are complete, 8433 is partial, and 9918 has not started.
- Offline audit passed all 4,767/4,767 current partitions with zero issues, and SQLite `quick_check=ok`.
- TWSE/TPEx official monthly daily data reconciles every current EMPTY: one for 2114, one for 2729, and fifteen for 2945. Three dates have zero volume and no OHLC; fourteen have non-price activity but still no OHLC. None requires re-request or repair.
- Raw timestamp inspection currently finds 203 exact 14/15/53/54-row observations: 191 are irregular natural sparse sessions. The twelve true 6163 five-minute grids run from 2025-12-05 through 2025-12-22 and exactly match TPEx's official 12-business-day disposition record with approximately five-minute matching.
- Since the prior 758-partition audited handoff, 4,009 additional KBar requests were successfully checkpointed. All progress came from the same writer using official-positive rolling releases; no quota-error probe was used.
- Aggregate usable coverage excluding quarantined 7610 is now 379 complete symbols plus one partial symbol, 275,938 partitions, 275,519 `READY`, 419 expected `EMPTY`, zero `INVALID`, and 46,578,915 bars.
- The existing `finmind` heartbeat was updated through the Codex app manager and scheduled for 10:55 Asia/Taipei with the live job, sole-writer guard, exact audited checkpoint, official exception evidence, and no-trading boundaries.

## 2026-08-26 10:55 Completion, Final Reconciliation, and Next Tranche

- Sole writer session 67947 exited normally after completing deterministic job `finmind-sponsor-ec68ea09b56c8162`. Since the prior 4,767-partition handoff, exactly 1,049 KBar responses were checkpointed without repeating the sealed calendar or any prior symbol-day.
- Final job state is 5,754 `READY`, 62 expected `EMPTY`, zero `INVALID`, 338,975 bars, and no next pending. Full offline audit passed 5,816/5,816 partitions with zero issues; SQLite URI-mode `quick_check=ok`.
- Per-symbol results are 1308 727 READY / 102,928 bars; 2114 726 READY plus one EMPTY / 12,497; 2729 726 READY plus one EMPTY / 16,588; 2945 712 READY plus fifteen EMPTY / 6,828; 3546 727 / 55,407; 6163 727 / 112,840; 8433 727 / 22,567; and 9918 682 READY plus 45 EMPTY / 9,320.
- Official TWSE/TPEx monthly daily tables reconcile all 62 EMPTY dates: three have zero volume and no OHLC, while 59 contain only non-price activity and still have no OHLC. No retry or repair is required.
- Raw timestamp inspection classified 264 exact 14/15/53/54-row observations: 252 irregular natural sparse sessions and twelve 6163 five-minute grids. The grids remain exactly covered by the official 2025-12-05--12-22 TPEx disposition period.
- Aggregate usable coverage excluding quarantined 7610 is now 381 complete symbols, 276,987 partitions, 276,523 `READY`, 464 expected `EMPTY`, zero `INVALID`, and 46,594,537 bars. The only excluded partial history remains 7610 with one READY and one intentionally quarantined INVALID partition.
- The next established distinct-industry tranche is 1321 (`塑膠工業`), 2010 (`鋼鐵工業`), 2109 (`橡膠工業`), 3055 (`電子通路業`), 8099 (`資訊服務業`), 8931 (`油電燃氣業`), 9935 (`居家生活`), and 9943 (`觀光餐旅`). Sealed official listing dates range from 1989-12-22 through 2004-03-29, all before the frozen start.
- Deterministic job `finmind-sponsor-3eead7cc8a091d5b` was created in status-only mode with zero provider requests. Sole writer session 38603 sealed one 727-day calendar, received an official-positive batch of 4,465 requests, and remains `RUNNING`.
- A bounded audit verified 95/95 READY partitions and 4,741 bars with zero issues. The later read-only handoff boundary reached 219 READY, zero EMPTY/INVALID, exact next pending `1321 / 2024-07-15`, and 5,597 symbol-days remaining; SQLite `quick_check=ok`.
- Through the handoff boundary, this heartbeat recorded 1,269 successful provider requests: 1,049 KBar responses completed the prior job, then one calendar plus 219 KBar responses advanced the new job. No quota-error probe was used.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back, and scheduled for 11:55 Asia/Taipei with the new job, sole-writer protection, official-positive-only policy, and all no-trading boundaries.

## 2026-08-26 Manual Continuation

- Read-only live status confirmed session 38603 remains the sole healthy writer for `finmind-sponsor-3eead7cc8a091d5b`; no second writer or repeated calendar was created.
- The audited continuation boundary reached 679/5,816 partitions: 679 `READY`, zero `EMPTY`/`INVALID`, 38,982 bars, exact next pending `1321 / 2026-06-10`, and 5,137 symbol-days remaining.
- Offline audit passed 679/679 partitions with zero issues and SQLite URI-mode `quick_check=ok`; the writer continues consuming only its official-positive preflight batch.

## 2026-08-26 11:55 Completion, Official Reconciliation, and Next Tranche

- Sole writer session 38603 completed deterministic job `finmind-sponsor-3eead7cc8a091d5b` after using the full official-positive 4,465-request batch and a subsequent 1,535-request positive batch. No quota-error probe, repeated calendar, or duplicate symbol-day occurred.
- Final job state is 5,815 `READY`, one expected `EMPTY`, zero `INVALID`, 414,633 bars, and no next pending. Full offline audit passed 5,816/5,816 partitions with zero issues and SQLite URI-mode `quick_check=ok`.
- Per-symbol results are 1321 727 READY / 41,255 bars; 2010 727 / 88,775; 2109 727 / 38,857; 3055 727 / 98,142; 8099 727 / 38,817; 8931 726 READY plus one EMPTY / 21,813; 9935 727 / 58,755; and 9943 727 / 28,219.
- TPEx official daily data reconciles the sole EMPTY, `8931 / 2025-07-08`, to a nonzero-activity row with no regular OHLC; no retry or repair is required.
- Raw timestamp inspection classified 229 exact 14/15/53/54-row observations: 218 irregular natural sparse sessions, four five-minute grids, and seven twenty-minute grids. All eleven true grids belong to 3055.
- TWSE official disposition data covers 3055's observed grids: approximately five-minute matching on 2025-04-15--04-28 and 2026-07-06--07-17, then approximately twenty-minute matching on 2026-07-09--07-22 and 2026-07-31--08-13. The stored grid dates fall within those official periods.
- Aggregate usable coverage excluding quarantined 7610 is now 389 complete symbols, 282,803 partitions, 282,338 `READY`, 465 expected `EMPTY`, zero `INVALID`, and 47,009,170 bars.
- The next established distinct-industry tranche is 1305 (`塑膠工業`), 2009 (`鋼鐵工業`), 2706 (`觀光餐旅`), 2916 (`居家生活類`), 4994 (`資訊服務業`), 6111 (`文化創意業`), 6582 (`橡膠工業`), and 9931 (`油電燃氣業`). Sealed official listing dates range from 1973-03-05 through 2017-06-14, all before the frozen start.
- Deterministic job `finmind-sponsor-650f66990c1d45b8` was created in status-only mode with zero provider requests. Sole writer session 42665 sealed one 727-day calendar and received an official-positive batch of 183 requests.

## 2026-08-26 12:55 completion and next diversified tranche

- Sole writer session 42665 completed deterministic job `finmind-sponsor-650f66990c1d45b8` without repeating its calendar or any prior checkpoint. Final state is 5,790 `READY`, 26 expected `EMPTY`, zero `INVALID`, 424,498 bars, and no next pending; the full offline audit verified 5,816/5,816 partitions with zero issues and SQLite URI-mode `quick_check=ok`.
- Per-symbol results are 1305 727 READY / 102,239 bars; 2009 727 / 133,966; 2706 727 / 26,802; 2916 727 / 19,474; 4994 720 READY plus seven EMPTY / 22,809; 6111 727 / 83,754; 6582 727 / 24,869; and 9931 708 READY plus nineteen EMPTY / 10,585.
- TWSE official daily rows reconcile all nineteen 9931 EMPTY dates to sessions with no regular OHLC: one is zero-volume and eighteen contain only non-price activity. TWSE's official capital-reduction record shows 4994 last traded on 2023-09-26 and resumed on 2023-10-11 after cash-capital-reduction share replacement, exactly covering its seven EMPTY trading sessions from 2023-09-27 through 2023-10-06.
- Raw timestamp inspection classified 251 exact 14/15/53/54-row observations: 249 irregular natural sparse sessions and two 4994 five-minute grids on 2024-03-15 and 2024-03-19. Both grids fall within TWSE's official approximately-five-minute disposition period from 2024-03-15 through 2024-03-28.
- Aggregate usable coverage excluding quarantined 7610 is now 397 complete symbols, 288,619 partitions, 288,128 `READY`, 491 expected `EMPTY`, zero `INVALID`, and 47,433,668 bars.
- The next established distinct-industry tranche is 1612 (`電器電纜`), 1795 (`生技醫療業`), 2201 (`汽車工業`), 3130 (`數位雲端`), 6613 (`其他電子類`), 6811 (`數位雲端類`), 8933 (`運動休閒類`), and 9930 (`綠能環保`). Sealed official listing dates range from 1976-07-08 through 2022-08-09, all before the frozen 2023-08-19 start.
- Deterministic job `finmind-sponsor-be65322fdea607a1` was created in status-only mode with zero provider requests. Sole writer session 79300 sealed one 727-day calendar, received an official-positive batch of 502 requests, and remains `RUNNING`.
- A bounded audit verified 332/332 READY partitions and 57,372 bars with zero issues. The later read-only handoff boundary reached 559 READY, zero EMPTY/INVALID, 92,244 bars, exact next pending `1612 / 2025-12-05`, and 5,257 symbol-days remaining; SQLite `quick_check=ok`.
- Through that handoff boundary, this heartbeat recorded 6,292 successful provider responses: 5,732 KBar responses completed the previous job, followed by one calendar and 559 KBar responses for the new job. Every symbol-day was checkpointed before the next request, and no quota-error probe was used.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back from its persisted definition, and scheduled for 13:55 Asia/Taipei with the current deterministic job, sole-writer guard, official-positive-only policy, and all no-trading boundaries.
- The bounded handoff audit passed 84/84 READY partitions and 12,924 bars with zero issues. Exact next pending is `1305 / 2023-12-20`, 5,732 symbol-days remain, and SQLite `quick_check=ok`.

## 2026-08-26 13:55 completion and next diversified tranche

- Sole writer session 79300 completed deterministic job `finmind-sponsor-be65322fdea607a1` without repeating its calendar or any prior checkpoint. Final state is 5,811 `READY`, five expected `EMPTY`, zero `INVALID`, 626,819 bars, and no next pending; the full offline audit verified 5,816/5,816 partitions with zero issues and SQLite `quick_check=ok`.
- Per-symbol results are 1612 727 READY / 116,273 bars; 1795 727 / 154,986; 2201 727 / 158,248; 3130 722 READY plus five EMPTY / 11,066; 6613 727 / 57,741; 6811 727 / 54,950; 8933 727 / 37,917; and 9930 727 / 35,638.
- TWSE official daily rows reconcile all five 3130 EMPTY dates (`2023-08-28`, `2023-09-01`, `2023-09-04`, `2023-10-03`, and `2023-12-27`) to sessions with nonzero non-price activity but no regular OHLC. No retry or repair is required.
- Raw timestamp inspection classified 182 exact 14/15/53/54-row observations: 164 irregular natural sparse sessions and eighteen five-minute grids. Official disposition records cover all true grids: ten 1795 dates in TWSE's 2025-10-02--10-17 period, three 6613 dates in TPEx's 2026-06-18--07-02 period, and five 8933 dates in TPEx's 2026-01-26--02-06 period.
- Aggregate usable coverage excluding quarantined 7610 is now 405 complete symbols, 294,435 partitions, 293,939 `READY`, 496 expected `EMPTY`, zero `INVALID`, and 48,060,487 bars.
- The next established diversified tranche is 6491 (`生技醫療業`, listed 2019-10-07), 6581 (`綠能環保`, 2018-01-30), 5287 (`數位雲端類`, 2014-01-20), 1593 (`運動休閒類`, 2012-06-13), 2204 (`汽車工業`, 1991-03-12), 6146 (`其他電子類`, 2002-01-23), 1604 (`電器電纜`, 1970-12-14), and 1711 (`化學工業`, 1988-12-27). Every sealed official listing date predates the frozen start.
- Deterministic job `finmind-sponsor-384674f97d4e6598` was created in status-only mode with zero provider requests. Sole writer session 86167 sealed one 727-day calendar, used an official-positive batch of 185 requests, then continued with positive rolling releases of 154, 143, 116, 105, 87, 82, and 75 requests; it remains `RUNNING`.
- A bounded audit verified 384/384 checkpointed partitions and 5,150 bars with zero issues. A later exact read-only handoff boundary reached 926 partitions: 921 `READY`, five `EMPTY`, zero `INVALID`, exact next pending `1604 / 2024-06-17`, and 4,890 symbol-days remaining; SQLite `quick_check=ok`. The writer continued advancing after this snapshot.
- Through the exact handoff boundary, this heartbeat recorded 6,184 successful provider responses: 5,257 KBar responses completed the prior job, followed by one sealed calendar and 926 checkpointed KBar responses for the new job. Every symbol-day was durable before the next request, and no quota-error probe was used.
- The initial `sqlite3` URI command failed locally with `unable to open database file (14)`; read-only Python URI mode and a later `sqlite3 -readonly` integrity check succeeded. No provider request or database state was affected.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back from its persisted definition, and scheduled for 14:55 Asia/Taipei with job `finmind-sponsor-384674f97d4e6598`, sole-writer protection, official-positive-only requests, and all no-trading boundaries.

## 2026-08-26 manual continuation after 13:55 handoff

- Session 86167 remains the sole healthy continuous writer for deterministic job `finmind-sponsor-384674f97d4e6598`; no second process, repeated calendar, or repeated checkpoint was started.
- The exact audited continuation boundary reached 1,868/5,816 partitions: 1,863 `READY`, five `EMPTY`, zero `INVALID`, 121,072 bars, exact next pending `1711 / 2025-05-09`, and 3,948 symbol-days remaining.
- Offline audit verified all 1,868 checkpointed partitions with zero issues, and SQLite `quick_check=ok`. The attached writer continued using only positive rolling releases after the snapshot.

## 2026-08-26 14:55 completion and next diversified tranche

- Sole writer session 86167 completed deterministic job `finmind-sponsor-384674f97d4e6598` without repeating its calendar or any prior checkpoint. Final state is 5,802 `READY`, fourteen expected `EMPTY`, zero `INVALID`, 503,723 bars, and no next pending; full offline audit verified 5,816/5,816 partitions with zero issues and SQLite `quick_check=ok`.
- Per-symbol results are 1593 722 READY plus five EMPTY / 10,416 bars; 1604 727 READY / 45,097; 1711 727 / 128,539; 2204 727 / 147,672; 5287 726 READY plus one EMPTY / 16,288; 6146 727 / 64,209; 6491 727 / 80,376; and 6581 719 READY plus eight EMPTY / 11,126.
- Official TWSE/TPEx daily rows reconcile all fourteen EMPTY dates: four are zero-volume sessions and ten contain only non-price activity, while every row lacks regular OHLC. No retry or repair is required.
- Raw timestamp inspection classified 252 exact 14/15/53/54-row observations: 236 irregular natural sparse sessions, ten 1711 five-minute grids, and six 1711 twenty-minute grids. TWSE's official records cover the five-minute grids in the 2026-03-20--04-02 first disposition and the twenty-minute grids in the 2026-04-24--05-08 second disposition.
- Aggregate usable coverage excluding quarantined 7610 is now 413 complete symbols, 300,251 partitions, 299,741 `READY`, 510 expected `EMPTY`, zero `INVALID`, and 48,564,210 bars.
- The next established diversified tranche is 4123 (`生技醫療業`, listed 2003-10-07), 8341 (`綠能環保`, 2015-03-23), 2640 (`數位雲端類`, 2012-11-07), 9914 (`運動休閒`, 1992-09-30), 6605 (`汽車工業`, 2004-03-17), 3587 (`其他電子類`, 2009-08-18), 1615 (`電器電纜`, 2000-03-30), and 4722 (`化學工業`, 2012-08-15). Every sealed official listing date predates the frozen start.
- Deterministic job `finmind-sponsor-b4cd8cc35cfd5e45` was created in status-only mode with zero provider requests. Sole writer session 73543 sealed one 727-day calendar and consumed only official-positive releases of 183, 50, 81, and 97 requests; it remains `RUNNING`.
- Exact read-only handoff reached 383 `READY`, zero `EMPTY`/`INVALID`, 27,733 bars, exact next pending `1615 / 2025-03-24`, and 5,433 symbol-days remaining. The bounded audit verified 383/383 partitions with zero issues and SQLite `quick_check=ok`; the writer continued after the snapshot.
- Since the prior 1,868-partition audited manual boundary, this heartbeat recorded 4,332 successful provider responses: 3,948 KBar responses completed the prior job, followed by one calendar and 383 KBar responses for the new job. No quota-error probe was used.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back from its persisted definition, and scheduled for 15:55 Asia/Taipei with the current job, sole-writer protection, official-positive-only requests, and all no-trading boundaries.

## 2026-08-26 15:55 completion and next diversified tranche

- Sole writer session 73543 completed deterministic job `finmind-sponsor-b4cd8cc35cfd5e45` without repeating its calendar or any prior checkpoint. Final state is 5,814 `READY`, two expected `EMPTY`, zero `INVALID`, 629,121 bars, and no next pending; full offline audit verified 5,816/5,816 partitions with zero issues and SQLite `quick_check=ok`.
- Per-symbol results are 1615 727 READY / 42,166 bars; 2640 727 / 14,295; 3587 726 READY plus one EMPTY / 111,769; 4123 726 READY plus one EMPTY / 123,908; 4722 727 / 82,216; 6605 727 / 87,991; 8341 727 / 43,777; and 9914 727 / 122,999.
- TPEx and TWSE official daily rows reconcile `3587 / 2026-07-31` and `4123 / 2024-11-29` as zero-volume sessions without regular OHLC. No retry or repair is required.
- Raw timestamp inspection classified 182 exact 14/15/53/54-row observations: 144 irregular natural sparse sessions, twenty five-minute grids, and eighteen twenty-minute grids. TPEx's official 2026-03-26--04-10 disposition covers all ten 3587 five-minute grids. TWSE's official records cover 4722's ten five-minute and eighteen twenty-minute grids across the 2025-08-21--09-03, 2025-08-26--09-08, 2025-10-07--10-21, and 2026-05-26--06-08 periods.
- Aggregate usable coverage excluding quarantined 7610 is now 421 complete symbols, 306,067 partitions, 305,555 `READY`, 512 expected `EMPTY`, zero `INVALID`, and 49,193,331 bars.
- The next low-coverage diversified tranche is 6902 (`數位雲端`, listed 2023-07-13), 5432 (`綠能環保類`, 2000-03-21), 4743 (`生技醫療業`, 2011-09-23), 8928 (`運動休閒類`, 2001-02-02), 4551 (`汽車工業`, 2015-08-10), 3289 (`其他電子類`, 2004-12-28), 1614 (`電器電纜`, 1997-09-18), and 1723 (`化學工業`, 1998-11-27). Every sealed official listing date predates the frozen start.
- Deterministic job `finmind-sponsor-bd63b6c8046d18f1` was created in status-only mode with zero provider requests. Sole writer session 25403 sealed one 727-day calendar, received an official-positive preflight batch of 349 requests, and remains `RUNNING`.
- Exact audited handoff reached 72 `READY`, zero `EMPTY`/`INVALID`, 1,086 bars, exact next pending `1614 / 2023-12-04`, and 5,744 symbol-days remaining. Audit passed 72/72 with zero issues and SQLite `quick_check=ok`; session 25403 continued advancing after the snapshot.
- Through that audited handoff, this heartbeat recorded 5,506 successful provider responses: 5,433 KBar responses completed the old job, followed by one calendar and 72 KBar responses for the new job. No quota-error probe was used.
- The existing `finmind` heartbeat was updated through the Codex app manager, corrected and read back from its persisted definition, and scheduled for 16:55 Asia/Taipei with the current job, sole-writer protection, official-positive-only requests, and all no-trading boundaries.

## 2026-08-26 16:55 transport-backoff continuation

- Sole writer session 25403 stopped safely at 2026-08-26 16:33:36+08:00 after a FinMind transport timeout. SQLite retained 2,894 `READY`, zero `EMPTY`/`INVALID`, 279,409 bars, exact next pending `4551 / 2026-07-30`, and 2,922 symbol-days remaining.
- The timeout attempt is explicitly recorded as failed and the preceding `4551 / 2026-07-29` response is durable. Offline audit verified 2,894/2,894 partitions with zero issues and SQLite `quick_check=ok`.
- More than 21 minutes had elapsed before the heartbeat inspected the failed attempt, satisfying the full 60-second backoff. No other writer had advanced SQLite, so the same deterministic job was resumed without a second calendar or duplicate symbol-day.
- Replacement session 94617 received an official-positive preflight of 2,957 requests, enough to cover the 2,922 remaining symbol-days at resume time. It successfully checkpointed the formerly pending `4551 / 2026-07-30` partition first and continued forward.
- The exact audited handoff reached 3,000 `READY`, zero `EMPTY`/`INVALID`, 300,219 bars, exact next pending `4743 / 2024-01-02`, and 2,816 symbol-days remaining. Four symbols are complete, 4743 is partial, and 5432, 6902, and 8928 remain pending; 3,000/3,000 audit passed with zero issues and `quick_check=ok`.
- From the prior 72-partition handoff through this audited boundary, 2,928 additional successful KBar responses were checkpointed. The single timeout attempt remained failed evidence and was not miscounted as a partition.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back from disk, and scheduled for 17:55 Asia/Taipei with session 94617, the exact live checkpoint, single-writer guard, full timeout backoff, and all no-trading boundaries.

## 2026-08-26 17:55 second transport-backoff continuation

- Replacement writer session 94617 stopped safely on a FinMind transport timeout at 2026-08-26 17:01:57+08:00. SQLite retained 3,248 `READY`, zero `EMPTY`/`INVALID`, 348,475 bars, exact next pending `4743 / 2025-01-10`, and 2,568 symbol-days remaining.
- The failed attempt is explicitly recorded and the preceding `4743 / 2025-01-09` response is durable. Offline audit verified 3,248/3,248 partitions with zero issues and SQLite `quick_check=ok`.
- More than 53 minutes elapsed before this heartbeat inspected the failure, satisfying the full 60-second backoff. No other writer advanced SQLite, so the same deterministic job resumed without another calendar or duplicate symbol-day.
- Sole writer session 27433 received an official-positive preflight of 5,662 requests, enough to cover all 2,568 remaining symbol-days at resume time, and checkpointed the formerly pending `4743 / 2025-01-10` first.
- The exact audited handoff reached 3,344 `READY`, zero `EMPTY`/`INVALID`, 367,293 bars, and passed 3,344/3,344 with zero issues plus `quick_check=ok`. A later read-only status reached 3,363 `READY`, exact next pending `4743 / 2025-07-08`, and 2,453 symbol-days remaining; session 27433 continued after the snapshot.
- Since the prior 3,000-partition audited handoff, 344 additional successful KBar responses were verified through the new audit boundary; the live status had advanced by 363 successful checkpoints. The one transport failure remains failed evidence and is not counted as a partition.
- The `finmind` heartbeat was updated through the Codex app manager and read back for 18:55 Asia/Taipei with session 27433, the audited and live boundaries, single-writer protection, full transport backoff, official-positive-only policy, and all no-trading boundaries.

## 2026-08-26 18:55 third transport-backoff continuation

- Sole writer session 27433 stopped safely on a FinMind transport timeout at 2026-08-26 18:02:27+08:00. SQLite retained 3,567 `READY`, zero `EMPTY`/`INVALID`, 414,050 bars, exact next pending `4743 / 2026-05-13`, and 2,249 symbol-days remaining.
- The failed attempt is explicitly recorded and the preceding `4743 / 2026-05-12` response is durable. Offline audit verified 3,567/3,567 partitions with zero issues and SQLite `quick_check=ok`.
- More than 52 minutes elapsed before this heartbeat inspected the failure, satisfying the full 60-second backoff. No other writer advanced SQLite, so the same deterministic job resumed without another calendar or duplicate symbol-day.
- Sole writer session 92530 received an official-positive preflight of 5,680 requests, enough to cover all 2,249 remaining symbol-days at resume time, and checkpointed the formerly pending `4743 / 2026-05-13` first.
- The exact audited handoff reached 3,646 `READY`, zero `EMPTY`/`INVALID`, 428,847 bars, and passed 3,646/3,646 with zero issues plus `quick_check=ok`. A later read-only status reached 3,660 `READY`, exact next pending `5432 / 2023-09-25`, and 2,156 symbol-days remaining; 4743 is now complete and session 92530 continued after the snapshot.
- Since the prior 3,344-partition audited handoff, 302 additional successful KBar responses were verified through the new audit boundary; the live status had advanced by 316 successful checkpoints. The one transport failure remains failed evidence and is not counted as a partition.
- The `finmind` heartbeat was updated through the Codex app manager and read back for 19:55 Asia/Taipei with session 92530, the audited and live boundaries, single-writer protection, full transport backoff, official-positive-only policy, and all no-trading boundaries.

## 2026-08-26 19:55 fourth transport-backoff continuation

- Sole writer session 92530 stopped safely on a FinMind transport timeout at 2026-08-26 19:07:16+08:00. SQLite retained 4,374 `READY`, three `EMPTY`, zero `INVALID`, 495,008 bars, exact next pending `6902 / 2023-09-11`, and 1,439 symbol-days remaining.
- The failed attempt is explicitly recorded and the preceding `6902 / 2023-09-08` response is a durable `EMPTY` checkpoint. Offline audit verified 4,377/4,377 partitions with zero issues and SQLite `quick_check=ok`.
- More than 49 minutes elapsed before this heartbeat inspected the failure, satisfying the full 60-second backoff. No other writer advanced SQLite, so the same deterministic job resumed without another calendar or duplicate symbol-day.
- Sole writer session 69253 received an official-positive preflight of 5,293 requests, enough to cover all 1,439 remaining symbol-days at resume time, and checkpointed the formerly pending `6902 / 2023-09-11` first.
- The exact audited handoff reached 4,466 `READY`, twenty `EMPTY`, zero `INVALID`, 495,349 bars, and passed 4,486/4,486 with zero issues plus `quick_check=ok`. A later read-only status reached 4,678 `READY`, fifty `EMPTY`, zero `INVALID`, exact next pending `6902 / 2025-02-26`, and 1,088 symbol-days remaining; session 69253 continued after the snapshot.
- The existing `finmind` heartbeat was updated through the Codex app manager and read back for 20:55 Asia/Taipei with session 69253, the exact live checkpoint, single-writer protection, full transport backoff, official-positive-only policy, and all no-trading boundaries.

## 2026-08-26 20:55 completion, official reconciliation, and next diversified tranche

- Sole writer session 69253 completed deterministic job `finmind-sponsor-bd63b6c8046d18f1` at 5,757 `READY`, 59 expected `EMPTY`, zero `INVALID`, 522,883 bars, and no next pending. It used exactly 1,439 KBar requests after the prior timeout checkpoint and did not repeat the sealed calendar or any completed partition.
- Full offline audit verified all 5,816 partitions with zero issues and SQLite `quick_check=ok`.
- TWSE/TPEx official daily data returned all 59 target rows with no regular OHLC: 37 zero-volume rows and 22 nonzero/non-price-activity rows. No EMPTY requires retry or repair.
- Raw timestamp inspection classified 213 exact 14/15/53/54-row observations: 197 irregular natural sparse sessions and sixteen five-minute grids. The fixed grids are eight dates for 3289, seven for 4551, and one for 5432; no twenty-minute grid was found.
- Official disposition records cover every fixed grid: TPEx records 3289 at approximately five minutes from 2026-04-17 through 2026-04-30 and 5432 from 2023-10-04 through 2023-10-23; TWSE records 4551 from 2026-06-23 through 2026-07-06.
- Aggregate usable coverage excluding quarantined 7610 now contains 429 complete symbols. From the sealed 2026-08-20 market-value snapshot and sealed official company rows, the next broad-industry-diverse eligible tranche is 1234 (`食品工業`), 1618 (`電器電纜`), 2247 (`汽車工業`), 3498 (`其他電子類`), 3708 (`綠能環保`), 4105 (`生技醫療業`), 4536 (`運動休閒`), and 6689 (`數位雲端`). Official listing dates range from 1999-03-12 through 2022-09-13, all before the frozen start.
- Deterministic job `finmind-sponsor-8f4d2c6ad7feaa95` was created without provider access. Sole writer session 85663 sealed one 727-day calendar and received an official-positive preflight of 4,959 requests.
- The first audited boundary is 47 `READY`, zero `EMPTY`/`INVALID`, 1,978 bars, exact next pending `1234 / 2023-10-30`, and 5,769 symbol-days remaining. Audit passed 47/47 with zero issues and `quick_check=ok`; session 85663 continued after the snapshot.
- The existing `finmind` heartbeat was updated through the Codex app manager and read back for 21:55 Asia/Taipei with session 85663, the exact audited checkpoint, single-writer protection, official-positive-only policy, and all no-trading boundaries.

## 2026-08-26 21:55 transport-backoff continuation

- Sole writer session 85663 stopped safely on a FinMind transport timeout at 2026-08-26 21:41:37+08:00. SQLite retained 3,351 `READY`, zero `EMPTY`/`INVALID`, 359,429 bars, exact next pending `3708 / 2025-06-20`, and 2,465 symbol-days remaining.
- The failed attempt is explicitly recorded and the preceding `3708 / 2025-06-19` response is durable. Offline audit verified 3,351/3,351 partitions with zero issues and SQLite `quick_check=ok`.
- More than fourteen minutes elapsed before this heartbeat inspected the failure, satisfying the full 60-second backoff. No other writer advanced SQLite, so the same deterministic job resumed without another calendar or duplicate symbol-day.
- Sole replacement writer session 42127 received an official-positive preflight of 2,646 requests, enough to cover all 2,465 remaining symbol-days at resume time, and checkpointed the formerly pending `3708 / 2025-06-20` first.
- The exact audited handoff reached 3,501 `READY`, zero `EMPTY`/`INVALID`, 384,489 bars, exact next pending `3708 / 2026-01-26`, and 2,315 symbol-days remaining. Audit passed 3,501/3,501 with zero issues and SQLite `quick_check=ok`; session 42127 continued after the snapshot.
- Since the prior 47-partition handoff, 3,454 additional successful KBar responses are durable; 150 were added by session 42127 after the timeout. The one transport failure remains failed evidence and is not counted as a partition.
- The existing `finmind` heartbeat was updated through the Codex app manager and read back for 22:55 Asia/Taipei with session 42127, the exact checkpoint, single-writer protection, full transport backoff, official-positive-only policy, and all no-trading boundaries.

## 2026-08-26 22:55 completion, official reconciliation, and next diversified tranche

- Sole writer session 42127 completed deterministic job `finmind-sponsor-8f4d2c6ad7feaa95` at 5,816 `READY`, zero `EMPTY`/`INVALID`, 619,223 bars, and no next pending. The resumed session spent exactly 2,465 KBar requests; whole-job local accounting is one calendar, 5,816 successful KBar responses, and one preserved failed timeout attempt.
- Full offline audit verified 5,816/5,816 partitions with zero issues and SQLite `quick_check=ok`. Per-symbol bars are 1234 29,177; 1618 135,121; 2247 30,104; 3498 99,243; 3708 109,967; 4105 88,992; 4536 57,049; and 6689 69,570.
- Raw timestamp inspection classified all 154 exact 14/15/53/54-row observations: 132 irregular natural sparse sessions and 22 five-minute grids, with no twenty-minute grids.
- TPEx officially records 3498 under approximately five-minute matching from 2026-05-19 through 2026-06-01, exactly covering all ten stored 3498 grids. TWSE officially records 3708 under approximately five-minute matching from 2025-07-17 through 2025-08-01, exactly covering all twelve stored 3708 grids.
- Aggregate usable coverage excluding quarantined 7610 is now 437 complete symbols, 317,699 partitions, 317,128 `READY`, 571 expected `EMPTY`, zero `INVALID`, and 50,335,437 bars.
- Industry-coverage ranking plus sealed 2026-08-20 market value selected 6763 (`數位雲端類`, listed 2022-03-15), 6869 (`綠能環保`, 2023-03-14), 6547 (`生技醫療業`, 2018-04-17), 9802 (`運動休閒`, 2012-10-18), 1444 (`紡織纖維`, 1990-08-08), 6754 (`居家生活`, 2020-08-25), 4764 (`化學工業`, 2018-01-04), and 6596 (`文化創意業`, 2018-01-04). All sealed official listing dates predate the frozen start.
- Deterministic job `finmind-sponsor-f9f1b8a5d0b7fb85` was created without provider access. Sole writer session 81526 sealed one 727-day calendar and received an official-positive preflight batch of 4,094 requests.
- First audited boundary reached 89 `READY`, zero `EMPTY`/`INVALID`, 10,681 bars, exact next pending `1444 / 2023-12-27`, and 5,727 symbol-days remaining. Audit passed 89/89 with zero issues and SQLite `quick_check=ok`; session 81526 continued after the snapshot.
- A later bounded audit reached 288 `READY`, zero `EMPTY`/`INVALID`, 34,948 bars, exact next pending `1444 / 2024-10-28`, and 5,528 symbol-days remaining. Audit passed 288/288 with zero issues and `quick_check=ok`; the sole writer remained active.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back from disk, and scheduled for 23:55 Asia/Taipei with session 81526, single-writer protection, official-positive-only requests, full timeout backoff, and all no-trading boundaries.

## 2026-08-26 23:55 provider-failure pause and partial official reconciliation

- Sole writer session 81526 stopped safely at 2026-08-26 23:29:53+08:00 after a FinMind HTTP 502 provider failure. SQLite retained 2,960 `READY`, eight `EMPTY`, zero `INVALID`, 301,521 bars, exact next pending `6754 / 2023-11-16`, and 2,848 symbol-days remaining.
- The current job has four complete stocks: 1444 has 727 READY / 79,795 bars; 4764 has 719 READY plus eight EMPTY / 35,535 bars; 6547 has 727 READY / 120,606 bars; and 6596 has 727 READY / 64,170 bars. Partial 6754 has 60 READY / 1,415 bars; 6763, 6869, and 9802 are still untouched.
- All 2,968 durable partitions audit cleanly with zero issues and SQLite `quick_check=ok`. The failed 6754/2023-11-16 attempt remains explicit failed evidence and did not create a partition.
- TWSE official daily data found all eight 4764 EMPTY rows and no regular OHLC: 2023-09-21 and 2023-10-20 are zero-volume; the other six contain only non-price activity. They are expected EMPTY checkpoints, not gaps.
- Raw timestamp inspection found 135 exact 14/15/53/54-row observations: 80 irregular natural sparse sessions, 31 five-minute grids, and 24 twenty-minute grids.
- TWSE official records cover every 4764 fixed grid: twenty-minute matching on 2025-10-30--11-12; overlapping first/second disposition windows from 2026-04-16 through 2026-05-20 that explain the single five-minute and subsequent twenty-minute grids; and five-minute matching on 2026-06-24--07-07.
- TPEx official records cover every 6547 grid with five-minute matching on 2025-01-16--02-07 and 2026-03-25--04-09, and every 6596 grid with five-minute matching on 2025-05-15--05-28.
- Because the stop kind is `PROVIDER`, this heartbeat did not retry FinMind. The existing `finmind` heartbeat was updated for 00:55 Asia/Taipei so the next run can confirm the exact live checkpoint and resume the same deterministic job once, without repeating the calendar or any checkpointed symbol-day.

## 2026-08-27 00:55 same-job provider recovery

- Live SQLite remained unchanged at 2,968 durable partitions and `6754 / 2023-11-16`; old session 81526 is closed. This establishes a single-writer-safe recovery boundary after the previous HTTP 502.
- Sole replacement session 65950 resumed the same deterministic job and checkpointed `6754 / 2023-11-16` first as `READY` with 39 bars. No calendar or earlier symbol-day was requested again.
- Initial audited recovery boundary is 3,030 partitions: 3,022 `READY`, eight expected `EMPTY`, zero `INVALID`, 304,492 bars, next pending `6754 / 2024-02-22`, and 2,786 symbol-days remaining. Audit is 3,030/3,030 with zero issues and SQLite `quick_check=ok`.
- A later audit reached 3,228/3,228 partitions and 314,119 bars with zero issues. The final live status reached 3,242 `READY`, eight expected `EMPTY`, zero `INVALID`, exact next pending `6754 / 2025-01-14`, and 2,566 symbol-days remaining while session 65950 continued.
- The sandboxed process-list query failed because macOS `sysmond` was unavailable; managed-session closure plus stable SQLite checkpoint provided the non-mutating single-writer evidence instead.

## 2026-08-27 01:55 completion and next diversified tranche

- Sole replacement writer session 65950 completed deterministic job `finmind-sponsor-f9f1b8a5d0b7fb85` without repeating its sealed calendar or any earlier checkpoint. The replacement spent exactly 2,848 KBar requests. Final state is 5,800 `READY`, sixteen expected `EMPTY`, zero `INVALID`, 599,453 bars, and no next pending; full offline audit verified 5,816/5,816 partitions with zero issues and SQLite `quick_check=ok`.
- Per-symbol results are 1444 727 READY / 79,795 bars; 4764 719 READY plus eight EMPTY / 35,535; 6547 727 / 120,606; 6596 727 / 64,170; 6754 727 / 20,349; 6763 719 READY plus eight EMPTY / 70,468; 6869 727 / 96,191; and 9802 727 / 112,339.
- Official daily and suspension evidence reconciles all sixteen EMPTY partitions. For 4764, two dates are zero-volume and six contain only non-price activity. For 6763, 2023-10-03 contains only non-price activity; the seven dates from 2024-08-29 through 2024-09-06 have no official daily trade row because TPEx announcement 證櫃監字第11300074961號 suspended trading while the par value changed from NT$10 to NT$1 and shares were exchanged, with trading resumed on 2024-09-09.
- Raw timestamp inspection classified 254 exact 14/15/53/54-row observations: 170 irregular natural sparse sessions, 39 five-minute grids, and 45 twenty-minute grids. Official TWSE/TPEx disposition records cover every fixed grid for 4764, 6547, 6596, 6754, 6763, and 6869; no grid indicates missing minute data.
- Aggregate usable coverage excluding quarantined 7610 is now 445 complete symbols, 323,515 partitions, 322,928 `READY`, 587 expected `EMPTY`, zero `INVALID`, and 50,934,890 bars.
- The next established diversified tranche is 1203 (`食品工業`, listed 1964-08-24), 2227 (`汽車工業`, 2004-12-21), 2937 (`居家生活類`, 2017-06-08), 4147 (`生技醫療業`, 2015-11-23), 5878 (`金融業`, 2014-10-28), 6165 (`數位雲端`, 2003-08-04), 8171 (`綠能環保類`, 2011-12-19), and 9960 (`運動休閒類`, 2004-12-06). Every sealed official listing date predates the frozen start.
- Deterministic job `finmind-sponsor-864f26b849120817` was created in status-only mode with zero provider requests. Sole writer session 6930 sealed one 727-day calendar and received an official-positive preflight of 3,584 requests.
- Exact audited handoff reached 289 partitions: 281 `READY`, eight `EMPTY`, zero `INVALID`, 2,868 bars, exact next pending `1203 / 2024-10-29`, and 5,527 symbol-days remaining. Audit passed 289/289 with zero issues and SQLite `quick_check=ok`; the writer continued after the snapshot.
- The existing `finmind` heartbeat was updated through the Codex app manager, read back from disk, and scheduled for 02:55 Asia/Taipei with session 6930, the new job, single-writer protection, official-positive-only requests, full timeout backoff, and all no-trading boundaries.

## 2026-08-27 02:55 completion and data-quality pause

- Sole writer session 6930 completed deterministic job `finmind-sponsor-864f26b849120817` at 5,606 `READY`, 210 provider `EMPTY`, zero recorded `INVALID`, 278,545 bars, and no next pending. Whole-job accounting is exactly one calendar plus 5,816 KBar requests: the initial positive batch consumed 3,584 requests including the calendar, and the next positive release consumed the remaining 2,233 KBar requests.
- Per-symbol results are 1203 716 READY plus eleven EMPTY / 8,336 bars; 2227 727 / 17,177; 2937 662 READY plus 65 EMPTY / 4,078; 4147 727 / 107,417; 5878 621 READY plus 106 EMPTY / 2,669; 6165 727 / 77,770; 8171 727 / 52,812; and 9960 699 READY plus 28 EMPTY / 8,286.
- Full offline audit verified 5,816/5,816 stored partitions with zero structural/digest issues and SQLite `quick_check=ok`. All 207 exact 14/15/53/54-row observations are irregular natural sparse sessions; there is no five- or twenty-minute fixed grid requiring disposition reconciliation.
- Official exchange daily rows were found for all 210 provider EMPTY dates. Of these, 168 are zero-volume and 41 contain only non-price activity with no OHLC. Those 209 dates are expected EMPTY checkpoints.
- The remaining date is a genuine source mismatch: TPEx's official regular-market daily close table, explicitly excluding negotiated fixed-price trading, records `9960 / 2026-03-20` at OHLC 22.90, 1,000 shares, NT$22,900, and one transaction. The sealed FinMind response for the same symbol-day is HTTP 200 / payload 200 with `{"msg":"success","status":200,"data":[]}`, recorded as EMPTY with raw payload SHA-256 `bd3deae97b9bbf5496db1c19da707df924ec244a8568f606429c0a6532ddca72`.
- No minute bar can be reconstructed safely because the official daily row does not provide the trade timestamp. The checkpoint was not repeated, no synthetic bar was created, and no next provider job was started.
- SQLite mechanically reports 453 complete symbols because EMPTY is a terminal checkpoint, but usable coverage must quarantine 9960 until the mismatch is resolved. Excluding 7610 and 9960, usable coverage is 452 complete symbols, 328,604 partitions, 327,835 READY, 769 expected EMPTY, zero INVALID, and 51,205,149 bars. The unadjusted mechanical totals are 453 symbols, 329,331 partitions, 328,534 READY, 797 EMPTY, zero INVALID, and 51,213,435 bars.
- Candidate ranking remains available for a future explicitly authorized continuation, but the acquisition is safely paused with no active writer due to the data-quality rule.
- The obsolete `finmind` heartbeat was deleted through the Codex app automation manager after this immutable mismatch was confirmed; no automatic retry or follow-up remains scheduled.

## 2026-08-27 source-repair workflow implementation

- User chose to build a source-repair workflow rather than resume acquisition. The workflow must preserve the immutable FinMind EMPTY response, keep official discrepancy evidence separate, and reject any attempt to turn a daily OHLC row without timestamps into a minute bar.
- The repair target begins with `9960 / 2026-03-20`, but the implementation should be generic at `(job_id, symbol, session_date)` grain and remain separate from formal immutable Dataset/backtest authority.
- Implemented `backtest/finmind_source_repair.py` as append-only repair tables plus a four-stage lifecycle: `QUARANTINED`, `PENDING_REVIEW`, `APPROVED`, and `ACTIVE`. Case, evidence, review, and activation IDs are content-derived; raw and canonical evidence are independently digested and audited.
- `scripts/manage_finmind_source_repair.py` provides `open-case`, `propose-minute`, `review`, `activate`, `status`, and `audit` operations without any FinMind provider call. Daily evidence can only open/quarantine a case. Minute candidates must be non-empty, ordered, unique, timezone-aware, minute-aligned, within observable regular-session bounds, use `COMMON_LOTS`, preserve the close-times-volume amount proxy, and match the exact target.
- `backtest/finmind_snapshot.py` now fails closed on any non-active case by excluding the whole symbol with `SOURCE_REPAIR_PENDING`. An active overlay replaces only the effective partition stream, adds full source/review/activation lineage to snapshot identity, and marks the Dataset with `ALTERNATE_SOURCE_REPAIR`; original acquisition rows remain untouched.
- Registered live case `finmind-repair-9f08aa0024440e4601ac` for `9960 / 2026-03-20` using normalized TPEx daily reconciliation evidence `research/finmind_source_repair_9960_20260320_tpex_daily_v1.json`. Its state is `QUARANTINED`, candidate/review/activation are null, and active bar count is zero.
- Live repair audit is one verified case, zero issues, zero active bars. The acquisition audit remains 5,816/5,816 verified partitions and 278,545 bars with zero issues. SQLite `quick_check=ok`, and the original partition remains `EMPTY`, zero bars, raw digest `bd3deae97b9bbf5496db1c19da707df924ec244a8568f606429c0a6532ddca72`, canonical digest `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
- Focused verification passed 51 tests across repair lifecycle, Sponsor acquisition, and immutable FinMind snapshot behavior. Python compile validation and scoped diff whitespace validation also passed.

## 2026-08-27 timestamped alternate-source discovery

- A repository-wide exact text search for `9960` together with `2026-03-20`, excluding the immutable FinMind database and the already sealed daily discrepancy artifact, found only tests, documentation, and planning references. It found no raw tick, raw Kbar, timestamped minute, CSV, JSONL, or capture artifact for the target symbol-day.
- The local file inventory exposes only the FinMind Sponsor SQLite authority, one old FinMind plan copy, the current materialized FinMind Dataset, the backtest metadata database, unrelated market-event captures, and backtest result JSONL files. No separate Shioaji historical-bar database or raw capture file is present in the workspace.
- Repository code confirms a Shioaji historical Kbar path exists, including dedicated raw capture/reconciliation scripts, but that path constructs a provider and therefore requires a Shioaji market-data login. Credential presence is not evidence, and no login has been attempted under this phase.
- Environment inspection also identified configured PostgreSQL authorities, but configuration alone does not establish that either database stores independent historical minute evidence. The next read-only check must inspect schemas and target rows without printing credentials or changing database state.
- The existing materialized Dataset is a 5.5 GB FinMind artifact created before the 9960 tranche. Its manifest's `observed_symbols` and `requested_symbols` omit 9960, so it cannot supply the missing target minute even though its general date calendar includes 2026-03-20.
- Read-only inspection of `data/backtest/finmind_plans/g3_20260823T1730+0800/source.sqlite3` found zero target rows in both attempts and partitions. Read-only inspection of the live Sponsor database found exactly the known FinMind attempt/EMPTY partition and the quarantined repair case, not an independent alternate-source bar.
- `data/backtest/backtest.sqlite3` contains backtest metadata/results tables and no table at a `(symbol, session_date/timestamp)` historical-bar grain. Thus none of the three local SQLite stores yields alternate timestamp evidence.
- The configured PostgreSQL backtest authority was inspected with an explicit read-only transaction. Its only persisted historical payload table is `backtest.backtest_history_partitions` at `(job_id, symbol, start_date, end_date)` with a `bars_payload`; no partition covering `9960 / 2026-03-20` exists. There are also zero backtest decisions for that symbol-day and zero trades for 9960.
- The existing Shioaji capture scripts are genuinely data-only in application behavior (`subscribe_trade=False`, no order construction), but they still instantiate and log in to the market-data provider before querying `Shioaji.kbars`. This is the first locally implemented path capable of returning an actual timestamp, and it remains behind an explicit external-login authority boundary.
- TPEx's current official OpenAPI inventory exposes daily close quotes, market rankings/statistics, intraday-trading eligibility/statistics, historical suspensions, block-trade data, and price-distribution data. It does not advertise a public historical regular-market trade-timestamp, tick, or one-minute endpoint.
- TPEx's official trading-system documentation says the exchange distributes real-time trade information and five-second snapshots during the live session. Its data-service page classifies delayed/realtime information as information products, while the public historical-stock-price route described by TPEx remains daily history. This distinguishes the existence of exchange timestamps from public historical retrieval of the 2026-03-20 event.
- The official Swagger JSON itself rejected direct retrieval with HTTP 403 in the web tool; no hidden endpoint was assumed. The indexed official endpoint inventory is therefore sufficient only for a negative capability finding, not proof that TPEx never licenses archived tick data.
- Fugle's official Historical Candles contract is a viable licensed alternate source: it accepts `timeframe=1`, returns ISO 8601 minute timestamps with timezone, covers listed/OTC one-minute history from 2023-05-23, and is updated after each trading day. Therefore `9960 / 2026-03-20` is within its documented minute-history window.
- This workspace already contains a credentialed Fugle historical-candle capture and cross-provider qualification workflow. A secret-safe environment-name check establishes that `FUGLE_API_KEY` is configured; the value itself is not eligible evidence and must never be persisted. This route is market-data-only and does not require broker/account/order authority.
- The current Shioaji documentation independently confirms Kbars provide timestamped OHLCV plus actual Amount and allow start/end date ranges up to 30 days, but Shioaji remains the fallback because it requires a provider login. Fugle can be attempted first with materially narrower authority.
- Prior repository controls establish Fugle's timestamp semantics and quality limits rather than granting blanket source authority. On fixed controls, Fugle start labels correspond to Shioaji observable minute-end labels after a +1 minute shift except the 13:30 close; OHLC matched, TPEX control volume matched exactly, but one TWSE control differed by eight lots and a different mismatch target returned empty. The prior result therefore remained `REJECTED_FOR_MISMATCH_RESOLUTION` globally.
- For this repair, Fugle must be judged only as a new immutable candidate for `9960 / 2026-03-20`: raw HTTP bytes must be sealed first, then the session's source totals must reconcile to the TPEx daily row (OHLC 22.90, one lot, NT$22,900), timestamps must survive the established label conversion, and no approval/activation may be inferred from the capture.
- The repair registry accepts only `OBSERVABLE_MINUTE_END` canonical bars in `COMMON_LOTS`. Fugle raw rows are start-labelled, so a candidate builder must preserve raw bytes while deterministically converting each non-13:30 label by +1 minute and retaining 13:30 unchanged. The source URI and conversion contract must be frozen in the evidence lineage.
- A PM safety gate was issued after the configured Fugle credential value appeared in tool output. That credential is now prohibited for any request, and using Shioaji or another credential as a bypass is also prohibited. The viable Fugle capability finding remains, but acquisition is blocked until the owner rotates the key and explicitly resumes the flow.
- The offline candidate normalizer and capture command were added before the safety gate. They contain only environment-variable names and public endpoint contracts; no credential value is embedded. They must remain unexecuted against the network until rotation is complete.
- At `2026-08-27T09:42:55+08:00`, the owner confirmed the Fugle key was rotated and explicitly resumed this one target. A secret-free rotation record now binds the case, prior block digest, environment-variable name, and resume status; the capture command requires this record and persists only its canonical digest.
- Exactly one Fugle request was issued after rotation. It returned HTTP 200 with one raw minute row: source timestamp `2026-03-20T10:55:00+08:00`, OHLC all 22.9, volume one common lot, and average 22.9. Raw response SHA-256 is `a02cc385e76125beb54db2ad74f427ce9a17c7ce41661b29574345815f2b3a6f`.
- Fugle omitted the requested `turnover` field, so the initial strict validator sealed the capture as `REJECTED` with zero canonical candidate bars. This is a validator-contract issue, not an empty provider response or mismatch in timestamp/OHLC/volume.
- No second request is needed or allowed. TPEx already proves exactly one regular-market transaction, OHLC all 22.90, 1,000 shares, and NT$22,900. Because Fugle supplies exactly one flat-price one-lot bar, the amount is unambiguously `22.9 * 1,000 = 22,900`; an offline candidate may use this special proof only while explicitly recording that source turnover was absent.
- The established Fugle label alignment converts the 10:55 start label to canonical observable minute end `10:56+08:00`. The original 10:55 source timestamp remains immutable in the raw evidence.
- The amended offline validator is deliberately narrow: absent turnover is acceptable only when TPEx reports exactly one transaction, Fugle returns exactly one bar, that bar has flat OHLC, and `close * lots * 1,000` exactly equals official amount. Missing turnover for multiple transactions remains rejected.
- Offline tests pass 15/15 across Fugle normalization and the source-repair lifecycle. The sealed raw response derived candidate `fugle-source-repair-candidate-9960-20260320-v1` contains one canonical `10:56+08:00` bar and passed every OHLC, one-lot/1,000-share, NT$22,900, timezone, session-bound, uniqueness, and lineage check.
- Derived candidate canonical-bars SHA-256 is `ebd88a7487cab63d7ff08810798f48ae5d9c57fff558cd6111c7143d2eaa51f9`; it references raw SHA-256 `a02cc385e76125beb54db2ad74f427ce9a17c7ce41661b29574345815f2b3a6f` and does not rewrite the initially rejected capture artifact.
- The candidate was proposed as evidence `finmind-repair-evidence-ac310a47f4e804507a79`. The case is now `PENDING_REVIEW`; reviewer ID, review ID, activation ID, and active bars remain absent.
- Post-proposal repair audit verifies 1/1 case with zero issues and state count `PENDING_REVIEW: 1`. The original FinMind partition remains immutable `EMPTY`, zero bars, with its exact original raw/canonical digests. SQLite `quick_check=ok`.
- The combined Fugle normalization, source-repair, Sponsor acquisition, and FinMind snapshot regression suite passes 58/58. Snapshot semantics therefore remain fail-closed: 9960 stays excluded until a separately approved and activated overlay exists.
- PM review handoff was independently confirmed from read-only SQLite. Case `finmind-repair-9f08aa0024440e4601ac` is `APPROVED`; review `finmind-repair-review-f28f1fdb50e78806a1df` has decision `APPROVE`, reviewer `Codex PM independent review`, and references the exact candidate raw/canonical digests.
- Read-only lineage verification passed all nine checks: approved state, review link, approval decision, review digest binding, raw digest, canonical digest, one-bar count, zero activation/active bars, and unchanged original FinMind partition. Issue count is zero and SQLite `quick_check=ok`.
- The approval rationale explicitly states `PM review only; no activation authority granted.` Therefore the case remains excluded with `current_activation_id=null`, activation count zero, and active bar count zero until a separately named owner-authorized actor and change note are supplied.
- Owner later supplied the exact activation authority with `actor=stevehuang-work` and an explicit change note. The resulting activation is `finmind-repair-activation-83ca14d4d3d0ca89ac42`; live case state is `ACTIVE`, repair audit is 1/1 with zero issues, active bar count is one, and SQLite `quick_check=ok`.
- Activation did not overwrite the acquisition checkpoint. The original `9960 / 2026-03-20` FinMind row remains `EMPTY`, zero bars, raw SHA-256 `bd3deae97b9bbf5496db1c19da707df924ec244a8568f606429c0a6532ddca72`, canonical SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
- PM has now authorized the next stage: use the existing formal snapshot/Dataset seam to create one new immutable artifact that actually consumes the ACTIVE overlay. This does not authorize another activation, any provider request, broker/order path, mutation of an existing immutable snapshot, commit, or push.
- The existing formal seam is `scripts/materialize_finmind_backtest_dataset.py`: `--plan` creates a new SQLite online backup plus content-addressed snapshot plan, and `--execute` materializes a new immutable Dataset without PostgreSQL writes unless the separately gated `--activate-default` flag is supplied.
- Required identity is available without invention: live source `data/finmind_sponsor/history.sqlite3`; sealed reference locator `data/finmind_sponsor/universes/raw/TaiwanStockInfo_0353f33f0b2f36a12bf0c9d30a802423352ba460f6e113012e7ff5f32b5315ad.json.gz`; owner-confirmed actor `stevehuang-work`; and CLI-generated `planned_at`/content digests. `--activate-default` will not be used.
- The prior immutable Dataset remains at `dataset-finmind-sponsor-sha256-88712...` with 182 symbols and 28,325,340 bars. It is an immutable baseline and will not be modified; the new artifact must receive a distinct content-derived Dataset ID and include repair lineage.
- Phase 81 planning completed successfully from a fresh SQLite online backup. The planned immutable Dataset identity is `dataset-finmind-sponsor-sha256-4defb3967d4e89f87d920197877358a8237cdf9baa51be1001fb156b70310ce4`, with 453 included symbols, 51,213,436 effective bars, one excluded symbol, plan identity digest `290d5dc5d224b39483ac87af711efca581c53dd9323ccdd9b6f6979700a8d674`, and actor `stevehuang-work`.
- The final immutable manifest reports storage `JSONL_FULL_V1`, timestamp-symbol ordering, manifest digest `367f81246977646798837d39b4e5bc8a0246877caa7543b3a8b209a753fe02dc`, bars digest `eadccfdac14d116af25bb089689f23c104a2fdb78ae6ea1d331b8a44a46817dc`, 453 requested/observed symbols, 51,213,436 bars, and explicit `ALTERNATE_SOURCE_REPAIR` issue lineage.
- Both the live acquisition database and copied snapshot pass `quick_check=ok` and contain the identical ACTIVE case/evidence/review/activation digest chain. In both stores, the original FinMind target remains `EMPTY`, zero bars, with raw digest `bd3deae...ca72` and canonical digest `4f53cda1...b945`.
- The published `bars.jsonl` contains exactly one 9960 row for 2026-03-20, at line 43,502,747: `10:56+08:00`, OHLC 22.9, volume one common lot, amount proxy 22.9, market TPEX. The subsequent full source-stream/materialized-payload equality audit completed successfully.
- The idempotent saved-plan execution re-opened the frozen source snapshot and the already published Dataset, revalidated semantic identity, then compared every source bar against every materialized bar. It completed with exit 0 at exactly 51,213,436 bars and returned the same Dataset ID, manifest digest, bars digest, and plan identity digest. This is the full stream/materialization consistency gate; no second Dataset was created.
- Offline recomputation of the deterministic review and activation projections produced full digests `f28f1fdb50e78806a1df0d84d15faf94d36eaa28cd8c1cf685d49cd734367dae` and `83ca14d4d3d0ca89ac42e154f3e6031a9a00c502806aee8f7efb2b39228acfed`; each existing ID exactly matches the corresponding first 20 digest characters.
- Final repair audit is 1/1 verified cases, one ACTIVE bar, zero issues. No temporary Dataset directory remains; planning-file whitespace checks pass. Snapshot-plan file SHA-256 is `010d7b814e912258c88fd6f7a0b6972eaf31d31a8ee3e11f8525438e7a131b5b`; final manifest file SHA-256 is `d8b7426abe0b2da6bbc16b8a579fb6f3db47cda504b05da0ab16aa35ee7e5c07`.
- The next unfinished acquisition step is not another automatic writer. After PM review, perform an offline rerank of the sealed 2026-08-20 market-value/current-industry artifacts against the live completed-symbol set; exclude all 453 included symbols, ETFs, recent/incomplete listings, mixed-market 7610, and any SQLite-completed candidates; verify official pre-window listing dates; then create the next diversified eight-symbol deterministic job in status-only mode. Any provider run still requires its separate positive-usage preflight stage.

## Phase 82 offline rerank evidence

- PM disposition is Phase 81 `APPROVE`, P1=0 and P2=0. The bounded next-stage authority is offline rerank plus exactly one status-only job; it does not authorize a provider request or job execution.
- Reused only the sealed FinMind raw artifacts `TaiwanStockMarketValue_06d1...32b2.json.gz` and `TaiwanStockInfo_0353...315ad.json.gz`. Market-value date is 2026-08-20.
- Reused the existing local official company snapshots `/private/tmp/finmind_twse_company_20260825.json` (1,095 rows, SHA-256 `efdb1688c5683a6574c84ec93af90e95715f0d454ca2a6daaab584f776272f69`) and `/private/tmp/finmind_tpex_company_20260825.json` (890 rows, SHA-256 `4f055c3c035d84c75b299211f36ef2dbe01b700c58c2115aeb6630c7628ce835`). Both provide explicit official listing dates, so there is no missing-evidence blocker.
- The exclusion union contains 454 symbols: all 453 immutable-Dataset requested symbols, all 426 symbols from SQLite jobs marked `COMPLETED`, and mixed-market 7610. The SQLite-completed set adds no symbol beyond the Dataset set except the separately excluded 7610.
- Applied the repository's current-identity rules, positive integer market value, four-digit common-stock and TWSE/TPEx filters, non-company/ETF exclusions, official listing date earlier than 2023-08-19, broad-industry alias normalization, then ranked broad industries by current Dataset coverage and candidates by descending sealed market value.
- Selected exactly eight distinct broad industries: 4114 健喬 (`生技醫療`, TPEx, listed 2003-05-12), 4438 廣越 (`紡織纖維`, TWSE, 2016-10-18), 1603 華電 (`電器電纜`, TWSE, 1968-06-03), 1718 中纖 (`化學`, TWSE, 1963-12-02), 1536 和大 (`汽車`, TWSE, 2001-09-17), 1702 南僑 (`食品`, TWSE, 1973-05-30), 2901 欣欣 (`貿易百貨`, TWSE, 1976-05-07), and 2607 榮運 (`航運業`, TWSE, 1990-12-14). Official and FinMind names/markets agree for all eight.
- None of the eight overlaps any existing FinMind history job. The frozen config sorts them as 1536, 1603, 1702, 1718, 2607, 2901, 4114, 4438 and deterministically projects full config SHA-256 `3fb900f8f272077e5af478103b0af7075da9f5d87be9e197dd174a82b1f6c009`, job ID `finmind-sponsor-3fb900f8f272077e`.
- The sole authorized status-only command returned exit 0 and created exactly that job as `QUEUED`. Its `trading_dates_json`, calendar SHA/payload, and status message are null; it has zero trading dates, zero partitions, zero attempts, and zero recorded data requests. Therefore no provider call or acquisition execution occurred.
- Read-only post-create verification found exactly one matching job row with the expected sorted symbols, source/version/date range/calendar symbol and `COMMON_LOTS` volume unit. SQLite `quick_check=ok`; the focused no-calendar reconcile regression passed 1/1; planning whitespace validation passed.

### Phase 82 errors

- The first local official-snapshot type summary called `__name__` on a string expression and raised `AttributeError`; a different row-by-row parser then verified both files without changing any state.

### Phase 82 PM request changes

- PM independently reproduced the official snapshot hashes/counts, rerank result, exclusion union, config/job identity, exact QUEUED row, zero children, SQLite integrity, and all 13 FinMind history regressions. There is no P1 and one P2 only.
- The P2 is durability: `/private/tmp` official bytes and selector code cannot support future inspection, while the SQLite job row stores only final config. Remediation must bind durable source bytes, exact selector/alias/exclusion/ranking inputs, selected evidence, existing job state, and fail-closed tamper verification into one content-addressed bundle.

### Phase 82 durable selection provenance

- Copied the already verified official bytes without transformation into `data/finmind_sponsor/universes/official/twse/company_efdb1688c5683a6574c84ec93af90e95715f0d454ca2a6daaab584f776272f69.json` and `data/finmind_sponsor/universes/official/tpex/company_4f055c3c035d84c75b299211f36ef2dbe01b700c58c2115aeb6630c7628ce835.json`. Byte comparison and SHA-256 both reproduce the PM-approved source digests and row counts of 1,095 and 890.
- Sealed `data/finmind_sponsor/universes/selections/phase82_selection_e9faeaddafc8a81b60289b07ec56571615b623b80f9d7a8d47912e7bf4af7d97.json`. Its self-digest is `e9faeaddafc8a81b60289b07ec56571615b623b80f9d7a8d47912e7bf4af7d97` and its size is 44,624 bytes.
- The bundle binds the canonical selector/alias contract; both sealed FinMind raw paths, compressed and raw-body digests, and row counts; both official source paths/digests/counts; approved Dataset ID plus manifest/bars/source-snapshot/plan digests; all 66 completed job bindings; the exact 426 completed-symbol set; the exact 453 Dataset symbols; mixed-market 7610; and the exact 454-symbol exclusion union with independent digests.
- Full offline reproduction finds 1,284 eligible candidates and 29 ranked broad-industry leaders, then selects 4114, 4438, 1603, 1718, 1536, 1702, 2901, and 2607 in ranking order. Their listing evidence, official names/source labels, FinMind identity, market value, industry coverage, and ranking fields are all sealed.
- The reproduced sorted job config has SHA-256 `3fb900f8f272077e5af478103b0af7075da9f5d87be9e197dd174a82b1f6c009` and job ID `finmind-sponsor-3fb900f8f272077e`. Live read-only verification still reports `QUEUED`, null calendar/SHA/payload/status message, zero partitions, zero attempts/recorded requests, and SQLite `quick_check=ok`.
- `scripts/verify_finmind_selection_bundle.py` verifies the bundle self-digest/filename, every referenced file byte digest and row count, Dataset manifest semantic digest, snapshot-plan digests, exclusion/job bindings, reranked candidates and selected order, config/job identity, and exact live zero-child state. It returned `VERIFIED`.
- Focused offline tests reject tampered official bytes, alias-map changes, exclusion-set changes, and selected-order changes. The combined new bundle suite plus existing Sponsor history suite passes 18/18; Python compilation and scoped whitespace validation also pass.
- No calendar was sealed, no job child was created, and no FinMind/Fugle/Shioaji/provider, activation, PostgreSQL/default binding, broker/order, commit, push, PR, or merge action occurred.

### Phase 82 PM re-review approval

- PM independently reverified the durable official bytes, canonical bundle self-digest, physical bundle file digest `ef9a1b60a1397c1ee619404e88cc4c321fd9dbcb605c87e43ff4371dd356e677`, repository verifier output, all 18 focused tests, compilation/whitespace checks, and the exact live zero-child job state.
- Final disposition is Phase 82 `APPROVE`, P1=0 and P2=0. The prior provenance blocker is resolved.
- Approval covers only the completed offline provenance/status-only stage. It does not authorize calendar sealing, a usage/provider request, job execution, activation, PostgreSQL/default binding, broker/order work, commit, push, PR, or merge.
- The workflow is stopped at the owner-authority gate. Any acquisition must explicitly name job `finmind-sponsor-3fb900f8f272077e`, the calendar/provider scope, request limits/pacing, checkpoint/timeout behavior, and the continued no-broker/no-order boundary.

## Phase 83 acquisition preflight

- Owner supplied the exact required authority for job `finmind-sponsor-3fb900f8f272077e`; scope is only the eight bound symbols and frozen 2023-08-19 through 2026-08-18 window.
- Read-only process inspection confirms no existing `download_finmind_sponsor_history.py` writer. Live SQLite remains `QUEUED` with null calendar fields, zero partitions, zero attempts, and `quick_check=ok`.
- The downloader calls `FinMindApiClient.usage()` before changing the job to `RUNNING` or requesting a calendar. A zero official allowance therefore pauses without calendar/provider data requests. With positive allowance, it seals the 2330 calendar before requesting the first pending symbol-day.
- `continuous-hourly` handles official rolling quota waits, but a transport error returns a provider stop. The controlling task must distinguish timeout/connection-reset text, wait a full 60 seconds, then restart the same deterministic job; other provider/auth/data-quality errors must stop.

## Phase 83 acquisition result

- The single authorized writer completed without timeout, connection reset, quota wait, auth failure, provider failure, or data-quality stop. Official preflight was `user_count=0`, `api_request_limit=6000`, `remaining=6000`; the run spent exactly 5,817 requests: one calendar plus 5,816 symbol-days.
- Final job state is `COMPLETED`, `next_pending=null`, 5,802 `READY`, fourteen checkpointed `EMPTY`, zero `INVALID`, and 676,190 bars. All 5,816 partitions passed the offline raw/canonical replay audit with zero issues; SQLite `quick_check=ok`.
- The fourteen EMPTY partitions are six consecutive 2607 dates from 2025-09-25 through 2025-10-03 and eight isolated low-liquidity 2901 dates: 2023-10-17, 2024-07-15, 2024-09-24, 2024-12-17, 2025-03-04, 2025-10-22, 2025-11-27, and 2025-12-19. All share the canonical empty-list digest and source empty-response digest; none was re-requested.
- A first bounded local-evidence search found no already sealed 2607/2901 daily reconciliation artifact. The broad search accidentally matched very large unrelated one-line institutional/capture artifacts and produced truncated output; it changed no state and will not be repeated. Subsequent checks must use scoped file/schema queries.
- TWSE `STOCK_DAY` rows reconcile all eight 2901 EMPTY dates. Each official row has shares, amount, and transaction count but `--` for open/high/low/close, so these are non-price-only sessions rather than missing minute data.
- TWSE monthly daily data has no 2607 row for the six intervening trading dates. The official reduction-recovery table records 2607 榮運 resuming on 2025-10-07 after `退還股款`, with the last pre-suspension detail date 2025-09-24; this exactly spans the six EMPTY dates from 2025-09-25 through 2025-10-03.
- Raw timestamp cadence classification covered every READY partition with exactly 14/15/53/54 rows: 115 observations total, 95 irregular natural sparse sessions, ten fixed five-minute sessions, and ten fixed twenty-minute sessions. All fixed sessions belong to 1718.
- TWSE's official disposition table records 1718 first disposition from 2026-06-08 through 2026-06-22 with approximately five-minute matching, and second disposition from 2026-07-07 through 2026-07-20 with approximately twenty-minute matching. These dates exactly explain the twenty fixed-grid observations; no unexplained cadence anomaly remains.
- Phase 83 is therefore data-quality clean: all 14 EMPTY partitions have official reasons, all fixed grids have official disposition support, offline audit remains 5,816/5,816 with zero issues, and SQLite `quick_check=ok`.

### Phase 83 independent PM approval

- PM independently verified the live job, an offline audit from a consistent SQLite backup, the exact deterministic config digest, request/partition/bar totals, integrity status, and absence of a downloader process. Final disposition is `APPROVE`, P1=0 and P2=0.
- The Phase 82 selection bundle is immutable pre-acquisition provenance. Its verifier correctly detects that the bound `QUEUED`/zero-child target row changed after Phase 83; this expected drift is not an acquisition failure, but that verifier cannot be cited as current post-acquisition-state validation.
- Owner direction is to leave the completed acquisition stopped. No next job, next batch, successor Dataset materialization, or Dataset activation is authorized or planned.
