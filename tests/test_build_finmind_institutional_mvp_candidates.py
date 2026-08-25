"""Drift gates for the immutable FinMind institutional MVP observation."""

from __future__ import annotations

import json

from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.finmind import (
    parse_finmind_mvp_flows,
    select_three_way_buy_candidates,
)
from scripts.build_finmind_institutional_mvp_candidates import (
    OUTPUT_PATH,
    _date_value,
    _load_inputs,
)


def test_sealed_candidate_observation_replays_the_pinned_capture_and_policy() -> None:
    policy, policy_digest, capture, capture_digest, flow_body, info_body = _load_inputs()
    result = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    expected_digest = OUTPUT_PATH.with_suffix(".canonical.sha256").read_text(
        encoding="utf-8"
    ).strip()

    assert sha256_text(canonical_json(result)) == expected_digest
    assert result["status"] == "MVP_CANDIDATE_OBSERVATION_ONLY"
    assert result["input_capture"] == {
        "artifact_id": capture["artifact_id"],
        "canonical_sha256": capture_digest,
        "flow_raw_response_sha256": "81b763a10af6e99dc06a03656088c984351cc5f60ebec022f8c6d6954551c640",
        "stock_info_raw_response_sha256": "9b97e8f0c1705696f7978d9d34c236d66f93f1fa26aed717ca31b434cec7b891",
    }
    assert result["input_candidate_policy"] == {
        "artifact_id": policy["artifact_id"],
        "canonical_sha256": policy_digest,
    }
    assert result["execution_permissions"] == policy["execution_permissions"]
    assert result["execution_permissions"]["mvp_candidate_observation_allowed"] is True
    assert all(
        value is False
        for name, value in result["execution_permissions"].items()
        if name != "mvp_candidate_observation_allowed"
    )

    contract = policy["candidate_contract"]
    flows = parse_finmind_mvp_flows(
        wide_payload=flow_body,
        stock_info_payload=info_body,
        session_date=_date_value(contract["session_date"], "session_date"),
        usable_from_session=_date_value(
            contract["usable_from_session"], "usable_from_session"
        ),
    )
    all_candidates = select_three_way_buy_candidates(flows)
    published = select_three_way_buy_candidates(flows, limit=contract["candidate_limit"])

    observation = result["candidate_observation"]
    assert observation["current_market_mapped_flow_rows"] == len(flows) == 2267
    assert observation["candidate_count_before_limit"] == len(all_candidates) == 17
    assert observation["candidates"] == [item.to_dict() for item in published]
