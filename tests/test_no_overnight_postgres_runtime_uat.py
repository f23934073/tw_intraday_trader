"""Disposable PostgreSQL UAT for durable breach and runtime singleton fences."""

from datetime import date, datetime

import pytest

from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.no_overnight import no_overnight_session_id
from runtime.no_overnight_guard import (
    NoOvernightGuardUnavailable,
    PostgresNoOvernightControllerGuard,
)
from simulation.service import SimulationStateError
from simulation.settings import LocalPaperSettings
from tests.test_no_overnight_breach_runtime import (
    ORIGIN_DATE,
    HealthyGuard,
    MutableBreachEvidenceReader,
    _admission,
    _controller,
)
from trading.migrations import apply_migrations
from trading.local_paper import session_archive_record
from trading.no_overnight_admission import ExecutionAdmissionStatus
from trading.no_overnight_journal import rebuild_no_overnight_projection
from trading.postgres_journal import PostgresJournalRepository


psycopg = pytest.importorskip("psycopg")
from psycopg import sql  # noqa: E402
from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402


MISMATCH_DATABASE = "tw_intraday_trader_guard_mismatch_test"


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def session_date(self) -> date:
        return self._now.date()


def _database_is_disposable(database_name: str) -> bool:
    return "test" in database_name.lower().replace("-", "_").split("_")


@pytest.fixture()
def no_overnight_postgres_dsn(postgres_test_dsn: str) -> str:
    setup = psycopg.connect(postgres_test_dsn)
    try:
        with setup.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = str(cursor.fetchone()[0])
        if not _database_is_disposable(database_name):
            pytest.fail(
                "refusing destructive No-Overnight UAT: database name must "
                "contain a standalone 'test' token"
            )
        with setup.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS trading CASCADE")
        setup.commit()
        apply_migrations(setup)
        yield postgres_test_dsn
    finally:
        setup.close()
        cleanup = psycopg.connect(postgres_test_dsn)
        try:
            with cleanup.cursor() as cursor:
                cursor.execute("DROP SCHEMA IF EXISTS trading CASCADE")
            cleanup.commit()
        finally:
            cleanup.close()


def _journal_counts(connection) -> tuple[int, int]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM trading.journal_sessions")
        sessions = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM trading.journal_records")
        records = int(cursor.fetchone()[0])
    connection.commit()
    return sessions, records


def _dsn_for_database(dsn: str, database_name: str) -> str:
    parameters = conninfo_to_dict(dsn)
    parameters["dbname"] = database_name
    return make_conninfo(**parameters)


def test_breach_resolution_ack_and_latch_survive_new_connection(
    no_overnight_postgres_dsn: str,
) -> None:
    reader = MutableBreachEvidenceReader()
    guard = HealthyGuard()
    first_connection = psycopg.connect(no_overnight_postgres_dsn)
    first_journal = PostgresJournalRepository(
        first_connection,
        database_url=no_overnight_postgres_dsn,
    )
    try:
        controller = _controller(first_journal, reader, guard)
        breached = controller.run_once(
            datetime.fromisoformat("2026-08-24T13:30:00+08:00")
        )
        breach_id = breached["breach"]["breach_id"]
        assert breached["breach"]["open"] is True

        reader.set_flat()
        resolution_at = datetime.fromisoformat("2026-08-25T09:05:00+08:00")
        resolved = controller.run_once(resolution_at)
        assert resolved["breach"]["breach_revision"] == 2
        assert resolved["breach"]["resolved"] is True
        acknowledged = controller.acknowledge_breach(
            breach_id=breach_id,
            breach_revision=2,
            reconciliation_digest="e" * 64,
            actor_id="local-operator",
            idempotency_key="postgres-ack-breach-revision-2",
            acknowledged_at=datetime.fromisoformat(
                "2026-08-25T09:06:00+08:00"
            ),
        )
        assert acknowledged["acknowledged"] is True
    finally:
        first_connection.close()

    second_connection = psycopg.connect(no_overnight_postgres_dsn)
    second_journal = PostgresJournalRepository(
        second_connection,
        database_url=no_overnight_postgres_dsn,
    )
    try:
        recovered = rebuild_no_overnight_projection(
            second_journal,
            session_id=no_overnight_session_id(ORIGIN_DATE),
            require_checkpoint=True,
        )
        assert recovered.breach_revision == 2
        assert recovered.breach_resolved is True
        assert recovered.breach_acknowledged is True

        same_session = datetime.fromisoformat("2026-08-25T09:07:00+08:00")
        assert _admission(second_journal, guard, same_session).status is (
            ExecutionAdmissionStatus.BLOCKED
        )

        next_session = datetime.fromisoformat("2026-08-26T09:05:00+08:00")
        restarted = _controller(second_journal, reader, guard)
        restarted.run_once(next_session)
        assert _admission(second_journal, guard, next_session).status is (
            ExecutionAdmissionStatus.APPROVED
        )
    finally:
        second_connection.close()


