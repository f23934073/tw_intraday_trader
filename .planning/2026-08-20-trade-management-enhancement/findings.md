# Findings: Trade Management Enhancement

## 2026-08-20 PR-TM-006 intake

- User approved PR-TM-005 and explicitly moved Simulation/Historical Tick Replay Validation ahead of
  durable guard enforcement and Shadow rollout.
- Existing `market_data.events.EventEnvelope` + `TickEvent` is the canonical `market-event-v1` input;
  it already carries event ordering, exchange/event time, price, cumulative lot volume, average price
  (usable as the frozen VWAP observation), and intraday high/low. PR-TM-006 should consume this type,
  not introduce a second market-event schema.
- `ThesisMonitor` intentionally accepts an upstream-aggregated immutable `ThesisMarketContext`, so
  PR-TM-006 needs a minimal pure reducer from ordered Tick envelopes into that context before invoking
  the already approved engines.
- Existing `ReplayRunIdentity`/`ReplayOutput` contracts already bind manifest digest and exact
  strategy/thesis/exit/guard versions. Replay must reject a policy/version mismatch rather than
  silently reevaluate historical evidence under a newer policy.
- Scope remains decision-chain validation only: no Journal writes, market replay engine changes,
  Shadow, OrderCommand, broker, SELL, Position mutation, wall clock, filesystem, or network.

## 2026-08-20 PR-TM-007 intake

- User approved PR-TM-006 and explicitly selected a Shadow Decision Pipeline before durable guard
  enforcement or any execution work.
- Target flow is live canonical market event -> existing ThesisMonitor -> ExitRecommendation ->
  RiskGate -> immutable Shadow Decision Record.
- Shadow records are observation evidence, not authoritative Trade Management Journal facts. This PR
  must not append Journal, change Position, form OrderCommand, call broker, or send SELL.
- The strongest parity design is one shared event-consumption kernel for Historical Replay and Shadow;
  separate live decision logic would make the parity claim unprovable and risks semantic drift.
- Existing repository memory reinforces the established no-real-money boundary and the required
  sequence of deterministic replay before live-data Shadow.
- The existing live seam is a canonical `EventEnvelope` after `CanonicalMarketDataPipeline` ingest;
  PR-TM-007 can be a standalone consumer and does not need to edit Shioaji callbacks, subscription
  ownership, the shared queue, or `runtime/momentum_shadow.py`.
- A live Shadow session cannot truthfully carry a finalized market manifest digest before the session
  ends. The Shadow run must bind fixed engine/policy/code versions during processing, then compute the
  exact event manifest and construct `ReplayRunIdentity` only at finalize/parity verification.
- Risk evidence can change per event. Shadow consumption should inject an immutable `RiskSnapshot`
  with each canonical event and retain it for replay parity; a single session-wide risk snapshot would
  misrepresent live RiskGate decisions.
- Minimal architecture: extract the approved PR-TM-006 event transition into one incremental decision
  kernel with frozen state. Batch replay loops over that kernel; Shadow calls it once per live event.
  This avoids duplicated thesis/recommendation/risk semantics and avoids O(n-squared) full-session
  reruns on every live tick.

## 2026-08-20 PR-TM-008 intake

- User approved PR-TM-007 and selected durable Shadow evidence before live runtime composition or
  long-running production decision monitoring.
- Persistence must reuse `trading.journal` so the repository keeps one append-order/idempotency/
  checkpoint authority. A separate Shadow database or event store would recreate the ambiguity that
  PR-TM-002 removed.
- Shadow evidence remains observational. Its projection may answer what the decision pipeline emitted
  and whether finalize parity matched, but it cannot activate/close Trade lifecycle, modify Position,
  create recommendation authority, or form execution commands.
- The retention question is now in scope as a contract. Safe v1 behavior should retain immutable
  decision evidence; any future compaction must be verification-preserving and cannot silently delete
  records required by a finalized session digest/checkpoint.
- `JournalRecord` already snapshots canonical UTF-8 bytes and its fingerprint binds record/session/
  kind/time/payload/idempotency. Both in-memory and PostgreSQL repositories consume this unchanged,
  so a sibling Shadow adapter needs no database migration.
- Existing projection recovery convention replays all append-order records, captures the digest at the
  checkpoint sequence, and rejects missing/corrupted checkpoints. PR-TM-008 should mirror it rather
  than invent a Shadow-specific checkpoint store.
- PR-TM-007 `ShadowDecisionRecord` carries a RiskSnapshot digest but not the RiskSnapshot values. The
  durable evidence artifact must include the complete immutable risk values; otherwise historical
  eligibility cannot be audited. The canonical market event itself remains owned by the Market Event
  Journal and is joined by source event ID plus exact serialized-event digest.
- Minimal fact set is two append-only kinds: one decision-recorded fact per post-fill event and one
  session-finalized fact containing manifest/run/parity/final digest evidence. Projection ordering must
  reject decision records after finalization and finalization without the exact recorded chain.
- Retention v1 should be explicit `RETAIN_ALL`: no compaction/deletion API and no silent pruning.
  Future compaction requires a new policy/schema and verification-preserving summary artifact.

## 2026-08-20 PR-TM-009 intake

- User approved PR-TM-008 and selected Live Runtime Composition / Shadow Operation before durable
  guard enforcement or any execution discussion.
- The existing `CanonicalMarketDataPipeline` already guarantees market artifact recording before
  projection ingest and returns the exact `IngestResult`; a runtime wrapper can therefore consume only
  `projection_applied` events without changing callback, queue, recorder, or ingestion ownership.
- `RuntimeComposition` currently owns dashboard/local-paper services and no canonical market pipeline.
  Injecting Trade Management Shadow there would mix unrelated authority. A separate application-level
  operation over an injected canonical pipeline is the smallest clean composition seam.
- Each applied event must obtain an immutable `RiskSnapshot` from an injected provider at processing
  time. Reading a later/global risk state would break live-to-replay parity.
- Decision evidence should append immediately after the Shadow kernel emits a record. Finalization
  appends the session parity artifact, writes the existing Shadow checkpoint, and rebuilds the
  projection to verify restart/audit integrity.
- Duplicate, out-of-order, session-mismatch, invalid, and recorder-failed events must not enter the
  Shadow decision chain. No synthetic event repair is allowed.
