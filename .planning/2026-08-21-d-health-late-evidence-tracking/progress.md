# Progress Log

## Session: 2026-08-21

### Current Status
- **Phase:** 4 - Automation and operations
- **Started:** 2026-08-21

### Actions Taken
- Read the supplied D-HEALTH-LATE-001 evidence tracking report completely.
- Created this isolated plan to avoid mutating the repository's older root planning files.
- Recorded the hard safety boundary: evidence only; no Health, Admission, Freshness, watermark, or trading-policy modification.
- Traced the existing single-symbol qualification harness, multi-symbol Shioaji stream adapter, Freshness capture, and provenance-backed cohort artifact.
- Confirmed the user-facing automation mechanism is available, but deferred schedule creation until a verified runner exists.
- Confirmed the canonical journal/disposition ordering can be reused directly for deterministic late-delivery analysis.
- Confirmed exact replay accepts multi-symbol reference and bootstrap coverage, allowing a passive collector to use the frozen replay contracts unchanged.
- Completed Phase 1 and fixed the Phase 2 evidence model: ledger rows preserve signed source regression and report semantic effects without a severity verdict.
- Added a versioned six-to-nine-symbol cohort contract that rejects unfrozen or subjective manifests before any provider connection.
- Implemented deterministic extraction from finalized canonical Journals, including Tick/BidAsk totals, per-symbol totals, OPEN/MID/CLOSE totals, signed source regression, receive progression, consecutive count, and the existing projection/Health/Admission effects.
- Implemented the flags-off passive multi-symbol collector. It obtains per-symbol real bootstrap evidence, waits for paired Tick/BidAsk acknowledgements, uses the existing bounded canonical pipeline and durable Journal, then verifies exact replay before writing the session ledger.
- Added a per-window CLI that performs flags/cohort/calendar/phase preflight before connecting and atomically refreshes that date's derived daily report.
- Added an immutable official-TWSE cohort builder. The first live artifact is `research/late_delivery_evidence/cohorts/cohort_2026-08-21_twse_2026-08-20.json`: 2330/2317/2454 fixed high plus 1455/3380 mid and 6918/8367 low, all tied to the 2026-08-20 completed official source digest.
- Paused the obsolete `p1-1b-case-a-qualification` automation so it cannot trigger a prohibited third Case A retry. Created active user-owned local cron automations for OPEN (08:55), MID (10:25), and CLOSE (12:55) on reviewed weekdays.
- The first real MID passive capture was preserved as INCOMPLETE at `records/market_events/2026-08-21/ldev-20260821T102803-mid-5abe35fe`: an early wake just before 10:30 hit an incomplete phase-wait loop. It recorded no market ingress and did not run replay. This is an implementation defect, not a market-data result; the corrected loop now rechecks the clock exactly as the existing qualification harness does. Per policy, MID was not retried.
- Added `late_delivery_daily_cli`; daily evidence v2 explicitly lists INCOMPLETE and replay-failed capture sessions in addition to finalized-session statistics. The regenerated 2026-08-21 report names the incomplete MID session instead of hiding it behind zero totals.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `tests/test_late_delivery_capture.py tests/test_late_delivery_evidence.py` | contract, passive collector, Journal analysis, exact replay | 6 passed | PASS |
| `python -m market_data.late_delivery_capture_cli --help` | CLI imports without provider connection | usage rendered | PASS |
| `tests/test_late_delivery_cohort.py tests/test_late_delivery_capture.py tests/test_late_delivery_evidence.py tests/test_qualification_capture.py tests/test_exact_projection_replay.py tests/test_market_event_journal.py tests/test_market_data_ingestion.py` | passive collector and canonical replay/journal regressions | 51 passed | PASS |
| `python -m market_data.late_delivery_daily_cli --date 2026-08-21` | derived report includes non-finalized session visibility | 0 finalized, 1 incomplete named | PASS |
| `python -m pytest -q` | full repository regression | 984 passed, 2 skipped | PASS |

### Errors
| Error | Resolution |
|-------|------------|
| `automation_update` rejected `view` as an argument name | The API requires `mode`; no automation was created or changed. |
| `automation_update` view mode requires a concrete id | No automation was created or changed; defer schedule creation until the runner is verified. |
| One read-only orchestration call had invalid JavaScript escaping | Reran the inspection with valid syntax; no repository file changed. |
| First multi-symbol collector fixture emitted timestamps out of callback receive order | Corrected only the test fixture to preserve monotonic callback receipt order; retained the source-time late BidAsk case. |
| First direct TWSE cohort fetch assumed a legacy root `fields/data` shape | Live source uses `tables`; added a validated parser branch, then froze the cohort from the official completed-session response. |
| Sandboxed Shioaji SDK capture could not bind its inter-thread descriptor | Reran only the already-approved data-only capture under local execution; the later phase-boundary outcome is recorded separately below. |
| First real passive MID capture hit `OUTSIDE_COLLECTION_PHASE` at a boundary early wake | Preserved its INCOMPLETE Journal and report, wrote the first visible daily outcome, added an early-wakeup regression test and fixed the phase wait loop; did not retry. |
