# Findings and Decisions

## Requirements

- Add a separate `MomentumSignalEngine`; do not fold the signal into `BuyScoreEngine`.
- First signal family contains breakout, volume acceleration, momentum acceleration, and limit-up momentum evidence.
- Initial feature hypotheses: price above VWAP, previous-high breakout, 2-minute return, distance to limit, 2-minute volume acceleration, external-ratio level/trend, and five-level bid/ask imbalance.
- Initial illustrative weights total 100 and trigger at 70, but all thresholds and weights remain research hypotheses.
- Add an explicit progression: `WATCH -> STRONG -> BREAKOUT -> ACCELERATING -> NEAR_LIMIT_UP -> LIMIT_UP`.
- Preserve both `EntryMode.NORMAL` and `EntryMode.MOMENTUM`; Momentum mode may recommend smaller sizing and strict breakout-failure exit, but cannot bypass RiskGate.
- Dashboard should issue an actionable Traditional Chinese alert with evidence, current/limit price, distance, score/state, and risk framing—not only a generic BuyScore.
- Preserve 8039 台虹, 2026-08-18, 09:16-09:18 as the first intended testcase.
- Design historical validation across past 9:00-10:00 limit-up stocks and pre-event windows of 1/3/5/10 minutes.
- Add `MarketScannerCandidateSource` so Scanner/AUTO/MANUAL/Position feed one Candidate Pool before subscription allocation.
- Qualify one Quote subscription per symbol against separate Tick+BidAsk for payload coverage, delivery frequency, latency, ordering, data loss, and detector parity.
- Add `OpeningMomentumSignal` for 09:00-09:10; preserve the complete five-window median baseline for `LimitUpMomentumSignal` after warm-up.
- Rename public `LIMIT_UP` stage to `LIMIT_TOUCHED`; model `limit_locked` and `limit_unlocked_at` independently.
- Rename UI `Momentum Score` to `Evidence Score` and state that 100/100 means six evidence rules passed, not 100% limit-up probability.

## Initial Evidence and Caveats

- The supplied screenshots/summary support 272 to 278 in two minutes, a new-high break over 275, total-volume increase of 2,306 lots, external ratio rising from 56.15% to 62.27%, and distance to the 284.5 limit narrowing to about 2.34%.
- A rise in cumulative volume over two minutes is not by itself proof that `volume_acceleration >= 1.5`; a baseline interval definition and earlier volume observations are required.
- `price = 272` below an observed `high = 275` at 09:16 is not yet a breakout state; it is more accurately a breakout-watch/pre-breakout state until price exceeds the prior high.
- External ratio derived from cumulative outside/total volume is not interchangeable with a rolling two-minute aggressor ratio. The plan must choose and name one definition.
- Bid/ask imbalance is a point-in-time depth feature and is vulnerable to cancellation/spoofing; it should be freshness-checked and treated as supporting evidence, not a standalone trading trigger.

## Research Findings

- Product Phase 2 will preserve the existing snapshot `MarketDataStore` and simulation-oriented provider path; the new stores consume the richer Phase 0 `TickEvent`/`BidAskEvent` contracts independently.
- Gate G2 needs per-stream ordering rather than a fabricated Tick/BidAsk total order. Replay will use a deterministic envelope order while stores independently reject stale projections and exact duplicate event IDs.
- The prior realtime research memory supports bounded callback queues, explicit sequence numbers, fatal/non-silent overflow, shutdown drain, and deterministic replay. Phase 2 will implement the data/store/replay contracts only; live queue orchestration remains a later runtime phase.
- A concurrent, unimplemented foundation plan proposes the same canonical EventEnvelope/DataHealth/Clock/ingestion boundaries. To avoid parallel domain models, Momentum Phase 2 will extend `market_data` with framework-free value objects and in-memory projections; no FastAPI, Shioaji, filesystem, PostgreSQL, or trading imports belong in those core modules.
- The active Momentum plan's store names remain useful bounded projections (`InstrumentReferenceStore`, `IntradayBarStore`, `OrderBookStore`). Shared ingestion will depend on their methods, while provider and replay adapters depend inward on the canonical event contracts.
- Tick volume is accumulated from unique common-lot Tick events, while cumulative total volume is a continuity invariant: a decrease or delta below tick volume is invalid; a larger delta indicates a missing-event gap and must block DataHealth rather than silently backfill the bar.
- Tick and BidAsk watermarks use `(event_time, ingress_sequence)` per symbol and stream. This accepts legitimate same-time events with increasing ingress identities while rejecting older projections; exact `event_id` handles retries independently of content equality.
- OrderBookStore retains bounded recent history, not only one object, so a Tick feature can select the latest book at or before its own `as_of` without using a future cross-stream update.
- Canonical ingestion validates both `session_id` and `session_date`; same-day replay/live sessions cannot share watermarks or projections accidentally.
- Replay identity is generated from immutable manifest content SHA-256 plus row index. The hash excludes generated IDs, avoiding a circular manifest, while identical legal rows remain separate events.
- The Phase 2 8039 synthetic fixture preserves 272 to 278 and cumulative volume 8,806 to 11,112. It deliberately does not claim a rolling volume baseline or Momentum signal; those remain Phase 3 inputs.

