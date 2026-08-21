# Progress: Trade Management Enhancement

## 2026-08-20

- User approved TM-012C-preflight-fix. Ingress Timestamp, Rehearsal Fixture, and Real Stream
  Post-fix Diagnostic gates are PASS. Production Shadow Gate remains NOT PASSED. The incorrect home
  path appeared only in the prior response; repository and runbook paths are correct.
- Frozen the next full-session qualification as six conjunctive gates: FINALIZED canonical session,
  zero lost evidence, at least one authoritative local-paper BUY fill activation, restart-safe
  PostgreSQL reconstruction, matching controlled-recovery digest, and MATCHED exact replay parity.
  A session without a qualifying fill is INSUFFICIENT_EVIDENCE, not a failure and not a gate pass.
- User approved the partial diagnostic and authorized the two preflight blocking fixes. Opened
  Phase 27 with a strict scope: shared Tick/BidAsk callback ingress ordering plus one fixture
  consistency repair; no new Trade Management feature or execution authority.
- Added failing-first stream tests. The old implementation delivered BidAsk before a deliberately
  delayed earlier Tick and clamped a regressed clock; both tests failed as expected.
- Added one shared market-callback ingress lock around observation/sequence/mapping/handler delivery
  and removed the timestamp clamp. Shioaji stream tests now pass 11.
- Corrected the operational composition fixture's envelope, payload, and test pipeline session date
  to the immutable observed fill date. The strict production event/ingestor contracts were not
  relaxed. Stream/composition/operation targeted tests pass 24.
- Broad ordering, duplicate, Journal, exact replay, qualification, composition, recovery, parity,
  and Shadow evidence verification passes 87 tests. Proceed to full regression and scope checks.
- Full repository regression passes 949 tests with 2 skips. The concurrency reproducer passes 20
  repeated runs; compileall and scoped diff/whitespace checks pass.
- Post-fix data-only preflight now reports only `SESSION_WINDOW_NOT_FUTURE`; `REHEARSAL_FAILED` is
  resolved. Provider login/logout and PostgreSQL checks remain safe and no execution path was added.
- A 60-second real 2330 postfix capture passes CASE_A: 102 events / 204 records, 0 rejected, queue
  drained, Journal FINALIZED, and exact disposition/bar/book/health replay MATCHED across 10 repeats.
- Sealed `research/trade_management_shadow/preflight_fix_validation_20260821.json` and updated the
  runbook. Phase 27 is complete; this evidence is not a full Shadow session and Production Shadow
  Gate remains NOT PASSED.

- On 2026-08-21 at 09:11 Asia/Taipei, the user authorized immediate execution of every safely
  verifiable partial-session component. Opened Phase 26 as non-qualifying diagnostic work; the
  complete-session requirement and Production Shadow Gate remain unchanged.
- The live partial preflight proved data-only Shioaji 1.7.2 login/logout and read-only PostgreSQL 17
  readiness with 0/0/0 formal evidence rows. It correctly returned BLOCKED because the session
  started after 09:00; the rehearsal also exposed a test-fixture date/time mismatch.
- Started a five-minute real 2330 Tick/BidAsk qualification capture. Connection/subscription ACKs
  succeeded, but the consumer thread later failed closed with `DataHealth time cannot move backward`;
  investigate the captured event/clock ordering after the runner terminates.
- The partial capture preserved 928 real ingress events / 1,855 records (843 BidAsk, 85 Tick). The
  first fatal ordering race is a paired BidAsk/Tick callback at one exchange timestamp whose
  `received_at` values moved backward by 19.361 ms. Journal verification reports 919 applied, 8
  rejected, and correctly refuses exact replay because the artifact is INCOMPLETE.
- Rechecked the formal PostgreSQL target outside the network sandbox using a read-only transaction:
  schema/migration remain valid and evidence rows remain 0/0/0. No fixture or partial session polluted
  the formal Shadow evidence Journal.
- The remaining Shadow/replay/recovery/validation contract set passes 26 tests with the one known
  fixture date/time test explicitly deselected. No file-backed authoritative local-paper fill was
  available, so no Shadow decision session was manufactured.
- Sealed `research/trade_management_shadow/partial_session_diagnostic_20260821.json` as explicitly
  non-qualifying diagnostic evidence. Phase 26 is complete; Production Shadow Gate remains NOT PASSED.

- Received user approval for PR-TM-012B2. The operational composition milestone is closed with no
  execution authority; Production Shadow Gate remains NOT PASSED.
- Opened PR-TM-012C as an operational evidence phase only. At 17:46 CST the 2026-08-20 market session
  was already over, so no partial or synthetic session was recorded as first-real-session evidence.
  The reviewed local TWSE calendar has no closure entry for the next scheduled weekday, 2026-08-21.
- Started PR-TM-012C0 pre-market readiness. Confirmed the project declares a postgres optional extra
  but `.venv` initially lacked psycopg. The restricted install could not reach the package index;
  approved network retry installed psycopg/psycopg-binary 3.3.4 into the project environment.
