# Progress Log

## Session: 2026-08-20

### Current Status
- **Phase:** Complete
- **Started:** 2026-08-20

### Actions Taken

- Read the approved review completely and confirmed explicit authorization for PR-002.
- Froze scope to TWSE/TPEx source adapters, immutable raw capture/revisions, fixture replay, and normalized PR-001 artifacts.
- Activated an isolated planning session and preserved the original active plan ID for restoration.
- Performed the quick memory pass for decision-support and no-real-money boundaries.
- Inspected PR-001 contracts, current institutional fixtures, package status, and existing content-addressed/append-only artifact repository patterns.
- Began official-source verification; confirmed the TPEx per-stock OpenAPI route and official formula/correction-policy semantics, while direct Swagger fetches were blocked.
- With approval, probed the official endpoints read-only: captured the exact TWSE T86 envelope/fields and confirmed the TPEx OpenAPI route/response component.
- Verified the exact TPEx latest-only OpenAPI shape, then verified the canonical historical endpoint's complete proprietary/hedge/total component split and mapped the richer historical product.
- Confirmed frozen trade-scope IDs, availability boundaries, existing urllib conventions, and the TPEx page's historical `insti/dailyTrade` route reference.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| PR-002 focused | all gates pass | 51 passed | PASS |
| Full regression before concurrent file appeared | no regression | 470 passed, 1 skipped | PASS |
| Regression excluding only concurrent unrelated collector | no regression | 471 passed, 1 skipped | PASS |
| Ruff lint/format | clean | clean | PASS |
| Focused coverage | sufficient critical-path coverage | 89% package total | PASS |
| Live TWSE ingestion | VALIDATED | 1,336 rows, 0 issues | PASS |
| Live TPEx ingestion | VALIDATED | 892 rows, 0 issues | PASS |
| Compile/wheel/isolated import | pass | pass | PASS |

### Errors
| Error | Resolution |
|-------|------------|
| Web access could not open official Swagger/raw endpoints | Continue with official documentation/search and only request a read-only probe if exact fields cannot be established. |
# 2026-08-20 update

- Confirmed TWSE T86's exact 19-field response contract.
- Confirmed TPEx OpenAPI's exact latest-session schema and the official page's `insti/dailyTrade` action.
- Historical TPEx URL construction remains the last source-discovery item before adapter implementation.
- Traced the table runtime: source retrieval is POST-based and preserves the page's `date`, `type`, and `sect` scope parameters.
- Froze PR-002's TPEx request scope as `Daily/EW`; only the base API pattern remains to resolve.
- TPEx source discovery is complete. The official historical endpoint and exact 24-column modern schema are verified; implementation can proceed without guessing.
- Reviewed PR-001 seams and confirmed no schema rewrite is needed. Next files are raw artifact storage, official adapters and orchestration tests.
- Chose standard-library HTTPS plus injected transport, with no `pyproject.toml` dependency edit.
- Implementation contract is now frozen: exact official schemas, explicit availability input, content-addressed revisions and existing validation composition.
- Re-read the approval gates; raw-before-parse and immutable revision behavior will be tested at the application boundary, not documented only.
- Completed exact envelope discovery for both official products; schema checks can now be strict rather than heuristic.
- Official scope notes and response markers are frozen. Starting code and fixture implementation.
- Finalized module boundaries: `artifacts` for immutable raw revisions, `sources` for official fetch/strict normalization, and `application` for raw-first orchestration plus quarantine.
- Captured representative official rows for deterministic TWSE/TPEx replay fixtures.
- Added `institutional_data/artifacts.py` and `institutional_data/sources.py`. Raw storage and strict official parsing are implemented; orchestration and tests remain.
- Added raw-first ingestion orchestration and public package exports. Next: official fixtures, gate tests, lint/test correction.
- Added reviewed TWSE/TPEx fixtures plus raw store and adapter/application gate tests. Moving to focused verification and correction.
- First focused command did not start because `python` is unavailable; `.venv` exists and will be used next.
- Focused verification: `50 passed`. Direct `.venv/bin/ruff` is unavailable; lint runner discovery is next.
- Ruff lint passes. Applying Ruff formatting to the five PR-002 files, then rerunning focused tests.
- Formatted, linted and reran focused suite: `50 passed`. Next: adversarial code review, architecture plan status/renames, full regression.
- Focused lint/format/coverage passes after adversarial fixes: `50 passed`, 89% package coverage. Updating the approved architecture plan and then running full regression/package checks.
- Architecture plan updated. Full suite passes: `470 passed, 1 skipped`. Package/compile/import/live-smoke verification remains.
- Compile and wheel build pass. Next: isolated wheel import and one live adapter ingestion smoke per official market.
- Wheel import passes. First combined live smoke reached TPEx but failed its strict X.509 chain check; implementing a verified TLS compatibility context and regression test before retrying.
- TLS compatibility fix is linted and tested without disabling certificate or hostname verification. Retrying live TWSE/TPEx ingestion.
- Live smoke passes for both markets. Final lint passes, but a concurrent unrelated market-event test now blocks full collection; verify its worktree provenance, rerun PR-002 focus, and do not modify that scope.
- Concurrent blocker confirmed outside scope. Regression excluding that single new test passes `471 passed, 1 skipped`; focused PR-002 passes `51`. Rebuild wheel with TLS fix, finalize docs/status, restore prior planning pointer.
- Final wheel build and isolated import pass. Remaining actions: mark plan complete, audit exact diff/status, restore prior planning pointer.
- PR-002 implementation and verification are complete. PR-003 remains on HOLD pending explicit approval.
- Final audit found wheel-build byproducts (`build/` and egg-info refresh). Cleaning only those files before delivery; prior planning pointer is already restored.
- Build byproducts are cleaned. Restoring the pre-existing no-final-newline byte in `SOURCES.txt`, then one final status audit.
- Cleanup complete: egg-info has no diff, `build/` is absent, prior planning pointer is restored, and final focused verification is `51 passed` with clean Ruff/compile checks.
- Final whole-worktree collection is still transiently blocked by concurrent canonical-market-pipeline work. No changes were made to that scope; delivery will report the blocker explicitly.
