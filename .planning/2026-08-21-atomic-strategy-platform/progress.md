# Progress: Atomic Strategy Platform

## 2026-08-21 — Gate G2 Review remediation started

- **Status:** in progress; Gate G2 NOT PASSED; Phase 3 blocked.
- Review returned five blocking groups: atomic Run route security, shared PostgreSQL connection state, incomplete durable idempotency, broken atomic browser clone/missing Version diff UI, and incomplete strict-input/audit contracts.
- Activated planning-with-files, code-review-excellence, architecture-patterns, and karpathy-guidelines for a finding-by-finding repair.
- Success criteria are negative-path tests first, then bounded code changes only in the Phase 2 Web/backtest/catalog seams.
- Existing FinMind history and planning changes are unrelated user work and will be preserved.

## 2026-08-21 — Gate G2 remediation candidate complete

- **Status:** READY FOR REVIEW; Gate G2 remains NOT PASSED; Phase 3 remains blocked.
- Added conditional atomic security enforcement for cancel/retry/clone, strict DTOs, actor-aware success/failure/conflict audit, Strategy Set change notes, and Audit API/UI.
- Replaced runtime single connections with bounded PostgreSQL pools and checkout-per-operation repository transactions; direct connections remain only for explicit tests.
- Reworked Run creation to use database conflict arbitration plus `config_digest` verification and immutable same-key replay.
- Persisted complete Draft operation results so create/update replay is independent of later mutable Draft state.
- Added browser response-loss key retention, atomic-specific clone payloads, and interactive Version diff selectors/rendering.
- Added migration 007 plus hostile Origin, non-loopback, missing CSRF, unknown-field, conflict audit, response-loss, same-key/different-digest, pool checkout, concurrent PostgreSQL Run, immutable Draft replay, atomic clone, and Version diff coverage.
- Focused no-DSN test run: `16 passed, 10 skipped`; final full no-DSN regression: `1112 passed, 15 skipped`.
- Python compilation, `node --check` for all changed Dashboard modules, and `git diff --check` passed.
- `TEST_POSTGRES_DSN` is unavailable, so the two newly added PostgreSQL concurrency tests and the existing PostgreSQL contract suite remain explicit skips pending disposable-database Review evidence.
- No Local Paper, simulation flow, Shioaji/broker order, or real-money execution changes were made by this remediation.

## 2026-08-21 — Gate G1 passed; Phase 2 implementation candidate complete

