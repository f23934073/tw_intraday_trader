"""Drift gates for the paused formal-price acquisition resolution snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
RESOLUTION = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "price_acquisition_resolution_v1_2026-08-20.json"
)
RESOLUTION_DIGEST = RESOLUTION.with_suffix(".canonical.sha256")
COMPLETION = RESOLUTION.with_name(
    "dataset_acquisition_completion_v1_2026-08-20.json"
)
COMPLETION_DIGEST = COMPLETION.with_suffix(".canonical.sha256")


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


def test_price_resolution_digest_and_schema_are_frozen() -> None:
    artifact = _load(RESOLUTION)
    expected = RESOLUTION_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(artifact)) == expected
    assert artifact["schema_version"] == "price_acquisition_resolution_v1"
    assert artifact["change_policy"] == "IMMUTABLE_NEW_ARTIFACT_REQUIRED"


def test_price_resolution_references_the_frozen_completion_gate() -> None:
    resolution = _load(RESOLUTION)
    completion = _load(COMPLETION)
    expected = COMPLETION_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(completion)) == expected
    assert resolution["completion_gate_reference"] == {
        "artifact_id": completion["artifact_id"],
        "canonical_sha256": expected,
    }


def test_resolution_classification_is_complete_and_non_overlapping() -> None:
    artifact = _load(RESOLUTION)
    classification = artifact["classification"]
    resolved = classification["resolved_success_prefix"]["count"]
    checkpointed_unresolved = classification[
        "checkpointed_unresolved_tail_count"
    ]
    not_checkpointed = classification["not_checkpointed_count"]

    assert resolved == 411
    assert checkpointed_unresolved == 131
    assert not_checkpointed == 2196
    assert resolved + checkpointed_unresolved + not_checkpointed == 2738
    assert classification["unresolved_count"] == 2327
    assert classification["tail_classes"] == {
        "legacy_empty_retry_required": 130,
        "nonempty_untrusted_after_retry_anchor": 1,
    }
    assert sum(classification["resolved_success_prefix"]["market_counts"].values()) == (
        resolved
    )


def test_ambiguous_resume_attempt_does_not_promote_price_staging() -> None:
    artifact = _load(RESOLUTION)

    assert artifact["last_resume_attempt"] == {
        "attempted_at": "2026-08-20T16:54:48.692202+08:00",
        "exit_code": 75,
        "partition_written": False,
        "response_class": "AMBIGUOUS_EMPTY_KBAR",
        "retry_symbol": "1259",
        "status": "SAFELY_PAUSED",
    }
    assert artifact["job"]["job_status"] == "PAUSED"
    assert artifact["expected_universe"]["universe_selection"] == "ALL_CURRENT"
    assert artifact["expected_universe"]["research_eligible"] is False
    assert artifact["expected_universe"]["survivorship_free"] is False


def test_unresolved_price_evidence_keeps_every_permission_closed() -> None:
    artifact = _load(RESOLUTION)

    assert all(value is False for value in artifact["exit_criteria"].values())
    assert artifact["gate"] == {
        "acquisition_manifest_revision_allowed": False,
        "all_price_exit_criteria_passed": False,
        "holdout_allowed": False,
        "outcome_generation_allowed": False,
        "population_freeze_allowed": False,
        "price_dataset_manifest_allowed": False,
        "status": "BLOCKED",
    }
    assert all(issue["severity"] == "BLOCKING" for issue in artifact["issues"])


def test_resolution_snapshot_contains_no_price_or_outcome_values() -> None:
    artifact = _load(RESOLUTION)
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
        "outcome_fields_read": False,
        "partition_payloads_read": False,
        "price_values_read": False,
        "staging_metadata_only": True,
    }
    assert _all_keys(artifact).isdisjoint(forbidden)
