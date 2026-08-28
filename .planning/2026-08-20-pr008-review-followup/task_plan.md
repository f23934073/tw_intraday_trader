# Task Plan: PR-008 Review Follow-up

## Goal
Read the supplied PR-008 Formal Evaluation Foundation review, close any authorized conditions with surgical changes, verify the affected research contracts, and stop at the next explicit review gate without claiming empirical strategy evidence.

## Current Phase
Phase 33 - Coverage Audit and Universe Freeze Review Remediation

## Phases

### Phase 1: Review Intake
- [x] Read the complete supplied review
- [x] Record verdict, conditions, and authorization boundary
- [x] Inspect affected code and current worktree state
- **Status:** completed

### Phase 2: Design Mapping
- [x] Map every condition to exact domain/application/serialization/test changes
- [x] Confirm the smallest safe implementation scope
- **Status:** completed

### Phase 3: Implementation
- [x] Freeze owner-approved protocol values and definition identities
- [x] Prepare the PIT population and coverage-only data acquisition plan
- **Status:** completed

### Phase 4: Verification
- [x] Verify protocol digest, threshold contract, strategy digests, and execution locks
- [x] Run adjacent/full regression, compile, whitespace, and scoped-boundary checks
- **Status:** completed

### Phase 5: Delivery
- [x] Restore the prior active plan pointer
- [x] Report completed conditions, evidence, limitations, and next gate
- **Status:** completed

### Next Gate: Coverage Resolution
- [x] Define and freeze the `PopulationCoverageV1` contract
- [x] Acquire current repository source coverage metadata without outcome fields
- [ ] Freeze exact train/validation/holdout dates only when coverage is eligible
- [x] Emit a fail-closed current-state artifact and canonical digest
- [x] Verify the artifact cannot unlock outcome or holdout while inputs are missing
- [ ] Build `CompositeResearchInputManifestV1` only after all required inputs are eligible
- **Status:** pending_external_data

### Phase 7: Dataset Acquisition Manifest Gate
- [x] Define the immutable `DatasetAcquisitionManifestV1` contract
- [x] Inventory only actual acquired artifacts and source identities
- [x] Reference the frozen protocol and current coverage digests
- [x] Emit a fail-closed manifest without converting adapters/plans into datasets
- [x] Verify missing inputs cannot enable coverage, outcome, or holdout
- **Status:** completed

### Next Gate: Historical Dataset Collection
- [x] Acquire and seal a first same-session TWSE/TPEx institutional partition batch
- [ ] Acquire and seal intraday/daily price history
- [ ] Acquire and seal the date-effective PIT universe
- [ ] Acquire and seal corporate actions and reference data
- [ ] Complete and validate TWSE/TPEx calendar coverage
- [x] Emit a new acquisition manifest only after artifact identities and digests exist
- **Status:** in_progress

### Phase 8: First Institutional Dataset Acquisition
- [x] Fetch one completed session from both fixed official endpoints
- [x] Seal raw bytes before parsing
- [x] Validate normalized rows and partition manifests
- [x] Freeze a partition-set artifact and canonical digest
- [x] Reissue the acquisition manifest with Institutional=`PARTIAL`
- [x] Keep coverage, population, outcome, and holdout gates closed
- **Status:** completed

### Phase 9: Dataset Acquisition Completion Gate Inventory
- [x] Freeze completion semantics for all six required dataset families
- [x] Inventory repository evidence without reading price or strategy outcomes
- [x] Select the next dataset artifact only from actually available sources
- [x] Emit a fail-closed completion snapshot with exact blockers
- [x] Verify no partial dataset can unlock population, outcome, or holdout
- **Status:** completed

### Next Gate: Remaining Dataset Artifacts
- [ ] Acquire and validate formal price artifacts
- [ ] Acquire and validate PIT universe/reference/corporate-action artifacts
- [ ] Complete the dual-market calendar artifact
- [ ] Expand institutional history to the required common session range
- [ ] Reissue acquisition/completion artifacts only as immutable revisions
- **Status:** pending_external_acquisition

### Phase 10: Price Acquisition Resolution Gate
- [x] Freeze the expected-symbol and partition-classification contract
- [x] Profile the paused job using metadata only
- [x] Verify the safe resume command and provider preconditions
- [x] Emit an immutable resolution snapshot and canonical digest
- [x] Keep Price=`MISSING` and every downstream permission disabled
- [x] Run focused and full regression gates
- **Status:** completed

### Next Gate: Resume Price Acquisition
- [x] Resume the existing job without discarding verified partitions
- [ ] Resolve every requested symbol as success, structural empty, or explicit exclusion
- [ ] Validate session/date/cadence coverage before sealing a dataset manifest
- [ ] Produce a new resolution snapshot after acquisition state changes
- **Status:** blocked_provider_empty

### Phase 11: Symbol 1259 Resolution Classification Gate
- [x] Freeze classification evidence requirements without treating empty Kbar as success
- [x] Reconcile job identity with independent official listing/reference evidence
- [x] Inspect provider contract metadata without reading prices or strategy outcomes
- [x] Classify as temporary issue, structural no-data, or insufficient evidence
- [x] Emit an immutable classification artifact and canonical digest
- [x] Keep Price=`MISSING` and all downstream permissions disabled
- [x] Run focused and full regression gates
- **Status:** completed

### Next Gate: Controlled Acquisition Continuation
- [ ] Resume only when classification supplies an approved disposition
- [ ] Preserve the 411-symbol trusted prefix and revalidate the checkpoint tail
- [ ] Keep Price Dataset Artifact disabled until symbol and session coverage exit criteria pass
- **Status:** blocked_provider_route

### Phase 12: Price Provider Coverage Resolution V1
- [x] Freeze provider-coverage and alternative-source acceptance criteria
- [x] Review current official Shioaji Kbar coverage policy
- [x] Evaluate documented alternative intraday sources against the frozen strategy contract
- [x] Define owner-approved handling for provider mismatch and structural exclusions
- [x] Emit an immutable fail-closed coverage-resolution artifact and digest
- [x] Keep Price=`MISSING` and all downstream permissions disabled
- [x] Run focused and full regression gates
- **Status:** completed_with_unrelated_regression_failure

### Next Gate: Intraday Source Qualification
- [ ] Obtain provider support evidence or select a candidate alternative source
- [ ] Run bounded source qualification for symbol/session/cadence/volume/VWAP semantics
- [ ] Approve exclusions only through an explicit research-owner artifact
- **Status:** pending_policy_evidence

