# Findings: FinMind Backtest Dataset Bridge

## G5 Formal Gate passed — 2026-08-24

- The first formal Run completed all 28,325,340 bars but PostgreSQL was
  OOM-killed while parsing the legacy single full-result JSONB INSERT. The
  engine result itself was complete; no result row was committed and the Run
  was recovered from orphaned `CANCELLING` to `FAILED` with an exact
  no-result precondition.
- Root cause was duplicate monolithic persistence: the same decisions, trades,
  and daily equity were embedded in `backtest_results.result_json` and then
  inserted again into normalized tables. The PostgreSQL log identified the
  failing `INSERT INTO backtest_results` statement.
- `CHUNKED_JSON_V1` now stores a compact immutable root plus 100-item chunks
  with sequence, count, and SHA-256 evidence. Legacy full JSON results remain
  readable. A bounded terminal retry also survives a short PostgreSQL restart
  without silently leaving RUNNING state.
- The Web retry `run-91ad87981676414da87b928398fa43c9` completed successfully
  with result digest
  `60c29af24fd67ef9c3952118e3f157f5fab62a81e33a6f9b955bc8b5e76f57bc`.
  Full reconstruction independently recomputed the same digest.
- Persisted evidence: 135,123 decisions, 12,642 fills, 6,321 trades, 135,123
  orders, 727 daily-equity points, zero unresolved positions; compact root
  size 214,827 bytes and largest JSONB chunk 84,585 bytes.
- The exact Dataset digest, binding revision 1, derived VWAP proxy contract,
  Feature input digest, Web retry actor/idempotency audit, and normalized trade
  pagination all verified. PostgreSQL cgroup `oom_kill` remained at the single
  historical event; the acceptance time window had no recovery/OOM log.
- Dashboard process sockets were limited to loopback port 8011 and application
  PostgreSQL port 5090. It ran with `PROVIDER=mock`, incremental sync disabled,
  memory trading journal, and one worker; no FinMind, Shioaji, CA, account,
  trade subscription, or broker call was possible or observed.
- The strategy result itself is intentionally not promoted: Dataset
  `research_eligible=false`, verdict `INSUFFICIENT_EVIDENCE`, full net P&L
  `-9,869,688.99`, and max drawdown `98.70%`. This does not block the G5 bridge
  infrastructure Gate and does block research promotion.

## G5 Code Review approved / formal acceptance authorized — 2026-08-23

- Independent short re-review approved all three code remediations with no new
  blocker. G5 Code Review is approved, while the formal Gate remains NOT
  PASSED at 80%.
- The user authorized a scoped G5 commit first, then application PostgreSQL
  registration/activation of the exact G3 Dataset and one complete
  28,325,340-bar Web Atomic Run.
- Acceptance must verify the persisted Run Dataset/binding/amount evidence,
  result digest, bounded DB control traffic, and zero provider/broker calls.
- Shared-worktree packaging must exclude all concurrent Local Paper, Strategy
  Set, live-trading, odd-lot, `.planning/.active_plan`, and research changes.

## G5 Review remediation — 2026-08-23

- Independent Review kept G5 at `REQUEST CHANGES / NOT PASSED` and formal
  progress at 80%.
- Serialized Run evidence already contains the FinMind amount contract, but
  the actual `CompletedOneMinuteKbarFeatureAdapter` is still constructed from
  an unbound `FeatureRequestSpec`. Runtime validation, Feature input identity,
  and the persisted VWAP evaluation must all carry the verified contract.
- The worker currently separates status reads from unconditional PREFLIGHT and
  RUNNING writes. A cancellation committed between those operations can be
  overwritten; the repository needs an atomic expected-status transition.
- `ThrottledProgressReporter.flush()` is only called on successful completion.
  Worker cancellation and exception paths need an explicit terminal flush and
  worker-level regressions.
- Remediation remains code-only evidence. Even after it passes, G5 requires a
  separate re-review and the authorized application binding/full-Dataset Run
  before the formal Gate can pass.
