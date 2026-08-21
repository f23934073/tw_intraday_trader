from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.events import (
    AggressorSide,
    EventEnvelope,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from tests.trade_management_builders import (
    EXIT_POLICY_VERSION,
    STRATEGY_VERSION,
    THESIS_VERSION,
    build_trade_thesis,
)
from trading.risk import (
    ExecutionEligibilityStatus,
    RiskPolicy,
    RiskSnapshot,
)
from trading.thesis_monitor import ThesisReasonCode
from trading.trade_management import ExitReason, ReplayRunIdentity, ThesisStatus
from trading.trade_management_replay import (
    TradeManagementReplayInput,
    TradeManagementReplayRunner,
    build_market_manifest_digest,
)


THESIS = build_trade_thesis()
POLICY = RiskPolicy(
    version="risk-v1",
    allow_strategy_origin=False,
    max_order_notional=Decimal("200000"),
    max_position_notional=Decimal("300000"),
    max_daily_loss=Decimal("50000"),
)
SNAPSHOT = RiskSnapshot(
    data_health_state="HEALTHY",
    market_open=True,
    instrument_tradable=True,
    available_cash=Decimal("0"),
    current_position_shares=1000,
    pending_buy_shares=0,
    pending_sell_shares=0,
    daily_realized_pnl=Decimal("-999999"),
    book_age_seconds=0,
)


def tick(
    sequence: int,
    hour: int,
    minute: int,
    second: int,
    price: str,
    *,
    average_price: str = "600.2",
    volume_lots: int = 1,
) -> EventEnvelope:
    event_id = f"historical-2330-{hour:02d}{minute:02d}{second:02d}-{sequence}"
    event_at = datetime(
        2026,
        8,
        20,
        hour,
        minute,
        second,
        tzinfo=THESIS.filled_at.value.tzinfo,
    )
    value = Decimal(price)
    payload = TickEvent(
        event_id=event_id,
        source=MarketEventSource.TICK,
        symbol="2330",
        session_date=event_at.date(),
        event_time=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        price=value,
        tick_volume_lots=volume_lots,
        total_volume_lots=1000 + sequence * volume_lots,
        average_price=Decimal(average_price),
        intraday_high=max(value, Decimal("600.6")),
        intraday_low=min(value, Decimal("599")),
        raw_tick_type=1,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=THESIS.draft.session_id,
        session_date=event_at.date(),
        source=MarketEventSource.TICK,
        source_mode="HISTORICAL_CAPTURE",
        stream_kind=MarketStreamKind.TICK,
        symbol="2330",
        event_at=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        source_identity=f"capture-row:{sequence}",
        payload=payload,
        raw_capture_id="historical-tick-fixture-v1",
    )


def identity(events: tuple[EventEnvelope, ...], **changes: object) -> ReplayRunIdentity:
    values: dict[str, object] = {
        "manifest_sha256": build_market_manifest_digest(events),
        "canonical_event_schema_version": MARKET_EVENT_SCHEMA_VERSION,
        "strategy_id": THESIS.draft.strategy_id,
        "strategy_version": STRATEGY_VERSION,
        "thesis_type": THESIS.draft.thesis_type,
        "thesis_version": THESIS_VERSION,
        "exit_policy_version": EXIT_POLICY_VERSION,
        "guard_policy_version": POLICY.version,
        "fill_model_version": "historical-tick-observation-v1",
        "code_identity": "git:pr-tm-006-test",
    }
    values.update(changes)
    return ReplayRunIdentity(**values)


def replay_input(
    events: tuple[EventEnvelope, ...],
    **changes: object,
) -> TradeManagementReplayInput:
    values: dict[str, object] = {
        "run_identity": identity(events),
        "thesis": THESIS,
        "events": events,
        "volume_baseline_shares": Decimal("1000"),
        "shares_per_lot": 1000,
        "remaining_quantity_shares": 1000,
        "risk_snapshot": SNAPSHOT,
        "risk_policy": POLICY,
    }
    values.update(changes)
    return TradeManagementReplayInput(**values)


def hard_invalid_events() -> tuple[EventEnvelope, ...]:
    return (
        tick(1, 9, 31, 3, "600.5"),
        tick(2, 9, 31, 30, "600.6"),
        tick(3, 9, 32, 0, "599.8"),
        tick(4, 9, 32, 30, "599.5"),
        tick(5, 9, 33, 0, "599.4"),
    )


def test_historical_ticks_reproduce_the_full_decision_chain() -> None:
    result = TradeManagementReplayRunner().run(replay_input(hard_invalid_events()))
    final = result.steps[-1]

    assert final.market_context.completed_bar_count == 2
    assert final.market_context.consecutive_completed_bars_below_breakout == 1
    assert final.evaluation.status is ThesisStatus.INVALID
    assert ThesisReasonCode.BREAKOUT_LEVEL_LOST in final.evaluation.reason_codes
    assert final.recommendation_result.recommendation is not None
    assert final.recommendation_result.recommendation.primary_reason is ExitReason.THESIS_INVALID
    assert final.eligibility is not None
    assert final.eligibility.status is ExecutionEligibilityStatus.ELIGIBLE
    assert result.verification.output.input_digest == build_market_manifest_digest(
        hard_invalid_events()
    )
    assert result.verification.output.journal_digest == result.empty_journal_digest


def test_deadline_invalid_maps_to_time_decay_without_hard_invalid() -> None:
    events = (
        tick(1, 9, 31, 3, "600.4", average_price="600.3"),
        tick(2, 9, 32, 3, "600.4", average_price="600.3"),
        tick(3, 9, 33, 3, "600.4", average_price="600.3"),
        tick(4, 9, 34, 3, "600.4", average_price="600.3"),
        tick(5, 9, 35, 3, "600.4", average_price="600.3"),
        tick(6, 9, 36, 3, "600.4", average_price="600.3"),
    )

    final = TradeManagementReplayRunner().run(replay_input(events)).steps[-1]

    assert final.evaluation.reason_codes == (
        ThesisReasonCode.EXPECTED_BEHAVIOR_EXPIRED,
    )
    assert final.recommendation_result.recommendation is not None
    assert final.recommendation_result.recommendation.primary_reason is ExitReason.TIME_DECAY


def test_same_input_replays_ten_times_with_one_output_digest() -> None:
    replay = replay_input(hard_invalid_events())
    results = tuple(TradeManagementReplayRunner().run(replay) for _ in range(10))

    assert len({item.verification.output.digest for item in results}) == 1
    assert len({item.verification.output.decision_digest for item in results}) == 1
    assert len(set(results)) == 1
    with pytest.raises(FrozenInstanceError):
        results[0].steps = ()  # type: ignore[misc]


def test_manifest_event_order_and_policy_versions_fail_closed() -> None:
    events = hard_invalid_events()

    with pytest.raises(ValueError, match="manifest digest"):
        TradeManagementReplayRunner().run(
            replay_input(
                (replace(events[0], source_identity="changed-row"), *events[1:]),
                run_identity=identity(events),
            )
        )
    with pytest.raises(ValueError, match="strictly ordered"):
        TradeManagementReplayRunner().run(
            replay_input((events[1], events[0], *events[2:]))
        )
    with pytest.raises(ValueError, match="guard policy version"):
        TradeManagementReplayRunner().run(
            replay_input(
                events,
                run_identity=identity(events, guard_policy_version="risk-v2"),
            )
        )


def test_changed_historical_evidence_changes_verified_output() -> None:
    first_events = hard_invalid_events()
    changed_events = (*first_events[:-2], tick(4, 9, 32, 30, "600.4"), tick(5, 9, 33, 0, "600.4"))

    first = TradeManagementReplayRunner().run(replay_input(first_events))
    changed = TradeManagementReplayRunner().run(replay_input(changed_events))

    assert first.verification.output.input_digest != changed.verification.output.input_digest
    assert first.verification.output.digest != changed.verification.output.digest


def test_synthetic_ticks_and_execution_capabilities_are_absent() -> None:
    events = hard_invalid_events()
    synthetic = (replace(events[0], source_mode="SYNTHETIC_REPLAY"), *events[1:])

    with pytest.raises(ValueError, match="synthetic ticks"):
        TradeManagementReplayRunner().run(replay_input(synthetic))

    root = Path(__file__).parents[1]
    source = (root / "trading" / "trade_management_replay.py").read_text()
    tree = ast.parse(source)
    imported_roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_roots.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    assert imported_roots.isdisjoint(
        {"dashboard", "position", "runtime", "simulation", "shioaji"}
    )
    assert referenced_names.isdisjoint(
        {"Journal", "OrderCommand", "OrderApplicationService", "Broker"}
    )
