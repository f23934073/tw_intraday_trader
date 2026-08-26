# Task Plan: Local Paper Tax and Adverse Slippage

## Goal

Implement the authoritative Local Paper common-stock, cash, non-day-trade tax and fixed adverse-slippage plan without adding broker or real-money authority, while preserving Kill Switch durability and legacy replay truth.

## Current Phase

TS-006 — Review / fix / re-review loop

## Phases

### TS-000: Rebase and scope guard
- [x] Confirm isolated worktree and clean initial status.
- [x] Record source snapshot and current HEAD.
- [x] Inspect current Local Paper source contracts and focused test inventory.
- [x] Run focused baseline tests.
- [x] Confirm no stable Kill Switch commit is visible; keep overlap files deferred.
- **Status:** complete

### TS-001: Pure instrument, tick, slippage, and accounting domain
- [x] Add provider-neutral descriptor seam with explicit common-stock admission.
- [x] Add Decimal-only tick/slippage/accounting decisions and fail-closed validation.
- [x] Add exhaustive pure-domain tests including the golden example.
- [x] Run TS-G1 focused tests.
- **Status:** complete

### TS-002a: Simulation core and fill.v3
- [x] Centralize submit/snapshot/stream matching through one execution decision.
- [x] Apply tax/commission/slippage atomically to cash, orders, positions, and PnL.
- [x] Add fill.v3 evidence, validation, replay, and legacy v1/v2 compatibility.
- [x] Prove deterministic replay and no double counting.
- **Status:** complete

### TS-002b: Journal-first application integration
- [x] Obtain a commit-addressable stable Kill Switch candidate, then rebase before touching overlap files.
- [x] Pin policy identities in session metadata and command outcomes.
- [x] Preserve durable final admission and fail-closed recovery.
- [x] Run combined restart and Kill Switch tests.
- **Status:** complete

### TS-003: Settings v2, API, and Dashboard
- [x] Add v1/v2 reader and explicit v2 new-session apply workflow.
- [x] Make tax/commission policy frozen and slippage the only editable cost input.
- [x] Expose Decimal-string tax/reference/slippage evidence in API/UI.
- [x] Run settings/API/UI concurrency and cache/static checks.
- **Status:** complete

### TS-004: Verification, PostgreSQL UAT, and documentation
- [x] Run focused, full, compile, JavaScript, and whitespace checks.
- [x] Run actual disposable PostgreSQL new-connection restart UAT three times.
- [x] Exercise tamper and persistence failure injections.
- [x] Update README/runbook with exact boundaries and evidence.
- **Status:** complete (TS-G4 PASS)

### TS-005: Independent review readiness
- [x] Review product admission, accounting conservation, replay compatibility, and Kill Switch integration.
- [x] Resolve all P1/P2 correctness findings found locally.
- [x] Report any remaining independent-review requirement and live calibration gap honestly.
- **Status:** complete — requested review/fix/re-review cycle ended in APPROVE

### TS-006: Review / fix / re-review loop
- [x] Re-establish exact diff scope and rerun a severity-first line-by-line review.
- [x] Record every blocking/important finding with a reproducible test.
- [x] If the decision is REQUEST CHANGES, apply only scoped fixes and rerun review.
- [x] Continue until no unresolved P1/P2 issue remains and the final decision is APPROVE.
- **Status:** complete — APPROVE

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Treat the user-supplied plan as authoritative scope | It is explicitly current-source and official-rule reviewed. |
| Keep pure policy in `simulation/execution_costs.py` | Maintains a framework-free domain boundary and one deterministic calculator. |
| Preserve legacy persisted amounts | Replay must use immutable monetary truth rather than current policy. |
| Defer overlapping integration until Kill Switch has a stable commit | Required to preserve durable control and final admission. |
| Do not push | The user explicitly withheld push authorization. |
| Rebase on Kill Switch commit `34fb5250030d170b7909870f086c5693f728a9aa` | User selected the commit-first coordination option; commit payload was scoped and whitespace-clean. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Initial external `list_threads` status query did not return after two minutes | Terminated the stalled read-only query, recorded the known same-HEAD worktree state, and will retry a narrower status read before overlap files. |
| `.venv/bin/python` does not exist in the isolated worktree and system Python lacks pytest | Used the existing main-workspace virtualenv interpreter read-only while keeping cwd and all writes in this worktree. |
| First sandboxed `git rebase --autostash` could not create the autostash | Retried with the approved git rebase escalation; autostash applied cleanly and left no stash residue. |
| v3 restart initially rejected the Journal-frozen nested descriptor mapping | Accepted the immutable `Mapping` contract instead of requiring a mutable `dict`; exact restart regression now passes. |
| First final test command used an incomplete worktree `.venv`, then `uv --frozen` had no lockfile | Reused the existing main-workspace virtualenv executable read-only, with cwd and all writes confined to this worktree. |
| Full regression found two stale v1 Dashboard assertions | Updated them to require frozen fee/tax presentation, editable slippage, and the v2 cache token; the full suite then passed. |
