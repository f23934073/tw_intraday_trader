# Freshness continuous repeat review — 2026-08-20 09:54 Asia/Taipei

## Decision

**Status: second qualified continuous quote sample; no threshold candidate.**

This is an independent repeat of the frozen three-tier cohort in the same
`continuous` session window. It is qualified quote evidence and may be compared
with the earlier continuous sample, but it does not freeze any
`FreshnessPolicyV1` threshold.

## Immutable source and provenance

| Field | Value |
|---|---|
| Artifact | `research/captures/freshness_quote/quote_20260820T095444+0800.json` |
| SHA-256 | `7c937d32d3fc48f46307b880d2feda58e3f1d5449b020f2da1ad12fdd339638c` |
| Schema / bytes | `freshness_calibration_quote_v1` / 834,811 |
| Capture range | 2026-08-20 09:54:44.797013–10:09:45.311011 +08:00 |
| Cohort manifest | `cohort_manifest_2026-08-20_twse_2026-08-19.json` |
| Callback scope | Tick and BidAsk only; `subscribe_trade=False`; no account, order, CA, or trade-callback API |
| Preflight NTP sample | `+47.647 ms +/- 48.080 ms` from `time.apple.com`; read-only host-clock provenance |

The digest and schema inspection passed. The capture recorded paired `TIC` and
`QUO` acknowledgement for each symbol. All 1,621 observations are
`CONNECTED/ACTIVE`; callback errors, callback monotonic regressions, duplicate
composite observation keys, and receipts outside the capture interval are all
zero.

## Coverage and observed event sparsity

| Tier / symbol | BidAsk callbacks | Tick callbacks | Longest observed BidAsk gap | Longest observed Tick gap |
|---|---:|---:|---:|---:|
| high / 2886 | 1,191 | 282 | 7.136 s | 8.082 s |
| mid / 6863 | 94 | 5 | 88.713 s | 210.941 s |
| low / 1530 | 37 | 12 | 181.902 s | 488.363 s |

The frozen labels are only prior-completed-session trade-value cohort labels.
Observed inter-arrival gaps are event-cadence evidence, not a stale threshold
or a declaration of quote health.

## Repeat-sample findings

1. **A paired-active subscription can have long Tick silence.** The low cohort
   had a 488.363-second observed Tick gap and the mid cohort 210.941 seconds,
   while every callback in the artifact was `CONNECTED/ACTIVE` and BidAsk
   updates continued. This repeats and strengthens the earlier finding: Tick
   silence alone cannot define executable-quote failure.
2. **Cadence changes materially between same-window samples.** Compared with
   the prior 09:30 capture, low-cohort callbacks increased from 8 BidAsk / 1
   Tick to 37 / 12, while its longest observed gap still reached 181.902 /
   488.363 seconds. A single continuous sample cannot represent a safe cutoff.
3. **Source timestamps remain unsuitable for a transport SLA.** Negative
   event-to-callback values occur in 879/1,621 observations. They are retained
   raw; the NTP preflight only establishes limited host-clock provenance and
   does not calibrate the provider/exchange event clock.
4. **Callback-to-store remains a narrow measurement.** It describes the
   calibration in-memory buffer only, not browser/UI delivery, RiskGate,
   Portfolio projection, broker positions, orders, accounting, or buying power.

## Explicit exclusions

- This repeat does not set `ui_tick_stale_after_ms`,
  `ui_bidask_stale_after_ms`, `risk_tick_stale_after_ms`, or
  `risk_bidask_stale_after_ms`. Qualified opening and close coverage, multi-day
  repetition, clock-skew disposition, and human review remain incomplete.
- It cannot support any broker/account threshold. No broker/account source was
  called, and quote evidence must not be used as a proxy for broker/accounting
  freshness.
- The two duplicate runner processes started after this sample were terminated
  before completion and produced no artifacts. They are not campaign evidence.

## Next evidence gates

1. Let the existing one-time close-window heartbeat collect the unchanged frozen
   cohort, then verify it with the same gates.
2. Repeat qualified opening coverage on a future session and build multi-day
   evidence before considering quote threshold proposals.
3. Obtain separate, explicitly authorized read-only broker/account timing
   evidence for the four non-quote thresholds.