- Product Phase 1 can be implemented while G0 remains open if all capacity/runtime choices are injected explicitly and no live subscription mode is enabled by default.
- The installed Shioaji 1.7.2 runtime exposes `Shioaji.scanners(scanner_type, date=None, ascending=True, count=100, timeout=30000, cb=None)` and six scanner types: Amount, ChangePercent, ChangePrice, DayRange, TickCount, and Volume rank.
- The existing `ShioajiProvider` owns a concurrent simulation-oriented Tick+BidAsk subscription set with a fixed 100-symbol guard. Phase 1 must not silently replace that shared runtime; it should add an allocator/controller contract that can later drive a qualified provider adapter.
- Candidate models currently support AUTO/MANUAL/POSITION but not SCANNER. Existing CandidateEngine output is symbol-only and can be adapted without carrying stale StockData into the pool.
- CandidatePool now treats MANUAL/POSITION and active episodes as protected; if protected symbols themselves exceed explicit capacity it raises instead of evicting one or exceeding the provider limit.
- Scanner admission uses a configured repeated-observation count, while TTL plus grace and SubscriptionManager minimum dwell provide separate admission/eviction hysteresis. The config/policy versions make these still-research values auditable.
- Subscription request/ack is intentionally two-step. Requests, ack timeouts, and failed/unconfirmed unsubscriptions consume capacity; coverage contains only provider-acked symbols.
- Scanner responses, CandidatePool decisions, subscription decisions, and lifecycle events are append-only immutable in-process records in Phase 1. Durable prospective archiving remains a runtime integration responsibility and is not represented as complete yet.

