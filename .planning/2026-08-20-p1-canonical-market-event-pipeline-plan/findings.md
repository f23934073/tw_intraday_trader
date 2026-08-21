# Findings: P1 Canonical Market Event Pipeline

## Initial confirmed context

- The repository already has two event-driven slices: local Paper Trading uses
  a bounded quote queue and worker; Momentum Shadow uses normalized envelopes,
  a bounded queue, ordered ingestion, bar/book projections, features, signals,
  state, and projections.
- The legacy scan remains pull-oriented: `run_scan()` creates a new
  `MarketDataStore`, fills it from `get_market_stocks()`, then runs Candidate and
  Score synchronously.
- `MarketDataStore` is currently a latest-value, unconditional overwrite map.
- The target is convergence, not a third pipeline and not deletion of the Store.
- Canonical market events must be recorded before strategy consumers so live
  and replay can run the same ingestion and projection code.
- Snapshots remain allowed for bootstrap, reconnect recovery, reconciliation,
  and newly subscribed symbols; their authority and merge semantics must be
  explicit.
- The root worktree contains substantial unrelated modified/untracked files.
  This task must add only isolated planning records and one architecture plan.

## External source note

- Shioaji's current official use-restrictions guidance recommends subscription
  or SSE streaming for realtime intraday data rather than polling snapshots,
  ticks, or Kbars; order/deal status should use callbacks or SSE events.
- Quote-Binding Mode documents queue and Redis Stream callback patterns.

## Current canonical assets confirmed

- `market_data.events.EventEnvelope` already carries schema/session/source,
  source mode, stream kind, symbol, event/receipt time, ingress sequence,
  source identity, payload, and optional raw-capture identity. Tick and BidAsk
  payloads already use immutable `Decimal`-based contracts.
- `MarketDataIngestor` already enforces session identity, event-id deduplication,
  independent `(symbol, stream_kind)` watermarks, out-of-order rejection,
  instrument-reference presence, bar/book projection application, cumulative
  volume gap reporting, and DataHealth updates.
- `BoundedMarketEventQueue` is explicit and fail-closed on overflow; overflow
  records health and raises instead of silently dropping an accepted event.
- `ReplayDatasetLoader` and `ReplayRunner` already validate immutable manifests,
  content digests, receipt ordering, event/reference membership, and replay the
  existing canonical envelopes through `MarketDataIngestor`.
- The current replay result proves bar/book/DataHealth determinism by digest,
  but it does not yet include MarketDataStore projection parity, recorder
  write/read parity, Paper Trading state, or Candidate/Score outputs.
- The new milestone should evolve these existing contracts rather than define a
  second `EventEnvelope` or a second ingestor under a new package name.

## Duplicate ownership and migration seams

- `StockData` and `RealtimeQuoteUpdate` are still float-based compatibility
  models. `StockData` lacks bid/ask, independent Tick/Book timestamps,
  provenance, revision, and stream health; `RealtimeQuoteUpdate` duplicates a
  smaller subset of the richer canonical Tick/BidAsk contracts.
- `SimulationService` owns its own `Queue`, background quote worker, ordering
  checks, freshness check, quote map, and Shioaji subscription lifecycle. This
  is the main duplicate pipeline to retire after it can consume the shared
  projection safely.
- `ShioajiProvider` and `ShioajiMomentumStream` both install Tick/BidAsk
  callbacks and manage subscriptions. A single backbone also requires a single
  quote-adapter/callback owner plus shared subscription-interest coordination;
  otherwise the two consumers can overwrite SDK callback registration or
  exceed capacity independently.
- Candidate and Score are already clean read-model consumers. They need no
  event awareness; the migration target is a long-lived, thread-safe Store fed
  by a MarketData projection.
- The current runtime composition owns Provider and Simulation but constructs
  no process-wide market event pipeline. Momentum constructs a separate live
  runtime outside this composition.
- Existing capture/qualification files and the trading Journal are evidence or
  command artifacts, not a canonical market-event recorder. No production path
  currently appends every normalized dequeued market event before projections.
- The current Store is not safe as a multi-reader materialized view: writes are
  unconditional, no revision/watermark is retained, and `get_all()` does not
  offer an atomic multi-symbol read revision.
