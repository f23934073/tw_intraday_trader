# Findings & Decisions

## Requirements
- Highest priority is to make the simulated-trading lifecycle run end to end.
- Scope is `LOCAL_PAPER_SIMULATION`; do not add Shioaji order calls, CA activation, trade callbacks, or real-money capability.
- The minimum closed loop is strategy intent -> Journal -> RiskGate -> local fill -> position -> strategy exit -> realized PnL.
- Preserve all unrelated tracked and untracked worktree changes.

## Research Findings
- The existing manual route already uses `LocalPaperCommandService`, `OrderApplicationService`, `RiskGate`, and `SimulationService`.
- The current command facade hard-codes `CommandOrigin.MANUAL_WEB` and its policy has `allow_strategy_origin=False`.
- `SimulationService` already supports idempotent BUY/SELL limit orders, cash/share reservations, fills, positions, and realized PnL.
- The current Dashboard runtime uses an in-memory Journal and projection; persistence is not required for the first deterministic run-once lifecycle.
- Candidate and momentum outputs are research evidence, not authorized automatic order signals. This slice must accept an explicit versioned intent instead of inventing a live strategy promotion rule.
- The current worktree contains extensive unrelated unfinished work, including one full-suite collection error for a missing late-delivery evidence module.
- `LocalPaperSimulationCommandAdapter` already propagates `OrderCommand.origin` into the simulator, so no second simulator adapter is needed.
- `OrderApplicationService` already journals the command and terminal fill/rejection records; the missing seam is origin-aware command construction and a flow-level result.
- Existing tests provide reusable fixtures for the command facade, API injection, runtime composition, Journal records, and projection recovery.
- The current simulator can close a long position through an ordinary SELL order and reports per-symbol realized PnL, so the first closed loop does not require a new accounting model.
- `record_risk_rejection()` already accepts an `origin`; the command facade must pass the strategy origin so rejected strategy intents remain auditable.
- `simulation/service.py`, `trading/journal.py`, `trading/local_paper.py`, and `trading/risk.py` already contain unrelated user changes. Avoid editing those files unless strictly required; build the new flow around their current contracts.
- `MockProvider` gives deterministic 3231 price 105.5, so a BUY limit 106 and SELL limit 105 can deterministically complete a round trip without modifying provider state.
- The dashboard already renders non-manual order origins, so strategy orders will be visible in the existing order blotter without a new UI workspace.
- Blocking asynchronous gap: when a streaming order is initially `SUBMITTED`, a later BidAsk callback calls `SimulationService._fill()` in the quote worker. The current `OrderApplicationService` only records terminal outcomes returned during the original submit call, so that later fill has no `local_paper_fill.v1` Journal record.
- The same gap applies to a pending Mock order filled during a later `refresh_quotes()` call. The terminal bridge must cover both paths and must not duplicate immediate-fill evidence.
- The terminal bridge now correlates the later simulator payload with the original command idempotency key and reuses `LocalPaperTerminalOutcomeRecorder`; duplicate BidAsk updates remain idempotent.
- A Journal bridge failure now blocks quote ingress and subsequent RiskGate submissions instead of allowing more non-replayable simulated orders.
- The 2026-08-21 10:43 Asia/Taipei live smoke used Shioaji simulation-environment Tick/BidAsk only: 3231 BUY filled locally at 177.5, SELL at 177.0, the position closed, stream health remained healthy, and both fill records proved `execution_authority=false`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add an explicit strategy-paper command method rather than weakening the manual method | Keeps origin and policy visible and testable. |
| Use deterministic intent-based idempotency keys | Prevents the same strategy decision from filling twice. |
| Implement run-once first | Provides an executable closed loop while avoiding an always-on scheduler before signal policy is frozen. |
| Keep one simulator adapter | It already preserves command origin and delegates BUY/SELL consistently. |
| Journal strategy metadata in a separate intent record | Avoids expanding the shared `OrderCommand` contract and conflicting with concurrent risk/trade-management work. |
| Strategy intent API submits one BUY or SELL at a time | Mirrors real lifecycle timing; two deterministic intents prove the complete round trip without inventing immediate round-trip behavior for live streaming. |
| Notify the command facade only for later terminal transitions | Immediate fills already use `CommandOutcomeRecorder`; limiting notifications to later fills avoids dual authorities while completing streaming evidence. |
| Store the command before invoking the simulator adapter | A BidAsk callback may complete a newly subscribed order before `apply()` returns; pre-registration makes that race journal-safe. |
| Treat continuous signal scheduling as the next milestone | This delivery proves explicit versioned intents end to end without silently promoting research scores into an always-on strategy. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- `simulation/application.py`
- `simulation/service.py`
- `trading/application.py`
- `trading/risk.py`
- `runtime/composition.py`
- `dashboard/server.py`
