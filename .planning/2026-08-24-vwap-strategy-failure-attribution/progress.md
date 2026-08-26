# Progress: VWAP Strategy Failure Attribution

## 2026-08-24

### R0: Contract freeze

- **Status:** complete
- Started the next phase as an independent strategy-failure attribution project.
- Kept `.planning/.active_plan` unchanged because it belongs to a concurrent shared-worktree task.
- Frozen baseline, Dataset, safety boundaries, and non-goals in this directory.
- Confirmed that the completed Dataset bridge will not be modified and that Local Paper/broker remain unauthorized.

### R1: Baseline evidence verification

- **Status:** complete
- Next action: query the application PostgreSQL read-only and reconstruct the exact cost, execution, signal, and trade evidence needed for attribution.
- Located the normalized trade projection, immutable result chunks, and qualification tables; no schema or product mutation is required for the analysis.
- Read the core and chunk migrations to freeze table grain. A sandboxed Docker status probe was denied; no retry or mutation was attempted yet.
- With explicit read-only Docker access, confirmed `tsg-single-db` is healthy and contains the application `tw_intraday_trader` database.
- Verified the durable Run/config/result identity and froze the exact cost, sizing, ENTRY, EXIT, and VWAP proxy contracts.
- A qualification query referenced a nonexistent `reasons_json` column. Recorded the error and will inspect the actual migration before retrying.
- Inspected qualification/family migrations and the actual trade/fill JSON shape. The evidence is sufficient for cost, time, strategy-semantic, and family-protocol attribution.
- Added a reproducible read-only SQL evidence pack and ran it successfully against the application database.
- Quantified the order conversion, cost drag, yearly path, entry/holding-time concentration, daily outcomes, symbol concentration, and VWAP-distance quintiles.
- A source inspection initially targeted nonexistent `backtest/execution.py`; code search located the actual slippage implementation in `backtest/engine.py`.
- Reconstructed slippage separately from explicit fees/tax and confirmed the pre-friction strategy result remains negative.
- Verified deterministic `(timestamp, symbol)` processing, total-equity sizing, remaining-cash admission, and one-attempt-per-symbol/day semantics in source.
- A frozen-parameter lookup used the wrong catalog schema/table name and failed read-only; it will be retried only after migration discovery.
- Located `backtest.strategy_versions` from migration 005 and verified the exact baseline parameters and digests.

### R2-R4: Attribution and next Gate

- **Status:** complete
- Completed the evidence decomposition and ranked supported versus unsupported causes.
- Confirmed that deterministic admission bias prevents treating the 6,321 fills
  as a cash-admission-neutral sample of 128,802 VWAP signals.
- Rejected an immediate cross-up clone and same-data parameter search as weak/unsafe next experiments.
- Authored `architecture/vwap_failure_attribution_research_gate.md` with a
  cash-admission-neutral R5 control and a deferred seven-strategy R6 benchmark
  matrix.
- Kept R5 execution, R6, lifecycle mutation, Local Paper, broker, and real-money disabled.
- Portable report validation attempt 1 rejected a `series` field on the waterfall chart. The chart already had explicit x/y encodings, so the unsupported redundant field was removed before the single targeted retry.
- Portable report validation attempt 2 found that the table sorted by an undeclared audit field. Added the existing `priority` field as an explicit table column; no analytical data changed.
- Portable report validation attempt 3 confirmed that `horizontalBar` still uses canonical category-x / numeric-y encodings; corrected the axis declarations and reference-line axis.
- Generated the canonical portable HTML technical report after schema validation and packaged-reader QA.
- Final report receipt: validation passed, package passed, browser verification passed at 1440 px and 390 px; 19 blocks, 3 charts, 5 metric cards, 1 table, source dialog and keyboard interaction passed.
- A sandboxed Chromium attempt failed before verification; the exact same builder passed with the required local browser permission. No report data changed for that retry.
- Final `git diff --check` for the isolated phase files and architecture plan passed.
- Final artifact SHA-256: `c6db10a5031c42d8018a8a8fe8cd07686d8423f0782ba13c1f95433371840bea`.
- Final report SHA-256: `18fd59565a0e66064aee6ac39ce4951d2d53f907475e6744db8e0c303e585c24`.
- Confirmed `.planning/.active_plan` remains an unrelated pre-existing modification and was not changed by this phase.

### R4.1: R5/R6 Review remediation

- **Status:** complete
- Addressed the four pre-implementation Review findings without creating a Run
  or changing product/runtime behavior.
- Froze a dedicated R5 control endpoint and durable preflight/control evidence.
- Corrected the research claim from allocation-neutral to cash-admission-neutral.
- Reconciled R6 with the server-owned 20-attempt family policy.
- Added an immutable seven-slot matrix registration contract so hypotheses are
  sealed before any Challenger Run.