- Snapshot conversion still skips individual mapping failures and uses its own
  `StockData` mapping. Scanner migration must make failure counts and snapshot
  authority visible rather than silently manufacturing complete coverage.

## Runtime semantics worth preserving

- Momentum already proves the desired callback discipline: callback receipt
  increments metrics, attempts bounded enqueue, wakes one worker, and re-raises
  overflow after DataHealth is blocked. Its worker serializes lifecycle and
  market events and drains accepted events before shutdown.
- Momentum's current stale-pair rule uses a provisional fixed 15-second value.
  The shared backbone must propagate timing/health evidence but must not freeze
  or spread this value while Freshness Calibration remains incomplete.
- `SubscriptionManager` already models requested/acked/failed/unsubscribed,
  capacity, timeout, retry, dwell, disconnect, and explicit partial-subscribe
  rollback. It should be adapted into a shared interest coordinator rather than
  discarded, with Paper/Position interests pinned above candidate interests.
- The Dashboard refreshes candidate discovery from a snapshot-derived payload
  every 30 seconds while realtime Momentum scoring is stream-driven. Scanner
  migration must split discovery cadence from subscribed-symbol projection; it
  cannot imply full-market Tick/BidAsk subscriptions.
- `RuntimeComposition` is the natural composition root for one backbone. The
  current Momentum Dashboard factory bypasses it and opens its own Shioaji
  session, while Simulation consumes the composition Provider directly.

## Replay and recorder decisions forced by current behavior

- The existing fixture replay rebuilds event IDs and changes `source` to
  `REPLAY`. That proves deterministic bar/book ingestion, but it is not yet
  exact live-event replay. Canonical log replay must preserve the original
  envelope identity/source/timestamps/sequence; replay mode belongs to the
  runner/session metadata, not the event's market origin.
- A v1 recorder should use canonical JSONL as the authoritative append format;
  Parquet can be a later derived/compacted artifact. The file format must
  preserve Decimal strings, timezone-aware timestamps, enums, source identity,
  dequeue order, schema version, and final/incomplete session state.
- To reproduce duplicate and out-of-order dispositions, every structurally
  valid dequeued envelope must be recorded before semantic dedupe/order
  projection. A recorder failure must block DataHealth and stop downstream
  projection/strategy processing. Malformed SDK callbacks that cannot become
  an envelope belong in explicit adapter-error/quarantine evidence.
- Existing tests already cover envelope/payload consistency, independent
  Tick/BidAsk watermarks, duplicates, out-of-order data, cumulative gaps,
  overflow, reconnect recovery, deterministic bar/book replay, and shutdown
  drain. New tests should extend these guarantees to recorder round-trip,
  Store projection, Candidate/Score parity, Paper parity, shared subscription
  ownership, and live-vs-replay digest equality.

## Final plan decisions

- Use the existing `market-event-v1` Tick/BidAsk envelope; do not create the
  smaller duplicate envelope proposed in the discussion.
- Introduce one process-wide pipeline at `RuntimeComposition` and migrate
  consumers independently behind flags.
- Keep raw SDK mapping before the queue and materialized-state projection after
  the ingestor; do not overload one "normalizer" with both responsibilities.
- Record every structurally valid dequeued event before semantic dedupe/order
  projection. Overflow is a terminal session incident and cannot be represented
  as a complete exact-replay capture.
- JSONL is the v1 authoritative recorder; Parquet is optional derived output.
- Preserve live envelope identities during exact replay. Existing fixture
  replay remains a separately named legacy import path.
- Add a Decimal `MarketDataSnapshotV1` as canonical Store state and retain
  `StockData` as a compatibility read view for Candidate/Score.
- Candidate/Score read one atomic Store revision at a bounded evaluation
  cadence; they are not invoked for every market event.
- Shared subscription interests prioritize positions/pending orders, active
  Momentum episodes, candidates, then warming discoveries.
- Add Snapshot only under a new schema version with explicit
  bootstrap/reconcile authority and no state rollback.
- Freshness evidence fields are unified, but no common duration threshold is
  selected by this plan.

## 2026-08-20 review revision

- The architecture direction was approved, with three requested pre-coding
  boundaries: EventEnvelope schema, queue overflow/drop policy, and event
  ordering.
