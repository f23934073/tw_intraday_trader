"""Drift gates for the PR-008 all-dataset acquisition completion decision."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
COMPLETION = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "dataset_acquisition_completion_v1_2026-08-20.json"
)
COMPLETION_DIGEST = COMPLETION.with_suffix(".canonical.sha256")
ACQUISITION = COMPLETION.with_name(
    "dataset_acquisition_manifest_v1_2026-08-20_r2.json"
)
ACQUISITION_DIGEST = ACQUISITION.with_suffix(".canonical.sha256")


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


def test_completion_artifact_digest_and_schema_are_frozen() -> None:
    artifact = _load(COMPLETION)
    expected = COMPLETION_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(artifact)) == expected
    assert artifact["schema_version"] == (
        "institutional_dataset_acquisition_completion_v1"
    )
    assert artifact["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"


def test_completion_references_exact_acquisition_revision() -> None:
    completion = _load(COMPLETION)
    acquisition = _load(ACQUISITION)
    expected = ACQUISITION_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(acquisition)) == expected
    assert completion["acquisition_manifest_reference"] == {
        "artifact_id": acquisition["artifact_id"],
        "canonical_sha256": expected,
    }


def test_readiness_is_derived_without_promoting_partial_or_staging_data() -> None:
    completion = _load(COMPLETION)
    acquisition = _load(ACQUISITION)
    readiness = completion["dataset_readiness"]
    required = set(completion["readiness_policy"]["required_datasets"])

    assert required == {
        "price",
        "institutional",
        "pit_universe",
        "corporate_actions",
        "reference_data",
        "trading_calendar",
    }
    assert set(readiness) == required
    for name in required:
        assert readiness[name]["status"] == acquisition["datasets"][name]["status"]
        assert readiness[name]["artifact_id"] == acquisition["datasets"][name][
            "artifact_id"
        ]
        assert readiness[name]["canonical_sha256"] == acquisition["datasets"][name][
            "canonical_sha256"
        ]
        assert readiness[name]["ready"] is False

    assert completion["summary"] == {
        "missing_count": 4,
        "partial_count": 2,
        "required_dataset_count": 6,
        "validated_count": 0,
    }
    assert completion["non_qualifying_evidence"] == [
        {
            "acquired_markets": ["TWSE", "TPEX"],
            "code": "PRICE_STAGING_JOB_INCOMPLETE",
            "completed_partition_count": 542,
            "error_partition_count": 130,
            "job_id": "dataset-download-f914feaddea04e37b3cbdcfce2b0179b",
            "job_status": "PAUSED",
            "nonempty_partition_count": 412,
            "reason": "NO_IMMUTABLE_DATASET_MANIFEST",
            "requested_symbol_count": 2738,
            "staged_bar_count": 9335704,
        }
    ]


def test_blockers_keep_every_downstream_permission_closed() -> None:
    artifact = _load(COMPLETION)
    blocker_codes = {issue["code"] for issue in artifact["blocking_issues"]}

    assert blocker_codes == {
        "PRICE_DATASET_MISSING",
        "INSTITUTIONAL_HISTORY_INCOMPLETE",
        "PIT_UNIVERSE_MISSING",
        "CORPORATE_ACTIONS_MISSING",
        "REFERENCE_DATA_MISSING",
        "TPEX_CALENDAR_COVERAGE_UNPROVEN",
    }
    assert all(
        issue["severity"] == "BLOCKING" for issue in artifact["blocking_issues"]
    )
    assert artifact["gate"] == {
        "all_required_datasets_ready": False,
        "composite_manifest_allowed": False,
        "coverage_revision_allowed": False,
        "dataset_population_freeze_allowed": False,
        "holdout_allowed": False,
        "outcome_generation_allowed": False,
        "status": "BLOCKED",
    }


def test_completion_inventory_contains_no_outcome_fields() -> None:
    artifact = _load(COMPLETION)
    forbidden = {
        "close",
        "executed",
        "execution_count",
        "expectancy",
        "fill_price",
        "gross_return",
        "high",
        "low",
        "net_expectancy",
        "net_return",
        "open",
        "pnl",
        "price_value",
        "setup_qualified",
        "win_rate",
    }

    assert artifact["inspection_scope"] == {
        "adapters_count_as_ready": False,
        "inventory_method": "IMMUTABLE_ARTIFACT_AND_METADATA_ONLY_STAGING_SCAN",
        "outcome_fields_read": False,
        "staging_payloads_read": False,
        "test_fixtures_count_as_ready": False,
    }
    assert _all_keys(artifact).isdisjoint(forbidden)
