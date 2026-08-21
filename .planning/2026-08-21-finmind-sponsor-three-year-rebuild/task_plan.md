# Task Plan: FinMind Sponsor three-year intraday rebuild

## Goal

Use the FinMind Sponsor 6,000-request hourly allowance to build a durable, resumable three-year Taiwan equity one-minute history across current large-cap industry representatives, in paced verified batches that never spend requests on already checkpointed symbol-days.

## Current Phase

Phase 6 — Today's diversified acquisition tranche

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
- [ ] Create or resume the deterministic diversified job and download only as many complete symbols as today's safe budget permits.
- [ ] Persist every symbol-day immediately and stop cleanly on any provider or validation failure.
- **Status:** pending

### Phase 7: Diversified-tranche verification and handoff

- [ ] Audit every saved partition and reconcile provider usage with local request accounting.
- [ ] Report completed industries, partial or pending industries, exact bars and checkpoints, and the safe continuation command.
- [ ] Re-run focused and repository verification in proportion to any code changes.
- **Status:** pending

### Phase 8: Remaining industry leaders

- [ ] Continue the other 33 missing industry leaders at no more than one data request per second so the 6,000/hour allowance can roll over safely.
- [ ] Keep each continuation deterministic and resumable; never re-request a completed symbol-day.
- [ ] Stop only on provider rejection or data-quality evidence requiring review, not because a daily total was assumed.
- **Status:** pending

### Phase 9: Full cross-industry audit

- [ ] Audit every completed industry job and reconcile local request/bar counts.
- [ ] Report exact industry coverage, expected suspensions/empty dates, and any remaining gaps.
- **Status:** pending

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
| Continue beyond the first five at one request per second | The account limit is 6,000 per hour, not a daily pool; this pace is at most about 3,600 requests per hour and allows continued construction as the window rolls over. |

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
