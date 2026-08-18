# Findings and Decisions

## Requirements

- Review the attached five-stage development proposal for adjustments and optimizations.
- Compare it with the actual repository, especially existing `MarketDataStore`, `CandidateEngine`, `BuyScoreEngine`, and adjacent components.
- Produce an implementation plan only; do not implement application changes.
- Make the plan concrete enough for user review before any implementation begins.
- Add a web-based manual Shioaji Simulation order flow.
- Add a place in the web UI to view simulated purchased stocks and their position information.
- Preserve a clear path for later program-generated orders to use the same backend flow.
- The user has now authorized implementation.
- The first implementation slice must provide local paper simulation only; it must not claim to be an authenticated Shioaji Simulation session or submit any broker order.
- The user has now explicitly requested Shioaji Tick/BidAsk subscriptions for realtime simulation quote updates.
- This authorization changes the market-data path only; local paper orders remain in-process and must not call Shioaji order APIs.

## Research Findings

- The worktree began clean on branch `main`, tracking `origin/main`.
- No repository-level `AGENTS.md`, `RULES.md`, or pre-existing planning files were discovered by the initial scoped scan.
- Relevant prior project guidance requires data-only/research boundaries, fail-closed market-data handling, explicit stream ordering, queue-draining shutdown, and no real-money path. These are context to verify against this repository, not substitutes for current evidence.
- The supplied proposal has 679 lines and describes Phase 0 architecture cleanup followed by Historical Backtest, Replay Trading, Shioaji Simulation, Small Live Trading, and Production Trading.
- Its strongest architectural invariant is that strategy code emits an `OrderRequest` and never calls Shioaji directly; `ReplayBroker`, `ShioajiSimulationBroker`, and `ShioajiLiveBroker` sit behind a common Broker boundary.
- The proposal correctly calls out asynchronous order/deal callbacks and a real order lifecycle rather than equating submission with fill.
- The proposal currently treats live-money phases as planned progression. That conflicts with the inherited project boundary (`Real Money = prohibited`) unless the user separately changes scope; the final plan must not silently authorize live-order implementation.
- The current repository is compact and contains market data, candidate selection, scoring, position, dashboard, configuration, application entrypoint, and focused tests. No broker/execution package appears in the file inventory.
- A pre-existing isolated `.planning/2026-08-17-intraday-visual-dashboard` directory exists; the new root planning files are specific to this review and did not overwrite it.
- The proposal's closing sequence begins with Broker models/interface, then ReplayBroker, OrderManager, Shioaji simulation callbacks/synchronization, decision/risk engines, automated simulation, journal, and only later live comparison/production.
- Risk controls are placed only in the live-safety section of the proposal. They should instead be invariant policy enforced for every broker mode so Replay and Simulation exercise the same admission decisions as any future execution mode.
- The proposal's stated milestone is “Execution Layer v1,” with success defined as switching the same BUY signal between Replay and Shioaji Simulation without changing Candidate, Scoring, or Position logic.
- The repository README documents a decision-support MVP: users decide whether to buy; the dashboard is read-only; current positions are inserted manually for demonstration. This is materially earlier than an execution system.
- Existing architecture guidance explicitly says the first version favors simplicity and should not pre-create execution/backtest/event-system abstractions. Therefore the final plan should add only the minimum seams proven necessary for Replay and paper execution, rather than importing a production-trading architecture wholesale.
- Existing repository principles already isolate Shioaji behind `MarketDataProvider`, distinguish Candidate from buy signal, require continuous position monitoring, preserve score breakdowns, and centralize thresholds in settings.
- `run_scan()` is a one-shot orchestration function: it creates a new in-memory `MarketDataStore`, candidate/scoring engines, exit rules, and `PositionManager` for every scan, then loads market snapshots and returns a presentation DTO. It is not yet a persistent session/runtime loop.
- `MarketDataStore` stores only the latest `StockData` per symbol and unconditionally overwrites existing data; its own docstring marks stale-timestamp rejection as future work. Replay/event-driven execution cannot safely depend on it until ordering and session-time semantics are defined.
- The current `PositionManager` is fed a hard-coded demonstration position in `app.py`; current Position objects are user-entered holdings, not broker-authoritative positions derived from fills.
- The dashboard intentionally calls the same one-shot `run_scan()` and marks provider mode as `snapshot`, `streaming=False`; it performs no trading operation.
- The existing code has a useful pure boundary: Candidate and scoring operate on internal `StockData`, while dashboard serialization consumes `ScanResult`. Execution work should preserve these pure computations and move long-lived session orchestration out of `run_scan()` rather than turning the dashboard path into a trading loop.
- `MarketDataProvider` is pull-oriented (`get_stock`, `get_market_stocks`, optional historical Kbars). It has no event/replay clock, subscription lifecycle, disconnect signal, or backpressure contract; adding Replay by only naming a new provider would not define deterministic event-time behavior.
- `StockData.timestamp` is a single timestamp. Mock/Shioaji snapshots currently populate it with naive local `datetime.now()`, while Kbars are timezone-aware Asia/Taipei. Execution/replay needs an explicit, timezone-aware event-time/received-time contract before freshness or latency can be trusted.
- `ShioajiProvider` owns login and a private SDK client and can select `simulation=False` via `SJ_SIMULATION`. Broker integration should not reach through this private provider or duplicate login implicitly; a dedicated session/gateway composition boundary is needed, with fail-closed mode configuration.
- Snapshot conversion uses local receipt time rather than an exchange timestamp and skips per-symbol conversion exceptions during full-market scans. This may be acceptable for a UI snapshot but is insufficient as an execution-quality feed without explicit data-health reporting.
- Current market snapshots do not include bid/ask, lot type, tick size, tradable status, or exchange sequence. Consequently a credible limit/market fill model, spread gate, stale-data gate, and order normalization cannot yet be specified from `StockData` alone.
- The repository's own documented evolution order is `Strategy Idea -> Backtest -> Statistical Validation -> Shadow Trading -> Approved -> Realtime Strategy`; it explicitly names Shadow Trading and Data Health/Risk Gate as future seams. This is safer and more consistent with project scope than jumping from Replay directly to broker-simulated automated orders.
- Candidate, scoring, and exit logic are currently deterministic/pure over `StockData`, which is valuable for Replay parity. However outputs lack decision provenance such as strategy/rule version, decision ID, evaluated-at timestamp, market-data timestamp, and input snapshot identity; those must exist before a journal can be auditable.
- Existing tests focus on pure rules, latest-value storage, provider mapping/batching, historical Kbar mapping, and dashboard serialization. There are no tests for session orchestration, stale/out-of-order data, deterministic Replay, repeated decision suppression, order lifecycle, recovery/reconciliation, or persistence.
- Current store tests intentionally use identical timestamps and assert last-call-wins overwrite behavior. Tightening event ordering will need explicit compatibility decisions and new tests rather than silently changing this contract.
- Git history contains only the initial MVP and dashboard feature commits, reinforcing that the next step should be a narrow research/execution-simulation foundation rather than a production brokerage stack.
- Current official Shioaji documentation confirms Simulation supports subscriptions, historical queries, order/update/cancel/status/list-trades, and position/P&L queries, but simulated order placement excludes emerging stocks and odd lots.
- Official order/deal documentation confirms callbacks report both order and deal events with exchange identifiers/timestamps. Therefore submission return values and callbacks must be normalized as idempotent events; callbacks alone are not a durable source of truth after restart.
- Official current limits confirm: quote/history query calls share 50 requests per 10 seconds, order-related calls share 250 requests per 10 seconds, subscriptions are capped at 200, logins create connections, and the provider explicitly warns not to poll snapshots/ticks/kbars as a live feed.
- The current full-market `get_market_stocks()` uses batched snapshots. It can remain an explicit/manual snapshot scan, but an automated intraday runtime must use streaming subscriptions and a bounded subscription-selection policy rather than loop this method.
- Because the 200-subscription cap is far below the full TWSE/TPEX universe, the implementation plan needs a two-tier universe flow: coarse discovery/refresh at an allowed cadence, then Tick/BidAsk subscriptions for bounded candidates and all open/pending positions.
- Shioaji's public SDK evolves frequently, while this project currently allows any `shioaji>=1.7,<2`. Integration work should qualify a narrower tested version/range (without assuming the latest installed version) and record the actual SDK version in journal/session metadata.
- `pyproject.toml` package discovery currently enumerates only existing packages. Any approved `replay`, `decision`, `execution`, or `journal` package must be added deliberately so editable installs and built wheels do not omit it.
- The existing configuration has only rule/display/provider switches. Introducing execution-like modes requires typed, fail-closed configuration with no `live` value in the current scope; a loose `BROKER_MODE` string and shared `SJ_SIMULATION` toggle would be too easy to misconfigure.
- The active virtual environment currently has Shioaji `1.7.2`; this is useful local evidence, not a substitute for an explicit supported-version policy.
- Official stock-order docs require CA activation before placing orders, require an explicit `order_lot`, and show that `place_order` can return `PendingSubmit` before a later status refresh/event. The plan must model pending submission and must never infer acceptance/fill from a successful function return.
- The proposal's generic `qty` is unsafe because internal share quantity, order-lot type, and broker quantity must not be conflated. Use an unambiguous internal unit and let a tested broker adapter perform the conversion; include boundary fixtures for common-lot and unsupported odd-lot Simulation requests.
- The current 64-test suite passes in 0.10 seconds. This is the regression baseline for future approved changes.
- The prior dashboard planning record confirms the dashboard was deliberately designed as a manual-refresh, read-only snapshot surface and explicitly deferred streaming/replay/order endpoints. The execution plan must preserve that boundary and must not reuse dashboard refresh as the runtime market-data loop.
- The new user requirement intentionally changes the future dashboard boundary: after the manual Simulation gate, the browser may submit simulation-only order commands and read order/portfolio projections. This does not authorize a live-money route.
- The browser must not construct Shioaji SDK objects or call the SDK. Manual web orders and future strategy orders should be separate command origins feeding the same backend `OrderApplicationService`.
- The purchased-stock view must use `PortfolioProjection` plus reconciliation metadata rather than the current hard-coded demonstration `PositionManager` entry.
- The current dashboard already has a top-right `持倉` button and an accessible slide-in position drawer. The plan should evolve this existing surface into a simulation portfolio view instead of adding a redundant page.
- Current position cards already show symbol/name, quantity, entry/current price, unrealized PnL, stop/take-profit markers, and exit status. Simulation positions need to add source/mode, market value, average fill price, pending quantity, realized PnL, last broker reconciliation time, and sync/data-health state.
- `dashboard/server.py` currently exposes only snapshot refresh and Candidate history; `DashboardService` refreshes through `run_scan()`, whose sole position is a hard-coded demonstration holding. Simulation views must read OrderManager/PortfolioProjection repositories rather than call `run_scan()` or query Shioaji on every browser request.
- The current page explicitly says it is a one-shot snapshot without order functionality. A future Simulation control state must be unmistakable: show a persistent `SIMULATION` badge and keep the order form disabled/hidden unless the backend reports a healthy `SHIOAJI_SIMULATION` session.
- There is no account, certificate-authority, or authenticated Shioaji session evidence in this checkout. The safe first deliverable is therefore a session-local `LOCAL_PAPER_SIMULATION` implementation, visibly distinguished from Shioaji Simulation and with no SDK order calls.
- The local simulation can preserve the future command seam by treating the browser as one command origin and keeping order validation, idempotency, position updates, and order projection in one backend service.
- `DashboardService` and its tests expose a stable read-only scan snapshot whose `positions` still contain the demo holding from `app.py`. The local simulator must provide a separate `simulation` projection instead of changing the existing scan-result contract in this first slice.
- `dashboard/server.py` already keeps a process-lifetime `DashboardService` instance. A process-lifetime local simulation service can use the same `MarketDataProvider` instance without browser reads creating a provider or Shioaji client per request.
- The dashboard is a single static page with an existing accessible holdings drawer and explicit-refresh button. The smallest UI change is to reuse the holdings drawer for the simulation positions and add a compact order drawer/blotter rather than create a new route or frontend build system.
- The installed FastAPI test client cannot be imported because its environment expects `httpx2`, which is not installed. This slice will avoid adding an unrelated runtime/testing dependency and cover the API contract through the service tests plus direct endpoint construction only where needed.
- Calling the dashboard route with the ambient provider setting initialized `ShioajiProvider`; its installed native dependency segfaulted under the active Python 3.13 interpreter. Focused API tests must inject `MockProvider` and must not exercise the external SDK. This is an environment/provider compatibility issue outside the local paper-simulation path.
- The running local dashboard was visually and interactively verified with `MockProvider`: the simulation badge is visible, the candidate action opens an accessible order drawer, and its 3231/BUY/1-lot/105.50 defaults are correctly populated. The browser test did not submit a persistent test order; command behaviour is covered by the service/API tests.
- The final regression suite has 71 passing tests, and the static dashboard script passes a standalone JavaScript syntax parse. The local simulator contains no Shioaji import or order call.
- The current simulation stores only snapshot `StockData`; position reads never call the provider, and `refresh_quotes()` runs only behind the explicit full-dashboard refresh.
- Current local fills compare limit price with last trade (`StockData.price`). Tick/BidAsk integration needs separate best bid/ask fields so BUY eligibility/fill uses ask and SELL eligibility/fill uses bid.
- `StockData` intentionally models a broad latest snapshot and currently has no bid/ask fields. A separate small streaming-quote model is safer than changing every Candidate/scoring fixture and snapshot serializer.
- `SimulationService` is already guarded by an `RLock`, so normalized quote callbacks can update its quote projection safely; Shioaji-specific objects should stay in `market_data/provider.py`.
- The installed Shioaji 1.7.2 package includes `_core.pyi`; implementation can be checked against its local callback and subscription signatures without importing the native extension in tests.
- Current official Shioaji stock-streaming docs show `set_on_tick_stk_v1_callback` and `set_on_bidask_stk_v1_callback`, with callbacks receiving exchange plus the Tick/BidAsk payload; both common-stock streams are event-driven and delivered only during trading hours.
- Official guidance says callbacks should avoid computation. Provider callbacks should therefore only map SDK fields and invoke the small normalized update sink; all matching and portfolio work stays under the simulator lock.
- One symbol consumes two subscriptions when both Tick and BidAsk are active; the implementation must track subscription pairs idempotently and stay within the documented account limit rather than resubscribing on every browser poll.
- A real local Shioaji 1.7.2 smoke test successfully logged into the simulation environment with `subscribe_trade=False`, installed both callbacks, reported streaming healthy, and logged out normally.
- A real 4946 subscription received successful server acknowledgements for both Tick and BidAsk but no market event within the 10-second observation window. Because the feed is event-driven, this proves subscription acceptance but not yet payload mapping.
- A high-liquidity 2330 direct provider smoke received and normalized both real Tick and BidAsk callbacks, proving the SDK callback signature and mapper.
- End-to-end UI and standalone `SimulationService` smokes received ongoing Tick updates but a marketable BUY remained `SUBMITTED` for 10-14 seconds. The issue is downstream of subscription acceptance and requires inspecting the merged quote state before completion.
- The apparently marketable test was correctly pending: live 2330 best bid/ask was 2380/2385 and the test BUY limit was only 2000. Raising the local-paper limit to 3000 filled at ask 2385; the next Tick marked the position at 2380 and produced -5,000 unrealized PnL.
- FastAPI shutdown initially cancelled subscriptions but did not log out the Shioaji client, producing a native-thread panic after process shutdown. Adding an explicit Provider close/logout contract removed the warning in a second real shutdown smoke.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Classify recommendations by priority and evidence | Keeps blocking correctness issues distinct from optional improvements. |
| Include exact files/components and acceptance tests in the final plan | Makes the plan directly executable after approval. |
| Treat performance ideas as hypotheses until current hot paths and state ownership are traced | Avoids premature optimization. |
| Preserve `MarketDataStore` as a latest-state projection, not a historical/event store | Keeps current consumers stable while a separate immutable event source/journal owns replay and audit history. |
| Use one event-driven runner for fast Backtest and paced Replay | Prevents the same strategy from producing different semantics in two engines. |
| Keep the dashboard observer-only | Trading runtime owns provider cadence and state; the UI must never trigger order or streaming side effects. |
| Build common-lot, cash, long-only, limit-order Simulation first | Matches current long-only decision model and Shioaji Simulation constraints while minimizing order-normalization surface area. |
| Treat 20-30 sessions as an observation window, not a sufficient pass criterion | Advancement also requires deterministic, integrity, risk, recovery, and reconciliation gates. |
| Use an explicit simulation-only web command namespace | Makes it difficult to confuse or later repurpose the endpoint as a production-order route. |
| Keep reads projection-backed | Browser refresh/polling reads local order/portfolio state and must not trigger Shioaji status/position queries per request. |
| Show pending orders separately from filled positions | A submitted or accepted order is not yet a purchased holding. |
| Reuse the existing holdings drawer and add a separate simulation order ticket/order blotter | Keeps Candidate inspection intact while making orders and owned positions distinct tasks. |
| Poll or stream local projections, never provider/account APIs per browser request | Keeps API usage, callback ordering, and reconciliation under the backend runtime's control. |
| Make the first implementation session-local | Meets the immediate web simulation requirement without introducing database schema/migration scope; the UI must disclose that restarting the backend clears simulated state. |
| Keep SDK callbacks thin and hand normalized quote updates to `SimulationService` | Avoids doing order-state work on Shioaji callback threads and keeps the simulator testable without the SDK. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Initial memory search had no match and prevented chained reads | Split the reads into independent operations. |

## Resources

- `/Users/stevehuang-work/.codex/attachments/db832d2f-0507-444a-8890-36b212eed197/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader`
- Shioaji Simulation Mode: https://sinotrade.github.io/tutor/simulation/
- Shioaji Order & Deal Event: https://sinotrade.github.io/tutor/order_deal_event/
- Shioaji Usage Limits: https://sinotrade.github.io/zh/tutor/limit/
- Official Shioaji repository: https://github.com/Sinotrade/Shioaji

## Visual/Browser Findings

- Official documentation was reviewed as of 2026-08-18; volatile API limits and supported operations should be rechecked at implementation time.
- Browser verification used the real local Shioaji feed: stream badge, subscription count, advancing quote time, cancel/pending behavior, ask-side fill, position count, bid/ask/current-price fields, and PnL all rendered correctly with no console errors.
