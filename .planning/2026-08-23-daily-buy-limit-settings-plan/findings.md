# Findings: Configurable local-paper risk and fee settings

## User requirement changes

- Both `10,000,000 TWD starting cash` and `2,000,000 TWD daily BUY limit` are defaults, not hard-coded permanent values.
- Both values must be editable through the settings page.
- Fee parameters must also be editable through the settings page.
- The implementation plan must be updated before any product development starts.

## Inherited safety boundary

- Local-paper account state must not be described as real broker buying power.
- This planning task does not authorize Shioaji order submission, cancellation, CA activation, or real-money execution.

## Repository findings

- The dashboard currently shows local-paper available cash in `dashboard/static/js/workspaces/simulation.js`, but the initial search found no local-paper settings form or settings API.
- `simulation/service.py` currently owns a hard-coded default starting cash of `10,000,000`.
- `simulation/application.py` derives order, position, and daily-loss caps from the simulation starting cash, so the plan must separate the new daily BUY budget rather than silently reusing those caps.
- The current local-paper documentation explicitly says fees and tax are not calculated.
- Backtest request models already expose `starting_cash`, `commission_rate`, and `sell_tax_rate`, but those contracts belong to historical backtesting and must not be reused as mutable local-paper account settings without a dedicated boundary.
- `config/settings.py` is currently a module of source constants and has no mutable settings repository or dashboard settings contract.
- `RuntimeComposition.create()` constructs one process-wide `SimulationService` and records `starting_cash` in the durable local-paper Journal session metadata. On restart it rejects a different starting-cash value for that same session.
- Because starting cash is an opening-account invariant, changing it safely cannot mutate an active session in place. The plan needs an explicit apply lifecycle that creates/resets a new local-paper session only after a confirmation gate.
- Current dashboard simulation routes expose session, projections, orders, positions, and automated-strategy controls, but no local-paper configuration read/update endpoint.
- `SimulationService` reserves only gross BUY notional and currently debits/credits cash with gross fill amounts. Realized PnL also excludes costs.
- Current `local_paper_fill.v1` and checkpoint projection do not carry commission values. Existing immutable v1 records therefore need backward-compatible replay with zero commission; new cost-bearing evidence should use an explicit new schema/version rather than reinterpret old records.
- Historical backtest already has defaults `commission_rate=0.001425` and `sell_tax_rate=0.003`, but its cost calculation is a simple gross multiplication without a local-paper settings lifecycle or cash-reservation contract.
- The dashboard has no settings navigation entry. The least disruptive UI plan is a new `本機模擬設定` item under the existing local-paper sidebar group, with active values, editable draft values, and explicit apply/reset status.
- BUY cash admission must reserve both gross notional and estimated commission. The daily BUY limit itself should continue counting gross BUY notional only, so changing the fee cannot silently change the user's 2,000,000 TWD trading budget.
- The selected Journal backend may be in-memory, so storing mutable UI settings only in Journal metadata would not satisfy restart persistence in the default configuration. A small dedicated file-backed settings repository is the appropriate local runtime boundary; the path must be ignored by Git and writes must be atomic.
- Each applied settings revision must be copied into immutable Journal session metadata. That makes subsequent fill replay deterministic even if the editable draft changes later.
- The existing Journal has multiple sessions but the runtime hard-codes one session id. Safe settings application therefore requires a local-paper session lifecycle/manager that can archive the old session, create a new id, and atomically switch the active-session pointer.
- A commission-aware fill projection must debit BUY cash by `gross + commission`, credit SELL cash by `gross - commission`, and include commission in realized PnL. Old v1 fill records continue to replay as commission `0`.
- Fee accounting should be deterministic Decimal arithmetic with one documented TWD rounding rule. It should not inherit binary floats from the current session API or silently copy the backtest's unrounded multiplication.
- Existing dashboard mutations already enforce loopback origin plus a process CSRF token. Local-paper settings writes and apply/reset actions should reuse that protection pattern instead of introducing an unauthenticated mutation route.
- `dashboard/static/js/app.js` already models drawer-style local-paper workspaces. A settings drawer can be added without changing the overview/candidates/momentum page structure, while still appearing as a dedicated `本機模擬設定` page in sidebar navigation.
- Focused regression coverage already exists in `test_simulation_service.py`, `test_local_paper_command_service.py`, `test_local_paper_projection.py`, `test_recoverable_simulation_orders.py`, `test_runtime_composition.py`, `test_dashboard_simulation_api.py`, and `test_candidate_workspace_ui.py`.

