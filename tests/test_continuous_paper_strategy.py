from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Event, Lock, Thread
from time import monotonic, sleep
import pytest

from config import twse_calendar_2026
from features.specifications import FeatureRequestSpec
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider
from runtime.in_memory import InMemoryJournalRepository
from simulation.application import LocalPaperCommandService
from simulation.atomic_runtime import (
    AtomicPaperCandidateDecision,
    AtomicPaperProjectionDecision,
    LocalPaperPipelineSnapshot,
    PaperSetStatus,
)
from simulation.continuous_strategy import (
    AutomatedStrategyConfig,
    AutomatedStrategyStateError,
    ContinuousPaperStrategyController,
)
from simulation.kill_switch import (
    DurableLocalPaperKillSwitch,
    KillSwitchAdmissionBlocked,
)
from simulation.service import SimulationService
from simulation.strategy_flow import StrategyPaperFlowService
from trading.journal import JournalSession
from strategy_catalog.domain import StrategyRole
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


TAIPEI_AT = datetime.fromisoformat("2026-08-21T10:30:00+08:00")


class MutableClock:
    def __init__(self, value: datetime = TAIPEI_AT) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


def durable_kill_switch(
    clock: MutableClock,
    journal: InMemoryJournalRepository | None = None,
) -> DurableLocalPaperKillSwitch:
    return DurableLocalPaperKillSwitch.recover(
        journal=journal or InMemoryJournalRepository(),
        clock=clock,
    )


class FakeFlow:
    def __init__(self, *, order_status: str = "FILLED") -> None:
        self.order_status = order_status
        self.intents = []
        self.cancellations = []
        self.retries = []
        self.activations = []
        self.quote_watches = []

    def preview_run_activation(self, **payload):
        return {
            "contract_version": "effective-local-paper-risk-v1",
            "owner_strategy_id": payload["owner_strategy_id"],
            "merge_rule": "MIN_SYSTEM_OPERATOR",
            "system_max_daily_loss": "10000000",
            "operator_max_daily_loss": str(payload["operator_max_daily_loss"]),
            "effective_max_daily_loss": str(payload["operator_max_daily_loss"]),
            "effective_policy_digest": "e" * 64,
        }

    def activate_run(self, **payload):
        self.activations.append(payload)
        return {
            "contract_version": "effective-local-paper-risk-v1",
            "owner_strategy_id": payload["owner_strategy_id"],
            "merge_rule": "MIN_SYSTEM_OPERATOR",
            "system_max_daily_loss": "10000000",
            "operator_max_daily_loss": str(payload["operator_max_daily_loss"]),
            "effective_max_daily_loss": str(payload["operator_max_daily_loss"]),
            "effective_policy_digest": "e" * 64,
        }

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

    def prepare_entry_quote(self, **payload):
        self.quote_watches.append((payload["owner_strategy_id"], payload["symbol"]))
        return {
            "contract_version": "local-paper-quote-watch-v1",
            "owner_id": payload["owner_strategy_id"],
            "symbol": payload["symbol"],
            "ready": True,
        }

    def clear_entry_quote_watch(self, **payload):
        self.quote_watches.append((payload["owner_strategy_id"], None))

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


class StreamingEntryProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.handler = None
        self.subscribed_symbols: set[str] = set()

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self.handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        self.subscribed_symbols = set(symbols)
        return set(self.subscribed_symbols)

    def stop_quote_stream(self) -> None:
        self.subscribed_symbols.clear()

    def emit_bidask(self, *, clock: MutableClock, bid: str, ask: str) -> None:
        assert self.handler is not None
        self.handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=clock.now(),
                received_at=clock.now(),
                bid_price=float(bid),
                ask_price=float(ask),
                bid_volume_lots=5,
                ask_volume_lots=5,
            )
        )


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("quote worker did not reach the expected state")


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