- Added R5 acceptance and R6 policy SQL templates for the next short Review.
- Executed the R5 acceptance SQL read-only with the immutable baseline supplied
  as both IDs to validate syntax and current PostgreSQL column names; the
  expected 122,481 baseline cash rejections proved the zero-rejection query is
  active rather than vacuously passing.
- Re-ran the baseline evidence pack read-only; the added ceiling query returned
  `S_max=182`, `distinct_S_max=182`, `observed_sessions=727` and the full pack
  committed only its `READ ONLY` transaction.
- Kept `.planning/.active_plan`, Local Paper, provider, broker, and real-money
  scopes untouched.

### R4.2: Authoritative R5 control and fail-closed acceptance

- **Status:** complete / ready for short re-review
- Removed caller freedom over R5 `C/f`; froze deterministic Decimal derivation
  and one authoritative sealed control per baseline＋contract revision.
- Added head-lock, unique registration, invalid-revision, Review-gated revision,
  and different-idempotency-key behavior to the contract.
- Moved acceptance into a server postflight before result exposure; invalid
  controls publish diagnostics only and cannot enter comparison, Qualification,
  or R6.
- Replaced the reporting SQL with a repeatable-read, multiplicity-aware Gate
  that returns a nonzero process exit on failure.
- PostgreSQL negative probe used the immutable baseline as both baseline and
  control. It rolled back and exited `3`, proving failed conditions no longer
  return process success.
- Updated and rebuilt the canonical artifact with a visible superseded notice;
  validation/package/browser QA passed at 1440 px and 390 px. Artifact SHA-256
  is `16877f66b81ecd937107498b18d6627dbd036f86d0f5ffff193d9a96d29822cf`;
  HTML SHA-256 is
  `cdc50550503ea7a9790ca99aa32e7e23ed4c9a4bdd0f6069379a5d693157f15b`.
  Baseline measurements remain unchanged.
- Kept R5 execution, R6 execution, Local Paper, provider, broker, and real-money
  scopes disabled.

## 2026-08-25

### R5 implementation

- **Status:** in progress
- User supplied independent short re-review approval and explicitly authorized
  implementation.
- Frozen scope: deterministic server-owned `C/f`, one sealed authoritative
  control per baseline＋contract revision, durable replay/CAS, server postflight
  barrier, result redaction, and adversarial tests.
- R5 Run creation/execution, R6, lifecycle mutation, Local Paper, provider,
  broker, and real-money remain unauthorized.
- Completed initial worktree/migration/API inventory. Selected migration 014 and
  confirmed that overlapping dirty files require surgical patches only.
- Confirmed that result redaction must cover every application accessor, not
  only `result()`, because several projections currently query the repository
  directly.
- Confirmed that R5 acceptance publication must be a PostgreSQL repository
  transaction spanning postflight registration, chunked result persistence,
  and terminal Run state. Generic retry/clone will be denied for sealed
  controls.
- Domain work now includes explicit `CONTROL_POSTFLIGHT` and
  `INVALID_CASH_ADMISSION_CONTROL` statuses plus a digested
  `research_control_snapshot` in the immutable Run config.
- Implemented the shared Decimal sizing, strict canonical preflight catalog,
  immutable control snapshot, multiplicity-aware postflight, and diagnostics-
  only invalid evidence. Focused domain regression: `7 passed`.
- Added migration 014 for authoritative head, sealed registration, durable
  operation replay, and postflight evidence. Extracted cursor-scoped immutable
  result persistence so accepted publication can share the registration
  transaction; chunk regression remains green (`9 passed, 1 skipped` with the
  PostgreSQL case skipped without DSN).
- Implemented the PostgreSQL head advisory lock, response replay, sealed-
  preflight conflict, baseline/Dataset/config/result identity verification,
  one authoritative Run, and atomic accepted/invalid postflight finalize.
  Direct result persistence now rejects research controls outside that path.
- Added the application use case with server-owned preflight lookup and C/f,
  worker postflight integration, generic retry/clone denial, and a common
  accepted-control guard across result, trade, export, compare, and
  Qualification accessors. Compilation passes; the first combined pytest
  command referenced a nonexistent test module and collected no tests, so it
  is not counted as verification evidence.
- Added the strict, CSRF-protected R5 endpoint using the existing loopback
  mutation boundary. The request cannot contain C/f or unknown fields, and R5
  conflicts/not-accepted evidence map to explicit HTTP 409 responses. Focused
  application/API regression: `20 passed, 6 skipped`.
- Added the provider-free preflight CLI and streaming exact-next-bar statistics.
  It reads PostgreSQL under `REPEATABLE READ READ ONLY`, verifies the local
  immutable manifest, and writes only the canonical preflight artifact. Domain
  coverage is now `9 passed`; CLI help and compilation pass without requiring a
  configured DSN.
