# Findings: Live Trading Mode Switch Implementation Plan

## Requirements

- Provide a staged implementation plan for moving from LOCAL_PAPER toward Shioaji simulation and real trading.
- Retain a fail-closed boundary: there must be no global hot switch that changes an existing route from paper to live.
- Bind commands to immutable account mode, expected mode, and portfolio revision.
- Separate market-data environment, broker environment, account-read capability, live-order capability, and automated-order capability.
- Represent ambiguous broker side effects and reconcile them without retrying.
- Keep the plan implementation-only; product changes require later authorization.

## Confirmed Starting State

- Runtime composition currently builds a LOCAL_PAPER-only execution path.
- Current `/api/simulation/*` routes are local-only, but the order request does not carry account, expected mode, or portfolio revision.
- Current order application handling collapses exceptions to `HANDLER_FAILED`.
- Shioaji is currently used as market data with trade subscription disabled.
- `FreshnessPolicyV1` remains blocked by incomplete evidence, including broker/account evidence.
- The worktree contains extensive unrelated modifications and a separate local-paper odd-lot task.
- The existing root plan explicitly blocks Portfolio migration/core, RiskGate freshness, provisional thresholds, and broker/account reads until the Freshness evidence chain is complete.
- The existing architecture intent already routes browser and future strategy commands through one application service; the live plan should extend that seam rather than add a UI-specific broker path.
- Qualified quote evidence supports connection/subscription plus BidAsk health, not a simple Tick-silence rule; source-clock and broker/account evidence remain unresolved.
- Two prior planning artifacts already define the execution and Portfolio foundations. The new deliverable should be a focused amendment for safe mode selection/live authority, not a replacement architecture or duplicate order pipeline.
- Current source layout already has domain/application code under `trading/`, runtime composition/ports, local simulation adapters, PostgreSQL journal support, and dashboard delivery adapters; new Shioaji code belongs at the infrastructure edge.
- `RuntimeComposition.create()` currently constructs local simulation, a fixed local session, and `StrategyPaperFlowService` in one factory. The live plan needs mode-specific startup builders and must omit automated strategy origins from production composition.
- `runtime.ports.OrderCommandHandler` is explicitly a LOCAL_PAPER compatibility seam with float-valued inputs. It should remain a facade during migration, not become the canonical broker command port.
- `trading.risk.OrderCommand` currently lacks `account_id`, `expected_mode`, `portfolio_revision`, lot/condition/TIF fields, and live-confirmation identity. Its retry fields also need a hard prohibition when prior state is `SUBMIT_UNKNOWN`.
- `OrderApplicationService` appends through a Journal repository before calling a local handler, but the PostgreSQL adapter opens a transaction per append. It cannot yet atomically lock the account, validate revision, create reservations, append intent, and increment revision.
- `RiskPolicy.max_book_age_seconds` currently defaults to 15 seconds. Broker-mode work must replace provisional/magic freshness with an injected frozen `FreshnessPolicyV1`.
- Recovery currently recognizes local fills or generic recovery-required only; it has no broker order identity, callback dedupe, submission-attempt state, or reconciliation result model.
- Existing PostgreSQL migrations persist Journal sessions/records/checkpoints only; there are no PortfolioAccount, order, reservation, fill, account-observation, live-session, nonce, or execution-lease tables yet.
- Persistence configuration defaults to memory. Any `BROKER_REAL` composition must reject startup unless durable PostgreSQL and migration health are verified.
- Dashboard protection is currently a loopback Host/Origin boundary. Live mutations need an explicit local command token/CSRF contract in addition to live session confirmation.
- Current simulation HTTP price input is `float`; the canonical Portfolio API must accept decimal strings and keep JavaScript out of accounting authority.
- `SimulationOrder` now supports exact shares and exposes legacy `lots=None` for odd-lot quantities, confirming LOCAL_PAPER capability-superset behavior is intentional current work.
- Local-paper retries are intentionally limited to terminal `CANCELLED`/`EXPIRED` remainders. Broker orders need a separate rule: no successor/retry while submission or broker state is unknown.
- Local-paper risk snapshots hard-code `market_open=True` and `instrument_tradable=True`; those conveniences must remain inside the local adapter and never be shared with Shioaji simulation or production.
- `simulation.execution_policy` contains a 5-second conservative local-only book age and explicitly says it is not FreshnessPolicyV1. Broker composition must not reuse it as approved policy.
- `ShioajiProvider` directly constructs and logs in an SDK client from `SJ_SIMULATION`, always with `subscribe_trade=False`. Broker environment/session ownership is not yet separately modeled.
- Dashboard process state is global and lifespan shutdown already has ordered component cleanup. Live composition must add stop-accepting, callback drain, Journal flush/checkpoint, unsubscribe, and logout without mixing it into request handlers.
- The current read-only broker intake explicitly prohibits CA, while production account access may require it. Before the evidence probe, the intake must be amended so CA activation is permitted only within a secret-safe, no-order-route probe process.
- Current Freshness checkpoint still reports broker/account `NO_EVIDENCE` and Phase 1 blocked.

## Working Decisions

