from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from features.engine import FeatureEngine
from features.models import (
    FeatureEngineConfig,
    FeatureEvaluationContext,
    FeatureStatus,
    FeatureValue,
    OpeningVolumeContext,
)
from market_data.events import TickEvent
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.replay import ReplayDatasetLoader


FIXTURES = Path(__file__).parent / "fixtures"


def project_fixture(name: str):
    dataset = ReplayDatasetLoader().load(FIXTURES / name)
    started_at = dataset.events[0].received_at
    references = InstrumentReferenceStore(dataset.manifest.session_date)
    for reference in dataset.references:
        references.put(reference)
    bars = IntradayBarStore(
        dataset.manifest.session_date,
        retention=timedelta(minutes=20),
    )
    books = OrderBookStore(
        dataset.manifest.session_date,
        retention=timedelta(minutes=20),
    )
    health = DataHealth(dataset.manifest.session_date, started_at=started_at)
    health.mark_ready(occurred_at=started_at, evidence="validated_fixture")
    ingestor = MarketDataIngestor(
        session_id=dataset.manifest.session_id,
        session_date=dataset.manifest.session_date,
        references=references,
        bars=bars,
        books=books,
        health=health,
    )
    current = None
    for envelope in dataset.events:
        result = ingestor.ingest(envelope)
        assert result.projection_applied
        if isinstance(envelope.payload, TickEvent):
            current = envelope.payload
    assert current is not None
    return references, bars, books, health, current


def evaluate_fixture(name: str, *, coverage_started_at: datetime):
    references, bars, books, health, current = project_fixture(name)
    snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=coverage_started_at,
            aggressor_mapping_verified=True,
        ),
    )
    return snapshot, (references, bars, books, health, current)


def test_enriched_8039_features_use_strict_prior_high_and_complete_windows():
    coverage = datetime.fromisoformat("2026-08-18T09:06:00+08:00")
    snapshot, _ = evaluate_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json",
        coverage_started_at=coverage,
    )

    assert snapshot.price.value == Decimal("278")
    assert snapshot.vwap.value == Decimal("270.76")
    assert snapshot.previous_intraday_high.value == Decimal("275")
    assert snapshot.breakout.value is True
    assert snapshot.return_2m.value == Decimal("278") / Decimal("272") - 1
    assert snapshot.distance_to_limit.value == Decimal("284.5") / Decimal("278") - 1
    assert snapshot.volume_2m.value == 2306
    assert snapshot.baseline_complete_windows == 5
    assert snapshot.baseline_2m.value == Decimal("1400")
    assert snapshot.volume_acceleration_2m.value == Decimal("2306") / Decimal("1400")
    assert snapshot.external_ratio_rising.value is True
    assert snapshot.bid_depth_5.value == 3300
    assert snapshot.ask_depth_5.value == 1800
    assert snapshot.bid_ask_ratio_5.value == Decimal("3300") / Decimal("1800")
    assert snapshot.required_inputs_valid is True


def test_screenshot_only_8039_does_not_invent_volume_baseline():
    coverage = datetime.fromisoformat("2026-08-18T09:16:00+08:00")
    snapshot, _ = evaluate_fixture(
        "8039_2026-08-18_phase2_replay.json",
        coverage_started_at=coverage,
    )

    assert snapshot.volume_2m.value == 2306
    assert snapshot.baseline_complete_windows == 0
    assert snapshot.baseline_2m.status is FeatureStatus.MISSING
    assert snapshot.volume_acceleration_2m.status is FeatureStatus.MISSING
    assert snapshot.required_inputs_valid is False
    assert any(
        reason.startswith("baseline_2m:MISSING")
        for reason in snapshot.block_reasons
    )


def test_four_of_five_complete_baseline_windows_are_sufficient():
    snapshot, _ = evaluate_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json",
        coverage_started_at=datetime.fromisoformat(
            "2026-08-18T09:08:00+08:00"
        ),
    )

    assert snapshot.baseline_complete_windows == 4
    assert snapshot.baseline_2m.status is FeatureStatus.VALID
    assert snapshot.baseline_2m.value == Decimal("1400")
    assert snapshot.volume_acceleration_2m.status is FeatureStatus.VALID


