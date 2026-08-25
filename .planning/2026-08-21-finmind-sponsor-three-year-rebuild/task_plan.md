# Task Plan: FinMind Sponsor three-year intraday rebuild

## Goal

Use the FinMind Sponsor 6,000-request hourly allowance to build a durable, resumable three-year Taiwan equity one-minute history across current large-cap industry representatives, in paced verified batches that never spend requests on already checkpointed symbol-days.

## Current Phase

Phase 44 — 2026-08-25 checkpoint-safe continuation

## Phases

### Phase 1: Existing contract and runtime audit

- [x] Confirm the frozen date range, universe source, FinMind entitlement evidence, credential presence, and current persisted data.
- [x] Trace existing FinMind probes, historical download contracts, repository storage, and safe additive seams.
- [x] Confirm the official live allowance endpoint and its fail-closed use without exposing credentials.
- **Status:** complete

### Phase 2: Resumable FinMind acquisition path

- [x] Add a Sponsor-compatible symbol-day downloader with durable checkpoints.
- [x] Normalize source bars to the repository's canonical minute-bar contract while retaining raw provenance.
- [x] Make retries idempotent and record empty/provider-error partitions separately.
- [x] Add focused tests before any large live batch.
- **Status:** complete

### Phase 3: Today's paced live batch

- [x] Run a credential/entitlement preflight with the smallest possible API cost.
- [x] Start conservative batches bounded by today's available allowance and a reserve margin.
- [x] Persist after each symbol-day and stop cleanly on rate-limit, auth, network, or data-quality failures.
- **Status:** complete

### Phase 4: Verification and handoff

- [x] Audit saved partitions for unique `(symbol, timestamp)`, monotonic timestamps, OHLC validity, volume validity, session bounds, and expected coverage.
- [x] Report exact requests spent, symbol-days completed, usable bars, empty/error partitions, next checkpoint, and remaining three-year work.
- [x] Leave a safe continuation command; do not start formal validation/OOS backtests.
- **Status:** complete

### Phase 5: Cross-industry large-cap universe

- [x] Verify the current FinMind market-cap and industry-classification datasets and their request semantics.
- [x] Build a reproducible universe that excludes the already completed 2317 and 2330, then chooses large-cap representatives across distinct industries.
- [x] Seal the selection date, source fields, exclusions, ranking rule, and selected symbols so the tranche can be reproduced.
- **Status:** complete

### Phase 6: Today's diversified acquisition tranche

- [x] Recheck the live allowance and calculate a request budget that keeps the agreed reserve.
- [x] Create or resume the deterministic diversified job and download only as many complete symbols as today's safe budget permits.
- [x] Persist every symbol-day immediately and stop cleanly on any provider or validation failure.
- **Status:** complete

### Phase 7: Diversified-tranche verification and handoff

- [x] Audit every saved partition and reconcile provider usage with local request accounting.
- [x] Report completed industries, partial or pending industries, exact bars and checkpoints, and the safe continuation command.
- [x] Re-run focused and repository verification in proportion to any code changes.
- **Status:** complete

### Phase 8: Remaining industry leaders

- [x] Continue the other 33 missing industry leaders with direct quota probing so every released request can be used without waiting on the slower usage endpoint.
- [x] Keep each continuation deterministic and resumable; never re-request a completed symbol-day.
- [x] Stop only on provider rejection or data-quality evidence requiring review, not because a daily total was assumed.
- **Status:** complete

### Phase 9: Full cross-industry audit

- [x] Audit every completed industry job and reconcile local request/bar counts.
- [x] Report exact industry coverage, expected suspensions/empty dates, and any remaining gaps.
- **Status:** complete

### Phase 10: Additional mega-cap allowance use

- [x] Add 2454, 3711, 2303, 2882, 2412, and 2383 as complete three-year histories beyond the 40-industry cohort.
- [x] Use the exact remaining hourly allowance to checkpoint the first 321 trading days of 3037 without quota-error probes.
- [x] Audit all 4,683 new symbol-day partitions and retain the deterministic `3037 / 2024-12-13` continuation point.
- **Status:** complete

### Phase 11: Resume additional mega-cap acquisition

- [x] Resume job `finmind-sponsor-9554ffeb898c161b` from `3037 / 2024-12-13` without re-requesting its 1,048 checkpoints.
- [x] Complete 3037, then select the next highest-market-value non-cohort common stocks from the sealed 2026-08-20 snapshot.
- [x] Use the available rolling 6,000/hour allowance without repeated quota-error probes, preserving a deterministic checkpoint if the window ends mid-symbol.
- [x] Audit every new partition and report the new completed/partial stock coverage and exact bar totals.
- **Status:** complete

### Phase 12: Scheduled hourly continuation

- [x] Restore the isolated plan and confirm job `finmind-sponsor-eecae66e2b50523c` is safely paused at 299/727 checkpoints through 2024-11-12.
- [x] Resume only from `1301 / 2024-11-13` and complete 1301 without re-requesting its 299 sealed symbol-days.
- [x] Select established non-ETF large caps from the sealed 2026-08-20 snapshot, excluding recent listings, 7610, and every complete symbol, while preferring additional industry diversity.
- [ ] Use the available 6,000/hour allowance without quota-error probes, audit every new partition, and preserve an exact next checkpoint if the window ends mid-symbol.
- [x] Report updated complete/partial coverage, request accounting, partition states, bar totals, audit results, and the next safe continuation point.
- **Status:** paused — third same-class provider transport timeout; exact next pending `2615 / 2024-08-14`

