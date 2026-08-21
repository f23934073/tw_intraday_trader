"""Unit gates for secret-safe immutable FinMind response capture."""

from __future__ import annotations

import hashlib
import json

from scripts.capture_finmind_intraday_probe import (
    SECRET_HEADERS,
    _load_protocol,
    _load_staged_prefix,
    _revision_paths,
    _response_envelope,
    _safe_headers,
)


class _Headers:
    def items(self) -> list[tuple[str, str]]:
        return [
            ("Authorization", "secret"),
            ("Set-Cookie", "secret"),
            ("Content-Type", "application/json"),
        ]


def test_capture_loads_only_digest_verified_protocol() -> None:
    protocol, digest = _load_protocol()
    assert protocol["authentication"]["credential_environment_name"] == (
        "FINMIND_API_TOKEN"
    )
    assert len(protocol["fixed_requests"]) == 10
    assert len(digest) == 64


def test_capture_resolves_r2_to_distinct_immutable_paths() -> None:
    r1_protocol, r1_output = _revision_paths("r1")
    r2_protocol, r2_output = _revision_paths("r2")
    assert r1_protocol != r2_protocol
    assert r1_output != r2_output
    assert r1_output.name.endswith("-r1")
    assert r2_output.name.endswith("-r2")


def test_capture_filters_secret_headers() -> None:
    assert {"authorization", "cookie", "set-cookie", "x-api-key"} == SECRET_HEADERS
    assert _safe_headers(_Headers()) == {"content-type": "application/json"}


def test_envelope_parser_does_not_copy_data_payload() -> None:
    body = json.dumps({"status": 200, "msg": "success", "data": [{"secret": 1}]}).encode()
    assert _response_envelope(body) == (200, "success", True)


def test_envelope_parser_handles_non_json() -> None:
    assert _response_envelope(b"not-json") == (None, None, False)


def test_resume_accepts_only_digest_verified_contiguous_prefix(tmp_path) -> None:
    protocol, _ = _load_protocol("r2")
    item = protocol["fixed_requests"][0]
    body = b'{"status":200,"msg":"success","data":[]}'
    body_name = "finmind_01_1259_TaiwanStockKBar.response.bin"
    (tmp_path / body_name).write_bytes(body)
    record = {
        "body_file": body_name,
        "raw_response_sha256": hashlib.sha256(body).hexdigest(),
        "request": {
            "query": {
                "dataset": item["dataset"],
                "data_id": item["data_id"],
                "start_date": item["start_date"],
            }
        },
    }
    (tmp_path / "finmind_01_1259_TaiwanStockKBar.metadata.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    assert _load_staged_prefix(tmp_path, protocol["fixed_requests"]) == [record]
