# Progress Log: Local paper odd-lot support

## Session: 2026-08-22

### Current Status

- **Phase:** 5 - Delivery
- **Status:** complete

### Actions Taken

- Confirmed the requested implementation is scoped to existing local paper simulation, not broker execution.
- Read and applied `planning-with-files` and `karpathy-guidelines`.
- Inspected the current whole-lot UI, API, application adapter, and model constraints.
- Created an isolated plan so the active Freshness calibration plan remains untouched.
- Traced quantity through matching, risk, Journal projection, retry, recovery, and UI; the core arithmetic is already share-based after the initial lot conversion.
- Inspected overlapping user changes in README, Dashboard server/UI, and Dashboard tests; they are unrelated atomic-strategy work and will be preserved with small context patches.
- Ran the broader local-paper baseline across service, command, strategy, recovery, projection, API, realtime, and continuous-strategy tests.
- Added exact-share regression tests for manual/strategy input, partial fill plus retry, restart recovery, API input, and UI quantity semantics.
- Implemented the core share-native model, legacy lot resolver, exact retry/rejection/restore plumbing, API request fields, and share-based order ticket.
- Documented that exact-share orders use the current regular Tick/BidAsk only as a local reference fill model, not the exchange odd-lot book or a broker execution.
- Verified manual exact-share boundaries at 1, 125, 999, 1,000, and 1,500 shares.
- Used the in-app browser against an isolated MockProvider/SQLite dashboard on port 8001: a 125-share 3231 buy returned HTTP 201, displayed `成交 125 股`, and created a `125 股` position.
- Inspected the final scoped diff and preserved the unrelated atomic-strategy, backtest, dashboard, and planning changes already present in the worktree.

### Test Results

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Existing local-paper/API/application focused tests | Baseline passes | 21 passed | PASS |
| Broader local-paper regression baseline | Baseline passes | 80 passed | PASS |
| New odd-lot tests before implementation | Unsupported boundaries fail | 6 failed, 39 passed | EXPECTED FAIL |
| Focused local-paper and UI suite after implementation | All pass | 93 passed | PASS |
| Final exact-share focused suite after boundary expansion | All pass | 81 passed | PASS |
| Python compile, Node syntax, Dashboard JS structure, diff whitespace | All pass | No output / exit 0 | PASS |
| Complete regression | Odd-lot work passes; unrelated work may remain visible | 1,131 passed, 16 skipped, 1 unrelated failure | PARTIAL |
| Full suite except one unrelated migration-order assertion | All remaining tests pass | 1,131 passed, 16 skipped, 1 deselected | PASS |
| MockProvider browser smoke: 125-share manual order | Order and position retain 125 shares | HTTP 201, order 125, position 125 | PASS |

### Errors

| Error | Resolution |
|-------|------------|
| Root planning files are owned by another active task | Used `.planning/2026-08-22-local-paper-odd-lot/` and did not modify the active-plan pointer. |
| Six new tests fail because `quantity_shares` and share UI do not exist yet | Expected red phase; implement only the traced boundaries. |
| UI patch initially placed `quantityShares` in `renderPositions` | Corrected immediately after source inspection by moving it into `renderOrders`. |
| Verification search named an absent `Makefile` | Continued with gates present in `pyproject.toml`, README, and scripts. |
| Default local environment tried PostgreSQL on localhost:5090 and sandbox initially blocked localhost binding | Used explicit SQLite/memory/mock settings and approved localhost port 8001. |
| Port 8000 was already in use | Left the existing process untouched and ran the isolated smoke server on port 8001. |
| Full suite reported one migration-order failure | It is outside this task: untracked migration 008 conflicts with a pre-existing modified test expecting 007 to be last; all other collected tests passed. |

## Session: 2026-08-22 Request Changes follow-up

### Current Status

- **Phase:** 6 - Request Changes remediation
- **Status:** complete

### Actions Taken

- Accepted the three review findings as commit blockers within the existing odd-lot scope.
- Re-read the isolated plan and recovered the unsynced review context.
- Confirmed the shared worktree still contains extensive unrelated changes and must be patched surgically.
- Traced both projection writers: `simulation.js` and `candidates.js` correctly own the dynamic `#order-preview`, confirming the static warning should be a separate sibling element.
- Confirmed both request models use coercive optional `int`, and the existing test suite has FastAPI `TestClient` coverage suitable for JSON boolean rejection tests.
- Confirmed the stale simulation module cache key is asserted directly in `test_dashboard_module_structure.py`.