- PR-TM-009 remains decision-only and evidence-only: no `OrderCommand`, OrderApplicationService,
  Position mutation, SELL, broker, Shioaji SDK, local-paper handler, filesystem/network, or real money.

## 2026-08-20 PR-TM-010 intake

- User approved PR-TM-009 and selected Shadow Observability / Production Readiness Gate before any
  execution discussion.
- Observability must remain a read model. It can inspect immutable operation counters, pending evidence,
  finalized parity, and durable projection counts, but it cannot call ThesisMonitor, RiskGate, market
  admission, Journal mutation, command routing, or broker code.
- The live operation currently stops dequeuing when a decision-evidence append fails and retains the
  record in memory. PR-TM-010 needs explicit counters and injected-time evidence for failure start,
  oldest pending age, recovery count, and recovery duration; wall-clock reads would break tests.
- Evidence completeness is measurable per finalized session as durable decision count versus emitted
  decision count plus the required finalization artifact. A pending record is not lost evidence, but a
  finalized session must have zero pending and exact durable counts.
- Parity readiness is a multi-session ratio, not a boolean copied from the latest session. The policy
  must bind minimum finalized sessions, minimum decision records, minimum parity rate, and zero lost/
  pending evidence requirements.
- `READY` is evidence classification only. It must not mean execution is enabled and must not produce
  an OrderCommand, feature flag mutation, broker permission, or automated transition.
- Minimal runtime instrumentation belongs inside `LiveTradeManagementShadowOperation`: processed and
  applied/rejected counts, durable/pending decision counts, injected-time failure/recovery timing, and
  finalized parity. It must not alter `ShadowDecisionRecord` or Journal fact schemas.
- A separate sibling observability module should own immutable metric/readiness contracts and the pure
  multi-session evaluator. This keeps metrics policy out of the live operation and avoids imports from
  UI, broker, simulation, or execution modules.
- Readiness reports must be deterministic over an unordered set of unique session metrics and bind the
  full policy values in their input digest. Reports explicitly carry `execution_enabled=False` even
  when status is `READY`.

## 2026-08-20 PR-TM-011 intake

- User approved PR-TM-010 and selected Extended Shadow Validation / Operational Readiness before any
  decision-to-command or execution discussion.
- PR-TM-010 readiness proves aggregate metric thresholds, but it does not identify the live provider,
  provider version, connection session, market date, complete-session coverage, or operational drills
  behind those metrics. PR-TM-011 must bind those facts in a separate immutable validation artifact.
- Real market evidence cannot be manufactured by unit tests. Test-source evidence must be explicitly
  classified and rejected by a production-evidence policy even when all deterministic tests pass.
- Recovery and divergence need distinct drill evidence: a recovery drill proves fail-closed backlog
  handling and durable resume; a divergence drill proves detection and investigation workflow. A
  production validation report may require both without modifying the live Shadow operation.
- The minimal clean boundary is a pure evaluator over PR-TM-010 readiness reports plus validation
  session/drill evidence. It must not write Journal records, call a broker, create commands, mutate
  positions, or influence the decision kernel.

## 2026-08-20 PR-TM-012 intake

- User approved PR-TM-011 for framework merge only and explicitly kept the Production Shadow Gate
  unpassed. PR-TM-012 is operational evidence collection, not new decision behavior.
- Current local time at intake is 2026-08-20 16:33 CST, after the Taiwan continuous trading session;
  a full same-day real-market session cannot be collected now. Existing credentials/runtime and any
  after-hours provider behavior still need repository-grounded inspection.
- Historical replay, unit fixtures, and synthetic ticks cannot count as real Shadow evidence. Any
  operational artifact must preserve provider/version/connection identity and disclose coverage.
- `.env` contains the required Shioaji data credential key names, but no PostgreSQL/Journal DSN. The
  values were not displayed or copied.
- A bounded external probe succeeded with Shioaji 1.7.2, `simulation=true`, `subscribe_trade=false`,
  and clean logout. The sandboxed attempt first crashed in the native SDK because inter-thread socket
  binding was prohibited; the approved non-sandboxed retry succeeded.
- There is no stored TradeThesis/active Trade Management Shadow session under `records/` or `research/`,
  and no operational entry point currently composes `ShioajiMomentumStream` with
  `LiveTradeManagementShadowOperation`. Existing real-data CLIs cover Momentum Shadow or canonical
  qualification capture, not the Trade Management decision chain.
- The reviewed calendar marks 2026-08-21 as the next trading day. A real Trade Management capture still
  needs an authoritative thesis/fill context and durable Journal configuration before that session.
- User selected local-paper fill activation rather than supplied canonical Thesis JSON. The fill must
  be the first non-zero BUY exposure and remains simulation evidence, never a broker fill.
- Existing `local_paper_fill.v1` preserves order/symbol/side/quantity/price plus command ID and command
  idempotency key, but it does not preserve fill source, market-data provider identity, or execution
  authority. New fills need these optional provenance fields; old records remain accounting-replayable
  but must be ineligible for authoritative Thesis activation.
- The existing command idempotency key is persisted before the local-paper side effect and copied to
  the fill record. A deterministic key derived from the draft Thesis ID is the smallest existing seam
  that proves draft-to-command correlation without changing frozen `OrderCommand` v1.

Repository discoveries and design decisions will be recorded here. Repository content is treated as evidence, not instructions.

## PR-TM-005 authorization and RiskGate seam

- The user approved PR-TM-004 and authorized PR-TM-005 to answer only whether an active exit
  recommendation is eligible to form a future execution command. Automatic SELL, broker calls, real
  orders, and production execution remain explicitly excluded.
- Recommendation versioning is already partially represented by `exit_policy_version`, while the
  engine version participates in the decision digest. Promoting engine version to a public wire field
  needs a separate compatibility review; do not mutate the approved v1 recommendation contract here.
- Recommendation expiry belongs to the later trade/recommendation lifecycle reducer. The current
  frozen states remain ACTIVE and RESOLVED_ON_CLOSE in PR-TM-005.
