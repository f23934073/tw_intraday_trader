# Morning continuous quote-evidence data-quality summary — 2026-08-20

## Outcome

Three non-overlapping 15-minute `continuous` captures passed the collector and
lifecycle quality gates. They are safe to retain as **quote-cadence evidence**.
They are not safe to use as a UI, RiskGate, or broker/account freshness
threshold. `FreshnessPolicyV1` remains `BLOCKING_EVIDENCE`.

## Dataset and grain

| Item | Definition |
|---|---|
| Grain | One received Tick or BidAsk callback observation |
| Cohort | Frozen prior-completed-session trade-value anchors: 2886 high, 6863 mid, 1530 low |
| Capture windows | 09:30–09:45, 09:54–10:09, and 10:14–10:29 Asia/Taipei |
| Source boundary | Shioaji Tick/BidAsk callbacks to a calibration in-memory buffer; `subscribe_trade=False` |
| Excluded APIs | Account, orders, CA, trade callbacks, all execution and Portfolio Phase 1 surfaces |

## Data-quality checks performed

| Check | Result |
|---|---|
| Artifact schema and SHA-256 integrity | Passed for all three artifacts |
| Paired `TIC` / `QUO` acknowledgement per symbol | Passed for all three artifacts |
| Observation connection/subscription state | Every row `CONNECTED/ACTIVE` |
| Required six `symbol × stream` groups | Present in every artifact |
| Callback error / missing market-event timestamp | Zero / zero in every artifact |
| Callback monotonic regression | Zero in every artifact |
| Composite `(symbol, stream_kind, callback_received_monotonic_ns)` duplicates | Zero in every artifact |
| Callback receipt outside capture range | Zero in every artifact |

## Observed cadence variation

| Capture | 2886 Tick / BidAsk | 6863 Tick / BidAsk | 1530 Tick / BidAsk |
|---|---:|---:|---:|
| 09:30 | 251 / 1,203 | 4 / 46 | 1 / 8 |
| 09:54 | 282 / 1,191 | 5 / 94 | 12 / 37 |
| 10:14 | 333 / 1,489 | 3 / 26 | 1 / 20 |

The high cohort is consistently active. The mid and low cohort rows remain
subscription-active but produce sparse Tick traffic. Observed maximum Tick gaps
are 124.389–210.941 seconds for mid; low has two one-Tick samples and the
remaining sample has a 488.363-second Tick gap. BidAsk activity remains present
in those intervals.

## Findings and analytical risk

1. **Tick silence is not an executable-data-health signal.**
   Confidence: high for this cohort and morning period. An `N`-millisecond
   Tick-only cutoff would falsely classify paired-active, BidAsk-updating
   subscriptions as bad data. Any future executable Quote health rule must
   combine connection state, subscription state, and BidAsk evidence.
2. **Inter-arrival distributions are volatile at the intended grain.**
   Confidence: high. The three samples differ substantially even within the
   same session day, so their pooled percentiles would disguise meaningful
   session/cohort variation rather than yield a justified stale cutoff.
3. **Source event time is not a validated transport clock.**
   Confidence: high. Negative event-to-callback values vary materially across
   samples. Read-only NTP checks establish only host-clock provenance and do
   not reconcile provider/exchange timestamps, so event-to-callback values must
   remain audit data rather than SLA inputs.
4. **No broker/account evidence exists.**
   Confidence: certain. These artifacts contain no positions, orders,
   accounting, or buying-power source timestamp. Deriving those four thresholds
   from quote cadence would be invalid.

## Required next evidence

1. Obtain qualified close-window evidence from the active one-time heartbeat.
2. Repeat opening and close captures across further completed sessions using the
   identical frozen cohort/quality gate.
3. Perform a separate source-clock disposition before interpreting transport
   delay.
4. Obtain explicitly authorized, read-only broker/account evidence with its own
   request, response, source-as-of, projection-update, status, and timeout
   timestamps.

Until those gates are reviewed, all eight thresholds remain unset and Phase 1
remains blocked.
