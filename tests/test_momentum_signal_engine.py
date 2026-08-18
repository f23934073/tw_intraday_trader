from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from config.momentum import (
    LIMIT_UP_MOMENTUM_HYPOTHESIS_V0,
    OPENING_MOMENTUM_HYPOTHESIS_V0,
    EvidenceWeight,
    OpeningVolumeContextMode,
)
from features.engine import FeatureEngine
from features.models import (
    FeatureEvaluationContext,
    FeatureStatus,
    FeatureValue,
    OpeningVolumeContext,
)
from market_data.events import (
    AggressorSide,
    InstrumentReference,
    MarketEventSource,
    TickEvent,
)
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from market_data.replay import ReplayDatasetLoader
from signals.models import (
    EvidenceStatus,
    MomentumSignal,
    SignalEvaluationStatus,
    SignalFamily,
)
from signals.momentum import MomentumSignalEngine


FIXTURES = Path(__file__).parent / "fixtures"


def replay_snapshot(name: str, coverage_started_at: datetime, *, verified=True):
    dataset = ReplayDatasetLoader().load(FIXTURES / name)
    start = dataset.events[0].received_at
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
    health = DataHealth(dataset.manifest.session_date, started_at=start)
    health.mark_ready(occurred_at=start, evidence="validated_fixture")
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
        assert ingestor.ingest(envelope).projection_applied
        if isinstance(envelope.payload, TickEvent):
            current = envelope.payload
    assert current is not None
    return FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(
        current,
        FeatureEvaluationContext(
            data_health=health.snapshot(),
            tick_coverage_started_at=coverage_started_at,
            aggressor_mapping_verified=verified,
        ),
    )


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.fromisoformat(
        f"2026-08-18T{hour:02d}:{minute:02d}:{second:02d}+08:00"
    )


