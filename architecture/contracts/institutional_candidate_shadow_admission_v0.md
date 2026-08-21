# Institutional Candidate Shadow Admission v0

## Status and boundary

This is the PR-007 adapter from the frozen, durable Candidate Prior v0 to the
existing `CandidatePool`. It is data-only shadow admission. It does not create
a BuyScore input, trading signal, subscription request, broker call, paper
fill, order, or real-money authority.

The authoritative path is:

```text
CandidatePriorRepository
        -> PreviousSessionWatchlistCandidateSource
        -> CandidateDiscovery(PREVIOUS_SESSION_WATCHLIST)
        -> CandidatePool
        -> InstitutionalCandidateShadowAdmission decision/metrics
```

The adapter never changes or reserializes `InstitutionalCandidatePriorArtifact
v0`. Its exploratory and readiness fields remain frozen, including
`live_admission_ready=false` and `execution_allowed=false`.

## Adapter projection

Only matched Candidate Prior projections are considered. The adapter requires
the artifact target session to equal the current `InstrumentReferenceStore`
session. Every symbol is checked against that T-day store; a T-1 PIT universe
membership is not runtime eligibility.

Each eligible row becomes one generic `CandidateDiscovery` with:

- `source=PREVIOUS_SESSION_WATCHLIST`;
- hypothesis definition IDs as `rank_types`;
- Candidate Prior rank as `best_rank`;
- prior generation time and an explicit target-session expiry;
- a configured bounded priority;
- one bounded contribution reference containing only artifact ID and entry
  digest.

CandidatePool does not receive institutional factor values, formulas, trust
rules, PIT calculations, upstream institutional dataset digests, or the full
artifact JSON. Unknown/missing artifacts, target-session mismatch, invalid
expiry, or actionability drift fail closed.

## Capacity and protected symbols

The shadow admission policy requires explicit provider limit, quote mode, and
reserved headroom. Missing headroom or mode is not a valid policy. Effective
symbol capacity uses the existing reviewed `SubscriptionCapacityConfig`
formula.

Capacity is allocated in this order:

1. manual, position, and active-episode protected symbols;
2. existing non-institutional CandidatePool entries;
3. previous-session-only entries, capped by both residual capacity and
   `max_institutional_candidates`.

A symbol already present through a selected non-institutional source keeps its
institutional contribution reference without consuming an incremental slot or
institutional budget. Protected symbols exceeding effective capacity fail
closed. The decision records base rejections, institutional overlaps, budget
rejections, capacity rejections, selected symbols, counts, and a deterministic
digest.

## Prohibited effects

Every decision explicitly carries `mode=SHADOW`, `subscription_allowed=false`,
and `execution_allowed=false`; these fields are included in the deterministic
decision digest. The PR-007 implementation does not call `SubscriptionManager`, provider SDKs,
BuyScore/scoring engines, risk/order applications, or brokers. It emits no
request symbols and mutates no live subscription state. Turning a shadow
selection into live subscription admission requires a separate review gate.

## Verification gate

- previous-session source is never folded into `AUTO`;
- contribution reference survives CandidatePool union and decision digest;
- wrong-session and T-day-ineligible symbols do not enter the pool batch;
- manual/position/active protections and reviewed capacity cannot be exceeded;
- institutional budget and residual-capacity rejections are explicit;
- identical inputs reproduce identical source/admission digests;
- Candidate Prior v0 schema and readiness flags remain unchanged;
- BuyScore, subscription, broker, and order semantics remain unchanged.
