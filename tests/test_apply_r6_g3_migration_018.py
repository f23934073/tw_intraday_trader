from __future__ import annotations

from pathlib import Path

import pytest

from backtest.atomic_benchmark.domain import (
    AtomicBenchmarkIntegrityError,
    canonical_object_bytes,
)
from backtest.domain import digest
from scripts import apply_r6_g3_migration_018 as migration_cli
from tests.test_audit_atomic_entry_benchmark_eligibility import _audit


ROOT = Path(__file__).resolve().parents[1]


def _context() -> dict[str, object]:
    sha = "a" * 64
    return {
        "family_id": "family-test",
        "matrix_id": "matrix-test-v2",
        "matrix_revision": 2,
        "registration_digest": sha,
        "protocol_core_digest": sha,
        "benchmark_build_binding": {"schema_version": "binding-test"},
        "research_baseline_digest": sha,
        "research_baseline": {"dataset_binding_revision": 1},
        "registered_manifest": {
            "dataset_id": "dataset-test",
            "manifest_digest": sha,
            "bars_sha256": sha,
            "bar_count": 1,
        },
        "family_head_sequence": 0,
        "attempt_count": 0,
    }


def _artifact(tmp_path: Path, context: dict[str, object]) -> Path:
    value = _audit()
    value.update(
        migration_cli._audit_scope(
            context=context,
            repository_root=ROOT,
        )
    )
    body = {key: item for key, item in value.items() if key != "audit_digest"}
    value["audit_digest"] = digest(body)
    path = tmp_path / f"{value['audit_digest']}.json"
    path.write_bytes(canonical_object_bytes(value))
    return path


def test_migration_018_accepts_exact_current_audit_scope(tmp_path: Path) -> None:
    context = _context()
    path = _artifact(tmp_path, context)

    audit = migration_cli._load_accepted_audit(
        path=path,
        context=context,
        repository_root=ROOT,
    )

    assert audit["eligible_symbol_session_ratio"] == "1.000000000000000000"
    assert audit["active_matrix_revision"] == 2
    assert audit["attempt_count"] == 0


def test_migration_018_rejects_current_scope_drift(tmp_path: Path) -> None:
    context = _context()
    path = _artifact(tmp_path, context)
    context["matrix_id"] = "replacement-matrix"

    with pytest.raises(AtomicBenchmarkIntegrityError, match="scope conflict"):
        migration_cli._load_accepted_audit(
            path=path,
            context=context,
            repository_root=ROOT,
        )
