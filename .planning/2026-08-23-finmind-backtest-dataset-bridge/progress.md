# Progress: FinMind Backtest Dataset Bridge

## 2026-08-24 — G5 formal acceptance complete

- Applied `013_backtest_result_chunks.sql` after disposable PostgreSQL
  validation (`39 passed`). Full no-DSN regression is green at `1339 passed,
  35 skipped` after adding the migration to the frozen migration inventory.
- Recovered the first OOM-affected Run as FAILED only after confirming it had
  no result row, then used the normal CSRF-protected Web retry endpoint with
  durable idempotency and actor audit.
- Completed Web Run `run-91ad87981676414da87b928398fa43c9` over all 28,325,340
  bars. Status is COMPLETED, progress is 1.0, error is null, and result digest
  is `60c29af24fd67ef9c3952118e3f157f5fab62a81e33a6f9b955bc8b5e76f57bc`.
- Verified compact chunk root, all chunk digests, normalized row counts, full
  result reconstruction, recomputed result digest, exact binding/Dataset,
  proxy amount evidence, Web summary/trade endpoints, audit event, bounded DB
  resources, and loopback/PostgreSQL-only process sockets.
- Marked G5 `APPROVED / GATE PASSED`; formal bridge progress is 100%. Local
  Paper, broker, Shioaji order, and real-money remain outside authorization.

## 2026-08-23 — G5 Code approval / formal acceptance start

- Independent re-review approved the G5 code remediation; formal progress
  remains 80% until the exact application binding and full Web Run pass.
- User authorized a scoped G5 commit, then formal G3 Dataset registration,
  default activation, full 28,325,340-bar Atomic Run, and evidence audit.
- Started commit-payload reconstruction against the current shared worktree.
  No push is authorized, and trading-related scopes remain excluded.

## 2026-08-23 — G5 Review remediation start

- Independent Review returned `G5 REQUEST CHANGES`; formal progress remains
  80% and no Gate status was advanced.
- Scoped remediation to three items: runtime VWAP amount-contract validation
  and evidence, atomic worker status transitions, and terminal progress flush
  for CANCELLED/FAILED.
- Success criteria are explicit negative tests for missing/unknown amount
  contracts, persisted VWAP evidence, an accepted-cancel/worker-transition
  race, and worker-level cancellation/failure progress preservation.
- Application activation, full 28,325,340-bar Web Run, Local Paper, broker,
  real-money, commit, and push remain outside this remediation.
- Added exact VWAP amount-contract validation to the completed-Kbar Feature
  adapter, bound the verified contract into runtime construction and per-bar
  Feature input digests, and persisted the resulting evidence in VWAP strategy
  evaluations.
- Added repository-level expected-status CAS for worker PREFLIGHT/RUNNING
  transitions and changed the worker to reject a conflicting `CANCELLING`
  state instead of overwriting it.
- Added forced progress flush in both CANCELLED and FAILED worker paths.
- First remediation subset passed `6 passed, 3 skipped`; the three skips are
  PostgreSQL-only binding/CAS cases. Relevant Python compilation also passed.
- Expanded no-DSN focused scope passed `89 passed, 6 skipped`; direct SQLite
  CAS plus worker-level terminal flush scope passed `10 passed`.
- Full no-DSN regression passed `1336 passed, 34 skipped`.
- Started a loopback-only disposable PostgreSQL 17 container, then focused
  runtime/CAS verification passed `19 passed` and the complete PostgreSQL suite
  passed `1370 passed`.
- Stopped the disposable container; its `--rm` lifecycle removed the test
  database. No application/development PostgreSQL or formal G3 binding changed.
- Marked the three findings `REMEDIATED / AWAITING RE-REVIEW`; formal G5 remains
  NOT PASSED at 80%, and no commit or push was created.
- Final relevant Python compilation and repository-wide `git diff --check`
  passed. A final scoped status inspection confirmed only the existing G5
  candidate files plus this remediation/planning evidence are in scope; shared
  Local Paper, Strategy Set, live-trading, odd-lot, and research changes remain
  untouched and unstaged.

## 2026-08-23 — G4 commit packaging / G5 authorization

- User explicitly requested a scoped G4 commit and authorized G5 only after
  that commit is created.