def test_zero_volume_baseline_is_missing_instead_of_infinite():
    coverage = datetime.fromisoformat("2026-08-18T09:06:00+08:00")
    references, source_bars, books, _, source_current = project_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json"
    )
    bars = IntradayBarStore(
        source_current.session_date,
        retention=timedelta(minutes=20),
    )
    running_total = 0
    current = None
    for original in source_bars.ticks(source_current.symbol):
        tick_volume = (
            original.tick_volume_lots
            if original.event_time > datetime.fromisoformat(
                "2026-08-18T09:16:00+08:00"
            )
            else 0
        )
        running_total += tick_volume
        event = replace(
            original,
            event_id=f"zero-baseline-{original.event_id}",
            tick_volume_lots=tick_volume,
            total_volume_lots=running_total,
        )
        assert bars.apply(event).projection_applied
        current = event
    assert current is not None
    health = DataHealth(current.session_date, started_at=coverage)
    health.mark_ready(occurred_at=current.received_at, evidence="zero_baseline")
    snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=coverage,
            aggressor_mapping_verified=True,
        ),
    )

    assert snapshot.volume_2m.value == 2306
    assert snapshot.baseline_2m.value == Decimal("0")
    assert snapshot.volume_acceleration_2m.status is FeatureStatus.MISSING
    assert snapshot.volume_acceleration_2m.reason == "baseline_volume_zero"


def test_unverified_aggressor_mapping_never_creates_external_ratio():
    coverage = datetime.fromisoformat("2026-08-18T09:06:00+08:00")
    references, bars, books, health, current = project_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json"
    )
    snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=coverage,
            aggressor_mapping_verified=False,
        ),
    )

    assert snapshot.external_ratio_session.status is FeatureStatus.UNVERIFIED
    assert snapshot.external_ratio_rising.status is FeatureStatus.UNVERIFIED


def test_ask_depth_zero_keeps_raw_ratio_missing_but_bounded_imbalance_valid():
    coverage = datetime.fromisoformat("2026-08-18T09:06:00+08:00")
    snapshot, projected = evaluate_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json",
        coverage_started_at=coverage,
    )
    references, bars, _, health, current = projected
    books = OrderBookStore(current.session_date, retention=timedelta(minutes=20))
    original = projected[2].latest(current.symbol)
    assert original is not None
    zero_ask = replace(
        original,
        event_id="zero-ask",
        event_time=current.event_time,
        received_at=current.received_at,
        ingress_sequence=2,
        ask_volume_lots=tuple(0 for _ in original.ask_volume_lots),
    )
    books.apply(zero_ask)
    zero_snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=coverage,
            aggressor_mapping_verified=True,
        ),
    )

    assert snapshot.bid_ask_ratio_5.status is FeatureStatus.VALID
    assert zero_snapshot.bid_ask_ratio_5.status is FeatureStatus.MISSING
    assert zero_snapshot.bid_ask_ratio_5.reason == "ask_depth_zero"
    assert zero_snapshot.book_imbalance_5.value == Decimal("1")


def test_future_book_is_not_used_and_stale_book_is_marked_stale():
    coverage = datetime.fromisoformat("2026-08-18T09:06:00+08:00")
    _, projected = evaluate_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json",
        coverage_started_at=coverage,
    )
    references, bars, original_books, health, current = projected
    original = original_books.latest(current.symbol)
    assert original is not None

    future_books = OrderBookStore(
        current.session_date,
        retention=timedelta(minutes=20),
    )
    future_books.apply(
        replace(
            original,
            event_id="future-book",
            event_time=current.event_time + timedelta(seconds=1),
            received_at=current.received_at + timedelta(seconds=1),
            ingress_sequence=2,
        )
    )
    context = FeatureEvaluationContext(
        data_health=health.snapshot(),
        tick_coverage_started_at=coverage,
        aggressor_mapping_verified=True,
    )
    future_snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=future_books,
    ).evaluate(current, context)
    stale_snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=original_books,
        config=FeatureEngineConfig(order_book_max_age=timedelta(0)),
    ).evaluate(current, context)

    assert future_snapshot.bid_depth_5.status is FeatureStatus.MISSING
    assert stale_snapshot.bid_depth_5.status is FeatureStatus.STALE


def test_future_opening_context_is_rejected():
    coverage = datetime.fromisoformat("2026-08-18T09:06:00+08:00")
    references, bars, books, health, current = project_fixture(
        "8039_2026-08-18_phase3_enriched_replay.json"
    )
    future = FeatureValue(
        value=Decimal("2"),
        status=FeatureStatus.VALID,
        source_as_of=current.event_time + timedelta(seconds=1),
    )
    snapshot = FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=coverage,
            aggressor_mapping_verified=True,
            opening_volume_context=OpeningVolumeContext(
                mode="HISTORICAL_ELAPSED_TIME_RVOL",
                value=future,
                provenance="test-future-value",
            ),
        ),
    )

    assert snapshot.opening_volume_context.status is FeatureStatus.MISSING
    assert snapshot.opening_volume_context.reason == (
        "opening_volume_context_uses_future_data"
    )
