# Findings and Decisions

## 2026-08-27 — Resume historical-data and R6 next stages

- Live source-repair authority, not the stale isolated workpad, says case `finmind-repair-9f08aa0024440e4601ac` is `ACTIVE` with activation `finmind-repair-activation-83ca14d4d3d0ca89ac42`, one active bar, audit 1/1, and zero issues. The next truthful step is a new immutable snapshot/Dataset that records this repair lineage; no provider call or repeated activation is needed.
- The wider three-year acquisition is not complete: current SQLite holds 454 distinct symbols and 329,333 partitions, recent jobs are terminal, and no writer or heartbeat is active. Snapshot verification is the immediate next phase, not proof of full-market completion.
- R6's post-release next stage is already frozen by the owning task: durable eligibility-audit registration, CAS creation/activation of matrix revision 3, exactly one full seven-slot G3 preflight, and independent artifact/PostgreSQL Gate review. G4 and every trading stage remain separate and unauthorized.
- If the R6 durable transitions require an actor or change note not frozen by the contract, the task must stop and return the exact missing fields rather than infer the owner's identity.
- R6's read-only preflight now proves the released migration and canonical artifact are eligible for the planned continuation, but durable work is correctly blocked on an exact `actor_id`. No audit registration, revision-3 state, preflight, attempt, or release transition was created.
- The merged package does not yet expose the required application/repository use cases for eligibility-audit registration and revision-3 CAS activation. Those seams must be implemented and independently reviewed before any formal PostgreSQL mutation; direct SQL would violate the frozen contract.
- `確認三大法人策略資料` should not start the prepared 2,781-symbol Shioaji r3 scan as a duplicate primary history source. Its dependency-safe next stage is an offline Coverage Audit and MVP Evaluation Universe freeze over the new FinMind immutable Dataset; Shioaji remains only a separately authorized gap/exception source.
- PM review found no request-change blocker in the new institutional consumer plan. It correctly separates the metadata-only FinMind handoff and MVP coverage audit from formal `PriceCoverageAuditV1`, PIT, holdout, runtime defaults, and outcome generation.
- The institutional consumer cannot yet freeze its universe: the one sealed source/target pair is 2026-08-18 -> 2026-08-19, while the Dataset ends 2026-08-18. A digest-pinned historical or prospectively accumulated series with at least 60 overlapping target sessions is independently required; Dataset completion alone does not satisfy this gate.
- The new immutable history Dataset is materialized as `dataset-finmind-sponsor-sha256-4defb3967d4e89f87d920197877358a8237cdf9baa51be1001fb156b70310ce4`, with 453 symbols and 51,213,436 bars. It is not yet PM-approved because the owning task's full source-versus-materialized equality audit is still running; latest live evidence reports zero mismatch and no mutable-state writes.
- R6 no longer waits for actor identity: the exact actor is `SteveHuangJob`, the eligibility audit and revision-3 CAS activation are durable, and one G3 preflight is supervised at 3.53% with zero errors/restarts and zero formal attempts. Completion still requires final immutable-artifact/PostgreSQL verification and independent Gate review.
- The existing R6 30-minute supervisor is the only monitor needed. Creating a duplicate would add race/noise without additional evidence; PM should use bounded task snapshots and act only on completion or attention-required events.
- Cross-task supervision is now durable through heartbeat `r6-pm`, scheduled at minute 15/45 and attached to this PM conversation. It coordinates completion review and handoff while delegating R6 process telemetry to the pre-existing `r6-g3-preflight-30` monitor.
- The 51,213,436-bar full equality audit has now passed with zero mismatch. Dataset ID, manifest digest, bars digest, and saved-plan digest are stable against the first atomic publication; this clears the data-equality blocker but still requires the owning task's bounded handoff and independent PM review before institutional consumption.
- Independent Phase 81 file inspection matches the reported manifest and plan file hashes and confirms the expected 10.596 GB JSONL payload. The saved snapshot directory also contains a 32 KiB SHM sidecar and a zero-byte WAL sidecar; this may be a harmless SQLite read-connection artifact, but PM must verify sealed database identity and absence of uncheckpointed WAL content before approval.
- Phase 81 is independently `APPROVE` with P1=0/P2=0. Actual payload SHA, manifest digest, snapshot-plan digests/handoff, both SQLite quick checks, exact repair projection digests, original EMPTY partition, 9960 materialized row, and focused regressions all pass. The SHM sidecar has no open holder and the zero-byte WAL contains no uncheckpointed data; copied main-file SHA is exactly pinned by the plan.
- Both approved downstream continuations are active in their original tasks. History is restoring the deterministic status-only job seam; Institutional is verifying only exact metadata pins. Neither has reported an immediate blocker or crossed the provider/outcome/G4/trading boundaries.
- Phase 82 physical evidence currently matches its handoff: official company snapshot identities/counts, sealed FinMind locators, one exact QUEUED eight-symbol job, null calendar/status payloads, and zero partitions. Remaining review work is direct attempt-count proof plus independent config/selection reproduction.
- Phase 82 selection and job identity reproduce exactly, but provenance is not durable: official listing snapshots and selector logic are available only in `/private/tmp`, while the SQLite job row contains only the final config. Hashes in a planning note do not preserve the source bytes or algorithm after temp cleanup. This is a P2 replay/audit blocker before any calendar/provider stage.
- Phase 82 P2 remediation now passes independent re-review. The exact TWSE/TPEx bytes are preserved under content-addressed project paths and remain byte-identical to the reviewed temp inputs. Bundle self-digest `e9faeadd...7d97` binds the selector contract, six source references, approved Dataset/plan identities, 66 completed-job bindings, exact 453/426/454 symbol sets, full ranking/selection, config digest, job ID, and post-create state. The repository verifier independently reproduces 1,284 eligible rows, 29 ranked candidates, the exact eight-symbol order, config/job identity, and live SQLite state; 18 focused tests pass including four fail-closed tamper cases.
- The bundle's self-digest is a canonical semantic digest computed with the `bundle_digest` field omitted; consequently the physical JSON file SHA-256 is `ef9a1b60...6e677`, not the filename suffix. This is internally consistent and verified by the tool, but downstream users must call it a self-digest rather than a raw-file digest.
- Institutional PR-MVP-EVAL-001 metadata-only handoff is independently `APPROVE`, P1=0/P2=0. The workpad preserves the exact Dataset/plan/9960 pins and no forbidden artifact or provider action. Direct inspection of `finmind_institutional_mvp_candidate_observation_v1_2026-08-24-r2.json` confirms exactly 17 candidates, each sourced from 2026-08-18 and usable only from 2026-08-19, while the approved Dataset ends 2026-08-18. Overlapping target sessions remain exactly zero, so `WAITING_FOR_INSTITUTIONAL_SERIES / INSUFFICIENT_EVIDENCE` is the only valid state and no Evaluation Universe may be frozen.

## 2026-08-27 — R6 A2 Migration 018 remote release

- Owner authorization is exact and scoped to branch `codex/r6-a2-migration018-20260827`, commit `ed477898e707435036936a91afe07f3b846f4758`, destination `origin`, PR creation, green CI, final integration checks, and merge.
- The same authorization expressly excludes audit registration, revision-3 activation, G3 preflight, Local Paper, broker, and real-money execution; remote release must stop after merge/reachability proof.
- The dirty primary checkout remains evidence/PM state only and is not an integration surface. All Git release mutations must use the clean isolated R6 worktree.
- Pre-push freeze passed: clean worktree, exact HEAD `ed477898`, parent and merge-base `7931d31`, `0 behind / 1 ahead`, remote URL `https://github.com/f23934073/tw_intraday_trader.git`, tree digest `f130410c7757fa803ac1e36f6a762f9edd8ca5a2`, and no remote branch collision.
- PR #6 was created with exact reviewed scope and is structurally mergeable, but initial CI is not green. Python 3.11 failed only `test_start_writes_durable_submission_before_launch` and `test_start_refuses_second_loaded_job` because the Linux runner correctly triggered the production macOS-only guard before the tests' mocked launchd assertions; PostgreSQL Journal passed.
- Correct remediation is test-harness portability, not weakening runtime safety: simulated launchd unit tests must set the module platform seam to `darwin`, production must continue rejecting non-macOS execution, and Linux guard behavior remains directly tested.
- The staged eight-line remediation satisfies that exact contract: two targeted `darwin` monkeypatches plus a new explicit Linux rejection test, all in the existing supervisor test file. No production or workflow file changed, so PM independent remediation review is `APPROVE` pending completed test/CI evidence.
- Approved remediation commit is `aced00adf19cad54d0cec7c399f0d6f5ea67d624`, one test file and eight insertions; production remains bit-for-bit at the reviewed `ed477898` payload.
- Concurrent PR #5 advanced `main` to `9ab43c3` while PR #6 CI was running. A mergeable label alone is insufficient: final CI/merge-ref evidence must bind R6 to that latest base so source-repair changes and R6 are tested together without rewriting either branch history.
- Final integration passed after that base movement: all three required jobs are green, GitHub reports `CLEAN/MERGEABLE`, and PR merge ref `e69630f` is a two-parent merge of exact latest main `9ab43c3` plus approved R6 head `aced00a`. PM disposition is final `APPROVE TO MERGE`.
- Release is complete: PR #6 is `MERGED`, merge commit `d5b86382c06a34e3a26ba2b23e3d714c783f0348` is live `origin/main`, original R6 `ed477898` and remediation `aced00a` are both reachable, and post-merge main CI `33035268279` is green across Python 3.11, Python 3.12, and PostgreSQL Journal.
- The release stopped exactly at integration. No audit registration, revision-3 activation, G3 preflight, Local Paper, broker, or real-money operation occurred.

## 2026-08-27 — Active branch and Codex-task PM reconciliation

