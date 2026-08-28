# Findings & Decisions

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
# Initial findings

- Original active plan before orchestration: `2026-08-25-pr-tm-012c1-c1-runtime`; restore it after the three tasks reach an initial dispatched/monitored state.
- Official OpenAI documentation lists long-running goals, project teammates, and verified operations as Codex workflows. For this request, the desktop app's task tools remain the actual authority for creating and monitoring user-owned tasks.
- User authorized three separate tasks: Shadow `fill.v3` compatibility, slippage calibration tooling/offline analysis, and No-Overnight integration onto the stable Kill Switch + Tax/Slippage baseline.
- All tasks must preserve Local Paper/data-only/no-real-money boundaries and provide evidence-backed completion rather than self-declared completion.
- PR #2 is fully merged. Stable common baseline is remote `main` merge commit `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`; Python 3.11, Python 3.12, and real PostgreSQL durability CI all passed on main.
- The repository has no later deployment/release workflow, so this merge commit is the correct starting baseline for all three new worktrees.
- Codex project `tw_intraday_trader` has project id `100eb4e6-194d-4cac-939d-e2756d1f221f` and is a Git repository; create all three tasks as isolated project worktrees from the default branch (`main`).

# Created task setup handles

- Shadow `fill.v3` compatibility: `client-new-thread:c5623d83-c475-4d7f-8e09-513c6c98ae5a`.
- Slippage calibration evidence tooling: `client-new-thread:267153a1-4970-469b-a743-da994080449a`.
- No-Overnight integration/UAT: `client-new-thread:f5d05db9-66bd-4c05-9b87-45ecc8f71138`.
- All three are queued for isolated worktree setup; resolve real thread IDs from the task list before waiting/monitoring.

# Resolved tasks and initial audit

