# Findings and Decisions

## 2026-08-19 — Freshness Calibration Evidence

### Requirements

- The approved baseline is immutable: P0-1 through P0-14, FeePolicyV1, and RoundingPolicyV1 remain `FROZEN`; `FreshnessPolicyV1` is the sole `BLOCKING_EVIDENCE`.
- Scope is evidence only. Do not start Portfolio Phase 1 or add Portfolio domain contracts.
- Calibrate eight distinct values: UI/Risk Tick and BidAsk freshness, plus broker positions, orders, accounting, and buying-power evidence freshness.
- Quote latency and broker/account freshness are separate datasets and analyses. Neither may be inferred from the other.
- Thresholds remain unset unless immutable captured evidence and data-quality review support them.

## 2026-08-22 — Frozen close-window execution

- The active heartbeat authorizes one bounded quote-only close capture for the
  pre-frozen cohort `2886:high`, `6863:mid`, `1530:low`. It explicitly excludes
  broker/account APIs, order APIs, CA, trade callbacks, all execution, and
  Portfolio Phase 1.
- This close observation must remain a separate immutable artifact and review.
  It may improve session-boundary evidence but cannot itself freeze a threshold
  or change `FreshnessPolicyV1=BLOCKING_EVIDENCE`.
- The host time at the requested window was `2026-08-22 13:01 +08:00 Sat`, a
  reviewed non-trading day. Five read-only NTP samples selected successfully
  (offsets approximately +0.405 to +0.407 ms), but that provenance cannot
  override the closed-date gate. The run is recorded as `NO_CAPTURE`; no SDK
  login, quote subscription, broker/account API, order API, CA, or Portfolio
  work occurred.

## 2026-08-22 — Broker/account read-only evidence authorization

- The owner has now explicitly authorized a strictly read-only broker/account
  evidence campaign and confirms that local Shioaji credentials are present.
  This changes only the source-access gate; it does not unblock Portfolio
  Phase 1 or permit a broker-order integration.
- The capture must record one distinct, redacted observation per `POSITIONS`,
  `ORDERS`, `ACCOUNTING`, and `BUYING_POWER` evidence kind. Required metadata
  remains request start, response receipt, provider `source_as_of_at` when
  actually supplied, local projection update, outcome, and a sanitized error
  class. It must not persist credentials, account identifiers, individual
  positions, balances, PnL, or order details.
- The local code search confirms the quote path is deliberately
  `subscribe_trade=False` and there is no dedicated broker-account evidence
  adapter yet. A capture must therefore be built as a separate calibration
  artifact, not by reaching through the existing quote provider or changing a
  product route.
- Fresh broker-order state normally requires a provider-side order refresh;
  that action-like call is excluded from this authorization. A local cached
  order list is not acceptable evidence for broker order freshness, so the
  initial campaign must record orders as an explicit constrained gap rather
  than fabricate an observation or infer a threshold.
- Local SDK inspection identifies Shioaji `1.7.2` and verifies the safe call
  signatures needed for the capture: `login(..., subscribe_trade=False)`,
  `list_accounts()`, `list_positions(...)`, `list_profit_loss(...)`, and
  `account_balance(...)`. Each read method exposes an optional callback, which
  the collector must leave unset; the collector will time the synchronous
  response path only. `update_status(...)` is intentionally excluded because
  it is an action-like order refresh, even though it has no order-placement
  signature.
- Existing configuration uses `SJ_SIMULATION=true` by default but permits a
  real-data source through `SJ_SIMULATION=false`. The new artifact must report
  that runtime environment as a non-sensitive metadata value and cannot claim
  simulation merely because the quote path did so in another run.
- A separate `broker_account_freshness_v1` artifact implementation now exists
  with exclusive creation and SHA-256 inspection. It records only endpoint
  shape/count, timing, explicit-as-of availability, guarded outcome, and
  capability disposition. Focused collector/quote/calendar tests passed
  (`22 passed in 0.09s`) without an SDK login or account API call.
- The broker/account campaign now has five reviewed daily windows (09:35,
  10:30, 11:30, 12:30, 13:20 Asia/Taipei) behind a calendar/time gate that
  runs before dotenv, SDK import, or provider construction. The Saturday
  schedule smoke produced a no-capture record with `provider_called=false`;
  all 24 focused collector/scheduler/quote/calendar tests passed.
- The corresponding launchd service is installed as
  `com.stevehuang.tw-intraday-trader.broker-account-freshness` and was verified
  to contain exactly those five calendar triggers. It is a separate process
  from the quote collector; `runs=0` immediately after installation confirms
  no broker/account observation has yet been collected.
- Revalidated the source boundary against current official Shioaji docs:
  `list_positions` and `list_profit_loss` are synchronous read APIs when no
  callback is supplied, while `account_balance` is a stock settlement-account
  balance endpoint with provider `date` described as query time. The latter is
  intentionally not promoted to buying-power authority. The official order
  docs require `update_status` before a cached `Trade` status is fresh, so the
  current `ORDERS` constrained gap is a source-supported consequence of the
  no-update-status/no-callback authorization, not a missing implementation.

### Initial decisions

| Decision | Rationale |
|----------|-----------|
| Use a standalone data-only calibration harness | Preserve the frozen Portfolio domain while making raw timing evidence inspectable and reproducible. |
| Keep broker/account calibration isolated from quote capture | The existing runtime is market-data-only, and the approved contract requires separate broker/account SLA evidence. |

### Discovery findings

- `market_data.models.RealtimeQuoteUpdate` already carries `exchange_timestamp` and `received_at`; the Shioaji provider emits normalized Tick and BidAsk updates with both timestamps.
- `simulation.service` keeps separate trade and book receive times, while existing quote execution uses a book-received timestamp. The calibration artifact should capture the raw callback receipt and a separate store-updated timestamp without changing the frozen Portfolio model.
- The repository already contains a data-only `market_data.shioaji_quote_capture` capture path, digest-validated capture artifacts, and `market_data.quote_qualification`; those are designed for Quote-versus-Tick/BidAsk parity, not for freezing FreshnessPolicyV1 thresholds.
- The current search found market-data streaming with `subscribe_trade=False`, but no implemented broker account read adapter or accounting polling capture path. Broker/account threshold evidence therefore requires a separately authorized read-only source or must remain unavailable; it cannot be inferred from the quote captures.
- The two existing parity artifacts cannot establish freshness thresholds: `8039` recorded zero callbacks in 20 seconds; `2330` recorded callbacks only for about 20 seconds. Neither has `store_updated_at`, connection-state transitions, liquidity/session labels, or independent broker/account observations. They remain callback-path evidence only.
- The `2330` artifact contains callback receipts earlier than the supplied market event time for some book updates. Calibration must preserve and count such clock-skew observations; it must never clip them into valid non-negative latency.
- Offline artifact validation on 2026-08-19 confirmed the insufficiency: the
  20.772745-second `8039` capture has zero callbacks/observations; the
  20.714851-second `2330` capture has 116 retained observations, 96 with
  negative event-to-receipt latency. These samples are callback-path evidence,
  not threshold-quality data.
- Added `market_data.freshness_calibration` and
  `scripts/capture_quote_freshness.py`: a Tick/BidAsk-only, bounded capture
  writes exclusive-create JSON evidence with market/callback/store timestamps,
  monotonic timing, reviewer-supplied cohort labels, lifecycle state, SHA-256
  inspection, and no threshold-selection code. The declared store boundary is
  only the calibration buffer, not a future Portfolio projection.
- A rendered technical evidence report has been validated with a partial
  snapshot. It records all eight values as unset, preserves the separate
  broker/account evidence gap, and prohibits a quote-to-account SLA inference.

### Preparation scope (in progress)

- Cohort labels must be selected and frozen before a capture starts, but no
  label will be assigned from reputation or the two insufficient samples. The
  capture records the reviewer-supplied label as provenance rather than treating
  it as a market-data fact.
- Non-sensitive preflight may verify local runtime/CLI, host timezone, artifact
  creation semantics, and credential *presence* only. It must not emit secret
  values, call order/account endpoints, or use an empty after-hours capture as
  calibration evidence.
