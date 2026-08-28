# Progress Log

## Session: 2026-08-20

### Current Status
- **Phase:** 14 - Credentialed Intraday Source Probe V1 completed; next source decision pending

### Actions Taken
- Read the applicable code-review, file-planning, and surgical-change skill entrypoints.
- Restored repository planning context and captured the prior active plan pointer.
- Read review lines 1-500 and recorded the foundation approval, evidence distinction, accepted design areas, and non-blocking PostgreSQL recommendation.
- Read lines 501-750 and captured all five evidence-phase conditions plus the explicit no-more-features instruction.
- Completed the required Python, architecture, and universal code-review references.
- Searched the repository for approved gate values and evidence artifacts; confirmed only synthetic test values exist and no real formal evaluation population is available.
- Inventoried existing strategy IDs, backtest costs, and local dataset paths; no selected evidence strategy or bar dataset was established.
- Verified the backtest database is empty through an immutable connection and identified the closest stable baseline strategy/cost contracts for an owner decision.
- Determined that Conditions 2-5 are already enforced by the approved framework; Condition 1 requires actual owner-approved values and cannot be completed from synthetic test defaults.
- Stopped before data acquisition or holdout access because the repository has no historical evaluation population and no approved protocol values.
- User approved the proposed baseline bundle with `ok`; protocol freeze is now authorized.
- Re-read the applicable skill entrypoints and complete Python review reference before product/research artifact changes.
- Completed the architecture and universal quality references; implementation remains artifact-first and avoids evaluator/runtime expansion.
- Confirmed reusable strategy-definition digests, research artifact conventions, and the existing threshold domain required for a minimal protocol freeze.
- Computed the owner-approved threshold digest and authoritative strategy-definition digests; confirmed PIT classification inputs and captured the registration timestamp.
- Added the owner-approved `formal_evaluation_gate_v1` artifact, canonical digest sidecar, and coverage-only PIT/data acquisition plan.
- Added drift tests for protocol bytes/semantics, evaluator thresholds, strategy definitions, exact-date lock, safety, and holdout prohibition.
- Final semantic review added aggregate definition digests, stable artifact identity, execution model, and deterministic multi-exit priority; canonical digest was regenerated.
- Completed compile, whitespace, line-length, safety-boundary, focused, and full-regression checks.
- Restored the prior active plan pointer after the scoped protocol-freeze task.
- User approved the protocol-freeze gate and directed the next step to coverage resolution only.
- Reactivated the isolated PR-008 plan; implementation is restricted to a coverage contract, immutable snapshot, digest, and drift tests.
- Added the `PopulationCoverageV1` contract, fail-closed 2026-08-20 repository snapshot, canonical digest sidecar, and semantic drift tests.
- Focused coverage/protocol verification passed with 10 tests.
- Full repository regression passed with 791 tests and 2 skips.
- Compile, canonical digest, line-length, and scoped whitespace checks passed; Ruff was not available in the repository virtual environment.
- Coverage resolution remains legitimately blocked; exact split dates and the composite manifest were not fabricated.
- Coverage framework review returned `APPROVED WITH CONDITIONS`; the next authorized slice is an acquisition-evidence manifest, not strategy or evaluator code.
- Added the `DatasetAcquisitionManifestV1` contract, current fail-closed inventory, canonical digest sidecar, and semantic drift tests.
- Focused acquisition/coverage/protocol gates passed with 16 tests.
- Full regression reached 798 passes and 2 skips but has six unrelated failures in a newly present trade-management shadow-validation test; this task did not edit that file.
- Regression excluding the unrelated failing file passed with 797 tests and 2 skips; acquisition manifest digest verification also passed.
- Dataset Acquisition Manifest review approved the framework with conditions and authorized actual historical artifact collection as the only next scope.
- First official acquisition sealed the 2026-08-19 TWSE raw response, then the one-off diagnostic formatter failed on non-canonical `ValidationCheck` objects before normalized publication or TPEx fetch.
- TWSE replay published a validated normalized partition; TPEx official fetch was quarantined because the endpoint returned 2026-08-20 for a 2026-08-19 request and exposed conflicting scope text.
- Confirmed the TPEx historical report uses slash-form dates and made the minimal adapter correction from `YYYYMMDD` to `YYYY/MM/DD`; added a transport-parameter regression test.
- Preserved the bad TPEx response as raw revision 1, acquired the correct 2026-08-19 response as revision 2, and validated 892 rows with 7,136 passing checks and zero issues.
- Froze the two-market institutional partition set, canonical digest, replay/drift tests, and a technical data-quality report. The pilot contains 2,228 rows and remains `VALIDATED_PARTIAL_COVERAGE`.
- Emitted immutable acquisition manifest r2 with Institutional=`PARTIAL`, `INSTITUTIONAL_HISTORY_INCOMPLETE`, and every downstream permission false.
- Focused source/partition/acquisition/coverage/protocol tests passed with 34 tests.
- Full repository regression passed with 811 tests and 2 skips; the six earlier concurrent shadow-validation failures are no longer present.
- Dataset Acquisition / Institutional Partition review approved the first institutional artifact with conditions and kept formal evaluation blocked.
- Started the completion-gate inventory; scope is limited to dataset identities, coverage, validation, lineage, and blocking issues without price or strategy outcomes.
- Revalidated local acquisition metadata and found one paused price job with 542/2,738 saved symbol partitions, 9,335,704 staged bars, 130 error/empty partitions, and no sealed dataset manifest.
- Added the `DatasetAcquisitionCompletionGateV1` contract, immutable current-state artifact, digest sidecar, and fail-closed drift tests.
- Completion status is 0 `VALIDATED`, 2 `PARTIAL`, and 4 `MISSING`; Price remains `MISSING` because paused staging is not an immutable dataset artifact.
- Focused completion/acquisition/coverage/protocol gates passed with 26 tests.
- Full repository regression passed with 826 tests and 2 skips.
- Price Acquisition Completion review approved the fail-closed gate and authorized the paused price acquisition as the next evidence-only slice.
- Started `PriceAcquisitionResolutionV1`; inspection remains metadata-only and does not read OHLC values or strategy outcomes.
- Initial provider preflight made no external call: implicit dotenv discovery failed under stdin and sandbox process listing was denied; switched to explicit-path and repository-metadata checks.
- Verified the supported resume preconditions without exposing credential values: Shioaji SDK and credentials are present, simulation mode is active, `subscribe_trade=False`, no external database override is configured, and no process held the SQLite file.
- Executed one approved resume attempt against the existing job. Shioaji login succeeded, symbol 1259 again returned an ambiguous empty Kbar response, and the downloader safely paused with exit code 75 without writing a new partition or sealing a dataset.
- Froze `PriceAcquisitionResolutionV1`, its classification contract, immutable metadata-only snapshot, canonical digest sidecar, and six drift tests.
- Corrected the durable resolution boundary to the trusted contiguous prefix: 411 trusted symbols, 131 checkpointed-but-unresolved tail symbols, and 2,196 not checkpointed, leaving 2,327 unresolved of 2,738.
- Rendered the validated technical Price Acquisition Resolution Report from bounded metadata-only evidence; no OHLC values, setup outcomes, or holdout data were read.
- Price remains `MISSING`; population freeze, outcome generation, and holdout execution all remain disabled.
- Price Resolution review approved the safe-pause design with conditions and authorized symbol 1259 classification as the next evidence-only gate; no further retry is allowed before an independent disposition exists.
- Official TPEx evidence establishes that 1259 listed on 2011-12-15 and appears once in the exact 2026-08-18 end-date daily report; structural no-data is rejected.
- Shioaji contract metadata resolves 1259 as the active OTC stock `安心`, but a non-persisting 2026-08-01 through 2026-08-18 probe still returned zero Kbars.
- Same-job TPEx controls 1240 and 12561 have non-empty checkpoints on 2026-08-18, so the failure is symbol-specific rather than a market-wide routing outage.
- Added the `PriceSymbolResolutionClassificationV1` contract, immutable 1259 classification artifact, digest sidecar, and six fail-closed drift tests.
- Classification is `SYMBOL_SPECIFIC_PROVIDER_COVERAGE_MISMATCH` with unknown provider-path root cause; unchanged retry, structural exclusion, Price Artifact creation, population freeze, outcome generation, and holdout remain forbidden.
- Validated and rendered the technical Symbol 1259 Provider Coverage Classification report with one six-check availability chart and a visible root-cause access issue.
- Focused symbol-resolution and upstream drift gates passed with 38 tests; the full repository passed with 845 tests and 2 skips.
- Compile, canonical digest verification, and `git diff --check` passed. Ruff remains not executed because it is unavailable.
- Gate A review approved the 1259 classification and authorized `PRICE_PROVIDER_COVERAGE_RESOLUTION_V1` as the next policy-and-source-qualification slice; acquisition retry and dataset sealing remain prohibited.
- Reviewed current primary documentation without provider calls or price/outcome reads. Shioaji documents the required request shape and history window but not universal per-symbol completeness.
- Evaluated Fugle, FinMind, and official exchange products against the frozen one-minute/OHLCV/VWAP/dual-market/PIT contract. Fugle ranks first for a bounded source qualification; no replacement source was selected.
- Added `PriceProviderCoverageResolutionV1`, canonical digest sidecar, and seven drift tests covering lineage, source-policy limits, alternative-candidate state, exclusion/mixing policy, qualification criteria, and fail-closed permissions.
- Focused provider-resolution and upstream tests passed with 19 tests. Compile, canonical digest, and scoped whitespace checks passed.
- Full repository regression reached 859 passes and 2 skips with one unrelated concurrent failure: `tests/test_live_entry_thesis_draft.py` still compares a stable computed digest to the placeholder `PENDING_GOLDEN`.
- Price remains `MISSING`; unchanged Shioaji resume, alternative acquisition, exclusion, Price Artifact creation, population freeze, outcome generation, and holdout execution all remain disabled.
- Validated and rendered the complete technical Price Provider Coverage Resolution report with a four-source documented-contract chart and exact disposition table; the report explicitly distinguishes contract shape from qualification.
- Provider Coverage Resolution review returned `APPROVED` and authorized only the `INTRADAY_SOURCE_QUALIFICATION_V1` gate; full acquisition and Price Dataset sealing remain prohibited.
- Reactivated the isolated PR-008 plan. Initial entitlement inventory found no Fugle- or FinMind-named key in the local `.env`; no credential value was read or printed.
- Added `IntradaySourceQualificationV1`, canonical digest sidecar, and seven fail-closed drift tests. The artifact records `INSUFFICIENT_EVIDENCE`, not `QUALIFIED` or `REJECTED`.
- Frozen probe scope is 1259 plus TPEx 1240/12561 and TWSE 2330/2317 on 2026-08-18; later common sessions must come from a validated dual-market calendar.
- Focused qualification and upstream drift gates passed with 26 tests; the full repository passed with 867 tests and 2 skips. Compile, digest, and scoped whitespace gates passed.
- Validated and rendered the complete technical Intraday Source Qualification report with one evidence-status chart and a thirteen-check audit table.
- Fugle remains unselected; alternative acquisition, Price Dataset Artifact, population freeze, outcome generation, exclusion, and holdout permissions remain false.
- Intraday Source Qualification review returned `APPROVED`. Rechecked the local environment and confirmed the required Fugle entitlement is still absent; no credential value was accessed and no provider request was issued.
- Recorded Phase 14 as `blocked_external_entitlement`. No additional strategy, acquisition, dataset, or outcome code was authorized or changed.
- Confirmed `FUGLE_API_KEY` is present and non-empty without reading it into output. No Fugle request was issued before the tolerance decision.
- Research owner approved `abs(source_average - reference_vwap) <= max(0.01 TWD, reference_vwap * 0.0001)`; Phase 14 is active and must seal this rule before the first payload read.
- Sealed `CredentialedIntradaySourceProbeProtocolV1` with fixed date/symbols, secret handling, raw-response preservation, no-fill policy, cross-market controls, and the owner-approved VWAP tolerance. Canonical digest is `f6b396072d858356bcd98965ddafc749f2b8b63cfe3555f9f60f58a9c16d10f7`; no candidate payload had been read when frozen.
- The first sandboxed probe attempt failed at DNS resolution before any HTTP response. Its temporary directory was removed and no partial capture artifact was published.
- Executed the exact credentialed Fugle probe once after approved network access. All five requests returned HTTP 200; sealed every raw body, secret-free response headers, retrieval timestamp, request metadata, and SHA-256 without persisting the API key.
- Captured four Shioaji data-only controls for the same session with simulation login and `subscribe_trade=False`; no orders or trading subscription were enabled.
- Fugle returned `data=[]` for 1259, while controls returned 9, 2, 266, and 266 bars. The provider mismatch therefore remains unresolved and is not converted into a structural exclusion.
- Reconciled Fugle start-minute labels to Shioaji end-minute labels, preserving the shared 13:30 closing-auction label. All 543 control bars aligned and all OHLC fields matched.
- All four final cumulative VWAP comparisons passed the frozen tolerance. Symbol 2330 had one eight-lot volume difference; the other three controls matched exact session volume.
- Emitted the immutable `CredentialedIntradaySourceProbeResultV1` with verdict `REJECTED_FOR_MISMATCH_RESOLUTION`; all downstream permissions remain false and no strategy outcome or holdout was read.
- Secret-safe scan confirmed `FUGLE_API_KEY` does not occur in the protocol, captures, result, or digest artifacts.
- Focused probe/upstream drift gates passed with 36 tests; full repository regression passed with 890 tests and 2 skips.
- Validated and rendered the technical Fugle fixed-probe qualification report with one VWAP comparison chart and one exact audit table.
- Compile, canonical digest verification, `git diff --check`, and active-plan restoration passed. Ruff remains not executed because it is unavailable.
- Credentialed Fugle Probe review returned `APPROVED` and confirmed the narrow rejection scope. Reactivated the isolated PR-008 plan for FinMind/official-source qualification only; no Price Artifact or outcome work is authorized.
- Revalidated current official FinMind OpenAPI, dataset catalog, and SDK evidence. KBar requires Sponsor, per-symbol tick requires Backer, and no local FinMind credential identity exists; no FinMind payload request has been executed.
- Confirmed the upstream artifact already enforces no silent mixing. The FinMind gate will reference that policy and explicitly require a new dataset revision for any qualified secondary-source composition.
- Added `AlternativeIntradaySourceQualificationV1` for FinMind KBar plus Tick, canonical digest `9a7111647292678c925c35a1aec6ff6afae1615b3e738f35aa7e20081a64f88b`, and fail-closed drift tests. No provider request or price payload read occurred.
- Focused FinMind/upstream drift gates passed with 43 tests. Full regression reached 908 passes and 2 skips with one unrelated date/session fixture failure in `tests/test_trade_management_operational_composition.py`.
- Regression excluding the unrelated operational-composition test passed with 902 tests and 2 skips. Compile, FinMind artifact digest, and `git diff --check` passed; Ruff remains unavailable.
- Phase 15 completed as `INSUFFICIENT_EVIDENCE`. Restored the prior realtime-dashboard active plan; the next PR-008 gate is blocked on a FinMind token plus KBar/Tick plan entitlement.
- User reported and a secret-safe local check confirmed non-empty `FINMIND_API_TOKEN`; the value was neither printed nor persisted. Reactivated the isolated PR-008 plan for the fixed credentialed probe.
- Revalidated current primary FinMind OpenAPI and dataset catalog. The protocol will use bearer authentication, `/api/v4/data`, fixed single-day KBar/Tick queries, and will classify both HTTP status and JSON status before parsing data.
- Froze the credentialed FinMind request/capture/semantic protocol before payload access; protocol digest `43aa0091e6c038da9714e847de0b8b6e93a80717640881a92efe2302567eb44e`.
- Executed and sealed exactly ten authenticated requests. All returned HTTP/JSON 400 with no data array and a user-level-upgrade response identifying the observed account as `register`.
- Verified the capture manifest digest `4f477c513a0a5e5482d13bdc24d9280c01539c7e568c770c5feb4c161bfe36ed`, every raw-body hash, exact request order, and absence of the full token or authorization header in the capture.
- Emitted `CredentialedFinMindIntradaySourceProbeResultV1` as `INSUFFICIENT_EVIDENCE`, digest `4cb400713f7f5f32d71a346cddb175611ee32690dbd6a439271c990a202b6d46`; all source-selection and downstream evaluation permissions remain false.
- Focused protocol/capture/result/upstream gates passed with 22 tests. Full regression reached 923 passes and 2 skips with the same unrelated operational-composition date/session fixture failure; excluding that file passed 917 tests and 2 skips.
- Compile, secret scan, canonical digests, and `git diff --check` passed. Ruff remains unavailable. Phase 16 completed as `INSUFFICIENT_EVIDENCE` and requires a newly entitled token/account state before a new immutable probe revision.
- Credentialed FinMind Probe review returned `APPROVED`. The user then reported a Sponsor account upgrade; reactivated the isolated PR-008 plan for a new r2 probe without changing or overwriting any r1 artifact.
- Secret-safe preflight confirmed the FinMind token remains present and non-empty. Reviewed the r1 capture boundary and selected an explicit revision argument as the minimal implementation needed to seal r2 separately.
- Added the Sponsor-asserted immutable r2 protocol and explicit capture revision selection. r1 remains the default and untouched; r2 protocol digest is `e0ecce5f893911d6a183396eee2fa94e2c785f3bb327c40882562d3d5e9e9f68`.
- Started the exact r2 probe. The execution environment stopped before request 10, leaving nine unsealed contiguous responses. No r2 artifact was published; recovery will validate and reuse the prefix rather than reissue those requests.
- Confirmed the original process subsequently completed and atomically sealed all ten responses. The recovery path rejected the already-existing output before network access. Verified manifest/raw digests and classified entitlement as observed PASS.
- Completed offline exploratory reconciliation using only sealed FinMind r2 and existing Shioaji control artifacts. Available controls prove exact Tick-to-KBar OHLCV, lot-unit volume, and VWAP equivalence; 1259 and control 12561 remain empty.
- Added the offline FinMind semantic evaluator, immutable r2 result builder, result digest, and drift tests. Result digest is `4a259a737643b60c80193ea40076456d1deebc3aacd3be7bc310850d3d57f189`; all downstream permissions remain false.
- Focused Sponsor r2 and upstream gates passed with 37 tests. Full regression reached 939 passes and 2 skips with the unchanged unrelated operational-composition fixture failure; excluding that file passed 933 tests and 2 skips.
- Compile, canonical digest verification, full-token/Authorization-header scan, and `git diff --check` passed. Ruff remains unavailable. Phase 17 stops at review with FinMind rejected only for mismatch resolution.
- Sponsor r2 review returned `APPROVED` for the narrow rejection and authorized the official/licensed-source resolution gate. Reactivated the isolated PR-008 plan; no procurement, full acquisition, source selection, or outcome work is authorized.
- Began primary-source review. Confirmed official TWSE and TPEx historical transaction-file procurement routes and TEJ PIT/delisted daily support, while recording that none of the reviewed pages yet proves a complete current-period dual-market one-minute dataset contract.
- Read the current TPEx official transaction-file product and format specification. Trade-level price/time/share fields support reconstruction in principle, but recent-history availability and retention/derived-use rights still require contractual confirmation.
- Downloaded and locally inspected the current official TWSE transaction-file format in a temporary file. It has sufficient trade-level fields for minute/VWAP reconstruction in principle; product recency and combined dual-market coverage remain blocking.
- Rechecked licensed-provider public documentation. TEJ currently proves useful daily PIT/reference support but not the required one-minute contract; no signed information vendor is selected from directory membership alone.
- Added immutable `OfficialOrLicensedIntradaySourceResolutionV1`, digest `43cbe7621c6e70541a98e7d565d76ca0c56d8ece2c59ef6856cef4bfaccd921b`, plus drift gates. It preserves `NO_SOURCE_SELECTED` and requires a written procurement RFI plus fixed sample.
- Focused official/licensed resolution and upstream gates passed with 29 tests. Full regression reached 948 passes and 2 skips with one unrelated operational-composition assertion failure; excluding that file passed 942 tests and 2 skips.
- Compile, canonical digest verification, and `git diff --check` passed; Ruff remains unavailable. Phase 18 completed as `INSUFFICIENT_EVIDENCE` and stops before any procurement or provider selection.
- Owner approved a general coverage-based evaluation-universe policy instead of pursuing a fourth provider for 1259. Reactivated PR-008 for a pre-outcome amendment; no named symbol is yet excluded and all outcome permissions remain false.
- Revalidated the original formal protocol and coverage snapshot. Their digests and fail-closed locks are unchanged; no outcome has been generated. Mapped the 95%/99% rule to per-symbol PIT session completeness plus overall covered-symbol share.
- Registered the immutable pre-outcome coverage amendment without modifying the original protocol. The general `DATA_COVERAGE_EXCLUDED` rule has no named-symbol override, freezes symbol coverage >=95%, and freezes both per-symbol and aggregate session coverage >=99%.
- Created the first fail-closed coverage-audit snapshot. Because formal PIT, price, institutional common-range, corporate-action/reference, and calendar inputs remain incomplete, all measurements are null, no symbol is excluded, and all downstream permissions remain false.
- Research owner formally approved the coverage amendment and authorized the next coverage-only data phase. Began Phase 20 by revalidating the partial Shioaji job and formal dataset blockers without reading outcomes.
- Added an explicit `--continue-on-empty-for-coverage-audit` runner option. Default empty behavior still pauses; the explicit mode stores a zero-bar `PRICE_DATA_UNAVAILABLE` observation and continues without treating it as success or evaluation exclusion.
- Extended `CompositeResearchInputManifestV1` and canonical serialization to require digest-pinned original protocol, coverage amendment, coverage audit, and frozen population identities.
- Froze `PriceCoverageObservationContinuationV1` with digest `6ebb34c1a2ab67097e5f447fe778fe2a3edc7eebb6f536478a102b1e2e4c1b65`, then started the approved data-only Shioaji resume. Symbol 1259 was stored as a zero-bar typed observation and acquisition continued from 411 to at least 428 checkpoints.
- Research owner approved the scan architecture and requested immutable scan-configuration evidence before the full scan completes. The active job has advanced beyond 1259 and is still writing data-only checkpoints; no intermediate progress ratio is being treated as formal PIT coverage.
- Registered `PriceCoverageScanConfigurationV1` with digest `16de2310f21fef0acb066f719227e5260539debab2b3647a18296e7802bfc887`; it pins the Shioaji 1.7.2 adapter/source identities, request digest, date range, explicit observation mode, and a metadata-only checkpoint snapshot. The snapshot records 468 nonempty partitions, 2 typed provider-empty observations, and 72 legacy empty rows pending revalidation.
- Registered the `PriceCoverageAuditV1` output contract with digest `6fb84bf8bd4950fe5558488590762f55da335ff3215b5c561fe39ec2c1457384`. It freezes four output sections, all 95%/99% gates, the five concentration dimensions, final-audit lineage requirements, and reason-code handling that blocks direct exclusion for timeouts/rate limits/mapping failures.
- Focused scan-configuration/audit tests pass with 38 tests. Full regression passes with 968 tests and 2 skips; JSON parse, canonical digest, compile, Ruff on Python tests, and `git diff --check` pass. The active scan reached at least 487/2,738 without interrupting execution.
- Implemented the approved coverage-scan taxonomy. In coverage mode, `MarketDataTemporarilyUnavailable` becomes a zero-bar `[TEMPORARY_FETCH_FAILURE]` observation and a `KeyError` becomes `[SYMBOL_MAPPING_ERROR]`; both continue to the next symbol. `MarketDataLimitReached` stays a whole-job pause with `[RATE_LIMITED]` in the durable retry error and writes no partial partition. Normal acquisition mode still pauses on a temporary provider failure.
- The already running Shioaji process loaded the prior continuation code, so it remains intentionally untouched until it reaches a safe pause. The new runner revision will be activated only on its next explicit resume, with a new configuration revision rather than silently changing an active scan.
- Focused taxonomy/lineage gates pass with 32 tests. Full regression passes with 987 tests and 2 skips; Ruff, compile, and whitespace checks pass. The active scan reached at least 655/2,738.
- 2026-08-21: The active r1 scan safely paused at 678/2,738 on Shioaji historical-query rate-limit protection (15.5 MiB remaining of 500 MiB). No process was interrupted and no partial partition was written. Began Phase 23 to record config-segment lineage before any resume; no price values or outcomes were inspected.
- 2026-08-21: Sealed metadata-only r0/r1 segment manifests. r0 covers the pre-coverage trusted non-empty prefix (0..410); r1 covers 411..677 and pins the r1 scan configuration, 259 non-empty observations, 8 typed provider-empty observations, and the rate-limit pause before index 678 / symbol 2101. Registered configuration r2 before any resume, with the new timeout/mapping taxonomy and explicit coverage-scan flag. Updated the CLI pause guidance to preserve that flag on a future coverage resume. Focused tests: 26 passed. Full regression: 993 passed, 2 skipped. JSON, canonical digest, compile, and `git diff --check` passed. Ruff is not installed and was not executed.
- 2026-08-21: Revalidated that the paused job remains at 678/2,738 with retry symbol 2101 and that r2's canonical/source digests still match. Provider allowance remains below the safe threshold, so no retry was run. Registered and locally validated the active `pr008-r2-price-coverage-resume` thread heartbeat for the next Taiwan weekday reset window. It may only perform the frozen data-only resume after metadata preflight; outcome, price payload, population, and holdout boundaries remain closed.
- 2026-08-24: Heartbeat metadata preflight stopped before r2 digest/source checks because the frozen `dataset-download-f914feaddea04e37b3cbdcfce2b0179b` job was absent from both the workspace SQLite database and the configured PostgreSQL repository. No provider query, price payload access, outcome access, or resume was performed. Workspace search found no copy of the job id. Two app automation pause calls timed out without changing the app-owned heartbeat state; its prompt fails closed at the same missing-job preflight. Phase 24 is blocked pending immutable job-store restoration or research-owner approval of an entirely new acquisition lineage.
- 2026-08-26: Owner selected option 2, an append-only r3 lineage. Began metadata-only recovery across available local stores; provider execution, price payload reads, dataset creation, population freeze, outcome generation, and holdout remain prohibited until recovery and r3 drift gates pass.
- 2026-08-26: Exhausted available local metadata stores and found no original job or partitions. Historical r0/r1/r2 artifact gates remain valid (`16 passed`), but no r3 resume artifact was published because its checkpoint pins cannot be independently reconstructed. No provider was built or called; a fresh-job lineage now requires a distinct initialization gate and target-order freeze.
- 2026-08-26: Owner authorized a fresh r3 job. Began create-only design so job/request/target order can be frozen before any historical Kbar call; downstream formal research locks remain disabled.
- 2026-08-26: Added a dedicated fresh-r3 metadata initializer, pure contract-target normalization, deterministic exact-once job identity, append-only artifact publication, and focused adversarial tests. Initial focused gate passed 12 tests; compilation and `git diff --check` passed, while Ruff remains not installed. No provider call has occurred yet.
- 2026-08-26: First live initializer attempt failed before provider construction because `.env` was loaded after importing PostgreSQL-backed application settings. No job or artifact was created. Corrected import-time configuration order before any retry.
- 2026-08-26: The corrected metadata-only initializer created one fresh r3 QUEUED job and immutable target/config artifacts. Read-only PostgreSQL postflight confirmed exact request/target digests, 2,781 targets, zero partitions, zero Dataset, and only one r3 job. Focused gates pass 18 tests; full regression passes 1,501 with 57 skips. Scan and every downstream research/runtime gate remain disabled pending independent re-review and a separate authorization.
- 2026-08-26: Independent review rejected the generic job execution boundary. Atomically quarantined the exact zero-partition job as `PRICE_COVERAGE_PREPARED / PREPARED`, added generic lineage rejection before provider construction, and left all price/data/outcome permissions disabled.
- 2026-08-26: Added no-follow root traversal, a repository-wide 0600 acquisition flock, symlink-safe artifact reads, and crash-replay-safe sidecar/JSON publication. Preserved original r3 artifacts and published append-only quarantine rev2 with digest `f44d1e87a81fd9aedded1d7bc1a42e2032d564e437431fe47f5d62fcf3db27af`.
- 2026-08-26: Final remediation gates pass: 59 focused tests; 1,537 full-suite passes and 59 skips; compile/canonical digest/whitespace checks pass. Ruff remains not installed. R3 is prepared/quarantined, not scan-authorized.
- 2026-08-26: Owner requested the next phase. Began Phase 27 activation-readiness implementation; scope is dedicated preflight/runner and immutable source binding only. Live r3 remains PREPARED, and no Kbar/provider/outcome action is authorized in this phase.
- 2026-08-26: Phase 27 implementation now has a dedicated immutable activation schema/verifier, registration CLI, process-lifetime acquisition lock, exact PREPARED-to-PRICE_COVERAGE_SCAN compare-and-set, and a raw-scan finalizer that never decodes partition payloads or creates a Dataset. Focused activation/history gates pass 55 tests; live artifacts/job/provider remain untouched.
- 2026-08-26: Final Phase 27 no-live verification passes 55 focused tests and 1,552 full-suite tests with 59 skips. Compile and `git diff --check` pass; Ruff remains unavailable. No activation artifact was published and the live r3 PREPARED job was not opened or mutated. Work stops at the explicitly required scoped Git source-freeze gate.
- 2026-08-26: Owner continuation completed the scoped source freeze (`f751843`) and immutable activation freeze (`2697619`). Metadata-only registration and exact replay published digest `ce5ecd701915309664320832df89201666083d0e5147488139a2048055e50c4f` with zero provider/Kbar/job mutation. Final full regression passes 1,555 tests with 61 skips; final activation/artifact gate passes 19 tests. Actual r3 scan remains stopped pending explicit start direction.
- 2026-08-27: PM continuation superseded the pending Shioaji r3 start for the MVP. Phase 29 is now a deliberate hold, not a provider-start gate. Began Phase 30 as an offline-only consumer audit: reuse the upstream immutable FinMind Dataset and existing Dataset/Catalog/Audit contracts; do not construct any provider, materialize a placeholder Dataset, inspect outcome/holdout, commit, or push.
- 2026-08-27: Restored the complete PR-008 plan/findings/progress context and ran the planning session catch-up. The shared worktree contains extensive concurrent changes, including the upstream FinMind snapshot/acquisition path; this phase will not edit source or disturb those changes.
- 2026-08-27: Confirmed the reusable producer/consumer boundary in current source: FinMind snapshot plan -> immutable `HistoricalDatasetCatalog` Dataset -> canonical manifest verification, with repair lineage preserved and `research_eligible=false`. No second historical store or default-binding mutation is needed for the MVP consumer.
- 2026-08-27: Initial planning pass read only the repair-aware snapshot-plan metadata before Dataset publication. This state is now superseded: the exact Dataset was subsequently materialized and passed the bounded PR-MVP-EVAL-001 handoff verification. The missing historical daily institutional candidate-batch series remains unchanged.

