# Institutional Candidate Prior v0 Contract

## Status and boundary

`institutional_candidate_prior_v0` is an immutable, research-only premarket
artifact. It implements exactly two exploratory hypotheses:

- `candidate.institutional_momentum_confirmation_v0`;
- `candidate.institutional_foreign_trust_consensus_5d_v0`.

Every artifact and read projection carries explicit
`research_status=EXPLORATORY`, `strategy_ready=false`,
`production_ready=false`, `live_admission_ready=false`, and
`execution_allowed=false`. It is a Candidate Prior, not a BUY signal, entry
rule, BuyScore contribution, CandidatePool admission, subscription request, or
order instruction. Real-money use is prohibited.

## Frozen v0 definitions

Both hypotheses use `ROLLING_NET_SHARES_5D` as the primary factor and preserve
five sessions as the primary factor and forward-evaluation horizon. The 1D and
3D forward horizons remain secondary exploratory diagnostics.

A foreign-ex-dealer or investment-trust component qualifies only when:

- the explicit 5D raw net-share value is strictly positive; and
- its PIT cross-sectional percentile is at least `0.50`.

The threshold and all null behavior are part of each definition's canonical
SHA256 digest. They were frozen before PR-005 output evaluation. Changing the
lookback, threshold, component policy, horizon, or label requires a new
definition version and review; v0 constructors reject such changes.

Hypothesis A requires membership in the pinned price-momentum prior and at
least one qualifying institutional component. Hypothesis B requires both
foreign-ex-dealer and investment-trust components to qualify. A missing
component remains missing and never becomes zero.

## Pinned inputs

`CandidatePriorRunManifestV0` pins by ID and SHA256 digest:

- a target-session institutional factor-prior snapshot projected from PR-004;
- a narrow price-momentum membership artifact generated elsewhere;
- the date-effective PIT equity universe;
- the market calendar;
- both v0 hypothesis definitions.

It also records target session, as-of session, and a timezone-aware generation
time. The target must be after the as-of session. The price prior must match
those sessions and calendar and cannot be generated after the Candidate Prior
run.

The factor-prior projector first validates the complete PR-004 report's
canonical bytes, exploratory/readiness flags, PIT/scope eligibility, universe,
and frozen baseline definition. It then serializes only the target-session 5D
cross-sectional points plus their immutable institutional-dataset, universe,
and definition lineage. The PR-005 manifest does not pin PR-004 forward
outcomes, IC, price bundle, or full-report digest. Adding later report sessions
or changing future outcome bytes under the same institutional input must
reproduce the same factor-prior digest. A new institutional bundle creates a
new factor-prior identity and cannot replace the artifact pinned by an existing
run manifest.

The price-momentum input carries only prior membership, rank, definition
identity, calendar identity, and per-entry digest. PR-005 does not duplicate or
recalculate SMA, volume, or momentum formulas.

## Complete denominator and evaluation cohorts

The builder resolves the exact pinned `EquityUniversePort` at the target
session. Every PIT eligible ordinary equity becomes an artifact entry even when
its 5D factor is missing. This prevents factor availability from silently
changing the evaluation denominator.

Each entry records non-exclusive cohort membership:

- `ELIGIBLE_UNIVERSE`;
- `PRICE_ONLY` for the pinned price baseline;
- `INSTITUTIONAL_ONLY` when either institutional component qualifies;
- `COMBINED` when both price and institutional membership exist.

Price-prior symbols outside the resolved universe are excluded fail-closed and
raise the artifact-level `PRICE_PRIOR_OUTSIDE_PINNED_UNIVERSE` issue code.
They cannot enter the read projection.

The immutable artifact retains matched and unmatched rows for later PR-008
incremental evaluation. The read-only projection contains only entries matching
hypothesis A and/or B.

## Ranking and bytes

Candidate rank is deterministic and is not a probability or BuyScore. Ordering
uses:

1. matched-hypothesis count descending;
2. minimum present foreign/trust percentile descending;
3. maximum present foreign/trust percentile descending;
4. price rank ascending, with missing rank last;
5. market and symbol ascending.

Every entry has a SHA256 digest over its canonical payload. The entries array,
both definitions, price prior, factor prior, and final artifact use canonical
JSON with sorted keys, compact separators, ISO dates/times, enum values, and
decimal strings. Identical pinned inputs and definitions must reproduce the
same bytes and digest regardless of caller Decimal precision.

## Poison gates

No artifact is emitted when any of these conditions applies:

- source factor-report bytes cannot be canonically projected;
- factor-prior or price-prior identity, JSON, or digest mismatch;
- source report or factor prior is not exploratory or claims
  research/strategy/production readiness;
- PIT, scope, or cross-sectional eligibility is false;
- baseline factor definition, universe, calendar, sessions, or hypothesis
  definition identity differs from the manifest;
- the PIT universe is missing, ineligible, unresolved, or digest-mismatched;
- a target factor point is duplicated or lies outside the pinned universe;
- the price prior is stale or generated after the run.

Post-target report rows and forward outcomes are excluded by construction and
must not change either the factor-prior or Candidate Prior digest.

The artifact contract rejects unknown fields and explicitly prohibits
`forward_return`, `IC`, `ICIR`, `decile_return`, `win_rate`, and `expectancy`.
Those fields belong only to a separately versioned evaluation artifact.

## Adapter boundary after PR-006

PR-006 adds only the durable projection defined by
`institutional_candidate_persistence_v0.md`. PR-007 may read this frozen
artifact only through the separate data-only adapter defined by
`institutional_candidate_shadow_admission_v0.md`; it does not change this v0
schema or its readiness flags. APIs, Dashboard UI, live subscription admission,
paper fills, broker integration, evaluation outcomes, and orders remain later
review gates.
