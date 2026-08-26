# R6 G0 Amendment A1 Review Request

## Requested disposition

```text
R6 G0 Amendment A1: APPROVE / CONTRACT FROZEN
or
R6 G0 Amendment A1: REQUEST CHANGES
```

Review source:

- `architecture/r6_atomic_entry_benchmark_v2_implementation_plan.md`,
  Section 14.

This is a contract-only re-review. Approval may authorize the separately scoped
implementation/migration remediation, but does not authorize matrix revision 2
activation, the 28.3M-bar G3 rerun, G4, lifecycle mutation, Local Paper,
provider, broker, or real-money execution.

## Triggering evidence

- Matrix revision 1 is sealed with family head `0`, attempts `0`.
- Formal G3 stopped before publication at slot 1 signal sequence `101`: a later
  entry Kbar existed, but no still-later same-session exit Kbar existed.
- All exact Versions already use end-exclusive `entry_window_end <= 12:45`;
  the defect is partial symbol/session tail coverage, not a 13:30 signal.
- No G3 artifact, attempt, episode, metric, result, or trading state exists.

## Review focus

1. Eligibility is a Dataset-only common `(symbol, session_date)` mask used by
   all seven slots; no strategy-specific or result-dependent deletion exists.
2. Exact `12:45` and `13:30` anchors guarantee entry no later than `12:45` and
   a strictly later terminal exit at exactly `13:30`.
3. Missing anchors produce exact common exclusions; duplicate anchors,
   synthetic bars, overnight carry, same-bar entry/exit, and admitted
   incomplete matches fail closed.
4. The 95% eligible symbol/session floor is computed at 18 decimals with
   `ROUND_HALF_EVEN` and `GTE`; zero denominator fails closed.
5. Eligibility row/manifest schemas, counts, reasons, anchor lineage, payload
   SHA, common-mask digest, downstream artifact roots, and postflight evidence
   are exact and independently rebuildable.
6. Eligibility is decided before all slot admission from timestamp existence
   only; it cannot inspect OHLCV values, Features, signals, returns, or P&L.
7. Amended protocol, hypothesis, Version-binding, hypothesis, slot, and
   algorithm contract digests are non-circular and exactly frozen.
8. The stable family and 20-attempt budget remain unchanged. Revision 1 stays
   immutable; revision 2 requires head `0`, attempts `0`, expected active
   revision `1`, and one CAS.
9. Migration 017 must enable revision 2 without updating or deleting any
   revision-1 row or permitting a third matrix; response loss and concurrency
   remain fail closed. Revision-1 protocol history is an additive immutable
   companion projection, not a matrix-row backfill. Migration 017 does not
   activate the new matrix or update the family. The subsequent activation
   transaction may CAS only family `active_matrix_revision: 1 -> 2` plus
   operational `updated_at`; all other family fields remain byte-equivalent.
10. The one-session spool is bounded and non-authoritative; clean-root rebuild
    produces identical canonical evidence.
11. Results remain explicitly limited to the coverage-qualified exploratory
    universe and cannot support promotion or Local Paper.
12. The G3 root has an exact 31-member tree, exact v2 preflight/slot-root
    schemas, one digest-addressed publication, and complete member revalidation.
13. PostgreSQL owns the only accepted-preflight authority through one immutable
    registration, idempotent operation result, and transactional outbox; a
    filesystem artifact alone cannot admit G4.
14. Every formal attempt must carry the exact accepted revision-2 preflight ID
    and registration digest before family-head mutation.
15. Migration 017 adds composite matrix/family/revision and
    matrix/family/slot/hypothesis integrity, preventing cross-revision attempt
    substitution after the old family/slot uniqueness is removed. Matrices own
    both exact referenced unique keys: `(matrix_id, family_id)` for operation,
    outbox, and slot foreign keys, and
    `(matrix_id, family_id, matrix_revision)` for protocol, release, and
    preflight foreign keys.
    Matrix/release/family active revisions are database-constrained to exact
    values `1` or `2`; revision 3 cannot be admitted by application convention.
