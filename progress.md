# Progress Log

## Session: 2026-08-27 — Resume historical-data and R6 next stages

### Phase 17: Resume unfinished historical-data and R6 research stages

- **Status:** in_progress
- Actions taken:
  - Owner directed the PM to enter the next stage for `建立三年歷史資料` and to continue the unfinished `歷史台股回測準備度` task.
  - Re-read both live task histories. The 9960 repair is durably ACTIVE and its immediate next stage is a new immutable snapshot/Dataset verification; the overall three-year acquisition remains incomplete and no writer/heartbeat is active.
  - Re-read the merged R6 task history. Its released A2/Migration 018 package leaves active revision 2, head 0, formal attempts 0/7, revision-3 matrices 0, preflights 0, and release NOT_READY. The already-defined next stage is audit registration, CAS revision-3 activation, one seven-slot G3 preflight, independent artifact/DB verification, and Gate review.
  - Preserved the boundary that this new authorization does not include G4, Local Paper, broker, CA, order submission, or real money.
  - Resumed both original tasks. The historical-data task is performing a long local full-partition scan and semantic identity calculation for a new immutable Dataset; it has made no network request and has not yet materialized the Dataset.
  - R6 completed its merged-main read-only preflight. Formal PostgreSQL, artifact, sidecar, and runtime-copy evidence agree; coverage is `0.995893643087254413`, revision remains 2, head/attempt/preflight/audit/revision-3 counts remain zero, and release remains `NOT_READY`.
  - R6 stopped before every durable mutation because its contract requires an exact owner-approved `actor_id`. It also confirmed that application/repository use cases for audit registration and revision-3 CAS activation must be implemented, tested, and reviewed before formal PostgreSQL operations; direct SQL is prohibited.
  - Reconciled `確認三大法人策略資料`: its latest decision explicitly pauses the duplicate full Shioaji r3 history scan and routes the next offline stage through the FinMind immutable Dataset produced by `建立三年歷史資料`.
  - The institutional task completed its offline consumer plan as `WAITING_FOR_FINMIND_DATASET_AND_INSTITUTIONAL_SERIES`. It froze PR-MVP-EVAL-001 through PR-MVP-EVAL-005, with outcome generation explicitly deferred to a later authorization.
  - PM review disposition for that consumer plan is `APPROVE`: it reuses the immutable Dataset/Catalog, preserves `research_eligible=false`, never activates `ATOMIC_BACKTEST_DEFAULT`, keeps formal PIT/holdout claims blocked, and prohibits an empty or non-overlapping Evaluation Universe.
  - The only sealed institutional observation targets 2026-08-19 while the Dataset ends 2026-08-18. The preregistered evidence gate requires at least 60 overlapping target sessions; the current series therefore remains `INSUFFICIENT_EVIDENCE` even after the Dataset finishes.
  - Owner instructed the PM to continue and supervise all three non-overlap tasks. Session catch-up found no new authorization beyond the frozen Phase 17 boundaries.
  - `建立三年歷史資料` has now atomically published `dataset-finmind-sponsor-sha256-4defb3967d4e89f87d920197877358a8237cdf9baa51be1001fb156b70310ce4`, covering 453 symbols and 51,213,436 bars with the ACTIVE 9960 lineage. It is still running a single full source-versus-materialized equality audit; latest status reports zero mismatch and no activation/timestamp mutation. Do not interrupt or restart it.
  - R6 durably registered the eligibility audit and activated matrix revision 3 under exact `actor_id=SteveHuangJob`, then started exactly one G3 full-Dataset preflight. Existing supervisor state remains `RUNNING` at checkpoint `1,000,000 / 28,325,340` (3.53%), PID 21109 unchanged, zero errors/restarts, and formal attempts 0. The existing 30-minute monitor remains authoritative; no duplicate monitor was created.
  - `確認三大法人策略資料` remains correctly idle at `WAITING_FOR_FINMIND_DATASET_AND_INSTITUTIONAL_SERIES`. PM will hand off only the bounded verified Dataset identity after the equality audit passes; the independent 60-overlapping-target-session blocker remains and no Shioaji/provider/outcome/holdout work is authorized.
  - Created heartbeat automation `r6-pm` on this PM task at minute 15/45 each hour. It supervises only the three named non-overlap tasks, preserves the existing R6 monitor, performs the review/request-change/fix loop after deliverables complete, and explicitly forbids duplicate preflights, provider/trading work, G4, remote release, or intervention in the excluded readiness tree.
  - Heartbeat 2026-08-27 12:45 Asia/Taipei: the history task's full source-stream versus immutable-Dataset comparison completed successfully. All 51,213,436 bars are equal with zero mismatch, and the returned Dataset ID, manifest digest, bars digest, and saved-plan digest exactly match the first atomic publication. The owning task is synchronizing its workpad and preparing the bounded PM review candidate; approval is not inferred before that handoff.
  - The same heartbeat found no new R6 or institutional-task event. R6 remains delegated to its existing supervisor, and the institutional task stays idle until the Dataset handoff is independently approved.
  - Phase 81 delivered its bounded PM review candidate. Independent read-only review confirmed the Dataset directory, 10,596,416,681-byte bars payload, 103,340,016-byte manifest, 776,699,904-byte source snapshot, manifest file SHA-256 `d8b7426a...e7e5c07`, and snapshot-plan file SHA-256 `010d7b81...a131b5b`.
  - The first structured summary used incorrect nested paths and expanded the large partition array; no state changed. Review will continue with exact key/path probes. A 32 KiB `source.sqlite3-shm` and zero-byte `source.sqlite3-wal` remain beside the copied snapshot and require bounded immutability clarification before disposition.
  - Independent 10.596 GB payload SHA-256 equals `eadccfda...17dc`. Repository-native `DatasetManifest`, `HistoricalDatasetCatalog`, `FinMindSnapshotPlan.verify_digests`, and `verify_snapshot_plan_handoff` all accept the exact artifact and reproduce manifest digest `367f8124...02dc` plus plan digest `290d5dc5...d674`.
  - One helper search was stopped before execution by an unmatched zsh glob; no state changed. Continue with repository-root `rg` and no shell glob.
  - First review/activation digest replay used a nonexistent JSON-helper import and failed before SQLite access. No state changed; replay will call the production repair module's deterministic digest helper instead.
  - Independent replay reproduced the full review digest `f28f1fdb...367dae` and activation digest `83ca14d4...8acfed`; both stored IDs equal the first 20 digest characters.
  - Current focused validation is stronger than the handoff count: the three history/snapshot/repair modules pass `51 passed`, and adding Dataset-binding coverage passes `59 passed, 8 skipped`. No test failed.
  - Read the exact materialized JSONL row at line 43,502,747: symbol 9960, session 2026-03-20, timestamp 10:56+08:00, OHLC 22.9, volume 1, amount 22.9, TPEX. This agrees with the one-row partition metadata and full source-stream audit.
  - Phase 81 independent review disposition is `APPROVE`, P1=0/P2=0. The 32 KiB SHM sidecar has no open holder, the WAL is zero bytes, the copied DB main-file SHA equals the plan handoff evidence, and all formal verifiers pass; it is not an immutable-artifact blocker.
  - Approved two parallel bounded continuations: the history task may perform only the offline sealed-artifact rerank and create a status-only deterministic eight-symbol job before stopping for PM review; the institutional task may consume only the verified metadata identity and must remain blocked from Evaluation Universe freeze until at least 60 overlapping target sessions exist.
  - Delivered the Phase 81 APPROVE packet to `建立三年歷史資料`; its next turn is active and is restoring the isolated workpad plus deterministic-job contract before any write. It acknowledged STATUS-ONLY/no-provider scope and has not created or run a second job.
  - Delivered the exact approved Dataset/plan/selection/repair pins to `確認三大法人策略資料`; its next turn is active and is performing consumer-side exact-pin verification only, without rerunning the 51M audit or reading price/outcome payloads.
  - Bounded post-handoff wait found no error or attention-required event. R6 had no new heartbeat and remains under the existing supervisor.
  - Phase 82 delivered a PM review candidate. Independent inspection reproduces official TWSE snapshot SHA/count `efdb1688...72f69` / 1,095 rows and TPEx `4f055c3c...ce835` / 890 rows, and confirms both sealed FinMind input filenames.
  - Live immutable SQLite returns exactly one job `finmind-sponsor-3fb900f8f272077e`, expected sorted symbols, source/version/date range/calendar symbol/COMMON_LOTS, `QUEUED`, null calendar fields/status message, and zero partitions.
  - First attempts summary referenced a nonexistent aggregate column; no state changed. The attempts table records one row per request, so continue with direct row count.
  - Corrected child-count proof: the Phase 82 job has zero attempt rows and no selected symbol appears in any other history job. Production config replay reproduces full SHA-256 `3fb900f8...6c009` and exact job ID suffix.
  - Re-executed the preserved read-only `/private/tmp/finmind_phase82_rerank.py` against the same inputs. It exactly reproduces exclusion union 454, completed set 426, eight selected symbols/industries/names/markets/listing dates, and selection ordering. Full `tests/test_finmind_sponsor_history.py` passes `13 passed`.
  - Phase 82 review found one P2 provenance blocker: both official company snapshots and the selector script exist only under mutable/ephemeral `/private/tmp`; no durable data artifact binds their bytes, alias rules, exact excluded-symbol set, output, and resulting job identity. The workpad stores hashes but cannot preserve replay if temp files disappear.
  - Phase 82 disposition is `REQUEST_CHANGES`, P1=0/P2=1. Remediation must be offline-only: content-address the already verified official bytes, seal a deterministic selection manifest/bundle including exact input/output identities and selector/alias contract, verify it reproduces the existing QUEUED job, and leave the job untouched with zero calendar/partitions/attempts.
  - Phase 82 P2 remediation delivered canonical bundle self-digest `e9faeadd...7d97` plus durable official TWSE/TPEx evidence. Independent hashes match both content-addressed official filenames and `cmp` confirms byte identity to the previously reviewed temp files; the bundle is 44,624 bytes and its raw-file SHA-256 is separately `ef9a1b60...6e677`.
  - Independent verifier replay returned `VERIFIED`: 1,284 eligible symbols, 29 ranked candidates, exact selected order 4114/4438/1603/1718/1536/1702/2901/2607, config SHA `3fb900f8...6c009`, job `finmind-sponsor-3fb900f8f272077e`, and `quick_check=ok`.
  - Focused re-review passes `18 passed`; Python compilation and scoped whitespace validation pass. Live SQLite independently confirms exactly one unchanged QUEUED target row, null calendar/status fields, zero partitions, zero attempts/recorded requests, and `quick_check=ok`. Phase 82 final disposition is `APPROVE`, P1=0/P2=0; no calendar/provider stage is authorized by this approval.
  - `確認三大法人策略資料` completed PR-MVP-EVAL-001 as metadata-only. Independent workpad review and artifact inspection confirm the exact Dataset handoff, all formal/outcome/order permissions remain false, the sole institutional observation contains 17 candidates for source 2026-08-18 -> usable/target 2026-08-19, and the price Dataset ends 2026-08-18. PM disposition is `APPROVE`, P1=0/P2=0, with overlap=0 and the >=60-session gate still blocked.

## Session: 2026-08-27 — R6 A2 Migration 018 remote release

## Session: 2026-08-27 — R6 A2 Migration 018 remote release

### Phase 16: R6 A2 Migration 018 remote release

