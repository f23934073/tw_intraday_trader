# R6 G3 Dynamic Entry Reserve Amendment A2

## Status

```text
Revision 2: FAILED / SEALED AS NEGATIVE EVIDENCE
Amendment A2: APPROVED / CONTRACT FROZEN
Source-only audit: PASSED / 0.995893643087254413
Migration 018: APPLIED / SCHEMA ONLY
Matrix revision 3: NOT CREATED
Formal G3: NOT AUTHORIZED
G4-G5 / Local Paper / Broker / Real-money: PROHIBITED
```

## Problem

The immutable FinMind Dataset contains trade-derived one-minute observations,
not a synthetic complete minute grid. Revision 2 requires an exact `12:45`
Kbar for every symbol-session. Two complete scans therefore failed with an
eligible ratio near `0.79`, even though almost all excluded sessions had usable
observations before the deadline and an exact terminal `13:30` Kbar.

Lowering the `0.95` floor or manufacturing a `12:45` bar would change the
research sample for the purpose of passing a Gate. Both are prohibited.

## A2 source-derived rule

For every `(symbol, session_date)`, before any strategy is evaluated:

```text
entry_reserve_at =
  max(observed Kbar timestamp where timestamp <= 12:45)

signal observation is admissible only when:
  signal_at < entry_reserve_at

entry fill remains:
  first observed same-symbol Kbar strictly after signal_at

therefore:
  entry_at <= entry_reserve_at <= 12:45

terminal exit remains:
  exact same-symbol 13:30 Kbar close
```

The reserve Kbar is fed to the pending-order matcher but is never evaluated as
a signal Kbar. No bar is generated, forward-filled, interpolated, or moved
between sessions.

## Common eligibility mask

One source-only pass derives a single symbol-session mask shared by all seven
slots. A session is `ELIGIBLE` only when all conditions hold:

1. at least one observed Kbar exists at or before `12:45`;
2. at least one earlier observed Kbar exists strictly before the selected
   reserve, so a signal can be evaluated before the reserve;
3. an exact observed same-symbol `13:30` Kbar exists.

The ordered exclusion codes are exact:

1. `NO_ENTRY_RESERVE_AT_OR_BEFORE_12_45`
2. `NO_SIGNAL_OBSERVATION_BEFORE_ENTRY_RESERVE`
3. `MISSING_TERMINAL_EXIT_13_30`

The mask is computed before strategy runtime, Feature values, triggers,
matches, costs, or performance exist. A strategy cannot add or remove a
symbol-session.

## Exact artifact schemas

### Eligibility row v2

The exact ordered canonical JSON object has these keys:

```text
schema_version = r6-session-eligibility-row-v2
sequence: positive integer
symbol: non-empty string
session_date: YYYY-MM-DD
entry_reserve_at: canonical Asia/Taipei timestamp or null
entry_reserve_bar_digest: lowercase SHA-256 or null
terminal_exit_at: canonical exact-13:30 Asia/Taipei timestamp or null
terminal_exit_bar_digest: lowercase SHA-256 or null
eligibility_status: ELIGIBLE | EXCLUDED
exclusion_reason_codes: ordered array from the frozen allowlist
signal_observation_count_before_reserve: non-negative integer
eligibility_row_digest: lowercase SHA-256 of all prior fields
```

`entry_reserve_at` must be no later than `12:45` on `session_date`.
`signal_observation_count_before_reserve` is zero when the reserve is absent.
Unknown fields, non-canonical bytes, numeric aliases, invalid offsets, and
reason order drift fail closed.

### Eligibility manifest v2

The exact canonical object contains:

```text
schema_version = r6-session-eligibility-manifest-v2
dataset_id
dataset_digest
dataset_bars_sha256
entry_reserve_selection_semantics =
  LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1
signal_admission_comparator = STRICT_LT_ENTRY_RESERVE_AT
entry_fill_deadline_time = 12:45
required_terminal_exit_time = 13:30
eligibility_row_schema_version = r6-session-eligibility-row-v2
observed_symbol_session_count
eligible_symbol_session_count
excluded_symbol_session_count
missing_entry_reserve_count
missing_signal_observation_count
missing_terminal_exit_count
eligible_symbol_session_ratio: Decimal text at scale 18
minimum_eligible_symbol_session_ratio = 0.95
eligibility_rows_sha256
eligibility_manifest_digest
```

