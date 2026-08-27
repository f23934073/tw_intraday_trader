#!/usr/bin/env python3
"""Idempotently install the approved R6 G2 schema and sealed matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

from backtest.atomic_benchmark.application import (
    RESEARCH_BASELINE,
    AtomicBenchmarkApplicationService,
    build_matrix_seal_request,
    matrix_activation_request_from_inventory,
    matrix_seal_request_from_inventory,
)
from backtest.atomic_benchmark.domain import build_benchmark_build_binding
from backtest.atomic_benchmark.postgres_repository import (
    AtomicBenchmarkPostgresRepository,
)
from backtest.domain import digest


G2_REVIEWED_COMMIT = "7b7ec7c"
G2_ACTOR_ID = "r6-g2-research-operator"
G2_CHANGE_NOTE = "R6 G2 approved seven-slot benchmark matrix seal"
G2_IDEMPOTENCY_KEY = "r6-g2-seal-matrix-v1"
A1_ACTOR_ID = "r6-g3-a1-research-operator"
A1_CHANGE_NOTE = "R6 Amendment A1 matrix revision 2 activation"
A1_IDEMPOTENCY_KEY = "r6-g3-a1-activate-matrix-revision-2-v1"
_IMPLEMENTATION_PATHS = (
    "backtest/atomic_benchmark/domain.py",
    "backtest/atomic_benchmark/artifacts.py",
    "backtest/atomic_benchmark/repository.py",
    "backtest/atomic_benchmark/postgres_repository.py",
    "backtest/atomic_benchmark/application.py",
    "backtest/atomic_benchmark/result_reader.py",
)


def _reviewed_file(root: Path, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{G2_REVIEWED_COMMIT}:{relative}"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _reviewed_build_binding(root: Path) -> dict[str, object]:
    files = []
    for relative in _IMPLEMENTATION_PATHS:
        payload = _reviewed_file(root, relative)
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
    migration = _reviewed_file(
        root, "backtest/migrations/016_atomic_entry_benchmark.sql"
    )
    return build_benchmark_build_binding(
        algorithm_implementation_digest=digest(implementation_manifest),
        persistence_schema_digest=hashlib.sha256(migration).hexdigest(),
    )


def _request(connection, root: Path) -> dict[str, object]:
    from publish_r6_g1_strategy_versions import binding_inventory

    inventory = binding_inventory(connection)
    current = matrix_seal_request_from_inventory(
        version_inventory=inventory,
        repository_root=root,
        actor_id=G2_ACTOR_ID,
        change_note=G2_CHANGE_NOTE,
    )
    return build_matrix_seal_request(
        research_baseline=RESEARCH_BASELINE,
        protocol_core=current["protocol_core"],
        benchmark_build_binding=_reviewed_build_binding(root),
        slots=current["slots"],
        actor_id=G2_ACTOR_ID,
        change_note=G2_CHANGE_NOTE,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install Migration 016 and seal the approved R6 G2 matrix",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--activate-revision-2",
        action="store_true",
        help="activate the frozen A1 revision 2 after the historical seal",
    )
    arguments = parser.parse_args(argv)
    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R6 G2 matrix seal requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error

    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        operation = (
            "ACTIVATE_MATRIX_REVISION_2"
            if arguments.activate_revision_2
            else "SEAL_MATRIX_REVISION_1"
        )
        idempotency_key = (
            A1_IDEMPOTENCY_KEY
            if arguments.activate_revision_2
            else G2_IDEMPOTENCY_KEY
        )
        if not arguments.execute:
            print(
                json.dumps(
                    {
                        "executed": False,
                        "operation": operation,
                        "reviewed_commit": G2_REVIEWED_COMMIT,
                        "idempotency_key": idempotency_key,
                    },
                    sort_keys=True,
                )
            )
            return 0
        repository = AtomicBenchmarkPostgresRepository(
            connection,
            apply_schema=True,
        )
        service = AtomicBenchmarkApplicationService(repository)
        if arguments.activate_revision_2:
            from publish_r6_g1_strategy_versions import binding_inventory

            result = service.activate_matrix_revision2(
                request=matrix_activation_request_from_inventory(
                    version_inventory=binding_inventory(connection),
                    repository_root=root,
                    actor_id=A1_ACTOR_ID,
                    change_note=A1_CHANGE_NOTE,
                ),
                idempotency_key=A1_IDEMPOTENCY_KEY,
            )
        else:
            result = service.seal_matrix(
                request=_request(connection, root),
                idempotency_key=G2_IDEMPOTENCY_KEY,
            )
    print(
        json.dumps(
            {
                **result,
                "executed": True,
                "operation": operation,
                "reviewed_commit": G2_REVIEWED_COMMIT,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
