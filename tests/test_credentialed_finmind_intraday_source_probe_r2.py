"""Immutable evidence gates for the Sponsor-entitled FinMind r2 result."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from institutional_data.serialization import canonical_json, sha256_text


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research" / "institutional_evaluation" / "acquisition"
PROTOCOL = BASE / (
    "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21_r2.json"
)
CAPTURE = BASE / (
    "credentialed_finmind_intraday_source_probe_capture_v1_2026-08-21-r2"
)
RESULT = BASE / (
    "credentialed_finmind_intraday_source_probe_result_v1_2026-08-21_r2.json"
)
REFERENCE = BASE / (
    "credentialed_intraday_source_reference_capture_v1_2026-08-20-r1"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_r2_protocol_capture_and_result_digests_are_frozen() -> None:
    for path in (PROTOCOL, RESULT):
        assert sha256_text(canonical_json(_load(path))) == (
            path.with_suffix(".canonical.sha256").read_text().strip()
        )
    manifest = _load(CAPTURE / "capture_manifest.json")
    assert sha256_text(canonical_json(manifest)) == (
        CAPTURE.joinpath("capture_manifest.canonical.sha256").read_text().strip()
    )
    for record in manifest["records"]:
        body = CAPTURE.joinpath(record["body_file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == record["raw_response_sha256"]


def test_r2_result_references_exact_upstream_artifacts() -> None:
    result = _load(RESULT)
    assert result["protocol_reference"]["canonical_sha256"] == (
        PROTOCOL.with_suffix(".canonical.sha256").read_text().strip()
    )
    assert result["capture_references"]["finmind"]["canonical_sha256"] == (
        CAPTURE.joinpath("capture_manifest.canonical.sha256").read_text().strip()
    )
    assert result["capture_references"]["shioaji_controls"][
        "canonical_sha256"
    ] == REFERENCE.joinpath("capture_manifest.canonical.sha256").read_text().strip()


def test_entitlement_passes_but_target_and_fixed_control_are_empty() -> None:
    result = _load(RESULT)
    assert result["result"]["dataset_entitlement_verified"] is True
    assert result["result"]["target_1259_nonempty"] is False
    assert result["result"]["all_fixed_controls_available"] is False
    issue_codes = {issue["code"] for issue in result["issues"]}
    assert issue_codes == {
        "FINMIND_1259_HTTP_200_EMPTY_DATA",
        "FINMIND_FIXED_CONTROL_EMPTY_DATA",
    }


def test_available_controls_have_exact_semantic_equivalence() -> None:
    controls = _load(RESULT)["control_reconciliations"]
    available = [item for item in controls if item["available"]]
    assert {item["symbol"] for item in available} == {"1240", "2330", "2317"}
    assert all(item["semantic_pass"] for item in available)
    assert all(item["tick_kbar_mismatch_count"] == 0 for item in available)
    assert all(item["reference_ohlcv_mismatch_count"] == 0 for item in available)
    assert all(Decimal(item["vwap_absolute_difference"]) == 0 for item in available)
    assert {item["volume_hypothesis"] for item in available} == {
        "RAW_VOLUME_IS_COMMON_LOTS_MULTIPLY_BY_1000"
    }


def test_r2_is_narrow_rejection_and_all_permissions_stay_false() -> None:
    result = _load(RESULT)
    assert result["status"] == "BLOCKED"
    assert result["result"]["verdict"] == "REJECTED_FOR_MISMATCH_RESOLUTION"
    assert result["result"]["source_qualified"] is False
    assert result["result"]["source_selected"] is False
    assert all(value is False for value in result["permissions"].values())