def atomic_resolution():
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="paper-entry-set-v1",
        strategy_set_id="paper-entry-set",
        version_number=1,
        display_name_zh_tw="站上 VWAP",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(
            StrategySetMemberSnapshot(
                strategy_version_id="above-vwap-v1",
                strategy_id="above_vwap_entry",
                role=StrategyRole.ENTRY,
                configuration_digest="config-v1",
                implementation_digest="implementation-v1",
                member_order=0,
                attribution_priority=0,
            ),
        ),
    )

    class Resolution:
        projection_requests = ()
        pipeline = LocalPaperPipelineSnapshot(
            entry_strategy_set=snapshot,
            runtime_bindings=(
                {
                    "strategy_version_id": "above-vwap-v1",
                    "binding": "above_vwap.local_paper_tick_bidask_v1",
                    "implementation_digest": "implementation-v1",
                },
            ),
            feature_contracts=(
                {
                    "feature_id": "vwap_session_v1",
                    "source_projection": "IntradayFeatureSnapshot.vwap",
                    "as_of_semantics": "CURRENT_TICK_AVERAGE_PRICE",
                    "implementation_identity": "FeatureEngine.intraday_features_v0",
                },
            ),
            lifecycle_admissions=(
                {
                    "strategy_version_id": "above-vwap-v1",
                    "status": "PAPER_APPROVED",
                    "last_sequence": 4,
                    "last_event_id": "paper-approved-event-v1",
                    "projection_digest": "a" * 64,
                },
            ),
        )

        def evaluate_projection(self, projection, *, evaluated_at, max_age_seconds):
            return AtomicPaperProjectionDecision(
                candidates=(
                    AtomicPaperCandidateDecision(
                        status=PaperSetStatus.TRIGGERED,
                        symbol="3231",
                        event_at=evaluated_at,
                        current_price="177.5",
                        entry_limit_price="178",
                        decision_digest="atomic-decision-digest-1",
                        primary_strategy_version_id="above-vwap-v1",
                        evaluations=(),
                    ),
                ),
                blocked_reasons=(),
            )

    return Resolution()


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
        kill_switch=durable_kill_switch(resolved_clock),
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


def test_exact_strategy_set_submits_pipeline_owned_auditable_entry() -> None:
    resolved = atomic_resolution()
    flow = FakeFlow()
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=MutableClock(),
        kill_switch=durable_kill_switch(MutableClock()),
        atomic_resolver=lambda strategy_set_version_id: (
            resolved
            if strategy_set_version_id == "paper-entry-set-v1"
            else None
        ),
    )
    instance.start(
        AutomatedStrategyConfig.create(
            entry_strategy_set_version_id="paper-entry-set-v1",
            stop_loss_pct="1.5",
            take_profit_pct="3",
            max_daily_loss="50000",
        ),
        background=False,
    )

    status = instance.run_once()

    assert status["decision"] == "ENTRY_SUBMITTED"
    assert status["pipeline"]["snapshot_digest"] == resolved.pipeline.snapshot_digest
    assert status["effective_risk"]["effective_max_daily_loss"] == "50000"
    assert flow.activations[0]["actor_id"] == "local-operator"
    assert len(flow.intents) == 1
    intent = flow.intents[0]
    assert intent.strategy_id == "atomic-set:paper-entry-set-v1"
    assert intent.strategy_version == (
        f"local-paper-pipeline:{resolved.pipeline.snapshot_digest}"
    )
    assert intent.limit_price == Decimal("178")
    assert intent.decision_evidence["strategy_set_decision"]["decision_digest"] == (
        "atomic-decision-digest-1"
    )


def test_exact_strategy_set_passes_feature_requests_to_atomic_reader() -> None:
    resolved = atomic_resolution()
    request = FeatureRequestSpec(
        "rolling_return_v1",
        {"window_minutes": 3},
    )
    resolved.projection_requests = (request,)
    calls: list[tuple[FeatureRequestSpec, ...]] = []
    flow = FakeFlow()
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: (_ for _ in ()).throw(
            AssertionError("atomic runtime 不應讀取固定 signal snapshot")
        ),
        atomic_signal_reader=lambda requests: (
            calls.append(requests) or live_signal()
        ),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=MutableClock(),
        kill_switch=durable_kill_switch(MutableClock()),
        atomic_resolver=lambda _: resolved,
    )
    instance.start(
        AutomatedStrategyConfig.create(
            entry_strategy_set_version_id="paper-entry-set-v1",
            stop_loss_pct="1.5",
            take_profit_pct="3",
            max_daily_loss="50000",
        ),
        background=False,
    )

    status = instance.run_once()

    assert status["decision"] == "ENTRY_SUBMITTED"
    assert calls == [(request,)]


