from datetime import datetime

import pytest

import dashboard.server as server
from app import build_provider
from market_data.provider import MockProvider
from premarket.artifacts import InMemoryPremarketArtifactRepository
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository, InMemoryProjectionRepository
from trading.journal import JournalRecord, JournalSession


def test_composition_reuses_one_provider_without_provider_io() -> None:
    provider = MockProvider()
    artifacts = InMemoryPremarketArtifactRepository()

    composition = RuntimeComposition.create(provider, premarket_artifacts=artifacts)

    assert composition.provider is provider
    assert composition.dashboard_service._provider is provider
    assert composition.dashboard_service._premarket_service is composition.premarket_service
    assert composition.premarket_artifacts is artifacts
    assert composition.clock.now().tzinfo is not None


def test_build_provider_defaults_to_mock_without_provider_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROVIDER", raising=False)

    assert isinstance(build_provider(), MockProvider)


def test_in_memory_adapters_are_append_ordered_and_copy_on_read() -> None:
    journal = InMemoryJournalRepository()
    projections = InMemoryProjectionRepository()
    session = JournalSession(
        session_id="runtime-composition-test",
        started_at=datetime.fromisoformat("2026-08-18T09:00:00+08:00"),
        mode="TEST",
        metadata={},
    )
    record = JournalRecord(
        record_id="event-1",
        session_id=session.session_id,
        kind="market_event",
        occurred_at=datetime.fromisoformat("2026-08-18T09:00:00+08:00"),
        payload={"symbol": "2330"},
    )

    journal.start_session(session)
    journal.append(record)
    projections.put("latest:2330", {"price": 1})
    projection = projections.get("latest:2330")
    assert projection == {"price": 1}
    assert projection is not None
    projection["price"] = 2

    assert journal.records(session.session_id)[0].record == record
    assert projections.get("latest:2330") == {"price": 1}


def test_dashboard_service_accessors_rebuild_a_composition_for_injected_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = MockProvider()
    monkeypatch.setattr(server, "_composition", None)
    monkeypatch.setattr(server, "_provider", provider)
    monkeypatch.setattr(server, "_service", None)
    monkeypatch.setattr(server, "_simulation_service", None)

    composition = server.get_runtime_composition()

    assert composition.provider is provider
    assert server.get_market_provider() is provider
    assert server.get_dashboard_service() is composition.dashboard_service
    assert server.get_simulation_service() is composition.simulation_service