### Phase 13: Transport-backoff continuation

- [x] Re-read the isolated planning files and confirm job `finmind-sponsor-472eca821ebe93e4` remains at `2615 / 2024-08-14` with 2,420 sealed partitions.
- [x] Adopt the user's explicit retry policy: after a transport timeout, retain the checkpoint, wait a full 60 seconds, and resume the same deterministic job instead of ending the run.
- [x] Continue the existing eight-symbol job without re-requesting completed symbol-days until it completes or an auth, quota, or data-quality stop requires handling.
- [x] Audit all newly written partitions, reconcile any new `EMPTY`/`INVALID` observations, and report exact request, bar, coverage, and next-pending totals.
- **Status:** complete

### Phase 14: Remaining rolling allowance

- [x] Select the next established non-ETF high-market-value symbols from distinct detailed industries in the sealed snapshot: 3443 創意 (`半導體業`) and 8046 南電 (`電子零組件業`).
- [x] Use the currently released allowance on a deterministic two-symbol job, applying the same 60-second transport-timeout backoff and per-symbol-day checkpoint contract.
- [x] Audit every new partition, reconcile any `EMPTY`/`INVALID`, and preserve the exact next checkpoint if the allowance ends during 8046.
- **Status:** complete

### Phase 15: Next rolling large-cap pair

- [x] Select 2886 兆豐金 (`金融保險`) and 3231 緯創 (`電腦及週邊設備業`) from the sealed 2026-08-20 snapshot, excluding all complete symbols.
- [x] Start the deterministic two-symbol job and continue using released allowance with the 60-second transport-timeout backoff.
- [x] Audit all new partitions, reconcile `EMPTY`/`INVALID` and disposition grids, and preserve the exact next checkpoint at the budget edge.
- **Status:** complete

### Phase 16: Highest remaining established pair

- [x] Complete 2884 玉山金 (`金融保險`) and 5274 信驊 (`半導體業`) from the sealed snapshot, excluding recent IPO 7769.
- [x] Reconcile the sole 2884 `EMPTY` session to the official 2025-11-05 material-information suspension and verify the full job offline.
- **Status:** complete

### Phase 17: Computer and component depth

- [x] Complete 2395 研華 (`電腦及週邊設備業`) and 2368 金像電 (`電子零組件業`) without duplicate symbol-day requests.
- [x] Audit all 1,454 partitions and confirm zero `EMPTY`, `INVALID`, or digest issues.
- **Status:** complete

### Phase 18: Financial and semiconductor depth

- [x] Complete 2890 永豐金 (`金融保險`) and 6223 旺矽 (`半導體業`) through rolling-quota waits.
- [x] Audit all 1,454 partitions and preserve the 2025-04-07 sparse source observations without fabricating bars.
- **Status:** complete

### Phase 19: Additional cross-industry depth

- [x] Complete 1519 華城 (`電機機械`), 2618 長榮航 (`航運業`), and 3665 貿聯-KY (`其他電子業`).
- [x] Reconcile the sole 3665 `EMPTY` session and all fixed 54/15-bar blocks to official TWSE suspension and disposition evidence.
- [x] Audit all 2,181 partitions and report the new aggregate complete-symbol coverage.
- **Status:** complete

### Phase 20: Additional financial and component pair

- [x] Complete 2880 華南金 (`金融保險`) and 4958 臻鼎-KY (`電子零組件業`) while consuming every released rolling request.
- [x] Audit all 1,454 partitions and reconcile 4958's fixed five-minute grid to the official 2026-05-28 through 2026-06-10 disposition period.
- **Status:** complete

### Phase 21: Additional financial and semiconductor pair

- [x] Complete 2883 凱基金 (`金融保險`) and 6488 環球晶 (`半導體業`) from the sealed market-value ranking.
- [x] Audit all 1,454 partitions and reconcile 6488's fixed five-minute and twenty-minute grids to official TPEX/TAIFEX disposition evidence.
- **Status:** complete

### Phase 22: Exact allowance-edge continuation

- [x] Start 2892 第一金 (`金融保險`) and 6274 台燿 (`電子零組件業`) in one-shot mode so the current allowance ends at an explicit checkpoint rather than an indefinite rolling wait.
- [x] Spend the exact 546-request preflight budget: one calendar plus 545 `READY` KBar partitions for 2892.
- [x] Audit the partial job and preserve exact next pending `2892 / 2025-11-17`; 909 symbol-days remain.
- **Status:** paused at exact rolling-budget edge

### Phase 23: Immediate rolling-quota continuation

- [x] Resume only job `finmind-sponsor-66b204f6b4e79082` at `2892 / 2025-11-17` without re-requesting its 545 sealed symbol-days.
- [x] Finish 2892, then finish 6274 using `max_requests=6000`, zero reserve, 0.25-second pacing, and rolling-hour waits.
- [x] On transport timeout, preserve the exact checkpoint, wait 60 seconds, and retry; stop separately for auth, quota-control, or data-quality conditions.
- [x] Audit every new partition and update exact request, READY/EMPTY/INVALID, bar, complete-symbol, partial-symbol, and next-pending totals.
- **Status:** complete

### Phase 24: Next eight-industry depth tranche

