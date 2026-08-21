from __future__ import annotations

import ast
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from market_data.ingress import AdmissionStatus
from market_data.momentum_stream import StreamLifecycleEvent, StreamLifecycleEventType
from runtime.trade_management_live_capture import (
    LIVE_SHADOW_CAPTURE_VERSION,
    LiveShadowCaptureConfig,
    LiveShadowCaptureRunner,
    LiveShadowProviderIdentity,
    live_shadow_journal_session,
)
from tests.test_paper_fill_thesis_builder import filled_paper_entry
from tests.test_trade_management_shadow_operation import live_events
from trading.paper_thesis_activation import PaperFillThesisBuilder


class MutableClock:
    def __init__(self, current):
        self.current = current

    def now(self):
        return self.current

    def session_date(self):
        return self.current.date()


class FakeStream:
    def __init__(
        self,
        identity: str,
        *,
        acknowledge: bool = True,
        pre_ack_event=None,
    ) -> None:
        self.environment_identity = identity
        self.callback_errors = ()
        self.acknowledge = acknowledge
        self.pre_ack_event = pre_ack_event
        self.market_handler = None
        self.lifecycle_handler = None
        self.closed = False

    def start(self, market_handler, lifecycle_handler) -> None:
        self.market_handler = market_handler
        self.lifecycle_handler = lifecycle_handler

    def request_subscribe(self, symbol: str) -> None:
        if self.pre_ack_event is not None:
            self.emit_market(self.pre_ack_event)
        if self.acknowledge:
            self.emit_lifecycle(
                StreamLifecycleEvent(
                    event_type=StreamLifecycleEventType.SUBSCRIBE_ACKED,
                    occurred_at=ACTIVATION.thesis.filled_at.value,
                    reason="paired Tick/BidAsk acknowledged",
                    symbol=symbol,
                )
            )

    def close(self) -> None:
        self.closed = True

    def emit_market(self, event) -> None:
        assert self.market_handler is not None
        self.market_handler(event)

    def emit_lifecycle(self, event) -> None:
        assert self.lifecycle_handler is not None
        self.lifecycle_handler(event)


class StubOperation:
    def __init__(self) -> None:
        self.market_factories = []
        self.lifecycle_factories = []
        self.process_calls = []
        self.finalized_at = None

    def submit_market(self, factory):
        self.market_factories.append(factory)
        return type("Admission", (), {"status": AdmissionStatus.ACCEPTED})()

    def submit_lifecycle(self, factory, *, timeout=0):
        self.lifecycle_factories.append(factory)
        return type("Admission", (), {"status": AdmissionStatus.ACCEPTED})()

    def process_pending(self, *, occurred_at, max_messages=None):
        self.process_calls.append(occurred_at)
        return ()

    def finalize(self, *, observed_at=None):
        self.finalized_at = observed_at
        return object()


DRAFT, FILL = filled_paper_entry()
PROVIDER = LiveShadowProviderIdentity(
    provider="shioaji",
    sdk_version="1.7.2",
    simulation=True,
    connection_session_id="shioaji-connection-20260820-a",
)
FILL = replace(
    FILL,
    payload={**FILL.payload, "provider_identity": PROVIDER.environment_identity},
)
ACTIVATION = PaperFillThesisBuilder().activate(DRAFT, FILL)
OPEN = ACTIVATION.thesis.filled_at.value - timedelta(minutes=1)
CLOSE = ACTIVATION.thesis.filled_at.value + timedelta(hours=4)


def config(**changes):
    values = {
        "session_id": ACTIVATION.thesis.draft.session_id,
        "symbol": ACTIVATION.thesis.draft.symbol,
        "provider": PROVIDER,
        "scheduled_open": OPEN,
        "scheduled_close": CLOSE,
        "subscribe_ack_timeout_seconds": 0.01,
    }
    values.update(changes)
    return LiveShadowCaptureConfig(**values)


def test_journal_session_binds_provider_paper_fill_and_no_execution() -> None:
    session = live_shadow_journal_session(config(), ACTIVATION)

    assert session.session_id == ACTIVATION.thesis.draft.session_id
    assert session.started_at == ACTIVATION.thesis.filled_at.value
    assert session.metadata["provider"] == "shioaji"
    assert session.metadata["provider_version"] == "1.7.2"
    assert session.metadata["provider_simulation"] is True
    assert session.metadata["provider_identity"] == PROVIDER.environment_identity
    assert session.metadata["paper_fill_activation_id"] == ACTIVATION.activation_id
    assert session.metadata["execution_enabled"] is False
    assert session.metadata["evidence_only"] is True