- Created local scoped commit `2e873cd` (`feat(backtest): bind immutable
  FinMind datasets`) after `14 passed, 8 skipped`, relevant compilation, and
  cached whitespace validation. No push and no application database activation.
- G5 is now explicitly authorized and implementation has started. Its scope is
  the selector-less Web Atomic Run resolver, binding preconditions, immutable
  Dataset evidence, VWAP amount-contract preflight, and bounded control traffic.
- Started shared-worktree payload inspection. The G4 commit must exclude
  Local Paper, Strategy Set archive, `.planning/.active_plan`, and all other
  concurrent changes; no push is authorized.
- Mixed files requiring partial staging were identified:
  `backtest/repository.py`, `README.md`, the migration expectation tests, and
  `tests/test_strategy_publish_idempotency.py`. G4-only files can be staged
  whole; concurrent archive and Local Paper changes must remain unstaged.
- The staged index will be reviewed independently before commit, including
  migration numbering and the current eight-strategy registry assertion.
- Built the scoped G4 index: 14 files, with partial hunks for the mixed files.
  `011_strategy_set_archives.sql`, archive tests, Local Paper settings, and all
  other concurrent work remain unstaged. `git diff --cached --check` passes.
- G5 implementation is in progress; application-environment activation, Local
  Paper, broker, and real-money work remain out of scope.
- Initial G5 seam audit confirms the current Web launcher still renders an
  independently guessed preferred READY Dataset and the application still
  falls back to `_select_ready_dataset()` for standalone Atomic Runs. The
  existing early Run lookup and Baseline inheritance can be retained but need
  request-digest and exact binding contracts.
- The worker's engine callbacks currently issue one durable progress UPDATE and
  cancellation SELECT on every local callback. Both will be wrapped rather than
  changing the deterministic engine cadence.
- Chosen implementation boundary: a new PostgreSQL-only atomic Run creation
  method will re-check the binding head and Dataset row inside the same
  transaction as `backtest_runs` insertion. Retry/clone remain on their
  existing original-config path and never consult the current binding.
- No G5 migration is required: request/binding/amount evidence will be optional
  canonical mappings inside `BacktestRunConfig`, covered by the existing config
  digest and row/config identity verification.
- Legacy automatic-selection tests are now identified as contract tests that
  must be replaced: standalone Atomic Runs will require PostgreSQL binding
  preconditions, while explicit original-Dataset retry/clone behavior remains
  covered separately.
- G5 will expose a server-owned binding status endpoint keyed by the selected
  exact Strategy Set. The browser will hold its revision/digest projection and
  submit those exact preconditions; it will no longer fetch or rank Dataset
  rows for launch readiness.
- First focused execution reached product code successfully: `19 passed,
  3 skipped, 4 failed`. All four failures are expected stale assertions from
  the removed automatic READY-Dataset selection and old launcher copy; no new
  runtime exception or syntax failure was found.
- Replaced the stale service tests with PostgreSQL-binding fixtures and added
  response-loss-after-switch, stale-precondition, same-key/different-request,
  Feature amount evidence, missing amount contract, and bounded control-traffic
  regressions. PostgreSQL cases remain skip-gated when no test DSN is present.
- Updated API/UI contract tests for the server-owned projection and exact
  revision/digest submission. The current no-DSN G5 focused slice is green at
  `25 passed, 5 skipped` before adding the remaining direct PostgreSQL lock and
  comparability assertions.
- Expanded no-DSN G5 scope is green at `44 passed, 13 skipped`. The skips are
  PostgreSQL-only binding/transaction cases. `TEST_POSTGRES_DSN` is not set;
  Docker is installed but daemon access requires an explicit sandbox
  escalation before disposable PostgreSQL verification.
- Disposable PostgreSQL 17 focused verification passed `27 passed`; full
  no-DSN regression passed `1330 passed, 33 skipped`; full disposable
  PostgreSQL regression passed `1363 passed`. The test database/container was
  stopped and auto-removed, and no application/development database was used.
- The first PostgreSQL attempt had two teardown errors because two new tests
  gave the fixture-owned connection to `service.close()`. They were corrected
  to use independent test connections; product assertions had already passed,
  and the clean reruns above are the current evidence.