- The minimal runtime fix is to construct the Atomic resolution twice: first
  unbound only to discover requirements, then again with the verified Dataset
  amount contract for the actual runtime registry and immutable snapshot.
  `CompletedOneMinuteKbarFeatureAdapter` can reject missing/unknown VWAP
  contracts during construction and include the contract in its per-bar input
  digest/evidence without changing the VWAP arithmetic kernel.
- The shared JSON repository already centralizes `update_run()`, so the smallest
  cross-backend status fix is a sibling conditional transition method using one
  `UPDATE ... WHERE status IN (...)`; the worker treats a failed CAS with
  current `CANCELLING` as cancellation instead of writing over it.
- `ThrottledProgressReporter` already retains the newest unwritten tuple. The
  worker can keep a nullable reporter and force `flush()` in both terminal
  exception handlers, preserving the final pending progress before terminal
  status without changing deterministic result identity.
- `StrategyEvaluation.observed` is the existing persisted decision evidence
  boundary. The Atomic adapter can augment only VWAP evaluations with a
  canonical `feature_input_evidence` projection containing the normalized
  input digest and verified amount kind/digest/semantic, while leaving the
  atomic strategy kernel and Local Paper identity unchanged.
- Existing direct strategy tests call `resolve_atomic_entry_set()` without a
  Dataset contract. Preserve this unbound inspection mode, but require the
  contract whenever `bind_dataset_feature_evidence()` constructs the runnable
  snapshot and whenever the application builds the actual worker registry.
- PostgreSQL atomic cancellation already locks and transitions the row to
  `CANCELLING`; the defect is specifically the worker's later unconditional
  write. A repository CAS used by both SQLite tests and PostgreSQL production
  is sufficient, while the existing durable cancel operation remains intact.
- The worker-control regressions can use a normal non-Atomic Run with a real
  temporary SQLite repository/catalog and an injected engine. This exercises
  `_run_backtest()` terminal behavior without requiring PostgreSQL or changing
  the Atomic persistence contract; the distinct PostgreSQL status CAS remains
  covered at the shared repository SQL boundary.

## G5 implementation seam audit — 2026-08-23

- `BacktestApplicationService.create_atomic_run()` already contains an early
  idempotency lookup and Baseline Dataset inheritance seam, but standalone Runs
  still need the exact binding projection/precondition contract and durable
  same-key/different-request validation.
- The worker still calls PostgreSQL-backed progress UPDATE and cancellation
  SELECT callbacks on the engine's local cadence; both need G5 monotonic
  throttling wrappers.
- The Web client still independently chooses a READY/research-eligible Dataset
  from `/api/backtests/datasets`; this is the frozen wrong-resolver behavior and
  must be replaced by a server-owned `ATOMIC_BACKTEST_DEFAULT` projection.
- G5 must preserve concurrent, unrelated edits already present in
  `backtest/application.py`, `dashboard/server.py`, and
  `dashboard/static/js/workspaces/backtest.js`.
- Current early replay only retrieves the Run by key; it does not compare the
  incoming atomic request digest before skipping binding resolution. G5 needs a
  canonical request document stored in the immutable Run config so replay can
  reject same-key/different-precondition requests without consulting the head.
- Standalone selection still calls `_select_ready_dataset()` and the browser
  still prefers `research_eligible`; both violate the frozen no-fallback
  binding contract.
- `_run_backtest()` currently sends every engine progress callback to
  `update_run()` and every cancellation callback to `get_run()`. These are the
  exact G5 control-traffic hot paths.
- `BacktestRunConfig` has no binding/request/amount evidence fields yet. Adding
  optional canonical mappings is backward-compatible with legacy Run parsing
  and makes those projections part of `config_digest`.
- Atomic retry/clone already operate from the original parsed config and exact
  Dataset, so they must not be redirected through the current default binding.
  The standalone create path is the only place that resolves the head.