- Local preflight on 2026-08-19 passed without reading secret values: the
  optional Shioaji SDK is installed, both required credential categories are
  configured, and the host UTC offset is `+08:00`, matching the explicit
  `Asia/Taipei` capture timezone. This verifies readiness, not clock accuracy
  or market-data quality.
- Current provider code confirms Tick/BidAsk-only streaming with
  `subscribe_trade=False` and a 100-symbol paired-subscription cap. The
  repository's separate momentum stream also registers SDK lifecycle events;
  the calibration collector should preserve those lifecycle transitions rather
  than fabricate connection health from callback arrival alone.
- The reusable lifecycle model distinguishes disconnect, reconnecting,
  reconnected, subscription acknowledgements, and subscription failures. The
  calibration artifact needs raw SDK lifecycle provenance plus its conservative
  mapped connection/subscription state so an empty callback interval is not
  misclassified as market-data staleness.
- Existing tests provide concrete lifecycle evidence: SDK event `(500, 12)` is
  treated as reconnecting, `(200, 13)` as reconnected, and paired Tick/BidAsk
  acknowledgements use event code `16`. The calibration collector can record
  these state changes without adding a Portfolio concern.
- The capture currently marks subscriptions active immediately after request;
  this is not valid acknowledgement evidence. The narrow correction is to keep
  `PENDING` until both `TIC` and `QUO` acknowledgements for a configured symbol
  are received, then persist the raw lifecycle inputs alongside the mapped
  state.
- Preparation artifacts are now ready: the cohort manifest template freezes
  reviewer-supplied labels before collection; the preflight/review checklist
  records required integrity, clock, lifecycle, and segmentation checks; and
  the broker/account intake defines read-only authorization and timing metadata
  without creating an adapter.

### Live discovery capture (2026-08-20 09:05 Asia/Taipei)

- A 120-second data-only capture for `2330` was deliberately labelled
  `discovery` / `continuous_discovery`; it is not evidence that the symbol
  belongs to any approved liquidity tier. The immutable artifact is
  `research/captures/freshness_quote/quote_20260820T090534+0800.json`
  (SHA-256 `17dd2ead6a7ad17b2c389f4e263104c756096c5dd4131c45a7a6143f438b5e97`,
  263,563 bytes, schema `freshness_calibration_quote_v1`).
- Digest inspection passed. It holds 494 observations: 474 BidAsk and 20 Tick,
  with no missing stream kind, no missing market event timestamp, no callback
  monotonic regression, and no captured callback error.
- Lifecycle provenance confirms a successful paired acknowledgement: `TIC` and
  `QUO` were both acknowledged for `TSE/2330`, after which all observations
  record `CONNECTED` / `ACTIVE`. Cleanup then recorded an explicit
  `DISCONNECTED` / `INACTIVE` transition.
- The source event timestamp cannot yet be used as a transport-latency clock:
  353 of 474 BidAsk and all 20 Tick observations have a negative
  event-to-callback value. Raw values are retained for audit; they are not
  clamped, discarded, or turned into a freshness threshold.
- A post-capture, read-only NTP sample against `time.apple.com` selected an
  offset of `+58.825 ms +/- 53.094 ms`. It establishes limited host-clock
  provenance without changing the system clock. It does not establish the
  exchange/provider event-clock offset, so it cannot correct the negative raw
  values or qualify event-to-callback latency as an SLA metric.
- The capture establishes that the callback-to-store measurement seam works
  during the continuous session. It remains insufficient for every threshold:
  it has one discovery-labelled symbol, one session window, no independently
  verified clock relation, and no broker/account read evidence. Consequently
  `FreshnessPolicyV1` remains `BLOCKING_EVIDENCE` and no candidate is emitted.

### Qualified cohort selection (in progress)

- The user authorized continuation during the regular session. This permits
  collection and evidence provenance work only; it does not authorize Portfolio
  Phase 1, broker account reads, or execution APIs.
- The official TWSE historical-data page documents a daily individual-security
  trading value/volume dataset available from 2010-01-04. The selection path is
  therefore to snapshot the prior completed-session dataset, record its source
  date/digest and a predeclared percentile rule, then freeze the resulting
  high/mid/low symbols in the cohort manifest before any qualified capture.
- This replaces reputation-based labels with auditable completed-session
  evidence. It must remain separate from current-session callback counts so
  selection cannot be altered after viewing capture outcomes.
- Downloaded the official TWSE `MI_INDEX` response for 2026-08-19 into an
  ephemeral inspection file. It reports `stat=OK`, contains a 1,377-row
  `Daily Quotes(All(no Warrant & CBBC & OCBBC))` table with explicit
  `Security Code`, `Trade Volume`, `Transaction`, and `Trade Value` fields,
  and has SHA-256
  `6e4105775abb4a5517706a47ee803e42f0f6063a9aea5e894a9c089a158e0c19`.
- The first generic `data` lookup was empty because this response is a
  multi-table schema rather than a single-table schema. The selection parser
  will target the named Daily Quotes table and validate its headers before
  calculating ranks; it will not silently use an index or market-summary table.
- The verified selection universe is now fixed as: four-digit numeric security
  codes whose first digit is `1`–`9`, with positive 2026-08-19 `Trade Value`.
  It yields 1,086 eligible rows and excludes 291 other rows from the 1,377-row
  Daily Quotes table. The completed-session `Trade Value` nearest-rank anchors
  are p10 `1530` (NT$842,314), p50 `6863` (NT$18,430,437), and p90 `2886`
  (NT$1,184,984,848).
- These anchors are selected solely from the downloaded completed-session
  snapshot and before any qualified capture outcome is examined. They will be
  persisted as `low`, `mid`, and `high` respectively in the cohort manifest;
  this is an observation-cohort classification, not a statement about a stale
  threshold, tradeability, or Portfolio risk policy.
- Frozen `cohort_manifest_2026-08-20_twse_2026-08-19.json` at
  2026-08-20T09:14:51+08:00 with `2886:high`, `6863:mid`, and `1530:low`;
  its source digest matched the inspected TWSE snapshot. The operational
  collection windows are opening 09:00–09:30, continuous 09:30–13:00, and
  close 13:00–13:30 Asia/Taipei. They segment evidence only, not a stale
  threshold or exchange-rule claim.
- A read-only NTP preflight immediately before the first qualified capture
  selected `+54.431 ms +/- 49.857 ms` from `time.apple.com`. It is host-clock
  provenance only and does not make source event timestamps a latency SLA.
- The frozen 10-minute opening capture started at 09:16:16 +08:00 and wrote
  `quote_20260820T091616+0800.json` with 1,048 observations and all six
  `symbol × {Tick,BidAsk}` groups present. Initial counts are: high 2886
  (816 BidAsk, 180 Tick), mid 6863 (24 BidAsk, 2 Tick), and low 1530
  (23 BidAsk, 3 Tick). Integrity/lifecycle inspection remains pending.
- Integrity inspection passed (SHA-256
  `816e35617c3efa3ff555f91ae24cb4ba242986ccbc8bedac100cd875708ac572`,
  539,087 bytes) and each symbol received `TIC` plus `QUO`. However every
  persisted observation is `CONNECTED/PENDING`, so this artifact is **not
  qualified evidence** under the existing fail-closed rule.
- Root cause is contained in the calibration collector: after one symbol became
  `ACTIVE`, the aggregate state was still `PENDING` while other symbols awaited
  acknowledgement; the lifecycle transition helper then broadcast that aggregate
  `PENDING` back to every per-symbol state, erasing the completed acknowledgement.
  This is an instrumentation bug, not a market-data failure. Preserve the raw
  artifact, repair the state propagation with a multi-symbol regression test,
  then recapture using the unchanged frozen manifest.
- The isolated repair leaves global lifecycle transitions intact but prevents an
  aggregate `PENDING` transition from rewriting per-symbol states. Reconnecting
  now explicitly resets both acknowledgement parts and per-symbol states to
  `UNKNOWN`. The multi-symbol regression passes: a fully acknowledged symbol
  remains `ACTIVE` while another symbol is still `PENDING`, then both become
  `ACTIVE` after their own paired acknowledgement.
