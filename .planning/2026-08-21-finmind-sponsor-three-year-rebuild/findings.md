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