def opening_snapshot(as_of: datetime, *, future_context: bool = False):
    session_date = as_of.date()
    references = InstrumentReferenceStore(session_date)
    references.put(
        InstrumentReference(
            symbol="8039",
            exchange="TSE",
            session_date=session_date,
            reference_price=Decimal("258.5"),
            limit_up_price=Decimal("284.5"),
            limit_down_price=Decimal("232.5"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=session_date,
        )
    )
    bars = IntradayBarStore(session_date, retention=timedelta(minutes=20))
    books = OrderBookStore(session_date, retention=timedelta(minutes=20))
    first_time = as_of - timedelta(minutes=2)
    first = TickEvent(
        event_id="opening-first",
        source=MarketEventSource.REPLAY,
        symbol="8039",
        session_date=session_date,
        event_time=first_time,
        received_at=first_time,
        ingress_sequence=1,
        price=Decimal("270"),
        tick_volume_lots=100,
        total_volume_lots=100,
        average_price=Decimal("269"),
        intraday_high=Decimal("270"),
        intraday_low=Decimal("260"),
        raw_tick_type=0,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=50,
        sell_aggressor_total_lots=50,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    current = replace(
        first,
        event_id="opening-current",
        event_time=as_of,
        received_at=as_of,
        ingress_sequence=2,
        price=Decimal("278"),
        tick_volume_lots=900,
        total_volume_lots=1000,
        average_price=Decimal("270"),
        intraday_high=Decimal("278"),
        buy_aggressor_total_lots=650,
        sell_aggressor_total_lots=350,
    )
    assert bars.apply(first).projection_applied
    assert bars.apply(current).projection_applied
    health = DataHealth(session_date, started_at=first_time)
    health.mark_ready(occurred_at=as_of, evidence="opening_fixture")
    context_time = as_of + timedelta(seconds=1) if future_context else as_of
    context = FeatureEvaluationContext(
        data_health=health.snapshot(),
        tick_coverage_started_at=first_time,
        aggressor_mapping_verified=True,
        opening_volume_context=OpeningVolumeContext(
            mode=OpeningVolumeContextMode.HISTORICAL_ELAPSED_TIME_RVOL.value,
            value=FeatureValue(
                value=Decimal("1.7"),
                status=FeatureStatus.VALID,
                source_as_of=context_time,
            ),
            provenance="synthetic historical elapsed-time profile",
        ),
    )
    return FeatureEngine(
        references=references,
        bars=bars,
        books=books,
    ).evaluate(current, context)


def configured_opening_engine() -> MomentumSignalEngine:
    opening = replace(
        OPENING_MOMENTUM_HYPOTHESIS_V0,
        opening_volume_context_mode=(
            OpeningVolumeContextMode.HISTORICAL_ELAPSED_TIME_RVOL
        ),
    )
    return MomentumSignalEngine(opening_config=opening)


def test_screenshot_only_8039_is_80_but_insufficient_data():
    snapshot = replay_snapshot(
        "8039_2026-08-18_phase2_replay.json",
        at(9, 16),
    )
    result = MomentumSignalEngine().evaluate(snapshot)

    assert result.signal_family is SignalFamily.LIMIT_UP_MOMENTUM
    assert result.evidence_score == 80
    assert result.evaluation_status is SignalEvaluationStatus.INSUFFICIENT_DATA
    assert result.momentum_acceleration_confirmed is False
    volume = next(
        detail
        for detail in result.details
        if detail.rule == "volume_acceleration_2m"
    )
    assert volume.status is EvidenceStatus.MISSING
    assert volume.points_awarded == 0


def test_enriched_8039_is_100_and_limit_up_momentum():
    snapshot = replay_snapshot(
        "8039_2026-08-18_phase3_enriched_replay.json",
        at(9, 6),
    )
    result = MomentumSignalEngine().evaluate(snapshot)

    assert result.signal is MomentumSignal.LIMIT_UP_MOMENTUM
    assert result.evaluation_status is SignalEvaluationStatus.TRIGGERED
    assert result.evidence_score == 100
    assert result.evidence_max_score == 100
    assert result.passed_rule_count == 6
    assert result.coverage == 1.0
    assert result.momentum_acceleration_confirmed is True
    assert result.triggered_signals == (
        MomentumSignal.BREAKOUT,
        MomentumSignal.VOLUME_ACCELERATION,
        MomentumSignal.MOMENTUM_ACCELERATION,
        MomentumSignal.LIMIT_UP_MOMENTUM,
    )


def test_unverified_external_ratio_loses_ten_points_without_being_faked():
    snapshot = replay_snapshot(
        "8039_2026-08-18_phase3_enriched_replay.json",
        at(9, 6),
        verified=False,
    )
    result = MomentumSignalEngine().evaluate(snapshot)

    assert result.evidence_score == 90
    assert result.evaluation_status is SignalEvaluationStatus.TRIGGERED
    assert result.coverage == pytest.approx(5 / 6)
    external = next(
        detail
        for detail in result.details
        if detail.rule == "external_ratio_rising"
    )
    assert external.status is EvidenceStatus.UNVERIFIED
    assert external.passed is None


def test_evidence_score_gate_is_inclusive_at_70_and_rejects_69():
    snapshot = replay_snapshot(
        "8039_2026-08-18_phase3_enriched_replay.json",
        at(9, 6),
    )
    score_70_snapshot = replace(
        snapshot,
        volume_acceleration_2m=replace(
            snapshot.volume_acceleration_2m,
            value=Decimal("1"),
        ),
        external_ratio_session=replace(
            snapshot.external_ratio_session,
            value=Decimal("0.50"),
        ),
    )
    score_70 = MomentumSignalEngine().evaluate(score_70_snapshot)
    weights_69 = tuple(
        EvidenceWeight(item.rule, 19 if item.rule == "breakout" else item.points)
        for item in LIMIT_UP_MOMENTUM_HYPOTHESIS_V0.weights
    )
    config_69 = replace(
        LIMIT_UP_MOMENTUM_HYPOTHESIS_V0,
        weights=weights_69,
    )
    score_69 = MomentumSignalEngine(limit_up_config=config_69).evaluate(
        score_70_snapshot
    )

    assert score_70.evidence_score == 70
    assert score_70.evaluation_status is SignalEvaluationStatus.TRIGGERED
    assert score_69.evidence_score == 69
    assert score_69.evaluation_status is SignalEvaluationStatus.NOT_TRIGGERED


def test_feature_and_signal_replay_digest_is_stable_across_ten_runs():
    digests = {
        MomentumSignalEngine()
        .evaluate(
            replay_snapshot(
                "8039_2026-08-18_phase3_enriched_replay.json",
                at(9, 6),
            )
        )
        .digest
        for _ in range(10)
    }

    assert len(digests) == 1


@pytest.mark.parametrize("as_of", [at(9, 3), at(9, 9, 59)])
def test_opening_family_can_confirm_acceleration_before_handoff(as_of):
    result = configured_opening_engine().evaluate(opening_snapshot(as_of))

    assert result.signal_family is SignalFamily.OPENING_MOMENTUM
    assert result.signal is MomentumSignal.OPENING_MOMENTUM
    assert result.evaluation_status is SignalEvaluationStatus.TRIGGERED
    assert result.momentum_acceleration_confirmed is True
    assert result.evidence_score == 100


def test_exact_0910_handoff_uses_limit_family_and_requires_rolling_baseline():
    result = configured_opening_engine().evaluate(opening_snapshot(at(9, 10)))

    assert result.signal_family is SignalFamily.LIMIT_UP_MOMENTUM
    assert result.evaluation_status is SignalEvaluationStatus.INSUFFICIENT_DATA
    assert result.momentum_acceleration_confirmed is False


def test_unresolved_opening_mode_fails_closed_even_with_supplied_context():
    result = MomentumSignalEngine().evaluate(opening_snapshot(at(9, 3)))

    assert result.evaluation_status is SignalEvaluationStatus.INSUFFICIENT_DATA
    assert "opening_volume_context_mode_unconfigured" in result.block_reasons


def test_future_opening_context_cannot_trigger():
    result = configured_opening_engine().evaluate(
        opening_snapshot(at(9, 3), future_context=True)
    )

    assert result.evaluation_status is SignalEvaluationStatus.INSUFFICIENT_DATA
    assert result.momentum_acceleration_confirmed is False


@pytest.mark.parametrize(
    ("rule", "attribute", "at_threshold", "below_or_above"),
    [
        ("return_2m", "return_2m", Decimal("0.015"), Decimal("0.014999")),
        (
            "distance_to_limit",
            "distance_to_limit",
            Decimal("0.03"),
            Decimal("0.030001"),
        ),
        (
            "volume_acceleration_2m",
            "volume_acceleration_2m",
            Decimal("1.5"),
            Decimal("1.499"),
        ),
    ],
)
def test_v0_decimal_thresholds_are_inclusive(
    rule,
    attribute,
    at_threshold,
    below_or_above,
):
    base = replay_snapshot(
        "8039_2026-08-18_phase3_enriched_replay.json",
        at(9, 6),
    )
    original = getattr(base, attribute)
    exact = replace(
        base,
        **{attribute: replace(original, value=at_threshold)},
    )
    miss = replace(
        base,
        **{attribute: replace(original, value=below_or_above)},
    )
    exact_detail = next(
        item
        for item in MomentumSignalEngine().evaluate(exact).details
        if item.rule == rule
    )
    miss_detail = next(
        item
        for item in MomentumSignalEngine().evaluate(miss).details
        if item.rule == rule
    )

    assert exact_detail.passed is True
    assert miss_detail.passed is False
