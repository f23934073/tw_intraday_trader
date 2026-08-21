"""Capture the frozen Fugle intraday probe without exposing credentials.

This command is intentionally bounded to the immutable protocol artifact. It
seals raw HTTP bodies and secret-free metadata before any semantic analysis.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "credentialed_intraday_source_probe_protocol_v1_2026-08-20.json"
)
PROTOCOL_DIGEST_PATH = PROTOCOL_PATH.with_suffix(".canonical.sha256")
OUTPUT_PATH = PROTOCOL_PATH.with_name(
    "credentialed_intraday_source_probe_capture_v1_2026-08-20-r1"
)
SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


def _load_protocol() -> tuple[dict[str, object], str]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    digest = sha256_text(canonical_json(protocol))
    if digest != PROTOCOL_DIGEST_PATH.read_text(encoding="utf-8").strip():
        raise RuntimeError("Probe protocol digest drift detected")
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


def _request_once(url: str, api_key: str) -> tuple[int, dict[str, str], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "tw-intraday-trader-research-probe/1.0",
            "X-API-KEY": api_key,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return int(response.status), _safe_headers(response.headers), response.read()
    except HTTPError as error:
        return int(error.code), _safe_headers(error.headers), error.read()
    except URLError as error:
        raise RuntimeError(f"Fugle transport failed: {error.reason}") from error


def main() -> None:
    if OUTPUT_PATH.exists():
        raise RuntimeError(f"Immutable capture already exists: {OUTPUT_PATH}")

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("FUGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("FUGLE_API_KEY is missing")

    protocol, protocol_digest = _load_protocol()
    fixed_probe = protocol["fixed_probe"]
    assert isinstance(fixed_probe, dict)
    endpoint_template = str(fixed_probe["endpoint_template"])
    query = fixed_probe["request"]
    assert isinstance(query, dict)
    symbols = fixed_probe["symbols"]
    assert isinstance(symbols, list)

    staging = Path(tempfile.mkdtemp(prefix="fugle-probe-", dir=OUTPUT_PATH.parent))
    records: list[dict[str, object]] = []
    try:
        for item in symbols:
            assert isinstance(item, dict)
            symbol = str(item["symbol"])
            url = f"{endpoint_template.format(symbol=symbol)}?{urlencode(query)}"
            retrieved_at = datetime.now().astimezone().isoformat()
            status, headers, body = _request_once(url, api_key)
            body_name = f"fugle_{symbol}.response.bin"
            (staging / body_name).write_bytes(body)
            record = {
                "body_file": body_name,
                "http_status": status,
                "market": str(item["market"]),
                "raw_response_bytes": len(body),
                "raw_response_sha256": hashlib.sha256(body).hexdigest(),
                "request": {
                    "endpoint": endpoint_template.format(symbol=symbol),
                    "query": query,
                },
                "response_headers_without_secrets": headers,
                "retrieved_at": retrieved_at,
                "role": str(item["role"]),
                "source_version": "FUGLE_MARKETDATA_HTTP_V1_0",
                "symbol": symbol,
            }
            (staging / f"fugle_{symbol}.metadata.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            records.append(record)
            print(f"captured symbol={symbol} http_status={status} bytes={len(body)}")

        manifest = {
            "artifact_id": "credentialed-intraday-source-probe-capture-v1-2026-08-20-r1",
            "authentication": {
                "credential_environment_name": "FUGLE_API_KEY",
                "credential_present": True,
                "credential_value_persisted": False,
            },
            "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
            "protocol_reference": {
                "artifact_id": protocol["artifact_id"],
                "canonical_sha256": protocol_digest,
            },
            "records": records,
            "schema_version": "credentialed_intraday_source_probe_capture_v1",
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
        os.replace(staging, OUTPUT_PATH)
        print(f"sealed capture={OUTPUT_PATH}")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
