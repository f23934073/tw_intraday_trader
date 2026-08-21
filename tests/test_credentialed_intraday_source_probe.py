"""Semantic and immutable-artifact gates for the credentialed probe."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text
from institutional_research.intraday_source_probe import inspect_candidate_payload


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research" / "institutional_evaluation" / "acquisition"
PROTOCOL = BASE / "credentialed_intraday_source_probe_protocol_v1_2026-08-20.json"
FUGLE_CAPTURE = BASE / "credentialed_intraday_source_probe_capture_v1_2026-08-20-r1"
REFERENCE_CAPTURE = (
    BASE / "credentialed_intraday_source_reference_capture_v1_2026-08-20-r1"
)
RESULT = BASE / "credentialed_intraday_source_probe_result_v1_2026-08-20.json"
RESULT_DIGEST = RESULT.with_suffix(".canonical.sha256")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_empty_http_success_is_not_treated_as_coverage() -> None:
    result = inspect_candidate_payload({"symbol": "1259", "data": []}, symbol="1259")
    assert result["bar_count"] == 0
    assert result["issues"] == ["HTTP_200_EMPTY_DATA"]


def test_timestamp_drift_is_classified_without_fill() -> None:
    row = {
        "date": "2026-08-18T08:59:30+08:00",
        "open": 1,
        "high": 1,
        "low": 1,
        "close": 1,
        "volume": 1,
        "average": 1,
    }
    result = inspect_candidate_payload({"symbol": "2330", "data": [row]}, symbol="2330")
    assert result["bar_count"] == 1
    assert set(result["issues"]) == {"NOT_EXACT_MINUTE", "OUTSIDE_REGULAR_SESSION"}


def test_duplicate_timestamp_is_rejected() -> None:
    row = {
        "date": "2026-08-18T09:00:00+08:00",
        "open": "1",
        "high": "1",
        "low": "1",
        "close": "1",
        "volume": "2",
        "average": "1",
    }
    result = inspect_candidate_payload(
        {"symbol": "2330", "data": [row, dict(row)]}, symbol="2330"
    )
    assert "DUPLICATE_TIMESTAMP" in result["issues"]
    assert result["total_volume_shares"] == "4000"


def test_result_has_stable_identity_and_digest() -> None:
    artifact = _load(RESULT)
    assert artifact["schema_version"] == "credentialed_intraday_source_probe_result_v1"
    assert sha256_text(canonical_json(artifact)) == RESULT_DIGEST.read_text().strip()


def test_capture_manifests_and_raw_bodies_are_digest_verified() -> None:
    fugle_manifest = _load(FUGLE_CAPTURE / "capture_manifest.json")
    assert sha256_text(canonical_json(fugle_manifest)) == (
        FUGLE_CAPTURE / "capture_manifest.canonical.sha256"
    ).read_text().strip()
    for record in fugle_manifest["records"]:
        body = (FUGLE_CAPTURE / record["body_file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == record["raw_response_sha256"]
        assert {key.lower() for key in record["response_headers_without_secrets"]}.isdisjoint(
            {"authorization", "cookie", "set-cookie", "x-api-key"}
        )

    reference_manifest = _load(REFERENCE_CAPTURE / "capture_manifest.json")
    assert sha256_text(canonical_json(reference_manifest)) == (
        REFERENCE_CAPTURE / "capture_manifest.canonical.sha256"
    ).read_text().strip()
    assert reference_manifest["trade_subscription_enabled"] is False


def test_protocol_was_registered_before_every_candidate_retrieval() -> None:
    registered_at = datetime.fromisoformat(_load(PROTOCOL)["registered_at"])
    manifest = _load(FUGLE_CAPTURE / "capture_manifest.json")
    assert all(
        registered_at < datetime.fromisoformat(record["retrieved_at"])
        for record in manifest["records"]
    )


def test_fixed_target_remains_unresolved_and_not_excluded() -> None:
    artifact = _load(RESULT)
    target = next(item for item in artifact["observations"] if item["symbol"] == "1259")
    assert target["http_status"] == 200
    assert target["bar_count"] == 0
    assert target["issues"] == ["HTTP_200_EMPTY_DATA"]
    assert artifact["result"]["target_1259_nonempty"] is False
    assert artifact["permissions"]["provider_mismatch_exclusion_allowed"] is False


def test_all_control_vwap_values_pass_frozen_tolerance() -> None:
    artifact = _load(RESULT)
    assert len(artifact["control_reconciliations"]) == 4
    assert all(item["vwap_pass"] for item in artifact["control_reconciliations"])
    assert artifact["result"]["cross_market_vwap_requirement_passed"] is True


def test_non_exact_control_volume_blocks_source_selection() -> None:
    artifact = _load(RESULT)
    control = next(
        item for item in artifact["control_reconciliations"] if item["symbol"] == "2330"
    )
    assert control["volume_difference_lots"] == "-8"
    assert control["volume_exact_match"] is False
    assert artifact["result"]["all_control_volume_exactly_reconciled"] is False
    assert artifact["result"]["source_selected"] is False


def test_result_is_fail_closed_and_outcome_free() -> None:
    artifact = _load(RESULT)
    assert artifact["status"] == "BLOCKED"
    assert set(artifact["permissions"].values()) == {False}
    assert artifact["evidence_scope"]["holdout_outcomes_read"] is False
    assert artifact["evidence_scope"]["strategy_outcomes_read"] is False
