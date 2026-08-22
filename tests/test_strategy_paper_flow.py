"""End-to-end contracts for strategy-origin local paper trading."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pytest

from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MarketDataProvider, MockProvider
from runtime.in_memory import InMemoryJournalRepository
from simulation.application import LocalPaperCommandService
from simulation.service import (
    SimulationService,
    SimulationStateError,
    SimulationValidationError,
)
from simulation.strategy_flow import (
    STRATEGY_PAPER_INTENT_KIND,
    StrategyPaperFlowService,
    StrategyPaperIntent,
)
from trading.journal import JournalSession
from trading.risk import CommandSide
from trading.local_paper import (
    LOCAL_PAPER_PROJECTION_NAME,
    rebuild_local_paper_projection,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_NOW = datetime(2026, 8, 21, 10, 30, tzinfo=_TAIPEI)
_SESSION_ID = "strategy-paper-test-session"


class FixedClock:
    def now(self) -> datetime:
        return _NOW

    def session_date(self) -> date:
        return _NOW.date()


class StreamingMockProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.handler = None

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self.handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        return None

    def emit_bidask(self, *, bid: float, ask: float) -> None:
        assert self.handler is not None
        now = _NOW
        self.handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=now,
                received_at=now,
                bid_price=bid,
                ask_price=ask,
            )
        )


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("quote worker did not reach the expected state")


def paper_flow(
    *,
    starting_cash: Decimal = Decimal("300000"),
    provider: MarketDataProvider | None = None,
):
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=_SESSION_ID,
            started_at=_NOW,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    simulation = SimulationService(
        provider or MockProvider(),
        starting_cash=starting_cash,
        clock=FixedClock(),
    )
    commands = LocalPaperCommandService(
        simulation=simulation,
        journal=journal,
        session_id=_SESSION_ID,
        clock=FixedClock(),
    )
    return (
        StrategyPaperFlowService(
            commands=commands,
            journal=journal,
            session_id=_SESSION_ID,
            clock=FixedClock(),
        ),
        simulation,
        journal,
    )


def intent(
    intent_id: str,
    side: CommandSide,
    limit_price: str,
) -> StrategyPaperIntent:
    return StrategyPaperIntent(
        intent_id=intent_id,
        strategy_id="opening_range_breakout",
        strategy_version="opening_range_breakout_entry_v1",
        symbol="3231",
        side=side,
        lots=1,
        limit_price=Decimal(limit_price),
        signaled_at=_NOW,
    )


def test_strategy_buy_is_journaled_risk_checked_filled_and_idempotent() -> None:
    flow, simulation, journal = paper_flow()
    buy = intent("orb-entry-3231-20260821", CommandSide.BUY, "106")

    first = flow.submit(buy)
    repeated = flow.submit(buy)

    assert first["intent_idempotent"] is False
    assert first["order_idempotent"] is False
    assert first["order"]["origin"] == "STRATEGY_AUTOMATED"
    assert first["order"]["status"] == "FILLED"
    assert repeated["intent_idempotent"] is True
    assert repeated["order_idempotent"] is True
    assert repeated["order"]["order_id"] == first["order"]["order_id"]
    assert simulation.positions()[0]["quantity"] == 1_000
    assert simulation.positions()[0]["owner_origin"] == "STRATEGY_AUTOMATED"
    assert simulation.positions()[0]["owner_strategy_id"] == "opening_range_breakout"
    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        STRATEGY_PAPER_INTENT_KIND,
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
    ]
    recorded = journal.records(_SESSION_ID)[0].record.payload
    assert recorded["strategy_id"] == "opening_range_breakout"
    assert recorded["strategy_version"] == "opening_range_breakout_entry_v1"
    assert recorded["side"] == "BUY"
    checkpoint = journal.latest_checkpoint(_SESSION_ID, LOCAL_PAPER_PROJECTION_NAME)
    assert checkpoint is not None
    assert checkpoint.journal_sequence == 4
    assert rebuild_local_paper_projection(
        journal,
        session_id=_SESSION_ID,
        starting_cash=simulation.starting_cash,
    ).digest == checkpoint.digest


def test_strategy_intent_accepts_exact_odd_lot_share_quantity() -> None:
    flow, simulation, journal = paper_flow()
    odd_lot = StrategyPaperIntent.create(
        intent_id="orb-odd-lot-entry-3231-20260821",
        strategy_id="opening_range_breakout",
        strategy_version="opening_range_breakout_entry_v1",
        symbol="3231",
        side="BUY",
        quantity_shares=125,
        limit_price="106",
        signaled_at=_NOW,
    )

    result = flow.submit(odd_lot)

    assert result["order"]["status"] == "FILLED"
    assert result["order"]["quantity_shares"] == 125
    assert simulation.positions()[0]["quantity"] == 125
    assert journal.records(_SESSION_ID)[0].record.payload["quantity_shares"] == 125


def test_strategy_buy_and_sell_complete_one_closed_local_paper_trade() -> None:
    flow, simulation, journal = paper_flow()

    buy = flow.submit(intent("orb-entry-3231-20260821", CommandSide.BUY, "106"))
    sell = flow.submit(intent("orb-exit-3231-20260821", CommandSide.SELL, "105"))

    assert buy["order"]["status"] == "FILLED"
    assert sell["order"]["status"] == "FILLED"
    assert simulation.positions() == []
    assert simulation.session()["available_cash"] == 300_000.0
    assert simulation.risk_snapshot("3231")["daily_realized_pnl"] == Decimal("0.0")
    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        STRATEGY_PAPER_INTENT_KIND,
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
        STRATEGY_PAPER_INTENT_KIND,
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
    ]


def test_strategy_cannot_sell_a_manual_position() -> None:
    flow, simulation, _ = paper_flow()
    manual, _ = simulation.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="manual-position",
    )

    result = flow.submit(
        intent("orb-exit-manual-position", CommandSide.SELL, "105")
    )

    assert manual["status"] == "FILLED"
    assert result["order"]["status"] == "REJECTED"
    assert "不屬於該策略" in result["order"]["reason"]
    assert simulation.positions()[0]["owner_origin"] == "MANUAL_WEB"


def test_later_bidask_fill_is_appended_to_journal_exactly_once() -> None:
    provider = StreamingMockProvider()
    flow, simulation, journal = paper_flow(provider=provider)

    submitted = flow.submit(
        intent("orb-stream-entry-3231-20260821", CommandSide.BUY, "106")
    )
    assert submitted["order"]["status"] == "PENDING"
    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        STRATEGY_PAPER_INTENT_KIND,
        "order_command.v1",
        "local_paper_order_state.v1",
    ]

    provider.emit_bidask(bid=105.4, ask=105.6)
    wait_until(
        lambda: simulation.orders()[0]["status"] == "FILLED"
        and len(journal.records(_SESSION_ID)) == 5
    )

    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        STRATEGY_PAPER_INTENT_KIND,
        "order_command.v1",
        "local_paper_order_state.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
    ]
    fill = journal.records(_SESSION_ID)[-2].record.payload
    assert fill["command_id"] == (
        "strategy-paper-command:orb-stream-entry-3231-20260821"
    )
    assert fill["command_idempotency_key"] == (
        "strategy-paper:orb-stream-entry-3231-20260821"
    )
    assert fill["fill_price"] == "105.6"
    checkpoint = journal.latest_checkpoint(_SESSION_ID, LOCAL_PAPER_PROJECTION_NAME)
    assert checkpoint is not None
    assert checkpoint.journal_sequence == 5

    provider.emit_bidask(bid=105.4, ask=105.6)
    wait_until(lambda: simulation.session()["quote_queue_depth"] == 0)
    assert len(journal.records(_SESSION_ID)) == 5
    simulation.close()


def test_cross_owner_pending_buy_is_rejected_before_reservation() -> None:
    provider = StreamingMockProvider()
    flow, simulation, _ = paper_flow(
        starting_cash=Decimal("500000"),
        provider=provider,
    )
    automated = flow.submit(
        intent("owner-strategy-pending", CommandSide.BUY, "106")
    )["order"]
    manual, _ = simulation.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="owner-manual-pending",
    )

    assert automated["status"] == "PENDING"
    assert manual["status"] == "REJECTED"
    assert "不同歸屬" in manual["reason"]
    assert simulation.risk_snapshot("3231")["pending_buy_shares"] == 1_000

    provider.emit_bidask(bid=105.4, ask=105.6)
    wait_until(lambda: simulation.positions())
    assert simulation.positions()[0]["quantity"] == 1_000
    assert simulation.positions()[0]["owner_origin"] == "STRATEGY_AUTOMATED"
    simulation.close()


def test_fill_time_rejects_legacy_cross_owner_pending_collision() -> None:
    provider = StreamingMockProvider()
    simulation = SimulationService(
        provider,
        starting_cash=Decimal("500000"),
        clock=FixedClock(),
    )
    first, _ = simulation.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="legacy-owner-first",
        origin="STRATEGY_AUTOMATED",
        strategy_id="atomic-set:paper-v1",
        strategy_version="pipeline-v1",
    )
    second, _ = simulation.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="legacy-owner-second",
        origin="STRATEGY_AUTOMATED",
        strategy_id="atomic-set:paper-v1",
        strategy_version="pipeline-v1",
    )
    assert first["status"] == second["status"] == "PENDING"

    # Simulate a pre-remediation/corrupt recovered order that changed owner
    # after reservation; _fill() must still refuse the merge under the lock.
    with simulation._lock:
        legacy = simulation._orders[second["order_id"]]
        legacy.origin = "MANUAL_WEB"
        legacy.strategy_id = None
        legacy.strategy_version = None

    provider.emit_bidask(bid=105.4, ask=105.6)
    wait_until(
        lambda: {item["status"] for item in simulation.orders()}
        == {"FILLED", "REJECTED"}
    )
    assert simulation.positions()[0]["quantity"] == 1_000
    assert simulation.positions()[0]["owner_origin"] == "STRATEGY_AUTOMATED"
    rejected = next(
        item for item in simulation.orders() if item["status"] == "REJECTED"
    )
    assert "成交時持倉歸屬衝突" in rejected["reason"]
    simulation.close()


def test_effective_strategy_daily_loss_policy_blocks_at_operator_limit() -> None:
    flow, simulation, journal = paper_flow(starting_cash=Decimal("300000"))
    simulation.restore_state(
        cash=Decimal("298000"),
        positions=[],
        realized_pnl_by_symbol={},
        order_states=[],
        daily_baseline={
            "trading_date": _NOW.date().isoformat(),
            "opening_equity": "300000",
            "opening_realized_pnl": "0",
            "includes_unrealized_pnl": True,
        },
    )
    effective = flow.activate_run(
        owner_strategy_id="atomic-set:paper-v1",
        operator_max_daily_loss=Decimal("1000"),
        activation_config={"pipeline_digest": "p" * 64},
        actor_id="local-operator",
        idempotency_key="activation-risk-1",
        occurred_at=_NOW,
    )
    result = flow.submit(
        StrategyPaperIntent.create(
            intent_id="operator-daily-loss-block",
            strategy_id="atomic-set:paper-v1",
            strategy_version="local-paper-pipeline:v1",
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            signaled_at=_NOW,
        )
    )

    assert effective["system_max_daily_loss"] == "300000"
    assert effective["operator_max_daily_loss"] == "1000"
    assert effective["effective_max_daily_loss"] == "1000"
    assert result["order"]["status"] == "REJECTED"
    assert "DAILY_LOSS_LIMIT" in result["order"]["reason"]
    command_record = next(
        item.record
        for item in journal.records(_SESSION_ID)
        if item.record.kind == "order_command.v1"
    )
    assert command_record.payload["risk_snapshot"]["daily_loss"] == "2000"
    assert command_record.payload["effective_risk_policy_digest"] == (
        effective["effective_policy_digest"]
    )
    assert command_record.payload["effective_risk_policy"][
        "max_daily_loss"
    ] == "1000"
    activation_record = next(
        item.record
        for item in journal.records(_SESSION_ID)
        if item.record.kind == "strategy_runtime_activation.v1"
    )
    assert activation_record.payload["effective_risk"][
        "effective_policy_digest"
    ] == effective["effective_policy_digest"]
    simulation.close()


def test_activation_preview_digest_conflict_has_no_policy_or_journal_side_effect() -> None:
    flow, simulation, journal = paper_flow(starting_cash=Decimal("300000"))

    preview = flow.preview_run_activation(
        owner_strategy_id="atomic-set:paper-v1",
        operator_max_daily_loss=Decimal("1000"),
    )

    with pytest.raises(SimulationStateError, match="preview 與 activation commit"):
        flow.activate_run(
            owner_strategy_id="atomic-set:paper-v1",
            operator_max_daily_loss=Decimal("1000"),
            activation_config={"pipeline_digest": "p" * 64},
            actor_id="local-operator",
            idempotency_key="activation-preview-conflict",
            occurred_at=_NOW,
            expected_policy_digest="f" * 64,
        )

    assert preview["effective_policy_digest"] != "f" * 64
    assert flow._commands.strategy_risk_policy(
        owner_strategy_id="atomic-set:paper-v1"
    ) is None
    assert all(
        item.record.kind != "strategy_runtime_activation.v1"
        for item in journal.records(_SESSION_ID)
    )
    simulation.close()


def test_effective_strategy_daily_loss_cannot_exceed_system_ceiling() -> None:
    flow, simulation, _ = paper_flow(starting_cash=Decimal("300000"))

    effective = flow.activate_run(
        owner_strategy_id="atomic-set:paper-v1",
        operator_max_daily_loss=Decimal("999999"),
        activation_config={"pipeline_digest": "p" * 64},
        actor_id="local-operator",
        idempotency_key="activation-risk-system-ceiling",
        occurred_at=_NOW,
    )

    assert effective["effective_max_daily_loss"] == "300000"
    simulation.close()


def test_strategy_activation_replays_same_request_without_timestamp_conflict() -> None:
    flow, simulation, journal = paper_flow(starting_cash=Decimal("300000"))
    request = {
        "owner_strategy_id": "atomic-set:paper-v1",
        "operator_max_daily_loss": Decimal("1000"),
        "activation_config": {"pipeline_digest": "p" * 64},
        "actor_id": "local-operator",
        "idempotency_key": "activation-response-loss",
    }

    first = flow.activate_run(**request, occurred_at=_NOW)
    replay = flow.activate_run(
        **request,
        occurred_at=_NOW + timedelta(seconds=5),
    )

    assert first["activation_idempotent"] is False
    assert replay["activation_idempotent"] is True
    assert replay["activation_sequence"] == first["activation_sequence"]
    assert len(
        [
            item
            for item in journal.records(_SESSION_ID)
            if item.record.kind == "strategy_runtime_activation.v1"
        ]
    ) == 1
    simulation.close()


def test_strategy_intent_over_cash_is_rejected_without_a_position() -> None:
    flow, simulation, journal = paper_flow(starting_cash=Decimal("100000"))

    result = flow.submit(intent("orb-over-cash-3231", CommandSide.BUY, "106"))

    assert result["order"]["origin"] == "STRATEGY_AUTOMATED"
    assert result["order"]["status"] == "REJECTED"
    assert "INSUFFICIENT_CASH" in result["order"]["reason"]
    assert simulation.positions() == []
    assert [item.record.kind for item in journal.records(_SESSION_ID)] == [
        STRATEGY_PAPER_INTENT_KIND,
        "order_command.v1",
        "local_paper_order_state.v1",
        "local_paper_rejection.v1",
    ]


def test_reusing_an_intent_id_with_different_content_fails_closed() -> None:
    flow, simulation, journal = paper_flow()
    flow.submit(intent("orb-conflicting-intent", CommandSide.BUY, "106"))

    with pytest.raises(SimulationStateError, match="策略意圖識別碼"):
        flow.submit(intent("orb-conflicting-intent", CommandSide.SELL, "105"))

    assert len(simulation.orders()) == 1
    assert len(journal.records(_SESSION_ID)) == 4


def test_future_strategy_signal_is_rejected_before_journal_or_order() -> None:
    flow, simulation, journal = paper_flow()
    future = StrategyPaperIntent(
        intent_id="orb-future-intent",
        strategy_id="opening_range_breakout",
        strategy_version="opening_range_breakout_entry_v1",
        symbol="3231",
        side=CommandSide.BUY,
        lots=1,
        limit_price=Decimal("106"),
        signaled_at=datetime(2026, 8, 21, 10, 31, tzinfo=_TAIPEI),
    )

    with pytest.raises(SimulationValidationError, match="不可晚於目前時間"):
        flow.submit(future)

    assert simulation.orders() == []
    assert journal.records(_SESSION_ID) == ()


def test_prior_session_strategy_signal_is_rejected_before_journal_or_order() -> None:
    flow, simulation, journal = paper_flow()
    stale = StrategyPaperIntent(
        intent_id="orb-stale-intent",
        strategy_id="opening_range_breakout",
        strategy_version="opening_range_breakout_entry_v1",
        symbol="3231",
        side=CommandSide.BUY,
        lots=1,
        limit_price=Decimal("106"),
        signaled_at=datetime(2026, 8, 20, 13, 25, tzinfo=_TAIPEI),
    )

    with pytest.raises(SimulationValidationError, match="目前本機模擬交易日"):
        flow.submit(stale)

    assert simulation.orders() == []
    assert journal.records(_SESSION_ID) == ()
