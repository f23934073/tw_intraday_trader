# Task Plan: 2026-08-28 trading-day job audit and recovery

## Goal

Identify every in-scope job expected on the 2026-08-28 Taiwan trading day, verify scheduler and immutable runtime evidence, repair only confirmed defects, review and test the repair, then execute at most one approved recovery run without enabling real-money orders.

## Safety boundary

- Fail closed on broker order, cancel, CA activation, trade callback, or real-money authority.
- Preserve existing artifacts and unrelated dirty-worktree changes.
- Do not claim a job passed from scheduler metadata alone.
- Do not rerun an immutable one-shot capture unless its contract and the user's authorization both permit the exact recovery run.

## Phases

### Phase 1: Establish today and expected-job inventory

- [x] Verify the official/repository trading-calendar result for 2026-08-28.
- [x] Inventory installed/configured jobs and their expected windows.
- [x] Classify data-only, broker-read-only, simulation, and execution-authority boundaries.
- **Status:** complete

### Phase 2: Verify scheduler and artifact outcomes

- [ ] Inspect current scheduler state, logs, claims, exit results, and immutable artifacts.
- [ ] Reconcile each expected run as PASS, FAIL, NOT_RUN, RUNNING, or NOT_APPLICABLE.
- [ ] Record exact root cause for every gap.
- **Status:** in_progress

### Phase 3: Minimal remediation

- [ ] Reproduce confirmed defects with focused checks/tests.
- [ ] Apply only the smallest safe fix.
- [ ] Preserve live-trading and immutable-evidence fences.
- **Status:** pending

### Phase 4: Review and verification

- [ ] Review changed lines for correctness, safety, races, error handling, and test coverage.
- [ ] Run focused tests and proportional regression/static checks.
- [ ] Issue APPROVE only with zero blocking findings.
- **Status:** pending

### Phase 5: One recovery run and final audit

- [ ] Re-run only the approved in-scope job once, inside its allowed contract/window.
- [ ] Inspect exit status and resulting artifacts/logs.
- [ ] Report final per-job disposition and remaining blockers.
- **Status:** pending

## Success criteria

- Complete per-job evidence table for 2026-08-28.
- Any code/config repair has a reproducing regression and passes review.
- No live order authority or destructive state change is introduced.
- Recovery run is exactly once and truthfully classified from artifacts.

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| launchd cannot read dedicated Documents worktree | 1 | Preserved exit 78/no claim; used the explicitly authorized reviewed external recovery path once. |
| Shioaji token-pool initialization cannot find home directory | 1 | Preserved formal claim/result; identified missing HOME in minimal child environment. No retry after claim. |
| py_compile could not write `__pycache__` in protected pinned worktree | 1 | Re-ran syntax compilation with `PYTHONPYCACHEPREFIX` under `/private/tmp`; passed without mutating runtime identity files. |
