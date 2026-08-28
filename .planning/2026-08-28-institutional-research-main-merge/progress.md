# Progress: Institutional Research Main Merge

## 2026-08-28

- User authorized merging the previously completed institutional research work into `main`.
- Confirmed the initial MVP is already merged, while the recent research/evaluation layers are not.
- Started a scoped, no-push integration workflow; no provider, outcome, holdout, runtime, broker, or order action is authorized.
- Created `codex/institutional-research-main-merge-20260828` from local `main@a6e096a` while preserving all existing dirty-worktree content.
- Staged 28 scoped files only: institutional domain/daily/series/evaluation/diagnostic code, the minimum calendar/engine seams, focused tests, and this merge workpad.
- Initial focused verification passed `102 passed` in 2.97 seconds.
- Staged whitespace check, scoped compile, and Ruff all pass. No forbidden runtime/data path is staged.
- Created the integration commit and replayed the focused suite in a detached clean worktree: `102 passed`.
- Full clean-worktree regression after providing the expected project `.venv` path completed `1721 passed, 86 skipped, 1 failed`. The one source-digest failure was reproduced on parent `a6e096a`, so it predates and is unrelated to this package.