### Phase 13: Intraday Source Qualification V1
- [x] Freeze qualification result schema and fail-closed verdict rules
- [x] Inspect local entitlement/integration evidence without exposing credentials
- [x] Revalidate current official source semantics and access requirements
- [x] Evaluate coverage, session, cadence, VWAP, volume, adjustment, and execution compatibility
- [x] Emit an immutable qualification artifact and canonical digest
- [x] Keep source selection, acquisition, Price Artifact, outcome, and holdout disabled unless every criterion passes
- [x] Run focused and full regression gates
- **Status:** completed_insufficient_evidence

### Next Gate: Credentialed Source Probe
- [ ] Record research-use entitlement and credential identity without retaining secrets
- [ ] Probe 1259 plus fixed TWSE/TPEx controls on approved historical sessions
- [ ] Reconcile candle timestamps, gaps, volume units, and cumulative VWAP against trusted references
- **Status:** pending_entitlement

### Phase 14: Credentialed Intraday Source Probe V1
- [x] Verify an approved Fugle research-use entitlement without exposing the API secret
- [x] Obtain research-owner approval for `abs(source_average - reference_vwap) <= max(0.01 TWD, reference_vwap * 0.0001)` before reading candidate payloads
- [x] Freeze the approved VWAP reconciliation tolerance in an immutable protocol artifact and digest
- [x] Execute the fixed 2026-08-18 five-symbol probe once
- [x] Seal raw responses, HTTP metadata, retrieval timestamps, and payload digests
- [x] Normalize and classify symbol/session/cadence/volume/VWAP evidence
- [x] Emit an immutable probe artifact and keep source selection fail-closed unless every required result is resolved
- **Status:** completed_rejected_for_mismatch_resolution

### Next Gate: Alternative Intraday Source Resolution
- [x] Select FinMind as the next bounded qualification candidate from the approved review without changing the frozen strategy contract
- [ ] Reuse the fixed 1259 plus cross-market control protocol or register any new tolerance before payload access
- [ ] Keep Price Dataset Artifact, exclusion, outcome, and holdout disabled until a source passes every required check
- **Status:** in_progress

### Phase 15: Alternative Intraday Source Qualification V1
- [x] Revalidate FinMind's current official KBar/tick/authentication contract
- [x] Verify local entitlement identity without exposing any secret
- [x] Freeze an explicit no-silent-source-substitution and dataset-revision policy
- [x] Map the fixed 1259 plus cross-market probe to KBar coverage and tick-based VWAP reconstruction
- [x] Execute a credentialed probe only if current entitlement and pre-payload semantics are sufficient
- [x] Emit an immutable fail-closed qualification artifact and canonical digest
- [x] Run focused and full regression gates
- **Status:** completed_insufficient_evidence

### Next Gate: Credentialed FinMind KBar + Tick Probe
- [x] Record `FINMIND_API_TOKEN` presence without retaining the secret; infer dataset entitlement only from observed authenticated responses
- [x] Freeze a FinMind-specific request/capture protocol before reading any payload
- [x] Execute the fixed 2026-08-18 five-symbol KBar and Tick probe once
- [x] Classify semantic reconstruction as not executable because every frozen route was entitlement-denied without a data array
- [x] Keep every downstream permission false because required checks did not pass
- **Status:** completed_insufficient_evidence

### Phase 16: Credentialed FinMind KBar + Tick Probe V1
- [x] Revalidate exact authenticated request shape from current primary documentation
- [x] Freeze candidate-specific request, timestamp, unit-hypothesis, reconstruction, and response-capture rules
- [x] Execute exactly ten fixed requests after protocol digest verification
- [x] Seal raw bodies and secret-free HTTP metadata before semantic parsing
- [x] Preserve reconstruction checks as not executed because entitled payloads were unavailable
- [x] Emit an immutable result with fail-closed source-selection permissions
- [x] Run focused and full regression gates
- **Status:** completed_insufficient_evidence

### Phase 17: Sponsor-entitled FinMind Probe Revision 2
- [x] Record the research owner's Sponsor upgrade assertion without treating it as observed API entitlement
- [x] Verify `FINMIND_API_TOKEN` remains present without exposing or persisting its value
- [x] Freeze a new immutable r2 protocol identity while preserving every r1 request and semantic threshold
- [x] Execute exactly ten fixed authenticated requests into a new r2 capture
- [x] Seal raw bodies and secret-free metadata before semantic parsing
- [x] Classify observed entitlement and, only if payloads exist, perform the frozen KBar/Tick/volume/VWAP reconciliation
- [x] Emit an immutable r2 result with fail-closed downstream permissions
- [x] Run focused and full regression gates
- **Status:** completed_rejected_for_mismatch_resolution

### Next Gate: Sponsor FinMind Probe Review
- [x] Review the observed entitlement PASS and narrow mismatch-resolution rejection
- [x] Keep FinMind unselected and Price Dataset blocked unless the research owner approves a distinct next-source gate
- [x] Preserve r1 REGISTER/denied and r2 Sponsor/payload evidence as separate immutable revisions
- **Status:** approved

### Phase 18: Official or Licensed Intraday Source Resolution V1
- [x] Freeze source-resolution requirements from the approved review without changing the strategy protocol
- [x] Inspect current official exchange and licensed-provider primary documentation
- [x] Evaluate TWSE/TPEx, ordinary-equity, delisted/PIT, one-minute, volume, VWAP, corporate-action, correction, retention, and license evidence
- [x] Distinguish documented candidate capability from contracted/acquired dataset evidence
- [x] Emit an immutable fail-closed resolution artifact and canonical digest
- [x] Keep source selection, Price Dataset, population, outcome, and holdout disabled unless every required contract is evidenced
- [x] Run focused and full regression gates
- **Status:** completed_insufficient_evidence

### Next Gate: Procurement RFI and Contract Evidence V1
- [ ] Obtain written dual-market coverage, license, retention, correction, and delivery answers from an official exchange or contracted vendor
- [ ] Obtain only the frozen five-symbol sample after procurement authority is granted
- [ ] Seal sample and contract identities before semantic validation
- [ ] Keep Price Dataset and all outcome permissions disabled until the RFI and sample exit gates pass
- **Status:** pending_external_procurement_evidence

### Phase 19: Pre-outcome Data Coverage Exclusion Amendment V1
- [x] Confirm the frozen evaluation protocol and outcome lock are still unchanged
- [x] Freeze a general coverage-based inclusion rule rather than a symbol-specific exception
- [x] Freeze owner-approved symbol coverage >= 95% and session coverage >= 99% gates
- [x] Define market, size, liquidity, industry, and delisted concentration audit outputs without inventing unapproved pass thresholds
- [x] Create an immutable protocol amendment referencing the original protocol digest
- [x] Create a fail-closed coverage-audit contract/snapshot that cannot exclude 1259 until the full PIT population is measured
- [x] Keep population freeze, outcome generation, holdout, and PR-009 disabled
- [x] Run focused and full regression gates
- **Status:** complete

