# Task Plan: PR-TM-012C1 complete data-only runtime

## Goal

Implement the smallest safe, executable C1 path that can collect full-session market evidence before any fill, activate Trade Management only from an observed existing local-paper BUY fill, persist/recover/replay PostgreSQL Shadow evidence, and remain incapable of order execution.

## Current Phase

Phase 7 - Commit packaging complete

## Phases

### Phase 1: Contract and baseline audit
- [x] Inventory current preflight, stream, composition, Journal, recovery, replay, validation, and tests.
- [x] Protect unrelated dirty worktree changes and record exact scope ownership.
- [x] Run focused baseline tests before edits.
- **Status:** completed

### Phase 2: Freeze architecture and failing tests
- [x] Define a session coordinator that opens market capture before 09:00 independently of fill activation.
- [x] Define no-fill `INSUFFICIENT_EVIDENCE` finalization without synthetic fills.
- [x] Add failing tests for C0 authority/identity/session-scoped PostgreSQL.
- [x] Add failing tests for C1 orchestration.
- **Status:** completed

### Phase 3: Implement C0 hardening
- [x] Bind `execution_authority=false` explicitly.
- [x] Replace Git-HEAD-only identity with immutable runtime source identity.
- [x] Scope PostgreSQL cleanliness to the proposed Shadow session/authority.
- **Status:** completed

### Phase 4: Implement executable C1 coordinator and CLI
- [x] Start/ACK data-only stream before open and persist session coverage independently of Thesis activation.
- [x] Observe an existing correlated local-paper BUY fill; never create an order/fill/match/Position.
- [x] Activate the existing operation only after fill and preserve journal backpressure.
- [x] Finalize coverage and, when activated, checkpoint recovery, exact replay, and readiness report.
- [x] Add an executable CLI with immutable artifacts/digests and fail-closed preflight loading.
- **Status:** completed

### Phase 5: Automation-safe execution seam
- [x] Provide a deterministic local invocation seam that does not rely on interactive escalation.
- [x] Keep the existing Codex automation fail-closed until the executable seam is verified.
- **Status:** completed

### Phase 6: Verification and handoff
- [x] Run focused tests, full relevant regression, compilation, CLI help, and whitespace checks.
- [x] Verify no broker/order/CA/trade-callback capability was added.
- [x] Update runbook and automation memory with exact current status.
- **Status:** completed

### Phase 7: Commit packaging
- [x] Re-audit the dirty worktree and exclude callback quarantine, R5, Freshness, and other concurrent changes.
- [x] Stage only the complete C0/C1 runtime, tests, and runbook.
- [x] Verify the exact staged snapshot and create one scoped commit without pushing.
- **Status:** completed

## Success Criteria

- Full-session market coverage can begin before 09:00 with no fill present.
- An existing paper BUY fill can activate Trade Thesis later without changing earlier market evidence.
- No-fill sessions finalize as non-qualifying lifecycle evidence, never as a fake pass.
- Every activated canonical event carries a RiskSnapshot and append failure blocks later processing.
- PostgreSQL recovery digest and exact replay are deterministic for activated sessions.
- C0 proves calendar/provider/database/authority/runtime identity for the proposed session without requiring unrelated Local Paper tables to be globally empty.
- No executable path can submit/cancel an order, create a fill, mutate Position, enable CA, or subscribe to trade callbacks.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Separate session market capture from trade activation | The current fill-first runner cannot cover the 09:00 boundary for normal post-open fills. |
| Keep existing domain and Journal ports | Current pure contracts already cover composition, backpressure, recovery, and replay; avoid a parallel framework. |
| Use tests before implementation | Formal evidence code must fail closed and remain deterministic. |
| Preserve unrelated worktree state | The repository contains extensive concurrent changes outside this task. |
| Bound journal retries on the pending append only | Recovery may resume the next Shadow event, while an outage timeout leaves the session incomplete and blocked. |
| Require distinct Local Paper and Shadow DSNs | One shared PostgreSQL Journal cannot hold two different modes under the same decision session ID. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Automation sandbox cannot reach the current localhost PostgreSQL DSN | Added a fail-closed local CLI seam; deployment still requires an unattended reachable dedicated Shadow DSN. |
| Final full suite saw two backtest migration expectation failures after an unrelated untracked `015_r5_signal_ledger_replays.sql` appeared | Preserved the concurrent R5 work; reran the isolated TM/Journal suite successfully. |
