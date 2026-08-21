# Findings: Worktree commit packaging

## Constraints

- The user authorized creating multiple commits and pushing them.
- Preserve the current dirty worktree; do not use destructive cleanup or reset operations.
- Prefer coherent, independently reviewable groups over one catch-all commit.
- Verify current state directly because prior test and worktree observations can drift.

## Inventory

- Branch/base: `main` at `6f7a842`, aligned with `origin/main`; no staged changes.
- Tracked delta: 76 files, approximately 5,338 insertions and 397 deletions.
- Untracked work spans canonical market-data evidence, institutional research, trade management, backtest/atomic strategies, dashboard/paper simulation, tests, planning records, and generated packaging output.
- Large local data under `data/finmind_sponsor/` is already excluded by the current `.gitignore` change and is not part of source packaging.
- `build/` is a generated setuptools copy and contains 168 untracked files. `.DS_Store` files are also present throughout the tree. Both should be ignored, not committed.
- `tw_intraday_trader.egg-info/` is already tracked in the repository and its metadata changes correspond to the expanded package list/dependencies; classify it with the final packaging commit rather than treating it as new source.
- Immutable research evidence is intentionally present (roughly 12 MB under `research/` and 5.3 MB under `records/`). The largest individual file is about 2.1 MB, so there is no GitHub large-file blocker.
- Credential-related capture manifests describe credential presence and explicitly label retained response headers as secret-free. A content-level secret scan is still required before push.
- `.planning/.active_plan` is a local task pointer, not source or durable task evidence; leave it uncommitted.
- `tests/test_paper_fill_thesis_builder.py` had a latent wall-clock dependency: the command service used `FixedClock`, but `SimulationService` did not. At late local hours the derived four-hour capture window crossed midnight and eight focused tests failed. The deterministic fix is to share one `FixedClock` between both components.
- Four Atomic Strategy Gate G1 review documents arrived after the backtest commit. They reopen Gate G1 for six findings; this packaging task closed only the already-reproduced split-clock test finding. The remaining five findings stay explicitly blocked and are committed as a separate late review record, not mixed into the earlier implementation commit.

## Commit Map

Draft dependency order:

1. Canonical market-event pipeline, qualification capture, replay, and late-delivery evidence.
2. Institutional data contracts, PIT universe, research diagnostics, candidate priors, and shadow admission.
3. Trade-management contracts, shadow runtime, journaling, and operational evidence.
4. PostgreSQL-backed backtest/atomic-strategy platform, memory streaming, FinMind download support, and exploratory pilot.
5. Dashboard realtime market-data/status/WebSocket behavior and paper-order entry controls.
6. Recoverable automated local-paper order lifecycle and sell-safety hardening.
7. Cross-cutting documentation, package metadata, repository hygiene, and planning records not cleanly owned by one source slice.

Cross-cutting tracked files (`README.md`, `pyproject.toml`, `dashboard/server.py`, `runtime/composition.py`, and several trading/provider files) will be assigned to the commit whose final runtime contract they implement; avoid hunk splitting unless a boundary is genuinely independent.

Implemented commit sequence:

1. `fab2e01` — canonical market-data journal and evidence pipeline.
2. `bf55f35` — institutional/PIT research and candidate pipeline.
3. `0bcf61c` — shadow trade-management lifecycle.
4. `1d9d014` — atomic-strategy/backtest persistence platform.
5. `72e1432` — recoverable local-paper lifecycle and PostgreSQL Journal.
6. `33dbfc6` — realtime dashboard paper-trading controls.
7. `15d5607` — runtime documentation, ignore rules, and regenerated package metadata.
8. `6060f92` — late Atomic Strategy Gate G1 review blockers.
9. `81e7386` — Atomic Strategy replay/snapshot/integrity/test-cleanup hardening candidate.

The final worktree packaging record is intentionally a separate audit-only commit.

Final verification after the late remediation candidate:

- focused Gate G1 candidate: `16 passed, 5 skipped`;
- full repository: `1102 passed, 10 skipped`;
- compileall, dashboard JavaScript, branch whitespace, and committed credential-pattern checks passed;
- PostgreSQL integration tests remain skipped without an explicit disposable `TEST_POSTGRES_DSN`, so Gate G1 is not claimed as passed.

## Exclusions

- Local only: `build/`, `.DS_Store`, `.planning/.active_plan`, ignored `.venv/`, caches, and `data/finmind_sponsor/`.
- No file will be deleted as part of exclusion; ignored/local files remain recoverable in the workspace.
- The only visible tracked worktree remainder after packaging is the pre-existing local `.planning/.active_plan` pointer; it is intentionally not committed.