def test_exact_streaming_first_entry_watches_book_before_hard_risk() -> None:
    clock = MutableClock()
    provider = StreamingEntryProvider()
    simulation = SimulationService(
        provider,
        starting_cash=Decimal("300000"),
        clock=clock,
    )
    journal = InMemoryJournalRepository()
    session_id = "exact-streaming-first-entry"
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
    switch = durable_kill_switch(clock, journal)
    flow = StrategyPaperFlowService(
        commands=commands,
        journal=journal,
        session_id=session_id,
        clock=clock,
        kill_switch=switch,
    )
    resolved = atomic_resolution()
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=simulation.projection,
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
        atomic_resolver=lambda _: resolved,
    )
    instance.start(
        AutomatedStrategyConfig.create(
            entry_strategy_set_version_id="paper-entry-set-v1",
            stop_loss_pct="1.5",
            take_profit_pct="3",
            max_daily_loss="50000",
            activation_idempotency_key="exact-streaming-first-entry",
        ),
        background=False,
    )

    warming = instance.run_once()

    assert warming["decision"] == "WAITING_BOOK"
    assert simulation.orders() == []
    assert provider.subscribed_symbols == {"3231"}
    assert simulation.session()["watched_symbols"] == ["3231"]

    provider.emit_bidask(clock=clock, bid="177", ask="178")
    wait_until(
        lambda: simulation.quote_watch_status(
            owner_id=resolved.pipeline.owner_strategy_id,
            symbol="3231",
        )["ready"]
    )

    submitted = instance.run_once()

    assert submitted["decision"] == "ENTRY_SUBMITTED"
    assert simulation.orders()[0]["status"] == "FILLED"
    assert simulation.orders()[0]["reason"] is None
    assert simulation.positions()[0]["owner_strategy_id"] == (
        resolved.pipeline.owner_strategy_id
    )
    assert simulation.session()["watched_symbols"] == []
    assert provider.subscribed_symbols == {"3231"}
    assert all(
        item.record.kind != "local_paper_rejection.v1"
        for item in journal.records(session_id)
    )

    instance.stop()
    simulation.close()


def test_start_fails_closed_when_existing_automated_owner_differs() -> None:
    projection = empty_projection()
    projection["orders"] = [
        {
            "origin": "STRATEGY_AUTOMATED",
            "strategy_id": "another-pipeline",
            "status": "FILLED",
        }
    ]
    instance = ContinuousPaperStrategyController(
        flow=FakeFlow(),
        projection_reader=ProjectionReader(projection),
        signal_reader=lambda: live_signal(),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=MutableClock(),
        kill_switch=durable_kill_switch(MutableClock()),
        atomic_resolver=lambda _: atomic_resolution(),
    )

    with pytest.raises(Exception, match="其他自動策略 owner"):
        instance.start(
            AutomatedStrategyConfig.create(
                entry_strategy_set_version_id="paper-entry-set-v1",
                stop_loss_pct="1.5",
                take_profit_pct="3",
                max_daily_loss="50000",
            ),
            background=False,
        )


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


def test_end_of_session_exit_is_delegated_to_central_controller() -> None:
    clock = MutableClock(datetime.fromisoformat("2026-08-21T13:25:00+08:00"))
    projection = ProjectionReader(
        {
            **empty_projection(),
            "positions": [
                {
                    "symbol": "3231",
                    "quantity": 1_000,
                    "average_price": 177.5,
                    "current_price": 177.5,
                    "unrealized_pnl_pct": 0,
                    "bid_price": 177.4,
                    "owner_origin": "STRATEGY_AUTOMATED",
                    "owner_strategy_id": "momentum_acceleration_local_paper",
                    "book_received_at": clock.now().isoformat(),
                }
            ],
        }
    )
    flow = FakeFlow(order_status="PENDING")
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=projection,
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=durable_kill_switch(clock),
        central_no_overnight_exit_owned=True,
    )
    instance.start(config(), background=False)

    status = instance.run_once()

    assert status["decision"] == "CENTRAL_FLATTEN_DELEGATED"
    assert flow.intents == []
    assert flow.retries == []


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
        kill_switch=durable_kill_switch(MutableClock()),
    )

    started = instance.start(config())
    stopped = instance.stop()

    assert started["state"] == "RUNNING"
    assert stopped["state"] == "STOPPED"
    assert stopped["restart_behavior"] == "MANUAL_START_REQUIRED"
    assert flow.intents == []


def test_global_kill_switch_stops_new_intents_fail_closed() -> None:
    clock = MutableClock()
    switch = durable_kill_switch(clock)
    flow = FakeFlow()
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
    )
    instance.start(config(), background=False)
    switch.engage(
        actor_id="local-operator",
        operation_id="controller-kill-switch-test",
        reason="operator emergency stop",
    )

    status = instance.run_once()

    assert status["state"] == "KILLED"
    assert status["decision"] == "KILL_SWITCH_ENGAGED"
    assert status["kill_switch"]["engaged"] is True
    assert flow.intents == []

    with pytest.raises(KillSwitchAdmissionBlocked, match="kill switch is engaged"):
        instance.start(config(), background=False)


