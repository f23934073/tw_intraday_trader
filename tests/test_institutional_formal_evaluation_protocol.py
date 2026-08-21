"""Drift gates for the owner-approved PR-008 preregistration artifact."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from backtest.strategies import (
    EndOfDayExitStrategy,
    GapVwapEntryStrategy,
    StopLossExitStrategy,
    TakeProfitExitStrategy,
)
from institutional_data.serialization import canonical_json, sha256_text
from institutional_research.evaluation import EvaluationThresholdsV0
from watchlist.reference_data import EquityMarket


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = (
    ROOT
    / "research"
    / "institutional_evaluation"
    / "protocols"
    / "formal_evaluation_gate_v1.json"
)
PROTOCOL_DIGEST = PROTOCOL.with_suffix(".canonical.sha256")


def _load() -> dict[str, object]:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def test_owner_approved_protocol_canonical_digest_is_frozen() -> None:
    protocol = _load()
    expected = PROTOCOL_DIGEST.read_text(encoding="utf-8").strip()

    assert sha256_text(canonical_json(protocol)) == expected
    assert protocol["schema_version"] == "institutional_formal_evaluation_gate_v1"
    assert protocol["status"] == "PREREGISTERED_PENDING_COVERAGE_RESOLUTION"


def test_owner_approved_thresholds_match_evaluator_contract() -> None:
    values = _load()["gate_thresholds"]
    assert isinstance(values, dict)
    thresholds = EvaluationThresholdsV0(
        confidence_level=Decimal(values["confidence_level"]),
        minimum_sessions=values["minimum_sessions"],
        minimum_executions_per_arm=values["minimum_executions_per_arm"],
        minimum_guardrail_executions_per_arm=(
            values["minimum_guardrail_executions_per_arm"]
        ),
        maximum_turnover_rate_increase=Decimal(
            values["maximum_turnover_rate_increase"]
        ),
        maximum_guardrail_net_expectancy_deterioration=Decimal(
            values["maximum_guardrail_net_expectancy_deterioration"]
        ),
        required_markets=tuple(EquityMarket(value) for value in values["required_markets"]),
        required_liquidity_cohorts=tuple(values["required_liquidity_cohorts"]),
    )

    assert thresholds.digest == values["thresholds_digest"]
    assert thresholds.primary_metric == "combined_minus_price_only_net_expectancy"


def test_owner_approved_strategy_definition_digests_cannot_drift() -> None:
    protocol = _load()
    strategy_contract = protocol["strategy_contract"]
    assert isinstance(strategy_contract, dict)
    frozen = {
        item["strategy_id"]: item["definition_digest"]
        for item in (
            strategy_contract["entry_strategies"]
            + strategy_contract["exit_strategies"]
        )
    }
    current = {
        strategy.definition.strategy_id: strategy.definition.definition_digest
        for strategy in (
            GapVwapEntryStrategy,
            StopLossExitStrategy,
            TakeProfitExitStrategy,
            EndOfDayExitStrategy,
        )
    }

    assert current == frozen
    assert strategy_contract["entry_policy"] == "ANY"
    assert strategy_contract["exit_policy"] == "ANY"
    assert strategy_contract["priority_order"] == [
        "stop_loss_exit_v1",
        "take_profit_exit_v1",
        "end_of_day_exit_v1",
    ]
    assert strategy_contract["execution_model"] == {
        "entry_and_non_eod_exit": "NEXT_BAR_OPEN",
        "end_of_day_exit": "SESSION_CLOSE",
    }


def test_protocol_stays_locked_until_exact_coverage_dates_exist() -> None:
    protocol = _load()
    split = protocol["split_policy"]
    lock = protocol["execution_lock"]
    safety = protocol["safety"]
    assert isinstance(split, dict)
    assert isinstance(lock, dict)
    assert isinstance(safety, dict)

    assert split["status"] == "PENDING_COVERAGE_ONLY_RESOLUTION"
    assert split["exact_ranges"] == {
        "train": None,
        "validation": None,
        "holdout": None,
    }
    assert lock["outcome_generation_allowed"] is False
    assert lock["holdout_outcome_materialization_allowed"] is False
    assert lock["holdout_execution_allowed"] is False
    assert safety == {
        "broker_allowed": False,
        "execution_allowed": False,
        "real_money": "PROHIBITED",
        "subscription_allowed": False,
    }


def test_composite_definition_identities_cover_every_outcome_input() -> None:
    protocol = _load()
    strategy = protocol["strategy_contract"]
    assert isinstance(strategy, dict)
    identities = protocol["definition_identities"]
    assert isinstance(identities, dict)
    payloads = {
        "setup_definition": {
            "entry_policy": strategy["entry_policy"],
            "entry_strategies": strategy["entry_strategies"],
            "execution_model": strategy["execution_model"][
                "entry_and_non_eod_exit"
            ],
        },
        "outcome_definition": {
            "exit_policy": strategy["exit_policy"],
            "exit_strategies": strategy["exit_strategies"],
            "execution_model": strategy["execution_model"],
            "holding_period": strategy["holding_period"],
            "priority_order": strategy["priority_order"],
        },
        "cost_model": protocol["transaction_cost_model"],
        "evaluation_plan": {
            key: protocol[key]
            for key in (
                "evaluation_arms",
                "gate_thresholds",
                "liquidity_definition",
                "matched_control_definition",
                "population_definition",
                "primary_hypothesis",
                "reporting_policy",
                "split_policy",
            )
        },
    }

    for name, payload in payloads.items():
        assert sha256_text(canonical_json(payload)) == identities[name][
            "definition_digest"
        ]
