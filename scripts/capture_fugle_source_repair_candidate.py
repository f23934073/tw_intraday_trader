"""Capture one immutable Fugle source-repair candidate without broker access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.domain import canonical_json  # noqa: E402
from backtest.fugle_source_repair import (  # noqa: E402
    FUGLE_ENDPOINT_TEMPLATE,
    FUGLE_SOURCE_NAME,
    FugleSourceRepairCandidateError,
    build_fugle_repair_candidate,
)


SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


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
            "User-Agent": "tw-intraday-trader-source-repair/1.0",
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


def _load_case(database: Path, case_id: str) -> dict[str, str]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT case_id, symbol, session_date, state "
            "FROM finmind_source_repair_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise KeyError(f"unknown source-repair case: {case_id}")
    result = {key: str(row[key]) for key in row.keys()}
    if result["state"] != "QUARANTINED":
        raise RuntimeError("Fugle capture requires a QUARANTINED repair case")
    return result


def _load_official_reference(
    path: Path, *, symbol: str, session_date: str
) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    target = value.get("target")
    reference = value.get("official_reference")
    if not isinstance(target, dict) or not isinstance(reference, dict):
        raise ValueError("official evidence has an unsupported schema")
    if target.get("symbol") != symbol or target.get("session_date") != session_date:
        raise ValueError("official evidence target does not match repair case")
    return reference


def _load_rotation_evidence(path: Path, *, case_id: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("credential rotation evidence must be an object")
    if value.get("case_id") != case_id:
        raise ValueError("credential rotation evidence case mismatch")
    if value.get("status") != "ROTATED_AND_EXPLICITLY_RESUMED":
        raise ValueError("credential rotation is not explicitly resumed")
    if value.get("credential_environment_name") != "FUGLE_API_KEY":
        raise ValueError("credential rotation evidence names the wrong environment")
    if value.get("credential_value_persisted") is not False:
        raise ValueError("credential rotation evidence must not persist the key")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture one Fugle minute candidate; never reviews or activates it"
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "finmind_sponsor" / "history.sqlite3",
    )
    parser.add_argument("--official-evidence", type=Path, required=True)
    parser.add_argument("--credential-rotation-evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    database = args.database if args.database.is_absolute() else PROJECT_ROOT / args.database
    evidence_path = (
        args.official_evidence
        if args.official_evidence.is_absolute()
        else PROJECT_ROOT / args.official_evidence
    )
    rotation_path = (
        args.credential_rotation_evidence
        if args.credential_rotation_evidence.is_absolute()
        else PROJECT_ROOT / args.credential_rotation_evidence
    )
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    if output_dir.exists():
        raise RuntimeError(f"immutable capture already exists: {output_dir}")

    case = _load_case(database, args.case_id)
    rotation_evidence = _load_rotation_evidence(rotation_path, case_id=args.case_id)
    rotation_evidence_sha256 = hashlib.sha256(
        canonical_json(rotation_evidence).encode("utf-8")
    ).hexdigest()
    symbol = case["symbol"]
    session_text = case["session_date"]
    session = date.fromisoformat(session_text)
    official_reference = _load_official_reference(
        evidence_path, symbol=symbol, session_date=session_text
    )
    query = {
        "fields": "open,high,low,close,volume,average,turnover",
        "from": session_text,
        "sort": "asc",
        "timeframe": "1",
        "to": session_text,
    }
    endpoint = FUGLE_ENDPOINT_TEMPLATE.format(symbol=symbol)
    source_uri = f"{endpoint}?{urlencode(query)}"

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("FUGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("FUGLE_API_KEY is missing")

    staging = Path(tempfile.mkdtemp(prefix="fugle-repair-", dir=output_dir.parent))
    try:
        retrieved_at = datetime.now().astimezone().isoformat()
        http_status, headers, raw_body = _request_once(source_uri, api_key)
        raw_sha256 = hashlib.sha256(raw_body).hexdigest()
        (staging / "raw_response.bin").write_bytes(raw_body)
        metadata = {
            "authentication": {
                "credential_environment_name": "FUGLE_API_KEY",
                "credential_present": True,
                "credential_value_persisted": False,
            },
            "case_id": args.case_id,
            "credential_rotation_evidence": {
                "canonical_sha256": rotation_evidence_sha256,
                "schema_version": rotation_evidence["schema_version"],
                "status": rotation_evidence["status"],
            },
            "http_status": http_status,
            "request": {"endpoint": endpoint, "query": query},
            "response_headers_without_secrets": headers,
            "retrieved_at": retrieved_at,
            "raw_response_bytes": len(raw_body),
            "raw_response_sha256": raw_sha256,
            "session_date": session_text,
            "source_name": FUGLE_SOURCE_NAME,
            "source_uri": source_uri,
            "symbol": symbol,
        }
        _write_json(staging / "metadata.json", metadata)

        validation: dict[str, object]
        candidate_bars: list[dict[str, object]] = []
        try:
            if http_status != 200:
                raise FugleSourceRepairCandidateError(
                    f"Fugle HTTP status is {http_status}"
                )
            payload = json.loads(raw_body)
            if not isinstance(payload, dict):
                raise FugleSourceRepairCandidateError(
                    "Fugle response root is not an object"
                )
            candidate = build_fugle_repair_candidate(
                payload,
                symbol=symbol,
                session_date=session,
                official_reference=official_reference,
            )
            validation = dict(candidate.validation)
            validation["status"] = "ACCEPTED_FOR_PROPOSAL"
            candidate_bars = [bar.to_dict() for bar in candidate.bars]
            _write_json(staging / "canonical_bars.json", candidate_bars)
        except (FugleSourceRepairCandidateError, json.JSONDecodeError) as error:
            validation = {
                "error": str(error),
                "safe_to_propose": False,
                "status": "REJECTED",
            }
        _write_json(staging / "validation.json", validation)

        manifest = {
            "artifact_id": f"fugle-source-repair-{symbol}-{session.strftime('%Y%m%d')}-v1",
            "canonical_bars_sha256": (
                hashlib.sha256(canonical_json(candidate_bars).encode("utf-8")).hexdigest()
                if candidate_bars
                else None
            ),
            "case_id": args.case_id,
            "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
            "metadata_sha256": hashlib.sha256(
                canonical_json(metadata).encode("utf-8")
            ).hexdigest(),
            "raw_response_sha256": raw_sha256,
            "schema_version": "fugle-source-repair-capture-v1",
            "status": validation["status"],
            "validation_sha256": hashlib.sha256(
                canonical_json(validation).encode("utf-8")
            ).hexdigest(),
        }
        _write_json(staging / "manifest.json", manifest)
        (staging / "manifest.canonical.sha256").write_text(
            hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
            + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output_dir)
        print(
            json.dumps(
                {
                    "bar_count": len(candidate_bars),
                    "case_id": args.case_id,
                    "output_dir": str(output_dir),
                    "raw_response_sha256": raw_sha256,
                    "status": validation["status"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if not candidate_bars:
            raise SystemExit(2)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
