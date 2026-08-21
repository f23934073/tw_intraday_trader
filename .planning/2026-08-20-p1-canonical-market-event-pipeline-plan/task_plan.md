# Task Plan: P1 Canonical Market Event Pipeline

## Goal

Produce the approved repository-grounded plan and incrementally implement its
flags-off canonical market-data backbone. The current authorized slice is P1.1:
session-scoped durable JSONL evidence, finalized/incomplete manifests, integrity
verification, and exact deterministic replay tooling. Preserve current Paper,
Momentum, Scanner, Store authority, Freshness thresholds, Shioaji runtime, and
all real-money safety boundaries.

## Current Phase

Phase 11 — P1.1b historical qualification evidence pending

## Phases

### Phase 1: Repository contract and gap trace

- [x] Trace the current event, queue, ingestion, projection, recorder, replay,
  snapshot, Store, Candidate, Score, and Paper Trading boundaries.
- [x] Identify contracts that can be reused unchanged and duplicate semantics
  that must be retired or adapted.
- [x] Preserve current data-only/local-paper safety boundaries and unrelated
  worktree changes.
- **Status:** complete

### Phase 2: Canonical architecture decisions

- [x] Freeze the canonical envelope, ports/adapters, ordering, idempotency,
  overflow, freshness, lifecycle, bootstrap, and reconciliation semantics.
- [x] Define recorder-before-strategy ordering and deterministic replay parity.
- [x] Define compatibility behavior for `MarketDataStore`, Candidate, Score,
  Position, Momentum, and Paper Trading consumers.
- **Status:** complete

### Phase 3: Implementation plan authoring

- [x] Write dependency-ordered implementation phases with exact repository
  areas, migrations, feature flags, acceptance gates, and rollback paths.
- [x] Specify focused/unit/integration/replay/live-shadow verification.
- [x] Keep implementation explicitly outside this task.
- **Status:** complete

### Phase 4: Plan verification and delivery

- [x] Cross-check the plan against current code and the user's proposed target.
- [x] Verify only planning Markdown was added for this task.
- [x] Deliver the plan for review before implementation begins.
- **Status:** complete

### Phase 5: Review contract-freeze revision

- [x] Incorporate the approved review without entering product implementation.
- [x] Freeze the EventEnvelope v1 field/version/serialization contract.
- [x] Freeze per-ingress-class overflow/drop and failure consequences.
- [x] Freeze callback admission, per-stream semantic ordering, and non-ordering
  boundaries.
- [x] Add explicit old/new comparison and per-phase rollback gates.
- [x] Re-run structural/scoped verification and deliver the revised plan.
- **Status:** complete

### Phase 6: First-slice repository audit and test design

- [x] Revalidate current queue, health, ingestor, Momentum runtime, lifecycle,
  test fixtures, and runtime boundaries against the frozen contracts.
- [x] Define the minimum new ports/models and exact failure-path tests without
  wiring consumers or a real Shioaji session.
- [x] Confirm the scoped files do not overlap unrelated worktree changes.
- **Status:** complete

### Phase 7: Executable contract and failure-path tests

- [x] Add C-EVT-001 golden serialization/validation tests.
- [x] Add C-QUE-001 capacity, control-reserve, non-crashing fail-closed gate,
  accepted-prefix drain, and recorder-failure tests.
- [x] Add C-ORD-001 record-before-ingest, watermark, and replay-consistency
  tests.
- **Status:** complete

### Phase 8: Shared ingress vertical slice implementation

- [x] Implement the smallest shared ingress message/queue/health-gate surface.
- [x] Implement recorder port plus in-memory recorder with full envelope
  identity and disposition evidence.
- [x] Implement a synchronous deterministic pipeline over the existing
  `MarketDataIngestor`; keep callbacks, consumers, and Store authority unwired.
- **Status:** complete

### Phase 9: Verification and handoff

- [x] Run focused tests, adjacent market-data/Momentum regression, compile,
  lint/format checks available in the repository, and `git diff --check`.
- [x] Audit the diff for slice-only scope and document remaining live-stream
  evidence work without overstating Freshness or consumer readiness.
- **Status:** complete

### Phase 10: P1.1 durable journal and replay CLI

- [x] Freeze `market-event-journal-v1` records, manifest, durability, and
  incomplete-session contracts in the architecture plan and executable tests.
- [x] Add a journal writer port and exclusive-create JSONL adapter whose
  successful append means flush and `fsync` completed before projection.
- [x] Add manifest finalization with SHA-256, record statistics, projection
  digests, queue-drain evidence, and `FINALIZED`/`INCOMPLETE` distinction.