@pytest.mark.parametrize(
    "settings",
    (
        LocalPaperSettings.defaults(),
        LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults()),
    ),
    ids=("settings-v1", "settings-v2"),
)
def test_disabled_runtime_holds_cross_process_advisory_guard(
    no_overnight_postgres_dsn: str,
    settings: LocalPaperSettings,
) -> None:
    clock = _FixedClock(datetime.fromisoformat("2026-08-24T09:05:00+08:00"))
    first_connection = psycopg.connect(no_overnight_postgres_dsn)
    second_connection = psycopg.connect(no_overnight_postgres_dsn)
    first_provider = MockProvider()
    second_provider = MockProvider()
    first_journal = PostgresJournalRepository(
        first_connection,
        database_url=no_overnight_postgres_dsn,
    )
    first = RuntimeComposition.create(
        first_provider,
        clock=clock,
        journal=first_journal,
        local_paper_settings=settings,
        start_simulation_streaming=False,
    )
    replacement: RuntimeComposition | None = None
    try:
        assert first.no_overnight_guard is not None
        assert first.no_overnight_guard.is_owned_and_healthy() is True
        with pytest.raises(NoOvernightGuardUnavailable, match="already owned"):
            RuntimeComposition.create(
                second_provider,
                clock=clock,
                journal=PostgresJournalRepository(
                    second_connection,
                    database_url=no_overnight_postgres_dsn,
                ),
                local_paper_settings=settings,
                start_simulation_streaming=False,
            )
        replacement = RuntimeComposition.create(
            first_provider,
            dashboard_service=first.dashboard_service,
            premarket_service=first.premarket_service,
            premarket_artifacts=first.premarket_artifacts,
            clock=clock,
            journal=first_journal,
            projections=first.projections,
            local_paper_settings=settings,
            local_paper_settings_revision=1,
            local_paper_session_id="local-paper-runtime-guarded-replacement",
            start_simulation_streaming=False,
            no_overnight_config=first.no_overnight_controller.config,
            equity_calendar=first.no_overnight_controller.calendar,
            no_overnight_guard=first.no_overnight_guard,
            local_paper_kill_switch=first.kill_switch,
        )
        first.prepare_local_paper_handoff_to(replacement)
        first.execute_prepared_local_paper_handoff(
            first.commit_local_paper_handoff
        )
        assert first.no_overnight_guard is None
        assert replacement.no_overnight_guard is not None
        assert replacement.no_overnight_guard.is_owned_and_healthy() is True
        old_records = first_journal.records(first.local_paper_commands.session_id)
        with pytest.raises(SimulationStateError, match="RUNTIME_REPLACED"):
            first.local_paper_commands.submit_order(
                symbol="3231",
                side="BUY",
                lots=1,
                limit_price="106",
                idempotency_key=f"revoked-old-runtime:{settings.schema_version}",
            )
        assert (
            first_journal.records(first.local_paper_commands.session_id)
            == old_records
        )
    finally:
        first.close()
        if replacement is not None:
            replacement.close()
        first_connection.close()
        second_connection.close()
        second_provider.close()

    restarted_connection = psycopg.connect(no_overnight_postgres_dsn)
    restarted = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=PostgresJournalRepository(
            restarted_connection,
            database_url=no_overnight_postgres_dsn,
        ),
        local_paper_settings=settings,
        start_simulation_streaming=False,
    )
    try:
        assert restarted.no_overnight_guard is not None
        assert restarted.no_overnight_guard.is_owned_and_healthy() is True
    finally:
        restarted.close()
        restarted_connection.close()


