# Morning quote evidence — reviewer disposition

## Decision

**PASS — qualified Phase 0 Freshness Calibration Evidence; not a threshold
freeze.**

The three qualified morning continuous artifacts may be used to describe
collector integrity and observed quote cadence. They do not unblock
`FreshnessPolicyV1` or Phase 1.

## Review-confirmed qualitative findings

1. **`Executable quote health != Tick freshness alone`.**
   The low cohort can have long Tick silence while its subscription is
   `CONNECTED/ACTIVE` and BidAsk callbacks continue. A future executable-book
   health decision must not map `now - last_tick > N` directly to `BOOK_STALE`.
2. **A BidAsk-plus-lifecycle model is supported as a design direction.**
   Future executable book health must consider connection health, subscription
   acknowledgement/state, BidAsk freshness, and BidAsk timestamp/order checks.
   This disposition does not set the BidAsk freshness threshold and does not
   replace market/session-state handling.
3. **Tick remains valuation/display evidence.**
   Tick timing can inform last-trade valuation/display evidence, but the present
   campaign does not qualify it as the sole executable-book health signal.
4. **Source event time remains provenance, ordering, and anomaly evidence.**
   Without a provider/exchange-to-local clock-domain contract,
   `callback_received_at - market_event_at` is not a transport-latency SLA
   input. The monotonic callback receipt time remains the local cadence measure.

## Evidence ledger status

| Evidence | Status | Basis / remaining gate |
|---|---|---|
| Quote collector integrity | `PASSED` | Schema, digest, receipt range, and composite-key checks pass across the retained artifacts. |
| Subscription lifecycle integrity | `PASSED` | Qualified artifacts require paired `TIC`/`QUO` acknowledgement and all-ACTIVE rows. |
| Morning continuous quote cadence | `QUALIFIED_EVIDENCE` | Three non-overlapping qualified samples under the unchanged frozen cohort. |
| Tick-only health hypothesis | `REJECTED` | Active subscriptions and BidAsk callbacks coexist with sparse/quiet Ticks. |
| BidAsk + connection/subscription health model | `SUPPORTED` | Qualitative model only; no freshness duration is selected. |
| Source-clock transport latency | `NOT_VALIDATED` | NTP gives host provenance only; provider/exchange clock relation is unresolved. |
| Opening-session evidence | `INSUFFICIENT` | The valid opening recapture has only 3/6 callback groups. |
| Close-session evidence | `INSUFFICIENT` | The 13:01 artifact is valid partial evidence, but has 5/6 callback groups and ends before the 13:30 boundary. |
| Cross-session repeatability | `INSUFFICIENT` | Current qualified samples are one trading date and one regime. |
| Broker positions freshness | `NO_EVIDENCE` | Requires separately authorized read-only broker source. |
| Broker orders freshness | `NO_EVIDENCE` | Requires separately authorized read-only broker source. |
| Broker accounting freshness | `NO_EVIDENCE` | Requires separately authorized read-only broker source. |
| Buying-power freshness | `NO_EVIDENCE` | Requires separately authorized read-only broker source. |
| `FreshnessPolicyV1` | `BLOCKING_EVIDENCE` | No quote or broker/account threshold is frozen. |

## Measurement protocol remains frozen

Continue with the unchanged `2886:high`, `6863:mid`, and `1530:low` cohort;
the same callback collector/schema/quality gate; and the same monotonic-clock
cadence definition. Add opening, continuous, and close evidence across multiple
completed sessions without pooling regimes to manufacture a cutoff.

Broker/account evidence is a separate campaign. It must capture
`request_started_at`, `response_received_at`, `broker_source_as_of`,
`projection_updated_at`, and success/unsupported/timeout/error outcome before
any of its four thresholds can be reviewed.

## Phase decision

```text
FreshnessPolicyV1: BLOCKING_EVIDENCE
Phase 0:           NOT COMPLETE
Phase 1:           BLOCKED
```

## Frozen execution order

1. Complete today's scheduled close-window quote capture under the unchanged
   cohort, collector, schema, and quality gate. Qualifying it adds evidence
   only; one close sample cannot select a threshold.
2. Repeat opening, continuous, and close capture across completed trading
   sessions, preserving the measurement protocol and comparing liquidity ×
   session regime × trading date rather than a pooled percentile.
3. Resolve the source-clock disposition. Until clock domains are proven
   comparable, `market_event_at` remains provenance/ordering/anomaly evidence
   and `event_to_callback_ms` is excluded from SLA selection.
4. Run a broker/account evidence campaign only after explicit authorization for
   read-only endpoints. It must capture request start, response receipt, source
   as-of, projection update, and success/unsupported/timeout/error outcome for
   positions, orders, accounting, and buying power.

Until these gates are complete and reviewed, do not implement Portfolio
migrations/core, RiskGate freshness logic, or a provisional magic-number
threshold.