### Test Results

| Test | Result | Status |
|---|---|---|
| Focused protocol/evaluation/shadow | 24 passed | PASS |
| Full repository regression | 779 passed, 2 skipped | PASS |
| Compile/format/boundary checks | Pass | PASS |
| Focused coverage/protocol drift gates | 10 passed | PASS |
| Full repository regression after coverage artifact | 791 passed, 2 skipped | PASS |
| Focused acquisition/coverage/protocol drift gates | 16 passed | PASS |
| Full repository regression after acquisition manifest | 798 passed, 2 skipped, 6 failed in unrelated concurrent test | FAIL (UNRELATED) |
| Regression excluding unrelated shadow-validation test | 797 passed, 2 skipped | PASS |
| Focused institutional acquisition and upstream drift gates | 34 passed | PASS |
| Full repository regression after first partition set | 811 passed, 2 skipped | PASS |
| Focused dataset-completion and upstream drift gates | 26 passed | PASS |
| Full repository regression after completion gate | 826 passed, 2 skipped | PASS |
| Focused price-resolution and upstream drift gates | 32 passed | PASS |
| Full repository regression after price-resolution artifact | 839 passed, 2 skipped | PASS |
| Compile, canonical digest, and `git diff --check` | Pass | PASS |
| Focused symbol-classification and upstream drift gates | 38 passed | PASS |
| Full repository regression after symbol classification | 845 passed, 2 skipped | PASS |
| Focused provider-resolution and upstream drift gates | 19 passed | PASS |
| Full repository regression after provider-resolution artifact | 859 passed, 2 skipped, 1 unrelated placeholder-golden failure | FAIL (UNRELATED) |
| Compile, canonical digest, and scoped `git diff --check` | Pass | PASS |
| Focused intraday qualification and upstream drift gates | 26 passed | PASS |
| Full repository regression after qualification artifact | 867 passed, 2 skipped | PASS |
| Qualification compile, canonical digest, and scoped `git diff --check` | Pass | PASS |
| Focused credentialed-probe and upstream drift gates | 36 passed | PASS |
| Full repository regression after credentialed probe | 890 passed, 2 skipped | PASS |
| Fugle secret scan across new artifacts | Not present | PASS |
| Probe compile, all canonical digests, and `git diff --check` | Pass | PASS |
| Focused FinMind qualification/upstream gates | 43 passed | PASS |
| Full repository regression after FinMind qualification | 908 passed, 2 skipped, 1 unrelated fixture failure | FAIL (UNRELATED) |
| Regression excluding unrelated operational-composition file | 902 passed, 2 skipped | PASS |
| FinMind artifact compile, canonical digest, and `git diff --check` | Pass | PASS |
| Focused credentialed FinMind protocol/capture/result gates | 22 passed | PASS |
| Full repository regression after credentialed FinMind probe | 923 passed, 2 skipped, 1 unrelated fixture failure | FAIL (UNRELATED) |
| Regression excluding unrelated operational-composition file | 917 passed, 2 skipped | PASS |
| FinMind full-token and authorization-header capture scan | Not present | PASS |
| FinMind probe compile, canonical digests, and `git diff --check` | Pass | PASS |
| Focused Sponsor FinMind r2/upstream gates | 37 passed | PASS |
| Full repository regression after Sponsor FinMind r2 | 939 passed, 2 skipped, 1 unrelated fixture failure | FAIL (UNRELATED) |
| Regression excluding unrelated operational-composition file | 933 passed, 2 skipped | PASS |
| Sponsor FinMind r2 full-token and authorization-header scan | Not present | PASS |
| Sponsor FinMind r2 compile, canonical digests, and `git diff --check` | Pass | PASS |
| Focused official/licensed resolution and upstream gates | 29 passed | PASS |
| Full repository regression after official/licensed resolution | 948 passed, 2 skipped, 1 unrelated operational-composition failure | FAIL (UNRELATED) |
| Regression excluding unrelated operational-composition file | 942 passed, 2 skipped | PASS |
| Official/licensed artifact compile, canonical digest, and `git diff --check` | Pass | PASS |
| Focused coverage amendment/audit and upstream drift gates | 18 passed | PASS |
| Full repository regression after coverage amendment | 957 passed, 2 skipped | PASS |
| Coverage amendment compile, JSON, canonical digest, `git diff --check`, and Ruff | Pass | PASS |
| Focused Phase 20 downloader/manifest lineage gates | 29 passed | PASS |
| Final focused Phase 20 gates | 32 passed | PASS |
| Full repository regression after Phase 20 implementation | 962 passed, 2 skipped | PASS |
| Scoped Ruff including downloader script with established E402 bootstrap ignored | Pass | PASS |
| Focused Phase 21 scan-configuration and audit-contract gates | 38 passed | PASS |
| Full repository regression after Phase 21 contracts | 968 passed, 2 skipped | PASS |
| Phase 21 JSON parse, canonical digest, compile, Ruff, and `git diff --check` | Pass | PASS |
| Focused Phase 22 scan taxonomy and lineage gates | 32 passed | PASS |
| Full repository regression after Phase 22 taxonomy | 987 passed, 2 skipped | PASS |
| Phase 22 Ruff, compile, and `git diff --check` | Pass | PASS |
| Focused fresh-r3 quarantine, path, lineage, and generic-resume gates | 59 passed | PASS |
| Full repository regression after r3 quarantine | 1,537 passed, 59 skipped | PASS |
| R3 compile, canonical sidecars, and `git diff --check` | Pass | PASS |
| R3 Ruff | Not installed / not executed | NOT EXECUTED |
| Focused Phase 27 activation/history gates | 55 passed | PASS |
| Full regression after Phase 27 activation foundation | 1,552 passed, 59 skipped | PASS |
| Phase 27 compile and `git diff --check` | Pass | PASS |
| Phase 27 Ruff | Not installed / not executed | NOT EXECUTED |
| Scoped r3 source commit | `f751843` | PASS |
| Metadata-only activation registration + exact replay | Same digest `ce5ecd70...e50c4f`; provider/Kbar/job mutation false | PASS |
| Activation artifact commit | `2697619` | PASS |
| Final activation/artifact gates | 19 passed | PASS |
| Full regression after activation artifact freeze | 1,555 passed, 61 skipped | PASS |