- Treat Git reachability, PR review/check state, and Codex task state as three separate facts. A branch is mergeable only after all three are reconciled.
- The primary checkout is not a safe merge surface: local `main` is `ahead 19, behind 4` relative to the currently recorded `origin/main`, and the worktree contains extensive tracked and untracked changes from several task families.
- The first local inventory found ten registered worktrees, including two prunable `/private/tmp` entries, six staged no-overnight branches, a Trade Management Shadow runtime branch, and three branches at the current recorded `origin/main` prepared for later integration/evidence work.
- `codex/local-paper-tax-slippage-20260826` points to `786f452` while the recorded `origin/main` is merge commit `037197e`, whose subject says PR #2 merged that branch. This branch is already reachable from the recorded remote main and must not be merged again.
- The Codex task-list request with `limit=100` exceeded the API maximum of 50. It changed no task state; retry with the supported bound.
- After a successful current fetch, GitHub has two PRs in total. PR #2 (`codex/local-paper-tax-slippage-20260826`) is merged at `037197e` with Python 3.11, Python 3.12, and PostgreSQL Journal checks successful. It requires no additional merge.
- PR #1 (`docs(architecture): 建立全專案 current-state 架構圖集`) was initially observed open at `e80f577` with all three CI checks successful and no review decision. While formal review was beginning, user `Steve_project` merged it at 2026-08-27T01:15:39Z as merge commit `33c9b3a`; the freshly fetched `origin/main` contains that head. Do not fabricate a retroactive approval decision; perform only post-merge STE-5 task/Linear reconciliation.
- The newly created worktree tasks `No-Overnight 新版整合與 PostgreSQL UAT`, `Shadow fill.v3 相容性整合`, and `Local Paper 滑價校準證據工具` are all currently `active`; do not duplicate or restart them.
- Two additional repo tasks, `建立三年歷史資料` and `歷史台股回測準備度`, are active in the dirty primary checkout. Their branch ownership is not isolated, so their output cannot be packaged or merged until their conversations and change provenance are inspected.
- Reachability after the current fetch shows `PR-NO-001` through `PR-NO-006` are all unmerged and based 25 commits behind current `origin/main`; their right-only histories are cumulative (1, 2, 3, 4, 5, and 7 commits). Do not merge those six stale stages independently. The active `No-Overnight 新版整合與 PostgreSQL UAT` task is already porting their reviewed semantics onto current main.
- `codex/pr-tm-012c1-runtime-readiness-20260826` is also unmerged on the old divergent lineage (4 current-main commits missing, 19 branch-only commits). Do not merge it wholesale. The active `Shadow fill.v3 相容性整合` task starts from current main and is adding regression-first v2/v3 compatibility.
- The three 2026-08-27 integration/evidence branches currently equal `origin/main@037197e`; their task worktrees contain ongoing uncommitted implementation and are not yet review candidates.
- The older `確認未合併到 main 的 branches` task is `active` only because it is waiting on an approval. It overlaps this PM reconciliation and must not be allowed to perform a competing merge workflow.
- The D-HEALTH-LATE-001 OPEN task remains active but has not armed launchd: it is blocked on safely changing the old provider-executing Codex automation to read-only verification. This is operational work in progress, not a merge candidate.
- PR #1 advanced `origin/main` from `037197e` to `33c9b3a`. The three active 2026-08-27 worktree tasks must incorporate the new docs-only main before their final review/merge gate and rerun their required validation; do not interrupt or discard current in-progress changes.
- PM follow-ups were delivered to the owning tasks: STE-5 post-merge cleanup, branch-audit deconfliction, current-main synchronization for No-Overnight/Shadow/slippage, and supervisor-only monitoring. No follow-up granted a new execution, broker, evidence, or merge authority.
- Worktree inspection confirms the three active 2026-08-27 tasks have isolated scoped changes: No-Overnight modifies/creates its domain, Journal, runtime guard, config, tests, and a forward-port map; Shadow modifies its composition/activation seams plus compatibility tests; slippage calibration adds only its planning state and analyzer module so far.
- The already merged tax/slippage worktree is clean. The detached kill-switch integration checkout, PR-NO-003 through PR-NO-006 worktrees, and old Trade Management runtime checkout are also clean, supporting their use as source evidence rather than active edit surfaces.
- After PR #1, the dirty primary checkout is now `ahead 19, behind 6`. It contains unrelated R6, FinMind, institutional, D-HEALTH, freshness, Trade Management, and PM changes/evidence. It remains categorically unsuitable for direct integration or a broad commit.
- `歷史台股回測準備度` is actively following the requested gate loop: A2 received `REQUEST CHANGES`, fixes/re-review are in progress, and source-only full audit plus Migration 018 remain correctly blocked until approval and coverage >= 0.95.
- `建立三年歷史資料` discovered no independent local minute evidence for the 9960 repair and then reported that a recursive search accidentally printed the `FUGLE_API_KEY` value from `.env` in tool output. Treat the credential as exposed: the task was instructed to stop all Fugle/key use and remain offline-only until owner rotation.
- The prior PR-TM-012C1 2026-08-27 automation completed one C0 and correctly failed closed on loopback/PostgreSQL/identity/input blockers; C1 did not start and `Production Shadow Gate=NOT_PASSED`. The old task requires no retry.
- The original Freshness/Portfolio conversation is idle at a real-environment authorization boundary (`SJ_SIMULATION=false`). Do not resume or infer authorization from this PM request; the broker/account freshness and Portfolio Phase 1 gates remain blocked.
- PR-NO-006 Phase 15 received an independent APPROVE, but only for the separately authorized supervised DISABLED capture. The existing capture is running once at `21fd771d` and is monitored read-only by its heartbeat; it must never be launched again.
- The completed PR-TM external-runner documentation commit `bd020b5` exists only on the divergent local `main`, not on `codex/pr-tm-012c1-runtime-readiness-20260826`. Its five docs depend on a broader old-lineage implementation series; standalone cherry-pick would document capabilities absent from current main.
- Directly merging the old PR-TM branch is also unsafe: its delta from current main spans 91 files and roughly 42k inserted lines across R5 replay, price coverage, C1 runtime, external runner, scripts, tests, and large artifacts. It has no single approved integration disposition. Classify the ended docs task as completed-but-not-mergeable, not as an omitted merge.
- The local `main` has 19 commits not in remote main, belonging to four distinct task families: R5 signal-ledger replay, Trade Management Shadow/C1/external runner, r3 price coverage, and R6 benchmark/amendment A1. They cannot be pushed or merged as one unit; each must be packaged from its owning task only after its own review/evidence gate.
- The active branch tasks acknowledged `origin/main@33c9b3a` as their final-review base. Shadow compatibility has 7 new compatibility tests and 17 legacy builder/observer tests passing; this is interim evidence, not approval.
- The superseded branch-audit task is now idle with no merge/push/delete action. STE-5 post-merge cleanup is active and is attempting its documented Linear update-script fallback because direct Linear writes are denied by its session policy.
- STE-5 post-merge cleanup completed without repository mutation. Git merge is independently verified, but its Linear workpad/status could not be updated because write calls require approval while that task's policy is `never`, and no script/credential fallback exists. STE-5 therefore remains `In Progress`, with STE-6 still shown as a blocker. Classify it as Git-complete / tracking-blocked, not fully closed.
- D-HEALTH-LATE-001 OPEN external-runner implementation completed in its original task without running the provider command. It configured one launchd attempt for 2026-08-28 08:55 and a one-shot 09:35 read-only Codex verification, with `runs=0`, no claim/result/session/evidence yet, and reported 27 focused tests plus compile/plist/diff checks passing. It now requires independent code review before the scheduled operational attempt is accepted.
- D-HEALTH independent review round 1 is `REQUEST CHANGES`: the installed plist executes an uncommitted runner and mutable imported modules from the broadly dirty shared primary checkout. The O_EXCL claim freezes only the command text, not the runner/CLI/cohort/calendar/source/venv identity. The reviewed bytes can therefore differ from the 2026-08-28 first-and-only attempt, a P1 provenance and safety gap.
- The 09:35 Codex automation is correctly read-only and fail-closed; a not-yet-complete result is reported rather than retried. It is not the blocker. The request-change packet requires unloading the mutable-main LaunchAgent while `runs=0`, moving the reviewed payload to a clean pinned checkout or equivalently strong loaded-bootstrap content identity, and adding a no-provider-on-source-drift adversarial test.
- The D-HEALTH owner accepted the review, unloaded the mutable LaunchAgent with `runs=0`, confirmed there are no claim/result/session/evidence artifacts, and created clean branch `codex/d-health-open-pinned-20260828` at `origin/main@33c9b3a`. Remediation and re-review are still in progress; no provider attempt is authorized before approval.
- `建立三年歷史資料` acknowledged the credential-safety gate and completed offline-only work: 13 focused tests passed, SQLite integrity is valid, and the case remains `QUARANTINED` with zero minute evidence/review/activation. It is correctly blocked as `BLOCKED_PENDING_CREDENTIAL_ROTATION`; do not resume until the owner rotates the key without pasting it into a task.
- `歷史台股回測準備度` completed its one-shot source-only audit with all `28,325,340` source bars read. The observed eligible coverage is `0.995893643087254413`, above the `0.95` threshold, with zero formal attempts. It is now independently rereading the canonical artifact before beginning Migration 018 and must not rerun the scan.
- Shadow fill.v3 compatibility is on `origin/main@33c9b3a` and the new-main full regression passed (`1507 passed, 43 skipped`); PostgreSQL remains explicitly not passed because the three DSN-dependent checks were skipped. Self-review fixed VWAP-evidence and Decimal-context defects; independent adversarial review remains pending.
- Slippage calibration's read-only dry run correctly failed closed: actual execution calibration is unqualified, model-proxy coverage has `0/42` required groups qualified, and no metric was manufactured from sessions lacking clock disposition. Full/static/diff validation remains in progress.
- Shadow's independent adversarial review returned `REQUEST_CHANGES` with P1=0 and P2=4: stored PostgreSQL fingerprints were not checked on read, a public builder accepted non-terminal partial prefixes, the observer used two Journal snapshots, and policy quantity was not bound to the authoritative aggregate. The task is fixing all four before re-review; commit and merge remain prohibited.
- Both Shadow and No-Overnight currently modify `trading/postgres_journal.py` and its unit tests. PM coordination requires Shadow to produce a minimal approved read-path patch, then No-Overnight to integrate it semantically rather than overwrite either side and rerun all Journal/PostgreSQL gates before declaring merge safety.
- Migration 018 passed the bounded second verification after the first disposable container exhausted its disk: full no-DSN `1735 passed, 88 skipped`, disposable PostgreSQL 17 `26 passed`, and production dry-run coverage remained `0.995893643087254413`. The migration was then applied transactionally to the Backtest DB and independently rechecked; active revision remains 2, family head and attempts remain 0, and no revision-3 matrix/preflight/audit registration was created.
- Shadow closed-loop re-review is `APPROVE` with P1=0/P2=0 and local commit `47a9303`. PM independently reviewed the exact 10-file diff, reran the actual focused suite (`26 passed`), compilation, and diff checks with no new P1/P2. Local PostgreSQL integration remains skipped; remote PostgreSQL CI is required before merge.
- The managed approval gate rejected pushing `codex/shadow-fill-v3-compat-20260827` to `origin` because it requires owner confirmation of the exact private-code payload and destination. Do not work around the rejection. The reviewed commit remains local and unmerged until that confirmation is supplied.
- The owner has now explicitly authorized pushing exactly `codex/shadow-fill-v3-compat-20260827@47a9303da0db26a17dd553488901af8caa423a55` to `https://github.com/f23934073/tw_intraday_trader.git`, creating a PR, waiting for all CI to pass, and merging it into `main`.
- Release preflight re-fetched `origin/main@33c9b3ab9d3b8300221e47b11685dfc24d7a5e51` and verified the isolated Shadow worktree is clean, the authorized branch is exactly `0 behind / 1 ahead`, the base is an ancestor of the authorized commit, and `git diff --check` passes.
- The exact authorized branch push succeeded and GitHub PR #3 was created at `https://github.com/f23934073/tw_intraday_trader/pull/3`. Merge remains blocked until every required CI check succeeds and GitHub reports a mergeable state.
- PR #3 CI returned Python 3.11 PASS and Python 3.12 PASS, but PostgreSQL Journal failed 3 of 25 tests. PostgreSQL normalizes `TIMESTAMPTZ` to the connection timezone, so reconstructing a record at UTC changed the ISO-offset bytes used by the immutable Journal fingerprint even though the instant was equal. This is a real P1 release blocker, not an infrastructure flake.
- The fix must preserve the original Journal fingerprint and historical records rather than globally changing the domain fingerprint algorithm or rewriting immutable rows. New PostgreSQL writes need a self-describing fingerprint envelope that preserves the original aware ISO timestamp; the reader must verify the stored instant and digest, with a bounded UTC/Taipei compatibility path for legacy raw digests.
- The reviewed remediation is commit `f6a38b1` on the same PR branch. It changes only `trading/postgres_journal.py` and `tests/test_shadow_postgres_journal_fingerprint.py`; focused validation is `31 passed, 3 skipped`, full isolated no-DSN regression is `1515 passed, 44 skipped`, and compilation/diff checks pass. It has been pushed to PR #3 for a fresh PostgreSQL CI run.
- GitHub shows `Steve_project` externally merged PR #3 at 2026-08-27 02:14:42Z as `023a082`, while its head was still `47a9303` and PostgreSQL Journal was failed. The later branch update `f6a38b1` was therefore not part of that merge. Remote `main@023a082` contains `47a9303`; the branch now has a clean two-file forward diff containing only the reviewed fix.
- PR #4 PostgreSQL CI then reduced the failures from 3 to 1: all replay/restart behavior passed, and the remaining failure was an outdated UAT regex expecting the later reducer's `order state integrity` error. The new reader correctly rejects the corruption earlier as `JournalConflictError: stored fingerprint conflicts...`.
- Commit `254317b` changes only the two corruption assertions in `tests/test_local_paper_postgres.py` to require that stronger earlier failure for both order-state and fill-v3 tampering. Local focused validation is `31 passed, 4 skipped`; production checks remain unchanged and a third remote PostgreSQL run is required.
- PR #4 third run passed Python 3.11, Python 3.12, and PostgreSQL Journal. `Steve_project` merged it at 2026-08-27T02:21:53Z as `7931d31e53657c4f28e684402589c2b20501c1d9`; final remote-main ancestry checks pass for `47a9303`, `f6a38b1`, `254317b`, and `7931d31`.
- The owning Codex task is `Shadow fill.v3 相容性整合` (`01a040b9-0761-7611-9dde-aa4f51a8d9af`). The dependent task is `No-Overnight 新版整合與 PostgreSQL UAT` (`01a040b9-0761-7611-9dde-aa263d9b7dca`), which was instructed to sync `7931d31`, preserve the PostgreSQL integrity semantics, and rerun its gates.
- The dirty primary checkout was not updated, reset, or used as a merge surface. It remains `ahead 19 / behind 11` with extensive unrelated user/task changes; remote-main verification was performed from the isolated Shadow worktree.
- Slippage calibration independent review returned `REQUEST_CHANGES` with 3 P1 and 3 P2 findings covering causal time windows, clock authority, instrument eligibility, per-symbol pair coverage, fill lineage, and atomic sealing. The owner is fixing all six and will reseal artifacts before round-two review.
- D-HEALTH remediation round one returned clean branch `codex/d-health-open-pinned-20260828` at `0bb2ee2`, with a loaded non-login-shell boundary, `runs=0`, provider attempts 0, and 33 focused tests passing. PM round-two review nevertheless remains `REQUEST_CHANGES`: the dedicated worktree has no `.env`, and every Shioaji credential alias in the user launchd environment is unset, so the one-shot claim would be consumed before a credential-missing failure.
- D-HEALTH must add a secret-safe external credential boundary after source/runtime verification, record only path/owner/mode/key-presence metadata, filter child environment keys, and ensure missing/insecure credential or setup exceptions produce auditable NOT_RUN with provider callable zero. Secret values must never enter Git, plist, manifest, artifacts, logs, or messages.
- The R6 A2/Migration 018 packaging task is active on clean branch `codex/r6-a2-migration018-20260827`. Its scoped transplant excludes R5, Shadow, price coverage, D-HEALTH, Local Paper, and broker paths; focused `94 passed, 28 skipped` and full no-DSN `1588 passed, 70 skipped`, with disposable PostgreSQL validation still in progress.
- Preserve existing task-specific gates. In particular, evidence capture, Production Shadow, Local Paper, broker-account, and real-money authority remain distinct; a completed implementation or approved review never grants a later operational stage.
- Resume incomplete work in its owning Codex task whenever possible so its prior approvals, immutable artifact identities, and scope constraints remain attached to the work.
- Do not merge broad dirty-worktree content merely because a related task ended. The merge unit must be an reviewed branch/PR with explicit commit identity and passing required checks.
- After reconciliation, start only work whose dependencies and authorization are already satisfied; otherwise leave it blocked with a concrete next gate.
- Owner scope correction: this PM task must not overlap `評估實盤交易就緒差距` (`01a03d58-1eda-7a12-8404-b8b308bc6255`). That referenced task owns the supervision of `Shadow fill.v3 相容性整合`, `No-Overnight 新版整合與 PostgreSQL UAT`, and `Local Paper 滑價校準證據工具`; exclude that supervisor and those child workstreams from this PM inventory, messaging, review, and merge decisions.
- Fresh fetch confirms `origin/main=7931d31e53657c4f28e684402589c2b20501c1d9` and there are currently no remote-tracking branches whose commits are outside `origin/main`.
- Local branches still outside `origin/main` are: `codex/r6-a2-migration018-20260827@ce8e9b6`, `codex/d-health-open-pinned-20260828@8d3747f`, dirty divergent local `main@a6e096a`, six old No-Overnight stages, and the old `codex/pr-tm-012c1-runtime-readiness-20260826@15a852c` lineage.
- The six No-Overnight stages and current No-Overnight integration worktree are excluded by the owner correction. Treat the old PR-TM Shadow lineage as overlap-sensitive/excluded unless the user later assigns it explicitly outside the readiness task. The two actionable non-overlap candidate branches are therefore R6 A2/Migration 018 and D-HEALTH OPEN pinned runtime; their task/review states still require live verification.
- Live task polling confirms `歷史台股回測準備度` remains active. Its A2/Migration 018 branch has all 32 focused PostgreSQL cases passing, but four broader Journal fingerprint failures appeared in the newest-main disposable PostgreSQL run; the owning task is reproducing the minimum case on detached `origin/main` to classify baseline versus branch regression. It is not review-ready or merge-ready.
- `codex/d-health-open-pinned-20260828@8d3747f` is clean and `6 ahead / 5 behind` current `origin/main`. It has no open PR and must not be merged until its owning task and latest review disposition are mapped live, then the branch is reconciled with current main and revalidated.
- Scope recheck against the full referenced conversation shows both candidates are also overlap: the readiness task explicitly includes R6/historical readiness in its staged work and says it continues supervising existing Freshness evidence, which owns D-HEALTH. Exclude both R6 and D-HEALTH from this PM. After that correction there is no actionable unmerged branch, open PR, or active Codex task outside the referenced readiness ownership tree.
- The only other unmerged local ref is dirty divergent `main`, which mixes multiple task families and is not a reviewable or mergeable unit. Every other unmerged named branch belongs to the excluded No-Overnight or Trade Management Shadow lineages.
- The prior inventory mistake was treating only `active` tasks as unfinished. Codex task status is process state, not completion disposition: `idle` and `notLoaded` tasks must be read before they can be classified as complete, blocked, stalled, or superseded.
- The first 50-visible-task scan contains several unfinished logical lines despite idle process state. `建立三年歷史資料` has a source-repair candidate at `PENDING_REVIEW`, with zero activation, and needs an independent reviewer disposition before any activation. `確認三大法人策略資料` has committed r3 activation metadata but has not executed the 2,781-symbol Shioaji Raw Coverage Scan; that provider action retains its own explicit authorization gate.
- The many STE-5 conversation boxes are repeated follow-up attempts for one Linear issue, not separate implementation branches. Its PR is merged, but the latest conversation remains externally blocked because Linear state/workpad writes were denied; the issue is still `In Progress` and must not be falsely marked complete.
- `實作 Local Paper Kill Switch` and `Tax/Slippage` not-loaded task conversations are logically complete: PR #2 merged as `037197e1` and main CI passed, so their process status does not represent unfinished implementation.
- `確認未合併到 main 的 branches` is a completed stale snapshot and is superseded by this PM reconciliation; it should not be resumed as a second branch manager.
- The latest R6 owner task is now idle because its scoped package is complete, not because it is abandoned: `codex/r6-a2-migration018-20260827@ed477898` is a clean one-commit branch directly on `origin/main@7931d31`, with independent adversarial `APPROVED`, no-DSN `1603 passed, 71 skipped`, disposable PostgreSQL 17 full `1674 passed`, and focused PostgreSQL `32 passed`. It is locally review-ready but unpushed; R6 G3 activation remains a later separate gate.
- Visible UI inventory contains 52 entries: 46 Codex tasks, including 21 tw_intraday_trader conversations and 25 STE-5 follow-up conversations. The 25 STE entries collapse to one logical Linear issue; task-box count is therefore not equal to independent unfinished work count.
- Within the current repository, the main non-child continuations are R6 package release review, 9960 source-repair review, and r3 scan authorization. The direct readiness child tree and Freshness/D-HEALTH/No-Overnight/Shadow work remain excluded from this PM.
- Excluded-task boundary update only: No-Overnight synced `main@7931d31`; disposable PostgreSQL reached `32 passed / 1 failed`, where the sole failure exposes `local_paper_fill.v4` compatibility against a v3-bound monetary reader. The owning readiness task is handling that overlap; this PM will not message, review, or merge it.
- R6 PM review froze exact payload `ed477898` on base `7931d31`: 38 files, 18,442 insertions, one commit, clean worktree, `0 behind / 1 ahead`, and whitespace-clean. Its prior packaging approval expressly authorizes only a mergeable local package, not push, merge, audit registration, revision-3 activation, or G3 execution.
- The 9960 candidate directory is present with manifest, canonical bars, validation, and SHA sidecar. Initial top-level `jq` field selection returned null for nested identity fields, so review must inspect the real schema keys rather than infer missing data; no candidate or durable state was changed.
- The 9960 candidate manifest is structurally populated: `artifact_id=fugle-source-repair-candidate-9960-20260320-v1`, one bar, raw SHA `a02cc385...f2b3a6f`, canonical SHA `ebd88a74...2eaa51f9`, and `status=ACCEPTED_FOR_PROPOSAL`. Validation binds one flat-price official transaction, 1 lot/1,000 shares, TWD 22,900, source label conversion to `10:56+08:00`, and all daily reconciliation checks true while explicitly retaining `source_turnover_twd=null`.
- Source-repair transition code keeps review and activation separate. `review()` accepts only minute evidence matching the current candidate and records reviewer/rationale/digests; `activate()` remains a distinct later transition requiring the exact approval review. This PM review must not call activation.
- R6 static scan found no TODO/FIXME, shell execution, `eval`, or `exec` in production changes. Broad exception handling is limited to cleanup/CLI boundaries and will be inspected with the high-risk migration/preflight paths; SQL uses repository-local statements, with `SELECT *` confined to known internal benchmark tables rather than user input.
- Independent PM focused rerun on exact R6 commit passed `94 passed, 28 skipped` in 8.94 seconds, matching the packaging review's focused no-DSN result. Migration 018 is schema-only, locks each family, rejects any revision/head/release/attempt/preflight drift, widens constraints additively to revision 3, and does not insert or activate revision-3 state.
- A2 tests explicitly cover reserve-after-deadline rejection, source-audit/preflight projection equivalence, and additive preservation of revision-2 protocol. The tracked canonical audit test binds its SHA sidecar, 28,325,340 bars, 132,234 observed sessions, 131,691 eligible sessions, 0.995893643087254413 ratio, head 0, and attempts 0.
- The source-repair database is `data/finmind_sponsor/history.sqlite3`. Phase 80 requires review of evidence `finmind-repair-evidence-ac310a47f4e804507a79`; current planning evidence says state `PENDING_REVIEW`, audit 1/1 with zero issues, original partition `EMPTY`, and zero active repair bars. The next operation can be a named review only; activation remains separate.
- Read-only SQLite confirms the live case and minute evidence digests/timestamps exactly match the candidate, with zero reviews and zero activations. The query's final active-bar count used a guessed table name and failed after those successful reads; this is a PM inspection error, not evidence corruption, and no database state changed.
- The 9960 implementation's `START_PLUS_ONE_MINUTE_EXCEPT_13_30_V1` contract is directly regression-tested: ordinary minute labels advance by one minute, the `13:30` closing-auction label does not, and missing turnover is rejected unless the official reference proves exactly one flat-price transaction whose OHLC, volume, and implied amount reconcile.
- The exact R6 diff remains whitespace-clean and its isolated worktree remains clean after PM test replay.
- R6 PM disposition is `APPROVE` for the exact local package `codex/r6-a2-migration018-20260827@ed477898e707435036936a91afe07f3b846f4758`. There are no P1/P2 findings after focused replay, production compilation, CLI smoke checks, diff validation, and clean-worktree verification. This does not authorize push, PR, merge, audit registration, revision-3 activation, or G3.
- 9960 PM review is durably `APPROVE` as `finmind-repair-review-f28f1fdb50e78806a1df`, reviewer `Codex PM independent review`. Post-review state is `APPROVED` with `current_activation_id=null`, `active_bar_count=0`, audit 1/1 and zero issues, and SQLite integrity `ok`; activation remains a separate owner gate.
- Fugle's current Historical Candles contract says whole-lot equity minute volume is measured in lots and `turnover` applies only to daily/weekly/monthly candles. The sealed one-lot 9960 minute response therefore correctly lacks turnover; the narrow one-transaction flat-price derivation is consistent with the provider contract and remains guarded by negative regressions.
- Original conversation `歷史台股回測準備度` (`01a02d3a-5a41-7580-a827-a8ce24d97f1e`) completed the PM handoff as `LOCAL RELEASE-READY`, reconfirming exact commit/base/clean state and returning one precise remote-release authorization sentence without changing the package.
- Original conversation `建立三年歷史資料` (`01a02323-6a92-7632-9ba6-88debb96c3ab`) completed the PM handoff as `APPROVED_AWAITING_OWNER_ACTIVATION`, reconfirming the review lineage, zero activation/active bars, original `EMPTY` partition, and the precise named-actor activation sentence without provider access or activation.
- Actual schema stores gzip-compressed raw and canonical evidence in `finmind_source_repair_evidence`; there is no separate bar table. After deterministic decompression, DB raw bytes hash exactly to `a02cc385...f2b3a6f` and canonical bytes hash exactly to `ebd88a74...2eaa51f9`. Focused source-repair tests independently pass `15 passed`.
- The original FinMind partition remains `EMPTY`, bar_count 0, with unchanged raw/canonical digests; `PRAGMA quick_check=ok`. The raw Fugle capture file itself hashes to the stored raw digest, and metadata records exactly one successful credentialed request with no credential value persisted.