- Added pure pre-market manifest/provider/PostgreSQL/rehearsal/report contracts plus a fail-closed
  evaluator. The core has no environment, provider, DB, Journal, decision, order, or execution access.
- Added `preflight_trade_management_shadow.py`: it binds the reviewed calendar and runtime versions,
  performs data-only login/logout, queries PostgreSQL with transaction read-only enabled, runs the
  fixed rehearsal suite, redacts secrets, and writes an immutable JSON plus report-digest sidecar.
- Executed the real C0 preflight outside the restricted network sandbox. Shioaji 1.7.2 simulation
  login/logout passed with `subscribe_trade=false`; PostgreSQL 17 and migration `001_journal.sql`
  matched, and formal session/record/checkpoint tables remained 0/0/0.
- Sealed `research/trade_management_shadow/premarket_20260821.json` with zero blockers and report
  digest `4e233ae941f9bef4d51752fb0ea6f33917fb25e31409c4ddf114bfdc89eda973`.
  Rehearsal source is explicitly non-qualifying and Production Shadow Gate remains NOT PASSED.
- C0 contract/artifact plus replay/composition/recovery/validation tests pass 39; full repository
  regression passes 902 with 2 skips. Compileall and whitespace checks pass. No commit/push or
  execution capability was added.
- Received the corrected PR-TM-012B2 approval: operational composition must reuse PR-TM-012A fill
  activation and PR-TM-012B1 draft creation, not introduce a parallel activation lifecycle.
- Added a deterministic `BuyScoreEntryEvidenceAdapter` that snapshots the existing BuyScore total and
  per-rule breakdown as typed evidence. It does not classify matched rules, choose a threshold, or
  modify CandidateEngine/BuyScoreEngine.
- Added read-only `ExistingPaperFillObserver`. It finds exactly one correlated immutable local-paper
  BUY fill in the source Journal, fails closed on absence/conflict, and delegates all activation
  validation to the existing `PaperFillThesisBuilder`.
- Added `LiveTradeManagementOperationalComposer`: Decision -> Draft -> observed fill -> activation ->
  existing Shadow operation/capture runner. Fill history and Shadow evidence must be separate Journal
  authorities; the evidence adapter remains compatible with the shared PostgreSQL Journal port.
- Restart reconstruction produces the same fill fingerprint, activation ID, and activation digest.
  An applied canonical event reaches the composed Shadow operation and appends immutable decision
  evidence; no product code creates a fill or invokes an order, Position, broker, Shioaji, or RiskGate.
- PR-TM-012B2 targeted tests pass 7; the focused composition/activation/capture/operation/PostgreSQL
  adapter set passes 38 with 1 skipped; full repository regression passes 874 with 2 skipped.
  Production Shadow Gate remains NOT PASSED because real full-session/multi-day evidence is pending.
- Received PR-TM-012A framework approval; PR-TM-012B and the Production Shadow Gate remain pending.
- Confirmed `.env` contains `PostgreSQL_DSN` without printing its value. A robust dotenv parse was
  required because the mixed-case key was missed by the earlier simple shell key scan.
- Completed a read-only PostgreSQL preflight outside the restricted sandbox: target fingerprint
  `083fcb4d1c8e3976`, PostgreSQL major 17, and zero current-schema tables before bootstrap.
- Applied only the existing `001_journal.sql` contract, then registered it through the forward-only
  migration runner. Verified four schema tables, six indexes, and zero session/record/checkpoint rows.
- Re-ran the local PaperFill activation, live Shadow operation, and durable evidence regressions:
  25 passed. No real-market session evidence was fabricated after market close.
- Received approval to continue PR-TM-012B infrastructure readiness while keeping the Production
  Shadow Gate not passed.
- Added a provider-neutral `LiveShadowCaptureRunner` outer adapter. It accepts an already-built
  PaperFill activation and existing Shadow operation, binds provider/version/connection identity into
  the Journal session, waits for paired subscription ACK, resequences admitted events, maps lifecycle
  incidents, counts pre-ACK events, drains pending work, and finalizes durable evidence.
- The runner deliberately has no Thesis builder, local-paper submission, DSN loader, PostgreSQL
  connection, Shioaji SDK, broker, order, SELL, or execution authority. A full operational composition
  entry point remains pending.
- Targeted runner tests pass 7; combined activation/Shadow/Journal/validation regressions pass 46.
  Compileall and scoped whitespace checks pass.
- Full repository regression reached 837 passed and 2 skipped, with one unrelated failure because an
  institutional price-acquisition `.canonical.sha256` artifact is absent. No out-of-scope artifact was
  created or modified.
- Audited the final operational composition input. Production code has no `TradeThesisDraft`
  construction point: the only constructor call outside the strict reader is in test builders, while
  Candidate/BuyScore do not emit the frozen entry-evidence, strategy-version, expected-behavior, and
  invalid-condition contract. Stopped before inventing entry semantics inside the capture runner.
