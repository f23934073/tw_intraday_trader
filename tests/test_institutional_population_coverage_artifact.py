"""Drift gates for the coverage-only PR-008 population snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
COVERAGE = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "coverage"
    / "population_coverage_v1_2026-08-20.json"
)
COVERAGE_DIGEST = COVERAGE.with_suffix(".canonical.sha256")
PROTOCOL = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "protocols"
    / "formal_evaluation_gate_v1.json"
)
PROTOCOL_DIGEST = PROTOCOL.with_suffix(".canonical.sha256")


def _load() -> dict[str, Any]:
    return json.loads(COVERAGE.read_text(encoding="utf-8"))


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            child_key
            for child in value.values()
            for child_key in _all_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def test_population_coverage_canonical_digest_is_frozen() -> None:
    artifact = _load()
    expected = COVERAGE_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(artifact)) == expected
    assert artifact["schema_version"] == "institutional_population_coverage_v1"
    assert artifact["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"


def test_population_coverage_references_the_frozen_protocol() -> None:
    artifact = _load()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    expected_protocol_digest = PROTOCOL_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(protocol)) == expected_protocol_digest
    assert artifact["protocol"] == {
        "artifact_id": protocol["artifact_id"],
        "canonical_sha256": expected_protocol_digest,
    }


def test_missing_inputs_fail_closed_without_inventing_population_counts() -> None:
    artifact = _load()
    sources = artifact["sources"]
    markets = artifact["markets"]

    assert all(
        source["status"] != "AVAILABLE" for source in sources.values()
    )
    assert sources["price_dataset"]["row_count"] == 0
    for market in markets.values():
        assert market["status"] == "MISSING"
        assert market["coverage_start"] is None
        assert market["coverage_end"] is None
        assert market["eligible_session_count"] is None
        assert market["eligible_member_count"] is None
        assert market["excluded_member_count"] is None


def test_blocking_issues_keep_every_execution_permission_disabled() -> None:
    artifact = _load()
    issue_codes = {issue["code"] for issue in artifact["issues"]}

    assert issue_codes == {
        "PIT_UNIVERSE_MISSING",
        "INSTITUTIONAL_PARTITIONS_MISSING",
        "PRICE_DATASET_MISSING",
        "CORPORATE_ACTIONS_MISSING",
        "REFERENCE_DATA_MISSING",
        "TPEX_CALENDAR_COVERAGE_UNPROVEN",
        "COVERAGE_RANGE_UNRESOLVED",
        "INSUFFICIENT_SESSIONS",
    }
    assert all(issue["severity"] == "BLOCKING" for issue in artifact["issues"])
    assert artifact["gate"] == {
        "composite_manifest_allowed": False,
        "dataset_population_frozen": False,
        "holdout_allowed": False,
        "outcome_generation_allowed": False,
        "status": "BLOCKED",
    }
    assert artifact["coverage"] == {"start_date": None, "end_date": None}
    assert artifact["split"]["train"] is None
    assert artifact["split"]["validation"] is None
    assert artifact["split"]["holdout"] is None


def test_coverage_snapshot_contains_no_outcome_fields() -> None:
    artifact = _load()
    forbidden = {
        "executed",
        "execution_count",
        "expectancy",
        "fill_price",
        "gross_return",
        "net_expectancy",
        "net_return",
        "pnl",
        "price",
        "setup_qualified",
        "win_rate",
    }

    assert artifact["inspection_scope"]["outcome_fields_read"] is False
    assert _all_keys(artifact).isdisjoint(forbidden)