- Strengthened the preflight with the baseline ENTRY multiplicity digest and
  added full established result-digest reconstruction for both baseline and
  control before finalize. This closes order-parity and performance tamper
  gaps without changing the engine's historical digest definition.
- Added API negative coverage (CSRF, forbidden C/f, idempotent response, and
  pre-postflight 409), migration acceptance updates, and PostgreSQL-only
  registration/finalize/tamper scenarios. Current no-DSN focused result:
  `13 passed, 4 skipped`; skips are the disposable PostgreSQL cases.
- Added the required two-worker race regression using different operation keys
  against the same baseline/preflight. It asserts one Run/head/registration,
  two durable operations, and exactly one non-replay result. No-DSN focused is
  now `13 passed, 5 skipped`.
- First full no-DSN regression reached `1378 passed, 39 skipped` with one
  expected migration-list failure because the forward-migration acceptance
  list ended at 013. Added only migration 014 to that list before rerunning;
  this was test-contract drift, not a runtime failure.
- Full no-DSN regression now passes: `1379 passed, 39 skipped in 8.61s`.
  `git diff --check` also passes. `TEST_POSTGRES_DSN` is unset; Docker and psql
  clients are installed, so disposable PostgreSQL verification is the next
  evidence step if the local daemon is available.
- Corrected the PostgreSQL fixture to include the FinMind reference metadata
  required by the immutable Dataset contract. The R5 repository slice then
  passed `4 passed`, covering authoritative replay, invalid-result redaction,
  tamper rejection, and the two-worker different-key race.
- Made preflight statistics safe for a single-pass baseline order stream and
  added a generator regression; domain coverage is now `10 passed`.
- Disposable PostgreSQL focused migration/result/control verification passed
  `10 passed`. Full no-DSN regression passed `1380 passed, 39 skipped`; the
  complete disposable PostgreSQL suite passed `1419 passed`.
- Python compilation, provider-free CLI help, and `git diff --check` passed.
  The disposable PostgreSQL container was stopped and removed after testing.
- **Disposition:** R5 implementation is complete and ready for independent
  Review. No official preflight, control Run, or postflight was created; R5
  execution remains `NOT STARTED`, and R6/Local Paper/provider/broker/real-money
  remain unauthorized.

### R5 implementation Review remediation

- **Status:** changes required / in progress
- Independent Review found that accepted reads do not revalidate ENTRY status
  and actual fill evidence, the formal SQL targets obsolete JSON paths, and the
  preflight CLI does not fail early on semantic baseline-result tamper.
- R5 execution remains unauthorized while these findings are remediated.
- Added postflight schema v2 with a complete canonical ENTRY order/fill
  admission projection digest. Accepted result reads now recompute it, and the
  reviewer attack that changes `FILLED` to `REJECTED` while clearing fills is a
  service-level fail-closed regression.
- Updated the formal SQL to read Migration 014 registration evidence,
  `preflight.statistics`, and actual ENTRY `fills` chunks. Added a psql-backed
  PostgreSQL test covering valid acceptance and missing-fill rejection.
- The preflight CLI now recomputes the baseline semantic result digest before
  opening the local Dataset stream. Focused no-DSN remediation currently passes
  `16 passed, 5 skipped`; the skips are PostgreSQL-only cases.
- PostgreSQL focused remediation passes `6 passed`. This includes the formal
  psql audit positive/negative cases and a durable self-consistent tamper probe
  that rewrites the accepted order chunk plus descriptors and removes the fill
  chunk; result reconstruction succeeds, but performance exposure fails closed
  on the admission projection digest.
- Full no-DSN regression passes `1384 passed, 41 skipped`. Full disposable
  PostgreSQL regression passes `1425 passed`. Python compilation, CLI help, and
  `git diff --check` pass.
- The disposable PostgreSQL 17 container was stopped and removed. No official
  R5 preflight/control/postflight was created, and no provider, Local Paper,
  broker, R6, or real-money path was invoked.
- **Disposition:** remediation complete / ready for independent re-review.
  This is not an R5 implementation approval and does not authorize execution.
- Follow-up Review reopened one SQL blocker because FILLED engine orders retain
  a non-empty explanatory reason. Restored the rejection-reason predicate to
  non-FILLED orders and upgraded the PostgreSQL positive fixture with reason,
  filled timestamp, embedded fill, and the full fill projection.
- The upgraded PostgreSQL focused slice passes `6 passed`: a valid FILLED order
  with explanatory reason and embedded fill is accepted, while missing actual
  fills still exits the formal SQL Gate non-zero.
