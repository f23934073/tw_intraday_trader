# Findings & Decisions

## Requirements
- On first browser load, call an HTTP API once to fetch indicators for all current observed symbols.
- After bootstrap, receive backend-pushed intraday updates over WebSocket.
- Optimize for near-realtime comparison across observed symbols during market hours.
- The user reviewed the plan and explicitly authorized implementation on 2026-08-19.
- Preserve the project boundary: Shioaji is market data only and no broker-order path is added.

## Research Findings
- Prior repository inspection established that the current Momentum frontend polls `/api/dashboard/momentum` every two seconds.
- Current candidate membership is refreshed server-side every 30 seconds, while Shioaji Tick/BidAsk callbacks feed a background projection runtime.
- The implementation must avoid a bootstrap race where an update occurs between the HTTP snapshot and WebSocket subscription.
- `dashboard/server.py` owns one process-local `RealtimeMomentumDashboardService`; `/api/dashboard/momentum` already returns the complete server-owned projection for all current candidates.
- The current browser keeps `momentumRenderKey` and only rerenders when `summary.projection_digest` changes, so a digest/revision gate can be retained for pushed events.
- `MomentumShadowRuntime` already serializes provider callbacks through a bounded queue and a single projection worker; WebSocket fan-out should subscribe to completed projection revisions rather than add work inside Shioaji callback threads.
- No existing WebSocket, SSE, broadcaster, or application event-bus abstraction was found in the repository.
- FastAPI lifespan currently closes the Momentum service before the shared runtime/provider, so a new connection hub must be closed and its clients disconnected before or together with Momentum shutdown.
- `DashboardService.realtime_candidate_snapshot()` still executes a Provider-backed `run_scan()` every candidate refresh; it is candidate-membership input, not the realtime indicator read model.
- The current complete indicator payload already exists at `GET /api/dashboard/momentum`; it should evolve to include an atomic `stream_id` and monotonic `revision` rather than introduce a second bootstrap endpoint unless broader dashboard sections are deliberately combined.
- The runtime exposes each projection through separate lock acquisitions after building a runtime snapshot. A cursor-safe bootstrap needs one atomic dashboard read-model capture under the runtime process lock; otherwise the HTTP payload and its revision can describe different moments.
- Projection updates happen only after Tick-driven feature/signal/state evaluation. BidAsk-only and health/lifecycle changes also affect user-visible freshness, so the push layer must publish source/candidate/availability changes in addition to symbol projection changes.
- `MomentumProjectionStore.digest` is content-addressed but not ordered. Keep it for duplicate/render suppression, but add a monotonic revision for replay and gap detection.
- The project already depends on FastAPI and Uvicorn, so basic WebSocket support needs no new runtime package. Current tests mostly call route functions directly and have no `websocket_connect` coverage; transport-level WebSocket tests may require adding a supported FastAPI/Starlette test client dependency to the dev extra or testing the hub separately.
- Existing UI tests intentionally assert the browser does not calculate Momentum signals or stages. The WebSocket client must continue applying server-serialized rows and must not move indicator formulas into JavaScript.
- The current detail dialog reads the same in-memory `state.momentum` payload as the table. Applying symbol-level upserts to that shared state will preserve the existing dialog behavior if row ordering and summary are recalculated server-side.
- Candidate metadata and realtime Momentum projections are separate concerns today: a Provider-backed candidate scan refreshes every 30 seconds, while Tick-driven indicators can change many times per second. The stream contract should use full candidate-set replacement/delta only on scan changes and coalesced per-symbol upserts for indicator changes.
- A new `/ws/dashboard/momentum` route avoids ambiguity with the existing `/api/dashboard/momentum/{symbol}` HTTP route and clearly separates bootstrap from stream transport.
- `python3 -m dashboard` starts one Uvicorn process bound to `127.0.0.1:8000`, which is compatible with a process-local v1 stream hub; the plan must fail/document single-worker operation rather than silently support multiple workers.
- Current browser state has only Momentum loading/digest/dialog fields. The migration needs explicit socket state (`connecting/open/degraded`), `streamId`, `lastRevision`, reconnect timer/attempt, heartbeat timestamp, and fallback-poll timer.
- Existing server serializers already produce complete per-symbol `intraday` and `signal` payloads. Reuse them for upserts so table and dialog remain contract-identical between HTTP and WebSocket.
- Existing architecture guidance keeps the dialog joined to `state.snapshot.candidates` for scanner-only fields. The first WebSocket scope should update Momentum indicators/candidate metadata only; historical Kbars, backtest jobs, and paper-simulation projections remain on their existing transports.
- Before implementation, `.venv` had neither `websockets` nor `wsproto` and lacked a supported Starlette transport client. The implementation installed and declared `websockets` plus `httpx2`.
- Concurrent HTTP fallback and WebSocket reconnect can produce late responses. The browser needs a transport-generation token in addition to revision checks so stale async completions cannot overwrite the active stream.
- Installed Uvicorn is 0.52.3 and declares `websockets>=13.0` for its standard extra; the project now declares an explicit WebSocket protocol backend rather than relying on an undeclared environment extra.
- A 500 ms watcher over the atomic dashboard read model satisfies the browser push requirement without introducing callbacks into the Shioaji worker. Candidate refresh needs its own service worker because a Provider full-market scan inside that watcher would periodically stall realtime fan-out.
- Shared bounded replay removes the need for per-client event queues: each client resumes by revision, and a lag beyond the ring is rejected with `REVISION_TOO_OLD` instead of accumulating memory.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Treat the backend projection as authoritative | The browser should render server-owned strategy results rather than recalculate Tick/BidAsk indicators independently. |
| Send versioned projection deltas, not raw Shioaji callbacks | This keeps SDK details server-side and bounds browser load. |
| Retain HTTP polling as a rollout fallback | WebSocket failures must degrade safely without losing dashboard availability. |
| Add a monotonic cursor alongside existing digests | Digests detect equality; cursors establish event order, replay ranges, and gap detection. |
| Keep v1 single-process | The live projection and subscriptions are process-local; multi-worker fan-out needs an external broker and is a separate phase. |
| Coalesce updates before browser fan-out | Sending every Shioaji callback would couple browser cost to market-event rate and create avoidable backpressure. |
| Push complete per-symbol rows rather than JSON Patch | The row payload is bounded, idempotent, easier to version/test, and keeps serialization logic server-side. |
| Default to 500 ms coalescing with configuration | Two UI update opportunities per second are four times more responsive than current 2-second polling while providing safer bandwidth and render load for up to 100 symbols. |
| Keep heartbeats independent of market events | Illiquid symbols or market pauses must not be mistaken for a dead WebSocket connection. |
| Add explicit protocol/test dependencies | FastAPI route support alone does not prove the installed Uvicorn environment can perform a WebSocket upgrade. |
| Capture an atomic runtime read view before stream serialization | All candidate rows, miss reasons, alerts, source health, and the cursor describe one committed projection view. |
| Use shared replay rather than per-client queues | The replay capacity is globally bounded and slow clients fail closed into HTTP resync. |
| Run candidate refresh independently from projection fan-out | A slow 30-second full-market scan must not pause Tick/BidAsk projection updates to connected browsers. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- `dashboard/static/index.html`
- `dashboard/server.py`
- `dashboard/momentum.py`
- `runtime/momentum_shadow.py`
- `market_data/shioaji_momentum_stream.py`