- Final candidate rerun after adding Baseline/Challenger Dataset inheritance:
  PostgreSQL focused `27 passed`, disposable PostgreSQL full `1363 passed`.
  Python compilation, Dashboard JavaScript syntax, and `git diff --check` all
  pass. The second disposable container was stopped and auto-removed.
- G5 code is now an implementation candidate awaiting independent Review. The
  formal Gate remains 80% / G5 NOT YET PASSED because the exact G3 full Dataset
  has not been activated in an application PostgreSQL environment and its
  28,325,340-bar Web Run acceptance has not been authorized or executed.

## 2026-08-23 — G4 implementation start

- Independent re-review approved `G4 APPROVED / GATE PASSED` with no remaining
  blocker. Formal Gate progress is now 80%.
- Recorded reviewer evidence: no-DSN `8 passed, 7 skipped`, migration
  `6 passed, 1 skipped`, collected PostgreSQL scope 15 tests with candidate
  evidence `15 passed`, plus compilation, CLI help, and `git diff --check`.
- This approval update changes planning documents only. No database,
  application activation, G5 work, commit, or push was performed.
- Independent Review returned G4 to `REQUEST CHANGES / GATE NOT PASSED` because
  concurrent activation only covered same-key replay, not distinct-operation
  CAS contention.
- Started the single-blocker remediation. Scope is one PostgreSQL regression
  using different keys/targets with the same expected revision, plus focused
  disposable-PostgreSQL verification. G5 and Local Paper remain untouched.
- Added the exact distinct-operation race regression with two registered target
  Datasets, two idempotency keys, one shared expected revision `0`, and a
  two-worker barrier. It asserts one `BOUND` result, one revision conflict,
  head revision `1`, and exactly one binding/revision/operation row.
- The first PostgreSQL execution reached the intended one-success/one-conflict
  assertions, then failed only because the fixture inspection connection had
  not set `search_path` while the new count queries used unqualified table
  names. The count assertions now explicitly use the `backtest` schema.
- Reviewer-specified distinct-operation race passed `1 passed`. Complete G4
  focused PostgreSQL passed `15 passed`; G4 plus migration scope passed
  `22 passed`.
- Focused no-DSN remains `8 passed, 7 skipped`, where all seven skips are
  explicit PostgreSQL tests. Compilation and `git diff --check` pass.
- Stopped and automatically removed the disposable PostgreSQL container. No
  development or production database was accessed.
- Marked G4 `REMEDIATED / AWAITING RE-REVIEW`. G5 remains unauthorized; no
  product logic, Local Paper code, commit, or push was added in remediation.

- Committed the four G3 approval/evidence documents as local commit `8beca2b`
  (`docs(backtest): record FinMind full artifact gate`); no push was performed.
- User then explicitly authorized G4 PostgreSQL immutable registration and
  `ATOMIC_BACKTEST_DEFAULT` binding.
- Marked G4 `AUTHORIZED / IN PROGRESS`; G5 Web, Local Paper, broker, and
  real-money remain unauthorized.
- Preflight reserved migration 012 because concurrent untracked migration 011
  already exists. Confirmed the PostgreSQL adapter has advisory-lock and
  transaction-per-checkout infrastructure, while the existing Dataset upsert is
  mutable and cannot satisfy G4 immutable registration.
- One read used a nonexistent `backtest/migrations/__init__.py` path; no change
  occurred, and the inspection was rerun against `backtest/migrations.py`.
- Added migration 012, the PostgreSQL-only immutable registration/binding
  contract, activation CLI flags, and focused tests without entering G5.
- The first focused command referenced a nonexistent standalone
  `tests/test_finmind_dataset_materializer.py`; materialization coverage lives
  in `tests/test_finmind_backtest_snapshot.py`. The corrected focused run was
  `34 passed, 3 skipped`; all skips require PostgreSQL.
- Python compilation, CLI help, and `git diff --check` passed.
- A disposable PostgreSQL 17 container was started on loopback only. The first
  sandboxed test connection was denied by network policy, so the same command
  was rerun with the approved local-network escalation.
- The first PostgreSQL run exposed that stored-manifest tampering raised a
  generic `ValueError`; the read/activation boundary now maps malformed stored
  evidence to `DatasetBindingIntegrityError`. The corrected focused PostgreSQL
  suite passed `7 passed`.
