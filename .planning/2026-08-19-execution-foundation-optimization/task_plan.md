# Task Plan: Execution Foundation Optimization

## Goal

Make the local paper-simulation and research runtime internally consistent, fail-closed, and observable without adding any broker-order, CA, or real-money capability.

## Current Phase

Phase 6 — Verification and delivery

## Phases

### Phase 1: Baseline and compatibility mapping

- [x] Preserve the existing dirty worktree and identify unrelated changes.
- [x] Confirm the direct SimulationService route, unwired RiskGate/Journal seam, unbounded quote queue, and full-memory backtest load.
- [x] Freeze the current local API response contract with focused tests before changing the command path.
- **Status:** completed

### Phase 2: Local-paper command consistency

- [x] Route submit/cancel through one local-paper application facade.
- [x] Reserve pending BUY cash and release it on terminal status.
- [x] Use Decimal internally for local-paper money and preserve JSON number API compatibility.
- [x] Record command and terminal outcome evidence in the existing in-memory Journal.
- **Status:** completed

### Phase 3: Market-data safety and observability

- [x] Replace the unbounded simulation ingress with a bounded queue and explicit overflow state.
- [x] Expose local readiness/health state without querying broker account APIs.
- [x] Add structured, local process diagnostics for stream state and command outcomes.
- **Status:** completed

### Phase 4: Research-runtime efficiency and guardrails

- [x] Add an iterator-based dataset read path and avoid redundant sort/load work where possible.
- [ ] Preserve existing manifest checksum and fail-closed semantics.
- [ ] Add a concrete data-quality projection so exploratory datasets cannot be misrepresented as research-approved.
- **Status:** completed (external evidence remains intentionally fail-closed)

### Phase 5: Presentation and quality gates

- [x] Keep dashboard edits to its existing native script boundary; a broad split would mix with active user changes and add regression risk.
- [x] Add endpoint and browser-contract coverage for the order lifecycle and health rendering.
- [ ] Add lint/type/reproducibility configuration only if it runs in the existing local toolchain.
- **Status:** in_progress

### Phase 6: Verification and delivery

- [x] Run focused, full, static, and regression checks.
- [x] Restore the prior active planning pointer and report all remaining evidence-dependent work.
- **Status:** completed

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Scope local paper only | The user authorized optimizations, not broker orders; `subscribe_trade=False`, no CA, and no account APIs remain invariants. |
| Incremental modular-monolith migration | Reuse existing `trading/` contracts rather than add a second execution architecture or microservices. |
| Money changes are internal first | API responses remain JSON numbers for dashboard compatibility while correctness uses Decimal and reservations. |
| Data-quality evidence stays fail-closed | Historical-universe and real freshness calibration need external immutable data; code must not invent a pass state. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| None | — |
