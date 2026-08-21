# Task Plan: Trade Management Enhancement implementation plan

## Goal

Implement the approved Trade Management enhancement in gated PR-sized phases. PR-TM-001 through
PR-TM-001 through PR-TM-010 are approved. PR-TM-011 is approved for framework merge only. PR-TM-012
collects real data-only Shadow evidence without granting order or trade authority.

## Scope boundary

- Inspect current code, tests, and documentation.
- Define exact contracts, ownership, integration seams, phases, acceptance criteria, rollout, and rollback.
- PR-TM-001 may add contract-only product modules and tests.
- PR-TM-005 may add immutable eligibility input/output contracts and a pure RiskGate method over an
  existing ACTIVE ExitRecommendation plus RiskSnapshot. It may narrow existing entry-only RiskGate
  blockers to BUY so future risk-reducing SELL validation is internally consistent.
- PR-TM-006 may add a pure Trade Management replay reducer/harness over existing canonical
  `market-event-v1` Tick envelopes and the frozen policy/version inputs. It may produce immutable
  replay steps and digest evidence, but may not write a Journal or modify the market replay engine.
- PR-TM-007 may add an application-level in-memory Shadow consumer and immutable observation records
  over existing canonical events. It must reuse the PR-TM-006 decision kernel and expose parity
  evidence without authoritative Journal writes, orders, Position mutation, or broker capability.
- PR-TM-008 may add versioned Shadow evidence Journal events, strict readers/builders, append
  idempotency, replay projection, checkpoints, and an explicit retention policy contract. It must use
  the existing Journal repository and keep Shadow evidence separate from authoritative trade facts.
- PR-TM-009 may add an application/runtime orchestrator over the existing synchronous canonical
  market pipeline. It may consume only projection-applied events, inject one immutable RiskSnapshot
  per event, append decision/finalization evidence, and verify a checkpoint at finalization.
- PR-TM-010 may add immutable operation metrics, health transitions, finalized-session summaries,
  and a pure readiness evaluator. Metrics may observe runtime/evidence state but may not influence
  Thesis, recommendation, eligibility, market admission, or execution.
- PR-TM-011 may add immutable validation-session/source identity, operational drill, and validation
  report contracts plus a pure evaluator over PR-TM-010 readiness evidence. Test fixtures must not be
  represented as real production evidence, and validation success must not enable execution.
- PR-TM-012 may inspect and run existing data-only Shioaji/canonical/Shadow paths, seal real-session
  evidence, and produce an evidence manifest/readiness report. It may add only the minimal operational
  adapter or artifact contract needed to make that evidence reproducible; it may not place orders,
  enable execution, or substitute replay/fixture data for a real session.
- Do not create an OrderCommand, invoke OrderApplicationService, add Shioaji/SELL execution behavior,
  Journal/runtime wiring, Position mutation, market-data Replay changes, broker actions, clocks,
  schedulers, command routing, persistence, backtest/local-paper adapters, or UI/read-model changes.
- Preserve the current local-paper/data-only and no-real-money boundary.

## Phases

### Phase 1: Repository intake

- [x] Check repository instructions, worktree state, and relevant architecture.
- [x] Map current entry, position, exit, simulation, event, and dashboard paths.
- **Status:** complete

### Phase 2: Gap and contract design

- [x] Compare the supplied v0.1 proposal to implemented behavior.
- [x] Resolve model semantics, inputs, timing, state transitions, priority, and persistence.
- [x] Identify compatibility and migration risks.
- **Status:** complete

### Phase 3: Implementation plan authoring

- [x] Write dependency-ordered phases with exact file-level changes.
- [x] Define tests, observability, rollout, rollback, and non-goals.
- [x] Add measurable acceptance criteria and Definition of Done.
- **Status:** complete

### Phase 4: Verification and handoff

- [x] Cross-check the plan against repository evidence and user requirements.
- [x] Verify no product code was changed.
- [x] Deliver a review-ready implementation plan.
- **Status:** complete

### Phase 5: Review feedback revision

- [x] Add explicit thesis logic versioning distinct from schema and entry-strategy versions.
- [x] Freeze a stable `ExitReason` enum and distinguish recommendation from execution outcome.
- [x] Make Historical Tick／Replay support an explicit contract and validation phase.
- [x] Reorder Phase 0-6 so Journal precedes monitoring, monitoring precedes recommendation, and simulation validation precedes controlled rollout.
- [x] Preserve the no-auto-SELL, no-broker, and no-real-money boundaries.
- [x] Revalidate document structure and confirm no product code changes.
- **Status:** complete