- G4 exposes a verified `get_dataset_binding()` projection and immutable
  Dataset rows. G5 can compose those without a new migration; the application
  must additionally verify the filesystem manifest and its amount contract.
- A simple application-level binding read is not sufficient: the frozen G5
  contract requires the binding head to be revalidated in the same PostgreSQL
  transaction that inserts the Run. A PostgreSQL-specific create method is
  needed; SQLite must fail closed for this standalone path.
- Imported legacy test Datasets do not carry `amount_contract`. That remains
  acceptable for non-VWAP strategies, but `vwap_session_v1` must explicitly
  require an allowlisted amount kind and preserve its digest/semantic label in
  Run evidence.
- The frozen FinMind allowlist is exact:
  `DERIVED_CLOSE_X_VOLUME_PROXY` with
  `COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY`; the embedded amount digest must
  equal the digest of the other amount-contract fields.
- To satisfy Feature-level evidence without changing calculation code, new
  Atomic snapshots will attach the verified Dataset input contract to each
  `vwap_session_v1` request and recompute the snapshot digest. Worker preflight
  will rebuild the same evidence before execution.
- Comparability already compares all non-ignored top-level config fields. The
  Dataset amount contract will remain a compared identity; request replay and
  binding provenance fields will be explicitly ignored so equivalent Baseline
  reruns do not reset experiment-family identity.
- Binding drift needs a dedicated HTTP 409 code distinct from generic
  idempotency conflict; missing backend/binding remains fail closed and the
  status projection disables launch before mutation.
- Full no-DSN and disposable-PostgreSQL suites are green. The shared worktree
  still contains substantial unrelated Local Paper, Strategy Set archive, UI,
  and research artifact changes; any future G5 commit must again use partial
  staging for mixed files and must not stage those concurrent scopes.
- README still described the removed research-eligible/READY ranking behavior;
  G5 documentation must state exact `ATOMIC_BACKTEST_DEFAULT`, browser
  preconditions, no fallback, and the VWAP close-volume proxy label.
- Final code evidence is green, but code Gate and operational acceptance remain
  distinct: synthetic/disposable binding and complete Atomic Run paths passed;
  the exact 28,325,340-bar G3 artifact has not been activated or run through an
  application Web environment. Do not mark G5 passed from the regression alone.

## 2026-08-23 — G4 execution boundary

- Independent re-review found no new blocker and approved
  `G4 APPROVED / GATE PASSED`; formal Gate progress is now 80%.
- Approval confirms the distinct-target/distinct-key revision-0 race, exact
  one-success/one-conflict outcome, and single head/revision/operation state.
- The exact G3 Dataset is still not bound to an application PostgreSQL. That
  environment activation requires separate authorization and does not itself
  authorize G5.
- Independent Review returned `G4 REQUEST CHANGES / GATE NOT PASSED` with one
  blocker: the existing concurrent activation test uses the same idempotency
  key and therefore proves durable response-loss replay, not two distinct CAS
  operations racing from the same expected revision.
- Remediation is test-only unless the new PostgreSQL regression exposes a
  product defect. It must use different keys and different targets, assert one
  `BOUND` result plus one `DatasetBindingRevisionConflict`, and verify exactly
  one head revision, one revision audit row, and one durable operation row.
- The new regression passed without a product-code change: the advisory-lock
  implementation permitted exactly one mutation, and the second distinct
  operation observed revision `1` and raised `DatasetBindingRevisionConflict`.
  Database readback confirmed one head, one revision audit, and one operation.
- G5 remains unauthorized; Local Paper failures in the shared worktree are
  unrelated and are not part of this remediation.

- User explicitly requested a G3 scoped commit and then authorized G4.
- G3 approval was committed locally as `8beca2b`; no push was performed.
- G4 is restricted to PostgreSQL immutable Dataset registration, exact
  `ATOMIC_BACKTEST_DEFAULT` binding CAS/idempotency/audit, activation CLI, and
  disposable PostgreSQL tests. G5 Web resolution and all trading paths remain
  unauthorized.
