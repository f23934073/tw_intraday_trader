from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pytest

from market_data.models import RealtimeQuoteUpdate
from market_data.provider import MarketDataProvider, MockProvider
from simulation.service import SimulationService, SimulationValidationError
from trading.journal import InMemoryJournalRepository, JournalSession
from trading.local_paper import (
    LOCAL_PAPER_FILL_V3_KIND,
    LocalPaperFill,
    LocalPaperProjection,
    ProjectionRecoveryError,
    journal_record_from_simulation_order,
    latest_local_paper_order_states,
    order_state_record_from_simulation_order,
)


TAIPEI = ZoneInfo("Asia/Taipei")
AT = datetime(2026, 8, 26, 10, 0, tzinfo=TAIPEI)
SETTINGS_DIGEST = "d" * 64


class PriceProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self._raw = {symbol: dict(value) for symbol, value in self._raw.items()}

    def set_price(self, price: str) -> None:
        self._raw["3231"]["price"] = Decimal(price)


class StreamingPriceProvider(PriceProvider):
    def __init__(self) -> None:
        super().__init__()
        self.handler = None

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(self, handler) -> None:
        self.handler = handler

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        return set(symbols)

    def stop_quote_stream(self) -> None:
        return None

    def emit_book(
        self,
        *,
        bid: str,
        ask: str,
        bid_volume_lots: int = 1,
        ask_volume_lots: int = 1,
        observed_at: datetime | None = None,
    ) -> None:
        assert self.handler is not None
        observed_at = observed_at or datetime.now(TAIPEI)
        self.handler(
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


def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("quote worker did not reach expected state")


def v2_service(provider: MarketDataProvider, starting_cash: str = "100000") -> SimulationService:
    return SimulationService(
        provider,
        starting_cash=Decimal(starting_cash),
        max_daily_buy_notional=Decimal("1000000"),
        slippage_bps=Decimal("5"),
        cost_policy_enabled=True,
    )


def golden_orders() -> tuple[SimulationService, dict, dict]:
    provider = PriceProvider()
    provider.set_price("100")
    service = v2_service(provider)
    buy, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=100,
        limit_price="100.5",
        idempotency_key="v2-golden-buy",
    )
    provider.set_price("110")
    sell, _ = service.submit_order(
        symbol="3231",
        side="SELL",
        quantity_shares=100,
        limit_price="109.5",
        idempotency_key="v2-golden-sell",
    )
    return service, buy, sell


def test_snapshot_v2_golden_buy_sell_tax_cash_and_pnl() -> None:
    service, buy, sell = golden_orders()

    assert buy["filled_price"] == 100.5
    assert buy["last_reference_price"] == "100"
    assert buy["last_reference_source"] == "SNAPSHOT_COMPATIBILITY"
    assert buy["last_fill_commission_decimal"] == "20"
    assert buy["last_fill_tax"] == "0"
    assert buy["last_net_cash_effect"] == "-10070.0"
    assert sell["filled_price"] == 109.5
    assert sell["last_fill_commission_decimal"] == "20"
    assert sell["last_fill_tax"] == "32"
    assert sell["last_net_cash_effect"] == "10898.0"
    assert Decimal(str(service.session()["available_cash"])) == Decimal("100828.0")
    assert service.risk_snapshot("3231")["daily_realized_pnl"] == Decimal("828.0")
    assert service.positions() == []


