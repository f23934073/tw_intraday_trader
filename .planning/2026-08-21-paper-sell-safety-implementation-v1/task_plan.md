# Task Plan: Paper Sell Safety and Recoverable Orders

## Goal

Implement the six direct paper-trading sell safety fixes, then add a recoverable
order state machine covering partial fills, timeout, cancel, retry, expiry,
alerts, and restart recovery. Reassess unattended readiness only after focused
concurrency, cross-day, and market-close boundary tests pass.

## Scope Guardrails

- Local paper simulation only; no broker order APIs or real-money execution.
- Preserve unrelated dirty-worktree changes.
- Use one executable BidAsk timestamp and policy threshold across controller,
  risk, and simulator execution.
- Treat trading-day opening equity as the daily-loss baseline and explicitly
  freeze unrealized-PnL inclusion in code/tests.

## Phases

### Phase 1: Baseline and contract trace

- [x] Read repository rules and the current simulation/controller/order tests.
- [x] Trace ownership, quote timestamps, risk ordering, close handling,
  controller construction, persistence seams, and existing order states.
- [x] Capture focused baseline tests and exact failing acceptance probes.
- **Status:** complete

### Phase 2: Six direct safety fixes

- [x] Enforce strategy position ownership for automated SELL.
- [x] Unify executable BidAsk receipt time and freshness threshold.
- [x] Drive controller state from SELL submission/fill result.
- [x] Permit risk-reducing exits before daily-loss entry blocking.
- [x] Reconcile or escalate unresolved exits after 13:30.
- [x] Serialize automated controller singleton construction.
- **Status:** complete

### Phase 3: Recoverable order lifecycle

- [x] Define minimal persistent lifecycle and legal transitions.
- [x] Implement partial fill, timeout, cancel, bounded retry, expiry, and alerts.
- [x] Restore pending automated orders and controller state on restart without
  duplicate intents.
- [x] Expose retry and recovery alerts through the operator API/dashboard.
- **Status:** complete

### Phase 4: Boundary and regression verification

- [x] Add race, stale-book/fresh-Tick, cross-day loss, partial-fill, close,
  timeout/retry/expiry, and restart tests.
- [x] Run focused suites, full regression, static checks, and `git diff --check`.
- [x] Reassess unattended readiness from evidence; do not assume GO from green
  tests alone.
- **Status:** complete (`152 passed` focused; full suite has two unrelated
  atomic-backtest dirty-worktree failures)

### Phase 5: Isolation evidence and operator UAT

- [x] Reproduce the two full-suite failures in an isolated snapshot that omits
  this paper-sell implementation, or leave merge readiness blocked if the same
  failure cannot be proven independently.
- [x] Execute the operator UAT matrix for ownership rejection, stale BidAsk,
  reject/retry, partial fill, 13:30 reconciliation, and PostgreSQL restart
  recovery.
- [x] Save rerunnable UAT evidence with order, position, alert, and Journal
  assertions; success requires `FILLED` plus the expected final position.
- [x] Rerun focused/full/static verification and update the four readiness gates.
- **Status:** complete (`7 passed` real PostgreSQL UAT; `152 passed, 1 skipped`
  focused; `1100 passed, 10 skipped` full repository)

### Phase 6 TODO: Unattended readiness development

- [ ] Persist and approve durable controller enablement/restart policy.
- [ ] Make PostgreSQL persistence mandatory and verify startup health in the
  unattended deployment profile.
- [ ] Deliver lifecycle alerts to an externally monitored notification channel.
- **Status:** backlog; explicitly deferred until Phase 5 is complete

## Decisions

| Decision | Rationale |
|---|---|
| Two implementation batches | Matches the approved review and isolates immediate safety from lifecycle recovery. |
| Opening equity baseline includes unrealized PnL | Equity is cash plus marked positions; this avoids distorted cross-day risk when holdings span sessions. |
| Preserve local-paper boundary | The request authorizes simulator safety, not broker/account trading integration. |
| Keep unattended as NO-GO | Default memory persistence, manual controller restart, and local-only alerts remain operational blockers despite completed order recovery. |
| Isolate before attributing full-suite failures | Dirty-worktree failures are not evidence of independence until reproduced without this task's changes. |
| Defer unattended implementation | Phase 5 is evidence/UAT only; durable controller enablement, mandatory PostgreSQL, and external alerts belong to the next development phase. |
| Separate repository green from merge packaging | The current full suite is green, but the large mixed dirty worktree has not been reduced to a reviewed scoped commit. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `read_thread` rejected `turnLimit=20` | 1 | Retried with the supported maximum of 10 and obtained the referenced task context. |
| `pytest` command was not on `PATH` | 1 | Locate the repository virtual environment and rerun through its Python module entrypoint. |
| Test-invocation search named an absent `Makefile` | 1 | Use the confirmed `.venv/bin/python -m pytest` entrypoint from the repository environment. |
| First multi-section SimulationService patch missed the live payload context | 1 | No product file changed; split into small exact-context patches against the current dirty file. |
| Combined partial-fill model/provider patch missed helper context | 1 | No file changed; apply model fields first, then patch provider against the exact helper body. |
| Planning update expected a nonexistent `Implementation findings` heading | 1 | No file changed; append to the actual findings/progress sections with exact context. |
| New lifecycle test imported nonexistent `simulation.errors` | 1 | Product code did not run; import the public `SimulationStateError` export from `simulation`. |
| Runtime composition test expected the initial checkpoint at sequence 0 | 1 | Update the contract to sequence 1 because the initial daily risk baseline is now an intentional durable record. |
| Full pytest collection failed in unrelated trade-management fixture | 1 | Record the exact import-time canonical identity failure, preserve that dirty-worktree scope, and rerun the full suite excluding only that unrelated file to expose any additional regressions. |
| Phase 5 shell probe assigned to zsh reserved `status` | 1 | Test execution completed; future probes use a task-specific variable such as `phase5_pg_exit`. |
| Isolation command's final `echo` masked pytest's shell exit code | 1 | The pytest output still proves the identical failure; record the output and use explicit task-specific exit propagation in any reusable UAT script. |
| Docker daemon socket denied by sandbox | 1 | Rerun the read-only daemon availability check with the required sandbox escalation before creating any disposable database. |