## 2026-08-19 — Freshness Calibration Evidence

### Requirements

- The approved baseline is immutable: P0-1 through P0-14, FeePolicyV1, and RoundingPolicyV1 remain `FROZEN`; `FreshnessPolicyV1` is the sole `BLOCKING_EVIDENCE`.
- Scope is evidence only. Do not start Portfolio Phase 1 or add Portfolio domain contracts.
- Calibrate eight distinct values: UI/Risk Tick and BidAsk freshness, plus broker positions, orders, accounting, and buying-power evidence freshness.
- Quote latency and broker/account freshness are separate datasets and analyses. Neither may be inferred from the other.
- Thresholds remain unset unless immutable captured evidence and data-quality review support them.

## 2026-08-24 — Quote scheduler hardening

- The installed quote scheduler previously accepted only an exact configured
  minute. The actual 10:01 scheduled-run record therefore proved that a one
  minute launch delay was classified `NO_CAPTURE_OFF_SCHEDULE`, despite being
  within the intended continuous collection period.
- Each configured quote window now accepts a single start up to five minutes
  late, records both `scheduled_for` and `launch_delay_seconds`, and otherwise
  remains fail-closed. The close window can therefore start as late as 13:20
  and still observe the required 13:30 boundary.
- The launchd command now uses absolute interpreter/script paths. The runner
  changes to its own repository root before reading relative manifests or
  writing artifacts, so it no longer depends on launchd inheriting a usable
  working directory.
- The user-level job was reinstalled and safely invoked at 17:22 outside every
  capture window. It exited 0 with `NO_CAPTURE_OFF_SCHEDULE`; no new stderr
  bytes were emitted after removing the invalid `WorkingDirectory` setting.
- This improves collection reliability only. It does not repair partial
  callback coverage, set a freshness threshold, or unblock Portfolio Phase 1.

## 2026-08-25 — Frozen close-window quote evidence

- A 15-minute Tick/BidAsk-only close artifact was captured from 13:01 to
  13:16 Asia/Taipei against the unchanged frozen `2886:high`, `6863:mid`,
  `1530:low` cohort. Its SHA-256 is
  `79e883fe1a1e3027caa085d7955d9ee0d21aad0533deff98975ac8ee28228401`.
- Digest/schema, paired acknowledgement (6/6), per-row `CONNECTED/ACTIVE`
  lifecycle, callback errors (0), and callback monotonicity regressions (0)
  passed. `1530/TICK` had no callback, so coverage is 5/6 and the formal
  result remains `REVIEW_REQUIRED_PARTIAL_COVERAGE`.
- 962/1,037 records retain source-clock skew. The artifact ends before 13:30,
  so it is early-close cadence evidence only. It does not select any quote
  threshold, establish source-clock comparability, or represent broker/account
  freshness.
- The close review is
  `research/freshness_calibration/reviews/2026-08-25_1301_close_review.md`.
  All eight thresholds remain unset and Portfolio Phase 1 remains blocked.

## 2026-08-26 — Frozen close-window quote evidence

- A 15-minute Tick/BidAsk-only close artifact was captured from 13:02 to
  13:17 Asia/Taipei against the unchanged frozen `2886:high`, `6863:mid`,
  `1530:low` cohort. Its SHA-256 is
  `b1d6714c697a86bc016a203c290e9d1a9cdd4cfbcce63b8ab4076bccf41e8ef1`.
- Digest/schema, paired acknowledgement (6/6), per-row `CONNECTED/ACTIVE`
  lifecycle, callback errors (0), and callback monotonicity regressions (0)
  passed. `1530/TICK` had no callback, so coverage is 5/6 and the formal
  result remains `REVIEW_REQUIRED_PARTIAL_COVERAGE`.
- 1,649/1,695 records retain source-clock skew. The artifact ends before
  13:30, so it is early-close cadence evidence only. It does not select any
  quote threshold, establish source-clock comparability, or represent
  broker/account freshness.
- The close review is
  `research/freshness_calibration/reviews/2026-08-26_1302_close_review.md`.
  All eight thresholds remain unset and Portfolio Phase 1 remains blocked.

## 2026-08-26 — Post-session cross-evidence verification

- Verification resumed after the 13:17 close artifact. The workspace contains
  scheduled quote artifacts and separately redacted broker/account artifacts
  for 2026-08-25 and 2026-08-26. Their existence alone is not qualification;
  schema, integrity, endpoint capability, lifecycle, and timing evidence must
  be checked separately before any review conclusion.
- The next audit also verifies that the installed quote close trigger observes
  the required 13:30 session boundary. No threshold, Portfolio code, or
  broker/order mutation is authorized by this audit.
- Offline inspection of ten redacted broker/account artifacts (five on each
  of 2026-08-25 and 2026-08-26) passed schema/digest and read-only guardrail
  validation, but none is a successful broker freshness observation:
  `POSITIONS=AUTH_DENIED(TokenError)`, `ACCOUNTING=SOURCE_ERROR`
  (`ShioajiConnectionError`), and `BUYING_POWER=UNSUPPORTED_FOR_EVIDENCE_KIND`
  in all ten. `ORDERS` is correctly retained as the existing excluded
  `update_status`/trade-callback gap. These are constrained evidence gaps, not
  candidate thresholds.
- Quote artifacts across the same dates have paired acknowledgement and zero
  callback errors/monotonicity failures. Coverage varies from 4/6 to 6/6,
  with the low-tier Tick absence being a market-activity result rather than a
  collector failure. The ordinary scheduler is configured for 13:15 plus
  1,200 seconds, which reaches 13:35 and can observe the required boundary;
  the 13:02 one-shot capture was deliberately shorter and does not test it.
- The full review is
  `research/freshness_calibration/reviews/2026-08-26_post_session_cross_evidence_review.md`.
  It retains every threshold as unset and identifies the broker/account
  simulation source access failure as the primary remaining collection gap.

## 2026-08-27 — Frozen close-window quote evidence

- `quote_20260827T130142+0800.json` passed integrity, 6/6 acknowledgement,
  lifecycle, callback-error, monotonicity, and clock-skew checks. Coverage is
  5/6 because `1530/TICK` is absent; no threshold is selected.

## 2026-08-22 — Frozen close-window execution

- The active heartbeat authorizes one bounded quote-only close capture for the
  pre-frozen cohort `2886:high`, `6863:mid`, `1530:low`. It explicitly excludes
  broker/account APIs, order APIs, CA, trade callbacks, all execution, and
  Portfolio Phase 1.
- This close observation must remain a separate immutable artifact and review.
  It may improve session-boundary evidence but cannot itself freeze a threshold
  or change `FreshnessPolicyV1=BLOCKING_EVIDENCE`.
- The host time at the requested window was `2026-08-22 13:01 +08:00 Sat`, a
  reviewed non-trading day. Five read-only NTP samples selected successfully
  (offsets approximately +0.405 to +0.407 ms), but that provenance cannot
  override the closed-date gate. The run is recorded as `NO_CAPTURE`; no SDK
  login, quote subscription, broker/account API, order API, CA, or Portfolio
  work occurred.

## 2026-08-23 — Frozen close-window execution