def test_postgres_runtime_without_explicit_guard_dsn_fails_closed(
    no_overnight_postgres_dsn: str,
) -> None:
    connection = psycopg.connect(no_overnight_postgres_dsn)
    journal = PostgresJournalRepository(connection)
    counts_before = _journal_counts(connection)

    try:
        with pytest.raises(ValueError, match="requires an explicit database_url"):
            RuntimeComposition.create(
                MockProvider(),
                clock=_FixedClock(
                    datetime.fromisoformat("2026-08-24T09:05:00+08:00")
                ),
                journal=journal,
                start_simulation_streaming=False,
            )
        assert _journal_counts(connection) == counts_before
    finally:
        connection.close()


def test_missing_journal_dsn_cannot_borrow_persistence_config_before_mutation(
    no_overnight_postgres_dsn: str,
) -> None:
    connection = psycopg.connect(no_overnight_postgres_dsn)
    journal = PostgresJournalRepository(connection)
    counts_before = _journal_counts(connection)

    try:
        with pytest.raises(ValueError, match="requires an explicit database_url"):
            RuntimeComposition.create(
                MockProvider(),
                clock=_FixedClock(
                    datetime.fromisoformat("2026-08-24T09:05:00+08:00")
                ),
                journal=journal,
                persistence_config=TradingPersistenceConfig(
                    backend=TradingJournalBackend.POSTGRESQL,
                    database_url=no_overnight_postgres_dsn,
                ),
                start_simulation_streaming=False,
            )
        assert _journal_counts(connection) == counts_before
    finally:
        connection.close()


def test_missing_journal_dsn_cannot_borrow_injected_guard_before_mutation(
    no_overnight_postgres_dsn: str,
) -> None:
    connection = psycopg.connect(no_overnight_postgres_dsn)
    journal = PostgresJournalRepository(connection)
    guard = PostgresNoOvernightControllerGuard.connect(
        database_url=no_overnight_postgres_dsn,
        connect_timeout_seconds=5,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )
    counts_before = _journal_counts(connection)

    try:
        with pytest.raises(ValueError, match="requires an explicit database_url"):
            RuntimeComposition.create(
                MockProvider(),
                clock=_FixedClock(
                    datetime.fromisoformat("2026-08-24T09:05:00+08:00")
                ),
                journal=journal,
                no_overnight_guard=guard,
                start_simulation_streaming=False,
            )
        assert _journal_counts(connection) == counts_before
    finally:
        guard.close()
        connection.close()


def test_injected_guard_database_mismatch_fails_before_journal_mutation(
    no_overnight_postgres_dsn: str,
) -> None:
    connection = psycopg.connect(no_overnight_postgres_dsn)
    journal = PostgresJournalRepository(
        connection,
        database_url=no_overnight_postgres_dsn,
    )
    admin = psycopg.connect(no_overnight_postgres_dsn, autocommit=True)
    guard = None

    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(MISMATCH_DATABASE)
                )
            )
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(MISMATCH_DATABASE)
                )
            )
        mismatch_dsn = _dsn_for_database(
            no_overnight_postgres_dsn,
            MISMATCH_DATABASE,
        )
        guard = PostgresNoOvernightControllerGuard.connect(
            database_url=mismatch_dsn,
            connect_timeout_seconds=5,
            account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        )
        counts_before = _journal_counts(connection)
        with pytest.raises(
            ValueError,
            match="guard database identity conflicts with Journal",
        ) as caught:
            RuntimeComposition.create(
                MockProvider(),
                clock=_FixedClock(
                    datetime.fromisoformat("2026-08-24T09:05:00+08:00")
                ),
                journal=journal,
                no_overnight_guard=guard,
                start_simulation_streaming=False,
            )
        assert no_overnight_postgres_dsn not in str(caught.value)
        assert mismatch_dsn not in str(caught.value)
        assert _journal_counts(connection) == counts_before
    finally:
        if guard is not None:
            guard.close()
        connection.close()
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(MISMATCH_DATABASE)
                )
            )
        admin.close()


