from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.provider import MockProvider
from runtime.in_memory import InMemoryJournalRepository
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationService
from tests.test_trade_management_replay import THESIS
from trading.journal import JournalRecord, JournalSession
from trading.paper_thesis_activation import (
    PAPER_FILL_THESIS_ACTIVATION_VERSION,
    PaperFillSource,
    PaperFillThesisBuilder,
    paper_thesis_entry_idempotency_key,
)
from trading.trade_management import build_thesis_id, build_trade_id


class FixedClock:
    def now(self):
        return THESIS.draft.created_at.value

    def session_date(self):
        return THESIS.draft.created_at.value.date()


def draft_for(*, session_id: str, symbol: str = "2330"):
    draft = THESIS.draft
    return replace(
        draft,
        thesis_id=build_thesis_id(
            session_id,
            draft.decision_id,
            draft.thesis_type,
            draft.thesis_version,
        ),
        session_id=session_id,
        symbol=symbol,
    )


def filled_paper_entry():
    session_id = "paper-thesis-session-20260820"
    draft = draft_for(session_id=session_id)
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=session_id,
            started_at=draft.signal_at.value,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"execution_boundary": "LOCAL_ONLY"},
        )
    )
    clock = FixedClock()
    simulation = SimulationService(
        MockProvider(),
        starting_cash=Decimal("2000000"),
        clock=clock,
    )
    service = LocalPaperCommandService(
        simulation=simulation,
        journal=journal,
        session_id=session_id,
        clock=clock,
    )
    order, _idempotent = service.submit_order(
        symbol=draft.symbol,
        side="BUY",
        lots=1,
        limit_price="1000",
        idempotency_key=paper_thesis_entry_idempotency_key(draft),
    )
    assert order["status"] == "FILLED"
    fill = next(
        item.record
        for item in journal.records(session_id)
        if item.record.kind == "local_paper_fill.v1"
    )
    return draft, fill


def with_payload(record: JournalRecord, **changes: object) -> JournalRecord:
    return JournalRecord(
        record_id=record.record_id,
        session_id=record.session_id,
        kind=record.kind,
        occurred_at=record.occurred_at,
        payload={**record.payload, **changes},
        idempotency_scope=record.idempotency_scope,
        idempotency_key=record.idempotency_key,
        schema_version=record.schema_version,
    )


def test_local_paper_buy_fill_activates_authoritative_thesis() -> None:
    draft, fill = filled_paper_entry()

    activation = PaperFillThesisBuilder().activate(draft, fill)

    assert activation.version == PAPER_FILL_THESIS_ACTIVATION_VERSION
    assert activation.provenance.fill_source is PaperFillSource.PAPER_SIMULATION
    assert activation.provenance.provider_identity == "market_data.provider.MockProvider"
    assert activation.provenance.execution_authority is False
    assert activation.provenance.fill_record_id == fill.record_id
    assert activation.provenance.fill_record_fingerprint == fill.fingerprint
    assert activation.thesis.draft is draft
    assert activation.thesis.opening_order_id == fill.payload["order_id"]
    assert activation.thesis.opening_fill_id == fill.record_id
    assert activation.thesis.entry_reference_price == Decimal(str(fill.payload["fill_price"]))
    assert activation.thesis.filled_at.value == fill.occurred_at
    assert activation.thesis.trade_id == build_trade_id(draft.session_id, fill.record_id)
    assert activation.thesis.thesis_start_at == activation.thesis.filled_at


def test_activation_is_deterministic_immutable_and_carries_no_execution_authority() -> None:
    draft, fill = filled_paper_entry()
    builder = PaperFillThesisBuilder()

    first = builder.activate(draft, fill)
    second = builder.activate(draft, fill)

    assert first == second
    assert first.activation_id == second.activation_id
    assert first.digest == second.digest
    with pytest.raises(FrozenInstanceError):
        first.activation_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="cannot grant execution authority"):
        replace(
            first,
            provenance=replace(first.provenance, execution_authority=True),
        )


def test_old_fill_without_explicit_provenance_cannot_activate_thesis() -> None:
    draft, fill = filled_paper_entry()
    legacy = JournalRecord(
        record_id=fill.record_id,
        session_id=fill.session_id,
        kind=fill.kind,
        occurred_at=fill.occurred_at,
        payload={
            key: value
            for key, value in fill.payload.items()
            if key not in {"fill_source", "provider_identity", "execution_authority"}
        },
        idempotency_scope=fill.idempotency_scope,
        idempotency_key=fill.idempotency_key,
    )

    with pytest.raises(ValueError, match="provenance"):
        PaperFillThesisBuilder().activate(draft, legacy)


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"side": "SELL"}, "BUY fill"),
        ({"symbol": "2317"}, "symbol"),
        ({"command_idempotency_key": "unrelated"}, "correlate"),
        ({"execution_authority": True}, "execution authority"),
        ({"fill_source": "broker_fill"}, "paper simulation"),
    ),
)
def test_activation_rejects_invalid_fill_semantics(change, message) -> None:
    draft, fill = filled_paper_entry()

    with pytest.raises(ValueError, match=message):
        PaperFillThesisBuilder().activate(draft, with_payload(fill, **change))


def test_activation_rejects_session_and_time_mismatch() -> None:
    draft, fill = filled_paper_entry()
    wrong_session = JournalRecord(
        record_id=fill.record_id,
        session_id="other-session",
        kind=fill.kind,
        occurred_at=fill.occurred_at,
        payload=fill.payload,
        idempotency_scope=fill.idempotency_scope,
        idempotency_key=fill.idempotency_key,
    )
    early_fill = JournalRecord(
        record_id=fill.record_id,
        session_id=fill.session_id,
        kind=fill.kind,
        occurred_at=draft.created_at.value - THESIS.draft.expected_behavior.warning_after,
        payload=fill.payload,
        idempotency_scope=fill.idempotency_scope,
        idempotency_key=fill.idempotency_key,
    )

    with pytest.raises(ValueError, match="session"):
        PaperFillThesisBuilder().activate(draft, wrong_session)
    with pytest.raises(ValueError, match="predate thesis draft"):
        PaperFillThesisBuilder().activate(draft, early_fill)


def test_builder_has_no_order_journal_broker_or_stream_authority() -> None:
    root = Path(__file__).parents[1]
    source = (root / "trading" / "paper_thesis_activation.py").read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported_names.isdisjoint(
        {
            "JournalRepository",
            "RiskGate",
            "OrderCommand",
            "OrderApplicationService",
            "ShioajiProvider",
        }
    )
    assert referenced_names.isdisjoint(
        {"Broker", "SELL", "Position", "SimulationService", "Shioaji"}
    )