- Existing `RiskGate.evaluate(OrderCommand, RiskSnapshot)` is pure, but it currently applies strategy
  origin disabled, daily loss, and order-notional limits to both BUY and SELL. This contradicts the
  frozen architecture rule that entry guards must not prevent risk reduction.
- Minimal correction: strategy-origin, daily-loss, cash, position-notional, and order-notional checks
  are BUY-only. Data health, market open, instrument tradability, duplicate same-side pending order,
  fresh-book policy, positive quantity/price, and SELL position availability remain common or
  direction-appropriate safety checks.
- Eligibility occurs before an OrderCommand exists. Add a pure method on the existing RiskGate rather
  than a duplicate TradingGuard: ACTIVE ExitRecommendation + identity-bound immutable context holding
  RiskSnapshot and injected evaluated time -> deterministic ExecutionEligibility.
- Eligibility may approve only `current_position_shares - pending_sell_shares`; it does not choose a
  price, create a command/idempotency key, append Journal evidence, or call a handler.
- Daily-loss/cooldown account guard state is not implemented in this PR. Only the already-existing
  daily-loss field is verified as BUY-only; consecutive-loss projection, cooldown, pending-fill
  quarantine, durability, and restart behavior remain later guard phases.
- Eligibility identity binds the full policy values, not only `policy.version`, and uses the shared
  canonical Decimal encoder for cash/PnL/limits. Equal Decimal scale variants therefore cannot create
  different eligibility evidence, while an improperly reused policy version with changed values still
  produces a different digest.
- `same_side_pending_order` remains the authoritative duplicate-order signal. `pending_sell_shares`
  reduces the eligible quantity; callers must set the duplicate flag when an existing pending SELL
  means no second command may be formed. This PR does not infer order lifecycle from aggregate shares.
- Final version audit found policy version alone was visible on the eligibility output. The artifact
  now also carries and digests the existing `RISK_GATE_VERSION`, keeping implementation and policy
  version boundaries explicit without changing the approved recommendation wire.

## PR-TM-004 authorization and minimal contract

- The user approved PR-TM-003 and authorized PR-TM-004 as a pure mapping from `ThesisEvaluation` plus
  position context to `ExitRecommendation`, explicitly excluding SELL, broker, Order, Position
  mutation, and RiskGate behavior.
- The first non-blocking review suggestion is already covered: `ThesisReasonCode` is typed and includes
  breakout loss, VWAP loss, expected-behavior expiry, data failures, and invalid latch. PR-TM-004 should
  map these typed reasons to the frozen `ExitReason`; it must not add free-form messages or rename the
  approved PR-TM-003 enum.
- Frozen PR-TM-001 contracts already require every recommendation to reference first/latest
  `ExitDecision` IDs. Therefore the pure engine must produce an auditable decision together with the
  optional recommendation, rather than manufacture an orphan recommendation ID.
- `VALID`, `WARNING`, and `INSUFFICIENT_DATA` map to a HOLD `ExitDecision` and no new recommendation.
  Only `INVALID` maps to EXIT. `EXPECTED_BEHAVIOR_EXPIRED` maps to `TIME_DECAY`; hard invalid reasons
  map to `THESIS_INVALID`.
- A caller-supplied immutable position context must own canonical EXIT_DECISION time, remaining open
  quantity, trade/thesis/session identity, lifecycle state, policy version, and any current active
  recommendation. The engine must not call Clock or read/mutate the legacy Position object.
- Repeated INVALID evaluations reuse the deterministic per-trade recommendation identity, preserve
  first-trigger provenance, update latest evidence monotonically, and union typed reasons in stable
  priority order. This satisfies one active recommendation without Journal mutation.
- Registry mapping, price-risk/take-profit adapters, backtest/local-paper read models, persistence,
  RiskGate, command routing, and execution remain later work despite the older roadmap's broader
  Phase 3 wording.
- The existing Trade Management Journal projection requires recommendation updates to remain ACTIVE,
  advance monotonically in `updated_at`, preserve every previously triggered reason, and actually
  change the snapshot. The pure engine should therefore return the existing immutable recommendation
  unchanged for an exact retry; the future application layer can skip appending a no-op update.
- Decision identity must not hash the current recommendation snapshot. It should bind only the current
  ThesisEvaluation, immutable open-position facts, canonical decision time, and policy version; this
  keeps an exact retry stable before and after the first recommendation was created.
- The frozen `ExitRecommendation` has no urgency field. PR-TM-004 must not extend that approved wire
  contract merely to mirror an illustrative example; urgency/execution policy belongs to a later
  separately reviewed contract.
- Source self-review found an explicit v0.4 idempotency rule that is stricter than the first green
  implementation: when a new INVALID market event does not add or reprioritize reasons, the active
  recommendation snapshot must remain byte-for-byte unchanged. Only the per-event ExitDecision is new;
  latest evidence belongs in a bounded projection/metrics until a material recommendation change.
- The pure result therefore needs an explicit `recommendation_changed` flag. An EXIT decision may
  legitimately carry the unchanged current recommendation, whose `latest_decision_id` still points to
  the last material update. A future Journal adapter must append only when this flag is true.

## Repository state and existing boundaries

- The worktree already contains broad, unrelated freshness, canonical-market-event, and institutional-data changes. This task must not edit or clean them.
- There is no repository `AGENTS.md` in the current checkout.
- Current product flow in `app.py` is a one-shot decision scan. It creates a fresh in-memory `PositionManager`, adds a hard-coded demonstration position, evaluates `StopLossRule` and `TakeProfitRule`, and emits HOLD/EXIT presentation data. It does not own fills or durable positions.
- `Position` contains only `symbol`, `entry_price`, and `quantity`; `PositionManager` is a symbol-keyed in-memory dictionary with add/remove/get operations.
- Current `ExitRule.should_exit(position, stock) -> bool` loses status, reason, evidence, timestamps, data-health, and priority information. This interface is not sufficient for thesis monitoring.
- `MarketDataStore` retains only the latest `StockData` snapshot. It cannot prove “new high within 5 minutes”, volume expansion across a window, or behavior since entry without a bounded history/feature input.
- Candidate evidence is available as matched rule names; Buy Score retains per-rule score breakdown. A thesis must snapshot the exact entry decision evidence rather than later recomputing it from the latest market snapshot.
- The local paper simulator is a separate in-memory source of fills, positions, realized PnL, orders, and realtime Tick/BidAsk state. It is the only currently implemented runtime that can supply actual fill-derived entry price/time and realized trade outcomes.
- Backtest already has Stop Loss, Take Profit, ATR Stop, Time Stop, End-of-Day, and death-cross exit strategies, plus configurable exit priority. The new thesis/time exit contract should be reusable or mapped into the backtest kernel to avoid live/backtest semantic drift.
- Existing project boundary remains local paper/data-only. No broker order API or real-money execution is authorized by this plan.