- Received approval to implement PR-TM-012B1 as a deterministic contract/builder-only phase.
- Added immutable `LiveEntryDecision` with builder version, canonical timestamps/Decimal, score,
  sorted matched rules, sorted typed entry evidence, market-context digest, content-derived input
  digest, and deterministic decision ID. Any content change invalidates the identity.
- Added strict canonical EntryDecision serialization/reader support. Unknown fields, unknown enums,
  duplicate JSON keys, non-canonical Decimal values, identity mismatch, and version mismatch fail
  closed; the reviewed canonical serialization SHA-256 is frozen in tests.
- Added `LiveThesisDraftPolicy`, `LiveEntryDecisionBuilder`, and `LiveTradeThesisDraftBuilder`. The
  policy ID is bound to the persisted expected-behavior policy ID; strategy/version/side mismatch is
  rejected; output is the existing immutable TradeThesisDraft with no order/fill/activation fields.
- PR-TM-012B1 targeted tests pass 8, combined Trade Management lifecycle tests pass 94, and the full
  shared repository now passes 860 with 2 skips. The previously absent institutional digest appeared
  through unrelated shared-worktree activity; this phase did not modify it.
- No CandidateEngine, BuyScoreEngine, Journal persistence, paper order, fill, TradeThesis activation,
  RiskGate, Shadow wiring, Broker, SELL, Position mutation, commit, or push was added.

- Received PR-TM-005 approval and started Phase 13, PR-TM-006 Simulation / Replay Validation.
- Reordered the working roadmap per review: deterministic Historical Tick decision-chain replay now
  precedes durable guard enforcement and Shadow.
- Confirmed the canonical input seam is `market-event-v1` Tick envelopes and the output seam is the
  existing frozen Trade Management replay identity/digest contract; no second event schema will be
  introduced.
- Added failing-first replay tests, observed the expected missing-module red phase, then implemented
  the pure replay reducer/harness. The focused PR-TM-006 suite now passes 6 tests.
- The first combined verification command used one nonexistent test filename; recorded the error and
  routed canonical event codec coverage to `test_market_event_contract_freeze.py`.
- Completed PR-TM-006: canonical Historical Tick reduction, hard-invalid and deadline/time-decay
  replay, Recommendation/Eligibility chaining, frozen output, exact manifest/version validation, and
  empty-Journal evidence semantics.
- Verification passed: PR-TM-006 targeted 6, combined decision-chain/market contracts 98, full suite
  734 passed with 2 skipped. No commit or push was performed.
- Received PR-TM-006 approval and started Phase 14, PR-TM-007 Shadow Decision Pipeline.
- Reordered the working roadmap again per review: decision-only live Shadow parity now precedes
  durable guard persistence; execution remains prohibited.
- Mapped the live integration seam to post-ingest canonical `EventEnvelope` consumption. Chose an
  independent Shadow consumer rather than modifying shared Shioaji/ingestion/momentum runtime files.
- Froze the implementation approach: incremental shared decision kernel, per-event RiskSnapshot,
  finalize-time manifest identity, and exact live-to-replay parity report.
- Added failing-first Shadow tests and the new Shadow consumer/contracts. The first green run exposed
  a test-fixture mistake: its timestamp was repeated but ingress sequence still increased, so it was
  correctly ordered. Corrected the fixture to use a lower watermark sequence.
- Extracted the PR-TM-006 transition into a shared immutable decision state/kernel and retained all 6
  approved replay tests. Added per-event risk evidence replay without changing existing default input.
- Completed PR-TM-007 Shadow records, exact-duplicate idempotency, conflict/order/session fail-closed,
  finalize-time manifest identity, and live-to-replay parity verification.
- Verification passed: Shadow targeted 6, combined contracts 116, full suite 749 passed with 2 skipped.
  No commit or push was performed.
- Received PR-TM-007 approval and started Phase 15, PR-TM-008 Durable Decision Journal / Shadow
  Evidence Persistence.
- Kept the new phase evidence-only: existing Journal repository is the durability authority, while
  Shadow records cannot mutate Trade/Position/Order state.
- Confirmed generic Journal canonical bytes, idempotency, checkpoint and PostgreSQL compatibility can
  be reused without changes or migration. Selected two Shadow evidence facts (decision, finalized)
  and a v1 retain-all/no-compaction policy.
- Added failing-first Journal tests and implemented the evidence adapter/projection. Self-review added
  full RiskSnapshot value-to-digest validation and explicit shadow/replay decision digests in matched
  finalization evidence. Adjusted one test to assert the adapter's stable wrapped decode error.
- Completed strict nested evidence decoding, deterministic Journal records, retry/partial-resume,
  restart projection/checkpoint verification, finalization ordering, full risk evidence, and the v1
  retain-all/no-compaction contract.
- Verification passed: evidence targeted 9; combined Journal/Trade Management 119 with 1 conditional
  PostgreSQL skip; full suite 768 passed with 2 skipped. No commit or push was performed.

