# Task Plan: PR-TM-012C1 adversarial review remediation

## Goal

Fix the reviewed input-draft, promotion, immutable-retry, and external execution-boundary findings without installing a runner, changing automation, creating reviewed inputs, or invoking C0/C1.

## Current Phase

Complete

## Phases

### Phase 1: Freeze contracts and failing tests
- [x] Define versioned immutable draft attempt paths and complete artifact-pair semantics.
- [x] Define a separate reviewer approval artifact and digest-preserving canonical promotion contract.
- [x] Add failing tests for retry, TOCTOU, approval bypass, RiskSnapshot provenance, and incomplete pairs.
- **Status:** completed

### Phase 2: Implement draft and promotion boundaries
- [x] Read each candidate exactly once and validate the same bytes that are hashed.
- [x] Add immutable attempt identity and source provenance.
- [x] Add a separate reviewed approval/promotion entrypoint that creates canonical files exclusively.
- **Status:** completed

### Phase 3: Enforce formal C1 admission
- [x] Require the immutable approval artifact and verify reviewer identity, approved attempt, packet, and four canonical digests.
- [x] Reject symlinked canonical input paths and incomplete approval/input pairs.
- [x] Preserve all no-execution and dedicated-DSN gates.
- **Status:** completed

### Phase 4: Close external execution design gaps
- [x] Document the complete child process graph and exact executable/argv policy.
- [x] Require an atomic cross-supervisor lock and define ownership/rollback behavior.
- [x] Define graceful termination and terminal artifact inventory semantics; do not install anything.
- **Status:** completed

### Phase 5: Verification and handoff
- [x] Run focused tests, full suite, compilation, CLI help, import-boundary checks, and diff checks.
- [x] Confirm no canonical 2026-08-27 inputs, automation, service, permissions, provider, database, or execution state changed.
- [x] Update automation memory with exact disposition.
- **Status:** completed

### Phase 6: Freeze second-review regressions
- [x] Add failing tests for incomplete C0/promotion locks and preflight admission-byte identity.
- [x] Add failing tests for no-replace promotion, complete workflow runtime identity, and RiskSnapshot time admissibility.
- **Status:** completed

### Phase 7: Harden artifact and promotion admission
- [x] Make C1 reject incomplete C0 and promotion transactions before provider/database connection.
- [x] Preserve the exact admitted preflight bytes/digest in terminal evidence.
- [x] Make canonical publication no-replace under the reviewed parent ownership contract.
- **Status:** completed

### Phase 8: Close identity and external-design gaps
- [x] Bind prepare/review/promotion entrypoints into runtime identity.
- [x] Define a reviewed RiskSnapshot capture window and enforce it at candidate and C1 admission.
- [x] Correct external lock uniqueness and exact Git child allowlist without installing anything.
- **Status:** completed

### Phase 9: Final verification and handoff
- [x] Run focused/full suites, compilation, CLI help, import-boundary, diff, and artifact-absence checks.
- [x] Confirm no reviewed 2026-08-27 inputs, runner, automation, provider, database, or execution state changed.
- [x] Update automation memory with the second-review disposition.
- **Status:** completed

### Phase 10: Freeze final P1 regressions
- [x] Add a failing regression proving future RiskSnapshot/review timestamps cannot create approvable evidence.
- [x] Add failing regressions proving tampered provider, PostgreSQL, and rehearsal C0 payloads are rejected even when claimed digests are retained.
- **Status:** completed

### Phase 11: Implement trusted-time and component-integrity gates
- [x] Bind prepare/review timestamps to the process clock and reject candidate capture/review times later than the actual operation.
- [x] Recompute C0 provider, PostgreSQL, and rehearsal digests from their exact payload fields before any provider/database connection.
- [x] Preserve existing data-only flags, immutable artifact behavior, and `Production Shadow Gate=NOT_PASSED`.
- **Status:** completed

### Phase 12: Final read-only re-review
- [x] Review the complete scoped diff for immutable retry, review promotion, C0/C1 integrity, and execution boundary regressions.
- [x] Run focused/full suites, compilation, CLI help, import-boundary, diff, and artifact-absence checks.
- **Status:** completed

### Phase 13: Scoped commit
- [x] Stage only the verified PR-TM-012C1 workflow/runtime/docs/tests; exclude planning files and unrelated dirty-worktree changes.
- [x] Inspect the staged diff and create one scoped commit without pushing.
- **Status:** completed

## Success Criteria

- Multiple immutable draft attempts for one market date cannot overwrite each other.
- Packet digests always cover the exact bytes that were validated.
- Canonical C1 inputs can only be created from a valid approved attempt by a separate reviewed promotion command.
- C1 verifies the approval artifact and exact canonical file digests before provider/database connection.
- RiskSnapshot review evidence is bound to session, symbol, market date, capture time, and source identity.
- RiskSnapshot capture and human review timestamps cannot be future-dated relative to the operation that seals them.
- C1 independently recomputes every C0 component digest instead of trusting a claimed digest.
- External runner design covers every existing child process, atomic ownership, and graceful interruption without adding another trading runner.
- Production Shadow Gate remains `NOT_PASSED`.

## Errors Encountered

| Error | Resolution |
|---|---|
| Expected test collection failed because review/promotion entrypoints do not exist | Implement the pure review contract and the two separate entrypoints, then rerun the same focused suite. |
| First implemented focused run had one stale assertion for the old path error text | Updated the test to assert the new typed `REVIEW_PACKET_PATH_MISMATCH`; behavior was already fail-closed. |
| Expanded focused suite found the existing missing-input C1 argv fixture lacked the new required approval path | Added a missing approval path to the fail-before-provider fixture so it continues testing the same boundary. |
| C1 packet-reference verification initially used the repository root in tmp-path promotion tests | Patched the C1 module root in those isolated tests; production path enforcement remains unchanged. |
| Second-review regression patch was too broad for the current test-file context | Split the patch into imports/fixtures and small independent regression groups; no partial edit was applied. |
| Second-review focused suite failed collection because the new RiskSnapshot window contract does not exist yet | Expected red state; implement the pure temporal contract before rerunning the same suite. |
| Final-P1 regression run failed 5 tests on missing clock injection and component-digest verification | Expected red state; implement only those two reviewed contracts, then rerun the identical selection. |
