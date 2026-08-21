# Task Plan: Package the dirty worktree into reviewable commits

## Goal

Inventory all current uncommitted changes, separate source changes into coherent commits, verify the packaged repository, and push the resulting `codex/` branch without losing or silently including generated/sensitive files.

## Current Phase

Phase 4 — Push awaiting explicit remote/payload approval

## Phases

### Phase 1: Worktree inventory and safety classification

- [x] Record branch, base commit, staged state, tracked/untracked inventory, and large/generated artifacts.
- [x] Check for overlapping features, credentials, and files that should remain local.
- [x] Establish the exact commit groups and their dependency order.
- **Status:** complete

### Phase 2: Build and verify commit groups

- [x] Create or switch to a scoped `codex/` branch when required.
- [x] Stage only one logical group at a time and review its cached diff.
- [x] Run proportionate focused checks before each commit.
- **Status:** complete

### Phase 3: Repository-level verification

- [x] Confirm commit boundaries and remaining worktree state.
- [x] Run the full repository suite plus static/whitespace checks.
- [x] Record any intentionally excluded local/generated artifacts.
- **Status:** complete

### Phase 4: Push and handoff

- [ ] Push the new branch and establish upstream tracking.
- [ ] Report branch, commit SHAs, checks, and any remaining files.
- **Status:** awaiting explicit approval — the safety reviewer requires confirmation of the exact GitHub remote and broad source/research/planning payload

## Success Criteria

- Every committed file belongs to an explainable feature/evidence group.
- No secret-bearing file or disposable runtime artifact is pushed.
- The final source tree passes the repository verification gates.
- The remote branch contains all intended commits in dependency order.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Initial credential-pattern scan had an unmatched shell quote | 1 | Use separate `rg -e` patterns over the repository with generated/local directories excluded; print filenames only. |
| Initial `.gitignore` patch expected `.DS_Store` beside Python patterns | 1 | Read the file, confirmed `.DS_Store` was already ignored, and added only the missing `build/` entry beside other generated outputs. |
| First staged market-data whitespace check found two Markdown EOF blank lines | 1 | Removed only the trailing blank lines and restaged the two contract files. |
| Institutional staged whitespace check found nine EOF blank lines | 1 | Removed only the trailing blank lines from three contracts, three JSON artifacts, and three tests; no semantic content changed. |
| Trade-management focused run had eight time-of-day-dependent failures | 1 | The shared paper-fill fixture injected `FixedClock` only into the command service, while the simulator stamped fills with wall time. Inject the same clock into both and rerun the suite. |
| Trade-management rerun retained two equivalent wall-clock failures | 2 | A second independent operational-composition fixture had the same split-clock construction. Share its existing `MutableClock` with the simulator as well. |
| Local-paper staged whitespace check found one EOF blank line | 1 | Removed only the trailing blank line from `simulation/execution_policy.py` and restaged it. |
| Editable metadata refresh tried to resolve build dependencies from the blocked network | 1 | Retry the local project install with `--no-build-isolation --no-deps` so the existing workspace setuptools is used and no download is attempted. |
| No-build-isolation metadata refresh could not import `setuptools.build_meta` from the venv | 2 | Stop retrying pip. Audit the already tracked egg-info against current package files and rely on compile/tests; do not change the environment or download packages for metadata-only packaging. |
| Initial push was rejected by the safety reviewer | 1 | Do not retry. The final payload targets `https://github.com/f23934073/tw_intraday_trader.git` and contains broad source/research/planning history; obtain explicit user confirmation after the payload is stable. |
| Late Gate G1 remediation broke test collection by changing `occurred_at` without its canonical record identity | 1 | Keep the already verified shared-clock fix from `0bcf61c`; remove the duplicate timestamp mutation and rerun the complete suite before classifying the late code. |

## Notes

- Existing root planning files belong to prior repository work and are treated as user-owned changes.
- Generated metadata and runtime evidence are classified before staging; exclusion is reported rather than silently discarded.
