# Freshness discovery capture review — 2026-08-20 09:05 Asia/Taipei

## Result

**Status: raw discovery evidence retained; no threshold candidate.**

This is a 120-second, data-only Shioaji Tick/BidAsk capture. It demonstrates
that the calibration callback/store seam and paired-subscription lifecycle work
during the Taiwan regular session. It does **not** satisfy the frozen cohort
protocol and cannot freeze any value in `FreshnessPolicyV1`.

## Immutable source

| Field | Value |
|---|---|
| Artifact | `research/captures/freshness_quote/quote_20260820T090534+0800.json` |
| Schema | `freshness_calibration_quote_v1` |
| SHA-256 | `17dd2ead6a7ad17b2c389f4e263104c756096c5dd4131c45a7a6143f438b5e97` |
| Bytes | 263,563 |
| Capture interval | 2026-08-20 09:05:34.660359–09:07:34.800169 +08:00 |
| Stream scope | Tick and BidAsk only; no order, account, CA, or trade-callback API |
| Cohort label | `2330:discovery` / `continuous_discovery` (explicitly unqualified) |

Digest and schema inspection passed. The collector wrote the JSON with
exclusive-create semantics.

## Observations

| Stream | Observations | Missing event time | Callback monotonic regressions | Negative event-to-callback |
|---|---:|---:|---:|---:|
| BidAsk | 474 | 0 | 0 | 353 |
| Tick | 20 | 0 | 0 | 20 |

The in-process callback-to-store seam is low in this sample: BidAsk p50/p95/p99
are 0.048/0.084/0.263 ms, and Tick p50/p95/p99 are 0.030/0.084/0.190 ms. These
are **collector-buffer measurements**, not UI, RiskGate, broker, or accounting
freshness values.

The source event-to-callback field is not usable as a transport-latency SLA:
many raw values are negative. The artifact preserves them unchanged. A
post-capture, read-only `time.apple.com` NTP sample reported local clock
provenance of `+58.825 ms +/- 53.094 ms`; it neither adjusted the host clock nor
established the provider/exchange event-clock offset.

## Lifecycle quality

The raw lifecycle record shows a successful Tick acknowledgement (`TIC`) and
BidAsk acknowledgement (`QUO`) for `TSE/2330`. Observations were made only
after the resulting `CONNECTED` / `ACTIVE` state. Cleanup recorded
`DISCONNECTED` / `INACTIVE`; no callback error was retained.

## Decision

Do not infer a stale-after threshold from this artifact. It has only one symbol,
one unqualified session label, a short time range, and uncalibrated
source-to-host clock relation. It supplies no broker/account observation, so it
cannot support any of:

- `broker_positions_stale_after_ms`
- `broker_orders_stale_after_ms`
- `broker_accounting_stale_after_ms`
- `buying_power_stale_after_ms`

`FreshnessPolicyV1` remains `BLOCKING_EVIDENCE`; Phase 0 remains incomplete and
Phase 1 remains blocked.

## Remaining evidence work

1. Freeze a reviewer-approved manifest with documented high/mid/low selection
   evidence and `opening`, `continuous`, and `close` time windows before
   qualified quote captures start.
2. Collect and inspect qualified Tick/BidAsk artifacts for every manifest
   cohort/window, retaining lifecycle and clock provenance.
3. Obtain separately authorized, read-only broker/account timing observations.
   Quote data must never be used to derive those four values.