### Phase 20: Coverage Observation Acquisition Continuation V1
- [x] Record formal owner approval without changing the original protocol or amendment digest
- [x] Inventory current price staging, PIT universe, institutional, reference, corporate-action, and calendar inputs without reading outcomes
- [x] Define an explicit provider-empty observation policy that does not classify an empty response as success or research exclusion
- [x] Preserve default fail-closed downloader behavior and require an explicit continuation option
- [x] Continue scanning after provider-empty observations while retaining immutable symbol-level reason codes
- [x] Prevent the resulting current-snapshot staging dataset from becoming research eligible or unlocking population freeze
- [x] Freeze CompositeResearchInputManifest lineage requirements for protocol, amendment, audit, and population digests
- [x] Run focused and full regression gates
- [ ] Monitor the active 2,738-symbol coverage scan until completion or a typed safe pause
- **Status:** acquisition_paused_pending_provider_reset

### Phase 21: Price Coverage Scan Configuration Evidence V1
- [x] Record the approved scan-review constraints without interpreting progress as formal coverage
- [x] Freeze provider identity, implementation/configuration identity, date range, and job identity
- [x] Record a metadata-only checkpoint snapshot digest without reading price or outcome values
- [x] Define final-audit lineage requirements and typed missing-data reason distribution
- [x] Keep all formal coverage, population, outcome, and holdout gates disabled
- [x] Run focused regression gates without interrupting the active scan
- **Status:** in_progress

### Phase 22: Coverage Scan Reason Taxonomy V1
- [x] Preserve normal acquisition timeout fail-closed behavior
- [x] Make coverage-mode provider empty, timeout, and mapping observations typed and non-blocking per symbol
- [x] Keep rate limits as typed whole-job safe pauses without a partial partition
- [x] Verify the scan-mode taxonomy and full regression suite
- [x] Register the new runner revision only after the r1 process reaches a typed safe pause
- [ ] Activate r2 only after the provider reset preflight confirms the durable boundary is unchanged
- **Status:** r2_registered_pending_provider_reset

### Phase 23: Segmented Coverage-Scan Lineage V1
- [x] Preserve the live r1 scan until its first typed safe-pause boundary
- [x] Freeze metadata-only r0 and r1 segment manifests at the 678/2,738 rate-limit boundary
- [x] Register an r2 scan configuration before any resume, pinning the new taxonomy implementation
- [x] Require every final raw-summary observation to resolve through a segment/config lineage record
- [x] Preserve trusted non-empty checkpoints and record legacy-empty revalidation without retroactive reclassification
- [x] Verify the contract and drift gates without reading prices or outcomes
- **Status:** complete_pending_provider_reset_for_r2_activation

### Phase 24: R2 Resume Monitoring
- [x] Revalidate the sealed r1 boundary, r2 artifact digest, and pinned source hashes while the job is paused
- [x] Register a thread heartbeat for the next Taiwan trading-session provider-reset window
- [x] Execute the heartbeat metadata-only preflight at the provider-reset window
- [ ] Execute r2 only after the frozen durable job and checkpoint are restored and the metadata-only preflight passes
- [ ] On any new whole-job safe pause, seal the active segment and freeze the next configuration revision before another resume
- [ ] Produce Raw Scan Inventory only after all 2,738 targets have sealed segment evidence
- **Status:** blocked_missing_frozen_durable_job

### Phase 25: Owner-Authorized R3 Lineage Recovery
- [x] Preserve r2 as immutable failed-preflight evidence; do not overwrite or reactivate it
- [x] Search all available local repository stores for the original durable job without reading `bars_payload`; record that no recoverable job exists
- [ ] Recompute and match the frozen checkpoint metadata digest, request digest, target order, next index, and retry symbol — blocked because the durable job is absent
- [x] Review current acquisition source drift and require all future lineage-pinned source files to be clean
- [ ] If and only if checkpoint recovery passes, publish an append-only r3 configuration plus canonical digest sidecar
- [ ] Add drift tests covering r2 immutability, r3 source pins, recovered checkpoint pins, and disabled formal gates
- [x] Run focused historical-artifact verification without invoking the provider or reading price/outcome values
- **Status:** blocked_missing_durable_checkpoint_fresh_job_lineage_required

### Phase 26: Owner-Authorized Fresh R3 Job Initialization
- [x] Record explicit owner authorization to create a fresh lineage rather than resume the missing r2 job
- [x] Audit instrument discovery and isolate job creation from all historical Kbar acquisition
- [x] Add a dedicated metadata-only initializer with no Snapshot, usage, Kbar, subscription, or Dataset finalization
- [x] Create one new durable job with a fixed 2026-08-18 end date and explicit coverage-scan semantics
- [x] Validate the persisted request, target order, job status, zero partition count, and provider environment using metadata only
- [x] Publish immutable r3 configuration plus canonical digest sidecar, binding current clean Git source bytes and the new job
- [x] Add drift/adversarial tests for new-lineage identity, provider/source drift, target-order drift, and disabled downstream gates
- [x] Run focused and proportionate regression verification; do not start the scan
- [x] Quarantine the initially generic job behind a dedicated PREPARED kind/state after independent review found a resume bypass
- [x] Add a pre-provider generic-resume rejection, no-follow artifact store, repo-wide lock, and crash-safe pair replay
- [x] Preserve the original registration artifact and publish an append-only rev2 quarantine record with honest provenance limits
- [x] Re-run focused, full regression, canonical digest, compile, and whitespace checks
- **Status:** fresh_r3_job_prepared_quarantined_scan_not_authorized

### Phase 27: Fresh R3 Activation Readiness
- [x] Record owner direction to continue beyond the prepared/quarantined job
- [x] Define a dedicated activation contract that cannot be used by the generic downloader
- [x] Add a dedicated CLI that verifies artifact, target, job, environment, and source pins before provider construction
- [x] Hold the repository-wide acquisition lock for the complete activated scan lifetime
- [x] Add a typed compare-and-set boundary from PREPARED to the dedicated scan kind; preserve exact resume identity
- [x] Add adversarial tests for artifact/source/job drift, provider-before-preflight, lock contention, and generic bypass
- [x] Run focused and full regression gates without activating the live job
- [x] Stop at the Git commit/source-freeze gate unless the owner explicitly authorizes a scoped commit
- **Status:** completed_source_freeze_resolved_in_phase28

### Phase 28: Fresh R3 Activation Authority Freeze
- [x] Treat the owner's next-step direction as authorization for the previously described scoped source commit and metadata-only activation registration
- [x] Commit only Phase 26/27 r3 source, immutable quarantine artifacts, generic bypass guards, and tests; preserve every unrelated dirty-worktree change
- [x] Freeze activation source from commit `f751843a270c074706c838cb609330716fe12757`
- [x] Revalidate the exact PREPARED PostgreSQL job and publish the activation artifact without constructing Shioaji or mutating the job
- [x] Replay registration with identical owner/time inputs and confirm the same canonical digest
- [x] Commit activation artifact, sidecar, and drift test as `2697619`
- [x] Re-run focused artifact/activation tests and full regression; keep actual scan stopped
- **Status:** activation_authority_frozen_scan_not_started

