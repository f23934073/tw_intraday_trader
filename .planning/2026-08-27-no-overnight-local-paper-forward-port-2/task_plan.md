# Task Plan: Forward-port No-Overnight onto Local Paper main

## Goal
Semantically forward-port PR-NO-001 through PR-NO-006 onto merge commit `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`, preserving Kill Switch, `local_paper_fill.v3` tax/slippage truth, and fail-closed No-Overnight safety in Local Paper only, with isolated PostgreSQL and regression evidence.

## Current Phase
Complete — Awaiting later trading-session campaign Gates

## Phases

### Phase 1: Baseline and source verification
- [x] Verify this task worktree, branch/detached state, initial dirty state, exact main/source identities, and ancestry.
- [x] Move the clean task worktree onto `codex/no-overnight-integration-20260827` exactly at `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`.
- [x] Inventory current schema/settings/control-session versions and capture focused/full CI baseline commands/results.
- [x] Record relevant prior project constraints without treating old evidence as current qualification.
- **Status:** complete

### Phase 2: Semantic diff and overlap map
- [x] Enumerate PR-NO-001–006 commits, plans, runbooks, migrations, runtime, application, simulation, risk, API, Dashboard, and evidence runner changes.
- [x] Compare each source change against the Local Paper baseline and classify as reuse, adapt, replace, obsolete, or conflict.
- [x] Freeze schema/migration and immutable-reader compatibility decisions before product edits.
- [x] Self-review the port map and run read-only diff/static checks.
- **Status:** complete

### Phase 3: Durable domain, Journal, checkpoint, and migration port
- [x] Port managed exposure identity and the monotonic No-Overnight state machine without weakening v1/v2/v3 immutable readers.
- [x] Integrate durable breach latch, resolution/ack, checkpoint/restart, and revision semantics with current control-session/Kill Switch durability.
- [x] Resolve additive projection/checkpoint compatibility without adding mutable SQL state.
- [x] Run focused tests and self-review before continuing.
- **Status:** complete

### Phase 4: Application, runtime, and risk integration
- [x] Integrate admission, cutoff progression, cancel/SELL/reconciliation/recovery, and fail-closed restart behavior.
- [x] Preserve Kill Switch durable final admission, exact revision reset, and `RECOVERY_REQUIRED` semantics.
- [x] Ensure unresolved breach blocks only exposure-increasing BUY while recovery-safe actions remain available.
- [x] Run focused tests and self-review before continuing.
- **Status:** complete

### Phase 5: Simulation and monetary-event integration
- [x] Reconcile No-Overnight source assumptions about `local_paper.v2`/fill.v2 with settings v2 and `local_paper_fill.v3` tax/slippage/instrument/settings truth.
- [x] Preserve replay and cash/tax/slippage invariants without rewriting old immutable events.
- [x] Cover partial/cancelled/rejected SELL and terminal-flat proof semantics.
- [x] Run focused tests and self-review before continuing.
- **Status:** complete

### Phase 6: Dashboard, API, and evidence runner integration
- [x] Integrate No-Overnight status/control projections and UI without regressing Kill Switch or Tax/Slippage surfaces.
- [x] Update PR-NO-006 runner/report to bind the active Local Paper session and new exact code identity, rejecting old evidence.
- [x] Preserve Local Paper only/no broker-order/no real-money boundaries.
- [x] Run focused API/frontend/runner tests, static checks, and self-review.
- **Status:** complete

### Phase 7: Full verification and disposable PostgreSQL UAT
- [x] After latest-main sync, rerun complete regression, static/JS/diff checks, schema/migration checks, and replay invariants.
- [x] Provision fresh disposable PostgreSQL databases and prove 0 user tables before destructive UAT.
- [x] Cover restart/new connection, singleton/duplicate process, cutoff races, partial/retry, breach latch/resolution/ack, Kill Switch engage/restart, and fill.v3 invariants.
- [x] Record NOT RUN/NOT PASSED accurately for anything not executed; never promote skip/waiver/no-DSN evidence.
- **Status:** complete