## Proposed v1 setting contract

- `starting_cash_twd`: default `10000000`; positive Decimal; independent from the daily limit.
- `max_daily_buy_notional_twd`: default `2000000`; positive Decimal; not required to be less than starting cash because cash and budget are separate gates.
- `commission_rate`: compatibility default `0`; applies to BUY and SELL fills and is editable as a percentage in the UI.
- `minimum_commission_twd`: default `0`; non-negative Decimal, allowing the user to model a broker minimum without forcing one into every simulation.
- Sell transaction tax remains explicitly unchanged/out of scope for this annotation-driven v1 plan.

## Proposed apply lifecycle

- Saving updates a persistent draft only; it does not rewrite an active account.
- Applying creates a new immutable settings revision and a new local-paper Journal session. The prior session remains archived/replayable.
- If an automated strategy is running, apply is blocked until it is stopped.
- If current positions or active orders exist, the UI requires an explicit destructive reset confirmation; no silent reset is allowed.
- All new orders in one session use the same pinned fee/risk settings revision, including recovered pending orders after restart.

## Independent review — Request Changes

- P1: recovery currently validates only `starting_cash`; a reused session id can accept different daily-limit and fee settings. Settings-bound sessions must validate schema, revision/digest, every pinned policy value, and the local-only execution boundary. Legacy sessions need a separate explicit compatibility path.
- P1: settings apply closes the old runtime before replacement creation and pointer activation complete. Pre-commit failure must preserve the exact old runtime object, provider subscriptions, and quote cache; only a successful swap may close it.
- P2: `minimum_commission_twd` accepts sub-cent values and can return them directly. The chosen contract is to reject values that are not exact TWD cents rather than silently altering a saved input.
- P2: the UI labels commission-inclusive `reserved_cash` as the daily pending-order budget. Gross-only `daily_reserved_buy_notional` and commission-inclusive cash reservation must have distinct labels.
- P2: new settings-bound sessions must always write `local_paper_fill.v2`, including zero-fee fills. The v2 payload needs gross, commission, net cash effect, cumulative order commission, and settings digest. Apply must also append terminal/archive evidence to the old session.
- The independent review's full-suite result is `1303 passed, 26 skipped, 2 failed`; both failures are attributed to concurrent uncommitted `012_backtest_dataset_bindings.sql` work. Until rerun, do not claim a green full suite.

## Phase 5 repository trace

- `RuntimeComposition.create()` writes daily limit, fee values, digest, and execution boundary for a new session, but recovery only branches on `starting_cash`. It also omits an explicit settings schema/revision from session metadata.
- Dashboard startup has the repository revision available in `LocalPaperSettingsState`, but does not pass it into composition. The replacement helper likewise accepts settings and session id only.
- `RuntimeComposition.close()` closes simulation, Journal, and the shared provider. Settings apply must not call it on the old composition while the replacement shares those dependencies; the lifecycle needs a simulation-only retirement step after a successful global swap.
- The existing apply implementation closes only the old simulation before replacement construction, then tries to rebuild old state on failure. This does not preserve object identity or provider subscription/cache state.
- `commission_for()` rounds the percentage calculation but takes `max()` with the unquantized minimum. Validation should reject a minimum whose value differs from its `0.01` quantization.
- `journal_record_from_simulation_order()` currently selects v2 only when incremental commission is positive, and `LocalPaperFillOutcomeRecorder` has no pinned settings context. A settings digest must be injected into the recorder when the command service is created.
- The UI status sentence currently uses commission-inclusive `reserved_cash` inside a phrase describing daily pending-order budget; the session projection already exposes the required gross-only `daily_reserved_buy_notional`.
- UX search confirmed financial labels should be semantically distinct and visible; the fix should show gross daily reservation and commission-inclusive cash reservation as two separately named values rather than overloading one parenthetical label.
- `SimulationService` starts its quote worker/provider handler inside `__init__`, while the provider permits only one handler. A safe replacement needs a suspended-construction mode: recover and validate the new account without registering a handler, activate the settings pointer while the old service is live, atomically swap globals, retire only the old simulation, then start streaming on the committed replacement.
- A suspended replacement must track quote-stream ownership so closing a failed replacement cannot call `provider.stop_quote_stream()` and accidentally stop the old runtime.
- The settings document needs separate `active_settings_revision` and `draft_settings_revision`. The optimistic document revision changes when a new draft is saved, so it cannot itself identify the settings revision pinned to an already-active Journal session.
- Legacy compatibility will be limited to the historical `local-paper-runtime-v1` session with default settings/revision zero and no partial settings-binding metadata. Any settings-bound or partially bound metadata mismatch will fail closed.
- The v2 evidence fields can be derived without new mutable order state: incremental gross is `last_fill_price * last_fill_quantity`, incremental net cash effect is signed by side, and `filled_commission` is the cumulative order commission after this fill.
- `RuntimeComposition.close()` cannot be used to retire the old account after a successful swap because it would also close the Journal and provider shared by the replacement. The commit path must close only the old `SimulationService`.
- Existing providers expose an exclusive quote handler. The bounded change is to add `start_streaming=False` plus an idempotent activation method to `SimulationService`; a failed suspended replacement must own neither callbacks nor the provider stream.
- Regression coverage will assert two independent pre-commit failures (`_replacement_composition` and `activate_draft`) preserve `_composition`, `_simulation_service`, and the old simulation's close state by identity; successful apply will assert an archive record and new settings-bound metadata.
- The repository already provides `trading.canonical_values.canonical_decimal_string`. Settings and v2 Journal values should reuse it so equivalent inputs such as `20`, `20.0`, and `20.00` produce the same policy digest and immutable evidence strings.