- Started a plan-only repository review.
- Kept the existing root planning context untouched because it belongs to an active freshness-calibration task.
- Created an isolated planning workspace for this request.
- Inspected the current Candidate, Buy Score, Position, Exit Rule, MarketDataStore, local simulation, and historical backtest seams.
- Identified the main integration risk: entry/exit state is split across a legacy decision view, local simulation, and backtest rather than owned by one current `PositionManager` runtime.
- Traced the existing Journal-first local-paper command path, versioned RiskGate, replay projection, injected clock, and backtest exit aggregator.
- Resolved that the plan should extend these foundations rather than create duplicate risk/event infrastructures.
- Wrote `architecture/trade_management_enhancement_implementation_plan.md` with domain contracts, six implementation phases plus Phase 0, file-level changes, tests, observability, rollout, rollback, and Definition of Done.
- Cross-checked plan invariants for delayed fills, pending BUY races, BUY/SELL guard separation, data insufficiency, canonical market pipeline dependency, and no automatic order side effects.
- Verified the new Markdown has balanced code fences and no trailing whitespace; existing unrelated worktree changes were preserved.
- Received user review approving the architecture direction and requesting explicit thesis versioning, `ExitReason`, Historical Tick Replay support, and Phase 0-6 reordering.
- Started a plan-only v0.3 revision; no product implementation is authorized by this revision.
- Revised the plan to v0.3 with explicit `thesis_version`, stable `ExitReason`, partial-exit legs, lifecycle states, and Historical Tick Replay contract.
- Reordered Phase 0-6 and PR-TM-001 through PR-TM-009 to keep Journal before Monitor and Simulation validation before Controlled Shadow rollout.
- Added a Phase 0 contract review checklist; explicitly retained decision-only/local-paper and no-broker/no-auto-SELL boundaries.
- Received Phase 0 review approval plus four hardening gates: canonical timestamps, recommendation idempotency, deterministic Replay, and no hidden mutation.
- Started a v0.4 plan-only revision and identified one concrete defect to fix: v0.3 recommendation identity included `source_event_id`, which did not by itself guarantee one active recommendation per trade.
- Completed v0.4 contract hardening: canonical timestamp roles, first-fill Thesis clock, one active
  recommendation per trade, deterministic Replay identity/digest, pure ThesisMonitor boundary, and
  separate Decision／Order／Trade lifecycle state machines.
- Expanded Phase 0 fixtures/tests and Section 20 merge gates; review is now marked approved to start
  PR-TM-001, while all completion checkboxes remain open until implementation evidence exists.
- Revalidated the plan-only boundary: no runtime or product implementation was started.
- Received explicit approval to start PR-TM-001 with a strict Contract Freeze boundary.
- Started Phase 7. Explicitly excluded ThesisMonitor, exit calculation, Shioaji/SELL integration,
  RiskGate changes, Journal wiring, Replay engine changes, and all trading behavior changes.
- Added new contract-only modules `trading/trade_management.py` and
  `trading/trade_management_serialization.py`. They contain immutable timestamp/thesis/lifecycle/
  exit/recommendation/Replay contracts, deterministic IDs, transition tables, and canonical JSON
  writers only; no existing runtime module was edited.
- Added deterministic test builders plus contract tests for timestamp provenance, independent
  lifecycle state machines, first-fill trade identity, per-event decisions versus per-trade
  recommendations, partial exit legs, Replay digest binding, immutability, and forbidden runtime
  dependencies.
- Added five `trade-management-v1` golden JSON fixtures covering TradeThesis,
  ExitRecommendation, partial TradeOutcome, ReplayVerification, and all lifecycle tables.
- First combined targeted run found one fixture-only precision typo; logged it and corrected the
  fixture without changing domain or serializer behavior.
- Contract self-review added the missing `ThesisStatus` wire enum, canonical ORB condition ordering,
  Replay divergence-to-output binding, exact enum tests, and a corrected partial-exit fixture PnL.
- Targeted PR-TM-001 suite passes: 20 tests.
- Existing RiskGate, Journal, order application, local-paper projection/command, and simulation
  regression subset passes: 32 tests.
- Compileall, `git diff --check`, and forbidden execution/wall-clock symbol scan pass.
- Full repository suite passes: 548 passed, 1 skipped.
- Added final contract evidence for frozen exit-category priority, recommendation resolution on final
  fill metadata, and ten identical Replay serializations.
- Split implementation-plan Section 20 into a checked, evidence-backed PR-TM-001 DoD and explicitly
  deferred PR-TM-002+ Journal/Monitor/Guard/runtime gates. No downstream behavior checkbox was
  falsely marked complete.
- Expanded the exact-value test to cover every public v1 wire enum, including timestamp, thesis,
  condition, lifecycle, exit, recommendation, and PnL values.
- Final full-suite rerun after all changes passes: 550 passed, 1 skipped.
- Phase 7 completed. The scoped status contains only new PR-TM-001 contract, serializer, test,
  fixture, architecture-plan, and isolated planning files. No commit or push was performed.
- Planning completion helper initially inspected the unrelated root plan because the script accepts a
  file argument rather than `PLAN_ID`; logged the issue and retained the shared active-plan pointer.
