"""Drift gates for immutable, configuration-pinned coverage-scan segments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text
from scripts.build_price_coverage_source_drift_acknowledgement import (
    DRIFT_STATUS,
    canonical_seal_errors,
    check_acknowledgement,
    evaluate_source_drift,
)
from scripts.download_backtest_history import _resume_command


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research/institutional_evaluation/acquisition"
R0 = ACQUISITION / "price_coverage_scan_segment_v1_2026-08-21-r0.json"
R1 = ACQUISITION / "price_coverage_scan_segment_v1_2026-08-21-r1.json"
R2 = ACQUISITION / "price_coverage_scan_configuration_v1_2026-08-21-r2.json"
R1_CONFIG = ACQUISITION / "price_coverage_scan_configuration_v1_2026-08-21.json"
ACKNOWLEDGEMENT = (
    ACQUISITION / "price_coverage_source_drift_acknowledgement_v1.json"
)
PINNED_SOURCE_FIELDS = {
    "backtest/historical_download.py": "historical_downloader_source_sha256",
    "scripts/download_backtest_history.py": "cli_source_sha256",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return path.with_suffix(".canonical.sha256").read_text(encoding="utf-8").strip()


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_pins(r2: dict[str, Any]) -> dict[str, str]:
    scan = r2["scan_configuration"]
    return {path: scan[field] for path, field in PINNED_SOURCE_FIELDS.items()}


def test_sealed_segments_have_distinct_configuration_lineage() -> None:
    r0 = _load(R0)
    r1 = _load(R1)
    r1_config = _load(R1_CONFIG)

    assert sha256_text(canonical_json(r0)) == _digest(R0)
    assert sha256_text(canonical_json(r1)) == _digest(R1)
    assert r0["configuration_binding"] == {
        "binding_kind": "PRE_COVERAGE_TRUSTED_CHECKPOINT_PROVENANCE",
        "price_acquisition_resolution": {
            "artifact_id": "price-acquisition-resolution-v1-2026-08-20-r1",
            "canonical_sha256": "6eb6cb4719d999ba49eec46c814383fbfb00b9cf1533f88b8837e9da1c41b5b9",
        },
        "scan_configuration": None,
    }
    assert r1["configuration_binding"]["scan_configuration"] == {
        "artifact_id": r1_config["artifact_id"],
        "canonical_sha256": _digest(R1_CONFIG),
    }


def test_r0_and_r1_snapshot_boundaries_are_complete_and_metadata_only() -> None:
    r0 = _load(R0)
    r1 = _load(R1)

    assert r0["segment"] == {
        "ordinal": 0,
        "segment_id": "pre-coverage-trusted-checkpoints-r0",
        "target_index_inclusive_end": 410,
        "target_index_inclusive_start": 0,
        "target_index_semantics": "ORIGINAL_JOB_REQUEST_ORDER",
        "target_count": 411,
    }
    assert r0["metadata_snapshot"]["observation_status_counts"] == {
        "NON_EMPTY_SUCCESS": 411
    }
    assert r1["segment"]["target_index_inclusive_start"] == 411
    assert r1["segment"]["target_index_inclusive_end"] == 677
    assert r1["metadata_snapshot"]["observation_status_counts"] == {
        "NON_EMPTY_SUCCESS": 259,
        "PRICE_DATA_UNAVAILABLE": 8,
    }
    assert r1["legacy_empty_revalidation"] == {
        "initial_pending_count_at_r1_configuration_snapshot": 72,
        "policy": "REOBSERVE_FROM_EARLIEST_LEGACY_EMPTY_BEFORE_NEW_TARGETS",
        "remaining_pending_count_at_r1_boundary": 0,
        "result": "ALL_R1_SCOPE_LEGACY_EMPTY_ROWS_REOBSERVED_UNDER_R1_CONTINUATION_POLICY",
    }
    assert r1["safe_pause_boundary"] == {
        "event_code": "RATE_LIMITED",
        "job_status": "PAUSED",
        "no_partial_partition_written": True,
        "next_target_index": 678,
        "observed_at": "2026-08-21T10:44:50.180685+08:00",
        "retry_symbol": "2101",
    }
    assert all(
        segment["metadata_snapshot"]["payloads_or_price_values_read"] is False
        for segment in (r0, r1)
    )
    assert all(
        value is False
        for segment in (r0, r1)
        for value in segment["execution_lock"].values()
    )


def test_r2_configuration_is_frozen_before_resume_and_pins_new_taxonomy() -> None:
    r0 = _load(R0)
    r1 = _load(R1)
    r2 = _load(R2)

    assert sha256_text(canonical_json(r2)) == _digest(R2)
    assert r2["prior_segments"] == [
        {"artifact_id": r0["artifact_id"], "canonical_sha256": _digest(R0)},
        {"artifact_id": r1["artifact_id"], "canonical_sha256": _digest(R1)},
    ]
    assert r2["resume_boundary"] == {
        "activation_rule": "REGISTERED_BEFORE_RESUME",
        "next_target_index": 678,
        "prior_pause_event": "RATE_LIMITED",
        "prior_pause_observed_at": "2026-08-21T10:44:50.180685+08:00",
        "retry_symbol": "2101",
    }
    scan = r2["scan_configuration"]
    assert scan["coverage_scan_mode"] is True
    for field in PINNED_SOURCE_FIELDS.values():
        source_pin = scan[field]
        assert isinstance(source_pin, str)
        assert len(source_pin) == 64
        assert all(character in "0123456789abcdef" for character in source_pin)
    assert scan["invocation_command"].endswith(
        "--continue-on-empty-for-coverage-audit"
    )
    assert scan["per_symbol_failure_policy"] == {
        "PRICE_DATA_UNAVAILABLE": "WRITE_ZERO_BAR_ERROR_OBSERVATION_AND_CONTINUE",
        "SYMBOL_MAPPING_ERROR": "WRITE_ZERO_BAR_ERROR_OBSERVATION_AND_CONTINUE",
        "TEMPORARY_FETCH_FAILURE": "WRITE_ZERO_BAR_ERROR_OBSERVATION_AND_CONTINUE",
    }
    assert scan["whole_job_failure_policy"] == {
        "RATE_LIMITED": "WRITE_NO_PARTIAL_PARTITION_AND_SAFE_PAUSE"
    }
    assert r2["summary_lineage_policy"] == {
        "final_raw_scan_summary_source": "AGGREGATE_SEALED_SEGMENT_MANIFESTS",
        "mixed_configuration_without_segment_reference_allowed": False,
        "r2_segment_required_before_its_observations_can_enter_summary": True,
    }
    assert all(value is False for value in r2["execution_lock"].values())


def test_pinned_scan_sources_have_no_unacknowledged_drift() -> None:
    r2 = _load(R2)
    pins = _source_pins(r2)
    live_shas = {path: _source_sha256(ROOT / path) for path in pins}
    errors = evaluate_source_drift(pins, live_shas, _load(ACKNOWLEDGEMENT))

    assert errors == [], "source drift review required:\n" + "\n".join(errors)


def test_drift_acknowledgement_is_canonically_sealed() -> None:
    acknowledgement = _load(ACKNOWLEDGEMENT)

    assert canonical_seal_errors(
        acknowledgement,
        _digest(ACKNOWLEDGEMENT),
        label="source drift acknowledgement",
    ) == []
    assert acknowledgement["pinned_configuration"] == {
        "artifact_path": str(R2.relative_to(ROOT)),
        "artifact_canonical_sha256": _digest(R2),
    }
    assert acknowledgement["reuse_constraint"].startswith(
        "任何重新執行、續跑或延伸此 r2 coverage scan"
    )


def test_drift_acknowledgement_matches_reviewed_builder() -> None:
    assert check_acknowledgement() == []


def test_unacknowledged_source_drift_fails_closed() -> None:
    errors = evaluate_source_drift(
        {"source.py": "a" * 64},
        {"source.py": "b" * 64},
        {"pinned_sources": []},
    )

    assert errors == ["unacknowledged source drift: source.py"]


def test_stale_acknowledgement_fails_closed() -> None:
    errors = evaluate_source_drift(
        {"source.py": "a" * 64},
        {"source.py": "c" * 64},
        {
            "pinned_sources": [
                {
                    "path": "source.py",
                    "pinned_sha256": "a" * 64,
                    "observed_sha256_at_acknowledgement": "b" * 64,
                    "drift_status": DRIFT_STATUS,
                }
            ]
        },
    )

    assert errors == ["stale source drift acknowledgement: source.py"]


def test_tampered_acknowledgement_digest_fails_closed(tmp_path: Path) -> None:
    acknowledgement = {
        "artifact_id": "fixture-acknowledgement",
        "pinned_sources": [],
    }
    acknowledgement_path = tmp_path / "acknowledgement.json"
    digest_path = acknowledgement_path.with_suffix(".canonical.sha256")
    acknowledgement_path.write_text(
        canonical_json(acknowledgement) + "\n", encoding="utf-8"
    )
    digest_path.write_text(
        sha256_text(canonical_json(acknowledgement)) + "\n", encoding="utf-8"
    )
    acknowledgement["pinned_sources"] = [{"path": "tampered.py"}]
    acknowledgement_path.write_text(
        canonical_json(acknowledgement) + "\n", encoding="utf-8"
    )

    errors = canonical_seal_errors(
        _load(acknowledgement_path),
        digest_path.read_text(encoding="utf-8").strip(),
        label="source drift acknowledgement",
    )

    assert len(errors) == 1
    assert errors[0].startswith("source drift acknowledgement canonical digest mismatch")


def test_coverage_resume_command_preserves_explicit_scan_mode() -> None:
    job_id = "dataset-download-fixture"

    assert _resume_command(job_id, coverage_scan_mode=True).endswith(
        "--resume dataset-download-fixture --continue-on-empty-for-coverage-audit"
    )
    assert _resume_command(job_id, coverage_scan_mode=False).endswith(
        "--resume dataset-download-fixture"
    )