- The second heartbeat again arrived on a reviewed non-trading day: host time
  was `2026-08-23 13:00 +08:00 Sun`. Five read-only NTP samples selected a
  valid source (offsets approximately +0.595 to +0.601 ms), but the Sunday
  calendar gate still requires `NO_CAPTURE`.
- No Shioaji import/login, quote subscription, account/order/CA/trade-callback
  API, execution, or Portfolio work occurred. No artifact-quality check is
  implicitly passed when no immutable quote artifact exists.

## 2026-08-24 — Frozen close-window execution

- A one-time trading-day close capture is authorized for only the frozen
  `2886:high`, `6863:mid`, `1530:low` Tick/BidAsk cohort. It remains evidence
  collection only: broker/account, orders, CA, trade callbacks, execution, and
  Portfolio Phase 1 are excluded, and every threshold remains unset pending
  artifact integrity and review.
- Host time at preflight was `2026-08-24 17:00 +08:00 Mon`, not the heartbeat's
  13:02 close window. Five read-only NTP samples selected successfully
  (approximately +0.037 ms), but the after-close host time requires
  `NO_CAPTURE_OFF_SESSION`. No provider path was entered and no evidence
  artifact-quality check is implicitly passed.

## 2026-08-22 — Broker/account read-only evidence authorization

- The owner has now explicitly authorized a strictly read-only broker/account
  evidence campaign and confirms that local Shioaji credentials are present.
  This changes only the source-access gate; it does not unblock Portfolio
  Phase 1 or permit a broker-order integration.
- The capture must record one distinct, redacted observation per `POSITIONS`,
  `ORDERS`, `ACCOUNTING`, and `BUYING_POWER` evidence kind. Required metadata
  remains request start, response receipt, provider `source_as_of_at` when
  actually supplied, local projection update, outcome, and a sanitized error
  class. It must not persist credentials, account identifiers, individual
  positions, balances, PnL, or order details.
- The local code search confirms the quote path is deliberately
  `subscribe_trade=False` and there is no dedicated broker-account evidence
  adapter yet. A capture must therefore be built as a separate calibration
  artifact, not by reaching through the existing quote provider or changing a
  product route.
- Fresh broker-order state normally requires a provider-side order refresh;
  that action-like call is excluded from this authorization. A local cached
  order list is not acceptable evidence for broker order freshness, so the
  initial campaign must record orders as an explicit constrained gap rather
  than fabricate an observation or infer a threshold.
- Local SDK inspection identifies Shioaji `1.7.2` and verifies the safe call
  signatures needed for the capture: `login(..., subscribe_trade=False)`,
  `list_accounts()`, `list_positions(...)`, `list_profit_loss(...)`, and
  `account_balance(...)`. Each read method exposes an optional callback, which
  the collector must leave unset; the collector will time the synchronous
  response path only. `update_status(...)` is intentionally excluded because
  it is an action-like order refresh, even though it has no order-placement
  signature.
- Existing configuration uses `SJ_SIMULATION=true` by default but permits a
  real-data source through `SJ_SIMULATION=false`. The new artifact must report
  that runtime environment as a non-sensitive metadata value and cannot claim
  simulation merely because the quote path did so in another run.
- A separate `broker_account_freshness_v1` artifact implementation now exists
  with exclusive creation and SHA-256 inspection. It records only endpoint
  shape/count, timing, explicit-as-of availability, guarded outcome, and
  capability disposition. Focused collector/quote/calendar tests passed
  (`22 passed in 0.09s`) without an SDK login or account API call.
- The broker/account campaign now has five reviewed daily windows (09:35,
  10:30, 11:30, 12:30, 13:20 Asia/Taipei) behind a calendar/time gate that
  runs before dotenv, SDK import, or provider construction. The Saturday
  schedule smoke produced a no-capture record with `provider_called=false`;
  all 24 focused collector/scheduler/quote/calendar tests passed.
- The corresponding launchd service is installed as
  `com.stevehuang.tw-intraday-trader.broker-account-freshness` and was verified
  to contain exactly those five calendar triggers. It is a separate process
  from the quote collector; `runs=0` immediately after installation confirms
  no broker/account observation has yet been collected.
- Revalidated the source boundary against current official Shioaji docs:
  `list_positions` and `list_profit_loss` are synchronous read APIs when no
  callback is supplied, while `account_balance` is a stock settlement-account
  balance endpoint with provider `date` described as query time. The latter is
  intentionally not promoted to buying-power authority. The official order
  docs require `update_status` before a cached `Trade` status is fresh, so the
  current `ORDERS` constrained gap is a source-supported consequence of the
  no-update-status/no-callback authorization, not a missing implementation.

### Initial decisions

| Decision | Rationale |
|----------|-----------|
| Use a standalone data-only calibration harness | Preserve the frozen Portfolio domain while making raw timing evidence inspectable and reproducible. |
| Keep broker/account calibration isolated from quote capture | The existing runtime is market-data-only, and the approved contract requires separate broker/account SLA evidence. |

### Discovery findings

- `market_data.models.RealtimeQuoteUpdate` already carries `exchange_timestamp` and `received_at`; the Shioaji provider emits normalized Tick and BidAsk updates with both timestamps.
- `simulation.service` keeps separate trade and book receive times, while existing quote execution uses a book-received timestamp. The calibration artifact should capture the raw callback receipt and a separate store-updated timestamp without changing the frozen Portfolio model.
- The repository already contains a data-only `market_data.shioaji_quote_capture` capture path, digest-validated capture artifacts, and `market_data.quote_qualification`; those are designed for Quote-versus-Tick/BidAsk parity, not for freezing FreshnessPolicyV1 thresholds.
- The current search found market-data streaming with `subscribe_trade=False`, but no implemented broker account read adapter or accounting polling capture path. Broker/account threshold evidence therefore requires a separately authorized read-only source or must remain unavailable; it cannot be inferred from the quote captures.
- The two existing parity artifacts cannot establish freshness thresholds: `8039` recorded zero callbacks in 20 seconds; `2330` recorded callbacks only for about 20 seconds. Neither has `store_updated_at`, connection-state transitions, liquidity/session labels, or independent broker/account observations. They remain callback-path evidence only.
- The `2330` artifact contains callback receipts earlier than the supplied market event time for some book updates. Calibration must preserve and count such clock-skew observations; it must never clip them into valid non-negative latency.
- Offline artifact validation on 2026-08-19 confirmed the insufficiency: the
  20.772745-second `8039` capture has zero callbacks/observations; the
  20.714851-second `2330` capture has 116 retained observations, 96 with
  negative event-to-receipt latency. These samples are callback-path evidence,
  not threshold-quality data.
- Added `market_data.freshness_calibration` and
  `scripts/capture_quote_freshness.py`: a Tick/BidAsk-only, bounded capture
  writes exclusive-create JSON evidence with market/callback/store timestamps,
  monotonic timing, reviewer-supplied cohort labels, lifecycle state, SHA-256
  inspection, and no threshold-selection code. The declared store boundary is
  only the calibration buffer, not a future Portfolio projection.
- A rendered technical evidence report has been validated with a partial
  snapshot. It records all eight values as unset, preserves the separate
  broker/account evidence gap, and prohibits a quote-to-account SLA inference.

### Preparation scope (in progress)

- Cohort labels must be selected and frozen before a capture starts, but no
  label will be assigned from reputation or the two insufficient samples. The
  capture records the reviewer-supplied label as provenance rather than treating
  it as a market-data fact.
- Non-sensitive preflight may verify local runtime/CLI, host timezone, artifact
  creation semantics, and credential *presence* only. It must not emit secret
  values, call order/account endpoints, or use an empty after-hours capture as
  calibration evidence.
- Local preflight on 2026-08-19 passed without reading secret values: the
  optional Shioaji SDK is installed, both required credential categories are
  configured, and the host UTC offset is `+08:00`, matching the explicit
  `Asia/Taipei` capture timezone. This verifies readiness, not clock accuracy
  or market-data quality.
- Current provider code confirms Tick/BidAsk-only streaming with
  `subscribe_trade=False` and a 100-symbol paired-subscription cap. The
  repository's separate momentum stream also registers SDK lifecycle events;
  the calibration collector should preserve those lifecycle transitions rather
  than fabricate connection health from callback arrival alone.
- The reusable lifecycle model distinguishes disconnect, reconnecting,
  reconnected, subscription acknowledgements, and subscription failures. The
  calibration artifact needs raw SDK lifecycle provenance plus its conservative
  mapped connection/subscription state so an empty callback interval is not
  misclassified as market-data staleness.
- Existing tests provide concrete lifecycle evidence: SDK event `(500, 12)` is
  treated as reconnecting, `(200, 13)` as reconnected, and paired Tick/BidAsk
  acknowledgements use event code `16`. The calibration collector can record
  these state changes without adding a Portfolio concern.
- The capture currently marks subscriptions active immediately after request;
  this is not valid acknowledgement evidence. The narrow correction is to keep
  `PENDING` until both `TIC` and `QUO` acknowledgements for a configured symbol
  are received, then persist the raw lifecycle inputs alongside the mapped
  state.
- Preparation artifacts are now ready: the cohort manifest template freezes
  reviewer-supplied labels before collection; the preflight/review checklist
  records required integrity, clock, lifecycle, and segmentation checks; and
  the broker/account intake defines read-only authorization and timing metadata
  without creating an adapter.

### Live discovery capture (2026-08-20 09:05 Asia/Taipei)

- A 120-second data-only capture for `2330` was deliberately labelled
  `discovery` / `continuous_discovery`; it is not evidence that the symbol
  belongs to any approved liquidity tier. The immutable artifact is
  `research/captures/freshness_quote/quote_20260820T090534+0800.json`
  (SHA-256 `17dd2ead6a7ad17b2c389f4e263104c756096c5dd4131c45a7a6143f438b5e97`,
  263,563 bytes, schema `freshness_calibration_quote_v1`).
- Digest inspection passed. It holds 494 observations: 474 BidAsk and 20 Tick,
  with no missing stream kind, no missing market event timestamp, no callback
  monotonic regression, and no captured callback error.
- Lifecycle provenance confirms a successful paired acknowledgement: `TIC` and
  `QUO` were both acknowledged for `TSE/2330`, after which all observations
  record `CONNECTED` / `ACTIVE`. Cleanup then recorded an explicit
  `DISCONNECTED` / `INACTIVE` transition.
- The source event timestamp cannot yet be used as a transport-latency clock:
  353 of 474 BidAsk and all 20 Tick observations have a negative
  event-to-callback value. Raw values are retained for audit; they are not
  clamped, discarded, or turned into a freshness threshold.
- A post-capture, read-only NTP sample against `time.apple.com` selected an
  offset of `+58.825 ms +/- 53.094 ms`. It establishes limited host-clock
  provenance without changing the system clock. It does not establish the
  exchange/provider event-clock offset, so it cannot correct the negative raw
  values or qualify event-to-callback latency as an SLA metric.
- The capture establishes that the callback-to-store measurement seam works
  during the continuous session. It remains insufficient for every threshold:
  it has one discovery-labelled symbol, one session window, no independently
  verified clock relation, and no broker/account read evidence. Consequently
  `FreshnessPolicyV1` remains `BLOCKING_EVIDENCE` and no candidate is emitted.

### Qualified cohort selection (in progress)

- The user authorized continuation during the regular session. This permits
  collection and evidence provenance work only; it does not authorize Portfolio
  Phase 1, broker account reads, or execution APIs.
- The official TWSE historical-data page documents a daily individual-security
  trading value/volume dataset available from 2010-01-04. The selection path is
  therefore to snapshot the prior completed-session dataset, record its source
  date/digest and a predeclared percentile rule, then freeze the resulting
  high/mid/low symbols in the cohort manifest before any qualified capture.
- This replaces reputation-based labels with auditable completed-session
  evidence. It must remain separate from current-session callback counts so
  selection cannot be altered after viewing capture outcomes.
- Downloaded the official TWSE `MI_INDEX` response for 2026-08-19 into an
  ephemeral inspection file. It reports `stat=OK`, contains a 1,377-row
  `Daily Quotes(All(no Warrant & CBBC & OCBBC))` table with explicit
  `Security Code`, `Trade Volume`, `Transaction`, and `Trade Value` fields,
  and has SHA-256
  `6e4105775abb4a5517706a47ee803e42f0f6063a9aea5e894a9c089a158e0c19`.
- The first generic `data` lookup was empty because this response is a
  multi-table schema rather than a single-table schema. The selection parser
  will target the named Daily Quotes table and validate its headers before
  calculating ranks; it will not silently use an index or market-summary table.
- The verified selection universe is now fixed as: four-digit numeric security
  codes whose first digit is `1`–`9`, with positive 2026-08-19 `Trade Value`.
  It yields 1,086 eligible rows and excludes 291 other rows from the 1,377-row
  Daily Quotes table. The completed-session `Trade Value` nearest-rank anchors
  are p10 `1530` (NT$842,314), p50 `6863` (NT$18,430,437), and p90 `2886`
  (NT$1,184,984,848).
- These anchors are selected solely from the downloaded completed-session
  snapshot and before any qualified capture outcome is examined. They will be
  persisted as `low`, `mid`, and `high` respectively in the cohort manifest;
  this is an observation-cohort classification, not a statement about a stale
  threshold, tradeability, or Portfolio risk policy.
- Frozen `cohort_manifest_2026-08-20_twse_2026-08-19.json` at
  2026-08-20T09:14:51+08:00 with `2886:high`, `6863:mid`, and `1530:low`;
  its source digest matched the inspected TWSE snapshot. The operational
  collection windows are opening 09:00–09:30, continuous 09:30–13:00, and
  close 13:00–13:30 Asia/Taipei. They segment evidence only, not a stale
  threshold or exchange-rule claim.
- A read-only NTP preflight immediately before the first qualified capture
  selected `+54.431 ms +/- 49.857 ms` from `time.apple.com`. It is host-clock
  provenance only and does not make source event timestamps a latency SLA.
- The frozen 10-minute opening capture started at 09:16:16 +08:00 and wrote
  `quote_20260820T091616+0800.json` with 1,048 observations and all six
  `symbol × {Tick,BidAsk}` groups present. Initial counts are: high 2886
  (816 BidAsk, 180 Tick), mid 6863 (24 BidAsk, 2 Tick), and low 1530
  (23 BidAsk, 3 Tick). Integrity/lifecycle inspection remains pending.
- Integrity inspection passed (SHA-256
  `816e35617c3efa3ff555f91ae24cb4ba242986ccbc8bedac100cd875708ac572`,
  539,087 bytes) and each symbol received `TIC` plus `QUO`. However every
  persisted observation is `CONNECTED/PENDING`, so this artifact is **not
  qualified evidence** under the existing fail-closed rule.
