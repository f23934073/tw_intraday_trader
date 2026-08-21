# Findings & Decisions

## Requirements
- PR-006 result is `APPROVED WITH CONDITIONS`.
- The authorized next slice is `PR-007 CandidatePool Shadow Admission`.
- PR-007 is `Shadow only` and `Data admission only`.
- PR-007 must not add live trading, BuyScore integration, or broker execution.
- Candidate Prior v0 must remain schema-frozen; PR-007-specific translation belongs in an adapter.
- The adapter path is Candidate Prior Repository -> PreviousSessionWatchlistCandidateSource -> CandidatePool.
- CandidatePool may know only symbol, source, rank, and evidence reference; it must not know institutional formulas, trust factor, digest internals, or PIT calculations.
- Current-session eligibility must be evaluated against T-day InstrumentReferenceStore, not copied directly from the T-1 PIT universe.
- Admission must protect manual candidates, active positions, subscription headroom, and provider limits; it must not subscribe every institutional candidate.
- The review recommends a real PostgreSQL adapter test when `TEST_POSTGRES_DSN` is available, but explicitly treats its absence as non-blocking.

## Research Findings
- The review approves Candidate Prior v0 as a durable, verifiable, replayable storage layer.
- It approves contract separation between CandidatePriorArtifact and performance/evaluation artifacts; forward_return, IC, ICIR, win_rate, and expectancy remain forbidden in Candidate Prior.
- It approves the institutional_prior bounded persistence namespace, canonical-JSON-first domain design, shared SQLite/PostgreSQL repository, fail-closed non-deterministic replay handling, and read-time integrity verification.
- PR-006 verification accepted by the reviewer: 728 passed, 2 skipped; focused coverage 92%; serialization 95%; SQL repository 92%; lint/format/compile/diff/wheel/isolated import all passed.
- The supplied file ends at line 695 immediately after saying PR-007 should validate rather than add strategy; no additional acceptance-test list follows in the attachment.
- Existing `CandidatePool` protects manual/position and active-episode symbols, but its read model currently drops discovery evidence.
- Existing `SubscriptionManager` already fails closed without reviewed headroom/mode and never exceeds provider capacity, but invoking it would create mutable subscription-request state and is therefore outside this shadow-only slice.
- `CandidateSource` currently lacks `PREVIOUS_SESSION_WATCHLIST`; dashboard projection explicitly folds its existing input to `AUTO`, so the new source must stay on an independent adapter path.
- `InstrumentReferenceStore` is session-scoped and clears references on session rollover; `eligible(symbol)` is the appropriate T-day gate.
- Candidate Prior v0 projections contain target/as-of session, rank, hypothesis IDs, artifact ID/digest, and entry digest while retaining all readiness flags as false.
- The existing PR-007 plan exit gate is exactly: independent previous-session adapter, current-session eligibility, reviewed headroom, pool/admission metrics, no orders, preserved source/evidence, protected-capacity invariants, and unchanged BuyScore/order semantics.
- The worktree contains many concurrent tracked and untracked user changes; edits must be limited to new PR-007 files and the smallest candidate model/pool/source exports needed for integration.
- `TEST_POSTGRES_DSN` is not set in this environment, so the reviewer-approved PostgreSQL test remains unavailable and non-blocking.
- Final review found and fixed a double-count edge case where an institutional-only discovery was also an active episode; protected selection now excludes it from incremental institutional allocation.
- Final full regression is 743 passed and 2 skipped; the only PR-006 PostgreSQL adapter skip remains caused by absent `TEST_POSTGRES_DSN`.
- Final wheel was built from a temporary staging copy, includes both PR-007 modules, imports outside the checkout, and has SHA256 `14e4ecb63da6a6385101f4bdbdc8cfdb61cbe2f67938dd02e579dbc1dfb54a43`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Do not infer the detailed PR-007 design from earlier plans | The supplied review is the current gate and must be read in full. |
| Reuse Candidate Prior through an adapter boundary only where the PR-007 contract requires it | This preserves the approved persistence/domain separation. |
| Treat institutional candidates as lowest-priority shadow admissions after protected usage | This matches the capacity-protection review focus and prevents resource starvation. |
| Do not call SubscriptionManager in PR-007 | Even without a provider adapter, it records subscribe-request transitions; the review permits data/shadow only. |
| Keep Candidate Prior projection semantics unchanged | The source filters and translates projections but never mutates or reserializes the artifact. |
| Keep SubscriptionManager entirely outside the implementation imports | This prevents shadow evaluation from creating subscribe-request state even accidentally. |

## Planned Change Surface
- `candidate/models.py`: add the explicit `PREVIOUS_SESSION_WATCHLIST` source enum.
- `candidate/sources.py` and `candidate/pool.py`: add an immutable bounded contribution reference and preserve it in pool decisions/digests.
- `candidate/previous_session.py`: repository-to-discovery adapter with target-session and T-day instrument eligibility gates.
- `candidate/shadow_admission.py`: pure residual-capacity/budget decision and metrics; no provider calls.
- `tests/test_institutional_candidate_shadow_admission.py`: adapter, eligibility, source/evidence, capacity, protected-symbol, determinism, and prohibited-boundary tests.
- `architecture/contracts/institutional_candidate_shadow_admission_v0.md` plus scoped plan/contract status updates.

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- `/Users/stevehuang-work/.codex/attachments/874b3f24-de2e-4ed5-8329-e3f9a60fcf22/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader/.planning/2026-08-20-pr006-review-followup/`