### Phase 6: Phase 0 gate hardening

- [x] Freeze canonical timestamp roles and the authoritative Thesis start time source.
- [x] Replace source-event-based recommendation identity with one active recommendation per trade lifecycle.
- [x] Freeze replay determinism inputs, clocks, IDs, ordering, and digest requirements.
- [x] Freeze the pure/no-hidden-mutation ThesisMonitor boundary.
- [x] Split decision, order, and trade/position lifecycle state machines instead of one mixed enum.
- [x] Add the approved Phase 0 completion checklist and revalidate plan-only scope.
- **Status:** complete

### Phase 7: PR-TM-001 Contract Freeze implementation

- [x] Re-check repository conventions, current dirty-worktree overlap, and contract dependencies.
- [x] Add versioned enums/value objects for timestamps, Thesis, lifecycle, ExitReason/ExitLeg,
  ExitRecommendation, and Replay divergence metadata.
- [x] Add deterministic identity and validation rules without behavior engines or side effects.
- [x] Freeze explicit serialization formats and immutable JSON fixtures.
- [x] Add transition-table, timestamp, uniqueness/idempotency, serialization, and scope-boundary tests.
- [x] Run targeted and full regression verification; prove no trading behavior/runtime wiring changed.
- [x] Update Section 20 checklist only for items backed by implementation/test evidence.
- **Status:** complete

### Phase 8: PR-TM-002 Journal Integration

- [x] Re-check the existing Journal repository/projection conventions and the frozen Trade Management
  serializers without touching unrelated dirty-worktree files.
- [x] Add strict v1 deserializers for the frozen Journal-facing Trade Management aggregate contracts.
- [x] Add versioned Journal record builders/readers with deterministic record identity, payload digest
  verification, and append idempotency through the existing Journal contract.
- [x] Add a pure replay reconstruction projection for thesis drafts, activated theses, exit
  recommendations, and closed outcomes; no evaluation, risk, order, or broker side effects.
- [x] Document backward-compatibility and enum-evolution policies without changing v1 wire meanings.
- [x] Add round-trip, restart/replay determinism, corruption, ordering, idempotency, compatibility, and
  scope-boundary tests.
- [x] Run targeted and full regression verification; prove no trading behavior/runtime wiring changed.
- **Status:** complete

### Phase 9: PR-TM-002 blocking review fixes

- [x] Freeze one Decimal wire representation: plain notation, insignificant trailing-zero removal,
  negative-zero normalization, and no exponent output.
- [x] Make the Journal's authoritative payload an immutable canonical byte snapshot while preserving
  the existing read-only `payload` compatibility view.
- [x] Add golden/reader tests for equivalent Decimal inputs and rejection of every non-canonical form.
- [x] Add append/source/nested payload mutation regression tests and prove checkpoint replay remains
  stable after rejected mutation attempts.
- [x] Re-run targeted Journal/Trade Management tests plus the full repository suite; retain the strict
  no-ThesisMonitor/no-RiskGate/no-broker/no-market-replay scope.
- [x] Update the PR-TM-002 merge checklist only with verified blocker-fix evidence.
- **Status:** complete

### Phase 10: PR-TM-003 ThesisMonitor, status only

- [x] Freeze the immutable `ThesisMarketContext` and structured `ThesisEvaluation` contracts needed
  by the existing typed ORB thesis definition; aggregation/window state remains upstream.
- [x] Add failing-first tests for VALID, WARNING, hard INVALID, deadline INVALID, and
  INSUFFICIENT_DATA, including exact boundary and missing/stale/out-of-order/session cases.
- [x] Implement pure typed-condition evaluation and deterministic status aggregation with no mutable
  cache, repository, Journal, Clock, RiskGate, Position, Order, broker, or filesystem/network access.
- [x] Add deterministic-output, input-immutability, dependency-boundary, and forbidden-capability
  tests; prove the result has no order/recommendation/action authority.
- [x] Run targeted and full regression verification; update architecture evidence without marking
  runtime Journal/status-transition or deadline-scheduler work complete.
- **Status:** complete

### Phase 11: PR-TM-004 Exit Recommendation, decision only

- [x] Record PR-TM-003 approval and typed reason-code evidence without changing its approved wire
  semantics.
- [x] Freeze an immutable active-position input and pure recommendation result using the existing
  ExitDecision/ExitRecommendation contracts; no legacy Position dependency or mutation.
