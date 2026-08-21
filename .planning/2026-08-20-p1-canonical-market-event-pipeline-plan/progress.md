# Progress: P1 Canonical Market Event Pipeline

## 2026-08-20 — Plan authoring

- **Status:** in_progress
- Activated `planning-with-files` for durable plan state and
  `architecture-patterns` for ports/adapters and dependency direction.
- Confirmed this is an implementation-plan-only request.
- Restored the repository's existing root planning context and catch-up output.
- Preserved the active Freshness Calibration plan and created this isolated
  planning session instead of changing `.planning/.active_plan`.
- Recorded the initial three-path architecture and the proposed convergence
  target; product code remains untouched.
- Confirmed the current `EventEnvelope`, bounded queue, `MarketDataIngestor`,
  replay loader/runner, bar/book projections, and health semantics are already
  reusable canonical foundations; the plan will extend them instead of
  creating a third market-data model.
- Traced the duplicate Paper Trading queue/worker/quote state, the two Shioaji
  callback owners, the snapshot-only Store, the stateless scan path, and the
  absence of a process-wide market-event recorder/composition.
- Reviewed Momentum lifecycle/backpressure/shutdown guarantees,
  `SubscriptionManager`, snapshot discovery cadence, the composition root, and
  current test coverage. Recorded the exact-replay identity gap and the
  recorder-before-projection fail-closed contract.
- Authored `architecture/p1_canonical_market_event_pipeline_implementation_plan.md`
  with target architecture, canonical contracts, recorder/replay semantics,
  Store projection, shared subscription ownership, Snapshot reconciliation,
  Freshness boundary, Phase 0-7 delivery gates, test strategy, rollout,
  rollback, file map, review decisions, and Definition of Done.
- Structural checks passed: required sections/identifiers are present, code
  fences are balanced, no trailing whitespace exists, and scoped
  `git diff --check` is clean.
- Final scope audit confirmed this task added only the standalone architecture
  plan and its isolated planning records. Existing Freshness, institutional,
  configuration, test, and active-plan worktree changes were left untouched.
- **Status:** complete; awaiting user review before any implementation.

## 2026-08-20 — Approved review contract-freeze revision

- **Status:** in_progress
- Read the full attached review and treated it as approval of the architecture
  plus a request to freeze three migration boundaries before coding.
- Re-read the planning and architecture skills, restored the isolated planning
  context, and confirmed unrelated worktree changes remain outside this task.
- Updated the architecture plan with `C-EVT-001`, `C-QUE-001`, and `C-ORD-001`:
  exact v1 fields/version/serialization, per-ingress overflow consequences,
  control reserve, atomic callback sequence/FIFO, independent stream
  watermarks, and explicit non-ordering boundaries.
- Added executable Phase 0 gates, burst/control-reserve tests, observability,
  phase-by-phase old/new comparison, rollback actions, frozen review decisions,
  Definition of Done checks, and the refined first implementation slice.
- Kept Tick/BidAsk fail-closed; did not adopt lossy `DROP_OLDEST`, and left
  future Order/Deal durability outside this market-data milestone.
- Verified 32 balanced code fences, no trailing whitespace, all three contract
  sections/G0/per-phase rollback/DoD/first-slice markers present, and a clean
  `git diff --check` for tracked changes.
- Scope audit confirms this revision changed only the P1 architecture plan and
  its isolated planning records; existing Freshness, institutional, active-plan,
  configuration, and test worktree changes remain untouched.
- **Status:** complete; revised plan is implementation-ready for a separately
  authorized coding turn.

## 2026-08-20 — First vertical slice implementation

- **Status:** in_progress
- The user approved the architecture and explicitly directed the work toward
  the first vertical slice.
- Scope is frozen to contract tests, shared bounded ingress, in-memory
  recorder, existing Ingestor integration, and failure-path verification.
- Paper, Momentum, Scanner, MarketDataStore authority/revisioning, JSONL,
  production Shioaji wiring, Order/Deal, Freshness thresholds, and real-money
  behavior remain outside this slice.
- Repository audit completed. Baseline focused suite passed 36 tests, target
  source/test files are clean, and the minimal module/test boundaries are
  frozen before editing.