- **Status:** READY FOR REVIEW; Gate G2 remains NOT PASSED until an implementation Review approves it.
- Final short Review returned APPROVE / Gate G1 PASSED with no remaining blocking or important finding.
- Reviewer evidence: focused `33 passed, 5 skipped`, full no-DSN `1103 passed, 10 skipped`, Python compilation passed, and `git diff --check` passed.
- Disposable PostgreSQL was not available to the reviewer; the earlier `1113 passed` PostgreSQL run remains the accepted database evidence.
- Began Phase 14 for the historical Web workflow: Template/Schema discovery, Draft validation and immutable Publish, exact-version Strategy Set composition, and Backtest Launcher integration.
- Local Paper, simulation trading, broker order integration, and real-money execution remain explicitly excluded.
- Added migration 006 for durable idempotent Web mutations and append-only audit records.
- Extended the PostgreSQL atomic repository/service with Draft update/list, Version list/clone/diff, and Strategy Set list/idempotent save while preserving Phase 1 Publish replay semantics.
- Added a same-route historical atomic launcher whose worker reconstructs the exact Strategy Set and per-run Registry from the immutable run snapshot before execution.
- Added loopback/origin/CSRF-protected Template, Draft, Publish, Version, Strategy Set, and atomic backtest APIs.
- First compile passed. First focused test run: `11 passed, 5 skipped, 1 failed`; the only failure was the migration acceptance fixture expecting 005 to remain the final migration, which is now updated for 006.
- Replaced the read-only strategy drawer with a Traditional Chinese Schema-driven management flow and added a separate exact-version atomic Backtest Launcher while retaining the legacy selector behind a collapsed compatibility section.
- Dashboard JavaScript validation passed; expanded focused backend/UI suite passed `29 passed, 5 skipped`.
- Started a disposable local PostgreSQL 17 database named `atomic_phase2_test`; no existing developer or production database was used.
- The restricted first attempt could not access the local Unix socket. The approved rerun passed the complete focused PostgreSQL slice: `15 passed`.
- Added a true end-to-end PostgreSQL acceptance test that publishes an atomic Version, persists an exact Strategy Set, launches it against a READY one-minute dataset, waits for the worker, and verifies the immutable Run Snapshot v2. The test first caught a cadence-fixture mismatch and an unsupported engine-version label; both contracts were corrected and the exact worker run now passes.
- Preserved exact atomic identity through failed-run retry and baseline clone; atomic clones may adjust only capital, cost, and evaluation thresholds and cannot replace raw strategy IDs or immutable snapshot evidence.
- Serialized resource-creating idempotent mutations with PostgreSQL transaction advisory locks. Concurrent same-key Draft creation returns one Draft and writes exactly one operation plus one audit event.
- Browser interaction smoke passed through Template selection, dynamic parameters, Draft validation, immutable Publish, exact Set creation, and Backtest Set selection.
- Final focused PostgreSQL Web/backtest slice: `18 passed`; the concurrent Publish/Web-mutation subset is included.
- Final full regression with disposable PostgreSQL: `1119 passed`; final normal regression without DSN: `1106 passed, 13 skipped`.
- Dashboard JavaScript graph validation, changed-module Python compilation, and `git diff --check` passed.
- Phase 2 is submitted as an implementation candidate for Gate G2 Review. No Local Paper, simulation, Shioaji/broker order, or real-money execution code was changed by this Phase.
- Stopped and removed the dedicated `/private/tmp` PostgreSQL cluster after verification; no developer or production database was accessed or changed.

## 2026-08-21 — Gate G1 implementation Review remediation

- **Status:** remediation complete; Gate G1 READY FOR REVIEW / NOT PASSED; Phase 2 blocked.
- Withdrew the prior `1100 passed, 10 skipped` result as stable Gate evidence after Review reproduced eight time-dependent failures.
- Activated planning-with-files for the remediation log, code-review-excellence for finding-by-finding verification, architecture-patterns for the durable replay port/adapter boundary, and karpathy-guidelines to keep changes limited to the six reviewed findings.
- Added Phase 13 covering Feature Specification snapshot identity, registry-independent durable Publish replay, fixed market-time fixtures, Strategy Set integrity validation, complete migration acceptance, and destructive PostgreSQL test guards.
- No Phase 2 Web management, Phase 4 local-paper integration, simulation trading, Shioaji order, or broker code is authorized in this remediation.
- Cross-worktree packaging follow-up fixed both split-clock paper-fill fixtures in `0bcf61c`; the post-fix repository run passed `1100 passed, 10 skipped`. Gate G1 remains `NOT PASSED` because the other five Review findings are not remediated here.
- Implemented Feature Specification identity in `atomic-backtest-run-snapshot-v2`: specification digest, feature implementation digest, and explicit as-of semantics are persisted per resolved request.
- Added a Registry-independent repository replay port. PostgreSQL locks the Draft, resolves same-key durable operation results first, and returns `DRAFT_ALREADY_PUBLISHED` for a different key before any current Template lookup.
- Added exact Strategy Set read integrity checks across stored `snapshot_json`, `snapshot_digest`, and the relational member projection, with fail-closed tamper tests.
- Expanded migration acceptance to all nine atomic-platform tables, every declared constraint count, and all four named supporting indexes.
- Added an executable PostgreSQL cleanup guard requiring a database name containing `test` or the explicit `ALLOW_POSTGRES_TEST_SCHEMA_RESET=1` sentinel.
- Focused non-PostgreSQL run after remediation: `16 passed, 5 skipped`.
- UTF8 disposable PostgreSQL migration/Publish/concurrency/Strategy Set suite: `9 passed`.
- First full regression with PostgreSQL reached `1112 passed, 1 failed`; the remaining failure was an existing `regclass` display-format assertion whose output changes with `search_path`, not a missing relation. Updated it to assert relation presence/absence semantically before rerunning.
- Short code Review found and closed two final edge cases: an empty deployed Registry can still replay a committed Publish, and the destructive test guard requires a standalone `test` database-name token instead of accepting arbitrary substrings such as `contest_prod`.
- Final focused PostgreSQL/atomic suite: `16 passed`; final full suite with disposable PostgreSQL: `1113 passed`; final normal suite without DSN: `1103 passed, 10 skipped`.
- Python compilation and `git diff --check` passed. Phase 2 was not started; Gate G1 awaits the requested short Review before it may change to PASSED.