- The 70-second opening recapture
  `quote_20260820T092834+0800.json` passed schema/digest inspection
  (SHA-256 `65edf0a391207fa69953e9440fb1e14a3fc4baa306a61f70764063b8241c110b`,
  63,606 bytes). Its three paired acknowledgements are present and every
  observation is `CONNECTED/ACTIVE`: high 2886 has 95 BidAsk plus 20 Tick,
  and mid 6863 has 2 BidAsk. It is valid partial evidence, but **not complete
  opening coverage** because mid Tick and both low 1530 stream groups had no
  callback in the 70-second interval. Missing market activity is a coverage
  result, never synthetic stale evidence.
- The 15-minute continuous capture
  `quote_20260820T093046+0800.json` is the first complete qualified cohort
  artifact: schema/digest passed (SHA-256
  `7451e75b3a3fe26e750844e9e902a7aeb5e62ffe84d4276bacc7e4f24ddccad1`,
  779,582 bytes), every configured `symbol × {Tick,BidAsk}` group has a
  callback, all 1,513 rows are `CONNECTED/ACTIVE`, all three symbols have
  `TIC` plus `QUO`, and no callback error or monotonic regression occurred.
- Its observed cadence validates a key contract premise without selecting a
  threshold: high 2886 has 1,203 BidAsk / 251 Tick updates (maximum gap about
  8.025 seconds); mid 6863 has 46 / 4 (about 166.857 / 124.389 seconds); low
  1530 has 8 / 1 (about 164.827 seconds / no Tick gap). Thus a quiet Tick can
  coexist with an active, paired-acknowledged subscription and must not alone
  be treated as an executable-data failure.
- Source-clock skew remains material in every cohort/stream, and the measured
  callback-to-store timing is only the calibration in-memory buffer. One date,
  continuous window coverage alone, uncalibrated source event time, and the
  independent broker/account evidence gap keep all eight thresholds unset.
- A one-time task heartbeat is active for the frozen 13:00–13:30 close window.
  Its work scope is limited to the same immutable quote cohort and artifact
  review; scheduling does not authorize broker/account reads, change the cohort,
  select a threshold, or begin Portfolio Phase 1.
- Cross-artifact quality profiling confirms the two rejected/partial artifacts
  remain segregated: all four files have no duplicate
  `(symbol, stream_kind, callback_received_monotonic_ns)` keys, no receipt
  outside the respective capture range, and no callback error. Only
  `quote_20260820T093046+0800.json` has complete six-group, all-ACTIVE qualified
  cohort coverage; the durable campaign ledger records each disposition.
- A second independent continuous capture began at approximately 09:55 +08:00
  under the unchanged manifest after a read-only NTP preflight (selected host
  offset about `+47.647 ms +/- 48.080 ms`). The capture runner returned its
  control channel before its child process completed; two later retry attempts
  were therefore stopped before completion, while the earliest process remains
  the sole retained sample. This is collection-process provenance only, not a
  data-quality result or threshold candidate.
- The retained repeat completed as
  `quote_20260820T095444+0800.json` (SHA-256
  `7c937d32d3fc48f46307b880d2feda58e3f1d5449b020f2da1ad12fdd339638c`,
  834,811 bytes). It has 1,621 all-`CONNECTED/ACTIVE` observations, paired
  acknowledgement for every cohort symbol, complete six-group coverage, and
  zero callback errors, monotonic regressions, duplicate composite callback
  keys, or out-of-range receipts.
- The independent repeat strengthens the non-threshold finding: low 1530's
  longest Tick gap is 488.363 seconds and mid 6863's is 210.941 seconds despite
  continued paired-active subscriptions and BidAsk callbacks. Neither this nor
  the earlier continuous sample makes Tick silence a valid stale/executable
  failure signal. Source clock skew persists (879/1,621 negative raw
  event-to-callback measurements), so all quote values remain unset; broker /
  account evidence remains a separate, uncollected blocker.
- The third non-overlapping continuous artifact
  `quote_20260820T101439+0800.json` is also qualified (SHA-256
  `181a59b0d9fbd378a70b638f659b0d854a8e5e74b29dd6c2cceeedb321accd6f`,
  963,235 bytes, 1,872 observations): paired acknowledgement, six-group
  coverage, all ACTIVE rows, zero callback errors, zero monotonic regressions,
  zero duplicate composite keys, and zero receipts outside its capture range.
  Its low/mid Tick counts are only 1/3 despite active BidAsk callbacks (20/26).
- Across the three complete continuous samples, mid Tick gaps span
  124.389–210.941 seconds; low has two single-Tick samples and one 488.363-second
  observed Tick gap. The third artifact's lower negative raw event-to-callback
  count (89/1,872) is variation, not proof of clock alignment. It reinforces the
  separate requirements for calendar/session coverage, source-clock disposition,
  and a broker/account evidence source; it does not change any threshold status.
- A pre-close cross-artifact integrity profile now covers all six immutable
  files: 6,665 observations, zero within- or cross-artifact duplicate composite
  callback keys, zero callback receipts outside their capture ranges, and zero
  callback errors. The known 09:16 `CONNECTED/PENDING` artifact remains the
  sole lifecycle-rejected artifact; it is retained but excluded. These are
  collection-integrity checks only and do not resolve source-clock, session,
  threshold, or broker/account evidence gates.
- Reviewer disposition: the morning continuous campaign is formally qualified
  evidence and can freeze the qualitative invariant that executable quote health
  is **not** Tick freshness alone. It rejects `no Tick for N -> BOOK_STALE` and
  supports a future connection/subscription-plus-BidAsk health model. This is
  not a duration threshold, RiskGate implementation, or Phase 1 authorization.
  The full evidence-status ledger is preserved in
  `research/freshness_calibration/reviews/2026-08-20_morning_reviewer_disposition.md`.
- Execution order is now explicitly frozen: today's close quote evidence, then
  cross-session quote evidence, then source-clock disposition, then a separate
  broker/account campaign only with explicit read-only authorization. No
  migration, Portfolio core, RiskGate freshness code, provisional threshold, or
  broker/account endpoint call may occur before `FreshnessPolicyV1` is frozen.
- The scheduled 13:01 close capture completed as
  `quote_20260820T130116+0800.json` (SHA-256
  `1994292cc3c9868952567283f9dc7b02a8ada8dca03a05e7c131872c8e3aed70`,
  2,092 all-ACTIVE observations). Its paired acknowledgements, schema/digest,
  duplicate/range, callback-error, and monotonicity checks pass. It is partial
  close evidence only: low 1530 has eight BidAsk callbacks but zero Tick
  callbacks, and the 13:01–13:16 interval does not reach the 13:30
  market/session boundary. The result supports the existing Tick-only model
  rejection but leaves close/session-boundary evidence insufficient.
- The 2026-08-21 cross-session close artifact
  `quote_20260821T130144+0800.json` (SHA-256
  `d00da28a50d2df53fa120c43a1aebf91cfa1baecca91705f590067898977469e`)
  passed schema/digest, paired acknowledgement, all-ACTIVE, error, monotonic,
  duplicate, and receipt-range checks for 1,497 observations. It repeats the
  5/6 callback coverage: 1530 has one BidAsk callback and zero Tick callbacks,
  while high/mid have both streams. This is partial cross-session early-close
  evidence that further rejects Tick-only executable health; it does not
  establish a BidAsk timeout or observe the 13:30 boundary.


## 2026-08-19 — Basic strategy expansion implementation

- The user has now explicitly authorized implementation of `architecture/basic_strategy_expansion_implementation_plan.md`.
- Preserve the current unrelated worktree changes in `backtest/historical_download.py`, `market_data/provider.py`, download scripts/tests, README, and separate `.planning/` sessions.
- Apply the approved sequence: capability preflight first, then pure indicators/features, then five experimental strategies, Dashboard defaults, and verification.
- Use the minimum new abstractions needed by the five strategies; do not build a strategy DSL, optimizer, broker adapter, or live-money path.

