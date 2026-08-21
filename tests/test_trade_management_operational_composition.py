from __future__ import annotations

import ast
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.momentum_stream import StreamLifecycleEvent, StreamLifecycleEventType
from market_data.provider import MockProvider
from runtime.trade_management_live_capture import (
    LiveShadowCaptureConfig,
    LiveShadowProviderIdentity,
)
from runtime.trade_management_operational_composition import (
    ExistingPaperFillObserver,
    LiveShadowDecisionPolicy,
    LiveTradeManagementOperationalComposer,
    PaperFillNotObservedError,
)
from scoring.models import BuyScoreResult, ScoreDetail
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationService
from tests.test_live_entry_thesis_draft import decision, policy
from tests.test_trade_management_replay import POLICY, SNAPSHOT
from tests.test_trade_management_shadow_operation import (
    build_market_pipeline,
    live_events,
)
from trading.buy_score_entry_evidence import BuyScoreEntryEvidenceAdapter
from trading.journal import InMemoryJournalRepository, JournalSession
from trading.live_entry_thesis_draft import LiveTradeThesisDraftBuilder
from trading.paper_thesis_activation import paper_thesis_entry_idempotency_key
from trading.shadow_evidence_journal import ShadowEvidenceJournalKind
from trading.trade_management import EntryEvidenceStatus, EvidenceValueKind


PROVIDER = LiveShadowProviderIdentity(
    provider="test-provider",
    sdk_version="1",
    simulation=True,
    connection_session_id="connection-20260820-a",
)


class MutableClock:
    def __init__(self, current):
        self.current = current

    def now(self):
        return self.current

    def session_date(self):
        return self.current.date()


class FakeStream:
    environment_identity = PROVIDER.environment_identity
    callback_errors = ()

    def __init__(self, acknowledged_at) -> None:
        self.acknowledged_at = acknowledged_at
        self.market_handler = None
        self.lifecycle_handler = None
        self.closed = False

    def start(self, market_handler, lifecycle_handler) -> None:
        self.market_handler = market_handler
        self.lifecycle_handler = lifecycle_handler

    def request_subscribe(self, symbol: str) -> None:
        assert self.lifecycle_handler is not None
        self.lifecycle_handler(
            StreamLifecycleEvent(
                event_type=StreamLifecycleEventType.SUBSCRIBE_ACKED,
                occurred_at=self.acknowledged_at,
                reason="paired Tick/BidAsk acknowledged",
                symbol=symbol,
            )
        )

    def close(self) -> None:
        self.closed = True

    def emit_market(self, event) -> None:
        assert self.market_handler is not None
        self.market_handler(event)


def existing_fill_journal():
    entry = decision()
    draft = LiveTradeThesisDraftBuilder().build(entry, policy())
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=draft.session_id,
            started_at=draft.signal_at.value,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    provider = MockProvider()
    provider.environment_identity = PROVIDER.environment_identity
    clock = MutableClock(draft.created_at.value)
    service = LocalPaperCommandService(
        simulation=SimulationService(
            provider,
            starting_cash=Decimal("2000000"),
            clock=clock,
        ),
        journal=journal,
        session_id=draft.session_id,
        clock=clock,
    )
    order, _ = service.submit_order(
        symbol=draft.symbol,
        side="BUY",
        lots=1,
        limit_price="1000",
        idempotency_key=paper_thesis_entry_idempotency_key(draft),
    )
    assert order["status"] == "FILLED"
    return entry, draft, journal


def capture_config(draft, filled_at) -> LiveShadowCaptureConfig:
    return LiveShadowCaptureConfig(
        session_id=draft.session_id,
        symbol=draft.symbol,
        provider=PROVIDER,
        scheduled_open=filled_at - timedelta(minutes=1),
        scheduled_close=filled_at + timedelta(hours=4),
        subscribe_ack_timeout_seconds=0.1,
    )


def shadow_policy() -> LiveShadowDecisionPolicy:
    return LiveShadowDecisionPolicy(
        exit_policy_version="thesis-exit-policy-v1",
        risk_policy=POLICY,
        volume_baseline_shares=Decimal("1000"),
        shares_per_lot=1000,
        remaining_quantity_shares=1000,
        fill_model_version="shadow-observation-no-fill-v1",
        code_identity="git:pr-tm-012b2-test",
    )


def test_buy_score_breakdown_becomes_typed_deterministic_entry_evidence() -> None:
    score = BuyScoreResult(
        symbol="2330",
        total_score=85,
        details=[
            ScoreDetail(rule="RVOL_HIGH", score=25, max_score=30),
            ScoreDetail(rule="BREAKOUT", score=40, max_score=40),
            ScoreDetail(rule="ABOVE_VWAP", score=20, max_score=30),
        ],
    )
    timestamp = decision().signal_at
    adapter = BuyScoreEntryEvidenceAdapter()

    first = adapter.capture(
        score,
        source_component="BuyScoreEngine",
        strategy_version=decision().strategy_version,
        status=EntryEvidenceStatus.MATCHED,
        market_event_id="market-event-score-1",
        observed_at=timestamp,
    )
    second = adapter.capture(
        replace(score, details=list(reversed(score.details))),
        source_component="BuyScoreEngine",
        strategy_version=decision().strategy_version,
        status=EntryEvidenceStatus.MATCHED,
        market_event_id="market-event-score-1",
        observed_at=timestamp,
    )

    assert first == second
    assert first.evidence_id == second.evidence_id
    assert first.kind == "BUY_SCORE_BREAKDOWN"
    assert first.status is EntryEvidenceStatus.MATCHED
    assert first.observed[0].value == "85"
    assert first.observed[0].kind is EvidenceValueKind.INTEGER
    assert tuple(item.value for item in first.threshold) == ("30", "40", "30")
    different_source = adapter.capture(
        score,
        source_component="BuyScoreEngine",
        strategy_version=decision().strategy_version,
        status=EntryEvidenceStatus.MATCHED,
        market_event_id="market-event-score-1",
        observed_at=replace(timestamp, source_identity="different-source"),
    )
    assert different_source.evidence_id != first.evidence_id