- Migration preflight found concurrent untracked
  `011_strategy_set_archives.sql`; G4 must therefore allocate
  `012_backtest_dataset_bindings.sql` and preserve the existing 011 work.
- `backtest_datasets` already exists in PostgreSQL with JSONB manifest storage,
  but its shared `upsert_dataset()` is mutable. G4 needs a separate
  PostgreSQL-only insert/verify operation and must not reuse that upsert.
- `PostgresBacktestRepository` already provides pool-aware transaction checkout
  and transaction-level advisory-lock patterns suitable for first-create CAS
  and durable idempotency serialization.
- `backtest/repository.py` contains unrelated uncommitted
  `get_run_by_idempotency_key` work. Any G4 edit there must be additive and
  preserve that diff exactly.
- G4 uses a distinct `register_immutable_dataset()` path rather than the
  mutable legacy `upsert_dataset()` path. SQLite implementations fail closed.
- Binding activation serializes the stable binding name with a PostgreSQL
  transaction advisory lock, checks durable replay before current revision,
  and records head/revision/operation in one transaction.
- Focused no-DSN coverage passes; PostgreSQL concurrency and migration tests
  remain skipped until a disposable PostgreSQL DSN is supplied.
- Disposable PostgreSQL 17 later verified migration application, exact
  registration replay/conflict, first-create CAS, durable replay after head
  advance, no-op behavior, stale conflict, tamper detection, and concurrent
  registration/activation. The final full PostgreSQL suite passed.
- No configured `BACKTEST_DATABASE_URL` was available, so the exact G3 artifact
  was not installed into an application/development database. This does not
  block the frozen G4 Gate, whose pass condition is disposable PostgreSQL
  registration/concurrency; actual environment activation remains an operator
  action before G5.

## 2026-08-23 — G3 approved

- Independent Review found no G3 blocker and approved
  `G3 APPROVED / GATE PASSED`; formal Gate progress is now 60%.
- Review independently confirmed canonical manifest/schema/identity, exact
  28,325,340-line payload and SHA-256, full saved-plan replay, all 182 observed
  symbols, fail-closed exclusion of 8 incomplete symbols, and no matching
  temporary Dataset residue.
- Dataset limitations remain explicit and non-blocking:
  `research_eligible=false`, close-volume amount proxy, current-snapshot
  survivorship, partial universe, raw unadjusted prices, and current non-PIT
  reference metadata.
- G4 PostgreSQL registration/default binding and G5 Web integration remain
  unauthorized; the Web backtest bridge is not yet deliverable.

## 2026-08-23 — G3 execution boundary

- The user explicitly authorized the next step after the G0–G2 scoped commit.
- G3 means one dynamic full snapshot of the currently complete semantic
  selection. Incomplete or incompatible symbols remain excluded evidence; they
  must not be silently included or used to block identity stability.
- The saved plan, copied SQLite source, and immutable Dataset must remain one
  verified handoff. PostgreSQL registration, default binding, Web, Local Paper,
  broker, and real-money paths remain prohibited in this slice.
- G3 preflight found the live source at
  `data/finmind_sponsor/history.sqlite3` (410,701,824 bytes) and the frozen
  reference artifact at
  `data/finmind_sponsor/universes/raw/TaiwanStockInfo_0353f33f0b2f36a12bf0c9d30a802423352ba460f6e113012e7ff5f32b5315ad.json.gz`.
- The workspace filesystem reported about 74 GiB available before planning;
  the saved plan's own dynamic output estimate remains authoritative.
- The G3 saved plan selected 182 complete symbols and 28,325,340 bars from
  132,314 partitions (132,234 READY and 80 EMPTY), while retaining 8 excluded
  symbols as selection-audit evidence.
- The plan estimated 9,192,825,060 output bytes and recorded 79,580,540,928
  available bytes, so the frozen preflight passed before materialization.
