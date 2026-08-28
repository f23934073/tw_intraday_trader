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
