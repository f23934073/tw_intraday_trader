from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.entries.opening_range_breakout import (
    OpeningRangeBreakoutEntryStrategy,
)
from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.protocol import AtomicEvaluationStatus, AtomicStrategyContext
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_strategy_adapter import resolve_atomic_entry_set
from backtest.domain import HistoricalBar
from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
from features.engine import FeatureEngine
from features.models import FeatureStatus
from features.specifications import (
    FeatureRequestSpec,
    FeatureSpecificationRegistry,
    NormalizedFeatureSnapshot,
)
from market_data.events import AggressorSide, MarketEventSource, TickEvent
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.order_book_store import OrderBookStore
from strategy_catalog.domain import StrategyRole
from strategy_catalog.drafts import StrategyVersion
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 24)


def _bar(minute: int, price: str, *, high: str | None = None) -> HistoricalBar:
    close = Decimal(price)
    resolved_high = Decimal(high) if high is not None else close
    return HistoricalBar(
        symbol="2330",
        timestamp=datetime(2026, 8, 24, 9, minute, tzinfo=TAIPEI),
        open=close,
        high=max(close, resolved_high),
        low=close - Decimal("0.5"),
        close=close,
        volume=100,
    )


def _context(bar: HistoricalBar, *, bars_seen: int) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=bar.symbol,
        bar=bar,
        resolved_session_date=SESSION_DATE,
        vwap=bar.close,
        session_high_before=None,
        cumulative_volume=bars_seen * 100,
        bars_seen=bars_seen,
    )


def _tick(minute: int, price: str, *, sequence: int) -> TickEvent:
    occurred_at = datetime(2026, 8, 24, 9, minute, 1, tzinfo=TAIPEI)
    decimal_price = Decimal(price)
    return TickEvent(
        event_id=f"orb-tick-{minute}-{sequence}",
        source=MarketEventSource.REPLAY,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=occurred_at,
        received_at=occurred_at,
        ingress_sequence=sequence,
        price=decimal_price,
        tick_volume_lots=100,
        total_volume_lots=sequence * 100,
        average_price=decimal_price,
        intraday_high=decimal_price,
        intraday_low=decimal_price,
        raw_tick_type=0,
        aggressor_side=AggressorSide.UNKNOWN,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )


def _version(parameters: dict[str, object]) -> StrategyVersion:
    template = OpeningRangeBreakoutEntryStrategy.template
    canonical = template.validate_parameters(parameters)
    now = datetime.now(timezone.utc)
    configuration_digest = canonical_digest(
        {
            "strategy_id": template.strategy_id,
            "parameters": canonical,
            "parameter_schema_version": template.parameter_schema.version,
            "parameter_schema_digest": template.parameter_schema.schema_digest,
            "parameters_digest": canonical_digest(canonical),
            "template_digest": template.template_digest,
            "implementation_digest": template.implementation_digest,
        }
    )
    return StrategyVersion(
        strategy_version_id="opening-range-breakout:v1",
        strategy_id=template.strategy_id,
        source_draft_id="draft-opening-range-breakout-v1",
        version_number=1,
        parameters=canonical,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(canonical),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=configuration_digest,
        change_note="ORB golden test",
        created_by="test",
        created_at=now,
        published_at=now,
    )


class _VersionRepository:
    def __init__(self, version: StrategyVersion) -> None:
        self._version = version

    def get_version(self, strategy_version_id: str) -> StrategyVersion:
        assert strategy_version_id == self._version.strategy_version_id
        return self._version


def test_orb_template_schema_and_request_are_parameterized() -> None:
    template = OpeningRangeBreakoutEntryStrategy.template
    parameters = template.validate_parameters(
        {
            "opening_range_minutes": 5,
            "breakout_buffer_pct": "0.2",
            "entry_window_start": "09:05",
            "entry_window_end": "11:00",
        }
    )
    requests = resolve_feature_requests(template, parameters)
    FeatureSpecificationRegistry().validate_requests(requests)

    assert parameters["breakout_buffer_pct"] == "0.2"
    assert requests[0].feature_id == "opening_range_high_v1"
    assert requests[0].parameters == {"opening_range_minutes": 5}
    assert set(template.runtime_bindings) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }
    with pytest.raises(ValueError, match="不可早於開盤區間完成時間"):
        template.validate_parameters(
            {
                "opening_range_minutes": 15,
                "entry_window_start": "09:10",
            }
        )