def test_existing_fill_observation_is_deterministic_and_read_only() -> None:
    _entry, draft, journal = existing_fill_journal()
    before = journal.records(draft.session_id)
    observer = ExistingPaperFillObserver()

    first = observer.observe(draft, journal)
    second = observer.observe(draft, journal)

    assert first == second
    assert first.activation.thesis.draft == draft
    assert first.fill_record_id == first.activation.provenance.fill_record_id
    assert journal.records(draft.session_id) == before


def test_fill_observation_identity_survives_journal_reconstruction() -> None:
    _entry, draft, journal = existing_fill_journal()
    original = ExistingPaperFillObserver().observe(draft, journal)
    rebuilt = InMemoryJournalRepository()
    rebuilt.start_session(
        JournalSession(
            session_id=draft.session_id,
            started_at=draft.signal_at.value,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    for result in journal.records(draft.session_id):
        rebuilt.append(result.record)

    recovered = ExistingPaperFillObserver().observe(draft, rebuilt)

    assert recovered == original
    assert recovered.activation.activation_id == original.activation.activation_id
    assert recovered.activation.digest == original.activation.digest


def test_fill_observation_waits_fail_closed_without_creating_a_fill() -> None:
    entry = decision()
    draft = LiveTradeThesisDraftBuilder().build(entry, policy())
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=draft.session_id,
            started_at=draft.signal_at.value,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )

    with pytest.raises(PaperFillNotObservedError, match="has not been observed"):
        ExistingPaperFillObserver().observe(draft, journal)

    assert journal.records(draft.session_id) == ()


def test_composer_connects_existing_fill_to_shadow_and_durable_evidence() -> None:
    entry, draft, fill_journal = existing_fill_journal()
    evidence_journal = InMemoryJournalRepository()
    observed = ExistingPaperFillObserver().observe(draft, fill_journal)
    filled_at = observed.activation.thesis.filled_at.value
    stream = FakeStream(filled_at)
    clock = MutableClock(filled_at)
    composition = LiveTradeManagementOperationalComposer().compose(
        decision=entry,
        draft_policy=policy(),
        fill_journal=fill_journal,
        evidence_journal=evidence_journal,
        shadow_policy=shadow_policy(),
        market_pipeline=build_market_pipeline(session_date=filled_at.date()),
        risk_snapshot_provider=lambda _event, _result: SNAPSHOT,
        capture_config=capture_config(draft, filled_at),
        stream=stream,
        clock=clock,
    )

    assert composition.draft == draft
    assert composition.shadow_config.thesis == composition.observed_fill.activation.thesis
    composition.runner.start()
    observed_at = filled_at + timedelta(minutes=1)
    source_event = live_events()[0]
    event = replace(
        source_event,
        session_id=draft.session_id,
        session_date=observed_at.date(),
        event_at=observed_at,
        received_at=observed_at,
        payload=replace(
            source_event.payload,
            session_date=observed_at.date(),
            event_time=observed_at,
            received_at=observed_at,
        ),
    )
    clock.current = observed_at
    stream.emit_market(event)
    composition.runner.process_pending()

    records = evidence_journal.records(draft.session_id)
    assert len(records) == 1
    assert records[0].record.kind == ShadowEvidenceJournalKind.DECISION_RECORDED.value
    assert fill_journal.records(draft.session_id)


def test_composer_rejects_one_repository_as_two_authorities() -> None:
    entry, draft, journal = existing_fill_journal()
    observed = ExistingPaperFillObserver().observe(draft, journal)
    filled_at = observed.activation.thesis.filled_at.value

    with pytest.raises(ValueError, match="separate Journal authorities"):
        LiveTradeManagementOperationalComposer().compose(
            decision=entry,
            draft_policy=policy(),
            fill_journal=journal,
            evidence_journal=journal,
            shadow_policy=shadow_policy(),
            market_pipeline=build_market_pipeline(),
            risk_snapshot_provider=lambda _event, _result: SNAPSHOT,
            capture_config=capture_config(draft, filled_at),
            stream=FakeStream(filled_at),
            clock=MutableClock(filled_at),
        )


def test_operational_composition_has_no_fill_order_position_or_broker_authority() -> None:
    root = Path(__file__).parents[1]
    source = (
        root / "runtime" / "trade_management_operational_composition.py"
    ).read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called_names = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }

    assert imported_names.isdisjoint(
        {
            "OrderCommand",
            "OrderApplicationService",
            "SimulationService",
            "LocalPaperCommandService",
            "RiskGate",
            "ShioajiProvider",
        }
    )
    assert called_names.isdisjoint(
        {"submit_order", "create_fill", "create_position", "match_order"}
    )
