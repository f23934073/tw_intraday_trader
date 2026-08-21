# Task Plan: PR-008 Review Follow-up

## Goal
Read the supplied PR-008 Formal Evaluation Foundation review, close any authorized conditions with surgical changes, verify the affected research contracts, and stop at the next explicit review gate without claiming empirical strategy evidence.

## Current Phase
Phase 21 - Price Coverage Scan Configuration Evidence V1

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
- [ ] Execute r2 only after the heartbeat's metadata-only preflight passes
- [ ] On any new whole-job safe pause, seal the active segment and freeze the next configuration revision before another resume
- [ ] Produce Raw Scan Inventory only after all 2,738 targets have sealed segment evidence
- **Status:** scheduled_pending_provider_reset

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