- Memory from the prior dashboard work says the current architecture is a decision-support MVP with `MarketDataProvider -> MarketDataStore -> CandidateEngine -> BuyScoreEngine -> PositionManager/Exit Rules`; this must be revalidated against current files.
- The current dashboard is historically read-only and source-backed; any alert design must keep provider and feature calculation server-side.
- Current code confirms `StockData` contains only latest snapshot fields: symbol/name/timestamp, OHLC, previous close, cumulative volume, previous-day volume, optional VWAP/RVOL/market. It has no external ratio, trade direction, limit price, price reference, bid/ask depth, exchange sequence, event-received time, or rolling history.
- `MarketDataStore.update()` is last-call-wins and retains one `StockData` per symbol; its docstring explicitly defers stale-timestamp rejection.
- `MarketDataProvider` is pull-oriented (`get_stock`, `get_market_stocks`, `get_kbars`) and has no Tick/BidAsk subscription or callback lifecycle contract.
- `run_scan()` creates a new in-memory store and engines on every call, so it cannot calculate 1/2/5-minute features or preserve state-machine episodes between dashboard refreshes.
- Dashboard refresh is manual and invokes a full one-shot scan; the provider status is explicitly `snapshot`, `streaming=False`. It cannot be the clock for a realtime momentum alert.
- Existing Candidate and BuyScore engines are stateless rule aggregators over `StockData`; preserving them while adding a sibling `MomentumSignalEngine` matches the request and current separations.
- Current settings centralize rule thresholds. Hypothesis parameters should follow this convention but be grouped/versioned separately from validated production parameters.
- Historical dashboard Kbars are source-backed but aggregate intraday display to 5-minute bars. They are insufficient for a 1/2-minute pre-limit event study unless raw 1-minute/tick data is separately acquired and retained.
- The architecture report deliberately deferred `features/`, `backtest/`, and `alerts/`; this request now supplies a concrete need for those seams, but still does not justify a broad event/microservice rewrite.
- Current package discovery enumerates existing modules. New `features`, `signals`, or `market_data` subpackages must be deliberately included/tested in built artifacts.
- Worktree is not clean: the pre-existing root planning Markdown and `architecture/execution_layer_v1_implementation_plan.md` are untracked, while this task modified only its isolated `.planning` files and active-plan pointer so far.
- Current official Shioaji Snapshot documentation lists `ts`, OHLC/close, `tick_type`, `average_price`, single-tick and total volume/amount, best buy/sell price and volume, and `volume_ratio`. Current code maps only a subset and replaces source `ts` with local `datetime.now()`.
- Official Shioaji quote-binding documentation confirms callbacks can append Tick/BidAsk-style quote payloads to a queue or push them to Redis. The plan should keep callback work minimal and hand off normalized events to a bounded queue/runtime worker.
- Current official TWSE rules set the ordinary stock price band to plus/minus 10% of the current session's opening auction reference price, subject to tick-size rules and exceptions such as the first five trading days of certain new listings. `previous_close * 1.10` is therefore not a universally correct limit-up computation.
- TWSE's current tick table includes price-dependent increments (for example, NT$100 to below NT$500 uses NT$0.50 ticks). A `LimitPricePolicy` must use authoritative reference/contract metadata and exchange rounding rules; it should not hard-code `round(previous_close * 1.1, 2)`.
- Current Shioaji stock streaming documentation says the realtime feed is event-driven and supports `Tick`, `BidAsk`, and `Quote` subscriptions. Tick includes exchange date/time, last/open/high/low/average price, per-tick and cumulative volume, aggressor-side `tick_type`, cumulative bid-side/ask-side traded volume and counts, suspend/simulated-trade flags. BidAsk includes five price/volume levels plus level changes.
- In Shioaji's documented Tick semantics, `tick_type=1` is ask-side execution and `tick_type=2` is bid-side execution; the plan must normalize this into domain names such as `AggressorSide.BUY/SELL/UNKNOWN` and prove the mapping with adapter tests instead of propagating raw integers.
- The user's screenshot `external_ratio` can likely be reproduced from cumulative aggressor-side trade volumes, but field naming must be verified against the actual screen/source. The first implementation should store both numerator/denominator and the derived ratio so it is auditable.
- Shioaji distinguishes common-stock volume (lots) from intraday odd-lot volume (shares). The detector must either exclude odd-lot events in v1 or normalize both to shares before combining; silent unit mixing would corrupt volume acceleration.
- Five-level `bid_ask_imbalance = sum(bid_volume) / sum(ask_volume)` requires zero-denominator and empty-level handling. A bounded/log transform or cap should be considered for research so a near-zero ask book does not dominate the score.
- Shioaji also provides completed 1-minute KBar subscription events at the end of each minute. They are suitable for closed-bar features but introduce up-to-one-minute availability delay; Tick-derived rolling features are required if the intended alert must fire within the current minute.
- Official Shioaji guidance explicitly says to avoid heavy computation in callbacks. Callback adapters should validate/map/enqueue, while one ordered consumer updates stores, bars, features, state, and alerts.
- The current official subscription cap is 200, and one identity may have at most five connections. Since Tick and BidAsk are separate subscriptions, the plan cannot subscribe both event families for the full market. It needs a bounded active universe and subscription manager, with positions/pending alerts protected from eviction.
- Official Shioaji restrictions reiterate that snapshots/ticks/kbars request APIs must not be polled as a realtime feed. Historical acquisition and realtime detection therefore need separate workflows.
- The existing execution-layer plan already defines reusable deterministic market-event, replay-clock, DataHealth, bounded-queue, Shadow, and subscription-management seams. The Momentum plan should depend on those foundations where present and avoid inventing a second realtime runtime.
- Official Shioaji historical data provides tick-by-tick trades by symbol/date/time range and 1-minute Kbars in at-most-30-day query windows. Historical ticks include last price, volume, best bid/ask price and volume, and `tick_type`; they do not provide archived five-level BidAsk snapshots.
- Therefore the first one-year retrospective can validate price/VWAP/breakout/return/distance/volume and possibly aggressor-ratio hypotheses, but full five-level imbalance needs either an independently archived source or prospective Shadow collection. It must be reported as `not_backtestable_with_current_dataset`, not silently filled or dropped.
- A one-year study cannot select only successful limit-up names. It needs an event table with `first_limit_up_at`, all eligible evaluation timestamps, non-limit-up/matched controls, and observation censoring for suspensions/no-price-limit instruments.
- There is conflicting nomenclature across current/older official Shioaji pages for raw `tick_type` (`ask/bid`, `inside/outside`, and Chinese inside/outside mappings). The adapter must not guess. Add a one-session labeled capture that reconciles raw values against bid/ask prices and the source UI before computing `external_ratio`.
- Historical 1-minute Kbars alone cannot reproduce a screenshot's cumulative external ratio. Historical Ticks may, after the above mapping is verified, by aggregating aggressor volume rather than tick counts.
- Official Shioaji stock contracts expose `limit_up`, `limit_down`, `reference`, `exchange`, and `update_date`. The safest v1 source for `distance_to_limit` is a session-scoped `InstrumentReferenceStore` populated from contract metadata, validated for the trading date, rather than recomputing limits from `previous_close`.
- Current TPEx main-board rules also use plus/minus 10% of opening auction reference with the same stock tick bands and exceptions for instruments/days without price limits. The eligible universe must explicitly exclude Emerging Stock Board and any contract without a valid daily limit.
- The current repository regression baseline is 71 passing tests in 0.23 seconds.
- Current official Shioaji Scanner documentation supports change-percent, change-price, day-range, volume, amount, and tick-count rankings; each call accepts up to 200 results and returns timestamped price/volume/amount plus best-price and cumulative side fields.
- Scanner is therefore suitable as a bounded discovery source, not as a realtime feature stream. Its cadence, request-budget use, union/deduplication, eligibility filtering, and admission/eviction delay must be observable.
- Current official stock streaming documentation exposes `Quote` as a subscription type alongside Tick and BidAsk. Exact stock Quote field coverage and delivery parity still require Phase 0 qualification against separate Tick+BidAsk before it becomes the default detector feed.
- The official `Quote` schema includes trade price, average price, cumulative volume/amount, `tick_type`, cumulative side statistics, and five-level bid/ask fields. Schema coverage is sufficient on paper, but it does not prove event-frequency, ordering, staleness, or feature-output equivalence to separate `Tick + BidAsk` streams.
- Phase 0 must run a simultaneous, small-symbol, market-hours A/B capture of `Quote` versus `Tick + BidAsk`. Acceptance evidence should compare cumulative-volume conservation, latest-book parity/staleness, update/latency/gap distributions, reconnect behavior, and the resulting feature/signal/alert digests.
- Capacity must be computed as `floor((200 - reserved_headroom) / subscriptions_per_symbol)` instead of hard-coding either 100 or 200 monitored symbols.
- The reviewed official limits page does not provide a numeric Scanner request-rate limit. Scanner cadence must remain configurable and cached, with usage telemetry, until Phase 0 measures and freezes an operational value.

## Formula Consistency Review

- `278 / 272 - 1 = 2.2059%` and `284.5 / 278 - 1 = 2.3381%`, matching the proposal after rounding.
- `11,112 - 8,806 = 2,306` lots in two minutes; no acceleration ratio is calculable without earlier 2-minute windows.
- The six proposed weights sum to 100. At 09:18 the five directly supported flags (above VWAP, breakout, 2-minute return, within 3% of limit, external ratio rising) sum to 80; if volume acceleration is later proven, the score is 100. A score of 85 is not reachable from the listed binary weights.
- The narrative uses `ACCELERATING` at 278 and `NEAR_LIMIT_UP` around 282, while the proposed testcase says `NearLimitUp = TRUE` at 278. The plan will separate an independent `within_3pct_of_limit` feature from the single state-machine stage; provisional stage thresholds must be reviewed and then frozen before the golden test.

