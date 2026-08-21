from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Event
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pytest

from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from simulation import SimulationStateError
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationService
from trading.journal import InMemoryJournalRepository, JournalRecord, JournalSession
from trading.local_paper import (
    latest_local_paper_daily_baseline,
    write_local_paper_checkpoint,
)


TAIPEI = ZoneInfo("Asia/Taipei")
AT = datetime(2026, 8, 21, 10, 30, tzinfo=TAIPEI)


class MutableClock:
    def __init__(self, value: datetime = AT) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class StreamingProvider(MockProvider):
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

    def emit_book(
        self,
        *,
        at: datetime,
        bid: float,
        ask: float,
        bid_volume_lots: int,
        ask_volume_lots: int,
    ) -> None:
        assert self.handler is not None
        self.handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=at,
                received_at=at,
                bid_price=bid,
                ask_price=ask,
                bid_volume_lots=bid_volume_lots,
                ask_volume_lots=ask_volume_lots,
            )
        )

    def emit_tick(self, *, at: datetime, price: float) -> None:
        assert self.handler is not None
        self.handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="TICK",
                exchange_timestamp=at,
                received_at=at,
                last_price=price,
            )
        )


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("simulation worker did not reach expected state")


def command_service(
    simulation: SimulationService,
    clock: MutableClock,
) -> tuple[LocalPaperCommandService, InMemoryJournalRepository]:
    journal = InMemoryJournalRepository()
    session_id = "recoverable-order-test"
    journal.start_session(
        JournalSession(
            session_id=session_id,
            started_at=clock.now(),
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    return (
        LocalPaperCommandService(
            simulation=simulation,
            journal=journal,
            session_id=session_id,
            clock=clock,
        ),
        journal,
    )


def test_best_level_volume_drives_two_partial_fill_events() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    service = SimulationService(provider, starting_cash=Decimal("500000"), clock=clock)
    commands, journal = command_service(service, clock)

    order, _ = commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=2,
        limit_price="106",
        idempotency_key="partial-buy",
    )
    assert order["status"] == "PENDING"

    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: service.orders()[0]["status"] == "PARTIALLY_FILLED")

    partial = service.orders()[0]
    assert partial["filled_quantity"] == 1_000
    assert partial["remaining_quantity"] == 1_000
    assert service.positions()[0]["quantity"] == 1_000

    clock.value += timedelta(seconds=1)
    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.6,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")

    filled = service.orders()[0]
    assert filled["filled_quantity"] == 2_000
    assert filled["remaining_quantity"] == 0
    assert filled["filled_price"] == 105.55
    assert service.positions()[0]["quantity"] == 2_000
    assert [
        item.record.kind for item in journal.records("recoverable-order-test")
    ].count("local_paper_fill.v1") == 2
    service.close()


def test_zero_book_volume_does_not_report_or_apply_a_fill() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    service = SimulationService(provider, starting_cash=Decimal("500000"), clock=clock)
    commands, journal = command_service(service, clock)
    commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="zero-volume-buy",
    )

    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=0,
        ask_volume_lots=0,
    )
    wait_until(lambda: service.orders()[0]["last_quote_at"] is not None)

    assert service.orders()[0]["status"] == "PENDING"
    assert service.positions() == []
    assert [
        item.record.kind for item in journal.records("recoverable-order-test")
    ].count("local_paper_fill.v1") == 0
    service.close()


def test_local_paper_command_gate_rejects_sell_with_stale_executable_book() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    service = SimulationService(provider, starting_cash=Decimal("500000"), clock=clock)
    commands, _ = command_service(service, clock)
    commands.submit_strategy_order(
        intent_id="freshness-entry",
        strategy_id="opening_range_breakout",
        strategy_version="entry-v1",
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
    )
    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")

    clock.value += timedelta(seconds=10)
    rejected, _ = commands.submit_strategy_order(
        intent_id="stale-book-exit",
        strategy_id="opening_range_breakout",
        strategy_version="exit-v1",
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price="105",
    )

    assert rejected["status"] == "REJECTED"
    assert "BOOK_STALE" in rejected["reason"]
    assert service.positions()[0]["quantity"] == 1_000
    service.close()


