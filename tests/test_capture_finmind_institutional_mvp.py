"""Drift gates for secret-safe FinMind institutional MVP capture."""

from __future__ import annotations

import json

from scripts.capture_finmind_institutional_mvp import (
    ALLOWED_DATASETS,
    SECRET_HEADERS,
    _load_protocol,
    _query,
    _safe_headers,
    _summary,
)


class _Headers:
    def items(self) -> list[tuple[str, str]]:
        return [
            ("Authorization", "secret"),
            ("Set-Cookie", "secret"),
            ("Content-Type", "application/json"),
        ]


def test_mvp_protocol_is_digest_verified_and_keeps_formal_permissions_locked() -> None:
    protocol, digest = _load_protocol()

    assert len(digest) == 64
    assert {request["dataset"] for request in protocol["fixed_requests"]} == ALLOWED_DATASETS
    assert protocol["mvp_contract"]["candidate_limit"] == 20
    assert protocol["mvp_contract"]["usable_from_session"] == "2026-08-19"
    assert protocol["execution_permissions"] == {
        "formal_candidate_prior_allowed": False,
        "formal_holdout_allowed": False,
        "formal_pit_universe_allowed": False,
        "mvp_candidate_observation_allowed": True,
        "order_submission_allowed": False,
        "outcome_generation_allowed": False,
        "production_strategy_binding_allowed": False,
    }


def test_mvp_capture_query_and_headers_are_secret_safe() -> None:
    protocol, _ = _load_protocol()

    flow = _query(protocol["fixed_requests"][0])
    assert flow == {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySellWide",
        "start_date": "2026-08-18",
    }
    assert SECRET_HEADERS == {"authorization", "cookie", "set-cookie", "x-api-key"}
    assert _safe_headers(_Headers()) == {"content-type": "application/json"}


def test_mvp_capture_summary_does_not_copy_flow_values() -> None:
    body = json.dumps(
        {
            "status": 200,
            "msg": "success",
            "data": [{"stock_id": "2330", "Foreign_Investor_buy": 123}],
        }
    ).encode()

    assert _summary(body) == {
        "data_array_present": True,
        "field_names": ["Foreign_Investor_buy", "stock_id"],
        "json_message": "success",
        "json_status": 200,
        "row_count": 1,
    }