- The existing `market-event-v1` already uses `stream_kind` as the Tick/BidAsk
  discriminator and `schema_version` as the envelope/payload version. The plan
  freezes these instead of introducing duplicate `event_type` or
  `payload_version` fields.
- v1 receipt-only monotonic timing metadata must remain outside the frozen
  market envelope in ingress/recorder metadata.
- Tick and BidAsk cannot use `DROP_OLDEST` in canonical ingress because Tick
  carries cumulative volume and current Bar/Book/DataHealth/replay semantics
  depend on a complete accepted sequence. Saturation therefore rejects the new
  event, blocks health, closes admission, drains the accepted prefix, suppresses
  consumers, and marks the session incomplete.
- Lifecycle messages share the one FIFO but need reserved capacity; snapshot
  producers use bounded wait/retry outside callback threads. Future Order/Deal
  events require their own durable never-drop contract and remain outside P1.
- Callback concurrency requires attempted sequence allocation and FIFO
  admission in one short critical section. Semantic ordering stays independent
  per `(session, symbol, stream_kind)`; cross-stream and cross-symbol receipt
  order is evidence, not exchange causality.
- Dual-run migration comparisons must fork after the single source callback or
  use the same finalized recorder offline. A parity run never authorizes a
  second SDK callback/subscription owner.

## First-slice implementation audit

- No repository `AGENTS.md` adds further local instructions.
- The relevant existing modules are concentrated in `market_data/events.py`,
  `health.py`, `ingestion.py`, the Bar/Book/reference stores, replay, and the
  Momentum runtime/adapter. Existing focused tests already separate event,
  ingestion, replay, store, subscription, and Momentum concerns.
- The first slice can remain inside `market_data/` plus focused tests; no
  dashboard, simulation, scanner, provider, or runtime-composition change is
  required merely to prove the shared deterministic backbone.
- `DataHealth` already provides the required non-crashing safety state:
  `record_queue(..., overflow=True)` transitions to `BLOCKED` with explicit
  `QUEUE_OVERFLOW`; recovery requires a newer reconnect epoch and evidence.
  The new queue should reuse this instead of inventing a separate trading gate.
- Existing ingestion tests already prove independent Tick/BidAsk watermarks,
  explicit duplicate/out-of-order dispositions, cumulative-gap blocking,
  crossed-book/reference validation, accepted-event preservation on overflow,
  recovery evidence, clock-skew evidence, and session rollover. New tests
  should extend these contracts through the shared pipeline rather than repeat
  all Ingestor internals.
- `test_market_data_events.py` validates dataclass invariants but has no
  canonical encoder/decoder or checked-in event JSON. Slice 1 therefore needs
  a small explicit serializer rather than treating `__dict__` or `json.dumps`
  defaults as the contract.
- `market_data/replay.py` is intentionally a legacy dataset importer: it
  rebuilds event IDs and source as `REPLAY`. It should remain unchanged in this
  slice; replay consistency for the in-memory recorder can feed the preserved
  recorded envelopes into a fresh pipeline directly, without prematurely
  implementing the Phase 2 exact JSONL reader.
- All current `EventEnvelope` constructors use `market-event-v1`, so enforcing
  that constant in the dataclass is compatible with the checked code paths.
  The constant is currently duplicated in replay and Shioaji modules and can be
  imported from `events.py` to keep the frozen contract single-sourced.
- The project targets Python 3.11+ and has no Ruff/mypy configuration. Focused
  pytest, full adjacent regressions, compileall, and `git diff --check` are the
  proportionate validation set; `pyproject.toml` is already modified by an
  unrelated Freshness task and should not be touched by this slice.
- Existing capture code uses broad dataclass/asdict JSON encoding for evidence,
  which is intentionally unsuitable for a frozen replay contract. The new
  serializer must enumerate exact fields and reject unknown/missing keys.
- Existing runtime ports are generic and the in-memory adapters are small,
  framework-free classes. The recorder port should follow that style, but stay
  under `market_data` because this slice is the canonical data application
  boundary and must not introduce runtime-composition wiring yet.
- Baseline focused regression is green: 36 tests across event contracts,
  ingestion, replay, and Momentum runtime passed before implementation.
- The target source/test files are clean in Git, so slice edits can be audited
  independently from the unrelated Freshness and institutional worktree.
