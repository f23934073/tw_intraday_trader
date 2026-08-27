from datetime import date, datetime, time
from threading import Event, Thread

import pytest

import runtime.composition as composition_module
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_POLICY_FAMILY,
)
from config.no_overnight import (
    NoOvernightDeploymentManifest,
    NoOvernightMode,
    NoOvernightPolicyConfig,
)
from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from runtime.in_memory import InMemoryJournalRepository
from runtime.trading_persistence import TradingPersistenceUnavailable
from runtime.no_overnight_guard import (
    NoOvernightGuardUnavailable,
    PostgresNoOvernightControllerGuard,
    advisory_lock_key,
    no_overnight_guard_identity,
)
from simulation.settings import LocalPaperSettings


class _Cursor:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._identity_pending = False

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query, parameters=None) -> None:
        if "pg_postmaster_start_time()" in query:
            self._identity_pending = True
            return
        self._connection.queries.append((query, parameters))

    def fetchone(self):
        if self._identity_pending:
            self._identity_pending = False
            return (
                "tw_intraday_trader_test",
                "16384",
                datetime.fromisoformat("2026-08-27T00:00:00+00:00"),
                "127.0.0.1",
                "5432",
            )
        return self._connection.rows.pop(0)


class _Connection:
    def __init__(self, rows) -> None:
        self.rows = list(rows)
        self.queries = []
        self.closed = False

    def cursor(self):
        return _Cursor(self)

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        return None


class _Clock:
    def __init__(self) -> None:
        self.value = datetime.fromisoformat("2026-08-24T13:09:00+08:00")

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


class _CompositionGuard:
    guard_identity = no_overnight_guard_identity(
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )

    def __init__(self) -> None:
        self.owned = False
        self.closed = False

    def acquire(self) -> None:
        self.owned = True

    def is_owned_and_healthy(self) -> bool:
        return self.owned and not self.closed

    def execute_if_owned(self, operation):
        if not self.is_owned_and_healthy():
            raise ValueError("guard ownership was lost")
        return operation()

    def close(self) -> None:
        self.closed = True
        self.owned = False


def _guard(connection: _Connection) -> PostgresNoOvernightControllerGuard:
    return PostgresNoOvernightControllerGuard(
        connection=connection,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
    )


def _config() -> NoOvernightPolicyConfig:
    return NoOvernightPolicyConfig(
        mode=NoOvernightMode.ENFORCING,
        account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
        policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
        policy_version="enforcing-v1",
        timezone="Asia/Taipei",
        market_open=time(9, 0),
        no_new_entry_at=time(13, 10),
        cancel_entry_at=time(13, 15),
        flatten_at=time(13, 20),
        aggressive_exit_at=time(13, 25),
        final_reconciliation_at=time(13, 28),
        reviewed_session_close=time(13, 30),
        max_exit_attempts=3,
        retry_cooldown_seconds=10,
        executable_book_policy_id="local-paper-book-v1",
    )


def test_postgres_guard_uses_nonblocking_lock_and_held_connection_health() -> None:
    connection = _Connection([(True,), (1,), (True,)])
    guard = _guard(connection)

    guard.acquire()

    assert guard.is_owned_and_healthy() is True
    assert connection.queries[0][0] == "SELECT pg_try_advisory_lock(%s)"
    assert connection.queries[1][0] == "SELECT 1"
    guard.close()
    assert connection.queries[2][0] == "SELECT pg_advisory_unlock(%s)"
    assert connection.closed is True


def test_guard_close_waits_for_owned_mutation_boundary() -> None:
    connection = _Connection([(True,), (1,), (True,)])
    guard = _guard(connection)
    guard.acquire()
    entered = Event()
    release = Event()
    operation_done = Event()
    close_started = Event()
    close_done = Event()

    def operation() -> None:
        entered.set()
        assert release.wait(1.0)

    def run_operation() -> None:
        guard.execute_if_owned(operation)
        operation_done.set()

    def close_guard() -> None:
        close_started.set()
        guard.close()
        close_done.set()

    operation_thread = Thread(target=run_operation)
    operation_thread.start()
    assert entered.wait(1.0)
    close_thread = Thread(target=close_guard)
    close_thread.start()
    assert close_started.wait(1.0)

    assert close_done.wait(0.05) is False
    release.set()
    operation_thread.join(1.0)
    close_thread.join(1.0)

    assert operation_done.is_set()
    assert close_done.is_set()
    assert connection.closed is True