## 2026-08-19 — Basic strategy expansion planning

- The requested deliverable is a reviewable implementation plan, not product-code implementation.
- The proposed batch is Opening Range Breakout entry, EMA crossover entry, RSI/Bollinger mean-reversion entry, ATR stop exit, and time stop exit.
- Preserve the repository boundary: strategies produce historical decisions or future intents; they do not call Shioaji order APIs or authorize real-money execution.
- External research is supporting context only. Published ORB evidence for TAIEX futures does not establish profitability for Taiwan cash equities; all imported parameters must remain hypotheses until Taiwan-stock OOS and walk-forward evidence passes.
- Public indicator definitions can standardize calculations, but indicator availability is not evidence that a trading rule is profitable.
- The current executable backtest registry contains two entries and three exits. New catalog rows are not executable unless their immutable definition digest and server-side execution binding exactly match a registered implementation.
- `HistoricalBar` already supplies timezone-aware OHLCV plus optional amount, so the proposed indicators do not require a new raw market-data source.
- `StrategyContext` currently exposes only the current bar, previous close, session open/high, cumulative volume/VWAP, bar count, last-bar flag, and entry price. ORB needs a frozen opening-range state; EMA/RSI/Bollinger/ATR need rolling bar history or precomputed features; ATR trailing exits and time stops also need position lifecycle state.
- The engine is deterministic, long-only, one-entry-per-symbol-per-day, and executes decisions on the next bar. New strategies must preserve those semantics and must not trigger from an unfinished or future bar.
- The worktree already contains unrelated modified product and planning files from concurrent work. Phase 9 will avoid those files and create only a standalone architecture plan plus updates to the root planning records.
- The existing `features/` engine is Tick/BidAsk-, DataHealth-, and event-ID-specific. Its semantics should not be imported directly into historical Kbar evaluation. The plan should introduce a small pure Kbar indicator layer first and require parity fixtures before any future live reuse.
- Strategy parameters are immutable catalog metadata, and a backtest run currently selects strategy IDs rather than arbitrary per-run parameter overrides. The first slice should keep fixed research defaults per strategy version; parameter changes create a new version instead of adding a browser parameter tuner.
- The strategy and backtest UI already render definitions and executable ENTRY/EXIT choices from the APIs. Once registry/catalog matching is correct, the new strategies should appear without a new endpoint or a new strategy-specific form.
- ATR exits require an explicit as-of rule: ATR used for an entry or same-bar protective exit must be based only on bars completed before the entry fill bar. Otherwise the fill bar's future high/low would leak into the stop distance.
- The prior architecture plan already requires as-of-only context, next-bar fills, deterministic aggregation, immutable definitions, and no-look-ahead tests. Phase 9 should extend those contracts rather than introduce a second strategy framework.
- Dataset manifests currently expose only generic `OHLCV`. Their profile is inferred from total observations per date, not cadence per symbol/session, so a multi-symbol daily dataset can be misclassified as one-minute data. ORB and intraday indicators must not rely on this heuristic.
- `create_run()` currently validates strategy side/registration but does not enforce each strategy's `required_capabilities` against the selected dataset. Capability preflight is a prerequisite, not an optional polish item.
- The plan should introduce explicit derived dataset capabilities such as `KBAR_INTRADAY`, `BAR_INTERVAL_SECONDS=60|300`, and `SESSION_BOUNDARIES`, computed from per-symbol/session intervals and coverage. Daily or irregular data must fail closed for ORB, time-stop, and intraday rolling strategies.
- The engine already stores `entry_event_index` internally and prevents exit evaluation on the entry event. It does not expose holding bars, entry time, peak price, or ATR-at-entry to strategies; position feature state can be extended without altering persistent database schema because run results remain JSON payloads.
- The current backtest application loads the full dataset into memory. This plan should keep the first strategy slice compatible with that engine and avoid bundling an unrelated streaming-engine rewrite, while documenting bounded rolling buffers so the strategy layer does not add unbounded per-symbol history.
- Source review: the NTU/IEEE TORB paper uses one-minute intraday index-futures data and includes TAIEX, so it supports ORB as a research candidate but not direct transfer of performance claims to Taiwan cash equities: https://scholars.lib.ntu.edu.tw/entities/publication/d69ecf33-892c-4f8a-9a88-2af1bcc4efcd
- Source review: the Santa Fe Institute record identifies moving-average and trading-range-break rules as simple, long-studied technical rules, but its Dow Jones sample is not Taiwan intraday evidence: https://web-prod.santafe.edu/research/results/working-papers/simple-technical-trading-rules-and-the-stochastic-
- Source review: TA-Lib documents EMA/BBANDS, RSI, and ATR with explicit lookback/unstable-period behavior. The implementation plan must freeze warm-up and seeding semantics and return `INSUFFICIENT_DATA`, not silently substitute zeros: https://ta-lib.github.io/ta-lib-python/func_groups/overlap_studies.html ; https://ta-lib.github.io/ta-lib-python/func_groups/momentum_indicators.html ; https://ta-lib.github.io/ta-lib-python/func_groups/volatility_indicators.html
- Source review: TWSE currently documents regular trading as 09:00–13:30 and distinguishes general stock sell tax from the reduced eligible day-trading rate. Strategy comparisons must keep session boundaries and cost scenarios explicit: https://wwwc.twse.com.tw/en/about/company/guide.html
- Runtime dependency decision: do not add TA-Lib merely to implement five functions. Use small pure Decimal-based calculations with hand-worked/golden fixtures; optionally compare results to TA-Lib in a non-required qualification test, but freeze this project's own formula/version contract.
- Final plan decision: implementation order is capability preflight -> pure rolling features/engine v2 -> ORB -> EMA and RSI/Bollinger -> ATR and Time Stop -> research qualification.
- Final plan decision: new experimental strategies must not become default-selected; legacy ACTIVE entry/exit defaults remain the baseline until the user explicitly chooses a challenger.
- Final plan decision: no SQL table is required for the first slice; strategy definitions and dataset capability evolution fit existing JSON contracts, while old manifests remain immutable and fail closed for the new strategies.

## Requirements

- Review the attached five-stage development proposal for adjustments and optimizations.
- Compare it with the actual repository, especially existing `MarketDataStore`, `CandidateEngine`, `BuyScoreEngine`, and adjacent components.
- Produce an implementation plan only; do not implement application changes.
- Make the plan concrete enough for user review before any implementation begins.
- Add a web-based manual Shioaji Simulation order flow.
- Add a place in the web UI to view simulated purchased stocks and their position information.
- Preserve a clear path for later program-generated orders to use the same backend flow.
- The user has now authorized implementation.
- The first implementation slice must provide local paper simulation only; it must not claim to be an authenticated Shioaji Simulation session or submit any broker order.
- The user has now explicitly requested Shioaji Tick/BidAsk subscriptions for realtime simulation quote updates.
- This authorization changes the market-data path only; local paper orders remain in-process and must not call Shioaji order APIs.

## Research Findings