def test_quote_fill_journal_callback_does_not_hold_simulation_lock() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    service = SimulationService(provider, starting_cash=Decimal("500000"), clock=clock)
    commands, journal = command_service(service, clock)
    commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="callback-lock-order-buy",
    )
    callback_started = Event()
    original_handler = commands._record_later_terminal_order

    def blocking_handler(order) -> None:
        callback_started.set()
        original_handler(order)

    service.set_terminal_order_handler(blocking_handler)
    executor = ThreadPoolExecutor(max_workers=1)
    commands._lock.acquire()
    try:
        provider.emit_book(
            at=clock.now(),
            bid=105.4,
            ask=105.5,
            bid_volume_lots=1,
            ask_volume_lots=1,
        )
        assert callback_started.wait(timeout=0.5)
        projection = executor.submit(service.orders).result(timeout=0.5)
        assert projection[0]["status"] == "FILLED"
    finally:
        commands._lock.release()
        executor.shutdown(wait=True)

    wait_until(
        lambda: [
            result.record.kind for result in journal.records("recoverable-order-test")
        ].count("local_paper_fill.v1")
        == 1
    )
    service.close()


def test_partially_filled_order_can_cancel_only_its_remaining_quantity() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    service = SimulationService(provider, starting_cash=Decimal("500000"), clock=clock)
    commands, _ = command_service(service, clock)
    pending, _ = commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=2,
        limit_price="106",
        idempotency_key="partial-cancel-buy",
    )
    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: service.orders()[0]["status"] == "PARTIALLY_FILLED")

    cancelled, _ = commands.cancel_order(
        pending["order_id"],
        "partial-cancel-request",
    )

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["filled_quantity"] == 1_000
    assert cancelled["remaining_quantity"] == 1_000
    assert service.positions()[0]["quantity"] == 1_000
    assert service.session()["reserved_cash"] == 0.0
    service.close()


def test_timeout_cancels_then_bounded_retry_creates_successor_order() -> None:
    clock = MutableClock()
    service = SimulationService(
        MockProvider(),
        clock=clock,
        pending_timeout_seconds=5,
        order_expiry_seconds=30,
        max_retry_attempts=2,
    )
    commands, _ = command_service(service, clock)
    pending, _ = commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key="timeout-buy",
    )

    clock.value += timedelta(seconds=6)
    service.reconcile_orders()
    cancelled = service.orders()[0]

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["reason"] == "ORDER_TIMEOUT"
    assert service.alerts()[0]["code"] == "ORDER_TIMEOUT_CANCELLED"

    retried, idempotent = commands.retry_order(
        pending["order_id"],
        "retry-timeout-buy",
    )

    assert idempotent is False
    assert retried["status"] == "PENDING"
    assert retried["attempt"] == 2
    assert retried["predecessor_order_id"] == pending["order_id"]

    clock.value += timedelta(seconds=6)
    service.reconcile_orders()
    with pytest.raises(SimulationStateError, match="重試次數已達上限"):
        commands.retry_order(retried["order_id"], "retry-over-limit")


def test_expiry_is_terminal_and_emits_alert() -> None:
    clock = MutableClock()
    service = SimulationService(
        MockProvider(),
        clock=clock,
        pending_timeout_seconds=30,
        order_expiry_seconds=10,
    )
    pending, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key="expiring-buy",
    )

    clock.value += timedelta(seconds=11)
    service.reconcile_orders()
    expired = service.orders()[0]

    assert pending["status"] == "PENDING"
    assert expired["status"] == "EXPIRED"
    assert expired["reason"] == "ORDER_EXPIRED"
    assert service.alerts()[0]["code"] == "ORDER_EXPIRED"


def test_same_trading_day_runtime_restart_restores_pending_order_idempotently() -> None:
    clock = MutableClock()
    journal = InMemoryJournalRepository()
    first = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
    )
    pending, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key="restart-pending-buy",
    )
    assert pending["status"] == "PENDING"

    restored = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
    )
    restored_order = restored.simulation_service.orders()[0]
    repeated, idempotent = restored.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="100",
        idempotency_key="restart-pending-buy",
    )

    assert restored_order["order_id"] == pending["order_id"]
    assert restored_order["status"] == "PENDING"
    assert repeated["order_id"] == pending["order_id"]
    assert idempotent is True


