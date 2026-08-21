# Task Plan: Institutional Data Contract PR-001

## Goal

Implement the approved, contract-only first slice for institutional daily flow data and revise the architecture plan to reflect the reviewer-approved PR ordering, without migrations, persistence, source adapters, strategy logic, APIs, UI, CandidatePool, live ingestion, or broker behavior.

## Current Phase

Complete

## Phases

### Phase 1: Scope and repository discovery

- [x] Read the reviewer feedback completely.
- [x] Freeze the PR-001 allowlist and explicit non-goals.
- [x] Inspect current domain, serialization, validation, test, packaging, and numeric conventions.
- [x] Record reuse opportunities and incompatibilities.
- **Status:** completed

### Phase 2: Contract and test design

- [x] Freeze minimal domain types, invariant ownership, serialization shape, and validation outcomes.
- [x] Define fixtures and success/failure cases before product implementation.
- [x] Revise the implementation plan to split Phase 1A contract artifacts from later migration/persistence.
- **Status:** completed

### Phase 3: PR-001 implementation

- [x] Add only `institutional_data/domain.py`, `serialization.py`, `validation.py`, package init, fixtures, and focused tests.
- [x] Keep implementation dependency-free, deterministic, immutable, and Decimal/int-safe.
- [x] Do not add migration, repository, source adapter, strategy, runtime, API, UI, or live ingestion.
- **Status:** completed

### Phase 4: Testing and review

- [x] Run focused tests, relevant regression tests, compilation, packaging/import, and whitespace checks.
- [x] Review diff for scope, overengineering, future-data assumptions, and accidental user-change overlap.
- [x] Confirm the existing freshness-calibration work and active planning pointer are preserved.
- **Status:** completed

### Phase 5: Delivery

- [x] Summarize contracts, validation behavior, tests, and deferred work.
- [x] Provide exact file links and call out any approval gate before PR-002.
- **Status:** completed

## Success Criteria

1. `InstitutionalFlowDaily` and `InstitutionalPartitionManifest` reject malformed identity/time/numeric contracts at construction.
2. Canonical serialization and SHA256 are deterministic and round-trip without float conversion.
3. Validation reports formula, trade-scope compatibility, duplicate/mismatched identity, and partition-level failures without fetching data or writing persistence.
4. Official-source-shaped fixtures cover valid TWSE/TPEx normalized contracts and representative invalid cases; they do not implement network parsers.
5. All new and relevant existing tests pass; no out-of-scope product surface changes.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Treat the attached review as authorization for PR-001 only | It explicitly says the project may start and the first PR must be data contracts only. |
| Use JSON fixtures/artifacts before SQL migration | Reviewer wants schema stabilization before `005_institutional.sql`. |
| Keep Phase 1 factor scope out of executable strategy code | Research hypotheses must not be frozen as trading rules in this slice. |
| Preserve root Phase 13 freshness work | Existing modified files and evidence are user/concurrent work outside this PR. |
| Allow one `pyproject.toml` include-list edit | Without `institutional_data*`, the approved package would not ship in the built distribution. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Root planning-file read exceeded direct output budget | The files were read by the command; use the isolated PR-001 session for all new planning updates and avoid modifying root planning files. |
| First planning-file replacement patch used unsupported delete-and-add operations on the same path | Split the operation into one delete patch followed by one add patch. |
| Initial focused tests failed collection because PR-001 modules did not exist | Expected red test-first baseline; implement only the approved modules next. |
| `.venv/bin/ruff` does not exist | Use the discovered system Ruff binary at `/Library/Frameworks/Python.framework/Versions/3.13/bin/ruff`; do not install dependencies. |
| Initial code-review reference paths used `references/` instead of the installed `reference/` directory | Listed the skill package and will read the required Python/universal references from their actual paths. |
| Virtualenv package-discovery check could not import setuptools | Use the existing system Python 3 setuptools 80.9.0 for the read-only discovery check; do not install dependencies. |
| Ruff format check found six new Python files not canonical | Run Ruff formatter only on PR-001-owned files, then rerun lint/tests; do not format unrelated files. |
