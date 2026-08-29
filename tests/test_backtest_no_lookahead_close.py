"""No-look-ahead and auction-only formal close acceptance tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from backtest.cost_policy_tw import build_cost_policy_snapshot
from backtest.domain import (
    BacktestRunConfig,
    HistoricalBar,
    StrategySetSnapshot,
    canonical_json,
    digest,
    formal_evidence_from_result,
)
from backtest.engine import HistoricalBacktestEngine
from backtest.execution_policy_tw import build_execution_policy_snapshot
from backtest.metrics import summarize_run


TAIPEI = ZoneInfo("Asia/Taipei")


def _truth_snapshot(*, auction_verified: bool = True) -> dict[str, object]:
    body: dict[str, object] = {
        "contract_version": "tw-research-truth-v1",
        "status": "VERIFIED" if auction_verified else "FAIL_CLOSED",
        "closing_auction_event_contract": {
            "status": "VERIFIED" if auction_verified else "UNKNOWN",
            "price_semantics": "AUCTION_ONLY" if auction_verified else "UNKNOWN",
            "volume_semantics": "AUCTION_ONLY" if auction_verified else "UNKNOWN",
        },
    }
    return {**body, "snapshot_digest": digest(body)}


def _config(*, auction_verified: bool = True) -> BacktestRunConfig:
    return BacktestRunConfig(
        dataset_id="no-lookahead-fixture",
        dataset_digest="no-lookahead-fixture-digest",
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=("legacy_gap_volume_vwap_entry_v1",),
            exit_strategy_ids=("take_profit_exit_v1", "end_of_day_exit_v1"),
            priority_order=("take_profit_exit_v1", "end_of_day_exit_v1"),
        ),
        engine_version="backtest-engine-v3-tw",
        minimum_oos_trades=1,
        execution_policy_snapshot=build_execution_policy_snapshot(
            participation_calibration_digest="a" * 64
        ),
        cost_policy_snapshot=build_cost_policy_snapshot(
            slippage_bps="5", slippage_calibration_digest="b" * 64
        ),
        research_truth_snapshot=_truth_snapshot(auction_verified=auction_verified),
    )


def _bar(
    day: int,
    hour: int,
    minute: int,
    opened: int,
    high: int,
    low: int,
    close: int,
    *,
    phase: str = "CONTINUOUS",
) -> HistoricalBar:
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(2026, 1, day, hour, minute, tzinfo=TAIPEI),
        open=Decimal(opened),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1_000_000,
        market_phase=phase,
        session_regime="REGULAR",
        reference_price=Decimal("100"),
        lower_limit_price=Decimal("90"),
        upper_limit_price=Decimal("110"),
    )


def _bars(*, include_auction: bool = True) -> list[HistoricalBar]:
    bars = [
        _bar(2, 13, 25, 100, 101, 99, 100),
        _bar(3, 9, 0, 103, 104, 102, 104),
        _bar(3, 9, 1, 104, 106, 103, 105),
        _bar(3, 9, 2, 105, 109, 104, 108),
        _bar(3, 13, 29, 108, 109, 107, 108),
    ]
    if include_auction:
        bars.append(_bar(3, 13, 30, 108, 108, 108, 108, phase="CLOSING_AUCTION"))
    return bars


def test_every_formal_fill_is_strictly_after_its_signal_event() -> None:
    result = HistoricalBacktestEngine().run(config=_config(), bars=_bars())
    decisions = {decision.decision_id: decision for decision in result.decisions}

    assert result.fills
    assert all(fill.filled_at > decisions[fill.decision_id].event_at for fill in result.fills)
    assert result.fills[0].filled_at.isoformat() == "2026-01-03T09:02:00+08:00"
    assert decisions[result.fills[0].decision_id].event_at.isoformat() == (
        "2026-01-03T09:01:00+08:00"
    )


def test_close_intent_uses_only_the_later_verified_1330_auction_event() -> None:
    result = HistoricalBacktestEngine().run(config=_config(), bars=_bars())

    exit_fill = result.fills[-1]
    exit_decision = next(
        item for item in result.decisions if item.decision_id == exit_fill.decision_id
    )
    assert exit_decision.event_at.isoformat() == "2026-01-03T13:29:00+08:00"
    assert exit_fill.filled_at.isoformat() == "2026-01-03T13:30:00+08:00"
    assert exit_fill.source == "CLOSING_AUCTION"
    assert result.unresolved_positions == []
    assert result.formal_evidence is not None
    assert result.formal_evidence["execution"]["auction_close_count"] == 1
    assert result.formal_evidence["execution"]["overnight_breach_count"] == 0


def test_generic_final_bar_cannot_stand_in_for_missing_auction() -> None:
    result = HistoricalBacktestEngine().run(config=_config(), bars=_bars(include_auction=False))

    assert len(result.fills) == 1
    assert result.orders[-1]["status"] == "UNFILLED_MISSING_AUCTION_CLOSE"
    assert result.unresolved_positions[0]["reason"] == "OVERNIGHT_BREACH"
    assert result.formal_evidence is not None
    assert result.formal_evidence["execution"]["auction_close_count"] == 0
    assert result.formal_evidence["execution"]["overnight_breach_count"] == 1


def test_auction_bar_without_immutable_auction_only_proof_is_unavailable() -> None:
    result = HistoricalBacktestEngine().run(config=_config(auction_verified=False), bars=_bars())

    assert len(result.fills) == 1
    assert result.orders[-1]["status"] == "UNFILLED_FORMAL_EVIDENCE"
    assert result.orders[-1]["reason"] == "MISSING_AUCTION_EVENT_PROOF"
    assert result.unresolved_positions[0]["reason"] == "OVERNIGHT_BREACH"


def test_auction_labeled_bar_at_wrong_time_cannot_close_a_position() -> None:
    bars = _bars(include_auction=False)
    bars.append(_bar(3, 13, 29, 108, 108, 108, 108, phase="CLOSING_AUCTION"))

    result = HistoricalBacktestEngine().run(config=_config(), bars=bars)

    assert len(result.fills) == 1
    assert result.orders[-1]["status"] == "UNFILLED_FORMAL_EVIDENCE"
    assert result.orders[-1]["reason"] == "INVALID_AUCTION_EVENT_TIME"
    assert result.unresolved_positions[0]["reason"] == "OVERNIGHT_BREACH"


def test_repeated_formal_runs_are_byte_identical_and_evidence_is_single_source() -> None:
    config = _config()
    results = [HistoricalBacktestEngine().run(config=config, bars=_bars()) for _ in range(3)]
    payloads = []
    for result in results:
        raw = result.to_dict()
        summary = summarize_run(config=config, result=result, dataset_research_eligible=True)
        stored = {**raw, "summary": summary}
        assert formal_evidence_from_result(stored) == raw["formal_evidence"]
        payloads.append(canonical_json(stored))

    assert payloads[1:] == [payloads[0], payloads[0]]