16. Protocol bodies resolve through immutable matrix-protocol companion rows
    after Migration 017. Revision 1 receives one additive, fully verified
    companion projection without rewriting its matrix/family rows; the family
    inception protocol is never overwritten by Amendment A1.
17. Excluded sessions remain in Dataset and source-only previous-close evidence
    but never enter strategy/Feature state or signal admission.
18. Revision-2 activation has an exact request/result, one family CAS, complete
    revision-1/G1 rebuild, operation/outbox replay, and no-third-matrix guard.
19. Present eligibility anchors bind their canonical Taipei timestamp and the
    exact Dataset source JSON bytes excluding LF; parsed/reformatted, reduced,
    or LF-inclusive digest inputs fail closed.
20. Migration 017 makes operation/outbox matrix identity non-null after
    verifying existing rows, binds outbox to its exact operation
    matrix/family aggregate, and binds transition evidence plus attempt-bound
    operation/outbox rows to the exact attempt matrix/family aggregate.
21. Migration 017 takes and holds the exact family `FOR UPDATE` lock before
    validating head/attempt/revision preconditions; attempt start, activation,
    and preflight registration share that serialization boundary.
22. The v2 matrix build binding seals exact algorithm, G3 preflight, and
    ordered Migration 016/017 source manifests. G3 cannot self-declare a new
    preflight implementation digest at publication or registration time.

## Prior Review remediation

The independent Review returned `REQUEST CHANGES` with two P1 findings and one
P2 finding. This candidate now:

- freezes the exact 31-file G3 root and durable preflight registration/G4
  barrier;
- requires composite attempt-to-slot identity across matrix revisions;
- freezes excluded-session source/reference/runtime behavior;
- additionally prevents the amended protocol from overwriting revision-1
  family evidence through an additive immutable matrix-protocol companion row;
- freezes the exact anchor timestamp and source-row SHA-256 input bytes.
- adds the missing exact `UNIQUE (matrix_id, family_id)` referenced key and
  requires cross-family operation/outbox/slot substitution regressions, while
  retaining the separate three-column matrix/revision identity.
- separates schema migration from activation and freezes the only permitted
  family mutation as the revision `1 -> 2` CAS plus `updated_at`.
- freezes database-level `1/2` revision checks and closes nullable/cross-family
  matrix, operation, outbox, transition-evidence, and attempt aggregate gaps.
- freezes family-row serialization across migration, activation, preflight
  registration, and attempt admission.
- advances the matrix build binding to v2 with exact source-manifest schemas,
  paths, order, bytes, and digest revalidation.

No Migration 017, product/test implementation, matrix activation, PostgreSQL
mutation, or G3 rerun is included in this remediation.

## Frozen roots

```text
protocol_core_digest = a4d645b5ea59fca5a90a00c9e14ca117366d87e4f310b88354fc73d03272f471
algorithm_contract_digest = d0d3b66395a06f600c698bad7890ad39f2dceec2963727814e5d3198643df0b6
matrix_revision = 2 (not created)
formal_attempts = 0 / 7
```

Exact seven-slot downstream roots and the full adversarial matrix are in
Sections 14.4 and 14.6 of the Implementation Plan.

## Current status

```text
Historical G0/G1/G2: PASSED
G0 Amendment A1: PASSED / CONTRACT FROZEN
Migration 017 / matrix revision 2: NOT STARTED / REQUIRES SEPARATE AUTHORIZATION
G3: BLOCKED ON A1 IMPLEMENTATION
G4-G5: NOT AUTHORIZED
Local Paper / Broker / Real-money: PROHIBITED
```

## Review result

The operator-authorized adversarial re-review and remediation loop completed
four additional cycles. The final cycle found no remaining Blocking or
Important finding.

```text
R6 G0 Amendment A1: APPROVE / CONTRACT FROZEN
Formal progress: 50%
Formal Replay: 0 / 7
```

Independent reconstruction verified the A1 protocol root, all seven
hypothesis-spec digests, Version-binding digests, hypothesis IDs, slot digests,
and the algorithm-contract root. Focused domain/artifact/application/full-
Dataset tests passed. Migration 017, matrix revision 2, PostgreSQL state, and
G3 execution remain outside this approval and were not performed.