### 2026-08-27 - Phase 30 Offline FinMind Consumer Planning Complete

- Synchronized the existing PR-008 workpad without changing the repository-wide active-plan pointer or touching concurrent source work.
- Kept the 2,781-symbol Shioaji r3 scan on hold; no provider, broker, account, trading, price-payload, return, PnL, outcome, or holdout call was made.
- Audited the existing `FinMindSnapshotPlan -> HistoricalDatasetCatalog -> DatasetManifest` producer seam and confirmed the consumer must reuse the new immutable Dataset rather than materialize a second history store or activate `ATOMIC_BACKTEST_DEFAULT`.
- Audited formal `PriceCoverageAuditV1`, PIT-universe, `CompositeResearchInputManifestV1`, FinMind institutional MVP batch, CandidatePool, and backtest application seams. Formal contracts remain frozen; the MVP needs distinct non-formal coverage/universe identities.
- Initial planning recorded the repair-aware plan while the target manifest was absent. That transient state is now closed by the exact PM-approved manifest and bars digest handoff documented below.
- Refreshed the upstream `建立三年歷史資料` task: the single offline materializer is still processing 51,213,436 bars from the saved plan, with no external API or PostgreSQL/default-binding action; this task will not duplicate, interrupt, or restart it.
- Found a second independent blocker: the only sealed institutional candidate observation targets 2026-08-19, one session after the planned Dataset end. It cannot be joined to the price data.
- Published consumer-side phases PR-MVP-EVAL-001 through PR-MVP-EVAL-005 with exact handoff fields and acceptance criteria. After PR-MVP-EVAL-001 passes, the current terminal state is `WAITING_FOR_INSTITUTIONAL_SERIES / INSUFFICIENT_EVIDENCE`; outcome generation is not authorized.

