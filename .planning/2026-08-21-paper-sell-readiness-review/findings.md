# Findings: Paper-trading sell readiness

## Context already established

- The repository has a local paper simulation that must not call broker order APIs.
- Referenced-task discussion requires strategy role/session separation and a shared executor.
- Referenced-task discussion called out timeout, cancellation, repricing, partial fills, costs/slippage, position ownership, restart recovery, stale-data handling, and emergency stop as execution contracts.

## Evidence log

- Prior verified local-simulation scope: long-only whole-lot limit orders; immediate marketable fills, pending/cancel states, idempotency, average cost and PnL; no fees/taxes and restart-cleared state.
- Prior architecture finding: dashboard simulation routes call `SimulationService` directly rather than the formal `RiskGate` / `OrderApplicationService` / append-only journal and recovery path.
- Prior quote-health finding: executable sell decisions must use acknowledged/fresh BidAsk evidence; Tick freshness alone is insufficient.
- The current worktree is substantially modified and contains new trade-management and exit-engine files. This review must evaluate the live worktree, not infer readiness from earlier committed behavior.
- The referenced task treats strategy output and order execution as separate: an EXIT recommendation is expected to flow through a shared simulator/executor.
- Review checklist will emphasize async cancellation, precise exception handling, race/TOCTOU behavior, idempotency, state ownership, and edge-case tests.
- The referenced task is still actively editing the atomic-strategy implementation plan and explicitly remains `NO-GO` for product implementation; its most recent blockers are lifecycle concurrency and Hard Risk ordering/monotonic policy merge.
- Therefore, strategy-template/parameter/Strategy Set work described in that task is plan-only and must not be counted as an implemented sell mechanism.
- `ExitRecommendationEngine` is explicitly decision-only and has no persistence, risk, position, order, or execution authority (`trading/exit_recommendation.py`). It currently maps only thesis invalidation and time decay into EXIT/HOLD recommendations.
- `StrategyPaperIntent` and `LocalPaperCommandService.submit_strategy_order()` accept both BUY and SELL, pass automated intents through the formal `RiskGate`, journal the command/outcome, and delegate only to the local simulator.
- Later terminal fills are journaled through a callback, while manual cancellation is journal-first. Checkpoint failure is surfaced as a do-not-resubmit state error.
- The sell-path review still needs to prove whether `ExitRecommendationEngine` is wired into any runtime that emits `StrategyPaperIntent(side=SELL)`; type-level SELL support alone is insufficient.
- A separate `ContinuousPaperStrategyController` does emit SELL intents, but only for one hard-coded Momentum strategy. Its exits are fixed-percent stop loss, fixed-percent take profit, and 13:25 end-of-session flatten.
- Confirmed ownership bug: the controller reads the simulator's sole position and manages it based only on symbol and exactly 1,000 shares. It does not verify the position was opened by this controller/run/strategy, so starting automation with one manual 1-lot position can cause an automatic SELL.
- Confirmed executable-book freshness bug: `SimulationService.positions()` exposes `quote_received_at` from the latest Tick-or-BidAsk receipt, while the controller uses that field to authorize a SELL at `bid_price`. A fresh Tick can therefore make an old BidAsk appear fresh. The order payload separately uses `book_received_at`, showing the needed timestamp already exists internally.
- Confirmed stuck-exit gap: if any order is `SUBMITTED`, the controller only waits. There is no automated timeout, cancellation, repricing, or escalation for an unfilled SELL; the simplified order model has no partial-fill status.
- Confirmed daily-loss ordering gap: the controller returns `BLOCKED_DAILY_LOSS` before inspecting open positions, so a breached daily-loss limit can stop the strategy from issuing a protective exit for an existing holding. `RiskGate` itself blocks daily-loss only for BUY, so the controller behavior is stricter in the unsafe direction.
- The simulator fills an order entirely or not at all at ask/bid and computes PnL without commission, sell tax, slippage, or partial fills. This is adequate for a smoke lifecycle but not realistic sell-performance validation.
- The formal thesis-based `ExitRecommendationEngine` is referenced only by replay/shadow code outside tests. The live local-paper controller does not consume its recommendation or execution-eligibility contracts; the two sell mechanisms are currently disconnected.
- Runtime creation always creates a fresh `SimulationService` and a new random local-paper Journal session with `restart_policy=NEW_LOCAL_PAPER_SESSION`. Although journal replay/checkpoint utilities can verify a prior projection, composition does not hydrate orders/positions/strategy state back into the simulator. Restart therefore loses the actionable sell state.
- The dashboard automated-strategy start contract exposes only `stop_loss_pct`, `take_profit_pct`, and `max_daily_loss`; the controller is hard-wired to the Momentum projection. Database strategy definitions and backtest exit selection are not connected to this runtime.
- Backtest supports separately selectable EXIT strategies and applies commission, sell tax, and slippage, but the automated simulator does not reuse that exit registry or cost model. Backtest coverage therefore does not establish live paper-sell parity.
- Focused regression suite passed: 66 tests covering continuous strategy, strategy paper flow, simulator, journal/checkpoint projection, exit recommendation, eligibility, and replay.
- Read-only scenario probes reproduced three review defects: a lone position with no ownership evidence produced `EXIT_SUBMITTED SELL`; a daily-loss breach with an open position produced `BLOCKED_DAILY_LOSS` and zero intents; a rejected SELL was still reported by the controller as `EXIT_SUBMITTED`.
- Exit submission result-handling bug: `_evaluate_position()` discards the flow result and unconditionally reports `EXIT_SUBMITTED`, unlike entry logic which checks `order.status`. A rejected exit can therefore be displayed as successfully submitted and retried only idempotently as the same rejected order.
- Final verification: full suite `1062 passed, 4 skipped`; Python compileall, dashboard JavaScript syntax check, and `git diff --check` passed.
- Final decision: supervised smoke only is conditionally ready; unattended automated selling is NO-GO; the general strategy sell platform remains plan-only/separate from this one hard-coded controller.