- Frozen identity: source digest
  `88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6`,
  plan identity digest
  `b72f4f6479b59acc71d5dedf780fc15c281b829bf6e645822dbd79ed27af15b6`.
- Full materialization atomically published the exact Dataset ID with no
  temporary directory left beside it. The manifest records 28,325,340 bars,
  182 requested/observed symbols, `TIMESTAMP_SYMBOL` order, and
  `research_eligible=false`.
- Independent filesystem readback found exactly 28,325,340 JSONL lines and
  SHA-256
  `216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d`,
  matching the immutable manifest. Manifest digest is
  `ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29`.
- A second execution of the exact saved plan took the existing-artifact replay
  path and completed successfully after full canonical source/payload, order,
  cadence, watermark, symbol, count, and digest verification. It returned the
  same Dataset, payload, manifest, and plan identity digests without publishing
  a replacement artifact.

## Gate status

- 2026-08-23 Review approved `G0 APPROVED / CONTRACT FROZEN` with no remaining
  blocking or important findings.
- Independent Review approved `G1 APPROVED / GATE PASSED` after verifying the
  identity and backup return-boundary fixes.
- The user explicitly authorized continuing into G2 small bounded-memory
  materialization.
- Independent Review returned G2 to `REQUEST CHANGES`: existing replay accepted
  non-canonical payload bytes after digest rewrite and ignored unknown manifest
  fields. The scoped remediation now requires exact canonical raw JSONL lines
  and exact canonical manifest bytes reconstructed from the known schema.
- The follow-up independent Review found no blocker or actionable finding and
  approved `G2 APPROVED / GATE PASSED`. G3～G5 remain unauthorized.
- G3 full materialization, PostgreSQL registration/binding, Web integration,
  Local Paper, broker, and real-money work remain outside authorized scope.

## Current repository seams

- `backtest.finmind_history.FinMindHistoryStore` owns the mutable, WAL-backed
  acquisition database and verifies raw plus canonical partition digests.
- `backtest.dataset.HistoricalDatasetCatalog` owns immutable Backtest Dataset
  files and ordered streaming into the existing Backtest Engine.
- `backtest.application.BacktestApplicationService` currently chooses READY
  Datasets independently and prioritizes `research_eligible=true`.
- The selector-less Web projection separately guesses the preferred Dataset,
  so it can disagree with the Dataset ultimately selected by the server.
- PostgreSQL stores Dataset manifests and immutable Runs, but there is no
  durable default Dataset binding.
- Existing Dataset registration uses an upsert shape; the bridge needs an
  immutable compare-and-register path rather than overwrite semantics.
- G1 can remain surgical: add `backtest/finmind_snapshot.py`, one planning CLI,
  and focused tests while reusing the existing SQLite schema and canonical
  partition verification rules from `backtest.finmind_history`.
- The acquisition schema stores jobs, calendar raw evidence, partitions, and
  first/last event boundaries needed by the frozen semantic projection.

## G2 implementation findings

- `HistoricalDatasetCatalog.create_provider_dataset_from_partitions()` already
  streams without loading the full Dataset, but it seals `SYMBOL_TIMESTAMP`,
  uses `datetime.now()` for manifest creation, returns any existing directory
  without integrity comparison, and lacks FinMind plan/amount lineage. Changing
  that legacy method would risk unrelated provider workflows, so G2 needs a
  dedicated timestamp-major immutable sealing entry point on the same catalog.
- `DatasetManifest` already supports `volume_contract`, but not the frozen
  `amount_contract`, source snapshot digest, or canonical plan identity
  projection/digest. G2 must add optional fields so legacy manifest digests stay
  unchanged when those fields are absent.
- The G1 reader currently validates partition payloads during inspection but
  does not yet expose the planned per-symbol bar iterator. G2 must add that
  read-only iterator and reuse the same raw/canonical verification path before
  the k-way merge.