## 2026-08-21 — Phase 1 implementation authorized

- **Status:** in progress
- Contract Review returned APPROVE / GO; B1–B5 are closed.
- User explicitly authorized planning-file finalization and implementation.
- Updated the Implementation Plan and isolated task plan to record Gate G0 passed.
- Added the two Review Important items to Phase 1: numbered PostgreSQL migration/acceptance tests and disposable PostgreSQL fixture/dependency/README setup.
- Activated planning-with-files, architecture-patterns, and karpathy-guidelines.
- Restored session context and confirmed the repository has extensive unrelated dirty worktree state that must be preserved.
- Implementation scope is Phase 1 only; no Web mutation UI, local-paper integration, Shioaji order API, CA, or real-money execution.
- Added migration 005, framework-free strategy domain modules, PostgreSQL Publish adapter/application service, shared feature specifications, two atomic entry files, exact-version set/engine bridge, and focused tests.
- Static Python compilation passed for the new modules.
- First focused test invocation found no global `pytest` executable and ran zero tests; next verification uses the project virtual environment.
- Focused domain/atomic tests passed after correcting the fixture entry time: `9 passed, 3 skipped` without a PostgreSQL DSN.
- Existing catalog/backtest regression passed: `30 passed, 1 skipped`.
- Created an isolated PostgreSQL 17 cluster under `/private/tmp`, ran real migration/Publish row-lock tests, and obtained `6 passed` including concurrent same-key replay and concurrent unique/monotonic version allocation.
- Stopped the disposable PostgreSQL instance and removed its temporary directory after verification; no existing database was accessed.
- Added README and `.env.example` instructions requiring a dedicated `TEST_POSTGRES_DSN`; integration tests never substitute SQLite.
- Added immutable PostgreSQL exact-version Strategy Set save/reload with member role/digest validation.
- Added explicit `parameter_schema_digest` persistence and included it in Version configuration/evidence digests.
- Added standalone engine runs for both `above_vwap_entry` and `breakout_previous_high_entry`, plus their deterministic combined `ALL` run.
- Final disposable PostgreSQL migration/Publish/Set suite: `7 passed`.
- Final full repository regression: `1100 passed, 10 skipped in 6.20s`; skips are opt-in external/PostgreSQL tests when the normal suite lacks explicit DSNs/credentials. PostgreSQL tests were separately executed and passed against disposable local instances.
- Whitespace, tracked diff-check, dependency-boundary search, and Python compilation checks passed. Ruff/pyflakes are not installed, so no lint result is claimed.
- **Historical status (superseded by the implementation Review above):** Phase 1 had been marked complete and Gate G1 PASSED. The current authoritative state remains READY FOR REVIEW / NOT PASSED until the short Review closes it.

## 2026-08-21 — Planning intake

- **Status:** in progress
- Captured the user's decision to use atomic, independently testable strategies rather than an aggregate `limit-up acceleration` concept.
- Captured Web-managed, database-persisted, versioned parameters and Strategy Set composition.
- Captured separate role and session-phase classification.
- Added the four-layer model: template, immutable parameter version, strategy set, and run snapshot.
- Added the missing runtime, execution, risk, reproducibility, lifecycle, observability, and governance concerns to the planning scope.
- Confirmed this turn is planning-only and does not authorize product-code changes.
- Created an isolated planning directory because the repository root planning files are actively tracking Freshness Calibration Evidence.
- Revalidated the existing catalog, immutable definition table, StrategySetSnapshot, DecisionAggregator, backtest run snapshot, APIs, and Momentum-specific local-paper controller.
- Identified a superseded earlier decision: browser parameters were intentionally read-only; the new plan must replace only that limitation with validated Schema-driven version creation while preserving allowlisted code execution and reproducibility.