- The worktree began clean on branch `main`, tracking `origin/main`.
- No repository-level `AGENTS.md`, `RULES.md`, or pre-existing planning files were discovered by the initial scoped scan.
- Relevant prior project guidance requires data-only/research boundaries, fail-closed market-data handling, explicit stream ordering, queue-draining shutdown, and no real-money path. These are context to verify against this repository, not substitutes for current evidence.
- The supplied proposal has 679 lines and describes Phase 0 architecture cleanup followed by Historical Backtest, Replay Trading, Shioaji Simulation, Small Live Trading, and Production Trading.
- Its strongest architectural invariant is that strategy code emits an `OrderRequest` and never calls Shioaji directly; `ReplayBroker`, `ShioajiSimulationBroker`, and `ShioajiLiveBroker` sit behind a common Broker boundary.
- The proposal correctly calls out asynchronous order/deal callbacks and a real order lifecycle rather than equating submission with fill.
- The proposal currently treats live-money phases as planned progression. That conflicts with the inherited project boundary (`Real Money = prohibited`) unless the user separately changes scope; the final plan must not silently authorize live-order implementation.
- The current repository is compact and contains market data, candidate selection, scoring, position, dashboard, configuration, application entrypoint, and focused tests. No broker/execution package appears in the file inventory.
- A pre-existing isolated `.planning/2026-08-17-intraday-visual-dashboard` directory exists; the new root planning files are specific to this review and did not overwrite it.
- The proposal's closing sequence begins with Broker models/interface, then ReplayBroker, OrderManager, Shioaji simulation callbacks/synchronization, decision/risk engines, automated simulation, journal, and only later live comparison/production.
- Risk controls are placed only in the live-safety section of the proposal. They should instead be invariant policy enforced for every broker mode so Replay and Simulation exercise the same admission decisions as any future execution mode.
- The proposal's stated milestone is “Execution Layer v1,” with success defined as switching the same BUY signal between Replay and Shioaji Simulation without changing Candidate, Scoring, or Position logic.
- The repository README documents a decision-support MVP: users decide whether to buy; the dashboard is read-only; current positions are inserted manually for demonstration. This is materially earlier than an execution system.
- Existing architecture guidance explicitly says the first version favors simplicity and should not pre-create execution/backtest/event-system abstractions. Therefore the final plan should add only the minimum seams proven necessary for Replay and paper execution, rather than importing a production-trading architecture wholesale.
- Existing repository principles already isolate Shioaji behind `MarketDataProvider`, distinguish Candidate from buy signal, require continuous position monitoring, preserve score breakdowns, and centralize thresholds in settings.
- `run_scan()` is a one-shot orchestration function: it creates a new in-memory `MarketDataStore`, candidate/scoring engines, exit rules, and `PositionManager` for every scan, then loads market snapshots and returns a presentation DTO. It is not yet a persistent session/runtime loop.
- `MarketDataStore` stores only the latest `StockData` per symbol and unconditionally overwrites existing data; its own docstring marks stale-timestamp rejection as future work. Replay/event-driven execution cannot safely depend on it until ordering and session-time semantics are defined.
- The current `PositionManager` is fed a hard-coded demonstration position in `app.py`; current Position objects are user-entered holdings, not broker-authoritative positions derived from fills.
- The dashboard intentionally calls the same one-shot `run_scan()` and marks provider mode as `snapshot`, `streaming=False`; it performs no trading operation.
- The existing code has a useful pure boundary: Candidate and scoring operate on internal `StockData`, while dashboard serialization consumes `ScanResult`. Execution work should preserve these pure computations and move long-lived session orchestration out of `run_scan()` rather than turning the dashboard path into a trading loop.
- `MarketDataProvider` is pull-oriented (`get_stock`, `get_market_stocks`, optional historical Kbars). It has no event/replay clock, subscription lifecycle, disconnect signal, or backpressure contract; adding Replay by only naming a new provider would not define deterministic event-time behavior.
- `StockData.timestamp` is a single timestamp. Mock/Shioaji snapshots currently populate it with naive local `datetime.now()`, while Kbars are timezone-aware Asia/Taipei. Execution/replay needs an explicit, timezone-aware event-time/received-time contract before freshness or latency can be trusted.
- `ShioajiProvider` owns login and a private SDK client and can select `simulation=False` via `SJ_SIMULATION`. Broker integration should not reach through this private provider or duplicate login implicitly; a dedicated session/gateway composition boundary is needed, with fail-closed mode configuration.
- Snapshot conversion uses local receipt time rather than an exchange timestamp and skips per-symbol conversion exceptions during full-market scans. This may be acceptable for a UI snapshot but is insufficient as an execution-quality feed without explicit data-health reporting.
- Current market snapshots do not include bid/ask, lot type, tick size, tradable status, or exchange sequence. Consequently a credible limit/market fill model, spread gate, stale-data gate, and order normalization cannot yet be specified from `StockData` alone.
- The repository's own documented evolution order is `Strategy Idea -> Backtest -> Statistical Validation -> Shadow Trading -> Approved -> Realtime Strategy`; it explicitly names Shadow Trading and Data Health/Risk Gate as future seams. This is safer and more consistent with project scope than jumping from Replay directly to broker-simulated automated orders.
- Candidate, scoring, and exit logic are currently deterministic/pure over `StockData`, which is valuable for Replay parity. However outputs lack decision provenance such as strategy/rule version, decision ID, evaluated-at timestamp, market-data timestamp, and input snapshot identity; those must exist before a journal can be auditable.
- Existing tests focus on pure rules, latest-value storage, provider mapping/batching, historical Kbar mapping, and dashboard serialization. There are no tests for session orchestration, stale/out-of-order data, deterministic Replay, repeated decision suppression, order lifecycle, recovery/reconciliation, or persistence.
- Current store tests intentionally use identical timestamps and assert last-call-wins overwrite behavior. Tightening event ordering will need explicit compatibility decisions and new tests rather than silently changing this contract.
- Git history contains only the initial MVP and dashboard feature commits, reinforcing that the next step should be a narrow research/execution-simulation foundation rather than a production brokerage stack.
- Current official Shioaji documentation confirms Simulation supports subscriptions, historical queries, order/update/cancel/status/list-trades, and position/P&L queries, but simulated order placement excludes emerging stocks and odd lots.
- Official order/deal documentation confirms callbacks report both order and deal events with exchange identifiers/timestamps. Therefore submission return values and callbacks must be normalized as idempotent events; callbacks alone are not a durable source of truth after restart.
- Official current limits confirm: quote/history query calls share 50 requests per 10 seconds, order-related calls share 250 requests per 10 seconds, subscriptions are capped at 200, logins create connections, and the provider explicitly warns not to poll snapshots/ticks/kbars as a live feed.
- The current full-market `get_market_stocks()` uses batched snapshots. It can remain an explicit/manual snapshot scan, but an automated intraday runtime must use streaming subscriptions and a bounded subscription-selection policy rather than loop this method.
- Because the 200-subscription cap is far below the full TWSE/TPEX universe, the implementation plan needs a two-tier universe flow: coarse discovery/refresh at an allowed cadence, then Tick/BidAsk subscriptions for bounded candidates and all open/pending positions.
- Shioaji's public SDK evolves frequently, while this project currently allows any `shioaji>=1.7,<2`. Integration work should qualify a narrower tested version/range (without assuming the latest installed version) and record the actual SDK version in journal/session metadata.
- `pyproject.toml` package discovery currently enumerates only existing packages. Any approved `replay`, `decision`, `execution`, or `journal` package must be added deliberately so editable installs and built wheels do not omit it.
- The existing configuration has only rule/display/provider switches. Introducing execution-like modes requires typed, fail-closed configuration with no `live` value in the current scope; a loose `BROKER_MODE` string and shared `SJ_SIMULATION` toggle would be too easy to misconfigure.
- The active virtual environment currently has Shioaji `1.7.2`; this is useful local evidence, not a substitute for an explicit supported-version policy.
- Official stock-order docs require CA activation before placing orders, require an explicit `order_lot`, and show that `place_order` can return `PendingSubmit` before a later status refresh/event. The plan must model pending submission and must never infer acceptance/fill from a successful function return.
- The proposal's generic `qty` is unsafe because internal share quantity, order-lot type, and broker quantity must not be conflated. Use an unambiguous internal unit and let a tested broker adapter perform the conversion; include boundary fixtures for common-lot and unsupported odd-lot Simulation requests.
- The current 64-test suite passes in 0.10 seconds. This is the regression baseline for future approved changes.
- The prior dashboard planning record confirms the dashboard was deliberately designed as a manual-refresh, read-only snapshot surface and explicitly deferred streaming/replay/order endpoints. The execution plan must preserve that boundary and must not reuse dashboard refresh as the runtime market-data loop.
- The new user requirement intentionally changes the future dashboard boundary: after the manual Simulation gate, the browser may submit simulation-only order commands and read order/portfolio projections. This does not authorize a live-money route.
- The browser must not construct Shioaji SDK objects or call the SDK. Manual web orders and future strategy orders should be separate command origins feeding the same backend `OrderApplicationService`.
- The purchased-stock view must use `PortfolioProjection` plus reconciliation metadata rather than the current hard-coded demonstration `PositionManager` entry.
- The current dashboard already has a top-right `持倉` button and an accessible slide-in position drawer. The plan should evolve this existing surface into a simulation portfolio view instead of adding a redundant page.
- Current position cards already show symbol/name, quantity, entry/current price, unrealized PnL, stop/take-profit markers, and exit status. Simulation positions need to add source/mode, market value, average fill price, pending quantity, realized PnL, last broker reconciliation time, and sync/data-health state.
- `dashboard/server.py` currently exposes only snapshot refresh and Candidate history; `DashboardService` refreshes through `run_scan()`, whose sole position is a hard-coded demonstration holding. Simulation views must read OrderManager/PortfolioProjection repositories rather than call `run_scan()` or query Shioaji on every browser request.
- The current page explicitly says it is a one-shot snapshot without order functionality. A future Simulation control state must be unmistakable: show a persistent `SIMULATION` badge and keep the order form disabled/hidden unless the backend reports a healthy `SHIOAJI_SIMULATION` session.
- There is no account, certificate-authority, or authenticated Shioaji session evidence in this checkout. The safe first deliverable is therefore a session-local `LOCAL_PAPER_SIMULATION` implementation, visibly distinguished from Shioaji Simulation and with no SDK order calls.
- The local simulation can preserve the future command seam by treating the browser as one command origin and keeping order validation, idempotency, position updates, and order projection in one backend service.
- `DashboardService` and its tests expose a stable read-only scan snapshot whose `positions` still contain the demo holding from `app.py`. The local simulator must provide a separate `simulation` projection instead of changing the existing scan-result contract in this first slice.
- `dashboard/server.py` already keeps a process-lifetime `DashboardService` instance. A process-lifetime local simulation service can use the same `MarketDataProvider` instance without browser reads creating a provider or Shioaji client per request.
- The dashboard is a single static page with an existing accessible holdings drawer and explicit-refresh button. The smallest UI change is to reuse the holdings drawer for the simulation positions and add a compact order drawer/blotter rather than create a new route or frontend build system.
- The installed FastAPI test client cannot be imported because its environment expects `httpx2`, which is not installed. This slice will avoid adding an unrelated runtime/testing dependency and cover the API contract through the service tests plus direct endpoint construction only where needed.
- Calling the dashboard route with the ambient provider setting initialized `ShioajiProvider`; its installed native dependency segfaulted under the active Python 3.13 interpreter. Focused API tests must inject `MockProvider` and must not exercise the external SDK. This is an environment/provider compatibility issue outside the local paper-simulation path.
- The running local dashboard was visually and interactively verified with `MockProvider`: the simulation badge is visible, the candidate action opens an accessible order drawer, and its 3231/BUY/1-lot/105.50 defaults are correctly populated. The browser test did not submit a persistent test order; command behaviour is covered by the service/API tests.
- The final regression suite has 71 passing tests, and the static dashboard script passes a standalone JavaScript syntax parse. The local simulator contains no Shioaji import or order call.
- The current simulation stores only snapshot `StockData`; position reads never call the provider, and `refresh_quotes()` runs only behind the explicit full-dashboard refresh.
- Current local fills compare limit price with last trade (`StockData.price`). Tick/BidAsk integration needs separate best bid/ask fields so BUY eligibility/fill uses ask and SELL eligibility/fill uses bid.
- `StockData` intentionally models a broad latest snapshot and currently has no bid/ask fields. A separate small streaming-quote model is safer than changing every Candidate/scoring fixture and snapshot serializer.
- `SimulationService` is already guarded by an `RLock`, so normalized quote callbacks can update its quote projection safely; Shioaji-specific objects should stay in `market_data/provider.py`.
- The installed Shioaji 1.7.2 package includes `_core.pyi`; implementation can be checked against its local callback and subscription signatures without importing the native extension in tests.
- Current official Shioaji stock-streaming docs show `set_on_tick_stk_v1_callback` and `set_on_bidask_stk_v1_callback`, with callbacks receiving exchange plus the Tick/BidAsk payload; both common-stock streams are event-driven and delivered only during trading hours.
- Official guidance says callbacks should avoid computation. Provider callbacks should therefore only map SDK fields and invoke the small normalized update sink; all matching and portfolio work stays under the simulator lock.
- One symbol consumes two subscriptions when both Tick and BidAsk are active; the implementation must track subscription pairs idempotently and stay within the documented account limit rather than resubscribing on every browser poll.
- A real local Shioaji 1.7.2 smoke test successfully logged into the simulation environment with `subscribe_trade=False`, installed both callbacks, reported streaming healthy, and logged out normally.
- A real 4946 subscription received successful server acknowledgements for both Tick and BidAsk but no market event within the 10-second observation window. Because the feed is event-driven, this proves subscription acceptance but not yet payload mapping.
- A high-liquidity 2330 direct provider smoke received and normalized both real Tick and BidAsk callbacks, proving the SDK callback signature and mapper.
- End-to-end UI and standalone `SimulationService` smokes received ongoing Tick updates but a marketable BUY remained `SUBMITTED` for 10-14 seconds. The issue is downstream of subscription acceptance and requires inspecting the merged quote state before completion.
- The apparently marketable test was correctly pending: live 2330 best bid/ask was 2380/2385 and the test BUY limit was only 2000. Raising the local-paper limit to 3000 filled at ask 2385; the next Tick marked the position at 2380 and produced -5,000 unrealized PnL.
- FastAPI shutdown initially cancelled subscriptions but did not log out the Shioaji client, producing a native-thread panic after process shutdown. Adding an explicit Provider close/logout contract removed the warning in a second real shutdown smoke.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Classify recommendations by priority and evidence | Keeps blocking correctness issues distinct from optional improvements. |
| Include exact files/components and acceptance tests in the final plan | Makes the plan directly executable after approval. |
| Treat performance ideas as hypotheses until current hot paths and state ownership are traced | Avoids premature optimization. |
| Preserve `MarketDataStore` as a latest-state projection, not a historical/event store | Keeps current consumers stable while a separate immutable event source/journal owns replay and audit history. |
| Use one event-driven runner for fast Backtest and paced Replay | Prevents the same strategy from producing different semantics in two engines. |
| Keep the dashboard observer-only | Trading runtime owns provider cadence and state; the UI must never trigger order or streaming side effects. |
| Build common-lot, cash, long-only, limit-order Simulation first | Matches current long-only decision model and Shioaji Simulation constraints while minimizing order-normalization surface area. |
| Treat 20-30 sessions as an observation window, not a sufficient pass criterion | Advancement also requires deterministic, integrity, risk, recovery, and reconciliation gates. |
| Use an explicit simulation-only web command namespace | Makes it difficult to confuse or later repurpose the endpoint as a production-order route. |
| Keep reads projection-backed | Browser refresh/polling reads local order/portfolio state and must not trigger Shioaji status/position queries per request. |
| Show pending orders separately from filled positions | A submitted or accepted order is not yet a purchased holding. |
| Reuse the existing holdings drawer and add a separate simulation order ticket/order blotter | Keeps Candidate inspection intact while making orders and owned positions distinct tasks. |
| Poll or stream local projections, never provider/account APIs per browser request | Keeps API usage, callback ordering, and reconciliation under the backend runtime's control. |
| Make the first implementation session-local | Meets the immediate web simulation requirement without introducing database schema/migration scope; the UI must disclose that restarting the backend clears simulated state. |
| Keep SDK callbacks thin and hand normalized quote updates to `SimulationService` | Avoids doing order-state work on Shioaji callback threads and keeps the simulator testable without the SDK. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Initial memory search had no match and prevented chained reads | Split the reads into independent operations. |

