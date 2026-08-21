# Cross-session close checkpoint — through 2026-08-21

## Evidence status

| Evidence | Status | Basis / remaining gate |
|---|---|---|
| Quote collector integrity | `PASSED` | All retained artifacts pass schema/digest and callback-integrity checks. |
| Subscription lifecycle integrity | `PASSED` | Every accepted observation is after paired acknowledgement and `CONNECTED/ACTIVE`. |
| Morning continuous cadence | `QUALIFIED_EVIDENCE` | Three complete 2026-08-20 continuous samples. |
| Tick-only executable-health | `REJECTED` | Sparse/no Tick occurs while paired-active subscriptions retain BidAsk callbacks. |
| BidAsk + connection/subscription direction | `SUPPORTED` | Qualitative only; no duration threshold is selected. |
| Cross-session early-close cadence | `PARTIAL_CROSS_SESSION_EVIDENCE` | 2026-08-20 and 2026-08-21 close samples repeat the low-cohort no-Tick result. |
| Close 13:30 session-boundary semantics | `INSUFFICIENT` | Both captures end around 13:16. |
| Complete three-tier close coverage | `INSUFFICIENT` | Both captures have 5/6 callback groups; `1530/TICK` is absent. |
| Source-clock transport latency | `NOT_VALIDATED` | Host NTP provenance does not align provider/exchange event time. |
| Cross-session all-regime repeatability | `INSUFFICIENT` | Opening / continuous / close are not yet complete across multiple dates. |
| Broker/account evidence | `NO_EVIDENCE` | Requires separately authorized read-only source. |
| `FreshnessPolicyV1` | `BLOCKING_EVIDENCE` | No threshold is frozen. |

## Cross-session close comparison

| Capture date | Range | 2886 Tick / BidAsk | 6863 Tick / BidAsk | 1530 Tick / BidAsk | Coverage |
|---|---|---:|---:|---:|---|
| 2026-08-20 | 13:01–13:16 | 371 / 1,636 | 6 / 71 | 0 / 8 | 5/6 |
| 2026-08-21 | 13:01–13:16 | 285 / 1,135 | 4 / 72 | 0 / 1 | 5/6 |

The two samples increase confidence in the qualitative Tick-only rejection but
not in a BidAsk stale duration. They remain separate date/regime observations
and must not be pooled into a threshold.

## Phase decision

```text
FreshnessPolicyV1: BLOCKING_EVIDENCE
Phase 0:           NOT COMPLETE
Phase 1:           BLOCKED
```