- [x] Start an established-stock job for 3189, 5880, 2313, 4938, 2609, 2404, 2409, and 1504, representing eight distinct detailed industries.
- [x] Consume released rolling allowance with zero reserve and 0.25-second pacing, checkpointing every symbol-day before the next request.
- [x] Apply the user-directed 60-second transport-timeout backoff without hiding auth, quota-control, or data-quality stops.
- [x] Audit the accumulated job, reconcile any EMPTY/INVALID or fixed-grid sessions, and report the exact next checkpoint if incomplete.
- **Status:** complete

### Phase 25: Continued eight-industry depth tranche

- [x] Start a deterministic job for 8299, 2801, 3044, 2356, 8069, 3702, 6139, and 1513, representing eight distinct detailed industries.
- [x] Use every released rolling request with zero reserve and 0.25-second pacing while persisting every symbol-day first.
- [x] On transport timeout, retain the exact checkpoint, wait 60 seconds, and resume; keep auth, quota-control, and data-quality conditions explicit.
- [x] Audit all accumulated partitions and preserve the exact next pending if this continuation remains partial.
- **Status:** complete

### Phase 26: Further diversified large-cap tranche

- [x] Start a deterministic job for 2379, 5347, 2376, 5876, 6213, 2633, 2347, and 2027 across eight distinct detailed industries.
- [x] Continue with 6,000 maximum requests, zero reserve, 0.25-second pacing, and checkpoint-first persistence across rolling releases.
- [x] On transport timeout, wait 60 seconds and resume the exact pending partition; stop explicitly for auth or data-quality failures.
- [x] Audit completed or partial partitions, reconcile source-observed EMPTY/INVALID and fixed-grid periods, and preserve the exact next pending.
- **Status:** complete

### Phase 27: Consume the remaining rolling allowance

- [x] Start the next deterministic eight-industry job for 3034, 6415, 2324, 2834, 3533, 2049, 1102, and 2610.
- [x] Spend the currently released allowance at checkpoint-first symbol-day boundaries with max 6,000, zero reserve, and 0.25-second pacing.
- [x] Audit the bounded partial job and report its exact next pending for the next rolling window.
- **Status:** complete

### Phase 28: Continue with the next diversified large-cap tranche

- [x] Re-rank the sealed 2026-08-20 market-value and current-industry snapshot after excluding all 117 complete symbols, rejected 7610, ETFs, and recent listings.
- [x] Select established unused symbols 3661, 3081, 5289, 2492, 2812, 2474, 8996, and 5434 across eight distinct detailed industries.
- [x] Continue checkpoint-first acquisition with 6,000 maximum requests, zero reserve, 0.25-second pacing, and rolling hourly resume.
- [x] Audit completed or partial partitions, reconcile source-observed exceptions, and preserve the exact next pending.
- **Status:** complete

### Phase 29: Spend subsequent rolling releases on another diversified tranche

- [x] Select established unused symbols 6770, 6442, 3026, 8210, 6196, 1560, 2838, and 1476 across eight distinct detailed industries after excluding recent listings and all 125 complete symbols.
- [x] Complete all 5,816 symbol-days with checkpoint-first persistence and no duplicate requests.
- [x] Audit every partition and reconcile fixed-grid sessions to official TWSE disposition periods.
- **Status:** complete

### Phase 30: 2026-08-23 scheduled continuation

- [x] Re-read the isolated planning files and verify the heartbeat's `1301 / 2024-10-15` checkpoint against SQLite before any provider request.
- [x] Reject the stale continuation point because job `finmind-sponsor-eecae66e2b50523c` is already `COMPLETED` at 727/727 partitions.
- [x] Select established unused high-market-value symbols from the sealed 2026-08-20 market-value and industry artifacts, excluding ETFs, recent listings, rejected 7610, and all 133 complete symbols.
- [x] Acquire only uncheckpointed symbol-days with the existing checkpoint-first downloader and the zero-reserve 6,000/hour rolling policy.
- [x] Audit every new partition, reconcile provider exceptions, and report the exact aggregate and next pending.
- [x] Spend the final 183 released requests on the next eight-industry tranche and preserve its exact rolling-boundary checkpoint.
- **Status:** paused at exact rolling-quota boundary

### Phase 31: 2026-08-23 manual rolling-quota resume

- [x] Re-read the isolated plan and verify job `finmind-sponsor-9e38dda7585f527f` remains paused at `2337 / 2024-05-22` with 182 sealed symbol-days.
- [x] Resume only uncheckpointed symbol-days with max 6,000 requests, zero reserve, 0.25-second pacing, and the user-directed 60-second transport-timeout backoff.
- [x] Complete and audit the current eight-industry job, then use any remaining released allowance on another established diversified large-cap tranche without quota-error probes.
- [x] Reconcile new EMPTY/INVALID or fixed-grid observations, update exact aggregate coverage, and preserve the next pending checkpoint.
- **Status:** paused at exact rolling-quota boundary

### Phase 32: 2026-08-23 checkpoint-safe continuation

- [x] Re-read the referenced task and isolated planning records, then verify the active SQLite job without provider access.
- [x] Confirm job `finmind-sponsor-f9728f6f8f43c270` remains at 182 `READY` partitions, 43,903 bars, and exact next pending `2385 / 2024-05-22`.
- [x] Resume only uncheckpointed symbol-days using max 6,000 requests, zero reserve, 0.25-second pacing, and official usage preflight polling.
- [x] If a transport timeout occurs, retain the exact checkpoint, wait a full 60 seconds, and retry the same job; pause safely for auth, quota-control, provider, or data-quality failures.
- [x] Audit new partitions, reconcile source-observed exceptions, and report the exact aggregate coverage and next checkpoint.
- **Status:** paused at exact rolling-quota boundary; next pending `2006 / 2025-02-25`

