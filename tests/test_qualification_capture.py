from __future__ import annotations

import json
from types import SimpleNamespace
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
from market_data.momentum_stream import (
    QualificationBootstrapEvidence,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from market_data.qualification_capture import (
    HistoricalQualificationCapture,
    QualificationCaptureConfig,
)
from market_data.qualification_capture_cli import main as capture_cli_main


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 20)
SESSION_ID = "qualification-case-a"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI)

    def now(self) -> datetime:
        return self.value


class FakeQualificationStream:
    def __init__(
        self,
        clock: MutableClock,
        *,
        emit_book: bool = True,
        emit_incident: bool = False,
    ) -> None:
        self.clock = clock
        self.emit_book = emit_book
        self.emit_incident = emit_incident
        self.event_handler = None
        self.lifecycle_handler = None
        self.thread: Thread | None = None
        self.callback_errors: tuple[str, ...] = ()
        self.closed = False

    def qualification_bootstrap_evidence(
        self,
        symbol: str,
        session_date: date,
        prior_session_date: date,
    ) -> QualificationBootstrapEvidence:
        reference = InstrumentReference(
            symbol=symbol,
            exchange="TWSE",
            session_date=session_date,
            reference_price=Decimal("1180"),
            limit_up_price=Decimal("1295"),
            limit_down_price=Decimal("1065"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=session_date,
        )
        return QualificationBootstrapEvidence(
            reference=reference,
            instrument_name="台積電",
            security_type="STOCK",
            instrument_source_identity="TSE:2330",
            captured_at=self.clock.now(),
            received_at=self.clock.now(),
            prior_session_date=prior_session_date,
            previous_close=Decimal("1180"),
            previous_session_volume_lots=27543,
            snapshot_source_identity="fake-snapshot:TSE:2330",
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
        self.thread = Thread(target=self._emit, daemon=True)
        self.thread.start()

    def _emit(self) -> None:
        sleep(0.1)
        assert self.event_handler is not None
        self.event_handler(_tick_envelope())
        if self.emit_book:
            self.event_handler(_book_envelope())
        if self.emit_incident:
            assert self.lifecycle_handler is not None
            self.lifecycle_handler(
                StreamLifecycleEvent(
                    event_type=StreamLifecycleEventType.DISCONNECTED,
                    occurred_at=datetime(
                        2026,
                        8,
                        20,
                        9,
                        0,
                        3,
                        tzinfo=TAIPEI,
                    ),
                    reason="natural_provider_disconnect",
                    raw_event_code=1,
                    raw_info="connection lost",
                )
            )
        self.clock.value = datetime(2026, 8, 20, 9, 0, 3, tzinfo=TAIPEI)

    def close(self) -> None:
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.closed = True


def _tick_envelope() -> EventEnvelope:
    observed_at = datetime(2026, 8, 20, 9, 0, 1, tzinfo=TAIPEI)
    payload = TickEvent(
        event_id="real-tick-1",
        source=MarketEventSource.TICK,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=observed_at,
        received_at=observed_at,
        ingress_sequence=77,
        price=Decimal("1181"),
        tick_volume_lots=2,
        total_volume_lots=102,
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
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.TICK,
        source_mode="TICK_BIDASK",
        stream_kind=MarketStreamKind.TICK,
        symbol="2330",
        event_at=observed_at,
        received_at=observed_at,
        ingress_sequence=77,
        source_identity="fake:tick:77",
        payload=payload,
    )


def _book_envelope() -> EventEnvelope:
    observed_at = datetime(2026, 8, 20, 9, 0, 2, tzinfo=TAIPEI)
    payload = BidAskEvent(
        event_id="real-book-1",
        source=MarketEventSource.BIDASK,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=observed_at,
        received_at=observed_at,
        ingress_sequence=78,
        bid_prices=(Decimal("1180"),),
        bid_volume_lots=(3,),
        ask_prices=(Decimal("1181"),),
        ask_volume_lots=(2,),
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=payload.event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.BIDASK,
        source_mode="TICK_BIDASK",
        stream_kind=MarketStreamKind.BIDASK,
        symbol="2330",
        event_at=observed_at,
        received_at=observed_at,
        ingress_sequence=78,
        source_identity="fake:book:78",
        payload=payload,
    )


def test_case_a_capture_writes_real_lifecycle_artifacts_and_exact_replays(tmp_path):
    clock = MutableClock()
    stream = FakeQualificationStream(clock)
    result = HistoricalQualificationCapture(
        stream,
        QualificationCaptureConfig(
            symbol="2330",
            session_id=SESSION_ID,
            records_root=tmp_path / "records" / "market_events",
            duration_seconds=1,
            qualification_case="A",
        ),
        prior_session_date=date(2026, 8, 19),
        calendar_version="reviewed-calendar-v1",
        clock=clock,
    ).run()

    assert result.qualified is True
    assert result.classification == "CASE_A"
    assert result.exact_replay_passed is True
    assert stream.closed is True
    assert {item.name for item in result.session_dir.iterdir()} == {
        "records.jsonl",
        "manifest.json",
        "instrument_reference.json",
        "bootstrap_snapshot.json",
        "projection_state.json",
        "qualification_report.json",
    }
    report = json.loads(result.report_path.read_text())
    assert report["safety"] == {
        "foundation_flags_off": True,
        "subscribe_trade": False,
        "order_path": "NOT_WIRED",
        "consumer_authority": "UNCHANGED",
        "source_environment": "qualification-stream:unspecified",
    }
    assert report["capture"]["stream_counts"] == {"BIDASK": 1, "TICK": 1}
    assert report["exact_replay"]["repeat_count"] == 10
    assert all(item["match"] for item in report["exact_replay"]["comparisons"])


def test_case_a_missing_book_evidence_fails_closed_but_preserves_artifacts(tmp_path):
    clock = MutableClock()
    result = HistoricalQualificationCapture(
        FakeQualificationStream(clock, emit_book=False),
        QualificationCaptureConfig(
            symbol="2330",
            session_id=SESSION_ID,
            records_root=tmp_path / "records" / "market_events",
            duration_seconds=1,
            qualification_case="A",
        ),
        prior_session_date=date(2026, 8, 19),
        calendar_version="reviewed-calendar-v1",
        clock=clock,
    ).run()

    assert result.qualified is False
    assert result.exact_replay_passed is True
    assert result.reasons == ("MISSING_BIDASK_EVIDENCE",)
    assert result.report_path is not None
    assert (result.session_dir / "projection_state.json").exists()


def test_natural_incident_is_classified_as_case_b_and_exact_replays(tmp_path):
    clock = MutableClock()
    result = HistoricalQualificationCapture(
        FakeQualificationStream(clock, emit_incident=True),
        QualificationCaptureConfig(
            symbol="2330",
            session_id=SESSION_ID,
            records_root=tmp_path / "records" / "market_events",
            duration_seconds=1,
            qualification_case="B",
        ),
        prior_session_date=date(2026, 8, 19),
        calendar_version="reviewed-calendar-v1",
        clock=clock,
    ).run()

    assert result.qualified is True
    assert result.classification == "CASE_B"
    assert result.exact_replay_passed is True
    records = (result.session_dir / "records.jsonl").read_text().splitlines()
    incident = [
        json.loads(item)
        for item in records
        if json.loads(item)["record_type"] == "SYSTEM_INCIDENT"
    ]
    assert len(incident) == 1
    assert incident[0]["incident"]["incident_type"] == "PROVIDER_DISCONNECTED"


def test_cli_checks_flags_before_provider_connection(monkeypatch, capsys):
    monkeypatch.setattr(
        "market_data.qualification_capture.FOUNDATION_FEATURE_FLAGS",
        SimpleNamespace(event_runtime_enabled=True),
    )
    connected = False

    def forbidden_connect(**kwargs):
        nonlocal connected
        connected = True
        raise AssertionError(kwargs)

    monkeypatch.setattr(
        "market_data.qualification_capture_cli."
        "ShioajiMomentumStream.connect_from_env",
        forbidden_connect,
    )

    exit_code = capture_cli_main(["--symbol", "2330"])

    assert exit_code == 2
    assert connected is False
    assert "FOUNDATION_FLAGS_MUST_BE_OFF" in capsys.readouterr().out


def test_wait_for_open_rechecks_clock_after_early_wakeup(monkeypatch, tmp_path):
    clock = MutableClock()
    clock.value = datetime(2026, 8, 20, 8, 59, 59, 900000, tzinfo=TAIPEI)
    capture = HistoricalQualificationCapture(
        FakeQualificationStream(clock),
        QualificationCaptureConfig(
            symbol="2330",
            session_id=SESSION_ID,
            records_root=tmp_path,
        ),
        prior_session_date=date(2026, 8, 19),
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
                20,
                8 if wakeups == 1 else 9,
                59 if wakeups == 1 else 0,
                59 if wakeups == 1 else 0,
                999999 if wakeups == 1 else 0,
                tzinfo=TAIPEI,
            )

    monkeypatch.setattr(
        "market_data.qualification_capture.Event",
        EarlyWakeEvent,
    )
    scheduled_open = datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI)
    scheduled_close = datetime(2026, 8, 20, 13, 30, tzinfo=TAIPEI)

    result = capture._wait_for_open(scheduled_open, scheduled_close)

    assert result == scheduled_open
    assert wakeups == 2
