# Institutional dependency map — 2026-08-28

## Freeze identity and method

- Plan: `ARCH-001`
- Source: `main@91323b0683d4e56ce7816ed532eb8c82a4281319`
- Command: `.venv/bin/python scripts/report_institutional_dependencies.py`
- Method: standard-library `ast.parse`; no institutional package is imported or
  executed, and no provider, database, or network resource is accessed.

The report scans every `*.py` below each package, records absolute top-level
imports, and separates imports of repository packages from standard-library and
third-party imports. Repository consumers are split into production, tests, and
scripts. Generated environments and caches are excluded.

## Package imports

| Package | Institutional dependencies | Other project dependencies |
|---|---|---|
| `institutional_data` | none | none |
| `institutional_research` | `institutional_data` | `market_data`, `watchlist` |
| `institutional_prior` | `institutional_data`, `institutional_research` | `watchlist` |
| `institutional_mvp` | `institutional_data` | `backtest` |

The result matches ARCH-001 section 2.1. In particular,
`institutional_mvp` has no dependency on `institutional_research` or
`institutional_prior`, and lineage A has no dependency on `institutional_mvp`.

## Production consumers

| Path | Imported institutional packages |
|---|---|
| `candidate/previous_session.py` | `institutional_prior` |
| `config/institutional_mvp.py` | `institutional_data`, `institutional_mvp` |

The result matches ARCH-001 section 2.2 exactly. The first path is a production
decision path, but it remains a data-only current-session projection that checks
false actionability flags; it is not an order or broker path.

## Test consumers

There are 47 distinct test files with direct institutional imports. Per-package
reference counts intentionally overlap when one file imports more than one
package:

| Package | Referencing test files |
|---|---:|
| `institutional_data` | 40 |
| `institutional_mvp` | 10 |
| `institutional_research` | 6 |
| `institutional_prior` | 3 |

The exact direct test consumers measured at the freeze are:

```text
tests/test_alternative_intraday_source_qualification_artifact.py
tests/test_build_finmind_institutional_mvp_candidates.py
tests/test_credentialed_finmind_intraday_source_probe.py
tests/test_credentialed_finmind_intraday_source_probe_protocol.py
tests/test_credentialed_finmind_intraday_source_probe_protocol_r2.py
tests/test_credentialed_finmind_intraday_source_probe_r2.py
tests/test_credentialed_finmind_pit_reference_probe.py
tests/test_credentialed_intraday_source_probe.py
tests/test_credentialed_intraday_source_probe_protocol.py
tests/test_data_coverage_audit_artifact.py
tests/test_finmind_institutional_mvp.py
tests/test_finmind_institutional_mvp_artifacts.py
tests/test_finmind_institutional_mvp_daily.py
tests/test_finmind_institutional_mvp_series.py
tests/test_finmind_intraday_probe.py
tests/test_finmind_mvp_evaluation_universe.py
tests/test_finmind_mvp_offline_diagnostic.py
tests/test_finmind_pit_reference_semantics_resolution.py
tests/test_formal_evaluation_coverage_amendment.py
tests/test_institutional_candidate_persistence.py
tests/test_institutional_candidate_prior.py
tests/test_institutional_candidate_shadow_admission.py
tests/test_institutional_dataset_acquisition_completion.py
tests/test_institutional_dataset_acquisition_manifest.py
tests/test_institutional_domain.py
tests/test_institutional_factor_diagnostics.py
tests/test_institutional_formal_evaluation.py
tests/test_institutional_formal_evaluation_protocol.py
tests/test_institutional_partition_set_artifact.py
tests/test_institutional_population_coverage_artifact.py
tests/test_institutional_raw_artifacts.py
tests/test_institutional_serialization.py
tests/test_institutional_source_adapters.py
tests/test_institutional_validation.py
tests/test_intraday_source_qualification_artifact.py
tests/test_official_or_licensed_intraday_source_resolution_artifact.py
tests/test_pit_reference_source_resolution_artifact.py
tests/test_pr008_finmind_pit_price_integration.py
tests/test_price_acquisition_resolution_artifact.py
tests/test_price_coverage_audit_contract.py
tests/test_price_coverage_observation_continuation_artifact.py
tests/test_price_coverage_scan_configuration_artifact.py
tests/test_price_coverage_scan_segment_manifest.py
tests/test_price_provider_coverage_resolution_artifact.py
tests/test_price_symbol_resolution_classification_artifact.py
tests/test_run_finmind_institutional_mvp_daily.py
tests/test_run_finmind_institutional_mvp_series.py
```

`tests/test_institutional_module_boundaries.py` is deliberately absent: it
contains no executable institutional import and inspects source only through
AST.

## Script consumers

There are 13 direct script consumers:

```text
scripts/build_credentialed_finmind_intraday_source_probe_result_r2.py
scripts/build_credentialed_finmind_pit_reference_probe_result.py
scripts/build_credentialed_intraday_source_probe_result.py
scripts/build_finmind_institutional_mvp_candidates.py
scripts/build_finmind_mvp_evaluation_universe.py
scripts/capture_finmind_institutional_mvp.py
scripts/capture_finmind_intraday_probe.py
scripts/capture_finmind_pit_reference_probe.py
scripts/capture_fugle_intraday_probe.py
scripts/capture_shioaji_intraday_probe_references.py
scripts/run_finmind_institutional_mvp_daily.py
scripts/run_finmind_institutional_mvp_series.py
scripts/run_finmind_mvp_offline_diagnostic.py
```

These operational/research scripts are not production package consumers and do
not alter the declared production-consumer contract.

## Frozen conclusion

- Lineage A is `institutional_data -> institutional_research -> institutional_prior`.
- Lineage B uses the shared `institutional_data` contracts and
  `institutional_mvp -> backtest`; it does not pass through lineage A.
- Production consumers remain exactly the two declared files.
- No institutional package imports `simulation`, `trading`, `dashboard`, or
  `runtime`.
- Any change to these conclusions must update the ADR and pass
  `tests/test_institutional_module_boundaries.py`.