## Early design consequences

- Do not attach thesis evaluation directly to the legacy three-field `Position` as the only source of truth.
- Separate immutable entry thesis/config from mutable thesis-monitor state and from fill-derived position/accounting state.
- Replace boolean-only thesis decisions with a structured evaluation containing status, reason codes, evidence, evaluated time, data-quality state, and an optional exit action.
- Time rules must use an injected exchange/session clock and explicit inclusive/exclusive boundary semantics; never call wall-clock time inside domain rules.
- Trading Guard belongs before creation/acceptance of a new BUY command or intent. It must not block SELL/exit actions, emergency liquidation, or reconciliation.

## Existing execution and audit foundation

- `trading.risk` already defines `OrderCommand`, `RiskPolicy`, `RiskSnapshot`, `RiskDecision`, and a pure `RiskGate`. It already enforces `max_daily_loss`, but currently applies entry-style blockers to every side; direction-specific guard semantics are required so daily-loss/cooldown rules never prevent a risk-reducing SELL.
- `trading.application.OrderApplicationService` journals every command and complete risk snapshot before calling the local-paper handler. Thesis/guard evidence should extend this path rather than add an unaudited side channel.
- `trading.journal` already supplies timezone-aware append-only records, idempotency, replay order, Postgres/in-memory adapters, and projection checkpoints. The proposed `TradeEvent` should therefore be a set of versioned Journal payload contracts/kinds, not a second event store.
- `trading.local_paper.LocalPaperProjection` reconstructs cash, symbol positions, and realized PnL from fill records. It does not yet model `trade_id`/`position_id`, per-trade closed PnL, or a lifecycle boundary needed to count consecutive losing trades correctly.
- `simulation.application.LocalPaperCommandService` is now the actual web command facade and uses an injected `Clock`. Automated strategy origin is deliberately disabled. Initial thesis-exit integration must remain decision-only or manual-confirmed; automatic SELL routing needs a separate explicit activation gate.
- The backtest `DecisionAggregator` already supports deterministic strategy priority and retains complete strategy evaluations. A common structured exit evaluation/priority contract should be shared or mapped at an adapter boundary rather than replacing the backtest kernel.
- Momentum already has a cooldown concept, but it is per-symbol signal-episode suppression. It is not an account/session-level psychological trading guard and must not be reused as if the semantics were identical.

## Required semantic clarifications resolved for the plan

- `entry_time` means the opening fill timestamp, not order submission or signal time. Keep `signal_at`, `decision_id`, `order_id`, and `filled_at` as separate provenance.
- A thesis is immutable after creation. Evaluator progress such as highest price since entry, condition states, warning time, and last event sequence belongs in a replayable mutable projection.
- A missing/stale/out-of-order input must produce `INSUFFICIENT_DATA`/`BLOCKED`, not silently `VALID` or `INVALID`. Emergency price protection remains a separate risk path.
- The first supported thesis template should be a versioned ORB/breakout template with typed thresholds. Do not interpret arbitrary reason strings as executable rules.
- One market event produces at most one exit decision. When several exits trigger, preserve all reasons but choose one primary reason via deterministic priority.
- Trading Guard loss streaks are updated only when a position lifecycle fully closes. Partial SELL fills do not count as separate losses.
- Daily loss and cooldown are scoped to the `Asia/Taipei` trading session. State is rebuilt from the Journal; process restart must not clear a guard in a persistent mode.
- Guard activation blocks new BUYs from manual and future strategy origins, allows SELL/cancel/reconciliation, and must prevent already-pending BUYs from filling unnoticed (cancel or explicitly quarantine them with Journal evidence).

## Final plan decisions

- Use the existing experimental `opening_range_breakout_entry_v1` as the first executable thesis mapping; Candidate/Buy Score evidence remains supporting evidence and is never reinterpreted as ORB.
- Add a Phase 0 contract freeze before implementation because new-high, volume-expansion, VWAP confirmation, and five-minute boundaries need exact formulas and source capabilities.
- Add `trade_id` and a v2 fill event before Trading Guard because per-symbol aggregate PnL cannot define consecutive losing trades.
- Require a common terminal fill sink for immediate and quote-triggered delayed fills.
- Keep local-paper thesis exits decision-only. Automated SELL is not authorized by this plan.
- Require a second guard check immediately before a pending BUY fill; command-time RiskGate alone is insufficient.
- Gate enforcing Trading Guard on a durable Journal; in-memory mode is explicitly preview-only.
- Preserve the existing canonical market-event plan as the realtime data dependency and prohibit a third temporary quote queue/history store.

## User review disposition for v0.3

- Accepted: make thesis logic version explicit so historical trades remain attributable after strategy changes.
- Accepted: add a stable `ExitReason` enum for aggregation and reporting; free-form text remains display detail only.
- Accepted: elevate Historical Tick／Replay from a general parity statement to a required input contract and dedicated Phase 5 validation gate.
- Accepted: split pure Thesis Monitor status evaluation from Exit Recommendation creation.
- Accepted: keep Journal/lifecycle integration before all monitor and recommendation work.
- Clarified: thesis invalidity remains owned by ThesisMonitor/ExitDecisionEngine. RiskGate consumes the resulting command provenance and decides execution eligibility; it must not become a strategy/thesis evaluator.
- Clarified: “Production rollout” in this repository means controlled decision-only Shadow rollout. It does not authorize broker orders, auto SELL, Shioaji Simulation orders, or real money.
- Dashboard remains P2 and will be included in the Simulation Validation phase after the server projection is stable.

## v0.3 contract additions