- Added v1 Tick/BidAsk golden JSON fixtures and executable tests for strict
  codec failure paths, non-crashing overflow/trading gate, control reserve,
  recorder-before-ingest failure, out-of-order recording, concurrent atomic
  admission, and in-memory replay projection parity.
- The first focused run is intentionally red at collection because the new
  schema constant and slice modules have not been implemented yet.
- Added the frozen schema constant/validation and strict field-enumerated v1
  codec; replay and Shioaji adapters now import the single schema constant.
- Added the shared bounded ingress queue with atomic sequence allocation,
  market capacity/control reserve, explicit non-throwing admission results,
  incident evidence, and separate market/all admission gates.
- Added the recorder protocol/in-memory adapter and synchronous canonical
  pipeline. Record failures block health and all admission before Ingestor;
  overflow leaves the process alive to record/drain the accepted prefix.
- New contract and failure-path suite is green: 10 tests passed.
- Focused plus adjacent regression is green after adding the sequence mismatch
  failure path: 47 tests passed.
- Added the checked-in `market-event-v1` contract document and kept the codec's
  dict conversion private so the public surface is only strict serialize/
  deserialize.
- Compileall passed; the adapter/contract/ingestion/replay focused regression
  now passes 53 tests.
- Full repository regression passed: 482 tests passed and 1 skipped.
- `git diff --check` passed. Scoped Git status contains only the expected
  contract document, four new market-data slice modules, four narrow existing
  module edits, golden fixtures/tests, and this isolated planning directory.
- Strengthened the overflow test to assert the accepted/recorded count
  invariant, rejected incident identity/sequence, and that the recorder keeps
  the full envelope timestamps, source identity, and payload. Focused suite now
  passes 11 tests.
- First data-only Shioaji smoke connected and received 6 BidAsk callbacks with
  exact `callback=accepted=recorded=processed=6`, zero rejection/incident/error,
  and queue depth 0 after drain. The 12-second window lacked Tick evidence and
  ended `DEGRADED`, so it is recorded as incomplete rather than a pass.
- A 30-second diagnostic window then received 73 paired Tick/BidAsk callbacks
  with zero loss/rejection/incident/error and caught one explicit same-stream
  out-of-order event plus source-clock skew evidence.
- Final 30-second live/replay qualification passed: 33 paired Tick/BidAsk
  callbacks equaled 33 accepted, recorded, and processed events; sequence was
  contiguous 1-33; queue drained to 0; no incidents/errors occurred; replay
  disposition, Bar digest, and Book digest all matched live.
- The live decision gate remained `BLOCK_NEW_ENTRY` because source-clock skew
  left DataHealth `DEGRADED`; no safety threshold or consumer authority was
  changed to force a green result.
- Final verification passed: full repository suite 485 passed / 1 skipped,
  compileall passed, `git diff --check` passed, and no trailing whitespace was
  found in the new contract/source/test files.
- Final scope audit confirms the new backbone is not imported by production
  runtime/consumer modules. Paper, Momentum, Scanner, Store authority, JSONL,
  and Freshness thresholds remain unchanged; unrelated concurrent Freshness,
  institutional, trade-management, and planning worktree files were preserved.
- **Status:** complete; first vertical slice implemented and live/replay
  qualified for review.

## 2026-08-20 — P1.1 durable journal and replay CLI

- **Status:** in_progress
- User accepted the session-scoped journal, durability, manifest, replay, and
  revised consumer-migration decisions and explicitly authorized implementation.
- Restored the isolated P1 planning files and catch-up context. The repository
  contains concurrent unrelated Freshness, institutional, trade-management,
  packaging, and active-plan changes; they remain outside this slice.
- Activated `planning-with-files`, `architecture-patterns`, and
  `karpathy-guidelines`. The implementation will keep the journal contract/port
  independent of the JSONL file-system adapter and add no speculative consumer
  or runtime abstraction.
- Next: inspect the current pipeline/recorder/codec/replay seams, freeze the
  executable journal contracts, then implement the smallest writer/reader/CLI.
- Inspected the seams and found two necessary precision boundaries: pipeline
  ingress indices cannot be reused as unique JSONL row indices, and exact
  projection replay cannot be claimed without the session's instrument
  reference/bootstrap inputs. The adapter will map indices explicitly; the
  first CLI slice will stop at strict artifact/order verification.