## Files created

- `.planning/2026-08-21-atomic-strategy-platform/task_plan.md`
- `.planning/2026-08-21-atomic-strategy-platform/findings.md`
- `.planning/2026-08-21-atomic-strategy-platform/progress.md`
- `architecture/atomic_strategy_platform_implementation_plan.md`

## 2026-08-21 — Plan completion

- **Status:** complete; awaiting user review and explicit implementation authorization.
- Authored a repository-grounded implementation plan covering the four-layer data model, Feature Registry, atomic strategy interface, parameter Schema, Web management, version lifecycle, composition, run snapshots, execution, ownership, risk, reproducibility, operations, security, migrations, tests, rollout, and Definition of Done.
- Reconciled current reusable foundations: immutable catalog definitions, allowlisted bindings, StrategySetSnapshot, DecisionAggregator, catalog APIs, and backtest run config snapshots.
- Recorded the intentional supersession of the old read-only-parameter decision.
- Selected conservative v1 defaults: DRAFT then immutable publish, ANY/ALL/AT_LEAST_N only, single automatic owner per symbol, completed 1-minute Kbar research plus a separate Tick/BidAsk paper adapter, and above-VWAP/breakout as the first migration slice.
- Structural validation passed: all required plan sections are present, Markdown fences are balanced, whitespace checks are clean, and only planning files were added in this slice.
## 2026-08-22 — Gate G2 Host/origin and deterministic-regression remediation

- **Status:** READY FOR REVIEW; Gate G2 remains NOT PASSED; Phase 3 blocked.
- Activated planning-with-files, code-review-excellence, architecture-patterns, and karpathy-guidelines for the bounded follow-up remediation.
- Preserved the unrelated active FinMind work and did not change `.planning/.active_plan`.
- Reproduced the security findings: public Host capabilities `200`, public Host atomic retry `201`, and wrong scheme/port Origin retry `201`.
- Reproduced the date-dependent failures with the repository virtualenv: `2 failed, 2 passed` across the two named tests plus the existing atomic Web API file.
- Added an application-wide HTTP boundary that requires both a loopback peer and loopback Host before any response, including the CSRF capabilities response; all proxy forwarding headers are rejected because this deployment is intentionally direct/local-only.
- Atomic mutation Origin now matches the validated request's normalized scheme, hostname, and effective port.
- Added negative coverage for public Host, public Host mutation, forwarding headers, wrong scheme, and wrong port, plus a positive exact-origin case.
- Injected a fixed Dashboard history clock/Mock history anchor and a fixed RuntimeComposition clock into the two cross-day tests; production market-date validation was not weakened.
- Focused Dashboard/atomic suite: `48 passed, 3 skipped`; full no-DSN suite: `1114 passed, 15 skipped`; full disposable PostgreSQL 17 suite: `1129 passed`.
- Python compilation, Dashboard JavaScript syntax, and `git diff --check` passed.
- The disposable PostgreSQL process was stopped and `/private/tmp/atomic_g2_followup_pg.ZZTtkR` was removed after verification; no developer or production database was accessed.
- The planning-with-files constraint kept the remediation within the reviewed Phase 2 boundary and prevented Phase 3 or transaction-path expansion; the architecture/security review kept the Host/origin checks at the HTTP edge while retaining application-layer CSRF validation.

## 2026-08-22 — Phase 3 Backtest Qualification authorized

