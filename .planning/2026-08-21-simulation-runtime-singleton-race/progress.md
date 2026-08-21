# Progress

## 2026-08-21

- Confirmed the six orders cannot fill in the current process because simulation streaming failed before any subscription was created.
- Traced the provider guard, simulation startup, and unlocked lazy composition construction.
- Captured the six order payloads needed for post-restart restoration.
- Activated `karpathy-guidelines` and `planning-with-files`; scoped the repair to atomic singleton construction plus verification.
- Added a focused concurrent-first-access regression with a provider that rejects a second distinct stream handler.
- Confirmed the regression fails before the repair because concurrent callers receive different compositions.
- Added one module-level `RLock` around runtime construction and shared-provider backtest construction.
- Focused simulation API suite passes: 9 tests.
- Full regression passes: 1009 tests, 2 skipped.
- Dashboard JavaScript graph and whitespace checks pass.
- Scoped code change only serializes local runtime construction; broker/order/account/CA boundaries are unchanged.
- Restarted PID 18050 as repaired PID 24251 with Shioaji market data; session is now streaming and healthy.
- First restoration attempt created no orders because the Journal-first facade rejected every payload as audit-incomplete; paused retries for root-cause analysis.
- Confirmed the underlying handler failure: the restarted provider was streaming but exposed an empty Shioaji stock-contract catalog (`loaded_symbols=0`).
- Verified that starting a second explicit contract fetch is unsafe during the SDK's automatic post-login load; returned to implementation for a bounded contract-readiness gate.
- Added a bounded wait for the SDK's automatic stock-contract catalog load; timeout explicitly fails startup and logs out.
- Contract-readiness, simulation, and realtime quote focused suites pass: 26 tests.
- Complete regression passes after both repairs: 1012 tests, 2 skipped; dashboard JavaScript and whitespace checks also pass.
- Traced the remaining 409 to `Snapshot not found: 00909`; a standalone read-only probe confirmed zero snapshots for both 00909 and 2330 in this Shioaji simulation session.
- Added contract-identity-only admission for streaming orders; no fallback price is synthesized and fills remain recent-BidAsk-only.
- Added fail-closed risk health when a streaming provider cannot start.
- Complete regression after the snapshotless-stream repair passes: 1015 tests, 2 skipped; dashboard JavaScript and whitespace checks pass.
- Restored all six orders successfully (HTTP 201) and observed 6830 fill from live BidAsk, with three paired subscriptions healthy and quote timestamps advancing.
- Confirmed subscription cold-start behavior does not guarantee replay of the existing order book; retained no-synthetic-fill semantics.
- Added order-level bid/ask timestamps and explicit pending reasons to the API and Traditional Chinese UI.
- Final full regression passes: 1017 tests, 2 skipped; dashboard JavaScript and whitespace checks pass.
- Started the repaired dashboard as transient macOS user service `com.codex.tw-intraday-dashboard` (PID 32578), so it survives this task without becoming a login item.
- Restored the exact six paper-order payloads into the final session.
- Final outcome: four 00909 orders filled at 46.24, one 3081 order filled at 2850, and one 6830 order correctly remains submitted because live ask 452.5 exceeds its 452 limit.
- Browser acceptance passed: WebSocket timestamp advances, six order cards and two positions render, the 6830 card shows live bid/ask plus `未達限價`, and no browser console errors were present.