### 2026-08-27 - Phase 30A PR-MVP-EVAL-001 Bounded Handoff Verification

- Received the PM-approved immutable Dataset identity after the upstream P1=0/P2=0 full-data review.
- Confirmed only by filesystem metadata that the Dataset directory, 103,340,016-byte manifest, 10,596,416,681-byte bars file, and 103,323,542-byte saved plan exist as regular non-symlink objects. The bars file was not opened, hashed, or iterated.
- Parsed bounded manifest and plan projections. Dataset identity, date range, requested/observed counts, bar count, storage/profile/order, research boundary, issues, selection counts, sole exclusion, and 9960 repair lineage agree with the handoff.
- A first manifest-to-plan `jq input` comparison had the wrong streaming evaluation order and exited without writes. The exact equality check will use existing domain loaders instead.
- The first domain-loader verifier successfully parsed the canonical schema and internal manifest digest before its raw-byte comparison failed because the command authored a literal `\\n`. This was verifier quoting, not artifact drift; no file was modified or bars content opened.
- The corrected provider-free verifier passed canonical manifest bytes/digest, snapshot-plan schema and four embedded digests, exact manifest/plan identity equality, all approved handoff pins, the 454-target/453-included selection arithmetic, the sole 7610 exclusion, and exact 9960 repair lineage. `bars.jsonl` remained unopened.
- Confirmed the only institutional observation is source 2026-08-18 -> target 2026-08-19 with 17 published candidates and false formal/outcome/order/production permissions. Its target lies outside the verified Dataset range, so overlap is zero.
- PR-MVP-EVAL-001 closes as `PASS (METADATA-ONLY)`. No Dataset/Coverage/Universe artifact was created, no binding or database was queried/mutated, and no provider, bars iterator, outcome, holdout, broker, order, commit, push, PR, or merge action occurred.