- Full no-DSN regression passes `1384 passed, 41 skipped`; full disposable
  PostgreSQL regression passes `1425 passed`. Compilation and
  `git diff --check` pass, and the disposable container was removed.
- **Disposition:** SQL reason remediation complete / ready for independent
  re-review. R5 execution and R6 remain unauthorized.

### R5 authorized execution

- User explicitly authorized execution of the single frozen R5 authoritative
  control. R6, Local Paper, providers, broker, and real-money remain prohibited.
- Baseline remains `run-91ad87981676414da87b928398fa43c9`; execution must use
  the existing immutable Dataset/binding and the provider-free preflight CLI.
- **Status:** preflight identity checks in progress; no control Run created yet.
- Sanitized runtime check confirms PostgreSQL backend, local Dataset root
  `data/backtest`, application database `tw_intraday_trader` on localhost:5090,
  and a healthy `tsg-single-db` container. No credential was printed.
- Repeatable-read read-only preflight check confirms baseline `COMPLETED`,
  config/result digests unchanged, Dataset `READY` with 28,325,340 bars,
  manifest/dataset/binding revision 1 identity aligned, and no existing R5
  registration. Migration 014 is not yet applied and will be installed only by
  formal repository initialization after the read-only preflight succeeds.
- Canonical preflight artifact
  `e03e7e5a985605668a72f7ae7a10b734879ca7023b781657a335a843e25a8a6f`
  was created provider-free. It derives `S_max=182`, `P_max=19590.0`,
  `C=4465307372`, and `f=0.004387155994`.
- Preflight coverage is not acceptable: 128,802 candidates, 128,792 matched,
  and 10 missing next bars. Because sealing the sole registration would make
  the known-failing revision permanently invalid, no R5 control Run has been
  created while the missing candidates are diagnosed read-only.
- First diagnostic launch failed before DB access because direct `.planning`
  execution did not include the repository root on `sys.path`; the launcher was
  corrected without changing preflight or product semantics.
- Missing-next-bar diagnostic artifact
  `0be2d029b02c7bfd6488b276fb5bf900140ebf07d42548ba77a75d99eb27a6ad`
  identifies all 10 exact candidates. A baseline FILLED order proves the engine
  carries ordinary NEXT_BAR_OPEN across sessions, while the preflight incorrectly
  filtered to the same calendar date.
- Execution is paused before migration/registration. The preflight matching
  implementation and regression must be corrected and independently reviewed;
  the known-invalid artifact will not be used to seal revision 1.
- Implemented preflight schema v2 with explicit next-observed-symbol-Kbar
  identity and removed the incorrect same-session filter. Added a cross-session
  engine-parity regression and clarified the frozen contract. Registration
  remains uncreated pending verification and re-review.
- Remediation verification passed: focused R5 tests `16 passed, 6 skipped`, full
  no-DSN regression `1384 passed, 41 skipped`, Python compilation, and
  `git diff --check`.
- Regenerated the official provider-free schema-v2 preflight as
  `fc6a682dafc831bd15234bcf75c68d6a715c9dbd90a8a78bdc1075b405bb2879`.
  It records 128,802 candidates, 128,802 matched next bars, zero missing bars,
  `S_max=182`, `P_max=19590.0`, `C=4465307372`, and
  `f=0.004387155994`. Canonical catalog reload and digest verification pass.
- Read-only application PostgreSQL verification confirms Migration 014 is still
  unapplied and no R5 head, registration, or operation exists. Execution stays
  paused before the first irreversible mutation until an independent short
  re-review approves the schema-v2 remediation.
- Independent short re-review approved the cross-session matcher, schema-v2
  algorithm identity, regression, canonical artifact rebuild, and v1
  fail-closed behavior with no blocker.
- User explicitly authorized formal R5 execution after that approval. The next
  action is one final pre-mutation identity check followed by Migration 014 and
  the sole authoritative registration/Control Run. R6, Local Paper, providers,
  broker, and real-money remain prohibited.
- The first final pre-mutation probe aborted read-only because status values
  were quoted as SQL identifiers. No table or Run changed; the retry uses a
  parameterized status array rather than repeating that SQL construction.
- Corrected pre-mutation verification passed: the baseline/binding/v2 preflight
  identities are unchanged, all 128,802 candidates match, no other Run is
  active, and Migration 014 tables remain absent. Added an isolated execution
  harness with a call-blocking MockProvider, stable idempotency key, durable
  status monitoring, and cleanup that cannot cancel unrelated Runs.
- Repository initialization applied Migration 014 and atomically created the
  sole revision-1 registration plus Control Run
  `run-4de8112d3a154148a1af93fc86a26f83` with config digest
  `1f0f38e0b7036f6dce2f7fd358ff38fea5bc0afe720cae1870c02c210d24e0f6`.
  Creation was not a replay; registration status is `RUN_CREATED`, preflight
  digest is the approved schema-v2 artifact, and the worker entered `RUNNING`.
