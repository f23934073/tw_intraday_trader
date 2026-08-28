# HYG-001 Working Tree Triage — 2026-08-28

## Frozen baseline

- Snapshot timestamp: `2026-08-28T12:29:24+0800`
- Branch: `main`
- HEAD: `d0e271e0a247c669adae23423244de0cc7200832`
- Manifest SHA-256: `a7a7dd77437c8f9b8df191b9f19d5d81313fb926d530e0c31cae0516c3391e60`
- Tracked/modified entries: `37`
- Untracked entries: `136`
- Total entries: `173`
- PCD-001 handoff: `tests/test_price_coverage_scan_segment_manifest.py` remains T9 and must stay unstaged.

## T1 (13)

```text
 M backtest/atomic_benchmark/application.py
 M backtest/atomic_benchmark/preflight.py
 M scripts/preflight_atomic_entry_benchmark.py
 M tests/test_atomic_entry_benchmark_full_dataset.py
 M tests/test_atomic_entry_benchmark_postgres.py
?? architecture/r6_g3_dynamic_entry_reserve_amendment_a2.md
?? backtest/migrations/018_r6_dynamic_entry_reserve.sql
?? scripts/apply_r6_g3_migration_018.py
?? scripts/audit_atomic_entry_benchmark_eligibility.py
?? scripts/supervise_atomic_entry_benchmark_preflight.py
?? tests/test_apply_r6_g3_migration_018.py
?? tests/test_audit_atomic_entry_benchmark_eligibility.py
?? tests/test_supervise_atomic_entry_benchmark_preflight.py
```

## T2 (15)

```text
 M backtest/finmind_snapshot.py
 M scripts/download_finmind_sponsor_history.py
 M tests/test_finmind_sponsor_history.py
?? backtest/finmind_selection_bundle.py
?? backtest/finmind_source_repair.py
?? backtest/fugle_source_repair.py
?? docs/
?? scripts/build_finmind_phase82_selection_bundle.py
?? scripts/capture_fugle_source_repair_candidate.py
?? scripts/derive_fugle_source_repair_candidate.py
?? scripts/manage_finmind_source_repair.py
?? scripts/verify_finmind_selection_bundle.py
?? tests/test_finmind_selection_bundle.py
?? tests/test_finmind_source_repair.py
?? tests/test_fugle_source_repair.py
```

## T3 (9)

```text
 M market_data/late_delivery_capture.py
 M market_data/late_delivery_capture_cli.py
 M market_data/late_delivery_daily_cli.py
 M market_data/late_delivery_evidence.py
 M tests/test_late_delivery_capture.py
 M tests/test_late_delivery_evidence.py
?? scripts/launchd/com.stevehuang.tw-intraday-trader.d-health-late-001-open-20260828.plist
?? scripts/run_one_shot_late_delivery_open.py
?? tests/test_run_one_shot_late_delivery_open.py
```

## T4 (2)

```text
 M market_data/shioaji_momentum_stream.py
 M tests/test_shioaji_momentum_stream.py
```

## T5 (2)

```text
 M scripts/launchd/com.stevehuang.tw-intraday-trader.freshness-calibration.plist
 M tests/test_freshness_calibration_schedule.py
```

## T6 (2)

```text
 M tests/test_backtest_sqlite_postgres_migration.py
 M tests/test_strategy_migrations.py
```

## T7 (43)

```text
 M .planning/.active_plan
 M .planning/2026-08-20-pr008-review-followup/findings.md
 M .planning/2026-08-20-pr008-review-followup/progress.md
 M .planning/2026-08-20-pr008-review-followup/task_plan.md
 M .planning/2026-08-21-finmind-sponsor-three-year-rebuild/findings.md
 M .planning/2026-08-21-finmind-sponsor-three-year-rebuild/progress.md
 M .planning/2026-08-21-finmind-sponsor-three-year-rebuild/task_plan.md
 M .planning/2026-08-24-finmind-premarket-strategy-impl-plan/findings.md
 M .planning/2026-08-24-finmind-premarket-strategy-impl-plan/progress.md
 M .planning/2026-08-24-finmind-premarket-strategy-impl-plan/task_plan.md
 M .planning/2026-08-26-r6-atomic-strategy-benchmark/findings.md
 M .planning/2026-08-26-r6-atomic-strategy-benchmark/progress.md
 M .planning/2026-08-26-r6-atomic-strategy-benchmark/task_plan.md
 M findings.md
 M progress.md
 M task_plan.md
?? .planning/2026-08-24-finmind-premarket-strategy-impl-plan/implementation_plan.md
?? .planning/2026-08-24-vwap-strategy-failure-attribution/audit_r5_terminal.py
?? .planning/2026-08-24-vwap-strategy-failure-attribution/execute_r5_control.py
?? .planning/2026-08-25-pr-tm-012c1-c1-runtime/
?? .planning/2026-08-25-uncommitted-commit-packaging/
?? .planning/2026-08-26-kill-switch-durable-control-implementati/
?? .planning/2026-08-26-local-paper-tax-slippage-implementation-/
?? .planning/2026-08-26-next-parallel-tasks-after-kill-switch-an/
?? .planning/2026-08-26-pr-tm-012c1-next-session-prep/
?? .planning/2026-08-26-pr-tm-012c1-review-remediation/
?? .planning/2026-08-26-pr-tm-012c1-shadow/
?? .planning/2026-08-27-d-health-late-recovery/
?? .planning/2026-08-27-pr-tm-012c1-shadow/
?? .planning/2026-08-27-r6-g3-eligibility-remediation/
?? .planning/2026-08-27-supervise-three-parallel-safety-tasks/
?? .planning/2026-08-27-trading-session-slippage-no-overnight-re/
?? .planning/2026-08-28-pr-tm-012c1-blocker-remediation/
?? .planning/2026-08-28-trading-day-job-audit/
?? WORKFLOW.md
?? architecture/hygiene_plans_index.md
?? architecture/institutional_module_boundary_implementation_plan.md
?? architecture/local_paper_kill_switch_durability_implementation_plan.md
?? architecture/local_paper_tax_slippage_implementation_plan.md
?? architecture/planning_log_single_source_implementation_plan.md
?? architecture/price_coverage_source_digest_drift_implementation_plan.md
?? architecture/static_analysis_ci_implementation_plan.md
?? architecture/working_tree_commit_packaging_implementation_plan.md
```