def test_duplicate_postgres_guard_owner_is_rejected() -> None:
    connection = _Connection([(False,)])

    with pytest.raises(NoOvernightGuardUnavailable, match="already owned"):
        _guard(connection).acquire()

    assert connection.closed is True


def test_guard_key_is_stable_and_scope_specific() -> None:
    first = advisory_lock_key(
        account_scope_id="scope-a",
        policy_family_id="family-a",
    )
    repeated = advisory_lock_key(
        account_scope_id="scope-a",
        policy_family_id="family-a",
    )
    changed = advisory_lock_key(
        account_scope_id="scope-b",
        policy_family_id="family-a",
    )

    assert first == repeated
    assert first != changed
    assert -(2**63) <= first < 2**63
    assert no_overnight_guard_identity(
        account_scope_id="scope-a",
        policy_family_id="family-a",
    ).endswith(f":{first}")


def test_single_worker_manifest_rejects_multiple_workers() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        NoOvernightDeploymentManifest(
            source="pytest",
            process_count=1,
            workers_per_process=2,
        )
    with pytest.raises(ValueError, match="exactly one"):
        NoOvernightDeploymentManifest(
            source="pytest",
            process_count=True,
            workers_per_process=1,
        )


def test_enforcing_refuses_memory_backend_before_runtime_construction() -> None:
    manifest = NoOvernightDeploymentManifest(
        source="pytest",
        process_count=1,
        workers_per_process=1,
    )

    with pytest.raises(ValueError, match="PostgreSQL Journal"):
        RuntimeComposition.create(
            MockProvider(),
            no_overnight_config=_config(),
            no_overnight_deployment_manifest=manifest,
        )


def test_postgres_startup_failure_never_falls_back_and_emits_critical_alert(
    monkeypatch,
    caplog,
) -> None:
    calls = 0

    def unavailable(_config):
        nonlocal calls
        calls += 1
        raise TradingPersistenceUnavailable("PostgreSQL Journal initialization failed")

    monkeypatch.setattr(composition_module, "build_journal_repository", unavailable)
    with caplog.at_level("CRITICAL"):
        with pytest.raises(
            TradingPersistenceUnavailable,
            match="initialization failed",
        ):
            RuntimeComposition.create(
                MockProvider(),
                persistence_config=TradingPersistenceConfig(
                    backend=TradingJournalBackend.POSTGRESQL,
                    database_url="postgresql://unit-test.invalid/test",
                ),
                no_overnight_config=_config(),
                no_overnight_deployment_manifest=NoOvernightDeploymentManifest(
                    source="pytest",
                    process_count=1,
                    workers_per_process=1,
                ),
            )

    assert calls == 1
    alert = next(
        record
        for record in caplog.records
        if record.getMessage() == "no_overnight_startup_failed"
    )
    assert alert.levelname == "CRITICAL"
    assert alert.event == "NO_OVERNIGHT_STARTUP_FAILED"
    assert alert.mode == "ENFORCING"


def test_enforcing_composition_owns_worker_until_close(monkeypatch) -> None:
    journal = InMemoryJournalRepository()
    guard = _CompositionGuard()
    monkeypatch.setattr(
        composition_module,
        "build_journal_repository",
        lambda _config: journal,
    )
    monkeypatch.setattr(
        composition_module.PostgresNoOvernightControllerGuard,
        "connect",
        lambda **_kwargs: guard,
    )
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=_Clock(),
        persistence_config=TradingPersistenceConfig(
            backend=TradingJournalBackend.POSTGRESQL,
            database_url="postgresql://unit-test.invalid/test",
        ),
        local_paper_settings=LocalPaperSettings.v2_from_v1(
            LocalPaperSettings.defaults()
        ),
        no_overnight_config=_config(),
        no_overnight_deployment_manifest=NoOvernightDeploymentManifest(
            source="pytest",
            process_count=1,
            workers_per_process=1,
        ),
    )
    worker = composition.no_overnight_worker

    assert worker is not None
    assert worker.status()["running"] is True
    assert guard.is_owned_and_healthy() is True

    composition.close()

    assert worker.status()["running"] is False
    assert guard.closed is True