## Resources

- `/Users/stevehuang-work/.codex/attachments/db832d2f-0507-444a-8890-36b212eed197/pasted-text.txt`
- `/Users/stevehuang-work/Documents/tw_intraday_trader`
- Shioaji Simulation Mode: https://sinotrade.github.io/tutor/simulation/
- Shioaji Order & Deal Event: https://sinotrade.github.io/tutor/order_deal_event/
- Shioaji Usage Limits: https://sinotrade.github.io/zh/tutor/limit/
- Official Shioaji repository: https://github.com/Sinotrade/Shioaji

## Visual/Browser Findings

## Freshness Calibration scheduling findings (2026-08-22)

- Official OpenAI guidance distinguishes Codex automations (focused Codex
  workflows) from ChatGPT Scheduled Tasks. Use the existing Codex automation
  mechanism for this local-workspace evidence campaign; do not treat a ChatGPT
  reminder as a reliable local capture runner.
- The legacy `freshness-close-window-capture` heartbeat remains `ACTIVE` despite
  two previously stalled native pause attempts. It starts at 13:00 and produces
  a 13:01–13:16 sample, which cannot observe the required 13:30 boundary.
- The recurring campaign must make an explicit Taiwan-equity-session decision
  before any provider login/subscription. A closed session must be recorded as
  `NO_CAPTURE`, with no Shioaji call. On an open session, it is restricted to
  the frozen 2886/6863/1530 cohort and Tick/BidAsk only with
  `subscribe_trade=False`; account, order, CA, trade-callback, and execution
  APIs remain prohibited.