- Received user approval for PR-TM-001 and authorization to enter PR-TM-002 Journal Integration.
- Started Phase 8 with a strict persistence/reconstruction-only boundary. Explicitly excluded thesis
  evaluation, exit calculation, RiskGate decisions, broker actions, SELL capability, and market-data
  Replay engine changes.
- Restored session context. The first attempted catchup shell helper did not exist in the installed
  skill; switched to its Python helper and recorded the recovered approval/scope context.
- Reconfirmed the dirty-worktree separation: shared root planning, canonical market, freshness,
  institutional, and `market_data/replay.py` changes remain out of scope.
- Inspected the existing Journal and local-paper projection seams plus the frozen serializer surface.
  Chose an additive sibling adapter: strict v1 aggregate readers, versioned Journal record codecs, and
  one deterministic reconstruction projection; the existing Journal repository remains unchanged.
- Mapped the exact TradeThesis draft/evidence/condition graph and recommendation/outcome schemas needed
  by v1 readers. The reader will instantiate frozen domain models so existing validation remains the
  sole contract authority.
- Compared the existing architecture roadmap to the newly approved PR boundary. Recorded that fill-v2,
  delayed-fill sinks, and runtime lifecycle wiring must be deferred; PR-TM-002 will not implement them.
- Added strict v1 deserialization for `TradeThesisDraft`, `TradeThesis`, `ExitRecommendation`, and
  `TradeOutcome`; readers reject unknown schemas, fields, enum values, timestamp formats, and malformed
  typed condition payloads before reconstructing through frozen dataclass validation.
- Added `trading/trade_management_journal.py` with six versioned fact kinds, canonical record builders,
  contract digest verification, deterministic Journal identity, a pure append-order projection, and
  checkpointed replay helpers. It imports no strategy, risk, market, simulation, position, or broker
  runtime.
- Added reader and Journal integration tests for exact round trips, idempotent retry/conflict,
  deterministic restart replay, digest/sequence corruption, lifecycle ordering, one recommendation per
  trade, checkpoint integrity, unrelated-record handling, and forbidden runtime capabilities.
- First targeted run passed 33 tests and found one test-only false positive: the dependency-boundary
  scan matched the word `RiskGate` in the module docstring. Replaced raw text matching with AST symbol
  and call inspection; product behavior was unchanged.
- Targeted PR-TM-001 plus PR-TM-002 contract/serialization/Journal suite now passes: 34 tests.
- Compile verification passes. Existing Journal, local-paper projection, and order application
  regression subset passes: 18 tests.
- Completed a first source self-review and queued two additive test/codec hardening changes before the
  full suite: canonical decimal notation on read and draft-envelope linkage to the v1 golden thesis.
- Hardened canonical decimal decoding and linked the standalone draft envelope to the existing golden
  TradeThesis draft representation. Targeted suite now passes: 35 tests.
- Added the approved backward-compatibility and enum-evolution rules to the architecture document,
  narrowed the roadmap's PR-TM-002 scope to Journal integration, recorded its evidence-backed merge
  checklist, and kept fill-v2/runtime behavior explicitly deferred.
- Hardened replay against duplicate JSON keys, unknown future Trade Management record kinds, mixed
  Journal sessions, and recommendation resolution metadata that does not match the final exit fill.
- One combined patch initially referenced a Journal class under the serializer path and was rejected
  atomically; verified no partial edit, split by file, and completed the intended hardening.
- Targeted suite after hardening passes: 36 tests.
- Froze all six Journal kind wire values plus golden draft/activation record IDs and canonical contract
  digests. Targeted suite now passes: 37 tests.
- Full repository regression passes: 575 tests passed, 1 skipped. Compileall, trailing-whitespace scan,
  Markdown fence parity, `git diff --check`, scoped status, and no-runtime-capability checks pass.
- Phase 8 completed. Existing `trading.journal`, local-paper runtime, RiskGate, broker paths,
  `market_data/replay.py`, and unrelated dirty-worktree files were not edited. No commit or push was
  performed.
- User confirmed formal PR-TM-002 `REQUEST CHANGES` with two P1 blockers: Decimal scale variants can
  share a business identity while producing different digests, and Journal payload mappings remain
  mutable after append.
- Started Phase 9. Scope is limited to canonical Decimal encoding, immutable canonical Journal payload
  snapshots, regression/golden tests, and evidence updates; PR-TM-003 remains out of scope.
- Audited all Journal payload consumers and the PostgreSQL adapter. Existing callers are read-only and
  PostgreSQL already persists `payload_json`, so a construction-time immutable byte snapshot can be
  introduced without changing repository protocols, database schema, or runtime authority.
- Added failing-first blocker tests and a Decimal golden fixture covering scale collapse, negative
  zero, plain exponent output, reader rejection, source/nested payload mutation, repository history,
  and checkpoint stability. The red run fails at collection because the intentionally referenced shared
  canonical helper does not exist yet.
