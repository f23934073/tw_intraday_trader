from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.trade_management_builders import build_trade_thesis, market_at
from trading.trade_management import ThesisStatus
from trading.thesis_monitor import (
    ConditionOutcome,
    MarketContextStatus,
    ThesisMarketContext,
    ThesisMonitor,
    ThesisReasonCode,
)


def ready_context(**changes: object) -> ThesisMarketContext:
    thesis = build_trade_thesis()
    context = ThesisMarketContext(
        thesis_id=thesis.thesis_id,
        trade_id=thesis.trade_id,
        session_id=thesis.draft.session_id,
        symbol=thesis.draft.symbol,
        source_event_id="tick-2330-093303",
        observed_at=market_at(9, 33, 3, "tick-2330-093303"),
        data_status=MarketContextStatus.READY,
        health_state="HEALTHY",
        highest_price_since_entry=Decimal("600.5"),
        post_entry_volume_shares=1100,
        volume_baseline_shares=Decimal("1000"),
        volume_sample_count=5,
        completed_bar_count=1,
        completed_bars_below_vwap=0,
        consecutive_completed_bars_below_vwap=0,
        consecutive_completed_bars_below_breakout=0,
    )
    return replace(context, **changes)


def test_all_expected_behavior_met_is_valid() -> None:
    context = ready_context(
        highest_price_since_entry=Decimal("600.5001"),
        post_entry_volume_shares=1200,
    )

    result = ThesisMonitor().evaluate(build_trade_thesis(), context)

    assert result.status is ThesisStatus.VALID
    assert result.reason_codes == (ThesisReasonCode.ALL_EXPECTED_BEHAVIOR_MET,)
    assert all(
        condition.outcome
        in {ConditionOutcome.SATISFIED, ConditionOutcome.NOT_TRIGGERED}
        for condition in result.conditions
    )


def test_condition_comparison_boundaries_are_frozen() -> None:
    thesis = build_trade_thesis()

    new_high_equal = ThesisMonitor().evaluate(
        thesis,
        ready_context(
            highest_price_since_entry=Decimal("600.5"),
            post_entry_volume_shares=1200,
        ),
    )
    volume_ratio_equal = ThesisMonitor().evaluate(
        thesis,
        ready_context(
            highest_price_since_entry=Decimal("600.5001"),
            post_entry_volume_shares=1200,
        ),
    )

    assert new_high_equal.status is ThesisStatus.VALID
    assert new_high_equal.reason_codes == (
        ThesisReasonCode.EXPECTED_BEHAVIOR_PENDING,
    )
    assert volume_ratio_equal.reason_codes == (
        ThesisReasonCode.ALL_EXPECTED_BEHAVIOR_MET,
    )

def test_pending_expected_behavior_before_warning_is_still_valid() -> None:
    result = ThesisMonitor().evaluate(build_trade_thesis(), ready_context())

    assert result.status is ThesisStatus.VALID
    assert result.reason_codes == (ThesisReasonCode.EXPECTED_BEHAVIOR_PENDING,)


def test_warning_starts_at_exact_warning_boundary() -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(
            source_event_id="tick-2330-093403",
            observed_at=market_at(9, 34, 3, "tick-2330-093403"),
        ),
    )

    assert result.status is ThesisStatus.WARNING
    assert result.reason_codes == (ThesisReasonCode.EXPECTED_BEHAVIOR_WARNING,)


def test_unmet_expected_behavior_is_invalid_at_exact_deadline() -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(
            source_event_id="tick-2330-093603",
            observed_at=market_at(9, 36, 3, "tick-2330-093603"),
        ),
    )

    assert result.status is ThesisStatus.INVALID
    assert result.reason_codes == (ThesisReasonCode.EXPECTED_BEHAVIOR_EXPIRED,)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {"consecutive_completed_bars_below_breakout": 1},
            ThesisReasonCode.BREAKOUT_LEVEL_LOST,
        ),
        (
            {"consecutive_completed_bars_below_vwap": 1},
            ThesisReasonCode.VWAP_CONFIRMATION_LOST,
        ),
    ],
)
def test_hard_invalid_condition_has_priority(
    changes: dict[str, object],
    reason: ThesisReasonCode,
) -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(**changes),
    )

    assert result.status is ThesisStatus.INVALID
    assert reason in result.reason_codes