- **Status:** complete
- Actions taken:
  - Received exact owner authorization to push `codex/r6-a2-migration018-20260827@ed477898e707435036936a91afe07f3b846f4758` to `origin`, create a PR, wait for CI and final integration checks, and merge.
  - Preserved explicit exclusions: no audit registration, revision-3 activation, G3 preflight, Local Paper, broker, or real-money execution.
  - Re-activated the file-based release ledger and final code-review checklist; session catch-up confirmed the authorization was the only unsynced decision.
  - Re-froze the clean isolated worktree: branch `codex/r6-a2-migration018-20260827`, HEAD `ed477898e707435036936a91afe07f3b846f4758`, parent/merge-base/local `origin/main` `7931d31e53657c4f28e684402589c2b20501c1d9`, ahead exactly one commit, and tree `f130410c7757fa803ac1e36f6a762f9edd8ca5a2`.
  - Live remote read confirms GitHub `main@7931d31` and no existing `codex/r6-a2-migration018-20260827` branch. The first sandboxed DNS attempt failed without state change; approved read-only network retry succeeded.
  - The original task pushed the exact branch and opened PR #6, `https://github.com/f23934073/tw_intraday_trader/pull/6`. PM readback confirms `base=main`, `head=ed477898`, one commit, 38 reviewed files, `MERGEABLE`, and preserved forbidden-stage boundaries.
  - Initial CI run `33034860434` produced PostgreSQL Journal `SUCCESS`, Python 3.11 `FAILURE`, and Python 3.12 still running at first observation. Merge was blocked and PM issued `REQUEST CHANGES` to the owning task.
  - Failed log shows two Linux-only unit-test setup failures: both macOS launchd behavior tests reach the production `sys.platform != darwin` guard before their simulated assertions. Result was `2 failed, 1661 passed, 69 skipped`; the production guard must remain and the tests must explicitly simulate macOS while retaining Linux-guard coverage.
  - PM inspected the staged remediation directly. It touches only `tests/test_supervise_atomic_entry_benchmark_preflight.py`: two simulated launchd tests set `supervisor.sys.platform` to `darwin`, and one new regression proves `linux` still raises `requires macOS`. Production code is unchanged; remediation review disposition is `APPROVE`.
  - Owning task committed and pushed the approved remediation as `aced00adf19cad54d0cec7c399f0d6f5ea67d624`; the branch is clean and exactly two commits ahead of its original base. New CI run is `33035130214`.
  - During CI, `origin/main` advanced independently to `9ab43c353fd4fd11b085bc94b08d78a605e603d6` through PR #5, making R6 `4 behind / 2 ahead`. PM tightened final integration: the green PR run must prove its merge ref includes latest base `9ab43c3`, or the integration check must be refreshed before merge.
  - Remediation CI run `33035130214` completed green: Python 3.11 `SUCCESS`, Python 3.12 `SUCCESS`, PostgreSQL Journal `SUCCESS`; PR #6 reports `CLEAN/MERGEABLE` with base `9ab43c3` and head `aced00a`.
  - Live merge ref `e69630f6ccd3b83d408ad0ba7a41b1d28c8151f8` has exact parents latest main `9ab43c3` and approved R6 head `aced00a`. The pull-request workflow uses default `actions/checkout@v4`, so final latest-main integration gate is approved and merge authority was sent to the owning task.
  - PR #6 merged at `2026-08-27T03:04:50Z` as `d5b86382c06a34e3a26ba2b23e3d714c783f0348`. Remote `main` now equals that SHA; both original package `ed477898` and remediation `aced00a` are ancestors, and the isolated branch worktree is clean.
  - Post-merge `main` push CI run `33035268279` completed `SUCCESS` for Python 3.11, Python 3.12, and PostgreSQL Journal. The owning `歷史台股回測準備度` task completed and stopped at the authorized release boundary.
  - No audit registration, revision-3 activation, G3 preflight, Local Paper, broker, or real-money execution was performed.

## Session: 2026-08-27 — Idle/not-loaded task reconciliation

### Phase 15: Idle and not-loaded Codex task reconciliation

- **Status:** complete
- Actions taken:
  - Owner corrected the PM inventory: Codex `idle` and `notLoaded` conversations may still be unfinished, so active-process status is insufficient.
  - Re-activated `planning-with-files`, restored the current plan, ran session catch-up, and confirmed the primary checkout remains a broad dirty shared workspace that must not be used as an integration unit.
  - Started a full visible task inventory that will read candidate conversations and preserve the explicit non-overlap boundary around `評估實盤交易就緒差距`.
  - Read the latest logical task lines for Institutional r3, STE-5, the old branch audit, Kill Switch/Tax-Slippage delivery, and three-year history repair. Identified two real repository continuations outside the direct readiness child tree: Institutional r3 awaits provider-scan authority; the 9960 history repair awaits independent review.
  - Received a readiness-supervisor update for No-Overnight and recorded it only as an exclusion boundary; no action was taken in that task.
  - Classified the old branch-audit task as superseded and both Local Paper implementation tasks as completed/merged despite `notLoaded` UI state. Classified STE-5 as one logical externally blocked issue represented by many follow-up conversations.
  - Read the latest R6 owner and reviewer tasks. R6 packaging is now clean, independently approved, and locally review-ready at `ed477898`, while G3 activation is still explicitly not part of that branch.
  - Counted visible tasks: 52 UI entries, 46 Codex tasks, 21 current-repository conversations, and 25 STE-5 follow-up conversations representing one blocked external issue.
  - Started PM review of exact R6 commit `ed477898` and the 9960 source-repair candidate. Confirmed R6 scope/ancestry/cleanliness and froze the prior review evidence; inspected the candidate file set without approving or activating it.
  - Inspected R6 static risk patterns and the complete 9960 candidate manifest/validation plus its review-vs-activation state machine. Candidate reconciliation is internally consistent so far; durable DB identity and test replay remain before disposition.
  - PM independently reran the exact R6 focused suite: `94 passed, 28 skipped`. Reviewed Migration 018's additive/schema-only boundaries and A2's reserve/audit contract tests; no new P1/P2 has appeared.
  - Located the live 9960 source-repair DB and exact pending evidence id. Next review checks will use read-only SQLite and file-digest verification before recording any decision.
  - Read-only DB inspection confirmed `PENDING_REVIEW`, exact candidate evidence identity, zero reviews, and zero activations. Logged one non-mutating query error for a guessed active-bar table name and will use the actual schema on the next check.
  - Verified compressed DB evidence bytes against the sealed raw capture and canonical bar digests after decompression. `PRAGMA quick_check` passed, original partition remains immutable `EMPTY`, and focused repair tests passed `15/15`.
  - Confirmed the 9960 Fugle conversion is not a blanket relaxation: the missing-turnover path is accepted only for an official single flat-price transaction, while multi-transaction or amount/volume mismatches fail closed; closing-auction `13:30` remains unshifted.
  - Rechecked the exact R6 payload with `git diff --check`; it remains whitespace-clean and the isolated review worktree remains clean after the focused tests.
  - Completed independent R6 PM review with no P1/P2 findings. Exact `ed477898` passed `94 passed, 28 skipped`, production compilation, four CLI help smoke checks, whitespace validation, and clean-worktree verification; disposition is local `APPROVE`, with push/PR/merge and G3 still unauthorized.
  - Recorded review-only approval for the 9960 candidate as `finmind-repair-review-f28f1fdb50e78806a1df` under reviewer `Codex PM independent review`. Post-review status is `APPROVED`, activation remains null, active bar count remains zero, source-repair audit verifies 1/1 with zero issues, and SQLite `quick_check=ok`.
  - Confirmed through current Fugle documentation that minute candles use lots for whole-lot equities and that `turnover` is available only for daily/weekly/monthly candles; this supports the narrow offline single-transaction reconciliation without weakening other cases.
  - Returned both PM approvals to their original task conversations and waited for completion. `歷史台股回測準備度` recorded `LOCAL RELEASE-READY` and stopped before remote release/G3; `建立三年歷史資料` recorded `APPROVED_AWAITING_OWNER_ACTIVATION` and stopped before activation/provider access.
  - Final non-overlap blockers are now explicit: R6 needs a scoped remote-release sentence; 9960 needs a named actor/change note for one-case activation; Institutional r3 needs the exact `啟動 r3 scan` provider authorization; STE-5 remains one externally blocked Linear issue despite many UI follow-up boxes.

## Session: 2026-08-27 — Active branch and Codex-task PM reconciliation

### Phase 14: Active branch, PR, and Codex-task reconciliation