## Phase 7 semantic review

- `OPENING_MOMENTUM` and `LIMIT_UP_MOMENTUM` are separate evidence families but share the domain semantic `momentum_acceleration_confirmed`; the state machine should consume that semantic instead of enumerating concrete families.
- Momentum Entry policy should depend on an active acceleration episode, a configurable set of supported families, and RiskGate PASS. Whether Opening is enabled is an explicit policy choice, not an accidental consequence of a hard-coded signal name.
- Episode provenance needs immutable creation fields, mutable current family/config fields, and transition/evidence-update records carrying their own family/config version. This preserves the 09:10 handoff in Replay without creating a new episode.
- Session catchup confirms the shared worktree still contains concurrent simulation/dashboard edits. Phase 0 must avoid those files unless package discovery requires a narrow, conflict-aware change.
- No repository-local `AGENTS.md`, `RULES.md`, `.codex`, or `.agents` instruction files were found by the scoped search.
- Current Python packages are flat top-level modules with stdlib dataclasses/enums and pytest. Phase 0 can add isolated `signals` contracts plus `market_data` qualification code without touching Dashboard behavior.
- Current `pyproject.toml` package discovery already contains concurrent `simulation*` work. Adding `signals*` must preserve that line and all other existing package entries.
- Current code already has a minimal `RealtimeQuoteUpdate` (`TICK`/`BIDASK`) and `ShioajiProvider` streaming lifecycle with a hard-coded `MAX_STREAMING_SYMBOLS = 100`. Phase 0 contracts should not silently treat that as proof that one Quote subscription is equivalent.
- Existing model style uses stdlib dataclasses and `StrEnum`; tests use direct pytest functions/classes without extra frameworks. New Phase 0 contracts can remain dependency-free.
- The existing streaming provider only forwards last price and best bid/ask and subscribes separate Tick+BidAsk; it does not retain total volume, average price, raw tick type, full five levels, or Quote-mode observations. It cannot serve as the Phase 0 parity evidence source without a separate capture schema/harness.
- The execution-layer architecture expects shared MarketEvent/DataHealth/Replay foundations but those production modules are not yet present. Phase 0 should define Momentum/provider contracts now and avoid prematurely implementing the later realtime reducer.

## Phase 0 implementation slice

