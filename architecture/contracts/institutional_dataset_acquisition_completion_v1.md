# Institutional Dataset Acquisition Completion Gate V1

## Purpose

`DatasetAcquisitionCompletionGateV1` is the explicit all-input readiness gate
between immutable dataset acquisition and dataset-population freeze. It answers:

> Does the referenced acquisition manifest prove that every required dataset
> family is validated for formal evaluation?

It does not acquire data, reinterpret source bytes, revise coverage, construct
the research population, or generate outcomes.

## Identity and input

Every completion artifact contains:

- `schema_version = institutional_dataset_acquisition_completion_v1`;
- a stable `artifact_id`, timezone-aware `evaluated_at`, and
  `change_policy = IMMUTABLE_NEW_ARTIFACT_REQUIRED`;
- the exact artifact ID and canonical SHA-256 of one frozen
  `DatasetAcquisitionManifestV1` revision;
- the six required dataset-family names and their statuses copied from that
  manifest;
- summary counts, blocking issues, and fail-closed downstream permissions.

The `.canonical.sha256` sidecar is the SHA-256 of the whole artifact encoded by
the repository `canonical_json` function. Any change to the input manifest,
readiness decision, inventory metadata, or blocker list requires a new artifact.

## Required dataset families

The gate requires exactly:

- `price`;
- `institutional`;
- `pit_universe`;
- `corporate_actions`;
- `reference_data`;
- `trading_calendar`.

A family is ready only when its acquisition-manifest status is `VALIDATED` and
it has a non-null immutable artifact identity and canonical digest. `PARTIAL`,
`ACQUIRED`, `MISSING`, and `INELIGIBLE` are not ready.

The completion artifact references dataset identities from the acquisition
manifest; it does not copy source payloads or replace dataset-specific replay
and validation contracts.

## Non-qualifying evidence

The gate may record metadata-only observations about staging tables, paused or
failed jobs, adapters, fixtures, or acquisition plans. These observations exist
to explain why a family remains blocked and may include job status, partition
counts, error counts, requested counts, markets, and coverage dates.

Staging bytes without a sealed dataset manifest and digest never count as an
artifact. Adapter capability, current instrument lists, build output, test
fixtures, and sample qualification data also never satisfy a dataset family.

## All-ready and downstream rule

`all_required_datasets_ready` is true if and only if all six families are ready
and there are no blocking issues. Otherwise:

- `status = BLOCKED`;
- `dataset_population_freeze_allowed = false`;
- `coverage_revision_allowed = false`;
- `composite_manifest_allowed = false`;
- `outcome_generation_allowed = false`;
- `holdout_allowed = false`.

Even an all-ready completion artifact does not directly permit outcome or
holdout execution. It permits the next coverage/population-freeze review only;
exact common sessions, PIT membership, chronological splits, and the composite
input manifest must still pass their own gates.

## Outcome boundary

Inventory is restricted to identities, statuses, counts, market/date coverage,
lineage, and issue codes. It must not read or store OHLC values, setup flags,
fills, returns, PnL, expectancy, win rate, or holdout results.
