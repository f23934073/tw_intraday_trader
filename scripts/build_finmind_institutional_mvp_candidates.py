"""Build one immutable FinMind daily institutional MVP candidate observation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text  # noqa: E402
from institutional_mvp.finmind import (  # noqa: E402
    parse_finmind_mvp_flows,
    select_three_way_buy_candidates,
)


MVP_ROOT = PROJECT_ROOT / "research/institutional_evaluation/mvp"
CAPTURE_ROOT = (
    PROJECT_ROOT
    / "research/institutional_evaluation/acquisition"
    / "finmind_institutional_mvp_capture_v1_2026-08-24-r1"
)
POLICY_PATH = MVP_ROOT / "finmind_institutional_mvp_candidate_policy_v1_2026-08-24-r2.json"
OUTPUT_PATH = MVP_ROOT / "finmind_institutional_mvp_candidate_observation_v1_2026-08-24-r2.json"
EXPECTED_CAPTURE_DIGEST = "01aa72b4b2e8b4f53f08a97e38c38c62bcb7e996e5215b1e2cec8710a94f4d98"
EXPECTED_PROTOCOL_DIGEST = "470282b38653f1502c92153e7ad6dc06409c3b62a95d8262e05a05a944734925"
FLOW_DATASET = "TaiwanStockInstitutionalInvestorsBuySellWide"
INFO_DATASET = "TaiwanStockInfo"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    return payload


def _verified_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = _load_json(path)
    digest = sha256_text(canonical_json(payload))
    expected = path.with_suffix(".canonical.sha256").read_text(encoding="utf-8").strip()
    if digest != expected:
        raise RuntimeError(f"canonical digest drift: {path.name}")
    return payload, digest


def _record_by_dataset(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    records = manifest.get("records")
    if not isinstance(records, list):
        raise RuntimeError("capture records are invalid")
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise RuntimeError("capture record is invalid")
        dataset = record.get("dataset")
        if not isinstance(dataset, str) or dataset in indexed:
            raise RuntimeError("capture dataset identity is invalid")
        indexed[dataset] = record
    if set(indexed) != {FLOW_DATASET, INFO_DATASET}:
        raise RuntimeError("capture dataset allowlist drift")
    return indexed


def _verified_raw_body(record: Mapping[str, Any]) -> bytes:
    body_name = record.get("body_file")
    expected = record.get("raw_response_sha256")
    if not isinstance(body_name, str) or not isinstance(expected, str):
        raise RuntimeError("capture raw-body metadata is invalid")
    body_path = CAPTURE_ROOT / body_name
    body = body_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != expected:
        raise RuntimeError(f"raw response digest drift: {body_name}")
    return body


def _load_inputs() -> tuple[dict[str, Any], str, dict[str, Any], str, bytes, bytes]:
    policy, policy_digest = _verified_json(POLICY_PATH)
    capture, capture_digest = _verified_json(CAPTURE_ROOT / "capture_manifest.json")
    if capture_digest != EXPECTED_CAPTURE_DIGEST:
        raise RuntimeError("unexpected capture manifest identity")
    if policy.get("input_capture", {}).get("canonical_sha256") != capture_digest:
        raise RuntimeError("candidate policy capture lineage drift")
    permissions = policy.get("execution_permissions")
    if not isinstance(permissions, Mapping):
        raise RuntimeError("candidate policy permissions are invalid")
    if permissions.get("mvp_candidate_observation_allowed") is not True or any(
        value is not False
        for name, value in permissions.items()
        if name != "mvp_candidate_observation_allowed"
    ):
        raise RuntimeError("candidate policy execution permissions drift")
    contract = policy.get("candidate_contract")
    if not isinstance(contract, Mapping):
        raise RuntimeError("candidate policy contract is invalid")
    if contract.get("market_mapping") != "LATEST_TAIWAN_STOCK_INFO_ROW_PER_SYMBOL;_CURRENT_MAPPING_ONLY":
        raise RuntimeError("candidate policy market mapping drift")
    records = _record_by_dataset(capture)
    protocol_reference = capture.get("protocol_reference")
    if not isinstance(protocol_reference, Mapping) or protocol_reference.get(
        "canonical_sha256"
    ) != EXPECTED_PROTOCOL_DIGEST:
        raise RuntimeError("capture protocol lineage drift")
    return (
        policy,
        policy_digest,
        capture,
        capture_digest,
        _verified_raw_body(records[FLOW_DATASET]),
        _verified_raw_body(records[INFO_DATASET]),
    )


def _date_value(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise RuntimeError(f"candidate policy {name} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError(f"candidate policy {name} is invalid") from error


def _write_immutable(payload: Mapping[str, Any]) -> str:
    if OUTPUT_PATH.exists() or OUTPUT_PATH.with_suffix(".canonical.sha256").exists():
        raise RuntimeError("immutable candidate observation already exists")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    digest = sha256_text(canonical_json(payload))
    staging = Path(tempfile.mkdtemp(prefix="finmind-mvp-candidate-", dir=MVP_ROOT))
    try:
        staged_output = staging / OUTPUT_PATH.name
        staged_sidecar = staging / OUTPUT_PATH.with_suffix(".canonical.sha256").name
        staged_output.write_text(serialized, encoding="utf-8")
        staged_sidecar.write_text(f"{digest}\n", encoding="utf-8")
        os.replace(staged_output, OUTPUT_PATH)
        os.replace(staged_sidecar, OUTPUT_PATH.with_suffix(".canonical.sha256"))
    finally:
        staging.rmdir()
    return digest


def main() -> None:
    policy, policy_digest, capture, capture_digest, flow_body, info_body = _load_inputs()
    contract = policy["candidate_contract"]
    assert isinstance(contract, Mapping)
    session_date = _date_value(contract.get("session_date"), "session_date")
    usable_from_session = _date_value(
        contract.get("usable_from_session"), "usable_from_session"
    )
    candidate_limit = contract.get("candidate_limit")
    if not isinstance(candidate_limit, int) or candidate_limit <= 0:
        raise RuntimeError("candidate policy candidate_limit is invalid")
    flows = parse_finmind_mvp_flows(
        wide_payload=flow_body,
        stock_info_payload=info_body,
        session_date=session_date,
        usable_from_session=usable_from_session,
    )
    all_candidates = select_three_way_buy_candidates(flows)
    candidates = select_three_way_buy_candidates(flows, limit=candidate_limit)
    records = _record_by_dataset(capture)
    result = {
        "artifact_id": "finmind-institutional-mvp-candidate-observation-v1-2026-08-24-r2",
        "candidate_observation": {
            "candidate_count_before_limit": len(all_candidates),
            "candidate_limit": candidate_limit,
            "candidates": [candidate.to_dict() for candidate in candidates],
            "current_market_mapped_flow_rows": len(flows),
            "session_date": session_date.isoformat(),
            "usable_from_session": usable_from_session.isoformat(),
        },
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "evidence_scope": {
            "backtest_or_holdout_read": False,
            "institutional_flow_fields_read": True,
            "price_or_kbar_read": False,
            "provider_call_performed": False,
            "return_or_pnl_read": False,
        },
        "execution_permissions": policy["execution_permissions"],
        "input_capture": {
            "artifact_id": capture["artifact_id"],
            "canonical_sha256": capture_digest,
            "flow_raw_response_sha256": records[FLOW_DATASET]["raw_response_sha256"],
            "stock_info_raw_response_sha256": records[INFO_DATASET]["raw_response_sha256"],
        },
        "input_candidate_policy": {
            "artifact_id": policy["artifact_id"],
            "canonical_sha256": policy_digest,
        },
        "mvp_limitations": policy["mvp_limitations"],
        "schema_version": "finmind_institutional_mvp_candidate_observation_v1",
        "status": "MVP_CANDIDATE_OBSERVATION_ONLY",
    }
    digest = _write_immutable(result)
    print(
        "sealed FinMind MVP candidate observation "
        f"mapped_flows={len(flows)} candidates={len(all_candidates)} "
        f"published={len(candidates)} digest={digest}"
    )


if __name__ == "__main__":
    main()