- [x] Add failing-first tests: VALID/WARNING/INSUFFICIENT_DATA -> HOLD/no recommendation;
  hard INVALID -> THESIS_INVALID; deadline INVALID -> TIME_DECAY; repeated INVALID -> one active
  recommendation with deterministic update/identity.
- [x] Implement stable reason mapping/priority, deterministic decision digest, and monotonic active
  recommendation update without Journal, RiskGate, Order, SELL, broker, Clock, or runtime access.
- [x] Add identity/lifecycle mismatch, immutability, ten-run determinism, dependency-boundary, and
  forbidden-capability tests.
- [x] Run targeted and full regression verification; update architecture evidence while explicitly
  deferring adapters, persistence, RiskGate, and execution.
- **Status:** complete

### Phase 12: PR-TM-005 RiskGate execution eligibility, pure only

- [x] Record PR-TM-004 approval and defer recommendation-version/expiry changes to explicit future
  contract/lifecycle work.
- [x] Freeze immutable recommendation-risk context and deterministic ExecutionEligibility output;
  bind recommendation/trade/session identity, injected evaluation time, RiskSnapshot, and policy.
- [x] Add failing-first tests for eligible risk-reducing exit, unhealthy/closed/untradable/stale book,
  pending duplicate, insufficient remaining position, identity/time mismatch, and exact determinism.
- [x] Make strategy-origin, daily-loss, cash/position-notional, and order-notional entry guards BUY-only
  in the existing RiskGate; retain data/market/instrument/book/quantity/price/position validation.
- [x] Implement pure RiskGate recommendation eligibility without constructing OrderCommand or calling
  application, Journal, Position, simulation, broker, filesystem/network, or wall clock.
- [x] Run existing RiskGate/application regressions, combined Trade Management tests, and full suite;
  update architecture evidence while deferring command creation, persistence, and execution.
- **Status:** complete

### Phase 13: PR-TM-006 Simulation / Replay Validation, decision chain only

- [x] Record PR-TM-005 approval and change the roadmap so replay validation precedes durable guard
  enforcement and Shadow rollout.
- [x] Freeze immutable replay input/output contracts using existing canonical `market-event-v1`
  Tick envelopes, `ReplayRunIdentity`, thesis, position, risk snapshot, and exact policy versions.
- [x] Add failing-first tests for Historical Tick reduction into ThesisMarketContext and the full
  ThesisEvaluation -> ExitRecommendation -> ExecutionEligibility chain.
- [x] Implement a pure deterministic reducer/harness with no Journal mutation, OrderCommand,
  Position mutation, broker, runtime, filesystem/network, or wall-clock access.
- [x] Prove ten-run digest parity, event-order validation, manifest/policy/version mismatch rejection,
  and sensitivity to changed market evidence.
- [x] Run targeted, combined Trade Management/market contract, and full-suite verification; update
  architecture evidence while explicitly deferring Shadow and execution.
- **Status:** complete

### Phase 14: PR-TM-007 Shadow Decision Pipeline, decision only

- [x] Record PR-TM-006 approval and move durable guard enforcement behind Shadow decision validation.
- [x] Map the existing live canonical event consumer/dispatch seam and choose the smallest adapter
  that does not alter shared market ingestion or execution runtime.
- [x] Freeze immutable Shadow input/state/record contracts, including event identity, run/policy
  versions, decision-chain digest, and live-to-replay parity metadata.
- [x] Add failing-first tests for live event progression, HOLD/EXIT records, idempotent duplicate
  handling, fail-closed out-of-order/session/version inputs, and exact replay parity.
- [x] Implement the Shadow pipeline by reusing the PR-TM-006 reducer/kernel; do not duplicate Thesis,
  Recommendation, or RiskGate semantics.
- [x] Prove no Journal write, OrderCommand, SELL, Position mutation, broker, filesystem/network, or
  wall-clock authority; run targeted, combined, and full-suite verification.
- **Status:** complete

### Phase 15: PR-TM-008 Durable Decision Journal / Shadow Evidence Persistence

- [x] Record PR-TM-007 approval and freeze persistence as evidence-only, not trade authority.
- [x] Inspect existing Journal record/repository/checkpoint/PostgreSQL seams and the PR-TM-002 adapter
  to select one compatible versioned Shadow evidence representation.
- [x] Freeze strict canonical serialization, deterministic record identity, append idempotency,
  session finalization/parity facts, and explicit retention/compaction policy semantics.
