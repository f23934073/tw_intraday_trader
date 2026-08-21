from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
from runtime.in_memory import InMemoryJournalRepository
from simulation.application import LocalPaperCommandService
from simulation.continuous_strategy import (
    AutomatedStrategyConfig,
    ContinuousPaperStrategyController,
)
from simulation.service import SimulationService
from simulation.strategy_flow import StrategyPaperFlowService
from trading.journal import JournalSession


TAIPEI_AT = datetime.fromisoformat("2026-08-21T10:30:00+08:00")


class MutableClock:
    def __init__(self, value: datetime = TAIPEI_AT) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class FakeFlow:
    def __init__(self, *, order_status: str = "FILLED") -> None:
        self.order_status = order_status
        self.intents = []
        self.cancellations = []
        self.retries = []

    def submit(self, intent):
        self.intents.append(intent)
        return {
            "mode": "LOCAL_PAPER_SIMULATION",
            "intent": intent.journal_payload(),
            "order": {
                "order_id": f"order-{len(self.intents)}",
                "origin": "STRATEGY_AUTOMATED",
                "symbol": intent.symbol,
                "side": intent.side.value,
                "status": self.order_status,
            },
        }

    def cancel(self, order_id: str, idempotency_key: str):
        self.cancellations.append((order_id, idempotency_key))
        return {
            "order": {
                "order_id": order_id,
                "status": "CANCELLED",
            },
            "idempotent": False,
        }

    def retry(self, order_id: str, idempotency_key: str, *, limit_price=None):
        self.retries.append((order_id, idempotency_key, limit_price))
        return {
            "order": {
                "order_id": f"retry-{len(self.retries)}",
                "status": self.order_status,
            },
            "idempotent": False,
        }


class ProjectionReader:
    def __init__(self, projection: dict | None = None) -> None:
        self.value = projection or empty_projection()

    def __call__(self) -> dict:
        return self.value


def empty_projection(*, equity: float = 10_000_000) -> dict:
    return {
        "session": {
            "mode": "LOCAL_PAPER_SIMULATION",
            "starting_cash": 10_000_000,
            "trading_date": "2026-08-21",
            "opening_equity": 10_000_000,
            "daily_loss_includes_unrealized": True,
            "equity": equity,
            "stream_health": "HEALTHY",
            "quote_mode": "SHIOAJI_TICK_BIDASK",
            "streaming": True,
        },
        "orders": [],
        "positions": [],
    }


def live_signal(*, at: datetime = TAIPEI_AT, digest: str = "signal-digest-1") -> dict:
    return {
        "status": "live",
        "source": {
            "is_live": True,
            "connection_state": "RUNNING",
            "data_health": "HEALTHY",
            "as_of": at.isoformat(),
        },
        "items": [
            {
                "symbol": "3231",
                "availability": "EVALUATED",
                "current_stage": "ACCELERATING",
                "as_of": at.isoformat(),
                "intraday": {
                    "price": {
                        "value": "177.5",
                        "status": "VALID",
                        "source_as_of": at.isoformat(),
                        "reason": None,
                    }
                },
                "signal": {
                    "family": "OPENING_MOMENTUM",
                    "evaluation_status": "TRIGGERED",
                    "momentum_acceleration_confirmed": True,
                    "evidence_score": 85,
                    "config_version": "momentum_entry_hypothesis_v0",
                    "data_health": "HEALTHY",
                    "digest": digest,
                },
            }
        ],
    }


def config() -> AutomatedStrategyConfig:
    return AutomatedStrategyConfig.create(
        stop_loss_pct="1.5",
        take_profit_pct="3",
        max_daily_loss="50000",
        poll_seconds=0.01,
    )


def controller(
    *,
    clock: MutableClock | None = None,
    flow: FakeFlow | None = None,
    projection: ProjectionReader | None = None,
    signal_snapshot: dict | None = None,
) -> tuple[ContinuousPaperStrategyController, FakeFlow, ProjectionReader]:
    resolved_clock = clock or MutableClock()
    resolved_flow = flow or FakeFlow()
    resolved_projection = projection or ProjectionReader()
    instance = ContinuousPaperStrategyController(
        flow=resolved_flow,
        projection_reader=resolved_projection,
        signal_reader=lambda: signal_snapshot or live_signal(at=resolved_clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=resolved_clock,
    )
    instance.start(config(), background=False)
    return instance, resolved_flow, resolved_projection


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stop_loss_pct", "0"),
        ("take_profit_pct", "-1"),
        ("max_daily_loss", "0"),
    ],
)
def test_config_rejects_unbounded_or_non_positive_risk_values(field: str, value: str) -> None:
    values = {
        "stop_loss_pct": "1.5",
        "take_profit_pct": "3",
        "max_daily_loss": "50000",
    }
    values[field] = value

    with pytest.raises(ValueError):
        AutomatedStrategyConfig.create(**values)