- **Status:** in_progress
- Actions taken:
  - Received authority to act as PM across active tasks: inspect unmerged branches, map them to their Codex conversations, resume idle incomplete work, review completed work, route requested changes, merge only approved work, and continue authorized next stages.
  - Activated `planning-with-files` for durable reconciliation state and `openai-docs` for current Codex task-workflow grounding.
  - Restored the existing root planning files and preserved every prior evidence and production-safety gate.
  - First session catch-up attempt used a non-existent global virtualenv interpreter; reran successfully with system `python3` and made no product or Git state change.
  - Captured the first local Git/worktree/ref snapshot. The primary checkout is dirty and its local `main` has diverged (`ahead 19, behind 4`), so it is not a safe integration surface.
  - Found ten registered worktrees and multiple branch families requiring task ownership and reachability review. The local-paper tax/slippage branch already appears in the recorded `origin/main` merge commit and will not be merged twice.
  - The first Codex task-list request exceeded the API's 50-item maximum. It made no state change; the supported bounded retry is next.
  - Retried the task list with the supported limit and identified the active branch-owning worktree tasks, the active shared-checkout historical-data tasks, and the unloaded STE-5 PR task.
  - The first sandboxed remote fetch and GitHub PR query failed on `.git/FETCH_HEAD` permissions and network isolation. Scoped approved retries succeeded.
  - Verified PR #2 is already merged with all three checks green. At this point PR #1 was still open with all three checks green but no review decision; its state changed during the later review preflight as recorded below.
  - Recomputed local-branch reachability against the freshly fetched `origin/main`. The six PR-NO stage branches and the old Trade Management Shadow runtime branch are unmerged stale-lineage work; the three new integration/evidence branches still equal current main while their tasks work in uncommitted state.
  - Polled eight active repo tasks. No-Overnight integration, Shadow fill.v3 compatibility, and slippage calibration are actively implementing; D-HEALTH OPEN remains in a safe pre-arm automation remediation; the prior branch-audit task is only waiting on approval and overlaps this PM task.
  - During the PR #1 review preflight, its GitHub state changed from OPEN to MERGED. Fetched and verified `origin/main@33c9b3a` contains PR head `e80f577`; the merge was performed by `Steve_project`, all three CI checks passed, and GitHub still records no review decision.
  - Sent post-merge cleanup to the STE-5 task, told the superseded branch-audit task to perform no merge/push/delete action, and instructed the three active branch tasks to incorporate `origin/main@33c9b3a` before their final review while preserving their current scope and gates.
  - Updated the existing readiness-supervisor task with the same coordination boundary: monitor and report task outcomes, but do not duplicate starts, bypass review, or merge early.
  - Inspected all registered worktree statuses. The three active integration/evidence tasks are isolated and dirty in their own worktrees; merged/stale stage worktrees are clean; the primary checkout remains a broad dirty shared workspace and is not an integration surface.
  - Confirmed `歷史台股回測準備度` is actively executing the A2 request-change/fix/re-review loop and has not crossed into source-only full audit or Migration 018 prematurely.
  - Read the remaining task handoffs. Stopped the active three-year-data task from using an accidentally exposed Fugle credential and set it to offline-only pending owner rotation.
  - Confirmed today's Trade Management C0 failed closed with no C1, the Freshness/Portfolio continuation requires separate real-environment authority, and the one-shot PR-NO-006 DISABLED baseline is already under read-only heartbeat monitoring.
  - Reviewed the completed but unpublished `bd020b5` docs commit and its lineage. Rejected standalone cherry-pick because its documented runtime dependencies are absent from current main; rejected wholesale old-branch merge because the unreviewed integration delta is broad and cross-task.
  - Grouped the 19 local-main-only commits into R5 replay, Trade Management Shadow/C1, r3 price coverage, and R6 benchmark families; none may be integrated as a single broad local-main push.
  - Received acknowledgements from the three active isolated tasks that they will sync `33c9b3a` and rerun validation before final review. Shadow focused compatibility and legacy tests are currently green, but no branch is approved yet.
  - The superseded branch-audit task ended without mutation. STE-5 is performing post-merge Linear/workpad reconciliation and is using the documented script fallback after direct writes were denied.
  - STE-5 post-merge cleanup finished. It could not update Linear through either direct write or fallback, so the issue remains truthfully `In Progress`; GitHub PR #1 itself remains independently verified merged.
  - D-HEALTH-LATE-001 OPEN task completed the one-shot local-runner scheduling implementation without an early provider attempt. Started an independent review gate over its runner, plist, and tests before accepting the 2026-08-28 schedule.
  - D-HEALTH review round 1 found a P1 mutable-runtime gap: launchd points at uncommitted code in the shared dirty checkout and the claim does not bind source content. Continued review will verify the post-capture automation timing before issuing the complete request-change packet.
  - Completed D-HEALTH review round 1 as `REQUEST CHANGES`. Sent the P1 source-pinning remediation back to the owning task with instructions to unload the current zero-run LaunchAgent, preserve read-only automation, use a clean pinned runtime, add an adversarial drift test, and return for re-review without executing the capture.
  - D-HEALTH accepted the P1 request changes, unloaded the mutable LaunchAgent at `runs=0`, verified no one-shot artifacts exist, and created clean branch `codex/d-health-open-pinned-20260828` at `33c9b3a`. Remediation is active and no capture has run.
  - Verified `建立三年歷史資料` obeyed the credential stop: it made no Fugle/Shioaji request, completed 13 offline tests, retained `QUARANTINED`, and ended `BLOCKED_PENDING_CREDENTIAL_ROTATION`.
  - The one-shot source audit in `歷史台股回測準備度` reached EOF and reported all `28,325,340` bars with `99.589%` eligible coverage, above the `0.95` gate. It is performing a second read-only artifact verification before Migration 018; no second scan is permitted.
  - Shadow synchronized `origin/main@33c9b3a` and passed the new-main full suite (`1507 passed, 43 skipped`), while keeping PostgreSQL not passed. Its self-review found and fixed two evidence-quality defects; independent adversarial review is pending.
  - Slippage calibration completed a fail-closed dry run with `0/42` required groups qualified and no derived metrics from unqualified sessions; full/static/diff validation is active.
  - Shadow adversarial review returned `REQUEST_CHANGES` with four P2 findings and no P1. Routed all four back for fix/re-review; no commit or merge is allowed yet.
  - Detected a real cross-task overlap in `trading/postgres_journal.py` and `tests/test_postgres_journal_unit.py`. Notified Shadow, No-Overnight, and the supervisor of the semantic-integration order and required reruns.
  - Migration 018's first disposable PostgreSQL regression hit environment disk exhaustion and was not counted as pass. After bounded recovery, no-DSN `1735 passed, 88 skipped` and disposable PostgreSQL `26 passed`; Migration 018 was applied transactionally and the post-check preserved active revision 2, head 0, attempts 0, and zero revision-3 activation records.
  - Shadow closed-loop re-review returned APPROVE (P1=0/P2=0) and produced clean local commit `47a9303`. PM independently reviewed its exact diff and reran `26 passed`, compilation, and whitespace checks with no new P1/P2.
  - The managed approval gate rejected the attempted push of the approved Shadow branch to `origin`, requiring explicit owner confirmation for that exact private-code payload/destination. Stopped without workaround; no PR or merge was created.
  - Sent No-Overnight the exact approved Shadow commit so its overlapping PostgreSQL reader diff can be integrated semantically and retested while the remote-push authority is resolved.
  - Received explicit owner authority to push exactly `codex/shadow-fill-v3-compat-20260827@47a9303da0db26a17dd553488901af8caa423a55` to the named GitHub origin, create a PR, wait for all CI checks, and merge into `main`.
  - Re-fetched `origin/main@33c9b3a` and completed the exact-payload preflight: the Shadow worktree is clean, branch/HEAD/remote all match the authorization, the branch is `0 behind / 1 ahead`, base ancestry passes, and the diff has no whitespace errors.
  - Pushed the exact branch successfully and created GitHub PR #3. The head commit remains `47a9303da0db26a17dd553488901af8caa423a55`; merge is waiting on all CI checks.
  - PR #3 CI completed Python 3.11 and 3.12 successfully, but PostgreSQL Journal failed three tests because `TIMESTAMPTZ` normalized `+08:00` records to UTC and the new read-integrity check compared offset-sensitive fingerprints. Classified the result as REQUEST_CHANGES and kept merge blocked.
  - Scoped the remediation to PostgreSQL storage/reconstruction: preserve the domain fingerprint and immutable historical rows, bind new stored fingerprints to the original aware timestamp, and retain bounded legacy UTC/Taipei verification.
  - Implemented and re-reviewed the two-file remediation. Focused tests passed `31 passed, 3 skipped`; the full suite initially hit two sandbox-only artifact write errors, then passed `1515 passed, 44 skipped` with isolated writable data paths. Compilation and diff checks passed.
  - Committed the fix as `f6a38b1` and pushed it to the same PR #3 branch. GitHub is rerunning all CI checks; merge remains blocked until the new run is fully green.
  - Detected that `Steve_project` had already merged PR #3 externally at 02:14:42Z while PostgreSQL Journal was failed and before `f6a38b1` reached the PR head. Fetched `origin/main@023a082`, verified it contains `47a9303`, and confirmed the branch-to-main forward diff is now only the reviewed two-file fix.
  - Chose a non-destructive forward-fix PR instead of rewriting or reverting remote main. The follow-up merge remains gated on a fresh all-green CI run.
  - Created forward-fix PR #4 at head `f6a38b1`. Its first remote run passed both Python jobs and reduced PostgreSQL from three failures to one outdated corruption-error expectation.
  - Updated both PostgreSQL corruption UAT assertions to require the new earlier `JournalConflictError`, committed as `254317b`, and pushed it for a third full CI run. Local focused tests passed `31 passed, 4 skipped`; compile and diff checks passed.
  - PR #4 third run passed Python 3.11, Python 3.12, and PostgreSQL Journal. It merged as `7931d31`; fetched remote main and verified ancestry for the original authorized `47a9303`, implementation fix `f6a38b1`, UAT fix `254317b`, and final merge commit.
  - Notified the owning `Shadow fill.v3 相容性整合` task, the dependent `No-Overnight 新版整合與 PostgreSQL UAT` task, and the readiness supervisor. No-Overnight is continuing from current main with semantic overlap reconciliation and fresh tests.
  - Preserved the dirty primary checkout unchanged; it remains unsuitable for direct integration.
  - Started a fresh post-`7931d31` inventory at the owner's request. Session catch-up found no missing release action; the next snapshot will re-fetch remote refs and reconcile branches, PRs, worktrees, and live task states without mutating the dirty primary checkout.
  - Owner narrowed this PM scope to exclude `評估實盤交易就緒差距`. Read that referenced task only to establish its ownership boundary; it supervises the Shadow, No-Overnight, and slippage-calibration child tasks. Those tasks are now excluded from this PM's inventory actions and follow-ups.
  - Refreshed all remote refs successfully after the earlier user interruption. `origin/main` remains `7931d31`; no remote branch is currently unmerged.
  - Recomputed local reachability and worktrees. Outside the excluded readiness tree, the remaining branch candidates are `codex/r6-a2-migration018-20260827@ce8e9b6` and `codex/d-health-open-pinned-20260828@8d3747f`; dirty local `main` remains a non-mergeable mixed workspace.
  - Polled the R6 owner task. Its 32 focused PostgreSQL cases pass, while four broader Journal fingerprint failures on newest main are being isolated against detached `origin/main`; the task is active and the branch is not ready for review or merge.
  - Inspected the D-HEALTH branch: clean at `8d3747f`, six commits ahead and five commits behind current main, with no open PR. Live owner/review mapping is still required before any integration action.
  - Re-read the referenced readiness conversation across all available pages. It explicitly includes R6/historical readiness and continued Freshness supervision, so R6 and D-HEALTH are overlap and have been removed from this PM's actionable set.
  - Final non-overlap result: no open PR, no unmerged remote branch, and no active or resumable Codex task remains for this PM. Dirty divergent local `main` is not a valid integration unit; all other unmerged named branches are excluded readiness lineages.
- **Status:** complete
  - Slippage calibration round-one review returned REQUEST_CHANGES with 3 P1/3 P2; all six fixes and a second independent review remain required.
  - D-HEALTH returned `READY FOR RE-REVIEW` at clean local HEAD `0bb2ee2`, provider attempts 0 and `runs=0`. PM round-two review found the pinned runtime has no credential source and would waste the single claim; sent a new P1 request-change packet requiring a secret-safe external credential boundary and auditable provider-zero failures.
  - Restarted the completed A2/Migration 018 task in its original conversation to package only its owned payload onto current main. The clean branch passed focused `94/94` and full no-DSN `1588 passed, 70 skipped`; disposable PostgreSQL review is active and R6 G3 remains blocked until this branch is reviewed and merged.
- Next:
  - Re-review D-HEALTH after immutable-runtime remediation; then review Shadow and slippage when their owning tasks return final dispositions. Continue monitoring No-Overnight and the Migration 018 gate without duplicating or rerunning work.

## Session: 2026-08-19 — Basic strategy expansion implementation

### Phase 10: Implement basic strategy expansion

- **Status:** in_progress
- Actions taken:
  - Received explicit authorization to implement the approved basic-strategy expansion plan.
  - Activated `planning-with-files` and `karpathy-guidelines`; success criteria are the Phase 10 checklist plus the approved plan Gates.
  - Restored session context and confirmed substantial unrelated worktree changes already exist in historical-download/provider/planning files.
  - Scoped edits to the strategy/backtest/catalog/dashboard surfaces and will preserve unrelated modifications, especially existing README and download/provider work.
- Verification target:
  - Focused new tests pass, full existing suite passes, JavaScript/static/whitespace checks pass, and no Shioaji order or CA path exists in the changes.

## Session: 2026-08-19 — Basic strategy expansion plan

### Phase 9: Basic strategy expansion implementation plan

- **Status:** complete
- Actions taken:
  - Confirmed the request is implementation-plan only; no strategy runtime changes are authorized.
  - Read and activated the `planning-with-files` workflow.
  - Restored the repository's prior planning context and session catch-up output.
  - Reconfirmed the inherited safety boundary: historical research and local paper simulation only; no broker orders or real-money execution.
  - Inventoried the current strategy catalog, executable registry, historical bar contract, deterministic next-bar engine, and focused strategy/backtest tests.
  - Identified the minimum architectural gap: rolling/session/position feature state must be added before the five proposed strategies can be deterministic and reusable.
  - Recorded unrelated existing worktree modifications and limited this task to non-overlapping planning Markdown.
  - Reviewed the existing realtime feature engine and rejected direct reuse for historical Kbars because its input, freshness, and provenance contracts are Tick-specific.
  - Confirmed the existing strategy catalog/API/UI can expose additional fixed-version strategies without a new route or strategy-specific parameter form.
  - Found a blocking capability gap: intraday strategies can currently be selected without a trustworthy per-symbol bar cadence or `required_capabilities` preflight.
  - Scoped the fix to explicit manifest/capability validation plus bounded rolling state; a full streaming backtest rewrite remains outside this plan.
  - Rechecked primary/authoritative sources for ORB, moving-average/trading-range rules, EMA/BBANDS/RSI/ATR definitions, and current TWSE session/cost context.
  - Chose dependency-free Decimal indicator contracts with explicit warm-up semantics rather than adding TA-Lib as a runtime dependency.
  - Authored `architecture/basic_strategy_expansion_implementation_plan.md` with fixed strategy contracts, P0 data gates, engine/context design, phased delivery, migrations, tests, rollout, rollback, and Definition of Done.
  - Kept all five new strategies `EXPERIMENTAL`, preserved legacy default selections, and explicitly excluded broker/real-money execution.
  - Structural validation passed; the first whitespace check found one extra blank line at EOF, which was removed before final verification.
  - Final checks passed: all five strategy IDs and required sections are present, code fences are balanced, and Markdown whitespace checks are clean.
  - Verified this task changed planning Markdown only; no strategy, engine, API, UI, provider, or test implementation was performed.
- Planned output:
  - `architecture/basic_strategy_expansion_implementation_plan.md`
- Files modified so far:
  - `task_plan.md`, `progress.md`, `findings.md` (planning records only)

## Session: 2026-08-18

### Phase 1: Requirements and proposal intake

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - Confirmed the request is review-and-plan only.
  - Read the required planning and code-review skill instructions.
  - Checked memory for relevant project constraints and verified the initial Git state.
  - Created the persistent planning files required for this review.
  - Read the first 520 lines of the attached proposal and inventoried repository files/directories.
  - Identified the first scope conflict: proposed live-money phases versus the inherited research-only boundary.
  - Finished the supplied proposal and read the repository README plus the first portion of the architecture report.
  - Identified that risk admission needs to be mode-independent and that the current system is decision support, not yet an execution system.
- Files created/modified:
  - `task_plan.md` (created)
  - `findings.md` (created)
  - `progress.md` (created)

### Phase 2: Repository architecture trace

- **Status:** complete
- Actions taken:
  - Started tracing current source and test contracts.
  - Inspected current orchestration, latest-snapshot store, provider/config packaging, Candidate/Scoring/Position modules, and dashboard service.
  - Confirmed that current scans are stateless snapshots and positions are manually seeded demonstration data.
  - Read the full market-data provider and data models; recorded timestamp, streaming-contract, client-ownership, and order-normalization gaps relevant to Replay/Simulation.
  - Compared the architecture report's intended Backtest/Shadow/Data Health evolution with the proposed broker-first roadmap.
  - Audited current tests and identified missing deterministic Replay, state-machine, idempotency, persistence, and recovery coverage.
  - Verified Simulation capabilities, callback semantics, odd-lot/emerging-stock exclusions, API limits, subscription cap, and the prohibition on polling snapshot/history APIs as a realtime feed against current official Shioaji documentation.
  - Inspected current settings and packaging boundaries; corrected the SDK constraint evidence to `shioaji>=1.7,<2`.
  - Read the existing dashboard planning record, confirmed its read-only/manual-refresh boundary, and ran the full baseline test suite (`64 passed`).
  - Verified the active Shioaji SDK version (`1.7.2`) and current official pending-submit/order-lot/CA requirements.
  - Completed the optimization review and fixed the target sequence: deterministic data -> decision/risk/journal -> shared Backtest/Replay -> live-data Shadow -> manual Simulation -> automated Simulation.
  - Authored `architecture/execution_layer_v1_implementation_plan.md` with scope, architecture contracts, phased tasks, gates, tests, rollback, file map, and official Shioaji references.
