"""Destructive PostgreSQL restart UAT for the Local Paper Kill Switch."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import os
from zoneinfo import ZoneInfo

import pytest

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from simulation.continuous_strategy import (
    AutomatedStrategyConfig,
    ContinuousPaperStrategyController,
)
from simulation.kill_switch import (
    KillSwitchAdmissionBlocked,
    KillSwitchPersistenceUnavailable,
    KillSwitchStateConflict,
)
from trading.kill_switch import (
    KILL_SWITCH_CONTRACT_VERSION,
    KILL_SWITCH_CONTROL_SESSION_ID,
    KILL_SWITCH_EXECUTION_BOUNDARY,
    KILL_SWITCH_IDEMPOTENCY_SCOPE,
    KillSwitchOperationConflict,
)
from trading.migrations import apply_migrations
from trading.postgres_journal import PostgresJournalRepository


psycopg = pytest.importorskip("psycopg")
TAIPEI = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 8, 26, 10, 0, tzinfo=TAIPEI)


class FixedClock:
    def now(self) -> datetime:
        return NOW

    def session_date(self) -> date:
        return NOW.date()


def _reset_trading_schema(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP SCHEMA IF EXISTS trading CASCADE;
            DROP TABLE IF EXISTS public.projection_checkpoints,
            public.journal_records, public.journal_sessions,
            public.journal_schema_migrations CASCADE
            """
        )
    connection.commit()


def _database_is_disposable(database_name: str) -> bool:
    normalized = database_name.strip().lower().replace("-", "_")
    explicit_reset = os.getenv("ALLOW_POSTGRES_TEST_SCHEMA_RESET", "").strip() == "1"
    return "test" in normalized.split("_") or explicit_reset


@pytest.fixture()
def kill_switch_postgres_dsn(postgres_test_dsn: str) -> str:
    setup = psycopg.connect(postgres_test_dsn)
    try:
        with setup.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = str(cursor.fetchone()[0])
        if not _database_is_disposable(database_name):
            pytest.fail(
                "refusing destructive Kill Switch UAT: database name must contain "
                "a standalone 'test' token or ALLOW_POSTGRES_TEST_SCHEMA_RESET=1"
            )
        _reset_trading_schema(setup)
        assert apply_migrations(setup) == (
            "001_journal.sql",
            "002_trading_schema.sql",
        )
    finally:
        setup.close()
    try:
        yield postgres_test_dsn
    finally:
        cleanup = psycopg.connect(postgres_test_dsn)
        try:
            _reset_trading_schema(cleanup)
        finally:
            cleanup.close()


def _runtime(dsn: str, *, session_id: str):
    connection = psycopg.connect(dsn)
    repository = PostgresJournalRepository(connection, database_url=dsn)
    composition = RuntimeComposition.create(
        MockProvider(),
        journal=repository,
        clock=FixedClock(),
        local_paper_session_id=session_id,
        start_simulation_streaming=False,
    )
    return composition, connection


def _controller(composition: RuntimeComposition) -> ContinuousPaperStrategyController:
    return ContinuousPaperStrategyController(
        flow=composition.strategy_paper_flow,
        projection_reader=composition.simulation_service.projection,
        signal_reader=lambda: {"status": "unavailable", "items": []},
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        clock=composition.clock,
        kill_switch=composition.kill_switch,
    )


def _start_config() -> AutomatedStrategyConfig:
    return AutomatedStrategyConfig.create(
        stop_loss_pct="1.5",
        take_profit_pct="3",
        max_daily_loss="50000",
    )