def test_same_day_restart_preserves_realized_pnl_against_opening_baseline() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    journal = InMemoryJournalRepository()
    first = RuntimeComposition.create(provider, clock=clock, journal=journal)
    first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="realized-baseline-buy",
    )
    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: first.simulation_service.orders()[0]["status"] == "FILLED")
    sold, _ = first.local_paper_commands.submit_order(
        symbol="3231",
        side="SELL",
        lots=1,
        limit_price="105",
        idempotency_key="realized-baseline-sell",
    )

    assert sold["status"] == "FILLED"
    assert first.simulation_service.risk_snapshot("3231")[
        "daily_realized_pnl"
    ] == Decimal("-100.0")

    first.close()
    restored = RuntimeComposition.create(MockProvider(), clock=clock, journal=journal)

    assert restored.simulation_service.risk_snapshot("3231")[
        "daily_realized_pnl"
    ] == Decimal("-100.0")


def test_restart_marks_approved_command_without_acknowledgement_for_recovery() -> None:
    clock = MutableClock()
    journal = InMemoryJournalRepository()
    first = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
    )
    session_id = first.local_paper_commands.session_id
    journal.append(
        JournalRecord(
            record_id="command:missing-ack-command",
            session_id=session_id,
            kind="order_command.v1",
            occurred_at=clock.now(),
            payload={
                "command_id": "missing-ack-command",
                "origin": "MANUAL_WEB",
                "symbol": "3231",
                "side": "BUY",
                "quantity_shares": 1_000,
                "limit_price": "100",
                "idempotency_key": "missing-ack-key",
                "strategy_id": None,
                "strategy_version": None,
                "attempt": 1,
                "predecessor_order_id": None,
                "risk_status": "APPROVED",
                "risk_reasons": [],
            },
        )
    )
    write_local_paper_checkpoint(
        journal,
        session_id=session_id,
        starting_cash=first.simulation_service.starting_cash,
    )

    restored = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
    )

    assert restored.simulation_service.orders()[0]["status"] == "RECOVERY_REQUIRED"
    assert restored.simulation_service.orders()[0]["reason"] == (
        "COMMAND_ACKNOWLEDGEMENT_MISSING"
    )
    assert restored.simulation_service.alerts()[0]["code"] == "RECOVERY_REQUIRED"


def test_cross_day_opening_equity_includes_unrealized_position_value() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    service = SimulationService(provider, starting_cash=Decimal("500000"), clock=clock)
    commands, _ = command_service(service, clock)
    commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="overnight-buy",
    )
    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")

    clock.value = datetime(2026, 8, 22, 9, 0, tzinfo=TAIPEI)
    provider.emit_tick(at=clock.now(), price=104.5)
    wait_until(lambda: service.session()["equity"] == 499_000.0)
    opening = service.session()

    assert opening["trading_date"] == "2026-08-22"
    assert opening["opening_equity"] == 500_000.0
    assert opening["equity"] == 499_000.0
    assert opening["daily_loss_includes_unrealized"] is True
    service.close()


def test_cross_day_baseline_survives_same_day_runtime_restart() -> None:
    clock = MutableClock()
    provider = StreamingProvider()
    journal = InMemoryJournalRepository()
    first = RuntimeComposition.create(provider, clock=clock, journal=journal)
    first.local_paper_commands.submit_order(
        symbol="3231",
        side="BUY",
        lots=1,
        limit_price="106",
        idempotency_key="runtime-overnight-buy",
    )
    provider.emit_book(
        at=clock.now(),
        bid=105.4,
        ask=105.5,
        bid_volume_lots=1,
        ask_volume_lots=1,
    )
    wait_until(lambda: first.simulation_service.orders()[0]["status"] == "FILLED")

    clock.value = datetime(2026, 8, 22, 9, 0, tzinfo=TAIPEI)
    provider.emit_tick(at=clock.now(), price=104.5)
    wait_until(lambda: first.simulation_service.session()["equity"] == 9_999_000.0)
    baseline = latest_local_paper_daily_baseline(
        journal,
        session_id=first.local_paper_commands.session_id,
    )
    assert baseline is not None
    assert baseline["trading_date"] == "2026-08-22"
    assert baseline["opening_equity"] == "10000000.0"

    first.close()
    restored = RuntimeComposition.create(MockProvider(), clock=clock, journal=journal)
    restored_session = restored.simulation_service.session()

    assert restored_session["trading_date"] == "2026-08-22"
    assert restored_session["opening_equity"] == 10_000_000.0
    assert restored_session["daily_loss_includes_unrealized"] is True
