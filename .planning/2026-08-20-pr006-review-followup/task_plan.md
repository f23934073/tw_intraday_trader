# Task Plan: PR-006 Review Follow-up and PR-007 CandidatePool Shadow Admission

## Goal
Complete the approved PR-006 follow-up by implementing and verifying only the PR-007 CandidatePool shadow data-admission slice defined by the supplied review, without BuyScore, broker, order, or live-trading integration.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm the supplied review result and transition authorization
- [x] Read all PR-007 requirements, invariants, and acceptance tests
- [x] Inspect the current repository and overlapping user changes
- [x] Document initial findings in findings.md
- **Status:** completed

### Phase 2: Planning & Structure
- [x] Map the requested contract to existing Candidate Prior and candidate-domain seams
- [x] Define the smallest independent implementation and test surface
- **Status:** completed

### Phase 3: Implementation
- [x] Implement only CandidatePool shadow data admission and its contract/docs/tests
- [x] Keep BuyScore, subscriptions, broker execution, orders, and live trading unchanged
- **Status:** completed

### Phase 4: Testing & Verification
- [x] Run focused contract/unit/integration tests
- [x] Run adjacent and full regression checks proportionate to the change
- [x] Verify packaging/import and prohibited-boundary invariants
- **Status:** completed

### Phase 5: Delivery
- [x] Review the scoped diff and preserve unrelated worktree changes
- [x] Restore the pre-existing active plan pointer
- [x] Deliver implementation, evidence, residual limitations, and next gate
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Treat the review as authorization for PR-007 only | It says PR-006 is approved with conditions and explicitly permits CandidatePool Shadow Admission. |
| Keep PR-007 shadow/data-admission only | The review expressly prohibits live trading, BuyScore integration, and broker execution. |
| Preserve PR-006 bounded persistence namespace | The review approves the independent institutional_prior persistence boundary and adapter integration only when needed. |
| Freeze InstitutionalCandidatePriorArtifact v0 | PR-007 requirements must be translated in an adapter, not added to the prior artifact schema. |
| Determine eligibility from T-day InstrumentReferenceStore | The review forbids directly using the T-1 PIT universe as the runtime subscription universe. |
| Apply admission after protected-capacity accounting | Manual candidates, active positions, subscription headroom, and provider limits have priority over institutional candidates. |
| Add a dedicated previous-session source module | It is an interface adapter from CandidatePriorRepository to generic CandidateDiscovery, avoiding CandidatePool knowledge of institutional formulas. |
| Add bounded contribution references to pool entries | Artifact ID plus entry digest preserves auditability without copying institutional features or unbounded evidence. |
| Keep capacity evaluation pure and shadow-only | A deterministic decision can validate provider/headroom/protected invariants without emitting subscribe, score, order, or broker operations. |
| Preserve existing non-institutional candidates before allocating institutional residual capacity | PR-007 must not displace the existing runtime universe; institutional candidates consume only residual reviewed headroom and their own budget. |
| Count a protected institutional-only active episode once | A protected pool entry is already selected and must not consume or duplicate an incremental institutional slot. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