## T8 (85)

```text
?? records/market_events/2026-08-25/
?? records/market_events/2026-08-26/
?? records/market_events/2026-08-27/
?? records/market_events/2026-08-28/
?? research/captures/freshness_broker_account/broker_account_20260825T113006+0800_db202416.json
?? research/captures/freshness_broker_account/broker_account_20260825T123003+0800_f6764399.json
?? research/captures/freshness_broker_account/broker_account_20260825T132005+0800_ec3f4f57.json
?? research/captures/freshness_broker_account/broker_account_20260826T093505+0800_1df6a1b7.json
?? research/captures/freshness_broker_account/broker_account_20260826T103005+0800_c78fe88f.json
?? research/captures/freshness_broker_account/broker_account_20260826T113005+0800_d429f5ac.json
?? research/captures/freshness_broker_account/broker_account_20260826T123000+0800_2ce20a8d.json
?? research/captures/freshness_broker_account/broker_account_20260826T132005+0800_d45e29d4.json
?? research/captures/freshness_broker_account/broker_account_20260827T093505+0800_68aa5d81.json
?? research/captures/freshness_broker_account/broker_account_20260827T103003+0800_621aa3e6.json
?? research/captures/freshness_broker_account/broker_account_20260827T113005+0800_15815231.json
?? research/captures/freshness_broker_account/broker_account_20260827T123005+0800_726f83db.json
?? research/captures/freshness_broker_account/broker_account_20260827T132001+0800_fbda09af.json
?? research/captures/freshness_broker_account/broker_account_20260828T093505+0800_747cf97f.json
?? research/captures/freshness_broker_account/broker_account_20260828T103005+0800_083c7abd.json
?? research/captures/freshness_broker_account/broker_account_20260828T113004+0800_d86cf3a8.json
?? research/captures/freshness_quote/quote_20260825T110016+0800.json
?? research/captures/freshness_quote/quote_20260825T120014+0800.json
?? research/captures/freshness_quote/quote_20260825T130132+0800.json
?? research/captures/freshness_quote/quote_20260826T090011+0800.json
?? research/captures/freshness_quote/quote_20260826T100010+0800.json
?? research/captures/freshness_quote/quote_20260826T110022+0800.json
?? research/captures/freshness_quote/quote_20260826T120017+0800.json
?? research/captures/freshness_quote/quote_20260826T130256+0800.json
?? research/captures/freshness_quote/quote_20260827T090011+0800.json
?? research/captures/freshness_quote/quote_20260827T100010+0800.json
?? research/captures/freshness_quote/quote_20260827T110012+0800.json
?? research/captures/freshness_quote/quote_20260827T120010+0800.json
?? research/captures/freshness_quote/quote_20260827T130142+0800.json
?? research/captures/freshness_quote/quote_20260828T090014+0800.json
?? research/captures/freshness_quote/quote_20260828T091718+0800.json
?? research/captures/freshness_quote/quote_20260828T100013+0800.json
?? research/captures/freshness_quote/quote_20260828T110017+0800.json
?? research/captures/freshness_quote/quote_20260828T120018+0800.json
?? research/finmind_source_repair_9960_20260320_tpex_daily_v1.json
?? research/finmind_source_repairs/
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260825T113006+0800_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260825T123003+0800_late_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260825T132005+0800_pre_close.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T093505+0800_early_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T103005+0800_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T113005+0800_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T123000+0800_late_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T132005+0800_pre_close.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T093505+0800_early_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T103003+0800_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T113005+0800_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T123005+0800_late_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T132001+0800_pre_close.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T093505+0800_early_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T103005+0800_continuous.json
?? research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T113004+0800_continuous.json
?? research/freshness_calibration/reviews/2026-08-25_1301_close_review.md
?? research/freshness_calibration/reviews/2026-08-26_1302_close_review.md
?? research/freshness_calibration/reviews/2026-08-26_post_session_cross_evidence_review.md
?? research/freshness_calibration/reviews/2026-08-27_1301_close_review.md
?? research/freshness_calibration/scheduled_runs/run_20260825T110000+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260825T120002+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260826T090000+0800_opening.json
?? research/freshness_calibration/scheduled_runs/run_20260826T100005+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260826T110006+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260826T120005+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260827T090005+0800_opening.json
?? research/freshness_calibration/scheduled_runs/run_20260827T100005+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260827T110005+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260827T120006+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260828T090006+0800_opening.json
?? research/freshness_calibration/scheduled_runs/run_20260828T091705+0800_opening.json
?? research/freshness_calibration/scheduled_runs/run_20260828T100003+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260828T110005+0800_continuous.json
?? research/freshness_calibration/scheduled_runs/run_20260828T120005+0800_continuous.json
?? research/late_delivery_evidence/runtime/
?? research/trade_management_shadow/premarket_20260826_postfix_diagnostic.json
?? research/trade_management_shadow/premarket_20260826_postfix_diagnostic.json.sha256
?? research/trade_management_shadow/premarket_20260826_postfix_diagnostic_v2.json
?? research/trade_management_shadow/premarket_20260826_postfix_diagnostic_v2.json.sha256
?? research/trade_management_shadow/premarket_20260827.json
?? research/trade_management_shadow/premarket_20260827.json.sha256
?? research/trade_management_shadow/premarket_20260828.json
?? research/trade_management_shadow/premarket_20260828.json.sha256
?? research/trade_management_shadow/session_input_drafts/
```