- **Status:** in progress; Gate G3 remains NOT PASSED.
- Final implementation Review returned APPROVE / Gate G2 PASSED with no remaining blocking or important finding.
- Reviewer evidence: last three blocker tests `3 passed`, no-DSN full `1114 passed, 15 skipped`, disposable PostgreSQL 17 full `1129 passed`, plus compilation, Dashboard JavaScript syntax, and `git diff --check`.
- User explicitly authorized Phase 3 Backtest Qualification.
- Activated planning-with-files, architecture-patterns, and karpathy-guidelines for this bounded implementation slice.
- Scope is qualification evidence only: explicit OOS/walk-forward protocol, baseline/challenger, multiple-testing record, parameterized Feature identity, PostgreSQL persistence, and Web review.
- Phase 4 Local Paper, simulation trading, Shioaji/broker orders, and real-money execution remain blocked.
- Added a framework-free qualification contract with explicit train/validation/OOS windows, non-overlapping walk-forward OOS folds, Bonferroni-adjusted multiple-testing identity, immutable attempted-Run history, and review-only verdicts.
- Qualification evidence recomputes interval metrics from immutable trades/equity, checks Atomic Snapshot v2 integrity, compares execution settings, and records exact Strategy Version/Feature/adapter identities.
- Added Feature Request runtime/state identity so 2m versus 3m windows and Kbar versus Tick adapters cannot share cache/state keys.
- Added PostgreSQL migration 008 and repository primitives for immutable qualification persistence; API/Web wiring and PostgreSQL integration verification remain in progress.
- Focused pure-domain/Feature/Atomic Snapshot tests: `10 passed`.
- Added strict CSRF/Origin-protected qualification create API plus bounded list/detail reads and durable audit events.
- Added a Traditional Chinese qualification form with explicit Primary train/validation/OOS dates, repeatable walk-forward fold controls, multi-select attempted Runs, multiple-testing fields, policy thresholds, immutable result list, and an explicit no-auto-activation warning.
- PostgreSQL qualification writes use an advisory-lock serialized transaction; same-key/same-digest requests replay, different requests conflict, and reads verify request/protocol/evidence/relational projection digests.
- Response-loss replay checks the durable qualification row before reading mutable Run/Dataset projections. A committed result therefore remains replayable even if the current dataset projection later changes.
- Focused no-DSN API/UI/domain suite: `26 passed, 1 skipped`; the skip is the opt-in real PostgreSQL migration test.
- Focused disposable PostgreSQL 17 suite: `22 passed`, including migration 008, concurrent create replay, request conflict, immutable digest tamper detection, and durable replay after dataset projection drift.
- Full no-DSN regression after final manifest/drawdown hardening: `1133 passed, 16 skipped`; full disposable PostgreSQL 17 regression: `1149 passed`.
- Python compilation, Dashboard JavaScript syntax, and `git diff --check` passed.
- Browser smoke opened the real MockProvider Dashboard, entered the Backtest comparison/qualification tab, verified Fold add/remove `2 -> 3 -> 2`, filled fixed date windows, observed the expected missing-Run validation message, and found no browser console errors.
- Stopped the MockProvider Dashboard and both disposable PostgreSQL 17 processes, then removed `/private/tmp/atomic_g3_pg.jPmmba` and `/private/tmp/atomic_g3_final_pg.JAgLuP`; no developer or production database was accessed.
- Phase 3 implementation candidate is complete and ready for implementation Review. Gate G3 remains NOT PASSED; Phase 4 remains blocked.

## 2026-08-22 — Gate G3 qualification-semantics remediation started

