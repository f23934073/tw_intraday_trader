# Findings & Decisions: Durable Kill Switch implementation plan

## Requirements

- Produce a plan that can be pasted into a new independent Codex task.
- Focus on Kill Switch persistence and restart safety.
- Do not implement product code in this task.
- Keep tax, fee, and slippage modeling out of this plan.
- Preserve Local Paper and no-real-money authority boundaries.

## Research Findings

- `LocalPaperKillSwitch` is a process-local object with an `RLock`, boolean `engaged`, reason, and engage timestamp. Its reset erases all three fields and accepts no actor or idempotency key.
- `dashboard.server` constructs one module-global switch and injects it into one process-local `ContinuousPaperStrategyController`.
- The controller checks the switch before `start()` and during each `_evaluate_locked()` iteration. Engaging stops the worker, sets controller state to `KILLED`, checkpoints controller runtime state, and clears the entry quote watch. Reset returns a killed controller to `STOPPED`; it does not restart automatically.
- The existing strategy runtime checkpoint is not authoritative Kill Switch persistence: it is written only after a run has an assigned `run_id`, while the global switch can be engaged before any run or across owners.
- Engage/reset endpoints use loopback, Origin, and CSRF mutation guards, but payloads do not carry actor/idempotency metadata. The Dashboard sends a fixed reason and no retry-stable operation key.
- README explicitly identifies stop and Kill Switch engage/reset as process-local controls without durable actor/idempotency audit.
- Existing behavior intentionally blocks new automated intents but does not flatten positions. No-overnight cancellation/flatten/reconciliation must remain independent from the Kill Switch.
- The repository already has one canonical Journal with record-level idempotency and monotonic projection checkpoints for memory/PostgreSQL parity; the plan should extend this path rather than add a standalone control database.
- `RuntimeComposition` owns the resolved Journal, creates or recovers the current Local Paper session, rebuilds orders/positions/daily risk, and constructs `StrategyPaperFlowService` with that same Journal. It is the correct composition seam for a durable control service.
- Journal identity already supports conflict-safe retries through `(idempotency_scope, idempotency_key)` and canonical record fingerprints. PostgreSQL enforces the same uniqueness as the memory adapter.
- Journal `append()` and `save_checkpoint()` are separate transactions. A Kill Switch design must not require an atomically paired checkpoint to remain safe; replaying append-only control events must be authoritative.
- Existing Local Paper settings can create a new trading session while the Kill Switch is global. Binding global control state only to the currently active trading session would risk losing the engaged state during session replacement; it needs a stable control session/scope in the same Journal.
- Current PostgreSQL tests are destructive and require explicit `TEST_POSTGRES_DSN`; no-DSN skips must never count as durable recovery evidence.
- Settings apply is serialized by `_runtime_composition_lock`, builds a replacement composition over the same Journal, rotates the Local Paper trading-session id, and discards the current controller. The module-global Kill Switch object survives that handoff only inside the same process.
- Dashboard shutdown calls controller `close()`/`stop()` and then closes the composition. A durable control must recover before a newly constructed controller can answer status or accept start.
- API contracts confirm the gap precisely: engage carries only `reason`; reset carries no body. Both need strict actor, retry-stable idempotency, and reset revision/change-reason fields.
- Existing mutation protection is suitable to retain: loopback-only middleware, exact Origin checks, and CSRF. Durability does not replace authorization.
- Runtime composition/controller first access is already serialized, and settings handoff has concurrency tests. New recovery and rotation tests should extend those seams instead of introducing a parallel lifecycle lock.
- The controller status already embeds Kill Switch state, so new revision/durability/recovery/audit fields can be added compatibly without creating a second status endpoint.
- `StrategyPaperFlowService.submit()` is the shared final path for current automated BUY and SELL intents. Controller-only checks are insufficient as a durable admission boundary because a future producer or an engage/submit race could bypass a stale early check.
- Current architecture distinguishes an entry emergency stop from a transport-wide kill. The implemented Local Paper switch stops all new automated strategy intents, while query/cancel/reconciliation and the independent no-overnight controller must remain available.
- The durable service can provide a single-process linearization lock around final automated-intent admission and engage/reset. An intent admitted before engage is pre-existing; after engage returns, no later automated intent may append or reach the command service.
- Multi-process/web-worker authority is not solved by the current singleton architecture. This plan must either enforce/document one local writer or explicitly leave distributed lease/HA as a future Gate; it must not claim multi-worker safety.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Use an isolated planning directory | The repository already has active parallel plans and unrelated dirty changes. |
| Treat durable PostgreSQL evidence separately from in-memory tests | Passing unit tests cannot prove cross-process recovery or transactional durability. |
| Persist the global switch independently from strategy `run_id` | The switch must remain engaged before a run exists, after a process restart, and across exact Strategy Set owners. |
| Keep engage one-way fail-safe and reset more strictly authorized | A lost engage response must remain stopped; reset is the risk-increasing control mutation. |
| Use append-only control events as authority; treat any checkpoint as rebuildable optimization | Journal append and checkpoint are not one transaction, so safety cannot depend on both succeeding together. |
| Use a stable control session in the existing Journal | Local Paper trading sessions can rotate when settings are applied, but the global engaged state must survive that rotation. |
| Recover the durable switch before controller construction | No status or start path may briefly observe a default-disengaged state after restart. |
| Keep existing loopback/Origin/CSRF defenses and add operation identity | Transport security and durable audit solve different risks and both are required. |
| Use optimistic revision on reset | A stale reset must not clear a newer emergency engage/reaffirm event. |
| Add a final guard in `StrategyPaperFlowService.submit()` | Early controller polling is not an authoritative last admission boundary for every automated intent. |
| Preserve current switch semantics | Block all new automated strategy intents, but do not block query, manual cancel, reconciliation, or the independent no-overnight safety path; do not auto-flatten on engage. |
| Define single-process linearization explicitly | The current product is loopback single-user/single-process; distributed leader/lease support is a separate expansion. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Initial combined replace patch was rejected because it targeted the same paths twice | Split the patch into delete and add operations. |

## Resources

- `architecture/local_paper_kill_switch_durability_implementation_plan.md`
- `simulation/continuous_strategy.py`
- `dashboard/server.py`
- `trading/journal.py`
- `trading/postgres_journal.py`
- `runtime/composition.py`
- `simulation/strategy_flow.py`

## Final Disposition

- The implementation plan is complete and remains plan-only.
- Four phases (`KS-001` through `KS-004`) cover contracts, durable recovery, final admission/API/UI, and PostgreSQL UAT.
- The plan can start immediately in an isolated task and does not require a trading session.
- Product code, the frozen PR-NO-006 worktree, broker authority, and tax/slippage behavior were not changed.

## Visual/Browser Findings

- None; this task uses repository source only.