- Updated the architecture plan to one `records.jsonl` timeline, two-state
  manifests, per-record flush/`fsync`, global journal-row indices, and the
  accepted Store → Scanner shadow → Momentum → Paper migration order.
- Confirmed `IngestResult` and `StreamWatermark` have a fully enumerable strict
  codec surface and Bar/Book/Health already expose deterministic digests. The
  first manifest can preserve those expected digests without altering stores.
- Added the first P1.1 executable tests for the single ordered timeline,
  exclusive session creation, fsync-before-projection failure, tampering,
  record-index corruption, incomplete sessions, and CLI exit semantics.
- The initial red run did not reach collection because `pytest` is not on this
  shell's PATH. No dependency change was made; use the checked-in/local virtual
  environment Python for the intended TDD run.
- Re-ran with `.venv/bin/pytest`; collection then failed at the intentionally
  absent `market_data.journal`, establishing the expected TDD red boundary.
- Added `market_data.journal`: one exclusive session directory, one canonical
  JSONL timeline, strict INGRESS/DISPOSITION/SYSTEM_INCIDENT codecs, per-record
  flush/`fsync`, initial INCOMPLETE manifest, atomic FINALIZED manifest,
  SHA-256/statistics/projection digests, and strict offline verification.
- Added `market_data.replay_cli` with explicit `--verify`-only behavior and
  non-zero failure exits. It labels projection replay pending rather than
  manufacturing missing instrument-reference/bootstrap state.
- Focused P1.1 journal suite is green: 7 tests passed.
- Expanded failure evidence to disk-full write, flush, ingress fsync, and
  post-projection disposition fsync failures; all close admission and leave an
  INCOMPLETE session, while only the ingress-failure cases prevent projection.
- Added truncated-tail, schema tamper with recomputed file digest, explicit
  inspectable INCOMPLETE, cross-run deterministic bytes, and real `python -m`
  CLI tests. Focused P1.1 suite now passes 15 tests.
- Added the frozen `market-event-journal-v1` contract document and split the
  architecture milestone into P1.1a durable artifact verification and P1.1b
  exact projection replay, which remains dependent on a frozen reference/
  bootstrap input contract.
- Audited manifest cross-field semantics: a FINALIZED artifact now requires
  SHA-256, queue drain, finalization time, no incomplete reason, and Bar/Book
  expected digests. The verifier also checks event/incident session identity
  against the manifest.
- Confirmed the durable adapter structurally satisfies the existing
  `MarketEventRecorder` port. Focused failure/integrity/CLI suite now passes
  16 tests.
- Adjacent market-event contract/pipeline/ingestion/replay regression passed:
  34 tests.
- Full repository regression passed: 516 tests passed and 1 skipped.
- Compileall, real module CLI help/entrypoint, `git diff --check`, strict
  line-length check on the new source/tests/contract, and production-import
  scope audit passed.
- Scope audit confirms no runtime, Shioaji adapter, Store, Candidate, Score,
  Position, Momentum, Paper, or Scanner module imports the durable journal.
  P1.1a is flags-off capability only; no consumer authority changed.
- **Status:** P1.1a complete and ready for review. P1.1b exact projection
  replay remains pending the reference/bootstrap input contract and is not
  claimed by this slice.

## 2026-08-20 — P1.1a formal acceptance

- **Status:** complete
- User formally marked `P1.1a Durable Journal Baseline — PASSED` and accepted
  reconstructability as the next gate before Store/Scanner migration.
- Updated the architecture status and P1 plan only; no product source, test,
  runtime wiring, Store, or consumer authority was changed in this review turn.
- Froze the P1.1b planning boundary around versioned/digested reference,
  bootstrap, and projection-initialization inputs plus exact Ingest/Bar/Book/
  DataHealth replay parity.
- Recorded that Store revision/digest parity moves into Phase 3 after the
  revisioned Store projection exists; P1.1b must not invent it early.
- P1.1b coding remains pending explicit implementation authorization.

## 2026-08-20 — P1.1b reference contract freeze

- **Status:** in_progress
- User authorized P1.1b but explicitly staged the first implementation step as
  contract documents only; replay code must wait until the contracts are
  frozen and reviewed.