def test_engage_cannot_return_before_an_overlapping_start_is_linearized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = MutableClock()
    switch = durable_kill_switch(clock)
    instance = ContinuousPaperStrategyController(
        flow=FakeFlow(),
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
    )
    admission_checked = Event()
    release_start = Event()
    completion_lock = Lock()
    completions: list[str] = []
    start_errors: list[Exception] = []
    original_assert = switch.assert_start_allowed

    def delayed_start_admission() -> None:
        original_assert()
        admission_checked.set()
        assert release_start.wait(timeout=1)

    monkeypatch.setattr(switch, "assert_start_allowed", delayed_start_admission)

    def start() -> None:
        try:
            instance.start(config(), background=False)
        except Exception as error:
            start_errors.append(error)
        finally:
            with completion_lock:
                completions.append("start")

    def engage() -> None:
        instance.engage_kill_switch(
            actor_id="local-operator",
            idempotency_key="overlapping-start-engage",
            reason="concurrency regression",
        )
        with completion_lock:
            completions.append("engage")

    start_thread = Thread(target=start)
    engage_thread = Thread(target=engage)
    start_thread.start()
    assert admission_checked.wait(timeout=1)
    engage_thread.start()
    wait_until(lambda: switch.control_state.value == "ENGAGED")
    release_start.set()
    start_thread.join(timeout=2)
    engage_thread.join(timeout=2)

    assert not start_thread.is_alive()
    assert not engage_thread.is_alive()
    assert start_errors == []
    assert completions == ["start", "engage"]
    assert instance.status()["state"] == "KILLED"


def test_recovered_engagement_is_killed_before_first_status_and_reset_stays_stopped() -> None:
    clock = MutableClock()
    journal = InMemoryJournalRepository()
    durable_kill_switch(clock, journal).engage(
        actor_id="local-operator",
        operation_id="recovered-controller-engage",
        reason="restart recovery",
    )
    recovered = durable_kill_switch(clock, journal)
    flow = FakeFlow()

    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=recovered,
    )

    first_status = instance.status()
    assert first_status["state"] == "KILLED"
    assert first_status["decision"] == "KILL_SWITCH_ENGAGED"
    assert first_status["kill_switch"]["recovered"] is True
    with pytest.raises(KillSwitchAdmissionBlocked, match="kill switch is engaged"):
        instance.start(config(), background=False)
    stopped_while_engaged = instance.stop()
    assert stopped_while_engaged["state"] == "KILLED"
    assert stopped_while_engaged["decision"] == "KILL_SWITCH_ENGAGED"

    reset = instance.reset_kill_switch(
        actor_id="local-operator",
        idempotency_key="recovered-controller-reset",
        expected_revision=1,
        reason="review complete",
    )

    assert reset["state"] == "STOPPED"
    assert reset["decision"] == "STOPPED"
    assert reset["kill_switch"]["revision"] == 2
    assert reset["operation"]["idempotent"] is False
    assert flow.intents == []


def test_durable_engage_remains_authoritative_when_controller_checkpoint_fails() -> None:
    clock = MutableClock()
    switch = durable_kill_switch(clock)

    class FailingCheckpointFlow(FakeFlow):
        def __init__(self) -> None:
            super().__init__()
            self.checkpoint_calls = 0

        def checkpoint(self, _payload, *, occurred_at) -> None:
            assert occurred_at == clock.now()
            self.checkpoint_calls += 1
            if self.checkpoint_calls > 1:
                raise RuntimeError("injected controller checkpoint failure")

    flow = FailingCheckpointFlow()
    instance = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
    )
    instance.start(config(), background=False)

    engaged = instance.engage_kill_switch(
        actor_id="local-operator",
        idempotency_key="checkpoint-failure-engage",
        reason="durable authority test",
    )

    assert engaged["state"] == "KILLED"
    assert engaged["kill_switch"]["control_state"] == "ENGAGED"
    assert engaged["kill_switch"]["revision"] == 1
    assert "checkpoint 寫入失敗" in engaged["last_error"]
    with pytest.raises(KillSwitchAdmissionBlocked, match="kill switch is engaged"):
        instance.start(config(), background=False)


