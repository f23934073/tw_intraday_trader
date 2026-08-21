# Institutional Partition Set V1

## Purpose

`InstitutionalPartitionSetV1` seals a reviewed collection of normalized
institutional-flow partitions and the raw evidence required to replay them. It
is a dataset-acquisition artifact, not an evaluation result.

The first artifact is intentionally a one-session pilot. Its status is
`VALIDATED_PARTIAL_COVERAGE`; it proves that both official market paths can be
captured, normalized, and validated for the same completed session, but it does
not prove that the formal historical period is complete.

## Identity and coverage

Each partition-set artifact contains:

- `schema_version = institutional_partition_set_v1`;
- a stable `artifact_id` and `change_policy = IMMUTABLE_NEW_ARTIFACT_REQUIRED`;
- exact start and end dates, session count, and represented markets;
- `formal_history_complete` and the first session on which the data may be used;
- one entry per included market/session partition.

The `.canonical.sha256` sidecar is the lowercase SHA-256 of the whole artifact
encoded with the repository `canonical_json` function. Any membership or
metadata change requires a new artifact and digest.

## Included partition evidence

Each partition entry records its market, source product, trade scope, partition
identity, raw artifact identity and revision, raw digest, normalized digest,
partition-manifest digest, source and normalized row counts, validation status,
validation check counts, and issue count.

A partition may be included only when:

- its response date equals the requested session;
- its raw bytes and metadata can be reloaded by the immutable raw store;
- its normalized rows and manifest deserialize under the frozen schemas;
- every normalized row has the same market, session, and partition identity;
- normalized rows have a unique symbol at the partition grain;
- the recorded raw and normalized digests match the referenced artifacts;
- status is `VALIDATED` and `validation_issue_count` is zero.

The partition-set grain is `(market, session_date, symbol)`. It does not apply
the later point-in-time equity-universe filter, so symbols that are not eligible
common equities may still be present in this acquisition layer.

## Revision and quarantine rule

Raw source responses are append-only revisions. A malformed request or a
response-date mismatch remains preserved for diagnosis, but it is quarantined
by exclusion from `partitions`. A later corrected revision may be included only
after passing the full partition contract. Revision history must never be
rewritten to make the acquisition look clean.

## Status and downstream boundary

Allowed partition-set status for this contract is:

- `VALIDATED_PARTIAL_COVERAGE`: every included partition is validated, but the
  formal required date range is incomplete;
- `VALIDATED`: every included partition is validated and the separately frozen
  required historical coverage is complete.

The first status can advance the institutional entry in
`DatasetAcquisitionManifestV1` from `MISSING` to `PARTIAL` only. It cannot enable
coverage revision, population freeze, composite-manifest creation, outcome
generation, or holdout execution.

## Outcome boundary

The artifact may contain identities, source scope, coverage, row counts,
validation counts, and issue counts. It must not contain prices, setup results,
fills, returns, PnL, expectancy, win rate, or any holdout outcome.
