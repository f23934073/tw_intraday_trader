# Findings & Decisions

## Requirements
- Continue beyond the completed run-once strategy intent flow into a continuous automated local-paper strategy session.
- Keep all fills inside `LOCAL_PAPER_SIMULATION`; Shioaji remains Tick/BidAsk data only.
- Start with one versioned strategy, one-lot entries, and at most one open position.
- Include explicit start/stop/status, market-session and data-health gating, deterministic retries, and automatic exit behavior.
- Preserve the very large unrelated dirty worktree.

## Research Findings
- The referenced task completed `strategy intent -> Journal -> RiskGate -> local fill -> position -> exit -> realized PnL` for explicit run-once intents.
- The referenced task identified continuous signal generation/scheduling as the next milestone.
- A separate overlapping task has now completed simulation-projection WebSocket delivery and stopped writing to the workspace.
- Prior project memory confirms Shioaji uses `subscribe_trade=False`; quote data is valuation/fill evidence, never broker-account or execution authority.
- `StrategyPaperFlowService.submit()` already rejects future and prior-session signals, journals a versioned intent, and delegates to the common strategy-origin command path.
- `LocalPaperCommandService` already enables strategy origin but currently uses very permissive notional/daily-loss defaults; the continuous controller needs stricter session-level exposure constraints of its own.
- `RuntimeComposition` owns the existing strategy flow and in-memory Journal, making it the natural place to own one controller lifecycle without creating a second execution path.
- The repository has a long-lived `MomentumShadowRuntime` with signal evaluation, state, read views, pending alerts, quote-pair staleness checks, and counters. This is a stronger candidate signal source than the dashboard's snapshot Candidate score.
- Existing signal code includes entry-opportunity evaluation and breakout-related state; the controller should consume that server-owned projection instead of recomputing a browser/display rule.
- Existing simulation projection exposes positions/orders and later BidAsk fills; controller decisions can observe this same authoritative local-paper state.
- `MomentumShadowRuntime` deliberately marks presentation entry opportunities blocked because no execution RiskGate is supplied in Shadow mode. A controller must not treat that blocked presentation object as an order; it may consume the underlying `SignalResult` only and then use the existing command-layer RiskGate.
- `RealtimeMomentumDashboardService.snapshot()` serializes a process-lock-consistent view with `status`, live-source flag, connection state, data-health state, evaluated items, signal digest/config, and provenance-bearing intraday price. This is a practical read-only signal adapter seam.
- A valid entry candidate can therefore require: live/healthy/running source, evaluated item, triggered signal, confirmed momentum acceleration, valid fresh price, and a unique signal digest. Raw Candidate score is only subscription priority and is not an execution condition.
- The existing Momentum policy represents opening/limit-up momentum, not a formally implemented ORB. The continuous controller should use a momentum strategy identifier that matches the actual evidence contract instead of the run-once README's illustrative `opening_range_breakout` label.
- No project-approved stop-loss/take-profit percentages are frozen. Start parameters should require the operator to supply them, then version and expose those values in controller status rather than embedding unexplained thresholds.
- `SimulationService.positions()` supplies average/current price, PnL percentage, best bid/ask, and quote timestamps, sufficient for a deterministic whole-position local-paper exit decision.
- The reviewed `ReviewedEquityCalendar` covers 2026 TWSE trading days. It can fail closed outside reviewed coverage and on closures; regular equity hours are 09:00-13:30 Asia/Taipei.
- `IntradayFeatureSnapshot` has a provenance-bearing Tick price but no best bid/ask prices. Entry will use the current valid Tick as the limit and let the simulator's independent BidAsk subscription decide whether or when it fills.
- Once a position exists, `SimulationService.positions()` exposes best bid and its receipt timestamp. Exit can submit the whole one-lot position at a fresh best bid; missing or stale book blocks the exit attempt and remains visible in controller status.
- Existing `AfterCloseIncrementalScheduler` provides a simple `Event` plus daemon-thread plus deterministic `run_due()` pattern that can be mirrored without sharing job-specific behavior.
- The deterministic end-to-end integration confirms one entry and one stop-loss exit traverse the real `StrategyPaperFlowService` and produce the expected LOCAL_ONLY intent, risk, order, fill, position, and exit evidence without a broker adapter.
- Browser verification confirms the operator controls are usable and that Mock mode fails closed with zero orders rather than silently simulating live evidence.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Treat `opening_range_breakout` as an identifier pending code-grounded signal validation | It is already used by the run-once API examples, but its name alone is not sufficient evidence to trade. |
| Do not auto-start on dashboard boot | Explicit operator control is a required safety boundary. |
| Replace the tentative ORB identifier with the existing Momentum evidence policy | Code evidence shows the live strategy contract is Momentum acceleration across opening and limit-up families, while ORB is only an example string. |
| Require stop-loss and take-profit at start time | Avoids inventing production-like thresholds before calibration is frozen. |
| Require daily-loss amount at start time | Prevents the permissive underlying command-policy default from silently becoming the automated-session limit. |
| One entry per session in v1 | Bounds retries and exposure while still proving continuous signal-to-exit behavior. |
| Stop does not flatten an existing local position | Avoids disguising a control action as an executable market decision; exit remains governed by fresh book evidence and strategy rules. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Planning patch targeted a decision row in `task_plan.md` that existed only in `findings.md` | Re-read the planning files and patched each section separately. |

## Resources
- Referenced task `01a02213-5121-7572-bbdc-95057769c607`
- `.planning/2026-08-21-automated-local-paper-trading-flow/`
- `simulation/strategy_flow.py`
- `runtime/composition.py`
- `dashboard/server.py`
