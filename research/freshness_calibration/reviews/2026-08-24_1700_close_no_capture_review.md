# 2026-08-24 Frozen Close Window — No-Capture Review

## Disposition

**NO_CAPTURE_OFF_SESSION — host clock was after the Taiwan-equity close.**

The heartbeat timestamp was `2026-08-24T05:02:25Z` (13:02 Asia/Taipei), but
the host reported `2026-08-24T17:00:08+08:00 Mon` immediately before the
preflight. Although 2026-08-24 is a reviewed trading day, 17:00 is outside the
frozen close collection window. The capture ended fail-closed before any
Shioaji import/login, Tick/BidAsk subscription/callback, account/order/CA/
trade-callback API, execution path, or Portfolio work.

## Read-only NTP preflight

Five `/usr/bin/sntp -d time.apple.com` invocations completed without adjusting
the system clock. Every invocation selected a successful source despite some
individual exchange timeout attempts:

| Sample | Selected offset | Selected uncertainty | Result |
|---|---:|---:|---|
| 1 | +0.037296 ms | +/- 0.271987 ms | success |
| 2 | +0.037298 ms | +/- 0.271564 ms | success |
| 3 | +0.037329 ms | +/- 0.271837 ms | success |
| 4 | +0.037209 ms | +/- 0.272184 ms | success |
| 5 | +0.036743 ms | +/- 0.271546 ms | success |

This remains host-clock provenance only. It cannot bridge the heartbeat/host
clock discrepancy, establish provider/exchange clock comparability, or select
a threshold.

## Required artifact checks

No quote artifact exists. Digest/schema, paired `TIC`/`QUO` acknowledgement,
per-row connection/subscription state, coverage, clock-skew, callback-error,
and monotonicity are **not applicable**, not pass.

## Gate effect

All eight FreshnessPolicyV1 thresholds remain unset. This is not qualified close
evidence, does not change the source-clock disposition, and leaves Portfolio
Phase 1 blocked.