- Three version axes are explicit: payload schema, entry strategy, and thesis/monitor logic.
- `ExitReason` is a wire/audit enum; localization and detail text do not change event identity.
- Partial exits retain per-fill `ExitLeg` records plus initiating and closing reasons rather than collapsing the trade to one free-form reason.
- Historical Tick Replay requires an immutable canonical manifest, source ordering, SHA-256 evidence, ReplayClock, no network access, and explicit gap/insufficient-data handling.
- Phase order is now Contract → Journal/Lifecycle → Monitor Status → Exit Recommendation → RiskGate/Guard → Simulation/Tick Replay → Controlled Shadow.
- The next review artifact is the Phase 0 checklist embedded in section 20 of the implementation plan.

## User review disposition for v0.4

- Accepted: freeze timestamp roles. Canonical market `event_at`, ingress `received_at`, fill
  `filled_at`, and Journal append order have different meanings and may not be substituted.
- Accepted: one active exit recommendation per trade lifecycle. The v0.3 hash containing every
  `source_event_id` is insufficient because repeated INVALID ticks could create new identities.
- Accepted: make deterministic replay a formal Phase 0 contract, including immutable input digest,
  config/code identities, ReplayClock, deterministic IDs, stable ordering, and exact output digest.
- Accepted: ThesisMonitor is pure and has no Position, Order, RiskState, Journal, projection, or
  adapter mutation capability.
- Refined: do not collapse signal, order, fill, and position states into one `TradeLifecycleState`.
  Freeze linked Decision, Order, and Trade state machines with correlation IDs.
- Updated: the revised Phase 0 checklist is approved to start PR-TM-001. Checklist items remain
  incomplete until contract, fixture, and test evidence exists; this plan-only turn does not start it.

## PR-TM-001 implementation intake

- Explicit authorization received to start the Contract Freeze implementation.
- Current branch is `main`; no branch creation, commit, or push was requested.
- The worktree remains broadly dirty with unrelated canonical-market-event, freshness, institutional,
  root planning, and `market_data/replay.py` changes. PR-TM-001 must not edit, stage, or clean them.
- No applicable repository `AGENTS.md` exists in this checkout.
- Prior repository evidence reinforces the local-paper decision-support/no-real-money boundary and the
  required sequence of contracts before deterministic replay and behavior integration.
- To avoid overlap, Replay determinism must be expressed as new immutable contract/serialization
  types and fixtures only; the already-modified `market_data/replay.py` is out of scope.
- Repository contract style is Python 3.11 `@dataclass(frozen=True)` plus `StrEnum`, explicit
  `__post_init__` validation, timezone-aware datetime enforcement, Decimal-as-string JSON, sorted-key
  canonical serialization, and SHA-256 fingerprints/digests.
- Existing `trading.risk` and `trading.journal` already expose pure domain contracts; PR-TM-001 can
  add sibling contract modules without changing these files or runtime composition.
- `runtime.clock.SystemClock` is the only current wall-clock implementation. New contracts must carry
  authoritative timestamps and source metadata but must not call it or `datetime.now()`.
- The in-progress canonical market contract uses separate aware `event_at` and `received_at`, strict
  envelope/payload identity matching, non-negative ingress sequence, and a golden JSON round-trip test.
  PR-TM-001 should follow the same semantic split while remaining in new `trading` modules.
- Contract tests in this repository prefer golden fixtures plus exact round-trip equality and rejection
  of unknown schemas/fields. This is suitable for freezing the trade-management serialization format.
- The approved v0.4 contract requires three separate state enums, pre-fill correlation without a
  `trade_id`, first-fill timestamp activation, stable `ExitReason`/`ExitLeg`, one recommendation ID per
  trade liquidation cycle, and Replay identity/output digests; none of these require runtime wiring.
- Existing canonical serializers do not reflect over dataclasses: they enumerate exact fields, reject
  missing/unknown keys, use ISO timestamps and Decimal strings, and preserve byte-stable sorted JSON.
  PR-TM-001 should use the same explicit approach for a small set of top-level trade contracts.
- Existing lifecycle code stores allowed progression in immutable enums/transition checks and keeps
  state mutations in copy-returning methods. For this PR, frozen transition tables are enough; no
  lifecycle service/reducer is needed.
- Chosen minimal implementation shape: `trading/trade_management.py` for immutable contracts,
  allowed-transition tables, validation, and deterministic ID derivation; and
  `trading/trade_management_serialization.py` for byte-stable canonical JSON only.
- Serialization readers and Journal/runtime adapters remain Phase 1/PR-TM-002. PR-TM-001 freezes
  writer output with golden fixtures; it does not consume or mutate runtime state.
- The timestamp value object will carry role, aware `Asia/Taipei` value, microsecond precision,
  source enum, and non-empty source identity. Model-level validation restricts fill timestamps to
  canonical market event, injected simulation clock, or future broker event sources.
- Expected/invalid thesis conditions will be typed immutable specs. They encode comparison direction,
  baseline/reference, sample/confirmation counts, and observation/warning windows, but perform no
  market evaluation.
- Recommendation, trade, thesis, and per-event exit decision IDs will be SHA-256-derived from frozen
  identity inputs. Recommendation identity intentionally excludes market event and price so repeated
  INVALID ticks resolve to the same `recommendation_id`.
- Contract self-review found four contract-only hardening items before regression: expose the approved
  `ThesisStatus` enum, require canonical ORB condition ordering rather than set equality, bind a Replay
  divergence's actual digest to the serialized output, and correct the illustrative partial-exit PnL.
- AST dependency tests confirm the new modules do not import runtime, simulation, market-data,
  position, or dashboard packages. The domain module contains no `datetime.now()` or execution class.
- Section 20 currently mixes PR-TM-001 contract evidence with PR-TM-002+ Journal, Monitor, Guard, and
  runtime gates. Requiring every old checkbox for PR-TM-001 would contradict the user's strict
  no-behavior scope. The document should separate a checked PR-TM-001 DoD from explicitly deferred
  downstream gates instead of falsely checking unimplemented behavior.
- PR-TM-001 finished with only new Trade Management contract/serializer/test/fixture files plus the
  approved plan/planning records. No pre-existing product or dirty-worktree file was modified.
- Final verification: 22 targeted tests passed; the full repository suite passed with 550 tests and
  1 skip; compileall, whitespace, `git diff --check`, and dependency/capability scope checks passed.