- Added real migration table/constraint/index acceptance and concurrent
  registration coverage; the expanded PostgreSQL suite passed `9 passed`.
- The first full no-DSN run intentionally disabled incremental sync, which
  invalidated two scheduler tests, and exposed two expected-migration-list
  assertions that still ended at 011. The scheduler environment override was
  removed and both lists now include migration 012 before the final rerun.
- One full PostgreSQL run exposed a stale four-Template assertion even though
  the current registry contains eight approved ENTRY Templates. The test now
  derives its expected IDs from the registry; the isolated regression passed.
- Added explicit missing and non-READY Dataset refusal coverage. Final G4
  focused evidence is `8 passed, 6 skipped` without a DSN and `14 passed`
  against disposable PostgreSQL 17.
- Final full evidence is `1309 passed, 29 skipped` without a DSN and
  `1338 passed` against disposable PostgreSQL 17. Python compilation and
  `git diff --check` passed.
- Stopped and automatically removed the loopback-only disposable PostgreSQL
  container. No development or production database was accessed.
- One cleanup command used a misspelled workspace path and could not start;
  rerunning the same `docker stop` from the correct workspace succeeded.
- Marked G4 `IMPLEMENTATION CANDIDATE / AWAITING REVIEW`; G5 remains
  unauthorized and no G4 commit or push was created.

## 2026-08-23 — G3 approved

- Independent Review found no blocker and approved
  `G3 APPROVED / GATE PASSED`; formal Gate progress is now 60%.
- Review evidence reconfirmed the canonical manifest, 28,325,340-line payload,
  exact SHA-256, approximately 16-minute full replay, 182 observed symbols,
  fail-closed exclusion of 8 incomplete symbols, and absence of matching
  temporary Dataset directories.
- Recorded the approval in the implementation plan and task plan only. G4–G5
  remain unauthorized; no PostgreSQL, Web, trading, commit, or push action was
  performed.

## 2026-08-23 — G3 full artifact start

- User authorized the next phase after local commit `9aa81eb`.
- Marked G3 Full Artifact `AUTHORIZED / IN PROGRESS`; G4 PostgreSQL and G5 Web
  remain unauthorized.
- Success requires a live online-backup plan, dynamic count/disk evidence,
  complete materialization from that exact saved snapshot, and independent
  readback verification before G3 may be submitted for Review.
- No PostgreSQL, Web, Local Paper, broker, real-money, commit, or push is
  included in this phase.
- Preflight located the 410,701,824-byte live SQLite source and the frozen
  TaiwanStockInfo artifact. About 74 GiB was available on the output
  filesystem before planning.
- A read-only `ps` probe was denied by the sandbox. It is not required because
  the implementation uses SQLite online backup; the command was not retried.
- Published the exact G3 plan/copy pair under
  `data/backtest/finmind_plans/g3_20260823T1730+0800/`.
- Dynamic plan evidence: 182 included symbols, 8 excluded symbols, 28,325,340
  bars, 132,314 included partitions, 9,192,825,060 expected output bytes, and
  79,580,540,928 bytes available. Disk preflight is sufficient.
- Executed the exact saved plan and atomically published
  `dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6`.
- CLI execution completed with bar count 28,325,340, payload SHA-256
  `216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d`,
  and manifest digest
  `ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29`.
- Independent `wc -l` and `shasum -a 256` readback matched the manifest exactly;
  the final directory exists and no matching temporary directory remains.
- Re-executed the exact saved plan against the already published artifact. The
  full idempotent replay verifier passed after comparing all canonical source
  and payload rows plus ordering, cadence, watermarks, symbols, count, and
  digests; it returned the same identities without replacement publication.
- Marked Phase 3 complete and G3 `IMPLEMENTATION CANDIDATE / AWAITING REVIEW`.
  G4–G5 remain unauthorized and no PostgreSQL, Web, trading, commit, or push
  action was performed.
- Post-materialization focused regression passed: `43 passed in 0.51s`.
  Python compilation and `git diff --check` also passed. The published Dataset
  occupies about 5.5 GiB and the immutable plan/copy evidence about 431 MiB.

