# Institutional Dataset Acquisition Manifest V1

## Purpose

`DatasetAcquisitionManifestV1` is the immutable evidence gate between a
coverage finding and a revised population-coverage snapshot. It answers only:

> Which required historical datasets have actually been acquired, sealed, and
> identified by digest?

An adapter, endpoint, acquisition plan, test fixture, live cache, or database
schema is not an acquired dataset. Missing data remains explicit and keeps all
downstream permissions disabled.

## Identity and references

Every manifest contains:

- `schema_version = institutional_dataset_acquisition_manifest_v1`;
- a stable `artifact_id`, timezone-aware `inventoried_at`, and
  `change_policy = IMMUTABLE_NEW_ARTIFACT_REQUIRED`;
- the frozen `FormalEvaluationGateV1` artifact ID and canonical digest;
- the coverage snapshot ID and canonical digest that triggered acquisition.

A later coverage revision may reference this manifest's digest. The already
sealed coverage snapshot is never modified to create a circular reference.

## Required dataset entries

The `datasets` object contains exactly:

- `price`;
- `institutional`;
- `pit_universe`;
- `corporate_actions`;
- `reference_data`;
- `trading_calendar`.

Each entry records required and acquired markets, acquisition status, coverage
period, artifact count, row count when meaningful, immutable artifact identity,
canonical SHA-256, and optional planned-source metadata.

## Status semantics

Allowed acquisition statuses are:

- `MISSING`: no formal immutable artifact was found;
- `PARTIAL`: at least one artifact exists, but required market, period, scope,
  validation, or digest coverage is incomplete;
- `ACQUIRED`: bytes and identity are sealed, but formal validation is pending;
- `VALIDATED`: the immutable dataset passed its dataset-specific contract;
- `INELIGIBLE`: an artifact exists but cannot satisfy the formal research
  protocol.

Only `VALIDATED` satisfies the acquisition gate. `PARTIAL`, `ACQUIRED`, and
`INELIGIBLE` must not be promoted to research-ready evidence.

For `MISSING`, `artifact_id` and `canonical_sha256` are null and
`artifact_count` is zero. A non-null endpoint or adapter under
`planned_sources` does not change this rule. For `PARTIAL`, every counted
artifact must have an immutable identity and digest.

## Coverage and source rules

Coverage dates describe acquired artifact bytes, not the theoretical range of
an API. Unknown dates and row counts are null. Required markets are both
`TWSE` and `TPEX`; acquired markets list only what the artifact itself proves.

Official source product IDs, endpoints, parser versions, license/access notes,
and correction policies belong in `planned_sources` or the referenced dataset
artifact. They never substitute for `artifact_id` plus digest.

Test fixtures and sample payloads are excluded from the inventory. Runtime
premarket contexts, quote captures, and unrelated qualification artifacts are
also excluded unless a reviewed dataset-specific contract declares them formal
inputs for this protocol.

## Fail-closed gate

If any required dataset is not `VALIDATED`, the manifest must have:

- `status = BLOCKED`;
- `coverage_revision_allowed = false`;
- `population_freeze_allowed = false`;
- `composite_manifest_allowed = false`;
- `outcome_generation_allowed = false`;
- `holdout_allowed = false`.

The acquisition manifest never enables outcome generation directly. Once all
datasets are validated, a new coverage snapshot must still resolve the common
eligible-session intersection, market completeness, PIT population counts,
and exact chronological split before any composite manifest can be created.

## Outcome boundary and digest

Inventory may read artifact identity, source, market, date coverage, counts,
validation status, and issue codes. It must not read prices, setups, fills,
returns, PnL, expectancy, win rate, or other outcome fields.

The `.canonical.sha256` sidecar is the lowercase SHA-256 of the whole manifest
encoded with the repository `canonical_json` function. Any acquisition change
requires a new manifest artifact and digest.