- Root cause is contained in the calibration collector: after one symbol became
  `ACTIVE`, the aggregate state was still `PENDING` while other symbols awaited
  acknowledgement; the lifecycle transition helper then broadcast that aggregate
  `PENDING` back to every per-symbol state, erasing the completed acknowledgement.
  This is an instrumentation bug, not a market-data failure. Preserve the raw
  artifact, repair the state propagation with a multi-symbol regression test,
  then recapture using the unchanged frozen manifest.
- The isolated repair leaves global lifecycle transitions intact but prevents an
  aggregate `PENDING` transition from rewriting per-symbol states. Reconnecting
  now explicitly resets both acknowledgement parts and per-symbol states to
  `UNKNOWN`. The multi-symbol regression passes: a fully acknowledged symbol
  remains `ACTIVE` while another symbol is still `PENDING`, then both become
  `ACTIVE` after their own paired acknowledgement.
- The 70-second opening recapture
  `quote_20260820T092834+0800.json` passed schema/digest inspection
  (SHA-256 `65edf0a391207fa69953e9440fb1e14a3fc4baa306a61f70764063b8241c110b`,
  63,606 bytes). Its three paired acknowledgements are present and every
  observation is `CONNECTED/ACTIVE`: high 2886 has 95 BidAsk plus 20 Tick,
  and mid 6863 has 2 BidAsk. It is valid partial evidence, but **not complete
  opening coverage** because mid Tick and both low 1530 stream groups had no
  callback in the 70-second interval. Missing market activity is a coverage
  result, never synthetic stale evidence.
- The 15-minute continuous capture
  `quote_20260820T093046+0800.json` is the first complete qualified cohort
  artifact: schema/digest passed (SHA-256
  `7451e75b3a3fe26e750844e9e902a7aeb5e62ffe84d4276bacc7e4f24ddccad1`,
  779,582 bytes), every configured `symbol × {Tick,BidAsk}` group has a
  callback, all 1,513 rows are `CONNECTED/ACTIVE`, all three symbols have
  `TIC` plus `QUO`, and no callback error or monotonic regression occurred.
- Its observed cadence validates a key contract premise without selecting a
  threshold: high 2886 has 1,203 BidAsk / 251 Tick updates (maximum gap about
  8.025 seconds); mid 6863 has 46 / 4 (about 166.857 / 124.389 seconds); low
  1530 has 8 / 1 (about 164.827 seconds / no Tick gap). Thus a quiet Tick can
  coexist with an active, paired-acknowledged subscription and must not alone
  be treated as an executable-data failure.
- Source-clock skew remains material in every cohort/stream, and the measured
  callback-to-store timing is only the calibration in-memory buffer. One date,
  continuous window coverage alone, uncalibrated source event time, and the
  independent broker/account evidence gap keep all eight thresholds unset.
- A one-time task heartbeat is active for the frozen 13:00–13:30 close window.
  Its work scope is limited to the same immutable quote cohort and artifact
  review; scheduling does not authorize broker/account reads, change the cohort,
  select a threshold, or begin Portfolio Phase 1.
- Cross-artifact quality profiling confirms the two rejected/partial artifacts
  remain segregated: all four files have no duplicate
  `(symbol, stream_kind, callback_received_monotonic_ns)` keys, no receipt
  outside the respective capture range, and no callback error. Only
  `quote_20260820T093046+0800.json` has complete six-group, all-ACTIVE qualified
  cohort coverage; the durable campaign ledger records each disposition.
- A second independent continuous capture began at approximately 09:55 +08:00
  under the unchanged manifest after a read-only NTP preflight (selected host
  offset about `+47.647 ms +/- 48.080 ms`). The capture runner returned its
  control channel before its child process completed; two later retry attempts
  were therefore stopped before completion, while the earliest process remains
  the sole retained sample. This is collection-process provenance only, not a
  data-quality result or threshold candidate.
- The retained repeat completed as
  `quote_20260820T095444+0800.json` (SHA-256
  `7c937d32d3fc48f46307b880d2feda58e3f1d5449b020f2da1ad12fdd339638c`,
  834,811 bytes). It has 1,621 all-`CONNECTED/ACTIVE` observations, paired
  acknowledgement for every cohort symbol, complete six-group coverage, and
  zero callback errors, monotonic regressions, duplicate composite callback
  keys, or out-of-range receipts.
- The independent repeat strengthens the non-threshold finding: low 1530's
  longest Tick gap is 488.363 seconds and mid 6863's is 210.941 seconds despite
  continued paired-active subscriptions and BidAsk callbacks. Neither this nor
  the earlier continuous sample makes Tick silence a valid stale/executable
  failure signal. Source clock skew persists (879/1,621 negative raw
  event-to-callback measurements), so all quote values remain unset; broker /
  account evidence remains a separate, uncollected blocker.
- The third non-overlapping continuous artifact
  `quote_20260820T101439+0800.json` is also qualified (SHA-256
  `181a59b0d9fbd378a70b638f659b0d854a8e5e74b29dd6c2cceeedb321accd6f`,
  963,235 bytes, 1,872 observations): paired acknowledgement, six-group
  coverage, all ACTIVE rows, zero callback errors, zero monotonic regressions,
  zero duplicate composite keys, and zero receipts outside its capture range.
  Its low/mid Tick counts are only 1/3 despite active BidAsk callbacks (20/26).
- Across the three complete continuous samples, mid Tick gaps span
  124.389–210.941 seconds; low has two single-Tick samples and one 488.363-second
  observed Tick gap. The third artifact's lower negative raw event-to-callback
  count (89/1,872) is variation, not proof of clock alignment. It reinforces the
  separate requirements for calendar/session coverage, source-clock disposition,
  and a broker/account evidence source; it does not change any threshold status.
- A pre-close cross-artifact integrity profile now covers all six immutable
  files: 6,665 observations, zero within- or cross-artifact duplicate composite
  callback keys, zero callback receipts outside their capture ranges, and zero
  callback errors. The known 09:16 `CONNECTED/PENDING` artifact remains the
  sole lifecycle-rejected artifact; it is retained but excluded. These are
  collection-integrity checks only and do not resolve source-clock, session,
  threshold, or broker/account evidence gates.
- Reviewer disposition: the morning continuous campaign is formally qualified
  evidence and can freeze the qualitative invariant that executable quote health
  is **not** Tick freshness alone. It rejects `no Tick for N -> BOOK_STALE` and
  supports a future connection/subscription-plus-BidAsk health model. This is
  not a duration threshold, RiskGate implementation, or Phase 1 authorization.
  The full evidence-status ledger is preserved in
  `research/freshness_calibration/reviews/2026-08-20_morning_reviewer_disposition.md`.
- Execution order is now explicitly frozen: today's close quote evidence, then
  cross-session quote evidence, then source-clock disposition, then a separate
  broker/account campaign only with explicit read-only authorization. No
  migration, Portfolio core, RiskGate freshness code, provisional threshold, or
  broker/account endpoint call may occur before `FreshnessPolicyV1` is frozen.
- The scheduled 13:01 close capture completed as
  `quote_20260820T130116+0800.json` (SHA-256
  `1994292cc3c9868952567283f9dc7b02a8ada8dca03a05e7c131872c8e3aed70`,
  2,092 all-ACTIVE observations). Its paired acknowledgements, schema/digest,
  duplicate/range, callback-error, and monotonicity checks pass. It is partial
  close evidence only: low 1530 has eight BidAsk callbacks but zero Tick
  callbacks, and the 13:01–13:16 interval does not reach the 13:30
  market/session boundary. The result supports the existing Tick-only model
  rejection but leaves close/session-boundary evidence insufficient.
- The 2026-08-21 cross-session close artifact
  `quote_20260821T130144+0800.json` (SHA-256
  `d00da28a50d2df53fa120c43a1aebf91cfa1baecca91705f590067898977469e`)
  passed schema/digest, paired acknowledgement, all-ACTIVE, error, monotonic,
  duplicate, and receipt-range checks for 1,497 observations. It repeats the
  5/6 callback coverage: 1530 has one BidAsk callback and zero Tick callbacks,
  while high/mid have both streams. This is partial cross-session early-close
  evidence that further rejects Tick-only executable health; it does not
  establish a BidAsk timeout or observe the 13:30 boundary.


## 2026-08-19 — Basic strategy expansion implementation

- The user has now explicitly authorized implementation of `architecture/basic_strategy_expansion_implementation_plan.md`.
- Preserve the current unrelated worktree changes in `backtest/historical_download.py`, `market_data/provider.py`, download scripts/tests, README, and separate `.planning/` sessions.
- Apply the approved sequence: capability preflight first, then pure indicators/features, then five experimental strategies, Dashboard defaults, and verification.
- Use the minimum new abstractions needed by the five strategies; do not build a strategy DSL, optimizer, broker adapter, or live-money path.

## 2026-08-19 — Basic strategy expansion planning

- The requested deliverable is a reviewable implementation plan, not product-code implementation.
- The proposed batch is Opening Range Breakout entry, EMA crossover entry, RSI/Bollinger mean-reversion entry, ATR stop exit, and time stop exit.
- Preserve the repository boundary: strategies produce historical decisions or future intents; they do not call Shioaji order APIs or authorize real-money execution.
- External research is supporting context only. Published ORB evidence for TAIEX futures does not establish profitability for Taiwan cash equities; all imported parameters must remain hypotheses until Taiwan-stock OOS and walk-forward evidence passes.
- Public indicator definitions can standardize calculations, but indicator availability is not evidence that a trading rule is profitable.
- The current executable backtest registry contains two entries and three exits. New catalog rows are not executable unless their immutable definition digest and server-side execution binding exactly match a registered implementation.
- `HistoricalBar` already supplies timezone-aware OHLCV plus optional amount, so the proposed indicators do not require a new raw market-data source.
- `StrategyContext` currently exposes only the current bar, previous close, session open/high, cumulative volume/VWAP, bar count, last-bar flag, and entry price. ORB needs a frozen opening-range state; EMA/RSI/Bollinger/ATR need rolling bar history or precomputed features; ATR trailing exits and time stops also need position lifecycle state.
- The engine is deterministic, long-only, one-entry-per-symbol-per-day, and executes decisions on the next bar. New strategies must preserve those semantics and must not trigger from an unfinished or future bar.
- The worktree already contains unrelated modified product and planning files from concurrent work. Phase 9 will avoid those files and create only a standalone architecture plan plus updates to the root planning records.
- The existing `features/` engine is Tick/BidAsk-, DataHealth-, and event-ID-specific. Its semantics should not be imported directly into historical Kbar evaluation. The plan should introduce a small pure Kbar indicator layer first and require parity fixtures before any future live reuse.
- Strategy parameters are immutable catalog metadata, and a backtest run currently selects strategy IDs rather than arbitrary per-run parameter overrides. The first slice should keep fixed research defaults per strategy version; parameter changes create a new version instead of adding a browser parameter tuner.
- The strategy and backtest UI already render definitions and executable ENTRY/EXIT choices from the APIs. Once registry/catalog matching is correct, the new strategies should appear without a new endpoint or a new strategy-specific form.
- ATR exits require an explicit as-of rule: ATR used for an entry or same-bar protective exit must be based only on bars completed before the entry fill bar. Otherwise the fill bar's future high/low would leak into the stop distance.
- The prior architecture plan already requires as-of-only context, next-bar fills, deterministic aggregation, immutable definitions, and no-look-ahead tests. Phase 9 should extend those contracts rather than introduce a second strategy framework.
- Dataset manifests currently expose only generic `OHLCV`. Their profile is inferred from total observations per date, not cadence per symbol/session, so a multi-symbol daily dataset can be misclassified as one-minute data. ORB and intraday indicators must not rely on this heuristic.
- `create_run()` currently validates strategy side/registration but does not enforce each strategy's `required_capabilities` against the selected dataset. Capability preflight is a prerequisite, not an optional polish item.
- The plan should introduce explicit derived dataset capabilities such as `KBAR_INTRADAY`, `BAR_INTERVAL_SECONDS=60|300`, and `SESSION_BOUNDARIES`, computed from per-symbol/session intervals and coverage. Daily or irregular data must fail closed for ORB, time-stop, and intraday rolling strategies.
- The engine already stores `entry_event_index` internally and prevents exit evaluation on the entry event. It does not expose holding bars, entry time, peak price, or ATR-at-entry to strategies; position feature state can be extended without altering persistent database schema because run results remain JSON payloads.
- The current backtest application loads the full dataset into memory. This plan should keep the first strategy slice compatible with that engine and avoid bundling an unrelated streaming-engine rewrite, while documenting bounded rolling buffers so the strategy layer does not add unbounded per-symbol history.
- Source review: the NTU/IEEE TORB paper uses one-minute intraday index-futures data and includes TAIEX, so it supports ORB as a research candidate but not direct transfer of performance claims to Taiwan cash equities: https://scholars.lib.ntu.edu.tw/entities/publication/d69ecf33-892c-4f8a-9a88-2af1bcc4efcd
- Source review: the Santa Fe Institute record identifies moving-average and trading-range-break rules as simple, long-studied technical rules, but its Dow Jones sample is not Taiwan intraday evidence: https://web-prod.santafe.edu/research/results/working-papers/simple-technical-trading-rules-and-the-stochastic-
- Source review: TA-Lib documents EMA/BBANDS, RSI, and ATR with explicit lookback/unstable-period behavior. The implementation plan must freeze warm-up and seeding semantics and return `INSUFFICIENT_DATA`, not silently substitute zeros: https://ta-lib.github.io/ta-lib-python/func_groups/overlap_studies.html ; https://ta-lib.github.io/ta-lib-python/func_groups/momentum_indicators.html ; https://ta-lib.github.io/ta-lib-python/func_groups/volatility_indicators.html
- Source review: TWSE currently documents regular trading as 09:00–13:30 and distinguishes general stock sell tax from the reduced eligible day-trading rate. Strategy comparisons must keep session boundaries and cost scenarios explicit: https://wwwc.twse.com.tw/en/about/company/guide.html
- Runtime dependency decision: do not add TA-Lib merely to implement five functions. Use small pure Decimal-based calculations with hand-worked/golden fixtures; optionally compare results to TA-Lib in a non-required qualification test, but freeze this project's own formula/version contract.
- Final plan decision: implementation order is capability preflight -> pure rolling features/engine v2 -> ORB -> EMA and RSI/Bollinger -> ATR and Time Stop -> research qualification.
- Final plan decision: new experimental strategies must not become default-selected; legacy ACTIVE entry/exit defaults remain the baseline until the user explicitly chooses a challenger.
- Final plan decision: no SQL table is required for the first slice; strategy definitions and dataset capability evolution fit existing JSON contracts, while old manifests remain immutable and fail closed for the new strategies.

## Requirements

