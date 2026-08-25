"""Capture a frozen, non-price FinMind PIT/reference qualification probe."""

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
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "credentialed_finmind_pit_reference_probe_protocol_v1_2026-08-24.json"
)
SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}
FORBIDDEN_DATASETS = {
    "TaiwanStockKBar",
    "TaiwanStockPrice",
    "TaiwanStockPriceAdj",
    "TaiwanStockPriceTick",
}


def _load_protocol() -> tuple[dict[str, Any], str]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    digest = sha256_text(canonical_json(protocol))
    expected = PROTOCOL_PATH.with_suffix(".canonical.sha256").read_text(
        encoding="utf-8"
    ).strip()
    if digest != expected:
        raise RuntimeError("FinMind PIT/reference probe protocol digest drift detected")
    _validate_protocol(protocol)
    return protocol, digest


def _validate_protocol(protocol: Mapping[str, Any]) -> None:
    requests = protocol.get("fixed_requests")
    if not isinstance(requests, list) or len(requests) != 8:
        raise RuntimeError("Frozen FinMind PIT/reference request set is invalid")
    budget = protocol.get("request_budget")
    if not isinstance(budget, Mapping) or budget.get("data_requests") != len(requests):
        raise RuntimeError("Frozen FinMind PIT/reference request budget is invalid")
    safety = protocol.get("outcome_safety")
    if not isinstance(safety, Mapping) or set(safety.get("forbidden_datasets", [])) != FORBIDDEN_DATASETS:
        raise RuntimeError("Frozen FinMind PIT/reference forbidden dataset set drifted")
    if any(not isinstance(item, Mapping) for item in requests):
        raise RuntimeError("Frozen FinMind PIT/reference request item is invalid")
    if any(str(item.get("dataset")) in FORBIDDEN_DATASETS for item in requests):
        raise RuntimeError("Frozen FinMind PIT/reference request contains a price dataset")
    locks = protocol.get("execution_lock")
    if not isinstance(locks, Mapping) or any(value is not False for value in locks.values()):
        raise RuntimeError("FinMind PIT/reference probe execution lock drifted")


def _safe_headers(headers: object) -> dict[str, str]:
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    return {
        str(name).lower(): str(value)
        for name, value in items()
        if str(name).lower() not in SECRET_HEADERS
    }


def _query_from_request(item: Mapping[str, Any]) -> dict[str, str]:
    query = {"dataset": str(item["dataset"])}
    for key in ("data_id", "start_date", "end_date"):
        value = item.get(key)
        if value is not None:
            query[key] = str(value)
    return query


