# Task Plan: Merge Institutional Research into Local Main

## Goal

Package the completed three-institutional-investor MVP research implementation as one reviewable, tested commit on local `main`, while preserving all unrelated dirty-worktree changes and leaving remote push/PR out of scope.

## Scope

- Institutional MVP domain, daily/series artifacts, coverage/universe freeze, and non-formal offline diagnostic.
- Only the minimum calendar/backtest engine seams required by that research flow.
- Focused tests and durable research metadata required to reproduce the bounded diagnostic.

## Explicit exclusions

- Price Dataset payloads, provider calls, Shioaji r3, runtime/default binding, broker/order paths.
- Freshness, Trade Management, R6, no-overnight, and unrelated dirty-worktree changes.
- Push, PR creation, or remote merge.

## Phases

### Phase 1: Scope and lineage audit

- [x] Identify exact relevant files and commits already present in local/remote main.
- [x] Detect cross-scope mixed hunks and immutable/generated artifacts that should not be committed.
- **Status:** complete

### Phase 2: Integration package

- [x] Create a scoped integration branch from current local main without disturbing unrelated changes.
- [x] Stage only reviewed institutional research files/hunks.
- [x] Verify staged diff contains no credentials, price payloads, runtime/order authorization, or unrelated files.
- **Status:** complete

### Phase 3: Verification

- [x] Run focused institutional, calendar, and engine tests.
- [x] Run static/diff checks proportional to the changed scope.
- [x] Review the staged diff and repository state.
- **Status:** complete

### Phase 4: Commit and local-main integration

- [x] Commit the verified package.
- [x] Ensure the commit is reachable from local `main` while preserving unrelated worktree changes.
- [x] Verify local ancestry and report remote divergence separately.
- **Status:** complete

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Sandbox denied creation of the Git ref under `.git`. | 1 | Re-ran the exact scoped `git switch -c` operation with approved Git escalation; branch creation succeeded. |
| A staged-scope audit used unsupported `rg` look-ahead syntax. | 1 | Relied on the complete staged name list and will use plain path-prefix checks; no repository content was changed. |
| Process-substitution input was unsupported by `git diff --no-index`. | 1 | Used `git show ... | diff -u - file` for the read-only comparison. |
| Two full-suite supervisor tests initially failed because the detached verification worktree lacked its expected `.venv/bin/python` path. | 1 | Added a temporary worktree-local symlink to the existing project environment; both tests then passed. |
| Full suite retained one r2 price-coverage source-digest mismatch. | 1 | Reproduced the same failure on parent `main@a6e096a`; classified as a pre-existing baseline failure outside this integration. |