- Activated `planning-with-files` and `architecture-patterns`; restored the P1
  isolated plan and reconfirmed the broad unrelated dirty worktree.
- Scope is three architecture contracts plus P1 planning records. No Python,
  CLI, tests, artifact fabrication, runtime wiring, or consumer authority
  change is authorized in this stage.
- Next: trace exact current InstrumentReference, snapshot/bootstrap, Bar/Book/
  DataHealth initialization and digest behavior, then author the three
  repository-grounded contracts.
- Traced the existing models and confirmed the exact-replay gaps: reference
  identity/validity metadata are absent, `StockData` is not an immutable
  bootstrap artifact, and the legacy replay runner silently chooses empty
  Bar/Book plus hard-coded HEALTHY initialization.
- The contracts will distinguish artifact provenance from runtime projection
  fields and make every initial-state choice explicit; they will not promote
  the legacy replay fixture format to exact replay.
- Audited digest provenance and found two contract-level evidence gaps before
  replay code: the current Health digest includes unjournaled queue
  high-watermark, and final-only projection digests cannot prove a first
  divergent record. These remain explicit review gates rather than guessed
  replay values.
- Added frozen `instrument-reference-v1` and `bootstrap-snapshot-v1` contracts.
  They require immutable provenance, complete session identity/coverage,
  canonical Decimal/date encoding, content digests, explicit journal boundary,
  and empty-session-only projection authority.
- Added `projection-state-v1` as `REVIEW_REQUIRED`, binding input digests,
  implementation versions, explicit Bar/Book/Health initial state, expected
  parity, stable failures, and a real historical qualification artifact.
- Updated the architecture plan to name all three contracts and keep replay
  coding blocked on `D-HEALTH-001` and `D-DIV-001`.
- User accepted `D-HEALTH-001` with a replay-semantic Health digest and
  `D-DIV-001` with honest `UNKNOWN_NOT_RECORDED` final-only mismatch reporting.
- Froze `projection-state-v1`. It now defines `projection-digest-set-v1` with
  independently versioned disposition, Bar, Book, and Health ownership;
  `data-health-replay-v1` excludes runtime queue/thread artifacts while keeping
  journal-derived transitions, severity, admission, streams, counters, and
  final semantic state.
- P1.1b contract baseline is frozen. Exact replay CLI implementation remains a
  separate next coding step and was not started in this contract turn.

## 2026-08-20 — P1.1b exact projection replay implementation

- **Status:** implementation_complete; historical_qualification_pending
- User formally passed the reference-contract baseline and authorized Step 2
  exact projection replay CLI implementation.
- Scope remains Journal + InstrumentReference + Bootstrap + ProjectionState
  loading, deterministic Ingestor/Bar/Book/semantic-Health replay, versioned
  digest comparison, CLI output/exit codes, and fail-closed artifact tests.
- MarketDataStore, Candidate, Score, Position, Order, Strategy, checkpoints,
  hash chains, consumer migration, runtime wiring, and Freshness thresholds
  remain excluded.
- Reconfirmed the broad dirty worktree. Existing Freshness, institutional,
  trade-management, active-plan, and prior P1 files must be preserved.
- Initial seam audit confirms `replay_cli.py` currently performs Journal
  integrity only; legacy `replay.py` rewrites identities and is not reusable as
  exact replay authority. Step 2 must load preserved journal envelopes through
  the existing `MarketDataIngestor` and keep orchestration outside the CLI.
- Added the Step 2 executable boundary tests: exact ten-run digest parity, CLI
  PASS output, missing-bootstrap no-fallback, reference tamper, incomplete
  Journal rejection, and honest final-only divergence reporting.
- The focused suite is intentionally red at collection because
  `market_data.exact_replay` does not exist yet. This establishes the TDD
  implementation boundary before product code is added.
- Added `market_data.exact_replay` with strict finalized artifact loading,
  cross-session/content/version/initial-state validation, preserved journal
  envelope replay through the existing Ingestor, independent versioned digest
  ownership, semantic Health digesting, ten-run determinism, and bounded digest
  comparison.
- Extended the existing Journal verification result with its already-validated
  canonical records so exact replay does not implement a second permissive
  Journal parser.