def test_fill_v3_round_trip_replays_persisted_monetary_truth_three_times() -> None:
    _service, buy, sell = golden_orders()
    records = [
        journal_record_from_simulation_order(
            order,
            session_id="v3-replay",
            settings_digest=SETTINGS_DIGEST,
        )
        for order in (buy, sell)
    ]
    assert all(record is not None for record in records)
    assert [record.kind for record in records if record is not None] == [
        LOCAL_PAPER_FILL_V3_KIND,
        LOCAL_PAPER_FILL_V3_KIND,
    ]
    buy_record, sell_record = records
    assert buy_record is not None and sell_record is not None
    assert sell_record.payload["tax"] == "32"
    assert sell_record.payload["gross_amount"] == "10950"
    assert sell_record.payload["net_cash_effect"] == "10898"
    assert sell_record.payload["fee_policy_version"] == "tw_stock_standard_v1"

    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id="v3-replay",
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"settings_digest": SETTINGS_DIGEST},
        )
    )
    journal.append(buy_record)
    journal.append(sell_record)
    digests = []
    for _ in range(3):
        projection = LocalPaperProjection(
            starting_cash=Decimal("100000"),
            settings_digest=SETTINGS_DIGEST,
        )
        for result in journal.records("v3-replay"):
            projection.apply(result)
        assert projection.cash == Decimal("100828")
        assert projection.realized_pnl("3231") == Decimal("828")
        assert projection.position("3231") is None
        digests.append(projection.digest)
    assert len(set(digests)) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tax", "31"),
        ("net_cash_effect", "10899"),
        ("reference_price", "109.5"),
        ("fee_policy_version", "tampered"),
        ("instrument_descriptor_digest", "0" * 64),
        ("limit_price", "110"),
    ],
)
def test_fill_v3_tampering_fails_closed(field: str, value: object) -> None:
    _service, _buy, sell = golden_orders()
    record = journal_record_from_simulation_order(
        sell,
        session_id="tamper",
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    payload = dict(record.payload)
    payload[field] = value

    with pytest.raises(ProjectionRecoveryError, match="invalid local-paper fill"):
        LocalPaperFill.from_record(replace(record, payload=payload))


def test_fill_v3_rejects_missing_tax_evidence() -> None:
    _service, _buy, sell = golden_orders()
    record = journal_record_from_simulation_order(
        sell,
        session_id="missing-tax",
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    payload = dict(record.payload)
    del payload["tax"]
    payload["net_cash_effect"] = "10930"

    with pytest.raises(ProjectionRecoveryError, match="invalid local-paper fill"):
        LocalPaperFill.from_record(replace(record, payload=payload))


def test_fill_v3_rejects_coherent_tax_and_net_tampering() -> None:
    _service, _buy, sell = golden_orders()
    record = journal_record_from_simulation_order(
        sell,
        session_id="coherent-tax-tamper",
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    payload = {
        **record.payload,
        "tax": "31",
        "net_cash_effect": "10899",
    }

    with pytest.raises(ProjectionRecoveryError, match="invalid local-paper fill"):
        LocalPaperFill.from_record(replace(record, payload=payload))


def test_fill_v3_rejects_coherent_commission_and_net_tampering() -> None:
    _service, buy, _sell = golden_orders()
    record = journal_record_from_simulation_order(
        buy,
        session_id="coherent-commission-tamper",
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    payload = {
        **record.payload,
        "commission": "21",
        "cumulative_order_commission": "21",
        "net_cash_effect": "-10071",
    }

    with pytest.raises(ProjectionRecoveryError, match="invalid local-paper fill"):
        LocalPaperFill.from_record(replace(record, payload=payload))


def test_fill_v3_rejects_coherent_reference_diagnostic_tampering() -> None:
    _service, _buy, sell = golden_orders()
    record = journal_record_from_simulation_order(
        sell,
        session_id="coherent-reference-tamper",
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    payload = {
        **record.payload,
        "reference_price": "109.5",
        "realized_slippage_bps": "0",
        "slippage_cost": "0",
    }

    with pytest.raises(ProjectionRecoveryError, match="invalid local-paper fill"):
        LocalPaperFill.from_record(replace(record, payload=payload))


@pytest.mark.parametrize("remove_digest", [False, True])
def test_v2_order_state_integrity_fails_closed_for_tamper_or_missing_digest(
    remove_digest: bool,
) -> None:
    _service, _buy, sell = golden_orders()
    record = order_state_record_from_simulation_order(
        sell,
        session_id="order-state-integrity",
    )
    payload = dict(record.payload)
    if remove_digest:
        payload.pop("order_state_digest", None)
    else:
        payload["filled_tax"] = "999"
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id="order-state-integrity",
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"settings_digest": SETTINGS_DIGEST},
        )
    )
    journal.append(replace(record, payload=payload))

    with pytest.raises(ProjectionRecoveryError, match="order state integrity"):
        latest_local_paper_order_states(
            journal,
            session_id="order-state-integrity",
            require_integrity=True,
        )


def test_stream_limit_miss_does_not_consume_best_level_volume() -> None:
    provider = StreamingPriceProvider()
    service = v2_service(provider, starting_cash="500000")
    missed, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=1_000,
        limit_price="100",
        idempotency_key="slippage-limit-miss",
    )
    assert missed["status"] == "PENDING"

    provider.emit_book(bid="99.5", ask="100")
    wait_until(
        lambda: service.orders()[0]["waiting_reason"]
        == "SLIPPAGE_ADJUSTED_LIMIT_NOT_REACHED"
    )
    executable, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=1_000,
        limit_price="100.5",
        idempotency_key="slippage-limit-hit",
    )

    assert executable["status"] == "FILLED"
    assert executable["filled_quantity"] == 1_000
    assert service.order_for_idempotency_key("slippage-limit-miss")["status"] == "PENDING"
    service.close()