- FinMind normalization already returns canonical `HistoricalBar` values and
  supports explicit `name`/`market`; the G2 iterator can therefore decode each
  included raw partition once, revalidate its canonical digest/count/boundary,
  and enrich it from the frozen reference mapping without another conversion
  pipeline.
- The frozen execute contract requires both physical handoff verification and
  semantic identity recomputation. G2 can call the existing reader against the
  copied snapshot/reference and compare the recomputed `identity` plus digest
  before any Dataset directory is published.
- The implemented replay path compares an existing payload against newly
  streamed source bars, not only against a self-consistent rewritten manifest;
  a payload plus checksum/manifest tamper therefore fails closed.
- The replay path also rejects byte-level JSONL differences such as blank lines
  and rejects unknown manifest keys such as locators, even when an attacker
  rewrites the stored checksums consistently.

## Review-time source observations

The acquisition store is live. Observations are not acceptance constants:

| Observation time | Complete symbols | Complete bars | READY | EMPTY | Global INVALID |
|---|---:|---:|---:|---:|---:|
| Reviewer probe | 159 | 25,030,469 | 115,651 | 73 | 1 |
| Plan-remediation probe | 160 | 25,159,169 | 116,247 | 73 | 1 |
| Second-review observation | 161 | 25,313,015 | not fixed | not fixed | not fixed |

The change during Review confirms that the materializer must first take one
consistent source snapshot and derive all counts from that snapshot.

At G1 implementation start, the live store contains many small jobs sharing the
same source/version/date/calendar/volume contract plus incomplete jobs. This
confirms the reader must merge compatible jobs by semantic contract rather than
require one terminal job or use job status as the selection authority.

## Revised identity decision

`source_snapshot_digest` is computed from the sorted semantic projection of
included inputs, not from SQLite file bytes, acquisition audit timestamps, or
wall-clock execution time.
The projection includes:

- source and source version;
- requested start/end dates;
- calendar canonical digest;
- one required `TaiwanStockInfo` raw-body digest and its mapping-contract
  version;
- the sorted per-symbol `(symbol, selected_date, name, market)` reference
  projection;
- canonical volume and amount contracts;
- every included `(symbol, session_date, status, bar_count,
  canonical_sha256, first_event_at, last_event_at)`;
- all contributing source job IDs for lineage.

`snapshot_identity_at` is the maximum included `last_event_at`, which is
already part of that projection. `DatasetManifest.created_at` is exactly this
value. Partition `created_at` and `updated_at` remain acquisition audit fields
and do not enter Dataset identity. Therefore changing only acquisition timing
cannot change Dataset ID or manifest digest.

If the final Dataset directory already exists, the materializer must verify
the stored source snapshot digest, payload checksum, bar count, ordering, and
manifest digest, then return that manifest unchanged. It must never regenerate
`created_at` or overwrite an existing directory.

## Plan-to-execute handoff

The reviewed full workflow uses a durable handoff rather than two independent
reads of the live acquisition database:

- `--plan --snapshot-out <sqlite> --plan-out <json>` creates one SQLite online
  backup and a canonical plan artifact.
- The plan records plan identity separately from copied-file handoff SHA-256,
  semantic source digest, dynamic counts, and external raw-artifact digests.
- `--execute --plan-file <json>` opens only the copied SQLite file named by the
  plan, verifies both file and semantic digests, and never reopens live
  `history.sqlite3`.
- A missing, changed, or semantically different snapshot fails closed.
- Activation uses the same plan artifact; immutable provenance saves only plan
  identity, while handoff/locator details remain operation audit.

The plan artifact is now split into canonical `identity`, non-identity
`handoff_evidence`, non-authoritative `locators`, and host-specific
`operation_audit`. `plan_identity_digest` hashes only semantic identity.
`copied_sqlite_sha256` belongs only to handoff evidence and proves that execute
opened the exact snapshot approved by that plan invocation. Dataset manifest
stores neither handoff evidence nor paths. A separately planned SQLite rebuild
may have different whole-file bytes but the same semantic/manifest identity;
effective paths and file-byte evidence remain operation audit only.