- Review the attached five-stage development proposal for adjustments and optimizations.
- Compare it with the actual repository, especially existing `MarketDataStore`, `CandidateEngine`, `BuyScoreEngine`, and adjacent components.
- Produce an implementation plan only; do not implement application changes.
- Make the plan concrete enough for user review before any implementation begins.
- Add a web-based manual Shioaji Simulation order flow.
- Add a place in the web UI to view simulated purchased stocks and their position information.
- Preserve a clear path for later program-generated orders to use the same backend flow.
- The user has now authorized implementation.
- The first implementation slice must provide local paper simulation only; it must not claim to be an authenticated Shioaji Simulation session or submit any broker order.
- The user has now explicitly requested Shioaji Tick/BidAsk subscriptions for realtime simulation quote updates.
- This authorization changes the market-data path only; local paper orders remain in-process and must not call Shioaji order APIs.

## Research Findings

- The worktree began clean on branch `main`, tracking `origin/main`.
- No repository-level `AGENTS.md`, `RULES.md`, or pre-existing planning files were discovered by the initial scoped scan.
- Relevant prior project guidance requires data-only/research boundaries, fail-closed market-data handling, explicit stream ordering, queue-draining shutdown, and no real-money path. These are context to verify against this repository, not substitutes for current evidence.
- The supplied proposal has 679 lines and describes Phase 0 architecture cleanup followed by Historical Backtest, Replay Trading, Shioaji Simulation, Small Live Trading, and Production Trading.
- Its strongest architectural invariant is that strategy code emits an `OrderRequest` and never calls Shioaji directly; `ReplayBroker`, `ShioajiSimulationBroker`, and `ShioajiLiveBroker` sit behind a common Broker boundary.
- The proposal correctly calls out asynchronous order/deal callbacks and a real order lifecycle rather than equating submission with fill.
- The proposal currently treats live-money phases as planned progression. That conflicts with the inherited project boundary (`Real Money = prohibited`) unless the user separately changes scope; the final plan must not silently authorize live-order implementation.
- The current repository is compact and contains market data, candidate selection, scoring, position, dashboard, configuration, application entrypoint, and focused tests. No broker/execution package appears in the file inventory.
- A pre-existing isolated `.planning/2026-08-17-intraday-visual-dashboard` directory exists; the new root planning files are specific to this review and did not overwrite it.
- The proposal's closing sequence begins with Broker models/interface, then ReplayBroker, OrderManager, Shioaji simulation callbacks/synchronization, decision/risk engines, automated simulation, journal, and only later live comparison/production.
- Risk controls are placed only in the live-safety section of the proposal. They should instead be invariant policy enforced for every broker mode so Replay and Simulation exercise the same admission decisions as any future execution mode.
- The proposal's stated milestone is “Execution Layer v1,” with success defined as switching the same BUY signal between Replay and Shioaji Simulation without changing Candidate, Scoring, or Position logic.
- The repository README documents a decision-support MVP: users decide whether to buy; the dashboard is read-only; current positions are inserted manually for demonstration. This is materially earlier than an execution system.
- Existing architecture guidance explicitly says the first version favors simplicity and should not pre-create execution/backtest/event-system abstractions. Therefore the final plan should add only the minimum seams proven necessary for Replay and paper execution, rather than importing a production-trading architecture wholesale.
- Existing repository principles already isolate Shioaji behind `MarketDataProvider`, distinguish Candidate from buy signal, require continuous position monitoring, preserve score breakdowns, and centralize thresholds in settings.
- `run_scan()` is a one-shot orchestration function: it creates a new in-memory `MarketDataStore`, candidate/scoring engines, exit rules, and `PositionManager` for every scan, then loads market snapshots and returns a presentation DTO. It is not yet a persistent session/runtime loop.
- `MarketDataStore` stores only the latest `StockData` per symbol and unconditionally overwrites existing data; its own docstring marks stale-timestamp rejection as future work. Replay/event-driven execution cannot safely depend on it until ordering and session-time semantics are defined.
- The current `PositionManager` is fed a hard-coded demonstration position in `app.py`; current Position objects are user-entered holdings, not broker-authoritative positions derived from fills.
- The dashboard intentionally calls the same one-shot `run_scan()` and marks provider mode as `snapshot`, `streaming=False`; it performs no trading operation.
- The existing code has a useful pure boundary: Candidate and scoring operate on internal `StockData`, while dashboard serialization consumes `ScanResult`. Execution work should preserve these pure computations and move long-lived session orchestration out of `run_scan()` rather than turning the dashboard path into a trading loop.
- `MarketDataProvider` is pull-oriented (`get_stock`, `get_market_stocks`, optional historical Kbars). It has no event/replay clock, subscription lifecycle, disconnect signal, or backpressure contract; adding Replay by only naming a new provider would not define deterministic event-time behavior.
- `StockData.timestamp` is a single timestamp. Mock/Shioaji snapshots currently populate it with naive local `datetime.now()`, while Kbars are timezone-aware Asia/Taipei. Execution/replay needs an explicit, timezone-aware event-time/received-time contract before freshness or latency can be trusted.
- `ShioajiProvider` owns login and a private SDK client and can select `simulation=False` via `SJ_SIMULATION`. Broker integration should not reach through this private provider or duplicate login implicitly; a dedicated session/gateway composition boundary is needed, with fail-closed mode configuration.
- Snapshot conversion uses local receipt time rather than an exchange timestamp and skips per-symbol conversion exceptions during full-market scans. This may be acceptable for a UI snapshot but is insufficient as an execution-quality feed without explicit data-health reporting.
- Current market snapshots do not include bid/ask, lot type, tick size, tradable status, or exchange sequence. Consequently a credible limit/market fill model, spread gate, stale-data gate, and order normalization cannot yet be specified from `StockData` alone.
- The repository's own documented evolution order is `Strategy Idea -> Backtest -> Statistical Validation -> Shadow Trading -> Approved -> Realtime Strategy`; it explicitly names Shadow Trading and Data Health/Risk Gate as future seams. This is safer and more consistent with project scope than jumping from Replay directly to broker-simulated automated orders.
- Candidate, scoring, and exit logic are currently deterministic/pure over `StockData`, which is valuable for Replay parity. However outputs lack decision provenance such as strategy/rule version, decision ID, evaluated-at timestamp, market-data timestamp, and input snapshot identity; those must exist before a journal can be auditable.
- Existing tests focus on pure rules, latest-value storage, provider mapping/batching, historical Kbar mapping, and dashboard serialization. There are no tests for session orchestration, stale/out-of-order data, deterministic Replay, repeated decision suppression, order lifecycle, recovery/reconciliation, or persistence.
- Current store tests intentionally use identical timestamps and assert last-call-wins overwrite behavior. Tightening event ordering will need explicit compatibility decisions and new tests rather than silently changing this contract.
- Git history contains only the initial MVP and dashboard feature commits, reinforcing that the next step should be a narrow research/execution-simulation foundation rather than a production brokerage stack.
- Current official Shioaji documentation confirms Simulation supports subscriptions, historical queries, order/update/cancel/status/list-trades, and position/P&L queries, but simulated order placement excludes emerging stocks and odd lots.
- Official order/deal documentation confirms callbacks report both order and deal events with exchange identifiers/timestamps. Therefore submission return values and callbacks must be normalized as idempotent events; callbacks alone are not a durable source of truth after restart.
- Official current limits confirm: quote/history query calls share 50 requests per 10 seconds, order-related calls share 250 requests per 10 seconds, subscriptions are capped at 200, logins create connections, and the provider explicitly warns not to poll snapshots/ticks/kbars as a live feed.
- The current full-market `get_market_stocks()` uses batched snapshots. It can remain an explicit/manual snapshot scan, but an automated intraday runtime must use streaming subscriptions and a bounded subscription-selection policy rather than loop this method.
- Because the 200-subscription cap is far below the full TWSE/TPEX universe, the implementation plan needs a two-tier universe flow: coarse discovery/refresh at an allowed cadence, then Tick/BidAsk subscriptions for bounded candidates and all open/pending positions.
- Shioaji's public SDK evolves frequently, while this project currently allows any `shioaji>=1.7,<2`. Integration work should qualify a narrower tested version/range (without assuming the latest installed version) and record the actual SDK version in journal/session metadata.
- `pyproject.toml` package discovery currently enumerates only existing packages. Any approved `replay`, `decision`, `execution`, or `journal` package must be added deliberately so editable installs and built wheels do not omit it.
- The existing configuration has only rule/display/provider switches. Introducing execution-like modes requires typed, fail-closed configuration with no `live` value in the current scope; a loose `BROKER_MODE` string and shared `SJ_SIMULATION` toggle would be too easy to misconfigure.
- The active virtual environment currently has Shioaji `1.7.2`; this is useful local evidence, not a substitute for an explicit supported-version policy.
- Official stock-order docs require CA activation before placing orders, require an explicit `order_lot`, and show that `place_order` can return `PendingSubmit` before a later status refresh/event. The plan must model pending submission and must never infer acceptance/fill from a successful function return.
- The proposal's generic `qty` is unsafe because internal share quantity, order-lot type, and broker quantity must not be conflated. Use an unambiguous internal unit and let a tested broker adapter perform the conversion; include boundary fixtures for common-lot and unsupported odd-lot Simulation requests.
- The current 64-test suite passes in 0.10 seconds. This is the regression baseline for future approved changes.
- The prior dashboard planning record confirms the dashboard was deliberately designed as a manual-refresh, read-only snapshot surface and explicitly deferred streaming/replay/order endpoints. The execution plan must preserve that boundary and must not reuse dashboard refresh as the runtime market-data loop.
- The new user requirement intentionally changes the future dashboard boundary: after the manual Simulation gate, the browser may submit simulation-only order commands and read order/portfolio projections. This does not authorize a live-money route.
- The browser must not construct Shioaji SDK objects or call the SDK. Manual web orders and future strategy orders should be separate command origins feeding the same backend `OrderApplicationService`.
- The purchased-stock view must use `PortfolioProjection` plus reconciliation metadata rather than the current hard-coded demonstration `PositionManager` entry.
- The current dashboard already has a top-right `持倉` button and an accessible slide-in position drawer. The plan should evolve this existing surface into a simulation portfolio view instead of adding a redundant page.
- Current position cards already show symbol/name, quantity, entry/current price, unrealized PnL, stop/take-profit markers, and exit status. Simulation positions need to add source/mode, market value, average fill price, pending quantity, realized PnL, last broker reconciliation time, and sync/data-health state.
- `dashboard/server.py` currently exposes only snapshot refresh and Candidate history; `DashboardService` refreshes through `run_scan()`, whose sole position is a hard-coded demonstration holding. Simulation views must read OrderManager/PortfolioProjection repositories rather than call `run_scan()` or query Shioaji on every browser request.
- The current page explicitly says it is a one-shot snapshot without order functionality. A future Simulation control state must be unmistakable: show a persistent `SIMULATION` badge and keep the order form disabled/hidden unless the backend reports a healthy `SHIOAJI_SIMULATION` session.
- There is no account, certificate-authority, or authenticated Shioaji session evidence in this checkout. The safe first deliverable is therefore a session-local `LOCAL_PAPER_SIMULATION` implementation, visibly distinguished from Shioaji Simulation and with no SDK order calls.
- The local simulation can preserve the future command seam by treating the browser as one command origin and keeping order validation, idempotency, position updates, and order projection in one backend service.
- `DashboardService` and its tests expose a stable read-only scan snapshot whose `positions` still contain the demo holding from `app.py`. The local simulator must provide a separate `simulation` projection instead of changing the existing scan-result contract in this first slice.
- `dashboard/server.py` already keeps a process-lifetime `DashboardService` instance. A process-lifetime local simulation service can use the same `MarketDataProvider` instance without browser reads creating a provider or Shioaji client per request.
- The dashboard is a single static page with an existing accessible holdings drawer and explicit-refresh button. The smallest UI change is to reuse the holdings drawer for the simulation positions and add a compact order drawer/blotter rather than create a new route or frontend build system.
- The installed FastAPI test client cannot be imported because its environment expects `httpx2`, which is not installed. This slice will avoid adding an unrelated runtime/testing dependency and cover the API contract through the service tests plus direct endpoint construction only where needed.
- Calling the dashboard route with the ambient provider setting initialized `ShioajiProvider`; its installed native dependency segfaulted under the active Python 3.13 interpreter. Focused API tests must inject `MockProvider` and must not exercise the external SDK. This is an environment/provider compatibility issue outside the local paper-simulation path.
- The running local dashboard was visually and interactively verified with `MockProvider`: the simulation badge is visible, the candidate action opens an accessible order drawer, and its 3231/BUY/1-lot/105.50 defaults are correctly populated. The browser test did not submit a persistent test order; command behaviour is covered by the service/API tests.
- The final regression suite has 71 passing tests, and the static dashboard script passes a standalone JavaScript syntax parse. The local simulator contains no Shioaji import or order call.
- The current simulation stores only snapshot `StockData`; position reads never call the provider, and `refresh_quotes()` runs only behind the explicit full-dashboard refresh.
- Current local fills compare limit price with last trade (`StockData.price`). Tick/BidAsk integration needs separate best bid/ask fields so BUY eligibility/fill uses ask and SELL eligibility/fill uses bid.
- `StockData` intentionally models a broad latest snapshot and currently has no bid/ask fields. A separate small streaming-quote model is safer than changing every Candidate/scoring fixture and snapshot serializer.
- `SimulationService` is already guarded by an `RLock`, so normalized quote callbacks can update its quote projection safely; Shioaji-specific objects should stay in `market_data/provider.py`.
- The installed Shioaji 1.7.2 package includes `_core.pyi`; implementation can be checked against its local callback and subscription signatures without importing the native extension in tests.
- Current official Shioaji stock-streaming docs show `set_on_tick_stk_v1_callback` and `set_on_bidask_stk_v1_callback`, with callbacks receiving exchange plus the Tick/BidAsk payload; both common-stock streams are event-driven and delivered only during trading hours.
- Official guidance says callbacks should avoid computation. Provider callbacks should therefore only map SDK fields and invoke the small normalized update sink; all matching and portfolio work stays under the simulator lock.
- One symbol consumes two subscriptions when both Tick and BidAsk are active; the implementation must track subscription pairs idempotently and stay within the documented account limit rather than resubscribing on every browser poll.
- A real local Shioaji 1.7.2 smoke test successfully logged into the simulation environment with `subscribe_trade=False`, installed both callbacks, reported streaming healthy, and logged out normally.
- A real 4946 subscription received successful server acknowledgements for both Tick and BidAsk but no market event within the 10-second observation window. Because the feed is event-driven, this proves subscription acceptance but not yet payload mapping.
- A high-liquidity 2330 direct provider smoke received and normalized both real Tick and BidAsk callbacks, proving the SDK callback signature and mapper.
- End-to-end UI and standalone `SimulationService` smokes received ongoing Tick updates but a marketable BUY remained `SUBMITTED` for 10-14 seconds. The issue is downstream of subscription acceptance and requires inspecting the merged quote state before completion.
- The apparently marketable test was correctly pending: live 2330 best bid/ask was 2380/2385 and the test BUY limit was only 2000. Raising the local-paper limit to 3000 filled at ask 2385; the next Tick marked the position at 2380 and produced -5,000 unrealized PnL.
- FastAPI shutdown initially cancelled subscriptions but did not log out the Shioaji client, producing a native-thread panic after process shutdown. Adding an explicit Provider close/logout contract removed the warning in a second real shutdown smoke.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Classify recommendations by priority and evidence | Keeps blocking correctness issues distinct from optional improvements. |
| Include exact files/components and acceptance tests in the final plan | Makes the plan directly executable after approval. |
| Treat performance ideas as hypotheses until current hot paths and state ownership are traced | Avoids premature optimization. |
| Preserve `MarketDataStore` as a latest-state projection, not a historical/event store | Keeps current consumers stable while a separate immutable event source/journal owns replay and audit history. |
| Use one event-driven runner for fast Backtest and paced Replay | Prevents the same strategy from producing different semantics in two engines. |
| Keep the dashboard observer-only | Trading runtime owns provider cadence and state; the UI must never trigger order or streaming side effects. |
| Build common-lot, cash, long-only, limit-order Simulation first | Matches current long-only decision model and Shioaji Simulation constraints while minimizing order-normalization surface area. |
| Treat 20-30 sessions as an observation window, not a sufficient pass criterion | Advancement also requires deterministic, integrity, risk, recovery, and reconciliation gates. |
| Use an explicit simulation-only web command namespace | Makes it difficult to confuse or later repurpose the endpoint as a production-order route. |
| Keep reads projection-backed | Browser refresh/polling reads local order/portfolio state and must not trigger Shioaji status/position queries per request. |
| Show pending orders separately from filled positions | A submitted or accepted order is not yet a purchased holding. |
| Reuse the existing holdings drawer and add a separate simulation order ticket/order blotter | Keeps Candidate inspection intact while making orders and owned positions distinct tasks. |
| Poll or stream local projections, never provider/account APIs per browser request | Keeps API usage, callback ordering, and reconciliation under the backend runtime's control. |
| Make the first implementation session-local | Meets the immediate web simulation requirement without introducing database schema/migration scope; the UI must disclose that restarting the backend clears simulated state. |
| Keep SDK callbacks thin and hand normalized quote updates to `SimulationService` | Avoids doing order-state work on Shioaji callback threads and keeps the simulator testable without the SDK. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Initial memory search had no match and prevented chained reads | Split the reads into independent operations. |

