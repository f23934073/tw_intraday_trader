# Task Plan: Package uncommitted work by function

## Goal

Partition the current dirty worktree into auditable local commits grouped by coherent functionality, without pushing or absorbing unrelated transient files.

## Current Phase

Complete

## Phases

### Phase 1: Inventory and ownership mapping

- [x] Capture branch, HEAD, staged, unstaged, untracked, submodule, and recent-history state.
- [x] Identify repository rules and concurrent-worktree changes.
- [x] Map every changed path and hunk to a functional owner.
- **Status:** complete

### Phase 2: Commit design and payload review

- [x] Define dependency-ordered commit groups and messages.
- [x] Review correctness, generated artifacts, secrets, whitespace, and cross-group dependencies.
- [x] Leave task-planning and unsafe or ambiguous files out of product commits.
- **Status:** complete

### Phase 3: Focused verification

- [x] Run proportional focused tests/static checks for each group.
- [x] Record skipped infrastructure coverage as a gap, not a pass.
- **Status:** complete

### Phase 4: Stage and commit

- [x] Recheck status, mtimes, and diffs immediately before each commit.
- [x] Stage only the current group and inspect the exact cached payload.
- [x] Create local commits in dependency order; do not push.
- **Status:** complete

### Phase 5: Final audit

- [x] Verify commit contents and remaining worktree state.
- [x] Report commit SHAs, purposes, verification, and intentionally uncommitted files.
- **Status:** complete

## Decisions

| Decision | Rationale |
|---|---|
| Keep this plan under an isolated `.planning` directory and do not change `.planning/.active_plan` | Preserve the existing active workflow in the shared worktree. |
| Do not push | The user authorized local commits only. |
| Create 15 commits | Keep runtime, research evidence, and planning-only histories auditable without producing one-file micro-commits. A late-arriving, independently coherent VWAP preflight remediation became stable during packaging and was kept separate. |
| Commit strategy lifecycle before VWAP cash admission | Four files contain both concerns; removing the smaller strategy hunks first leaves a cohesive cash-admission diff. |
| Leave `WORKFLOW.md`, `.planning/.active_plan`, and this task plan uncommitted | The workflow is foreign to this repository; the active pointer is shared transient state; the current plan is packaging scratch state. |

## Commit Groups

1. `feat(strategy): add strategy set lifecycle management`
2. `research(vwap): add cash admission control gate`
3. `research(institutional): qualify FinMind PIT reference data`
4. `feat(institutional): add FinMind three-way candidate MVP`
5. `fix(freshness): harden scheduled quote launches`
6. `research(freshness): add scheduled quote and account evidence`
7. `research(market-data): preserve incomplete OPEN capture`
8. `research(trading): record shadow premarket evidence`
9. `docs(data): record FinMind acquisition completion`
10. `docs(trading): add live mode switch plan`
11. `docs(simulation): record odd-lot support rollout`
12. `docs(risk): add central no-overnight controller plan`
13. `docs(simulation): record configurable limit settings rollout`
14. `docs(backtest): record simplified atomic backtest rollout`
15. `fix(backtest): align preflight next-bar semantics`

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Existing legacy planning files produced a very large catch-up output | 1 | Created a separate task plan and will pin commands with `PLAN_ID` without changing the shared active-plan pointer. |
| `shasum -c` rejected digest-only Shadow sidecars | 1 | Read the artifact schema: premarket sidecars intentionally store `readiness_report_digest`; verified them against the embedded field instead of treating them as whole-file checksums. |
| First credential regex command had an unmatched shell quote | 1 | Replaced the fragile expression with simpler filename-only secret patterns and separate JSON field inspection; no candidate secret was exposed. |
| First planning update targeted the error table in `findings.md` instead of `task_plan.md` | 1 | Re-read all three isolated planning files and applied the update to the correct files. |
| `.venv/bin/ruff` is unavailable | 1 | Retain this as an unavailable lint check; use focused pytest, compileall, Node syntax, and Git whitespace checks already available in the workspace. |
| First hunk-level `git add -p` could not create `.git/index.lock` in the sandbox | 1 | Re-ran the narrowly scoped staging operation with the required repository-index approval. |
| Exact staged strategy checkout initially inspected only the last 8 migrations | 1 | Updated the regression to include migration `011`; the subsequent cash-admission commit extended the window through migration `014`. |
| Two temporary unified patch drafts had malformed hunk counts | 2 | Rebuilt the small patch with corrected context/counts and verified its exact staged application. |
| Exact staged PIT checkout depended on an ignored local Dataset manifest | 1 | Reworked the regression to validate only the committed immutable registration artifact and re-ran it successfully. |
| VWAP remediation files changed while packaging was in progress | 1 | Did not stage them immediately; waited for stable mtimes, reviewed the new complete payload, ran its focused regression, and committed it as its own final functional group. |