- Files created/modified:
  - None.

### Phases 3-5: Optimization, plan authoring, and verification

- **Status:** complete
- Actions taken:
  - Prioritized proposal changes against current code, tests, prior constraints, and current official Shioaji documentation.
  - Wrote the standalone implementation plan and added exact gates, test strategy, rollback, and file map.
  - Verified the plan includes the current 40-point score ceiling, strict RVOL semantic gap, no-live scope, read-only dashboard boundary, official callback/limit behavior, and no product implementation.
- Files created/modified:
  - `architecture/execution_layer_v1_implementation_plan.md` (created)
  - `task_plan.md`, `findings.md`, `progress.md` (planning records only)

### Phase 6: Web Simulation and Portfolio Plan Extension

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - Restored prior planning context and confirmed the worktree still contains planning artifacts only.
  - Captured the new requirements: manual web simulation orders, purchased-stock information, and a future automated-order path.
  - Chose a shared backend command pipeline so browser and strategy orders cannot bypass safety or audit controls.
  - Inspected the current FastAPI routes, DashboardService, tests, and existing holdings drawer.
  - Confirmed the UI can reuse its current holdings surface, but must replace demo-position data with simulation PortfolioProjection and add a separate order ticket/order-status view.
  - Updated the implementation plan with simulation-only API routes, UI fields, mode/security gates, web acceptance tests, and rollback behavior.
  - Updated automated Simulation so strategy orders reuse the same OrderApplicationService and appear with manual orders in one order/portfolio projection.
  - Verified this turn changed planning Markdown only and did not implement product code.
- Files created/modified:
  - `task_plan.md`, `findings.md`, `progress.md` (updated planning records)
  - `architecture/execution_layer_v1_implementation_plan.md` (pending update)

### Phase 7: Local web paper simulation implementation

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - User authorized implementation after reviewing the plan.
  - Restored the planning context with the installed session catch-up helper.
  - Scoped the first deliverable to an explicitly labelled, session-local paper simulator: no Shioaji authentication, no broker order SDK calls, and no live-money route.
  - Defined verification targets: idempotent manual orders, separately projected orders and holdings, existing regression compatibility, and UI disclosure of local/session-only behaviour.
  - Inspected the current FastAPI/dashboard contracts, package configuration, README, and static dashboard structure. Confirmed that scan positions are hard-coded demo data, so simulation state will be returned in a separate projection without breaking existing scan tests.
  - Verified that the installed FastAPI test client is unavailable because its expected `httpx2` dependency is absent; will use focused service tests without changing dependencies for this feature.
  - Added focused service/API-contract tests. The first API test attempt triggered `ShioajiProvider` from the ambient provider setting and hit a Python 3.13 native-extension segmentation fault; tests now explicitly inject `MockProvider` so they do not initialize external SDK code.
  - Fixed the first focused-test failure: a new sell order was counted as its own pending reservation before availability validation, causing every sell to be rejected. The availability check now excludes the order currently being validated.
  - Implemented the dashboard order drawer, local order blotter, simulation holdings drawer, candidate-to-ticket prefill, and browser-side local projection refreshes.
  - Ran JavaScript syntax validation and dashboard/service tests (`10 passed`). Started the dashboard with `MockProvider` and visually verified the accessible candidate-to-order-ticket flow; no browser test order was submitted.
  - Documentation patch initially used an incorrect project-tree context and was rejected without modifying README; will re-read the exact README sections and apply a scoped replacement.
  - Updated README and the implementation plan with the explicit local-paper semantics and the remaining Shioaji scope.
  - Completed final regression and syntax checks: `71 passed`; dashboard JavaScript syntax check passed; `git diff --check` passed.

### Phase 8: Shioaji Tick/BidAsk simulation quote updates

- **Status:** complete
- **Started:** 2026-08-18
- Actions taken:
  - User explicitly authorized replacing manual snapshot refreshes with Shioaji Tick/BidAsk subscriptions.
  - Restored the existing planning context and preserved the uncommitted local-simulation implementation.
  - Scoped the change to market data: local paper orders stay local and no Shioaji order API is authorized.
  - Defined initial verification targets: bounded dynamic subscriptions, callback normalization, ask/bid fills, browser projection updates, stale-state visibility, and full regression compatibility.
  - Inspected the current `StockData`, `SimulationService`, simulation models/tests, provider tests, package bounds, and installed Shioaji package layout.
  - Chose a separate normalized streaming-quote model to avoid expanding the general Candidate/scoring snapshot contract.
  - Verified the installed 1.7.2 type stubs and current official stock-streaming callback/subscribe documentation.
  - Added the internal `RealtimeQuoteUpdate` contract and Shioaji callback/subscription lifecycle.
  - Changed Shioaji login to `subscribe_trade=False`; this stream slice still does not register order callbacks or call order APIs.
  - Added the simulator quote worker, separate Tick/BidAsk ordering, best ask/bid fill logic, bounded-symbol subscription synchronization, stream health projection, and shutdown cleanup.
  - Added a unified local simulation projection endpoint so browser refreshes do not call Shioaji snapshot/account APIs.
  - Updated the browser to poll only the local projection every two seconds while visible, show stream/wait/error state, and display latest trade plus best bid/ask and quote time.
  - First compile and focused compatibility run passed (`10 passed`), confirming the existing MockProvider simulation and snapshot provider contracts remain intact before adding stream-specific tests.
  - Added stream-specific tests for callback normalization, idempotent paired subscriptions, BidAsk fills, Tick marking, per-stream ordering, cancellation unsubscribe, and the unified API projection.
  - Completed a real Shioaji 1.7.2 login/callback/close smoke with `streaming=True` and no stream error.
  - Real 4946 Tick/BidAsk subscriptions were acknowledged, but the 10-second observation window contained no quote event; will retry callback payload verification with a more liquid symbol.
  - Real 2330 provider smoke received both normalized Tick and BidAsk updates.
  - Browser UI showed `Shioaji 即時行情`, one active subscription, and advancing quote time after a local 2330 order; however the marketable order remained pending, reproduced in a standalone service smoke. Investigation remains active.
  - Confirmed the pending test was correct: live best bid/ask was 2380/2385 while the test BUY limit was 2000. A 3000 local-paper limit filled at ask 2385, then Tick marked the position at 2380 with -5,000 unrealized PnL; UI displayed current bid/ask and quote time with no console errors.
  - Browser-driven local test state was discarded when the test server stopped.
  - Added explicit Provider close/logout and confirmed a second real FastAPI shutdown completed without the prior native-thread warning.
  - Re-reviewed the final provider/service/API/frontend paths and preserved unrelated concurrent momentum/signal worktree changes.
  - Final compile, complete regression, JavaScript parse, and whitespace checks passed (`100 passed`).
- Errors encountered:
  - Attempted a non-existent `check-session.sh` helper before reading the installed skill; switched to the documented `session-catchup.py` helper.

### Phase 13: Freshness Calibration Evidence

- **Status:** in_progress
- **Started:** 2026-08-19
- Actions taken:
  - Restored the completed repository planning context and opened a calibration-only phase.
  - Confirmed the user-approved baseline: P0-1 through P0-14 and Fee/Rounding remain frozen; only FreshnessPolicyV1 may change after evidence review.
  - Activated data-quality review for eight independent thresholds and separated quote/executable data from broker/account evidence.
  - Preserved the existing market-data-only boundary: no Portfolio Phase 1, broker order, CA, trade callback, or real-money path is authorized by this task.
  - Located reusable quote evidence seams: normalized `RealtimeQuoteUpdate`, the data-only Shioaji quote capture, digest-validated artifacts, and parity qualification utilities.
  - Identified the initial collection gap: no implemented broker/account read capture path exists in the current market-data-only runtime, so those four thresholds cannot be derived from quote data.
  - Inspected the two existing 20-second parity artifacts: one has no callbacks and the other has clock-skew observations but lacks store, connection, liquidity, and session evidence. Neither can support a threshold.
  - Completed safe-seam tracing: calibration will subscribe Tick/BidAsk only, record an explicit in-memory evidence-store boundary, and retain source clock skew rather than attempting a product-side change.
  - Added an immutable `freshness_calibration_quote_v1` artifact path, offline
    analysis, and a bounded Tick/BidAsk-only CLI. It never imports Portfolio,
    order, or account APIs and its analysis explicitly has no threshold output.
  - Revalidated old captures: `8039` has zero observations; `2330` has 116
    observations with 96 negative source-latency values. The report therefore
    retains `BLOCKING_EVIDENCE` for all eight thresholds.
  - Rendered and validated the technical initial evidence report with the two
    collection gaps as a partial snapshot.
  - Verification passed: 16 focused calibration/parity/artifact tests, CLI
    help, compilation, artifact inspection smoke test, and whitespace check.
- Files created/modified:
  - `task_plan.md` (Phase 13 added)
  - `findings.md` (calibration requirements and initial decisions added)
  - `progress.md` (this entry added)
  - `market_data/freshness_calibration.py` (data-only capture and analysis)
  - `scripts/capture_quote_freshness.py` (bounded capture CLI)
  - `tests/test_freshness_calibration.py` (focused contract tests)
  - `research/freshness_calibration/README.md` (capture and review runbook)

### Phase 13a: Calibration collection preparation

- **Status:** in_progress
- **Started:** 2026-08-19
- Actions taken:
  - User authorized the non-Phase-1 preparation slice only: cohort/session protocol, non-sensitive capture preflight, data-quality checklist, and a read-only broker/account intake checklist.
  - Restored the active plan and reconfirmed the dirty worktree has broad unrelated strategy/dashboard changes; this slice will remain isolated to calibration artifacts and tests.
  - Ran a non-sensitive local preflight: Shioaji SDK and both credential
    categories are present, and the host offset matches `Asia/Taipei`; no secret
    values or network/broker calls were made.
  - Revalidated the current stream cap and data-only login path. Found a
    reusable SDK lifecycle callback seam that must be captured as evidence.
  - Confirmed the lifecycle model has explicit disconnect/reconnect and
    subscription acknowledgement/failure states; capture work will add those
    provenance records before the next live run.
  - Confirmed the tested SDK lifecycle callback codes needed for a conservative
    calibration lifecycle record.
  - Added lifecycle provenance to the data-only quote capture. A configured
    symbol remains `PENDING` until both Tick (`TIC`) and BidAsk (`QUO`) SDK
    acknowledgements arrive; disconnect/reconnect and raw lifecycle inputs are
    persisted for later review.
  - Published reviewer-facing cohort/session manifest, preflight/review
    checklist, and broker/account read-only intake. They establish collection
    readiness only; no liquidity tier, threshold, or broker adapter was added.
  - Verification passed: JSON template validation, 25 focused tests, CLI help,
    compilation, and whitespace check.

### Phase 13b: Live quote discovery capture

- **Status:** in_progress
- Actions taken:
  - At 2026-08-20 09:05 Asia/Taipei, started a 120-second data-only live
    Tick/BidAsk capture for `2330`, labelled `discovery` rather than assigned
    an unsupported liquidity tier.
  - The sandbox blocked the SDK native client before it could create a
    subscription; reran the identical capture in the approved local runtime.
  - Produced `research/captures/freshness_quote/quote_20260820T090534+0800.json`.
    Its initial review has 494 observations (474 BidAsk, 20 Tick), no missing
    stream kind, and no proposed threshold.
  - Source event timestamps exhibit material clock skew (353/474 BidAsk and
    20/20 Tick observations with a negative event-to-callback value), so this
    capture must be retained as raw evidence rather than treated as an SLA.
  - A read-only post-capture NTP sample recorded host-clock provenance
    (`+58.825 ms +/- 53.094 ms`); it neither adjusted the clock nor established
    the provider event-clock offset required to interpret source latency.
  - Wrote the durable review at
    `research/freshness_calibration/reviews/2026-08-20_0905_discovery_review.md`.
    It records lifecycle success, collector-buffer timing, data-quality limits,
    and the unchanged evidence gates without proposing a threshold.
  - Regression and hygiene verification after capture/reporting passed:
    25 focused freshness/capture/stream tests and `git diff --check`.

### Phase 13c: Qualified cohort provenance

