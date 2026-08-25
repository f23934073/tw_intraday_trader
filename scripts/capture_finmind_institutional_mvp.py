"""Capture the frozen FinMind daily institutional-flow MVP source evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.finmind_history import FinMindApiClient, FinMindRequestError  # noqa: E402
from institutional_data.serialization import canonical_json, sha256_text  # noqa: E402


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "research/institutional_evaluation/acquisition"
    / "finmind_institutional_mvp_protocol_v1_2026-08-24.json"
)
SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}
ALLOWED_DATASETS = {
    "TaiwanStockInstitutionalInvestorsBuySellWide",
    "TaiwanStockInfo",
}


def _load_protocol() -> tuple[dict[str, Any], str]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    digest = sha256_text(canonical_json(protocol))
    expected = PROTOCOL_PATH.with_suffix(".canonical.sha256").read_text(
        encoding="utf-8"
    ).strip()
    if digest != expected:
        raise RuntimeError("FinMind institutional MVP protocol digest drift detected")
    requests = protocol.get("fixed_requests")
    if not isinstance(requests, list) or len(requests) != 2:
        raise RuntimeError("FinMind institutional MVP request set is invalid")
    if {str(item.get("dataset")) for item in requests if isinstance(item, Mapping)} != ALLOWED_DATASETS:
        raise RuntimeError("FinMind institutional MVP allowlist drift detected")
    permissions = protocol.get("execution_permissions")
    if not isinstance(permissions, Mapping):
        raise RuntimeError("FinMind institutional MVP permissions are invalid")
    if permissions.get("mvp_candidate_observation_allowed") is not True or any(
        value is not False
        for name, value in permissions.items()
        if name != "mvp_candidate_observation_allowed"
    ):
        raise RuntimeError("FinMind institutional MVP execution permissions drifted")
    return protocol, digest


def _safe_headers(headers: object) -> dict[str, str]:
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    return {
        str(name).lower(): str(value)
        for name, value in items()
        if str(name).lower() not in SECRET_HEADERS
    }


def _query(item: Mapping[str, Any]) -> dict[str, str]:
    result = {"dataset": str(item["dataset"])}
    for key in ("data_id", "start_date", "end_date"):
        if item.get(key) is not None:
            result[key] = str(item[key])
    return result


def _request_once(url: str, token: str) -> tuple[int, dict[str, str], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "tw-intraday-trader-institutional-mvp/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return int(response.status), _safe_headers(response.headers), response.read()
    except HTTPError as error:
        return int(error.code), _safe_headers(error.headers), error.read()
    except URLError as error:
        raise RuntimeError(f"FinMind institutional MVP transport failed: {error.reason}") from error


def _summary(body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "data_array_present": False,
            "field_names": [],
            "json_message": None,
            "json_status": None,
            "row_count": None,
        }
    if not isinstance(payload, Mapping):
        return {
            "data_array_present": False,
            "field_names": [],
            "json_message": None,
            "json_status": None,
            "row_count": None,
        }
    rows = payload.get("data")
    if not isinstance(rows, list):
        return {
            "data_array_present": False,
            "field_names": [],
            "json_message": payload.get("msg"),
            "json_status": payload.get("status"),
            "row_count": None,
        }
    return {
        "data_array_present": True,
        "field_names": sorted(
            {
                str(key)
                for row in rows
                if isinstance(row, Mapping)
                for key in row.keys()
            }
        ),
        "json_message": payload.get("msg"),
        "json_status": payload.get("status"),
        "row_count": len(rows),
    }


def _usage_preflight(protocol: Mapping[str, Any], token: str) -> dict[str, int]:
    try:
        usage = FinMindApiClient(token).usage()
    except FinMindRequestError as error:
        raise RuntimeError("FinMind institutional MVP usage preflight failed") from error
    budget = protocol["request_budget"]
    if not isinstance(budget, Mapping):
        raise RuntimeError("FinMind institutional MVP request budget is invalid")
    if usage.remaining < int(budget["data_requests"]) + int(
        budget["minimum_remaining_after_probe"]
    ):
        raise RuntimeError("FinMind institutional MVP quota is insufficient; no data request sent")
    return {
        "api_request_limit": usage.api_request_limit,
        "remaining_before": usage.remaining,
        "user_count_before": usage.user_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    protocol, protocol_digest = _load_protocol()
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.environ.get("FINMIND_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("FINMIND_API_TOKEN is missing")
    usage_preflight = _usage_preflight(protocol, token)
    if args.preflight_only:
        print(
            "FinMind institutional MVP preflight passed "
            f"remaining_before={usage_preflight['remaining_before']}"
        )
        return

    capture_config = protocol["response_capture"]
    assert isinstance(capture_config, Mapping)
    output_path = PROTOCOL_PATH.parent / str(capture_config["immutable_output_directory"])
    if output_path.exists():
        raise RuntimeError("Immutable FinMind institutional MVP capture already exists")
    endpoint = str(protocol["http_contract"]["endpoint"])
    requests = protocol["fixed_requests"]
    assert isinstance(requests, list)
    staging = Path(tempfile.mkdtemp(prefix="finmind-institutional-mvp-", dir=output_path.parent))
    try:
        records: list[dict[str, object]] = []
        for index, item in enumerate(requests, start=1):
            assert isinstance(item, Mapping)
            query = _query(item)
            if query["dataset"] not in ALLOWED_DATASETS:
                raise RuntimeError("FinMind institutional MVP request is outside allowlist")
            http_status, headers, body = _request_once(
                f"{endpoint}?{urlencode(query)}", token
            )
            stem = f"finmind_{index:02d}_{query['dataset']}"
            body_name = f"{stem}.response.bin"
            (staging / body_name).write_bytes(body)
            record: dict[str, object] = {
                "body_file": body_name,
                "dataset": query["dataset"],
                "http_status": http_status,
                "raw_response_bytes": len(body),
                "raw_response_sha256": hashlib.sha256(body).hexdigest(),
                "request": {"endpoint": endpoint, "query": query},
                "response_headers_without_secrets": headers,
                "retrieved_at": datetime.now().astimezone().isoformat(),
                "role": str(item["role"]),
                "source_version": "FINMIND_API_V4",
                **_summary(body),
            }
            (staging / f"{stem}.metadata.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            records.append(record)
            print(
                f"captured request={index}/{len(requests)} dataset={record['dataset']} "
                f"http_status={record['http_status']} rows={record['row_count']}"
            )
        manifest = {
            "artifact_id": "finmind-institutional-mvp-capture-v1-2026-08-24-r1",
            "authentication": {
                "credential_environment_name": "FINMIND_API_TOKEN",
                "credential_present": True,
                "credential_value_persisted": False,
            },
            "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
            "protocol_reference": {
                "artifact_id": protocol["artifact_id"],
                "canonical_sha256": protocol_digest,
            },
            "records": records,
            "schema_version": "finmind_institutional_mvp_capture_v1",
            "usage_preflight": usage_preflight,
        }
        (staging / "capture_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "capture_manifest.canonical.sha256").write_text(
            sha256_text(canonical_json(manifest)) + "\n", encoding="utf-8"
        )
        os.replace(staging, output_path)
        print(f"sealed capture={output_path}")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
