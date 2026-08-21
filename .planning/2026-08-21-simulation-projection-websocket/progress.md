# Progress Log

## Session: 2026-08-21

### Current Status
- **Phase:** 1 - Discovery

### Actions Taken
- Inspected the supplied holdings screenshot.
- Confirmed the current browser transport is two-second HTTP polling although the backend simulation already consumes quote callbacks.
- Created an isolated plan for the simulation projection WebSocket.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
# Progress

## 2026-08-21

- Confirmed server-side streaming quote consumption is already implemented in `SimulationService`.
- Confirmed the simulation browser workspace currently refreshes through a two-second HTTP interval.
- Defined a dedicated same-origin WebSocket envelope with change-only projection messages and heartbeats.
- Added `/ws/simulation/projection` with a 250ms projection sample, change-only pushes, and 10-second heartbeat.
- Added browser reconnect/backoff behavior and disabled the two-second HTTP poll while the socket is open.
- Added visible `WebSocket` / `HTTP 備援` transport state and asset versioning.
- Verified a 105.5 -> 106.0 price/P&L WebSocket update in the backend contract test.
- Verified in the in-app browser that the WebSocket upgraded, a Mock 3231 order filled, and the position count updated to one.
- Observed no fallback HTTP polling during a 3.5-second connected window.
- Full regression: 995 passed, 2 skipped. JavaScript syntax and diff whitespace checks passed.