## T9 (2)

```text
 M tests/test_price_coverage_scan_segment_manifest.py
?? data/
```

## UNCLASSIFIED (0)

```text
```

## Execution ledger

- Backup: `../tw_intraday_trader_backup_20260828.bundle`; `git bundle verify` passed; SHA-256 `11aa52d46421e4a32a16dcfec41be430bcba89023812d3927a95aff8a00483dd`.
- Commits:
  - T1 + T6: `980f396656e48fab88ba90c5f6329c6d02f88dfb`; focused tests `35 passed` and `6 passed, 1 skipped`.
  - T3: `1fac6fba0088aac20f72c5b0fd159e37d71f1616`; focused tests `18 passed`.
  - T4: `b7bc44f646803b0128a361b7fd2782f58b6d3228`; focused tests `13 passed` with `PROVIDER=mock`.
  - T5: `bfa27aeca7b6e9960e57d64e94077f41772b8f08`; focused tests `11 passed`.
  - T7 architecture documents: `f99186e3620be2fb12986b26e4873fb574139e63`; `git diff --check` passed.
  - T7 planning workpads: `7b4d3cab082ce0bcd1914848b4afe5d9bc1c888a`; 64-path manifest SHA-256 `c91daf996f0980365a996b4337571ac112ccde62765ded9616d21cb614a9bd68`; `git diff --check` passed.
  - HYG-001 repository hygiene artifacts and `.gitignore`: `6a8a167f1eb86449dabe84c910d05b482bed164d`; classifier returned `UNCLASSIFIED (0)`, Python compilation passed, `git check-ignore -v` passed, and the four-path staged set passed `git diff --check`.
- Deferred groups:
  - T2: focused suite returned `1 failed, 32 passed`; `test_phase82_bundle_reproduces_selection_and_status_only_job` failed with `FinMindSelectionBundleError: bound target job row drifted`. All T2 paths were explicitly unstaged and left unchanged.
  - T8: final cutoff at `2026-08-28T12:37:05+0800` expanded to 126 exact files. Path-manifest SHA-256 was `da0b84ca20a3d43fd377ddd973d4c1ee0bbcd41f22ceb1001f28b4b1531df88d`; file-digest-manifest SHA-256 was `ca891622ae6f88d805b807b213e1ce4ff713a64fbf066ad17483e0589fe3e8c2`. Staged paths and file digests matched the cutoff, but `git diff --check` failed on existing trailing whitespace at `research/freshness_calibration/reviews/2026-08-27_1301_close_review.md:5`. All 126 paths were explicitly unstaged and no evidence was edited.
- Refreshed-baseline scheduled evidence additions:
  - `research/captures/freshness_quote/quote_20260828T120018+0800.json`: SHA-256 `5bee45145da89cdee2a7f642f76cb1653ea6015d301b3e917228c29ae0d1da3d`.
  - `research/freshness_calibration/scheduled_runs/run_20260828T120005+0800_continuous.json`: SHA-256 `0d16acd20269769904f5c594e6405bf925e55573e39166b724eb51d5ef7121b1`.
- Post-baseline, pre-T8-cutoff allowlisted evidence:
  - `research/captures/freshness_broker_account/broker_account_20260828T123003+0800_471b06a7.json`: SHA-256 `13a371723ede253a2e157249c29991a4880ee9ba380e4913d9188443269e9240`.
  - `research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T123003+0800_late_continuous.json`: SHA-256 `bc3db37010bd6928009664418b7b0ce7221a6952ce9132f7965877652fea62d2`.
- `.gitignore`: added `data/institutional_mvp/` and `data/.locks/`; `git check-ignore -v` resolved both paths to the new rules and `git status --short -- data` returned no entry.
- Post-cutoff check at `2026-08-28T12:39:12+0800`: still 126 T8 files with the same path-manifest SHA-256 `da0b84ca20a3d43fd377ddd973d4c1ee0bbcd41f22ceb1001f28b4b1531df88d`; no new evidence appeared after the cutoff.
- T8 retention note: scheduled evidence follows the existing repository convention; a separate owner decision is still needed for long-term retention policy.

## Final verification

- Observed at: `2026-08-28T12:41:33+0800`.
- Full suite: `PROVIDER=mock PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q` returned `1 failed, 1784 passed, 88 skipped in 37.82s`. The only failure was the already-deferred T2 `bound target job row drifted` failure.
- Compile: `PYTHONPYCACHEPREFIX=/private/tmp/hyg001_compileall .venv/bin/python -m compileall -q app.py backtest candidate config dashboard features market_data position runtime scoring signals simulation strategy_catalog trading scripts tests` passed.
- Final unstaged `git diff --check` passed. T8 nevertheless remains deferred because the required staged T8 check exposed the immutable evidence trailing whitespace recorded above.
- Remaining `git status --short`: 103 entries, exactly T2 (15 status entries), T8 (87 status entries, 126 expanded files), and T9/PCD-001 (1 status entry). `data/` is now ignored.
- Post-cutoff evidence: none through `2026-08-28T12:41:33+0800`; the T8 expanded manifest remains 126 paths with SHA-256 `da0b84ca20a3d43fd377ddd973d4c1ee0bbcd41f22ceb1001f28b4b1531df88d`.
- Disposition: `PARTIAL / DEFERRED`; HYG-001 is not fully accepted while T2 and T8 remain uncommitted and the full suite is red.

## Successor remediation — owner-authorized 2026-08-28

- Authorization: owner explicitly allowed local successor commits for T2, the exact-two-path T7 drift, T8, and this remediation ledger, including commits beyond the original eight-commit cap. All original no-push/no-PR/no-merge/no-rebase/no-amend/no-reset/no-restore/no-checkout/no-clean/no-stash/no-evidence-deletion constraints remained in force.

### T2 closure