## 2026-08-23 — G2 approved

- Independent Review confirmed both replay-verifier remediations and found no
  new blocker or actionable finding.
- Recorded `G2 APPROVED / GATE PASSED` using the independent evidence:
  negative subset `4 passed`, focused subset `55 passed`, full no-DSN
  `1285 passed, 23 skipped`, with compilation, CLI help, whitespace, and
  `git diff --check` passing.
- G3～G5 remain unauthorized. No full snapshot, PostgreSQL binding, Web change,
  commit, or push was performed as part of this Gate status update.

## 2026-08-23 — G2 replay-verifier remediation complete

- Added a FinMind-only canonical payload iterator. Every raw JSONL line must
  exactly equal `canonical_json(HistoricalBar.to_dict()) + newline`; blank,
  reordered, padded, or otherwise non-canonical bytes fail closed.
- FinMind manifest replay now requires the raw file to exactly equal the
  canonical serialization reconstructed from `DatasetManifest.to_dict()`.
  Unknown fields, paths, handoff evidence, and non-canonical bytes are rejected.
- Added the two exact Reviewer regressions: blank payload line with rewritten
  payload/manifest digests, and injected `locators` with the original digest.
- Reviewer negative subset passes: `4 passed, 26 deselected`.
- Focused G2 plus affected Dataset tests pass: `65 passed in 0.80s`.
- Full no-DSN regression passes: `1285 passed, 23 skipped in 7.59s`.
- Python compilation and `git diff --check` pass.
- Marked G2 `REMEDIATED / AWAITING REVIEW`. G3～G5 remain unauthorized; no
  full snapshot, PostgreSQL, Web, Local Paper, broker, commit, or push work was
  performed.

## 2026-08-23 — G2 replay-verifier remediation start

- Independent Review set `G2 REQUEST CHANGES / NOT PASSED` after two negative
  probes were incorrectly accepted.
- Scoped remediation to exact canonical `bars.jsonl` bytes and exact canonical
  FinMind manifest schema/bytes, plus the two corresponding regressions.
- G3～G5 remain unauthorized; no full snapshot, PostgreSQL, Web, Local Paper,
  broker, commit, or push work is included.

## 2026-08-23 — G2 implementation candidate

- Added optional Dataset manifest lineage for amount contract, source snapshot
  digest, canonical plan identity, and plan identity digest without changing
  legacy manifest bytes when the fields are absent.
- Added read-only, per-symbol FinMind streams that revalidate raw/canonical
  partition evidence and enrich bars from the frozen reference mapping.
- Extended the existing `HistoricalDatasetCatalog` with a bounded timestamp /
  symbol k-way merge, deterministic timestamp and ID, checksum/count/cadence /
  watermark evidence, unique temporary directories, and atomic publication.
- Existing artifacts are fully revalidated and compared with newly streamed
  source bars; manifest-only or payload-plus-manifest tampering fails closed.
- Added `--execute --plan-file` with locator overrides and exact physical plus
  semantic handoff verification. It writes only filesystem Dataset artifacts.
- Focused G2 plus affected Dataset tests pass: `63 passed in 0.62s`.
- Full no-DSN regression passes with isolated premarket artifacts:
  `1283 passed, 23 skipped in 7.36s`.
- Python compilation, CLI help, `git diff --check`, line scan, and prohibited-
  scope import scan pass.
- Marked G2 `IMPLEMENTATION CANDIDATE / AWAITING REVIEW`. No full live snapshot,
  PostgreSQL row, migration, default binding, Web change, Local Paper change,
  broker operation, commit, or push was performed. G3～G5 remain unauthorized.

## 2026-08-23 — G2 implementation start

- Independent Review approved `G1 APPROVED / GATE PASSED` with no remaining
  blocker or actionable finding.
- User said to continue, explicitly authorizing G2 small bounded-memory
  materialization.
- Scoped G2 to a small saved-plan execution path, deterministic immutable
  Dataset publication/replay, and bounded-memory/conflict tests. G3 full live
  materialization, PostgreSQL, Web, Local Paper, broker, and real-money remain
  unauthorized.

## 2026-08-23 — G1 remediation

- A follow-up Review confirmed the selection-audit fix and reproduced one
  remaining race between successful backup return and caller-side inode lookup.
