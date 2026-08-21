from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from threading import Thread
from time import sleep
from zoneinfo import ZoneInfo

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.late_delivery_capture import (
    PassiveLateDeliveryCapture,
    PassiveLateDeliveryCaptureConfig,
)
from market_data.late_delivery_capture_cli import main as capture_cli_main
from market_data.late_delivery_evidence import LateDeliveryCohort, SessionPhase
from market_data.momentum_stream import (
    QualificationBootstrapEvidence,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 21)
SESSION_ID = "late-delivery-passive-test"


class MutableClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 21, 9, 0, tzinfo=TAIPEI)


class FakeMultiSymbolStream:
    def __init__(self, session_id: str, clock: MutableClock) -> None:
        self.session_id = session_id
        self.clock = clock
        self.event_handler = None
        self.lifecycle_handler = None
        self.thread: Thread | None = None
        self.callback_errors: tuple[str, ...] = ()
        self.closed = False

    @property
    def environment_identity(self) -> str:
        return "fake:market-data-only"

    def qualification_bootstrap_evidence(
        self,
        symbol: str,
        session_date: date,
        prior_session_date: date,
    ) -> QualificationBootstrapEvidence:
        reference = InstrumentReference(
            symbol=symbol,
            exchange="TSE",
            session_date=session_date,
            reference_price=Decimal("1180"),
            limit_up_price=Decimal("1295"),
            limit_down_price=Decimal("1065"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=session_date,
        )
        now = self.clock.now()
        return QualificationBootstrapEvidence(
            reference=reference,
            instrument_name=f"Stock {symbol}",
            security_type="STOCK",
            instrument_source_identity=f"TSE:{symbol}",
            captured_at=now,
            received_at=now,
            prior_session_date=prior_session_date,
            previous_close=Decimal("1180"),
            previous_session_volume_lots=100,
            snapshot_source_identity=f"fake-snapshot:TSE:{symbol}",
        )

    def start(self, event_handler, lifecycle_handler) -> None:
        self.event_handler = event_handler
        self.lifecycle_handler = lifecycle_handler

    def request_subscribe(self, symbol: str) -> None:
        assert self.lifecycle_handler is not None
        self.lifecycle_handler(
            StreamLifecycleEvent(
                event_type=StreamLifecycleEventType.SUBSCRIBE_ACKED,
                occurred_at=self.clock.now(),
                reason="paired_tick_bidask_ack",
                symbol=symbol,
                raw_event_code=16,
                raw_info="paired",
            )
        )

    def emit(self, symbols: tuple[str, ...]) -> None:
        assert self.event_handler is not None
        for offset, symbol in enumerate(symbols):
            self.event_handler(_tick(self.session_id, symbol, 20 + offset))
        for offset, symbol in enumerate(symbols):
            self.event_handler(_book(self.session_id, symbol, 40 + offset))
        self.event_handler(_book(self.session_id, "2330", 99, older=True))

    def close(self) -> None:
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.closed = True


def _at(second: int, microsecond: int = 0) -> datetime:
    return datetime(2026, 8, 21, 9, 0, second, microsecond, tzinfo=TAIPEI)


def _tick(session_id: str, symbol: str, sequence: int) -> EventEnvelope:
    at = _at(1, sequence)
    payload = TickEvent(
        event_id=f"tick-{symbol}-{sequence}",
        source=MarketEventSource.TICK,
        symbol=symbol,
        session_date=SESSION_DATE,
        event_time=at,
        received_at=at,
        ingress_sequence=sequence,
        price=Decimal("1181"),
        tick_volume_lots=1,
        total_volume_lots=sequence,
        average_price=Decimal("1180.5"),
        intraday_high=Decimal("1181"),
        intraday_low=Decimal("1180"),
        raw_tick_type=1,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=payload.event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=session_id,
        session_date=SESSION_DATE,
        source=MarketEventSource.TICK,
        source_mode="TICK_BIDASK",
        stream_kind=MarketStreamKind.TICK,
        symbol=symbol,
        event_at=at,
        received_at=at,
        ingress_sequence=sequence,
        source_identity=f"fake:tick:{symbol}:{sequence}",
        payload=payload,
    )


def _book(
    session_id: str,
    symbol: str,
    sequence: int,
    *,
    older: bool = False,
) -> EventEnvelope:
    event_at = _at(2 if not older else 1, 100 if not older else 900_000)
    received_at = _at(2, 200 if not older else 50_000)
    payload = BidAskEvent(
        event_id=f"book-{symbol}-{sequence}",
        source=MarketEventSource.BIDASK,
        symbol=symbol,
        session_date=SESSION_DATE,
        event_time=event_at,
        received_at=received_at,
        ingress_sequence=sequence,
        bid_prices=(Decimal("1180"),),
        bid_volume_lots=(sequence,),
        ask_prices=(Decimal("1181"),),
        ask_volume_lots=(sequence,),
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=payload.event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=session_id,
        session_date=SESSION_DATE,
        source=MarketEventSource.BIDASK,
        source_mode="TICK_BIDASK",
        stream_kind=MarketStreamKind.BIDASK,
        symbol=symbol,
        event_at=event_at,
        received_at=received_at,
        ingress_sequence=sequence,
        source_identity=f"fake:book:{symbol}:{sequence}",
        payload=payload,
    )


def _cohort() -> LateDeliveryCohort:
    return LateDeliveryCohort.from_mapping(
        {
            "schema": "late-delivery-cohort-manifest-v1",
            "status": "FROZEN_FOR_COLLECTION",
            "capture_timezone": "Asia/Taipei",
            "selection_source": {
                "provider": "TWSE",
                "source_date": "2026-08-20",
                "source_identity": "fixture:twse",
            },
            "symbols": [
                {"symbol": symbol, "liquidity_tier": tier, "selection_evidence": "fixture"}
                for symbol, tier in (
                    ("2330", "high"), ("2317", "high"), ("2454", "high"),
                    ("6863", "mid"), ("1530", "low"), ("2002", "low"),
                )
            ],
            "session_windows": [
                {"phase": "OPEN", "start_local": "09:00", "end_local": "09:30"},
                {"phase": "MID", "start_local": "10:30", "end_local": "11:00"},
                {"phase": "CLOSE", "start_local": "13:00", "end_local": "13:30"},
            ],
        }
    )


def test_passive_collector_finalizes_multi_symbol_evidence_without_case_taxonomy(tmp_path) -> None:
    clock = MutableClock()
    stream = FakeMultiSymbolStream(SESSION_ID, clock)
    capture = PassiveLateDeliveryCapture(
        stream,
        PassiveLateDeliveryCaptureConfig(
            cohort=_cohort(),
            phase=SessionPhase.OPEN,
            session_id=SESSION_ID,
            records_root=tmp_path / "records" / "market_events",
            duration_seconds=1,
        ),
        prior_session_date=date(2026, 8, 20),
        calendar_version="reviewed-calendar-v1",
        clock=clock,
    )
    original_wait = capture._wait_for_capture_duration
    capture._wait_for_capture_duration = lambda: stream.emit(capture.config.cohort.symbols)  # type: ignore[method-assign]

    result = capture.run()

    assert result.completed is True
    assert result.exact_replay_passed is True
    assert stream.closed is True
    assert result.evidence_path is not None
    evidence = json.loads(result.evidence_path.read_text())
    assert evidence["policy_interpretation"] == "PROHIBITED_EVIDENCE_ONLY"
    assert evidence["by_symbol"]["2330"]["by_stream"]["BIDASK"]["late_delivery_count"] == 1
    assert {item["symbol"] for item in json.loads((result.session_dir / "instrument_reference.json").read_text())["references"]} == set(capture.config.cohort.symbols)


def test_passive_cli_checks_flags_before_loading_cohort_or_provider(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "market_data.late_delivery_capture_cli.require_qualification_flags_off",
        lambda: (_ for _ in ()).throw(RuntimeError("FOUNDATION_FLAGS_MUST_BE_OFF:test")),
    )

    exit_code = capture_cli_main(["--cohort", "missing.json", "--phase", "OPEN"])

    assert exit_code == 2
    assert "FOUNDATION_FLAGS_MUST_BE_OFF:test" in capsys.readouterr().out


def test_wait_for_phase_rechecks_clock_after_early_wakeup(monkeypatch, tmp_path) -> None:
    class AdvancingClock:
        def __init__(self) -> None:
            self.value = datetime(2026, 8, 21, 10, 25, tzinfo=TAIPEI)

        def now(self) -> datetime:
            return self.value

    clock = AdvancingClock()
    capture = PassiveLateDeliveryCapture(
        FakeMultiSymbolStream(SESSION_ID, clock),
        PassiveLateDeliveryCaptureConfig(
            cohort=_cohort(),
            phase=SessionPhase.MID,
            session_id=SESSION_ID,
            records_root=tmp_path / "records" / "market_events",
        ),
        prior_session_date=date(2026, 8, 20),
        calendar_version="reviewed-calendar-v1",
        clock=clock,
    )
    wakeups = 0

    class EarlyWakeEvent:
        def wait(self, timeout: float) -> None:
            nonlocal wakeups
            assert timeout > 0
            wakeups += 1
            clock.value = datetime(
                2026,
                8,
                21,
                10,
                29 if wakeups == 1 else 30,
                59 if wakeups == 1 else 0,
                999999 if wakeups == 1 else 0,
                tzinfo=TAIPEI,
            )

    monkeypatch.setattr("market_data.late_delivery_capture.Event", EarlyWakeEvent)
    start = datetime(2026, 8, 21, 10, 30, tzinfo=TAIPEI)
    end = datetime(2026, 8, 21, 11, 0, tzinfo=TAIPEI)

    assert capture._wait_for_phase(start, end) == start
    assert wakeups == 2