Counts, SHA, canonical rows, ratio, Dataset identity, and exact schema are
recomputed during artifact verification.

### Preflight root v3

Revision 3 uses:

```text
r6-preflight-manifest-v3
r6-preflight-slot-root-v3
matrix_revision = 3
```

Revision-2 schemas and artifacts remain readable and immutable. A revision-3
root cannot be registered against revision 2, and vice versa.

## Source-only audit

`scripts/audit_atomic_entry_benchmark_eligibility.py` performs one canonical
Dataset traversal without strategy runtimes or PostgreSQL mutations. The
PostgreSQL context lookup is executed in a read-only transaction. Its exact
`r6-eligibility-source-audit-v2` body binds:

- current family ID, active revision-2 matrix ID/registration, protocol and
  build-binding digests;
- research-baseline digest, Dataset binding revision, family head `0`, and
  attempt count `0`;
- candidate revision-3 protocol digest and the exact source-audit
  implementation digest;
- Dataset ID, manifest digest, bars SHA/count, and source EOF evidence;
- candidate revision, A2 semantics, totals, yearly projections, sorted symbol
  projections, and the final `audit_digest`.

Migration 018 must compare every stored scope field with the same locked
family row and immutable roots. A self-consistent audit for another family,
matrix, baseline, implementation, head, or attempt count is not admissible.

The source-only audit must pass `ratio >= 0.95` before Migration 018 activation
or another seven-slot full scan is authorized. An identical audit replays exact
bytes; a same-path mismatch fails closed.

## Additive identity and persistence boundary

Revision 2 remains sealed. A later, separately reviewed Migration 018 may:

1. extend matrix/family/release revision constraints to admit revision `3`;
2. admit revision-3 preflight rows and operation types without rewriting
   revision-2 rows;
3. require the family row lock, active revision `2`, head `0`, attempts `0`,
   release `NOT_READY`, and no accepted revision-2 preflight;
4. insert a new revision-3 protocol/build-binding/matrix/slots/release graph;
5. use CAS `2 -> 3`; stale or concurrent activation fails closed.

The protocol dependency is non-circular:

```text
research baseline
  -> protocol core v3
  -> seven existing exact Version bindings
  -> revision-3 matrix registration
  -> preflight source/build identities
  -> accepted preflight registration
```

Migration 018 is a forward-only schema migration. It was applied only after
the exact source-only audit passed the `0.95` floor; application PostgreSQL
remains at active revision `2`, head `0`, attempts `0`, and no revision-3
matrix or accepted audit registration exists. The revision-3 activation
request remains a separate implementation and Review boundary.

## Supervisor one-shot contract

Every run root owns one `worker_claim.json`. The first worker creates it using
atomic `O_CREAT | O_EXCL` before reading credentials, PostgreSQL, or Dataset
bytes. Any later launchd invocation for the same run root verifies the claim
identity and exits `0` without changing status or rerunning the scan.

A failed run may only be retried by an explicit new run root after diagnosis
and authorization. Interrupted staging is evidence only and is never resumed
or promoted.

## Acceptance tests

- sparse session without exact `12:45` uses the last observed bar before the
  deadline and can match an earlier signal;
- reserve bar itself is never evaluated as a signal;
- no observation before reserve is commonly excluded before all runtimes;
- reserve after `12:45`, missing exact `13:30`, cross-session entry/exit,
  synthetic rows, schema drift, and digest drift fail closed;
- revision-2 artifact replay remains valid;
- source-only audit and preflight builder share the same source accumulator and
  eligibility decision function, with adversarial aggregate parity coverage;
- scope substitution, symbol-total substitution, implementation drift, and
  family-state drift fail closed;
- same supervisor run root invokes preflight at most once, including after a
  deterministic nonzero exit.
