from datetime import datetime

import pytest

import dashboard.server as server
from app import build_provider
from market_data.provider import MockProvider
from premarket.artifacts import InMemoryPremarketArtifactRepository
from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository, InMemoryProjectionRepository
from trading.journal import JournalRecord, JournalSession
from trading.local_paper import LOCAL_PAPER_PROJECTION_NAME


class CloseTrackingJournal(InMemoryJournalRepository):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_composition_reuses_one_provider_without_provider_io() -> None:
    provider = MockProvider()
    artifacts = InMemoryPremarketArtifactRepository()

    composition = RuntimeComposition.create(provider, premarket_artifacts=artifacts)

    assert composition.provider is provider
    assert composition.dashboard_service._provider is provider
    assert composition.dashboard_service._premarket_service is composition.premarket_service
    assert composition.premarket_artifacts is artifacts
    assert composition.clock.now().tzinfo is not None
    checkpoint = composition.journal.latest_checkpoint(
        composition.local_paper_commands.session_id,
        LOCAL_PAPER_PROJECTION_NAME,
    )
    assert checkpoint is not None
    assert checkpoint.journal_sequence == 1
    assert composition.journal.records(
        composition.local_paper_commands.session_id
    )[0].record.kind == "local_paper_daily_baseline.v1"


def test_composition_selects_configured_journal_through_infrastructure_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = InMemoryJournalRepository()
    received: list[TradingPersistenceConfig] = []

    def build(config: TradingPersistenceConfig) -> InMemoryJournalRepository:
        received.append(config)
        return journal

    monkeypatch.setattr("runtime.composition.build_journal_repository", build)
    config = TradingPersistenceConfig(
        backend=TradingJournalBackend.POSTGRESQL,
        database_url="postgresql://not-opened-in-this-test/db",
    )

    composition = RuntimeComposition.create(
        MockProvider(),
        persistence_config=config,
    )

    assert received == [config]
    assert composition.journal is journal


def test_injected_journal_bypasses_environment_persistence_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRADING_JOURNAL_BACKEND", "postgresql")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRESQL_DSN", raising=False)
    monkeypatch.delenv("PostgreSQL_DSN", raising=False)
    journal = InMemoryJournalRepository()

    composition = RuntimeComposition.create(MockProvider(), journal=journal)

    assert composition.journal is journal


def test_composition_closes_a_lifecycle_aware_journal() -> None:
    provider = MockProvider()
    journal = CloseTrackingJournal()
    composition = RuntimeComposition.create(provider, journal=journal)

    composition.close()

    assert journal.closed is True


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
