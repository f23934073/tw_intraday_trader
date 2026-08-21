# Findings

- Live session evidence: `quote_mode=SHIOAJI_TICK_BIDASK`, `streaming=false`, `stream_health=DEGRADED`, no subscribed symbols, no quote receipt time.
- Direct error: `Shioaji 即時行情接收端已經啟動`.
- `/readyz` returns 503 and all six local-paper BUY orders remain `SUBMITTED` because no BidAsk can be evaluated.
- `ShioajiProvider.start_quote_stream` rejects a second distinct handler; only `SimulationService` calls this provider method in product code.
- `dashboard.server.get_runtime_composition` lazily reads and writes shared globals without a lock, allowing concurrent first requests to construct duplicate `SimulationService` instances over the same prebuilt provider.
- `get_backtest_service` also lazily assigns the shared `_provider`; it must share the lock but must remain independent from simulation construction.
- Orders to restore: 00909 BUY 1 lot at 46.30 three times, 00909 BUY 1 lot at 46.29 once, 6830 BUY 1 lot at 452.00 once, 3081 BUY 1 lot at 2850.00 once.
- The operation remains local paper: `execution_authority=false`; Shioaji supplies market data only.
- The singleton repair works in the restarted process: simulation reports `streaming=true`, `stream_health=HEALTHY`, and no duplicate callback error.
- All six restore requests were safely rejected before mutation; projection still contained zero orders and zero positions.
- Both snapshot and manual refresh reported `loaded_symbols=0`, so `SimulationService._get_stock()` could not resolve a contract before creating each order.
- Shioaji 1.7 contract loading is automatic/lazy. A standalone immediate `fetch_contracts(contract_download=True)` collided with the login-triggered SDK call (`exclusive access lost`), so startup must wait for readiness instead of issuing a competing fetch.
- Live read-only probes resolved 00909 (`StockInfo`, 國泰數位支付服務) and 2330 contracts, but `snapshots()` returned an empty list for both legacy and modern contract objects.
- Streaming simulation does not need a snapshot to create a pending order: the catalog supplies canonical symbol/name, and fill evaluation already waits for a recent BidAsk best price.
- Live subscription acknowledgements succeeded for Tick and BidAsk on 00909, 6830, and 3081. 6830 filled twice in separate recovery sessions from real BidAsk events (451.0 and 449.5), proving callback-to-fill works.
- Official quote cross-check at 11:45 showed best asks 00909=46.25 and 3081=2855; 00909 limits were marketable while 3081 limit 2850 was not. The 00909 Shioaji subscription had not emitted a post-subscription book event, so the conservative local simulator correctly lacked execution evidence.
- A five-second Shioaji Quote-v2 probe also produced no initial event. Official Shioaji docs describe event-driven subscriptions but do not guarantee initial state replay.