- Add dependency-free `signals` contracts for family-neutral acceleration, versioned entry-family policy, immutable episode provenance, and lock state.
- Add dependency-free `market_data.quote_qualification` capture/report models that calculate deterministic parity evidence but return `INCOMPLETE` until reviewed thresholds and both source captures are present.
- Keep the existing Shioaji provider in Tick+BidAsk mode for now; do not change its 100-symbol behavior or claim Quote parity before a live labeled capture.
- Add offline fixtures/tests for Opening→Limit family handoff provenance and Quote parity pass/fail/incomplete behavior; update package discovery without removing concurrent `simulation*`.
- Code review confirmed the family/config contracts preserve immutable creation provenance and keep Entry policy independent of engine classes.
- The first parity metrics draft reported p95 latency only, while the plan requires p50/p95/p99 evidence. Add p50/p99 source metrics before treating the offline harness slice as complete.
- The focused offline Momentum slice contains 23 passing tests. The shared repository now reports 100 passing tests, but part of the increase over the earlier 71-test baseline comes from concurrent realtime-stream work and must not be attributed to this task. These results verify contracts and deterministic qualification logic only, not live Shioaji Quote parity.
- Final status review shows concurrent edits now also include `market_data/models.py`, `market_data/provider.py`, and `tests/test_realtime_quote_stream.py`. They remain outside this task; the only overlapping tracked file intentionally edited here is the additive `signals*` package entry in `pyproject.toml`.
- At 2026-08-18 10:25 CST the market-hours window is active and Shioaji is installed in the project `.venv`. A live A/B capture may be technically possible if data-only credentials are configured, but no credential values should be printed or recorded.
- Data-only credentials are configured (presence only was checked; values were not printed). Installed Shioaji is 1.7.2 and exposes `subscribe(... quote_type, version, ranking)`, `set_on_quote_stk_v1_callback`, and its clear callback, so a bounded live A/B capture can proceed with `subscribe_trade=False`.
- Shioaji 1.7.2 deprecates `sj.constant.QuoteType`; the current enum-like API is exposed as top-level `sj.QuoteType`/`sj.QuoteVersion`. Tick/BidAsk/Quote stock v1 models are also top-level SDK objects rather than members of `shioaji.data`.
- Installed enum values are `sj.QuoteType.Tick='tick'`, `BidAsk='bid_ask'`, `Quote='quote'`, and `sj.QuoteVersion.v1='v1'`. The SDK models are compiled objects without useful Python annotations, so live callbacks should remain defensive (`getattr`) and save a schema/sample manifest.
- Installed 1.7.2 model descriptors confirm Quote exposes total volume/amount, average price, tick type, cumulative bid/ask-side volumes/counts, and five-level bid/ask arrays; Tick and BidAsk expose the corresponding separate fields. Login supports `subscribe_trade=False`; subscribe/unsubscribe share the same quote type/version contract and `logout()` takes no arguments.
- The apparent duplicated `quote_books` assignment was an artifact of overlapping `sed` ranges, not a code duplication. Exact line-number search is required before the next evaluator patch.
- The first successful unsandboxed live capture subscribed/unsubscribed Quote, Tick, and BidAsk for 8039 and logged out cleanly, but all callback counts were zero during the 20-second 10:36 window. It proves lifecycle cleanup only, not parity; the artifact remains correctly `INCOMPLETE`.
- First live artifact: `research/captures/quote_parity/8039_20260818T103605+0800.json`, SHA256 `d413fc7386d6ddc27a37de84fe8cb6eb14867227c1cb9e8768ae628fb7ec01ef`.
- The live run emitted an SDK 1.7.2 deprecation warning for `api.Contracts`; use `api.contracts` when available before the next sample.
- That recommendation was disproven by runtime: `api.contracts` is a `ContractsApi` without `.Stocks`, not a drop-in collection replacement. Keep the working legacy `api.Contracts.Stocks[...]` lookup for this bounded Phase 0 capture and isolate v2 contract migration from parity testing.
- Corrected 2330 live capture (20 seconds, 10:37:59-10:38:20 CST) completed with zero callback errors: Quote 62 callbacks, Tick 3, BidAsk 47; 66 projected Quote observations including two baselines and 50 paired observations.
- Preliminary trade evidence matched exactly across modes: 3/3 non-baseline trade events, terminal volume/amount/average price/bid-side total/ask-side total deltas all zero, raw tick type equal, and latest trade time delta zero.
- Latest five-level book and latest book time matched, but Quote emitted 61 non-baseline book changes versus 47 BidAsk events (count ratio about 0.7705). This confirms update cadence is not trivially identical and requires reviewed criteria plus a longer sample.
- Source-to-local timing showed negative p50 values (about -64.8ms Quote and -62.3ms paired), indicating clock skew; these values cannot be interpreted as one-way network latency without clock qualification. Relative p50/p95/p99 deltas were about 2.45/4.51/10.53ms in this sample.
- Active live artifact: `research/captures/quote_parity/2330_20260818T103759+0800.json`, SHA256 `40416f29b652c60fb6ea917b86a6e81f33ac9d6a184097c28786551ca45a9a9b`. Status remains `INCOMPLETE` solely because production criteria are not frozen; reconnect and derived digests also remain future gates per artifact note.
- After the final clock-skew and capture changes, the shared repository passes 107 tests. The focused Momentum Phase 0 subset is 30 tests; the remainder includes pre-existing and concurrent work.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Separate latest projections from recent/history stores | Latest value, deterministic 1m bars, and order-book depth have different update and retention semantics. |
| Compute features from one immutable as-of snapshot | Prevents mixing data from different timestamps and makes test/replay evidence auditable. |
| Make state transitions monotonic only within an episode, with reset rules | Raw score alone can chatter around thresholds or carry yesterday's state into a new session. |
| Include negative/control cases in validation | Looking only at stocks that eventually hit limit-up creates selection bias and cannot estimate false alerts. |
| Introduce a long-lived intraday runtime separate from `run_scan()` | State, rolling windows, stream freshness, and event-time ordering cannot be reliable inside manual HTTP refreshes. |
| Keep `StockData` backward-compatible initially | Candidate/BuyScore/UI consumers need not absorb tick/order-book fields; richer event and feature models can sit beside the current snapshot DTO. |
| Use one ordered processing lane per symbol (or deterministic partition) | Prevent Tick and BidAsk callbacks from racing while preserving parallelism across symbols later. |
| Use Tick-derived 1m bars as the canonical live feature input | Supports within-minute decisions and lets replay use the same bar builder; provider KBar events can be used as reconciliation evidence rather than a second decision clock. |
| Reuse execution-layer MarketEvent/DataHealth/Replay seams | Prevents two event clocks, two queue policies, and incompatible replay semantics in one repository. |
| Split retrospective and prospective feature validation | One-year Kbar/Tick evidence and prospective five-level order-book evidence have different source availability and must not be presented as one homogeneous dataset. |
| Source limit prices from current-session contract metadata | Shioaji already exposes the reference and exchange-calculated limit prices, avoiding unsafe local rounding and exception logic. |
| Keep evidence booleans separate from stage | Multiple conditions may be true simultaneously, but a state machine has one current stage; conflating them makes the 8039 expected result contradictory. |
| Make above-VWAP and breakout v0 regime guards | Prevents unrelated near-limit/volume evidence from creating a composite acceleration signal without the strong-breakout regime described by the user. |
| Do not deduplicate content-equal live trades | Without a provider-stable event identity, two identical payloads may be two legitimate executions; live and Replay need explicit source/session row identities. |
| Treat discovery recall as a first-class detector metric | A correct signal engine is ineffective if the symbol never enters the active subscription universe. |
| Keep opening and post-warm-up signals separate | Avoids weakening the deterministic five-window volume baseline merely to cover early-session moves. |
| Separate touch from lock state | Reaching the limit price and remaining locked at the limit are different observable market facts. |
| Call the total an Evidence Score | Prevents users from interpreting a binary-rule sum as a calibrated probability. |
| Qualify one-Quote-per-symbol before adopting it | Field coverage is documented, but detector equivalence depends on delivery behavior and derived-output parity. |
| Calculate subscription capacity with explicit headroom | Keeps the active-universe policy correct for either one Quote or separate Tick+BidAsk subscriptions. |
| Place existing CandidateEngine output upstream of CandidatePool | Candidate discovery must happen before subscription and realtime features; keeping it below FeatureEngine would create a discovery loop. |
| Keep `limit_locked` nullable until book evidence is current | `False` would conflate a proven unlocked market with stale or unavailable order-book data. |
| Preserve one episode across the 09:10 signal-family handoff | Opening and post-warm-up engines need separate configs without duplicate alerts or a fake second breakout. |
| Implement discovery/subscription allocation before realtime detector integration | The previous phase order deferred CandidatePool until Shadow, which would leave the principal coverage risk untested too late. |
| Name the live phase realtime Shadow rather than Quote-only Shadow | Quote is preferred only after parity qualification; the plan must continue to describe the Tick+BidAsk fallback accurately. |
| Anchor features to the current Tick identity | Event time alone cannot exclude a later same-timestamp Tick; `(event_time, ingress_sequence)` preserves strict-prior semantics. |
| Require explicit continuous Tick coverage | Empty windows are valid only when coverage proves the stream spanned the whole interval; otherwise volume evidence is missing. |
| Expose evaluation status separately from component signal | `BREAKOUT + INSUFFICIENT_DATA` is more honest than either hiding a verified breakout or claiming a complete composite signal. |