- Reproduction: `PROVIDER=mock PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_finmind_selection_bundle.py::test_phase82_bundle_reproduces_selection_and_status_only_job -q` initially failed with `FinMindSelectionBundleError: bound target job row drifted`.
- Exact live drift from the sealed post-create state: `trading_dates_json`, `calendar_raw_sha256`, `calendar_raw_payload_is_null`, `status`, `status_message`, and `updated_at` advanced; `partition_count` advanced from 0 to 5,816 and `attempt_count` from 0 to 5,817.
- Immutable identity fields remained equal: `calendar_symbol`, `created_at`, `end_date`, `job_id`, `source`, `source_version`, `start_date`, `symbols`, and `volume_unit`.
- Root cause: the selection bundle verifier compared the full mutable status-only job lifecycle row and append-only acquisition counts as if they were immutable post-create identity.
- Remediation semantics: immutable request/selection/target identity remains exact and fail-closed; source files, Dataset identity, snapshot-plan identity, and all sealed digests retain their existing checks. Only the explicit lifecycle fields may advance, counts may only increase, calendar state must be internally consistent, and the stored gzip calendar payload must reproduce `calendar_raw_sha256`.
- Regression coverage confirms lifecycle progress passes while a changed `source_version` still fails with target identity drift.
- Tests:
  - Exact formerly failing test: `1 passed in 7.41s`.
  - Pre-commit T2 focused suite: `34 passed in 5.05s`.
  - Post-commit T2 focused suite: `34 passed in 7.79s`.
- Commit: `48df8f21b3a2dcae5bd4d716828d5864a2f1010e`.
- Exact commit paths: `backtest/finmind_snapshot.py`, `scripts/download_finmind_sponsor_history.py`, `tests/test_finmind_sponsor_history.py`, `backtest/finmind_selection_bundle.py`, `backtest/finmind_source_repair.py`, `backtest/fugle_source_repair.py`, `docs/finmind_source_repair.md`, `scripts/build_finmind_phase82_selection_bundle.py`, `scripts/capture_fugle_source_repair_candidate.py`, `scripts/derive_fugle_source_repair_candidate.py`, `scripts/manage_finmind_source_repair.py`, `scripts/verify_finmind_selection_bundle.py`, `tests/test_finmind_selection_bundle.py`, `tests/test_finmind_source_repair.py`, and `tests/test_fugle_source_repair.py`.

### T7 drift closure

- Bounded observations at `2026-08-28T13:17:17+0800`, `13:17:22+0800`, and `13:17:27+0800` were stable:
  - `.planning/2026-08-28-trading-day-job-audit/findings.md`: 19,466 bytes, mtime `2026-08-28T12:42:31+0800`, SHA-256 `e9f1cdf311470caedc04b62288fe5aeaa68480c1092b443a9faed967b43c1b9c`, exact diff `+9/-0`.
  - `.planning/2026-08-28-trading-day-job-audit/progress.md`: 4,944 bytes, same mtime, SHA-256 `cf6c75800ccfd7912ecdc58832b93d2fc13068b1fa308178f4b5afba5e4d3b1d`, exact diff `+4/-0`.
- `lsof` found only PID 7383 with read-only FDs `989r` and `991r`; `ps` identified it as Apple Virtualization VM XPC. No writable FD or heartbeat process owning either path was found. Writer verdict: `QUIESCENT` for the bounded audit.
- Commit: `7e18cf69202658e59b572cce4565f3079352adec`, containing exactly the two paths above.

### T8 byte-preserving closure

- The prior 126-file subset still reproduced path-manifest SHA-256 `da0b84ca20a3d43fd377ddd973d4c1ee0bbcd41f22ceb1001f28b4b1531df88d` and digest-manifest SHA-256 `ca891622ae6f88d805b807b213e1ce4ff713a64fbf066ad17483e0589fe3e8c2`; therefore all previously recorded evidence bytes were unchanged.
- Final cutoff: `2026-08-28T13:20:59+0800`, 129 exact files, 0 unstable files, 0 `UNCLASSIFIED`.
- Final path-manifest SHA-256: `7f73f23cba3a9faf5aae740c4291785cbf7c758a5f98be401e314931eea580a2`.
- Final per-file digest-manifest SHA-256: `5d268e1f1183c2b2d3077912e325689190428f8b6d8bbe4ab91969d6e8bb52f4`.
- Post-prior-cutoff allowlisted evidence:
  - `research/captures/freshness_quote/quote_20260828T130103+0800.json`: SHA-256 `2e7a0acbe037af2f960574bbc8ae6d8b4263dd43de09969acf07c64a4ab58139`.
  - `research/captures/freshness_broker_account/broker_account_20260828T132004+0800_311c2225.json`: SHA-256 `2893ab91b90c7822ad7bceb1c091952cc1de4d7dd4d5df553f381a2d1c5f828b`.
  - `research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T132004+0800_pre_close.json`: SHA-256 `49ff10f38a88308e05389d5f2e0cb852744aada321e85821ceb96a3ae6dd65d9`.
- Staged path and digest manifests matched the cutoff. Working and index SHA-256 matched for all 129 files with 0 byte mismatches. The commit-tree manifests also reproduced the same two aggregate digests.
- `git diff --cached --check` reported only the owner-exempt legacy trailing whitespace at `research/freshness_calibration/reviews/2026-08-27_1301_close_review.md:5`; no other issue appeared and the exempt bytes were not edited.
- Commit: `55c1b0370e0a8265137aa01b74f9548048fb8117`.
- No post-cutoff evidence appeared through `2026-08-28T13:24:23+0800`.

#### Final T8 exact path and SHA-256 manifest