- **Status:** in_progress
- Actions taken:
  - Restored planning context after the discovery capture and reconfirmed the
    only remaining work is Freshness Calibration Evidence.
  - User authorized continued intraday evidence work. Began an auditable cohort
    selection path based on official prior completed-session trading value,
    rather than inferred liquidity or callback outcomes.
  - Validated the downloaded 2026-08-19 official TWSE multi-table response and
    derived the fixed 1,086-row completed-session universe. Its p10/p50/p90
    trade-value anchors are `1530`/`6863`/`2886`; manifest creation and paired
    stream acknowledgement will occur before qualifying their first capture.
  - Frozen and JSON-validated
    `cohort_manifest_2026-08-20_twse_2026-08-19.json`; the saved source SHA-256
    matches the inspected official snapshot. Captured the frozen three-symbol
    cohort for ten minutes in the `opening` window after a read-only NTP
    preflight (`+54.431 ms +/- 49.857 ms`).
  - Initial collector review reports 1,048 observations across all six
    required symbol/stream groups. Artifact digest, timestamp range, lifecycle,
    per-row state, and data-quality disposition are the next verification step.
  - Inspection found a calibration-harness state-propagation defect: all six
    groups retain `CONNECTED/PENDING` despite per-symbol paired acknowledgements.
    The 09:16 artifact is immutable raw evidence but excluded from qualified
    threshold review. Will add a multi-symbol lifecycle test, repair only the
    capture instrumentation, then recapture with the same frozen manifest.
  - Repaired lifecycle state propagation and added a multi-symbol regression;
    focused calibration tests now pass (`7 passed`). A 70-second opening
    recapture verified `CONNECTED/ACTIVE` rows after all paired acknowledgements
    (digest `65edf0a…1c110b`). It is partial coverage only: high has Tick/BidAsk,
    mid has BidAsk, and low has no callbacks in that short window.
  - Next: run the unchanged frozen cohort in the `continuous` window and retain
    any sparse low-tier behavior as data quality / coverage evidence.
  - Completed the 15-minute `continuous` capture. Artifact
    `quote_20260820T093046+0800.json` passed digest/schema, paired-ack, complete
    six-group coverage, ACTIVE-state, error, timestamp, and monotonic checks;
    it has 1,513 observations. Published its data-quality review at
    `research/freshness_calibration/reviews/2026-08-20_0930_continuous_review.md`.
  - The review retains all eight thresholds as unset: sparse mid/low Ticks are
    real observed cadence, source clock skew remains unresolved, and broker /
    account capture remains separately unavailable.

### Phase 13d: Close-window scheduling and evidence readiness

- **Status:** in_progress
- Actions taken:
  - Restored the active calibration plan after the continuous capture; its next
    valid quote window is 13:00–13:30 Asia/Taipei.
  - Inspected the app automation capability. The first read used an unsupported
    action field; the tool returned the valid `view/create/update/delete` mode
    contract. Will inspect existing automation state before adding any one-time
    close-window heartbeat.
  - Confirmed no matching existing automation. Created and verified one active,
    one-time thread heartbeat named `Freshness close-window capture` for the
    remaining 13:00–13:30 close window. Its prompt is limited to NTP provenance,
    frozen-cohort Tick/BidAsk collection, artifact review, and planning records;
    it explicitly prohibits broker/account/order/CA/trade-callback APIs and
    Portfolio Phase 1.
- Next:
  - The heartbeat will perform the close-window capture. Continue to preserve
    the independent broker/account evidence blocker until a read-only source
    and environment are explicitly authorized.
  - Wrote `research/freshness_calibration/reviews/2026-08-20_campaign_checkpoint.md`
    after cross-artifact quality checks. It keeps discovery, lifecycle-rejected,
    partial-opening, and qualified-continuous files explicitly segregated and
    records zero duplicate callback keys, out-of-range callback times, or
    callback errors across the current campaign artifacts.
  - Final pre-close verification passed: 26 focused calibration/capture/stream
    tests, manifest JSON validation, and `git diff --check`.
- Next:
  - Acquire and validate the official completed-session source snapshot, freeze
    the derived cohort manifest, and only then run qualified quote captures.
- Next:
  - Verify digest, lifecycle acknowledgement state, and raw schema before
    deciding whether the capture qualifies only as discovery evidence or
    exposes a harness defect.

### Phase 13e: Independent continuous repeat sample

- **Status:** in_progress
- Actions taken:
  - Performed a read-only NTP preflight before the second continuous sample;
    selected host offset was `+47.647 ms +/- 48.080 ms`. This is provenance only
    and did not adjust the system clock or calibrate source event time.
  - The capture control channel returned before its child process completed;
    process inspection found two duplicate retries. Stopped only those later
    duplicate data-only subscriptions and retained the earliest process as the
    sole sample. The retained capture ran 900.514 seconds.
  - Validated `quote_20260820T095444+0800.json`: SHA-256
    `7c937d32d3fc48f46307b880d2feda58e3f1d5449b020f2da1ad12fdd339638c`,
    schema `freshness_calibration_quote_v1`, 1,621 observations, paired
    Tick/BidAsk acknowledgement, six-group coverage, all ACTIVE rows, zero
    callback errors, zero monotonic regressions, zero duplicate composite keys,
    and zero receipts outside the capture interval.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_0954_continuous_repeat_review.md`
    and updated the campaign ledger. The repeated low/mid Tick silence confirms
    only that Tick silence cannot itself signal stale executable data; every
    quote threshold remains unset and all broker/account thresholds remain
    separately blocked.
- Next:
  - Preserve the active 13:00 close-window heartbeat; do not add a second
    heartbeat or change its frozen collection scope.

### Phase 13f: Continued calibration collection

- **Status:** in_progress
- Actions taken:
  - User requested uninterrupted progress. Reconfirmed the sole authorized
    scope is Freshness Calibration Evidence: Tick/BidAsk-only quote artifacts
    may be collected and profiled, while Portfolio Phase 1, account/order/CA /
    trade-callback APIs, and any broker freshness inference remain prohibited.
  - Reapplied the campaign's data-quality method: treat the event grain as one
    callback observation; validate lifecycle state, paired acknowledgements,
    duplicate composite keys, receipt range, timestamp skew, and coverage
    separately from inter-arrival distributions. Preserve each sample as a
    separate artifact rather than pooling it into a threshold claim.
- Next:
  - Start the next non-overlapping continuous sample under the unchanged frozen
    manifest, then inspect it with the same gates. The existing one-time close
    heartbeat remains the only scheduled collection task.

### Phase 13g: Third continuous repeat sample

- **Status:** in_progress
- Actions taken:
  - Ran the unchanged 15-minute Tick/BidAsk-only cohort capture following a
    read-only NTP preflight. The selected host offset was `+33.583 ms +/-
    53.005 ms`; two NTP exchanges timed out but successful samples remained,
    and no system-clock change was made.
  - Validated `quote_20260820T101439+0800.json`: SHA-256
    `181a59b0d9fbd378a70b638f659b0d854a8e5e74b29dd6c2cceeedb321accd6f`,
    1,872 observations, six-group coverage, paired acknowledgement, all
    `CONNECTED/ACTIVE`, zero callback errors, monotonic regressions, duplicate
    composite keys, and out-of-range receipts.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_1014_continuous_third_review.md`
    and updated the campaign ledger. The three same-day continuous samples
    demonstrate material low/mid Tick sparsity while the subscription remains
    active; all thresholds remain unset.
- Next:
  - Continue only through the existing 13:00 close-window heartbeat. Before
    freezing quote thresholds, obtain qualified opening and close coverage,
    multi-day repetition, and source-clock disposition; obtain a separate
    authorized broker/account evidence source for the other four thresholds.

### Phase 13h: Morning continuous data-quality synthesis

- **Status:** in_progress
- Actions taken:
  - Confirmed the active close-window heartbeat remains scheduled for 13:00 and
    is restricted to the frozen cohort and quote-only APIs.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_morning_continuous_data_quality_summary.md`.
    It records event grain, integrity/lifecycle gates, per-sample volume,
    cadence variation, clock limitation, and the separate broker/account gap.
    It neither pools same-day samples into a cutoff nor proposes a threshold.
- Next:
  - Wait for the scheduled close capture and apply the identical quality gate.

### Phase 13i: Pre-close cross-artifact integrity review

- **Status:** in_progress
- Actions taken:
  - Performed a read-only profile of all six immutable quote artifacts. It found
    6,665 total observations, zero duplicate composite callback keys within or
    across artifacts, zero callback receipts outside each artifact range, and
    zero callback errors.
  - Corrected the campaign ledger wording from four to six reviewed artifacts.
    The 09:16 all-PENDING artifact remains explicitly rejected for its known
    instrumentation defect; integrity success does not qualify it as threshold
    evidence.
- Next:
  - Continue only with the scheduled close capture and its separate artifact
    review. P1 remains blocked until the full FreshnessPolicyV1 gate is frozen.

### Phase 13j: Morning evidence reviewer disposition

- **Status:** in_progress
- Actions taken:
  - Recorded the reviewed `PASS` disposition for the morning continuous data:
    collector/lifecycle integrity passed; morning cadence is qualified evidence;
    Tick-only executable-health is rejected; the connection/subscription-plus-
    BidAsk direction is supported without selecting a duration threshold.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_morning_reviewer_disposition.md`
    and linked its detailed status ledger from the campaign checkpoint. No
    collector, cohort, Portfolio contract, risk implementation, or P1 code was
    changed.
- Next:
  - Preserve the scheduled close capture and continue the unchanged measurement
    protocol. P1 remains blocked pending close/multi-session/clock disposition
    plus independently authorized broker/account evidence.

### Phase 13k: Evidence-chain execution order freeze

- **Status:** in_progress
- Actions taken:
  - Recorded the approved execution order: close-window quote evidence,
    cross-session quote evidence, source-clock disposition, then a separately
    authorized broker/account evidence campaign.
  - Added an explicit implementation guardrail: while `FreshnessPolicyV1` is
    not frozen, do not create migrations, Portfolio core, RiskGate freshness
    code, provisional thresholds, or broker/account API calls.
- Next:
  - The active 13:00 heartbeat remains the immediate next action. A qualified
    close artifact will extend evidence only and cannot independently unblock
    Phase 1.

### Phase 13l: Scheduled close-window collection

- **Status:** in_progress
- Actions taken:
  - The one-time close-window heartbeat triggered at 13:00 Asia/Taipei.
    Reconfirmed the evidence-only boundary: unchanged frozen cohort, Tick/
    BidAsk callbacks with `subscribe_trade=False`, no account/order/CA/
    trade-callback API, no execution, and no Portfolio Phase 1.
- Next:
  - Record read-only NTP provenance, run one 15-minute close capture, then
    validate its immutable artifact before assigning any evidence disposition.

### Phase 13m: Close-window artifact review

- **Status:** in_progress
- Actions taken:
  - Performed read-only NTP provenance before the 13:01 close capture. The
    selected offset was `+32.587 ms +/- 53.185 ms`; successful samples and
    timeout attempts are retained without changing the system clock.
  - Validated `quote_20260820T130116+0800.json`: SHA-256
    `1994292cc3c9868952567283f9dc7b02a8ada8dca03a05e7c131872c8e3aed70`,
    2,092 observations, paired acknowledgement, all ACTIVE rows, zero callback
    errors, zero monotonic regressions, zero duplicate composite keys, and zero
    receipts outside range.
  - Published
    `research/freshness_calibration/reviews/2026-08-20_1301_close_review.md`.
    It is partial close evidence: 1530/Tick has no callback and the 13:01–13:16
    capture ends before the 13:30 market/session boundary. It cannot complete
    the close gate or select a threshold.
- Next:
  - On later completed sessions collect complete close-regime evidence that
    covers the documented session transition, then repeat all regimes across
    dates. Keep broker/account evidence separate and await explicit read-only
    authorization. Phase 1 remains blocked.

### Phase 13n: 2026-08-21 cross-session close collection

- **Status:** in_progress
- Actions taken:
  - A close-window heartbeat triggered for a second completed trading date.
    Reconfirmed the frozen cross-session protocol and the no-Portfolio/no-
    broker-accounting boundary before collection.
- Next:
  - Run one 15-minute close Tick/BidAsk capture, validate its artifact against
    the unchanged quality gate, and retain it as separate date/regime evidence.
  - Session catch-up identifies a broad pre-existing dirty worktree that includes
    product and P1-adjacent paths. Preserve it entirely; this heartbeat remains
    limited to the freshness artifacts, reviews, and planning records.
  - NTP preflight recorded five successful read-only samples (selected
    `+54.899 ms +/- 95.187 ms`) before the 13:01 capture. No system-clock change
    was made and source event time remains outside SLA selection.
  - Validated `quote_20260821T130144+0800.json`: SHA-256
    `d00da28a50d2df53fa120c43a1aebf91cfa1baecca91705f590067898977469e`,
    1,497 all-ACTIVE observations, paired acknowledgement, zero callback errors,
    monotonic regressions, duplicate composite keys, and out-of-range receipts.
  - Published
    `research/freshness_calibration/reviews/2026-08-21_1301_close_review.md`
    and `2026-08-21_cross_session_close_checkpoint.md`. The close sample is
    partial (5/6 callback groups, no 1530 Tick) and ends at 13:16 before the
    13:30 session boundary; it adds cross-session qualitative evidence only.
