# Findings & Decisions

## Requirements

- Optimize the reviewed project in place while preserving unrelated dirty worktree changes.
- Do not add broker orders, CA activation, broker account reads, or a real-money mode.
- Keep historical evidence and FreshnessPolicy thresholds fail-closed until genuine collection/review completes.

## Confirmed Findings

- The simulation API directly invokes `SimulationService`; the existing `OrderApplicationService`, RiskGate, Journal, and compatibility adapter are deliberately not wired.
- Two pending BUY orders can exceed the same virtual cash balance because the simulator checks each order independently and creates no cash reservation.
- Simulation uses a `SimpleQueue`, so a high-rate callback source has no bounded-memory or overflow contract.
- Momentum already has richer ordered event/health contracts, while simulation retains a compatibility quote DTO path.
- Full backtests load and sort every bar in memory; this conflicts with the documented full-market three-year target.
- Current research datasets remain exploratory unless a date-effective universe and per-session completion evidence are supplied.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Add a narrow local-paper facade, not a generic broker layer | The existing `trading/` application contracts are sufficient for current scope. |
| Reserve worst-case BUY notional at the limit price | This prevents aggregate overcommit; a lower fill releases the difference. |
| Use a bounded `Queue` with terminal overflow health | Dropping quote callbacks must never silently preserve entry eligibility. |
| Stream catalog data where possible | Avoid changing immutable dataset formats before a measured need for Parquet/DuckDB. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Worktree contains active unrelated implementation work | Changes are confined to new/owned optimization files and focused seams. |

## Resources

- `trading/application.py`, `trading/risk.py`, `trading/journal.py`
- `simulation/service.py`, `dashboard/server.py`, `runtime/composition.py`
- `market_data/health.py`, `market_data/ingestion.py`, `backtest/dataset.py`
