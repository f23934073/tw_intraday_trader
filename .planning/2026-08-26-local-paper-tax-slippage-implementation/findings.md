# Findings & Decisions

## Requirements

- Only proven TWSE/TPEX common stock, cash, non-day-trade Local Paper execution may use the new policy.
- Freeze `tw_stock_standard_v1`, `twd_round_down_v1`, `fixed_adverse_bps_v1`, and `tw_common_stock_tick_v1`.
- SELL tax is 3 per mille, whole-TWD ROUND_DOWN; slippage is adverse price movement and is never deducted again.
- Adjusted price beyond limit stays pending and must not consume visible volume.
- Add settings v2 and fill.v3; never rewrite fill.v1/v2 or old monetary truth.
- Preserve local-only, market-data-only, no-broker/no-CA/no-trade-callback/no-real-money boundaries.
- Wait for stable Kill Switch candidate before overlapping application/composition/API/UI files.
- Formal completion requires actual PostgreSQL restart UAT; skips and waivers are not a pass.

## Research Findings

- At the start of TS-006, the current diff also contains overlapping Local Paper changes in `simulation/strategy_flow.py`, `tests/test_local_paper_command_service.py`, `tests/test_local_paper_projection.py`, and `tests/test_strategy_paper_flow.py`, plus larger application/local-paper hunks than the prior handoff. Treat these as concurrent user-owned candidate changes: review them in place and do not discard or overwrite them.
- TS-006 P1 fixed: `_record_later_terminal_order` and `_record_daily_baseline` relied on `_write_checkpoint` to enter command-level recovery. An earlier Journal append failure escaped those callbacks and was swallowed by `SimulationService`, which blocked simulator admission but left the command recovery latch green. The fix latches every persistence boundary before re-raising, and the strategy flow now verifies no later intent is appended.
- TS-006 P1 fixed: equal-timestamp BidAsk replays were accepted as fresh book updates, resetting best-level available quantity after a partial fill. Because the feed contract has no exchange sequence number, equality cannot prove new liquidity; BidAsk ingress now requires a strictly newer exchange timestamp.
- TS-006 P2 fixed: the accounting kernel allowed a tiny SELL whose gross was below the cumulative minimum commission to produce a negative `net_cash_effect`. The frozen decision now detects this impossible cash-credit outcome and returns no fill.
- TS-006 P1 fixed: fill.v3 validated whole-TWD commission shape but not the frozen cumulative commission formula, so a coherent commission/cumulative/net rewrite could pass. v3 now persists cumulative order gross and reconstructs both previous and current cumulative commission deltas exactly.
- TS-006 P1 fixed: an appended cancellation intent followed by a crash before order-state/checkpoint persistence was not classified as an uncheckpointed mutation. Restart could therefore reactivate the pre-cancel pending order. Cancel intents are now checkpoint-covered mutation evidence and unresolved tails stop recovery.
- TS-006 P1 fixed: standalone v3 checks could not prove cumulative tax lineage on later partial fills. The reducer now carries per-order v3 cumulative state and requires strictly consecutive fill sequence plus exact gross/commission/tax deltas before applying cash or positions.
- TS-006 P1 fixed: v2 tick and instrument scope validation ran only inside the side-effect adapter, after an approved command was journaled. Expected user admission errors were therefore classified as handler durability failures and latched the account. A provider-read-only preflight now rejects them before any Journal mutation.

