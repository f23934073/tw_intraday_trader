#!/usr/bin/env python3
"""Audit R6 G3 source eligibility without strategies, attempts, or DB writes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from backtest.atomic_benchmark.application import (
    AtomicBenchmarkApplicationService,
    amendment_a2_protocol_core,
)
from backtest.atomic_benchmark.domain import (
    FAMILY_ID,
    AtomicBenchmarkIntegrityError,
    canonical_object_bytes,
)
from backtest.atomic_benchmark.postgres_repository import (
    AtomicBenchmarkPostgresRepository,
)
from backtest.atomic_benchmark.preflight import (
    AtomicBenchmarkEligibilityAuditService,
    CanonicalAtomicDatasetAdapter,
    eligibility_audit_implementation_digest,
    verify_eligibility_audit,
)
from backtest.domain import digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--family-id", default=FAMILY_ID)
    parser.add_argument("--matrix-revision-candidate", type=int, default=3)
    parser.add_argument("--dataset-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--progress-every", type=int, default=1_000_000)
    return parser


def _progress(current: int, total: int) -> None:
    print(
        json.dumps(
            {
                "event": "r6_g3_eligibility_audit_progress",
                "bars_read": current,
                "bars_total": total,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _publish_exact(path: Path, value: dict[str, object]) -> None:
    verified = verify_eligibility_audit(value)
    payload = canonical_object_bytes(verified)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = json.loads(path.read_bytes())
            if not isinstance(existing, dict):
                raise AtomicBenchmarkIntegrityError(
                    "eligibility audit artifact is not an object"
                )
            existing_verified = verify_eligibility_audit(existing)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            AtomicBenchmarkIntegrityError,
        ) as error:
            raise RuntimeError("R6 eligibility audit artifact replay conflict") from error
        if (
            path.is_symlink()
            or not path.is_file()
            or existing_verified != verified
            or path.read_bytes() != payload
        ):
            raise RuntimeError("R6 eligibility audit artifact replay conflict")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.progress_every < 1:
        raise ValueError("progress-every must be positive")
    if arguments.matrix_revision_candidate != 3:
        raise ValueError("A2 source audit requires matrix revision candidate 3")
    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R6 eligibility audit requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error

    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        context = AtomicBenchmarkApplicationService(
            AtomicBenchmarkPostgresRepository(connection, apply_schema=False)
        ).get_preflight_context(arguments.family_id)
    candidate_protocol_core_digest = digest(amendment_a2_protocol_core())
    repository_root = Path(__file__).resolve().parents[1]
    audit_scope = {
        "family_id": context["family_id"],
        "active_matrix_id": context["matrix_id"],
        "active_matrix_revision": context["matrix_revision"],
        "active_matrix_registration_digest": context["registration_digest"],
        "active_protocol_core_digest": context["protocol_core_digest"],
        "active_benchmark_build_binding_digest": digest(
            context["benchmark_build_binding"]
        ),
        "research_baseline_digest": context["research_baseline_digest"],
        "dataset_binding_revision": context["research_baseline"][
            "dataset_binding_revision"
        ],
        "family_head_sequence": context["family_head_sequence"],
        "attempt_count": context["attempt_count"],
        "candidate_protocol_core_digest": candidate_protocol_core_digest,
        "candidate_eligibility_audit_implementation_digest": (
            eligibility_audit_implementation_digest(repository_root)
        ),
    }
    preview = {
        "executed": False,
        "family_id": context["family_id"],
        "active_matrix_revision": context["matrix_revision"],
        "matrix_revision_candidate": 3,
        "dataset_id": context["registered_manifest"]["dataset_id"],
        "dataset_bar_count": context["registered_manifest"]["bar_count"],
        "formal_attempts_created": context["attempt_count"],
        "candidate_protocol_core_digest": candidate_protocol_core_digest,
    }
    if not arguments.execute:
        print(json.dumps(preview, sort_keys=True))
        return 0

    dataset_root = arguments.dataset_root or backtest_settings.BACKTEST_DATA_DIR
    output_root = arguments.output_root or (
        backtest_settings.BACKTEST_DATA_DIR
        / "atomic_entry_benchmark"
        / "eligibility_audit"
    )
    dataset = CanonicalAtomicDatasetAdapter(
        root=dataset_root,
        registered_manifest=context["registered_manifest"],
        progress_every=arguments.progress_every,
        progress=_progress,
    )
    audit = AtomicBenchmarkEligibilityAuditService().audit(
        dataset=dataset,
        audit_scope=audit_scope,
        matrix_revision=3,
    )
    artifact_path = output_root / f"{audit['audit_digest']}.json"
    _publish_exact(artifact_path, audit)
    print(
        json.dumps(
            {
                "executed": True,
                "verified": True,
                "audit_digest": audit["audit_digest"],
                "artifact_path": str(artifact_path.resolve()),
                "source_bar_count": audit["source_bar_count"],
                "observed_symbol_session_count": audit[
                    "observed_symbol_session_count"
                ],
                "eligible_symbol_session_count": audit[
                    "eligible_symbol_session_count"
                ],
                "eligible_symbol_session_ratio": audit[
                    "eligible_symbol_session_ratio"
                ],
                "formal_attempts_created": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
