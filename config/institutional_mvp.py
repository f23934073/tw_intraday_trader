"""Reviewed constants and policy loader for FinMind institutional MVP daily runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.domain import InstitutionalMvpDailyPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data/institutional_mvp"
ACQUISITION_LOCK_PATH = (
    PROJECT_ROOT / "data/.locks/finmind_institutional_mvp_daily.lock"
)
BASE_POLICY_PATH = (
    PROJECT_ROOT
    / "research/institutional_evaluation/mvp"
    / "finmind_institutional_mvp_candidate_policy_v1_2026-08-24-r2.json"
)
EXPECTED_BASE_POLICY_DIGEST = (
    "48db00974a2a5f916eef92bdc4cccef039d342d528457ada72fd216f8c23a18a"
)
EXPECTED_CALENDAR_SCHEMA_VERSION = "twse_calendar_2026_v1"
EXPECTED_CALENDAR_TIMEZONE = "Asia/Taipei"
EXPECTED_CALENDAR_SOURCE_DIGEST = (
    "1671338c8247f7f5344657912f469fce111b82b9be0dea1d61d21eb6d3a3593a"
)
CALENDAR_SCOPE = "TWSE_REVIEWED_PROXY_FOR_CURRENT_TWSE_TPEX_MVP"
MINIMUM_REMAINING_AFTER_BATCH = 100
DATA_REQUEST_COUNT = 2


def load_daily_policy() -> InstitutionalMvpDailyPolicy:
    """Validate the sealed r2 rule artifact and derive its daily projection."""
    raw = json.loads(BASE_POLICY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise RuntimeError("FinMind MVP base policy must be one JSON object")
    digest = sha256_text(canonical_json(raw))
    sidecar = BASE_POLICY_PATH.with_suffix(".canonical.sha256").read_text(
        encoding="utf-8"
    ).strip()
    if digest != sidecar or digest != EXPECTED_BASE_POLICY_DIGEST:
        raise RuntimeError("FinMind MVP base policy digest drift detected")

    contract = _mapping(raw.get("candidate_contract"), "candidate_contract")
    permissions = _mapping(raw.get("execution_permissions"), "execution_permissions")
    if not permissions or any(
        not isinstance(name, str) or not isinstance(value, bool)
        for name, value in permissions.items()
    ):
        raise RuntimeError("FinMind MVP base policy permissions are invalid")
    limitations = raw.get("mvp_limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item.strip() for item in limitations
    ):
        raise RuntimeError("FinMind MVP base policy limitations are invalid")

    expected = {
        "candidate_limit": 20,
        "candidate_rule": "FOREIGN_INVESTOR_NET_GT_0_AND_INVESTMENT_TRUST_NET_GT_0_AND_CANONICAL_DEALER_NET_GT_0",
        "dealer_total_net_formula": "IF_ANY_DEALER_SELF_OR_HEDGING_FIELD_IS_NONZERO:(Dealer_self_buy-Dealer_self_sell)+(Dealer_Hedging_buy-Dealer_Hedging_sell);_ELSE:(Dealer_buy-Dealer_sell)",
        "market_mapping": "LATEST_TAIWAN_STOCK_INFO_ROW_PER_SYMBOL;_CURRENT_MAPPING_ONLY",
        "rank_rule": "DESCENDING_BY_SUM_OF_FOREIGN_TRUST_AND_DEALER_TOTAL_NET_SHARES",
    }
    if any(contract.get(name) != value for name, value in expected.items()):
        raise RuntimeError("FinMind MVP base candidate rule drift detected")

    return InstitutionalMvpDailyPolicy(
        artifact_id="finmind-institutional-mvp-daily-candidate-policy-v1",
        base_policy_artifact_id=_text(raw.get("artifact_id"), "artifact_id"),
        base_policy_digest=digest,
        candidate_limit=expected["candidate_limit"],
        candidate_rule=expected["candidate_rule"],
        dealer_total_net_formula=expected["dealer_total_net_formula"],
        market_mapping=expected["market_mapping"],
        rank_rule=expected["rank_rule"],
        session_binding="EXPLICIT_SOURCE_SESSION_TO_REVIEWED_NEXT_EQUITY_SESSION_V1",
        execution_permissions=tuple(
            sorted((name, value) for name, value in permissions.items())
        ),
        limitations=tuple(
            [*limitations, "TWSE_CALENDAR_IS_OPERATIONAL_PROXY_FOR_CURRENT_TWSE_TPEX_MVP"]
        ),
    )


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"FinMind MVP base policy {field_name} is invalid")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"FinMind MVP base policy {field_name} is invalid")
    return value.strip()