### Phase 33: 2026-08-23 second checkpoint-safe continuation

- [x] Re-read the isolated planning records and verify job `finmind-sponsor-cbd9954018dc7546` remains at 365 `READY` partitions, 69,568 bars, and exact next pending `2006 / 2025-02-25`.
- [x] Avoid a second writer by moving the pending heartbeat later than the immediate manual resume.
- [x] Resume only uncheckpointed symbol-days with positive official usage preflight, max 6,000, zero reserve, 0.25-second pacing, and 10-second quota polling.
- [x] Apply the full 60-second retry delay only after a transport timeout; pause safely for auth, quota-control, provider, or data-quality failures.
- [x] Audit all new partitions, reconcile source exceptions and fixed grids, and preserve the exact next checkpoint.
- **Status:** paused at exact rolling-quota boundary; next pending `1785 / 2025-11-20`

### Phase 34: 2026-08-23 16:32 scheduled continuation

- [x] Re-read the isolated planning records, run session catch-up, and verify the SQLite job, audit, and exact pending partition without provider access.
- [x] Resume only uncheckpointed symbol-days in job `finmind-sponsor-ffbf4a85539d9edc` using positive official usage preflight, max 6,000, zero reserve, 0.25-second pacing, and 10-second polling.
- [x] After a transport timeout, preserve the checkpoint, wait a full 60 seconds, and retry the same job; pause separately for auth, quota-control, provider, or data-quality failures.
- [x] Audit all new partitions, reconcile EMPTY/INVALID and fixed grids, update aggregate coverage, and preserve the exact next checkpoint.
- **Status:** paused at exact rolling-quota boundary; next pending `2850 / 2023-08-25`

### Phase 35: 2026-08-23 23:20 manual continuation

- [x] Re-read the referenced task and complete isolated planning records, run session catch-up, and verify the live SQLite checkpoint without provider access.
- [x] Resume only uncheckpointed symbol-days in job `finmind-sponsor-d561ed5fd6d7a9bd` from exact next pending `2850 / 2023-08-25` using positive official usage preflight and the 6,000/0/0.25/10-second policy.
- [x] After a transport timeout, preserve the exact checkpoint, wait a full 60 seconds, and retry the same job; pause separately for auth, quota-control, provider, or data-quality failures.
- [x] Audit all new partitions, reconcile new `EMPTY`/`INVALID` and fixed grids, update aggregate usable coverage, and preserve the exact next checkpoint.
- **Status:** completed; no next pending

### Phase 36: 2026-08-24 rolling-window continuation

- [x] Create deterministic job `finmind-sponsor-e7bed6eb88f4fd81` for established distinct-industry symbols 6531, 3042, 5522, 1477, 9941, 2206, 2312, and 8926 without making a provider request.
- [x] Use the official positive preflight remainder exactly: one calendar plus 914 KBar requests, with zero reserve, 0.25-second pacing, and no quota-error probe.
- [x] Complete 1477 and advance 2206 only through its durable 2024-05-28 checkpoint; do not request any pending symbols after the initial budget edge.
- [x] Reuse only newly released positive official allowance to finish all remaining dates without repeating the calendar or prior partitions.
- [x] Audit all 5,816 partitions, reconcile fixed grids and isolated exact-count sessions, and update aggregate usable coverage.
- **Status:** completed; no next pending

### Phase 37: 2026-08-24 second rolling-window tranche

- [x] Select established unused symbols 3260, 1815, 1319, 1210, 1773, 2352, 2540, and 3563 across eight distinct detailed industries from the sealed 2026-08-20 snapshot.
- [x] Confirm every candidate's official ISIN listing date predates the frozen 2023-08-19 start.
- [x] Create deterministic job `finmind-sponsor-51388b566e74d689` and spend exactly one calendar plus 1,097 KBar requests from positive official preflights.
- [x] Complete 1210 and advance 1319 through 2025-03-04 with a durable checkpoint after every symbol-day.
- [x] Audit all 1,097 partitions, confirm zero EMPTY/INVALID/fixed-grid observations, update aggregate coverage, and preserve the exact next checkpoint.
- **Status:** paused at exact positive-preflight boundaries; next pending `1319 / 2025-03-05`

### Phase 38: 2026-08-24 checkpoint-safe continuation

- [x] Re-read the referenced task and complete isolated planning records, then run session catch-up.
- [x] Verify job `finmind-sponsor-51388b566e74d689`, its audit, SQLite integrity, and exact pending partition without provider access.
- [x] Resume only uncheckpointed symbol-days from `1319 / 2025-03-05` with positive official usage preflight, max 6,000, zero reserve, 0.25-second pacing, and 10-second quota polling.
- [x] If a transport timeout occurs, preserve the exact checkpoint, wait a full 60 seconds, and retry the same job; pause separately for auth, quota-control, provider, or data-quality failures.
- [x] Audit every new partition, reconcile source exceptions and fixed grids, update aggregate coverage, and preserve the exact next checkpoint.
- **Status:** complete; no next pending

### Phase 39: 2026-08-24 remaining positive allowance