### Errors

| Error | Resolution |
|-------|------------|
| First boolean HTTP red test reached Shioaji native initialization and segfaulted because coercion allowed the request through | Added explicit `MockProvider` isolation to the negative HTTP tests before rerunning; the default-provider path will not be repeated. |

### Red Test Results

- Cache-key structural test failed on the old `20260821-continuous-paper-v1` import, as expected.
- Static safety-boundary test failed because the warning still shares the dynamic `#order-preview`, as expected.
- Manual-order HTTP test reproduced the reported coercion exactly: JSON `true` returned HTTP 201 instead of 422.
- Strategy-intent HTTP test returned 422 before the strict-field change; its response reason must be checked so the test cannot pass for an unrelated strategy policy.

### Remediation Results

- Added four red/green contracts covering the static boundary, cache key, manual boolean rejection, and strategy boolean rejection.
- Split the permanent safety copy into `#order-simulation-boundary` while preserving `#order-preview` for cash/alert updates.
- Added a strict positive integer Pydantic alias and applied it to both `quantity_shares` and legacy `lots` on both request models.
- Updated the simulation ES-module cache key to `20260822-share-native-v1`.
- Targeted red/green verification: 4 passed.
- Final focused local-paper/UI suite: 83 passed.
- Python compile, app/simulation/candidate Node syntax, Dashboard JS structure, and `git diff --check`: all passed.
- Full repository regression now passes cleanly: 1,135 passed, 16 skipped.
- Browser smoke on isolated MockProvider/SQLite port 8011 confirmed projection rendering updates the cash line but leaves `#order-simulation-boundary` visible and unchanged.
- Browser server logs confirmed the new `simulation.js?v=20260822-share-native-v1` asset was requested with HTTP 200.
- Stopped the isolated browser tab and local smoke server after verification; no staging or commit was performed.

## Session: 2026-08-22 Scoped commit

### Current Status

- **Phase:** 7 - Scoped commit
- **Status:** complete

### Actions Taken

- Received explicit approval to commit the reviewed share-native local-paper scope.
- Confirmed the branch is `codex/organize-uncommitted-20260821` and the worktree still mixes extensive unrelated changes.
- Confirmed `.planning/` must remain outside the runtime commit and no push is authorized.
- Classified the pure share-native files for whole-file staging and isolated the mixed README/Dashboard hunks that require index-only patch staging.
- Confirmed the approved cache chain requires the current `index.html` app entrypoint key, `app.js` simulation import key, and both structural assertions in the same commit.
- Staged the ten pure share-native core/test files as whole files after obtaining Git index write approval.
- Rebuilt a clean `HEAD + staged diff` snapshot under `/private/tmp` so unrelated worktree changes could not affect verification.
- Added the deterministic `FixedClock` API-test fixture after the clean snapshot exposed the date-sensitive strategy test.
- Added the remaining entrypoint cache-key assertion required by the staged `index.html` cache chain.
- Verified the focused staged snapshot with `83 passed`, Python compilation, Dashboard JavaScript syntax, and `git diff --cached --check`.
- Confirmed one full-suite failure (`105.52` versus `105.5`) also fails on a pure HEAD snapshot and is unrelated to this scope; the remaining staged-snapshot suite passed with `1,115 passed, 10 skipped, 1 deselected`.
- Created commit `1a49f41` (`feat(simulation): support share-native paper orders`) with 18 intended files; no push was performed and unrelated worktree changes remain unstaged.

### Errors

| Error | Resolution |
|-------|------------|
| Sandboxed `git add` could not create `.git/index.lock` | Retried the exact scoped Git add with approved repository-index write access. |
| Sandboxed `git add -p` failed only at its final internal `git apply` step | No README hunks were committed to the index; switch the interactive staging command to approved Git-write execution. |
| First staged snapshot failed one date-sensitive strategy API test | Included the existing `FixedClock` fixture and runtime composition cleanup so the test no longer depends on wall-clock date. |
| Full staged snapshot retained one DashboardService close-value failure | Reproduced the same failure on pure HEAD, excluded only that unrelated baseline test, and verified all remaining 1,115 tests. |