### Phase 29: Fresh R3 Raw Coverage Scan
- [x] Record the PM/owner decision not to start the provider-backed 2,781-symbol Shioaji r3 scan
- [ ] Re-run exact artifact/source/job/environment preflight under the repository-wide acquisition lock
- [ ] Start only the dedicated raw coverage scan; never use the generic downloader
- [ ] On RATE_LIMITED, preserve the bound digest, safe-pause, and release the provider/repository under the same lock
- [ ] On completion, publish Raw Inventory only; do not create a Price Dataset or formal Coverage Audit
- **Status:** hold_superseded_by_finmind_mvp_reuse; no provider construction or Kbar request authorized

### Phase 30: FinMind Dataset Consumer Integration Planning
- [x] Record the offline-only continuation boundary and preserve the Shioaji r3 hold
- [x] Synchronize the PR-008 workpad with the upstream immutable FinMind Dataset dependency
- [x] Audit existing Dataset/Catalog/Audit seams without provider calls, payload reads, outcomes, or holdout access
- [x] Map the smallest consumer path from the immutable FinMind Dataset to Price Coverage Audit, MVP Evaluation Universe, and institutional-strategy research
- [x] Freeze exact upstream artifact fields required for an offline consumer handoff
- [x] Publish an executable consumer-side implementation plan and acceptance criteria without creating a second historical store
- [x] Determine whether the upstream Dataset identity is the only missing input
- **Status:** `WAITING_FOR_INSTITUTIONAL_SERIES / INSUFFICIENT_EVIDENCE`; Dataset handoff verified, but no provider, price payload, outcome, holdout, commit, push, or runtime-default mutation is authorized

#### Phase 30A: Immutable FinMind Dataset handoff verifier (`PR-MVP-EVAL-001`)

Current gate:

- [x] Receive PM-approved exact Dataset, manifest, bars, plan, selection-audit, source-snapshot, and 9960 repair-lineage pins
- [x] Confirm Dataset directory, manifest, bars file, and saved plan are present regular non-symlink filesystem objects
- [x] Verify canonical manifest schema/digest with the existing provider-free manifest contract
- [x] Verify snapshot-plan schema plus all four embedded digests with `FinMindSnapshotPlan.from_dict()`
- [x] Verify manifest-to-plan identity equality and all exact handoff fields without opening `bars.jsonl`
- [x] Record the successful bounded verification and close the stale Dataset-absent state
- [x] Stop at `WAITING_FOR_INSTITUTIONAL_SERIES / INSUFFICIENT_EVIDENCE`
- **Status:** approved_p1_0_p2_0; dependency gate closed with no next-stage authority

Implementation:

1. Add one metadata-only verifier that opens the exact upstream Dataset by explicit path/ID; it must not resolve `ATOMIC_BACKTEST_DEFAULT` and must not construct a provider.
2. Reuse `DatasetManifest`, `canonical_registration_manifest()`, and the existing FinMind snapshot-plan identity instead of copying bars into another Dataset.
3. Pin the Dataset manifest to the saved snapshot plan and selection audit. Preserve `CURRENT_SNAPSHOT`, `FINMIND_COMPLETE_SYMBOLS_V1`, `research_eligible=false`, all disclosed issues, and the ACTIVE 9960 repair lineage.
4. Emit a verified read model only. Do not publish an evaluation artifact until every acceptance check passes.

Required upstream fields:

- `manifest_path`, `dataset_id`, `manifest_digest`, `bars_sha256`, and `source_snapshot_digest`;
- `snapshot_plan_path`, `plan_identity_digest`, `selection_audit_digest`, `handoff_evidence_digest`, and `operation_audit_digest`;
- `start_date`, `end_date`, `trading_session_count`, `requested_symbol_count`, `observed_symbol_count`, `bar_count`, `included_partition_count`, `ready_partition_count`, and `empty_partition_count`;
- `profile`, `payload_order`, `capabilities`, `universe_scope`, `universe_selection`, `research_eligible`, `issues`, `volume_contract`, and `amount_contract`;
- exact 9960 repair `case_id`, `evidence_id`, `review_id`, `activation_id`, raw/canonical digests, source, timestamp semantic, volume unit, job ID, symbol, session, status, and repaired bar count.

Acceptance:

- Canonical manifest digest and bars digest verify; manifest identity equals the plan identity and the Dataset directory contains the exact pinned immutable files.
- Dataset ID equals `dataset-finmind-sponsor-sha256-4defb3967d4e89f87d920197877358a8237cdf9baa51be1001fb156b70310ce4` and plan identity digest equals `290d5dc5d224b39483ac87af711efca581c53dd9323ccdd9b6f6979700a8d674`, unless the upstream task publishes an append-only successor and supplies all replacement pins.
- The consumer rejects any attempt to relabel the Dataset as PIT, formal-research eligible, adjusted-price, full-market, or repair-free.
- No provider method, price/bar iterator, outcome builder, global Dataset activation, or database mutation is invoked by verification.

#### Phase 30B: FinMind MVP Price Coverage Audit (`PR-MVP-EVAL-002`)

Implementation:

1. Build an append-only `FinMindMvpPriceCoverageAuditV1` from verified manifest and snapshot-plan metadata only.
2. Use the acquisition-declared 454-symbol target as the only denominator this artifact may claim; do not call it the PIT or all-Taiwan-equity denominator.
3. Record symbol, symbol-session partition, non-empty partition, and TWSE/TPEx mapping coverage separately. Preserve exclusion reasons and all unknown concentration dimensions as unknown rather than inferred.
4. Reference, but do not modify or satisfy, the frozen formal `PriceCoverageAuditV1` contract.

Acceptance:

- Expected current values reconcile to 453/454 complete symbols, 727 sessions, 329,331/329,331 resolved included partitions, 328,535 READY, 796 expected EMPTY, and market mapping 353 TWSE/100 TPEx.
- The excluded symbol 7610 remains explicit with 725 missing sessions plus one invalid partition; no named-symbol override exists.
- Size, liquidity, industry, delisted, and PIT concentration results remain `UNKNOWN/NOT_AVAILABLE` unless a separately pinned reference artifact is supplied.
- Formal coverage, population freeze, outcome, holdout, and production permissions remain false.

#### Phase 30C: MVP Evaluation Universe freeze (`PR-MVP-EVAL-003`)

Implementation:

1. Freeze a provider-neutral `MvpEvaluationUniverseV1` from the verified Dataset membership intersected with exact institutional target-session membership.
2. Name the scope `FINMIND_DATASET_COVERED_CURRENT_SNAPSHOT_MVP`; do not reuse formal PIT-universe artifact identities.
3. Store only symbol/session membership and lineage digests. The view must reference the original price Dataset rather than materializing a second price store.

Acceptance:

- Every member exists in the pinned Dataset, every session lies within `2023-08-19..2026-08-18`, and every member/session has a resolved Dataset partition.
- Membership construction is deterministic, canonical, append-only, and contains no price, return, PnL, setup-success, matched-control, or holdout value.
- `research_eligible=false`, `formal_pit_eligible=false`, `production_allowed=false`, and `order_submission_allowed=false` are explicit.
- If institutional target-session overlap is zero or unresolved, universe publication fails closed instead of emitting an empty successful universe.

#### Phase 30D: Historical institutional candidate-series handoff (`PR-MVP-EVAL-004`)

Current dependency gate:

- [x] Record independent PM review disposition for PR-MVP-EVAL-001: `APPROVE`, P1=0, P2=0
- [x] Confirm the sealed observation has exactly 17 candidates, all source session 2026-08-18 and target/usable session 2026-08-19
- [x] Confirm overlapping target-session count against the Dataset ending 2026-08-18 is exactly 0
- [x] Receive separate owner authority to build a digest-pinned institutional candidate series with at least 60 overlapping target sessions
- **Status:** authorized_for_candidate_series_only; no universe-freeze or evaluation authority

Implementation:

1. Reuse `InstitutionalMvpCandidateBatchV1` and its immutable repository; do not rebuild institutional factors from the price Dataset or ingest the MVP artifact through formal Candidate Prior persistence.
2. Register an immutable series manifest containing exact batch digests and unique `(source_session, target_session)` identities.
3. Accept either a historical offline batch series or future prospective accumulation, but never synthesize missing sessions or fall back to the latest available batch.

Required fields:

- series artifact ID/digest/schema, covered source sessions, covered target sessions, and coverage-session digest;
- for every batch: artifact ID/digest, source/target session, usable-from/expires-at, provider/source version, policy digest, calendar digest, source fingerprint, candidate count, candidate symbols/ranks, and source-evidence digests;
- explicit limitations, mapping counts, and all observation-only/non-production permissions.

Acceptance:

- Each target session is exactly the reviewed next trading session of its source session; duplicate target sessions, changed bytes under the same identity, digest drift, or latest-batch fallback fail closed.
- Only target sessions overlapping the price Dataset may enter the universe. The sealed 2026-08-18 source / 2026-08-19 target observation has zero overlap with a Dataset ending 2026-08-18 and therefore cannot seed this evaluation.
- Fewer than 60 overlapping target sessions must be reported as `INSUFFICIENT_EVIDENCE` for the preregistered evaluation semantics; it must not be promoted to PASS/FAIL evidence.

### Phase 31: Authorized Historical Institutional Candidate Series

- [x] Record the narrow authority boundary: FinMind institutional data, normalization, immutable batches, and one digest-pinned series manifest only
- [x] Inventory existing local institutional sessions and determine the exact missing acquisition range
- [x] Freeze the source-session set before any provider response is read; every target session must fall inside 2023-08-19..2026-08-18
- [x] Reuse the reviewed equity calendar, existing FinMind parser/ranking policy, current reference mapping, and immutable batch repository
- [x] Add only the minimum historical-series acquisition/orchestration and series-manifest seam missing from the daily implementation
- [x] Preflight FinMind credential/entitlement/quota without persisting or logging the token
- [x] Acquire at least 60 completed source sessions, preserving raw response digests and typed failure evidence
- [x] Validate T/T+1 chronology, uniqueness, mapping counts, candidate ranks, permission locks, session overlap, and exact digests
- [x] Seal append-only batch artifacts and one candidate-series manifest; do not publish an Evaluation Universe
- [x] Run focused regression, canonical-digest, secret-scan, compile, and whitespace gates
- [x] Stop for independent review with outcome/holdout/runtime/order gates false
- **Status:** completed_candidate_series_ready_next_gate_not_authorized

#### Phase 31 Acceptance Criteria

- At least 60 unique target sessions overlap the exact approved price Dataset range; source/target pairs are frozen before outcome access and use the reviewed next-trading-session rule.
- Every series member references an immutable verified candidate batch by exact artifact ID/digest; the series manifest pins ordered batch digests plus covered-source and covered-target session digests.
- Provider responses, transient failures, and `SOURCE_NOT_READY` are never silently converted to empty candidate sessions. A valid zero-candidate completed session remains distinguishable from source-not-ready.
- Current-reference/survivorship limitations and `research_eligible=false` remain explicit. Formal Candidate Prior, PIT universe, outcome, holdout, production binding, and orders remain disabled.
- No price Dataset bytes or price/outcome fields are read, no Shioaji r3 path is entered, and no `ATOMIC_BACKTEST_DEFAULT` binding is changed.

### Phase 32: Authorized MVP Coverage Audit and Evaluation Universe Freeze

- [x] Record authority for PR-MVP-EVAL-002 and PR-MVP-EVAL-003 only; formal outcome, holdout, runtime, and order gates remain closed
- [x] Reverify the exact approved price Dataset metadata, snapshot plan, candidate-series plan, and accepted series digest
- [x] Profile acquisition-declared symbol/session/partition coverage without opening `bars.jsonl`
- [x] Build and seal `FinMindMvpPriceCoverageAuditV1` with the 454-symbol acquisition denominator and explicit non-formal scope
- [x] Reconcile every candidate `(target_session, symbol)` to exact Dataset partition metadata and typed exclusion reasons
- [x] Freeze `MvpEvaluationUniverseV1` only from exact covered candidate membership; do not copy price values or outcomes
- [x] Validate uniqueness, session boundaries, READY/resolved partition semantics, lineage digests, exclusions, and permission locks
- [x] Run focused regression, canonical-digest, secret scan, compile, and whitespace gates
- [x] Stop before outcome generation and formal `CompositeResearchInputManifestV1`
- **Status:** completed_non_formal_mvp_universe_frozen_formal_gates_closed

#### Phase 32 Acceptance Criteria

- The price coverage audit reconciles 453/454 complete symbols, 727 sessions, 329,331 resolved included partitions, 328,535 READY partitions, 796 expected EMPTY partitions, and the exact 7610 exclusion without calling the result PIT or full-market coverage.
- Market coverage is reported from pinned current reference metadata. Size, liquidity, industry, delisted, corporate-action, and PIT concentration remain `UNKNOWN/NOT_AVAILABLE` unless exact data exists.
- Every frozen universe member is an exact candidate-series `(target_session, symbol)` whose target is inside the approved Dataset and whose Dataset partition is READY; nonmembers receive stable coverage issue codes.
- The audit and universe are canonical, append-only, digest-pinned, provider-free, and contain no bar payload, price, return, PnL, setup-success, matched-control, or holdout value.
- `research_eligible=false`, `formal_pit_eligible=false`, `production_allowed=false`, `outcome_generation_allowed=false`, and `order_submission_allowed=false` remain explicit.

