# Findings & Decisions

## Requirements
- The holdings drawer must update current price, best bid/ask, market value, and unrealized P&L without waiting for manual refresh.
- Browser transport should use WebSocket.
- Shioaji remains quote-only with `subscribe_trade=False`; no broker order, account, or CA path is added.

## Current Behavior
- `SimulationService` already consumes Shioaji Tick/BidAsk in a background worker.
- Tick updates the position's current price; BidAsk updates best bid/ask and can fill local-paper orders.
- The browser currently fetches `/api/simulation/projection` every two seconds.
- MockProvider has no moving quote stream, so a WebSocket cannot make Mock prices change.

## Screenshot Evidence
- The supplied holdings drawer shows 2317 and 3231 with snapshot prices and missing bid/ask values.
- The screen therefore does not prove Shioaji streaming is active; provider mode and stream health must remain visible and testable.
# Findings

- `SimulationService` already consumes server-side Shioaji Tick/BidAsk updates and recalculates each position's current price, best bid/ask, market value, and unrealized P&L.
- `/api/simulation/projection` reads that in-memory projection and does not poll a Shioaji snapshot or account API.
- The browser currently calls that HTTP endpoint every two seconds, so the screenshot is not evidence of a browser WebSocket connection.
- A dedicated WebSocket can safely reuse the same projection while keeping Shioaji credentials and callbacks entirely on the server.
- The existing HTTP endpoint is suitable as a reconnect fallback.
- Browser verification confirmed the dedicated WebSocket opens and prevents periodic HTTP projection requests while healthy.
- `PROVIDER=mock` still displays fixed snapshot prices and blank bid/ask; actual changing prices require a restarted server with `PROVIDER=shioaji` and valid market-data credentials.
- The transport remains local-paper only: Shioaji is used for quote subscriptions, not broker orders or account access.