def test_triggered_fresh_momentum_submits_one_journaled_local_entry() -> None:
    instance, flow, _ = controller()

    first = instance.run_once()
    repeated = instance.run_once()

    assert first["decision"] == "ENTRY_SUBMITTED"
    assert repeated["decision"] == "SESSION_COMPLETE"
    assert first["entries_submitted"] == 1
    assert len(flow.intents) == 1
    intent = flow.intents[0]
    assert intent.strategy_id == "momentum_acceleration_local_paper"
    assert intent.strategy_version == (
        "continuous_momentum_local_paper_v1:momentum_entry_hypothesis_v0"
    )
    assert intent.symbol == "3231"
    assert intent.side.value == "BUY"
    assert intent.lots == 1
    assert intent.limit_price == Decimal("177.5")
    assert intent.intent_id.endswith(":entry:signal-digest-1")


@pytest.mark.parametrize(
    ("unrealized_pnl_pct", "expected_reason"),
    [(-1.5, "STOP_LOSS"), (3.0, "TAKE_PROFIT")],
)
def test_open_position_exits_at_fresh_best_bid(
    unrealized_pnl_pct: float,
    expected_reason: str,
) -> None:
    projection = ProjectionReader(
        {
            **empty_projection(),
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 174.8,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "bid_price": 174.5,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                    "book_received_at": TAIPEI_AT.isoformat(),
                    "quote_received_at": TAIPEI_AT.isoformat(),
                }
            ],
        }
    )
    instance, flow, _ = controller(
        projection=projection,
        flow=FakeFlow(order_status="PENDING"),
    )

    status = instance.run_once()

    assert status["decision"] == "EXIT_SUBMITTED"
    assert status["last_exit_reason"] == expected_reason
    assert len(flow.intents) == 1
    intent = flow.intents[0]
    assert intent.side.value == "SELL"
    assert intent.lots == 1
    assert intent.limit_price == Decimal("174.5")


def test_manual_position_is_not_owned_by_automated_strategy() -> None:
    projection = ProjectionReader(
        {
            **empty_projection(),
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 174.8,
                    "unrealized_pnl_pct": -2.0,
                    "bid_price": 174.5,
                    "owner_origin": "MANUAL_WEB",
                    "owner_strategy_id": None,
                    "book_received_at": TAIPEI_AT.isoformat(),
                    "quote_received_at": TAIPEI_AT.isoformat(),
                }
            ],
        }
    )
    instance, flow, _ = controller(projection=projection)

    status = instance.run_once()

    assert status["decision"] == "BLOCKED_OWNERSHIP"
    assert flow.intents == []


def test_fresh_tick_does_not_mask_stale_executable_book() -> None:
    projection = ProjectionReader(
        {
            **empty_projection(),
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 174.8,
                    "unrealized_pnl_pct": -2.0,
                    "bid_price": 174.5,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                    "book_received_at": (
                        TAIPEI_AT - timedelta(seconds=10)
                    ).isoformat(),
                    "quote_received_at": TAIPEI_AT.isoformat(),
                }
            ],
        }
    )
    instance, flow, _ = controller(projection=projection)

    status = instance.run_once()

    assert status["decision"] == "BLOCKED_DATA"
    assert flow.intents == []


def test_sell_rejection_is_reported_instead_of_exit_submitted() -> None:
    projection = ProjectionReader(
        {
            **empty_projection(),
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 174.8,
                    "unrealized_pnl_pct": -2.0,
                    "bid_price": 174.5,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                    "book_received_at": TAIPEI_AT.isoformat(),
                    "quote_received_at": TAIPEI_AT.isoformat(),
                }
            ],
        }
    )
    instance, _, _ = controller(
        projection=projection,
        flow=FakeFlow(order_status="REJECTED"),
    )

    status = instance.run_once()

    assert status["decision"] == "EXIT_REJECTED"