## PR-TM-002 authorization and scope

- The user marked PR-TM-001 `APPROVED — Contract Freeze Passed` and authorized the next Journal
  integration phase.
- PR-TM-002 has one responsibility: persist frozen Trade Management contracts as canonical Journal
  records and rebuild the same state from those records.
- It must not introduce ThesisMonitor, thesis/exit/risk decisions, broker calls, automatic/manual SELL
  routing, or changes to the market-data Replay engine.
- The user requested two non-blocking contract policies: old schemas must remain replayable through
  explicit versioned readers/migrations, and existing enum names/meanings must never be renamed or
  reinterpreted.
- Existing repository evidence supports using `trading.journal` as the only event store and keeping
  this phase local-paper/no-real-money; a second Journal or Replay infrastructure would violate the
  approved architecture.
- Session catchup confirmed that the last completed work was PR-TM-001 and that no code after its
  approval had yet been synchronized into this isolated plan.

## PR-TM-002 repository integration seam

- `trading.journal` already owns session registration, canonical payload fingerprints, append-order
  sequence numbers, record/idempotency conflict detection, repository replay, and projection
  checkpoints. PR-TM-002 should consume this protocol unchanged rather than add storage APIs.
- `trading.local_paper` demonstrates the repository convention: one versioned record kind, a strict
  record reader, a projection that accepts only increasing Journal sequences, a deterministic digest,
  and optional checkpoint verification.
- The frozen Trade Management serializer currently has canonical writers but no readers; PR-TM-002
  therefore needs explicit v1 decoding for the four Journal aggregates only, not a generic reflective
  deserializer or behavior engine.
- The minimal Journal representation is a versioned record whose payload contains the exact canonical
  contract JSON plus its SHA-256 digest. Replay must verify both the record kind/contract type and the
  digest before reconstructing state.
- A dedicated Trade Management projection can safely ignore unrelated Journal kinds while still
  advancing the append sequence. It should reconstruct immutable draft, active thesis,
  recommendation, and closed-outcome snapshots only.
- Journal event kinds should preserve lifecycle facts (`drafted`, `activated`, recommendation
  `created`/`updated`/`resolved`, and `trade_closed`) instead of embedding strategy evaluation logic.
- The aggregate object graph required by replay is finite and explicit: `TradeThesisDraft` contains
  typed evidence, expected-condition specs, and invalid-condition specs; `TradeThesis` embeds that
  draft; recommendations and outcomes use only exit enums, timestamps, decimals, and exit legs.
  This permits small exact-field decoders that reconstruct through dataclass validation.
- The projection must key drafts/theses by `thesis_id`, recommendations by `recommendation_id`, and
  outcomes by `trade_id`. Activation must match its previously journaled draft; recommendation events
  must match the active trade/thesis; closure must match the active trade. These are replay-integrity
  checks, not trading decisions.
- The architecture document's older PR-TM-002 label still bundles fill-v2 and delayed-fill runtime
  wiring. The user's latest approved scope is narrower and takes precedence: this PR is Journal
  persistence/reconstruction only. The roadmap text must be corrected so those runtime items remain
  explicitly deferred rather than silently implemented.
- The project runs Python 3.11 and existing tests already define Journal retry/conflict/checkpoint
  semantics. New tests should reuse those public contracts and avoid modifying `trading.journal`.
- Compile checks and the existing Journal/local-paper/order application regression subset pass without
  modifying those modules, confirming the sibling adapter is compatible with the current foundation.
- Self-review found two contract hardening items before full regression: decimal strings should be
  canonical on direct decode (not merely when wrapped by Journal fingerprint verification), and the
  newly journaled draft envelope should be bound to the already-golden nested draft representation.
- A v1 projection must not silently ignore a future Trade Management kind; it now fails closed for
  unknown thesis/recommendation/trade-close versions while still ignoring truly unrelated Journal
  domains.
- `TradeOutcome` lacks an embedded `session_id`, so replay must lock the projection session from its
  Journal envelope. Recommendation resolution also needs to match the final outcome fill ID/time;
  otherwise a syntactically valid but inconsistent close could be reconstructed.
- Final PR-TM-002 evidence: 37 targeted tests and the full 575-test repository suite pass (1 skip).
  The scoped status consists only of the PR-TM-001/002 Trade Management modules, tests, fixtures,
  architecture document, and isolated planning files; no existing execution module was changed.

## PR-TM-012B PostgreSQL evidence preflight

- The configured DSN key is exactly `PostgreSQL_DSN`. Configuration loaders for the operational
  capture must support that deployed key explicitly; logs and artifacts must never include its value.
- The dedicated target was verified empty before mutation using a redacted target fingerprint. The
  existing Journal migration creates only `journal_sessions`, `journal_records`, and
  `projection_checkpoints`; the migration runner additionally owns `journal_schema_migrations`.
- Bootstrap completed with `001_journal.sql` tracked and all authoritative evidence tables still at
  zero rows. This establishes storage readiness only, not a real Shadow evidence session or gate pass.
- The current virtual environment does not include the optional PostgreSQL driver, although system
  Python has psycopg 3.2.3. The eventual capture entry point must fail closed with an actionable
  optional-extra error or the project environment must install `.[postgres]` before the live run.
- A full raw market session and an active-Thesis Shadow interval have different legitimate start
  times. The raw canonical capture may begin at market open, but live Thesis decisions cannot begin
  before the authoritative paper BUY fill. Evidence must preserve both boundaries and must never
  backfill pre-fill events as if they were live decisions.
- The smallest safe runner is an outer callback adapter over the existing live Shadow operation. It
  receives an immutable PaperFill activation, binds the stream identity, waits for paired Tick/BidAsk
  ACK, and leaves all decision/persistence semantics with the approved operation and Journal ports.
- Events arriving before paired ACK are outside the decision boundary. They are counted for audit but
  not admitted; the Shadow coverage clock starts at the paired ACK, not at callback installation.
- Repository search found no production `TradeThesisDraft` builder. The only direct constructor is in
  `tests/trade_management_builders.py`; product code only reconstructs a previously serialized draft.
  CandidateEngine and BuyScoreEngine do not own the frozen ORB entry evidence or expected/invalid
  condition versions. Operational composition therefore needs a separately reviewed live entry-
  decision-to-draft authority before a real paper fill can activate a Thesis.