def test_completed_kbar_orb_requires_exact_contiguous_opening_range() -> None:
    request = FeatureRequestSpec(
        "opening_range_high_v1",
        {"opening_range_minutes": 5},
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for index, minute in enumerate((0, 1, 3, 4, 5), start=1):
        bar = _bar(minute, "100", high="105" if minute == 4 else "101")
        snapshot = adapter.normalize(_context(bar, bars_seen=index))

    assert snapshot is not None
    assert snapshot.values["opening_range_high_v1"] is None
    assert snapshot.missing_reasons["opening_range_high_v1"] == (
        "opening_range_kbars_non_contiguous"
    )


def test_orb_strategy_triggers_from_shared_completed_kbar_projection() -> None:
    request = FeatureRequestSpec(
        "opening_range_high_v1",
        {"opening_range_minutes": 5},
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    bars = tuple(
        _bar(minute, "102" if minute == 5 else "100", high="101")
        for minute in range(6)
    )
    for index, bar in enumerate(bars, start=1):
        snapshot = adapter.normalize(_context(bar, bars_seen=index))

    assert snapshot is not None
    evaluation = OpeningRangeBreakoutEntryStrategy().evaluate(
        AtomicStrategyContext(
            strategy_version_id="opening-range-breakout:v1",
            symbol="2330",
            event_at=bars[-1].timestamp,
            current_price="102",
            parameters={
                "opening_range_minutes": 5,
                "breakout_buffer_pct": "0.5",
                "entry_window_start": "09:05",
                "entry_window_end": "11:00",
            },
            features=snapshot,
        )
    )

    assert snapshot.values["opening_range_high_v1"] == "101"
    assert evaluation.status is AtomicEvaluationStatus.TRIGGERED
    assert evaluation.threshold["breakout_price"] == "101.505"

    not_triggered = OpeningRangeBreakoutEntryStrategy().evaluate(
        AtomicStrategyContext(
            strategy_version_id="opening-range-breakout:v1",
            symbol="2330",
            event_at=bars[-1].timestamp,
            current_price="101.5",
            parameters={
                "opening_range_minutes": 5,
                "breakout_buffer_pct": "0.5",
                "entry_window_start": "09:05",
                "entry_window_end": "11:00",
            },
            features=snapshot,
        )
    )
    assert not_triggered.status is AtomicEvaluationStatus.NOT_TRIGGERED


def test_orb_breakout_threshold_is_strict() -> None:
    features = NormalizedFeatureSnapshot(
        symbol="2330",
        session=SESSION_DATE.isoformat(),
        as_of=datetime(2026, 8, 24, 9, 15, tzinfo=TAIPEI),
        adapter_identity="orb-boundary-test",
        values={"opening_range_high_v1": "100"},
        input_digest="orb-boundary-input",
    )
    strategy = OpeningRangeBreakoutEntryStrategy()

    equal_to_high = strategy.evaluate(
        AtomicStrategyContext(
            strategy_version_id="opening-range-breakout:v1",
            symbol="2330",
            event_at=features.as_of,
            current_price="100",
            parameters={
                "opening_range_minutes": 15,
                "breakout_buffer_pct": "0",
                "entry_window_start": "09:15",
                "entry_window_end": "11:00",
            },
            features=features,
        )
    )
    strictly_above_buffered_threshold = strategy.evaluate(
        AtomicStrategyContext(
            strategy_version_id="opening-range-breakout:v1",
            symbol="2330",
            event_at=features.as_of,
            current_price="100.5001",
            parameters={
                "opening_range_minutes": 15,
                "breakout_buffer_pct": "0.5",
                "entry_window_start": "09:15",
                "entry_window_end": "11:00",
            },
            features=features,
        )
    )

    assert equal_to_high.status is AtomicEvaluationStatus.NOT_TRIGGERED
    assert equal_to_high.threshold["breakout_price"] == "100"
    assert (
        strictly_above_buffered_threshold.status
        is AtomicEvaluationStatus.TRIGGERED
    )
    assert strictly_above_buffered_threshold.threshold["breakout_price"] == (
        "100.500"
    )


def test_orb_exact_version_snapshot_preserves_feature_identity() -> None:
    version = _version(
        {
            "opening_range_minutes": 5,
            "breakout_buffer_pct": "0.5",
            "entry_window_start": "09:05",
            "entry_window_end": "11:00",
        }
    )
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-orb-v1",
        strategy_set_id="set-orb",
        version_number=1,
        display_name_zh_tw="ORB golden set",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(
            StrategySetMemberSnapshot(
                strategy_version_id=version.strategy_version_id,
                strategy_id=version.strategy_id,
                role=StrategyRole.ENTRY,
                configuration_digest=version.configuration_digest,
                implementation_digest=version.implementation_digest,
                member_order=0,
                attribution_priority=0,
            ),
        ),
    )
    resolved = resolve_atomic_entry_set(
        _VersionRepository(version),
        AtomicStrategyRegistry(),
        snapshot,
    )
    request = resolved.run_snapshot["feature_requests"][0]["requests"][0]

    assert request["feature_id"] == "opening_range_high_v1"
    assert request["parameters"] == {"opening_range_minutes": 5}
    assert len(request["specification_digest"]) == 64
    assert len(request["runtime_identity_digest"]) == 64


def test_local_paper_orb_projection_uses_existing_feature_engine() -> None:
    bars = IntradayBarStore(
        SESSION_DATE,
        retention=timedelta(minutes=20),
        bar_retention=timedelta(hours=6),
    )
    engine = FeatureEngine(
        references=InstrumentReferenceStore(SESSION_DATE),
        bars=bars,
        books=OrderBookStore(
            SESSION_DATE,
            retention=timedelta(minutes=20),
        ),
    )
    current = None
    for sequence, minute in enumerate(range(7), start=1):
        current = _tick(
            minute,
            "105" if minute == 4 else ("102" if minute == 6 else "100"),
            sequence=sequence,
        )
        bars.apply(current)
    assert current is not None

    request = FeatureRequestSpec(
        "opening_range_high_v1",
        {"opening_range_minutes": 5},
    )
    projection = engine.evaluate_requests(current, (request,))[0]

    assert projection.value.status is FeatureStatus.VALID
    assert projection.value.value == Decimal("105")
    assert projection.request_digest == request.request_digest
    assert projection.evidence["opening_range_bar_count"] == 5


def test_local_paper_orb_projection_rejects_missing_opening_minute() -> None:
    bars = IntradayBarStore(
        SESSION_DATE,
        retention=timedelta(minutes=20),
        bar_retention=timedelta(hours=6),
    )
    engine = FeatureEngine(
        references=InstrumentReferenceStore(SESSION_DATE),
        bars=bars,
        books=OrderBookStore(
            SESSION_DATE,
            retention=timedelta(minutes=20),
        ),
    )
    current = None
    for sequence, minute in enumerate((0, 1, 3, 4, 5, 6), start=1):
        current = _tick(minute, "100", sequence=sequence)
        bars.apply(current)
    assert current is not None

    request = FeatureRequestSpec(
        "opening_range_high_v1",
        {"opening_range_minutes": 5},
    )
    projection = engine.evaluate_requests(current, (request,))[0]

    assert projection.value.status is FeatureStatus.MISSING
    assert projection.value.reason == "opening_range_kbars_non_contiguous"


def test_atomic_registry_exposes_orb_as_one_independent_strategy() -> None:
    implementation = AtomicStrategyRegistry().strategy(
        "opening_range_breakout_entry"
    )

    assert isinstance(implementation, OpeningRangeBreakoutEntryStrategy)
    assert implementation.template.display_name_zh_tw == "開盤區間突破 ORB"