- **Status:** in progress; Gate G3 NOT PASSED; Phase 4 blocked.
- Independent Review reproduced a false-positive `ELIGIBLE_FOR_PROMOTION_REVIEW` with client-weakened thresholds, no walk-forward folds, one independent OOS date, historical placeholder train/validation windows, and mismatched Feature adapter identity.
- The same Review found that multiple-testing history is client-declared instead of PostgreSQL-authoritative, compare and qualification use different comparability rules, and qualification does not verify `digest(run.config) == run.config_digest`.
- Important follow-ups are part of this remediation: bind actor/change note into integrity verification, expose full review evidence in the UI, and either connect Feature state identity to a real owner or withdraw the unsupported Gate claim.
- Scope remains Phase 3 research qualification only. No Local Paper, simulation trading, Shioaji/broker order, or real-money execution change is authorized.
- Tooling note: one cleanup patch targeted a duplicated line that only appeared because two `sed` ranges overlapped at the same boundary; patch verification correctly failed, direct inspection confirmed the source contains one key, and no code change was required.
- First focused run after removing client-owned policy/history: `7 failed, 24 passed, 1 skipped`. All failures are expected stale-contract fixtures: four construct the retired `MultipleTestingRecord`, one sends the retired API fields before the CSRF assertion, one expects removed UI inputs, and one expects migration 008 to remain last. No unrelated regression appeared in this slice.
- Updated the stale qualification/domain/API/UI/migration fixtures and added adversarial coverage for a weakened policy, one-day clustered samples, adapter mismatch, and out-of-manifest windows. Current no-DSN focused result: `39 passed, 1 skipped`.
- The first sandboxed PostgreSQL `initdb` failed at `shmget(...): Operation not permitted`; this is an environment restriction, not product evidence. A fresh disposable PostgreSQL 17 cluster was started outside the restricted sandbox under `/private/tmp/g3_remediation_pg.mpPaAz`.
- PostgreSQL focused migration/family/qualification/Web persistence result: `10 passed`, including migration 009, monotonic concurrent attempts, response-loss replay, Run config tamper rejection, actor projection tamper rejection, and existing PostgreSQL backtest paths.

## 2026-08-22 — Gate G3 qualification-semantics remediation candidate complete

- **Status:** READY FOR REVIEW; Gate G3 remains NOT PASSED; Phase 4 remains blocked.
- Replaced request-owned thresholds/history with a fixed server policy and PostgreSQL-authoritative family ledger. The Baseline Run deterministically owns the family; Challenger creation appends one monotonic attempt in the same transaction as the Run.
- Compare and qualification now share one comparability contract. Intended Strategy Version differences remain comparable, while dataset, execution/cost/capital settings, Feature Request semantics, implementation digest, adapter identity, and as-of semantics remain fail closed.
- Qualification verifies Run config/result, DatasetManifest bounds, Atomic Snapshot, independent OOS dates, train/validation/OOS observations, actor/change note, family head/history, and all evidence digests before returning a record.
- Withdrew the unsupported Feature runtime-state claim. `state_key()` remains an identity helper only; a real rolling Feature state/cache owner is explicitly deferred to Phase 5.
- Reviewer UI now shows the fixed policy, adjusted alpha, full authoritative family history, windows/folds, and Run/Strategy/Feature/adapter identities. The browser can no longer submit policy, attempt count, attempted Run IDs, alpha, or family identity.
- Final focused no-DSN suite: `40 passed, 1 skipped`; focused disposable PostgreSQL 17 suite: `10 passed`.
- Final full no-DSN regression: `1147 passed, 18 skipped`; final disposable PostgreSQL 17 regression: `1165 passed`.
- Browser smoke against the existing local Dashboard verified the server-owned policy notice, Baseline selector, two required folds, Fold add/remove `2 -> 3 -> 2`, native required-field fail-closed behavior, and no browser console errors. Its stale PostgreSQL connection was not used as backend evidence.
- Python compilation, Dashboard JavaScript syntax, and `git diff --check` passed. Disposable PostgreSQL directories were removed; no developer or production database was accessed.
- No Local Paper, simulation-trading, Shioaji/broker-order, or real-money code was changed for this remediation.

## 2026-08-22 — Gate G3 identity/isolation remediation started