## Phase 3 implementation slice

- Added `features.models` and `features.engine` with immutable validity/source metadata, strict as-of price/high selection, five-window volume baseline, external ratio, five-level book support, and fail-closed completeness.
- The rolling windows are `(as_of-2m, as_of]` for current volume and five immediately preceding non-overlapping windows. Four of five complete windows are accepted; a zero median denominator remains missing.
- The screenshot-only 8039 fixture now deterministically produces known Evidence Score 80 and `INSUFFICIENT_DATA`; no earlier volume is inferred from the 2,306-lot cumulative change.
- The separate enriched synthetic fixture has median baseline 1,400 lots and current volume 2,306 lots, producing acceleration 1.647142857..., Evidence Score 100, and `LIMIT_UP_MOMENTUM` at 09:18.
- Added Opening and Limit-Up evaluators plus the 09:10 event-time router. Opening can confirm the shared acceleration semantic only when a named research context is explicitly injected; the repository default remains unconfigured and fail closed.
- External-ratio evidence is optional and loses 10 points when mapping is `UNVERIFIED`; it is never silently calculated from raw tick-type names.
- Added deterministic `SignalResult.digest` and a read-only Replay inspection CLI. No live subscription, state machine, Dashboard alert, RiskGate, Entry, Broker, or order behavior was enabled.
- Phase 3 focused suite passed 32 tests with 88% coverage; full shared-worktree regression passed 207 tests with 1 skip after a concurrent trading-test update settled.

## Phase 4 implementation start

- The user authorized the next implementation phase after Phase 3 completion.
- The current shared worktree also contains concurrent `trading/`, generated `build/`, egg-info, Dashboard, simulation, and provider changes. Phase 4 will not edit or clean those artifacts.
- Phase 4 must keep StateMachine dependent only on family-neutral SignalResult semantics and feature evidence, never switch on concrete Opening/Limit-Up family names to decide acceleration.
- No external notification, Dashboard mutation, live subscription, Broker API, order application, or real-money path is authorized in this phase.
- Existing `MomentumEpisode`, `StageTransition`, and `EvidenceUpdate` already preserve family/config provenance, but the aggregate lacks breakout level, peak, last evaluation, closure reason/time, and cooldown metadata required by the reviewed lifecycle.
- One evaluation may satisfy breakout and acceleration together. The episode should record ordered internal transitions while Projection emits at most one final-stage alert for that evaluation, avoiding an alert burst.
- The public state machine can inspect `momentum_acceleration_confirmed`, feature booleans, distance, and DataHealth; it must not branch on concrete signal-family enum values. Family/config are provenance only.
- A 09:10 handoff on an active episode appends a new evidence record and updates current provenance. It does not fabricate a stage transition or change the episode ID.
- Lock confirmation needs a separate semantic book observation and versioned duration. The default unresolved lock policy remains unknown; tests may inject an explicit duration without promoting it.
- A concurrent execution-layer RiskGate now exists under `trading/`, but Momentum Phase 4 will retain a domain-level RiskGate status port and not import the trading adapter. Integration mapping remains a later application-layer responsibility.
- Entry `AVAILABLE` requires an active stage at least ACCELERATING, an enabled current family, RiskGate PASS, and an auditable risk decision ID. Missing/unavailable RiskGate remains BLOCKED.
- Alert identity intentionally excludes config version, so an Opening-to-Limit-Up evidence handoff cannot bypass deduplication. Family/config remain in the alert payload for audit.
- A single evaluation can write both BREAKOUT and ACCELERATING transitions into the episode, but Projection emits only the final alertable stage. This avoids an artificial alert burst while preserving Replay provenance.
- Limit touch and limit lock are independent event types. The unresolved default lock duration never produces `LIMIT_LOCKED`; explicit tests inject a reviewed duration only as fixture policy.
- Cooldown is an invalidation policy, not a generic closure policy. Applying it to `EXPIRED` or `DATA_BLOCKED` caused a recovered/new breakout to be suppressed without a false-breakout reason.
- Episode TTL must be based on lack of progress. Measuring only from `created_at` expired the enriched 8039 episode at 09:17 even though it made a new high at 09:14 and accelerated at 09:18; progress now means a new peak or forward stage transition.
- The read-only Replay output is the first concrete way to inspect the signal before Phase 5: `last_observation.state.current_stage`, episode provenance, alert list, and Entry block reasons are all serialized with deterministic digests.

## Phase 5 implementation start