### 2026-08-27 - PM Review Disposition

- Received independent disposition `PR-MVP-EVAL-001 APPROVE (P1=0, P2=0)`.
- Reviewer independently confirmed 17 candidates all map from source session 2026-08-18 to usable/target session 2026-08-19; the verified price Dataset ends 2026-08-18, so overlapping target sessions are exactly 0.
- Stopped at `WAITING_FOR_INSTITUTIONAL_SERIES / INSUFFICIENT_EVIDENCE`. No next-stage authority was inferred and no external, runtime, research-outcome, repository-release, or trading action was taken.

### 2026-08-27 - Phase 31 Candidate-Series Authority

- Owner explicitly authorized creation of at least 60 overlapping, digest-pinned institutional candidate sessions.
- Interpreted the authority narrowly: FinMind institutional acquisition, normalization, immutable candidate batches, and one series manifest. Price payloads, outcome, holdout, Evaluation Universe freeze, Shioaji r3, runtime/default binding, broker, and orders remain excluded.
- Began local inventory and source-seam inspection before any provider call.
- Local inventory confirms zero existing daily batch artifacts/series artifacts. Reuse targets are the reviewed 2026 equity calendar, frozen candidate policy, daily application service, FinMind adapter, and immutable batch repository.

### 2026-08-27 - Phase 31 Candidate-Series Completion