- [x] Add failing-first tests for append/retry/restart reconstruction, ordering, corruption/conflict,
  checkpoint verification, retention safety, and separation from Trade Management authority.
- [x] Implement the minimal Shadow evidence Journal adapter/projection without changing the generic
  Journal repository, PostgreSQL schema, Shadow decision engine, runtime composition, or execution.
- [x] Run targeted Journal/Shadow tests, combined Trade Management regressions, full suite, scope and
  planning gates; update architecture evidence.
- **Status:** complete

### Phase 16: PR-TM-009 Live Runtime Composition / Shadow Operation

- [x] Record PR-TM-008 approval and preserve the decision-only/evidence-only authority boundary.
- [x] Map the canonical record-before-ingest result seam and select a wrapper composition rather than
  changing Shioaji callbacks, market admission, or local-paper order runtime.
- [x] Add failing-first tests for applied-event consumption, rejected-event exclusion, per-event risk
  injection, immediate durable evidence, finalize parity, checkpoint recovery, and failure handling.
- [x] Implement the minimal runtime orchestrator using the existing Shadow pipeline and Journal
  adapters; no duplicate Thesis/Recommendation/Risk logic.
- [x] Prove no OrderCommand, SELL, broker, Shioaji, Position mutation, or real-money capability and run
  targeted, combined, and full-suite verification.
- [x] Update architecture evidence and hand off PR-TM-009 for review without commit or push.
- **Status:** complete

### Phase 17: PR-TM-010 Shadow Observability / Production Readiness Gate

- [x] Record PR-TM-009 approval and freeze observability/readiness as read-only evidence.
- [x] Map operation counters, pending-evidence timing, durable projection, and finalized parity inputs.
- [x] Add failing-first tests for health states, backlog age, writer failure/recovery, evidence
  completeness, parity rate, typed readiness failures, and deterministic reports.
- [x] Implement immutable observability snapshots and a pure multi-session readiness evaluator without
  changing decision, Journal fact, RiskGate, market pipeline, or execution semantics.
- [x] Prove no OrderCommand, SELL, broker, Shioaji, Position mutation, or real-money capability and run
  targeted, combined, and full-suite verification.
- [x] Update architecture evidence and hand off PR-TM-010 for review without commit or push.
- **Status:** complete

### Phase 18: PR-TM-011 Extended Shadow Validation / Operational Readiness

- [x] Record PR-TM-010 approval and preserve readiness as evidence rather than execution permission.
- [x] Map the missing production-evidence identity, full-session coverage, replay/checkpoint proof,
  recovery drill, divergence drill, and multi-market-date stability contracts.
- [x] Add failing-first tests for source identity, complete-session evidence, unique dates/sessions,
  drill outcomes, deterministic aggregation, typed failures, and no-execution authority.
- [x] Implement immutable validation artifacts and a pure extended-validation evaluator without
  changing decision, Journal, RiskGate, market admission, runtime processing, or execution semantics.
- [x] Add an operational runbook for BLOCKED recovery, divergence investigation, evidence handling,
  and the explicit rule that test fixtures do not satisfy the real-market gate.
- [x] Run targeted, combined, and full-suite verification; document which production evidence remains
  unavailable rather than claiming a real one-day or multi-day Shadow run.
- **Status:** complete

### Phase 19: PR-TM-012 Real Shadow Evidence Collection

- [x] Record PR-TM-011 framework-only approval and keep Production Shadow Gate NOT PASSED.
- [x] Audit the existing Shioaji data-only runtime, canonical market pipeline, durable Journal adapter,
  provider/connection identity, credential availability, market hours, and operational entry point.
- [ ] Define a sealed `ShadowValidationRun` artifact and minimum real-session policy only where the
  existing contracts cannot preserve the collected evidence reproducibly.
- [x] Execute the longest safe real-market Shadow capture available in the current session, or record
  the exact external blocker without fabricating evidence.
- [ ] Verify durable evidence completeness, checkpoint recovery, replay parity, and deterministic
  readiness over every collected real session; keep multi-day and drill gates pending until proven.
- [ ] Update the runbook/architecture with evidence paths, exact commands, test results, limitations,
  and explicit Production Shadow Gate status. No execution discussion or enablement.
- **Status:** in_progress

### Phase 20: PR-TM-012A Paper Fill to TradeThesis Activation