- Proposed observation windows are 09:15–09:30 (opening), 10:00–10:15
  (continuous), and 13:15–13:35 (close boundary). The final interval must
  cross 13:30; its extra five minutes are an observation window, not a new
  freshness threshold or Portfolio implementation authorization.
- `ReviewedEquityCalendar` already gives a reviewed 2026 TWSE calendar with
  coverage checks and exceptional closures. The scheduling wrapper can use it
  to fail closed on holidays, weekends, and out-of-coverage dates before it
  loads the quote-capture function or initializes Shioaji.
- The existing quote CLI accepts a reviewer-supplied label but does not itself
  enforce the frozen cohort, reviewed calendar, or capture start time. A small
  dedicated runner is therefore required to make unattended collection safe.
- Native `codex_app__automation_update` is not callable in this thread: its
  view request returned `No handler registered for tool: codex_app.automation_update`.
  It is the third distinct failure after two earlier stalled pause attempts;
  do not retry it. A user-authorized local scheduler may be installed only
  after its fail-closed runner is tested.
- The user-level launchd job is installed as
  `com.stevehuang.tw-intraday-trader.freshness-calibration` with all three
  calendar triggers confirmed by `launchctl print`. A manual smoke produced
  `NO_CAPTURE_OFF_SCHEDULE` and no `ntp_preflight` field, demonstrating that
  an unplanned launch does not enter either NTP or quote-provider work.
- The Mac must remain logged in and awake around each start time. If it wakes
  outside the scheduled minute, the runner deliberately returns
  `NO_CAPTURE_OFF_SCHEDULE` rather than backfilling a later, incomparable
  capture window.

## Freshness Calibration acceleration findings (2026-08-22)

- The only safe acceleration within the authorized evidence scope is more
  non-overlapping Tick/BidAsk samples on the same reviewed trading day. It can
  improve opening/continuous coverage but cannot replace evidence from distinct
  trading dates, source-clock disposition, or separate broker/account evidence.
- The accelerated schedule will retain the exact frozen cohort and labels and
  add 09:00–09:15 (`opening`), 11:00–11:15 (`continuous`), and
  12:00–12:15 (`continuous`) to the existing 09:15–09:30, 10:00–10:15, and
  13:15–13:35 captures. The intervals do not overlap.
- Broker/account endpoint collection remains explicitly unapproved. This
  schedule change must not be interpreted as permission to read any account,
  order, accounting, or buying-power endpoint.
- The reloaded launchd service reports exactly six calendar triggers:
  09:00, 09:15, 10:00, 11:00, 12:00, and 13:15 Asia/Taipei. Each starts one
  bounded capture only after the runner's reviewed-calendar and NTP gates.

## Automated evidence-QA findings (2026-08-22)

- Existing accepted evidence is structurally trustworthy only after inspecting
  the immutable artifact's digest/schema, paired acknowledgement, lifecycle,
  coverage, callback errors, monotonicity, and clock-skew. A capture's own
  cadence analysis is useful but does not replace those structural checks.
- The smallest safe acceleration is a post-capture summary written beside the
  scheduler run record. It may state `REVIEW_REQUIRED` or a structural failure,
  but must never select a threshold, label a policy frozen, or make a
  broker/account claim.
- The capture artifact already stores enough immutable fields to create this
  summary: `connection_transitions` carries the per-symbol `TIC`/`QUO`
  acknowledgement evidence, while every observation carries its own
  connection/subscription state. A missing callback group remains partial
  coverage, not structural corruption and not a reason to discard the raw
  artifact.
- Backfill over all eight retained artifacts matches the current human review:
  three continuous captures are structurally complete; the early PENDING
  opening artifact is rejected; early opening and both close artifacts retain
  partial coverage; and the discovery artifact is excluded from the frozen
  cohort. Every artifact has zero callback errors and zero callback-monotonic
  regressions. Clock-skew remains provenance/anomaly evidence only.
- Post-capture QA now compares the artifact bytes to the inspected SHA-256
  before summarizing. If an artifact changes or is structurally invalid, the
  scheduler reports `CAPTURE_INVALID` while leaving the original bytes in
  place for investigation.

- Official documentation was reviewed as of 2026-08-18; volatile API limits and supported operations should be rechecked at implementation time.
- Browser verification used the real local Shioaji feed: stream badge, subscription count, advancing quote time, cancel/pending behavior, ask-side fill, position count, bid/ask/current-price fields, and PnL all rendered correctly with no console errors.

## Basic strategy expansion implementation findings (2026-08-19)

- The pre-change repository baseline is green: 29 focused backtest tests pass; the full suite has 326 passing and 1 skipped test.
- Dataset manifests already carry `profile` and `capabilities`, but all current creation paths only advertise `OHLCV`.
- `create_from_partitions()` counts bars per `(symbol, session)` while `_seal()` counts all symbols per date. The latter can misclassify a multi-symbol daily dataset as intraday.
- Incremental datasets currently inherit their parent's profile and capabilities without re-evaluating the combined immutable bar chain.
- The backtest application validates strategy side but does not compare a strategy definition's required capabilities with the selected dataset.
- Dashboard defaults are positional instead of status-based, so introducing experimental strategies would silently change the default entry and enable all new exits.
- Adding an optional manifest field can silently change the recomputed digest of legacy JSON. The implementation therefore remembers whether `cadence_summary` existed and omits it when reserializing old manifests.
- Legacy strategy runs produce byte-equivalent engine result payloads under frozen v1 and v2; v1 explicitly rejects the five feature-dependent strategies.
- ATR propagation is engine-tested end to end: the signal-bar ATR travels through the pending entry, becomes immutable position context at fill, triggers on a later completed bar, and exits on the following open.
- The final suite has 337 passing and 1 skipped test. Python compilation, Dashboard inline JavaScript compilation, and whitespace validation also pass.
- The implemented slice remains historical/data-only: no CA activation, trade subscription, broker callback, or broker order submission was introduced.

## Previous-day premarket watchlist planning findings (2026-08-19)

