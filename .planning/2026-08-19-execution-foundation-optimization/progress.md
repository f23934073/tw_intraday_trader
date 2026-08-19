# Progress Log

## Session: 2026-08-19

### Current Status

- **Phase:** 6 - Verification and delivery
- **Started:** 2026-08-19

### Actions Taken

- Created this isolated optimization plan; the root planning files and prior isolated plans were preserved.
- Verified the existing full suite baseline: 408 passed, 1 PostgreSQL test skipped locally because `psycopg` is not installed; CI has a PostgreSQL service job.
- Reproduced aggregate pending-BUY overcommit with 150,000 cash and two 106,000 limit reservations; both were accepted before one later rejected at fill time.
- Measured core-module coverage: 84%.
- Replaced float arithmetic inside the simulator with Decimal, preserved the JSON-number response contract, and added pending BUY notional reservations released on fill, rejection, or cancellation.
- Routed dashboard submit/cancel through `LocalPaperCommandService`, which uses the existing `OrderApplicationService`, `RiskGate`, Journal, and compatibility adapter while retaining a local-only execution boundary.
- Bounded callback ingress at 1,024 quote updates by default; queue overflow becomes a visible `BLOCKED` state and blocks route-level submissions through RiskGate.
- Added `/healthz` and `/readyz` that report local simulation health without broker-account queries; the dashboard now exposes blocked/degraded health and reserved cash.
- Added verified JSONL `iter_bars()` use in the backtest worker to avoid the catalog's redundant full-dataset list for normal full snapshots.

### Test Results

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Full pytest | Regression baseline | 408 passed, 1 skipped | pass |
| Python compileall | Syntax validity | passed | pass |
| Pending cash reservation repro | Aggregate exposure should be denied | Existing behavior accepts both orders | confirmed gap |
| Local simulation and command facade | Reservation, Journal, RiskGate, cancellation | 15 focused tests passed | pass |
| Dataset iterator and durable backtest | Existing catalog/run contracts | 27 focused tests passed | pass |
| Dashboard JavaScript syntax and static contracts | Existing UI behavior plus health display | 22 tests passed | pass |
| Full regression suite | All repository contracts | 414 passed, 1 skipped | pass |

### Errors

| Error | Resolution |
|-------|------------|
| Local PostgreSQL adapter test skipped without `psycopg` | Keep it covered by the repository CI service job; do not install or configure an external database for this task. |
