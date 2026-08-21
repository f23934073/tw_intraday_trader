# Task Plan: Institutional PR-001 review fixes

## Goal

Resolve the four blocking review conditions in the institutional-data plan and PR-001 code, verify the implementation, and keep PR-002 on HOLD.

## Current Phase

Complete

## Phases

### Phase 1: Review intake and scope freeze
- [x] Read the supplied review completely.
- [x] Confirm the authorized scope is PR-001 plus implementation-plan corrections.
- [x] Preserve PR-002 HOLD and the research/data-only boundary.
- **Status:** complete

### Phase 2: Repository and code review
- [x] Inspect PR-001 domain, serialization, validation, exports, tests, and plan references.
- [x] Identify correctness gaps and the smallest compatible API change.
- [x] Record unrelated worktree changes and avoid them.
- **Status:** complete

### Phase 3: Surgical implementation
- [x] Add explicit component-reconciliation statuses and NULL behavior.
- [x] Add regression tests for absent and mismatched dealer components.
- [x] Correct the plan with PIT PR/gates, manifest digests, renumbering, and status consistency.
- **Status:** complete

### Phase 4: Verification and re-review
- [x] Run focused tests, package coverage, full suite, lint/format, compilation, packaging, and whitespace checks.
- [x] Re-review the resulting diff for API, design, and scope correctness.
- [x] Confirm no PR-002 adapter or downstream strategy/runtime code was added.
- **Status:** complete

### Phase 5: Delivery
- [x] Restore the pre-existing active planning pointer.
- [x] Prepare the decision, changed files, validation evidence, and remaining HOLD gate.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Treat the supplied review as authorization to fix PR-001 and the plan only | It explicitly conditions approval on four corrections and preserves PR-002 HOLD. |
| Implement dealer NULL semantics in the PR-001 validation contract | This is the only requested condition that changes existing PR-001 code. |
| Keep PIT universe and ResearchRunManifest as planned later-PR work | The review asks for ownership and contracts, not premature implementation in PR-001. |
| Use a separate isolated planning directory | Root planning files contain concurrent Freshness work and must remain untouched. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Initial combined root-planning read exceeded output limits | The current phase and boundaries were visible; use scoped reads from this isolated plan and repository files from here onward. |
| System `python3` has no pytest module | Locate and use the repository's existing virtual environment before treating tests as run. |
| Neither `.venv/bin/ruff` nor the `.venv` Ruff module exists | Locate the already available Ruff executable without installing or mutating dependencies; retain separate compile/test/whitespace evidence if unavailable. |
| The `.venv` does not include the `build` module | Use existing pip/setuptools with no build isolation and a temporary output directory; do not install dependencies. |
| `.venv` pip wheel cannot import `setuptools.build_meta` | Use the system Python's existing setuptools 80.9.0 as a materially different offline build path. |