## Resources

- `/Users/stevehuang-work/.codex/attachments/db832d2f-0507-444a-8890-36b212eed197/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader`
- Shioaji Simulation Mode: https://sinotrade.github.io/tutor/simulation/
- Shioaji Order & Deal Event: https://sinotrade.github.io/tutor/order_deal_event/
- Shioaji Usage Limits: https://sinotrade.github.io/zh/tutor/limit/
- Official Shioaji repository: https://github.com/Sinotrade/Shioaji

## Visual/Browser Findings

## Freshness Calibration scheduling findings (2026-08-22)

- Official OpenAI guidance distinguishes Codex automations (focused Codex
  workflows) from ChatGPT Scheduled Tasks. Use the existing Codex automation
  mechanism for this local-workspace evidence campaign; do not treat a ChatGPT
  reminder as a reliable local capture runner.
- The legacy `freshness-close-window-capture` heartbeat remains `ACTIVE` despite
  two previously stalled native pause attempts. It starts at 13:00 and produces
  a 13:01–13:16 sample, which cannot observe the required 13:30 boundary.
- The recurring campaign must make an explicit Taiwan-equity-session decision
  before any provider login/subscription. A closed session must be recorded as
  `NO_CAPTURE`, with no Shioaji call. On an open session, it is restricted to
  the frozen 2886/6863/1530 cohort and Tick/BidAsk only with
  `subscribe_trade=False`; account, order, CA, trade-callback, and execution
  APIs remain prohibited.
- Proposed observation windows are 09:15–09:30 (opening), 10:00–10:15
  (continuous), and 13:15–13:35 (close boundary). The final interval must
  cross 13:30; its extra five minutes are an observation window, not a new
  freshness threshold or Portfolio implementation authorization.
- `ReviewedEquityCalendar` already gives a reviewed 2026 TWSE calendar with
  coverage checks and exceptional closures. The scheduling wrapper can use it
  to fail closed on holidays, weekends, and out-of-coverage dates before it
  loads the quote-capture function or initializes Shioaji.
- The existing quote CLI accepts a reviewer-supplied label but does not itself
  enforce the frozen cohort, reviewed calendar, or capture start time. A small
  dedicated runner is therefore required to make unattended collection safe.
- Native `codex_app__automation_update` is not callable in this thread: its
  view request returned `No handler registered for tool: codex_app.automation_update`.
  It is the third distinct failure after two earlier stalled pause attempts;
  do not retry it. A user-authorized local scheduler may be installed only
  after its fail-closed runner is tested.
- The user-level launchd job is installed as
  `com.stevehuang.tw-intraday-trader.freshness-calibration` with all three
  calendar triggers confirmed by `launchctl print`. A manual smoke produced
  `NO_CAPTURE_OFF_SCHEDULE` and no `ntp_preflight` field, demonstrating that
  an unplanned launch does not enter either NTP or quote-provider work.
- The Mac must remain logged in and awake around each start time. If it wakes
  outside the scheduled minute, the runner deliberately returns
  `NO_CAPTURE_OFF_SCHEDULE` rather than backfilling a later, incomparable
  capture window.

## Freshness Calibration acceleration findings (2026-08-22)

- The only safe acceleration within the authorized evidence scope is more
  non-overlapping Tick/BidAsk samples on the same reviewed trading day. It can
  improve opening/continuous coverage but cannot replace evidence from distinct
  trading dates, source-clock disposition, or separate broker/account evidence.
- The accelerated schedule will retain the exact frozen cohort and labels and
  add 09:00–09:15 (`opening`), 11:00–11:15 (`continuous`), and
  12:00–12:15 (`continuous`) to the existing 09:15–09:30, 10:00–10:15, and
  13:15–13:35 captures. The intervals do not overlap.
- Broker/account endpoint collection remains explicitly unapproved. This
  schedule change must not be interpreted as permission to read any account,
  order, accounting, or buying-power endpoint.
- The reloaded launchd service reports exactly six calendar triggers:
  09:00, 09:15, 10:00, 11:00, 12:00, and 13:15 Asia/Taipei. Each starts one
  bounded capture only after the runner's reviewed-calendar and NTP gates.

## Automated evidence-QA findings (2026-08-22)

- Existing accepted evidence is structurally trustworthy only after inspecting
  the immutable artifact's digest/schema, paired acknowledgement, lifecycle,
  coverage, callback errors, monotonicity, and clock-skew. A capture's own
  cadence analysis is useful but does not replace those structural checks.
- The smallest safe acceleration is a post-capture summary written beside the
  scheduler run record. It may state `REVIEW_REQUIRED` or a structural failure,
  but must never select a threshold, label a policy frozen, or make a
  broker/account claim.
- The capture artifact already stores enough immutable fields to create this
  summary: `connection_transitions` carries the per-symbol `TIC`/`QUO`
  acknowledgement evidence, while every observation carries its own
  connection/subscription state. A missing callback group remains partial
  coverage, not structural corruption and not a reason to discard the raw
  artifact.
- Backfill over all eight retained artifacts matches the current human review:
  three continuous captures are structurally complete; the early PENDING
  opening artifact is rejected; early opening and both close artifacts retain
  partial coverage; and the discovery artifact is excluded from the frozen
  cohort. Every artifact has zero callback errors and zero callback-monotonic
  regressions. Clock-skew remains provenance/anomaly evidence only.
- Post-capture QA now compares the artifact bytes to the inspected SHA-256
  before summarizing. If an artifact changes or is structurally invalid, the
  scheduler reports `CAPTURE_INVALID` while leaving the original bytes in
  place for investigation.

- Official documentation was reviewed as of 2026-08-18; volatile API limits and supported operations should be rechecked at implementation time.
- Browser verification used the real local Shioaji feed: stream badge, subscription count, advancing quote time, cancel/pending behavior, ask-side fill, position count, bid/ask/current-price fields, and PnL all rendered correctly with no console errors.

## Basic strategy expansion implementation findings (2026-08-19)

- The pre-change repository baseline is green: 29 focused backtest tests pass; the full suite has 326 passing and 1 skipped test.
- Dataset manifests already carry `profile` and `capabilities`, but all current creation paths only advertise `OHLCV`.
- `create_from_partitions()` counts bars per `(symbol, session)` while `_seal()` counts all symbols per date. The latter can misclassify a multi-symbol daily dataset as intraday.
- Incremental datasets currently inherit their parent's profile and capabilities without re-evaluating the combined immutable bar chain.
- The backtest application validates strategy side but does not compare a strategy definition's required capabilities with the selected dataset.
- Dashboard defaults are positional instead of status-based, so introducing experimental strategies would silently change the default entry and enable all new exits.
- Adding an optional manifest field can silently change the recomputed digest of legacy JSON. The implementation therefore remembers whether `cadence_summary` existed and omits it when reserializing old manifests.
- Legacy strategy runs produce byte-equivalent engine result payloads under frozen v1 and v2; v1 explicitly rejects the five feature-dependent strategies.
- ATR propagation is engine-tested end to end: the signal-bar ATR travels through the pending entry, becomes immutable position context at fill, triggers on a later completed bar, and exits on the following open.
- The final suite has 337 passing and 1 skipped test. Python compilation, Dashboard inline JavaScript compilation, and whitespace validation also pass.
- The implemented slice remains historical/data-only: no CA activation, trade subscription, broker callback, or broker order submission was introduced.

## D-HEALTH-LATE-001 minimum-pass findings (2026-08-25)

- The failed CLOSE capture could not be reclassified because its malformed SDK callbacks were recorded only as error strings; their raw market fields were not retained in a verifiable artifact.
- The minimum safe relaxation is therefore prospective: preserve `TickEvent` validation and quarantine each failed callback with its SDK ingress sequence, error identity, selected raw market fields, and a content digest.
- A callback anomaly is warning-only only when error and quarantine counts match, every error string matches its quarantine entry, the quarantine artifact verifies after persistence, the bounded queue drains, the Journal finalizes and verifies, and exact replay runs and passes.
- Missing or mismatched quarantine evidence, queue drain failure, admission/recorder failure, Journal verification failure, and replay failure remain hard failures.
- New reports use passive-capture schema v2 and daily schema v3; the daily builder continues to accept retained passive-capture v1 reports.
- This change does not alter Health, Admission, Freshness, watermark, foundation flags, provider trade subscription, consumer authority, Historical Qualification, Freshness Calibration, or P1.2 gates.

## D-HEALTH-LATE-001 one-shot OPEN runner findings (2026-08-27)

- The repository already fails closed before constructing Shioaji when `127.0.0.1:0` cannot bind; removing that guard would restore the native-crash risk and is out of scope.
- The required change belongs at the execution boundary: one local launchd attempt must own the exact OPEN command, while the Codex automation may only inspect retained artifacts.
- No sandbox attempt may precede the launchd attempt, and neither runner may retry or choose an alternate session.
- The runner must preserve `subscribe_trade=false`, foundation flags off, and every Health/Admission/Freshness/watermark and qualification gate contract.
- The current Codex cron is still active at weekdays 08:55 and its prompt executes the provider command itself; it must be changed before enabling launchd or both schedulers could contend for the same OPEN run.
- The repository's existing launchd convention uses an absolute interpreter/script path, `TZ=Asia/Taipei`, unbuffered output, and explicit stdout/stderr logs. The new one-shot runner should follow those conventions but must add an immutable run identity and self-disable/no-op after its first terminal attempt.
- The automation control tool accepted the existing automation id in `view` mode after rejecting the wrong `automationId` key; future updates must use `id` and full preserved fields.
- The frozen OPEN phase is 09:00-09:30 Asia/Taipei with a 600-second pre-connect allowance, so 08:55 is a valid start. The local job must not start earlier than 08:50 or at/after 09:30.
- The existing launchd plist validates with `plutil`; its absolute-path and logging structure is reusable without touching the capture CLI or phase contracts.
- At 2026-08-27 09:10 Asia/Taipei, today's OPEN phase had already started, so arming a new one-shot for today would violate the reviewed first-attempt setup. The runner must target the next reviewed trading day instead.
- The reviewed 2026 calendar has no 2026-08-28 closure and Friday is a weekday, so 2026-08-28 is the next eligible target date.
- Another repository launchd supervisor already uses an `O_EXCL` claim before sensitive work specifically to prevent launchd re-invocation. The OPEN runner should reuse this simple pattern rather than invent a scheduler framework.
- The implemented runner accepts provider execution only on 2026-08-28 from 08:50:00 through 08:59:59 Asia/Taipei, ensuring the full 09:00-09:30 OPEN window remains available. Off-date or delayed launch still consumes the one-shot claim and records `NOT_RUN`; it cannot be retried later.
- Focused verification passed: 6 runner tests, Python compilation, launchd plist lint, and scoped whitespace validation.
- The native Codex automation update handler did not persist changes, and policy prevents UI control of Codex. A validated exact TOML replacement was therefore installed with a recoverable `/private/tmp` backup after explicit scoped approval.
- Readback confirms the old provider-running weekday cron is replaced by one `COUNT=1` read-only inspection at 09:35; its prompt expressly prohibits provider execution, retry, artifact mutation, and gate claims.
- The initial daily one-shot would have fired on 2026-08-27 before the target run; pre-execution review corrected it to Friday 09:35 with `COUNT=1`. Readback now shows the intended post-capture schedule.
- launchd is loaded with the exact 2026-08-28 08:55 calendar trigger, `runs=0`, and no claim/result file. No provider command was started during installation or verification.

## D-HEALTH-LATE-001 immutable runtime remediation (2026-08-27)