- [x] Record the architecture decision: authoritative Thesis starts from a real local-paper BUY fill,
  not a caller-supplied canonical Thesis JSON.
- [x] Audit local-paper command/fill Journal provenance and deterministic draft-to-command correlation.
- [x] Add failing-first tests for fill provenance, deterministic correlation, BUY/session/symbol/time
  validation, immutable activation identity, old-record rejection, and no execution authority.
- [x] Preserve provider identity, paper fill source, and `execution_authority=false` on new local-paper
  fill evidence without breaking replay of older v1 fill records.
- [x] Implement a pure PaperFill-to-TradeThesis builder; no order submission, Journal append, strategy
  evaluation, broker, Shioaji SDK, Position mutation, or runtime stream wiring.
- [x] Run targeted, combined, and full-suite verification; update PR-TM-012A evidence and keep the
  Production Shadow Gate NOT PASSED.
- **Status:** complete

### Phase 21: PR-TM-012B First Real Shadow Session Evidence

- [x] Confirm the dedicated PostgreSQL DSN without exposing credentials and prove the target schema
  is empty before applying any migration.
- [x] Bootstrap only the existing Trade Management Journal schema and verify its exact table/index/
  constraint contract; do not create execution, order, or broker tables.
- [x] Add a provider-neutral data-only callback runner that accepts only an existing
  `PaperFillThesisActivation`, waits for paired subscription ACK, records pre-boundary event counts,
  and finalizes through the existing durable Shadow operation.
- [ ] Add the smallest data-only live-capture entry point that composes canonical applied events,
  local-paper fill activation, the shared Shadow kernel, and durable PostgreSQL evidence.
- [x] Freeze and implement the missing live `EntryDecision -> TradeThesisDraft` authority in a
  separately reviewed scope; production code currently has no draft construction point and the
  capture runner must not substitute a caller-authored JSON or test fixture.
- [ ] Add fail-closed configuration/preflight tests for DSN, provider/runtime identity, paper-fill
  provenance, session identity, market hours, recovery, and `execution_authority=false`.
- [ ] Run a complete real-market session, finalize durable evidence, restart from checkpoint, replay
  the same inputs, and produce deterministic parity/readiness artifacts without synthetic ticks.
- [ ] Repeat across the minimum required market dates and complete the recovery drill before changing
  `Production Shadow Gate` from `NOT PASSED`.
- **Status:** in_progress

### Phase 22: PR-TM-012B1 Live EntryDecision to TradeThesisDraft

- [x] Record approval and freeze the scope to deterministic EntryDecision/Draft contracts only; no
  CandidateEngine, BuyScoreEngine, paper order, fill, activation, Journal, RiskGate, or Shadow wiring.
- [x] Add immutable `LiveEntryDecision` plus deterministic content-bound identity and strict canonical
  serialization/reader contracts.
- [x] Add a pure EntryDecision builder that captures score, matched rules, typed entry evidence,
  strategy version, canonical timestamps, and market-context digest without importing Candidate or
  BuyScore runtime models.
- [x] Add a version-bound Thesis draft policy and pure `LiveEntryDecision -> TradeThesisDraft` builder
  with deterministic thesis ID, expected behavior, and invalid conditions.
- [x] Add golden/fail-closed/immutability/authority tests and run targeted, combined, and full-suite
  verification without changing the Production Shadow Gate.
- **Status:** complete

### Phase 23: PR-TM-012B2 Operational Composition / Fill Observation

- [x] Freeze the boundary to observe/connect/activate only; reuse PR-TM-012A and PR-TM-012B1,
  and prohibit fill creation, matching, order submission, Position mutation, broker access, and
  RiskGate changes.
- [x] Add a typed BuyScore breakdown evidence adapter without changing CandidateEngine or
  BuyScoreEngine and without moving entry-strategy decisions into the adapter.
- [x] Add fail-closed observation of an existing correlated local-paper BUY fill from its
  authoritative Journal and reuse `PaperFillThesisBuilder` for deterministic activation.
- [x] Compose the activated Thesis into the existing live Shadow operation/capture runner while
  keeping the fill Journal read-only and the Shadow evidence Journal as a separate authority.
- [x] Verify provenance, restart/replay identity, PostgreSQL Journal port compatibility, and the
  absence of any execution/fill-generation capability with targeted, combined, and full tests.
- **Status:** complete; user approved

### Phase 24: PR-TM-012C0 Pre-market Readiness

- [x] Record user authorization to finish every safe pre-market preparation without representing
  rehearsal output as real Shadow evidence.
