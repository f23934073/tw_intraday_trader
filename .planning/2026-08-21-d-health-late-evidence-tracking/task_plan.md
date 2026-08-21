# Task Plan: D-HEALTH-LATE-001 evidence collection automation

## Goal
Build a data-only, multi-symbol Tick/BidAsk late-delivery collector that preserves the current canonical Health contract and produces reproducible per-session and daily evidence without setting policy thresholds.

## Current Phase
Phase 4 — automation and operations

## Phases

### Phase 1: Requirements & Discovery
- [x] Read the D-HEALTH-LATE-001 report and preserve its no-policy-change boundary.
- [x] Trace existing qualification capture, journal, replay, symbol/cohort, and scheduler seams.
- [x] Confirm how a user-owned recurring schedule can safely invoke the collector.
- **Status:** complete

### Phase 2: Contracts & Test Design
- [x] Define a versioned passive-collection manifest and multi-symbol configuration contract.
- [x] Define immutable late-delivery ledger and daily summary schemas; no thresholds or policy verdicts.
- [x] Add contract tests for validation, event analysis, and phase bucketing.
- **Status:** complete

### Phase 3: Passive Collector & Analyzer
- [x] Implement bounded multi-symbol Tick/BidAsk collection using canonical ingress, journal, and exact replay.
- [x] Implement deterministic ledger extraction and daily Tick/BidAsk-by-symbol-by-phase summaries.
- [x] Preserve flags-off, subscribe_trade=false, no order path, and unchanged consumer authority.
- **Status:** complete

### Phase 4: Automation & Operations
- [x] Add a per-window collection runner with explicit market-calendar and frozen-cohort preflight.
- [x] Add a cohort builder that freezes the 6–9 symbol campaign from an official completed-session source.
- [x] Generate and review the three OPEN/MID/CLOSE automation jobs from a frozen cohort.
- [x] Configure user-owned recurring automations after verifying the runner and reviewing the schedule.
- [x] Keep incomplete/missing cohort or failed session artifacts visible; do not retry or select favourable sessions.
- **Status:** complete

### Phase 5: Verification & Delivery
- [x] Run focused regression, CLI help/smoke checks, and cohort artifact validation.
- [x] Record the frozen seven-symbol TWSE cohort and its evidence boundary.
- [x] Verify the first real passive MID artifact after its in-window collector completes.
- [x] Update planning records and deliver commands, artifact locations, and active gates.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Preserve current Health, Admission, Freshness, and watermark semantics | D-HEALTH-LATE-001 is evidence collection, not a policy revision. |
| Use passive collection rather than Case A/B qualification | Natural late delivery must be observed and retained, not used to search for a preferred classification. |
| Separate Tick and BidAsk evidence at every level | Their projection risk differs materially. |
| Fail closed on an incomplete cohort manifest | The report prohibits subjective medium/low liquidity selection. |
| Retain every finalized or incomplete capture outcome | Prevents retry-based selection bias. |
| Build a separate passive collector rather than changing Case A/B | Case classification and the current Health contract remain evidence, not collector success criteria. |
| Use the current feed-native `OUT_OF_ORDER_REJECTED` disposition as the late-delivery signal | It retains the frozen watermark contract and provides prior watermark, projection, Health, and Admission effects. |
| Keep source-regression values signed in the ledger and summarize their magnitude separately | Preserves the evidence while making percentile comparisons meaningful. |
| Treat a valid multi-symbol cohort manifest as a hard prerequisite for scheduling | The requested 6–9-symbol campaign cannot be honestly automated with only the current three high-liquidity seeds. |
| Passive capture completion depends on durable Journal and exact replay, not final Health state | Natural late delivery is the subject of evidence collection; it must remain visible rather than turn a capture into a Case A/B search. |
| Freeze one campaign cohort from an official completed-session quote source | A fixed seed set plus p45/p55 mid and p05/p15 low Trade Value selections reaches seven symbols without subjective picks. |
| Replace the obsolete Case A schedule with three passive evidence schedules | A third Case A retry would violate HQ-INV-002; the new schedules start five minutes before each collection phase. |
| Retain incomplete sessions in the derived daily report | A zero-event rollup must not hide a failed or partial capture; daily evidence v2 names incomplete and replay-failed sessions explicitly. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial automation inspection used `view` instead of the required `mode` discriminator | No automation changed; use `mode: "view"` when inspecting jobs. |
| Second automation inspection omitted the required automation id | No automation changed; create/view calls will be made only after the runner is verified and a schedule name/id is available. |
| One orchestration probe contained invalid JavaScript escaping | No repository file changed; reran the read-only inspection with valid syntax. |
| First direct TWSE cohort query assumed an older `fields/data` response shape | No output artifact was written; extended parser for the current top-level `tables` shape and validated it with a fixture. |
| Initial sandboxed Shioaji capture could not bind its SDK inter-thread descriptor | No session artifact was finalized; reran under user-approved local execution where the data-only capture could run. |
| First real MID passive capture woke just before the phase boundary and was marked `OUTSIDE_COLLECTION_PHASE` | Preserved the INCOMPLETE Journal/report; added an early-wakeup loop (matching the existing qualification harness), covered by a regression test, and did not retry MID. |