- Independent review returned `REQUEST CHANGES`: the loaded plist referenced a shared dirty checkout (`ahead 19 / behind 6`), while the one-shot claim sealed only argv and did not establish reviewed source/runtime identity for the next-day attempt.
- The unsafe LaunchAgent was unloaded before any provider attempt. Its final observed state was `runs=0`, `last exit code=(never exited)`; post-unload lookup is absent and no claim/result artifact exists.
- The 09:35 Codex automation remains active as a Friday `COUNT=1` read-only inspection and still prohibits provider execution or retry.
- Completion now requires a commit-pinned clean worktree from `origin/main@33c9b3a`, adversarial source/runtime drift rejection before provider invocation, and a loaded plist whose exact pinned path/HEAD/identity can be read back.
- Readback confirms `origin/main=33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`; shared `main` is exactly `ahead 19, behind 6` with broad unrelated changes. The dedicated branch name `codex/d-health-open-pinned-20260828` is unused.
- The dedicated worktree is clean at `33c9b3a`. It has no `.venv`; the shared interpreter is Python 3.13.5 with Shioaji 1.7.2, but reusing that mutable shared path would not satisfy runtime identity.
- `pyproject.toml` uses version ranges rather than a locked broker environment, so the remediation must create a dedicated interpreter environment and seal its resolved package/binary identity in the reviewed manifest.
- `.venv/` is already ignored in the reviewed base, so a dedicated worktree-local environment can coexist with `git status --porcelain --untracked-files=all` cleanliness. No lock file exists; resolved versions and binary/tree digests must therefore be frozen explicitly.
- The shared environment contains an editable install bound to dirty `main`, confirming it cannot be copied or reused. The pinned environment must omit editable project installation and import project code only from the clean worktree cwd.
- The reviewed D-HEALTH transplant is limited to 8 tracked files: five market-data guard/quarantine/report modules and three focused test modules. `equity_calendar.next_trading_day()` and all unrelated dirty changes are excluded.
- A fresh worktree-local venv was created with no editable project install. Exact installed runtime/test packages are Shioaji 1.7.2, python-dotenv 1.2.3, pytest 9.1.1, iniconfig 2.3.0, packaging 26.3, pluggy 1.6.0, and Pygments 2.21.0.
- The first immutable-runtime test slice passed all 33 runner/capture/evidence/stream tests. The only warning/compile issue was sandbox inability to write cache files in the sibling worktree, not a product failure; validation will redirect caches to `/private/tmp`.
- The final clean branch is `codex/d-health-open-pinned-20260828` at `0bb2ee2fb25c5d818a1784a84ea49e2881265aee`, with four scoped local commits: payload `ffd4d79`, initial seal `e37d2a9`, non-login `/bin/sh -c` boundary hardening `f905520`, and final reseal `0bb2ee2`; nothing was pushed or merged.
- The sealed manifest binds all tracked source except its self-referential manifest path, explicit critical runner/CLI/cohort/calendar files, the exact capture argv, Python 3.13.5 interpreter bytes, `pyvenv.cfg`, exact distributions, and full stdlib/site-packages tree digests.
- The bootstrap runner now imports no project module before complete identity verification. Adversarial source and site-packages drift tests exercise the actual identity gate, retain provider calls at zero, and write auditable `NOT_RUN` results with exit 78.
- Final read-only identity rehearsal passed at final HEAD. Focused tests are `33 passed`; compilation, template/rendered plist lint, rendered shell syntax, and diff checks pass.
- Loaded plist readback uses the non-login `/bin/sh -c` boundary, points only to the dedicated worktree, and embeds HEAD plus manifest/runner/interpreter digests. launchd remains `runs=0`, `last exit code=(never exited)`, with no claim/result/session/evidence. The 09:35 Codex automation remains read-only and now inspects the pinned state and records paths.

## D-HEALTH-LATE-001 external credential remediation (2026-08-27)

- Second independent review returned `REQUEST CHANGES`: the dedicated checkout has no `.env`, user launchd has no Shioaji credential aliases, and current `connect_from_env()` searches only the dedicated project root after identity verification. The first one-shot would therefore claim and fail for missing credentials.
- The loaded job was confirmed at `runs=0`, `last exit code=(never exited)` with no formal artifacts, then unloaded. The Friday 09:35 Codex automation remains active and read-only.
- The credential fix must be metadata-only in evidence: absolute path, owner, mode, selected allowed key names, and presence. Secret values and hashes are prohibited from Git, manifest, plist, claim/result, logs, tests, and conversation.
- The child environment must be allowlisted to Shioaji key/secret aliases plus `SJ_SIMULATION`; unrelated Fugle, FinMind, broker-account, or ambient secret variables must not cross the boundary.
- P2 requires `source_payload_head` to become a checked identity statement or be removed; an unchecked manifest field is not acceptable evidence.
- The selected external boundary is `/Users/stevehuang-work/Documents/tw_intraday_trader/.env`. It is owner UID 501, one regular link, and was tightened from `0644` to `0600` without reading, copying, or rewriting values. Allowed-name inspection found one API alias and one secret alias; `SJ_SIMULATION` is absent and the reviewed child boundary supplies the existing `true` default.
- The runner opens the exact absolute path with no-follow/close-on-exec flags, validates single regular file, owner, exact owner-only mode, and stable file metadata across the read. It filters lines before dotenv parsing and retains only the selected Shioaji API alias, selected Shioaji secret alias, and `SJ_SIMULATION`.
- The late-delivery CLI now calls `connect_from_env(load_dotenv_file=False)`, so the child cannot search another dotenv file. Its environment is reconstructed from a small non-secret runtime allowlist plus only the three selected Shioaji fields; ambient Fugle, FinMind, broker-account, and other secrets are dropped.
- Exact secret values are redacted from subprocess stdout/stderr and setup exceptions before launchd output or result persistence. A value-aware scan of all tracked files plus manifest, rendered/installed plist, and automation reported `leak_file_count=0` without printing values.
- Missing file, insecure mode, missing key, calendar import/evaluation, subprocess setup, redaction, and filtered-env tests all use temporary state roots. Final focused verification is `42 passed`; no formal claim/result was created.
- P2 was resolved by removing `source_payload_head`. Final identity is HEAD `8d3747f28c2fc3e8f2582504932114526c7c4ea1`, manifest SHA-256 `07cbfaa0a1a227a35e723e7b6ecedbfb712999bf2cc443653421209b407e9d9b`, clean-worktree verification, and source-tree digest `ae7d97bff3ebf117dd12844e738ee83bd31a31dc68e54ba569928e14260642b8`.
- Final loaded readback uses `/bin/sh -c`, the pinned runner/interpreter, exact credential path, final HEAD and hashes, and remains `runs=0`, `last exit code=(never exited)`. Formal state count is zero; 09:35 automation remains active/read-only.

## Previous-day premarket watchlist planning findings (2026-08-19)

- The requested watchlist must be fully available before the open using only data whose market date is earlier than the target session; `PREOPEN_INDICATIVE` is explicitly out of scope.
- The existing `premarket_gap_watchlist_v1` is `DRAFT` and unsuitable for this slice because its contract requires pre-open indicative prices.
- The current Candidate flow and unified strategy catalog are reusable seams, but repository evidence must determine whether a durable watchlist projection and as-of-date API already exist.
- The worktree already contains strategy-expansion and unrelated downloader/provider/night-session changes; this phase is plan-only and must not modify product code.
- `CandidateEngine` consumes current `StockData` snapshots and applies OR-combined rules; it cannot truthfully evaluate an as-of-previous-session watchlist without a separate historical input contract.
- `Candidate` stores only `symbol`, source set, and matched rule names. That is insufficient for a durable premarket artifact because it lacks target session, source dataset digest, evaluation timestamp, and observed evidence.
- The repository already has `CandidatePool`/discovery-source seams and a separate TAIFEX premarket context module/tests. The stock watchlist plan should reuse the pool boundary but remain independent from the market-level TAIFEX context.
- Current Dashboard candidate history is on-demand for symbols already in the snapshot and derives the date range from `datetime.now()`. A premarket watchlist requires an explicit target session/as-of contract rather than this UI cache path.
- `CandidateDiscovery` is the better downstream seam than the legacy `Candidate`: it already carries timezone-aware discovery/expiry timestamps, priority, rank types, and immutable evidence, and `CandidatePool` merges it without treating discovery as a buy signal.
- `CandidatePool` admits every non-scanner source immediately and currently has no target-session identity. A prior-session watchlist source therefore needs explicit expiry at the target session boundary and must not rely on process-lifetime pool history as the reproducible artifact.
- `CandidateSource` has no dedicated prior-session/watchlist value. Reusing generic `USER_STRATEGY` would lose provenance; the plan should add an explicit source while preserving existing AUTO/SCANNER/MANUAL/POSITION semantics.
- Strategy catalog metadata supports a PRE_MARKET CANDIDATE family and immutable versions. New watchlist definitions can be code-owned `EXPERIMENTAL` bindings without changing the existing pre-open gap draft.
- Repository search found tracked `tests/test_premarket_*` imports but no readable `premarket/` package at the expected path. This checkout inconsistency must be resolved before any implementation phase reuses the TAIFEX premarket module.
- Follow-up shows the `premarket/` package and `config/premarket.py` truly do not exist in this checkout, while ignored/untracked-looking premarket test files are present. The implementation plan must treat the separate TAIFEX plan/files as concurrent, unavailable work and define no dependency on them.
- The existing after-close scheduler only excludes weekends; it has no holiday/makeup-session calendar. A prior-session watchlist must use a versioned TWSE/TPEX trading calendar or fail closed rather than infer previous session as calendar day minus one.
- `HistoricalDatasetCatalog.load_bars()` materializes the entire immutable dataset. Reusing it directly for an every-day full-market screen would be correct for a small fixture but inefficient for a multi-year market dataset; the plan needs a bounded recent-session read or a derived daily-bar artifact.
- Current historical capabilities distinguish OHLCV/intraday/1m/session boundaries but do not explicitly certify complete daily bars. The watchlist must require a daily aggregation/completeness capability and never calculate from a partially synchronized target session.
- `HistoricalBar.amount` is currently populated as `close × volume` for Provider downloads, while `KBar` itself exposes only OHLCV. Liquidity filters must label this as a traded-value proxy unless a source-backed turnover field is introduced.
- Session-scoped `InstrumentReferenceStore` supports momentum eligibility, but it is not a date-effective listing/delisting universe. Operational next-session screening and historical research eligibility must remain separate.
- During planning, untracked `config/premarket.py`, `config/taifex_calendar_2026.json`, and partial `premarket/` files appeared from concurrent work. They are user/concurrent changes, remain outside this plan's edit scope, and cannot be treated as a stable dependency until that work is complete and reviewed.
- `CandidatePoolDecision` hashes admission metadata but drops each discovery's detailed evidence. The immutable watchlist artifact must remain queryable for UI/research evidence even after its symbols are converted to CandidateDiscovery items.
- The main Dashboard still uses legacy `run_scan()` (`CandidateEngine` plus manual list), while CandidatePool belongs to the Momentum subscription universe. The implementation must explicitly project the new watchlist in the Dashboard and separately adapt it into CandidatePool; changing only CandidatePool would not make the list visible in the current dashboard.
- Existing runtime composition is provider/dashboard/simulation oriented and contains no durable research-artifact service. A read-only watchlist projection can be composed separately, similar to the Momentum dashboard service, to avoid initializing provider or order paths.
- Existing backtest job persistence already supports arbitrary job kinds and immutable resource IDs. It can coordinate watchlist generation, but artifact content should have its own catalog/repository contract rather than overloading CandidatePool history.
- Instrument references do not include security type/listing intervals. The plan requires a date-effective universe input with explicit equity eligibility; it must not infer common-stock status from a four-digit symbol.
- Existing `candidate/rules.py` operates on floating-point current `StockData` and global settings. Prior-session strategies need separate immutable Decimal daily-feature inputs and version-owned parameters; they should not be added as more `CandidateRule.match(StockData)` implementations.
- The Dashboard already has a market-overview candidate panel and strategy-catalog drawer. The smallest truthful UI is a separate read-only `盤前觀察池` panel/status in the overview, with drill-down evidence, rather than silently mixing historical candidates into the current score-sorted candidate list.
- Current backtest persistence has durable jobs but no watchlist artifact tables. A forward migration can add manifest/entry rows for bounded reads while preserving immutable JSON evidence and supporting both SQLite and PostgreSQL adapters.
- Existing UI tests are static HTML contracts and service/API tests use injected providers. The plan should add watchlist domain fixtures plus service/API/UI tests without requiring Shioaji or network access.
- The concurrent TAIFEX work also modified package discovery to include `premarket*`. The stock watchlist should use a distinct `watchlist*` package include to avoid namespace and rollout coupling.
- The finalized design uses an explicit target session `T` and calendar-derived prior session `P`; the pure engine receives both and may read only sessions through `P`.
- The first reviewable implementation slice is calendar/universe contracts, shared indicators, immutable daily derivation, Momentum v1, artifact persistence, and deterministic CLI. CandidatePool, Dashboard, scheduler activation, NR7, and Oversold follow only after the evidence layer is verified.
- A current-snapshot equity universe may support an operational next-session artifact, but it must be marked `research_eligible=false`; historical out-of-sample evidence requires a date-effective universe.
- The completed plan is `architecture/previous_day_premarket_watchlist_implementation_plan.md`; it changes no product behavior and keeps all three definitions `EXPERIMENTAL`.

## Previous-day watchlist Phase 0-3 review findings (2026-08-19)

- The three strategies remain candidate generators, not demonstrated trading strategies; Watchlist, intraday confirmation, BuyScore, and entry decision must remain separate stages.
- Corporate actions are a P0 blocker for formal validation. Preserve raw OHLCV, derive a consistently adjusted OHLC series, store the adjustment factor/type/source/digest, and forbid mixing raw and adjusted fields inside one indicator.
- Momentum needs `daily_return` and `close_location` evidence to distinguish strong closes from high-volume distribution. The initial research design should compare baseline, positive-return, close-location, and combined variants rather than promote `0.6` directly to a production threshold.
- A one-price bar makes `close_location` undefined and must be classified before strategy evaluation.
- Rename the normalized NR7 strategy to `nr7_compression_watchlist_v1`; it is direction-neutral and must wait for next-session NR7-high/ORB/VWAP confirmation before any LONG bias.
- Hard-exclude one-price or limit-locked false compressions from NR7. Merely touching a price limit while retaining a real range should remain a flagged research cohort rather than an automatic exclusion.
- Momentum limit-up observations should be flagged and evaluated separately from ordinary momentum instead of silently mixed into one population.
- Oversold remains `EXPERIMENTAL` and confirmation-only; it must not block the first Momentum artifact slice.
- Formal validation must be net of date-effective commission, minimum fee, transaction tax, bid/ask, and slippage. Gross performance alone cannot pass a promotion gate.
- The user authorized rewriting the plan's Phase 0-3, not implementing product code.
- Corporate-action adjustment itself needs point-in-time semantics: historical target `T` uses an `adjustment_as_of=P` view containing only actions effective and available by the generation cutoff. A vendor's later fully adjusted series must not rewrite old artifacts.
- Raw daily bars and adjusted views should therefore be separate immutable layers; adjusted-view identity includes raw derivation, as-of session, adjustment snapshot, and reference-data digest.