- PR-TM-012B1 resolves that authority with two transforms instead of editing discovery/scoring:
  explicit caller-selected score/rules/evidence become a content-bound `LiveEntryDecision`, then one
  versioned `LiveThesisDraftPolicy` produces the existing TradeThesisDraft contract.
- EntryDecision canonical ordering sorts matched rule codes and evidence IDs before identity. Its
  input digest binds builder version, session/symbol/side, strategy/version, canonical timestamps,
  score, market-context digest, and every typed observed/threshold evidence value.
- Thesis policy identity must equal the expected-behavior policy ID already persisted by
  TradeThesisDraft. This avoids an unobservable wrapper policy version that replay could not recover.
- PR-TM-012B2 must treat the local-paper fill Journal as an observed source and the Shadow PostgreSQL
  Journal as a distinct evidence authority. Reusing one repository/session would mix
  `LOCAL_PAPER_SIMULATION` and `TRADE_MANAGEMENT_SHADOW` session semantics.
- Correlation is already frozen by `paper_thesis_entry_idempotency_key(draft)`. The observer should
  filter by that persisted command key, require exactly one fill, then reuse PR-TM-012A validation
  rather than duplicate fill semantics.
- BuyScore breakdown is evidence, not entry authority. A standalone adapter can freeze total score,
  sorted rule names, scores, and maxima while leaving matched-rule classification and decision
  creation with the explicit caller.
- Local-paper fill `occurred_at` is the canonical activation/capture anchor and can differ from the
  EntryDecision time. Tests must move the capture window and ACK to the actual fill instead of
  weakening the live runner's fill-window checks.

## PR-TM-012C0 pre-market readiness

- Existing components already cover decision kernel, durable evidence, observability, extended
  validation, live callback admission, fill observation, and operational composition. C0 should add
  one outer preflight/rehearsal contract and CLI, not another Shadow or replay engine.
- The current repository has no Trade Management live/preflight command. `run_momentum_shadow.py` is
  a separate momentum workflow and must not be reused as evidence for this gate.
- The configured PostgreSQL evidence target was intentionally left empty. C0 database validation must
  remain read-only; the existing integration test drops Journal tables and therefore must never be
  pointed at this formal target.
- The virtual environment may lack the optional psycopg driver even when system Python has it. The
  preflight report needs a typed blocker and must not fall back silently to a different interpreter.
- A C0 rehearsal may use reviewed historical canonical ticks and in-memory/failure-injection adapters,
  but its manifest/report must explicitly state `qualifying_real_session=false` and cannot advance the
  Production Shadow Gate.
- `ShioajiMomentumStream.connect_from_env()` is already data-only: it loads credentials, uses the
  configured simulation mode, calls login with `subscribe_trade=False`, and exposes a redaction-safe
  environment identity. C0 should probe this existing adapter rather than import the SDK in core code.
- Existing validation contracts already distinguish `LIVE_MARKET`, `TEST_FIXTURE`, and
  `HISTORICAL_REPLAY`. The rehearsal result should reuse that semantic boundary and must never emit a
  live-source validation session.
- The operational runbook still says the B2 composition is pending. C0 must update this stale status
  and add concrete preflight, rehearsal, database-read-only, and next-session launch procedures.
- The reviewed calendar port exposes `is_trading_day()` and a SHA-256 source digest but not market
  hours; C0 may freeze the already-established regular window 09:00-13:30 Asia/Taipei in its own
  manifest while binding the reviewed calendar digest.
- PostgreSQL migration `001_journal.sql` defines exactly three authoritative tables. A safe formal-DB
  preflight can use a read-only transaction to verify migration registry, table set, and zero row
  counts; it must not call `apply_migrations()` or the integration fixture that drops tables.
- The prior preflight artifact is stale by design: it records DSN/draft/live-entrypoint blockers that
  have since been resolved. C0 should emit a new versioned artifact rather than rewrite the old fact.
- The executed C0 probe proves the formal PostgreSQL target can be inspected with
  `transaction_read_only=on`; it has PostgreSQL major 17, exactly the four expected schema tables,
  migration `001_journal.sql`, and zero rows in all three authoritative evidence tables.
- The sealed provider evidence is `shioaji:1.7.2:simulation=true`, successful login/logout, and
  `subscribe_trade=false`. Credentials are represented only by logical key-presence labels.
- `READY_FOR_SESSION` is intentionally narrower than Production Shadow readiness: the C0 report and
  rehearsal both reject `qualifying_real_session=true`, and the artifact keeps the gate NOT PASSED.

## 2026-08-21 partial-session diagnostic

- At 09:11 Asia/Taipei the regular session had already started. Any evidence collected today must be
  labelled partial/non-qualifying and cannot satisfy full-session coverage.
- `LiveShadowCaptureRunner` and `LiveTradeManagementOperationalComposer` are library-level adapters,
  not an executable C1 entry point. Composition still requires a caller-provided authoritative
  `LiveEntryDecision` and an already-journaled correlated local-paper BUY fill.
- The runner correctly cannot create a Thesis, fill, order, Position, or broker action. The partial
  diagnostic may verify provider connectivity, canonical live capture/replay, PostgreSQL readiness,
  and fixture-backed Shadow/recovery/parity contracts, but must not manufacture the missing entry/fill
  authority merely to obtain Shadow decision records.
- The five-minute real 2330 capture connected and received paired subscription ACK, then persisted
  1,855 records before finalizing `INCOMPLETE`. Its consumer failed because `DataHealth` was advanced
  to the post-bootstrap `ready_at`, while the first admitted callback envelope retained a slightly
  earlier `received_at`. This is a real callback/admission-boundary race; fail-closed behavior
  prevented replay from treating the session as valid.
- The separate rehearsal failure is test-only: replacing a historical event timestamp without also
  replacing its `session_date` now violates the event contract. It does not explain the live capture
  failure and should remain separately classified.

## TM-012C preflight blocking-fix design

## 2026-08-24 live callback data-quality diagnostic