- The worker completed all 28,325,340 Kbars with zero provider calls, then the
  server postflight correctly sealed revision 1 as `INVALID` and the Run as
  `INVALID_CASH_ADMISSION_CONTROL`; no performance result was published.
- Postflight diagnostics: baseline/candidate signals `128802`, control ENTRY
  orders `128772`, control ENTRY fills `118252`, non-FILLED cash rejections
  `10520`, and both signal-count/multiplicity parity checks failed. Postflight
  digest is `e0bf1d76555eb62b4e4fe93b0dcd9f0187bf2a8fd8b878ea070ea4fa8cf78c6f`;
  provider audit is an empty list.
- The formal `REPEATABLE READ READ ONLY` acceptance SQL rejected as required
  with exit code `3`, rolled back its snapshot, and reported no published
  control result, registration `INVALID`, Run `INVALID_CASH_ADMISSION_CONTROL`,
  and server postflight not accepted.
- Final durable audit confirms Migration 014 exactly once, one head, one sealed
  registration, one operation, no active Runs, and zero published result rows,
  chunks, trades, or daily-equity rows for the invalid Control Run.
- R5 decision: the authoritative control is invalid and cannot be interpreted
  as strategy performance. The strategy remains `HOLD / NOT ELIGIBLE`; R6 is
  blocked. Any attempt to change sizing or signal-parity semantics requires a
  separately reviewed contract revision rather than retry/clone of revision 1.

### R5 contract revision 2 design

- User required a new R5 contract revision that removes current-equity sizing
  and signal-parity path dependence.
- Started a design-only phase. No revision-2 Run, migration, PostgreSQL state,
  R6, Local Paper, provider, broker, or real-money operation is authorized.
- Frozen the primary design direction: baseline ENTRY evidence becomes a
  canonical signal ledger, and every signal is independently replayed at one
  lot without strategy re-evaluation or shared portfolio state.
- Source inspection confirmed engine order: pending fill, position-dependent
  branch, then exit or new ENTRY evaluation. The revision-2 implementation will
  therefore use a separate research replay boundary, not
  `HistoricalBacktestEngine.run()`.
- Frozen provisional exit matching for design review: first same-symbol
  session close strictly after the matched entry Kbar; an entry on a closing
  Kbar exits at the next observed session close. Missing entry/exit invalidates
  the replay.
- Created `architecture/vwap_signal_ledger_replay_v2_implementation_plan.md`
  with frozen research scope, ledger/match/episode schemas, Decimal formulas,
  Clean Architecture ports, PostgreSQL/idempotency contract, publication
  barrier, adversarial tests, and staged Gates.
- Updated the original failure-attribution Gate so revision 1 and R6 v1 are
  visibly historical/superseded and cannot be mistaken for execution authority.
- Contract self-review corrected order-level strategy fields to the actual
  member IDs, moved exact Version identity to the manifest, and disclosed that
  the ledger covers baseline-observed rather than counterfactual signals.
- Targeted `git diff --check`, trailing-whitespace, EOF newline, Markdown fence,
  and local-link checks pass. No product tests were run because this phase only
  changes design/planning documents.
- **Disposition:** R5 revision 2 design complete / ready for independent Review.
  Implementation, migration, PostgreSQL mutation, formal replay, R6, Local
  Paper, provider, broker, and real-money remain unauthorized.

### R5 revision 2 G0 remediation

- Independent Review found three P1 blockers: nonexistent historical order
  projection authority, open-ended immutable schemas, and incomplete layer-by-
  layer parity checks.
- Accepted the findings and reopened G0. Design direction remains the canonical
  signal ledger plus independent one-lot episodes; implementation and execution
  remain unauthorized.
- Replaced order authority with baseline ENTRY decisions already protected by
  `result_digest`. Signal IDs now derive from decision IDs; current orders only
  form an explicitly labelled v2 inception derivation seal that is recomputed in
  the registration transaction and on later reads.
- Froze common UTF-8/canonical JSONL, timezone, Decimal, sorting, and digest
  rules plus exact key sets for order derivation, Signal Ledger/manifest,
  Match Plan/manifest, modeled Entry/Exit, Replay Episode, result summary/
  manifest, and postflight conditions/diagnostics/verdict.
- Added exact `(sequence, signal_id, semantic_key)` multiset parity in both
  directions across all six boundaries, explicit duplicate-match rejection,
  per-direction difference counts, and same-count substitution regressions.
- **Disposition:** three G0 Review fixes applied / ready for short re-review.
  G0 is not passed or frozen; implementation/execution and all downstream
  authorities remain blocked.

