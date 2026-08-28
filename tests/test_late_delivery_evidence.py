from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_data.events import (
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
)
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.ingress import BoundedIngressQueue
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.journal import JsonlMarketEventRecorder, MarketEventJournalSummary
from market_data.late_delivery_evidence import (
    LATE_DELIVERY_COHORT_MANIFEST_SCHEMA,
    LateDeliveryCohort,
    SessionPhase,
    analyze_late_delivery_session,
    build_daily_late_delivery_report,
    classify_session_phase,
    write_late_delivery_session_report,
)
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import CanonicalMarketDataPipeline


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 21)
SESSION_ID = "late-delivery-evidence-test"


def at(second: int, microsecond: int = 0) -> datetime:
    return datetime(
        2026,
        8,
        21,
        9,
        0,
        second,
        microsecond,
        tzinfo=TAIPEI,
    )


def cohort_payload(*, status: str = "FROZEN_FOR_COLLECTION") -> dict[str, object]:
    return {
        "schema": LATE_DELIVERY_COHORT_MANIFEST_SCHEMA,
        "status": status,
        "capture_timezone": "Asia/Taipei",
        "selection_source": {
            "provider": "TWSE",
            "source_date": "2026-08-20",
            "source_identity": "twse-daily-2026-08-20",
        },
        "symbols": [
            {"symbol": "2330", "liquidity_tier": "high", "selection_evidence": "ranked"},
            {"symbol": "2317", "liquidity_tier": "high", "selection_evidence": "ranked"},
            {"symbol": "2454", "liquidity_tier": "high", "selection_evidence": "ranked"},
            {"symbol": "6863", "liquidity_tier": "mid", "selection_evidence": "ranked"},
            {"symbol": "1530", "liquidity_tier": "low", "selection_evidence": "ranked"},
            {"symbol": "2002", "liquidity_tier": "low", "selection_evidence": "ranked"},
        ],
        "session_windows": [
            {"phase": "OPEN", "start_local": "09:00", "end_local": "09:30"},
            {"phase": "MID", "start_local": "10:30", "end_local": "11:00"},
            {"phase": "CLOSE", "start_local": "13:00", "end_local": "13:30"},
        ],
    }


def book_envelope(
    sequence: int,
    *,
    event_at: datetime,
    received_at: datetime,
) -> EventEnvelope:
    event_id = f"book-{sequence}"
    payload = BidAskEvent(
        event_id=event_id,
        source=MarketEventSource.BIDASK,
        symbol="2330",
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
        event_id=event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.BIDASK,
        source_mode="TEST",
        stream_kind=MarketStreamKind.BIDASK,
        symbol="2330",
        event_at=event_at,
        received_at=received_at,
        ingress_sequence=sequence,
        source_identity=f"pytest:book:{sequence}",
        payload=payload,
    )


def finalized_late_session(tmp_path: Path) -> Path:
    references = InstrumentReferenceStore(SESSION_DATE)
    references.put(
        InstrumentReference(
            symbol="2330",
            exchange="TSE",
            session_date=SESSION_DATE,
            reference_price=Decimal("1180"),
            limit_up_price=Decimal("1295"),
            limit_down_price=Decimal("1065"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=SESSION_DATE,
        )
    )
    bars = IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))
    books = OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))
    health = DataHealth(SESSION_DATE, started_at=at(0))
    health.mark_ready(occurred_at=at(0), evidence="fixture")
    recorder = JsonlMarketEventRecorder(
        root=tmp_path / "records" / "market_events",
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        started_at=at(0),
        producer_identity="pytest",
        source_mode="TEST",
    )
    pipeline = CanonicalMarketDataPipeline(
        queue=BoundedIngressQueue(capacity=8, control_reserve=1, health=health),
        recorder=recorder,
        ingestor=MarketDataIngestor(
            session_id=SESSION_ID,
            session_date=SESSION_DATE,
            references=references,
            bars=bars,
            books=books,
            health=health,
        ),
        health=health,
    )
    first = book_envelope(1, event_at=at(1), received_at=at(1, 10_000))
    late = book_envelope(2, event_at=at(0, 940_000), received_at=at(1, 63_000))
    assert pipeline.submit_market(lambda _: first).accepted
    assert pipeline.submit_market(lambda _: late).accepted
    pipeline.process_pending(occurred_at=at(2))
    recorder.finalize(
        MarketEventJournalSummary(
            finalized_at=at(3),
            queue_drained=True,
            projection_digest={
                "bar": bars.digest,
                "book": books.digest,
                "health": health.snapshot().digest,
            },
        )
    )
    return recorder.session_dir


