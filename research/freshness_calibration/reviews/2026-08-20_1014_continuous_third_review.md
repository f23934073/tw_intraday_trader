# Freshness third continuous review — 2026-08-20 10:14 Asia/Taipei

## Decision

**Status: third qualified continuous quote sample; no threshold candidate.**

This is the third non-overlapping, same-day `continuous` sample under the
unchanged frozen cohort. It adds cadence variability evidence only; it does not
freeze a `FreshnessPolicyV1` value.

## Immutable source and provenance

| Field | Value |
|---|---|
| Artifact | `research/captures/freshness_quote/quote_20260820T101439+0800.json` |
| SHA-256 | `181a59b0d9fbd378a70b638f659b0d854a8e5e74b29dd6c2cceeedb321accd6f` |
| Schema / bytes | `freshness_calibration_quote_v1` / 963,235 |
| Capture range | 2026-08-20 10:14:39.534396–10:29:39.757975 +08:00 |
| Cohort manifest | `cohort_manifest_2026-08-20_twse_2026-08-19.json` |
| Callback scope | Tick and BidAsk only; `subscribe_trade=False`; no account, order, CA, or trade-callback API |
| Preflight NTP sample | `+33.583 ms +/- 53.005 ms` from `time.apple.com`; successful selected sample with two retained timeout attempts; read-only host-clock provenance |

Schema and digest inspection passed. The artifact records `TIC` and `QUO`
acknowledgement for every symbol. All 1,872 observations are
`CONNECTED/ACTIVE`; callback errors, callback monotonic regressions, duplicate
composite observation keys, and receipts outside the capture interval are zero.

## Coverage and observed event sparsity

| Tier / symbol | BidAsk callbacks | Tick callbacks | Longest observed BidAsk gap | Longest observed Tick gap |
|---|---:|---:|---:|---:|
| high / 2886 | 1,489 | 333 | 7.640 s | 8.065 s |
| mid / 6863 | 26 | 3 | 127.990 s | 166.818 s |
| low / 1530 | 20 | 1 | 152.231 s | N/A (one Tick only) |

## Three-sample synthesis

| Sample | 2886 Tick / BidAsk | 6863 Tick / BidAsk | 1530 Tick / BidAsk |
|---|---:|---:|---:|
| 09:30 | 251 / 1,203 | 4 / 46 | 1 / 8 |
| 09:54 | 282 / 1,191 | 5 / 94 | 12 / 37 |
| 10:14 | 333 / 1,489 | 3 / 26 | 1 / 20 |

All three samples are paired-acknowledged and all-ACTIVE, yet low-tier Tick
counts range from one to twelve and mid-tier Tick counts range from three to
five per fifteen-minute sample. Longest observed Tick gaps also vary materially:
mid 124.389–210.941 seconds; low has two samples with only one Tick and the
remaining sample reaches 488.363 seconds. Thus event silence is a normal
observed cadence outcome in this cohort, not evidence that an active book is
stale.

The third sample happens to have fewer negative event-to-callback values
(89/1,872) than the first two samples. That variation does not establish source
clock alignment, provider transport latency, or an SLA: no independent
source-clock calibration exists. Raw values remain provenance, not threshold
inputs.

## Explicit exclusions and next gate

- No `ui_*` or `risk_*` threshold is proposed. Same-day repetition is not
  multi-day evidence, opening remains partial, close is not yet collected, and
  source-clock disposition is unresolved.
- No broker/account threshold is represented. Quote artifacts must never proxy
  positions, orders, accounting, or buying-power freshness.
- The active one-time close-window heartbeat is the next authorized collection
  action; its cohort and API scope remain unchanged.
