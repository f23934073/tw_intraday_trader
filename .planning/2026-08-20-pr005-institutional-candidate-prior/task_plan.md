# Task Plan: PR-005 Institutional Candidate Prior

## Goal
Implement two immutable, reproducible premarket Candidate Prior hypotheses from approved institutional research evidence without creating entry, BuyScore, runtime, broker, or production-trading behavior.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Read the complete PR-004 review and authorization for PR-005.
- [x] Inspect approved PR-005 architecture and existing previous-session candidate/artifact seams.
- [x] Freeze the two authorized hypotheses, conditions, lineage inputs, and protected concurrent files.
- **Status:** completed

### Phase 2: PR-004 conditions and PR-005 contracts
- [x] Add explicit exploratory/strategy-ready/production-ready report semantics without changing research conclusions.
- [x] Freeze primary institutional factor lookback at 5D; keep 1D/3D outcome horizons secondary/exploratory.
- [x] Define immutable Candidate Prior input/output manifests and canonical digests.
- **Status:** completed

### Phase 3: Candidate Prior hypotheses
- [x] Implement PR-005-A institutional momentum confirmation using a pinned price-momentum candidate artifact plus approved institutional factors.
- [x] Implement PR-005-B foreign/trust consensus as a candidate-only hypothesis.
- [x] Keep Candidate Prior distinct from entry eligibility, BuyScore, CandidatePool, subscriptions, runtime, paper fills, broker APIs, and orders.
- **Status:** completed

### Phase 4: Lineage and poison gates
- [x] Prove same inputs/definition reproduce the same prior artifact digest.
- [x] Prove target/future data, PIT/report ineligibility, digest mismatch, and stale/missing price prior fail closed.
- [x] Prove output remains candidate-only and cannot claim strategy/production readiness.
- **Status:** completed

### Phase 5: Verification and review gate
- [x] Run focused coverage, Ruff/format/compile, package/wheel, adjacent, and full regressions.
- [x] Audit production imports and protected worktree changes.
- [x] Update architecture status, restore the previous active-plan pointer, and stop at the PR-005 review gate.
- **Status:** completed

## Scope Boundary

- In scope: PR-004 schema conditions, two versioned Candidate Prior hypotheses, immutable lineage/artifact serialization, tests and contracts.
- Out of scope: direct buy/sell rules, entry triggers, BuyScore changes, CandidatePool admission, watchlist runtime source wiring, dashboard/API, subscription changes, paper/live execution, broker orders, real money, optimizer/ML, additional factor families.
- Candidate Prior is research-derived evidence, not a Trading Strategy.
- All outputs remain exploratory; strategy-ready and production-ready are false.
- Real Money: PROHIBITED.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Implement PR-005-A and PR-005-B only | The review explicitly narrows the first PR-005 version to these two hypotheses instead of four strategies. |
| Treat them as Candidate Prior definitions | The review requires Candidate Prior to remain separate from entry and trading strategy semantics. |
| Preserve the 5D factor as primary | The review forbids selecting a best lookback after inspecting diagnostics and recommends fixing 5D before PR-005. |
| Preserve unrelated worktree changes | Canonical market, freshness, trade-management, and earlier institutional work are concurrent scopes. |
| Do not register PR-005 in the executable strategy catalog | These are research Candidate Prior hypotheses; catalog binding and runtime admission are outside this gate. |
| Store evaluation arms but project only matched hypotheses | Price-only/flow-only/combined memberships are needed for later incremental evaluation, while the read-only Candidate Prior projection must not present unmatched controls as candidates. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