- The scheduled 30-minute passive opening capture `ldev-20260824T085711-open-d21e86ef` preserved
  35,118 records but finalized `INCOMPLETE`: 17,472 canonical events were accepted and 87 rejected.
  It is diagnostic-only evidence and must not be rewritten or replay-qualified.
- The failure differs from the repaired Tick/BidAsk ingress ordering race. Real callbacks raised
  `positive field unavailable: high` and `BidAsk event has no valid price levels`; the adapter stores
  those as callback errors, and the capture correctly fail-closes when callback errors exist.
- The repair must not synthesize intraday high/low from close or manufacture book levels. First
  establish whether the Shioaji payload has an alternate authoritative field; otherwise distinguish
  an unrepresentable observation from a fatal runtime failure while preserving auditable rejection.

- `ShioajiMomentumStream._next_receipt()` currently clamps a regressed clock to
  `_last_received_at`; this mutates the observed timestamp and conflicts with the reviewed rule that
  raw provider observation time must remain evidence rather than be repaired with an epsilon/clamp.
- Tick and BidAsk each enter `_record()` independently. `_next_receipt()` is locked, but envelope
  mapping and the external handler call occur after that lock is released. A slower callback can
  obtain an earlier provider sequence/time yet reach the canonical queue after a faster later callback,
  which explains the captured inversion.
- The minimal fix is a dedicated market-callback ingress lock around observation timestamp capture,
  provider sequence assignment, mapping, and handler delivery. It does not reorder after the fact,
  alter `received_at`, or change Journal replay ordering; it merely makes the callback-to-canonical
  admission boundary single-writer across Tick and BidAsk.
- The rehearsal failure is isolated to `test_composer_connects_existing_fill_to_shadow_and_durable_evidence`:
  its `dataclasses.replace()` changes event times to the activated fill date but leaves the historical
  payload/envelope `session_date` unchanged. Both fixture dates must be replaced; production
  validation must remain strict.
- The operational fixture also reused a pipeline helper bound to the previous fixed Thesis market
  date. Once the envelope/payload dates were corrected, the strict ingestor correctly rejected the
  fixture as a session mismatch. The test-only helper now accepts the observed fill date explicitly;
  production session validation is unchanged.
- The callback fix serializes only the short mapping/enqueue delivery path and leaves lifecycle
  callbacks independent. It removes the prior `_last_received_at` clamp, so a genuine system-clock
  regression remains visible and fail-closed rather than being silently normalized.
- Post-fix live evidence confirms the intended behavior: a 60-second 2330 capture finalized with
  102 applied events, zero rejection, a drained queue, and exact disposition/bar/book/health parity
  over 10 replay runs. This is strong ingress-fix evidence but remains a short market-data
  qualification run, not a full Trade Management Shadow session.
- Re-running the outer preflight after both changes removed `REHEARSAL_FAILED`; the only remaining
  blocker is `SESSION_WINDOW_NOT_FUTURE`, which is expected because the repair occurred after 09:00.

## PR-TM-002 blocking review findings

- P1 Decimal reproduction: `Decimal("100.0") == Decimal("100.00")`, but current serialization and
  fact digests differ while deterministic record IDs remain equal. Reader checks `str(parsed) == raw`,
  which accepts both scale variants and therefore does not enforce one wire representation.
- Required Decimal representation is plain JSON string notation with insignificant fractional zeros
  removed, negative zero encoded as `"0"`, and exponent syntax never emitted or accepted.
- P1 immutability reproduction: `JournalRecord(frozen=True)` retains the caller's mutable payload dict;
  the in-memory repository stores the same object reference. Mutating `contract_json` and its digest
  before checkpoint creation rewrites the replayed thesis and allows a checkpoint over altered history.
- Existing checkpoint verification correctly detects mutation after a checkpoint, but that does not
  make the underlying Journal artifact immutable.
- Minimal compatibility-preserving fix: canonicalize once at `JournalRecord` construction, retain the
  canonical UTF-8 bytes as the authoritative artifact, and expose a recursively immutable payload view
  for existing readers. This avoids changing every existing consumer to a new constructor in this PR.
- Existing Journal consumers only perform mapping reads (`[]`, `.get`, mapping expansion) or use
  `payload_json`; no product code mutates a stored payload. A recursively immutable mapping/tuple view
  is therefore compatible with observed callers.
- PostgreSQL writes `record.payload_json` and reconstructs through `JournalRecord(payload=...)`, so
  freezing/canonicalizing in `JournalRecord.__post_init__` applies the same artifact semantics to both
  in-memory and PostgreSQL adapters without a migration or wire-schema change.
- Preserve the current constructor for compatibility, but add an authoritative `payload_bytes`
  property backed by a construction-time snapshot. `payload_json` and fingerprint must read that
  snapshot rather than reserializing the public view.
- Decimal normalization belongs in a small dependency-free leaf helper shared by generic Journal JSON
  and Trade Management serialization; importing Journal infrastructure into the domain codec would
  violate the approved dependency direction.
- Self-review found one remaining Decimal-shaped input outside dataclass Decimal fields:
  `EvidenceValue(kind=DECIMAL)` stores a string and currently accepts scale/exponent variants. Because
  that string is serialized verbatim into the fact, the domain constructor must reject non-canonical
  DECIMAL evidence rather than relying on the serializer to infer string semantics.
- The immutable snapshot implementation preserves sorted canonical JSON bytes, converts nested JSON
  objects/lists into mapping proxies/tuples for read compatibility, and leaves fingerprint computation
  bound to the byte snapshot. Existing `dataclasses.replace()` compatibility is covered by accepting
  read-only `Mapping` input during reconstruction.
- Full-suite test count increased from 575 to 624 during this shared dirty-worktree task. The only
  failure is an expected artifact digest in `test_institutional_candidate_prior`, outside all Journal
  and Trade Management dependencies. Treat it as concurrent external state until isolated; do not
  rewrite its golden digest as part of PR-TM-002.
- The institutional digest test passes when isolated and repository search confirms no dependency on
  the changed modules. The earlier mismatch was transient shared-worktree state, not a PR-TM-002
  regression.
- Final blocker evidence: the focused Journal/Trade Management set passes 64 tests; stable full suite
  passes 625 tests with 1 skip. Equivalent Decimal variants now produce one representation and all
  post-construction payload mutation paths covered by tests are rejected.