- Added the minimal `InstitutionalMvpCandidateSeriesPlanV1` and `InstitutionalMvpCandidateSeriesV1` domain/CLI seam. It reuses the reviewed daily service, parser, policy, calendar, FinMind adapter, and immutable daily repository.
- Verified the exact approved price Dataset manifest and snapshot-plan metadata without opening or iterating `bars.jsonl`, then froze 60 T/T+1 pairs before provider access. Plan digest: `0f11907b01d713aba768ee62ff8c0b9cf61283ed2b326fdc32efaf177c8569b4`.
- The sandboxed provider preflight returned `PROVIDER_PREFLIGHT_FAILED` with zero batches. Re-ran the exact frozen plan in the approved network environment; it completed all 60 sessions. The accepted consumer manifest digest is `71723f527c673cd0e6d225f03ee7083ad260fe2005b96401792cdd5fd5ed1931`.
- Preserved the first pre-review series projection (`315c4de6...11e29e`) append-only, then replayed the same 60 exact batches offline to add explicit per-batch policy/calendar/mapping-count lineage. No second provider call occurred; consumers must pin only the accepted `71723f52...d1931` revision.
- Offline reconstruction verified 60 unique overlapping target sessions, 60 exact batch digests, 1,168 candidate entries, Dataset lineage pins, candidate ranks, T/T+1 chronology, raw-response digests, current-mapping limitations, and all downstream permission locks.
- Replayed the exact series from local immutable batches as `IDEMPOTENT_REPLAY`; no second provider request was needed. Token and Authorization-header scans were clean.
- Focused institutional regression: 59 passed. Compile and whitespace checks passed; Ruff is unavailable. Full regression: 1,749 passed, 88 skipped, one unrelated `test_finmind_selection_bundle` failure caused by current mutable Phase 82 target-job row drift.
- Stopped at `INSTITUTIONAL_SERIES_READY / NEXT_GATE_NOT_AUTHORIZED`. No Coverage Audit, Evaluation Universe, outcome, holdout, runtime/default binding, broker, order, commit, push, PR, or merge action was taken.

### 2026-08-27 - Phase 32 Coverage/Universe Authority