- Set G1 back to `REQUEST CHANGES / REMEDIATION IN PROGRESS`; the scoped fix is
  to register ownership inside backup publication and add the exact boundary
  regression. G2～G5 remain unauthorized.
- Added the protected `on_published` ownership callback and removed the
  caller-side post-return `stat()` gap.
- Added the exact Reviewer timing regression: real backup succeeds, the wrapper
  raises `KeyboardInterrupt` before returning, and neither snapshot nor plan is
  left behind.
- Focused FinMind scope now passes: `31 passed in 0.26s`.
- Full no-DSN regression passes with the isolated premarket artifact directory:
  `1274 passed, 23 skipped in 7.69s`.
- Python compilation, CLI help, `git diff --check`, whitespace, and forbidden-
  scope checks pass.
- Synchronized the plan text so selection-audit digest is explicitly allowed to
  differ without entering immutable identity.
- Marked G1 `REMEDIATED / AWAITING REVIEW`; no full live `--plan`, Dataset,
  PostgreSQL mutation, G2 work, commit, or push was performed.
- Reviewer reproduced same Dataset/source digest but different plan identity
  when an excluded symbol gained another partition and remained incomplete.
- Reviewer also reproduced an orphan snapshot after `KeyboardInterrupt` before
  plan publication.
- Restored task context, preserved the dirty shared worktree, and limited the
  remediation to immutable/audit projection separation plus ownership-aware
  interruption cleanup and their regression tests.
- Set G1 back to `REQUEST CHANGES / REMEDIATION IN PROGRESS`; G2～G5 remain
  unauthorized.
- Split volatile compatibility/exclusion details into a separately digested
  `selection_audit`; immutable counts now derive only from included partitions.
- Added a regression where an excluded symbol advances from one to two of three
  required sessions. Dataset ID, source digest, identity, and identity digest
  stay equal while the selection-audit digest changes.
- Wrapped backup through plan publication in `BaseException` cleanup and used
  filesystem identity checks so cleanup only removes invocation-owned files.
- Added KeyboardInterrupt, SystemExit, and interrupted-backup publication
  regressions.
- Added a post-publication interruption regression proving a fully published,
  digest-valid snapshot/plan pair is preserved rather than split by cleanup.
- Focused FinMind tests pass: `30 passed in 0.26s`.
- Full no-DSN regression passes with an isolated premarket artifact directory:
  `1273 passed, 23 skipped in 7.51s`.
- Python compilation, CLI `--help`, `git diff --check`, and forbidden-scope
  searches pass. No live full snapshot, Dataset, PostgreSQL mutation, G2 work,
  commit, or push was performed.
- Marked G1 `REMEDIATED / AWAITING REVIEW`; independent Review is still required
  before it may be called passed or G2 may begin.

## 2026-08-23 — G1 implementation start

- Reviewer approved `G0 APPROVED / CONTRACT FROZEN` without remaining findings.
- User explicitly authorized implementation.
- Scoped this implementation slice to Snapshot Reader, saved plan, SQLite
  online backup, reference projection, `--plan`, and focused tests only.
- G2 materialization, PostgreSQL binding, Web Run, Local Paper, broker, and
  real-money changes remain unauthorized.
- Recovered session context and observed a heavily dirty shared worktree;
  unrelated tracked and untracked changes will be preserved.
- Located the existing FinMind job/calendar/partition schema and confirmed G1
  can be isolated from Dataset materialization and PostgreSQL work.
- One read-only repository search used an unmatched zsh
  `requirements*.txt` glob and exited early; it changed nothing, and later
  searches will use explicit paths or `rg --files`.
- Read-only inspection of the live SQLite confirmed the intended shape: many
  jobs share one semantic compatibility contract while incomplete jobs coexist.
  Counts remain dynamic evidence and are not copied into acceptance gates.
- A parallel read initially used a misspelled workdir, was retried once with the
  repository path, and made no changes.
- Added the isolated G1 implementation files:
  `backtest/finmind_snapshot.py`,
  `scripts/materialize_finmind_backtest_dataset.py`, and
  `tests/test_finmind_backtest_snapshot.py`.
