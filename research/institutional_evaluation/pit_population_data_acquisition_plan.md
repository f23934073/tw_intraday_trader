# PR-008 PIT Population and Data Acquisition Plan

## Current gate

`FormalEvaluationGateV1` is preregistered, but exact split dates remain locked
behind a coverage-only resolution. No setup, execution, return, or holdout
outcome may be generated until that resolution is immutable and referenced by
the final `CompositeResearchInputManifestV1`.

## Phase A — coverage-only inventory

Inventory availability without reading outcome fields:

1. TWSE and TPEx trading sessions and holidays.
2. Official institutional partitions, publication timestamps, scope, and
   validated normalized digests.
3. Date-effective ordinary-equity universe, industry, market-cap, listing, and
   delisting history.
4. Corporate-action and reference-price evidence.
5. One-minute OHLCV availability sufficient for the frozen Gap/VWAP setup.
6. Daily volume and close history sufficient for T-1 ADV20 and prior-20-session
   momentum ranks.

Allowed inspection is limited to session dates, markets, availability flags,
PIT member counts, row counts, and issue codes. Price values, setup flags,
executions, and returns are prohibited during this phase.

Output: an immutable `coverage_resolution_v1` artifact containing source IDs,
digests, capabilities, eligible session intersection, exclusions, exact
train/validation/holdout dates, and its own SHA-256 digest.

## Phase B — deterministic split resolution

Sort the eligible-session intersection chronologically. Assign:

- first `floor(0.60 * N)` sessions to train;
- next `floor(0.20 * N)` sessions to validation;
- all remaining sessions to untouched holdout.

The holdout must contain at least 60 eligible sessions. Empty markets, missing
PIT classifications, incomplete corporate-action coverage, or an insufficient
holdout produce `BLOCKED`; ratios and dates are not adjusted after seeing
outcomes.

## Phase C — PIT population and arms

For each target session T:

1. Resolve common stocks active and eligible on T from the date-effective
   universe.
2. Use only information available before T opens.
3. Produce `ELIGIBLE_UNIVERSE`, `PRICE_ONLY`, `INSTITUTIONAL_ONLY`, and
   `COMBINED` memberships from frozen prior definitions.
4. Calculate `ADV20_SHARES` from the prior 20 eligible sessions after corporate
   action normalization; form HIGH/MID/LOW terciles independently within TWSE
   and TPEx, breaking ties by symbol.
5. Build matched controls without replacement using exact market, industry,
   market-cap cohort, and ADV20 cohort; select the nearest prior-20-session
   return rank. Do not relax a failed match. Record unmatched candidates.

All arm memberships and controls must be frozen before any T-session setup or
outcome calculation.

## Phase D — train and validation only

Run the frozen strategy and cost definitions on train. Validation may select
only a choice declared before validation begins; after validation, archive the
selected definition/config digest. Secondary metrics and favorable subgroups
cannot replace the primary gate.

Do not materialize holdout setup flags, fills, returns, summaries, or previews.

## Phase E — untouched holdout

Before the single holdout run, require:

- protocol and coverage-resolution digests;
- exact split dates;
- all `CompositeResearchInputManifestV1` inputs and definition digests;
- `research_eligible=true` with no formal-required issue;
- PostgreSQL adapter verification or an explicit reviewed persistence waiver;
- locked validation choice and code identity.

Execute holdout once and persist the report unchanged whether the verdict is
`PASS`, `FAIL`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`. PR-009 remains on hold
regardless of framework readiness and can start only after evidence review.

## Current repository inventory

- `data/backtest/backtest.sqlite3` contains zero datasets, runs, and trades.
- No formal evaluation observation population exists.
- `TEST_POSTGRES_DSN` is not available in the current environment.
- Therefore this plan authorizes acquisition and coverage resolution only; it
  does not claim that the evidence campaign can run yet.