- Minimal implementation shape: `serialization.py` for the strict v1 codec,
  `ingress.py` for atomic sequence/FIFO/control reserve and non-throwing
  admission results, `recording.py` for a small recorder port/in-memory adapter,
  and `pipeline.py` for synchronous record-before-ingest orchestration.
- Both current Bar and Book stores expose deterministic `digest` properties and
  `finalize_session()`, so replay consistency can compare projection state
  without adding Store revisioning or a new persistence layer.
- The tracked compatibility diff is surgical: one schema constant/validation,
  one recorder health reason, and two imports replacing duplicated constants.
  Existing queue/runtime behavior is unchanged.
- The explicit codec and ingress modules are larger than the orchestration
  layer because they enumerate the frozen schema and failure evidence. Before
  handoff they need a focused simplification review to remove accidental API
  surface while retaining strict failure paths.
- `market_data/__init__.py` is intentionally empty, so the new modules should
  remain explicit imports rather than adding a broad package re-export layer.
- New source and tests currently keep every line at or below 100 characters;
  no formatting dependency or unrelated `pyproject.toml` change is needed.
- A real 2330 data-only Shioaji smoke (`subscribe_trade=False`) proved the new
  slice can consume both Tick and BidAsk without a second callback owner. The
  final 30-second run had 33 callbacks, all 33 accepted/recorded/processed,
  contiguous ingress sequence 1-33, zero rejection/overflow/handler/adapter
  errors, and queue depth 0 after stop/drain.
- Replaying those 33 preserved live envelopes through a fresh queue, recorder,
  and Ingestor produced identical disposition sequence plus identical Bar and
  Book digests. This is in-memory slice parity, not yet finalized JSONL exact
  replay.
- Live health correctly remained `DEGRADED` for `SOURCE_CLOCK_SKEW`, so the
  decision gate was `BLOCK_NEW_ENTRY`. An earlier 73-event window also recorded
  and rejected one same-stream out-of-order event. These are real inputs for
  Freshness/ordering evidence, not reasons to loosen the fail-closed contract.

## P1.1 accepted decisions

- The user formally accepted `P1 Vertical Slice 1 — PASSED` and authorized
  P1.1 implementation.

## P1.1b reconstructability audit

- The current runtime `InstrumentReference` is session-scoped and contains
  symbol, exchange, reference/limit prices, price-limit applicability, trading
  unit, and source update date. It does not preserve security type, display
  name, a point-in-time instrument identity, validity interval, or artifact
  provenance; exact replay therefore needs a separate immutable reference
  artifact rather than serializing the store ad hoc.
- Current `StockData` snapshots are float-based compatibility views. Their
  timestamps are generated at conversion time and they lack artifact identity,
  source provenance, completeness, content digest, and explicit bootstrap
  authority. They cannot be adopted unchanged as exact-replay input.
- Bar and Book projections begin as empty session stores with independent
  stream watermarks. DataHealth begins `STARTING`, with empty reasons/streams,
  zero counters, reconnect epoch zero, and no resync evidence; the legacy
  replay runner then hard-codes a READY transition. P1.1b must record these
  choices instead of repeating that implicit default.
- The existing full DataHealth digest includes live queue depth and queue
  high-watermark. Journal v1 records the dequeue timeline but not every
  admission/dequeue depth transition, so the full digest is not reconstructable
  from the finalized journal without either a replay-semantic health digest or
  additional queue-transition evidence.
- A finalized journal stores only final Bar, Book, and Health digests. If a
  final projection digest differs while every disposition matches, the current
  evidence cannot identify the first divergent record. The verifier must either
  state `UNKNOWN_NOT_RECORDED` honestly or consume a separately frozen
  checkpoint/hash-chain artifact; it must never infer a record index.
- Versioned reference, bootstrap, and projection-state artifacts can be frozen
  independently of the two evidence-policy choices above. Exact replay coding
  remains gated on resolving health parity and divergence-evidence semantics.

## P1.1b projection contract decisions

- The user accepted `D-HEALTH-001`: exact replay compares a versioned semantic
  Health digest derived from durable evidence, not runtime queue/thread
  scheduling metrics. Queue depth, queue high-watermark, worker latency, and
  thread state are excluded; final queue drain remains a separate manifest
  qualification gate.