### Phase 8: Independent adversarial review and remediation
- [x] Semantically preserve the merged Shadow fill.v3 fingerprint envelope/read verification from `47a9303`/`f6a38b1`/`254317b` in the shared PostgreSQL reader.
- [x] Request independent runtime-safety and PostgreSQL/schema reviews of the full integration.
- [x] Close eight review rounds with no unresolved P1/P2 and rerun every affected gate.
- [x] Confirm no synthetic fill, broker/live order, CA, trade callback, unattended promotion, or real-money authority was added.
- **Status:** complete

### Phase 9: Scoped local commits and delivery
- [x] Inspect final dirty state and ensure only task-scoped files are included.
- [x] Create one scoped local commit only after verification; do not push or create a PR.
- [x] Deliver semantic port map, file/schema decisions, Gate/UAT evidence, commit identity, and remaining trading-session campaigns.
- [x] State explicitly that G6/production remains NOT PASSED and the result is Local Paper only/no real-money.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use an isolated `.planning/2026-08-27-no-overnight-local-paper-forward-port-2/` plan | Existing root planning files belong to another long-running project phase and must not be overwritten. |
| Treat source branch and all 2026-08-27 evidence as read-only reference | The new integrated code identity requires fresh evidence and cannot inherit qualification. |
| Do not cherry-pick or merge the old branch wholesale | The user requires semantic forward-porting across overlapping Local Paper/Kill Switch/fill.v3 changes. |
| Trust updated `refs/remotes/origin/main` plus the exact requested object, not shared `FETCH_HEAD` | The shared repo's `FETCH_HEAD` retained ancestor `786f452`, while `origin/main` and local baseline both resolve to `037197e1`. |
| Synchronize to `7931d31e` only after a green pre-sync suite and use one transient commit for safe rebase | PM requires latest main, including `47a9303`, `f6a38b1`, and `254317b`, plus a single final scoped commit after revalidation. |
| Fetch once more and rebase the identical one-commit patch onto `d5b86382` | `origin/main` advanced through non-overlapping PR #5/#6 before delivery; range-diff and an empty path intersection prove the reviewed patch did not change. |
| Add `local_paper_fill.v4` rather than reinterpret v2 | v4 carries the complete v3 monetary/instrument/settings truth plus managed identity/action; immutable v1/v2/v3 events remain unchanged. |
| Use the PostgreSQL advisory guard for every Local Paper runtime and transfer it explicitly during a same-process DISABLED settings handoff | Prevents cross-process breach-latch TOCTOU while retaining one reviewed in-process replacement path. |
| Share the exact Kill Switch authority and revoke stale command/strategy-flow mutation during a same-process settings handoff | Prevents cached durable-control divergence and post-archive mutation through old runtime references. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Task worktree initially opened detached at stale `a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9` | 1 | Stopped product work, fetched origin, restored planning artifacts to regain cleanliness, and created the requested branch exactly at `037197e1`. |
| Initial multi-file planning patch targeted the same file with delete/add operations unsupported by `apply_patch` | 1 | No files changed; reinitialized after the baseline gate and used exact update hunks. |
| Ran the Python dashboard-check script with Node, causing a syntax error on its Python docstring | 1 | No files changed; reran the CI command with the shared venv Python and it passed. |
| First generated `apply_patch` conversion kept standard line-number hunk headers, which this patch tool did not accept | 1 | Two new config files had applied; no partial change to the failed file. Converted each modified hunk header to plain `@@` and applied the remaining exact deltas. |
| Initial Phase 3 focused selection included three guard/composition tests before `RuntimeComposition` had been ported | 1 | Recorded the three expected Phase 4 failures; the domain/Journal slice passed `72 passed, 3 deselected`. |
| Parallel PostgreSQL suites in separate databases collided on the cluster-wide advisory key | 1 | Preserved the failure evidence, reran the required suites sequentially, and obtained `39 passed` plus a separate fresh-DB Phase 5 `7 passed`. |