- [x] Freeze a canonical preflight/session manifest that binds market date/window, symbol, provider,
  SDK/simulation/connection, code, schema, migration, strategy/thesis/exit/risk/fill/validator
  versions, and `execution_enabled=false`.
- [x] Add fail-closed readiness checks for reviewed trading date, future/full market window,
  data-only provider identity, PostgreSQL DSN presence/driver/schema/empty evidence target, paper-fill
  provenance inputs, and required replay/recovery components without logging secrets.
- [x] Add a fixture/replay rehearsal mode that exercises canonical events, observed paper fill,
  Shadow evidence, finalization, checkpoint recovery, replay parity, and readiness reporting while
  marking every artifact `qualifying_real_session=false`.
- [x] Add the exact launch/check/recovery commands and evidence paths to the operational runbook;
  prove no order, matching, Position, broker, Shioaji order, or real-money authority exists.
- [x] Run targeted, combined, and full-suite verification and produce a deterministic C0 readiness
  report for the next scheduled complete market session without mutating the formal evidence tables.
- **Status:** complete; READY_FOR_SESSION does not qualify as real evidence

### Phase 25: PR-TM-012C1 First Real Shadow Evidence Session

- [x] Record PR-TM-012B2 approval and keep the Production Shadow Gate `NOT PASSED` until real
  full-session evidence satisfies every operational gate.
- [ ] Run the data-only preflight for the scheduled market session with provider, SDK, simulation,
  connection-session, code, policy, and schema identities frozen before capture.
- [ ] Capture one complete real market session through canonical admission, observed local-paper BUY
  fill activation, live Shadow decisions, and the dedicated PostgreSQL evidence Journal.
- [ ] Perform the controlled Journal interruption/checkpoint recovery drill without losing or
  reordering evidence.
- [ ] Finalize the session, replay the durable evidence, require parity `MATCHED`, and produce the
  deterministic readiness report.
- [ ] Repeat across the minimum multi-day evidence window before changing the Production Shadow Gate
  to `EVIDENCE PASSED`; do not add order or execution capability.
- **Status:** pending next complete market session; Production Shadow Gate NOT PASSED

### Phase 26: 2026-08-21 Partial-session Diagnostic

- [x] Freeze the run as `PARTIAL_SESSION` / non-qualifying evidence because capture starts after
  09:00 Asia/Taipei; keep Production Shadow Gate `NOT PASSED`.
- [x] Re-run data-only provider and PostgreSQL preflight without exposing credentials or mutating
  formal evidence before the capture boundary is accepted.
- [x] Inspect and invoke only the existing C1 operational entry point; do not create orders, fills,
  positions, matching behavior, synthetic ticks, or execution capability.
- [x] Validate the parts available today: live canonical event admission, durable Shadow evidence,
  checkpoint/recovery, replay parity, and deterministic artifacts through market close where the
  existing runtime supports them.
- [x] Record exact blockers and artifact paths if an authoritative EntryDecision or observed
  local-paper BUY fill is unavailable; do not weaken contracts to force a decision record.
- **Status:** complete; diagnostic evidence only, live capture failed closed and Production Shadow
  Gate remains NOT PASSED

### Phase 27: TM-012C Preflight Blocking Fixes

- [x] Add failing tests that reproduce concurrent Tick/BidAsk callback interleaving without changing
  provider observation timestamps or making wall time the replay ordering authority.
- [x] Introduce the smallest shared callback ingress serialization boundary so callback delivery and
  canonical ingress sequencing have one authority; retain raw `received_at` as observed evidence.
- [x] Fix only the rehearsal fixture whose replacement `event_time` no longer matches
  `session_date`; keep the production event invariant strict.
- [x] Verify Tick/BidAsk interleaving, exact duplicates, qualification capture, rehearsal,
  Shadow/recovery/parity, and full repository regression.
- [ ] Update diagnostic/runbook evidence and keep Production Shadow Gate `NOT PASSED` until a future
  complete real session passes.
- **Status:** complete; both blocking fixes verified, Production Shadow Gate NOT PASSED

## Key questions

1. Does the existing system have a real `PositionManager`, or are exit decisions split across strategy/backtest/simulation components?
2. Which current entry evidence can be captured deterministically as a thesis without recomputation drift?
3. What market history and clock contract are required to evaluate expected behavior and time decay?
4. Should Trading Guard block intents, order submissions, or both, and where does realized PnL come from today?
5. How can events remain replayable and idempotent without introducing live broker execution?