- Next:
  - Do not infer or implement a threshold. Future work needs a complete
    boundary-crossing close protocol, full cross-date regime evidence,
    source-clock disposition, and separately authorized broker/account reads.
    Phase 1 remains blocked.
  - The one-time heartbeat unexpectedly triggered on a second day despite its
    `COUNT=1` rule. Its configuration still reports `ACTIVE`. Two system-tool
    pause attempts (full then minimal payload) stalled without state change and
    were terminated; no automation file was edited directly. Treat any future
    automated capture as requiring explicit user confirmation until the app
    automation service can be updated successfully.

### Phase 13o: recurring trading-session scheduling (2026-08-22)

- **Status:** in_progress
- User authorized scheduling only the quote-evidence collection campaign.
- Confirmed the existing close heartbeat is still active and its 13:00 trigger
  cannot produce the required 13:30-boundary observation. The replacement
  campaign will use the unchanged cohort/schema/quality gates, require an
  explicit open-session check, and schedule opening, continuous, and
  boundary-crossing close observations. It remains Tick/BidAsk-only with
  `subscribe_trade=False`; broker/account collection and all Portfolio work
  remain excluded.
- The native automation service is unavailable (`No handler registered`), after
  two prior pause attempts stalled. Repository inspection found the reviewed
  `ReviewedEquityCalendar` and confirmed that the raw quote CLI does not
  enforce cohort/calendar/window constraints. Next: add a small testable
  runner that validates all of those constraints before loading the quote
  capture path, then install a local scheduler only after verification.

### Phase 13o: runner and launchd definition verified (2026-08-22)

- Added `market_data/freshness_calibration_schedule.py` and the
  `scripts/run_scheduled_quote_freshness.py` CLI. A reviewed-calendar decision
  happens before manifest parsing, NTP, and any live-capture callable. The
  runner permits only the frozen 2886/6863/1530 cohort, requires five
  read-only NTP successes, and leaves a JSON outcome record for every run.
- Added an exact macOS launchd definition with three starts: 09:15 opening,
  10:00 continuous, and 13:15 close (20 minutes to observe the 13:30
  boundary). It delegates to the runner, which remains the calendar gate.
- Verification: `plutil -lint` passed; focused schedule/freshness/calendar
  tests passed (`14 passed in 0.08s`); a 2026-08-22 Saturday CLI smoke wrote
  `NO_CAPTURE_NON_TRADING_DAY` without running NTP or Shioaji; `git diff
  --check` passed.
- Next: copy/bootstrap the verified user-level LaunchAgent and inspect its
  loaded state. This is the only remaining scheduling step; it does not
  authorize broker/account evidence or Portfolio Phase 1.

### Phase 13o: launchd installed and smoke-verified (2026-08-22)

- Installed the verified plist at
  `/Users/stevehuang-work/Library/LaunchAgents/com.stevehuang.tw-intraday-trader.freshness-calibration.plist`
  and bootstrapped it as the current user. `launchctl print` confirms the
  09:15, 10:00, and 13:15 calendar triggers, working directory, Taiwan time
  zone, and one subsequently completed smoke run.
- The manual smoke intentionally ran at 09:47 rather than a scheduled minute.
  It wrote `NO_CAPTURE_OFF_SCHEDULE`, contained no NTP preflight field, and
  did not initialize Shioaji. This validates the installed service follows the
  same fail-closed runner. A separate CLI smoke already proved the scheduled
  Saturday path returns `NO_CAPTURE_NON_TRADING_DAY` without provider work.
- Phase 13o is complete. Future expected behavior is data-only artifacts on
  reviewed trading days; every artifact still requires the existing quality
  review. The Mac must remain logged in and awake around the configured times;
  a late wake fails closed rather than backfilling a different market window.

### Phase 13p: accelerated quote cadence (2026-08-22)

- **Status:** in_progress
- User requested an earlier completion path. The safe in-scope response is to
  increase same-day quote observations only: add one opening and two
  continuous 15-minute windows while preserving the frozen cohort, collector,
  schema, and quality gates. Cross-date evidence, source-clock disposition,
  broker/account evidence, threshold review, and Portfolio Phase 1 remain
  unchanged gates.
- Updated the runner and launchd definition, then verified `plutil -lint`,
  focused evidence tests (`15 passed in 0.05s`), and `git diff --check`.
  Rebootstrapped the same user-level LaunchAgent; `launchctl print` confirms
  all six expected triggers. No quote capture was manually started and no
  broker/account API was called.
- **Status:** complete

### Phase 13q: automated post-capture evidence QA (2026-08-22)

- **Status:** in_progress
- User authorized completing remaining in-scope work. The next slice reuses
  existing immutable artifact inspection to emit per-capture quality summaries
  and fail closed on a structurally invalid artifact. It is evidence tooling
  only: thresholds remain unset, final review stays human-owned, and no
  broker/account or Portfolio path is introduced.
- Inspected the artifact schema and retained close evidence. The QA summary can
  check all required structural dimensions from immutable fields: digest/schema,
  per-symbol TIC/QUO acknowledgement, per-row lifecycle state, six-group
  coverage, callback errors, monotonic regressions, and source-clock skew.
- Initial QA tests exposed a stale hard-coded schema string in the new fixture;
  no live capture ran. The fixture now imports the collector's schema constant
  before verification is retried.
- The first correction used the similarly named quote-parity schema rather than
  the Freshness collector schema. Located the collector-owned constant and
  corrected the fixture import; no artifact or live API call occurred.
- QA verification passed (`17 passed in 0.09s`) and a Saturday scheduler smoke
  again returned `NO_CAPTURE_NON_TRADING_DAY` without NTP or provider work.
  Backfilled structural QA over all eight retained artifacts and published
  `research/freshness_calibration/reviews/2026-08-22_post_capture_qa_backfill.md`.
  Results agree with prior review and retain all thresholds as unset.
- Added an immutable-byte recheck before summary generation and a regression
  test that invalid evidence raises without rewriting the raw file. Final
  verification passed: focused QA/schedule/freshness/calendar tests
  `18 passed in 0.06s`; Saturday smoke remained `NO_CAPTURE_NON_TRADING_DAY`;
  `git diff --check` passed. Phase 13q is complete.

### Phase 13r: broker/account read-only evidence (2026-08-22)

- **Status:** in_progress
- The owner explicitly authorized read-only broker/account freshness evidence
  and confirmed local Shioaji credentials exist. The approved boundary is
  positions, accounting, and account/buying-power-like reads only; it excludes
  submit, cancel, CA, trade callbacks, and action-like order refresh.
- Started a separate evidence-only design rather than changing the existing
  market-data provider or Portfolio surfaces. The artifact will be redacted
  and integrity-checked; all thresholds remain unset.
- An initial code-path audit found no current broker/account freshness adapter.
  It also confirmed that a locally cached order list cannot establish broker
  order freshness without the excluded provider refresh, so that evidence kind
  will be retained as an explicit availability constraint.
- The worktree contains broad unrelated product, dashboard, backtest, strategy,
  and planning changes across 45 files. Phase 13r will create only its new
  calibration module/script/tests/docs and will not reformat or absorb those
  concurrent changes.
- Restored the active Phase 13 evidence context for the one-time frozen close
  heartbeat. The worktree remains broadly dirty and the heartbeat scope is
  quote-only; this execution will neither use nor modify the new broker/account
  collector, and it retains every threshold as unset.
- Frozen close heartbeat disposition: host time was `2026-08-22 13:01 +08:00
  Sat`, so the reviewed calendar requires `NO_CAPTURE`. Completed the required
  five read-only NTP samples (each selected a valid source; +0.405 to +0.407
  ms offset) but did not initialize Shioaji or enter any quote/account/order/CA
  path. Published
  `research/freshness_calibration/reviews/2026-08-22_1301_close_no_capture_review.md`;
  no quote artifact exists and all artifact-quality checks are N/A rather than
  treated as pass.
- Second frozen close heartbeat disposition: host time was `2026-08-23 13:00
  +08:00 Sun`, again a reviewed non-trading day. The required five read-only
  NTP samples all selected valid sources (+0.595 to +0.601 ms offset), but no
  provider path was entered. Published
  `research/freshness_calibration/reviews/2026-08-23_1300_close_no_capture_review.md`;
  the result remains `NO_CAPTURE`, no quote artifact exists, and all thresholds
  stay unset.
- Trading-day frozen close heartbeat disposition: the host clock was
  `2026-08-24 17:00 +08:00 Mon`, after the close session, rather than the
  heartbeat's 13:02 window. Five read-only NTP samples selected valid sources
  (+0.0367 to +0.0373 ms), but the capture ended `NO_CAPTURE_OFF_SESSION`
  before Shioaji import/login or any quote/account/order/CA operation.
  Published
  `research/freshness_calibration/reviews/2026-08-24_1700_close_no_capture_review.md`;
  no quote artifact exists and all thresholds remain unset.
- Inspected the installed Shioaji 1.7.2 method signatures without logging in.
  The synchronous, callback-free read signatures are available for positions,
  profit/loss, and account balance; `update_status` exists but remains
  explicitly out of scope because it refreshes order state. The configured
  `SJ_SIMULATION` runtime value must be captured as an environment label rather
  than guessed from existing quote artifacts.
- Reconfirmed the quote collector's evidence conventions: immutable exclusive
  JSON creation, a SHA-256 inspector, timezone-aware receipt timestamps, and
  explicit limitations. Phase 13r will use the same integrity/redaction shape
  in a separate module rather than extend the quote schema with account data.
- Added the separate broker/account collector, CLI, capture contract, and
  isolated fakes. Focused verification passed: `22 passed in 0.09s` across the
  new capture and existing quote/calendar evidence tests; Python compilation
  and scoped `git diff --check` also passed. No Shioaji login or broker/account
  endpoint was called during this verification.
- Corrected the CA-required classification so a provider rejection is retained
  as `CA_REQUIRED_BUT_PROHIBITED` rather than being overwritten by the separate
  buying-power limitation. Focused tests still pass (`22 passed in 0.08s`).
- First Saturday CLI smoke failed before SDK import/login because it referenced
  a non-existent calendar constructor. No provider call, credentials, or
  account data was involved; the exact failure is logged in `task_plan.md` and
  needs the established calendar-loading path before a different retry.
- Reused the established `ReviewedEquityCalendar.from_path(...)` construction
  and reran the smoke. It returned `NO_CAPTURE_NON_TRADING_DAY` at
  2026-08-22 10:21 +08:00 with `provider_called=false`; focused tests still
  passed (`22 passed in 0.07s`). This proves the collector fails closed before
  importing Shioaji or reading credentials on a closed date.
- Reviewed the existing local quote launchd shape. Phase 13r will use a
  separate user-level job and a calendar/time-gated wrapper, so a late wake or
  manual off-window invocation cannot silently become an unlabelled broker
  evidence sample. The accelerated plan is five short, non-overlapping
  observations per reviewed trading day: 09:35, 10:30, 11:30, 12:30, and 13:20
  Asia/Taipei. Each sample has three endpoint calls and one explicit orders
  gap; it stays far below the documented burst limit because calls are spaced
  through the session.
- Added the separate broker/account scheduler, scheduled runner, five-window
  launchd template, contract/README update, and fail-closed schedule tests.
  Verification passed: `24 passed in 0.09s`, Python compilation, plist syntax,
  and scoped whitespace validation. A Saturday 09:35 scheduled smoke wrote a
  `NO_CAPTURE_NON_TRADING_DAY` run record with `provider_called=false`; it did
  not import Shioaji or read credentials.
- Installed `/Users/stevehuang-work/Library/LaunchAgents/com.stevehuang.tw-intraday-trader.broker-account-freshness.plist`
  as the separate user-level service
  `com.stevehuang.tw-intraday-trader.broker-account-freshness`. `launchctl`
  confirms all five exact calendar triggers, the repository working directory,
  and the bounded runner command. It has `runs=0` and remains inactive until a
  future trigger; installation itself made no Shioaji login, account read,
  callback, CA, order, or cancellation call.
- Rechecked the capture choices against the current primary Shioaji accounting
  and order-status documentation. It confirms that positions/profit-loss reads
  support synchronous no-callback calls and that fresh `Trade` status requires
  the intentionally excluded `update_status`. `account_balance` reports a
  settlement-account balance and a provider query-time field, not a documented
  buying-power authority.

### Phase 13s: Quote-evidence scheduler hardening (2026-08-24)