## Phase 5 remediation result

- Settings-bound recovery now compares the complete immutable metadata contract, including schema, settings revision/digest, risk/fee values, rounding policy, mode, and local-only execution boundary. The legacy path is explicit and default-only; partial binding fails closed.
- Settings apply now prepares a suspended replacement while the exact old runtime and quote handler remain live. Replacement construction, settings activation, and archive-record failures leave the old runtime object active and restore the active settings pointer when needed.
- Minimum commission rejects values below TWD-cent precision, and all canonical settings/evidence Decimal strings are scale invariant.
- The UI now renders gross `daily_reserved_buy_notional` as `今日掛單保留買入額度` and commission-inclusive `reserved_cash` separately as `含手續費現金保留`.
- Every settings-bound fill uses `local_paper_fill.v2`, including zero-fee fills, with gross, commission, signed net cash effect, cumulative order commission, and settings digest. Successful settings apply appends a terminal archive record to the prior session.
- Final feature regression passed `151 passed`; the current complete suite passed `1319 passed, 30 skipped`. The earlier two concurrent migration failures no longer reproduce in the current checkout.
- The local dashboard and simulation drawer loaded successfully in the Browser smoke. At the browser's 720px-high viewport the existing drawer places the submit button below the actionable viewport, so no order/settings mutation was made; the two reservation labels and their distinct value sources remain covered by focused UI/API tests.

## Follow-up independent review — Request Changes

- Three prior P2 areas are fully closed: minimum fee cent precision, separated gross/cash UI reservations, and complete settings-bound v2/archive evidence.
- P1 legacy gap: pre-feature production Journal metadata already contained `execution_boundary=LOCAL_ONLY`. Treating that historical field as a new partial settings-binding key rejects a legitimate legacy session before the explicit compatibility branch. The regression fixture must include the real historical metadata shape plus v1 fill and checkpoint evidence.
- P1 lifecycle gap: the current successful apply path swaps globals and stops the old simulation before calling `replacement.simulation_service.activate_streaming()`. That method catches Provider startup failures, so the API can report success while the committed runtime has `streaming=False` and the exact old runtime is already stopped.
- Required lifecycle invariant: a Provider handoff failure must be observable to the apply orchestration, must happen before settings pointer/archive/global commit, and must reactivate the same old simulation object/handler before returning failure.
- The review independently observed `12 passed` remediation tests, `130 passed` focused, and `1319 passed, 30 skipped` complete. These are pre-Phase-6 evidence and do not close the two remaining P1 cases.

## Phase 6 source trace