def test_duplicate_book_timestamp_does_not_replenish_consumed_volume() -> None:
    provider = StreamingPriceProvider()
    service = v2_service(provider, starting_cash="500000")
    submitted, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=2_000,
        limit_price="100.5",
        idempotency_key="duplicate-book-volume",
    )
    assert submitted["status"] == "PENDING"
    observed_at = datetime.now(TAIPEI)

    provider.emit_book(
        bid="99.5",
        ask="100",
        ask_volume_lots=1,
        observed_at=observed_at,
    )
    wait_until(
        lambda: service.orders()[0]["status"] == "PARTIALLY_FILLED"
    )
    provider.emit_book(
        bid="99.5",
        ask="100",
        ask_volume_lots=1,
        observed_at=observed_at,
    )
    wait_until(lambda: service.session()["quote_queue_depth"] == 0)

    order = service.orders()[0]
    assert order["status"] == "PARTIALLY_FILLED"
    assert order["filled_quantity"] == 1_000
    service.close()


def test_partial_v3_replay_validates_order_cumulative_tax_lineage() -> None:
    provider = StreamingPriceProvider()
    service = v2_service(provider, starting_cash="500000")
    submitted, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=1_500,
        limit_price="100.5",
        idempotency_key="partial-v3-lineage",
    )
    at = datetime.now(TAIPEI)
    provider.emit_book(
        bid="99.5",
        ask="100",
        ask_volume_lots=1,
        observed_at=at,
    )
    wait_until(lambda: service.orders()[0]["status"] == "PARTIALLY_FILLED")
    first = journal_record_from_simulation_order(
        service.orders()[0],
        session_id="partial-v3-lineage",
        settings_digest=SETTINGS_DIGEST,
    )
    assert first is not None

    provider.emit_book(
        bid="99.5",
        ask="100",
        ask_volume_lots=1,
        observed_at=at + timedelta(microseconds=1),
    )
    wait_until(lambda: service.orders()[0]["status"] == "FILLED")
    second = journal_record_from_simulation_order(
        service.orders()[0],
        session_id="partial-v3-lineage",
        settings_digest=SETTINGS_DIGEST,
    )
    assert second is not None
    projection = LocalPaperProjection(
        starting_cash=Decimal("500000"),
        settings_digest=SETTINGS_DIGEST,
    )
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id="partial-v3-lineage",
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"settings_digest": SETTINGS_DIGEST},
        )
    )
    projection.apply(journal.append(first))
    tampered = replace(
        second,
        payload={**second.payload, "cumulative_order_tax": "1"},
    )

    with pytest.raises(ProjectionRecoveryError, match="cumulative order evidence"):
        projection.apply(journal.append(tampered))

    service.close()


def test_unknown_descriptor_is_rejected_before_order_creation() -> None:
    class UnknownProvider(PriceProvider):
        def get_local_paper_instrument_descriptor(self, symbol: str):
            return None

    service = v2_service(UnknownProvider())

    with pytest.raises(SimulationValidationError, match="UNSUPPORTED_COST_POLICY_SCOPE"):
        service.submit_order(
            symbol="3231",
            side="BUY",
            quantity_shares=100,
            limit_price="100",
            idempotency_key="unknown-product",
        )
    assert service.orders() == []
