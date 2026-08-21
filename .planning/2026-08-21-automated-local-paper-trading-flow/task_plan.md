# Task Plan: Automated Local Paper Trading Flow

## Goal
Run one complete strategy-origin local-paper lifecycle through intent, Journal, RiskGate, simulated fill, position, simulated exit, and realized PnL without any broker-order capability.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm local-paper automation is the highest-priority scope.
- [x] Preserve the no-broker-order and `subscribe_trade=false` boundary.
- [x] Trace current command, risk, journal, simulation, API, and test seams.
- **Status:** complete

### Phase 2: Contract & Tests
- [x] Define a versioned strategy-paper intent and deterministic idempotency contract.
- [x] Add failing tests for BUY fill, duplicate suppression, risk block, SELL fill, and closed lifecycle.
- **Status:** complete

### Phase 3: Implementation
- [x] Route strategy-origin commands through the existing Journal-first application service.
- [x] Add a minimal run-once flow service and API without selecting research signals automatically.
- [x] Expose flow status/result while preserving manual order behavior.
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Pass focused unit and API tests.
- [x] Journal fills/rejections that become terminal after a later snapshot or BidAsk update.
- [x] Pass the final full repository regression after the terminal-event bridge.
- [x] Verify no Shioaji order/CA/trade-subscription path is introduced.
- [x] Verify dirty-worktree changes outside this scope remain untouched.
- **Status:** complete

### Phase 5: Delivery
- [x] Document how to execute the run-once paper flow.
- [x] Summarize remaining work for continuous strategy scheduling.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Implement a run-once strategy-paper flow before a scheduler | Proves the lifecycle deterministically without silently promoting an experimental score into an always-on strategy. |
| Reuse Journal -> RiskGate -> SimulationService | Manual and future automated orders must not have separate safety paths. |
| Keep all fills local | The user prioritized simulation; Shioaji remains market-data-only. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Parallel inspection script had an invalid escaped string literal | No repository files changed; rerun the same read-only inspections with valid JavaScript string syntax. |
| New Pydantic request used `datetime` without importing it in `dashboard.server` | Added the standard-library import; all non-API strategy-flow tests already passed. |
| Scope audit found later quote-driven fills bypass terminal Journal evidence | Add one simulator terminal-event bridge and regression tests before declaring the lifecycle complete. |
| A streaming order can fill while its original submit call is still returning | Register the normalized command before applying it; Journal idempotency keeps the terminal record exactly once if the two paths race. |