- The requested watchlist must be fully available before the open using only data whose market date is earlier than the target session; `PREOPEN_INDICATIVE` is explicitly out of scope.
- The existing `premarket_gap_watchlist_v1` is `DRAFT` and unsuitable for this slice because its contract requires pre-open indicative prices.
- The current Candidate flow and unified strategy catalog are reusable seams, but repository evidence must determine whether a durable watchlist projection and as-of-date API already exist.
- The worktree already contains strategy-expansion and unrelated downloader/provider/night-session changes; this phase is plan-only and must not modify product code.
- `CandidateEngine` consumes current `StockData` snapshots and applies OR-combined rules; it cannot truthfully evaluate an as-of-previous-session watchlist without a separate historical input contract.
- `Candidate` stores only `symbol`, source set, and matched rule names. That is insufficient for a durable premarket artifact because it lacks target session, source dataset digest, evaluation timestamp, and observed evidence.
- The repository already has `CandidatePool`/discovery-source seams and a separate TAIFEX premarket context module/tests. The stock watchlist plan should reuse the pool boundary but remain independent from the market-level TAIFEX context.
- Current Dashboard candidate history is on-demand for symbols already in the snapshot and derives the date range from `datetime.now()`. A premarket watchlist requires an explicit target session/as-of contract rather than this UI cache path.
- `CandidateDiscovery` is the better downstream seam than the legacy `Candidate`: it already carries timezone-aware discovery/expiry timestamps, priority, rank types, and immutable evidence, and `CandidatePool` merges it without treating discovery as a buy signal.
- `CandidatePool` admits every non-scanner source immediately and currently has no target-session identity. A prior-session watchlist source therefore needs explicit expiry at the target session boundary and must not rely on process-lifetime pool history as the reproducible artifact.
- `CandidateSource` has no dedicated prior-session/watchlist value. Reusing generic `USER_STRATEGY` would lose provenance; the plan should add an explicit source while preserving existing AUTO/SCANNER/MANUAL/POSITION semantics.
- Strategy catalog metadata supports a PRE_MARKET CANDIDATE family and immutable versions. New watchlist definitions can be code-owned `EXPERIMENTAL` bindings without changing the existing pre-open gap draft.
- Repository search found tracked `tests/test_premarket_*` imports but no readable `premarket/` package at the expected path. This checkout inconsistency must be resolved before any implementation phase reuses the TAIFEX premarket module.
- Follow-up shows the `premarket/` package and `config/premarket.py` truly do not exist in this checkout, while ignored/untracked-looking premarket test files are present. The implementation plan must treat the separate TAIFEX plan/files as concurrent, unavailable work and define no dependency on them.
- The existing after-close scheduler only excludes weekends; it has no holiday/makeup-session calendar. A prior-session watchlist must use a versioned TWSE/TPEX trading calendar or fail closed rather than infer previous session as calendar day minus one.
- `HistoricalDatasetCatalog.load_bars()` materializes the entire immutable dataset. Reusing it directly for an every-day full-market screen would be correct for a small fixture but inefficient for a multi-year market dataset; the plan needs a bounded recent-session read or a derived daily-bar artifact.
- Current historical capabilities distinguish OHLCV/intraday/1m/session boundaries but do not explicitly certify complete daily bars. The watchlist must require a daily aggregation/completeness capability and never calculate from a partially synchronized target session.
- `HistoricalBar.amount` is currently populated as `close × volume` for Provider downloads, while `KBar` itself exposes only OHLCV. Liquidity filters must label this as a traded-value proxy unless a source-backed turnover field is introduced.
- Session-scoped `InstrumentReferenceStore` supports momentum eligibility, but it is not a date-effective listing/delisting universe. Operational next-session screening and historical research eligibility must remain separate.
- During planning, untracked `config/premarket.py`, `config/taifex_calendar_2026.json`, and partial `premarket/` files appeared from concurrent work. They are user/concurrent changes, remain outside this plan's edit scope, and cannot be treated as a stable dependency until that work is complete and reviewed.
- `CandidatePoolDecision` hashes admission metadata but drops each discovery's detailed evidence. The immutable watchlist artifact must remain queryable for UI/research evidence even after its symbols are converted to CandidateDiscovery items.
- The main Dashboard still uses legacy `run_scan()` (`CandidateEngine` plus manual list), while CandidatePool belongs to the Momentum subscription universe. The implementation must explicitly project the new watchlist in the Dashboard and separately adapt it into CandidatePool; changing only CandidatePool would not make the list visible in the current dashboard.
- Existing runtime composition is provider/dashboard/simulation oriented and contains no durable research-artifact service. A read-only watchlist projection can be composed separately, similar to the Momentum dashboard service, to avoid initializing provider or order paths.
- Existing backtest job persistence already supports arbitrary job kinds and immutable resource IDs. It can coordinate watchlist generation, but artifact content should have its own catalog/repository contract rather than overloading CandidatePool history.
- Instrument references do not include security type/listing intervals. The plan requires a date-effective universe input with explicit equity eligibility; it must not infer common-stock status from a four-digit symbol.
- Existing `candidate/rules.py` operates on floating-point current `StockData` and global settings. Prior-session strategies need separate immutable Decimal daily-feature inputs and version-owned parameters; they should not be added as more `CandidateRule.match(StockData)` implementations.
- The Dashboard already has a market-overview candidate panel and strategy-catalog drawer. The smallest truthful UI is a separate read-only `盤前觀察池` panel/status in the overview, with drill-down evidence, rather than silently mixing historical candidates into the current score-sorted candidate list.
- Current backtest persistence has durable jobs but no watchlist artifact tables. A forward migration can add manifest/entry rows for bounded reads while preserving immutable JSON evidence and supporting both SQLite and PostgreSQL adapters.
- Existing UI tests are static HTML contracts and service/API tests use injected providers. The plan should add watchlist domain fixtures plus service/API/UI tests without requiring Shioaji or network access.
- The concurrent TAIFEX work also modified package discovery to include `premarket*`. The stock watchlist should use a distinct `watchlist*` package include to avoid namespace and rollout coupling.
- The finalized design uses an explicit target session `T` and calendar-derived prior session `P`; the pure engine receives both and may read only sessions through `P`.
- The first reviewable implementation slice is calendar/universe contracts, shared indicators, immutable daily derivation, Momentum v1, artifact persistence, and deterministic CLI. CandidatePool, Dashboard, scheduler activation, NR7, and Oversold follow only after the evidence layer is verified.
- A current-snapshot equity universe may support an operational next-session artifact, but it must be marked `research_eligible=false`; historical out-of-sample evidence requires a date-effective universe.
- The completed plan is `architecture/previous_day_premarket_watchlist_implementation_plan.md`; it changes no product behavior and keeps all three definitions `EXPERIMENTAL`.

## Previous-day watchlist Phase 0-3 review findings (2026-08-19)

- The three strategies remain candidate generators, not demonstrated trading strategies; Watchlist, intraday confirmation, BuyScore, and entry decision must remain separate stages.
- Corporate actions are a P0 blocker for formal validation. Preserve raw OHLCV, derive a consistently adjusted OHLC series, store the adjustment factor/type/source/digest, and forbid mixing raw and adjusted fields inside one indicator.
- Momentum needs `daily_return` and `close_location` evidence to distinguish strong closes from high-volume distribution. The initial research design should compare baseline, positive-return, close-location, and combined variants rather than promote `0.6` directly to a production threshold.
- A one-price bar makes `close_location` undefined and must be classified before strategy evaluation.
- Rename the normalized NR7 strategy to `nr7_compression_watchlist_v1`; it is direction-neutral and must wait for next-session NR7-high/ORB/VWAP confirmation before any LONG bias.
- Hard-exclude one-price or limit-locked false compressions from NR7. Merely touching a price limit while retaining a real range should remain a flagged research cohort rather than an automatic exclusion.
- Momentum limit-up observations should be flagged and evaluated separately from ordinary momentum instead of silently mixed into one population.
- Oversold remains `EXPERIMENTAL` and confirmation-only; it must not block the first Momentum artifact slice.
- Formal validation must be net of date-effective commission, minimum fee, transaction tax, bid/ask, and slippage. Gross performance alone cannot pass a promotion gate.
- The user authorized rewriting the plan's Phase 0-3, not implementing product code.
- Corporate-action adjustment itself needs point-in-time semantics: historical target `T` uses an `adjustment_as_of=P` view containing only actions effective and available by the generation cutoff. A vendor's later fully adjusted series must not rewrite old artifacts.
- Raw daily bars and adjusted views should therefore be separate immutable layers; adjusted-view identity includes raw derivation, as-of session, adjustment snapshot, and reference-data digest.