- Worktree began clean at detached `657c3bbc117af1c2909175dfc799bce7e8be07ca`, while main remained `a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9`.
- A second Codex worktree exists at the same `657c3bb` HEAD, so no stable Kill Switch candidate commit is yet visible from git state.
- Prior Local Paper settings implementation pins settings digest/session lifecycle and preserves old Journal; tax and slippage were intentionally outside v1.
- Existing root planning files belong to an unrelated freshness-evidence task. This task uses an isolated `.planning/2026-08-26-local-paper-tax-slippage-implementation/` directory.
- No repository `AGENTS.md` was found.
- Current SDK and official Shioaji docs confirm the `STK` catalog also contains ETFs. Admission now requires `TSE/OTC + STK + four-digit numeric ordinary-share code + reviewed exchange-specific industry category`; category `00`, management `80`, special-share codes, and unknown values fail closed.
- Existing matching is duplicated across submit, snapshot reconcile, and BidAsk worker; all currently compare raw reference price to limit before `_fill`.
- Existing commission is cumulative order commission delta but uses v1 settings cents `ROUND_HALF_UP`; SELL cash and realized PnL have no tax.
- Compatibility is explicit in `SimulationService`: legacy construction keeps the existing policy; `cost_policy_enabled=True` pins the frozen v2 rate/minimum and activates descriptor/tick/slippage/tax/fill.v3 evidence.
- fill.v3 replay requires the session settings digest, validates persisted monetary/reference/policy/descriptor evidence, and applies stored net cash rather than recalculating current policy.
- Final adversarial review tightened fill.v3 audit so missing cost fields, coherently modified tax/net pairs, and coherently modified reference diagnostics cannot bypass the frozen policy.
- Settings v2 now normalizes its schema before identity checks, requires a present slippage field, and accepts only the exact Boolean `false` for non-day-trade identity.
- Kill Switch candidate was independently reviewed, committed as `34fb5250030d170b7909870f086c5693f728a9aa`, and rebased into this worktree before any overlapping integration edits.
- settings v2 supports a mixed migration document: active v1 plus draft v2 until explicit activation creates a new session pointer. Reading or previewing a v1 file does not rewrite it.
- The environment had no inherited DSN, but a disposable local `postgres:16-alpine` database is now available at a task-only port; the actual Journal baseline passed and final restart UAT can run after integration.
- Kill Switch commit contains exactly 16 expected product/doc/test paths, has parent `657c3bb`, and does not contain its temporary planning files.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Framework-free frozen dataclasses/value decisions | Enables domain tests without runtime, provider, DB, or UI dependencies. |
| Optional provider descriptor port defaults unavailable | Unknown products must fail closed and cannot be guessed into the tax policy. |
| Compute complete fill decision before state mutation | Prevents partial cash/order/position changes on policy or Decimal errors. |
| Persist complete v3 monetary/reference/policy evidence | New fills remain auditable and replay does not depend on future policy code. |
| Recompute tax and adverse tick result only during v3 validation | Detects coherent evidence tampering while the reducer still applies persisted monetary truth and never reprices history. |

## TS-006 Final Review Decision

- **APPROVE** after the requested fix/re-review loop.
- Six P1 findings and one P2 finding were reproduced and fixed.
- No unresolved P1/P2 correctness issue remains; live slippage calibration is still a separate evidence task.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Cross-thread status lookup stalled | Continue non-overlap work and retry before integration. |
| Isolated worktree has no local pytest environment | Reuse the main-workspace venv executable without changing that workspace. |
| First new service test mutated shared Mock fixture dictionaries | Copied fixture rows per `PriceProvider` instance so tests cannot leak prices into legacy tests. |
| Fixed timestamp made the streaming test book stale | Use a fresh Asia/Taipei receipt timestamp for executable-book tests. |
| Cross-thread coordination message also stalled | Terminated the stalled call; retain filesystem evidence and inspect the candidate worktree before every overlap phase. |
| Homebrew `libpq` includes `initdb` but not the matching `postgres` server binary | Used the already-installed local Docker image for a disposable PostgreSQL instance. |
| Kill Switch worktree reached a quiet, whitespace-clean candidate but remains detached and uncommitted | Do not mutate the independent worktree; request an explicit commit/coordination decision before rebase. |
| Sandboxed rebase could not autostash tracked edits | Approved rebase escalation created and reapplied the autostash cleanly; no conflict or stash residue remained. |
| Formal review must be independent | Local code-review-excellence audit resolved all findings found here, but TS-G5 is not claimed until a separate reviewer reports no P1/P2 issue. |

## Resources

- User-supplied authoritative implementation plan in the current task.
- `MEMORY.md` Local Paper task group and the prior daily-limit/settings rollout summary.
- `planning-with-files`, `karpathy-guidelines`, `architecture-patterns`, `ui-ux-pro-max`, browser-control, and code-review-excellence skill instructions.
