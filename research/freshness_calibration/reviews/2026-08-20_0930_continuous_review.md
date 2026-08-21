# Freshness continuous cohort review — 2026-08-20 09:30 Asia/Taipei

## Decision

**Status: partial qualified quote evidence; no threshold candidate.**

This is the first artifact from the frozen three-tier cohort that has complete
`symbol × {Tick,BidAsk}` callback coverage and `CONNECTED/ACTIVE` state for
every persisted observation. It supports the calibration evidence campaign, but
does not freeze any `FreshnessPolicyV1` value.

## Immutable source and provenance

| Field | Value |
|---|---|
| Artifact | `research/captures/freshness_quote/quote_20260820T093046+0800.json` |
| SHA-256 | `7451e75b3a3fe26e750844e9e902a7aeb5e62ffe84d4276bacc7e4f24ddccad1` |
| Schema / bytes | `freshness_calibration_quote_v1` / 779,582 |
| Capture range | 2026-08-20 09:30:46.619658–09:45:47.362423 +08:00 |
| Cohort manifest | `cohort_manifest_2026-08-20_twse_2026-08-19.json` |
| Callback scope | Tick and BidAsk only; `subscribe_trade=False`; no account, order, CA, or trade-callback API |
| Preflight NTP sample | `+45.877 ms +/- 59.169 ms` from `time.apple.com`; read-only host-clock provenance |

The artifact schema and digest inspection passed. All three symbols received
both `TIC` and `QUO` acknowledgement, and all 1,513 persisted observations are
`CONNECTED/ACTIVE`. There were no callback errors, missing event timestamps, or
callback monotonic regressions.

## Coverage and observed event sparsity

| Tier / symbol | BidAsk callbacks | Tick callbacks | Longest observed BidAsk gap | Longest observed Tick gap |
|---|---:|---:|---:|---:|
| high / 2886 | 1,203 | 251 | 8.025 s | 8.025 s |
| mid / 6863 | 46 | 4 | 166.857 s | 124.389 s |
| low / 1530 | 8 | 1 | 164.827 s | N/A (one Tick only) |

The tier labels come only from the frozen prior-completed-session TWSE trade
value ranking. They do not assert a service quality level. The observed gaps are
raw evidence of market-event cadence during this interval, not a declared stale
cutoff.

## Data-quality findings

1. **Quote subscription health is distinguishable from Tick silence.** Every
   row was received after paired acknowledgement in `CONNECTED/ACTIVE` state,
   while 1530 had one Tick and 6863 had four over fifteen minutes. A rule of
   `no Tick for N ms = bad executable quote` would therefore be unsupported by
   this data. Severity: critical for any future RiskGate design.
2. **Source event time is not yet a trustworthy transport-latency clock.**
   Negative event-to-callback values occur in 679/1,203 high BidAsk, 176/251
   high Tick, 34/46 mid BidAsk, 4/4 mid Tick, 4/8 low BidAsk, and 1/1 low Tick
   observations. The NTP sample establishes limited host provenance only; it
   does not calibrate the provider/exchange event clock. Severity: high for
   event-to-callback latency interpretation.
3. **The calibration-buffer update is fast but has narrow meaning.** High-tier
   callback-to-store p99 is 0.128 ms (BidAsk) and 0.151 ms (Tick). This is the
   in-memory calibration buffer, not a UI render path, RiskGate, Portfolio
   projection, or broker/account SLA. Severity: medium if misrepresented.

## Explicit exclusions

- The earlier `quote_20260820T091616+0800.json` is immutable raw evidence but
  is excluded from qualified review because its former lifecycle bug persisted
  `PENDING` rows after paired acknowledgements.
- This review does not set `ui_*` or `risk_*` thresholds: only one date and one
  of three required session windows has complete qualified coverage, source
  clock relation remains unresolved, and threshold selection is human-review
  work.
- It cannot support `broker_positions_stale_after_ms`,
  `broker_orders_stale_after_ms`, `broker_accounting_stale_after_ms`, or
  `buying_power_stale_after_ms`. No broker/account source was called.

## Next evidence gates

1. Capture the unchanged frozen cohort during the `close` window and repeat
   qualified opening coverage on a future session.
2. Obtain a separate, authorized read-only broker/account evidence source with
   request, response, source-as-of, projection-update, status, and timeout
   timestamps.
3. Complete clock-skew disposition and a human review across all raw artifacts
   before proposing any threshold.
