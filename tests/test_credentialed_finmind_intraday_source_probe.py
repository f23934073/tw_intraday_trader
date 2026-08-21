"""Evidence gates for the sealed credentialed FinMind probe result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research" / "institutional_evaluation" / "acquisition"
PROTOCOL = ACQUISITION / (
    "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21.json"
)
CAPTURE = ACQUISITION / (
    "credentialed_finmind_intraday_source_probe_capture_v1_2026-08-21-r1"
)
RESULT = ACQUISITION / (
    "credentialed_finmind_intraday_source_probe_result_v1_2026-08-21.json"
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_capture_manifest_and_raw_responses_are_digest_verified() -> None:
    manifest = _load(CAPTURE / "capture_manifest.json")
    expected = (CAPTURE / "capture_manifest.canonical.sha256").read_text().strip()
    assert sha256_text(canonical_json(manifest)) == expected
    assert len(manifest["records"]) == 10
    for record in manifest["records"]:
        body = (CAPTURE / record["body_file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == record["raw_response_sha256"]


def test_capture_follows_exact_frozen_request_order() -> None:
    protocol = _load(PROTOCOL)
    manifest = _load(CAPTURE / "capture_manifest.json")
    observed = [record["request"]["query"] for record in manifest["records"]]
    expected = [
        {
            "dataset": item["dataset"],
            "data_id": item["data_id"],
            "start_date": item["start_date"],
        }
        for item in protocol["fixed_requests"]
    ]
    assert observed == expected


def test_all_routes_are_entitlement_denied_without_data_arrays() -> None:
    records = _load(CAPTURE / "capture_manifest.json")["records"]
    assert {record["http_status"] for record in records} == {400}
    assert {record["json_status"] for record in records} == {400}
    assert {record["data_array_present"] for record in records} == {False}
    assert all("update your user level" in record["json_message"] for record in records)


def test_result_references_frozen_protocol_and_capture() -> None:
    result = _load(RESULT)
    assert sha256_text(canonical_json(result)) == (
        RESULT.with_suffix(".canonical.sha256").read_text().strip()
    )
    assert result["protocol_reference"]["canonical_sha256"] == (
        PROTOCOL.with_suffix(".canonical.sha256").read_text().strip()
    )
    assert result["capture_reference"]["canonical_sha256"] == (
        CAPTURE.joinpath("capture_manifest.canonical.sha256").read_text().strip()
    )


def test_result_remains_blocked_and_cannot_select_source() -> None:
    result = _load(RESULT)
    assert result["status"] == "BLOCKED"
    assert result["result"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["result"]["credentialed_probe_completed"] is True
    assert result["result"]["entitlement_sufficient"] is False
    assert result["result"]["source_qualified"] is False
    assert result["result"]["target_1259_nonempty"] is None
    assert all(value is False for value in result["permissions"].values())
