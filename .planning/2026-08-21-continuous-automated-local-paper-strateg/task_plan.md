# Task Plan: Continuous Automated Local Paper Strategy

## Goal
Run a startable and stoppable in-process strategy session that converts one explicit, versioned intraday signal policy into Journal-first, risk-gated local-paper BUY/SELL intents while preserving the no-broker-order boundary.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Read the referenced readiness task and completed run-once strategy flow.
- [x] Wait for the overlapping simulation WebSocket task to finish.
- [x] Trace current candidate/momentum signals, quote health, session hours, exit rules, runtime lifecycle, and API seams.
- [x] Confirm the smallest truthful signal policy that can fail closed.
- **Status:** complete

### Phase 2: Contract & Tests
- [x] Define controller state, start/stop/status, tick cadence, deterministic idempotency, and restart semantics.
- [x] Add failing tests for entry, duplicate suppression, max-one-position, stop-loss/take-profit exit, stale/closed-market blocking, and stop behavior.
- **Status:** complete

### Phase 3: Implementation
- [x] Implement the continuous local-paper strategy controller around the existing `StrategyPaperFlowService`.
- [x] Wire runtime lifecycle and read-only/control API endpoints without adding broker execution capability.
- [x] Document safe Mock and Shioaji startup/stop behavior.
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Pass focused strategy/runtime/API tests.
- [x] Run the full repository regression and static checks.
- [x] Smoke a deterministic complete entry-to-exit session and inspect Journal/projection evidence.
- [x] Audit for CA, broker order, trade callback, or `subscribe_trade=True` additions.
- **Status:** complete

### Phase 5: Delivery
- [x] Reconcile plan, findings, and progress with verified behavior.
- [x] Summarize how to start/stop the automated local-paper session and its remaining evidence limits.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Reuse the completed strategy intent flow | Keeps Journal, RiskGate, local fill, idempotency, and audit evidence under one authority. |
| Keep Shioaji market-data-only | The requested outcome is simulated automatic trading, not broker execution. |
| Require an explicit start and expose stop/status | Continuous automation must not begin merely because the dashboard process starts. |
| Fail closed when signal, quote health, or market-session evidence is insufficient | A research score must not silently become an order instruction. |
| Use the reviewed TWSE calendar plus the 09:00-13:30 local session | Avoids the current command facade's always-open risk snapshot when deciding whether automation may act. |
| Use current valid Tick as entry limit and fresh best bid as exit limit | Lets the existing local simulator and BidAsk worker determine fills without fabricating a spread or market-order model. |
| Default to one entry per process session | Gives the requested automatic loop while bounding exposure until multi-trade evidence exists. |
| Restart always leaves automation stopped | Matches the current in-memory simulation and Journal lifetime without implying persistence that is not wired. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| First planning-file patch referenced a decision row in the wrong file | Inspected current plan files and applied the phase/decision updates to their actual sections. |
| JavaScript checker could not resolve the new cache-busted app URL | Strip the query component when resolving the local entrypoint; syntax validation passed. |
| Ruff executable is not installed in `.venv` | Do not claim lint; continue with compilation, focused/full tests, browser smoke, and diff checks. |
| Full regression retained one old `app.js` cache-version assertion | Update the existing static contract to the new continuous-paper version and rerun the full suite. |
| First integrated controller fixture could not fill a historically timestamped streaming book | Preserve the real streaming bridge test separately and use a deterministic fresh executable projection for the controller-to-real-flow lifecycle. |