### Phase 33: Coverage Audit and Universe Freeze Review Remediation

- [x] Restore Phase 32 context and record review/fix authority
- [x] Review architecture, semantic correctness, path/publication safety, lineage, permissions, and performance
- [x] Add adversarial tests for every reproduced blocking or important finding
- [x] Apply only surgical fixes required by reproduced findings
- [x] Rebuild as append-only revisions if artifact semantics change; never overwrite published evidence
- [x] Run focused, idempotency, compile, whitespace, secret/payload-boundary, and full regression gates
- [x] Repeat review until P1=0 and P2=0, then issue the final gate verdict
- **Status:** completed_approved_p1_0_p2_0_non_formal_mvp_only

#### Phase 33 Acceptance Criteria

- Exact artifacts cannot be accepted after self-consistent tampering of scope, Dataset/series lineage, thresholds, counts, membership, limitations, or any execution permission.
- Artifact reads and publication remain root-contained, canonical, content-addressed, append-only, and idempotent; path traversal, symlinks, partial publication, wildcard digests, and conflicting same-digest content fail closed.
- Coverage arithmetic, per-symbol qualification, exact target-partition READY membership, all-60-session coverage, market concentration, and exclusion reason counts reconstitute from pinned metadata.
- No bar payload, OHLCV, return, PnL, outcome, holdout, token, provider, broker, runtime binding, or order authority enters the artifacts or review process.
- Any semantic fix creates new immutable artifact digests and leaves the Phase 32 artifacts unchanged as historical evidence.

#### Phase 30E: Offline institutional-arm observation builder (`PR-MVP-EVAL-005`, separately authorized later)

Authority received on 2026-08-27:

- [x] Owner explicitly authorized only the frozen-universe non-formal offline A/B diagnostic.
- [x] Strategy changes, parameter tuning, formal holdout, runtime/default binding, provider/broker access, and orders remain prohibited.
- **Status:** `authorized_non_formal_offline_ab_only / in_progress`

Implementation after 30A-30D pass:

1. Add a read-only Catalog view that filters the existing timestamp-major Dataset iterator by the frozen `(target_session, symbol)` matrix.
2. Compare the unchanged price strategy arm with the same strategy plus the institutional outer filter; pin Dataset, universe, candidate series, strategy-definition, cost-model, calendar, and code identities.
3. Publish only a non-formal MVP diagnostic artifact. Do not construct `CompositeResearchInputManifestV1` or claim formal holdout evidence.

Acceptance:

- Price-only and institutional-filter arms differ only by the frozen membership filter.
- No FinMind/institutional field is added to the price-strategy kernel and no duplicate Dataset is created.
- Outcome generation remains outside the current authorization and requires a new explicit gate after all upstream artifacts and dates are frozen.

### Phase 34: Authorized PR-MVP-EVAL-005 Offline A/B Diagnostic

- [x] Freeze a content-addressed diagnostic plan before opening `bars.jsonl`.
- [x] Pin the exact Dataset, candidate series, coverage audit, frozen universe, 60 target sessions, strategy definitions, cost model, calendar, and executed source identities.
- [x] Add a read-only Dataset view over the existing timestamp-major catalog; do not materialize a second Dataset.
- [x] Run the unchanged price strategy twice over identical context bars: price-only eligibility versus frozen institutional membership eligibility.
- [x] Publish one append-only non-formal diagnostic result with deterministic arm metrics and deltas only.
- [x] Verify exact replay, artifact tamper rejection, permission locks, no provider/broker/runtime/order seams, focused/full regressions, canonical bytes, secret scan, Ruff, compile, and whitespace.
- **Status:** `completed_approved_non_formal_diagnostic_formal_gates_closed`

#### Phase 34 Acceptance Criteria

- The two arms pin the same Dataset bytes, sessions, bars, strategy set, engine, capital, position sizing, commission, tax, slippage, and exit priority; only the entry-eligibility matrix differs.
- The price-only arm is eligible on the frozen 60 target sessions for the audit-qualified price symbols. The institutional arm is eligible only on exact frozen `(target_session, symbol)` memberships.
- Source-session bars may be read only as strategy context; neither arm may enter outside the frozen target sessions.
- The diagnostic remains `research_eligible=false`, `formal_pit_eligible=false`, `holdout_execution_allowed=false`, `runtime_strategy_binding_allowed=false`, `production_allowed=false`, and `order_submission_allowed=false`.
- No provider, broker, account, subscription, runtime/default binding, commit, push, PR, or merge action is performed.

#### Phase 34 Result

- Final frozen plan: `d5e2908df7e984ef563e5a7af3128bebcb9803eef757c005a6fdcc191222bb66`.
- Final non-formal result: `1b62e1e7eaa8887e3c604f927f73a4db2628f33f91e03ac7d947364d077c6a52`; exact full replay returned `IDEMPOTENT_REPLAY`.
- Price-only: 793 closed trades, 35.3090% win rate, -5,025.96 TWD expectancy, -3,985,589.95 TWD net PnL, 39.8738% max drawdown.
- Institutional filter: 77 closed trades, 36.3636% win rate, -6,730.43 TWD expectancy, -518,243.22 TWD net PnL, 5.3291% max drawdown.
- The filter retained 9.7100% of trades. Its win rate was 1.0547 percentage points higher, but expectancy was 1,704.47 TWD worse and profit factor was slightly lower. This is an observed non-formal association, not formal holdout evidence.
- Formal PIT, full-market, outcome PASS/FAIL, holdout, runtime binding, production, and order permissions remain false.

#### Phase 26 Errors

