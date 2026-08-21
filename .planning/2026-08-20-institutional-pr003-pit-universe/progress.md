# Progress Log

## Session: 2026-08-20

### Current Status
- **Phase:** Complete - HOLD before PR-004
- **Started:** 2026-08-20

### Actions Taken

- Read the complete PR-002 review and accepted its two prerequisite conditions.
- Activated an isolated PR-003 planning session; prior active plan to restore is `2026-08-19-realtime-dashboard-websocket-plan`.
- Froze scope to PIT universe foundation only; no factor, strategy, watchlist projection, CandidatePool, BuyScore, orders, or real-money changes.
- Restored root planning/catch-up context and inventoried the dirty worktree. Concurrent canonical pipeline/freshness/trade-management files are explicitly protected from this task.
- Read the approved PIT/watchlist architecture and code-review references. Discovery confirms PR-003 must separate historical research eligibility from current runtime admission and remain artifact-first.
- Added the frozen `institutional_partition_manifest_v1` public field/status contract, executable golden digest tests, and contract documentation.
- Added `architecture/institutional_source_coverage.md` with the exact reviewed TWSE/TPEx scopes and unsupported cases.
- Added the shared `watchlist.reference_data.EquityUniversePort` foundation with immutable date-effective records, explicit current/PIT evidence modes, research gates, and pinned-snapshot resolution.
- Added strict canonical snapshot/manifest codecs and a bytes-first import adapter; no network, persistence, ranking, strategy, runtime, or order behavior was introduced.
- Added reviewed fixtures and poison tests for listing, delisting, security-type, industry, market-cap cohort, current-snapshot, missing coverage/digest, overlapping intervals, source lineage, and immutable future revisions.
- Updated architecture status to PR-003 implemented/pending review and left PR-004/PR-005 on HOLD.

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `.venv/bin/pytest -q tests/test_institutional_serialization.py` | Manifest v1 freeze remains compatible | 14 passed | PASS |
| `.venv/bin/python -m compileall -q watchlist institutional_data` | New contracts compile | exit 0 | PASS |
| isolated import | `watchlist` imports and exports v1 schema | `pit_equity_universe_snapshot_v1` | PASS |
| institutional + PIT focused suite with coverage | All source/data/PIT gates pass | 69 passed, 88% combined line coverage | PASS |
| Ruff check/format + compileall | Clean source/style/import contracts | all passed | PASS |
| wheel build and workspace-external import | Package contains `institutional_data*` and `watchlist*` | wheel built; both frozen schemas imported | PASS |
| full repository regression | No regressions | 500 passed, 1 skipped | PASS |

### Errors
| Error | Resolution |
|-------|------------|
| Initial multi-operation patch targeted the same files twice | Replaced it with exact `Update File` operations. |
| `pytest: command not found` during first focused check | Switched to the repository `.venv` runtime. |
| `.venv/bin/ruff` was unavailable | Used the installed Ruff 3.13 binary; first pass found one unused test import, which was removed. |
| First coverage command named two non-existent institutional test files | Enumerated the repository's actual `test_institutional_*` files with `rg --files` and reran the exact set. |
| Future-revision test compared whole version rows, so an intentionally shortened `effective_to` made equal as-of classifications compare unequal | Compare the as-of security/classification/cohort projection while separately asserting the pinned artifact stays byte-identical. |
| Default isolated wheel build could not reach build requirements; `.venv` also lacked `setuptools.build_meta` | Used installed Python 3.13 build dependencies with `--no-build-isolation`; removed generated `build/` and restored generated egg-info changes afterward. |