- **Status:** in progress; Gate G3 NOT PASSED; Phase 4 blocked.
- Follow-up Review found three remaining bypasses: Fold OOS may reuse Primary OOS, equivalent Baseline reruns reset the family attempt budget, and tampered Run-row Dataset identity is not reconciled with the verified config snapshot.
- The family snapshot digest is also not reconstructable after mutable attempt linkage is written; this Important item is included in the same repository/migration slice.
- Scope remains Phase 3 qualification evidence only. No Local Paper, simulation, Shioaji/broker order, or real-money execution change is authorized.
- Added the exact Primary-OOS reuse regression first. It currently fails as expected (`DID NOT RAISE ValueError`), reproducing Blocking 1 before the product change.
- Added the strict `fold.oos_end < primary.oos_start` invariant; the exploit test is now expected to pass in the next focused run.
- One combined test-fixture patch missed a later expected line and was rejected atomically. It was split into exact domain and PostgreSQL helper patches; no partial edit from the failed patch remained.
- First PostgreSQL focused attempt used a `postgres` role that this disposable cluster did not create, producing six setup errors before tests ran. Rebuilt the DSN with the cluster's actual local role; the next run reached product assertions.
- The first real PostgreSQL run was `7 passed, 1 failed`: snapshot tampering failed closed on the earlier sequence invariant instead of the test's expected digest message. Moved canonical digest verification before structural projection checks; focused PostgreSQL migration/qualification result is now `8 passed`.
- Implemented strict Fold/Primary OOS isolation, stable research-baseline family identity, unified Run row/config Dataset verification, migration 010, immutable family snapshot JSON, dynamic current-family detail projection, and historical/current Reviewer UI linkage.
- Broader no-DSN qualification/Web/core/migration suite is green: `31 passed, 10 skipped`. The skips remain opt-in PostgreSQL tests, which passed separately against the disposable PostgreSQL 17 cluster.
- Full no-DSN regression is green: `1157 passed, 20 skipped`; full disposable PostgreSQL 17 regression is green: `1177 passed`.
- Browser smoke against the existing local Dashboard verified the fixed server policy, Baseline/Challenger selectors, and Fold add/remove `2 -> 3 -> 2`. Its pre-existing PostgreSQL connection is closed, so it could not load Qualification detail and is not counted as backend evidence; repository/API behavior is covered by the disposable PostgreSQL suite.
- Python compilation, Dashboard JavaScript syntax, and `git diff --check` passed after the final documentation update. The disposable PostgreSQL cluster and test data were stopped and removed; no development or production database was accessed.
- **Status:** second remediation candidate complete — READY FOR REVIEW; Gate G3 remains NOT PASSED and Phase 4 remains blocked.

## 2026-08-22 — Phase 4 Local Paper Runtime authorized

- **Status:** in progress; Gate G4 NOT PASSED.
- The final MVP Review approved Gate G3 as `PASSED / MVP CONDITIONAL GO`. The user's immediately following 「開始process」 is treated as explicit authorization to begin Phase 4 Local Paper Runtime.
- Scope is limited to the existing local Journal/Risk/Simulation path, exact-version strategy selection, runtime ownership, recovery, kill switch, and Web controls. Shioaji remains market-data-only; broker orders, CA, trade subscription, and real-money execution remain prohibited.
- Architecture work will converge existing `continuous_strategy.py` and `strategy_flow.py` paths rather than create another Feature, execution, or persistence pipeline.
- Added the first Phase 4 vertical slice: exact-version Local Paper resolver, deterministic pipeline snapshot, canonical live Feature projection adapter, composition evidence, and explicit Local Paper bindings for the two deployed atomic entry strategies.
- Verification: `.venv/bin/python -m pytest -q tests/test_atomic_paper_runtime.py` -> `4 passed`.

## 2026-08-22 — Phase 4 implementation candidate ready for Gate G4 Review