def test_daily_loss_blocks_new_entry_but_not_risk_reducing_exit() -> None:
    projection = ProjectionReader(
        {
            **empty_projection(equity=9_900_000),
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 174.8,
                    "unrealized_pnl_pct": -2.0,
                    "bid_price": 174.5,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                    "book_received_at": TAIPEI_AT.isoformat(),
                    "quote_received_at": TAIPEI_AT.isoformat(),
                }
            ],
        }
    )
    instance, flow, _ = controller(
        projection=projection,
        flow=FakeFlow(order_status="PENDING"),
    )

    status = instance.run_once()

    assert status["decision"] == "EXIT_SUBMITTED"
    assert len(flow.intents) == 1


def test_daily_loss_uses_trading_day_opening_equity() -> None:
    projection = empty_projection(equity=10_040_000)
    projection["session"]["opening_equity"] = 10_100_000
    instance, flow, _ = controller(projection=ProjectionReader(projection))

    status = instance.run_once()

    assert status["decision"] == "BLOCKED_DAILY_LOSS"
    assert flow.intents == []


def test_after_close_cancels_pending_exit_and_escalates_alert() -> None:
    clock = MutableClock(datetime.fromisoformat("2026-08-21T13:31:00+08:00"))
    projection = ProjectionReader(
        {
            **empty_projection(),
            "orders": [
                {
                    "order_id": "pending-exit-1",
                    "origin": "STRATEGY_AUTOMATED",
                    "strategy_id": "momentum_acceleration_local_paper",
                    "side": "SELL",
                    "status": "PENDING",
                    "submitted_at": "2026-08-21T13:25:00+08:00",
                }
            ],
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                }
            ],
        }
    )
    instance, flow, _ = controller(clock=clock, projection=projection)

    status = instance.run_once()

    assert status["decision"] == "ALERT_EXIT_UNRESOLVED"
    assert flow.cancellations == [
        (
            "pending-exit-1",
            f"auto:{status['run_id']}:cancel:pending-exit-1:after-close",
        )
    ]


def test_cancelled_exit_retries_with_bounded_successor_attempt() -> None:
    projection = ProjectionReader(
        {
            **empty_projection(),
            "orders": [
                {
                    "order_id": "cancelled-exit-1",
                    "origin": "STRATEGY_AUTOMATED",
                    "strategy_id": "momentum_acceleration_local_paper",
                    "symbol": "3231",
                    "side": "SELL",
                    "status": "CANCELLED",
                    "attempt": 1,
                    "remaining_quantity": 1_000,
                    "updated_at": TAIPEI_AT.isoformat(),
                    "reason": "ORDER_TIMEOUT",
                }
            ],
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 174.8,
                    "unrealized_pnl_pct": -2.0,
                    "bid_price": 174.5,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                    "book_received_at": TAIPEI_AT.isoformat(),
                }
            ],
        }
    )
    flow = FakeFlow(order_status="PENDING")
    instance, _, _ = controller(projection=projection, flow=flow)

    status = instance.run_once()

    assert status["decision"] == "EXIT_SUBMITTED"
    assert flow.retries == [
        (
            "cancelled-exit-1",
            f"auto:{status['run_id']}:retry:cancelled-exit-1:2",
            Decimal("174.5"),
        )
    ]


def test_stale_signal_and_closed_market_fail_without_intents() -> None:
    stale_at = TAIPEI_AT - timedelta(seconds=6)
    stale, stale_flow, _ = controller(signal_snapshot=live_signal(at=stale_at))

    stale_status = stale.run_once()

    assert stale_status["decision"] == "BLOCKED_SIGNAL"
    assert stale_flow.intents == []

    closed_clock = MutableClock(datetime.fromisoformat("2026-08-21T13:31:00+08:00"))
    closed, closed_flow, _ = controller(clock=closed_clock)

    closed_status = closed.run_once()

    assert closed_status["decision"] == "WAITING_MARKET"
    assert closed_flow.intents == []


