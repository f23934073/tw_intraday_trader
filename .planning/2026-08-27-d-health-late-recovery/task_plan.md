# Task Plan: D-HEALTH-LATE-001 Evidence Recovery

## Goal

Complete passive late-delivery evidence collection with finalized, replay-verified sessions while preserving frozen market-data, Health, admission, and trading boundaries.

## Current Phase

Phase 2 — Verify the contract-preserving calendar-metadata repair.

## Phases

### Phase 1: Artifact and source diagnosis

- [x] Review the current passive-capture implementation and prior retained reports.
- [x] Identify the exact journal record and adapter condition that makes exact replay reject the 2026-08-27 session.
- [x] Record the smallest contract-preserving remediation.
- **Status:** completed

### Phase 2: Minimal recovery implementation

- [x] Implement only the capture-metadata handling needed for replay correctness.
- [x] Preserve callback quarantine, immutable artifacts, and non-trading authority.
- **Status:** completed

### Phase 3: Verification

- [x] Add or update focused regression tests for the diagnosed condition.
- [x] Run focused and appropriate full regression tests.
- [x] Verify no Health, Admission, watermark, Freshness, or trading-policy change.
- **Status:** completed

### Phase 4: Passive collection automation

- [x] Inspect and repair only the affected recurring passive-capture schedules.
- [x] Verify the automation payload remains flags-off and `subscribe_trade=false`.
- **Status:** completed

### Phase 5: Evidence handoff

- [x] Report retained completed/incomplete artifacts and verification outcome.
- [ ] Await the scheduled real OPEN artifact, then report its immutable result without retrying.
- [ ] Keep Historical Qualification and P1.2 blocked unless their independent gates pass.
- **Status:** in_progress

## Decisions Made

| Decision | Rationale |
|---|---|
| Preserve prior immutable sessions | Failed and replay-rejected captures are evidence, not repair targets. |
| Use callback quarantine rather than suppressing invalid provider input | The capture must remain auditable and must not silently manufacture valid market data. |
| Do not edit `.planning/.active_plan` | It is already changed by unrelated concurrent work. |
| Replace—not modify—the existing 08:55 runtime | The prior runtime is immutable but contained the bug; a new clean, committed runtime was sealed and its LaunchAgent was atomically swapped before it runs. |

## Errors Encountered

| Error | Resolution |
|---|---|
| 2026-08-27 MID replay rejected an event outside the captured session calendar | Diagnose retained records before any code or schedule change. |
| Deployment runtime lacks FastAPI for unrelated API tests | D-HEALTH focused tests pass; the passive capture has no FastAPI dependency. |
| Main workspace full suite has one mutable FinMind bundle drift failure | Preserve and report it as unrelated; it does not affect the D-HEALTH focused test or sealed runtime identity. |
