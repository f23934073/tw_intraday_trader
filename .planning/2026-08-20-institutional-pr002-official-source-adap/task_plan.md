# Task Plan: PR-002 Official Source Adapter

## Goal

Implement fixture-driven TWSE and TPEx official-source adapters that preserve immutable raw evidence and produce verified PR-001 normalized artifacts, without strategy or runtime integration.

## Current Phase

Complete

## Phases

### Phase 1: Scope and repository discovery
- [x] Read the approved review and freeze PR-002 scope.
- [x] Inspect current PR-001 contracts and repository artifact patterns.
- [x] Inspect official captured fixture availability and source-shape requirements.
- **Status:** completed

### Phase 2: Contract and test design
- [x] Define source response envelopes, parser revisions, capture identity, and revision semantics.
- [x] Add tests for TWSE/TPEx replay and all exit gates.
- **Status:** completed

### Phase 3: PR-002 implementation
- [x] Implement immutable raw capture/revision catalog.
- [x] Implement TWSE and TPEx parsers/adapters into PR-001 artifacts.
- [x] Add reviewed captured fixtures and expected normalized outputs.
- [x] Update the implementation plan with the approved PR names and exit gates.
- **Status:** completed

### Phase 4: Verification and review
- [x] Run focused tests/coverage, full regression, lint/format, compile, package, and whitespace checks.
- [x] Verify date pollution, raw immutability, source revision, schema drift, empty response, scope mismatch, and formula failure gates.
- [x] Confirm no feature/ranking/watchlist/CandidatePool/PR-003 code exists.
- **Status:** completed

### Phase 5: Delivery
- [x] Restore the pre-existing planning pointer.
- [x] Deliver changed files, evidence, review decision, and next HOLD gate.
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Implement only PR-002 source-to-artifact flow | The approved review explicitly authorizes Official Source Adapter implementation and prohibits strategy scope. |
| Use captured fixture replay as the deterministic default | Tests and review must not depend on live network responses. |
| Preserve raw bytes before parsing | Parser failure must not destroy source evidence. |
| Create immutable revisions on content change | Same market/date/scope with different bytes must never overwrite evidence. |
| Keep PR-003 and later phases blocked | User authorized the next PR only. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Root planning read exceeded the display budget | Relevant active phase and dirty-worktree boundaries were visible; continue in this isolated plan. |
| `python` and `.venv/bin/ruff` were unavailable | Used `.venv/bin/python` and the system Ruff binary. |
| Python 3.13 rejected TPEx's trusted chain under `VERIFY_X509_STRICT` | Kept CA/hostname verification and cleared only the incompatible strict-chain flag; live smoke passed. |
| Concurrent untracked market-event test blocked final full collection | Preserved that scope; earlier full run passed and final run excluding only that new test passed 471/1. |