def _request_once(url: str, token: str) -> tuple[int, dict[str, str], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "tw-intraday-trader-pit-reference-probe/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return int(response.status), _safe_headers(response.headers), response.read()
    except HTTPError as error:
        return int(error.code), _safe_headers(error.headers), error.read()
    except URLError as error:
        raise RuntimeError(f"FinMind PIT/reference transport failed: {error.reason}") from error


def _summarize_body(body: bytes) -> dict[str, object]:
    """Return only envelope, schema, and date-range evidence; never row values."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "data_array_present": False,
            "date_field_min": None,
            "date_field_max": None,
            "field_names": [],
            "json_message": None,
            "json_status": None,
            "row_count": None,
        }
    if not isinstance(payload, Mapping):
        return {
            "data_array_present": False,
            "date_field_min": None,
            "date_field_max": None,
            "field_names": [],
            "json_message": None,
            "json_status": None,
            "row_count": None,
        }
    rows = payload.get("data")
    if not isinstance(rows, list):
        return {
            "data_array_present": False,
            "date_field_min": None,
            "date_field_max": None,
            "field_names": [],
            "json_message": payload.get("msg"),
            "json_status": payload.get("status"),
            "row_count": None,
        }
    field_names = sorted(
        {
            str(key)
            for row in rows
            if isinstance(row, Mapping)
            for key in row.keys()
        }
    )
    date_values = sorted(
        str(row["date"])
        for row in rows
        if isinstance(row, Mapping) and row.get("date") is not None
    )
    return {
        "data_array_present": True,
        "date_field_min": date_values[0] if date_values else None,
        "date_field_max": date_values[-1] if date_values else None,
        "field_names": field_names,
        "json_message": payload.get("msg"),
        "json_status": payload.get("status"),
        "row_count": len(rows),
    }


def _output_path(protocol: Mapping[str, Any]) -> Path:
    capture = protocol["response_capture"]
    if not isinstance(capture, Mapping):
        raise RuntimeError("FinMind PIT/reference response-capture contract is invalid")
    directory = capture.get("immutable_output_directory")
    if not isinstance(directory, str) or not directory:
        raise RuntimeError("FinMind PIT/reference output directory is invalid")
    return PROTOCOL_PATH.parent / directory


def _usage_preflight(protocol: Mapping[str, Any], token: str) -> dict[str, int]:
    try:
        usage = FinMindApiClient(token).usage()
    except FinMindRequestError as error:
        raise RuntimeError("FinMind usage preflight failed") from error
    budget = protocol["request_budget"]
    if not isinstance(budget, Mapping):
        raise RuntimeError("FinMind PIT/reference request budget is invalid")
    data_requests = int(budget["data_requests"])
    minimum_remaining = int(budget["minimum_remaining_after_probe"])
    if usage.remaining < data_requests + minimum_remaining:
        raise RuntimeError(
            "FinMind PIT/reference request budget is insufficient; no data request sent"
        )
    return {
        "api_request_limit": usage.api_request_limit,
        "remaining_before": usage.remaining,
        "user_count_before": usage.user_count,
    }


def _write_record(
    *,
    staging: Path,
    index: int,
    item: Mapping[str, Any],
    endpoint: str,
    token: str,
) -> dict[str, object]:
    query = _query_from_request(item)
    if query["dataset"] in FORBIDDEN_DATASETS:
        raise RuntimeError("Price dataset request rejected by PIT/reference capture")
    url = f"{endpoint}?{urlencode(query)}"
    retrieved_at = datetime.now().astimezone().isoformat()
    http_status, headers, body = _request_once(url, token)
    stem = f"finmind_{index:02d}_{query['dataset']}"
    if "data_id" in query:
        stem = f"{stem}_{query['data_id']}"
    body_name = f"{stem}.response.bin"
    (staging / body_name).write_bytes(body)
    summary = _summarize_body(body)
    record: dict[str, object] = {
        "body_file": body_name,
        "dataset": query["dataset"],
        "http_status": http_status,
        "market": item.get("market"),
        "raw_response_bytes": len(body),
        "raw_response_sha256": hashlib.sha256(body).hexdigest(),
        "request": {"endpoint": endpoint, "query": query},
        "response_headers_without_secrets": headers,
        "retrieved_at": retrieved_at,
        "role": str(item["role"]),
        "source_version": "FINMIND_API_V4",
        **summary,
    }
    (staging / f"{stem}.metadata.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate credential and quota budget without calling a data dataset",
    )
    args = parser.parse_args()

    protocol, protocol_digest = _load_protocol()
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.environ.get("FINMIND_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("FINMIND_API_TOKEN is missing")
    usage_preflight = _usage_preflight(protocol, token)
    if args.preflight_only:
        print(
            "FinMind PIT/reference preflight passed "
            f"remaining_before={usage_preflight['remaining_before']}"
        )
        return

    output_path = _output_path(protocol)
    if output_path.exists():
        raise RuntimeError("Immutable FinMind PIT/reference capture already exists")
    endpoint = str(protocol["http_contract"]["endpoint"])
    requests = protocol["fixed_requests"]
    assert isinstance(requests, list)
    staging = Path(tempfile.mkdtemp(prefix="finmind-pit-reference-", dir=output_path.parent))
    try:
        records: list[dict[str, object]] = []
        for index, item in enumerate(requests, start=1):
            assert isinstance(item, Mapping)
            record = _write_record(
                staging=staging,
                index=index,
                item=item,
                endpoint=endpoint,
                token=token,
            )
            records.append(record)
            print(
                f"captured request={index}/{len(requests)} "
                f"dataset={record['dataset']} http_status={record['http_status']} "
                f"rows={record['row_count']}"
            )
        manifest = {
            "artifact_id": "credentialed-finmind-pit-reference-probe-capture-v1-2026-08-24-r1",
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
            "schema_version": "credentialed_finmind_pit_reference_probe_capture_v1",
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