- The new code is restricted to SQLite online backup, read-only semantic
  inspection, reference projection, canonical plan persistence, and handoff
  verification. It contains no Dataset writer, PostgreSQL, Web, or trading path.
- Added focused coverage for backup isolation, partial/INVALID/EMPTY selection,
  cross-job dedupe/conflict, incompatible job evidence, reference ambiguity,
  audit/SQLite-byte identity stability, handoff mismatch, raw digest drift,
  no-overwrite behavior, empty Dataset refusal, and the actual `--plan` CLI.
- First focused execution passed: `12 passed in 0.22s`.
- Re-ran the new tests together with the existing FinMind acquisition suite:
  `24 passed in 0.17s`.
- Python compilation, CLI `--help`, line-length, forbidden-scope import, and
  direct trailing-whitespace checks passed.
- Full no-DSN regression first passed with an isolated premarket artifact
  directory: `1267 passed, 23 skipped in 7.02s`.
- Added one final failure-cleanup regression; focused FinMind scope now passes
  `25 passed in 0.20s`.
- Marked G1 as an implementation candidate awaiting independent Review. G2～G5
  remain unauthorized.
- Re-ran the full no-DSN regression after the final cleanup test:
  `1268 passed, 23 skipped in 7.12s`.
- Final scoped status contains only the four bridge planning documents and the
  three new G1 implementation/test files. Direct whitespace, EOF newline,
  Markdown fence, Python compilation, `git diff --check`, and out-of-scope
  import checks all passed.
- No real full snapshot, Dataset, PostgreSQL row, migration, Web Run, Local
  Paper, broker operation, commit, or push was created.

## 2026-08-23 — Plan remediation

- Re-read the planning workflow and restored repository context.
- Preserved the dirty shared worktree and did not change
  `.planning/.active_plan`.
- Reconfirmed the current migration tip includes concurrent untracked
  `011_strategy_set_archives.sql`; no binding migration was created.
- Requeried the live acquisition store read-only. Counts advanced from the
  Review's 159 complete symbols to 160, proving fixed count gates are invalid.
- Revised the plan to use a semantic snapshot digest, deterministic manifest
  timestamp, and verified existing-directory replay.
- Added mandatory cross-job duplicate conflict semantics.
- Froze `COMMON_LOTS` for new snapshots while retaining explicit legacy
  compatibility for `COMMON_LOT` manifests.
- Made PostgreSQL `ATOMIC_BACKTEST_DEFAULT` binding a prerequisite for the
  selector-less Web flow.
- Expanded operational throttling to cover both progress writes and durable
  cancellation reads.
- No product code, tests, migration, Dataset, PostgreSQL row, Local Paper, or
  broker behavior was modified.

## 2026-08-23 — G0 contract remediation 2

- Preserved the planning-only boundary and shared dirty worktree.
- Removed acquisition `updated_at` from Dataset identity; manifest `created_at`
  now derives from the maximum included market-event boundary.
- Linked `--plan` and `--execute` through a saved canonical plan plus its exact
  SQLite online-backup artifact.
- Added binding revision and Dataset digest preconditions to close Web Run
  creation TOCTOU while preserving idempotent response-loss replay.
- Froze a required content-addressed `TaiwanStockInfo` artifact and fail-closed
  symbol/name/market mapping.
- Inspected the raw response shape and corrected the plan not to assume a
  nonexistent Dataset-name field in the body; schema plus explicit plan input
  establish the source contract.
- Confirmed read-only that the artifact's valid TWSE/TPEX rows cover all 167
  symbols currently present in acquisition partitions; this is evidence only.
- Confirmed the current raw artifact has zero ambiguous latest-date
  `(stock_name,type)` mappings under the proposed v1 rule.
- Chose to permit close-volume proxy VWAP for exploratory Runs only, with exact
  amount-contract evidence and no Qualification eligibility.
- Added Backtest-runtime Feature input preflight so generic `OHLCV` cannot hide
  a missing/unknown VWAP weight source; Local Paper remains independently bound.
- Recorded the Review's newer 161-symbol observation as non-gating evidence.
- The first combined patch failed to match one exact paragraph; it made no
  changes and was replaced with smaller exact patches.
- No product code, tests, migration, Dataset, PostgreSQL row, Local Paper, or
  broker behavior was modified.

