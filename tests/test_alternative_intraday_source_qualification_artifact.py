"""Drift gates for the FinMind alternative-source qualification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "alternative_intraday_source_qualification_v1_2026-08-21.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")
PROVIDER_RESOLUTION = ARTIFACT.with_name(
    "price_provider_coverage_resolution_v1_2026-08-20.json"
)
PROVIDER_RESOLUTION_DIGEST = PROVIDER_RESOLUTION.with_suffix(".canonical.sha256")
FUGLE_RESULT = ARTIFACT.with_name(
    "credentialed_intraday_source_probe_result_v1_2026-08-20.json"
)
FUGLE_RESULT_DIGEST = FUGLE_RESULT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_artifact_has_stable_identity_and_digest() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == "alternative_intraday_source_qualification_v1"
    assert artifact["artifact_id"] == (
        "alternative-intraday-source-qualification-v1-2026-08-21-r1"
    )
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_artifact_references_exact_upstream_evidence() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["upstream_references"] == [
        {
            "artifact_id": _load(PROVIDER_RESOLUTION)["artifact_id"],
            "canonical_sha256": PROVIDER_RESOLUTION_DIGEST.read_text().strip(),
        },
        {
            "artifact_id": _load(FUGLE_RESULT)["artifact_id"],
            "canonical_sha256": FUGLE_RESULT_DIGEST.read_text().strip(),
        },
    ]


def test_kbar_alone_cannot_satisfy_vwap_contract() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["candidate"]["kbar_dataset"] == "TaiwanStockKBar"
    assert artifact["candidate"]["tick_dataset"] == "TaiwanStockPriceTick"
    reconstruction = artifact["planned_probe"]["vwap_reconstruction"]
    assert reconstruction["volume_unit_must_be_proven_before_calculation"] is True
    assert reconstruction["tolerance_reference"] == (
        "REUSE_FROZEN_VWAP_TOLERANCE_WITHOUT_CHANGE"
    )


def test_fixed_probe_scope_is_preserved() -> None:
    probe = _load(ARTIFACT)["planned_probe"]
    assert probe["fixed_control_session"] == "2026-08-18"
    assert [item["symbol"] for item in probe["fixed_symbols"]] == [
        "1259",
        "1240",
        "12561",
        "2330",
        "2317",
    ]
    assert probe["semantic_protocol_reference"]["canonical_sha256"] == (
        "f6b396072d858356bcd98965ddafc749f2b8b63cfe3555f9f60f58a9c16d10f7"
    )


def test_no_silent_substitution_requires_new_dataset_revision() -> None:
    policy = _load(ARTIFACT)["dataset_revision_policy"]
    assert policy["in_place_partition_substitution_allowed"] is False
    assert policy["primary_source_missing_cannot_be_silently_replaced"] is True
    assert policy["new_source_composition_requires_new_dataset_revision"] is True
    assert policy["source_identity_required_per_partition"] is True


def test_missing_entitlement_prevents_probe_or_selection() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["evidence_scope"]["credential_names_found"] == []
    assert artifact["evidence_scope"]["credential_values_read"] is False
    assert artifact["evidence_scope"]["provider_requests_executed"] is False
    assert artifact["permissions"]["finmind_probe_allowed"] is False
    assert artifact["candidate"]["selected_for_dataset_acquisition"] is False
    assert artifact["result"]["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_qualification_remains_fail_closed_and_outcome_free() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["status"] == "BLOCKED"
    assert set(artifact["permissions"].values()) == {False}
    assert artifact["evidence_scope"]["price_payloads_read"] is False
    assert artifact["evidence_scope"]["outcome_fields_read"] is False
