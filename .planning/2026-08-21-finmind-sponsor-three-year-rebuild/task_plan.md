# Task Plan: FinMind Sponsor three-year intraday rebuild

## Goal

Use the FinMind Sponsor 6,000-request hourly allowance to build a durable, resumable three-year Taiwan equity one-minute history across current large-cap industry representatives, in paced verified batches that never spend requests on already checkpointed symbol-days.

## Current Phase

Phase 15 — next rolling large-cap pair

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

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `read_thread` rejected `turnLimit=12` because the maximum is 10 | 1 | Re-read the referenced task with `turnLimit=10`. |
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
