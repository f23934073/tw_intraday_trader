"""Drift gates for the PR-008 dataset-acquisition inventory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "dataset_acquisition_manifest_v1_2026-08-20.json"
)
MANIFEST_DIGEST = MANIFEST.with_suffix(".canonical.sha256")
PROTOCOL = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "protocols"
    / "formal_evaluation_gate_v1.json"
)
PROTOCOL_DIGEST = PROTOCOL.with_suffix(".canonical.sha256")
COVERAGE = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "coverage"
    / "population_coverage_v1_2026-08-20.json"
)
COVERAGE_DIGEST = COVERAGE.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_acquisition_manifest_canonical_digest_is_frozen() -> None:
    manifest = _load(MANIFEST)
    expected = MANIFEST_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(manifest)) == expected
    assert manifest["schema_version"] == (
        "institutional_dataset_acquisition_manifest_v1"
    )
    assert manifest["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"


def test_acquisition_manifest_references_frozen_upstream_evidence() -> None:
    manifest = _load(MANIFEST)
    protocol = _load(PROTOCOL)
    coverage = _load(COVERAGE)
    protocol_digest = PROTOCOL_DIGEST.read_text(encoding="utf-8").strip()
    coverage_digest = COVERAGE_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(protocol)) == protocol_digest
    assert sha256_text(canonical_json(coverage)) == coverage_digest
    assert manifest["protocol_reference"] == {
        "artifact_id": protocol["artifact_id"],
        "canonical_sha256": protocol_digest,
    }
    assert manifest["coverage_reference"] == {
        "artifact_id": coverage["artifact_id"],
        "canonical_sha256": coverage_digest,
    }


def test_only_actual_immutable_artifacts_count_as_acquired() -> None:
    datasets = _load(MANIFEST)["datasets"]
    required = {
        "price",
        "institutional",
        "pit_universe",
        "corporate_actions",
        "reference_data",
        "trading_calendar",
    }

    assert set(datasets) == required
    for name in required - {"trading_calendar"}:
        dataset = datasets[name]
        assert dataset["status"] == "MISSING"
        assert dataset["artifact_count"] == 0
        assert dataset["artifact_id"] is None
        assert dataset["canonical_sha256"] is None
        assert dataset["acquired_markets"] == []

    calendar = datasets["trading_calendar"]
    assert calendar["status"] == "PARTIAL"
    assert calendar["artifact_count"] == 1
    assert calendar["artifact_id"] == "twse_calendar_2026_v1"
    assert calendar["acquired_markets"] == ["TWSE"]
    assert calendar["required_markets"] == ["TWSE", "TPEX"]


def test_adapter_metadata_does_not_promote_institutional_dataset() -> None:
    institutional = _load(MANIFEST)["datasets"]["institutional"]

    assert len(institutional["planned_sources"]) == 2
    assert institutional["status"] == "MISSING"
    assert institutional["artifact_id"] is None
    assert institutional["canonical_sha256"] is None


def test_missing_datasets_keep_all_downstream_gates_closed() -> None:
    manifest = _load(MANIFEST)

    assert manifest["gate"] == {
        "composite_manifest_allowed": False,
        "coverage_revision_allowed": False,
        "holdout_allowed": False,
        "outcome_generation_allowed": False,
        "population_freeze_allowed": False,
        "status": "BLOCKED",
    }
    assert all(issue["severity"] == "BLOCKING" for issue in manifest["issues"])


def test_acquisition_inventory_contains_no_outcome_fields() -> None:
    manifest = _load(MANIFEST)
    forbidden = {
        "executed",
        "execution_count",
        "expectancy",
        "fill_price",
        "gross_return",
        "net_expectancy",
        "net_return",
        "pnl",
        "price_value",
        "setup_qualified",
        "win_rate",
    }

    assert manifest["inspection_scope"]["outcome_fields_read"] is False
    assert manifest["inspection_scope"]["test_fixtures_count_as_acquired"] is False
    assert _all_keys(manifest).isdisjoint(forbidden)
