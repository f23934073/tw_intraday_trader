# Task Plan: PR-003 PIT Equity Universe Foundation

## Goal
Close the two PR-002 review conditions, then implement a date-effective point-in-time equity universe foundation that PR-004 can depend on without survivorship, security-type, industry, or market-cap look-ahead.

## Current Phase
Complete — HOLD before PR-004

## Phases

### Phase 1: Review conditions and repository discovery
- [x] Read the PR-002 review and freeze conditions/scope.
- [x] Inspect current institutional contracts, previous-day watchlist universe seams, reference-data code, and concurrent worktree changes.
- [x] Define verifiable PR-003 exit gates from the approved plan.
- **Status:** completed

### Phase 2: PR-002 conditions
- [x] Add explicit `InstitutionalPartitionManifest v1` freeze tests/documentation.
- [x] Add `institutional_source_coverage.md` with supported and unsupported cases.
- **Status:** completed

### Phase 3: PIT universe contract and artifacts
- [x] Implement minimal date-effective security/universe snapshot contracts.
- [x] Implement deterministic canonical artifact/digest and as-of query port.
- [x] Reuse/extend the existing watchlist universe boundary; do not create an institutional-only universe subsystem.
- **Status:** completed

### Phase 4: Fixtures and poison tests
- [x] Add fixtures covering delisting, listing, security-type, industry, and market-cap changes.
- [x] Verify historical as-of queries include disappeared symbols and never use future revisions.
- [x] Verify missing coverage/digest or current-only snapshots return `PIT_UNIVERSE_MISSING` and block research eligibility.
- **Status:** completed

### Phase 5: Verification and delivery
- [x] Run focused tests/coverage, Ruff, compile, package, and scoped regression.
- [x] Confirm no PR-004/PR-005 code or runtime integration was added.
- [x] Update architecture status, restore the prior planning pointer, and report the next HOLD gate.
- **Status:** completed

## Scope Boundary

- In scope: PR-002 manifest schema freeze evidence, source coverage matrix, PIT universe contracts/artifacts/query port, reviewed fixtures, poison tests, packaging and documentation.
- Out of scope: institutional factors, ranking, backtests, watchlist generation, CandidatePool, BuyScore, live admission, orders, real money.
- Real Money: PROHIBITED.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Close both PR-002 conditions before PR-003 code | The review marks them as prerequisites for stable lineage. |
| Extend a shared/watchlist universe boundary | The approved design forbids an institutional-only universe subsystem. |
| Keep current snapshots research-ineligible | A present-day contract list cannot prove historical membership. |
| Require identity plus content digest | PR-003 lineage must compose cleanly with institutional/calendar artifacts. |
| Stop before factor or strategy work | PR-004 and PR-005 remain explicitly blocked. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Initial multi-operation patch targeted the same planning files twice | Switched to exact template updates with `apply_patch`. |
| `pytest` was not on the shell `PATH` | Located the repository runtime at `.venv/bin/pytest`; verification uses `.venv/bin/python` / `.venv/bin/pytest`. |
| `.venv/bin/ruff` does not exist | Located the installed Ruff binary at `/Library/Frameworks/Python.framework/Versions/3.13/bin/ruff`. |
| Isolated wheel build attempted to download build requirements, then `.venv` lacked `setuptools.build_meta` | Reused the installed Python 3.13 setuptools/wheel backend with `--no-build-isolation`; wheel and isolated imports passed without a network download. |
