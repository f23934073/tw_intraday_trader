"""Drift gates for the pre-payload FinMind KBar plus Tick probe."""

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
    / "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21.json"
)
DIGEST = ARTIFACT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_protocol_has_stable_identity_and_digest() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["schema_version"] == (
        "credentialed_finmind_intraday_source_probe_protocol_v1"
    )
    assert artifact["artifact_id"] == (
        "credentialed-finmind-intraday-source-probe-protocol-v1-2026-08-21-r1"
    )
    assert sha256_text(canonical_json(artifact)) == DIGEST.read_text().strip()


def test_protocol_freezes_exact_ten_request_order() -> None:
    requests = _load(ARTIFACT)["fixed_requests"]
    assert len(requests) == 10
    assert [item["data_id"] for item in requests] == [
        "1259",
        "1259",
        "1240",
        "1240",
        "12561",
        "12561",
        "2330",
        "2330",
        "2317",
        "2317",
    ]
    assert [item["dataset"] for item in requests] == [
        "TaiwanStockKBar",
        "TaiwanStockPriceTick",
    ] * 5
    assert {item["start_date"] for item in requests} == {"2026-08-18"}


def test_protocol_requires_authenticated_dual_status_success() -> None:
    artifact = _load(ARTIFACT)
    assert artifact["authentication"]["no_anonymous_fallback"] is True
    assert artifact["authentication"]["credential_value_may_be_logged"] is False
    assert artifact["authentication"]["credential_value_may_be_persisted"] is False
    assert artifact["http_contract"]["success_requires"] == (
        "HTTP_200_AND_JSON_STATUS_200_AND_DATA_ARRAY"
    )


def test_protocol_freezes_unit_and_timestamp_hypotheses() -> None:
    artifact = _load(ARTIFACT)
    units = artifact["unit_reconciliation_policy"]
    assert units["allowed_hypotheses_per_dataset"] == [
        "RAW_VOLUME_IS_SHARES",
        "RAW_VOLUME_IS_COMMON_LOTS_MULTIPLY_BY_1000",
    ]
    assert units["exact_control_volume_match_required"] is True
    assert units["one_hypothesis_required_across_all_controls"] is True
    assert artifact["kbar_policy"]["synthetic_zero_volume_fill_allowed"] is False


def test_protocol_reuses_frozen_vwap_tolerance() -> None:
    tolerance = _load(ARTIFACT)["vwap_reconciliation"]["tolerance"]
    assert tolerance == {
        "absolute_twd": "0.01",
        "formula": "max(0.01 TWD, reference_vwap * 0.0001)",
        "relative_fraction": "0.0001",
    }


def test_probe_cannot_select_dataset_or_exclude_symbol() -> None:
    policy = _load(ARTIFACT)["decision_policy"]
    assert policy["bounded_probe_pass_is_not_full_pit_qualification"] is True
    assert policy["dataset_source_selected_by_this_probe"] is False
    assert policy["provider_mismatch_is_not_structural_exclusion"] is True