- Owner explicitly authorized the next Coverage Audit and Evaluation Universe Freeze stage.
- Scope is the already planned non-formal MVP path: metadata-only FinMind Dataset coverage plus exact intersection with the accepted 60-session institutional candidate series. Formal PIT eligibility, outcome, holdout, runtime/default binding, broker, and orders remain excluded.
- Began source/contract reconciliation. The formal coverage amendment still requires PIT/reference/corporate-action inputs and a coverage-only concentration owner review; this phase must not relabel the MVP audit or universe as formal evidence.
- Completed the first offline join profile without opening `bars.jsonl`: the acquisition-declared Dataset passes its numeric 95%/99% gates after uniform full-window READY qualification, but the candidate-to-price join covers only 199/319 candidate symbols and is strongly weaker for TPEx.
- Selected the fail-closed universe rule already implied by the amendment: only candidate memberships whose symbol has >=99% full-window READY price partitions and whose exact target partition is READY may enter. This produces 889 membership rows across 199 symbols and all 60 sessions; all exclusions remain explicit in the audit.

### 2026-08-27 - Phase 32 Coverage Audit and MVP Universe Freeze Complete

- Added the offline coverage/universe contract, verifier, and CLI. The command reads only the approved Dataset manifest/snapshot-plan metadata and immutable institutional candidate metadata; it does not open `bars.jsonl`, call a provider, or inspect price/Kbar values, return, PnL, outcome, or holdout.
- Published coverage audit `8c60c80a18b3c4aecdaaaff547231203b54361718d4d8638f1ee400ee1690470` as `PASS_FOR_NON_FORMAL_MVP_FREEZE_ONLY`. The acquisition-declared current-snapshot denominator has 435/454 qualified symbols (95.8150%) and 316,055/316,245 READY qualified partitions (99.9399%).
- The candidate join includes 889/1,168 observations across 199/319 symbols and all 60 sessions. Exclusions are 271 observations whose symbols are absent from the price Dataset plus eight observations from symbols below the uniform 99% full-window READY rule. TPEx included-observation coverage is 36.8% versus TWSE 80.8245%, so formal/all-market claims remain blocked.
- Published universe `dd1f4f30d7795a3dc4d802f51d23f52f8cd3fa0a17d01f2c57f71713011120e3` as `FROZEN_NON_FORMAL_MVP`. All formal population, outcome, holdout, production, runtime-strategy, and order permissions remain false.
- Exact replay returned `IDEMPOTENT_REPLAY`. Focused institutional regression passed 55 tests; compile and `git diff --check` passed. Ruff is unavailable (`NOT_EXECUTED`). Full regression passed 1,754 tests with 88 skips; the sole failure is the previously recorded unrelated mutable Phase 82 target-job row drift.
- Stopped before `CompositeResearchInputManifestV1`, outcome generation, holdout, runtime/default binding, broker, order, commit, push, PR, or merge. Phase 32 is complete only for the explicitly scoped non-formal MVP universe.

### 2026-08-27 - Phase 33 Review Cycle 1

- Performed architecture, semantic, publication-path, and trust-boundary review of the new coverage/universe builder, shared series publisher/loader, exact-batch CLI loader, and tests.
- Added adversarial tests before implementation for false content digests, symlink/hardlink artifact paths, batch path escape, symlinked batch reads, covered-symbol market drift, candidate-series count drift, overlapping included/excluded symbols, and self-rehashed arbitrary coverage authority.
- The expected red gate reproduced all findings: 13 failed and 8 passed. Failures are confined to the newly added adversarial cases and the deliberately strengthened universe-builder call contract; no existing passing behavior regressed before remediation.

### 2026-08-27 - Phase 33 Review Cycle 2

- Hardened the shared content-addressed publisher/loader with full body-digest/artifact-id checks, schema/category binding, no-follow owner-controlled paths, an exact publication lock, single-link artifact reads, safe stale-temporary recovery, and correct one-winner idempotency under concurrency.
- Hardened the offline exact-batch loader with canonical path components, directory-descriptor traversal, no symlink/special/hardlink reads, and candidate-batch body digest/id/session verification before returning a payload.
- Strengthened coverage/universe semantics: exact selection-audit binding, current-snapshot/research/storage/source contract checks, partition status/bar-count invariants, candidate-series authority/count/session/rank/market invariants, market cross-checks, and mandatory coverage reconstruction before universe construction or verification.
- Added valid BLOCKED behavior for zero-candidate and zero-qualified-symbol evidence. No output schema or accepted real artifact membership changed.
- First concurrency implementation exposed a transient two-link window (`1 failed / 34 passed`). Added a secure per-category publication lock and stale-link recovery; the corrected focused gate passed 76 tests.
- Real 60-session replay returned `IDEMPOTENT_REPLAY` with unchanged coverage digest `8c60c80a...1690470`, universe digest `dd1f4f30...11120e3`, 889 memberships, 199 symbols, and 60 sessions. Artifact file SHA-256 values and 0440/single-link metadata remained unchanged; only new 0600 publication lock files were added to the two category directories.
- Repository virtualenv still lacks the Ruff module, but the installed system Ruff executable was discovered and the complete Phase 33 scoped set passed `ruff check`. Compile and whitespace gates also pass.

### 2026-08-27 - Phase 33 Final Review Disposition

- Added and passed the final T/T+1 Dataset-order adversarial gate; focused Phase 33/institutional regression is 77 passed.
- Real artifact replay remains exact and idempotent: coverage `8c60c80a18b3c4aecdaaaff547231203b54361718d4d8638f1ee400ee1690470`, universe `dd1f4f30d7795a3dc4d802f51d23f52f8cd3fa0a17d01f2c57f71713011120e3`, 889 memberships, 199 symbols, 60 sessions.
- Canonical-byte comparison, recursive forbidden secret/OHLCV/return/PnL/outcome key scan, owner/mode/link metadata, scoped Ruff, compile, and whitespace gates pass.
- Final full regression: 1,776 passed, 88 skipped, one previously known unrelated Phase 82 mutable target-job row drift failure. Its four adjacent immutable selection-bundle tamper tests pass; no Phase 33 file reads or mutates that SQLite job.
- Final decision: `APPROVED` with P1=0/P2=0 for the explicitly non-formal MVP Coverage Audit and Evaluation Universe Freeze. All formal and execution permissions remain closed.

### 2026-08-27 - Phase 34 PR-MVP-EVAL-005 Authority

- Received explicit owner authority for only the frozen-universe non-formal offline A/B diagnostic.
- Preserved the prohibitions on strategy changes, tuning, formal holdout, provider/broker access, runtime/default binding, and orders.
- Selected the minimum architecture: one content-addressed pre-outcome plan, one read-only Catalog view, one engine-level entry-eligibility port, and one append-only non-formal result artifact.
- No price bar, return, PnL, outcome, or holdout value was read during this design/freeze preparation step.

### 2026-08-27 - Phase 34 Offline A/B Diagnostic Complete

