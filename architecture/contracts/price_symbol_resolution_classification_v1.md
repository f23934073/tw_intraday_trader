# Price Symbol Resolution Classification V1

## Purpose

`PriceSymbolResolutionClassificationV1` decides whether one unresolved price
acquisition symbol is a documented structural exclusion, a provider-path
mismatch, a temporary failure, or still unsupported by enough evidence. It is
an evidence gate before acquisition continuation, not a Price Dataset Artifact.

The gate may inspect listing/reference metadata, provider contract metadata,
source availability, response row counts, timestamps, and existing partition
metadata. It must not inspect strategy signals, returns, PnL, or holdout
outcomes.

## Required evidence

Every classification artifact records:

- the frozen acquisition job, symbol, market, requested date range, and upstream
  resolution artifact digest;
- at least one independent official listing/reference source;
- an official in-range source-availability observation when one exists;
- the provider contract identity and a bounded, non-persisting coverage probe;
- same-job control metadata sufficient to distinguish a symbol-specific failure
  from a market-wide path failure;
- evidence digests, observation timestamps, confidence, remaining uncertainty,
  and downstream permissions.

An empty provider response is never, by itself, evidence of structural no-data.

## Classification decisions

- `STRUCTURAL_NO_DATA`: official evidence proves the security was outside the
  requested population or period. Exclusion still requires an explicit reason.
- `TEMPORARY_PROVIDER_ISSUE`: evidence identifies a transient provider failure
  and controlled retry may proceed.
- `SYMBOL_SPECIFIC_PROVIDER_COVERAGE_MISMATCH`: official evidence shows the
  security and in-range source row exist, but the configured provider path
  returns no Kbars while comparable market controls succeed.
- `INSUFFICIENT_EVIDENCE`: available evidence cannot distinguish the cases.

`SYMBOL_SPECIFIC_PROVIDER_COVERAGE_MISMATCH` is not an approved exclusion and
does not authorize repeating the same unchanged acquisition request. It
requires a provider-route fix, an independently validated replacement source,
or new evidence that changes the disposition.

## Fail-closed exit

The artifact must keep all of the following false unless a later immutable
revision supplies the missing evidence:

- `controlled_retry_allowed`;
- `structural_exclusion_approved`;
- `price_dataset_artifact_allowed`;
- `dataset_population_freeze_allowed`;
- `outcome_generation_allowed`;
- `holdout_execution_allowed`.