def test_frozen_cohort_requires_six_to_nine_provenance_backed_symbols() -> None:
    cohort = LateDeliveryCohort.from_mapping(cohort_payload())

    assert cohort.symbols == ("1530", "2002", "2317", "2330", "2454", "6863")
    assert cohort.tier_for("2330") == "high"

    with pytest.raises(ValueError, match="FROZEN_FOR_COLLECTION"):
        LateDeliveryCohort.from_mapping(cohort_payload(status="PENDING_SELECTION"))


def test_phase_classification_uses_received_time_in_taipei() -> None:
    assert classify_session_phase(at(1)) is SessionPhase.OPEN
    assert classify_session_phase(datetime(2026, 8, 21, 10, 45, tzinfo=TAIPEI)) is SessionPhase.MID
    assert classify_session_phase(datetime(2026, 8, 21, 13, 15, tzinfo=TAIPEI)) is SessionPhase.CLOSE
    assert classify_session_phase(datetime(2026, 8, 21, 12, 0, tzinfo=TAIPEI)) is None


def test_late_delivery_ledger_preserves_signed_regression_and_effects(tmp_path: Path) -> None:
    report = analyze_late_delivery_session(finalized_late_session(tmp_path))

    assert report.status == "FINALIZED"
    assert report.stream_totals["BIDASK"].total_events == 2
    assert report.stream_totals["BIDASK"].late_delivery_count == 1
    assert report.by_symbol["2330"].by_stream["BIDASK"].total_events == 2
    assert report.by_phase["OPEN"].by_stream["BIDASK"].total_events == 2
    late = report.late_deliveries[0]
    assert late.stream_kind == "BIDASK"
    assert late.source_regression_ms == pytest.approx(-60.0)
    assert late.receive_progression_ms == pytest.approx(53.0)
    assert late.consecutive_late_count == 1
    assert late.session_phase is SessionPhase.OPEN
    assert late.projection_effect == "REJECTED_BEFORE_PROJECTION"
    assert late.health_effect == "HEALTHY_TO_DEGRADED"
    assert late.admission_effect == "OPEN_TO_BLOCK_NEW_ENTRY"


def test_daily_report_separates_streams_and_is_built_from_session_ledgers(tmp_path: Path) -> None:
    session_dir = finalized_late_session(tmp_path)
    report = analyze_late_delivery_session(session_dir)
    evidence_path = write_late_delivery_session_report(session_dir, report)
    assert json.loads(evidence_path.read_text())["schema"] == "late-delivery-session-evidence-v1"
    incomplete_dir = evidence_path.parent.parent / "incomplete-passive-session"
    incomplete_dir.mkdir()
    (incomplete_dir / "passive_capture_report.json").write_text(
        json.dumps(
            {
                "schema": "late-delivery-passive-capture-report-v1",
                "session_id": "incomplete-passive-session",
                "status": "INCOMPLETE",
            }
        )
    )
    (session_dir / "passive_capture_report.json").write_text(
        json.dumps(
            {
                "schema": "late-delivery-passive-capture-report-v1",
                "session_id": SESSION_ID,
                "status": "COMPLETE_WITH_WARNINGS",
            }
        )
    )

    daily = build_daily_late_delivery_report(tmp_path / "records" / "market_events", SESSION_DATE)

    assert daily.session_count == 1
    assert daily.incomplete_session_ids == ("incomplete-passive-session",)
    assert daily.replay_failed_session_ids == ()
    assert daily.warning_session_ids == (SESSION_ID,)
    assert daily.by_stream["BIDASK"].late_delivery_count == 1
    assert daily.by_stream["TICK"].total_events == 0
    assert daily.by_symbol["2330"].by_stream["BIDASK"].late_delivery_count == 1
    assert daily.by_symbol["2330"].by_stream["BIDASK"].total_events == 2
    assert daily.by_phase["OPEN"].by_stream["BIDASK"].late_delivery_count == 1