- Implemented the shared canonical Decimal encoder and construction-time Journal payload bytes/frozen
  view. First green attempt exposed a compatibility edge: `dataclasses.replace()` passes the frozen
  mapping view back to the constructor. Added explicit read-only `Mapping` JSON support without
  weakening the stored snapshot.
- Blocker test set passes: 38 tests. Added explicit evidence that equivalent Decimal scales produce one
  Trade Management record ID, fact digest, and Journal fingerprint before broader regression.
- Broader Journal/local-paper/order/recovery/Trade Management regression passes: 72 tests, 1 skipped.
- Self-review identified canonical DECIMAL evidence strings as the final unguarded numeric wire seam;
  add a domain validation test before completing the blocker fix.
- The first evidence test run failed at test setup because `EvidenceValue` was not imported; logged the
  issue, added the explicit import, and enforced the shared canonical Decimal rule in the domain value
  object so string-backed decimal evidence cannot bypass the serializer contract.
- The next run exposed a patch-placement mistake that moved the existing enum assertion loop under a
  parametrized evidence test. Restored the original test boundary without changing product code.
- Direct blocker verification passes: equivalent Decimal variants yield exactly one JSON, record ID,
  fact digest, and fingerprint; payload mutation raises `TypeError`; authoritative payload is bytes.
- Compileall, whitespace, and diff checks pass. Full suite currently reports 623 passed, 1 skipped, and
  one institutional candidate-prior digest mismatch in unrelated dirty-worktree code; isolate and
  verify that concurrent failure without changing institutional files.
- The isolated institutional digest test passes immediately on rerun and has no imports/dependencies on
  Journal, canonical Decimal, or Trade Management modules. No out-of-scope file was edited; rerun the
  full suite against the now-stable shared worktree.
- Stable full-suite rerun passes: 625 tests, 1 skipped. The earlier institutional mismatch was transient
  concurrent worktree state.
- Updated the PR-TM-002 contract/checklist with evidence-backed Decimal and Journal immutability blocker
  resolutions. Phase 9 is complete and ready for user re-review; no commit, push, or PR-TM-003 work was
  performed.
- Final targeted Trade Management suite passes 57 tests; focused Journal/Trade Management set passes
  64 tests. Planning completion gate reports all 9 phases complete.
- User approved PR-TM-002 to merge after confirming both P1 fixes and unchanged scope. No branch,
  commit, push, or merge operation was requested or performed in the shared dirty worktree.
- Started Phase 10 / PR-TM-003 with a strict status-only boundary: pure immutable inputs and
  `ThesisEvaluation` output; no ExitRecommendation, Order, SELL, Position/Risk mutation, Journal,
  scheduler, Replay engine, broker, or runtime wiring.
- The initially attempted planning recovery helper used an obsolete filename. Located the current
  helper and restored the isolated plan directly; product code was unaffected.
- Added failing-first PR-TM-003 tests for status/time boundaries, hard invalid conditions, unreliable
  or missing observations, invalid latch, deterministic immutability, identity validation, and the
  no-execution dependency boundary. The global shell lacked `pytest`; switched to the repository
  virtual environment before running the red phase.
- Implemented the immutable market context, structured condition/evaluation results, deterministic
  input/evaluation identity, typed ORB condition checks, fill-relative warning/deadline boundaries,
  invalid latch, and fail-closed data states. A test-patch placement error was caught by the combined
  suite and corrected without changing product semantics.
- Self-review removed Decimal division from volume-ratio evaluation: integer observed shares are
  compared to `baseline * ratio`, so global Decimal division precision cannot change replay output.
  Added exact strict-new-high and inclusive-volume threshold tests plus stronger context/evaluation
  validation.
- PR-TM-003 targeted monitor suite passes 27 tests; combined Trade Management contract,
  serialization, Journal, and monitor suite passes 84 tests. Compileall and scoped diff checks pass.
- Full repository regression passes: 657 tests, 1 skipped. Architecture Section 22 records the
  evidence-backed status-only checklist and explicitly defers context reducer/registry, deadline
  scheduler, Journal transition persistence, bar adapter, and runtime wiring.
- Phase 10 completed and is ready for user review. No commit, push, actual merge, recommendation,
  SELL, broker, RiskGate, Position, Journal, Replay engine, or runtime behavior change was performed.
- User approved PR-TM-003 and authorized PR-TM-004. Recorded that PR-TM-003 already has stable typed
  reason codes; no follow-up enum change is needed.
- Started Phase 11 with a pure decision/recommendation-only boundary. Inspected the frozen
  ExitDecision/ExitRecommendation identity and lifecycle contracts and narrowed the initial engine to
  Thesis status/reason mapping plus immutable open-position context. Adapters, Journal, RiskGate,
  Position mutation, Order, SELL, broker, Clock, Replay engine, UI, and runtime wiring remain excluded.
- Added failing-first PR-TM-004 tests and implemented the first pure engine slice. Initial targeted
  suite passes 12 tests and combined Trade Management suite passes 96 tests.
