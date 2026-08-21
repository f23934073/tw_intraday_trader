# Freshness calibration campaign checkpoint — 2026-08-20 13:16 Asia/Taipei

## Evidence ledger

| Artifact | Duration | Observations | State | Coverage | Disposition |
|---|---:|---:|---|---|---|
| `quote_20260820T090534+0800.json` | 120.485 s | 494 | 494 `CONNECTED/ACTIVE` | 2/2 discovery groups | Unqualified discovery only |
| `quote_20260820T091616+0800.json` | 600.390 s | 1,048 | 1,048 `CONNECTED/PENDING` | 6/6 groups | Rejected: lifecycle instrumentation bug |
| `quote_20260820T092834+0800.json` | 70.480 s | 117 | 117 `CONNECTED/ACTIVE` | 3/6 groups | Partial opening coverage |
| `quote_20260820T093046+0800.json` | 900.743 s | 1,513 | 1,513 `CONNECTED/ACTIVE` | 6/6 groups | Qualified continuous quote evidence |
| `quote_20260820T095444+0800.json` | 900.514 s | 1,621 | 1,621 `CONNECTED/ACTIVE` | 6/6 groups | Second qualified continuous quote sample |
| `quote_20260820T101439+0800.json` | 900.224 s | 1,872 | 1,872 `CONNECTED/ACTIVE` | 6/6 groups | Third qualified continuous quote sample |
| `quote_20260820T130116+0800.json` | 900.351 s | 2,092 | 2,092 `CONNECTED/ACTIVE` | 5/6 groups | Partial close evidence: no 1530 Tick; ends before 13:30 boundary |

Every artifact passed its own schema/digest inspection. Across all seven files,
the composite `(symbol, stream_kind, callback_received_monotonic_ns)` key has no
duplicates, every callback receipt falls within its capture interval, and there
is no recorded callback error. These checks validate collector/artifact
integrity; they do not validate a stale threshold.

## What can and cannot be used

Three independent continuous artifacts are currently complete qualified cohort
evidence. They remain separate samples: mid Tick gaps span 124.389–210.941
seconds, while low has two one-Tick samples and the remaining sample reaches a
488.363-second Tick gap. This supports the conclusion that Tick silence alone
cannot establish stale executable market data, but cannot define a cutoff.
The 09:16 artifact remains immutable but excluded, because it documented the
now-fixed multi-symbol lifecycle bug. The short opening recapture is retained as
partial evidence, not silently dropped: it records that 1530 and 6863 Tick data
did not appear in that 70-second interval despite paired acknowledgement.

No quote artifact supports broker/account freshness. All eight values remain
unset because source-clock skew has not been disposed, qualified opening and
close coverage is incomplete, and a separately authorized read-only broker /
account source does not yet exist.

The 13:01 close-window capture is valid partial evidence: it confirms
paired-active subscriptions and sparse/no low-cohort Tick callbacks near close,
but ends at 13:16 and has 5/6 callback-group coverage. It does not observe the
13:30 market/session boundary. Therefore close-session evidence remains
insufficient for threshold selection or session-boundary semantics.

## Reviewer disposition

The morning continuous evidence is `QUALIFIED_EVIDENCE`; quote collector and
subscription lifecycle integrity are `PASSED`. The campaign **rejects** a
Tick-only executable-health model and **supports** a future model that combines
connection state, subscription state, BidAsk freshness, and BidAsk
timestamp/order checks. This is a qualitative calibration result, not a
BidAsk-duration threshold or an implementation authorization. See
`2026-08-20_morning_reviewer_disposition.md` for the complete evidence-status
ledger.

## Next collection gate

The one-time 13:00 close heartbeat has run and produced the partial
`quote_20260820T130116+0800.json` artifact. It does not justify an immediate
same-day retry outside the frozen session-window protocol. On a future completed
session, collect the unchanged frozen cohort across the documented close regime
including the 13:30 market/session transition; preserve the same API boundary,
collector, schema, quality gate, and threshold prohibition.
