# Task Plan: Repair Simulation Runtime Singleton Race

## Goal
Guarantee that one process constructs exactly one shared `RuntimeComposition` and one simulation quote callback, then restart the Shioaji market-data-only dashboard, restore the six local-paper orders, and verify BidAsk-driven outcomes.

## Current Phase
Complete

## Phases

### Phase 1: Regression and repair
- [x] Add a concurrency regression that reproduces duplicate runtime construction.
- [x] Serialize runtime and shared-provider initialization with one narrow lock.
- [x] Run focused tests.
- **Status:** completed

### Phase 2: Regression verification
- [x] Run JavaScript/static checks and the complete Python suite.
- [x] Confirm no broker order/account/CA capability was introduced.
- **Status:** completed

### Phase 3: Runtime recovery
- [x] Preserve the six pending local-paper order payloads.
- [x] Stop the exact broken local dashboard process and start the repaired Shioaji process.
- [x] Wait for the automatically loaded Shioaji stock catalog before exposing the provider.
- [x] Re-submit the same six local-paper orders.
- **Status:** completed

### Phase 4: Live verification
- [x] Verify streaming health, paired subscriptions, and quote receipt.
- [x] Classify each restored order as correctly filled or pending against live ask.
- [x] Verify browser/WebSocket projection and document the result.
- **Status:** completed

## Decisions

| Decision | Rationale |
|---|---|
| Use one module-level reentrant lock | Minimum change that makes the existing lazy singleton atomic and also protects shared provider creation. |
| Lock `get_backtest_service` with the same lock | Prevent the independent historical service from racing `_provider` assignment without forcing it to create the simulation runtime. |
| Re-submit exact order payloads after restart | The user approved recovery after being warned that process-local orders are cleared by restart. |
| Keep Shioaji market-data-only | The repair must not enable broker execution, accounts, CA, or trade callbacks. |
| Poll the SDK's automatic stock-contract load | Shioaji 1.7 loads contracts lazily; an immediate explicit `fetch_contracts` conflicts with that automatic call, while a bounded readiness poll does not start a second API request. |
| Admit streaming orders from contract identity | This Shioaji simulation session returns no snapshots even for valid contracts; contract identity can validate the symbol while actual fill remains strictly BidAsk-driven. |
| Expose pending quote evidence | Event-driven subscriptions do not guarantee an initial replay; the order projection must distinguish first-book wait, stale-book wait, and limit-not-reached without synthesizing a fill. |

## Errors Encountered

| Error | Resolution |
|---|---|
| Current runtime has `streaming=false`, zero subscriptions, and duplicate callback error | Add atomic singleton construction, regression coverage, then restart. |
| First test patch expected imports before an existing `Decimal` import | Re-read the live test file and applied a narrower context without touching concurrent changes. |
| All six restored POSTs were rejected with `委託稽核未完成` | No orders were created; stop retries and trace the Journal-first command path before changing anything. |
| First standalone contract-fetch probe did not load `.env` | It failed before login; retry with `load_dotenv()` without printing credential values. |
| Second probe assumed `ContractsTypedView` supports `len()` | The SDK view is not sized; switch to a direct 2330 lookup after `fetch_contracts` and guarantee logout in `finally`. |
| Explicit `fetch_contracts(contract_download=True)` lost exclusive access | Do not start a competing contract fetch; wait for the login-triggered automatic catalog load instead. |
| Repaired server reported `loaded_symbols=0` | Add a bounded provider-startup readiness gate so simulation orders are not accepted against an empty contract catalog. |
| 00909 and 2330 both returned zero snapshots | Do not require snapshot for streaming order admission; resolve symbol/name from the loaded contract catalog and wait for real Tick/BidAsk. |
| Quote/Tick/BidAsk subscriptions did not replay 00909's existing book | Preserve conservative BidAsk-only fills and expose the exact wait reason plus live bid/ask when received. |
