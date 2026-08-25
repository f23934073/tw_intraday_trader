# Task Plan: Configurable local-paper cash, daily buy limit, and fee settings

## Goal

Implement the approved local-paper settings design so starting cash, daily gross BUY limit, and buy/sell fee settings are editable and persistently applied through the existing dashboard.

## Scope boundary

- Planning remained read-only until the user issued the explicit `process` command; implementation is now authorized.
- Modify only the local-paper settings, risk, accounting, recovery, API, UI, documentation, and focused tests required by the approved plan.
- Preserve the local-paper/no-real-broker-order boundary.
- Do not change `.planning/.active_plan`.

## Phases

### Phase 1: Requirement update and current-state inspection

- [x] Incorporate both user annotations.
- [x] Trace the current settings UI, settings API, persistence, and runtime composition.
- [x] Trace current local-paper cash and fee ownership.
- **Status:** complete

### Phase 2: Contract and lifecycle design

- [x] Define editable fields, validation rules, defaults, and currency precision.
- [x] Define when changes take effect and how active sessions are handled.
- [x] Define persistence, restart recovery, and failure behavior.
- **Status:** complete

### Phase 3: Implementation plan and acceptance criteria

- [x] Map phased changes to exact modules and tests.
- [x] Define rollout, rollback, and non-goals.
- [x] Deliver the updated plan without implementing it.
- **Status:** complete

### Phase 4: Authorized implementation

- [x] Capture focused regression baseline and protect unrelated dirty-worktree changes.
- [x] Add settings contract/persistence and settings-bound runtime wiring.
- [x] Add daily BUY budget and commission accounting with restart recovery.
- [x] Add settings API/page and visible session metrics.
- [x] Run focused/full regression, browser smoke, and static checks.
- **Status:** complete

### Phase 5: Review remediation and re-verification

- [x] Fail closed when a settings-bound Journal session metadata contract differs from the requested settings.
- [x] Build and validate a replacement runtime before swapping globals; keep the old runtime live on every pre-commit failure.
- [x] Enforce TWD-cent precision for minimum commission.
- [x] Separate gross daily BUY reservation from commission-inclusive cash reservation in the UI.
- [x] Complete `local_paper_fill.v2` evidence and old-session terminal/archive evidence.
- [x] Add regression tests for all five findings and rerun focused/static/full verification without hiding unrelated failures.
- **Status:** complete

### Phase 6: Legacy and stream-handoff P1 remediation

- [x] Reproduce recovery with the real pre-feature legacy metadata plus v1 fill/checkpoint evidence.
- [x] Narrow partial settings-binding detection so the historical `execution_boundary=LOCAL_ONLY` field remains legacy-compatible.
- [x] Make replacement quote-stream activation report Provider failures instead of degrading silently.
- [x] Perform a rollback-capable stream handoff before settings pointer/archive/global commit; restore the same old simulation object and handler on failure.
- [x] Add both P1 regression tests and rerun focused, complete, compilation, JavaScript, and diff verification.
- **Status:** complete

### Phase 7: Runtime-command lease P1 remediation

- [x] Add a deterministic concurrency regression that pauses a mutating command after runtime lookup while settings apply starts.
- [x] Hold the runtime lifecycle lease for the full submit/cancel/retry and strategy-mutation transaction, not only service lookup.
- [x] Cover any projection or controller action that can append Journal evidence under the same lifecycle lease.
- [x] Recheck positions and active-order blockers only after prior runtime mutations have drained.
- [x] Prove the old session archive record is terminal and no command/fill/state record can be appended afterward.
- [x] Rerun focused, complete, compilation, JavaScript, and diff verification.
- **Status:** complete

### Phase 8: Independent acceptance recording

- [x] Record the independent `Approve` result and its scoped verification evidence.
- [x] Update the formal Implementation Plan from ready-for-review to independently accepted.
- [x] Preserve the active-plan pointer, unrelated worktree changes, local-paper-only boundary, and no-commit state.
- [x] Re-run planning completeness and diff-format checks after the documentation-only update.
- **Status:** complete

### Phase 9: Scoped commit packaging and handoff

- [x] Reconstruct the exact local-paper runtime settings file and hunk scope against the shared dirty worktree.
- [x] Stage only accepted feature changes and exclude unrelated backtest, strategy, research, and planning work.
- [x] Verify the staged payload, whitespace, and accepted regression evidence before committing.
- [x] Create one local commit without pushing and report the resulting SHA.
- [x] Report feature completeness and whether any next phase is required or optional.
- **Status:** complete

## Confirmed requirements

