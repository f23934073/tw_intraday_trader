# Task Plan: Review paper-trading sell readiness

## Goal

Determine whether the current local paper-trading strategies have a complete sell path, and identify evidence-backed gaps without changing product code.

## Phases

### Phase 1: Context and scope
- [x] Read the referenced Codex task's recent strategy and execution decisions.
- [x] Preserve the existing dirty worktree and isolate review notes.
- [x] Trace earlier referenced-task turns needed for concrete acceptance criteria.
- **Status:** complete

### Phase 2: Architecture and implementation trace
- [x] Map signal/recommendation, eligibility, order submission, fill, position, and journal boundaries.
- [x] Inspect sell-side rules and their runtime wiring.
- [x] Inspect persistence/restart, ownership, market-data freshness, and fail-closed behavior.
- **Status:** complete

### Phase 3: Tests and runtime verification
- [x] Map existing sell-focused tests to required failure and edge cases.
- [x] Run focused tests and read-only scenario probes proportional to the review scope.
- [x] Run final full/static regression checks and record results.
- **Status:** complete

### Phase 4: Readiness decision
- [x] Classify confirmed capabilities and gaps by severity.
- [x] Separate implemented behavior, tested behavior, and plan-only behavior.
- [x] Deliver prioritized remediation recommendations with exact file evidence.
- **Status:** complete

## Readiness Decision

- Supervised local-paper lifecycle smoke: CONDITIONAL GO.
- Unattended automated paper trading: NO-GO until ownership, executable-book freshness, exit order lifecycle/result handling, and daily-loss flatten ordering are fixed and tested.
- General strategy sell platform: NOT IMPLEMENTED; current automation is one hard-coded Momentum controller, while thesis exits and backtest exits remain separate decision/research paths.

## Constraints

- Review only; do not implement fixes.
- Do not reset, overwrite, or commit existing user changes.
- Treat local paper simulation as market-data-only unless current code proves otherwise.
- Do not equate an EXIT recommendation with a successfully closed position.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `read_thread` rejected `turnLimit=40` | 1 | Re-read with the supported maximum of 10 turns and paginate as needed. |
| `rg` referenced a missing `Makefile` while inspecting test configuration | 1 | Read `pyproject.toml` directly; the repository has no Makefile gate. |