- [x] Add a session reader and replay CLI that verifies integrity, schema,
  record-index ordering, and event/disposition links without claiming exact
  projection parity.
- [x] Cover write/flush/fsync failure, tampering, truncation, incomplete
  sessions, ordering violations, and deterministic artifact verification.
- [x] Run focused, adjacent, full, compile, CLI, and whitespace verification;
  audit that no consumer authority or production runtime wiring changed.
- **Status:** complete; `P1.1a Durable Journal Baseline — PASSED`

### Phase 11: P1.1b reference contract and exact projection replay

- [x] Freeze versioned InstrumentReference and empty-session bootstrap snapshot
  inputs with session identity, provenance, completeness, and content digests.
- [x] Freeze projection initial-state, versioned digest ownership, semantic
  Health parity, and bounded divergence reporting after approval of
  `D-HEALTH-001` and `D-DIV-001`.
- [x] Add an exact reader/CLI mode that rejects missing, tampered, incomplete,
  cross-session, or version-incompatible replay inputs.
- [x] Rebuild a fresh Ingestor, Bar, Book, and semantic DataHealth state without
  synthetic defaults; preserve original market-event identities.
- [x] Verify disposition/Bar/Book/DataHealth digests across repeated replay.
- [x] Keep Candidate, Score, Position, Order, Strategy, Store migration, and
  every consumer authority change outside this phase.
- [ ] Qualification Case A: one normal real session with finalized Journal,
  Bootstrap, InstrumentReference, and ProjectionState artifacts proves Tick,
  BidAsk, Bar, Book, and all four versioned digest matches.
- [ ] Qualification Case B: one real incident-bearing session proves ordered
  SYSTEM_INCIDENT/rejected-event evidence and semantic Health digest parity.
- [ ] Execute Case A first, then wait for naturally occurring Case B evidence;
  qualification must not inject or hand-author an incident.
- [ ] Preserve both qualification evidence reports; fixtures, hand-edited
  artifacts, and synthetic bootstrap state do not satisfy either gate.
- [ ] After Phase 3 implements the revisioned Store projection, extend the same
  replay gate with MarketDataStore revision/digest parity.
- **Status:** implementation PASSED; Historical Qualification ACTIVE with
  Case A + Case B required, P1.2 and consumer migration blocked

## Key Decisions

| Decision | Rationale |
|---|---|
| Create an isolated planning session | The root Freshness Calibration plan and unrelated worktree changes are active. |
| Plan only; do not modify product code | The user asked for an implementation plan. |
| Preserve `MarketDataStore` as a materialized current-state view | Candidate and Score should keep a simple read model and must not replay events. |
| Keep snapshots as bootstrap/reconciliation inputs | Streaming is the continuous path, not the only valid source of market state. |
| Keep `stream_kind` as the v1 payload discriminator | Adding `event_type` would duplicate the current canonical contract. |
| Use fail-closed Tick/BidAsk overflow | Dropping/coalescing canonical ingress breaks cumulative-volume, book, health, and exact-replay evidence. |
| Reserve queue capacity for lifecycle messages | A market burst must not silently starve ACK/reconnect evidence while preserving one FIFO. |
| Keep Tick and BidAsk watermarks independent | Cross-stream exchange causality is not established by receipt order. |
| Make the first pipeline synchronous and explicitly pumped | It proves deterministic queue/recorder/ingestor semantics without introducing an unrequested production thread or lifecycle owner. |
| Represent overflow as health/gate state, not a process crash | Callback admission reports rejection and blocks new decisions while the process remains available to drain and expose evidence. |
| Keep Store revisioning out of slice 1 | Recorder owns history; this slice proves the event backbone only. |
| Use one session-scoped authoritative journal | Splitting Tick, BidAsk, and incidents would destroy the observed dequeue and failure timeline. |
| Treat durable append as flush plus `fsync` | P1.1 prioritizes evidence integrity; an event cannot reach projection before its INGRESS evidence is durable. |
| Keep journal infrastructure behind a writer port | The pipeline depends on the evidence contract, while JSONL/file-system behavior remains an adapter. |
| Migrate Scanner before Momentum and Paper after P1.1 | Scanner has no execution or position authority and is the lowest-risk first shadow consumer. |
| Require reconstructability before Store/Scanner migration | Scanner parity is not attributable until Journal plus immutable reference/bootstrap inputs reproduce the same canonical projections. |
| Defer Store digest to Phase 3 | P1.1b runs before the revisioned MarketDataStore projection exists; it must not claim a parity metric for an unimplemented contract. |
| Freeze P1.1b artifacts before replay code | Exact replay is defined by complete historical inputs; the engine must not invent missing reference, bootstrap, or initial projection state. |
| Use a replay-semantic Health digest | Durable event semantics are deterministic; queue depth, scheduling, and thread metrics are runtime artifacts. |
| Keep final-only divergence bounded | Without checkpoints, report `UNKNOWN_NOT_RECORDED` rather than inventing the first divergent record. |
| Version digest ownership per projection | Bar, Book, Health, and disposition contracts can evolve independently without false cross-version parity. |

