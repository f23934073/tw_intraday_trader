# Task Plan: PR-TM-012C1 next-session preparation

## Goal

Create a fail-closed 2026-08-27 input-draft review workflow whose outputs cannot be mistaken for reviewed C1 inputs, and write a review-only design for running the existing C0/C1 entrypoints outside the current network-restricted sandbox without installing or enabling it.

## Current Phase

Phase 5 - Verification and handoff

## Phases

### Phase 1: Contract and source audit
- [x] Inventory existing EntryDecision/Draft serializers, Shadow/Risk policy contracts, and candidate source artifacts.
- [x] Confirm canonical C1 input-path behavior and prevent draft promotion by filename/location alone.
- [x] Record unrelated dirty-worktree boundaries.
- **Status:** completed

### Phase 2: Freeze failing tests and architecture
- [x] Define immutable `PENDING_REVIEW` review-packet contract and digest rules.
- [x] Keep preparation core free of provider, database, broker, order, and automation dependencies.
- [x] Add failing tests for unsafe status/path/digest/parity cases.
- **Status:** completed

### Phase 3: Implement draft workflow
- [x] Add the smallest repository entrypoint that validates supplied candidate inputs and writes only to a non-canonical draft root.
- [x] Produce a 2026-08-27 pending-review packet if legitimate source artifacts exist; otherwise preserve explicit missing-source blockers.
- [x] Do not create or modify canonical `session_inputs/2026-08-27/` files.
- **Status:** completed

### Phase 4: External execution design
- [x] Document a narrow, review-only local runner design that invokes only the committed C0/C1 scripts.
- [x] Specify least privilege, exact command allowlist, immutable outputs, environment/DSN isolation, watchdog, and rollback.
- [x] Do not install, schedule, enable, or alter the existing Codex automation.
- **Status:** completed

### Phase 5: Verification and handoff
- [x] Run focused tests, compilation, CLI help, and whitespace checks.
- [x] Verify no execution-capable imports or canonical reviewed artifacts were introduced.
- [x] Update automation memory with the exact disposition.
- **Status:** completed

## Success Criteria

- Draft artifacts are stored outside `research/trade_management_shadow/session_inputs/` and explicitly say `PENDING_REVIEW` and `reviewed=false`.
- The workflow cannot invent a LiveEntryDecision, order, fill, RiskSnapshot, or policy; every candidate payload must come from an explicit source file.
- Draft validation proves canonical deserialization, EntryDecision/Draft parity, session/date/symbol/policy bindings, and deterministic content digests.
- No draft output can be consumed by formal C1 without a separate, explicit human review/promotion step that is not performed in this task.
- The external execution proposal does not use `danger-full-access`, does not introduce another trading runner, and invokes only the committed C0/C1 entrypoints.
- Production Shadow Gate remains `NOT_PASSED`.

## Errors Encountered

| Error | Resolution |
|-------|------------|
| Expected test collection failed because `scripts.prepare_trade_management_shadow_inputs` did not exist | Implement the reviewed-boundary CLI and rerun the same focused test once. |
| Draft CLI initially imported the C0 module solely for runtime identity, transitively loading the Shioaji adapter | Extracted the unchanged source-digest algorithm to a pure runtime module and added an isolated import-boundary regression test. |