### R5 revision 2 exact-contract re-review reopening

- Independent Review closed the original three G0 blockers but found three new
  P1 contract inconsistencies: Match multiplicity token arity, finite Profit
  Factor canonicalization, and source-order regression semantics.
- Reopened G0 as `CHANGES REQUIRED / NOT PASSED / NOT FROZEN` before editing
  the contract.
- Work remains design-document-only. Implementation, execution, Migration,
  PostgreSQL mutation, R6, Local Paper, provider, broker, and real-money paths
  remain unauthorized.
- Unified Match/Result/Postflight layer multiplicity identity on the exact
  `(sequence, signal_id, semantic_key)` token and shared projection schema.
- Froze finite Profit Factor arithmetic and canonical scale-18 Decimal output,
  including zero, infinity, undefined, and failure cases.
- Split source-order tests: authoritative durable decision reorder fails
  identity verification, while unpublished derived-chunk reorder converges
  after canonical publication.
- Clarified that derived parity sorting happens only after durable authority
  identity verification and never rewrites the stored-order projection.
- **Disposition:** exact-contract fixes complete / ready for short G0 re-review.
  G0 is still not passed or frozen; downstream authority remains blocked.

### R5 revision 2 G0 approval and scoped packaging

- Independent Review reported no remaining blocker and explicitly approved G0.
- Updated the implementation plan, research Gate, task plan, findings, and
  progress to `APPROVED / G0 PASSED / CONTRACT FROZEN`.
- User authorized a scoped local commit containing only the R5 revision-2 design
  and these approval records. Push, G1 implementation, formal replay, R6, Local
  Paper, provider, broker, and real-money execution remain unauthorized.

### R5 revision 2 G1 implementation

- User explicitly authorized the next phase. Started G1 only: pure domain,
  minimal ports, immutable filesystem artifact adapter, and focused tests.
- Frozen boundary: no migration, PostgreSQL repository, Dashboard/API, official
  full-Dataset preflight, formal replay, R6, Local Paper, provider, broker, or
  real-money operation.
- Verification targets are exact-schema/canonical-byte fail closed behavior,
  deterministic one-lot math and matching, six-layer multiplicity parity,
  bounded streaming/external-sort behavior, interruption cleanup, clean-root
  digest replay, focused/no-DSN regression, compilation, and whitespace.
- Inspected the frozen schemas and existing canonical/domain/artifact patterns.
  Chosen implementation keeps `domain.py` framework-free, uses minimal Protocol
  ports, and places filesystem publication/reload in `artifact_store.py`.
- Added the isolated `backtest.research_replay` package, G1-only ports, strict
  canonical primitives, decision-ledger/order derivation builders, streaming
  cross-session matcher, Decimal one-lot episode/summary calculator, and exact
  layer multiplicity comparison. No persistence or external-call composition
  was added.
- Initial package compilation passes. The next G1 slice is exact manifest
  construction plus filesystem publication/reload; PostgreSQL remains out of
  scope.
- Added exact ledger/match/result manifest builders and verifiers, cost/result
  identities, strict postflight conditions/diagnostics, all six bidirectional
  layer comparisons, and frozen-signal-count fail-closed behavior.
- Added atomic filesystem publication/reload for ledger, match-plan, and result
  directories. Payloads use bounded sequence-sorted chunks, canonical JSONL,
  fsync, exact file sets, SHA/parity/semantic checks, same-digest replay, and
  `BaseException` temporary cleanup. Compilation remains green.
- First focused domain/artifact regression passes `14 passed`.
- Self-review identified three pre-Gate hardening items: reconstruct row IDs,
  distinguish matched-entry from completed-match counts, and recompute Result
  row/formula/summary consistency instead of trusting a self-consistent
  manifest. These are being fixed before broader regression.
- Closed all three self-review items and added fail-closed regressions for
  reconstructed IDs/economics, entry-versus-exit counts, and a payload plus
  manifest digest rewrite that attempts to alter episode economics.
- Replaced the production match path with one-pass streaming state and added a
  400-session regression proving only one waiting/pending signal is retained in
  the fixture. Added bounded fan-in external merge coverage with 150 one-row
  chunks and canonical sequence reconstruction.
- G1 focused domain/artifact result: `22 passed`.
- Related R5 no-DSN result: `38 passed, 6 skipped`; skips are PostgreSQL-only.
- Full no-DSN regression: `1412 passed, 41 skipped`.
- Python compilation and scoped whitespace checks pass. No external provider,
  broker, PostgreSQL, official full-Dataset, or formal replay operation ran.
- **Disposition:** `G1 IMPLEMENTATION CANDIDATE / REVIEW REQUIRED`; formal G1
  remains not passed, and G2-G5/R6 remain unauthorized.

