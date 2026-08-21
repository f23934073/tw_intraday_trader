# Progress Log

## Session: 2026-08-20

### Current Status
- **Phase:** Complete - awaiting PR-004 review gate
- **Started:** 2026-08-20

### Actions Taken

- Read the complete PR-003 review: approved with no blocking issue; PR-004 is authorized under research-only conditions.
- Activated code-review, planning-with-files, and surgical-change guidance.
- Restored root planning/catch-up context, recorded the concurrent worktree, and created this isolated PR-004 plan.
- Froze the scope to exploratory factor diagnostics; PR-005 and all execution/runtime paths remain HOLD.
- Completed review-reference and repository discovery for the existing institutional, PIT, and daily-price lineage contracts.
- Added immutable `ResearchRunManifestV0`, fixed baseline definition, canonical factor/report serialization, and input digest verification.
- Added availability-safe foreign/trust factor computation plus Decimal-only distributions, cross-sectional ranks, deciles, forward outcomes, Rank IC, mean IC, and ICIR.
- Added all-or-nothing PIT and scope gates; cross-sectional arrays remain empty when a required universe session or digest is ineligible.
- Added deterministic institutional, PIT-universe, and adjusted-close fixtures plus reproducibility, lineage-tamper, PIT/current-snapshot, scope-drift, future-poison, incomplete-window, zero-denominator, and delayed-publication tests.
- Documented the v0 report contract, time semantics, formulas, statistics, canonical bytes, and poison-gate arrays.
- Fixed the report Decimal context at precision 36 and froze the baseline definition/report fixture digests.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `python3 -m py_compile institutional_research/*.py` | New package compiles | Passed | pass |
| `ruff check institutional_research` | No lint findings | Passed | pass |
| `.venv/bin/pytest -q tests/test_institutional_factor_diagnostics.py --cov=institutional_research` | PR-004 contracts pass with focused coverage | 12 passed; 93% package coverage | pass |
| Institutional + PIT adjacent regression | PR-001 through PR-004 contracts pass together | 81 passed | pass |
| System Python `pip wheel --no-deps --no-build-isolation` | Wheel includes and imports the research package | 8 package files verified; isolated zip import v0 | pass |
| `.venv/bin/pytest -q` | Full repository regression | 550 passed, 1 skipped | pass |
| Runtime/candidate/order import audit | PR-004 has no downstream executable integration | No production import outside `institutional_research` | pass |

### Errors
| Error | Resolution |
|-------|------------|
| Full baseline test collection initially failed because `tests/test_market_event_journal.py` imported an absent concurrent `market_data.journal` | Preserved the unrelated scope; final full regression passed after that concurrent file arrived. |
| Delayed-publication fixture initially retained a stale normalized digest | Validation rejected it; recomputed the affected manifest digest and the poison test passed. |
| `.venv` wheel build could not import `setuptools.build_meta` | Used the system Python's existing backend without network access; build and isolated import passed. |
| Wheel validation generated `build/` and refreshed tracked egg metadata | Removed only the generated build directory and restored the pre-build metadata bytes; no generated artifacts remain in the workspace. |
