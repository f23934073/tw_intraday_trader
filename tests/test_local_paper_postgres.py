"""PostgreSQL restart UAT for Local Paper tax and adverse slippage v2."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pytest

from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MockProvider
from runtime.composition import RuntimeComposition
from simulation.settings import LocalPaperSettings
from trading.local_paper import LOCAL_PAPER_PROJECTION_NAME
from trading.migrations import apply_migrations
from trading.postgres_journal import PostgresJournalRepository


psycopg = pytest.importorskip("psycopg")
TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_ID = "local-paper-tax-slippage-postgres-uat"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 26, 10, 0, tzinfo=TAIPEI)

    def now(self) -> datetime:
        return self.value

    def session_date(self) -> date:
        return self.value.date()

    def advance(self) -> datetime:
        self.value += timedelta(seconds=1)
        return self.value


class StreamingMockProvider(MockProvider):
    def __init__(self, clock: MutableClock) -> None:
        super().__init__()
        self._clock = clock
        self._handler = None

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self._handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        self._handler = None

    def emit_book(
        self,
        *,
        bid: str,
        ask: str,
        bid_volume_lots: int,
        ask_volume_lots: int,
    ) -> None:
        assert self._handler is not None
        observed_at = self._clock.advance()
        self._handler(
            RealtimeQuoteUpdate(
                symbol="3231",
                kind="BIDASK",
                exchange_timestamp=observed_at,
                received_at=observed_at,
                bid_price=Decimal(bid),
                ask_price=Decimal(ask),
                bid_volume_lots=bid_volume_lots,
                ask_volume_lots=ask_volume_lots,
            )
        )


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
def local_paper_postgres_dsn(postgres_test_dsn: str) -> str:
    setup = psycopg.connect(postgres_test_dsn)
    try:
        with setup.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = str(cursor.fetchone()[0])
        if not _database_is_disposable(database_name):
            pytest.fail(
                "refusing destructive Local Paper UAT: database name must contain "
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


def _runtime(
    dsn: str,
    *,
    clock: MutableClock,
    settings: LocalPaperSettings,
) -> tuple[RuntimeComposition, object]:
    connection = psycopg.connect(dsn)
    repository = PostgresJournalRepository(connection)
    composition = RuntimeComposition.create(
        StreamingMockProvider(clock),
        journal=repository,
        clock=clock,
        local_paper_settings=settings,
        local_paper_settings_revision=1,
        local_paper_session_id=SESSION_ID,
    )
    return composition, connection


def _wait_for_status(
    composition: RuntimeComposition,
    *,
    order_id: str,
    status: str,
) -> dict[str, object]:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        order = next(
            item
            for item in composition.simulation_service.orders()
            if item["order_id"] == order_id
        )
        if order["status"] == status:
            return order
        sleep(0.01)
    raise AssertionError(f"order {order_id} did not reach {status}")


def _stable_state(composition: RuntimeComposition) -> dict[str, object]:
    session = composition.simulation_service.session()
    orders = sorted(
        composition.simulation_service.orders(),
        key=lambda item: str(item["idempotency_key"]),
    )
    checkpoint = composition.journal.latest_checkpoint(
        SESSION_ID,
        LOCAL_PAPER_PROJECTION_NAME,
    )
    journal_results = composition.journal.records(SESSION_ID)
    journal_session = composition.journal.session(SESSION_ID)
    assert checkpoint is not None
    assert journal_session is not None
    return {
        "settings_digest": journal_session.metadata["settings_digest"],
        "fee_policy_version": journal_session.metadata["fee_policy_version"],
        "slippage_policy_version": journal_session.metadata[
            "slippage_policy_version"
        ],
        "checkpoint_sequence": checkpoint.journal_sequence,
        "checkpoint_digest": checkpoint.digest,
        "journal_kinds": tuple(result.record.kind for result in journal_results),
        "fill_v3_count": sum(
            result.record.kind == "local_paper_fill.v3"
            for result in journal_results
        ),
        "available_cash": session["available_cash"],
        "daily_filled_buy_notional": session["daily_filled_buy_notional"],
        "realized_pnl": session["realized_pnl"],
        "commission_total": session["commission_total"],
        "tax_total": session["tax_total"],
        "slippage_cost_total": session["slippage_cost_total"],
        "positions": composition.simulation_service.positions(),
        "orders": tuple(
            {
                "idempotency_key": order["idempotency_key"],
                "status": order["status"],
                "filled_quantity": order["filled_quantity"],
                "filled_amount_decimal": order["filled_amount_decimal"],
                "filled_commission_decimal": order[
                    "filled_commission_decimal"
                ],
                "filled_tax": order["filled_tax"],
                "filled_slippage_cost": order["filled_slippage_cost"],
                "fill_sequence": order["fill_sequence"],
            }
            for order in orders
        ),
    }


def test_v2_partial_fills_reconstruct_exactly_across_three_new_connections(
    local_paper_postgres_dsn: str,
) -> None:
    dsn = local_paper_postgres_dsn
    clock = MutableClock()
    settings = LocalPaperSettings.v2_from_v1(LocalPaperSettings.defaults())
    first, first_connection = _runtime(dsn, clock=clock, settings=settings)
    provider = first.provider
    assert isinstance(provider, StreamingMockProvider)
    try:
        buy, _ = first.local_paper_commands.submit_order(
            symbol="3231",
            side="BUY",
            quantity_shares=1_500,
            limit_price="100.5",
            idempotency_key="uat-v2-buy",
        )
        provider.emit_book(
            bid="99.5",
            ask="100",
            bid_volume_lots=10,
            ask_volume_lots=1,
        )
        partial_buy = _wait_for_status(
            first,
            order_id=str(buy["order_id"]),
            status="PARTIALLY_FILLED",
        )
        assert partial_buy["filled_quantity"] == 1_000
        provider.emit_book(
            bid="99.5",
            ask="100",
            bid_volume_lots=10,
            ask_volume_lots=1,
        )
        _wait_for_status(
            first,
            order_id=str(buy["order_id"]),
            status="FILLED",
        )

        sell, _ = first.local_paper_commands.submit_order(
            symbol="3231",
            side="SELL",
            quantity_shares=1_500,
            limit_price="109.5",
            idempotency_key="uat-v2-sell",
        )
        provider.emit_book(
            bid="110",
            ask="110.5",
            bid_volume_lots=1,
            ask_volume_lots=10,
        )
        partial_sell = _wait_for_status(
            first,
            order_id=str(sell["order_id"]),
            status="PARTIALLY_FILLED",
        )
        assert partial_sell["filled_quantity"] == 1_000
        provider.emit_book(
            bid="110",
            ask="110.5",
            bid_volume_lots=1,
            ask_volume_lots=10,
        )
        _wait_for_status(
            first,
            order_id=str(sell["order_id"]),
            status="FILLED",
        )
        expected = _stable_state(first)
    finally:
        first.close()
        first_connection.close()

    assert expected["fill_v3_count"] == 4
    assert expected["available_cash"] == 10_012_560.0
    assert expected["daily_filled_buy_notional"] == 150_750.0
    assert Decimal(str(expected["realized_pnl"])) == Decimal("12560")
    assert Decimal(str(expected["commission_total"])) == Decimal("448")
    assert Decimal(str(expected["tax_total"])) == Decimal("492")
    assert Decimal(str(expected["slippage_cost_total"])) == Decimal("1500")
    assert expected["positions"] == []

    for _ in range(3):
        restored, connection = _runtime(dsn, clock=clock, settings=settings)
        try:
            assert _stable_state(restored) == expected
        finally:
            restored.close()
            connection.close()

    order_state_corruption = psycopg.connect(dsn)
    try:
        with order_state_corruption.cursor() as cursor:
            cursor.execute(
                """
                UPDATE trading.journal_records
                SET payload_json = jsonb_set(
                    payload_json,
                    '{filled_tax}',
                    to_jsonb('999'::text)
                )
                WHERE session_id = %s
                  AND kind = 'local_paper_order_state.v1'
                  AND payload_json->>'idempotency_key' = 'uat-v2-sell'
                  AND payload_json->>'status' = 'FILLED'
                """,
                (SESSION_ID,),
            )
            assert cursor.rowcount == 1
        order_state_corruption.commit()
    finally:
        order_state_corruption.close()

    bad_order_state_connection = psycopg.connect(dsn)
    try:
        with pytest.raises(ValueError, match="order state integrity"):
            RuntimeComposition.create(
                StreamingMockProvider(clock),
                journal=PostgresJournalRepository(bad_order_state_connection),
                clock=clock,
                local_paper_settings=settings,
                local_paper_settings_revision=1,
                local_paper_session_id=SESSION_ID,
            )
    finally:
        bad_order_state_connection.close()

    order_state_restore = psycopg.connect(dsn)
    try:
        with order_state_restore.cursor() as cursor:
            cursor.execute(
                """
                UPDATE trading.journal_records
                SET payload_json = jsonb_set(
                    payload_json,
                    '{filled_tax}',
                    to_jsonb('492'::text)
                )
                WHERE session_id = %s
                  AND kind = 'local_paper_order_state.v1'
                  AND payload_json->>'idempotency_key' = 'uat-v2-sell'
                  AND payload_json->>'status' = 'FILLED'
                """,
                (SESSION_ID,),
            )
            assert cursor.rowcount == 1
        order_state_restore.commit()
    finally:
        order_state_restore.close()

    corruption = psycopg.connect(dsn)
    try:
        with corruption.cursor() as cursor:
            cursor.execute(
                """
                UPDATE trading.journal_records
                SET payload_json = jsonb_set(payload_json, '{tax}', '491'::jsonb)
                WHERE session_id = %s
                  AND kind = 'local_paper_fill.v3'
                  AND payload_json->>'side' = 'SELL'
                  AND payload_json->>'fill_sequence' = '2'
                """,
                (SESSION_ID,),
            )
            assert cursor.rowcount == 1
        corruption.commit()
    finally:
        corruption.close()

    bad_connection = psycopg.connect(dsn)
    try:
        with pytest.raises(ValueError, match="invalid local-paper fill"):
            RuntimeComposition.create(
                StreamingMockProvider(clock),
                journal=PostgresJournalRepository(bad_connection),
                clock=clock,
                local_paper_settings=settings,
                local_paper_settings_revision=1,
                local_paper_session_id=SESSION_ID,
            )
    finally:
        bad_connection.close()