- [x] Re-rank the sealed 2026-08-20 market-value and current-industry snapshots after excluding 205 complete symbols, rejected 7610, ETFs, and recent/incomplete listings.
- [x] Select established symbols 1722, 2923, 3714, 9921, 5903, 9933, 8415, and 2464 across eight distinct detailed industries and verify official listing dates before the frozen start.
- [x] Create deterministic job `finmind-sponsor-4cb46283cc3a19e3` without provider access, then spend only positive official allowance with checkpoint-first persistence.
- [x] After the transport reset, preserve the exact checkpoint, wait a full 60 seconds, and resume the same job at `2464 / 2023-10-11` without repeating its calendar or 761 completed symbol-days.
- [x] Complete and audit all 5,816 partitions, reconcile every `EMPTY` and fixed-grid observation to official exchange evidence or irregular raw timestamps, and update aggregate coverage.
- **Status:** complete; no next pending

### Phase 40: 2026-08-24 final released allowance

- [x] Re-rank the sealed 2026-08-20 market-value/current-industry snapshot after excluding all 213 complete symbols and recent/ineligible listings.
- [x] Select established unused symbols 2539, 4766, 1409, 6116, 9939, 2015, 8070, and 3596 across eight distinct industries; verify each official listing date predates 2023-08-19.
- [x] Create deterministic job `finmind-sponsor-3709bd4ca4276f5b` without provider access and spend the exact 943-request official positive preflight remainder with checkpoint-first persistence.
- [x] Audit all 942 partial partitions, reconcile 1409's official five-minute disposition block and 2015's isolated irregular sessions, and preserve exact next pending `2015 / 2024-07-09`.
- **Status:** paused at exact positive-preflight boundary; next pending `2015 / 2024-07-09`

### Phase 41: 2026-08-24 stale-heartbeat reconciliation and live continuation

- [x] Reject the heartbeat's obsolete `finmind-sponsor-ffbf4a85539d9edc` continuation point after live SQLite proves that job is already complete; use SQLite rather than planning text as acquisition authority.
- [x] Resume only job `finmind-sponsor-3709bd4ca4276f5b` at `2015 / 2024-07-09`, spend 4,874 checkpointed KBar requests, and complete all 5,816 partitions without repeating its calendar or prior 942 symbol-days.
- [x] Audit the completed job, reconcile 6116's fixed five-/twenty-minute blocks to official TWSE disposition periods, and classify isolated exact-count dates in 2015, 2539, and 4766 by irregular raw gaps plus zero-row official disposition responses.
- [x] Re-rank the sealed 2026-08-20 snapshot after excluding 221 complete symbols and ineligible listings; verify official pre-window listing dates for 1736, 2504, 2851, 3019, 3090, 4583, 6592, and 6789.
- [x] Create deterministic job `finmind-sponsor-991a2e7af862a395`, then spend two official positive preflight releases as one calendar plus 696 checkpointed KBar requests without a quota-error probe.
- [x] Audit all 696 partial partitions, preserve exact next pending `1736 / 2026-07-06`, and verify aggregate counts plus SQLite `quick_check`.
- **Status:** paused at official rolling-window boundary; next pending `1736 / 2026-07-06`

### Phase 42: 2026-08-24 21:03 checkpoint-safe continuation

- [x] Re-read the referenced task and planning records, run session catch-up, and preserve the unrelated dirty worktree.
- [x] Verify job `finmind-sponsor-991a2e7af862a395`, its 696-partition audit, SQLite integrity, request ledger, and exact next pending without provider access.
- [x] Resume only uncheckpointed symbol-days from `1736 / 2026-07-06` using positive official usage preflight and the 6,000/0/0.25/10-second settings.
- [x] Preserve the exact `2851 / 2024-01-19` checkpoint after the transport timeout, wait more than 60 seconds, and resume the same job without repeating completed symbol-days.
- [x] Complete and audit all 5,816 partitions, reconcile the one official 3090 suspension and every fixed-grid observation, and update aggregate coverage.
- **Status:** complete; no next pending

### Phase 43: 2026-08-25 remaining-positive-allowance continuation

- [x] Re-rank the sealed 2026-08-20 market-value and current-industry snapshots after excluding 229 complete symbols, recent/ineligible listings, and quarantined 7610.
- [x] Select 3532, 6670, 2211, 2498, 5371, 3010, 1215, and 2903 across eight distinct industries and verify all listing dates predate 2023-08-19.
- [x] Create deterministic job `finmind-sponsor-5631808b9766f955` without provider access and spend the exact 1,743-request official positive preflight as one calendar plus 1,742 checkpointed KBar requests.
- [x] Audit all 1,742 partial partitions, reconcile 1215's three isolated 53/54-bar sessions to irregular raw gaps plus a zero-row official disposition response, and verify aggregate coverage plus SQLite integrity.
- **Status:** paused at exact positive-preflight boundary; next pending `2498 / 2024-10-28`

### Phase 44: 2026-08-25 checkpoint-safe continuation

- [x] Re-read the referenced task and complete isolated planning records, run session catch-up, and verify live SQLite remains authoritative.
- [ ] Resume only job `finmind-sponsor-5631808b9766f955` from exact next pending `2498 / 2024-10-28` using positive official usage preflight and the 6,000/0/0.25/10-second settings.
- [ ] If a transport timeout occurs, preserve the exact checkpoint, wait a full 60 seconds, and retry the same job; stop separately for auth, quota, provider, or data-quality failures.
- [ ] Audit every new partition, reconcile any `EMPTY`/`INVALID` and fixed-grid observations, update aggregate coverage, and preserve the next exact checkpoint.
- **Status:** in progress

## Decisions Made

