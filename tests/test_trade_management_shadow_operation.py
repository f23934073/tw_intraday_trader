from __future__ import annotations

import ast
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.health import DataHealth
from market_data.ingestion import IngestStatus, MarketDataIngestor
from market_data.ingress import BoundedIngressQueue
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.events import EventEnvelope, InstrumentReference
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import CanonicalMarketDataPipeline
from market_data.recording import InMemoryMarketEventRecorder
from runtime.trade_management_shadow import (
    LIVE_SHADOW_OPERATION_VERSION,
    LiveTradeManagementShadowOperation,
)
from tests.test_trade_management_replay import SNAPSHOT, THESIS, hard_invalid_events
from tests.test_trade_management_shadow import config
from trading.journal import InMemoryJournalRepository, JournalSession
from trading.shadow_evidence_journal import (
    SHADOW_EVIDENCE_PROJECTION_NAME,
    ShadowEvidenceJournalKind,
    rebuild_shadow_evidence_projection,
)


def build_market_pipeline(*, session_date=None) -> CanonicalMarketDataPipeline:
    session_date = session_date or THESIS.filled_at.value.date()
    health = DataHealth(session_date, started_at=THESIS.draft.signal_at.value)
    health.mark_ready(
        occurred_at=THESIS.draft.signal_at.value,
        evidence="live paired Tick/BidAsk subscription",
    )
    references = InstrumentReferenceStore(session_date)
    references.put(
        InstrumentReference(
            symbol="2330",
            exchange="TSE",
            session_date=session_date,
            reference_price=Decimal("590"),
            limit_up_price=Decimal("649"),
            limit_down_price=Decimal("531"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=session_date,
        )
    )
    return CanonicalMarketDataPipeline(
        queue=BoundedIngressQueue(
            capacity=16,
            control_reserve=2,
            health=health,
        ),
        recorder=InMemoryMarketEventRecorder(),
        ingestor=MarketDataIngestor(
            session_id=THESIS.draft.session_id,
            session_date=session_date,
            references=references,
            bars=IntradayBarStore(session_date, retention=timedelta(minutes=20)),
            books=OrderBookStore(session_date, retention=timedelta(minutes=20)),
            health=health,
        ),
        health=health,
    )


def live_events() -> tuple[EventEnvelope, ...]:
    return tuple(
        replace(
            event,
            source_mode="LIVE_STREAM",
            source_identity=f"live-provider:{event.ingress_sequence}",
            raw_capture_id=None,
        )
        for event in hard_invalid_events()
    )


def build_operation(*, risk_provider=None, journal=None):
    journal = journal or InMemoryJournalRepository()
    operation = LiveTradeManagementShadowOperation(
        market_pipeline=build_market_pipeline(),
        shadow_config=config(code_identity="git:pr-tm-009-test"),
        risk_snapshot_provider=risk_provider or (lambda _event, _result: SNAPSHOT),
        journal=journal,
        journal_session=JournalSession(
            session_id=THESIS.draft.session_id,
            started_at=THESIS.draft.signal_at.value,
            mode="TRADE_MANAGEMENT_SHADOW",
            metadata={
                "execution_enabled": False,
                "evidence_only": True,
                "operation_version": LIVE_SHADOW_OPERATION_VERSION,
            },
        ),
    )
    return operation, journal


class FailOnceDecisionJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def append(self, record):
        if (
            record.kind == ShadowEvidenceJournalKind.DECISION_RECORDED.value
            and not self.failed
        ):
            self.failed = True
            raise OSError("durable evidence unavailable")
        return super().append(record)


def submit_and_process(operation, event):
    admission = operation.submit_market(lambda sequence: event)
    assert admission.accepted
    results = operation.process_pending(occurred_at=event.received_at)
    assert len(results) == 1
    return results[0]


def test_applied_live_events_run_shadow_and_append_decision_evidence() -> None:
    risk_calls = []
    operation, journal = build_operation(
        risk_provider=lambda event, result: (
            risk_calls.append((event.event_id, result.status)) or SNAPSHOT
        )
    )

    for event in live_events():
        result = submit_and_process(operation, event)
        assert result.ingest_result is not None
        assert result.ingest_result.status is IngestStatus.APPLIED

    shadow = operation.snapshot()
    journaled = journal.records(THESIS.draft.session_id)

    assert shadow.consumed_event_count == len(live_events())
    assert len(shadow.records) == len(live_events())
    assert len(risk_calls) == len(live_events())
    assert len(journaled) == len(shadow.records)
    assert all(
        item.record.kind
        == ShadowEvidenceJournalKind.DECISION_RECORDED.value
        for item in journaled
    )


def test_duplicate_or_rejected_market_event_does_not_enter_shadow_chain() -> None:
    operation, journal = build_operation()
    first = live_events()[0]
    submit_and_process(operation, first)
    before = operation.snapshot()

    duplicate_event = replace(
        first,
        ingress_sequence=2,
        source_identity="live-duplicate-delivery",
        payload=replace(first.payload, ingress_sequence=2),
    )
    duplicate = submit_and_process(operation, duplicate_event)

    assert duplicate.ingest_result is not None
    assert duplicate.ingest_result.status is IngestStatus.DUPLICATE
    assert operation.snapshot() == before
    assert len(journal.records(THESIS.draft.session_id)) == 1


def test_writer_failure_keeps_pending_evidence_and_retries_before_new_input() -> None:
    operation, journal = build_operation(journal=FailOnceDecisionJournal())
    first = live_events()[0]
    assert operation.submit_market(lambda sequence: first).accepted

    with pytest.raises(OSError, match="evidence unavailable"):
        operation.process_pending(occurred_at=first.received_at)

    assert operation.snapshot().consumed_event_count == 1
    assert journal.records(THESIS.draft.session_id) == ()

    assert operation.process_pending(occurred_at=first.received_at) == ()
    assert len(journal.records(THESIS.draft.session_id)) == 1


def test_finalize_persists_parity_writes_checkpoint_and_verifies_recovery() -> None:
    operation, journal = build_operation()
    for event in live_events():
        submit_and_process(operation, event)

    finalized = operation.finalize()
    checkpoint = journal.latest_checkpoint(
        THESIS.draft.session_id,
        SHADOW_EVIDENCE_PROJECTION_NAME,
    )
    rebuilt = rebuild_shadow_evidence_projection(
        journal,
        session_id=THESIS.draft.session_id,
    )

    assert finalized.session.parity.status.value == "MATCHED"
    assert finalized.projection.digest == rebuilt.digest
    assert finalized.projection.finalization is not None
    assert checkpoint is not None
    assert checkpoint.digest == rebuilt.digest
    assert len(journal.records(THESIS.draft.session_id)) == (
        len(live_events()) + 1
    )
    assert operation.finalize() is finalized
    with pytest.raises(RuntimeError, match="finalized"):
        operation.process_pending(occurred_at=live_events()[-1].received_at)


def test_operation_requires_explicit_evidence_only_session() -> None:
    journal = InMemoryJournalRepository()
    with pytest.raises(ValueError, match="evidence-only"):
        LiveTradeManagementShadowOperation(
            market_pipeline=build_market_pipeline(),
            shadow_config=config(code_identity="git:pr-tm-009-test"),
            risk_snapshot_provider=lambda _event, _result: SNAPSHOT,
            journal=journal,
            journal_session=JournalSession(
                session_id=THESIS.draft.session_id,
                started_at=THESIS.draft.signal_at.value,
                mode="TRADE_MANAGEMENT_SHADOW",
                metadata={
                    "execution_enabled": True,
                    "evidence_only": False,
                    "operation_version": LIVE_SHADOW_OPERATION_VERSION,
                },
            ),
        )


def test_live_shadow_operation_has_no_execution_or_broker_authority() -> None:
    root = Path(__file__).parents[1]
    source = (root / "runtime" / "trade_management_shadow.py").read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }

    assert imported_names.isdisjoint(
        {"OrderCommand", "OrderApplicationService", "SimulationService"}
    )
    assert referenced_names.isdisjoint(
        {"Broker", "Position", "SELL", "Shioaji"}
    )