### Phase 12: Flags-off data-only qualification capture harness

- [x] Audit the existing Shioaji Tick/BidAsk adapter, canonical queue,
  durable Journal, reference/bootstrap contracts, and exact replay seam.
- [x] Add an isolated capture application that forces empty-session startup,
  gates callbacks until real reference/bootstrap evidence is durable, drains
  the bounded queue, and never imports or invokes an order path.
- [x] Add a thin Shioaji CLI entry point that uses the existing
  `subscribe_trade=false` login and paired Tick/BidAsk subscription adapter.
- [x] Produce finalized InstrumentReference, BootstrapSnapshot, Journal, and
  live ProjectionState artifacts without deriving expected state from replay.
- [x] Run exact replay automatically after finalization and preserve a
  qualification report; fail Case A closed if required streams are missing or
  a natural incident occurred.
- [x] Prove the lifecycle with a deterministic fake stream and run focused plus
  full repository validation without starting a broker session.
- **Status:** complete; harness ready, real Case A/Case B evidence pending

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Root planning-file read output was truncated because the three files are large | 1 | Use focused chunked reads and an isolated planning session; do not overwrite the active root plan. |
| Initial title/status patch did not match the file's exact status wording | 1 | Read the exact header and apply a narrower context-aware patch. |
| Completion helper defaulted to the unrelated root `task_plan.md` | 1 | Re-run it with this isolated task-plan path; all 5 phases completed. |
| `rg` pattern attempted to embed a literal newline while checking digest APIs | 1 | Use a simple alternation for `digest|finalize_session`; both stores expose deterministic digests. |
| New contract/pipeline tests failed collection before implementation | 1 | Expected TDD red: `MARKET_EVENT_SCHEMA_VERSION` and the new serializer/ingress/recorder/pipeline modules do not exist yet; implement the scoped contracts next. |
| Temporary live-smoke script could import installed `market_data` but not the workspace `runtime` package | 1 | Add the explicit workspace root to the temporary script's import path; do not change project packaging for a smoke harness. |
| Sandboxed Shioaji SDK could not bind its inter-thread file descriptor | 1 | Re-run the same data-only `subscribe_trade=False` smoke with approved unsandboxed execution. |
| First 12-second live window received only BidAsk callbacks | 1 | Accounting/drain passed, but paired evidence is incomplete; extend the bounded window and expose health/disposition reasons before drawing a conclusion. |
| A final line-number search put Markdown backticks inside a double-quoted shell pattern | 1 | The shell attempted command substitution; use a plain anchored heading pattern for the remaining read-only lookup. |
| Direct `pytest` command was unavailable in the current non-login shell | 1 | Locate and use the repository's existing virtual-environment Python rather than installing or changing dependencies. |
| First P1.1 test collection could not import `market_data.journal` | 1 | Expected TDD red; implement the approved journal adapter and verification surface. |
| Frozen-contract structural check expected the literal `queue_high_watermark`, while the document used prose wording | 1 | Use the exact runtime field names in the exclusion contract and update the stale architecture-plan summary status. |
| Step 2 focused test collection cannot import `market_data.exact_replay` | 1 | Expected TDD red; implement the frozen artifact loader, deterministic projection runtime, comparator, and thin CLI adapter. |
| First implemented focused run used nonexistent `MarketEventSource.SHIOAJI` in the new test fixture | 1 | Match the frozen envelope enum used by existing journal tests and use `MarketEventSource.TICK`; provider identity remains in `source_identity`. |
| Second focused run omitted three required Tick flags in the new fixture | 1 | Match the frozen `TickEvent` constructor and set suspended/simulated/odd-lot flags explicitly to false. |
| Artifact bootstrap helper used zero Bar/Book expected digests, which correctly failed Journal binding before reconstruction | 1 | Seed the test ProjectionState Bar/Book expectations from the finalized Journal manifest; only derive the new disposition/semantic-Health digests from the first test reconstruction. |
| Scoped Ruff check found one unused `pytest` import in the new test module | 1 | Remove the unused import; no production behavior changed. |
