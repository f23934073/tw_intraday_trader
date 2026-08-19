# Task Plan: Add TAIFEX night-session detection to the premarket workflow

## Goal
Implement a repository-grounded, observation-only TAIFEX night-session premarket context with reproducible source evidence, separate context/reconciliation artifacts, durable storage, and no Candidate/Score/RiskGate/order effects.

## Current Phase
Complete

## Phases

### Phase 1: Requirements and repository discovery
- [x] Confirm plan/report-only scope and preserve unrelated worktree changes.
- [x] Trace the current premarket workflow, market-data abstractions, settings, API/UI output, and tests.
- [x] Record relevant prior repository decisions and current constraints in findings.md.
- **Status:** complete

### Phase 2: TAIFEX data and session semantics
- [x] Verify the current TAIFEX TX/TXM day/night session and Shioaji futures data contracts from primary sources.
- [x] Define trading-date attribution, reference prices, freshness, holiday/partial-session, and missing-data rules.
- [x] Define what can be called a market-context indicator versus a directional prediction.
- **Status:** complete

### Phase 3: Repository-aligned solution design
- [x] Map the smallest required backend, configuration, API, UI, and test changes to exact code areas.
- [x] Define a normalized premarket context model and score/gating policy without coupling stock scoring to raw provider payloads.
- [x] Specify observability, caching, rate limits, and fail-degraded behavior.
- **Status:** complete

### Phase 4: Implementation plan and validation strategy
- [x] Break delivery into dependency-ordered phases with acceptance criteria.
- [x] Cover unit, calendar/session, integration, replay/backtest, API/UI, and operational tests.
- [x] Define rollout, feature flag, rollback, and decision-quality validation.
- **Status:** complete

### Phase 5: Report authoring and delivery
- [x] Write the Traditional Chinese review report as a standalone Markdown artifact.
- [x] Cross-check it against repository evidence and primary-source constraints.
- [x] Verify only planning/report artifacts were changed and deliver the review gate.
- **Status:** complete

### Phase 6: Review corrections
- [x] Separate Shioaji provider reference from unproven TAIFEX settlement semantics.
- [x] Split Context Artifact from Reconciliation Artifact and define a projection-only join.
- [x] Correct historical backfill contract identity so it never uses the current `TXFR1.target_code` for past rows.
- [x] Make 05:05 query eligibility only; define READY from explicit completeness evidence.
- [x] Remove FLAT and all unvalidated categorical direction thresholds from v0.
- [x] Re-check the complete report for stale wording and verify no product-code changes.
- **Status:** complete

### Phase 7: Implementation baseline and bounded design
- [x] Capture current tests, worktree ownership, and repository instructions without disturbing unrelated changes.
- [x] Re-trace the current provider, runtime composition, dashboard projection, configuration, and UI seams against the approved report.
- [x] Freeze the minimum Phase 0-3 implementation slice and explicit fail-closed behavior where live source qualification is unavailable.
- **Status:** complete

### Phase 8: Core premarket contracts and services
- [x] Implement typed configuration, calendar/session resolution, immutable Context/Reconciliation artifacts, and canonical digests.
- [x] Implement observation-only context aggregation with signed metrics and a versioned completeness predicate.
- [x] Add focused unit tests for session attribution, artifact separation, historical identity, READY gating, and no FLAT/direction output.
- **Status:** complete

### Phase 9: Provider and dashboard integration
- [x] Add a narrow futures-context capability to Mock/Shioaji providers without changing stock DTO or broker-order behavior.
- [x] Inject the premarket service into runtime/dashboard composition with fail-degraded caching and projection-only reconciliation join.
- [x] Add provider, composition, dashboard API, and regression tests.
- **Status:** complete

### Phase 10: Traditional Chinese observation UI and documentation
- [x] Add the 台指期夜盤 panel with separate context health and reconciliation status.
- [x] Keep all calculations server-side and verify the UI has no FLAT/direction/regime classification.
- [x] Update README and strategy catalog while preserving `premarket_gap_watchlist_v1` as DRAFT.
- **Status:** complete

### Phase 11: Verification and handoff
- [x] Run focused tests, full regression, static/whitespace checks, and inspect the final diff for scope.
- [x] Record any live-source qualification limitation without overstating READY or TAIFEX reconciliation evidence.
- [x] Confirm Candidate, Score, RiskGate, simulation, and broker-order paths are unchanged.
- **Status:** complete

