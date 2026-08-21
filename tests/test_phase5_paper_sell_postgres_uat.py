"""Real PostgreSQL restart-recovery acceptance for Phase 5 paper UAT."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from zoneinfo import ZoneInfo

import pytest

from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from trading.migrations import apply_migrations
from trading.postgres_journal import PostgresJournalRepository


TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_DSN,
    reason="requires explicit TEST_POSTGRES_DSN",
)
TAIPEI = ZoneInfo("Asia/Taipei")


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 21, 10, 30, tzinfo=TAIPEI)

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()


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


def _runtime(dsn: str, clock: MutableClock):
    connection = psycopg.connect(dsn)
    repository = PostgresJournalRepository(connection)
    composition = RuntimeComposition.create(
        MockProvider(),
        clock=clock,
        journal=repository,
    )
    return composition, connection


@pytest.fixture()
def postgres_uat_dsn():
    assert TEST_POSTGRES_DSN is not None
    setup = psycopg.connect(TEST_POSTGRES_DSN)
    try:
        _reset_trading_schema(setup)
        assert apply_migrations(setup) == (
            "001_journal.sql",
            "002_trading_schema.sql",
        )
    finally:
        setup.close()
    try:
        yield TEST_POSTGRES_DSN
    finally:
        cleanup = psycopg.connect(TEST_POSTGRES_DSN)
        try:
            _reset_trading_schema(cleanup)
        finally:
            cleanup.close()


def test_postgresql_restart_restores_orders_positions_reservations_and_alerts(
    postgres_uat_dsn,
) -> None:
    dsn = str(postgres_uat_dsn)
    clock = MutableClock()

    first, first_connection = _runtime(dsn, clock)
    try:
        filled, _ = first.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="106",
            idempotency_key="phase5-postgres-filled-buy",
        )
        pending, _ = first.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="100",
            idempotency_key="phase5-postgres-pending-buy",
        )
        assert filled["status"] == "FILLED"
        assert pending["status"] == "PENDING"
        assert first.simulation_service.positions()[0]["quantity"] == 1_000
        assert first.simulation_service.session()["reserved_cash"] == 100_000.0
    finally:
        first.close()
        first_connection.close()

    second, second_connection = _runtime(dsn, clock)
    try:
        restored_pending = next(
            order
            for order in second.simulation_service.orders()
            if order["idempotency_key"] == "phase5-postgres-pending-buy"
        )
        repeated, idempotent = second.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            lots=1,
            limit_price="100",
            idempotency_key="phase5-postgres-pending-buy",
        )
        assert restored_pending["status"] == "PENDING"
        assert repeated["order_id"] == restored_pending["order_id"]
        assert idempotent is True
        assert second.simulation_service.positions()[0]["quantity"] == 1_000
        assert second.simulation_service.session()["reserved_cash"] == 100_000.0

        clock.value += timedelta(seconds=31)
        second.simulation_service.reconcile_orders()
        cancelled = next(
            order
            for order in second.simulation_service.orders()
            if order["order_id"] == restored_pending["order_id"]
        )
        assert cancelled["status"] == "CANCELLED"
        assert cancelled["reason"] == "ORDER_TIMEOUT"
        assert second.simulation_service.session()["reserved_cash"] == 0.0
        assert second.simulation_service.alerts()[0]["code"] == (
            "ORDER_TIMEOUT_CANCELLED"
        )
    finally:
        second.close()
        second_connection.close()

    third, third_connection = _runtime(dsn, clock)
    try:
        recovered_cancel = next(
            order
            for order in third.simulation_service.orders()
            if order["idempotency_key"] == "phase5-postgres-pending-buy"
        )
        assert recovered_cancel["status"] == "CANCELLED"
        assert third.simulation_service.positions()[0]["quantity"] == 1_000
        assert third.simulation_service.session()["reserved_cash"] == 0.0
        assert third.simulation_service.alerts()[0]["code"] == (
            "ORDER_TIMEOUT_CANCELLED"
        )
    finally:
        third.close()
        third_connection.close()