- The user authorized the next implementation phase after G4 passed.
- Existing repository convention is FastAPI in `dashboard/server.py`, server-side assembly in `dashboard/service.py`, and Vanilla JS in `dashboard/static/index.html`; Momentum must extend that surface rather than introduce Sites, Streamlit, or a separate HTML artifact.
- Phase 5 core source is local Replay projection. Browser refresh must only read that projection; it cannot start a Provider, recompute score/stage, or touch Broker/order code.
- The default view must answer: what stage is active, why it triggered, how fresh the evidence is, whether the alert is acknowledged, and why Momentum Entry is waiting/blocked. Evidence Score remains rule evidence, never probability.
- The dashboard skill's portable-artifact packaging workflow is not the selected delivery path because this repository already owns a live FastAPI/static Dashboard. Its general quality contracts still apply: bounded source-backed payload, visible freshness/fixture state, consistent metric definitions, read-only interactions, narrow-width QA, and no hidden fallback data.
- Current `dashboard/server.py` and `dashboard/static/index.html` already contain substantial concurrent changes. Phase 5 must inspect and extend their present contract rather than overwrite them with the older memory snapshot.
- The current Dashboard server owns a provider-backed `DashboardService` plus concurrent local-paper simulation routes. Momentum should use a separate global service and endpoint so `/api/dashboard/momentum` never calls `get_runtime_composition()`, `build_provider()`, `run_scan()`, simulation refresh, or account/order code.
- The enriched Replay symbol is not guaranteed to exist in the current MockProvider Candidate list. Momentum therefore needs its own summary region; a matching Candidate badge can be optional enrichment, not the only access path.
- Polling the local projection is sufficient for G5 and keeps the API smaller than SSE. The server keeps acknowledgement state; browser reload reads pending/all alert state and cannot replay an acknowledged notification.
- Phase 5 will label the source as `fixture`/not live, include dataset id, content SHA-256, session/as-of timestamps, and expose complete backend-computed score/state/provenance. The browser only formats and renders those values.
- Current page uses a viewport-height app shell with one flexible two-column Dashboard grid and switches to document scrolling at 700px. The Momentum section should be a bounded full-width strip above that grid so desktop keeps the existing candidate/detail workspace and mobile can stack naturally.
- Existing client state/polling already separates the provider-backed scan from two-second simulation local reads. Momentum can follow the same visibility-aware polling pattern with its own loading guard and error status, without clearing Kbar cache or rerendering the whole scan.
- The UI consumes server labels, stage, score, rule points, episode transitions, and Entry reasons. Its only numeric work is display formatting/progress width; no signal threshold, Evidence Score, or state transition is recomputed in JavaScript.
- Alert acknowledgement mutates only the in-memory ProjectionStore. The API returns the updated full snapshot, so the card disappears immediately and remains acknowledged across browser reloads while the server process lives.
- Replacing the entire `aria-live` Momentum region on every two-second poll would create repeated screen-reader announcements and reset Candidate DOM unnecessarily. The client now compares the backend projection digest and rerenders only on an actual projection/acknowledgement change.
- Final browser evidence confirms the server-provided 8039 projection is understandable without opening Candidate details: `ACCELERATING`, price/limit/distance/two-minute return, 100/100 rule evidence, episode handoff, lock unknown, and RiskGate block are all visible in one bounded region.
- G5 is satisfied by process-local acknowledgement plus digest-gated polling: one real UI acknowledgement survived reload, unchanged polls preserved DOM identity, and the browser emitted no console errors. This does not imply cross-process persistence or realtime notification delivery.
- The 390px layout has no horizontal overflow; all three Momentum cards are within the viewport. This verifies presentation only and does not close G0 or authorize Phase 6 live subscriptions.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Existing root plan tracks another in-progress feature | Initialized an isolated `.planning/2026-08-18-limit-up-momentum-implementation-plan/` session. |

## Phase 6 implementation start