- `_validate_session_settings()` currently derives `partial_binding_keys` from the entire expected settings metadata minus only schema and starting cash. That unintentionally includes the historical `execution_boundary` field; the minimal correction is an explicit set containing only fields introduced by settings binding.
- `SimulationService.activate_streaming()` starts its worker, calls the provider, catches every Provider exception, cleans up the worker, and returns `None`. The caller therefore cannot distinguish activation from degraded failure.
- `apply_local_paper_settings()` currently activates the settings pointer and appends archive evidence before globals swap, but the provider handoff is later: globals swap, old simulation close, then replacement activation. This violates the required rollback invariant specifically for the exclusive handler exchange.
- The Provider contract is exclusive-handler based. A rollback-capable handoff must stop only the old stream without destroying old simulation state, attempt replacement activation, and if it fails re-register the same old simulation's handler before any repository/archive/global commit.
- `SimulationService.close()` is not suitable for temporary handoff because it also clears `_subscribed_symbols` and `_quote_watch_by_owner`. Phase 6 needs a dedicated stream suspension primitive that stops Provider ownership and drains the worker while preserving runtime state needed to reactivate the exact old object.
- Reactivation must restore Provider subscriptions, not only the callback. The simulation can preserve its existing desired subscribed-symbol set across a temporary suspension, start the callback again, then call `sync_quote_subscriptions()` before declaring streaming healthy.
- Shioaji `stop_quote_stream()` removes current subscriptions and callbacks but keeps the Provider object usable; `start_quote_stream()` can then register a handler again. This supports a bounded old-stop/new-start/old-restart transaction without rebuilding either runtime.
- The current legacy regression only creates `metadata={"starting_cash": "10000000"}` and contains no Journal evidence. It must be upgraded to the actual historical metadata shape and exercise replay through v1 fill plus checkpoint, not only session admission.
- `git show HEAD:runtime/composition.py` confirms the exact pre-feature session metadata keys were `starting_cash`, `execution_boundary`, `journal_backend`, and `restart_policy`. Only `execution_boundary` overlaps the new expected settings metadata; `journal_backend` and `restart_policy` are unrelated session lifecycle evidence.
- The quote worker exits on a `None` sentinel and a subsequent activation already replaces its Queue, so a dedicated suspension can deterministically drain/stop the worker and later reuse the same simulation object and quote cache.
- The six-module lifecycle/recovery regression is green (`94 passed`). Existing constructor behavior remains degrade-on-startup for compatibility, while the public handoff activation is strict and observable.
- Usage search confirms only the settings-apply orchestrator calls the new public suspend/strict-activate methods; ordinary subscription reconciliation keeps its prior degrade-and-report behavior. This keeps the transactional failure policy localized to settings handoff.
- Focused source review confirms concurrent first composition construction still expects exactly one Provider start, while successful settings apply remains exactly two starts. Failure after a completed handoff now intentionally produces a third start to restore the old handler.
- The rollback branch retains the original exception when rollback succeeds and raises an explicit rollback failure if the Provider/settings restoration itself fails; no successful HTTP response can be returned from a failed strict handoff.
- Final Phase 6 focused regression is `162 passed`; Python compilation, both JavaScript syntax checks, and `git diff --check` pass after the last stream-race hardening.
- The complete suite currently has one unrelated concurrent backtest UI copy failure (`1328 passed, 32 skipped, 1 failed`). Active-plan pointer remains `2026-08-19-realtime-dashboard-websocket-plan`, and verification created no local settings file.

## Phase 7 independent review — Request Changes

