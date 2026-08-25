"""Drift gates for the bounded, non-price FinMind PIT/reference probe."""

from __future__ import annotations

import json

from scripts.capture_finmind_pit_reference_probe import (
    FORBIDDEN_DATASETS,
    SECRET_HEADERS,
    _load_protocol,
    _query_from_request,
    _safe_headers,
    _summarize_body,
)


class _Headers:
    def items(self) -> list[tuple[str, str]]:
        return [
            ("Authorization", "secret"),
            ("Set-Cookie", "secret"),
            ("Content-Type", "application/json"),
        ]


def test_probe_protocol_is_digest_verified_and_non_price() -> None:
    protocol, digest = _load_protocol()

    assert len(digest) == 64
    assert protocol["schema_version"] == "credentialed_finmind_pit_reference_probe_protocol_v1"
    assert protocol["request_budget"]["data_requests"] == 8
    assert protocol["request_budget"]["minimum_remaining_after_probe"] == 100
    assert set(protocol["outcome_safety"]["forbidden_datasets"]) == FORBIDDEN_DATASETS
    assert all(
        request["dataset"] not in FORBIDDEN_DATASETS
        for request in protocol["fixed_requests"]
    )
    assert all(value is False for value in protocol["execution_lock"].values())


def test_probe_uses_only_explicit_optional_query_fields() -> None:
    protocol, _ = _load_protocol()

    info = _query_from_request(protocol["fixed_requests"][0])
    twse_calendar = _query_from_request(protocol["fixed_requests"][4])
    assert info == {"dataset": "TaiwanStockInfo"}
    assert twse_calendar == {
        "dataset": "TaiwanStockTradingDate",
        "data_id": "2330",
        "start_date": "2023-08-21",
        "end_date": "2023-08-23",
    }


def test_probe_filters_secret_headers() -> None:
    assert SECRET_HEADERS == {"authorization", "cookie", "set-cookie", "x-api-key"}
    assert _safe_headers(_Headers()) == {"content-type": "application/json"}


def test_probe_summary_keeps_schema_and_date_range_but_not_row_values() -> None:
    body = json.dumps(
        {
            "status": 200,
            "msg": "success",
            "data": [
                {"date": "2023-08-21", "stock_id": "2330", "industry": "x"},
                {"date": "2023-08-23", "stock_id": "1240", "industry": "y"},
            ],
        }
    ).encode()

    summary = _summarize_body(body)
    assert summary == {
        "data_array_present": True,
        "date_field_min": "2023-08-21",
        "date_field_max": "2023-08-23",
        "field_names": ["date", "industry", "stock_id"],
        "json_message": "success",
        "json_status": 200,
        "row_count": 2,
    }
