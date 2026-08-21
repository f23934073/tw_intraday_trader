# Findings & Decisions

## Requirements

- Improve large historical backtest memory use before acquiring replacement data.
- Preserve the current deterministic results, strategy semantics, next-bar fills, costs, and output contracts.
- Do not use Shioaji or attempt deleted-database recovery.
- Keep the implementation bounded to historical datasets/backtests.

## Starting Hypothesis

- The current catalog exposes `load_bars()` as a full list.
- The current engine performs a second global `sorted(...)` and creates session groupings, so large datasets may have multiple simultaneous in-memory representations.
- The actual optimization must be chosen only after confirming storage order and cross-symbol portfolio dependencies.

## Confirmed Hot Path

- `_run_backtest()` already calls `HistoricalDatasetCatalog.iter_bars()`, so full JSONL input no longer creates the catalog's first redundant list.
- `HistoricalBacktestEngine.run()` immediately rebuilds a full `ordered = sorted(...)` list, then retains every bar again inside `by_session` lists. Peak memory therefore still contains the full sorted list plus full session-index containers.
- Terminal timestamps are computed with one full scan per symbol, and session-last timestamps with one session scan per symbol. These comprehensions are `O(N × symbols)`, not merely memory-heavy.
- The engine needs `is_last_bar` for end-of-day exits and `is_terminal_dataset_bar` for terminal behavior. Any streaming path must preserve both facts before strategy evaluation.
- Cross-symbol cash and position sizing depend on global `(timestamp, symbol)` order, so independent per-symbol backtests would change results and are rejected.
- `iter_bars()` directly streams full JSONL in file order, but provider-partition sealing writes symbol-major partitions. Imported datasets are timestamp-major. A production streaming path therefore needs an explicit ordered-input contract or bounded external ordering; assuming file order would be incorrect.
- Delta datasets currently call `load_bars()` and materialize parent plus delta. They require a separate ordered merge after the full-snapshot path is safe.
- `trade_chart()` also loads the full dataset, but it is a read-side drill-down rather than the active backtest hot path and remains out of the first optimization slice.

## Baseline Evidence

- Focused engine/strategy regression: `16 passed` before the streaming change.
- Synthetic workload: 100 symbols × 60 sessions × 5 bars = 30,000 bars.
- With input bars allocated before `tracemalloc`, the current engine itself peaked at 12.96 MiB and took 6.683 seconds. The superlinear terminal/session scans dominate this small workload before production-scale memory is reached.
- The replacement contract will allow a bounded session buffer while eliminating the full `ordered` list, full `by_session` map, and repeated symbol scans.

## Chosen First Slice

- Add a catalog `iter_bars_ordered()` contract. Timestamp-major payloads stream directly; unknown/symbol-major payloads use bounded disk-backed external merge sorting.
- Stream the engine one session at a time. A single session is retained so end-of-day strategies still know each symbol's true last bar.
- Pass compact manifest bar count and per-symbol terminal timestamps from the application worker; do not rediscover terminals by rescanning all bars per symbol.
- Keep the existing unsorted `run()` behavior for direct callers, while the application worker opts into the verified ordered stream.
- Bound external-sort fan-in so a full-market dataset cannot exhaust file descriptors.

## Issues Encountered

| Issue | Resolution |
|---|---|
| The first checked-in profiler invocation could not import the repository package because its script directory became `sys.path[0]` | Re-ran with the repository root on `PYTHONPATH`; no product configuration changed. |

## Final Evidence

- New streaming contract suite: 6 passed.
- Focused historical-backtest regression set: 59 passed.
- Complete repository suite: 1,059 passed, 4 skipped.
- Compile check and whitespace/error-marker check passed.
- Same 30,000-bar JSONL workload and same result digest:
  - materialized replay: 39.43 MiB peak, 8.233 seconds;
  - ordered streaming replay: 14.25 MiB peak, 8.982 seconds;
  - peak traced allocation reduced by 63.9%.
- The small synthetic run paid about 9.1% runtime overhead for per-event streaming validation. The large-data benefit is bounded Kbar residency: one session plus compact symbol state rather than all parsed bars and all session containers.
- Unknown/legacy and symbol-major datasets require temporary disk capacity for external sorting. Newly imported timestamp-major datasets stream directly without that sort.