## 2026-08-23 — G0 contract remediation 3

- Split plan identity from locator and operation-audit fields; only canonical
  identity is retained by immutable manifests.
- Made locator overrides clean-root safe through content-digest verification.
- Froze Dataset ID to the full lowercase 64-hex source SHA-256.
- Replaced the ambiguous single metadata as-of field with the sorted per-symbol
  selected date/name/market projection.
- Added caller-supplied expected revision, durable idempotency, actor, and
  change note to default-binding activation.
- Froze first creation, stale conflict, same-target no-op, and response-loss
  replay revision behavior.
- Set the main plan disposition to G0 remediated and awaiting Review; no
  implementation authorization was inferred.
- Verified all four planning files have no trailing whitespace, end with a
  newline, and contain balanced Markdown code fences.
- Verified the frozen full-digest ID, locator exclusion, per-symbol mapping,
  expected-revision conflict, no-op, and activation replay terms are present.
- No product code, tests, migration, Dataset, PostgreSQL row, Local Paper, or
  broker behavior was modified.

## 2026-08-23 — G0 contract remediation 4

- Removed copied SQLite whole-file SHA from canonical plan identity.
- Added a separate handoff-evidence projection/digest for exact plan→execute
  byte verification.
- Excluded handoff evidence from Dataset ID, manifest, Run, and all immutable
  identity digests.
- Added the required regression: same canonical data with different acquisition
  audit timestamps and SQLite bytes keeps immutable identity unchanged while
  handoff evidence may differ.
- Kept old-plan execution fail closed when the supplied file does not match its
  own handoff evidence; an independent semantic rebuild requires a new plan.
- No product code, tests, migration, Dataset, PostgreSQL row, Local Paper, or
  broker behavior was modified.
### Scoped commit preflight — 2026-08-23

- Confirmed branch `codex/organize-uncommitted-20260821` at `2e873cd` before staging.
- The shared worktree contains many unrelated Local Paper, live-trading, odd-lot, Strategy Set and research changes; the G5 commit must be reconstructed file-by-file and hunk-by-hunk.
- A combined diff was too large to review safely, so staging will use focused per-file inspection followed by an exact cached-diff audit.
- Push remains unauthorized.

### Scoped payload classification

- The amount-contract runtime/evidence changes in `atomic_strategy_adapter.py` and `feature_adapters.py`, Run evidence/domain changes, binding exceptions, repository CAS transitions, bounded control helper, and their tests are all G5 scope.
- `backtest/application.py` is predominantly G5, but contains an unrelated Strategy Set archive admission check/import that must stay out of this commit.
- PostgreSQL and generic repository changes are G5 scope: locked binding Run creation, idempotent replay lookup, and atomic status CAS.
- Dashboard and README files remain mixed and require hunk-level staging.

### Scoped index reconstruction

- Staged the G5 core/domain/repository/control files and focused tests as whole files.
- Reconstructed `backtest/application.py` so the staged version includes binding/idempotency/amount/CAS changes but excludes the concurrent Strategy Set archive check and import.
- Reconstructed Dashboard server and historical-backtest HTML/entrypoint/workspace hunks while excluding Local Paper settings and Strategy Management redesign/archive work.
- Added the response-loss request cache and removed the withdrawn legacy strategy selector only in the staged JavaScript projection.
- While the scoped index was being reconstructed, another authorized task advanced
  the shared branch from `2e873cd` to `072c0c5` with a Local Paper commit. The G5
  patch was rebased through a detached temporary tree object; the shared index was
  not cleared or overwritten.
- Resolved the two expected cache-version conflicts by retaining the committed
  Local Paper asset version while adding the Atomic Backtest module assertion.
- Finished mixed Web tests and README hunk selection. Strategy Set archive and UI
  redesign coverage remain outside this commit.
- Exported the exact alternate-index tree to an isolated directory and verified:
  focused G5 scope `53 passed, 14 skipped`; full no-DSN `1328 passed, 33 skipped`;
  Python compilation, Dashboard JavaScript syntax, and cached whitespace all pass.
- Next: commit the audited alternate-index tree, then begin the separately
  authorized application PostgreSQL activation and full Web Atomic Run.
