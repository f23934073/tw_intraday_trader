# Progress Log

## Session: 2026-08-20

### Current Status

- **Phase:** Complete
- **Started:** 2026-08-20

### Actions Taken

- Read the reviewer feedback in full and treated its explicit approval as authorization for PR-001 only.
- Activated and read `karpathy-guidelines` and `planning-with-files`.
- Restored root session context, ran session catch-up, inspected the worktree, and isolated this task from active freshness-calibration work.
- Created an isolated planning session and froze allowlist, non-goals, success criteria, and deferred reviewer suggestions.
- Inspected existing frozen domain models, canonical serializers, artifact validators, tests, and explicit setuptools package discovery.
- Chose structural constructor invariants plus pure reconciliation reports, and recorded the one necessary packaging include edit.
- Revised the architecture plan to reflect the reviewer-approved PR-001 through PR-004 ordering and deferred migration/persistence.
- Added the smaller research manifest, factor ordering, candidate-hypothesis ordering, compression/coverage/attention metrics, and no-trade success semantics.
- Added normalized TWSE/TPEx row/manifest JSON fixtures and focused domain, serialization, validation, duplicate, digest, and scope-compatibility tests before implementation.
- Implemented frozen domain contracts, canonical JSON/SHA256 serialization, strict deserialization, pure formula/partition/scope validation, package exports, and the minimal setuptools include.
- Completed the first severity review; identified three focused contract/diagnostic gaps to cover with tests before final regression.
- Added regression coverage and fixed contradictory scope decisions, JSON date type diagnostics, and row/manifest observation-time reconciliation.
- Reconciled the architecture document with the implemented v1 row/manifest schema and marked PR-002 as the next HOLD gate.
- Completed final scope review: only the architecture plan, new institutional contract package/tests/fixtures, and one package-discovery token belong to PR-001; active freshness work remains untouched.
- Restored the original `.planning/.active_plan` pointer after completing the isolated session.

### Test Results

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Initial PR-001 focused tests | Fail because approved modules are not implemented yet | 3 collection errors: missing `institutional_data.domain/serialization/validation` | EXPECTED RED |
| PR-001 focused tests after implementation | All new contract tests pass | `29 passed in 0.04s` | PASS |
| Review-gap tests before fixes | New tests reproduce all three review findings | `5 failed, 29 passed` | EXPECTED RED |
| Focused tests and Ruff after review fixes | All PR-001 checks pass | Ruff clean; `34 passed in 0.04s` | PASS |
| Full regression suite | Existing repository remains green | `454 passed, 1 skipped in 1.63s` | PASS |
| Python compilation | New package compiles | `compileall` clean | PASS |
| Package discovery | New package is selected by the explicit include list | `institutional_data packaged` | PASS |
| Ruff format check | All new Python files canonical | 6 files require formatting | FIX REQUIRED |
| Ruff lint/format + focused tests after scoped formatting | New Python files are canonical and tests remain green | Ruff clean; 7 files formatted; `34 passed in 0.05s` | PASS |
| Naive canonical timestamp regression before fix | Serializer must reject missing timezone | 1 expected failure | EXPECTED RED |
| Final focused coverage | Contract slice has reviewable test coverage | `35 passed`; 94% total package coverage | PASS |
| Final full regression | Entire checkout remains green | `455 passed, 1 skipped in 2.13s` | PASS |
| Final static/structure checks | Ruff, format, packaging, Markdown, whitespace clean | All checks passed | PASS |

### Errors

| Error | Resolution |
|-------|------------|
| Root planning output was truncated by the display budget | Continue from the isolated plan; repository state and relevant root constraints were captured. |
| First planning-file replacement patch was invalid | Split delete and add into supported apply-patch operations. |
| Focused test collection could not import PR-001 modules | Expected test-first failure; proceed with minimal module implementation. |
| Virtualenv has no Ruff executable | Located the existing system Ruff binary and will use it for static checks. |
| Two code-review reference reads used the wrong directory name | Located the installed `reference/` paths before continuing the review. |
| `.venv` does not contain setuptools for package discovery | System Python has setuptools 80.9.0; use it for the read-only include-list check. |
| Six new files were not Ruff-canonical | Limit formatter scope to those PR-001 files and rerun all relevant checks. |