```text
88e9146a6daeefd4ca67af320fb663e2b5fe14a4d0f55dc808e6be9df76a3e77  records/market_events/2026-08-25/late_delivery_daily_evidence.json
180230da9848bacec9de71a1c472ce0f4fd27726d58a6fd56c1eec45741c9b04  records/market_events/2026-08-25/ldev-20260825T132239-close-55b0624c/bootstrap_snapshot.json
984ac120efea171eaba8686bc295614f38e981e0db1ebdbecdcf0ec9507f53c0  records/market_events/2026-08-25/ldev-20260825T132239-close-55b0624c/instrument_reference.json
66aa492e41e6001710709395e216c4cc24dad49fc9b87e458cf968517157370d  records/market_events/2026-08-25/ldev-20260825T132239-close-55b0624c/manifest.json
8abb7be89fa67126d95ab5f62f561015089c7d151574785e3167786299b9d731  records/market_events/2026-08-25/ldev-20260825T132239-close-55b0624c/passive_capture_report.json
6093e03baee956c2e94b7a0d443a0a4715b9ac6da4bbf3eaf2fc2801c7556fa5  records/market_events/2026-08-25/ldev-20260825T132239-close-55b0624c/records.jsonl
11fa5a9df4f7392ffedc66fa7900a0cc379973a65b257a7254585e24f61f1a78  records/market_events/2026-08-26/late_delivery_daily_evidence.json
00f8ef39e65ac2f9d1f4eb058b59f8753d9050378120088000d4291356939d2a  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/bootstrap_snapshot.json
f2d0d7d5e4b5268e518095ef0a8bc90d4625846e7fc5e1a7d362c1fc05191701  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/instrument_reference.json
706f45a29400c6836b309cdf973957f5e5226004b52cb9b00ac1b9952125de81  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/late_delivery_evidence.json
00be20ca6842da651024dedba6638f4f1d584aa3c470e96d6af4ecfafe121afe  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/manifest.json
7a562d56c932b4d5a9c70010f7d491baf7661e3bd5e285f84b574cfc643f5130  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/passive_capture_report.json
ea13481a3d3d90bc0345acf61273a01ab0d03cf5aff9022fd0eea37c0fbdf5af  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/projection_state.json
4dbe04be51ab9640b8402658ee14713991fce2b8e9fce53a318efd96634f83c9  records/market_events/2026-08-26/ldev-20260826T105708-mid-6687ad05/records.jsonl
c6dade93e2100cbcbe89e146bd5b38106d6f72c1b054a7b0826ecd22b110754c  records/market_events/2026-08-27/late_delivery_daily_evidence.json
529376859111ac10022da75e8fca9acce0f3cf626528748686ff0c9a20b895c7  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/bootstrap_snapshot.json
dac6b553d7650ad7929a781d7bac4cba9c778ce09216da296bed283254395373  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/callback_quarantine.json
38e941694b0e654727cb58995cde10a3406961b81fb495d8a31017491229e512  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/instrument_reference.json
c86fdd7583f5441f83b213d5151c3e2a12ecac92e1e296cdde6445a6c846e82a  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/late_delivery_evidence.json
ef55617a45646d49a43979548fcabe0bf1c64c77eb688f91f7b3808d1bf29936  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/manifest.json
35314bea757d7eb3fe7e9b0ed07b39c0d6507d7ae1e3e8ec0c2c7e911f2577a4  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/passive_capture_report.json
d67321d7cab84245ede2b60d416354d1988ed50581bd6192c5b671ad83171957  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/projection_state.json
210812c81396f473fdb4e3f6c5754447dd0056fbaec2eb6ad961bd471bcd663a  records/market_events/2026-08-27/ldev-20260827T102242-mid-5798b014/records.jsonl
bc6c6671c2acca7dad0f1ca659c09b7a60e358cf7c057190ae0a3a6d35a86be6  records/market_events/2026-08-28/late_delivery_daily_evidence.json
17d5894a28925fc29347330465b1fccd6e5474033756f73225a03e181ad5acbb  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/bootstrap_snapshot.json
056d40f3272b4154b9362d716adf9913cf7fc6a59366175de1a88e2581adae4e  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/callback_quarantine.json
152a5c67dc6985b526f9fa089f3ebfc17a512572607cf6f5fbec9596194c98aa  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/instrument_reference.json
f6e975c7f1f07ba24fa56fa799c3c92768bf504b0ceecdf81e8d1b5a94a0a5c8  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/late_delivery_evidence.json
fb29cd611558ef76b9269f219dfcd2ff131362426943ae177c5872bc408bbd25  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/manifest.json
c68da14dcfbdc61431be1845fe7d396c1ff61f16f6c80a9be632843e2d66adfb  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/passive_capture_report.json
ba641e907242de5c6826797717e38df0f6b952374a319438e296906673e87a84  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/projection_state.json
6b0e68940cbe63409975ba69625b47258700e7cac983978307290fa13c70ea85  records/market_events/2026-08-28/ldev-20260828T102327-mid-a16a920c/records.jsonl
0d817bc11e33112223f1e425c6dd7c0847e2e840fb92a9d4e712c3b89cd8e6ae  research/captures/freshness_broker_account/broker_account_20260825T113006+0800_db202416.json
d4b504858c53fdaa01b27dbf299d282de6e6b2271f386e650b519de533447a31  research/captures/freshness_broker_account/broker_account_20260825T123003+0800_f6764399.json
e810e6f63372c6bae47a9646a32c802cc60994aa426d676f758fc6df34a0858d  research/captures/freshness_broker_account/broker_account_20260825T132005+0800_ec3f4f57.json
47c72533cd70e41ecc0a74f90a0b7c3093945e0bebfce7d8df45d1a38254f994  research/captures/freshness_broker_account/broker_account_20260826T093505+0800_1df6a1b7.json
5419ad15141d29ee3c782e17f29828b5669a86902d4d41eb26907bb6f58cbbf5  research/captures/freshness_broker_account/broker_account_20260826T103005+0800_c78fe88f.json
10d55a31db406c2a13775d25880d78e38a4dd84f07ace58502ff1794a3e5c43d  research/captures/freshness_broker_account/broker_account_20260826T113005+0800_d429f5ac.json
c1d1d9c3dccf46cc2a801ced199311480675900598c3079e59e2003aec6e2ae7  research/captures/freshness_broker_account/broker_account_20260826T123000+0800_2ce20a8d.json
70b76c775a097839f113a7a78bfd896c860e97019ec81b20a583240f6c27f97b  research/captures/freshness_broker_account/broker_account_20260826T132005+0800_d45e29d4.json
987146a54eaca2df68cf6d926f69006bb16b9bb8fa8d812596daccaf389c30eb  research/captures/freshness_broker_account/broker_account_20260827T093505+0800_68aa5d81.json
737a7968b4b6c28e81b532702325ce3913b3cd4ad0833fb3895924612384e029  research/captures/freshness_broker_account/broker_account_20260827T103003+0800_621aa3e6.json
9c1162f2e29f32a48d815d0effb414d689cd487bb1b42c77e0ad40e6e973aec9  research/captures/freshness_broker_account/broker_account_20260827T113005+0800_15815231.json
6e251106863dd989d4c4327bafff7bcea9015f8bd8e3e12fd4ec2f4c127352c2  research/captures/freshness_broker_account/broker_account_20260827T123005+0800_726f83db.json
8db0a4fe78ba80d94a10a1d72b21899f87b6a290ed8bdfa0d53e5dd6a805acfa  research/captures/freshness_broker_account/broker_account_20260827T132001+0800_fbda09af.json
5b2c5d53d7e6031caf717cc07b66fc9bb319108f180f5b897723bf1a655fbebd  research/captures/freshness_broker_account/broker_account_20260828T093505+0800_747cf97f.json
e7300eebf1bff04dc9ab865bc146ef4885a530ef26374ddbb0ade631f0d189ef  research/captures/freshness_broker_account/broker_account_20260828T103005+0800_083c7abd.json
4ea3a0c51e989b13a1c859bd457d5a2fedcc3518e59c65a23810be9588b5d223  research/captures/freshness_broker_account/broker_account_20260828T113004+0800_d86cf3a8.json
13a371723ede253a2e157249c29991a4880ee9ba380e4913d9188443269e9240  research/captures/freshness_broker_account/broker_account_20260828T123003+0800_471b06a7.json
2893ab91b90c7822ad7bceb1c091952cc1de4d7dd4d5df553f381a2d1c5f828b  research/captures/freshness_broker_account/broker_account_20260828T132004+0800_311c2225.json
fd429faf90154e7e7dda234749ec59280ec6d1cb8606742c077b90d254f18951  research/captures/freshness_quote/quote_20260825T110016+0800.json
d8a05cb93e5cce6d80f592d14b1289602ca6688b079c26f3dea70f9aeed26e32  research/captures/freshness_quote/quote_20260825T120014+0800.json
79e883fe1a1e3027caa085d7955d9ee0d21aad0533deff98975ac8ee28228401  research/captures/freshness_quote/quote_20260825T130132+0800.json
69886b2d5fd6805489186e6d29fe57163783930758ba01bf49893c194a493fcc  research/captures/freshness_quote/quote_20260826T090011+0800.json
9782dcad2f6cfe38d110d8917e9ab24a4a2604e1afb13a34efb1dc85a8feb692  research/captures/freshness_quote/quote_20260826T100010+0800.json
6dafab37aed343354cf5b41116e2c902b5899efba8a3c7cf38cabd3deeacf655  research/captures/freshness_quote/quote_20260826T110022+0800.json
f898ea40714b2790824f2c0cf9da0a91c2e547881415b8356c6ae9879eced48b  research/captures/freshness_quote/quote_20260826T120017+0800.json
b1d6714c697a86bc016a203c290e9d1a9cdd4cfbcce63b8ab4076bccf41e8ef1  research/captures/freshness_quote/quote_20260826T130256+0800.json
989e8ac33552190d62afa6cca935bfecf2522fff4ed3bffe76f307d8dc6e10d8  research/captures/freshness_quote/quote_20260827T090011+0800.json
0fd043b7f0749abe085240340337337a5d7ae02fb2eeac9cf15222d31c68535a  research/captures/freshness_quote/quote_20260827T100010+0800.json
a119a873b73d2ddfd0177db427b8ad7e4a8b086f57459616dddd484e2b621448  research/captures/freshness_quote/quote_20260827T110012+0800.json
6ec6bcc6d850787c74c29674c7c16763516ef3adf6580736d0cb4bf352c18f48  research/captures/freshness_quote/quote_20260827T120010+0800.json
70259fbf0377e3f9dbf4bf86bf099dcb12350498357b3e2ece7d3846780a8ebc  research/captures/freshness_quote/quote_20260827T130142+0800.json
56751458de4a300559ba310d7c6d14e909d97719da35639e4871caa90fd9f253  research/captures/freshness_quote/quote_20260828T090014+0800.json
1d680b58e157a4c9123f3d4e69e143e4d447adc706b8f19ba4e26f89d97112ca  research/captures/freshness_quote/quote_20260828T091718+0800.json
024c2e31c76e32039fe268fd6a364e7b8a3ad8869f754112e090d4ecdab3fec1  research/captures/freshness_quote/quote_20260828T100013+0800.json
fdae36e962354c5dcb8880c0d07259c151e2ddc56f744870cc012190994a8292  research/captures/freshness_quote/quote_20260828T110017+0800.json
5bee45145da89cdee2a7f642f76cb1653ea6015d301b3e917228c29ae0d1da3d  research/captures/freshness_quote/quote_20260828T120018+0800.json
2e7a0acbe037af2f960574bbc8ae6d8b4263dd43de09969acf07c64a4ab58139  research/captures/freshness_quote/quote_20260828T130103+0800.json
863798ba323bc6a74f1680a2e2df97faadef3bde48b3b828b3e83b68e83195d1  research/finmind_source_repair_9960_20260320_tpex_daily_v1.json
3cab2519ef03f070d0275f2a3987197319ba675fa0f8adec8a1a40e0614176f8  research/finmind_source_repairs/9960_20260320_credential_rotation_block_v1.json
6e58b3f25e6a88ef8d79bdba0b88bd70e338325f982eed491f7ce7786ce864ff  research/finmind_source_repairs/9960_20260320_fugle_credential_rotation_v1.json
4bd295d72878f7f5a70a514940a443ad1620313cb0032877abb83fcf1c59629e  research/finmind_source_repairs/fugle_9960_20260320_candidate_v1/canonical_bars.json
cc9581da5b8b6d1f61f6bf2e98a3fb48d3650d08bcdb7c68ad67627c8e92f7d2  research/finmind_source_repairs/fugle_9960_20260320_candidate_v1/manifest.canonical.sha256
45233f72819aa758c2aaaabed16f7a5b9cbbfc99365bdaefa5ed0ed391f09b92  research/finmind_source_repairs/fugle_9960_20260320_candidate_v1/manifest.json
586b1f3d06751ff2d139dc3b39467d489c03264b99f846f53a75fe543262951a  research/finmind_source_repairs/fugle_9960_20260320_candidate_v1/validation.json
906be8411e00cecdf62afda0a1e995862d7113a871dba53fa98929f757a46830  research/finmind_source_repairs/fugle_9960_20260320_v1/manifest.canonical.sha256
b9b506aaabc062676deffbcc7ced45cac775ad4ffa8381f97939b51909755611  research/finmind_source_repairs/fugle_9960_20260320_v1/manifest.json
0a86a198b0056ba9f6817592208160f616dde60328ce14131d47bfb64e00b737  research/finmind_source_repairs/fugle_9960_20260320_v1/metadata.json
a02cc385e76125beb54db2ad74f427ce9a17c7ce41661b29574345815f2b3a6f  research/finmind_source_repairs/fugle_9960_20260320_v1/raw_response.bin
87a7bdd85e33b9f45bb606c2502f5772c369459cb89bf2ad405d6f54b1163d7b  research/finmind_source_repairs/fugle_9960_20260320_v1/validation.json
e7f21b5c52649b08ec50bf91419cbcb4da8409718c7624766e091f3ef775d0aa  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260825T113006+0800_continuous.json
01520be1300019ea090f894e738cc311b915649b952ea97376e887383efd0abf  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260825T123003+0800_late_continuous.json
b502b30e248d1f20856ec8e759bb9ae6668e2869b33bc9a2c2d912d52af7562d  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260825T132005+0800_pre_close.json
cb9af1d586649985cd8a4d3f907db89fa4b0b66033c8bbb21005ee74f916539d  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T093505+0800_early_continuous.json
d5fabe33040e160beae2e30f9e310fe2a08dec74a370c26aa65d600c6948705e  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T103005+0800_continuous.json
f7846a6974b5cdd9c3d95bf1cb8227bd268e0c03bcc1f960b0187d7b51d7dec5  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T113005+0800_continuous.json
255666abd0aba68b605f8ce7382673c93cfe2d4f6ba42d2f89d095099958df2f  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T123000+0800_late_continuous.json
f42db465fbc7458c5ad08dcdcc59a51cbb9c4e7c2be5c165ec013a0240f85f89  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260826T132005+0800_pre_close.json
6cf2c7901b0da4e9cd52aa059fb973953e88f133faae4c4974ee987299fa7339  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T093505+0800_early_continuous.json
e14c0d4ec6a1cff3d35854d18c95f26296a7848127b16173ea0f7ef1bfed62d8  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T103003+0800_continuous.json
01d8ae4e38d20a914a9150504650e4d95f6e2043e058814d1497f70c06deee26  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T113005+0800_continuous.json
a6261f5995598c6eca8ebd28ae1f3b8b03951115ac10430d3f55476230542fe1  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T123005+0800_late_continuous.json
ca07f6e85ffb4a45383b6686ed593917bb33f3a787ec0dcbcc3ed9948d71cb30  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260827T132001+0800_pre_close.json
6767bec39653134316220559f94722c232371cc0f361afd84ba21d957ed2929e  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T093505+0800_early_continuous.json
e9fa9dff8d08e4567d09b3be6b675b243bb2a01067e9a934642baa0f69d394b1  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T103005+0800_continuous.json
77715cb4b694b590e6f39cb5d696133a350f0304556886aef7475d1c8d872056  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T113004+0800_continuous.json
bc3db37010bd6928009664418b7b0ce7221a6952ce9132f7965877652fea62d2  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T123003+0800_late_continuous.json
49ff10f38a88308e05389d5f2e0cb852744aada321e85821ceb96a3ae6dd65d9  research/freshness_calibration/broker_account_scheduled_runs/broker_account_run_20260828T132004+0800_pre_close.json
e816dd49c812b1fa6465d89e23b09ac43282057905156a0c490cd8457803cf6e  research/freshness_calibration/reviews/2026-08-25_1301_close_review.md
78470871bc4954289f1b7f3e57b0d902214fcbecb95bf37923bf2d3ecf45e3bb  research/freshness_calibration/reviews/2026-08-26_1302_close_review.md
01c52b1b8d48daa6157ca79ebc6264c59a2bb33e0c23b0e771f312507982cb50  research/freshness_calibration/reviews/2026-08-26_post_session_cross_evidence_review.md
5cc7fa501a641095b9cbdc28838e5dd4adbaa565e161c5baaf8993705d3bc795  research/freshness_calibration/reviews/2026-08-27_1301_close_review.md
d500f5f47753e1594af0443934a1459dbf946d6232cc59e394cf46bedfa2bb03  research/freshness_calibration/scheduled_runs/run_20260825T110000+0800_continuous.json
e5ec8bd422663aaac4d735a21c160ec891e8dedba7c5543408595b6a4e6a0496  research/freshness_calibration/scheduled_runs/run_20260825T120002+0800_continuous.json
a6907fa18131b7e6bcd3793616b9f73dcdddb3db1dad6b7e8cd25fd764dabe21  research/freshness_calibration/scheduled_runs/run_20260826T090000+0800_opening.json
a392b9c074bc96a627ef8845bb5f3486eb6fccb60244ebf3363183d2fbc823a6  research/freshness_calibration/scheduled_runs/run_20260826T100005+0800_continuous.json
87567a94520780ef220c0eb567616c6cdd0a3d75447374aa1a2fef260faeeec5  research/freshness_calibration/scheduled_runs/run_20260826T110006+0800_continuous.json
2eca4e8e035275cbf700d2a4d1fddba435cb223a3e63639cff0acdf5a5e892c0  research/freshness_calibration/scheduled_runs/run_20260826T120005+0800_continuous.json
fb27c01e7891005a55256907c6597c3d1ed01eb465088942fcfeb2c5e6feb45d  research/freshness_calibration/scheduled_runs/run_20260827T090005+0800_opening.json
ca2f19ceda04c4adebf57127e7476ca99f930939508872e970c4892a850a1909  research/freshness_calibration/scheduled_runs/run_20260827T100005+0800_continuous.json
b19091952fe78dbe4203947f85ae1886279c266058d36b6715a20be1ec3b8447  research/freshness_calibration/scheduled_runs/run_20260827T110005+0800_continuous.json
1b3db2ac6a4e441db51d856966612a4cbbd779e710171c5350a7d34a6988919c  research/freshness_calibration/scheduled_runs/run_20260827T120006+0800_continuous.json
60f12e0ab8000d385bfe5abde71c49d9a25099fe16b88f0c9fa22ad24ade2514  research/freshness_calibration/scheduled_runs/run_20260828T090006+0800_opening.json
f10d8dca9fc6039ab0002b4d166e32565eb27a7f641264d2a3ad946faa04b258  research/freshness_calibration/scheduled_runs/run_20260828T091705+0800_opening.json
ade393683dff48d3bdbf1d62ede00cc478ab15315106d969cb3206b5b41f7372  research/freshness_calibration/scheduled_runs/run_20260828T100003+0800_continuous.json
d50b743719fff8ce06bcf82501c809fec56625df39089647e753cb901c15794a  research/freshness_calibration/scheduled_runs/run_20260828T110005+0800_continuous.json
0d16acd20269769904f5c594e6405bf925e55573e39166b724eb51d5ef7121b1  research/freshness_calibration/scheduled_runs/run_20260828T120005+0800_continuous.json
0f70afcd1cdcfa61eb6a5d19b4777836f51b1011aca2c74717a8d23e42d8c6c4  research/late_delivery_evidence/runtime/d_health_open_20260828_calendar_fix.launchagent.plist
907904be24dd06fadd34587856edcb1b14b14961640ccf53a44f85fa1a32156b  research/trade_management_shadow/premarket_20260826_postfix_diagnostic.json
661c3899e3bd33518cc4a3e53a495f7426b8fe11f7778750540a12864cda553b  research/trade_management_shadow/premarket_20260826_postfix_diagnostic.json.sha256
d95689a1253f0c5ed68c7cd97fe8bf8d94a6b1362c81b003aeece077716d80c1  research/trade_management_shadow/premarket_20260826_postfix_diagnostic_v2.json
7126741fafef4bac7e630a505b5f4fda83d7b4af85d6dcac91f9ee786b7259b7  research/trade_management_shadow/premarket_20260826_postfix_diagnostic_v2.json.sha256
5316d07cfdd8884761729ad87dce1a3bb21ef3ecf343fc45ec8d038b93b888d6  research/trade_management_shadow/premarket_20260827.json
cc938cd9a78f56331742dc81647b4844b36cc35be1f40e691d23d8c8f4c79dbf  research/trade_management_shadow/premarket_20260827.json.sha256
fffb6329aba9bfdd40cfb2b239bb0609f63bb830d2602c3c3fba17b77189ad82  research/trade_management_shadow/premarket_20260828.json
690029af0ea07723b5fb0ec720aa49a098fc031e7b80cab3a5b9528335d3f9bc  research/trade_management_shadow/premarket_20260828.json.sha256
4ede8bca968eee6dc13bb6f69a85aa1e0b7e314f997b4cde52011c5505ae58d2  research/trade_management_shadow/session_input_drafts/2026-08-27/review_packet.json
3cd533e319d77e1d80c59949db08cf605a35075127c4bff680308b5d5d810b0a  research/trade_management_shadow/session_input_drafts/2026-08-27/review_packet.json.sha256
```

### Successor final verification

- Full suite: `PROVIDER=mock PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q` returned `1786 passed, 88 skipped in 37.54s`.
- Compile: `PYTHONPYCACHEPREFIX=/private/tmp/hyg001_successor_compileall .venv/bin/python -m compileall -q app.py backtest candidate config dashboard features market_data position runtime scoring signals simulation strategy_catalog trading scripts tests` passed with exit 0.
- PCD-001 handoff remains byte-identical and unstaged: `tests/test_price_coverage_scan_segment_manifest.py`, SHA-256 `b88aa30c74f7c1f0bee7182b5e2cfa29bef737eda341b7670983060e2c5d06f2`.
- Pre-ledger-commit status contained exactly that one PCD-001 path; index was empty, no Git lock remained, and there were no new `UNCLASSIFIED` paths.
- Disposition: successor remediation satisfies the T2, T7, T8, full-suite, compile, byte-preservation, and classification gates. HYG-001 is ready for PCD-001, ARCH-001, and DOC-001; CI-001 remains ordered after PCD-001 as specified by `architecture/hygiene_plans_index.md`.
