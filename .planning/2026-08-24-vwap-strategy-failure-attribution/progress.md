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