## Errors encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `trade_outcome.json` golden mismatch: `MICSECOND` typo | 1 | Keep domain output unchanged; correct fixture to `MICROSECOND` |
| `check-complete.sh` reported unrelated root plan status | 1 | Pass the isolated plan file path explicitly; do not change the shared active-plan pointer |
| Tried nonexistent `scripts/session-catchup.sh` | 1 | Located the installed helper and used `python3 scripts/session-catchup.py <project-path>` |
| Scope test matched `RiskGate` in the module docstring | 1 | Changed the assertion to inspect AST name/call references instead of comments and documentation text |
| Combined hardening patch targeted a Journal class in the serializer file | 1 | Verified the failed patch was atomic, then split codec, Journal, and test edits by file |
| Blocker regression suite could not import `trading.canonical_values` | 1 | Expected red phase: tests were added before the new shared canonical Decimal helper; implement the leaf helper next |
| `dataclasses.replace()` could not reserialize an immutable `mappingproxy` payload | 1 | Teach the existing Journal JSON default to copy any read-only `Mapping` into a JSON object; keep stored views immutable |
| New evidence canonicalization tests omitted the `EvidenceValue` import | 1 | Add the missing explicit test import, then exercise the intended domain validation red/green path |
| New evidence tests displaced the existing enum assertion loop | 1 | Restore the loop inside `test_wire_enums_are_frozen` and keep the new parametrized tests independent |
| Full suite hit unrelated institutional candidate digest mismatch | 1 | Blocker reproduction and 623 tests pass; isolate the concurrently changed institutional test and do not edit out-of-scope files |
| Tried obsolete `scripts/catchup.py` helper name | 1 | Located the installed `scripts/session-catchup.py`; restored context directly from the isolated planning files before continuing |
| `pytest` was not on the shell PATH | 1 | Located and use the repository's `.venv/bin/pytest` executable for PR-TM-003 verification |
| Boundary-test patch displaced the preceding test's assertions | 1 | Restored the original VALID assertions to their test and kept the comparison-boundary test independent |
| PR-TM-005 RiskGate test patch displaced an existing test's assertions | 1 | Restored unhealthy/strategy assertions to their original test and kept BUY-only guard assertions independent |
| Combined PR-TM-006 command referenced nonexistent `tests/test_market_event_serialization.py` | 1 | Located the actual canonical codec coverage in `tests/test_market_event_contract_freeze.py` and rerun with that file |
| Shadow out-of-order test reused a later ingress sequence at the same event time | 1 | Set both envelope and payload ingress sequence below the prior watermark so the fixture actually represents out-of-order input |
| RiskSnapshot corruption test expected the inner validation message | 1 | Match the adapter's stable public `cannot decode` error while retaining the RiskSnapshot digest mismatch as the chained cause |
| Retention compaction test used an unsupported policy version | 1 | Use the frozen `shadow-evidence-retention-v1` so the test reaches the intended no-compaction invariant |
| Validation fixture passed `Decimal` directly to `timedelta` | 1 | Convert the fixture's integral seconds string to `int`; keep Decimal only in domain metrics/policy |
| Local-paper ISO timestamp had a fixed `+08:00` tzinfo without the canonical zone key | 1 | Normalize the immutable fill instant with `astimezone(Asia/Taipei)` before constructing `TradeTimestamp` |
| Live-capture tests reused a local-paper fill created after market close | 1 | Keep product market-window rejection strict; define the unit-test window around the immutable fixture fill instead of weakening validation |
| Live-capture fixture tried to set `session_id` on a `TickEvent` payload | 1 | Keep session identity on the `EventEnvelope`; only ingress sequence is shared by envelope and payload |
| Full suite lacked an unrelated institutional price-resolution digest file | 1 | Keep the Trade Management scope unchanged; report 837 passing tests plus the external missing-artifact failure instead of fabricating its digest |
| New EntryDecision canonical test used a deliberate pending digest | 1 | Capture the first reviewed canonical serialization digest and freeze it after round-trip validation passed |
| PostgreSQL driver install could not resolve packages in the restricted network sandbox | 1 | Retried the same declared postgres extra with approved network access; psycopg 3.3.4 installed in `.venv` |
| Partial preflight rehearsal failed after a fixture event-time replacement | 1 | Isolated the failure to a test fixture whose `session_date` was not updated with the replacement event time; do not treat it as provider/DB failure or weaken the domain invariant |
| Live qualification consumer raised `DataHealth time cannot move backward` | 1 | Preserve the partial capture artifact, wait for clean shutdown, then inspect raw event ordering and health-clock inputs before choosing a different diagnostic path |
| Replay CLI was invoked without its required `--verify` mode | 1 | Read CLI help and reran with `--verify`; the tool correctly rejected the incomplete Journal |
| First fixture repair passed event construction but pipeline rejected the new date | 1 | Bind the test-only market pipeline helper to the immutable observed fill date; keep production session matching strict |
| `apply_patch` could not match one exact completed-checklist line after repeated exact/relative/block attempts | 3 | Keep Phase 27 status and evidence complete; do not switch to an unsafe shell rewrite for a cosmetic checkbox |