- Local-paper starting cash must be configurable and editable from the settings page.
- Daily gross BUY limit must be independently configurable and editable from the settings page.
- Trading fee settings must be configurable and editable from the settings page.
- Starting cash and daily BUY limit remain independent controls.
- Selling does not restore the current trading day's BUY limit.

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `check-complete.sh` checked the legacy root plan instead of the isolated plan because this installed script accepts a plan-file argument and does not resolve `PLAN_ID` itself | 1 | Re-run once with the explicit isolated `task_plan.md` path |
| A combined patch targeted `trading/local_paper.py` in two update blocks | 1 | No file changed; reapply as one grouped file update |
| Full regression still expected the pre-feature static asset cache versions | 1 | Updated the two exact structural assertions and reran the full suite |
| Independent review found incomplete settings pinning and a non-atomic runtime replacement lifecycle | 1 | Reopened the plan as Request Changes and added Phase 5 before remediation |
| `ui-ux-pro-max` search could not start because `python` is not installed as that executable name | 1 | Use the available `python3` interpreter for the required local UX search |
| Expanded focused run found checkpoint digest drift when a helper caller omitted the now-pinned settings digest, plus zero-fee Decimal scale changed legacy baseline strings | 1 | Derive a settings-bound digest from Journal session metadata in checkpoint writes and preserve the prior zero-fee Decimal scale while still rejecting sub-cent minimums |
| New API precision test entered FastAPI lifespan without MockProvider/scheduler isolation and triggered the known Python 3.13 Shioaji native segfault | 1 | Add the same explicit MockProvider globals and incremental-scheduler disable used by adjacent API tests before rerunning |
| Follow-up review found the legacy fixture omitted historical `execution_boundary=LOCAL_ONLY`, and stream activation failure happened after commit | 1 | Reopen the plan with Phase 6 and add real legacy-evidence plus Provider-failure lifecycle regressions before changing implementation |
| Phase 6 red tests reproduced both remaining P1 cases: legacy recovery raised a settings conflict and second stream start still returned HTTP 200 | 1 | Keep these two exact tests as acceptance regressions, then implement the narrowed key set and rollback-capable handoff |
| Current complete suite has one unrelated backtest UI copy failure: `test_atomic_launcher_reports_server_managed_dataset_readiness` | 1 | Do not modify the concurrent backtest workspace; report `1328 passed, 32 skipped, 1 failed` and keep Phase 6 acceptance grounded in its green focused tests |
| Strengthened quote-cache regression expected `105.00`, but the existing Decimal projection preserves input scale as `105.0` | 1 | Correct only the test expectation to the established projection format and retain before/after cache equality assertions |
| Follow-up review reproduced an order request retaining the old command service across settings apply and writing a fill after archive | 1 | Reopen the plan with Phase 7; add a deterministic concurrency regression before introducing a full runtime-command lease |
| Phase 7 regression observed no lifecycle-lock contention while the old command was paused | 1 | Keep the failing test as the red baseline; make runtime resolution and the complete mutating action share one composition lease |
| Dashboard simulation module reached the WebSocket test and triggered the known Python 3.13 Shioaji native segfault | 1 | The leased projection bypassed the test's existing `get_simulation_service` injection and built a real Provider; retain that getter seam while holding the lifecycle lock for the full projection |
| The next module run reached the automated-controller route and exposed the same getter-bypass problem | 2 | Make the lease own only lifecycle locking; resolve each simulation/command/controller dependency through its existing getter inside the lease |
| A status search placed Markdown backticks inside a double-quoted shell argument, so zsh attempted to execute `Approve` | 1 | The search still returned the required file status lines; do not repeat it, and use literal-safe patterns for subsequent checks |
| `check-complete.sh` treats `independently_accepted` as incomplete and reported 7/8 | 1 | Keep acceptance semantics in the formal plan/findings, use the helper's machine-readable `complete` phase status, and rerun once |
| A file-map search again embedded Markdown backticks in a double-quoted shell regex and zsh rejected the pattern | 1 | Stop using backticks in shell search expressions; inspect the architecture plan with literal-safe heading searches and `sed` |

## Deliverables

- `architecture/local_paper_runtime_settings_implementation_plan.md`
- Settings contract/repository, settings-bound runtime, daily BUY limit, fee accounting, API/UI, documentation, and regression coverage.

## Implementation success criteria

- Cash, daily BUY limit, commission rate, and minimum commission are editable and persistent.
- Daily BUY budget aggregates fills and reservations, and SELL does not replenish it.
- Commission affects BUY reservation/cash, SELL proceeds, and realized PnL.
- Existing local-paper recovery remains deterministic.
- Manual and automated orders share the same enforcement.
- No broker-order path is added.
- Every settings-bound Journal session validates the complete immutable settings contract before recovery.
- A failed settings apply leaves the exact old runtime instance live and active.
- New settings-bound fills always write the complete v2 audit contract, including zero-fee fills.
- Settings apply is serialized with every Journal-mutating runtime action; after `local_paper_session_archive.v1`, the archived session accepts no later command/fill/state evidence.