## G1 implementation shape

- The reader will open copied SQLite files with `mode=ro`; it will not construct
  `FinMindHistoryStore`, because that acquisition adapter creates schema and
  configures WAL.
- Online backup publishes a new snapshot path and refuses to overwrite an
  existing path.
- The live store currently has one valid semantic job family plus a job without
  calendar evidence. G1 will exclude structurally unsupported/missing-calendar
  jobs with reason codes and fail closed if more than one fully formed semantic
  job family exists instead of choosing one silently.
- READY and EMPTY partitions are revalidated from compressed raw response bytes,
  including raw digest, canonical digest, count, session, and event boundaries.
  INVALID/missing/extra sessions exclude the symbol; conflicting duplicate
  identities fail the whole plan.
- `TaiwanStockInfo` mapping uses the frozen latest-date and unique
  `(stock_name,type)` rule directly; no market-value artifact is needed.
- G1 will expose saved-plan integrity and physical handoff verification without
  adding `--execute` or Dataset materialization early.
- Frozen semantic inputs and included partition lineage belong in immutable
  identity. Excluded/incomplete progress belongs in a separately digested
  `selection_audit`; otherwise one Dataset ID can map to different future
  manifest digests.
- The CLI exposes only `--plan`; `--execute` is intentionally absent until the
  materialization gate rather than presenting a verification-only command as a
  completed materializer.
- `identity.counts` is now recalculated solely from included partitions;
  compatible jobs, excluded jobs/symbols, and snapshot-observed selection
  counts live under separately digested `selection_audit` and cannot change the
  Dataset ID or plan identity.
- Backup and plan publication now catch `BaseException` and compare filesystem
  identity before cleanup, so an interruption removes only artifacts published
  by that invocation and never an existing/replacement path.
- The CLI cannot acquire ownership after `backup_source()` returns because that
  leaves one unprotected call/assignment boundary. The token must instead be
  registered by backup publication itself into caller-owned state before the
  protected backup call returns.
- `backup_source()` now invokes a caller-provided ownership callback immediately
  after atomic publication while still inside its `BaseException` cleanup
  region. If callback registration itself is interrupted, backup removes the
  hard-linked destination; if backup returns and a wrapper interrupts, the CLI
  already holds the inode token and removes the unpaired snapshot.

## Reference metadata decision

`TaiwanStockInfo` is required because `name` and `market` are serialized into
the current bar payload. It is identity-affecting, not optional UI decoration.

- CLI requires `--stock-info-raw <TaiwanStockInfo_*.json.gz>` during planning.
- The canonical digest is SHA-256 of the decompressed raw response body; gzip
  container bytes and the filename are not authoritative.
- Per included symbol, use the latest valid-date rows in that exact artifact,
  keep only `type in {twse,tpex}`, require one unique `(stock_name,type)` after
  ignoring duplicate industry-category rows, and map markets to `TWSE`/`TPEX`.
- Missing or ambiguous included symbols fail the whole plan; names are never
  silently replaced by the symbol and markets are never left blank.
- Raw digest, declared Dataset name, mapping contract version, and sorted
  per-symbol mapping enter the semantic source projection. Market-value
  metadata does not affect bar payload and is not independently resolved by
  the bridge.
- This is current descriptive metadata, not point-in-time identity, so the
  Dataset carries `REFERENCE_METADATA_CURRENT_NOT_PIT`.

The checked-in content-addressed raw artifact has only `status`, `msg`, and
`data` envelope keys; it does not self-identify its FinMind Dataset name. The
contract therefore validates the response/row schema and freezes
`reference.dataset=TaiwanStockInfo` in the plan input. A read-only coverage
probe found all 167 symbols currently present in acquisition partitions in the
artifact's valid TWSE/TPEX symbol set; this observation is not a completion
gate and mapping ambiguity still must be checked by the plan reader.
The same raw artifact currently has zero latest-date symbols with more than one
unique `(stock_name,type)` identity under the frozen mapping rule.

