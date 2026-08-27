"""End-to-end contracts for strategy-origin local paper trading."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Event, Thread
from time import monotonic, sleep
from typing import Mapping
from zoneinfo import ZoneInfo

import pytest

from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MarketDataProvider, MockProvider
from runtime.in_memory import InMemoryJournalRepository
from simulation.application import LocalPaperCommandService
from simulation.kill_switch import (
    DurableLocalPaperKillSwitch,
    KillSwitchAdmissionBlocked,
)
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
from trading.journal import JournalAppendResult, JournalRecord, JournalSession
from trading.kill_switch import (
    KILL_SWITCH_CONTROL_SESSION_ID,
    KILL_SWITCH_ENGAGED_KIND,
)
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
    flow, simulation, kill_switch = _controlled_flow(
        journal=journal,
        starting_cash=starting_cash,
        provider=provider,
    )
    return flow, simulation, journal


def _controlled_flow(
    *,
    journal: InMemoryJournalRepository,
    starting_cash: Decimal = Decimal("300000"),
    provider: MarketDataProvider | None = None,
):
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
    kill_switch = DurableLocalPaperKillSwitch.recover(
        journal=journal,
        clock=FixedClock(),
    )
    return (
        StrategyPaperFlowService(
            commands=commands,
            journal=journal,
            session_id=_SESSION_ID,
            clock=FixedClock(),
            kill_switch=kill_switch,
        ),
        simulation,
        kill_switch,
    )


class BlockingJournal(InMemoryJournalRepository):
    def __init__(self, blocked_kind: str) -> None:
        super().__init__()
        self.blocked_kind = blocked_kind
        self.entered = Event()
        self.release = Event()

    def append(self, record: JournalRecord) -> JournalAppendResult:
        if record.kind == self.blocked_kind and not self.release.is_set():
            self.entered.set()
            if not self.release.wait(timeout=2):
                raise AssertionError("test did not release blocked Journal append")
        return super().append(record)


class IntentBlockingFailingCheckpointJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.intent_entered = Event()
        self.release_intent = Event()
        self.fail_checkpoint = False

    def append(self, record: JournalRecord) -> JournalAppendResult:
        if record.kind == STRATEGY_PAPER_INTENT_KIND:
            self.intent_entered.set()
            if not self.release_intent.wait(timeout=2):
                raise AssertionError("test did not release strategy intent")
        return super().append(record)

    def save_checkpoint(self, checkpoint) -> None:
        if self.fail_checkpoint:
            raise RuntimeError("injected checkpoint failure")
        super().save_checkpoint(checkpoint)


class FailingKindJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_kind: str | None = None

    def append(self, record: JournalRecord) -> JournalAppendResult:
        if record.kind == self.fail_kind:
            raise RuntimeError(f"injected {record.kind} append failure")
        return super().append(record)


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


def test_submit_admitted_first_finishes_before_concurrent_engage_returns() -> None:
    journal = BlockingJournal(STRATEGY_PAPER_INTENT_KIND)
    flow, simulation, kill_switch = _controlled_flow(journal=journal)
    submitted: list[dict] = []
    engaged: list[dict] = []
    submit_thread = Thread(
        target=lambda: submitted.append(
            flow.submit(intent("concurrent-submit-first", CommandSide.BUY, "106"))
        )
    )
    engage_thread = Thread(
        target=lambda: engaged.append(
            kill_switch.engage(
                actor_id="local-operator",
                operation_id="concurrent-engage-second",
                reason="concurrency test",
            )
        )
    )

    submit_thread.start()
    assert journal.entered.wait(timeout=1)
    engage_thread.start()
    sleep(0.02)
    assert engage_thread.is_alive()
    journal.release.set()
    submit_thread.join(timeout=2)
    engage_thread.join(timeout=2)

    assert not submit_thread.is_alive()
    assert not engage_thread.is_alive()
    assert submitted[0]["order"]["status"] == "FILLED"
    assert engaged[0]["kill_switch"]["control_state"] == "ENGAGED"
    kinds = [item.record.kind for item in journal.records(_SESSION_ID)]
    assert kinds[0] == STRATEGY_PAPER_INTENT_KIND
    assert journal.records(_SESSION_ID)[0].sequence < journal.records(
        KILL_SWITCH_CONTROL_SESSION_ID
    )[0].sequence
    simulation.close()


def test_engage_linearized_first_blocks_concurrent_submit_before_intent_journal() -> None:
    journal = BlockingJournal(KILL_SWITCH_ENGAGED_KIND)
    flow, simulation, kill_switch = _controlled_flow(journal=journal)
    engaged: list[dict] = []
    submit_errors: list[Exception] = []
    engage_thread = Thread(
        target=lambda: engaged.append(
            kill_switch.engage(
                actor_id="local-operator",
                operation_id="concurrent-engage-first",
                reason="concurrency test",
            )
        )
    )

    def submit() -> None:
        try:
            flow.submit(intent("concurrent-submit-second", CommandSide.BUY, "106"))
        except Exception as error:
            submit_errors.append(error)

    submit_thread = Thread(target=submit)
    engage_thread.start()
    assert journal.entered.wait(timeout=1)
    submit_thread.start()
    sleep(0.02)
    assert journal.records(_SESSION_ID) == ()
    journal.release.set()
    engage_thread.join(timeout=2)
    submit_thread.join(timeout=2)

    assert not engage_thread.is_alive()
    assert not submit_thread.is_alive()
    assert engaged[0]["kill_switch"]["control_state"] == "ENGAGED"
    assert len(submit_errors) == 1
    assert isinstance(submit_errors[0], KillSwitchAdmissionBlocked)
    assert journal.records(_SESSION_ID) == ()
    assert simulation.orders() == []
    simulation.close()


def test_recovery_required_blocks_automated_intent_before_journal_append() -> None:
    class RecoveryRequiredCommands:
        def admit_automated_intent(self, _operation):
            raise SimulationStateError("LOCAL_PAPER_RECOVERY_REQUIRED")

    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=_SESSION_ID,
            started_at=_NOW,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    flow = StrategyPaperFlowService(
        commands=RecoveryRequiredCommands(),
        journal=journal,
        session_id=_SESSION_ID,
        clock=FixedClock(),
        kill_switch=DurableLocalPaperKillSwitch.recover(
            journal=journal,
            clock=FixedClock(),
        ),
    )

    with pytest.raises(SimulationStateError, match="RECOVERY_REQUIRED"):
        flow.submit(intent("recovery-blocked", CommandSide.BUY, "106"))

    assert journal.records(_SESSION_ID) == ()


def test_checkpoint_failure_and_automated_intent_are_linearized() -> None:
    journal = IntentBlockingFailingCheckpointJournal()
    journal.start_session(
        JournalSession(
            session_id=_SESSION_ID,
            started_at=_NOW,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    simulation = SimulationService(
        MockProvider(),
        starting_cash=Decimal("500000"),
        clock=FixedClock(),
    )
    commands = LocalPaperCommandService(
        simulation=simulation,
        journal=journal,
        session_id=_SESSION_ID,
        clock=FixedClock(),
    )
    flow = StrategyPaperFlowService(
        commands=commands,
        journal=journal,
        session_id=_SESSION_ID,
        clock=FixedClock(),
        kill_switch=DurableLocalPaperKillSwitch.recover(
            journal=journal,
            clock=FixedClock(),
        ),
    )
    automated_errors: list[Exception] = []
    manual_errors: list[Exception] = []

    def submit_automated() -> None:
        try:
            flow.submit(intent("linearized-recovery", CommandSide.BUY, "106"))
        except Exception as error:
            automated_errors.append(error)

    def submit_manual() -> None:
        try:
            commands.submit_order(
                symbol="3231",
                side="BUY",
                lots=1,
                limit_price="106",
                idempotency_key="manual-during-recovery-race",
            )
        except Exception as error:
            manual_errors.append(error)

    automated_thread = Thread(target=submit_automated)
    automated_thread.start()
    assert journal.intent_entered.wait(timeout=1)
    journal.fail_checkpoint = True
    manual_thread = Thread(target=submit_manual)
    manual_thread.start()
    sleep(0.02)
    journal.release_intent.set()
    automated_thread.join(timeout=2)
    manual_thread.join(timeout=2)

    assert not automated_thread.is_alive()
    assert not manual_thread.is_alive()
    assert len(automated_errors) == 1
    assert len(manual_errors) == 1
    kinds = [item.record.kind for item in journal.records(_SESSION_ID)]
    assert kinds[0] == STRATEGY_PAPER_INTENT_KIND
    assert sum(kind == "order_command.v1" for kind in kinds) == 1


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


def test_later_fill_append_failure_blocks_next_intent_before_journal() -> None:
    journal = FailingKindJournal()
    provider = StreamingMockProvider()
    flow, simulation, _ = _controlled_flow(
        journal=journal,
        provider=provider,
    )
    submitted = flow.submit(
        intent("later-fill-persistence-failure", CommandSide.BUY, "106")
    )
    assert submitted["order"]["status"] == "PENDING"
    journal.fail_kind = "local_paper_fill.v1"

    provider.emit_bidask(bid=105.4, ask=105.6)
    wait_until(
        lambda: simulation.orders()[0]["status"] == "FILLED"
        and simulation.risk_snapshot("3231")["data_health_state"] == "BLOCKED"
    )
    record_count = len(journal.records(_SESSION_ID))
    journal.fail_kind = None

    with pytest.raises(SimulationStateError, match="RECOVERY_REQUIRED"):
        flow.submit(intent("must-not-be-journaled", CommandSide.BUY, "106"))

    assert len(journal.records(_SESSION_ID)) == record_count
    simulation.close()


def test_cross_owner_pending_buys_reserve_independent_exposures() -> None:
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
    assert manual["status"] == "PENDING"
    assert simulation.risk_snapshot("3231")["pending_buy_shares"] == 2_000

    provider.emit_bidask(bid=105.4, ask=105.6)
    wait_until(lambda: simulation.positions())
    assert simulation.positions()[0]["quantity"] == 2_000
    assert simulation.positions()[0]["owner_origin"] == "MIXED"
    assert len(simulation.exposures()) == 2
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
    assert "exposure owner 衝突" in rejected["reason"]
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


def test_runtime_handoff_waits_for_complete_strategy_activation() -> None:
    journal = BlockingJournal("strategy_runtime_activation.v1")
    flow, simulation, _ = _controlled_flow(journal=journal)
    activated: list[Mapping[str, object]] = []
    activation_errors: list[Exception] = []
    handoff_prepared = Event()

    def activate() -> None:
        try:
            activated.append(
                flow.activate_run(
                    owner_strategy_id="atomic-set:paper-v1",
                    operator_max_daily_loss=Decimal("1000"),
                    activation_config={"pipeline_digest": "p" * 64},
                    actor_id="local-operator",
                    idempotency_key="activation-before-runtime-handoff",
                    occurred_at=_NOW,
                )
            )
        except Exception as error:
            activation_errors.append(error)

    def prepare_handoff() -> None:
        flow._commands.prepare_runtime_handoff()
        handoff_prepared.set()

    activation_thread = Thread(target=activate)
    activation_thread.start()
    assert journal.entered.wait(timeout=1)
    handoff_thread = Thread(target=prepare_handoff)
    handoff_thread.start()
    sleep(0.02)

    assert handoff_thread.is_alive()
    assert handoff_prepared.is_set() is False
    assert journal.records(_SESSION_ID) == ()

    journal.release.set()
    activation_thread.join(timeout=2)
    handoff_thread.join(timeout=2)

    assert not activation_thread.is_alive()
    assert not handoff_thread.is_alive()
    assert activation_errors == []
    assert activated[0]["activation_idempotent"] is False
    assert handoff_prepared.is_set() is True
    records = journal.records(_SESSION_ID)
    assert [item.record.kind for item in records] == [
        "strategy_runtime_activation.v1"
    ]
    assert flow._commands.strategy_risk_policy(
        owner_strategy_id="atomic-set:paper-v1"
    ) is not None
    with pytest.raises(SimulationStateError, match="RUNTIME_HANDOFF"):
        flow.activate_run(
            owner_strategy_id="atomic-set:paper-v1",
            operator_max_daily_loss=Decimal("1000"),
            activation_config={"pipeline_digest": "p" * 64},
            actor_id="local-operator",
            idempotency_key="activation-during-runtime-handoff",
            occurred_at=_NOW,
        )
    assert journal.records(_SESSION_ID) == records
    flow._commands.rollback_runtime_handoff()
    simulation.close()


def test_revoked_runtime_blocks_stale_strategy_checkpoint_before_journal() -> None:
    flow, simulation, journal = paper_flow()
    before = journal.records(_SESSION_ID)
    flow._commands.finalize_runtime_handoff()

    with pytest.raises(SimulationStateError, match="RUNTIME_REPLACED"):
        flow.checkpoint(
            {
                "owner_strategy_id": "atomic-set:paper-v1",
                "pipeline_digest": "p" * 64,
            },
            occurred_at=_NOW,
        )

    assert journal.records(_SESSION_ID) == before
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