def test_postgresql_restart_rotation_concurrency_and_failure_injection(
    kill_switch_postgres_dsn: str,
) -> None:
    dsn = kill_switch_postgres_dsn

    process_a, connection_a = _runtime(dsn, session_id="kill-switch-uat-session-a")
    try:
        engaged = process_a.kill_switch.engage(
            actor_id="uat-operator",
            operation_id="uat-engage-a",
            reason="Process A engage",
        )
        assert engaged["kill_switch"]["control_state"] == "ENGAGED"
        assert engaged["kill_switch"]["revision"] == 1
        assert engaged["kill_switch"]["durability"] == "POSTGRESQL"
        assert engaged["kill_switch"]["restart_safe"] is True
    finally:
        process_a.close()
        connection_a.close()

    process_b, connection_b = _runtime(dsn, session_id="kill-switch-uat-session-a")
    try:
        controller_b = _controller(process_b)
        first_status = controller_b.status()
        assert first_status["state"] == "KILLED"
        assert first_status["kill_switch"]["control_state"] == "ENGAGED"
        assert first_status["kill_switch"]["revision"] == 1
        assert first_status["kill_switch"]["recovered"] is True
        with pytest.raises(KillSwitchAdmissionBlocked):
            controller_b.start(_start_config(), background=False)

        retry = process_b.kill_switch.engage(
            actor_id="uat-operator",
            operation_id="uat-engage-a",
            reason="Process A engage",
        )
        assert retry["operation"]["idempotent"] is True
        assert retry["operation"]["operation_revision"] == 1
        with pytest.raises(KillSwitchOperationConflict):
            process_b.kill_switch.engage(
                actor_id="uat-operator",
                operation_id="uat-engage-a",
                reason="conflicting retry",
            )

        def reaffirm(operation_id: str) -> dict:
            return process_b.kill_switch.engage(
                actor_id="uat-operator",
                operation_id=operation_id,
                reason=f"concurrent reaffirm {operation_id}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent = list(
                executor.map(reaffirm, ("uat-reaffirm-1", "uat-reaffirm-2"))
            )
        assert sorted(item["operation"]["operation_revision"] for item in concurrent) == [
            2,
            3,
        ]
        assert process_b.kill_switch.status()["revision"] == 3

        with pytest.raises(KillSwitchStateConflict, match="revision is stale"):
            process_b.kill_switch.reset(
                actor_id="uat-operator",
                operation_id="uat-stale-reset",
                expected_revision=1,
                reason="stale browser",
            )
        reset = process_b.kill_switch.reset(
            actor_id="uat-operator",
            operation_id="uat-valid-reset",
            expected_revision=3,
            reason="review complete",
        )
        assert reset["kill_switch"]["control_state"] == "DISENGAGED"
        assert reset["kill_switch"]["revision"] == 4
    finally:
        process_b.close()
        connection_b.close()

    process_c, connection_c = _runtime(dsn, session_id="kill-switch-uat-session-a")
    rotated: RuntimeComposition | None = None
    try:
        controller_c = _controller(process_c)
        first_status = controller_c.status()
        assert first_status["state"] == "STOPPED"
        assert first_status["kill_switch"]["control_state"] == "DISENGAGED"
        assert first_status["kill_switch"]["revision"] == 4
        assert first_status["kill_switch"]["recovered"] is True

        rotated = RuntimeComposition.create(
            process_c.provider,
            journal=process_c.journal,
            clock=process_c.clock,
            local_paper_session_id="kill-switch-uat-session-rotated",
            local_paper_settings_revision=1,
            start_simulation_streaming=False,
            no_overnight_config=process_c.no_overnight_controller.config,
            equity_calendar=process_c.no_overnight_controller.calendar,
            no_overnight_guard=process_c.no_overnight_guard,
            local_paper_kill_switch=process_c.kill_switch,
        )
        process_c.prepare_local_paper_handoff_to(rotated)
        process_c.execute_prepared_local_paper_handoff(
            process_c.commit_local_paper_handoff
        )
        assert rotated.local_paper_commands.session_id == (
            "kill-switch-uat-session-rotated"
        )
        assert rotated.kill_switch.status()["control_state"] == "DISENGAGED"
        assert rotated.kill_switch.status()["revision"] == 4
        assert rotated.kill_switch is process_c.kill_switch

        connection_c.close()
        with pytest.raises(
            KillSwitchPersistenceUnavailable,
            match="Journal append failed",
        ):
            rotated.kill_switch.engage(
                actor_id="uat-operator",
                operation_id="uat-db-failure",
                reason="closed connection injection",
            )
        assert rotated.kill_switch.status()["control_state"] == "RECOVERY_REQUIRED"
    finally:
        if rotated is not None:
            rotated.close()
        process_c.close()
        if not connection_c.closed:
            connection_c.close()

    corruption = psycopg.connect(dsn)
    try:
        payload = {
            "contract_version": KILL_SWITCH_CONTRACT_VERSION,
            "action": "ENGAGE",
            "operation_id": "uat-corrupt-gap",
            "actor_id": "uat-corruption-injection",
            "reason": "revision gap",
            "prior_revision": 8,
            "revision": 9,
            "resulting_state": "ENGAGED",
            "execution_boundary": KILL_SWITCH_EXECUTION_BOUNDARY,
        }
        with corruption.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO trading.journal_records (
                    session_id, record_id, kind, occurred_at, payload_json,
                    idempotency_scope, idempotency_key, schema_version, fingerprint
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    KILL_SWITCH_CONTROL_SESSION_ID,
                    "local-paper-kill-switch:uat-corrupt-gap",
                    "local_paper_kill_switch_engaged.v1",
                    NOW,
                    psycopg.types.json.Jsonb(payload),
                    KILL_SWITCH_IDEMPOTENCY_SCOPE,
                    "uat-corrupt-gap",
                    "journal-v1",
                    "intentional-uat-corruption",
                ),
            )
        corruption.commit()
    finally:
        corruption.close()

    process_d, connection_d = _runtime(dsn, session_id="kill-switch-uat-session-a")
    try:
        status_d = _controller(process_d).status()
        assert status_d["state"] == "KILLED"
        assert status_d["decision"] == "KILL_SWITCH_RECOVERY_REQUIRED"
        assert status_d["kill_switch"]["control_state"] == "RECOVERY_REQUIRED"
        with pytest.raises(
            KillSwitchPersistenceUnavailable,
            match="recovery is required",
        ):
            process_d.kill_switch.assert_start_allowed()
    finally:
        process_d.close()
        connection_d.close()