- Shadow `fill.v3`: thread `01a040b9-0761-7611-9dde-aa4f51a8d9af`, worktree `/Users/stevehuang-work/.codex/worktrees/ca66/tw_intraday_trader`.
- Slippage calibration: thread `01a040b9-0762-7352-9386-0481ccb93b52`, worktree `/Users/stevehuang-work/.codex/worktrees/cfab/tw_intraday_trader`.
- No-Overnight integration: thread `01a040b9-0761-7611-9dde-aa263d9b7dca`, worktree `/Users/stevehuang-work/.codex/worktrees/0f24/tw_intraday_trader`.
- Initial scope was aligned, but baseline validation found that Codex worktree creation used the saved project's stale local `main@a6e096a`, not merged `main@037197e1`. No task had begun product edits when detected.
- Sent a supervisory correction to all three tasks: only within their own clean worktree, fetch/resolve exact `037197e1`, create a scoped `codex/*-20260827` branch, verify Kill Switch/Tax-Slippage/CI commit ancestry, and stop fail-closed if exact baseline cannot be obtained.
- All three tasks acknowledged the correction and confirmed no product edits had occurred. Baseline fetch/branch creation is in progress; slippage reported the expected need for controlled Git worktree-metadata permission rather than bypassing the sandbox.
- Shadow baseline correction passed: scoped branch at exact `037197e1`, required three ancestor commits verified; only isolated planning data is untracked.
- No-Overnight baseline correction passed: `codex/no-overnight-integration-20260827@037197e1`, tracked/untracked clean before planning restart, required ancestry verified. It correctly treats stale shared `FETCH_HEAD` as non-authoritative and uses `origin/main` plus exact SHA.
- Slippage baseline correction has completed Git commands but has not yet emitted explicit branch/ancestry proof; keep its product implementation gate closed until that confirmation arrives.
- Slippage subsequently supplied complete proof: `codex/slippage-calibration-evidence-20260827@037197e1`, origin/main and FETCH_HEAD exact, required three ancestor commits verified, and no stale baseline product diff.
- All three task baseline gates are now passed; the initial stale-local-main drift is fully corrected.
- No-Overnight worktree does not contain its own pytest environment. The task is correctly searching for the bundled/root read-only runtime instead of installing ad hoc dependencies or claiming skipped tests as pass; this is not yet a blocker.
- No-Overnight safely reused the root interpreter from its own cwd; baseline full suite is `1500 passed, 43 skipped`. Four DSN-dependent PostgreSQL skips are explicitly `NOT RUN / NOT PASSED`, not a gate pass.
- Slippage decision Gate is correct: actual broker execution calibration is `ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`; current repo has no authorized broker-fill sample. Model-stress proxy tooling is feasible, but real artifacts currently lack joinable fill.v3 plus complete clock/session/liquidity coverage. The task will make actual-artifact dry run fail closed rather than infer 5 bps.
- Shadow completed contract inventory and entered test-first work for v3 single, partial, duplicate/conflict, tamper, and restart/replay; shared-core expansion remains explicitly constrained.
- No-Overnight semantic comparison now identifies 23 bilateral overlap files, with the five highest-risk core conflicts in runtime composition, simulation application/service, trading application, and Local Paper Journal code. It is using phased semantic porting rather than an old-branch merge.
- Supervisor read-only diff audit: Shadow has only isolated planning changes; slippage has only isolated planning changes; No-Overnight has isolated planning plus a new architecture semantic-port map. No product-code overlap has occurred yet and all `git diff --check` checks pass.
- Slippage implementation design is now constrained to one pure offline analyzer module and one CLI, reading existing sealed artifacts plus optional fill.v3 export; no provider/callback/capture/order/runtime seam will be added.
- Shadow added new regressions before implementation and obtained the expected failing run for the v1-only builder/observer boundary; it is recording red evidence before code changes.
- No-Overnight Phase 3 begins with provably non-conflicting domain/Journal deltas only; runtime composition, simulation, Dashboard, and fill.v3 projection reconciliation are intentionally deferred to later verified slices.
- Shadow froze a minimal compatibility contract: legacy v1 remains byte/digest compatible; v2/v3 activate through a new aggregate activation only after terminal `FILLED`, ordered by `fill_sequence`, preserving every record id/fingerprint and using total quantity plus quantity-weighted price/last-fill time. Product changes are limited to two Shadow files plus tests.
- PM reports PR #1 merged and `origin/main` advanced to `33c9b3a`. The three existing tasks were directly instructed to synchronize that commit before final review and rerun required validation; this supersedes `037197e1` only as the final-review baseline, while preserving the initial baseline evidence.
- All three tasks acknowledged the new baseline instruction and will integrate `33c9b3a` before final review, then rerun their required validations.
- Supervision must not perform formal review or merge. A completion or request-changes report must explicitly include branch, HEAD, tests, and gate status.
- Shadow focused implementation is green: 7 new compatibility regressions passed and 17 unchanged legacy builder/observer tests passed; broader and post-sync validation remains pending.
- Shadow independent review returned `REQUEST_CHANGES` with `P1=0`, `P2=4`: missing PostgreSQL stored-fingerprint comparison, public builder activation of non-terminal partial prefixes, two-read Journal snapshot TOCTOU, and policy quantity not bound to observed aggregate quantity. Commit/review gate remains closed.
- PM identified a concrete shared-file overlap: Shadow and No-Overnight both need `trading/postgres_journal.py` and `tests/test_postgres_journal_unit.py`. Ordered integration is mandatory: Shadow keeps a minimal reviewed patch; only after Shadow APPROVE may No-Overnight semantic-integrate that shared diff before final review and rerun validation.
- Slippage independent review returned `REQUEST_CHANGES` with `P1=3`, `P2=3`: causal timing window, clock authority, instrument eligibility, per-symbol pairing coverage, fill lineage, and atomic sealing. Despite synchronized focused/full/static/dry-run evidence, tooling-complete gate remains closed until fixes, regenerated checksums, and second independent review.
- Shadow post-fix no-DSN regression is `1511 passed, 44 skipped`; formal PostgreSQL selection is `4 skipped`, so PostgreSQL runtime remains `NOT RUN / NOT PASSED`. A narrow database-free reader-contract unit is being added to cover stored-fingerprint validation without claiming PostgreSQL integration.
- Shadow completed: branch `codex/shadow-fill-v3-compat-20260827`, HEAD `47a9303da0db26a17dd553488901af8caa423a55`, base `33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`, ahead 1 and clean. Closed-loop review APPROVE (`P1=0`, `P2=0`); final focused `30 passed`, full `1513 passed, 44 skipped`; PostgreSQL selection `4 skipped` remains not passed. No push/PR/merge; Production Shadow Gate remains NOT_PASSED.
- Sent exact Shadow commit identity to No-Overnight with instructions to inspect only the shared-file diff and semantic-integrate it before final review; no whole-file overwrite or broad cherry-pick.
- PM focused review of Shadow commit `47a9303` passed `26` tests. A push attempt was rejected by the permission gate; it must not be bypassed or retried without owner confirmation of the exact branch, payload, and destination. Local implementation approval does not imply remote publication or merge safety.
- Slippage second review closed all original six findings but returned `REQUEST_CHANGES` with two new P2s: clock review evidence was hash-only rather than parsed/bound to session, bound, market manifest, and reviewer; fill-store root was declared rather than derived from a read-only `JournalRepository` range snapshot. Third-loop fixes/review are required.
- Shadow is now remotely integrated at main `7931d31e53657c4f28e684402589c2b20501c1d9`. PR #3 was externally merged early at `023a082` while PostgreSQL failed; forward fixes `f6a38b1` (TIMESTAMPTZ/fingerprint reconstruction) and `254317b` (stronger corruption UAT expectation) landed through PR #4 after Python 3.11, Python 3.12, and PostgreSQL Journal passed.
- The final-review baseline for remaining tasks is therefore `7931d31e...`, not `33c9b3a`. No-Overnight was PM-instructed to synchronize and preserve shared PostgreSQL semantics; the supervisor sent the same sync/rerun gate to slippage before final review.
- Remote integration does not authorize broker, operational, Production Shadow, or later live gates.
- Slippage completed: branch `codex/slippage-calibration-evidence-20260827`, HEAD `82688e58ea8f44c8f00fb297b7bd23acdf1f59ab`, parent `7931d31e53657c4f28e684402589c2b20501c1d9`, clean worktree. Final review APPROVE (`P1=0`, `P2=0`); focused `18 passed`, PostgreSQL/Shadow compatibility `33 passed, 4 skipped`, full `1533 passed, 44 skipped`; no push/PR/merge.
- Slippage tooling completion is separate from calibration qualification: actual execution remains `ACTUAL_EXECUTION_CALIBRATION_NOT_QUALIFIED`, proxy input remains `MODEL_STRESS_PROXY_INPUT_NOT_QUALIFIED`, with 42 expected groups and zero qualified. The 5 bps value remains a model assumption; at least five complete qualified trading days are still needed.
- No-Overnight first independent review returned `REQUEST_CHANGES` with at least `P1=1`, `P2=4`: settings recompose may drop active No-Overnight/breach BUY latch; SELL durable cancel recovery applies BUY-only identity rules; PostgreSQL atomic evidence-window retry may mis-handle timestamp offsets across connections; reconciliation accepts uncheckpointed tail after checkpoint; CI PostgreSQL job omits the new UAT.
- Request-changes checkpoint: branch `codex/no-overnight-integration-20260827`, HEAD `a2abc3801268eef014caea4cb82fd09cf176db71`, parent `7931d31e53657c4f28e684402589c2b20501c1d9`, working tree contains minimal review fixes. Pre-review evidence was full `1731 passed, 46 skipped` plus disposable PostgreSQL `33+1+1 passed, 0 skipped`, but review gate overrides those results.
- No-Overnight completed after repeated closed-loop remediation and a final non-overlap rebase: branch `codex/no-overnight-integration-20260827`, HEAD `f73f004220ab826c6a84df237e822cf8a70cf125`, parent/current origin main `d5b86382c06a34e3a26ba2b23e3d714c783f0348`, ahead 1 and clean, one scoped local commit, no push/PR/merge. Both reviewers APPROVE (`P1=0`, `P2=0`).
- Final No-Overnight validation: full `1902 passed, 77 skipped`; focused `336 passed, 11 skipped`; evidence identity `30 passed`; disposable PostgreSQL CI-equivalent `39 passed`, handoff `5 passed`, Phase 5 `7 passed`, all PostgreSQL groups `0 skipped`; post-rebase reviewers ran `16` and `116` tests respectively. Temp clusters/databases were stopped and deleted without touching existing evidence databases.
- No-Overnight remains local-paper/no-real-money only. Formal DISABLED, OBSERVE_ONLY, supervised ENFORCING full-session campaigns, restart/duplicate-process/breach drills, and G6/production qualification remain `NOT PASSED`.