- Source self-review caught a contract-level no-op issue before full regression: the first green
  implementation updated recommendation latest evidence for every new INVALID event even when
  reason/priority were unchanged. Revise the result contract with a material-change flag and keep the
  active snapshot unchanged for no-op evidence, as required by v0.4 Journal-spam prevention.
- Added `recommendation_changed` to the pure result. Exact retries and new events with unchanged
  reason/priority now return the byte-identical active recommendation with the flag false; a new or
  reprioritized reason returns one updated snapshot with the flag true. Combined Trade Management
  verification now passes 97 tests.
- Full repository regression passes: 677 tests, 1 skipped. Updated the roadmap and Section 23 with the
  evidence-backed PR-TM-004 checklist, including typed reason mapping, HOLD/EXIT semantics,
  deterministic identity, one-active-recommendation/no-op rules, and authority isolation.
- Phase 11 completed and is ready for user review. Stop/ATR/Take Profit adapters, Journal persistence,
  backtest/local-paper read models, RiskGate, warning scheduler, Position mutation, Order, SELL,
  broker, Replay engine, UI, and runtime execution remain explicitly deferred. No commit or push was
  performed.
- User approved PR-TM-004 and authorized PR-TM-005. Recorded recommendation version/expiry as deferred
  compatibility/lifecycle work rather than changing the approved v1 wire.
- Started Phase 12. Inspected existing RiskGate and confirmed a concrete direction bug: strategy
  origin, daily loss, and order-notional entry guards currently block SELL as well as BUY. Narrowed
  PR-TM-005 to a pure recommendation eligibility method on the existing RiskGate plus BUY-only guard
  correction; no duplicate guard, command creation, Journal, application service, Position mutation,
  SELL execution, broker, or runtime wiring.
- Added failing-first eligibility and BUY/SELL direction tests, then implemented immutable eligibility
  contracts, deterministic input/identity digest, the pure RiskGate recommendation method, and
  BUY-only entry guards. The first green run caught test assertion displacement from patch placement;
  restored the existing test boundary without changing product semantics.
- Hardened eligibility evidence with canonical Decimal scale collapse, frozen public status values,
  full policy-value digest binding, ten-run determinism, ACTIVE recommendation identity/time checks,
  and explicit no-command/no-application dependency tests.
- RiskGate/application/eligibility plus combined Trade Management verification passes 132 tests;
  compileall and scoped diff checks pass. Proceed to full repository regression before marking the
  phase complete.
- First full regression passed 728 tests with 2 skips. Final version audit then added explicit
  `RISK_GATE_VERSION` ownership to the eligibility output/input digest; rerun targeted and full
  verification after this contract hardening before recording final evidence.
- Final post-version-hardening verification passes: eligibility/RiskGate targeted 23 tests, combined
  RiskGate/application/Trade Management 132 tests, and full repository 728 tests with 2 skips.
- Updated roadmap and Section 24 with the evidence-backed PR-TM-005 contract, direction correction,
  deterministic artifact/version ownership, authority boundary, and explicit deferred guard/execution
  work. Phase 12 is complete and ready for user review.
- No Journal/application/Position/simulation/Replay/dashboard/broker module was changed for
  eligibility integration; no command was created by product code, no SELL executed, and no commit or
  push was performed.
- User approved PR-TM-008 Durable Shadow Evidence after confirming existing Journal reuse, immutable
  evidence, retry/partial-resume idempotency, RiskSnapshot preservation, parity evidence, restart
  recovery, retain-all policy, and absence of execution authority.
- Started Phase 16 / PR-TM-009 Live Runtime Composition / Shadow Operation. The approved scope is a
  decision-only/evidence-only composition from the formal canonical market pipeline into the shared
  Shadow kernel and existing Journal; automatic SELL, broker/Shioaji order calls, Position mutation,
  and real money remain prohibited.
- Repository tracing selected a wrapper over `CanonicalMarketDataPipeline.process_pending()` rather
  than editing Shioaji callbacks or the dashboard/local-paper `RuntimeComposition`. This preserves
  record-before-ingest ordering and gives the Shadow consumer the exact applied/rejected disposition.
- Added failing-first PR-TM-009 operation tests. The expected red run fails only because
  `runtime.trade_management_shadow` does not exist yet; implement that isolated orchestrator next.
- Implemented `LiveTradeManagementShadowOperation` as an outer-layer wrapper over the existing
  canonical pipeline. It processes one recorded/ingested result at a time, consumes only
  projection-applied events, injects the event-time RiskSnapshot, and immediately appends immutable
  Shadow decision evidence.
- Added fail-closed writer recovery: a failed decision append remains pending and must be retried
  successfully before the operation dequeues another canonical message. No market event is
  synthetically repaired or silently advanced past missing decision evidence.
- Finalization is idempotent and persists the parity artifact, writes the existing Shadow projection
  checkpoint, then rebuilds and compares the durable projection digest before returning success.
- PR-TM-009 targeted operation tests pass: 6 tests. Combined canonical market, Journal, replay,
  Shadow, Thesis, recommendation, eligibility, RiskGate, and runtime contracts pass: 157 tests.