The authoritative reference projection is the sorted per-symbol list of
`(symbol, selected_date, normalized_name, normalized_market)`. There is no
single identity-bearing metadata as-of date; min/max dates are derived display
summaries only.

## Dataset ID decision

The ID is `dataset-finmind-sponsor-sha256-` followed by the complete lowercase
64-hex `source_snapshot_digest`. Truncation and collision fallbacks are not
allowed; same ID with different immutable digests is corruption and fails
closed.

## Default binding activation decision

Activation requires caller `expected_binding_revision`, an activation
idempotency key, actor, and change note. Revision `0` means no current binding;
the first mutation creates revision `1`. PostgreSQL serializes the binding name
even before a row exists, rechecks durable operations under that lock, and
applies strict CAS. Stale revision returns 409. Same target with current
revision records a no-op result without incrementing revision. Same-key/same-
digest response-loss retry replays the original result; same key with a
different request digest conflicts.

## Binding TOCTOU decision

The browser submits `expected_binding_revision` and
`expected_dataset_digest` from the server projection. A new Run transaction
must match both or return `409 ATOMIC_BACKTEST_BINDING_CHANGED`; it must never
silently follow a newly switched binding. Same-key/same-request-digest replay
is resolved before current binding lookup and returns the original Run.

## Revised cross-job duplicate decision

The semantic identity is `(symbol, session_date)` across all compatible jobs.

- Equal `canonical_sha256`, status, bar count, and first/last event boundaries:
  emit one canonical partition and retain every contributing job ID in
  lineage.
- Different canonical digest or incompatible metadata: fail the complete
  snapshot. Do not prefer a newer job, completed job, larger payload, or first
  row.
- A partial duplicate cannot make an incomplete symbol complete unless its
  full exact-date set passes the same merged identity checks.

## Revised volume and amount decision

- The new canonical enum token is `COMMON_LOTS`, matching the acquisition
  store's frozen value.
- Existing daily manifests using `COMMON_LOT` remain byte/digest compatible.
  Readers may expose an explicit legacy alias mapping, but old manifests are
  not rewritten and new materialization never emits the singular token.
- FinMind `amount=close*volume` is recorded as
  `DERIVED_CLOSE_X_VOLUME_PROXY`; it is useful for the existing VWAP ratio but
  must not be described as actual turnover.

The MVP explicitly permits `above_vwap_entry` on this exploratory Dataset.
The resulting value is labelled a completed-1m close-volume proxy, not exchange
VWAP. Dataset manifest, immutable Run snapshot, Feature input/evaluation
evidence, and comparability identity retain the exact amount contract and its
digest. Missing or unknown amount semantics fail closed, and Qualification
continues to reject the Dataset because `research_eligible=false`.
This requires a runtime-specific preflight: generic `OHLCV` does not prove a
known VWAP weight source. The Backtest adapter accepts the frozen proxy kind,
labels it explicitly, and rejects missing/unknown kinds before Run creation;
Local Paper retains its separate runtime binding and source semantics.

## Revised operational-control decision

The Engine may continue calling cheap callbacks every 128 bars, but those
callbacks cannot each touch PostgreSQL.

- A monotonic-time `RunControlProbe` caches durable cancellation status and
  polls PostgreSQL no more than once per second by default.
- A progress reporter writes no more than once per second or on a configured
  minimum progress delta, and always writes terminal state.
- Cancellation latency is bounded by the poll interval plus one local event
  checkpoint.
- These operational clocks do not enter the deterministic Run result.

## Migration collision

`backtest/migrations/011_strategy_set_archives.sql` currently exists as
untracked concurrent work. The bridge plan does not allocate or write a new
migration until Phase 0 confirms whether 011 is retained. If retained, the
binding migration is the next available number; if it changes, the bridge uses
the actual current tip rather than a hard-coded filename.