- **Status:** implementation candidate complete; Gate G4 remains `NOT PASSED` pending independent Review.
- The Web start path now requires one immutable PostgreSQL `ENTRY` Strategy Set Version. Runtime activation revalidates Version/configuration/Template/Schema/implementation/runtime-binding identity and derives a deterministic Local Paper Pipeline snapshot.
- Strategy evaluation consumes the existing live Momentum `FeatureEngine` projection and same-process Tick/BidAsk book. Strategy thresholds use current Tick price; the Execution Policy proposes BUY at fresh best ask. ANY/ALL/AT_LEAST_N evidence preserves every member and deterministic primary attribution.
- The command boundary is now explicit and runtime-enforced: adapters accept only `ApprovedOrderCommand`. Journal evidence binds the proposed command, Risk snapshot, effective policy, Risk decision and approved command with SHA-256 identities.
- Runtime ownership is the exact Strategy Set Version. Consumed decision digests and controller state are checkpointed in the same Journal; restart restores dedup evidence and fails closed on foreign positions/orders or integrity drift.
- The controller remains `STOPPED` by default and requires a loopback/Origin/CSRF-protected manual start. Emergency kill blocks new intents; reset leaves the controller stopped and requires another explicit start.
- Existing stop-loss/take-profit/13:25 flatten behavior remains the code-owned v1 Exit Policy and continues to use fresh best bid, Hard Risk and the same Simulation path. No speculative EXIT strategy or second feature pipeline was added.
- Final focused evidence: `55 passed`. Full no-DSN regression: `1166 passed, 20 skipped`. Disposable PostgreSQL 17 full regression: `1186 passed`. Python compilation, Dashboard JavaScript syntax, browser interaction smoke and `git diff --check` passed.
- Browser smoke verified the required exact-set selector, PostgreSQL-unavailable fail-closed message, native required-field prevention, kill-switch engagement, and reset-to-STOPPED behavior.
- The disposable PostgreSQL container and all generated test data were removed after verification. No broker adapter, CA, trade subscription, Shioaji order API or real-money capability was introduced.

## 2026-08-22 — Gate G4 Review remediation started

- **Status:** in progress; Gate G4 remains `NOT PASSED`; Phase 5 remains unauthorized.
- Review identified three MVP blockers: activation does not require `PAPER_APPROVED`, operator daily loss is outside the effective Hard Risk Policy, and cross-owner same-symbol pending orders can merge into the wrong owner at fill.
- The raw Strategy Intent HTTP endpoint is part of the lifecycle bypass and must be closed at the delivery boundary rather than documented as trusted.
- ALL composition currently collapses `NOT_TRIGGERED + INSUFFICIENT_DATA` to NOT_TRIGGERED; remediation will preserve unavailable evidence as required by the frozen contract.
- Start/stop/kill durable actor/idempotency audit remains an Important item. This remediation will at minimum bind the activation config and operator identity to Journal evidence and explicitly document any process-local limitation that remains.
- Scope remains Local Paper only. No Phase 5 strategy expansion, broker transport, CA, trade subscription, or real-money capability is authorized.
- Added a transactional Paper activation catalog snapshot. PostgreSQL now locks and verifies the immutable Set snapshot plus every Version/lifecycle projection, admits only `PAPER_APPROVED`, and returns sequence/event/projection digest evidence to the runtime snapshot.
- Resolver adversarial tests now reject PUBLISHED, REVIEWED, BACKTESTED, PAUSED, RETIRED, and catalogs that expose only raw Set/Version reads. Focused lifecycle/runtime result: `10 passed`.

## 2026-08-22 — Gate G4 remediation candidate ready for short Review

- **Status:** remediation implementation complete; Gate G4 remains `NOT PASSED`; Phase 5 remains unauthorized.
- Closed the three Review blockers: transactional `PAPER_APPROVED` activation evidence, Effective Hard Risk daily-loss merge/evidence, and cross-owner pending/fill-time isolation. Removed the raw Strategy Intent HTTP bypass and corrected ALL unavailable precedence.
- Added response-loss activation replay, lifecycle event/projection tamper checks, exact-risk checkpoint drift recovery, PUBLISHED/REVIEWED/BACKTESTED/PAUSED/RETIRED negative cases, raw-route 404, operator/system ceiling, and reservation/fill collision tests.
- Focused no-DSN suite: `74 passed, 8 skipped`. Focused disposable PostgreSQL 17 suite: `82 passed`.
- Full no-DSN regression: `1178 passed, 21 skipped`. Full disposable PostgreSQL 17 regression: `1199 passed`.
- Python compilation, all Dashboard JavaScript syntax checks and `git diff --check` passed.
- The disposable cluster at `/private/tmp/g4_remediation_pg.VCGtZ4` was stopped and deleted after validation; no development or production database was accessed.
- Start activation now has actor/config/durable-idempotency evidence. Stop and kill-switch operations remain documented process-local MVP audit limitations; they must be hardened before multi-user, external network, auto-promotion or real-money scope.
- No broker adapter, CA, trade subscription, `place_order`, `subscribe_trade=True`, or real-money capability was added.