## Deliverable

- PR-TM-001 contract-only code, fixtures, and tests matching
  `architecture/trade_management_enhancement_implementation_plan.md` v0.4.
- PR-TM-002 Journal persistence/replay reconstruction, compatibility policy, and tests.
- PR-TM-001 verification: targeted 22 passed; full suite 550 passed, 1 skipped.
- PR-TM-002 verification: targeted 37 passed; full suite 575 passed, 1 skipped.
- PR-TM-002 is approved to merge after Phase 9 Decimal/immutability blocker re-review.
- PR-TM-002 blocker-fix verification: Trade Management targeted 57 passed, focused Journal set 64
  passed, full suite 625 passed, 1 skipped; ready for
  user re-review and approved to merge.
- PR-TM-003 pure ThesisMonitor status contracts, implementation, and tests; no recommendation,
  execution, or runtime wiring.
- PR-TM-003 verification: monitor targeted 27 passed; combined Trade Management 84 passed; full suite
  657 passed, 1 skipped.
- PR-TM-004 pure Exit Recommendation mapping and tests; no adapters, persistence, RiskGate, Position
  mutation, Order, SELL, broker, or runtime wiring.
- PR-TM-004 verification: engine targeted 13 passed; combined Trade Management 97 passed; full suite
  677 passed, 1 skipped.
- PR-TM-005 pure RiskGate ExecutionEligibility and entry-only guard correction; no command creation,
  application service, persistence, Position mutation, SELL execution, broker, or runtime wiring.
- PR-TM-005 verification: eligibility/RiskGate targeted 23 passed; combined Risk/Trade Management 132
  passed; full suite 728 passed, 2 skipped.
- PR-TM-006 pure Simulation/Replay validation over canonical Historical Tick evidence; no Shadow,
  command creation, persistence, broker, SELL, or runtime wiring.
- PR-TM-006 verification: replay targeted 6 passed; combined decision-chain/market contracts 98
  passed; full suite 734 passed, 2 skipped.
- PR-TM-007 immutable Shadow Decision Pipeline and parity evidence; no authoritative persistence,
  order/execution capability, Position mutation, broker, or real money.
- PR-TM-007 verification: Shadow targeted 6 passed; combined Trade Management/market/Shadow contracts
  116 passed; full suite 749 passed, 2 skipped.
- PR-TM-008 durable Shadow evidence records/projection/checkpoint/retention policy over the existing
  Journal; no Trade lifecycle authority, runtime composition, Order, Position mutation, or broker.
- PR-TM-008 verification: evidence targeted 9 passed; combined Journal/Trade Management 119 passed,
  1 skipped; full suite 768 passed, 2 skipped.
- PR-TM-009 evidence-only live composition over the canonical market pipeline, shared Shadow kernel,
  and existing Journal; no order/execution capability, Position mutation, broker, or Shioaji SDK.
- PR-TM-009 verification: operation targeted 6 passed; combined market/Journal/Trade Management 157
  passed; full suite 774 passed, 2 skipped.
- PR-TM-010 immutable Shadow operation metrics and pure multi-session production-readiness evidence;
  no decision mutation, execution capability, broker, or Shioaji order integration.
- PR-TM-010 verification: observability/operation targeted 13 passed; combined contracts 164 passed;
  full suite 791 passed, 2 skipped.
- PR-TM-011 pure extended Shadow validation artifacts, operational drills, deterministic report, and
  operational runbook; no persistence mutation, execution capability, broker, or Shioaji order path.
- PR-TM-011 verification: validation targeted 8 passed; combined contracts 172 passed; full suite
  805 passed, 2 skipped. Real-market one-day/multi-day evidence remains pending.
- No commit or push unless separately requested.
