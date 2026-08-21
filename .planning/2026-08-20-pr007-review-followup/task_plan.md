# Task Plan: PR-007 Conditions and PR-008 Formal Evaluation

## Goal
Close the approved PR-007 shadow-semantics conditions, then implement the smallest PR-008 formal evaluation slice that compares frozen candidate arms under identical setup/outcome/cost definitions without changing BuyScore, entry/exit, subscription, broker, or order behavior.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Read the complete supplied PR-007 review
- [x] Identify PR-007 conditions and PR-008 authorization
- [x] Inspect existing evaluation, backtest, paper-simulation, and artifact contracts
- [x] Document initial findings in findings.md
- **Status:** completed

### Phase 2: Planning & Structure
- [x] Map PR-008 arms, metrics, manifests, costs, and holdout gates to existing seams
- [x] Define the smallest frozen evaluation artifact and test surface
- **Status:** completed

### Phase 3: Implementation
- [x] Make PR-007 shadow result explicitly non-actionable
- [x] Implement PR-008 formal evaluation without changing runtime trading semantics
- **Status:** completed

### Phase 4: Testing & Verification
- [x] Run focused evaluation/poison/determinism tests and coverage
- [x] Run adjacent and full regressions, compile, diff, and wheel checks
- **Status:** completed

### Phase 5: Delivery
- [x] Review scoped diff and preserve unrelated worktree changes
- [x] Restore the prior active plan pointer
- [x] Deliver implementation evidence, residual limitations, and next gate
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Treat PR-007 as approved and PR-008 as authorized | The supplied review explicitly marks PR-008 ready to start. |
| Close PR-007 explicit shadow semantics before PR-008 | The remaining condition asks for SHADOW mode plus false subscription/execution side effects to prevent misinterpretation. |
| Keep institutional prior outside BuyScore and entry rules | PR-008 must measure candidate quality and execution quality under identical rules, not create a new trading signal. |
| Keep real-money and live subscription out of scope | Review and repository safety boundary remain data/research/paper only. |
| Do not claim PR-008 evidence completion | The engine and contract are implemented, but no owner-approved real holdout population or result exists yet. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
