#!/usr/bin/env python3
"""Build or verify the provider-free R6 G3 seven-slot preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_benchmark.application import AtomicBenchmarkApplicationService
from backtest.atomic_benchmark.domain import FAMILY_ID
from backtest.atomic_benchmark.postgres_repository import (
    AtomicBenchmarkPostgresRepository,
)
from backtest.atomic_benchmark.preflight import (
    AtomicBenchmarkPreflightService,
    CanonicalAtomicDatasetAdapter,
    PreflightSlotRuntime,
    preflight_implementation_digest,
    verify_preflight_artifact,
)
from backtest.atomic_strategy_adapter import AtomicBacktestStrategyAdapter
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the provider-free R6 G3 seven-slot Dataset preflight",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--family-id", default=FAMILY_ID)
    parser.add_argument("--dataset-root", type=Path, default=None)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--progress-every", type=int, default=1_000_000)
    parser.add_argument(
        "--idempotency-key", default="r6-g3-register-a1-preflight-v1"
    )
    parser.add_argument("--actor-id", default="r6-g3-research-operator")
    parser.add_argument(
        "--change-note", default="R6 G3 A1 full-Dataset preflight registration"
    )
    return parser


def _progress(current: int, total: int) -> None:
    print(
        json.dumps(
            {
                "event": "r6_g3_dataset_progress",
                "bars_read": current,
                "bars_total": total,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _slot_runtime(
    *,
    source: Mapping[str, Any],
    context: Mapping[str, Any],
    catalog: PostgresAtomicStrategyRepository,
    registry: AtomicStrategyRegistry,
) -> PreflightSlotRuntime:
    specification = dict(source["hypothesis_spec"])
    version_binding = dict(source["version_binding"])
    version = catalog.get_version(str(source["strategy_version_id"]))
    implementation = registry.strategy(version.strategy_id)
    requests = resolve_feature_requests(implementation.template, version.parameters)
    if (
        version.strategy_id != specification["strategy_id"]
        or version.configuration_digest
        != specification["strategy_configuration_digest"]
        or version.implementation_digest
        != specification["strategy_implementation_digest"]
        or version_binding["strategy_version_id"] != version.strategy_version_id
        or version_binding["strategy_configuration_digest"]
        != version.configuration_digest
        or version_binding["lifecycle_status"] != "PUBLISHED"
        or source["hypothesis_id"] != source["slot_binding"]["hypothesis_id"]
        or len(requests) != 1
        or requests[0].request_digest
        != specification["feature_request_identity_digest"]
    ):
        raise RuntimeError("R6 G3 slot runtime identity drift")
    baseline = context["research_baseline"]
    build_binding = context["benchmark_build_binding"]
    identity = {
        "matrix_id": context["matrix_id"],
        "registration_digest": context["registration_digest"],
        "family_id": context["family_id"],
        "research_baseline_digest": context["research_baseline_digest"],
        "slot_sequence": source["slot_sequence"],
        "hypothesis_id": source["hypothesis_id"],
        "strategy_id": specification["strategy_id"],
        "strategy_version_id": source["strategy_version_id"],
        "strategy_configuration_digest": specification[
            "strategy_configuration_digest"
        ],
        "strategy_implementation_digest": specification[
            "strategy_implementation_digest"
        ],
        "lifecycle_sequence": version_binding["lifecycle_sequence"],
        "lifecycle_event_id": version_binding["lifecycle_event_id"],
        "lifecycle_projection_digest": version_binding[
            "lifecycle_projection_digest"
        ],
        "dataset_id": baseline["dataset_id"],
        "dataset_digest": baseline["dataset_manifest_digest"],
        "dataset_bars_sha256": baseline["dataset_bars_sha256"],
        "dataset_binding_revision": baseline["dataset_binding_revision"],
        "protocol_core_digest": context["protocol_core_digest"],
        "algorithm_contract_digest": build_binding["algorithm_contract_digest"],
        "algorithm_implementation_digest": build_binding[
            "algorithm_implementation_digest"
        ],
    }
    return PreflightSlotRuntime(
        identity=identity,
        feature_request_identity_digest=str(
            specification["feature_request_identity_digest"]
        ),
        strategy=AtomicBacktestStrategyAdapter(
            implementation,
            version,
            requests,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.progress_every < 1:
        raise ValueError("progress-every must be positive")
    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R6 G3 preflight requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error

    repository_root = Path(__file__).resolve().parents[1]
    dataset_root = arguments.dataset_root or backtest_settings.BACKTEST_DATA_DIR
    artifact_root = arguments.artifact_root or (
        backtest_settings.BACKTEST_DATA_DIR / "atomic_entry_benchmark" / "preflight"
    )
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        benchmark_repository = AtomicBenchmarkPostgresRepository(
            connection,
            apply_schema=False,
        )
        context = AtomicBenchmarkApplicationService(
            benchmark_repository
        ).get_preflight_context(arguments.family_id)
        if not arguments.execute:
            print(
                json.dumps(
                    {
                        "executed": False,
                        "family_id": context["family_id"],
                        "matrix_id": context["matrix_id"],
                        "matrix_revision": context["matrix_revision"],
                        "dataset_id": context["registered_manifest"]["dataset_id"],
                        "dataset_bar_count": context["registered_manifest"][
                            "bar_count"
                        ],
                        "slot_count": len(context["slots"]),
                        "family_head_sequence": context["family_head_sequence"],
                        "attempt_count": context["attempt_count"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        catalog = PostgresAtomicStrategyRepository(connection)
        registry = AtomicStrategyRegistry()
        slots = tuple(
            _slot_runtime(
                source=source,
                context=context,
                catalog=catalog,
                registry=registry,
            )
            for source in context["slots"]
        )

    dataset = CanonicalAtomicDatasetAdapter(
        root=dataset_root,
        registered_manifest=context["registered_manifest"],
        progress_every=arguments.progress_every,
        progress=_progress,
    )
    implementation_digest = preflight_implementation_digest(repository_root)
    if implementation_digest != context["benchmark_build_binding"].get(
        "preflight_implementation_digest"
    ):
        raise RuntimeError("R6 G3 preflight implementation differs from matrix seal")
    build = AtomicBenchmarkPreflightService(artifact_root).build(
        slots=slots,
        dataset=dataset,
        family_id=context["family_id"],
        matrix_id=context["matrix_id"],
        registration_digest=context["registration_digest"],
        research_baseline_digest=context["research_baseline_digest"],
        protocol_core_digest=context["protocol_core_digest"],
        dataset_binding_revision=int(
            context["research_baseline"]["dataset_binding_revision"]
        ),
        algorithm_implementation_digest=context["benchmark_build_binding"][
            "algorithm_implementation_digest"
        ],
        preflight_implementation_digest=implementation_digest,
        matrix_revision=int(context["matrix_revision"]),
    )
    verified = verify_preflight_artifact(
        build.path,
        expected_manifest=build.manifest,
    )
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        benchmark_repository = AtomicBenchmarkPostgresRepository(
            connection,
            apply_schema=False,
        )
        registration = AtomicBenchmarkApplicationService(
            benchmark_repository
        ).register_preflight(
            manifest=verified.manifest,
            matrix_registration_digest=context["registration_digest"],
            artifact_locator=str(verified.path.resolve()),
            idempotency_key=arguments.idempotency_key,
            actor_id=arguments.actor_id,
            change_note=arguments.change_note,
        )
    print(
        json.dumps(
            {
                "executed": True,
                "verified": True,
                "family_id": verified.manifest["family_id"],
                "matrix_id": verified.manifest["matrix_id"],
                "preflight_digest": verified.preflight_digest,
                "source_bar_count": verified.manifest["source_bar_count"],
                "slot_count": len(verified.slot_roots),
                "artifact_path": str(verified.path),
                "preflight_id": registration["preflight_id"],
                "preflight_registration_digest": registration[
                    "preflight_registration_digest"
                ],
                "registration_replayed": registration["replayed"],
                "family_head_sequence": 0,
                "attempt_count": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