- Full repository regression passes: 774 tests, 2 skipped. No Shioaji callback/order, Broker,
  OrderCommand, SELL, Position mutation, dashboard/local-paper runtime, or real-money capability was
  added. No commit or push was performed.
- User approved PR-TM-009 Live Shadow Operation and selected PR-TM-010 Shadow Observability /
  Production Readiness Gate. Started Phase 17 with a strict read-only metrics/report boundary; no
  execution discussion or capability is authorized.
- Added failing-first observability/readiness tests and implemented the first immutable metrics plus
  pure multi-session readiness slice. Initial operation/observability tests pass 11 tests.
- Self-review found finalization/checkpoint failures were not yet counted by the decision-writer health
  path. Extended the same BLOCKED/RECOVERING accounting to finalization and added a retry regression
  before broader verification.
- Added canonical event-backlog metrics and a finalize gate: admitted/processed counts, pending market
  event count, and oldest pending event age are measured from injected canonical timestamps; a session
  cannot finalize while accepted canonical messages remain queued.
- Hardened observability contracts with finite canonical Decimal values, exact pending/durable/lost
  evidence invariants, parity divergence sequence, divergent session identities, deterministic policy
  binding, and an explicit `execution_enabled=False` readiness report.
- PR-TM-010 observability/operation tests pass: 13 tests. Combined canonical market, Journal, replay,
  Shadow, Thesis, recommendation, eligibility, RiskGate, runtime, and readiness contracts pass: 164.
- Final post-hardening repository regression passes: 791 tests, 2 skipped. Compileall, trailing-whitespace,
  `git diff --check`, dependency-authority tests, and the isolated planning gate pass; all 17 phases
  are complete. No commit or push was performed.
- User approved PR-TM-010 Shadow Observability / Production Readiness Gate and selected PR-TM-011
  Extended Shadow Validation / Operational Readiness. Started Phase 18 with a strict evidence-only
  boundary; actual one-day/multi-day market evidence and execution remain unclaimed and unauthorized.
- Added failing-first validation tests and the initial pure validation contracts/evaluator. The first
  green run exposed a test-fixture type error (`timedelta` rejects Decimal seconds); corrected the
  fixture to use integral seconds without changing product semantics.
- Hardened qualification so incomplete/non-live sessions cannot satisfy cross-date thresholds and one
  successful drill cannot hide a failed drill of the same type. Added the operational runbook and
  explicit fixture-versus-real-market evidence boundary.
- PR-TM-011 validation tests pass 8 tests; combined Trade Management/market/Journal/Shadow contracts
  pass 172 tests; full repository regression passes 805 tests with 2 skips. Compileall, whitespace,
  scoped diff, and no-authority scans pass. Actual real-market session evidence remains pending; no
  commit, push, order, SELL, broker, or real-money capability was added.
- User approved PR-TM-011 for framework merge only and selected PR-TM-012 Real Shadow Evidence
  Collection. Started Phase 19 at 16:33 CST, after Taiwan market hours; inspect the existing runtime
  and evidence seams before deciding what evidence can honestly be collected today.
- Verified `.env` has Shioaji credential keys without exposing values. The sandboxed SDK probe exited
  139 because native inter-thread socket binding was prohibited; an approved external data-only retry
  logged in successfully as `shioaji:1.7.2:simulation=true`, used `subscribe_trade=false`, and logged
  out cleanly.
- Recorded a non-qualifying preflight artifact. Full-session evidence remains false because the probe
  occurred after market hours; no PostgreSQL Journal DSN, authoritative TradeThesis artifact, or Trade
  Management live-capture entry point exists yet.
- Preflight artifact SHA-256 is
  `ce35c73a030c1dbd5bb83122aeec0ada6a12237622448d4565f9578ec0a01be1`; JSON parsing and
  whitespace checks pass. Phase 19 remains in progress and Production Shadow Gate remains NOT PASSED.
- User selected the recommended authoritative source: activate TradeThesis only from the next
  local-paper BUY fill. Started Phase 20 / PR-TM-012A with a pure builder boundary and minimal new-fill
  provenance; manual Thesis JSON and Shioaji stream wiring remain out of scope.
- Added failing-first builder/provenance tests and the initial implementation. The first green run
  exposed that the legacy simulation parses its ISO fill time into a fixed `+08:00` timezone rather
  than canonical `Asia/Taipei`; normalize the same immutable instant at the builder boundary.
- PR-TM-012A targeted builder tests pass 10 tests; combined local-paper/provider/Trade Management
  contracts pass 112 tests; full repository regression passes 821 tests with 2 skips. New fills retain
  explicit paper/provider/no-execution provenance while old fills remain accounting-replayable only.
- Updated the operational runbook and architecture checklist. Phase 20 is complete and ready for
  framework review; PR-TM-012B, PostgreSQL, full-session evidence, and Production Shadow Gate remain
  pending. No commit, push, Broker, SELL, Shioaji order, or execution enablement was performed.
