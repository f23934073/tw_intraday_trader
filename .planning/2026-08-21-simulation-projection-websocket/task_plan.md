# Task Plan: Simulation Projection WebSocket

## Goal
Push local-paper positions, current price, best bid/ask, and P&L to the browser over a dedicated WebSocket, while retaining HTTP polling as fallback and preserving the market-data-only boundary.

## Current Phase
Phase 4 — Delivery

## Phases

### Phase 1: Discovery
- [x] Confirm the current browser updates simulation projection by HTTP every two seconds.
- [x] Trace the existing Momentum WebSocket contract and simulation test seams.
- [x] Define a minimal simulation stream payload and disconnect behavior.
- **Status:** completed

### Phase 2: Implementation
- [x] Add the read-only simulation projection WebSocket endpoint.
- [x] Add browser connection, rendering, reconnect, and HTTP fallback behavior.
- [x] Add focused backend/frontend contracts.
- **Status:** completed

### Phase 3: Verification
- [x] Verify WebSocket payloads and streaming quote projection behavior.
- [x] Run focused and full regression tests.
- [x] Browser-smoke the connection and holdings UI.
- **Status:** completed

### Phase 4: Delivery
- [x] Document the provider/runtime condition for real-time prices.
- [x] Summarize the verified behavior and limitations.
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep Shioaji callbacks server-side | The browser must not connect to credentials or provider SDKs. |
| Use a dedicated simulation WebSocket | Keeps market-data/position projection separate from Momentum signals. |
| Preserve HTTP polling as fallback | Existing UI remains usable when WebSocket transport is unavailable. |
| Sample the in-memory projection every 250ms and push only changes | Keeps UI latency low without rendering every provider tick or polling Shioaji. |
| Send a 10-second heartbeat | Detects broken browser/proxy connections without resending unchanged positions continuously. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Existing server on port 8000 had not loaded the new Python endpoint | Kept it running and used isolated port 8010 for browser verification. |
| `.venv/bin/ruff` is not installed | Relied on Python/JS syntax checks, `git diff --check`, and the full 995-test suite. |
