# Institutional Factor Report v0 Contract

## Status and boundary

`institutional_factor_report_v0` is a research-only diagnostic artifact. Every
artifact is labeled `EXPLORATORY`, `research_eligible=false`, and
`UNADJUSTED_INDUSTRY_SIZE`. The serialized report also fixes
`strategy_ready=false` and `production_ready=false`; constructors reject either
flag when true. It does not define a threshold, weight, consensus
score, Top-N rule, candidate/watchlist, executable strategy, runtime admission,
or order instruction.

PR-005 first validates this artifact, then projects a target-session 5D factor
prior that excludes forward outcomes and IC. The Candidate Prior manifest pins
that safe projection rather than the complete report digest. Real-money use is
prohibited.

## Pinned inputs

`ResearchRunManifestV0` pins these identities:

- adjusted-close price dataset ID and SHA256 digest;
- validated institutional bundle ID and SHA256 digest;
- optional PIT equity-universe snapshot ID and content SHA256 digest;
- fixed factor-definition ID, version, and SHA256 digest;
- inclusive factor target-session range.

Price and institutional digests are mandatory. A missing or mismatched digest
raises a `ResearchInputError` and produces no report. The institutional bundle
also verifies every row partition against a `VALIDATED`
`InstitutionalPartitionManifest` and its normalized digest.

The universe identity is optional only to support the limited no-PIT tier. A
missing, current-snapshot, invalid, out-of-coverage, or mismatched universe
poisons all cross-sectional output for the entire run.

## Availability and factor time

The source exchange session is not the factor target session. A partition for
source session `S` contributes a factor point on its reviewed
`usable_from_session=T`. The five-session window ends at `S` and contains only
validated source partitions whose data are available by `T`.

This prevents a same-session institutional observation from being treated as
known before publication. Forward outcomes start from the adjusted close on
target session `T` and end at the close exactly 1, 3, or 5 market sessions
later.

## Fixed baseline definition

Components:

- foreign investors excluding foreign dealers;
- investment trusts.

Per component and symbol:

- `NET_SHARES_1D`: latest validated net shares;
- `ROLLING_NET_SHARES_5D`: sum of five complete net-share observations;
- `POSITIVE_DAYS_5D`: count of strictly positive net-share observations;
- `CONSECUTIVE_POSITIVE_DAYS_5D`: positive streak ending at the latest source
  session, capped by the five-session window;
- `SELF_NORMALIZED_FLOW_5D`: `sum(net) / sum(buy + sell)`; value is null when
  the denominator is zero.

Five-session fields are null until all five validated market sessions exist for
that symbol. No calendar-day fill or previous-value carry-forward is allowed.

## Diagnostic tiers

### Per-symbol tier

Always available after price/institutional lineage validation:

- factor points and completeness counts;
- daily distribution;
- observed/null counts and raw null rate.

Without PIT evidence, `expected_count` and universe coverage are null.

### PIT-gated cross-sectional tier

Requires every factor target session to resolve the exact pinned,
date-effective universe and requires a stable institutional scope contract per
market. One failed session disables this tier for the whole report.

When eligible, the report may contain diagnostic-only:

- average-tie cross-sectional percentile and decile labels;
- 1/3/5-session adjusted-close forward outcomes;
- daily Spearman Rank IC and sample size;
- mean Rank IC and unannualized `ICIR = mean IC / sample standard deviation`;
- mean forward outcome by decile.

Percentile/decile labels describe diagnostic buckets only. They are not a
selection or buy rule. Industry and market-cap cohort fields are carried for
confounding visibility, but v0 does not neutralize them.

## Deterministic statistics and bytes

- All numeric calculations use `Decimal`; float input is not canonical.
- Ties use one-based average ranks.
- Cross-sectional percentiles map ranks inclusively to `[0, 1]`.
- Distribution quartiles use nearest-rank percentiles.
- Rank IC is null for fewer than two pairs or a constant rank vector.
- ICIR is null for fewer than two non-null IC observations or zero IC standard
  deviation.
- Report arrays have canonical sort orders and canonical JSON uses sorted keys,
  UTF-8, compact separators, ISO dates, enum values, and decimal strings.
- SHA256 of the canonical report JSON is `report_digest`.

Identical input bytes, IDs/digests, definition, and target-session range must
produce identical report JSON and digest.

## Poison-gate output contract

When `PIT_UNIVERSE_MISSING` or `SCOPE_INCOMPATIBLE` applies, all of these arrays
must be empty:

- `cross_sectional_points`;
- `forward_outcomes`;
- `rank_ic_observations`;
- `ic_summaries`;
- `decile_outcomes`.

`factor_points` and `distributions` remain present, the report remains
`EXPLORATORY`, and formal `research_eligible` remains false.