def test_runner_requires_matching_session_symbol_and_provider() -> None:
    stream = FakeStream(PROVIDER.environment_identity)
    operation = StubOperation()
    clock = MutableClock(ACTIVATION.thesis.filled_at.value)

    with pytest.raises(ValueError, match="session"):
        LiveShadowCaptureRunner(
            config=config(session_id="different-session"),
            activation=ACTIVATION,
            stream=stream,
            operation=operation,
            clock=clock,
        )
    with pytest.raises(ValueError, match="provider identity"):
        LiveShadowCaptureRunner(
            config=config(),
            activation=ACTIVATION,
            stream=FakeStream("shioaji:other:simulation=true"),
            operation=operation,
            clock=clock,
        )


def test_runner_waits_for_paired_ack_before_admitting_market_events() -> None:
    stream = FakeStream(PROVIDER.environment_identity, acknowledge=False)
    operation = StubOperation()
    runner = LiveShadowCaptureRunner(
        config=config(),
        activation=ACTIVATION,
        stream=stream,
        operation=operation,
        clock=MutableClock(ACTIVATION.thesis.filled_at.value),
    )

    with pytest.raises(RuntimeError, match="ACK timed out"):
        runner.start()

    assert stream.closed is True
    assert operation.market_factories == []


def test_runner_counts_but_does_not_admit_events_before_paired_ack() -> None:
    stream = FakeStream(
        PROVIDER.environment_identity,
        pre_ack_event=live_events()[0],
    )
    operation = StubOperation()
    clock = MutableClock(ACTIVATION.thesis.filled_at.value)
    runner = LiveShadowCaptureRunner(
        config=config(subscribe_ack_timeout_seconds=0.1),
        activation=ACTIVATION,
        stream=stream,
        operation=operation,
        clock=clock,
    )
    runner.start()

    evidence = runner.finalize()

    assert evidence.pre_ack_market_event_count == 1
    assert operation.market_factories == []


def test_runner_admits_resequenced_events_and_lifecycle_after_ack() -> None:
    stream = FakeStream(PROVIDER.environment_identity)
    operation = StubOperation()
    clock = MutableClock(ACTIVATION.thesis.filled_at.value)
    runner = LiveShadowCaptureRunner(
        config=config(),
        activation=ACTIVATION,
        stream=stream,
        operation=operation,
        clock=clock,
    )
    runner.start()

    event = replace(
        live_events()[0],
        session_id=config().session_id,
    )
    stream.emit_market(event)
    stream.emit_lifecycle(
        StreamLifecycleEvent(
            event_type=StreamLifecycleEventType.DISCONNECTED,
            occurred_at=clock.now(),
            reason="test disconnect",
        )
    )

    admitted = operation.market_factories[0](7)
    lifecycle = operation.lifecycle_factories[0](8)
    assert admitted.ingress_sequence == 7
    assert admitted.payload.ingress_sequence == 7
    assert lifecycle.ingress_sequence == 8
    assert lifecycle.event_type == "PROVIDER_DISCONNECTED"


def test_runner_reports_shadow_coverage_without_claiming_full_market_session() -> None:
    stream = FakeStream(PROVIDER.environment_identity)
    operation = StubOperation()
    clock = MutableClock(ACTIVATION.thesis.filled_at.value)
    runner = LiveShadowCaptureRunner(
        config=config(),
        activation=ACTIVATION,
        stream=stream,
        operation=operation,
        clock=clock,
    )
    runner.start()
    clock.current += timedelta(minutes=30)

    evidence = runner.finalize()

    assert evidence.version == LIVE_SHADOW_CAPTURE_VERSION
    assert evidence.activation_id == ACTIVATION.activation_id
    assert evidence.full_market_session_covered is False
    assert evidence.pre_ack_market_event_count == 0
    assert evidence.shadow_started_at == ACTIVATION.thesis.filled_at.value
    assert evidence.shadow_ended_at == clock.current
    assert stream.closed is True
    assert runner.finalize() is evidence


def test_capture_runner_has_no_thesis_order_broker_or_sdk_authority() -> None:
    root = Path(__file__).parents[1]
    source = (root / "runtime" / "trade_management_live_capture.py").read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported_names.isdisjoint(
        {"PaperFillThesisBuilder", "TradeThesis", "OrderCommand", "SimulationService"}
    )
    assert referenced_names.isdisjoint({"Broker", "SELL", "Shioaji"})
