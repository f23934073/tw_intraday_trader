# Progress Log

## Session: 2026-08-21

### Current Status

- **Phase:** 1 — Baseline and ordering audit
- **Status:** in_progress

### Actions Taken

- Received explicit authorization to prioritize large-backtest memory optimization.
- Stopped the deleted-database recovery line of work.
- Re-read the file-based planning and surgical coding instructions.
- Restored session context and confirmed the repository has a broad pre-existing dirty worktree.
- Created this isolated plan without changing `.planning/.active_plan`.
- Confirmed the application worker already uses the catalog iterator.
- Located the remaining primary peak: engine global sort plus full `by_session` retention.
- Found two avoidable superlinear scans for terminal and per-session last timestamps.
- Confirmed global event ordering cannot be replaced by independent symbol runs because cash and position sizing are shared.
- Focused pre-change baseline passed: 16 engine/strategy tests.
- The first standalone memory profiler hit the intended fail-closed PostgreSQL configuration because it ran outside pytest's environment fixture; production code was not changed.
- Re-ran the profiler with process-local SQLite configuration: 30,000 bars, 6.683 seconds, 12.96 MiB engine peak, 597 trades.
- Froze the first implementation slice: bounded external event ordering at the catalog, one-session engine buffering, and compact terminal/count metadata from the manifest.
- Added six red contracts for result parity, bounded session consumption, fail-closed ordering, symbol-partition external merge, non-materialized delta merge, and legacy manifest compatibility.
- Confirmed the new contracts fail only because the ordered iterator, payload-order metadata, and ordered engine inputs do not exist yet: 6 expected failures.
- Added optional payload-order metadata without changing legacy manifest serialization.
- Added bounded external merge ordering with a 50,000-bar chunk and 32-file merge fan-in.
- Added ordered parent/delta stream merging that avoids `load_bars()`.
- Refactored the engine to retain one session instead of a global session map and removed the per-symbol repeated scans.
- Wired the application worker to the ordered catalog iterator plus compact manifest count and terminal timestamps.
- New streaming contract suite passes: 6 passed.
- Focused backtest, dataset, download, incremental, API, strategy, and pilot regressions pass: 59 passed.
- Repeatable disk-to-engine profile on 30,000 bars produced identical result digests and reduced peak traced allocation from 39.43 MiB to 14.25 MiB (63.9%).
- The profile records a small-workload runtime tradeoff: 8.233 seconds materialized versus 8.982 seconds streaming.
- Python compile check and diff whitespace check passed.
- Complete repository suite passes: 1,059 passed, 4 skipped.

### Next

- Ready for user review. No database recovery or Shioaji calls were attempted.