### Phase 12: Durable evidence repository
- [x] Define an artifact repository port and a filesystem append-only adapter for raw source, Context, and Reconciliation evidence.
- [x] Rehydrate stored Context/Reconciliation artifacts across process restarts with digest and path validation.
- [x] Wire runtime storage through explicit configuration while preserving an in-memory test adapter.
- **Status:** complete

### Phase 13: Shioaji source qualification
- [x] Verify current official historical tick/Kbar APIs and freeze a provider-neutral qualification report contract.
- [x] Implement a market-data-only capture/qualification workflow that never promotes completeness without explicit reviewed evidence.
- [x] Add SDK-free fixtures/tests plus a sanitized live smoke when credentials and source data are available.
- **Status:** complete

### Phase 14: TAIFEX reconciliation ingestion
- [x] Define a strict official-source input contract and adapter independent from Shioaji context acquisition.
- [x] Persist a separate Reconciliation Artifact keyed by context digest, trading date, and resolved contract code.
- [x] Expose stored reconciliation through the existing projection without changing context health.
- **Status:** complete

### Phase 15: Verification and handoff
- [x] Run focused and full regression tests, static checks, and final diff ownership review.
- [x] Update README/report with rerunnable commands, evidence status, and remaining qualification gates.
- [x] Reconfirm no FLAT threshold and no Candidate/Score/RiskGate/simulation/broker-order dependency.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Initial planning was report-only | Product implementation began only after the user explicitly replied `實作`. |
| Keep existing stock Tick/BidAsk and historical-download edits untouched | They are unrelated uncommitted user work. |
| Treat the prior night session as contextual evidence, not a guaranteed forecast | Futures-stock linkage is informative but can diverge at the cash open. |
| Use a separate `PremarketContextSource` port implemented by the existing Shioaji provider | Keeps domain boundaries clear while reusing the single authenticated SDK session. |
| Treat all five review points as corrections, not optional alternatives | They tighten evidence semantics and must be reflected consistently throughout the report. |
| Implement only approved Phase 0-3 behavior | Phase 4 research, 08:45 confirmation, and strategy influence still require later evidence or approval. |
| Fail closed when source completeness or historical identity is unqualified | The approved semantics prohibit time-only READY and current-alias historical backfill. |
| Continue with durable evidence before any strategy research | The user explicitly requested continued implementation; storage and reconciliation are the next observation-only gaps and do not broaden into Phase 4-6 strategy influence. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Combined initial reads were truncated | Re-read only the exact current-plan and repository files needed for decisions. |
| Ambient `python3 -m pytest` failed because pytest is not installed | Check the repository's existing virtual environment and use it if available; do not mutate dependencies merely for baseline collection. |
| First core test run passed 8 and failed 5 because the context artifact factory rehydrated canonical identity JSON instead of the `ContractIdentity` value object | Keep the canonical dict only for hashing and pass the original immutable identity object into the artifact constructor. |
| Test-first dashboard integration run failed because the optional premarket service and composition field were not implemented yet | Added the minimal constructor injection and runtime wiring without changing `ScanResult` or stock scan behavior. |
| Combined dashboard/runtime/planning patch placed planning-table context under the runtime file and was rejected atomically | Split product wiring and planning-record updates into separate scoped patches. |
| Phase 12 test-first run failed collection because the filesystem repository and text digest helper did not exist yet | Implemented the tested port/adapter and reran the focused suite successfully. |
| Phase 13 Shioaji provider test initially lacked the qualification capability | Added deterministic Mock and SDK-backed Shioaji capture methods behind the provider port. |
| First live qualification reported duplicate Tick order plus close -9 and volume +12 deltas | Raw evidence showed duplicate Tick timestamps are valid and the exact 05:00 minute-end Kbar was excluded; allow nondecreasing Tick order and normalize source Kbars from `(start, end]` to domain `[start, end)` timestamps. |
| First post-Phase-14 full suite found repeated Mock raw payloads colliding only on `captured_at` | Keep raw payload SHA as the content address, preserve the first immutable capture metadata, and make identical schema/source/payload saves idempotent; focused regression passes. |
