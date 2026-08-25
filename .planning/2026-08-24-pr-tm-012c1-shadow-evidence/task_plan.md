# Task Plan: PR-TM-012C1 full-session Shadow evidence

## Goal

Collect one immutable, full 09:00-13:30 Taiwan-equity data-only and decision-only Shadow session using only the existing safe C1 runtime, or fail closed with repository-backed blockers.

## Current Phase

Complete - 2026-08-25 BLOCKED before session start

## Phases

### Phase 1: Calendar and C0 preflight
- [x] Verify 2026-08-24 against the reviewed TWSE calendar.
- [x] Locate the existing complete C1 live entrypoint and frozen runbook.
- [x] Verify simulation, trade-subscription, execution authority, execution flag, PostgreSQL DSN/schema, runtime/provider identity, and `READY_FOR_SESSION`.
- **Status:** complete

### Phase 2: Start immutable session
- [ ] Start before 09:00 without code/policy/fixture edits.
- [ ] Confirm only canonical applied events enter Shadow and journal backpressure is fail-closed.
- [ ] Observe existing local-paper BUY fills only; never create a fill or send an order.
- **Status:** complete

### Phase 3: Full-session monitoring
- [ ] Maintain coverage for 09:00-13:30 Asia/Taipei.
- [ ] Preserve journal/session evidence and record any fatal evidence loss.
- **Status:** complete

### Phase 4: Close and qualification checks
- [ ] Finalize after the session boundary.
- [ ] Verify PostgreSQL checkpoint recovery and digest equality.
- [ ] Run historical replay parity and deterministic readiness report.
- **Status:** complete

### Phase 5: Report and automation memory
- [x] Report manifest, identity, counts, lost evidence, parity, recovery, paths, and digests.
- [x] Keep Production Shadow Gate under the existing multi-day policy; never mark PASSED from one day.
- [x] Update automation memory with outcome and run time.
- **Status:** complete

### Phase 6: 2026-08-25 automation run
- [x] Verify 2026-08-25 against the reviewed TWSE calendar before open.
- [x] Re-audit the current checkout for a complete, safe executable C1 entrypoint.
- [x] Run the frozen C0 preflight before 09:00 and preserve its artifact verbatim.
- [x] Start a full session only if every C0 condition and the entrypoint gate pass.
- [x] Report the fail-closed disposition and update automation memory.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Treat today as a formal evidence session once started | Prior reviewed policy makes code, policy, fixtures, and artifacts immutable during collection. |
| Stop at any unmet C0 requirement | The user explicitly requires fail-closed behavior and forbids synthetic or partial substitute evidence. |
| Existing fill observation only | This automation has no authority to create orders, fills, matching, positions, or broker capabilities. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Initial multi-operation planning patch was rejected | Re-applied each existing file as one scoped update. |
| 2026-08-25 sandboxed C0 exited 139 because the Shioaji native SDK could not bind an inter-thread fd | Ran the identical C0 command once outside the sandbox; preserved its formal BLOCKED artifact. |