@pytest.mark.parametrize(
    ("data_status", "reason"),
    [
        (MarketContextStatus.MISSING, ThesisReasonCode.MARKET_DATA_MISSING),
        (MarketContextStatus.STALE, ThesisReasonCode.MARKET_DATA_STALE),
        (
            MarketContextStatus.OUT_OF_ORDER,
            ThesisReasonCode.MARKET_DATA_OUT_OF_ORDER,
        ),
        (
            MarketContextStatus.SESSION_MISMATCH,
            ThesisReasonCode.SESSION_MISMATCH,
        ),
    ],
)
def test_unreliable_market_context_is_insufficient_data(
    data_status: MarketContextStatus,
    reason: ThesisReasonCode,
) -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(data_status=data_status),
    )

    assert result.status is ThesisStatus.INSUFFICIENT_DATA
    assert reason in result.reason_codes


def test_blocked_health_state_is_insufficient_not_invalid() -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(health_state="BLOCKED"),
    )

    assert result.status is ThesisStatus.INSUFFICIENT_DATA
    assert result.reason_codes == (ThesisReasonCode.SESSION_DATA_BLOCKED,)


@pytest.mark.parametrize(
    "changes",
    [
        {"highest_price_since_entry": None},
        {"post_entry_volume_shares": None},
        {"volume_baseline_shares": None},
        {"volume_sample_count": None},
        {"completed_bar_count": 0},
        {"completed_bars_below_vwap": None},
        {"consecutive_completed_bars_below_vwap": None},
        {"consecutive_completed_bars_below_breakout": None},
    ],
)
def test_missing_required_observation_is_insufficient_data(
    changes: dict[str, object],
) -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(**changes),
    )

    assert result.status is ThesisStatus.INSUFFICIENT_DATA
    assert ThesisReasonCode.REQUIRED_INPUT_MISSING in result.reason_codes


def test_observation_before_fill_is_insufficient_data() -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(
            source_event_id="tick-2330-093102",
            observed_at=market_at(9, 31, 2, "tick-2330-093102"),
        ),
    )

    assert result.status is ThesisStatus.INSUFFICIENT_DATA
    assert result.reason_codes == (ThesisReasonCode.OBSERVED_BEFORE_FILL,)


def test_invalid_status_is_latched_by_explicit_prior_status() -> None:
    result = ThesisMonitor().evaluate(
        build_trade_thesis(),
        ready_context(
            prior_status=ThesisStatus.INVALID,
            data_status=MarketContextStatus.STALE,
        ),
    )

    assert result.status is ThesisStatus.INVALID
    assert result.reason_codes == (ThesisReasonCode.INVALID_LATCHED,)


def test_context_identity_mismatch_is_a_contract_error() -> None:
    with pytest.raises(ValueError, match="symbol does not match"):
        ThesisMonitor().evaluate(
            build_trade_thesis(),
            ready_context(symbol="2317"),
        )


def test_inputs_and_outputs_are_immutable_and_deterministic() -> None:
    thesis = build_trade_thesis()
    context = ready_context()
    monitor = ThesisMonitor()

    results = tuple(monitor.evaluate(thesis, context) for _ in range(10))

    assert len(set(results)) == 1
    assert len({result.evaluation_id for result in results}) == 1
    assert len({result.input_digest for result in results}) == 1
    with pytest.raises(FrozenInstanceError):
        context.health_state = "BLOCKED"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        results[0].status = ThesisStatus.INVALID  # type: ignore[misc]


def test_monitor_has_no_execution_or_mutation_authority() -> None:
    module_path = Path(__file__).parents[1] / "trading" / "thesis_monitor.py"
    tree = ast.parse(module_path.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    forbidden = {
        "Journal",
        "RiskGate",
        "Position",
        "Order",
        "ExitRecommendation",
        "SimulationService",
        "Broker",
        "datetime",
    }

    assert imports.isdisjoint(
        {
            "trading.journal",
            "trading.risk",
            "position",
            "simulation",
            "market_data.replay",
        }
    )
    assert referenced_names.isdisjoint(forbidden)
    result = ThesisMonitor().evaluate(build_trade_thesis(), ready_context())
    assert not hasattr(result, "action")
    assert not hasattr(result, "order")
    assert not hasattr(result, "recommendation")


def test_context_rejects_noncanonical_source_identity_and_negative_counts() -> None:
    with pytest.raises(ValueError, match="source_event_id must match"):
        ready_context(source_event_id="different-event")
    with pytest.raises(ValueError, match="must not be negative"):
        ready_context(volume_sample_count=-1)


def test_context_observation_age_is_derived_from_fill_not_signal() -> None:
    thesis = build_trade_thesis()
    context = ready_context()

    assert context.observed_at.value - thesis.thesis_start_at.value == timedelta(minutes=2)
