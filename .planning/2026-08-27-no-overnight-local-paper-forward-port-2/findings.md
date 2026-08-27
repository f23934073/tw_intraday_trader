# Findings & Decisions: No-Overnight Local Paper forward-port

## Requirements
- Start exactly from main merge commit `037197e1a3aadd7a480208f97f291cdcb6ce7a2f` in this independent task worktree.
- Use `codex/no-overnight-pr-no-006` at `21fd771d2086122d2c49a5c0bbbbcdb206087bc0` as read-only semantic source; never blind merge/rebase/cherry-pick the old branch.
- Preserve managed exposure identity, monotonic cutoff state, terminal flat proof, durable breach/admission behavior, Kill Switch durability, and fill.v3 monetary truth.
- No synthetic fills, broker/live orders, CA, trade callbacks, unattended promotion, or real-money authority.
- Verify each phase with focused tests/self-review; finish with full regression, isolated disposable PostgreSQL UAT, static/JS/diff checks, and independent adversarial review.
- No push/PR without later authorization; scoped local commits are allowed only after verification.
- Full-session DISABLED/OBSERVE_ONLY/supervised ENFORCING campaigns and three drills remain later trading-session Gates.

## Research Findings
- Initial worktree state was clean and detached at stale `a6e096af6d966f6e46f8549e4ea6ac1d0d48b7f9`.
- After `git fetch origin main`, `refs/remotes/origin/main` resolves exactly to `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`.
- Scoped branch `codex/no-overnight-integration-20260827` was absent, then created from the exact authoritative object.
- Immediately after branch creation, HEAD equalled the baseline and both tracked and untracked cleanliness checks passed.
- `34fb525`, `99ece089`, and `786f452` are all ancestors of baseline HEAD.
- Source branch resolves exactly to `21fd771d2086122d2c49a5c0bbbbcdb206087bc0`.
- The shared repo's `FETCH_HEAD` shows `786f45212f822ae0514957adac748c00fb6a95fa`, so it is not used as authority; updated `origin/main` and the exact commit object agree.
- Root planning files belong to a separate Freshness Calibration effort; this task uses an isolated planning directory.
- Prior release memory identifies `34fb525` as Kill Switch, `99ece08` as Tax/Slippage, `786f452` as PostgreSQL CI coverage, and `037197e1` as the merged endpoint; these labels must still be verified from current Git objects.
- Prior No-Overnight review memory says the source runner is MockProvider-only, PostgreSQL-required, and fail-closed around monotonic clock/cutoff/incomplete markers; its recorded PostgreSQL UAT was waived/not passed.
- Prior review also reinforces that `CONFIRMED_FLAT` is exposure-scoped and needs terminal SELL, managed quantity zero, fresh reconciliation, and durable Journal/checkpoint proof.
- A specifically remembered overlap risk is v1-only `ExistingPaperFillObserver` / `PaperFillThesisBuilder` handling against current `local_paper_fill.v3`; verify this directly during the semantic map.
- The source and baseline diverge at `7f6247c793768aa2c826626a575b19e8b71cbfa0`. The source has exactly seven ordered commits: PR-NO-001 `5b26371`, PR-NO-002 `060fb6a`, PR-NO-003 `13a9b13`, PR-NO-004 `57c9fa7`, PR-NO-005 `067f013`, PR-NO-006 evidence `ca05fc3`, and supervised runner `21fd771`.
- Baseline added 21 commits after the merge base, including Local Paper settings (`072c0c5`), Kill Switch (`34fb525`), fill.v3 tax/slippage (`99ece089`), PostgreSQL CI coverage (`786f452`), and merge `037197e1`.
- PR-NO-001 through PR-NO-005 are heavy overlapping changes to `runtime/composition.py`, `simulation/application.py`, `simulation/service.py`, `trading/application.py`, and `trading/local_paper.py`; these cannot be source-file replacements.
- PR-NO-002 through PR-NO-006 also add mostly new No-Overnight modules/tests/runbooks that can be ported after checking imports and current contracts.
- Current baseline explicitly supports settings schema v1/v2 and immutable `local_paper_fill.v1`, `.v2`, and `.v3`; projection name is still `local_paper.v1`, so the source's proposed `local_paper.v2` projection must be reconciled rather than overwriting current readers.
- Current CI compiles all packages, checks dashboard modules, runs all tests, and has a PostgreSQL job covering Journal, Local Paper projection, Kill Switch, and fill.v3 durability tests.
- This worktree has no executable `.venv/bin/pytest`; baseline validation must use an available environment or install dependencies only if needed/authorized.
- The read-only shared project venv is usable against this checkout (`Python 3.13.5`, `pytest 9.1.1`). Baseline full regression passed `1500 passed, 43 skipped` in 10.70s.
- Baseline PostgreSQL-focused selection passed `20 passed, 4 skipped`; the four skips explicitly require `TEST_POSTGRES_DSN`, so baseline PostgreSQL UAT is NOT RUN / NOT PASSED locally.
- Baseline compileall, Python-driven dashboard JS graph check, and `git diff --check` passed. No product diff existed at phase close.
- Read the PR-NO-001–006 task plans and both source runbooks. Their repeated independent-review remediations make strict JSON types, retry lineage, command/final-admission/fact append order, stale/future BidAsk, guard loss, late facts, policy upgrades, and no-follow artifact chronology mandatory regressions rather than incidental implementation details.
- The source PR-NO-004 plan confirms `NEVER_EXPOSED` is allowed only under strict zero/pending/unresolved/MATCH fences, while fill-derived flatness requires a terminal/resolved exit chain.
- The source PR-NO-005 plan confirms resolution and acknowledgement are distinct, revision/digest bound, invalidated by later facts, and only release BUY in a later reviewed session.
- The source PR-NO-006 runbook binds operational qualification to immutable open/close chronology and exact code/report identity; old runner output cannot be reused after this port.
- A concrete schema collision exists: both branches use `local_paper_fill.v2` for different meanings. The frozen map therefore reserves v1/v2/v3 readers unchanged and selects additive `local_paper_fill.v4` for settings-v2 monetary truth plus exposure identity.
- The current settings workflow rotates immutable Local Paper sessions. The frozen map therefore separates a fixed scope/family identity anchor from the active settings-bound ledger instead of replacing settings sessions with the old branch's fixed v2 ledger.
- PM's PostgreSQL compatibility milestone is `7931d31e53657c4f28e684402589c2b20501c1d9`; it contains approved Shadow `47a9303`, timestamp-identity fix `f6a38b1`, and UAT expectation fix `254317b`.
- Exact review of those commits shows that final `trading/postgres_journal.py` must read stored fingerprints, retain the timestamp envelope on new rows, verify the original aware timestamp on reconstruction, and preserve bounded legacy UTC/+08 candidate compatibility.
- A final fetch found that `origin/main` had advanced through PR #5/#6 to `d5b86382c06a34e3a26ba2b23e3d714c783f0348`. The added paths have no overlap with this 81-file patch, and `git range-diff` proves the rebased patch is identical. The initial `037197e1` remains the audited common port baseline, not the final parent.
- PostgreSQL advisory locks are cluster-wide for this identity, so separate test databases must run sequentially when they exercise full runtime ownership.
- A safe DISABLED settings rotation reuses the current healthy guard under the process-wide runtime lock, then explicitly transfers ownership only after settings activation/archive succeeds; any unrelated process remains unable to acquire the lock.
- The rotation also shares the exact current Kill Switch object after validating its Journal, Clock, and durability binding. This preserves one cached projection/lock/revision authority across old and replacement references while ordinary process restart still performs durable recovery.
- Old command and strategy-flow references are suspended during the reversible handoff and permanently revoked at commit. Complete activation and checkpoint Journal flows hold that same authority lock, eliminating check-then-append races against archive.
- A signed v2 state must numerically bind its reader-preferred decimal aliases and its chronological status/cumulative quantities to v4 fills. A fill appended before its state remains projected but restores the order as `RECOVERY_REQUIRED`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Freeze compatibility decisions before editing product code | Identity/readers/projections/checkpoints/migrations are the highest-risk overlap with Kill Switch and fill.v3. |
| Prove PostgreSQL isolation before running UAT | The request explicitly prohibits use of formal Shadow/Freshness/existing evidence databases. |
| Evidence qualification includes exact integrated code identity | Fixture results and old branch artifacts cannot qualify the forward-ported implementation. |
| Preserve fill.v1/v2/v3 readers and add No-Overnight identity as an additive projection evolution | Baseline monetary history is immutable; replacing `local_paper.v1` or downgrading fill kinds would corrupt replay semantics. |
| Emit integrated managed fills as `local_paper_fill.v4` only under settings v2 | The old and current v2 schemas collide; v4 can require exact v3 Tax/Slippage/instrument/settings evidence plus identity without reinterpreting history. |
| Require settings v2 for OBSERVE_ONLY/ENFORCING | No-Overnight must not manage a fill that lacks the integrated monetary and identity truth. |
| Keep a fixed identity anchor separate from settings-rotated ledger sessions | Stable breach authority must survive settings revisions, while settings/session history remains immutable. |
| Require one mutation advisory guard for PostgreSQL Local Paper in every mode/settings schema | A restart downgrade cannot create a second BUY-capable path outside the durable breach fence. |
| Retain historical decimal spellings but require numeric alias equality | Existing immutable order states may contain `980.0`; rejecting the spelling would reinterpret history, while equality still prevents reader drift. |
| Reuse one exact Kill Switch object only for a validated in-process handoff | Prevents stale/new cached projections from disagreeing while preserving restart replay and exact revision reset. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Existing active planning pointer referred to an unrelated plan | Initialized and activated an isolated forward-port plan after the clean baseline gate. |
| Dashboard check was accidentally invoked with Node even though it is a Python launcher | Reran the exact CI form with Python; passed. |
| Generated modified-file patches used standard numbered hunk headers | Re-generated them with the patch tool's plain `@@` form; every carried file now hashes exactly to the reviewed source blob. |
| Three focused guard tests require the not-yet-integrated composition constructor | Classified as Phase 4 dependencies, not domain regressions; retained them and deselected only those three for the Phase 3 checkpoint. |

## Resources
- Baseline: `037197e1a3aadd7a480208f97f291cdcb6ce7a2f`
- Read-only source: `codex/no-overnight-pr-no-006` / `21fd771d2086122d2c49a5c0bbbbcdb206087bc0`
- Memory registry: release workflow and No-Overnight runner sections in `MEMORY.md`; exact runner-review evidence in `rollout_summaries/2026-08-23T08-13-45-kSUo-no_overnight_plan_and_phase15_runner_review.md`.
