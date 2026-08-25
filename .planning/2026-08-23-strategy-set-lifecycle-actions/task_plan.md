# Task Plan: Strategy Set lifecycle actions

## Goal

Let users revise and remove saved Strategy Sets without mutating or breaking exact-version evidence already referenced by backtests or Local Paper.

## Current Phase

Complete

## Phases

### Phase 1: Repository contracts and dependency audit

- [x] Trace Strategy Set persistence, references, API, and audit contracts.
- [x] Decide lifecycle-safe semantics for modify and delete.
- **Status:** complete

### Phase 2: Backend lifecycle implementation

- [x] Add the smallest repository/application/API operations required.
- [x] Preserve exact-version snapshots, idempotency, CSRF, and conflict behavior.
- **Status:** complete

### Phase 3: Dashboard interactions

- [x] Add accessible modify/remove actions and confirmation/feedback.
- [x] Keep existing immutable-version terminology accurate.
- **Status:** complete

### Phase 4: Verification

- [x] Add focused domain, API, persistence, and UI tests.
- [x] Run JavaScript, focused regression, diff, and browser interaction checks.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|---|---|
| Never edit an existing exact snapshot in place | Existing backtests and activations must remain reproducible. |
| Resolve delete semantics only after reference audit | Hard deletion may break evidence or database references. |
| Implement delete as archive | Users can remove a family from active selectors without destroying historical snapshots. |
| Implement modify as next-version creation | The existing `(strategy_set_id, version_number)` contract already models immutable revisions. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| Initial search referenced a non-existent top-level `migrations` directory | 1 | Re-ran against the actual `backtest/migrations` path. |
| Initial migration-runner read used `backtest/migrations/__init__.py` instead of `backtest/migrations.py` | 1 | Located the functions with `rg` and read the correct module. |