- The user authorized realtime Shadow, not trading. The new application layer may subscribe to market data and update in-memory projections, but it must not import `trading`, register order callbacks, activate certificates, or expose order commands.
- Because G0 has not promoted single-Quote mode, Phase 6 must instantiate an explicit Tick+BidAsk subscription policy and preserve its smaller symbol capacity. Quote remains qualification/research evidence only.
- The runtime needs a narrow market-data stream port so deterministic fake-adapter tests can exercise admission, acknowledgement, queue overflow, reconnect, and shutdown without Shioaji, credentials, network, FastAPI, or wall-clock sleeps.
- Existing domain contracts should be composed, not duplicated: CandidatePool and SubscriptionManager own coverage allocation; MarketDataIngestor owns normalized ordering/health; FeatureEngine, MomentumSignalEngine, MomentumStateMachine, and MomentumProjectionStore own detector semantics.
- The current `RuntimeComposition` owns the provider-backed Dashboard and local-paper simulation lifecycle and closes simulation before the shared Provider. Momentum Shadow should not silently alter that lifecycle while concurrent simulation work is uncommitted; use a separate composition/application service and integrate it only through an explicit later startup seam.
- There is no existing `runtime/realtime_quotes.py`; the first broad inspection stopped at that missing inferred path. Continue from the actual `runtime/` file list rather than repeating the guessed path.
- `SubscriptionManager` is already a pure decision/lifecycle component: `reconcile()` returns request/unsubscribe operations; only ACKED records count as covered; requested, timeout, and unsubscribe-failure states continue consuming capacity. Phase 6 should execute these decisions through a stream port and feed success/failure back through the existing methods.
- `BoundedMarketEventQueue` already rejects the incoming event on overflow, preserves accepted events, and blocks shared `DataHealth`; `MarketDataIngestor` already owns per-stream ordering, dedupe, reference/session checks, and cumulative-gap behavior. The runtime should schedule/consume these types instead of adding another queue or ordering model.
- `DataHealth` recovery requires a newer reconnect epoch plus explicit resync evidence. A transport reconnect callback alone is not sufficient to mark the detector healthy; Phase 6 must keep evaluation fail closed until subscriptions and required streams are re-established.
- The existing `MarketDataProvider.start_quote_stream()` adapter was added for local-paper execution and emits only `RealtimeQuoteUpdate` with last price or best bid/ask. It drops cumulative volume, VWAP, intraday high/low, aggressor totals, full five-level depth, event identity, sequence, and session metadata, so it cannot be reused as the canonical Momentum feed.
- Do not expand `RealtimeQuoteUpdate` into the Momentum domain DTO: that would couple the trading simulation projection to detector requirements. A dedicated `MomentumMarketDataStream` port should emit canonical `EventEnvelope` values and own subscribe/unsubscribe acknowledgement separately.
- The current Shioaji provider's `sync_quote_subscriptions()` is set-based and synchronous, with paired Tick+BidAsk rollback on subscribe failure. It can inform adapter behavior, but Phase 6 needs per-symbol request results so `SubscriptionManager` can audit acknowledgement/failure without assuming the entire desired set succeeded.
- The Phase 0 capture already contains defensive raw Shioaji parsing for event time, cumulative volume, average price, raw tick type, neutral side totals, and five-level depth. The live adapter should share or reproduce these exact semantics while adding the canonical fields capture did not need: tick volume, intraday high/low, flags, event identity, session, and ingress sequence.
- Aggressor mapping is still unverified, so live Tick events must use `AggressorSide.UNKNOWN` and the Feature context must set `aggressor_mapping_verified=False`. Neutral SDK side totals may be retained only if they are not relabeled BUY/SELL; the first safe runtime version should omit those mapped totals from detector scoring.
- A concurrency issue exists in the current queue/health seam: `queue.put()` advances global DataHealth time before earlier queued events are ingested. If callbacks enqueue event N+1 before the worker processes N, `record_applied(N)` can appear to move backward. Phase 6 must separate queue-observation time from processed-event `as_of` (or otherwise guarantee health time is advanced only by the ordered consumer) before starting a worker.
- Official current Shioaji stock streaming documentation confirms common-stock Tick provides `avg_price`, `volume`, `total_volume`, `high`, `low`, raw `tick_type`, neutral bid/ask-side cumulative totals, and flags; BidAsk provides five price/volume levels and flags. It also explicitly advises avoiding heavy computation in callbacks, matching the normalize-and-enqueue design.
- Official event-callback documentation defines event 1 as connection down, 2 as connect failed, 4 as subscription error, 12 as reconnecting, 13 as reconnected, and 16 as subscribe/unsubscribe success. The callback also carries `info` and `event` strings, so per-symbol ACK correlation must parse/retain those strings defensively rather than invent an SDK enum.
- SDK automatic reconnect does not prove detector continuity. Event 13 should increment a reconnect epoch and trigger resubscription/resync; `DataHealth.recover()` should happen only after the runtime receives explicit new Tick/BidAsk evidence for the required covered symbols.
- Phase 6 now composes CandidatePool, SubscriptionManager, bounded canonical ingestion, FeatureEngine, both Momentum signal families, family-neutral state, blocked EntryOpportunity, projection, and alert deduplication in one long-lived `MomentumShadowRuntime` without importing the execution layer.
- Queue observation no longer advances ordered DataHealth time. Callback N+1 can be accepted before consumer N without creating a false time-reversal rejection; overflow still rejects the incoming event, increments an explicit counter, and blocks health.
- Pair coverage is provider-ACK based. A partial subscribe enters an explicit rollback lifecycle and continues consuming capacity until cleanup ACK; rollback failure is `SUBSCRIPTION_STATE_UNKNOWN` and remains fail closed.
- Disconnect/reconnect and stale-stream recovery share an epoch gate. Re-ACK alone is insufficient; each covered symbol needs a fresh successfully applied Tick and BidAsk after resync begins. `APPLIED_WITH_GAP` Tick data cannot satisfy that gate.
- The Shadow snapshot exposes callback/enqueue/reject/silent-drop counts, queue high-water/overflow, source lag, health reasons, capacity/coverage, ACK latency, missed-reason funnel, signal evaluation/acceleration counts, projection/alert counts, reconnects, runtime errors, and adapter mapping errors.
- The executable Shadow CLI connects Scanner discovery to CandidatePool and the allocation/runtime path. Capacity, headroom, Scanner cadence/count, candidate TTL/admission, queue, and stale thresholds are required arguments; output is JSON status plus deduplicated Momentum alerts.
- The regular market session had already ended when Phase 6 was completed. No after-hours connection was counted as Tick/BidAsk callback evidence, so Gate G6's prospective live-duration criteria remain explicitly incomplete.

## Resources

- `/Users/stevehuang-work/Documents/tw_intraday_trader`
- `/Users/stevehuang-work/.codex/memories/MEMORY.md`
- Shioaji Snapshot: https://sinotrade.github.io/tutor/market_data/snapshot/
- Shioaji Quote-Binding Mode: https://sinotrade.github.io/tutor/market_data/streaming/quote_binding/
- Shioaji Stock Streaming: https://sinotrade.github.io/tutor/market_data/streaming/stocks/
- Shioaji Use Restrictions: https://sinotrade.github.io/tutor/limit/
- TWSE Trading Mechanism: https://www.twse.com.tw/en/products/system/trading.html
- TWSE Operating Rules, Article 63: https://twse-regulation.twse.com.tw/tw/law/DOC01.aspx?FLCODE=FL007304&FLNO=63
- Shioaji Contracts: https://sinotrade.github.io/tutor/contract/
- TPEx Trading Mechanism: https://www.tpex.org.tw/en-us/mainboard/trading/rules/system.html
- Shioaji Scanner: https://sinotrade.github.io/tutor/market_data/scanners/