- Kept `replay_cli.py` thin: Journal-only `--verify` remains backward
  compatible; supplying Bootstrap and InstrumentReference activates exact mode,
  prints per-digest MATCH/MISMATCH, and returns non-zero on failure.
- Initial Step 2 focused suite is green: 6 tests passed across success and the
  approved fail-closed boundaries.
- Expanded Step 2 coverage to 12 tests: real module entrypoint, Journal SHA
  mismatch, projection-version mismatch, initial-state digest mismatch, exact
  disposition record linkage, and proof that the legacy runtime Health digest
  is not replay truth.
- Scoped Ruff, line-length, trailing-whitespace, compileall, and `git diff
  --check` passed. Adjacent exact/journal suite passed 28 tests; broader
  Journal/pipeline/ingestion/legacy replay regression passed 50 tests.
- Final full repository regression passed: 587 tests passed and 1 skipped.
  Ruff, compileall, CLI help/entrypoint, contract JSON/fence checks, scoped
  `git diff --check`, line length, trailing whitespace, and runtime-import scope
  all passed.
- Scope audit confirms only `market_data.replay_cli` imports the exact replay
  application module; no production runtime, Store, scanner, Momentum, Paper,
  Candidate, Score, Position, Order, or Strategy authority was wired.
- **Status:** exact replay engine implementation complete. P1.1b historical
  qualification remains pending one real four-artifact session; no synthetic
  fixture is promoted to evidence.

## 2026-08-20 — P1.1b implementation formal acceptance

- **Status:** implementation_passed; historical_qualification_pending
- User formally accepted the contract freeze, engine correctness,
  deterministic replay, digest comparison, failure handling, and CLI gates.
- Historical qualification remains the active gate and requires one genuine
  production-like lifecycle that emits all four finalized artifacts.
- No artifact was created, no product/runtime code changed, and P1.2/consumer
  migration remains blocked in this status-only update.

## 2026-08-20 — Historical qualification matrix

- **Status:** ACTIVE; Case A + Case B required
- Split the qualification gate into Case A normal-session evidence and Case B
  incident/rejection semantic-Health evidence.
- Both cases require a genuine finalized five-file session directory and exact
  CLI PASS with disposition, Bar, Book, and Health matches across ten runs.
- Case A alone does not unlock P1.2. No code or artifact was changed in this
  planning-only refinement.
- Execution order is Case A first and naturally occurring Case B second. No
  fake reconnect, clock skew, rejection, or other incident may be introduced
  merely to satisfy qualification.

## 2026-08-20 — Qualification capture harness started

- Audited the current seams and confirmed the missing component is the
  production-like capture lifecycle, not another replay implementation.
- Reusing `ShioajiMomentumStream` preserves the existing lightweight callback,
  paired Tick/BidAsk ACK, and `subscribe_trade=false` login contracts.
- Implementation remains flags-off and standalone. It will neither attach to
  the production runtime nor unlock P1.2; only real Case A and natural Case B
  qualification evidence can change that gate.

## 2026-08-20 — Qualification capture harness completed

- Added the standalone `market_data.qualification_capture_cli` and application
  lifecycle. It checks flags before provider connection, reuses
  `ShioajiMomentumStream`, forces the existing `subscribe_trade=false` login,
  and has no order/consumer authority wiring.
- Added real contract/snapshot bootstrap capture, paired-subscription boundary,
  bounded callback admission, single worker drain, durable five-artifact
  finalization, live-derived ProjectionState, automatic ten-run exact replay,
  and a non-promoting qualification report.
- Added fail-closed Case A stream/Health checks and natural Case B
  classification without any incident-injection CLI.
- Added a reviewed TWSE 2026 equity calendar artifact with source URLs and
  digest-bound Bootstrap identity; the TAIFEX calendar is not reused.
- Focused qualification/replay/journal/Shioaji suite passed 42 tests. Full
  repository regression passed 664 tests with 1 skipped. Scoped Ruff,
  compileall, CLI help, and diff checks passed. Repository-wide Ruff still
  reports pre-existing unrelated script/import findings and was not modified.
- **Status:** harness implementation complete. No Shioaji session was started
  and no real qualification evidence was claimed. Historical Qualification
  remains ACTIVE; Case A and natural Case B are both pending, and P1.2 remains
  blocked.