def test_injected_postgres_runtime_rejects_conflicting_guard_dsn_before_mutation(
    no_overnight_postgres_dsn: str,
) -> None:
    connection = psycopg.connect(no_overnight_postgres_dsn)
    journal = PostgresJournalRepository(
        connection,
        database_url=no_overnight_postgres_dsn,
    )
    conflicting_dsn = _dsn_for_database(
        no_overnight_postgres_dsn,
        "tw_intraday_trader_config_conflict_test",
    )
    counts_before = _journal_counts(connection)

    try:
        with pytest.raises(
            ValueError,
            match="conflicts with injected Journal",
        ) as caught:
            RuntimeComposition.create(
                MockProvider(),
                clock=_FixedClock(
                    datetime.fromisoformat("2026-08-24T09:05:00+08:00")
                ),
                journal=journal,
                persistence_config=TradingPersistenceConfig(
                    backend=TradingJournalBackend.POSTGRESQL,
                    database_url=conflicting_dsn,
                ),
                start_simulation_streaming=False,
            )

        assert no_overnight_postgres_dsn not in str(caught.value)
        assert conflicting_dsn not in str(caught.value)
        assert _journal_counts(connection) == counts_before
    finally:
        connection.close()


def test_unhealthy_guard_aborts_handoff_before_archive(
    no_overnight_postgres_dsn: str,
) -> None:
    clock = _FixedClock(datetime.fromisoformat("2026-08-24T09:05:00+08:00"))
    settings = LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())
    connection = psycopg.connect(no_overnight_postgres_dsn)
    journal = PostgresJournalRepository(
        connection,
        database_url=no_overnight_postgres_dsn,
    )
    first = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=journal,
        local_paper_settings=settings,
        start_simulation_streaming=False,
    )
    replacement = RuntimeComposition.create(
        first.provider,
        dashboard_service=first.dashboard_service,
        premarket_service=first.premarket_service,
        premarket_artifacts=first.premarket_artifacts,
        clock=clock,
        journal=journal,
        projections=first.projections,
        local_paper_settings=settings,
        local_paper_settings_revision=1,
        local_paper_session_id="local-paper-runtime-failed-handoff",
        start_simulation_streaming=False,
        no_overnight_config=first.no_overnight_controller.config,
        equity_calendar=first.no_overnight_controller.calendar,
        no_overnight_guard=first.no_overnight_guard,
        local_paper_kill_switch=first.kill_switch,
    )
    old_session_id = first.local_paper_commands.session_id
    old_records = journal.records(old_session_id)
    operation_called = False
    try:
        first.prepare_local_paper_handoff_to(replacement)
        assert first.no_overnight_guard is not None
        first.no_overnight_guard.close()

        def archive_and_commit() -> None:
            nonlocal operation_called
            operation_called = True
            journal.append(
                session_archive_record(
                    session_id=old_session_id,
                    replacement_session_id=(
                        replacement.local_paper_commands.session_id
                    ),
                    replacement_settings_digest=settings.digest,
                    active_order_count=0,
                    position_count=0,
                    occurred_at=clock.now(),
                )
            )
            first.commit_local_paper_handoff()

        with pytest.raises(NoOvernightGuardUnavailable, match="ownership was lost"):
            first.execute_prepared_local_paper_handoff(archive_and_commit)
        first.rollback_local_paper_handoff()

        assert operation_called is False
        assert journal.records(old_session_id) == old_records
        first.local_paper_commands.assert_mutation_allowed()
    finally:
        replacement.close()
        first.close()
        connection.close()
