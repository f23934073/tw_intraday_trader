# Ruff static-analysis baseline — 2026-08-28

## Scope and identity

- Plan: `CI-001`
- Source: `18c08713e4bb953457ab531db133c96d2b9132dd`
- Ruff: `0.16.3`
- Target: repository Python files, excluding `.venv`, `build`, `data`, `records`, `research`, and `.planning`
- Tests retain the planned narrow `F401`/`F811` exceptions; package `__init__.py` files retain the planned `F401` re-export exception.

The unconfigured informational pass reported 1,586 findings because Ruff's defaults were broader than the first CI gate. Applying the plan's original selection (`F`, `E4`, `E7`, `E9`, `I`, `UP`, `B`, with `B008` excluded) produced 706 findings and triggered the plan's mandatory `>500` decision gate. The owner then authorized `F + E9` as the first blocking gate.

## Original planned selection: decision baseline

### Findings by rule

| Rule | Count |
|---|---:|
| `I001` | 372 |
| `UP035` | 121 |
| `E402` | 82 |
| `UP037` | 33 |
| `B905` | 27 |
| `UP017` | 26 |
| `F401` | 15 |
| `B904` | 12 |
| `UP012` | 6 |
| `F841` | 4 |
| `B009` | 3 |
| `E731` | 2 |
| `F821` | 2 |
| `UP042` | 1 |
| **Total** | **706** |

### Findings by top-level directory

| Directory | Count |
|---|---:|
| `tests` | 190 |
| `scripts` | 171 |
| `backtest` | 102 |
| `market_data` | 66 |
| `runtime` | 22 |
| `trading` | 22 |
| `strategy_catalog` | 19 |
| `institutional_mvp` | 17 |
| `features` | 16 |
| `simulation` | 13 |
| `atomic_strategies` | 12 |
| `premarket` | 12 |
| `dashboard` | 10 |
| `institutional_research` | 10 |
| `config` | 9 |
| `institutional_data` | 4 |
| `candidate` | 2 |
| `signals` | 2 |
| `watchlist` | 2 |
| `institutional_prior` | 1 |
| `position` | 1 |
| `scoring` | 1 |

| Cohort | Count |
|---|---:|
| Production (excluding `scripts`) | 345 |
| `tests` | 190 |
| `scripts` | 171 |

### Top 10 files

| File | Count |
|---|---:|
| `scripts/replay_momentum_signal.py` | 15 |
| `scripts/run_price_coverage_r3_scan.py` | 10 |
| `scripts/run_scheduled_quote_freshness.py` | 10 |
| `market_data/provider.py` | 8 |
| `backtest/qualification.py` | 7 |
| `market_data/late_delivery_evidence.py` | 7 |
| `scripts/download_backtest_history.py` | 7 |
| `scripts/derive_backtest_daily_dataset.py` | 6 |
| `scripts/import_backtest_dataset.py` | 6 |
| `scripts/run_one_shot_late_delivery_open.py` | 6 |

`strategy_catalog/postgres_repository.py` also had 6 findings; it follows the displayed top 10 under the deterministic count/path ordering used for this report.

## High-risk findings

| Rule | Location | Disposition |
|---|---|---|
| `F821` | `tests/test_atomic_entry_benchmark_postgres.py:1487` | Real test defect: SQL assertion was unreachable inside `pytest.raises` and used an undefined `cursor`; fixed directly without suppression. |
| `F821` | `tests/test_atomic_entry_benchmark_postgres.py:1494` | Same defect and direct fix as above. |
| `F841` | `dashboard/server.py:1209` | Removed only the unused exception binding; bare re-raise behavior is unchanged. |
| `F841` | `strategy_catalog/postgres_repository.py:77` | Removed unused `template_document` local; SQL parameters remain unchanged. |
| `F841` | `tests/test_late_delivery_capture.py:253` | Removed unused saved bound method. |
| `F841` | `tests/test_signal_ledger_replay_artifacts.py:176` | Removed unused manifest local. |

No `F811` or `F402` findings were present. No `noqa`, per-file exception, or hard-coded bypass was added for the two `F821` defects.

## Authorized first blocking gate

### Baseline before fixes

| Rule | Count |
|---|---:|
| `F401` | 15 |
| `F841` | 4 |
| `F821` | 2 |
| `E9` family | 0 |
| **Total** | **21** |

| Directory | Count |
|---|---:|
| `backtest` | 7 |
| `tests` | 4 |
| `market_data` | 3 |
| `scripts` | 3 |
| `strategy_catalog` | 2 |
| `dashboard` | 1 |
| `premarket` | 1 |

| Cohort | Count |
|---|---:|
| Production (excluding `scripts`) | 14 |
| `tests` | 4 |
| `scripts` | 3 |

### Final result

`python -m ruff check .` reports `All checks passed!`. The 685 findings belonging only to deferred `I`, `UP`, `B`, `E4`, and `E7` rules are recorded baseline debt and are not hidden inside the first blocking gate. Any expansion requires a separate staged cleanup plan.