| Decision | Rationale |
|----------|-----------|
| LOCAL_PAPER remains an exact-share capability superset | Current worktree and tests intentionally allow quantities such as 125 shares. |
| SHIOAJI_SIMULATION and BROKER_REAL v1 accept COMMON lots only | Avoid claiming unsupported broker-simulation odd-lot behavior; real odd-lot support needs a separate contract. |
| Production market data does not imply real-order permission | Data source and execution authority are independent dimensions. |
| Rejected stale/mode-mismatched commands do not enter the trading command journal | They are rejected before domain execution, but should emit a redacted security audit event. |
| Replace request `mode` with `expected_mode`; derive actual mode from the locked account row | A client must never select execution authority by payload alone. |
| Keep broker account reads in one environment-scoped `ShioajiAccountAdapter` | Simulation and production execution adapters must not create duplicate position/account mappings. |
| Use one idempotent reconciliation use case for callbacks, startup, manual refresh, and `SUBMIT_UNKNOWN` recovery | Multiple reconciliation implementations would drift and create conflicting authority. |
| Introduce an account-scoped unit-of-work port around repositories and Journal append | Correctness requires one PostgreSQL transaction across row lock, revision, reservations, events, and projection state. |

## Issues and Risks

- A boolean environment switch cannot prevent stale-browser, wrong-account, replay, or multi-worker execution hazards.
- `place_order()` return values and asynchronous order/deal callbacks must not be treated as the same event.
- Timeout after network transmission creates `SUBMIT_UNKNOWN`; automatic retry could duplicate a real order.
- A live kill switch must block new orders without disabling cancellation or reconciliation.
- Broker/account read-only evidence may require CA and therefore needs an earlier secret boundary than the current intake assumed.
- The original execution-foundation plan deliberately excluded live-money work and required a separate RFC/authorization. This new document must define later gates without treating plan approval as permission to place orders.
- Existing evidence shows sparse Tick activity can coexist with active BidAsk subscriptions; execution health must consume the eventual frozen policy rather than inventing a provisional timeout in broker code.
- `portfolio-contract-v0.4` says AccountMode and whole-lot validation are frozen and calls Freshness the only blocker. The new requirement invalidates that status statement: publish an explicit v0.5 amendment rather than silently editing frozen meaning.
- The current v0.4 domain contract applies `COMMON`/1000-share validation globally, while the current LOCAL_PAPER worktree supports exact shares. The plan must move lot capability validation to an account-mode capability policy while keeping the domain command impossible to route to an unsupported adapter.
- Account revision is only an optimistic client/UX guard; correctness remains an account-level database transaction and row lock.
- Current v0.4 mentions UI second confirmation but not a server-issued, order-digest-bound live session and single-use nonce; that contract must be added before any live mutation route exists.
- Journal-first must be split into durable command intent before broker I/O and durable outcome after I/O. A timeout after invocation cannot be flattened into ordinary handler failure.
- PostgreSQL outage must keep broker modes query-only/degraded and must never fall back to memory mutation.
- The older execution plan proposed `/api/simulation/*` for Shioaji simulation, but that namespace is now an established LOCAL_PAPER compatibility contract. New broker-capable routes must live under account-bound `/api/portfolio/{account_id}/*` endpoints.
- The older execution plan's SQLite default is superseded for this scope: account locks, cross-worker correctness, durable broker recovery, and execution leases require PostgreSQL before any broker mutation.
- Existing Shadow and canonical market-event work should supply market health/provenance. The live plan should not create new quote callback queues or another `MarketDataStore` ingestion path.
- A new top-level `broker/` package requires updating setuptools package discovery; alternatively infrastructure adapters can live under an existing package. The plan will use `broker/` explicitly and include packaging verification.
- `dashboard/server.py` currently has more than one thousand lines of unrelated uncommitted API work. Implementation should first extract an account-bound portfolio router/module and avoid broad edits to the monolithic server until those changes are reconciled.
- The current worktree has 52 modified tracked files plus untracked work. Implementation must start from a dedicated branch/checkpoint after the owner commits or isolates current work; this planning task must not stack live-order code onto it.

## Resources

- `architecture/asset_portfolio_dual_mode_implementation_report.md`
- `runtime/composition.py`
- `trading/application.py`
- `dashboard/server.py`
- `market_data/provider.py`
- `research/freshness_calibration/`
- Shioaji CA, simulation, order, and callback documentation

## Current Official Shioaji Contract Check (2026-08-22)

- Official CA guidance says order and account APIs require signed documents, simulation testing, and CA activation; simulation accounts do not require CA. The production read-only probe therefore needs a CA-capable secret boundary even though it exposes no order route.
- Official stock-order examples return `PendingSubmit`, then direct callers to `update_status`; exchange order/deal events arrive separately. The adapter return type must not imply fill or final acceptance.
- Official order/deal callback payloads carry broker/account identity, order ids/sequence/order number, deal id/exchange sequence, timestamps, and `custom_field`. Normalize and redact at ingress; do not persist SDK objects or full account identity.
- `custom_field` is only alphanumeric and at most six characters, so it cannot carry the full internal command id. Persist a durable local correlation mapping and treat custom field only as one hint during reconciliation.
- Simulation currently offers order/status/trade and position/PnL APIs but does not support emerging-stock or odd-lot orders.
- Current published limits group accounting reads at 25 calls per 5 seconds, order APIs at 250 calls per 10 seconds, subscriptions at 200, and connections at five per person id. Centralized rate limiters/cache ownership are required; browser refresh must never fan out into broker calls.
- `list_positions` changes quantity units between `Unit.Common` and `Unit.Share`; the anti-corruption adapter must convert everything to internal shares and retain source unit/provenance.
- `account_balance` is officially limited to certain supported banks/accounts. Unsupported or error outcomes must remain typed unavailable evidence, never zero cash or unlimited buying power.
- Settlement reads provide T/T+1/T+2 amounts. These belong in `BrokerBuyingPowerSnapshot` with source timestamps; they are not interchangeable with bank balance or trading limits.