- Diagnosed the missed 10:00 continuous window: the scheduler accepted only an
  exact minute, so its 10:01 invocation correctly but unhelpfully ended
  `NO_CAPTURE_OFF_SCHEDULE`.
- Added a bounded five-minute late-launch grace to each frozen quote window.
  Every accepted run retains its original session label and immutable duration,
  and records the planned timestamp plus measured launch delay. A later launch
  still makes no NTP or provider call.
- Replaced the relative launchd command with absolute paths; the runner now
  changes to its own repository root. Removed the launchd `WorkingDirectory`
  setting after proving it produced `getcwd` errors in this environment.
- Focused scheduler tests passed (`10 passed in 0.07s`), Python compilation,
  plist syntax validation, and `git diff --check` passed. A non-session
  launchd smoke exited 0 as `NO_CAPTURE_OFF_SCHEDULE` and produced no new
  stderr output. No Shioaji provider, broker/account, order, CA, or Portfolio
  path was entered.
- **Status:** complete

### Phase 13t: Frozen close-window evidence (2026-08-25)

- Completed five read-only NTP preflight invocations without changing the
  system clock. Each selected a successful source; the evidence is host-clock
  provenance only.
- Captured the frozen three-symbol Tick/BidAsk-only close observation through
  `scripts/capture_quote_freshness.py`, with `subscribe_trade=False` and no
  account/order/CA/trade-callback API. The immutable artifact is
  `quote_20260825T130132+0800.json`, covering 13:01:32–13:16:32 +08:00.
- Offline integrity and structural QA passed for digest/schema, six paired
  acknowledgements, 1,037 `CONNECTED/ACTIVE` rows, zero callback errors, and
  zero callback monotonic regressions. Coverage is 5/6 because `1530/TICK`
  has no callback; source-clock skew is retained in 962 rows.
- Published
  `research/freshness_calibration/reviews/2026-08-25_1301_close_review.md`.
  It records partial early-close evidence only: the sample ends before 13:30,
  no threshold is selected, and broker/account evidence remains separate.
- The direct capture continued after its interactive launcher returned. A
  temporary duplicate-prevention job was stopped before producing another
  artifact, and the normal daily quote scheduler was restored. No threshold or
  Portfolio code changed.
- **Status:** complete

### Phase 13v: Frozen close-window evidence (2026-08-26)

- Completed five read-only NTP preflight invocations without changing the
  system clock. Each selected a successful source; the evidence is host-clock
  provenance only.
- Captured the frozen three-symbol Tick/BidAsk-only close observation through
  `scripts/capture_quote_freshness.py`, with `subscribe_trade=False` and no
  account/order/CA/trade-callback API. The immutable artifact is
  `quote_20260826T130256+0800.json`, covering 13:02:56–13:17:56 +08:00.
- Offline integrity and structural QA passed for digest/schema, six paired
  acknowledgements, 1,695 `CONNECTED/ACTIVE` rows, zero callback errors, and
  zero callback monotonic regressions. Coverage is 5/6 because `1530/TICK`
  has no callback; source-clock skew is retained in 1,649 rows.
- Published
  `research/freshness_calibration/reviews/2026-08-26_1302_close_review.md`.
  It records partial early-close evidence only: the sample ends before 13:30,
  no threshold is selected, and broker/account evidence remains separate.
- A one-shot launchd job completed with exit `0`; its temporary plist was
  removed and the normal daily quote scheduler was restored. No threshold or
  Portfolio code changed.
- **Status:** complete

### Phase 13w: Post-session cross-evidence verification (2026-08-26)

- **Status:** in_progress
- Resumed the evidence-only workflow after the 2026-08-26 close capture.
- Preserved the existing dirty worktree and scoped this pass to immutable
  calibration artifacts, evidence scheduling, and planning/review records.
- Detected scheduled broker/account artifact candidates for 2026-08-25 and
  2026-08-26. They will be structurally inspected before being treated as
  evidence; no new broker request has been made in this verification pass.
- Inspected ten broker/account artifacts offline. All satisfy the immutable
  artifact schema and no-mutation guardrails, but all ten show
  `POSITIONS=AUTH_DENIED`, `ACCOUNTING=SOURCE_ERROR`, an unsupported
  buying-power endpoint, and the already-declared orders gap. They provide
  reproducible failure evidence, not usable broker freshness observations.
- Inspected the ordinary quote scheduler configuration: the 13:15 close
  window lasts 1,200 seconds and reaches 13:35. The earlier 13:02 heartbeat
  artifact was a separate 900-second one-shot capture, so its 13:17 end does
  not indicate a scheduler defect.
- Re-ran the schedule decision with the existing runner's calendar factory:
  13:15 and bounded-late 13:20 are both permitted `close` captures with the
  same 1,200-second duration. The initial wrong calendar-helper import was not
  retried.
- Published
  `research/freshness_calibration/reviews/2026-08-26_post_session_cross_evidence_review.md`.
  The result is not a threshold review pass: quote evidence remains
  regime/date incomplete and every broker/account evidence kind remains an
  explicit unavailable or unsupported source gap.
- **Status:** complete

### Phase 13x: Frozen close-window evidence (2026-08-27)

- Completed the bounded Tick/BidAsk-only capture and review; coverage is 5/6
  because `1530/TICK` is absent. All thresholds remain unset.

### Phase 13u: Minimum viable passive-capture qualification (2026-08-25)

- Added structured raw-market callback quarantine to the Shioaji Momentum adapter while retaining the existing canonical Tick/BidAsk validation.
- Added exclusive, checksummed `callback_quarantine.json` persistence and read-back verification to passive late-delivery capture.
- A fully accounted quarantine now yields `COMPLETE_WITH_WARNINGS`, exact replay `PASS`, CLI `PASS_WITH_WARNINGS`, and exit 0. Unaccounted or identity-mismatched callback errors remain `INCOMPLETE`; replay truth is `NOT_RUN` until invoked.
- Added daily warning-session reporting with passive-capture v1 compatibility, and versioned the new report contracts as passive-capture v2 and daily v3.
- Focused verification passed (`27 passed`); final full regression passed (`1390 passed, 41 skipped`). Python compilation and scoped `git diff --check` passed.
- No live market-data capture was run. The earlier 2026-08-25 CLOSE session remains immutable and failed; no qualification or P1.2 gate was claimed or changed.
- **Status:** complete

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Initial scope check | `git status --short --branch` | Clean starting tree | `main...origin/main`, no changes | Pass |
| Baseline regression | `.venv/bin/python -m pytest tests/ -q` | Existing tests pass | 64 passed in 0.10s | Pass |
| Local SDK evidence | Read installed package metadata | Determine active Shioaji version | 1.7.2 | Pass |
| Plan scope audit | Git status | Only Markdown planning artifacts changed | Four untracked `.md` files; no application/config/test changes | Pass |
| Local simulation service and API contracts | Focused pytest files | Fill, idempotency, pending/cancel, sell constraints, dashboard projection | 7 passed | Pass |
| Dashboard compatibility | Focused service/API/dashboard pytest files | Existing snapshot behavior remains intact | 10 passed | Pass |
| Full regression | `.venv/bin/python -m pytest tests/ -q` | All existing and new tests pass | 71 passed in 0.22s | Pass |
| Dashboard JavaScript | Node parser | Static script parses | Passed | Pass |
| Local UI interaction | MockProvider dashboard | Candidate action opens prefilled local order ticket | Passed | Pass |
| Stream-focused regression | Fake streaming provider plus fake Shioaji SDK | Normalize callbacks, pair subscriptions, ask/bid fills, Tick marking, ordering, cancellation and close | 5 stream tests plus related simulation/API tests passed | Pass |
| Real Shioaji callback smoke | Shioaji 1.7.2 simulation environment, `subscribe_trade=False` | Receive Tick and BidAsk without any broker order API | Both callback kinds received for 2330 | Pass |
| Real dashboard flow | Local 2330 paper BUY with live Shioaji market data | Pending below ask; fill above ask; position marks from Tick | 2000 remained pending; 3000 filled at 2385; marked 2380 with -5,000 PnL | Pass |
| Graceful shutdown | Initialized Shioaji dashboard then stop FastAPI | Cancel subscriptions and logout without native panic | Clean application shutdown | Pass |
| Final regression | Full current `tests/` suite | All repository tests pass | 100 passed in 0.31s | Pass |
| Final static checks | Python compile, dashboard JavaScript parse, `git diff --check` | No syntax or whitespace errors | Passed | Pass |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-08-18 | No-match `rg` stopped later chained reads | 1 | Reissued reads independently and captured all required instructions. |
| 2026-08-18 | `check-session.sh` did not exist in the installed planning skill | 1 | Used the documented `session-catchup.py` helper. |
| 2026-08-18 | FastAPI test client expected unavailable `httpx2` | 1 | Used focused direct route-contract tests rather than adding an unrelated dependency. |
| 2026-08-18 | Ambient Shioaji provider initialization segfaulted under Python 3.13 in a test | 1 | Explicitly injected MockProvider in local API tests; did not exercise external SDK code. |
| 2026-08-18 | Initial README patch had an incorrect project-tree context | 1 | Re-read exact sections and applied a scoped patch. |
| 2026-08-18 | Stream PnL test observed `400.0000000000057` instead of exact `400.0` | 1 | Changed the test to `pytest.approx`; no production logic change was needed. |
| 2026-08-18 | Sandboxed Shioaji smoke could not bind an inter-thread fd | 1 | Re-ran the read-only market-data smoke with approved execution; login/callback setup/close succeeded. |
| 2026-08-18 | Live dashboard shutdown emitted a Shioaji native-thread panic after FastAPI stopped | 1 | Added explicit Provider close/logout to the application lifespan and a focused close test. |

### Phase 13x: One-shot OPEN external runner

- **Status:** complete
- **Started:** 2026-08-27
- Actions taken:
  - User selected a one-shot local runner: allow loopback bind from the first attempt, use launchd when unattended Codex cannot pre-authorize it, prohibit sandbox-first retry, and preserve all evidence-only contracts.
  - Activated `planning-with-files` and `karpathy-guidelines`; restored the existing planning context without starting a provider session.
  - Inspected the active Codex cron, existing launchd quote runner/plist, and dirty worktree. Confirmed the implementation must avoid overlapping broad concurrent changes and must replace the provider-executing cron before the local one-shot job is armed.
  - First automation view call used the unsupported `automationId` key and failed without changing state; the corrected `id` call returned without error.
  - Verified the code-owned OPEN window is 09:00-09:30 with a ten-minute pre-connect allowance; retained 08:55 as the one-shot launch time.
  - Confirmed the host time was already 09:10 on 2026-08-27; did not start or arm an immediate same-day capture.
  - Confirmed 2026-08-28 is the next reviewed trading day and found an existing tested `O_EXCL` one-shot claim pattern suitable for launchd duplicate prevention.
  - Added the date-frozen launchd plist, one-shot runner, and focused tests. The runner claims the attempt before calendar/provider work, invokes only the frozen relative command, preserves stdout/stderr and exit code, and rejects any second attempt.
  - Focused verification passed: `6 passed`, Python compilation, `plutil -lint`, and scoped `git diff --check`.
  - The first full-field automation update returned without error, but a direct readback showed every persisted field unchanged. No launchd job has been installed, so duplicate-provider execution remains impossible while the control-plane update is resolved.
  - A schema-correct `kind=cron` update also returned without persistence. `computer-use` cannot control the Codex app by policy, so the UI fallback is unavailable. Stopped control-plane retries and retained the no-install safety boundary.
  - Built and TOML-validated an exact replacement for the existing automation, saved the original under `/private/tmp`, installed the replacement with scoped elevated permission, and verified persisted readback. The Codex task is now a single read-only 09:35 artifact inspection and cannot execute the provider command.
  - Post-install schedule review caught that `DAILY;COUNT=1` would fire today before the target capture. Corrected the staged configuration to a Friday-only one-shot before any automation or provider execution.
  - Installed and bootstrapped the reviewed LaunchAgent. Readback shows the exact absolute runner path, 2026-08-28 08:55 calendar trigger, `runs=0`, and no one-shot claim/result artifacts.
  - Final focused verification passed: 27 related runner/capture/stream tests, Python compilation, launchd plist lint, scoped whitespace checks, and schedule readback. No provider command ran during implementation.

### Phase 13y: Immutable OPEN runtime remediation

