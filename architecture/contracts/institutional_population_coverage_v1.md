# Institutional Population Coverage V1

## Purpose

`PopulationCoverageV1` is the coverage-only gate between the frozen
`FormalEvaluationGateV1` protocol and any train, validation, or holdout outcome
generation. It records whether the required point-in-time population can be
constructed without reading price values, setup flags, fills, returns, or
performance summaries.

The artifact is evidence, including when its status is `BLOCKED`. A blocked
artifact must not be rewritten as a passing artifact. A later inspection uses
a new artifact ID, timestamp, and canonical digest.

## Required identity

Every artifact contains:

- `schema_version = institutional_population_coverage_v1`;
- a stable `artifact_id` and `inspected_at` timestamp;
- the frozen protocol artifact ID and canonical SHA-256;
- `change_policy = IMMUTABLE_NEW_ARTIFACT_REQUIRED`.

## Coverage-only boundary

Allowed observations are limited to:

- session dates and market identifiers;
- source availability and immutable source identity;
- PIT eligible and excluded member counts;
- row counts;
- issue codes and severity.

The artifact must not contain price values, setup qualification, executions,
fills, PnL, returns, expectancy, win rate, or any other outcome-derived field.
Source identity may include an artifact path or ID and a canonical digest, but
not source contents.

## Null and zero semantics

`null` means the metric could not be resolved from eligible immutable inputs.
`0` means an inspected source definitively contained zero records. Missing
sources must not be represented as zero-member universes or zero-session
markets because that would turn absence of evidence into a population claim.

## Required sources

The gate requires immutable, scope-compatible inputs for:

1. one-minute price/volume data and prior-session daily history;
2. official TWSE and TPEx institutional partitions;
3. a date-effective common-stock PIT universe;
4. corporate actions;
5. instrument reference data;
6. trading calendars for both TWSE and TPEx.

Each source has `AVAILABLE`, `PARTIAL`, `MISSING`, or `INELIGIBLE` status. An
`AVAILABLE` source must carry a non-null artifact ID and SHA-256. `PARTIAL`,
`MISSING`, and `INELIGIBLE` are not sufficient for the formal run.

## Market coverage

Both `TWSE` and `TPEX` entries are mandatory. Each contains the resolved date
range, eligible session count, PIT eligible member count, and excluded member
count. Counts remain null until the eligible source intersection exists.

## Split resolution

Exact ranges remain null unless the eligible session intersection is complete.
When eligible, sessions are sorted chronologically and split using the frozen
60/20/20 rule: `floor(0.60*N)`, then `floor(0.20*N)`, with the remainder held
out. The holdout requires at least 60 eligible sessions. No ratio or boundary
may be changed after outcome inspection.

## Gate semantics

`HOLDOUT_ALLOWED` is true only when all required sources are `AVAILABLE`, both
markets have complete PIT coverage, the calendar intersection is consistent,
the split is exact, the holdout has at least 60 sessions, and no blocking issue
exists.

Any blocking issue requires all of the following:

- `status = BLOCKED`;
- `dataset_population_frozen = false`;
- `composite_manifest_allowed = false`;
- `outcome_generation_allowed = false`;
- `holdout_allowed = false`.

Common blocking issue codes include `PIT_UNIVERSE_MISSING`,
`INSTITUTIONAL_PARTITIONS_MISSING`, `INSTITUTIONAL_SCOPE_MISMATCH`,
`PRICE_DATASET_MISSING`, `PRICE_DATA_GAP`, `CORPORATE_ACTIONS_MISSING`,
`REFERENCE_DATA_MISSING`, `CALENDAR_INCONSISTENT`,
`TPEX_CALENDAR_COVERAGE_UNPROVEN`, `COVERAGE_RANGE_UNRESOLVED`, and
`INSUFFICIENT_SESSIONS`.

## Canonical digest

The sidecar is the lowercase SHA-256 of the whole artifact encoded with the
repository `canonical_json` function. It is named by replacing `.json` with
`.canonical.sha256`. Any content change requires a new digest and, after a
reviewed snapshot is accepted, a new artifact rather than in-place mutation.
