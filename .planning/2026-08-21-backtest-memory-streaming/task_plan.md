# Task Plan: Large backtest memory optimization

## Goal

Reduce historical backtest peak memory so large multi-symbol datasets no longer require materializing and globally sorting every Kbar, while preserving deterministic strategy, fill, accounting, and result semantics.

## Current Phase

Phase 4 — Verification complete

## Phases

### Phase 1: Baseline and ordering audit

- [x] Trace dataset storage order, parent/delta loading, engine grouping, and result persistence.
- [x] Establish a focused regression baseline and a synthetic memory profile.
- [x] Identify which state is truly required across symbols/sessions.
- **Status:** completed

### Phase 2: Streaming contract and red tests

- [x] Freeze an iterator contract that supports full and delta datasets.
- [x] Add parity tests comparing the current materialized path with the streaming path.
- [x] Add guards proving the engine consumes one session at a time and delta replay does not call full-dataset `load_bars()`.
- **Status:** completed

### Phase 3: Surgical implementation

- [x] Add bounded dataset iteration or external merge at the catalog boundary.
- [x] Refactor the engine/application worker to consume bounded ordered input.
- [x] Keep existing public API/results and legacy fixtures compatible.
- **Status:** completed

### Phase 4: Verification

- [x] Run focused engine, dataset, application, API, and strategy regressions.
- [x] Compare deterministic result payloads and digests across old/new paths.
- [x] Measure peak memory on a representative synthetic multi-symbol dataset.
- [x] Run the complete repository suite and static checks.
- **Status:** completed

## Decisions Made

| Decision | Rationale |
|---|---|
| Stop all database-recovery work | The user confirmed the deleted database cannot be recovered. |
| Optimize against generated fixtures and immutable local datasets | No Shioaji quota or historical database is required. |
| Preserve event-time and tie-break ordering exactly | Memory improvement cannot change cross-symbol cash, position, or fill results. |
| Avoid touching unrelated dirty files where an additive seam is possible | The worktree contains broad user-owned changes. |
| Accept bounded temporary-disk sorting for symbol-major/legacy payloads | It prevents RAM from scaling with the entire dataset while preserving global event order. |
| Keep result collections in memory in this slice | The dominant production blocker was Kbar materialization; changing result persistence would be a separate contract migration. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Standalone synthetic profiler imported the test module before the pytest SQLite environment boundary, so fail-closed PostgreSQL config rejected the missing DSN | 1 | Re-run the diagnostic with explicit process-local `BACKTEST_DATABASE_BACKEND=sqlite`; do not weaken production configuration. |