- **Status:** complete
- **Started:** 2026-08-27
- Actions taken:
  - Received an independent `REQUEST CHANGES` review identifying the shared dirty checkout and incomplete runtime identity as a P1 blocker.
  - Unloaded `com.stevehuang.tw-intraday-trader.d-health-late-001-open-20260828` before any provider attempt. Verified the prior loaded state had `runs=0`, the service is now absent, no one-shot artifacts exist, and the Codex inspection automation remains read-only.
  - Verified the requested reviewed base resolves exactly to `origin/main@33c9b3ab9d3b8300221e47b11685dfc24d7a5e51`; the shared checkout remains `ahead 19, behind 6`, and the selected dedicated branch name is free.
  - Created `/Users/stevehuang-work/Documents/worktrees/tw_intraday_trader_d_health_open_20260828` on `codex/d-health-open-pinned-20260828`; initial status is clean at `33c9b3a`.
  - Confirmed the clean checkout has no interpreter environment and project broker dependencies are range-based. A dedicated sealed runtime is required; the shared `.venv` will not be referenced by the new plist.
  - Confirmed `.venv/` is ignored, no dependency lock exists, and the shared environment has an editable install of dirty `main`. Chose a fresh worktree-local venv with exact resolved package identity and no editable project install.
  - Generated, checked, and applied an 8-file patch containing only the reviewed D-HEALTH loopback guard, callback quarantine/report behavior, and focused tests. No unrelated calendar or other task changes were transplanted.
  - Created the ignored dedicated `.venv` and installed exact minimal runtime/test dependencies from cached wheels; no editable project package or shared-checkout path was installed.
  - Recreated the dedicated venv from `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13`, removing the shared dirty path from `pyvenv.cfg`, then reinstalled the exact packages.
  - Drafted the immutable runner, runtime-manifest builder, launchd template, and adversarial tests in `/private/tmp`. The first combined replace patch was rejected without changes; separate delete/add operations succeeded.
  - Copied the reviewed runtime files into the dedicated worktree. Initial focused tests passed (`33 passed`); plist lint and whitespace checks passed. Sandboxed bytecode output was denied in the sibling path, so compilation will be rerun with an external cache directory.
  - Moved all project imports behind the complete identity gate, then replaced mocked drift rejection with adversarial source and site-packages mutations that exercise the real gate. Both preserve provider callable count zero and produce durable `NOT_RUN`, exit-78 results.
  - Created four scoped local commits only: payload `ffd4d79`, initial seal `e37d2a9`, shell-boundary hardening `f905520`, and final reseal/HEAD `0bb2ee2fb25c5d818a1784a84ea49e2881265aee`. No push or merge occurred.
  - Replaced the mutable login-shell boundary with non-login `/bin/sh -c`, then regenerated the manifest so the reviewed template and tracked tree remain sealed.
  - Final identity rehearsal matched HEAD, manifest, runner, interpreter, tracked source, stdlib, site-packages, distributions, cohort, and calendar. The dedicated worktree is clean and `ahead 4` of `origin/main` solely by the four scoped commits.
  - Final verification passed: `33 passed`, Python compilation, template and rendered plist lint, immutable-boundary shell syntax, and diff checks.
  - Replaced and loaded the plist with the pinned worktree boundary. Readback shows the exact pinned path, HEAD and digests, `runs=0`, and `last exit code=(never exited)`; no capture, claim, result, session, or evidence was created.
  - Updated the Friday 09:35 Codex automation through the native automation control to remain read-only while inspecting the pinned state/log/records paths.

### Phase 13z: External credential boundary and terminal-result hardening

- **Status:** complete
- **Started:** 2026-08-27
- Actions taken:
  - Received second independent `REQUEST CHANGES` for a missing dedicated credential source and unchecked `source_payload_head` semantics.
  - Re-activated `planning-with-files`, `karpathy-guidelines`, and `code-review-excellence`; reviewed Python, security, secret-handling, exception, and TOCTOU guidance.
  - Read back the loaded job at `runs=0`, `last exit code=(never exited)`, found no claim/result/session/evidence, and confirmed the 09:35 automation remains read-only.
  - Unloaded `com.stevehuang.tw-intraday-trader.d-health-late-001-open-20260828`; post-unload lookup is absent. No provider/capture command was run.
  - Metadata-only inspection selected the owner-controlled shared project `.env`; required Shioaji API/secret aliases are present, while its initial `0644` mode correctly failed the new boundary. Tightened mode to `0600` without reading or rewriting values.
  - Added same-fd external credential validation/filtering, safe child-environment reconstruction, result/log redaction, dotenv bypass in the passive CLI, and terminal `NOT_RUN` handling for identity, calendar/import, credential, and subprocess setup failures.
  - Added adversarial missing-file, insecure-mode, missing-key, filtered-env, no-secret-leak, calendar/import, subprocess setup, and explicit-no-dotenv coverage. Final focused suite is `42 passed`.
  - Removed unchecked `source_payload_head`, added a metadata-only credential contract to manifest v2, and created local commits `c91f64e` and `8d3747f`; no push or merge occurred.
  - Read-only rehearsal first verified source/runtime identity, then validated credential metadata and selected child key names without printing values or creating formal state. Secret absence scan returned `leak_file_count=0`.
  - Final compilation, template/rendered plist lint, POSIX shell syntax, diff check, clean-worktree check, and installed readback passed. Loaded job is `runs=0`, `last exit code=(never exited)` with formal state count zero; no kickstart/capture occurred.

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 8 complete |
| Where am I going? | Await user direction; authenticated Shioaji order Simulation remains a separate unimplemented gate |
| What's the goal? | Use Shioaji Tick/BidAsk to update the local paper simulator without enabling broker orders |
| What have I learned? | See `findings.md` |
| What have I done? | Implemented, documented, and live-verified dynamic Tick/BidAsk subscriptions, local bid/ask fills, UI projection updates, and graceful shutdown |

### Phase 10: Basic strategy expansion implementation

- **Status:** complete
- **Started:** 2026-08-19
- Actions taken:
  - Re-read the approved implementation plan and recorded the current dirty worktree so unrelated download/provider/planning changes remain untouched.
  - Confirmed the pre-change baseline: focused backtest tests `29 passed`; full suite `326 passed, 1 skipped`.
  - Located all dataset-manifest creation paths and confirmed cadence capabilities are currently inferred inconsistently and only emit `OHLCV`.
  - Confirmed the dashboard currently auto-selects the first entry strategy and every exit strategy; this must change before adding experimental strategies.
  - Added cadence evidence/capability derivation, immutable Decimal feature state, five experimental strategy definitions, engine-v2 context, run/worker capability preflight, and safe dashboard defaults.
  - First focused test command referenced test filenames that do not exist in this checkout; no tests ran and no state changed.
  - Corrected registry ordering so existing API consumers still receive the legacy ACTIVE entry first; focused compatibility tests now pass (`28 passed`).
  - Added six cadence/indicator/strategy/engine/preflight contract tests; all six pass.
  - Python compilation passed. Direct `node --check dashboard/static/index.html` is unsupported because Node does not accept `.html`; an extracted-script check remains pending.
  - Full regression passed after the first implementation slice (`332 passed, 1 skipped`); extracted Dashboard inline JavaScript compiled successfully.
  - Added UI safety assertions, legacy v1/v2 parity, old-manifest digest compatibility, and engine-level ATR entry-snapshot propagation coverage; focused expansion tests now pass (`8 passed`).
  - Updated the historical-backtest README section without altering the user's concurrent downloader documentation changes.
  - Removed obsolete whole-day row-count state, added Taiwan-timezone cadence validation, and made feature input digests depend on computed state rather than only the latest bar.
  - Preserved legacy manifest digests by omitting the new optional cadence field when it was absent from the original JSON.
  - Added explicit catalog metadata assertions for all five experimental one-minute strategies.
  - Completed the final end-to-end worker test for an approved v2 ORB/time-stop run.
  - Final verification passed: full suite `337 passed, 1 skipped`; Python compilation, extracted Dashboard JavaScript compilation, and `git diff --check` all passed.
  - Audited the implementation scope: no CA activation, Shioaji trade subscription, broker order callback, or broker `place_order` path was added.
  - Preserved unrelated downloader/provider/night-session worktree changes and did not create a commit.

### Phase 11: Previous-day premarket watchlist implementation plan

- **Status:** complete
- **Started:** 2026-08-19
- Actions taken:
  - Restored the completed strategy-expansion context and confirmed the current dirty worktree before planning.
  - Scoped the plan to prior-session historical data only; no pre-open indicative feed, broker API, or product implementation is authorized.
  - Identified three candidate plan contracts from the discussion: previous-day momentum/liquidity, NR7 contraction, and previous-day RSI/Bollinger oversold.
  - Traced the current Candidate snapshot engine, dashboard snapshot/history service, strategy catalog premarket draft, and existing CandidatePool discovery seams.
  - Confirmed the existing Candidate model lacks the historical identity/evidence needed for a reproducible premarket watchlist artifact.
  - Inspected CandidateDiscovery/CandidatePool and selected that discovery contract as the downstream integration seam, with a separate immutable watchlist artifact as source of truth.
  - Confirmed strategy catalog PRE_MARKET/CANDIDATE metadata can represent the new family without mutating `premarket_gap_watchlist_v1`.
  - Detected an apparent checkout inconsistency: premarket tests exist, while the referenced `premarket/` package is not present at the expected filesystem path; investigation remains plan-only.
  - Confirmed no usable TAIFEX premarket package exists in this checkout, so the stock watchlist plan will not depend on it.
  - Identified required foundations absent from the current scheduler/dataset path: exchange trading calendar, complete daily-bar capability, bounded recent-session reads, and explicit operational-versus-research universe semantics.
  - Audited runtime composition, immutable artifact patterns, instrument references, backtest jobs, and the main Dashboard scan path.
  - Noted concurrent untracked TAIFEX premarket files appearing during this planning task; preserved them and excluded them as a hard dependency.
  - Split the intended design into two outputs: a durable evidence-rich watchlist artifact and a lightweight CandidateDiscovery adapter for CandidatePool admission.
  - Rejected extending legacy float/current-snapshot CandidateRule for the new strategies; selected a separate Decimal daily-feature engine with version-owned contracts.
  - Mapped the minimal UI/API/persistence seams and the required offline test layers.
  - Authored `architecture/previous_day_premarket_watchlist_implementation_plan.md` with exact Momentum, NR7, and RSI/Bollinger formulas, deterministic ranks, time/data contracts, persistence, API/UI, scheduler, test, rollout, rollback, and Definition of Done.
  - Sequenced the first implementation slice through Momentum artifact generation before CandidatePool/UI integration or the remaining two strategies.
  - Verified all required strategy IDs and safety contracts are present; planning Markdown has no trailing whitespace and the tracked planning diffs pass `git diff --check`.
  - Confirmed no product implementation was performed by this phase. Concurrent product, TAIFEX, and separate planning changes remain present and untouched in the dirty worktree.
- Planned output:
  - `architecture/previous_day_premarket_watchlist_implementation_plan.md`

### Phase 12: Rewrite previous-day watchlist Phase 0-3

- **Status:** complete
- **Started:** 2026-08-19
- Actions taken:
  - Received the strategy/data-contract review and explicit authorization to rewrite Phase 0-3 of the existing implementation plan.
  - Re-activated `planning-with-files`, restored unsynced context, and re-read the root planning records.
  - Confirmed this remains a plan-only task; concurrent product, market-data qualification, TAIFEX, dashboard, and other planning changes will remain untouched.
  - Recorded corporate-action normalization, price-limit/one-price classification, Momentum evidence variants, direction-neutral NR7 semantics, Oversold confirmation, and net-of-cost validation as required plan changes.
  - Rewrote Phase 0 as a P0 contract/Formal Gate freeze, Phase 1 as point-in-time reference-data foundations, Phase 2 as corporate-action-aware raw/adjusted derivation, and Phase 3 as the Momentum-only artifact vertical slice.
  - Added four Momentum OOS memberships, market-state rank cohorts, one-price handling, normalized NR7 naming/semantics, confirmation-only Oversold, and gross-to-net cost attribution.
  - Separated immutable raw daily bars from `adjustment_as_of=P` views so future corporate actions cannot rewrite historical candidate artifacts.
  - Reconciled strategy catalog IDs, artifact schema, persistence tables, application workflow, Phase 5/6 semantics, tests, Definition of Done, and the first-reviewable-slice summary with the rewritten Phase 0-3.
  - Final structural checks passed: Phase 0-6 headings remain ordered, 36 code-fence delimiters are balanced, required strategy/gate identifiers are present, no trailing whitespace was found, and tracked planning diffs pass `git diff --check`.
  - Confirmed this task edited only the implementation plan and root planning Markdown; no product code, runtime configuration, migrations, tests, or concurrent worktree files were changed.
  - The first completion patch used an outdated Phase 12 label and failed without changing files; re-read the live block and applied the corrected scoped patch.
- Planned output:
  - Revised `architecture/previous_day_premarket_watchlist_implementation_plan.md` with rewritten Phase 0-3 and consistent cross-references.