- Added a provider-neutral, content-addressed diagnostic plan/result contract, a read-only Catalog bar view, an outer engine entry-eligibility port, and an explicit freeze/execute CLI. No second price Dataset or runtime binding was created.
- The first frozen plan `693a009b...b891` completed both arms but failed closed before result publication. A bounded aggregate replay found four cross-session trades despite zero unresolved positions and zero eligibility violations.
- Fixed the existing engine boundary by cancelling non-daily pending orders at session end while preserving `DAILY_NEXT_BAR`. The second frozen plan `d7df1f02...0a86` still failed closed because an intraday entry could fill on the session's terminal bar and could not be exited on the same event.
- Added a second surgical engine guard that rejects a non-daily entry before a terminal-bar fill. Strategy definitions, thresholds, priority, capital, and cost model were not changed. Focused engine/daily/MVP regressions passed 52 tests.
- Froze final plan `d5e2908df7e984ef563e5a7af3128bebcb9803eef757c005a6fdcc191222bb66` before opening bars. It pins the exact Dataset/candidate-series/coverage/universe/protocol/code identities, 60 target sessions, 435 symbols, 889 memberships, and 4,568,727 selected bars.
- Published result `1b62e1e7eaa8887e3c604f927f73a4db2628f33f91e03ac7d947364d077c6a52` as `NON_FORMAL_MVP_OBSERVATION_ONLY`: price-only 793 trades versus institutional-filter 77; expectancy delta -1,704.466846 TWD; trade retention 9.709962%; win-rate delta +1.054683 percentage points.
- A second full two-arm replay returned the same result digest as `IDEMPOTENT_REPLAY`. Both arms have zero unresolved positions and 60 per-session observations.
- Canonical load, 0440/single-link metadata, forbidden secret-key scan, scoped Ruff, compile, whitespace, artifact tamper tests, and exact replay pass. Full regression: 1,783 passed, 88 skipped, one previously known unrelated Phase 82 mutable target-job row drift failure.
- Final Phase 34 disposition: `APPROVED` for the authorized non-formal offline diagnostic only. The observation does not show improved per-trade expectancy or profit factor from the institutional filter. Formal outcome/holdout, PIT/full-market claims, strategy tuning, runtime/default binding, provider/broker calls, production, and orders remain disabled.

### Errors

| Error | Resolution |
|---|---|
| The first outer-gate test compared all strategy-evaluation counters with an ungated run | Corrected the assertion to the execution outcomes that must remain identical; suppressing non-target entry evaluations is the intended outer-gate behavior. |
| The first diagnostic fixture used a generic imported manifest without FinMind plan/source identities | Kept the tiny Catalog payload unchanged and supplied a projected immutable manifest carrying the exact snapshot identities required by the consumer contract. |
| The first manifest verifier used institutional canonical JSON on a Dataset cadence summary containing floats | Reconstituted `DatasetManifest` and used its own canonical `manifest_digest` contract instead of crossing serialization bounded contexts. |
| The first engine-result digest used institutional canonical JSON on existing float projections | Used the backtest bounded context's deterministic `digest()` for the existing engine result projection while retaining float-free institutional artifact fields. |
| The first real plan completed both arms but post-run validation rejected four cross-session intraday trades | Preserve the failed plan, add a session-end cancellation for non-daily pending orders, and keep explicit daily-next-session orders unchanged. |
| The second real plan still allowed an intraday entry to fill on the session terminal bar | Preserve the second failed plan, reject terminal-bar intraday entry fills before position creation, add a dedicated regression, and freeze a new plan revision. |
| `sqlite3 -readonly data/backtest/backtest.sqlite3` could not open the database | Retried with Python SQLite `mode=ro&immutable=1`; inspection succeeded without writes. |
| `python` command not found while refreshing coverage evidence | Switched to `python3`; failed attempt made no repository changes. |
| System Python reported `No module named pytest` | Compile and whitespace checks still completed; focused tests will use the repository virtual environment. |
| `.venv/bin/ruff` was unavailable | Focused pytest passed; retain compile and `git diff --check` as the available format/static gates. |
| First series execution in the restricted sandbox returned `PROVIDER_PREFLIGHT_FAILED` before any batch | Re-ran the exact digest-pinned plan with approved FinMind network access; all 60 batches completed and the series sealed. |
| Full regression Phase 82 selection-bundle test found its mutable target job row had drifted | Preserve the unrelated live SQLite state and report the full gate honestly; focused institutional regression passes 59 tests. |
| Six `test_trade_management_shadow_validation.py` tests fail at `timedelta(seconds=Decimal(...))` | Preserve unrelated user/concurrent work; report the full gate honestly and verify the remaining suite separately. |
| Acquisition diagnostic rejected `ValidationCheck` objects | Replay the already sealed TWSE raw bytes and serialize only scalar check-status counts; no raw evidence was lost. |
| TPEx Swagger and report page returned HTTP 403 through the web reader | Inspect official contract through a browser-like fixed HTTPS request and retain the 403 as a source-access limitation. |
| TPEx compact-date request returned 2026-08-20 instead of 2026-08-19 | Preserve revision 1, verify the official page's slash-form parameter, patch the adapter, and validate revision 2. |
| Initial partition-manifest drift test hashed the file's trailing newline | Hash parsed canonical JSON as required by the contract; the artifact digest was correct. |
| Initial SQLite query used columns absent from the current schema | Reconciled the schema with `PRAGMA table_info` and repeated the metadata-only query using the actual columns. |
| Parameterized TPEx daily-report pages failed in the browser reader | Queried the official JSON transport and preserved only digest/date/row-count evidence. |
| Modern TPEx endpoint returned 2026-08-20 for a 2026-08-18 request | Rejected the response for exact-date classification and used the official historical endpoint that honored 2026-08-18. |
| Technical report reference path was stale | Loaded the current technical and MCP app report specifications from the skill's `specifications` directory. |
| Initial report validation required runnable chart-source SQL | Added a bounded six-row SQLite `VALUES` projection and revalidated before rendering. |
| First corrected report payload had invalid JavaScript syntax | Rebuilt the same complete report using an explicit SQL line array; the second validator attempt passed. |
| Sandboxed Shioaji initialization failed to bind an inter-thread file descriptor | Re-ran the exact supported data-only resume outside the sandbox after approval; SDK initialization and login succeeded. |
| Symbol 1259 returned another ambiguous empty Kbar response | The downloader safely paused with exit code 75, wrote no new partition, and did not create a Price Dataset Artifact. |
| Full regression compares a live-entry digest against `PENDING_GOLDEN` | Preserve the unrelated concurrent test file; the stable computed value is `3ad4d65be0e7b72034be2beb2c93088cdb0e8997dab0be1e07b287f0b197d857`. |
| Sponsor r2 capture process ended before fixed request 10 | Keep the nine responses unpublished, validate their exact contiguous prefix and hashes, then fetch only the missing suffix before atomic sealing. |
| Initial semantic test compared the textual exponent of Decimal zero | Assert numeric zero instead; canonical Decimal strings may legitimately retain different zero exponents. |
| Recovery command found the immutable r2 capture already sealed | The command failed before any provider access, issued no duplicate request, and the sealed ten-record capture passed manifest and raw-body digest verification. |
| Full regression operational-composition test now reaches the journal assertion but records zero entries | Preserve unrelated concurrent work; the Phase 18 files do not touch runtime trade-management composition, and the remainder of the suite passes when that file is excluded. |
| Initial protocol/coverage paths were guessed incorrectly | Used the paths declared by existing drift tests under `protocols/` and `coverage/`; failed reads made no changes. |
| Scoped Ruff surfaced pre-existing `E402` imports in `scripts/download_backtest_history.py` after its intentional `sys.path` bootstrap | Do not refactor the established script bootstrap in this scope; run Ruff on changed library/tests normally and check the script with `--ignore E402`. |
| Ruff was invoked directly on JSON research artifacts and parsed JSON booleans as Python identifiers | JSON is not a Ruff target; validate artifacts with `python -m json.tool`, canonical digest checks, and drift tests instead. |
| Restoring the old active planning pointer failed because another active task changed it concurrently | Preserve the current `2026-08-21-d-health-late-evidence-tracking` pointer and update only the isolated PR-008 planning files. |