- The prior legacy-metadata and quote-stream handoff P1 findings are independently confirmed closed, but acceptance remains blocked by a new lifecycle race.
- Dashboard command routes currently hold `_runtime_composition_lock` only while resolving `LocalPaperCommandService`; `submit_order()` then runs after the lock is released.
- A request can therefore retain the old command service, settings apply can observe an empty account and archive/swap it, and the request can then append `order_command.v1`, `local_paper_fill.v2`, and `local_paper_order_state.v1` after `local_paper_session_archive.v1`.
- This violates both immutable archive ordering and the rule that settings reset must recheck non-empty-account blockers after all older mutations have drained.
- The bounded fix is a runtime-command lease backed by the existing reentrant composition lock. Resolution and the full mutating action must occur inside one lease; settings apply already uses the same lock and will therefore inspect blockers only after earlier actions finish.
- Deterministic acceptance must pause a command inside its full route action, start apply concurrently, verify apply cannot commit early, then prove it sees the resulting position/order blocker and that any eventual archive remains the final old-session record.
- Source trace confirms submit, cancel, and retry currently resolve `get_local_paper_command_service()` and execute the command after its internal lookup lock has already been released.
- Automated strategy start/stop/kill/reset have the same lookup-only lifecycle gap. In addition, projection/session/positions readers require review because they can perform reconciliation or trading-day rollover rather than being guaranteed pure reads.
- The simulation WebSocket directly calls `get_simulation_service().projection()` on every sample, so lifecycle protection must include that call without holding a synchronous lock across WebSocket network waits.
- `SimulationService.projection()` calls `reconcile_orders()`, which can emit terminal-order notifications later recorded in Journal; `session()` and `positions()` call trading-day rollover, whose baseline callback can also append evidence. These are state-mutating reads and must take the lifecycle lease for the complete projection calculation.
- `orders()` itself is a locked in-memory read, but using one leased composition per composite response avoids mixing orders from the old runtime with positions/session from the replacement.
- `LocalPaperCommandService` performs each command, Journal outcome write, and checkpoint write under its own service lock, but that lock is runtime-local and cannot serialize against dashboard composition replacement; the lifecycle lease must sit outside the complete service call.
- `ContinuousPaperStrategyController.stop()` sets its stop event and joins the worker before returning, while controller status/start/kill/reset synchronize on its controller lock. If their HTTP actions are lifecycle-leased, apply cannot pass the RUNNING check or archive until the controller transition and any in-flight evaluation have drained.
- The broader dashboard snapshot path also calls `projection()`, and manual dashboard refresh calls `refresh_quotes()`, which can fill active mock orders and trigger Journal callbacks. Both must resolve and execute against one leased runtime.
- The lease should be scoped only around synchronous runtime calculation/mutation. In the WebSocket loop it must be released before `send_json()`, `receive()`, or timeout waits so one slow client cannot block settings apply.
- A deterministic test can replace the global reentrant lock with a behavior-compatible observing wrapper: a failed non-blocking acquire signals that settings apply is actually waiting behind the paused command. This avoids relying on arbitrary sleeps to infer contention.
- After releasing the command, the first unconfirmed apply must return 409 because it rechecks the newly created position; a confirmed second apply must succeed and leave `local_paper_session_archive.v1` as the final record of the old session.
- The new `runtime_composition_lease()` resolves the composition while holding the existing reentrant lifecycle lock and keeps that lock until the complete synchronous runtime action returns.
- WebSocket sampling now offloads the leased projection calculation to a worker thread and releases the lease before any network send/receive wait.
- Post-patch usage search leaves direct controller getter calls only inside leased blocks; the controller's bound projection reader remains safe because settings apply rejects RUNNING and waits on the controller lock for any in-flight evaluation to finish.
- Settings GET/draft-save should also keep repository state acquisition and runtime blocker projection in one lease, preventing a response from pairing an old settings document with a newly swapped runtime.
- Existing WebSocket coverage intentionally replaces `get_simulation_service()` with an in-memory fake. The projection endpoint must keep that dependency-injection seam; acquiring `_runtime_composition_lock` around the getter plus `projection()` still provides the required complete lease in production.
- Automated-controller route tests use the same getter-injection pattern. A lease that eagerly resolves and yields `RuntimeComposition` is unnecessarily coupled; a lock-only context with service resolution inside it is both smaller and fully compatible.
- The final lock-only lease retains every existing service/controller getter seam while ensuring those getters and the full action share the same reentrant lock; nested composition creation remains safe.
- Final source audit confirms submit/cancel/retry, controller status/start/stop/kill/reset, dashboard refresh, projection/WebSocket reconciliation, session/positions rollover, settings blocker projection, and health projections all execute inside the lifecycle lease.
- Settings apply continues to hold the same underlying lock from repository/version validation through blocker recheck, replacement handoff, archive append, global swap, and old-runtime retirement.
- Existing functional route coverage already exercises submit followed by cancel and bounded retry against the real local-paper command service; the new concurrency regression adds the missing lifecycle-ordering assertion rather than duplicating command semantics.
- Additional strategy coverage includes continuous-controller lifecycle, strategy flow, exact atomic paper runtime, and atomic-strategy Web API; these are the relevant automated-mutation consumers of the same local-paper runtime.
- The architecture status section still records pre-Phase-7 verification (`162 passed` and an older unrelated full-suite failure) and must be refreshed before handoff without self-approving acceptance.
- Final boundary audit preserved `.planning/.active_plan=2026-08-19-realtime-dashboard-websocket-plan`, created no local settings artifact, and found no new broker login/CA/place-order/update-order call in the scoped server diff.

## Independent acceptance — Approve

