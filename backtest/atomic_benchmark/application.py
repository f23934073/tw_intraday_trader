"""Use cases for R6 matrix registration and read-only G3 admission context.

Formal replay, performance calculation, Local Paper, and broker operations are
intentionally absent from this application boundary.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.domain import digest

from .domain import (
    INTEGRITY_REJECTION_CODES,
    RETRYABLE_INFRASTRUCTURE_CODES,
    MatrixSealBuild,
    build_benchmark_build_binding,
    build_matrix_seal,
    build_version_binding,
    classify_attempt_failure,
    require_decimal_text,
    require_exact_fields,
    validate_attempt_transition,
)
from .repository import (
    AtomicBenchmarkConflict,
    BenchmarkMatrixRepositoryPort,
)


MATRIX_SEAL_REQUEST_SCHEMA = "r6-matrix-seal-request-v1"
MATRIX_ACTIVATE_REQUEST_SCHEMA = "r6-matrix-activate-request-v2"
PREFLIGHT_REGISTER_REQUEST_SCHEMA = "r6-preflight-register-request-v1"
PREFLIGHT_REGISTER_RESULT_SCHEMA = "r6-preflight-register-result-v1"
PREFLIGHT_REGISTRATION_SCHEMA = "r6-preflight-registration-v1"

RESEARCH_BASELINE: dict[str, Any] = {
    "schema_version": "r6-research-baseline-v1",
    "research_question_id": "ATOMIC_ENTRY_ABSOLUTE_ZERO_EDGE",
    "research_semantics_id": "FIRST_TRIGGER_ONE_LOT_SAME_SESSION_V1",
    "source_lineage_run_id": "run-91ad87981676414da87b928398fa43c9",
    "dataset_id": "dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6",
    "dataset_manifest_digest": "ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29",
    "dataset_bars_sha256": "216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d",
    "dataset_bar_count": 28325340,
    "dataset_binding_revision": 1,
    "dataset_amount_contract_digest": "12a6d73f22adb46ab8d99024812b3f0944dc03052ef92a3fbe56faba146d90fe",
    "r5_replay_id": "replay-e70d205528ef4e5f891f3d6f3c99997a",
    "r5_result_digest": "420ef2dd3c3e814e0691eef0531c2c6f787789278675d092b86df3e1f9fa3347",
    "r5_postflight_digest": "ca041816dd69454ce53d321fa8a78cb0188a267d5ab2b7c864eb58051a557ad9",
    "planned_attempts": 20,
    "family_alpha": "0.05",
    "adjustment_method": "BONFERRONI",
}

PROTOCOL_CORE: dict[str, Any] = {
    "schema_version": "r6-protocol-core-v2",
    "research_baseline_digest": "75f9efda41f843d95ddc324d2db7756d33415bcc8dbd274e7bc079062a7d4543",
    "source_lineage_run_id": RESEARCH_BASELINE["source_lineage_run_id"],
    "dataset_id": RESEARCH_BASELINE["dataset_id"],
    "dataset_manifest_digest": RESEARCH_BASELINE["dataset_manifest_digest"],
    "dataset_bars_sha256": RESEARCH_BASELINE["dataset_bars_sha256"],
    "dataset_bar_count": 28325340,
    "dataset_binding_revision": 1,
    "dataset_amount_contract_digest": RESEARCH_BASELINE["dataset_amount_contract_digest"],
    "engine_lineage": "backtest-engine-v2",
    "feature_adapter_identity": "backtest.completed-kbar-1m-feature-adapter-v1",
    "input_cadence": "COMPLETED_KBAR_1M_ONLY",
    "signal_admission": (
        "FIRST_TRIGGER_PER_SLOT_SYMBOL_ELIGIBLE_SESSION_"
        "BEFORE_COMMON_CUTOFF_V2"
    ),
    "entry_semantics": (
        "NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_"
        "STRICTLY_AFTER_SIGNAL_AND_NOT_AFTER_COMMON_ENTRY_DEADLINE_V2"
    ),
    "entry_session_semantics": "MUST_EQUAL_SIGNAL_SESSION_V1",
    "shares": 1000,
    "exit_semantics": (
        "EXACT_SAME_SYMBOL_SAME_SESSION_13_30_KBAR_CLOSE_"
        "STRICTLY_AFTER_ENTRY_V2"
    ),
    "entry_slippage_bps": "5",
    "exit_slippage_bps": "5",
    "commission_rate": "0.001425",
    "sell_tax_rate": "0.003",
    "position_cash_semantics": "INDEPENDENT_EPISODES_NO_SHARED_CASH_V1",
    "timezone": "Asia/Taipei",
    "decimal_precision": 38,
    "decimal_rounding": "ROUND_HALF_EVEN",
    "research_window_start": "2023-08-19",
    "research_window_end": "2026-08-18",
    "complete_quarters": [
        "2023Q4", "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1",
        "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2",
    ],
    "family_planned_attempts": 20,
    "family_alpha": "0.05",
    "adjustment_method": "BONFERRONI",
    "adjusted_one_sided_alpha": "0.0025",
    "bootstrap_cluster_unit": "COMPLETE_EXIT_SESSION_DATE",
    "bootstrap_sample_count": 20000,
    "bootstrap_sampler": "SHA256_UINT64_MODULO_V1",
    "bootstrap_seed_semantics": "FAMILY_ID_HYPOTHESIS_ID_BOOTSTRAP_V1",
    "bootstrap_quantile_index": 49,
    "canonical_wire_format": "BACKTEST_CANONICAL_JSON_V1",
    "return_scale": 18,
    "metric_contract_version": "r6-result-summary-v1",
    "bootstrap_contract_version": "r6-daily-cluster-bootstrap-v1",
    "disposition_policy_version": "r6-absolute-zero-edge-screen-v1",
    "minimum_episodes": 30,
    "minimum_independent_exit_dates": 20,
    "minimum_mean_pre_slippage_return": "0",
    "minimum_mean_net_return": "0",
    "minimum_return_profit_factor": "1",
    "minimum_bootstrap_lower_bound": "0",
    "minimum_positive_complete_quarter_count": 7,
    "complete_quarter_count": 11,
    "maximum_daily_equal_signal_drawdown": "0.20",
    "evidence_floor_comparator": "GTE",
    "positive_edge_comparator": "STRICT_GT",
    "quarter_ratio_comparator": "GTE",
    "drawdown_comparator": "LTE",
    "zero_episode_quarter_semantics": "INSUFFICIENT_EVIDENCE",
    "profit_factor_special_semantics": "POSITIVE_INFINITY_ONLY_WITH_POSITIVE_GAINS_AND_ZERO_LOSSES",
    "pairwise_claim_semantics": "PROHIBITED",
    "exploratory_limitation": "EXPLORATORY_ONLY_NO_PROMOTION",
    "common_signal_cutoff_time": "12:45",
    "common_signal_cutoff_comparator": "STRICT_LT",
    "entry_fill_deadline_time": "12:45",
    "entry_fill_deadline_comparator": "LTE",
    "required_terminal_exit_time": "13:30",
    "session_eligibility_semantics": (
        "REQUIRE_EXACT_12_45_ENTRY_RESERVE_AND_13_30_TERMINAL_BAR_V1"
    ),
    "incomplete_signal_semantics": (
        "EXCLUDE_INELIGIBLE_SYMBOL_SESSION_BEFORE_ALL_SLOT_ADMISSION_V1"
    ),
    "eligibility_scope": (
        "COMMON_SYMBOL_SESSION_MASK_SHARED_BY_ALL_SEVEN_SLOTS_V1"
    ),
    "minimum_eligible_symbol_session_ratio": "0.95",
    "eligibility_ratio_scale": 18,
    "eligibility_ratio_comparator": "GTE",
}


def amendment_a2_protocol_core() -> dict[str, Any]:
    """Build the additive revision-3 protocol candidate without activating it."""

    value = dict(PROTOCOL_CORE)
    value.update(
        {
            "schema_version": "r6-protocol-core-v3",
            "signal_admission": (
                "FIRST_TRIGGER_PER_SLOT_SYMBOL_ELIGIBLE_SESSION_"
                "STRICTLY_BEFORE_SOURCE_DERIVED_ENTRY_RESERVE_V3"
            ),
            "entry_semantics": (
                "NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_"
                "STRICTLY_AFTER_SIGNAL_AND_NOT_AFTER_SOURCE_DERIVED_"
                "ENTRY_RESERVE_V3"
            ),
            "session_eligibility_semantics": (
                "REQUIRE_LAST_OBSERVED_KBAR_AT_OR_BEFORE_12_45_WITH_"
                "PRIOR_SIGNAL_OBSERVATION_AND_EXACT_13_30_TERMINAL_BAR_V2"
            ),
            "incomplete_signal_semantics": (
                "EXCLUDE_SOURCE_INELIGIBLE_SYMBOL_SESSION_BEFORE_ALL_"
                "SLOT_ADMISSION_V2"
            ),
            "entry_reserve_selection_semantics": (
                "LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1"
            ),
            "signal_reserve_comparator": "STRICT_LT_ENTRY_RESERVE_AT",
        }
    )
    value.pop("common_signal_cutoff_time")
    value.pop("common_signal_cutoff_comparator")
    return value


def historical_protocol_core() -> dict[str, Any]:
    """Rebuild the immutable revision-1 protocol for durable replay only."""

    value = dict(PROTOCOL_CORE)
    value.update(
        {
            "schema_version": "r6-protocol-core-v1",
            "signal_admission": "FIRST_TRIGGER_PER_SLOT_SYMBOL_SESSION_V1",
            "entry_semantics": (
                "NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_"
                "STRICTLY_AFTER_SIGNAL_V1"
            ),
            "exit_semantics": (
                "LAST_OBSERVED_SAME_SYMBOL_ENTRY_SESSION_CLOSE_"
                "STRICTLY_AFTER_ENTRY_V1"
            ),
        }
    )
    for field in (
        "common_signal_cutoff_time",
        "common_signal_cutoff_comparator",
        "entry_fill_deadline_time",
        "entry_fill_deadline_comparator",
        "required_terminal_exit_time",
        "session_eligibility_semantics",
        "incomplete_signal_semantics",
        "eligibility_scope",
        "minimum_eligible_symbol_session_ratio",
        "eligibility_ratio_scale",
        "eligibility_ratio_comparator",
    ):
        value.pop(field)
    return value

FROZEN_STRATEGY_PARAMETERS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("breakout_previous_high_entry", {"buffer_bps": "0", "entry_window_start": "09:02", "entry_window_end": "12:45"}),
    ("rolling_return_entry", {"window_minutes": 2, "minimum_return_pct": "1.5", "entry_window_start": "09:02", "entry_window_end": "12:45"}),
    ("volume_acceleration_entry", {"window_minutes": 2, "baseline_window_count": 5, "minimum_complete_baseline_windows": 4, "baseline_method": "MEDIAN", "minimum_acceleration_ratio": "1.5", "entry_window_start": "09:10", "entry_window_end": "12:45"}),
    ("opening_range_breakout_entry", {"opening_range_minutes": 15, "breakout_buffer_pct": "0.1", "entry_window_start": "09:15", "entry_window_end": "11:00"}),
    ("ema_crossover_entry", {"fast_period": 5, "slow_period": 20, "entry_window_start": "09:20", "entry_window_end": "12:45"}),
    ("rsi_oversold_entry", {"rsi_period": 14, "oversold_threshold": "30", "entry_window_start": "09:15", "entry_window_end": "12:45"}),
    ("bollinger_lower_reentry_entry", {"bollinger_period": 10, "stddev_multiplier": "2", "entry_window_start": "09:20", "entry_window_end": "12:45"}),
)

FROZEN_VERSION_INVENTORY: tuple[dict[str, Any], ...] = tuple(
    {
        "slot_sequence": slot,
        "strategy_version_id": version_id,
        "version_number": 1,
        "strategy_configuration_digest": configuration_digest,
        "lifecycle_status": "PUBLISHED",
        "lifecycle_sequence": 1,
        "lifecycle_event_id": event_id,
        "lifecycle_projection_digest": projection_digest,
    }
    for slot, version_id, configuration_digest, event_id, projection_digest in (
        (1, "ecbfe315-0a0c-400c-9005-d33bb1db7e62", "71c9825e3dae63177c6895245fe0d56e097b83d2eb755eac93ca812a7dfa6958", "994bdd15-8f53-469e-ae89-303cfa739d8f", "1023d1d3a67aaf2dc8ce5dbd5990b6e9fe55f6c37a32e87516e0360f3f52913a"),
        (2, "c95ade9e-09e2-443d-a6cd-40d576c07e6e", "681aa02fda0e0390b626c7db1be7fa921a0b176ab45a7a5d99608e946b3f2967", "36125a0d-65c5-497e-98a1-2f1c5c6234d7", "0dad68b96affd1c5b42439890b3ceba565091032f1c4a5fdda34ebc580bdb1b9"),
        (3, "f309ccc7-c181-4e69-a0b2-2ec53d48f008", "56751a5c501ac430456120694ca242dc49dc1846fdbd06823817162b805cdf3d", "1acd5936-ab26-41ce-8575-5db54202a183", "42322dd7b2a2a51c839458f8ffee68f6ccf5bb0f772c817dcc99b15e15152004"),
        (4, "1460fd64-37c3-4bc6-a2d1-53e89fc5f3b6", "a99f9896b877a4373c5943fba8ea80992e9f4c8723f9e93ce6bc13f0c8684b3b", "e1faf74f-19d5-4f56-9c67-4bded688f23d", "5793e1735fed7ffca86e6f279e38a2770521a0c86f71da8dbae90bc4062e5864"),
        (5, "31c55c80-ab96-4f81-8d5c-ed1c57ec471d", "1f898e9c17b067ab89613a97bf7511557a28af9166474bb362db97cacae3a334", "0998a459-7bf3-460b-b2b3-760a4d7d8c68", "ac778c92f0e05a3f6454b8f88ff4739409e502d8d4cba3a901e6b3848bbb3f2a"),
        (6, "701483dc-6efe-446a-aa76-1b5526c07d07", "f90f85c194bee56b587712d213c6eda06207242ea5770d8549441f1cc98a4ed3", "c63c55e7-6bed-439d-89ab-7f39f737ab6d", "ffb8fca2acf1cbcadfb6acb444490d0c872fecdea0a822f57d1cb92647e4ac96"),
        (7, "9cc0c8e9-2e4f-4245-9307-533a1927bbfd", "1143834e51682660121ba74b7118e3e3dc7485da5be55e766bd33d8a45fc81ae", "16ee83b3-328e-4265-ae16-0ff19c840875", "46e2cfbbf6b3d94569ac5337a410cef56d2d62b2a793e5bc738d36fb3fc4e257"),
    )
)


def frozen_hypothesis_specs(
    protocol_core: Mapping[str, Any] = PROTOCOL_CORE,
) -> tuple[dict[str, Any], ...]:
    """Rebuild the seven G0 specs from the deployed strategy/Feature registries."""

    from atomic_strategies.feature_requests import resolve_feature_requests
    from atomic_strategies.registry import AtomicStrategyRegistry
    from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
    from features.specifications import FeatureSpecificationRegistry
    from strategy_catalog.parameter_schema import canonical_digest

    registry = AtomicStrategyRegistry()
    feature_registry = FeatureSpecificationRegistry()
    values: list[dict[str, Any]] = []
    for slot, (strategy_id, raw_parameters) in enumerate(
        FROZEN_STRATEGY_PARAMETERS, start=1
    ):
        template = registry.strategy(strategy_id).template
        parameters = template.validate_parameters(raw_parameters)
        configuration = {
            "strategy_id": strategy_id,
            "parameters": parameters,
            "parameter_schema_version": template.parameter_schema.version,
            "parameter_schema_digest": template.parameter_schema.schema_digest,
            "parameters_digest": canonical_digest(parameters),
            "template_digest": template.template_digest,
            "implementation_digest": template.implementation_digest,
        }
        request = resolve_feature_requests(template, parameters)[0]
        specification = feature_registry.get(request.feature_id)
        values.append(
            {
                "schema_version": "r6-hypothesis-spec-v1",
                "slot_sequence": slot,
                "strategy_id": strategy_id,
                "parameters": parameters,
                "parameters_digest": canonical_digest(parameters),
                "strategy_configuration_digest": canonical_digest(configuration),
                "template_digest": template.template_digest,
                "parameter_schema_digest": template.parameter_schema.schema_digest,
                "strategy_implementation_digest": template.implementation_digest,
                "backtest_runtime_binding": template.runtime_bindings["BACKTEST_KBAR_1M"],
                "feature_id": request.feature_id,
                "feature_parameters": dict(request.parameters),
                "feature_parameter_digest": request.parameter_digest,
                "feature_request_identity_digest": request.request_digest,
                "feature_specification_digest": specification.specification_digest,
                "feature_implementation_digest": specification.implementation_digest,
                "feature_runtime_identity_digest": request.runtime_identity_digest(
                    adapter_identity=CompletedOneMinuteKbarFeatureAdapter.identity,
                    cadence=specification.cadence,
                ),
                "protocol_core_digest": digest(dict(protocol_core)),
            }
        )
    return tuple(values)


def current_benchmark_build_binding(repository_root: Path) -> dict[str, Any]:
    """Bind exact A1 algorithm, preflight, and Migration 016/017 bytes."""

    relative_paths = (
        "backtest/atomic_benchmark/domain.py",
        "backtest/atomic_benchmark/artifacts.py",
        "backtest/atomic_benchmark/repository.py",
        "backtest/atomic_benchmark/postgres_repository.py",
        "backtest/atomic_benchmark/application.py",
        "backtest/atomic_benchmark/result_reader.py",
    )
    files = []
    for relative in relative_paths:
        payload = (repository_root / relative).read_bytes()
        files.append(
            {
                "path": relative,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    implementation_manifest = {
        "schema_version": "r6-algorithm-source-manifest-v1",
        "files": files,
    }
    preflight_paths = (
        "backtest/atomic_benchmark/preflight.py",
        "backtest/atomic_strategy_adapter.py",
        "scripts/preflight_atomic_entry_benchmark.py",
    )
    preflight_files = []
    for relative in preflight_paths:
        payload = (repository_root / relative).read_bytes()
        preflight_files.append(
            {
                "path": relative,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    preflight_manifest = {
        "schema_version": "r6-preflight-source-manifest-v2",
        "files": preflight_files,
    }
    persistence_paths = (
        "backtest/migrations/016_atomic_entry_benchmark.sql",
        "backtest/migrations/017_r6_matrix_revision_and_preflight.sql",
    )
    persistence_files = []
    for relative in persistence_paths:
        payload = (repository_root / relative).read_bytes()
        persistence_files.append(
            {
                "path": relative,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    persistence_manifest = {
        "schema_version": "r6-persistence-source-manifest-v2",
        "files": persistence_files,
    }
    return build_benchmark_build_binding(
        algorithm_implementation_digest=digest(implementation_manifest),
        preflight_implementation_digest=digest(preflight_manifest),
        persistence_schema_digest=digest(persistence_manifest),
    )


def historical_benchmark_build_binding(repository_root: Path) -> dict[str, Any]:
    """Rebuild a revision-1-compatible binding for historical seal replay."""

    relative_paths = (
        "backtest/atomic_benchmark/domain.py",
        "backtest/atomic_benchmark/artifacts.py",
        "backtest/atomic_benchmark/repository.py",
        "backtest/atomic_benchmark/postgres_repository.py",
        "backtest/atomic_benchmark/application.py",
        "backtest/atomic_benchmark/result_reader.py",
    )
    files = []
    for relative in relative_paths:
        payload = (repository_root / relative).read_bytes()
        files.append(
            {
                "path": relative,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    implementation_manifest = {
        "schema_version": "r6-algorithm-source-manifest-v1",
        "files": files,
    }
    migration = (
        repository_root / "backtest/migrations/016_atomic_entry_benchmark.sql"
    ).read_bytes()
    return build_benchmark_build_binding(
        algorithm_implementation_digest=digest(implementation_manifest),
        persistence_schema_digest=hashlib.sha256(migration).hexdigest(),
    )


def matrix_seal_request_from_inventory(
    *,
    version_inventory: Sequence[Mapping[str, Any]],
    repository_root: Path,
    actor_id: str,
    change_note: str,
) -> dict[str, Any]:
    """Combine G1 durable bindings with the seven frozen G0 specifications."""

    if len(version_inventory) != 7:
        raise ValueError("R6 G1 inventory must contain exactly seven Versions")
    protocol = historical_protocol_core()
    specs = frozen_hypothesis_specs(protocol)
    slots = []
    for expected, (specification, inventory) in enumerate(
        zip(specs, version_inventory, strict=True), start=1
    ):
        if inventory.get("slot_sequence") != expected:
            raise ValueError("R6 G1 inventory slot order drift")
        binding = build_version_binding(
            hypothesis_spec_digest=specification["hypothesis_spec_digest"]
            if "hypothesis_spec_digest" in specification
            else digest(specification),
            strategy_version_id=str(inventory["strategy_version_id"]),
            version_number=int(inventory["version_number"]),
            strategy_configuration_digest=str(
                inventory["strategy_configuration_digest"]
            ),
            lifecycle_status=str(inventory["lifecycle_status"]),
            lifecycle_sequence=int(inventory["lifecycle_sequence"]),
            lifecycle_event_id=str(inventory["lifecycle_event_id"]),
            lifecycle_projection_digest=str(
                inventory["lifecycle_projection_digest"]
            ),
        )
        slots.append(
            {"hypothesis_spec": specification, "version_binding": binding}
        )
    return build_matrix_seal_request(
        research_baseline=RESEARCH_BASELINE,
        protocol_core=protocol,
        benchmark_build_binding=historical_benchmark_build_binding(repository_root),
        slots=slots,
        actor_id=actor_id,
        change_note=change_note,
    )


def matrix_activation_request_from_inventory(
    *,
    version_inventory: Sequence[Mapping[str, Any]],
    repository_root: Path,
    actor_id: str,
    change_note: str,
) -> dict[str, Any]:
    """Build the frozen revision-2 activation request from durable Versions."""

    if len(version_inventory) != 7:
        raise ValueError("R6 A1 inventory must contain exactly seven Versions")
    specs = frozen_hypothesis_specs()
    slots = []
    for expected, (specification, inventory) in enumerate(
        zip(specs, version_inventory, strict=True), start=1
    ):
        if inventory.get("slot_sequence") != expected:
            raise ValueError("R6 A1 inventory slot order drift")
        binding = build_version_binding(
            hypothesis_spec_digest=digest(specification),
            strategy_version_id=str(inventory["strategy_version_id"]),
            version_number=int(inventory["version_number"]),
            strategy_configuration_digest=str(
                inventory["strategy_configuration_digest"]
            ),
            lifecycle_status=str(inventory["lifecycle_status"]),
            lifecycle_sequence=int(inventory["lifecycle_sequence"]),
            lifecycle_event_id=str(inventory["lifecycle_event_id"]),
            lifecycle_projection_digest=str(
                inventory["lifecycle_projection_digest"]
            ),
        )
        slots.append({"hypothesis_spec": specification, "version_binding": binding})
    return build_matrix_activation_request(
        research_baseline=RESEARCH_BASELINE,
        protocol_core=PROTOCOL_CORE,
        benchmark_build_binding=current_benchmark_build_binding(repository_root),
        slots=slots,
        actor_id=actor_id,
        change_note=change_note,
    )


_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "expected_family_head_sequence",
        "research_baseline",
        "protocol_core",
        "benchmark_build_binding",
        "slots",
        "actor_id",
        "change_note",
    }
)
_ACTIVATE_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "expected_active_matrix_revision",
        "expected_family_head_sequence",
        "expected_attempt_count",
        "research_baseline",
        "protocol_core",
        "benchmark_build_binding",
        "slots",
        "actor_id",
        "change_note",
    }
)
_PREFLIGHT_REGISTRATION_FIELDS = frozenset(
    {
        "schema_version",
        "preflight_id",
        "family_id",
        "matrix_id",
        "matrix_revision",
        "matrix_registration_digest",
        "protocol_core_digest",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "dataset_binding_revision",
        "eligibility_manifest_digest",
        "preflight_digest",
        "preflight_implementation_digest",
        "status",
    }
)
_PREFLIGHT_REGISTER_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "family_id",
        "matrix_id",
        "matrix_revision",
        "expected_active_matrix_revision",
        "expected_family_head_sequence",
        "expected_attempt_count",
        "preflight_id",
        "preflight_digest",
        "eligibility_manifest_digest",
        "preflight_registration_digest",
        "actor_id",
        "change_note",
    }
)


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def build_matrix_seal_request(
    *,
    research_baseline: Mapping[str, Any],
    protocol_core: Mapping[str, Any],
    benchmark_build_binding: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]],
    actor_id: str,
    change_note: str,
) -> dict[str, Any]:
    return {
        "schema_version": MATRIX_SEAL_REQUEST_SCHEMA,
        "expected_family_head_sequence": 0,
        "research_baseline": dict(research_baseline),
        "protocol_core": dict(protocol_core),
        "benchmark_build_binding": dict(benchmark_build_binding),
        "slots": [dict(slot) for slot in slots],
        "actor_id": _nonempty(actor_id, "actor_id"),
        "change_note": _nonempty(change_note, "change_note"),
    }


def verify_matrix_seal_request(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], MatrixSealBuild]:
    request = dict(value)
    require_exact_fields(request, _REQUEST_FIELDS, "matrix seal request")
    if request["schema_version"] != MATRIX_SEAL_REQUEST_SCHEMA:
        raise ValueError("R6 matrix seal request schema drift")
    expected = request["expected_family_head_sequence"]
    if isinstance(expected, bool) or not isinstance(expected, int) or expected != 0:
        raise AtomicBenchmarkConflict("R6_FAMILY_HEAD_SEQUENCE_CONFLICT")
    _nonempty(request["actor_id"], "actor_id")
    _nonempty(request["change_note"], "change_note")
    if not isinstance(request["slots"], list):
        raise ValueError("slots must be an ordered JSON array")
    build = build_matrix_seal(
        research_baseline=request["research_baseline"],
        protocol_core=request["protocol_core"],
        benchmark_build_binding=request["benchmark_build_binding"],
        slot_inputs=request["slots"],
    )
    return request, build


def build_matrix_activation_request(
    *,
    research_baseline: Mapping[str, Any],
    protocol_core: Mapping[str, Any],
    benchmark_build_binding: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]],
    actor_id: str,
    change_note: str,
) -> dict[str, Any]:
    return {
        "schema_version": MATRIX_ACTIVATE_REQUEST_SCHEMA,
        "expected_active_matrix_revision": 1,
        "expected_family_head_sequence": 0,
        "expected_attempt_count": 0,
        "research_baseline": dict(research_baseline),
        "protocol_core": dict(protocol_core),
        "benchmark_build_binding": dict(benchmark_build_binding),
        "slots": [dict(slot) for slot in slots],
        "actor_id": _nonempty(actor_id, "actor_id"),
        "change_note": _nonempty(change_note, "change_note"),
    }


def verify_matrix_activation_request(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], MatrixSealBuild]:
    request = dict(value)
    require_exact_fields(request, _ACTIVATE_REQUEST_FIELDS, "matrix activation request")
    if request["schema_version"] != MATRIX_ACTIVATE_REQUEST_SCHEMA:
        raise ValueError("R6 matrix activation request schema drift")
    exact_expectations = {
        "expected_active_matrix_revision": 1,
        "expected_family_head_sequence": 0,
        "expected_attempt_count": 0,
    }
    for field, expected in exact_expectations.items():
        value = request[field]
        if type(value) is not int or value != expected:
            raise AtomicBenchmarkConflict("R6_MATRIX_ACTIVATION_PRECONDITION_CONFLICT")
    _nonempty(request["actor_id"], "actor_id")
    _nonempty(request["change_note"], "change_note")
    if not isinstance(request["slots"], list):
        raise ValueError("slots must be an ordered JSON array")
    build = build_matrix_seal(
        research_baseline=request["research_baseline"],
        protocol_core=request["protocol_core"],
        benchmark_build_binding=request["benchmark_build_binding"],
        slot_inputs=request["slots"],
    )
    if build.matrix_core["matrix_revision"] != 2:
        raise AtomicBenchmarkConflict("R6_MATRIX_IDENTITY_CONFLICT")
    return request, build


def build_preflight_registration(
    *, manifest: Mapping[str, Any], matrix_registration_digest: str
) -> dict[str, Any]:
    preflight_digest = str(manifest["preflight_digest"])
    registration = {
        "schema_version": PREFLIGHT_REGISTRATION_SCHEMA,
        "preflight_id": f"r6-preflight-sha256-{preflight_digest}",
        "family_id": str(manifest["family_id"]),
        "matrix_id": str(manifest["matrix_id"]),
        "matrix_revision": 2,
        "matrix_registration_digest": matrix_registration_digest,
        "protocol_core_digest": str(manifest["protocol_core_digest"]),
        "dataset_id": str(manifest["dataset_id"]),
        "dataset_digest": str(manifest["dataset_digest"]),
        "dataset_bars_sha256": str(manifest["dataset_bars_sha256"]),
        "dataset_binding_revision": manifest["dataset_binding_revision"],
        "eligibility_manifest_digest": str(
            manifest["eligibility_manifest_digest"]
        ),
        "preflight_digest": preflight_digest,
        "preflight_implementation_digest": str(
            manifest["preflight_implementation_digest"]
        ),
        "status": "ACCEPTED",
    }
    require_exact_fields(
        registration, _PREFLIGHT_REGISTRATION_FIELDS, "preflight registration"
    )
    if type(registration["dataset_binding_revision"]) is not int:
        raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
    for field in (
        "matrix_registration_digest",
        "protocol_core_digest",
        "dataset_digest",
        "dataset_bars_sha256",
        "eligibility_manifest_digest",
        "preflight_digest",
        "preflight_implementation_digest",
    ):
        value = registration[field]
        if not isinstance(value, str) or len(value) != 64:
            raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
    return registration


def build_preflight_register_request(
    *,
    registration: Mapping[str, Any],
    actor_id: str,
    change_note: str,
) -> dict[str, Any]:
    return {
        "schema_version": PREFLIGHT_REGISTER_REQUEST_SCHEMA,
        "family_id": registration["family_id"],
        "matrix_id": registration["matrix_id"],
        "matrix_revision": 2,
        "expected_active_matrix_revision": 2,
        "expected_family_head_sequence": 0,
        "expected_attempt_count": 0,
        "preflight_id": registration["preflight_id"],
        "preflight_digest": registration["preflight_digest"],
        "eligibility_manifest_digest": registration[
            "eligibility_manifest_digest"
        ],
        "preflight_registration_digest": digest(registration),
        "actor_id": _nonempty(actor_id, "actor_id"),
        "change_note": _nonempty(change_note, "change_note"),
    }


def verify_preflight_register_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(value)
    require_exact_fields(
        request, _PREFLIGHT_REGISTER_REQUEST_FIELDS, "preflight register request"
    )
    if request["schema_version"] != PREFLIGHT_REGISTER_REQUEST_SCHEMA:
        raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
    for field, expected in {
        "matrix_revision": 2,
        "expected_active_matrix_revision": 2,
        "expected_family_head_sequence": 0,
        "expected_attempt_count": 0,
    }.items():
        if type(request[field]) is not int or request[field] != expected:
            raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
    for field in (
        "family_id",
        "matrix_id",
        "preflight_id",
        "actor_id",
        "change_note",
    ):
        _nonempty(request[field], field)
    for field in (
        "preflight_digest",
        "eligibility_manifest_digest",
        "preflight_registration_digest",
    ):
        value = request[field]
        if not isinstance(value, str) or len(value) != 64:
            raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
    if request["preflight_id"] != f"r6-preflight-sha256-{request['preflight_digest']}":
        raise AtomicBenchmarkConflict("R6_PREFLIGHT_INTEGRITY_ERROR")
    return request


class AtomicBenchmarkApplicationService:
    def __init__(self, repository: BenchmarkMatrixRepositoryPort) -> None:
        self._repository = repository

    def seal_matrix(
        self, *, request: Mapping[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        key = _nonempty(idempotency_key, "idempotency_key")
        request_body, build = verify_matrix_seal_request(request)
        result, replayed = self._repository.seal_matrix(
            build=build,
            idempotency_key=key,
            request=request_body,
            request_digest=digest(request_body),
            actor_id=str(request_body["actor_id"]),
            change_note=str(request_body["change_note"]),
        )
        return {**result, "replayed": replayed}

    def activate_matrix_revision2(
        self, *, request: Mapping[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        key = _nonempty(idempotency_key, "idempotency_key")
        request_body, build = verify_matrix_activation_request(request)
        result, replayed = self._repository.activate_matrix_revision2(
            build=build,
            idempotency_key=key,
            request=request_body,
            request_digest=digest(request_body),
            actor_id=str(request_body["actor_id"]),
            change_note=str(request_body["change_note"]),
        )
        return {**result, "replayed": replayed}

    def register_preflight(
        self,
        *,
        manifest: Mapping[str, Any],
        matrix_registration_digest: str,
        artifact_locator: str,
        idempotency_key: str,
        actor_id: str,
        change_note: str,
    ) -> dict[str, Any]:
        registration = build_preflight_registration(
            manifest=manifest,
            matrix_registration_digest=matrix_registration_digest,
        )
        request = verify_preflight_register_request(
            build_preflight_register_request(
                registration=registration,
                actor_id=actor_id,
                change_note=change_note,
            )
        )
        result, replayed = self._repository.register_preflight(
            request=request,
            request_digest=digest(request),
            manifest=dict(manifest),
            artifact_locator=_nonempty(artifact_locator, "artifact_locator"),
            idempotency_key=_nonempty(idempotency_key, "idempotency_key"),
            actor_id=request["actor_id"],
            change_note=request["change_note"],
        )
        return {**result, "replayed": replayed}

    def get_matrix(self, family_id: str) -> dict[str, Any]:
        return self._repository.get_matrix(_nonempty(family_id, "family_id"))

    def get_preflight_context(self, family_id: str) -> dict[str, Any]:
        return self._repository.get_preflight_context(
            _nonempty(family_id, "family_id")
        )

    def start_next_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        expected_family_head_sequence: int,
        idempotency_key: str,
        actor_id: str,
        change_note: str,
        expected_preflight_id: str,
        expected_preflight_registration_digest: str,
    ) -> dict[str, Any]:
        if (
            isinstance(expected_family_head_sequence, bool)
            or not isinstance(expected_family_head_sequence, int)
            or not 0 <= expected_family_head_sequence < 7
        ):
            raise AtomicBenchmarkConflict("R6_FAMILY_HEAD_SEQUENCE_CONFLICT")
        request = {
            "schema_version": "r6-attempt-start-request-v1",
            "family_id": _nonempty(family_id, "family_id"),
            "matrix_id": _nonempty(matrix_id, "matrix_id"),
            "expected_family_head_sequence": expected_family_head_sequence,
            "actor_id": _nonempty(actor_id, "actor_id"),
            "change_note": _nonempty(change_note, "change_note"),
            "expected_preflight_id": _nonempty(
                expected_preflight_id, "expected_preflight_id"
            ),
            "expected_preflight_registration_digest": _nonempty(
                expected_preflight_registration_digest,
                "expected_preflight_registration_digest",
            ),
        }
        result, replayed = self._repository.start_next_attempt(
            family_id=request["family_id"],
            matrix_id=request["matrix_id"],
            expected_family_head_sequence=expected_family_head_sequence,
            idempotency_key=_nonempty(idempotency_key, "idempotency_key"),
            request=request,
            request_digest=digest(request),
            actor_id=request["actor_id"],
        )
        return {**result, "replayed": replayed}

    def request_attempt_cancellation(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        retry_generation: int,
        idempotency_key: str,
        actor_id: str,
    ) -> dict[str, Any]:
        return self._transition_attempt(
            family_id=family_id,
            matrix_id=matrix_id,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            expected_status="RUNNING",
            next_status="CANCELLING",
            retry_generation=retry_generation,
            outcome_code="OPERATOR_CANCELLED",
            progress=None,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
        )

    def complete_attempt_cancellation(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        retry_generation: int,
        progress: str,
        idempotency_key: str,
        actor_id: str,
    ) -> dict[str, Any]:
        next_status = (
            "CANCELLED_FINAL" if retry_generation == 4 else "CANCELLED_RETRYABLE"
        )
        return self._transition_attempt(
            family_id=family_id,
            matrix_id=matrix_id,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            expected_status="CANCELLING",
            next_status=next_status,
            retry_generation=retry_generation,
            outcome_code="OPERATOR_CANCELLED",
            progress=progress,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
        )

    def retry_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        expected_status: str,
        retry_generation: int,
        progress: str,
        idempotency_key: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if expected_status not in {"FAILED_RETRYABLE", "CANCELLED_RETRYABLE"}:
            raise AtomicBenchmarkConflict("R6_ATTEMPT_RETRY_STATUS_CONFLICT")
        return self._transition_attempt(
            family_id=family_id,
            matrix_id=matrix_id,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            expected_status=expected_status,
            next_status="RUNNING",
            retry_generation=retry_generation,
            outcome_code="ATTEMPT_RETRY_STARTED",
            progress=progress,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
        )

    def seal_retryable_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        expected_status: str,
        retry_generation: int,
        progress: str,
        idempotency_key: str,
        actor_id: str,
    ) -> dict[str, Any]:
        mapping = {
            "FAILED_RETRYABLE": (
                "FAILED_FINAL",
                "OPERATOR_SEALED_TECHNICAL_FAILURE",
            ),
            "CANCELLED_RETRYABLE": (
                "CANCELLED_FINAL",
                "OPERATOR_SEALED_CANCELLATION",
            ),
        }
        try:
            next_status, outcome_code = mapping[expected_status]
        except KeyError as error:
            raise AtomicBenchmarkConflict(
                "R6_ATTEMPT_SEAL_STATUS_CONFLICT"
            ) from error
        return self._transition_attempt(
            family_id=family_id,
            matrix_id=matrix_id,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            expected_status=expected_status,
            next_status=next_status,
            retry_generation=retry_generation,
            outcome_code=outcome_code,
            progress=progress,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
        )

    def record_attempt_failure(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        retry_generation: int,
        progress: str,
        error: BaseException,
        idempotency_key: str,
        actor_id: str,
    ) -> dict[str, Any]:
        outcome_code = classify_attempt_failure(error)
        if outcome_code in INTEGRITY_REJECTION_CODES:
            next_status = "REJECTED_FINAL"
        elif outcome_code in RETRYABLE_INFRASTRUCTURE_CODES:
            next_status = (
                "FAILED_FINAL" if retry_generation == 4 else "FAILED_RETRYABLE"
            )
        else:
            next_status = "FAILED_FINAL"
        return self._transition_attempt(
            family_id=family_id,
            matrix_id=matrix_id,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            expected_status="RUNNING",
            next_status=next_status,
            retry_generation=retry_generation,
            outcome_code=outcome_code,
            progress=progress,
            idempotency_key=idempotency_key,
            actor_id=actor_id,
        )

    def _transition_attempt(
        self,
        *,
        family_id: str,
        matrix_id: str,
        attempt_id: str,
        expected_revision: int,
        expected_status: str,
        next_status: str,
        retry_generation: int,
        outcome_code: str,
        progress: str | None,
        idempotency_key: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise AtomicBenchmarkConflict("R6_ATTEMPT_REVISION_CONFLICT")
        next_generation = validate_attempt_transition(
            current_status=expected_status,
            next_status=next_status,
            retry_generation=retry_generation,
            outcome_code=outcome_code,
        )
        if progress is not None:
            require_decimal_text(progress, "progress", nonnegative=True, maximum_scale=6)
            if Decimal(progress) > 1:
                raise ValueError("progress must be <= 1")
        request = {
            "schema_version": "r6-attempt-transition-request-v1",
            "family_id": _nonempty(family_id, "family_id"),
            "matrix_id": _nonempty(matrix_id, "matrix_id"),
            "attempt_id": _nonempty(attempt_id, "attempt_id"),
            "expected_revision": expected_revision,
            "expected_status": expected_status,
            "next_status": next_status,
            "retry_generation": retry_generation,
            "next_retry_generation": next_generation,
            "outcome_code": outcome_code,
            "progress": progress,
            "actor_id": _nonempty(actor_id, "actor_id"),
        }
        result, replayed = self._repository.transition_attempt(
            family_id=request["family_id"],
            matrix_id=request["matrix_id"],
            attempt_id=request["attempt_id"],
            expected_revision=expected_revision,
            expected_status=expected_status,
            next_status=next_status,
            retry_generation=retry_generation,
            outcome_code=outcome_code,
            progress=progress,
            idempotency_key=_nonempty(idempotency_key, "idempotency_key"),
            request=request,
            request_digest=digest(request),
            actor_id=request["actor_id"],
        )
        return {**result, "replayed": replayed}
