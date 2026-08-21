# Price Acquisition Resolution V1

## Purpose

`PriceAcquisitionResolutionV1` freezes the evidence and exit decision for one
resumable historical-price acquisition job before any Price Dataset Artifact is
created. It classifies every expected symbol as trusted success, explicitly
excluded, retry-required, or not yet checkpointed.

It does not run a backtest, read strategy outcomes, select a research cohort,
or promote staging bytes into a formal dataset.

## Identity and lineage

Every resolution artifact contains:

- `schema_version = price_acquisition_resolution_v1`;
- stable artifact identity, timezone-aware observation time, and immutable
  revision policy;
- the exact job ID, provider, request digest, requested date range, expected
  symbol count, and expected symbol/market identity digest;
- the referenced dataset-completion artifact and canonical digest;
- staging-metadata digest, partition classifications, coverage observations,
  integrity status, issues, and exit-gate decision.

The `.canonical.sha256` sidecar is the SHA-256 of the entire artifact encoded
with repository `canonical_json`. Any job-state, classification, coverage, or
decision change requires a new resolution artifact and digest.

## Expected universe

The expected acquisition universe is the immutable instrument list stored in
the referenced job request. Its digest is calculated from sorted
`(market, symbol)` identities; names are descriptive and do not define identity.

`ALL_CURRENT` is an acquisition scope, not a PIT research universe. It is
explicitly survivorship-limited and cannot prove delisted-security coverage.
Completing this job may create a replayable price artifact, but cannot by itself
make the formal research population eligible.

## Classification semantics

Each expected symbol must resolve to exactly one final class:

- `SUCCESS_NONEMPTY`: a non-empty partition inside the downloader's trusted
  contiguous prefix;
- `EXCLUDED_STRUCTURAL`: no price rows are expected for a documented,
  independently verifiable reason;
- `RETRY_REQUIRED`: an ambiguous empty response, temporary failure, checksum
  issue, or any partition at or after a retry anchor;
- `NOT_CHECKPOINTED`: no partition exists yet.

An old non-empty partition after the first untrusted/empty checkpoint is not a
success until the resumed downloader reaches and revalidates it. This prevents
holes from being hidden by later staging rows.

`all_expected_symbols_resolved` is true only when every expected identity is
either `SUCCESS_NONEMPTY` or an approved `EXCLUDED_STRUCTURAL`. Ambiguous empty
responses are never structural exclusions.

## Required exit evidence

Price artifact sealing remains disabled until all conditions pass:

1. all expected symbol identities are resolved with no untrusted tail;
2. every empty/error partition has a stable classification and evidence code;
3. every included partition payload has been streamed, counted, and verified
   against its recorded digest;
4. market/session coverage is reconciled against the frozen calendars and PIT
   universe, with exact session count and missing-session issues;
5. intraday OHLCV cadence and VWAP-required volume semantics are validated;
6. RAW/adjusted price policy and corporate-action treatment are frozen;
7. immutable `bars.jsonl`, manifest identity, and digest are generated.

The resolution artifact may report metadata-only observations before these
checks pass. Metadata presence never substitutes for an unmet condition.

## Fail-closed boundary

When any exit condition fails:

- `status = BLOCKED`;
- `price_dataset_manifest_allowed = false`;
- `acquisition_manifest_revision_allowed = false`;
- `population_freeze_allowed = false`;
- `outcome_generation_allowed = false`;
- `holdout_allowed = false`.

Even a passed resolution permits only Price Dataset Artifact sealing and its
dataset-specific review. It does not directly unlock population or evaluation.

## Outcome boundary

Resolution inventory may inspect job/request metadata, symbol/market identity,
partition counts, date coverage, checksums, payload row counts, cadence, and
issue codes. It must not calculate setup flags, returns, fills, PnL, expectancy,
win rate, or inspect holdout outcomes.
