# Findings & Decisions

## Requirements
- Collect slippage calibration data during trading hours.
- Execute No-Overnight DISABLED and OBSERVE_ONLY evidence campaigns.
- Prepare formal release reviews for `82688e58ea8f44c8f00fb297b7bd23acdf1f59ab` and `f73f004220ab826c6a84df237e822cf8a70cf125`.
- Do not push, create PRs, merge, send broker orders, use real money, or promote operational/Production Shadow Gates.

## Research Findings
- At 2026-08-27 12:22 CST the Taiwan cash session was already in progress, so a new run cannot be represented as a complete trading day.
- Slippage worktree: `/Users/stevehuang-work/.codex/worktrees/cfab/tw_intraday_trader`, branch `codex/slippage-calibration-evidence-20260827`, HEAD `82688e58...`.
- No-Overnight worktree: `/Users/stevehuang-work/.codex/worktrees/0f24/tw_intraday_trader`, branch `codex/no-overnight-integration-20260827`, HEAD `f73f004...`.
- Main checkout is heavily dirty with unrelated user work and must not be used for code modification or branch integration.
- The main checkout catchup diff contains thousands of unrelated user lines across research, market-data, backtest, and planning files; all execution stays in the two clean task worktrees.
- The No-Overnight branch documents default `DISABLED`, observation-only `OBSERVE_ONLY`, and separate operational/evidence campaign runbooks; exact commands still require direct runbook reading.
- A qualifying DISABLED capture must start no later than 09:00 Asia/Taipei and the PostgreSQL transaction rejects any open-marker creation that crosses 09:00. At 12:22, no valid partial campaign can be started or backdated.
- No-Overnight stage order is strict: full DISABLED session, later full OBSERVE_ONLY session, parameter approval, supervised ENFORCING, then drills. DISABLED and OBSERVE_ONLY cannot qualify on the same trading date or run concurrently.
- The slippage CLI only seals and analyzes already-existing canonical Local Paper fill evidence. It does not connect to a broker or collect live data by itself; the task must identify the approved source/export workflow before any session claim.
- Existing task IDs will be reused: slippage `01a040b9-0762-7352-9386-0481ccb93b52`, No-Overnight `01a040b9-0761-7611-9dde-aa263d9b7dca`, Shadow/reviewer `01a040b9-0761-7611-9dde-aa4f51a8d9af`.
- Slippage task already had one bounded CLOSE partial-rehearsal supervisor and a same-task inspection heartbeat; follow-up explicitly forbids a second capture.
- No-Overnight task is keeping planning/scheduler state outside the candidate worktree so `f73f004` can remain clean for the runner's own preflight.
- Independent reviewer is active under a read-only constraint and will not create planning or code files in either candidate worktree.
- No-Overnight preflight has confirmed exact code/runbook/calendar/Python/env-file metadata; next reviewed DISABLED date is 2026-08-28 and the earliest possible later OBSERVE_ONLY date is 2026-08-31.
- A legacy `pr-no-006-disabled-baseline` heartbeat is still ACTIVE. It must be inspected and safely updated or disabled in place; creating a second schedule would be a conflict.
- Independent topology review found no file-level upstream conflict for Slippage; No-Overnight is directly parented on current main. Semantic and test review remains in progress.
- Independent release review completed: both exact commits APPROVE with P1=0/P2=0. Slippage is 7 behind/1 ahead with no path overlap or merge-tree conflict; No-Overnight is 0 behind/1 ahead on current main.
- Slippage independent tests: focused 18 passed; full 1533 passed, 44 skipped. PostgreSQL was not rerun by this reviewer; the commit does not modify the PG adapter. Exact commit excludes later operational files.
- No-Overnight independent tests: critical 156 passed; full 1902 passed, 77 skipped; static/diff passed. Reviewer accepted the exact candidate's fresh-disposable PostgreSQL 39+5+7 passed, all zero skip.
- No-Overnight preflight is BLOCKED only by the already-running legacy `21fd771d` runner PID 72965, started 08:46:50 and waiting through close. PostgreSQL read-only health, clean code, calendar, env metadata, MockProvider, absent integrated session/root all passed.
- One continuation heartbeat `no-overnight-f73f004-post-close-preflight` is scheduled for 14:00. It is not a runner schedule; only a clean post-close re-preflight may update that same automation for the 2026-08-28 integrated DISABLED run.
- Planned integrated identity is `no-overnight-integrated-f73f004-20260828-v1`; earliest later OBSERVE_ONLY date is 2026-08-31, but no OBSERVE_ONLY entrypoint or schedule is authorized yet.
- Root PM heartbeat `pm-trading-campaign-supervisor` is active for 14:15 on 2026-08-27. It will consolidate the Slippage 13:14 inspection and No-Overnight 14:00 continuation without rerun; if a valid 8/28 DISABLED schedule exists, it must update the same heartbeat for post-close verification rather than create another monitor.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Treat partial-session evidence as non-qualifying | Prevents a late start from being mistaken for one of the required complete trading days. |
| Run incompatible No-Overnight modes separately | Avoids ambiguous authority and evidence identities. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Session catchup found prior orchestration context | Reconciled exact task/commit status into this isolated plan before execution. |
| Reviewer test could not create a temp directory in its read-only sandbox | No tests were collected, so it is neither pass nor product failure; reviewer is rerunning with an approved non-worktree temp root. |

## Resources
-