def test_calendar_artifact_is_required_and_out_of_coverage_fails_closed() -> None:
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    clock = MutableClock(datetime.fromisoformat("2027-01-04T10:00:00+08:00"))
    instance = ContinuousPaperStrategyController(
        flow=FakeFlow(),
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=calendar,
        clock=clock,
        kill_switch=durable_kill_switch(clock),
    )
    instance.start(config(), background=False)

    status = instance.run_once()

    assert status["decision"] == "BLOCKED_CALENDAR"


def test_exact_runtime_checkpoint_preserves_effective_risk_and_rejects_drift() -> None:
    clock = MutableClock()
    simulation = SimulationService(
        MockProvider(),
        starting_cash=Decimal("300000"),
        clock=clock,
    )
    journal = InMemoryJournalRepository()
    session_id = "exact-risk-checkpoint-session"
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
    switch = durable_kill_switch(clock, journal)
    flow = StrategyPaperFlowService(
        commands=commands,
        journal=journal,
        session_id=session_id,
        clock=clock,
        kill_switch=switch,
    )
    resolved = atomic_resolution()
    run_config = AutomatedStrategyConfig.create(
        entry_strategy_set_version_id="paper-entry-set-v1",
        stop_loss_pct="1.5",
        take_profit_pct="3",
        max_daily_loss="50000",
        activation_idempotency_key="exact-risk-response-loss",
    )

    first = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
        atomic_resolver=lambda _: resolved,
    )
    first_status = first.start(run_config, background=False)
    first.stop()

    restarted = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
        atomic_resolver=lambda _: resolved,
    )
    replayed_status = restarted.start(run_config, background=False)

    assert first_status["effective_risk"]["effective_max_daily_loss"] == "50000"
    assert replayed_status["effective_risk"]["activation_idempotent"] is True
    checkpoint = flow.latest_checkpoint(
        owner_strategy_id=resolved.pipeline.owner_strategy_id,
        pipeline_digest=resolved.pipeline.snapshot_digest,
    )
    assert checkpoint is not None
    assert checkpoint["effective_risk"]["effective_policy_digest"] == (
        replayed_status["effective_risk"]["effective_policy_digest"]
    )
    assert len(
        [
            item
            for item in journal.records(session_id)
            if item.record.kind == "strategy_runtime_activation.v1"
        ]
    ) == 1
    installed_before_failed_restart = commands.strategy_risk_policy(
        owner_strategy_id=resolved.pipeline.owner_strategy_id
    )
    assert installed_before_failed_restart is not None
    assert installed_before_failed_restart["policy"]["max_daily_loss"] == "50000"
    restarted.stop()

    drifted = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=ProjectionReader(),
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
        atomic_resolver=lambda _: resolved,
    )
    with pytest.raises(AutomatedStrategyStateError, match="Effective Hard Risk 已漂移"):
        drifted.start(
            AutomatedStrategyConfig.create(
                entry_strategy_set_version_id="paper-entry-set-v1",
                stop_loss_pct="1.5",
                take_profit_pct="3",
                max_daily_loss="40000",
                activation_idempotency_key="exact-risk-changed-policy",
            ),
            background=False,
        )
    assert drifted.status()["state"] == "STOPPED"
    installed_after_failed_restart = commands.strategy_risk_policy(
        owner_strategy_id=resolved.pipeline.owner_strategy_id
    )
    assert installed_after_failed_restart == installed_before_failed_restart
    assert len(
        [
            item
            for item in journal.records(session_id)
            if item.record.kind == "strategy_runtime_activation.v1"
        ]
    ) == 1
    simulation.close()


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
    switch = durable_kill_switch(clock, journal)
    flow = StrategyPaperFlowService(
        commands=commands,
        journal=journal,
        session_id=session_id,
        clock=clock,
        kill_switch=switch,
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
        kill_switch=switch,
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
    kinds = [item.record.kind for item in journal.records(session_id)]
    assert [kind for kind in kinds if kind != "strategy_runtime_checkpoint.v1"] == [
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
    assert kinds.count("strategy_runtime_checkpoint.v1") == 3

    instance.stop()
    restarted = ContinuousPaperStrategyController(
        flow=flow,
        projection_reader=executable_projection,
        signal_reader=lambda: live_signal(at=clock.now()),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=clock,
        kill_switch=switch,
    )
    restarted.start(
        AutomatedStrategyConfig.create(
            stop_loss_pct="0.05",
            take_profit_pct="3",
            max_daily_loss="50000",
            poll_seconds=0.01,
        ),
        background=False,
    )
    recovered = restarted.run_once()
    assert recovered["decision"] == "SESSION_COMPLETE"
    assert recovered["entries_submitted"] == 1
    instance.stop()
    restarted.stop()
    simulation.close()
