# Freshness post-session cross-evidence review — through 2026-08-26

## Decision

**Status: evidence collection is operating; FreshnessPolicyV1 remains blocked.**

The quote collector and its normal close scheduler are structurally healthy.
The current broker/account campaign is also producing valid, redacted artifacts,
but all endpoint results are constrained gaps rather than successful freshness
observations. No threshold candidate is selected.

## Scope and safety boundary

This is an offline review of already-written immutable artifacts. It made no
broker/account request and made no change to a quote, account, order, CA, trade
callback, or Portfolio path. All reviewed broker artifacts declare
`submit_order=false`, `cancel_order=false`, `modify_order=false`,
`activate_ca=false`, `subscribe_trade=false`, `trade_callback=false`,
`update_status=false`, and `retry=false`.

## Quote evidence

Ten 15-minute quote artifacts from 2026-08-25 and 2026-08-26 pass schema and
digest inspection. Every artifact has 6/6 paired Tick/BidAsk subscription
acknowledgements, zero callback errors, and zero callback monotonicity
regressions.

| Date | Opening | Continuous samples | Close | Complete callback groups |
|---|---|---|---|---|
| 2026-08-25 | 5/6 | 5/6, 5/6, 6/6 | 5/6 | 1 of 5 artifacts |
| 2026-08-26 | 4/6 | 5/6, 5/6, 6/6 | 5/6 | 1 of 5 artifacts |

The intermittent low-tier Tick absence is an observed market-activity/coverage
fact after active acknowledgement, not a collector failure and not a synthetic
stale result. The two complete continuous artifacts are useful qualitative
evidence only.

The normal quote scheduler is correctly configured for a `close` start at
13:15 with a 1,200-second duration. It is permitted both on-time (13:15) and
within its five-minute launch grace (13:20), and runs through 13:35. Therefore
the next ordinary close run can observe the 13:30 session boundary. The
2026-08-26 one-shot artifact ended at 13:17 because the heartbeat explicitly
requested a separate 13:02, 900-second run; that does not indicate a scheduler
defect.

## Broker/account evidence

Ten `broker_account_freshness_v1` artifacts (five each on 2026-08-25 and
2026-08-26) pass schema, digest, exclusive endpoint shape, and no-mutation
guardrail validation. Each uses `shioaji:1.7.2:simulation=true`.

| Evidence kind | Outcome across 10 artifacts | Freshness-threshold support |
|---|---|---|
| Positions | `AUTH_DENIED` / `TokenError` | No |
| Accounting | `SOURCE_ERROR` / `ShioajiConnectionError` | No |
| Buying power | `UNSUPPORTED_FOR_EVIDENCE_KIND` | No — account balance is not buying-power authority |
| Orders | Explicit excluded-source gap | No — fresh status requires prohibited `update_status` or trade callback |

The persistent `TokenError` is evidence that the selected simulation
broker/account source is not presently readable by this campaign. It is not
safe to infer whether this is account entitlement, environment configuration,
or provider behavior from the redacted artifacts alone. The persistent failure
is valuable diagnostic evidence, but it cannot set a broker freshness SLA.

## Remaining blockers

1. Quote: collect and review a normal 13:15–13:35 close artifact, then repeat
   required session regimes across additional normal trading dates without
   pooling them into a threshold before review.
2. Source clock: retain negative event-to-callback observations as provenance;
   no transport-latency SLA can use them until clock comparability is disposed.
3. Broker/account: no successful positions or accounting observation, no
   documented buying-power source, and no permitted orders freshness source.

## Gate effect

All eight FreshnessPolicyV1 thresholds remain unset. `FreshnessPolicyV1`
remains `BLOCKING_EVIDENCE`; Phase 0 remains incomplete and Portfolio Phase 1
remains blocked.
