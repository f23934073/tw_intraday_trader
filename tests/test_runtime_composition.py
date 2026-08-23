from datetime import datetime
from decimal import Decimal

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
from simulation.settings import LocalPaperSettings
from trading.journal import JournalRecord, JournalSession
from trading.local_paper import (
    LOCAL_PAPER_FILL_KIND,
    LOCAL_PAPER_PROJECTION_NAME,
    write_local_paper_checkpoint,
)


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


def test_settings_bound_session_recovery_validates_complete_policy() -> None:
    journal = InMemoryJournalRepository()
    initial = LocalPaperSettings.from_mapping(
        {
            "starting_cash_twd": "10000000",
            "max_daily_buy_notional_twd": "200000",
            "commission_rate": "0.001425",
            "minimum_commission_twd": "20",
        }
    )
    RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        local_paper_settings=initial,
        local_paper_settings_revision=7,
        local_paper_session_id="local-paper-settings-bound-test",
    )
    session = journal.session("local-paper-settings-bound-test")

    assert session is not None
    assert session.metadata["settings_schema"] == "local-paper-settings-v1"
    assert session.metadata["settings_revision"] == 7
    assert session.metadata["settings_digest"] == initial.digest

    changed = LocalPaperSettings.from_mapping(
        {
            "starting_cash_twd": "10000000",
            "max_daily_buy_notional_twd": "999999",
            "commission_rate": "0.002",
            "minimum_commission_twd": "30",
        }
    )
    with pytest.raises(ValueError, match="settings conflicts with Journal"):
        RuntimeComposition.create(
            MockProvider(),
            journal=journal,
            local_paper_settings=changed,
            local_paper_settings_revision=7,
            local_paper_session_id="local-paper-settings-bound-test",
        )
    with pytest.raises(ValueError, match="settings conflicts with Journal"):
        RuntimeComposition.create(
            MockProvider(),
            journal=journal,
            local_paper_settings=initial,
            local_paper_settings_revision=8,
            local_paper_session_id="local-paper-settings-bound-test",
        )


def test_legacy_default_session_uses_explicit_compatibility_policy() -> None:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id="local-paper-runtime-v1",
            started_at=datetime.fromisoformat("2026-08-18T09:00:00+08:00"),
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"starting_cash": "10000000"},
        )
    )

    composition = RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        local_paper_settings_revision=0,
    )

    assert composition.local_paper_commands.session_id == "local-paper-runtime-v1"


def test_real_legacy_session_metadata_recovers_v1_fill_and_checkpoint() -> None:
    journal = InMemoryJournalRepository()
    session_id = "local-paper-runtime-v1"
    occurred_at = datetime.fromisoformat("2026-08-18T09:00:00+08:00")
    journal.start_session(
        JournalSession(
            session_id=session_id,
            started_at=occurred_at,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "starting_cash": "10000000",
                "execution_boundary": "LOCAL_ONLY",
                "journal_backend": "INJECTED",
                "restart_policy": "RESUME_CHECKPOINTED_LOCAL_PAPER_SESSION",
            },
        )
    )
    journal.append(
        JournalRecord(
            record_id="legacy-fill-1",
            session_id=session_id,
            kind=LOCAL_PAPER_FILL_KIND,
            occurred_at=occurred_at,
            payload={
                "order_id": "legacy-order-1",
                "symbol": "2330",
                "name": "台積電",
                "side": "BUY",
                "quantity_shares": 100,
                "fill_price": "10",
            },
        )
    )
    write_local_paper_checkpoint(
        journal,
        session_id=session_id,
        starting_cash=Decimal("10000000"),
    )

    composition = RuntimeComposition.create(
        MockProvider(),
        journal=journal,
        local_paper_settings_revision=0,
    )

    assert composition.simulation_service.session()["available_cash"] == 9_999_000.0
    assert composition.simulation_service.positions()[0]["quantity"] == 100


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("settings_revision", 0),
        ("settings_digest", "0" * 64),
        ("max_daily_buy_notional", "2000000"),
        ("commission_rate", "0"),
        ("minimum_commission", "0"),
        ("fee_rounding_policy", "ROUND_HALF_UP_0.01_TWD"),
    ],
)
def test_legacy_session_with_partial_new_settings_binding_fails_closed(
    field_name: str,
    field_value: object,
) -> None:
    journal = InMemoryJournalRepository()
    metadata: dict[str, object] = {
        "starting_cash": "10000000",
        "execution_boundary": "LOCAL_ONLY",
        "journal_backend": "INJECTED",
        "restart_policy": "RESUME_CHECKPOINTED_LOCAL_PAPER_SESSION",
        field_name: field_value,
    }
    journal.start_session(
        JournalSession(
            session_id="local-paper-runtime-v1",
            started_at=datetime.fromisoformat("2026-08-18T09:00:00+08:00"),
            mode="LOCAL_PAPER_SIMULATION",
            metadata=metadata,
        )
    )

    with pytest.raises(ValueError, match="settings conflicts with Journal"):
        RuntimeComposition.create(
            MockProvider(),
            journal=journal,
            local_paper_settings_revision=0,
        )


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