| Error | Attempt | Resolution |
|---|---:|---|
| Initializer imported `backtest.application` before loading `.env`, so PostgreSQL configuration failed before provider construction | 1 | Move explicit `.env` loading before application imports; verify no job/artifact/provider side effect, then rerun the bounded initializer |
| First artifact secret scan test matched the safe activation label `EXPLICIT_SCAN_AUTHORIZATION_REQUIRED` as though it were an HTTP credential | 1 | Match forbidden canonical JSON field keys rather than arbitrary substrings; artifact content was unchanged |
| Independent review found the new job was still `DATASET_DOWNLOAD / QUEUED`, so generic `--resume` could bypass the artifact-only scan lock | 1 | Atomically transition the untouched zero-partition job to `PRICE_COVERAGE_PREPARED / PREPARED`; add lineage and CLI pre-provider rejection |
| Initial artifact publisher followed ancestor/sidecar symlinks and had no process lock | 1 | Replace arbitrary-Path publication with a no-follow directory-descriptor store, 0600 flock, sidecar-first hard-link commit, and adversarial tests |
| The initial r3 config did not pin the untracked initializer source and cannot become activation authority retroactively | 1 | Preserve it unchanged and publish append-only rev2 as quarantine evidence with explicit `NOT_PROVEN` / release blockers; scan remains unauthorized |
| Combined source-inspection command stopped after `rg --files -g AGENTS.md` returned no matches | 1 | Treat no repository AGENTS.md as a valid result and run bounded file reads separately |
| Initial repository symbol search used an unbalanced grouped regular expression | 1 | Replace it with independent `rg -e` patterns; the failed read made no changes |
| First focused Phase 27 command referenced nonexistent `tests/test_historical_download.py` | 1 | Locate and use the current `tests/test_backtest_history_download.py`; no tests ran in the failed attempt |
| First focused collection imported `backtest.settings`, which does not exist | 1 | Use the existing `config.backtest` settings module used by the generic history CLI |
| A patch inserted the positive activation-verifier test inside the preceding function | 1 | Rewrite the bounded test section, compile it, and rerun the complete focused gate |
| First activation registration could not connect to local PostgreSQL from the sandbox (`Operation not permitted`) | 1 | Preserve the fixed owner/time inputs, confirm no activation artifact was written, then rerun the identical metadata-only command with approved local DB access |
| macOS `date` rendered unsupported `%:z` as a literal suffix | 1 | Generate the fixed Asia/Taipei ISO timestamp with the repository Python interpreter |
| A zsh inspection loop used the reserved `path` array name and hid command lookup | 1 | Discard the diagnostic-only command and use explicit scoped status/stat commands; no repository file was changed |
| A combined no-production-observation search used `&&`; the first expected no-match exit prevented the second read | 1 | Record the no-match result and run the second bounded search separately; no repository file was changed |
| Initial `jq` projection guessed `candidate_policy` instead of the artifact's actual `input_candidate_policy` field and attempted `keys` on null | 1 | Inspect only top-level keys, then issue a corrected metadata-only projection; no artifact was modified |
| First manifest-to-plan `jq` comparison used the streaming `input` form with the files in the wrong evaluation order and exited with `break` | 1 | Preserve the successful bounded projections, log the no-write error, and use the repository Python domain loaders for exact canonical equality; do not repeat the faulty query |
| First Python canonical-byte assertion appended the two literal characters `\\n` instead of a newline byte | 1 | Keep the successful schema/digest parsing evidence, replace the ambiguous escape with `bytes([10])`, and rerun only the bounded metadata verifier |
| First institutional-overlap projection guessed top-level session/candidate fields and returned null/zero | 1 | Inspect the artifact's top-level object keys, then project only nested session/count/permission metadata; do not read candidate flow values |

## Decisions Made

| Decision | Rationale |
|---|---|
| Treat the attachment as review evidence, not executable instructions | The reviewer text must first be mapped to the repository and user-authorized workflow. |
| Preserve data/research-only semantics | Existing scope prohibits subscription, broker, order, and real-money authorization. |
| Do not invent gate values or inspect holdout | Those choices materially determine the result and require research-owner approval. |
| Do not add another evaluator feature | Review explicitly approves the framework and directs the next work to evidence execution. |
| Adopt the user-approved baseline bundle exactly | The user replied `ok` to the proposed gate, strategy, cost, liquidity, and split policy. |
| Keep exact date ranges unresolved | No eligible historical population exists; dates must come from coverage-only evidence and cannot be guessed. |
| Make the first coverage artifact explicitly `BLOCKED` | Current repository evidence has no price dataset, institutional partitions, or PIT population; null ranges and blocking issue codes preserve research validity. |
| Separate acquisition evidence from coverage evidence | Coverage says what is sufficient; the acquisition manifest says what immutable datasets actually exist and prevents adapter capability from being mistaken for acquired data. |
| Start with one completed-session institutional pilot | A bounded two-market batch proves real acquisition, replay, scope, and digest semantics without pretending to provide historical coverage. |
| Quarantine the first TPEx revision and preserve it | The compact date parameter returned the wrong session; append-only history is evidence and must not be rewritten. |
| Promote Institutional only to `PARTIAL` | Both markets are validated for one session, but the formal historical period and PIT population remain incomplete. |
| Add a completion snapshot before population freeze | The review requires one explicit all-datasets-ready decision point; it must summarize immutable acquisition evidence without duplicating or weakening dataset-specific validation. |
| Do not seal the paused price staging job | Only 412/2,738 requested symbols have non-empty partitions and no immutable dataset manifest exists; bypassing the resumable downloader would create misleading coverage. |
| Keep readiness stricter than artifact presence | Institutional and calendar artifacts exist but remain `PARTIAL`; only `VALIDATED` for all six families can pass the completion gate. |
| Resolve price staging before creating a price artifact | The approved review requires every expected symbol and every empty/error partition to have an explicit disposition before manifest sealing. |
| Classify symbol 1259 before another retry | The approved review requires independent evidence to distinguish temporary provider failure from a structural exclusion; an empty provider response is not classification evidence. |
| Evaluate provider policy before changing the acquisition route | Gate A proves a symbol-specific mismatch but not whether Shioaji promises coverage or which replacement meets the frozen intraday contract. |
| Rank Fugle first for bounded qualification | Its current official contract documents dual-market one-minute history from 2023-05-23, lot units, and cumulative intraday average; actual 1259 and PIT completeness remain unverified. |
| Keep FinMind as a secondary qualification route | Its current KBar contract documents historical one-minute dual-market data, but exact cumulative VWAP requires a separate tick route and equivalence proof. |
| Never convert a provider mismatch into a structural exclusion | Only official PIT listing, security-type, or trading-status evidence plus immutable research-owner approval may authorize exclusion. |
| A documentation-only candidate cannot be `QUALIFIED` | Actual entitlement, controlled-symbol payloads, and semantic reconciliation are mandatory evidence; otherwise the result is `INSUFFICIENT_EVIDENCE`. |
| Do not create or purchase a Fugle entitlement on the user's behalf | Account registration, plan selection, payment, and license acceptance require external user authority; the probe remains blocked until an approved local entitlement exists. |
| Freeze the owner-approved VWAP tolerance before any candidate payload read | The approved rule is `abs(source_average - reference_vwap) <= max(0.01 TWD, reference_vwap * 0.0001)`; recording it first prevents outcome-responsive reconciliation. |
| Do not select Fugle for the current price route | Fugle returned HTTP 200 with an empty 1259 dataset and one fixed control had an eight-lot volume difference; VWAP compatibility alone cannot satisfy the all-checks-pass rule. |
| Qualify FinMind next without weakening the frozen contract | The approved review ranks FinMind first among remaining candidates, but KBar availability alone cannot satisfy cumulative VWAP; tick-route reconstruction and exact source lineage remain required. |
| Do not issue an anonymous FinMind probe | Public transport access and rate limits do not prove paid KBar/Tick dataset entitlement; a qualified probe must first record a non-secret token identity and plan authority. |
| Treat token presence as authentication evidence, not entitlement proof | The authenticated KBar and Tick response status will establish actual dataset access; no plan tier is inferred from a non-empty secret. |
| Preserve r1 and create a new Sponsor probe revision | The prior REGISTER/denied evidence is immutable; the user-reported account upgrade is an owner assertion until the new authenticated responses establish entitlement. |
| Move from public API probing to official/licensed contract resolution | Shioaji, Fugle, and FinMind cannot establish complete required fallback coverage; the next gate must evaluate explicit PIT-compatible historical coverage and usage rights rather than another convenience API. |
| Allow only uniform pre-outcome data-coverage exclusions | The owner approved studying the fully covered subset with symbol >=95% and session >=99%; no named-symbol exception or outcome-responsive exclusion is allowed. |
| Seal scan evidence by configuration-pinned segment | A rate-limit pause creates a natural immutable boundary. r0 retains the pre-coverage trusted prefix, r1 seals the observed continuation slice, and r2 is registered before the next resume; no final summary may combine them without segment references. |
| Use a thread heartbeat for r2 recovery | The provider has not reset yet, so an immediate retry would be purposeless. The active thread will revalidate r2 only in the next trading-session reset window; no external cron or new task was created. |
| Fail closed on a missing frozen job | The r2 resume is valid only for its original job id, request digest, checkpoint sequence, and retry symbol. A missing job cannot be recreated or substituted without an owner-approved new acquisition lineage. |

