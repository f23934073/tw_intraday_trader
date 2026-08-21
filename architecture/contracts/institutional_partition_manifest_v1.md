# `institutional_partition_manifest_v1` Contract

Status: frozen after PR-002 Official Source Adapter review.

## Identity and scope

- `partition_id` is the immutable normalized-partition identity.
- `market`, `session_date`, `source_product`, and `trade_scope_id` define the
  bounded source scope. The review's `scope_id` is represented by
  `trade_scope_id`; v1 does not rename it.
- `correction_policy` and `response_scope_note` preserve how the official
  product treats corrections and included trade categories.

## Digest relation

- `raw_artifact_id` locates the immutable captured response.
- `raw_sha256` proves the exact captured response bytes.
- `normalized_sha256` proves the canonical
  `institutional_flow_rows_v1` bytes produced from that raw artifact.
- A normalized partition must not be rebound to different raw or normalized
  bytes without creating a new immutable artifact/revision.

## Availability fields

- `retrieved_at` and `first_observed_at` are timezone-aware evidence times.
- `usable_from_session` is strictly after `session_date`; downstream consumers
  must not make the partition visible to an earlier session.

## Status enum

The only v1 values are `RAW_CAPTURED`, `NORMALIZED`, `VALIDATED`, and
`QUARANTINED`. Unknown values fail closed.

## Exact fields and change rule

The executable field list is
`institutional_data.serialization.PARTITION_MANIFEST_V1_FIELDS`; readers reject
missing and unknown fields. Any incompatible identity, digest, availability, or
status change requires a new schema version and new golden fixtures. v1 bytes
must not be silently extended.
