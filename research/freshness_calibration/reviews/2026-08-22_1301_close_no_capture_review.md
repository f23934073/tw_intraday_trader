# 2026-08-22 Frozen Close Window — No-Capture Review

## Disposition

**NO_CAPTURE — reviewed calendar / host date conflict.**

The close-window heartbeat was received at `2026-08-22T05:00:08Z`, but the
host reported `2026-08-22T13:01:11+08:00 Sat`. 2026-08-22 is Saturday and is
therefore not a reviewed Taiwan-equity trading day.  The frozen close protocol
requires a fail-closed outcome in this situation: no Shioaji login,
subscription, Tick/BidAsk callback, account/order/CA/trade-callback API, or
Portfolio work was started.

## Read-only NTP preflight

Five `/usr/bin/sntp -d time.apple.com` invocations were made without changing
the system clock. Each invocation selected a successful time source despite
some individual endpoint timeout attempts:

| Sample | Selected offset | Selected uncertainty | Result |
|---|---:|---:|---|
| 1 | +0.406864 ms | +/- 0.270298 ms | success |
| 2 | +0.406116 ms | +/- 0.269178 ms | success |
| 3 | +0.405410 ms | +/- 0.271489 ms | success |
| 4 | +0.407023 ms | +/- 0.270985 ms | success |
| 5 | +0.406715 ms | +/- 0.270263 ms | success |

This is host-clock provenance only. It does not establish a provider/exchange
clock relation and cannot select a quote threshold.

## Required artifact checks

No quote artifact exists for this heartbeat, so digest/schema, paired
`TIC`/`QUO` acknowledgement, per-row lifecycle, coverage, clock-skew,
callback-error, and monotonicity checks are **not applicable**. They were not
silently treated as passing.

## Gate effect

All eight FreshnessPolicyV1 thresholds remain unset. This is not a qualified
close observation, does not alter the source-clock disposition, and does not
unblock Portfolio Phase 1.
