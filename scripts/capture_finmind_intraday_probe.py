"""Seal the frozen credentialed FinMind probe before semantic analysis."""

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
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text


PROTOCOL_R1_PATH = (
    PROJECT_ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21.json"
)
PROTOCOL_R2_PATH = PROTOCOL_R1_PATH.with_name(
    "credentialed_finmind_intraday_source_probe_protocol_v1_2026-08-21_r2.json"
)
SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


def _revision_paths(revision: str) -> tuple[Path, Path]:
    if revision == "r1":
        return PROTOCOL_R1_PATH, PROTOCOL_R1_PATH.with_name(
            "credentialed_finmind_intraday_source_probe_capture_v1_2026-08-21-r1"
        )
    if revision == "r2":
        return PROTOCOL_R2_PATH, PROTOCOL_R2_PATH.with_name(
            "credentialed_finmind_intraday_source_probe_capture_v1_2026-08-21-r2"
        )
    raise ValueError(f"Unsupported FinMind probe revision: {revision}")


def _load_protocol(revision: str = "r1") -> tuple[dict[str, Any], str]:
    protocol_path, _ = _revision_paths(revision)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    digest = sha256_text(canonical_json(protocol))
    if digest != protocol_path.with_suffix(".canonical.sha256").read_text(
        encoding="utf-8"
    ).strip():
        raise RuntimeError("FinMind probe protocol digest drift detected")
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


def _response_envelope(body: bytes) -> tuple[object, object, bool]:
    """Extract only envelope status, message, and data-array shape."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None, False
    if not isinstance(payload, dict):
        return None, None, False
    return payload.get("status"), payload.get("msg"), isinstance(payload.get("data"), list)


def _request_once(url: str, token: str) -> tuple[int, dict[str, str], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "tw-intraday-trader-research-probe/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return int(response.status), _safe_headers(response.headers), response.read()
    except HTTPError as error:
        return int(error.code), _safe_headers(error.headers), error.read()
    except URLError as error:
        raise RuntimeError(f"FinMind transport failed: {error.reason}") from error


def _load_staged_prefix(
    staging: Path, requests: list[object]
) -> list[dict[str, object]]:
    metadata_paths = sorted(staging.glob("finmind_*.metadata.json"))
    records: list[dict[str, object]] = []
    if len(metadata_paths) > len(requests):
        raise RuntimeError("Staged FinMind prefix exceeds the frozen request set")
    for index, metadata_path in enumerate(metadata_paths, start=1):
        item = requests[index - 1]
        if not isinstance(item, dict):
            raise RuntimeError("Frozen FinMind request item is invalid")
        record = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_query = {
            "dataset": str(item["dataset"]),
            "data_id": str(item["data_id"]),
            "start_date": str(item["start_date"]),
        }
        if record.get("request", {}).get("query") != expected_query:
            raise RuntimeError("Staged FinMind request prefix drift detected")
        body_path = staging / str(record["body_file"])
        if not body_path.is_file():
            raise RuntimeError("Staged FinMind response body is missing")
        if hashlib.sha256(body_path.read_bytes()).hexdigest() != record.get(
            "raw_response_sha256"
        ):
            raise RuntimeError("Staged FinMind response digest drift detected")
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", choices=("r1", "r2"), default="r1")
    parser.add_argument("--resume-staging", type=Path)
    args = parser.parse_args()
    _, output_path = _revision_paths(args.revision)
    if output_path.exists():
        raise RuntimeError(f"Immutable capture already exists: {output_path}")

    load_dotenv(PROJECT_ROOT / ".env")
    token = os.environ.get("FINMIND_API_TOKEN", "")
    if not token:
        raise RuntimeError("FINMIND_API_TOKEN is missing")

    protocol, protocol_digest = _load_protocol(args.revision)
    endpoint = str(protocol["http_contract"]["endpoint"])
    requests = protocol["fixed_requests"]
    if not isinstance(requests, list) or len(requests) != 10:
        raise RuntimeError("Frozen FinMind request set is invalid")

    if args.resume_staging is None:
        staging = Path(
            tempfile.mkdtemp(prefix="finmind-probe-", dir=output_path.parent)
        )
        records: list[dict[str, object]] = []
    else:
        staging = args.resume_staging.resolve()
        if (
            staging.parent != output_path.parent.resolve()
            or not staging.name.startswith("finmind-probe-")
            or not staging.is_dir()
        ):
            raise RuntimeError("Resume staging path is outside the probe boundary")
        records = _load_staged_prefix(staging, requests)
        print(f"validated staged prefix={len(records)}/10")
    try:
        for index, item in enumerate(requests[len(records) :], start=len(records) + 1):
            if not isinstance(item, dict):
                raise RuntimeError("Frozen FinMind request item is invalid")
            query = {
                "dataset": str(item["dataset"]),
                "data_id": str(item["data_id"]),
                "start_date": str(item["start_date"]),
            }
            url = f"{endpoint}?{urlencode(query)}"
            retrieved_at = datetime.now().astimezone().isoformat()
            http_status, headers, body = _request_once(url, token)
            json_status, json_message, has_data_array = _response_envelope(body)
            stem = f"finmind_{index:02d}_{query['data_id']}_{query['dataset']}"
            body_name = f"{stem}.response.bin"
            (staging / body_name).write_bytes(body)
            record = {
                "body_file": body_name,
                "data_array_present": has_data_array,
                "dataset": query["dataset"],
                "http_status": http_status,
                "json_message": json_message,
                "json_status": json_status,
                "market": str(item["market"]),
                "raw_response_bytes": len(body),
                "raw_response_sha256": hashlib.sha256(body).hexdigest(),
                "request": {"endpoint": endpoint, "query": query},
                "response_headers_without_secrets": headers,
                "retrieved_at": retrieved_at,
                "role": str(item["role"]),
                "source_version": str(protocol["http_contract"]["transport_version"]),
                "symbol": query["data_id"],
            }
            (staging / f"{stem}.metadata.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            records.append(record)
            print(
                "captured"
                f" request={index}/10 symbol={query['data_id']}"
                f" dataset={query['dataset']} http_status={http_status}"
                f" json_status={json_status!r} bytes={len(body)}"
            )

        manifest = {
            "artifact_id": (
                "credentialed-finmind-intraday-source-probe-capture-"
                f"v1-2026-08-21-{args.revision}"
            ),
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
            "schema_version": (
                "credentialed_finmind_intraday_source_probe_capture_v1"
            ),
        }
        manifest_text = canonical_json(manifest)
        (staging / "capture_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "capture_manifest.canonical.sha256").write_text(
            sha256_text(manifest_text) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output_path)
        print(f"sealed capture={output_path}")
    except Exception:
        if args.resume_staging is None:
            shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
