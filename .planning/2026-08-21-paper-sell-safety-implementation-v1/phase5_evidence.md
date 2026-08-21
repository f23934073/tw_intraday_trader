# Phase 5 Paper Sell UAT Evidence

## Scope

- Local paper simulation only; no broker order API or real-money execution.
- Base commit: `6f7a8424270a1688b3dcd3fbd12116107ee415a6`.
- Unattended development is deferred to Phase 6.

## Dirty-worktree failure isolation

- Built `/tmp/tw-intraday-phase5-isolation.lQkDvW` from the base commit.
- Overlaid only the current `backtest/`, migration test, and test configuration.
- Did not overlay simulation, trading, runtime, dashboard, or Phase 5 product
  changes.
- The then-current migration-list failure reproduced as `1 failed, 3 passed`,
  proving it belonged to the independent atomic-backtest slice.
- Subsequent concurrent atomic-backtest changes resolved that failure; the final
  complete repository suite is green.

## Rerunnable UAT command

```bash
TEST_POSTGRES_DSN=postgresql://... \
  .venv/bin/python scripts/run_phase5_paper_sell_uat.py
```

The runner refuses memory fallback and exits 2 when `TEST_POSTGRES_DSN` is
absent.

## UAT matrix

| Case | Acceptance evidence |
|---|---|
| Ownership rejection | Automated strategy cannot sell a manual position; position remains owned and open. |
| Stale BidAsk | SELL is rejected with `BOOK_STALE`; a fresh Tick cannot authorize an old executable book. |
| SELL rejection | Controller reports `EXIT_REJECTED`, never `EXIT_SUBMITTED`. |
| Timeout and retry | Pending order becomes `CANCELLED`; one bounded successor is created and exhaustion fails closed. |
| Partial fill | Two best-level volume updates produce two fill deltas, then `FILLED` with the expected 2,000-share position. |
| 13:30 reconciliation | Pending automated SELL is cancelled and the remaining position escalates `ALERT_EXIT_UNRESOLVED`. |
| PostgreSQL restart | Three independent runtime generations restore position, pending order, 100,000 reservation, idempotency, timeout cancellation, released reservation, and `ORDER_TIMEOUT_CANCELLED`. |

## Execution results

- Disposable database: official `postgres:16-alpine`, image digest
  `sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685`.
- Real PostgreSQL UAT: `7 passed in 0.33s`.
- Focused regression: `152 passed, 1 skipped in 0.86s`.
- Full repository regression: `1100 passed, 10 skipped in 6.15s`.
- Dashboard JavaScript syntax, Python compileall, and `git diff --check`: passed.
- Disposable UAT container was stopped and auto-removed after verification;
  no container with the Phase 5 name remains.

## Gate after Phase 5

- Attended paper smoke/UAT implementation evidence: `GO`.
- Unattended: `NO-GO`; Phase 6 backlog remains open.
- Performance credibility: `NO-GO`; fees, taxes, slippage, and queue priority
  remain outside the simulator contract.
- Repository test health: `GREEN`.
- Merge packaging: `PENDING`; no scoped commit or push exists, and the worktree
  contains unrelated changes.