### R5 revision 2 G1 Review remediation

- Independent Review returned `REQUEST CHANGES` with two P1 blockers and one
  P2 finding: cost identity substitution, source-bar bytes/value divergence,
  and falsey execution-horizon normalization.
- Reopened G1 as `REMEDIATION REQUIRED / GATE NOT PASSED` before changing
  product code. The remediation is limited to the three domain identities and
  their adversarial tests; downstream phases remain unauthorized.
- Added exact cost identity to `ReplayBuild`; manifest construction compares
  caller parameters, ReplayBuild evidence, and economics reconstructed from
  modeled rows. Postflight and artifact publication/reload repeat the digest
  comparison and reject relabelled economics before final publication.
- Removed source-byte synthesis from `ObservedBar.from_historical_bar()`.
  Exact canonical bytes are now mandatory, must round-trip through the complete
  `HistoricalBar` projection, and must match symbol/time/session/open/close used
  by the matcher.
- Restricted horizon normalization to missing/null only in both decision and
  order construction. Empty string, false, and zero regressions fail closed.
- Remediation focused result currently passes `26 passed`; broader regression
  remains to be run before returning to Review.
- Related R5 no-DSN remediation regression passes `42 passed, 6 skipped`.
- Full no-DSN remediation regression passes `1416 passed, 41 skipped`.
- Source AST/compilation, untracked-file trailing-whitespace/EOF checks, and
  tracked planning/document `git diff --check` pass. Generated cache artifacts
  inside the new package were removed; unrelated existing caches were untouched.
- **Disposition:** all three Review findings are closed in the candidate;
  `G1 REMEDIATION CANDIDATE / RE-REVIEW REQUIRED`. Formal G1 is not yet passed,
  and G2-G5/R6 remain unauthorized.

### R5 revision 2 G1 approval and G2 implementation

- Independent short re-review approved G1 and reported no new finding.
- Recorded `G1 APPROVED / FORMAL GATE PASSED`; formal progress is 33.3%.
- User explicitly authorized G2 only. Began PostgreSQL/application inventory,
  confirmed migration 015 is currently the next available number, and kept G3
  full Dataset preflight plus all execution/trading authorities blocked.
- Selected a bounded-context implementation: G1 domain remains framework-free;
  application depends on ports; PostgreSQL owns atomic mutation and current
  durable-evidence verification; filesystem artifacts remain immutable outer
  evidence and locator paths do not enter identity.

### R5 revision 2 G2 implementation candidate

- Added PostgreSQL migration 015 with dedicated replay head, immutable
  registration, durable operation replay, accepted result root, and bounded
  result-chunk tables. Revision 2 remains outside normal `backtest_runs`.
- Added strict application use cases and ports for create/start/cancel/fail,
  terminal publication, redacted status reads, and accepted-economics reads.
- Added advisory-lock serialization, revision CAS, same-key response-loss
  replay, different-key authoritative no-op, and atomic registration/operation/
  result/postflight publication.
- Same-key response-loss replay is resolved before current filesystem artifacts
  or baseline evidence. A new operation still revalidates baseline result,
  config, Dataset, v1 INVALID lineage, decision/order inception seal, and exact
  G1 ledger/match artifacts.
- Registration preserves and revalidates exact request JSON/digest, actor,
  change note, preflight, ledger, match, and order-derivation identity. Status
  CAS cannot overwrite a committed `CANCELLING` state.
- Economics remain unavailable unless postflight is `ACCEPTED`. INVALID
  publication persists diagnostics but creates no result root or economics.
- Focused no-DSN G1/G2/migration result: `35 passed, 9 skipped`.
- Disposable PostgreSQL 17 focused result: `11 passed`.
- Full no-DSN regression: `1454 passed, 49 skipped`.
- Full disposable PostgreSQL 17 regression: `1503 passed`.
- Python compilation and `git diff --check` pass. No official Dataset scan,
  replay execution, provider/broker call, Local Paper, R6, commit, or push ran.
- **Disposition:** `G2 IMPLEMENTATION CANDIDATE / INDEPENDENT REVIEW REQUIRED`;
  formal progress stays 33.3% until G2 is independently approved.

### R5 revision 2 G2 Review remediation

- Independent Review returned `REQUEST CHANGES` for operation replay scope,
  cancellation progress preservation, and exact integer revision validation.
- Reopened G2 before product edits. The remediation is limited to these three
  findings and adversarial regressions; G3-G5, R6, Local Paper, provider,
  broker, and real-money remain unauthorized.
- Added exact regression probes before changing product code. Current candidate
  reproduces request revision `0.0` acceptance and cancellation progress reset;
  PostgreSQL scope/revision/progress probes await the disposable database.