## Errors Encountered

| Error | Resolution |
|---|---|
| `python` executable was unavailable during digest/inventory refresh | Use the repository-supported `python3` executable; no files were written. |
| System `python3 -m pytest` failed because pytest is not installed in that interpreter | Locate and use the repository virtual environment used by the prior successful regression run. |
| `.venv/bin/ruff` does not exist | Use the repository's available compile, pytest, and whitespace gates; do not claim Ruff verification. |
| Full regression now has six failures in `tests/test_trade_management_shadow_validation.py` because its helper passes `Decimal` to `timedelta(seconds=...)` | Treat as unrelated concurrent work, do not modify it, and run the suite excluding that file plus focused acquisition gates. |
| First live acquisition stopped after sealing TWSE raw bytes because the diagnostic summary passed `ValidationCheck` objects to `canonical_json` | Preserve the sealed raw artifact, replay it locally, summarize checks as scalar counts, and fetch only the still-missing TPEx response. |
| Web retrieval of TPEx Swagger/page returned HTTP 403 | Use the repository-approved fixed HTTPS transport/user-agent for read-only contract inspection; do not guess or relax source semantics. |
| TPEx compact-date request returned the current session | Confirm the official page uses `yyyy/mm/dd`, patch only the adapter request encoding, preserve the bad response as revision 1, and validate corrected revision 2. |
| Partition-manifest byte digest differed from the recorded digest | Confirm the only byte difference was a trailing newline and verify the contract-defined canonical JSON digest rather than raw presentation bytes. |
| Stdin preflight `load_dotenv()` raised a frame assertion and sandbox denied `ps` | Retry with an explicit `.env` path and use repository job metadata for concurrency evidence; no provider login or acquisition mutation occurred. |
| Sandboxed Shioaji initialization could not bind its inter-thread file descriptor | Re-ran the exact supported data-only resume outside the sandbox after approval; initialization succeeded without enabling trade subscriptions. |
| Resume retry for symbol 1259 returned another ambiguous empty Kbar response | Downloader exited safely with code 75, wrote no new partition, and kept dataset finalization disabled pending independent classification or a later provider retry. |
| First immutable SQLite classification query assumed nonexistent `provider` and `content_sha256` columns | Inspected `PRAGMA table_info`, then used `request_json` for provider identity and `bars_sha256` for partition metadata; no database write occurred. |
| Direct browser fetches for two parameterized TPEx daily-report URLs returned internal errors | Used the official JSON endpoints with fixed user-agent transport and recorded response digests plus date-honoring evidence. |
| The modern TPEx daily endpoint ignored the requested 2026-08-18 date and returned 2026-08-20 | Rejected it as exact-date evidence and used the legacy official historical endpoint, which returned report date 2026-08-18 and one 1259 row. |
| Initial technical-report specification path did not exist | Read the skill's declared `specifications/technical-report.md` and MCP report specification instead. |
| First report validation lacked runnable SQL provenance for the derived chart | Added and validated a bounded SQLite `VALUES` projection matching the six reviewed evidence checks before the single visible render. |
| First corrected report script contained an invalid JavaScript token | Rebuilt the same full report payload with ASCII-safe strings and an explicit SQL line array; validation then passed without creating a visible broken card. |
| Full regression has one failure in `tests/test_live_entry_thesis_draft.py` because its unrelated concurrent golden digest is the literal `PENDING_GOLDEN` | Preserve the unrelated file, report the exact computed digest, and rely on focused provider-resolution gates plus compile/digest/whitespace verification for this scope. |
| First focused qualification run could not read the digest sidecar because it had not yet been added | Added the already computed canonical SHA-256 sidecar with `apply_patch`, then reran the same focused gate. |
| Sandboxed credentialed Fugle probe could not resolve `api.fugle.tw` | The temporary capture was removed without publishing a partial artifact; rerun the exact fixed probe with approved network access. |
| Report skill links resolved relative to the skill root rather than the `build-report` subdirectory | Located and read the required technical and MCP report specifications under `skills/build-report/specifications`; report evidence was unaffected. |
| Full regression has one failure in `tests/test_trade_management_operational_composition.py` because its unrelated fixture replaces `event_time` with a timestamp whose date differs from the source event's fixed `session_date` | Preserve the unrelated trade-management test and report the failure honestly; run the suite excluding that file plus all focused PR-008 gates. |
| Official OpenAI documentation search returned an expired local web token while configuring the heartbeat | Used the app-provided automation schema and validated the resulting active heartbeat configuration locally; no repository or research evidence was affected. |
| R2 heartbeat preflight cannot find its frozen job in either the workspace SQLite database or configured PostgreSQL repository | Do not run `--resume`, do not reconstruct checkpoints, and request either immutable backup restoration or owner approval for a new acquisition lineage. |
| Attempt to pause the heartbeat through the app automation interface timed out twice and did not persist a status change | Do not edit the app-owned automation file directly. The active heartbeat remains fail-closed because its first step is the missing-job metadata check. |
