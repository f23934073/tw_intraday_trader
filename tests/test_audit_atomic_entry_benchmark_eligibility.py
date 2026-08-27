from __future__ import annotations

from pathlib import Path

import pytest

from backtest.atomic_benchmark.domain import (
    AtomicBenchmarkIntegrityError,
    canonical_object_bytes,
)
from backtest.atomic_benchmark.preflight import verify_eligibility_audit
from backtest.domain import digest
from scripts import audit_atomic_entry_benchmark_eligibility as audit_cli


def _scope() -> dict[str, object]:
    sha = "b" * 64
    return {
        "family_id": "family-test",
        "active_matrix_id": "matrix-test-v2",
        "active_matrix_revision": 2,
        "active_matrix_registration_digest": sha,
        "active_protocol_core_digest": sha,
        "active_benchmark_build_binding_digest": sha,
        "research_baseline_digest": sha,
        "dataset_binding_revision": 1,
        "family_head_sequence": 0,
        "attempt_count": 0,
        "candidate_protocol_core_digest": sha,
        "candidate_eligibility_audit_implementation_digest": sha,
    }


def _audit() -> dict[str, object]:
    sha = "a" * 64
    body = {
        "schema_version": "r6-eligibility-source-audit-v2",
        **_scope(),
        "matrix_revision_candidate": 3,
        "dataset_id": "dataset-test",
        "dataset_digest": sha,
        "dataset_bars_sha256": sha,
        "dataset_bar_count": 1,
        "source_bar_count": 1,
        "source_bars_sha256": sha,
        "source_eof_verified": True,
        "entry_reserve_selection_semantics": (
            "LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1"
        ),
        "required_terminal_exit_time": "13:30",
        "observed_symbol_session_count": 1,
        "eligible_symbol_session_count": 1,
        "excluded_symbol_session_count": 0,
        "eligible_symbol_session_ratio": "1.000000000000000000",
        "minimum_eligible_symbol_session_ratio": "0.95",
        "missing_entry_reserve_count": 0,
        "missing_signal_observation_count": 0,
        "missing_terminal_exit_count": 0,
        "yearly": [
            {
                "year": 2026,
                "observed_symbol_session_count": 1,
                "eligible_symbol_session_count": 1,
                "eligible_symbol_session_ratio": "1.000000000000000000",
                "missing_entry_reserve_count": 0,
                "missing_signal_observation_count": 0,
                "missing_terminal_exit_count": 0,
            }
        ],
        "symbols": [
            {
                "symbol": "2330",
                "observed_symbol_session_count": 1,
                "eligible_symbol_session_count": 1,
                "eligible_symbol_session_ratio": "1.000000000000000000",
                "missing_entry_reserve_count": 0,
                "missing_signal_observation_count": 0,
                "missing_terminal_exit_count": 0,
            }
        ],
    }
    return {**body, "audit_digest": digest(body)}


def test_publish_exact_replays_identical_audit(tmp_path: Path) -> None:
    path = tmp_path / "audit.json"
    value = _audit()

    audit_cli._publish_exact(path, value)
    first = path.read_bytes()
    audit_cli._publish_exact(path, value)

    assert first == canonical_object_bytes(value)
    assert path.read_bytes() == first
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_publish_exact_rejects_existing_drift(tmp_path: Path) -> None:
    path = tmp_path / "audit.json"
    path.write_bytes(b"{}")

    with pytest.raises(RuntimeError, match="replay conflict"):
        audit_cli._publish_exact(
            path,
            _audit(),
        )


def test_audit_verifier_rejects_self_consistent_year_total_tamper() -> None:
    value = _audit()
    value["yearly"][0]["missing_terminal_exit_count"] = 1
    body = {key: item for key, item in value.items() if key != "audit_digest"}
    value["audit_digest"] = digest(body)

    with pytest.raises(AtomicBenchmarkIntegrityError, match="yearly totals"):
        verify_eligibility_audit(value)


def test_audit_verifier_rejects_self_consistent_scope_substitution() -> None:
    value = _audit()
    value["family_id"] = "foreign-family"
    body = {key: item for key, item in value.items() if key != "audit_digest"}
    value["audit_digest"] = digest(body)

    with pytest.raises(AtomicBenchmarkIntegrityError, match="scope conflict"):
        verify_eligibility_audit(value, expected_scope=_scope())


def test_audit_verifier_rejects_symbol_total_tamper() -> None:
    value = _audit()
    value["symbols"][0]["eligible_symbol_session_count"] = 0
    value["symbols"][0]["eligible_symbol_session_ratio"] = "0.000000000000000000"
    body = {key: item for key, item in value.items() if key != "audit_digest"}
    value["audit_digest"] = digest(body)

    with pytest.raises(AtomicBenchmarkIntegrityError, match="symbol totals"):
        verify_eligibility_audit(value)