- The semantic Health digest owns ordered evidence-derived incidents and state
  transitions, incident severity, admission transitions, reconstructable
  stream/counter state, and final Health/admission state. Severity is the
  resulting semantic impact, not a provider-supplied unversioned label.
- The user accepted `D-DIV-001`: exact disposition mismatch may name its linked
  ingress record, while final-only Bar/Book/Health mismatch must report
  `first_divergence=UNKNOWN_NOT_RECORDED`. P1.1b adds no checkpoint or hash-chain
  lifecycle.
- Projection digest ownership must be versioned independently. A
  `projection-digest-set-v1` binds disposition, Bar, Book, and semantic Health
  digest contract names to SHA-256 values; a future `bar-v2` is not comparable
  as `bar-v1` merely because both are SHA-256 strings.
- Step 2 can be implemented and tested deterministically, but the repository
  currently has no single real session containing all four finalized artifacts.
  The earlier live Tick/BidAsk parity evidence was in-memory and cannot be
  upgraded retroactively into a non-synthetic Bootstrap/Reference artifact set.
  Engine verification and historical qualification must remain separate.
- The user formally accepted the Step 2 review as `P1.1b implementation —
  PASSED` while keeping qualification pending. This acceptance does not
  authorize P1.2, Store revisioning, Scanner shadow migration, or artifact
  fabrication.
- Historical qualification now has two required evidence classes. Case A is a
  normal real Tick/BidAsk session proving Bar/Book projection parity. Case B is
  a real incident-bearing session proving ordered incident/rejection evidence
  and `data-health-replay-v1` parity. Both must pass before P1.2 is unblocked.
- Qualification is sequential: establish the normal Case A baseline first,
  then retain a naturally occurring Case B incident session. Injected or
  hand-authored incidents validate fixtures/parsers only and cannot qualify the
  historical evidence gate.
- P1.1 is limited to durable evidence and deterministic replay. It excludes
  Store/Candidate/Score/Position migrations, Freshness threshold selection,
  Shioaji runtime changes, and every consumer authority change.
- The authoritative artifact is one session-scoped `records.jsonl` timeline
  plus `manifest.json`, not separate files per stream or health category.
- Journal v1 has three record types: `INGRESS`, `DISPOSITION`, and
  `SYSTEM_INCIDENT`. Rejected market events remain replayable evidence rather
  than being omitted from the journal.
- A successful durable append means append, flush, and `fsync` have completed.
  Projection cannot observe the INGRESS event before that boundary succeeds.
- A session manifest distinguishes `FINALIZED` from `INCOMPLETE`; file
  existence alone never proves a complete capture.
- The replay CLI must fail non-zero on integrity, schema, ordering, or
  projection-parity failure so CI can consume it directly.
- The approved post-P1.1 migration order is Store revision projection, Scanner
  shadow, Momentum, then Paper. P1.1 itself performs none of those migrations.
- Repository recovery reconfirmed a broad dirty worktree and an unrelated
  active-plan pointer. P1.1 will update only this isolated plan and scoped
  canonical market-data files; it will not switch the global active plan.
- The current recorder API uses `record_index` as the contiguous dequeued
  ingress index, and a disposition refers back to that same index. Journal v1
  instead needs one unique index per JSONL row. The JSONL adapter will preserve
  the pipeline API while mapping each ingress index to its global journal row;
  `DISPOSITION.ingress_record_index` links back to that INGRESS row.
- `LifecycleIngressMessage` already carries the incident identity, ingress
  sequence, timestamp, source, reason, optional symbol, and raw SDK evidence.
  It can serialize as `SYSTEM_INCIDENT` without adding a second lifecycle
  schema in this slice.
- The current exact projection path requires an `InstrumentReferenceStore`,
  while accepted journal v1 records do not yet contain bootstrap/reference
  inputs. The first P1.1 coding slice must not synthesize references and call
  that exact replay. Its CLI will verify artifact integrity, strict schemas,
  timeline order, stream ordering, and ingress/disposition links; a later P1.1
  slice must freeze complete replay inputs before claiming projection parity.
- The existing architecture plan still shows split ingress/disposition files
  and the old Paper-first consumer order. Both must be revised before code is
  treated as conforming to the newly accepted decision.

## P1.1a formal acceptance and P1.1b direction

- The user formally accepted `P1.1a Durable Journal Baseline — PASSED` and
  identified reconstructability as the next technical risk.