| Decision | Rationale |
|---|---|
| Keep this plan isolated and do not change `.planning/.active_plan` | Another referenced task is actively modifying the backtest memory path in the same checkout. |
| Reuse the previously frozen three-year request unless repository evidence supersedes it | Prevent date/universe drift while rebuilding deleted data. |
| Spend quota only after local idempotency and validation tests pass | Today's Sponsor allowance is limited and should not be burned on repeated or corrupt downloads. |
| Keep FinMind partitions source-distinct | FinMind and Shioaji have different provider identities and must not be silently mixed. |
| Preserve research-only boundaries | Data acquisition does not authorize live trading or formal holdout evaluation. |
| Select representatives from current source data | The cross-industry universe must be reproducible and not based only on remembered company size. |
| Prefer whole-symbol completion within today's budget | A fully audited three-year representative is more useful than many partially downloaded symbols, while the job remains resumable for the rest. |
| Use 2308, 2881, 1303, 2382, and 2345 for the first diversified tranche | These are the five highest-current-market-value leaders from industries not already represented by completed 2317/2330. |
| Continue beyond the first five with direct quota probes | The usage endpoint takes several seconds and can underuse a rolling 6,000/hour allowance; after the initial check, the data endpoint is the authoritative quota signal and checkpoints make retries safe. |
| Replace 7610 with 8422 in the formal cohort | 7610 was still Emerging Stock Board during part of the requested history; 8422 is the highest-market-value same-industry candidate with full normal-market history. |
| Treat fixed five-minute grids as valid when they match disposition periods | TWSE disposition securities are legitimately matched about every five minutes; sparse rows must not be fabricated into one-minute bars or rejected as provider aggregation. |
| Spend the final 1,049-request allowance on 2383 then 3037 | This completed the higher-market-value stock first and left a deterministic partial checkpoint for the next window. |
| Skip recent IPO 7769 in the resumed three-year tranche | TWSE lists its first trading date as 2025-11-27, so it cannot supply the requested full three-year normal-market history. |
| Use the final 280 requests on 1301 after completing 2357, 2887, and 3045 | This used the allowance exactly while leaving a durable `1301 / 2024-10-15` continuation point across four additional industry exposures. |
| Retry transport timeouts after a full 60-second backoff | The user explicitly requested uninterrupted continuation; durable symbol-day checkpoints make a delayed retry idempotent while avoiding immediate hammering of the provider. Auth, quota, and data-quality stops remain separate conditions. |
| Use the final 183-request allowance on 2337 before the other seven Phase 30 continuation symbols | One calendar plus 182 KBar calls uses the full 6,000-request window without a quota-error probe and leaves a deterministic checkpoint for the next scheduled run. |
| Use the final 366-request allowance on 2353 in the next eight-industry job | One calendar plus 365 KBar calls consumes the authoritative preflight remainder exactly, avoids a quota-error probe, and leaves deterministic next pending `2353 / 2025-02-25`. |
| Use the final 366-request allowance on 2006 in the next eight-industry job | After completing and auditing the prior job, one calendar plus 365 KBar calls uses the remaining authoritative preflight allowance exactly and leaves deterministic next pending `2006 / 2025-02-25`. |
| Use subsequent rolling releases to complete `finmind-sponsor-3b89b912c38e836b`, then spend the final 183 requests on 2385 | Official usage preflight avoids 402 probes, completes the second job, and leaves deterministic next pending `2385 / 2024-05-22` in the third eight-industry job. |
| Use the final 549-request allowance on a new eight-industry job beginning with 1785 | One calendar plus 548 KBar requests spends the full positive official allowance without a quota-error probe and leaves exact next pending `1785 / 2025-11-20`. |
| Use the final 732-request allowance on the next eligible eight-industry job beginning with 2597 | One calendar plus 731 checkpointed KBar calls uses the full positive official allowance, completes 2597, and leaves exact next pending `2850 / 2023-08-25` without a quota-error probe. |
| Use the remaining 915-request allowance on the next eight-industry job beginning with 1477 | One calendar plus 914 checkpointed KBar calls consumes the authoritative preflight remainder exactly, completes 1477, and leaves exact next pending `2206 / 2024-05-29` without a quota-error probe. |
| Consume only rolling releases to finish `finmind-sponsor-e7bed6eb88f4fd81`, then use the next 1,098 requests on a new eight-industry job | Positive official preflights complete eight symbols, then one calendar plus 1,097 KBar calls completes 1210 and leaves deterministic next pending `1319 / 2025-03-05`; total turn usage is exactly 12,000 successful requests without a quota-error probe. |
| Resume `finmind-sponsor-4cb46283cc3a19e3` after the connection reset instead of creating another job | The first 761 symbol-days and calendar were already durable; a full 60-second backoff followed by the same deterministic command resumed exactly at `2464 / 2023-10-11` and avoided duplicate requests. |
| Treat live SQLite as authoritative when a heartbeat carries a stale checkpoint | The stale job was already complete; reconciling before provider access prevented duplicate data requests and safely advanced the actual paused job. |
| Use only the 214- and 483-request official positive releases for the new job | The provider's usage preflight, not arithmetic from the preceding batch, defines the safe rolling-window allowance; both releases were exhausted without a quota-error probe. |
| Spend the 1,743-request positive remainder on the next eight-industry job beginning with 1215 and 2211 | One calendar plus 1,742 KBar calls uses the authoritative allowance exactly, completes two symbols, and leaves deterministic next pending `2498 / 2024-10-28` without a quota-error probe. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `read_thread` rejected `turnLimit=12` because the maximum is 10 | 1 | Re-read the referenced task with `turnLimit=10`. |
| `read_thread` rejected `turnLimit=40` because the maximum is 10 | 1 | Re-read the referenced task with `turnLimit=10`; no workspace or provider state changed. |
| Multi-file Phase 23 completion patch used a stale aggregate line | 1 | Re-read the exact planning tails and split the update into narrow patches; the failed patch changed no files. |
| Sparse-partition query referenced non-existent `raw_row_count` and `canonical_row_count` columns | 1 | Read the table schema and re-ran the read-only query with `bar_count`; no database state changed. |
| Two initial sealed-snapshot `jq` joins changed scope before indexing candidate `stock_id` | 1-2 | Bound the completed-symbol array and each candidate ID explicitly; the corrected read-only join returned the ranked unused candidates. |
| Two read-only status queries assumed summary-only job/partition column names | 1 each | Read the SQLite schemas and re-ran the queries with persisted columns plus derived checkpoint counts; no database state changed. |
| First 2026-08-23 read-only `jq -s` candidate join referenced `.[2]` after changing the pipeline scope | 1 | Bind the completed-symbol input before transforming the stock-info stream, then rerun the local-only join; no provider request or file write occurred. |
| Direct web fetch of the TWSE OpenAPI company endpoint was rejected as unsafe and the TPEx OpenAPI endpoint returned 403 | 1 | Use indexed official TWSE company PDFs and official ISIN/listing pages instead; no FinMind request was involved. |
| Opening the full official ISIN listed-company page exceeded the web tool's 4 MiB response limit | 1 | Query smaller symbol-specific TWSE/TPEx official pages rather than downloading the full table through the web tool. |
| Sandboxed `curl` could not resolve the official ISIN host | 1 | Re-ran the same read-only official request with approved network access. |
| The ISIN HTML has its full table on one line, so contextual `rg` emitted a huge truncated line | 1 | Extract only the two target `<tr>` rows with a bounded non-greedy parser before decoding the legacy encoding. |
| Web open rejected parameterized TWSE/TPEx historical and disposition JSON endpoints as unsafe | 1 | Use approved read-only `curl` against the same official endpoints and emit only bounded JSON rows. |
| Assumed the r2 2330 capture prefix was `finmind_03`; the file does not exist | 1 | List the immutable capture manifest/files first, then inspect the exact referenced filename. |
| Static-tool discovery searched a non-existent `Makefile` together with valid paths | 1 | Use the repository's actual `pyproject.toml` configuration and direct test/static commands. |
| Ruff flagged the CLI's intentional post-`sys.path` import as E402 | 1 | Mark that repository-standard bootstrap import with a narrow `# noqa: E402`. |
| Two initial multi-file Ruff-fix patches had malformed or stale hunk context | 1-2 | Re-read the exact plan tail and applied a minimal patch; neither failed attempt changed files. |
| First live preflight could not resolve FinMind hosts inside the restricted network sandbox | 1 | Re-ran the same verified command with approved network access; no data request was spent by the failed DNS attempt. |
| Local `sqlite3 -readonly` option could not open the WAL database in this CLI build | 1 | Re-ran the same `SELECT` statements without that unsupported option; the statements themselves were read-only. |
| 2330/2025-03-24 contained a 13:33 closing bar and failed the initial 09:00-13:30 bound | 1 | Confirmed the TWSE delayed-closing mechanism and the day's 13:33 print; accept only 13:33 as an exceptional close label and revalidate sealed raw bytes without a new request. |
| A batch that completed the final partition on its exact request-budget boundary remained `PAUSED` | 1 | Recompute completion after the loop and mark `COMPLETED` when no symbol-days remain; add an exact-boundary regression assertion. |
| All-market `TaiwanStockMarketValue` returned an empty array when queried as a date range | 1 | Use the documented exact-date all-market query and search backward across a bounded window. |
| Current `TaiwanStockInfo` has repeated aggregate and detailed industry rows, plus some null-date rows | 1-3 | Seal raw metadata, remove aggregate labels when one detailed label exists, and exclude incomplete or truly ambiguous current rows. |
| Some all-market rows have zero `market_value` | 1 | Exclude non-positive values because they cannot qualify as large-cap leaders; retain strict validation for positive non-integral values. |
| 7610/2023-08-22 contained a 13:31 trade because the company was still on the Emerging Stock Board | 1 | Preserve the invalid raw partition, exclude mixed-venue history from this normal-session cohort, and replace it with 8422, the highest-market-value same-industry company with full normal-market history. |
| Direct 0.25-second quota probes accumulated enough expected 402 responses to trigger FinMind's 30-minute IP ban | 1 | Stop immediately on 403, wait the documented 30 minutes, and schedule future probes from locally recorded successful-request timestamps plus a safety margin. |
| Fixed five-minute disposition sessions were briefly suspected to be provider downsampling | 1 | Compared consecutive date blocks with TWSE disposition rules and exact company periods, withdrew the false anomaly, and restored all 88 affected partitions from sealed raw responses without API calls. |
| HTTPS response body read raised an uncaught `TimeoutError` during 2360 acquisition | 1 | Preserve all prior checkpoints, add a narrow transport-timeout wrapper and regression test, then resume the same deterministic job. |
| Network escalation auto-review timed out before the resume process started | 1 | Confirmed no command/API call ran and retried the same approved downloader command once. |
| Ruff is installed on the host rather than inside `.venv` | 1 | Ran the same focused Ruff scope with the available `ruff` executable; all checks passed. |
| Scheduled/manual continuation hit repeated FinMind HTTPS read timeouts | 1-3 | The third occurrence preserved `2615 / 2024-08-14` and its audit stayed clean. After user escalation, change strategy from immediate bounded retries to a full 60-second transport backoff followed by deterministic checkpoint resume. |
| Multi-file planning update used stale status context | 1 | Re-read the exact Phase 12 and log tails, then split the update into narrow patches; the failed patch changed no files. |
| First Phase 30 final-state query assumed a non-existent `download_jobs` table | 1 | Read the SQLite schema and re-ran the same read-only checks against `finmind_history_jobs`, `finmind_history_partitions`, and `finmind_history_attempts`; no database state changed. |
| Codex automation manager did not return for view, schema-probe, or full-update calls | 1-3 | Terminated each hung management call after bounded waits and verified the existing automation file stayed unchanged. Acquisition data and SQLite checkpoints were unaffected; the stale one-shot automation prompt was not falsely reported as updated. |
| First release-delay helper passed a string instead of `Path` to `FinMindHistoryStore` | 1 | Re-ran the same read-only helper with `Path(...)`; no database or provider state changed. |
| Automation update first used unsupported `target_thread_id` and then omitted the required target | 1-2 | Re-ran with the accepted `targetThreadId`; verified the automation file now contains the current job and checkpoint. |
| `pgrep` could not read the process list because the local `sysmond` service is unavailable | 1 | Used the unchanged SQLite `updated_at`, partition counts, and exact checkpoint to verify no scheduled writer had advanced the job; moved the imminent heartbeat before starting the manual writer. |
| Referenced-task read used unsupported `turnLimit=20` | 1 | Retried with the documented maximum of 10; no workspace or provider state changed. |
| Initial TPEx disposal requests used compact `yyyymmdd` dates and silently returned the current default range | 1 per symbol | Read TPEx's official `tables.js`, which formats `data-format=D` fields as `yyyy/mm/dd`, then repeated the read-only official queries with slash-form dates and obtained the requested three-year responses. |
| First automation update omitted the required heartbeat `kind` discriminator | 1 | Repeated the same full update with `kind="heartbeat"`; the app accepted it and the automation file was re-read to verify the new job and checkpoint. |
| Fourth scheduled preflight command mistyped `--reserve-requests` as `--reserve-quests` | 1 | Argparse rejected the command before client construction, so zero provider requests were made; rerun with the existing valid flag. |
| Referenced-task read with explicit `hostId="local"` returned a generic app error | 1 | Retried the same read without the stale host hint; the referenced task loaded successfully and no workspace/provider state changed. |
| Local `ps` process-list check was denied by the managed environment | 1 | Used the unchanged job/partition `updated_at`, exact SQLite checkpoint, and stale one-shot automation file to establish that no scheduled writer advanced the store. |
| First Phase 35 official-usage preflight could not resolve the FinMind host inside the restricted network sandbox | 1 | The failure occurred before any usage/data response or checkpoint write; rerun the same verified command with approved network access. |
| Phase 35 sparse-day helper generated invalid SQLite `IN (15,)` syntax | 1 | The completed offline job audit had already passed; correct the later diagnostic to parameterized predicates before using sparse-day output. No database/provider state changed. |
| Two parallel official TWSE diagnostic curls ran without network escalation and failed DNS resolution | 1 | Re-ran the same read-only official queries with approved network access; no FinMind request, checkpoint, or trading state was involved. |
| Phase 36 automation-manager updates did not return and were terminated after bounded waits | 1-2 | Re-read the persisted automation file after each attempt and confirmed it remained the stale 16:32 one-shot; no raw automation file edit was made and no acquisition checkpoint was affected. |
| A read-only attempt-timestamp query used non-existent `created_at` instead of `requested_at` | 1 | Read the `finmind_history_attempts` schema and reran the query with `requested_at`; no database state changed. |
| Computer Use fallback was not allowed to control the Codex desktop app | 1 | Stopped without UI actions. The stale automation remains unchanged and must not be treated as a valid future continuation; SQLite acquisition state is unaffected. |
| Current continuation first used unsupported `read_thread` `turnLimit=20` | 1 | Re-read the referenced task with the documented maximum of 10; no workspace or provider state changed. |
| Planning session catch-up initially invoked unavailable `python` | 1 | Re-ran the same read-only helper with `python3`; it completed without output and no acquisition state changed. |
| Current fixed-grid diagnostic queried non-existent partition column `status_message` | 1 | Read the live table schema and reran the same read-only query with `error_message`; no database or provider state changed. |
| The live Phase 39 HTTPS read raised uncaught `ConnectionResetError: [Errno 54] Connection reset by peer` after 761 KBar checkpoints | 1 | Preserved the exact durable checkpoint at `2464 / 2023-10-04`, waited a full 60 seconds, and reran the same deterministic job; it resumed at `2464 / 2023-10-11` and completed without duplication. |
| Legacy TPEx daily-close URLs ignored the requested 2023 date and returned the current 2026-08-24 table | 1 | Switched to TPEx's current official `afterTrading/tradingStock` JSON endpoint with `date=2023/09/01&code=5903`; it returned the requested historical month. |
| The Phase 42 live process ended on a FinMind transport timeout after the interactive session was no longer attached | 1 | Live SQLite retained 1,559 `READY` checkpoints and exact next pending `2851 / 2024-01-19`; the full 60-second backoff had elapsed, and offline audit verified every checkpoint before deterministic resume. |