def test_multiple_positions_and_daily_loss_breach_block_automation() -> None:
    two_positions = [
        {
            "symbol": symbol,
            "quantity": 1_000,
            "average_price": 100,
            "current_price": 100,
            "unrealized_pnl_pct": 0,
            "bid_price": 99.5,
            "owner_origin": "STRATEGY_AUTOMATED",
            "owner_strategy_id": "momentum_acceleration_local_paper",
            "book_received_at": TAIPEI_AT.isoformat(),
            "quote_received_at": TAIPEI_AT.isoformat(),
        }
        for symbol in ("3231", "2317")
    ]
    invalid_projection = ProjectionReader(
        {**empty_projection(), "positions": two_positions}
    )
    invalid, invalid_flow, _ = controller(projection=invalid_projection)

    invalid_status = invalid.run_once()

    assert invalid_status["decision"] == "BLOCKED_INVARIANT"
    assert invalid_flow.intents == []

    loss_projection = ProjectionReader(empty_projection(equity=9_949_999))
    loss, loss_flow, _ = controller(projection=loss_projection)

    loss_status = loss.run_once()

    assert loss_status["decision"] == "BLOCKED_DAILY_LOSS"
    assert loss_flow.intents == []


def test_background_controller_stops_and_restart_does_not_auto_resume() -> None:
    flow = FakeFlow()
    projection = ProjectionReader()
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=projection,
        signal_reader=lambda: {"status": "unavailable", "items": []},
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=MutableClock(),
    )

    started = instance.start(config())
    stopped = instance.stop()

    assert started["state"] == "RUNNING"
    assert stopped["state"] == "STOPPED"
    assert stopped["restart_behavior"] == "MANUAL_START_REQUIRED"
    assert flow.intents == []


def test_calendar_artifact_is_required_and_out_of_coverage_fails_closed() -> None:
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    clock = MutableClock(datetime.fromisoformat("2027-01-04T10:00:00+08:00"))
    instance = ContinuousPaperStrategyController(
        flow=FakeFlow(),
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=calendar,
        clock=clock,
    )
    instance.start(config(), background=False)

    status = instance.run_once()

    assert status["decision"] == "BLOCKED_CALENDAR"


def test_real_flow_controller_completes_entry_and_stop_loss_exit() -> None:
    clock = MutableClock()
    provider = MockProvider()
    simulation = SimulationService(provider, starting_cash=Decimal("300000"))
    journal = InMemoryJournalRepository()
    session_id = "continuous-controller-integration"
    journal.start_session(
        JournalSession(
            session_id=session_id,
            started_at=clock.now(),
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    commands = LocalPaperCommandService(
        simulation=simulation,
        journal=journal,
        session_id=session_id,
        clock=clock,
    )
    flow = StrategyPaperFlowService(
        commands=commands,
        journal=journal,
        session_id=session_id,
        clock=clock,
    )

    def executable_projection() -> dict:
        projection = simulation.projection()
        projection["session"] = {
            **projection["session"],
            "quote_mode": "SHIOAJI_TICK_BIDASK",
            "streaming": True,
        }
        for position in projection["positions"]:
            position.update(
                current_price=105.4,
                unrealized_pnl_pct=-0.1,
                bid_price=105.4,
                book_received_at=clock.now().isoformat(),
                quote_received_at=clock.now().isoformat(),
            )
        return projection

    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=executable_projection,
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
    )
    instance.start(
        AutomatedStrategyConfig.create(
            stop_loss_pct="0.05",
            take_profit_pct="3",
            max_daily_loss="50000",
            poll_seconds=0.01,
        ),
        background=False,
    )

    entry = instance.run_once()
    assert entry["decision"] == "ENTRY_SUBMITTED"
    assert simulation.orders()[0]["status"] == "FILLED"

    exit_status = instance.run_once()

    assert exit_status["decision"] == "EXIT_FILLED"
    assert exit_status["last_exit_reason"] == "STOP_LOSS"
    assert simulation.positions() == []
    assert [item.record.kind for item in journal.records(session_id)] == [
        "strategy_paper_intent.v1",
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
        "strategy_paper_intent.v1",
        "order_command.v1",
        "local_paper_fill.v1",
        "local_paper_order_state.v1",
    ]
    assert all(
        item.record.payload.get("execution_boundary") == "LOCAL_ONLY"
        for item in journal.records(session_id)
        if item.record.kind == "strategy_paper_intent.v1"
    )
    instance.stop()
    simulation.close()
