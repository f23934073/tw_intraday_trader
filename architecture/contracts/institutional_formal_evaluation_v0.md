# Institutional Formal Evaluation v0

## Status and purpose

This is the PR-008 research-only evaluation boundary for Candidate Prior v0.
It asks one fixed question: under the same setup, outcome, and cost definitions,
does `COMBINED` improve net expectancy over `PRICE_ONLY`? It does not change
candidate ranking, BuyScore, entry/exit rules, subscriptions, risk decisions,
paper fills, broker calls, or orders.

Every report carries `subscription_allowed=false` and
`execution_allowed=false`. A formal PASS is research evidence only; it is not
production or real-money authorization.

## Frozen inputs

`CompositeResearchInputManifestV1` requires digest-pinned identities for:

- price and institutional datasets;
- PIT universe plus PIT classification/size data;
- calendar, corporate actions, and reference data;
- complete Candidate Prior population and pre-frozen matched controls;
- the exact evaluation observations and coverage matrix;
- setup, outcome, cost, and evaluation-plan definitions;
- code identity and non-overlapping train/validation/holdout ranges.

All formal-required digests must exist. The cost model must cover the complete
time range. A manifest with unresolved issues cannot claim
`research_eligible=true`.

## Observation contract

One observation is one unique session/market/symbol identity. It preserves the
five cohort memberships:

1. `ELIGIBLE_UNIVERSE`;
2. `PRICE_ONLY`;
3. `INSTITUTIONAL_ONLY`;
4. `COMBINED`;
5. `MATCHED_CONTROL`.

Every row belongs to the complete eligible denominator. `COMBINED` membership
must exactly equal price/institutional overlap. A matched control cannot satisfy
institutional selection. The first valid setup timestamp is required exactly
when a setup qualified. Execution outcomes are accepted only for qualified
setups, and `net_return = gross_return - cost_return` is enforced.

The evaluator does not generate these outcomes or reinterpret the existing
strategy. It consumes an immutable outcome population created under the pinned
definitions and rejects a digest mismatch, duplicate identity, or wrong split.

## Metrics and inference

Candidate/setup metrics and execution metrics remain separate:

- candidate count, setup count, setup precision;
- execution count and turnover rate;
- gross, cost, and net expectancy.

The primary comparison is `COMBINED - PRICE_ONLY` net expectancy. Its confidence
interval uses session-clustered influence contributions, so same-session symbols
are not treated as independent observations. TWSE, TPEx, and preregistered
liquidity guardrails use the same comparison and confidence rule.

## Preregistered holdout gate

Thresholds have their own deterministic digest. The gate records an immutable
registration artifact, timestamp, and the exact registered threshold digest.
Formal evaluation supports only confidence levels 90%, 95%, and 99%, with the
actual choice, sample sizes, turnover allowance, liquidity cohorts, and allowed
guardrail deterioration supplied by the research owner before holdout.

The verdict is:

- `NOT_APPLICABLE` for train/validation;
- `BLOCKED` for ineligible inputs or registration on/after holdout start;
- `INSUFFICIENT_EVIDENCE` for missing controls, samples, or confidence intervals;
- `FAIL` when the primary CI lower bound is not positive or a guardrail fails;
- `PASS` only when every preregistered condition passes.

Negative, null, blocked, and insufficient results remain in the immutable report.
No code path promotes a favorable subgroup into a formal PASS.

## Remaining operational gate

This implementation establishes the deterministic evaluation engine and
artifact contract. It does not contain a real historical holdout result. Before
PR-008 review can approve evidence, the research owner must freeze threshold
values, build eligible TWSE/TPEx observations from the pinned datasets, run the
untouched holdout once, and archive the resulting artifact and coverage matrix.