- The accepted dependency order is Durable Journal → exact projection replay →
  revisioned MarketDataStore projection → Scanner shadow → Momentum → Paper.
- P1.1b is limited to immutable InstrumentReference, bootstrap snapshot,
  projection initial-state inputs, exact replay CLI mode, and disposition/
  Bar/Book/DataHealth parity. Candidate, Score, Position, Order, and Strategy
  remain consumer-layer exclusions.
- A Store revision digest cannot be a P1.1b exit gate because the revisioned
  Store projection is not implemented until Phase 3. P1.1b proves canonical
  projection reconstructability first; Phase 3 adds Store revision/digest to
  the same exact-replay evidence set.
- This acceptance authorizes status/plan updates only. P1.1b product coding was
  not explicitly requested in this review turn.

## P1.1b contract-freeze authorization

- The user explicitly authorized `process P1.1b`, with a mandatory first stage:
  freeze three reference contracts before writing replay code.
- This turn is limited to `instrument_reference_v1.md`,
  `bootstrap_snapshot_v1.md`, and `projection_state_v1.md`, plus P1 planning
  records. Replay CLI/engine, Store, consumers, and synthetic fixtures remain
  excluded.
- Exact replay must be defined as Journal + immutable reference artifact +
  immutable bootstrap artifact + explicit projection initial state + projection
  version. Missing inputs must fail closed rather than use program defaults.
- The current dirty worktree still includes unrelated Freshness,
  institutional, trade-management, and planning changes. The P1.1b contract
  freeze will not switch the active plan or modify those files.
- Current `InstrumentReference` is session-scoped and already supplies the
  fields required by `MarketDataIngestor`: normalized symbol, exchange,
  reference/limit prices, price-limit applicability, trading unit, and optional
  source update date. It does not carry security type, display name, stable
  provider identity, or validity interval; the v1 artifact must define those
  explicitly rather than infer them during replay.
- `InstrumentReferenceStore.digest` is deterministic over its sorted current
  fields. The new artifact must preserve a content digest and define how it
  relates to this runtime projection digest.
- Existing `momentum-replay-v1` bundles references and events, reconstructs
  event IDs/source as REPLAY, starts Bar/Book empty, and calls
  `DataHealth.mark_ready()` with a hard-coded evidence string. It is a legacy
  fixture importer, not exact historical reconstruction.
- `IntradayBarStore` and `OrderBookStore` currently initialize empty for one
  session and retain private event IDs/watermarks; `DataHealth` initializes
  STARTING and only becomes HEALTHY through explicit evidence. Exact replay
  therefore needs a declared initial-state mode and digest, not constructor
  defaults hidden inside the runner.
- Current `StockData` snapshot is float-based and lacks stable capture identity,
  coverage/completeness, provenance, independent Tick/Book watermarks, and a
  content digest. It cannot be adopted unchanged as the exact bootstrap
  artifact.

## Phase 12 qualification capture audit

- The frozen replay contracts and exact engine exist, but the repository has
  no application that captures one real subscription into the required
  finalized artifact set.
- `ShioajiMomentumStream.connect_from_env()` is already data-only and passes
  `subscribe_trade=False`; it also owns the proven Tick/BidAsk normalization
  and paired subscription acknowledgements, so the harness must reuse it.
- The bootstrap contract requires acknowledged subscriptions before the
  Journal boundary. The harness therefore needs a callback admission gate:
  callbacks received before durable bootstrap finalization are outside the
  qualification boundary and must not silently enter projection state.
- Expected Bar/Book digests must come from the live projection. Exact replay
  may verify them afterward but must not manufacture the expected artifact.
- Case A requires both Tick and BidAsk evidence and no natural incident. A
  real incident is retained only as a Case B candidate; the harness exposes no
  incident-injection option.
- The repository's only prior reviewed calendar was TAIFEX-specific. The
  qualification CLI now uses a separate official-source-linked TWSE 2026
  artifact, includes the natural 2026-07-10 closure, and binds schema plus file
  SHA-256 into Bootstrap calendar identity.
- Capture-side expected digests are built from durable disposition/incident
  records plus the live Bar/Book/Health projections. The exact replay runtime
  is invoked only after ProjectionState is durable, avoiding circular expected
  evidence.
