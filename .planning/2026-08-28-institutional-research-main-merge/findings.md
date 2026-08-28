# Findings: Institutional Research Main Merge

- Initial FinMind three-way-candidate MVP commit `44bcef3` is already an ancestor of both local `main` and `origin/main`.
- Immutable daily-batch commit `2bc76f7` is present in `origin/main` but not the divergent local `main` history.
- Series, evaluation-universe, and offline-diagnostic files currently exist only as uncommitted workspace content.
- Local `main` is dirty and diverged from `origin/main`; unrelated changes must remain untouched.
- The runtime artifacts under `data/institutional_mvp` are intentionally left untracked; the code commit pins and verifies their identities without embedding price data or generated evidence.
- The staged package contains no `data/`, `records/`, dashboard, simulation, provider-capture, or order-path file.
- Every production permission projection remains fail closed: `research_eligible=false`, formal outcome/holdout/runtime/order authorization false.
- The exact integration commit passes all 102 focused tests in a detached clean worktree, proving it does not depend on unrelated uncommitted files.
- Full clean-worktree regression is `1721 passed, 86 skipped, 1 failed`; the sole r2 price-coverage source-digest drift reproduces unchanged on parent `main@a6e096a` and is outside this commit.