- The independent reviewer approved the local-paper runtime settings scope and confirmed the third P1 is closed.
- Review confirmation covers the shared reentrant lifecycle lease, complete command/controller/projection/rollover coverage, WebSocket network waits outside the lock, blocker recheck after mutation drain, and terminal archive ordering.
- Independent verification recorded: third-P1 regression `1 passed`, local-paper regression selection `163 passed`, automated/atomic selection `64 passed`, complete suite `1331 passed, 33 skipped`, plus green Python compilation, two JavaScript syntax checks, and `git diff --check`.
- Acceptance is strictly scoped to local-paper runtime settings and does not approve unrelated concurrent worktree changes.
- The reviewer made no file changes and created no commit.
- Formal status is now `Independently Accepted`; the reviewer evidence is recorded separately from implementation self-verification, and approval remains limited to local-paper runtime settings.

## Phase 9 scoped commit packaging

- The user explicitly authorized a local commit and requested completion/next-phase status; push remains unauthorized.
- The current branch is `codex/organize-uncommitted-20260821` and the shared worktree contains extensive unrelated backtest, strategy-catalog, research, and planning changes.
- Commit packaging must operate at exact file/hunk granularity; whole-file staging is unsafe for overlapping files such as `dashboard/server.py`, shared dashboard assets, and simulation/runtime modules.
- `.planning/.active_plan` remains a separate existing pointer and must not be changed or committed as part of this feature.
- Prior shared-worktree packaging on this same branch confirms the safe procedure: inspect/stage exact payload, recheck status and diff immediately before commit because concurrent workflows may mutate files, and keep push as a separate explicit gate.
- Planning files may be committed only when they are the isolated accepted feature plan; unrelated `.planning` directories and the active-plan pointer remain excluded.
- The accepted architecture file map identifies the candidate product scope: `.gitignore`, `config/local_paper.py`, `simulation/settings.py`, `runtime/composition.py`, `dashboard/server.py`, `trading/risk.py`, `trading/application.py`, `trading/local_paper.py`, `simulation/application.py`, `simulation/models.py`, `simulation/service.py`, dashboard settings UI assets, `README.md`, and the focused regression files.
- The file map is only a candidate list: overlapping files still require hunk-level comparison because unrelated backtest/strategy/dashboard work is present in the same worktree.
- Core diffs in `runtime/composition.py`, `simulation/application.py`, `simulation/models.py`, `simulation/service.py`, `trading/application.py`, `trading/risk.py`, and `trading/local_paper.py` align with the accepted settings/daily-budget/commission/recovery/stream-handoff contract; no odd-lot-only additions were found in the simulation-service diff.
- `README.md` is mixed: the local-paper settings/recovery/commission hunks belong to this feature, while later historical-backtest dataset/binding/UI workflow hunks are unrelated and must remain unstaged.
- `.gitignore` adds only `data/local_paper/`; `config/local_paper.py`, `simulation/settings.py`, and the formal architecture plan are untracked feature-owned files.
- UI overlap is substantial. `simulation.js` and the new settings assertions in `test_candidate_workspace_ui.py` are feature-owned, but `index.html`, `app.js`, `dashboard.css`, and `test_dashboard_module_structure.py` combine settings changes with unrelated atomic-backtest auto-dataset and strategy-management redesign work.
- For mixed UI files, stage only: settings nav/drawer markup, settings drawer wiring/workspace metadata/Escape handling, the simulation module cache-bust, the SVG nav icon rule, and settings-specific structural assertions. Exclude backtest workflow removal, strategy redesign CSS/markup/JS, and backtest module cache assertions.
- The top-level CSS/app asset cache key currently contains both feature names. It may be staged as a shared cache-bust only if the staged tree stays internally consistent; unrelated backtest module source and workflow changes remain excluded.
- `dashboard/server.py` has a clean feature region from settings imports/state/models through settings endpoints/apply and lifecycle-lease coverage, but also contains unrelated backtest binding and strategy-set lifecycle hunks before and after that region. It requires selective staging.
- `tests/test_dashboard_simulation_api.py` changes are concentrated in accepted settings lifecycle, stream rollback, and runtime-lease regressions; the inspected diff contains no unrelated backtest API changes.
- The inspected diffs for runtime composition, risk, application, simulation service/models, local-paper Journal/recovery, and their focused tests are feature-coherent and suitable for whole-file staging, subject to a final cached-payload review.