- Implemented exact integer checks for request and operation revisions; bool,
  float, Decimal, and string aliases now fail before mutation or replay.
- Cancellation now sends no progress mutation. PostgreSQL uses the existing
  durable registration value for `RUNNING -> CANCELLING`; only later worker
  terminal transitions can write final progress.
- Operation replay now binds the result to the queried baseline and request
  preflight, then verifies the referenced registration, request digest, replay,
  head revision, and ledger identity without revalidating mutable baseline
  evidence needed only by new operations.
- Disposable PostgreSQL focused remediation passes `25 passed`, including five
  independent scope substitutions, numeric revision alias, and nonzero progress
  preservation.
- Full no-DSN regression passes `1482 passed, 56 skipped`.
- Full disposable PostgreSQL 17 regression passes `1538 passed`.
- Python compilation, scoped whitespace checks, and `git diff --check` pass.
- The disposable PostgreSQL container is the only remaining temporary resource
  and will be removed before handoff. No formal preflight, Replay execution,
  provider, broker, Local Paper, R6, commit, or push ran.
- **Disposition:** `G2 REMEDIATION CANDIDATE / RE-REVIEW REQUIRED`; formal
  progress remains 33.3%.

### R5 revision 2 G2 approval and scoped commit authorization

- Independent short re-review approved G2 with no new finding.
- Updated the Formal Gate to `APPROVED / PASSED` and progress to 50%.
- User authorized a local scoped commit containing only R5 v2 G1/G2 code,
  tests, migration, architecture, and isolated planning evidence. Push and all
  unrelated shared-worktree files remain excluded.

## 2026-08-25 R5 revision 2 G3 start

- Created scoped local commit `3ff0182 feat(backtest): add R5 v2 replay
  foundation`; no push and no unrelated dirty-worktree files were included.
- Updated the frozen Gate record to G3 `AUTHORIZED / IN PROGRESS`; formal
  progress remains 50% until independent G3 Review passes.
- Implemented the first G3 candidate slice: read-only baseline evidence,
  exact full-Dataset source adapter, provider-free preflight service/CLI, and
  focused tests.
- Focused no-DSN result at this checkpoint: `38 passed`.
- Formal 28,325,340-bar execution and PostgreSQL read-only integration remain
  pending; no durable Replay, Local Paper, broker, or real-money action occurred.

## 2026-08-25 R5 revision 2 G3 candidate completion

- Disposable PostgreSQL read-only evidence regression passed after separating
  G3 snapshot reads from the G2 row-lock path; Replay table counts stayed zero.
- Formal full-Dataset preflight completed with exit `0` and published canonical
  ledger, match-plan, and operation-audit artifacts under
  `data/backtest/research_replay`.
- Formal counts: `128802` signals, entries, and exits; zero missing entry, zero
  missing exit, zero duplicate match, and zero strategy/provider/broker calls.
- Independent artifact reload audit exited `0`; both bidirectional parity
  differences are zero and both manifest digests rebuild.
- Full no-DSN: `1487 passed, 57 skipped`; full disposable PostgreSQL 17.11:
  `1544 passed`. Compilation and `git diff --check` pass; disposable DB removed.
- Application PostgreSQL remains untouched by migration 015 and has no R5 v2
  Replay relations. G4 registration/execution is still not authorized.
- **Disposition:** `G3 IMPLEMENTED / EXECUTED / FORMAL REVIEW REQUIRED`;
  formal progress remains 50% pending independent Review.

## 2026-08-26 R5 revision 2 G3 provenance remediation

- Reproduced the Review boundary: canonical operation-audit fields were not
  compared with immutable ledger and match provenance.
- Added exact schema identity and three-way baseline/Dataset provenance checks.
- Added canonical valid-shape tamper regressions for schema version, baseline
  Run ID, Dataset ID, Dataset digest, and Dataset payload SHA-256.
- Focused G1/G3 regression passes `31 passed`; the unchanged formal artifacts
  re-audit with 128,802 signals and zero parity differences.
- Python compilation and scoped `git diff --check` pass. No full Dataset scan,
  PostgreSQL operation, Replay execution, G4 work, commit, or push occurred.
- **Disposition:** `G3 REMEDIATION CANDIDATE / FORMAL RE-REVIEW REQUIRED`;
  formal progress remains 50%.

## 2026-08-26 R5 revision 2 G3 approval and commit authorization

- Independent short re-review approved G3 with no new finding.
- Recorded `G3 APPROVED / FORMAL GATE PASSED`; formal progress is 66.7%.
- User authorized a local scoped G3 commit followed by G4 start. Push and all
  unrelated shared-worktree files remain excluded; G5, R6, Local Paper,
  provider, broker, and real-money remain unauthorized.
