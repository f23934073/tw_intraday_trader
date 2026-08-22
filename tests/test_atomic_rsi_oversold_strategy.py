from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.entries.rsi_oversold import RsiOversoldEntryStrategy
from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.protocol import AtomicEvaluationStatus, AtomicStrategyContext
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_strategy_adapter import resolve_atomic_entry_set
from backtest.domain import HistoricalBar
from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
from backtest.indicators import relative_strength_index
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


def _bar(minute: int, price: str) -> HistoricalBar:
    close = Decimal(price)
    return HistoricalBar(
        symbol="2330",
        timestamp=datetime(2026, 8, 24, 9, minute, tzinfo=TAIPEI),
        open=close,
        high=close,
        low=close,
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


def _snapshot(prices: tuple[str, ...], *, period: int = 14):
    request = FeatureRequestSpec("wilder_rsi_v1", {"rsi_period": period})
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    result = None
    for minute, price in enumerate(prices):
        bar = _bar(minute, price)
        result = adapter.normalize(_context(bar, bars_seen=minute + 1))
    assert result is not None
    return result


def _tick(minute: int, price: str, *, sequence: int) -> TickEvent:
    occurred_at = datetime(2026, 8, 24, 9, minute, 1, tzinfo=TAIPEI)
    decimal_price = Decimal(price)
    return TickEvent(
        event_id=f"rsi-tick-{minute}-{sequence}",
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
    template = RsiOversoldEntryStrategy.template
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
        strategy_version_id="rsi-oversold:v1",
        strategy_id=template.strategy_id,
        source_draft_id="draft-rsi-oversold-v1",
        version_number=1,
        parameters=canonical,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(canonical),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=configuration_digest,
        change_note="RSI oversold golden test",
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


def test_rsi_template_schema_and_request_are_parameterized() -> None:
    template = RsiOversoldEntryStrategy.template
    parameters = template.validate_parameters(
        {
            "rsi_period": 14,
            "oversold_threshold": "30",
            "entry_window_start": "09:15",
            "entry_window_end": "12:45",
        }
    )
    requests = resolve_feature_requests(template, parameters)
    FeatureSpecificationRegistry().validate_requests(requests)

    assert requests[0].feature_id == "wilder_rsi_v1"
    assert requests[0].parameters == {"rsi_period": 14}
    assert set(template.runtime_bindings) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }
    with pytest.raises(ValueError, match="oversold_threshold 大於 maximum"):
        template.validate_parameters({"oversold_threshold": "51"})


def test_wilder_rsi_golden_all_up_all_down_and_flat() -> None:
    all_up = _snapshot(tuple(str(100 + index) for index in range(15)))
    all_down = _snapshot(tuple(str(100 - index) for index in range(15)))
    flat = _snapshot(("100",) * 15)

    assert all_up.values["wilder_rsi_v1"] == "100"
    assert all_down.values["wilder_rsi_v1"] == "0"
    assert flat.values["wilder_rsi_v1"] == "50"


def test_wilder_rsi_requires_period_plus_one_bars() -> None:
    snapshot = _snapshot(tuple(str(100 - index) for index in range(14)))

    assert snapshot.values["wilder_rsi_v1"] is None
    assert snapshot.missing_reasons["wilder_rsi_v1"] == "rsi_warmup_incomplete"


def test_wilder_rsi_non_default_period_uses_full_recurrence() -> None:
    raw_prices = ("100", "99", "98", "99", "100")
    snapshot = _snapshot(raw_prices, period=3)

    legacy_result = relative_strength_index(
        tuple(Decimal(item) for item in raw_prices),
        3,
    )
    assert legacy_result is not None
    assert Decimal(snapshot.values["wilder_rsi_v1"]) == legacy_result
    expected = Decimal(500) / Decimal(9)
    assert abs(legacy_result - expected) < Decimal("1e-24")


def test_completed_kbar_rsi_rejects_middle_session_gap() -> None:
    request = FeatureRequestSpec("wilder_rsi_v1", {"rsi_period": 14})
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for index, minute in enumerate((*range(7), *range(8, 16)), start=1):
        bar = _bar(minute, str(100 - index))
        snapshot = adapter.normalize(_context(bar, bars_seen=index))

    assert snapshot is not None
    assert snapshot.values["wilder_rsi_v1"] is None
    assert snapshot.missing_reasons["wilder_rsi_v1"] == (
        "rsi_session_kbars_non_contiguous"
    )


def test_rsi_strategy_threshold_is_inclusive() -> None:
    strategy = RsiOversoldEntryStrategy()
    as_of = datetime(2026, 8, 24, 9, 15, tzinfo=TAIPEI)

    def evaluate(value: str):
        features = NormalizedFeatureSnapshot(
            symbol="2330",
            session=SESSION_DATE.isoformat(),
            as_of=as_of,
            adapter_identity="rsi-boundary-test",
            values={"wilder_rsi_v1": value},
            input_digest=f"rsi-{value}",
        )
        return strategy.evaluate(
            AtomicStrategyContext(
                strategy_version_id="rsi-oversold:v1",
                symbol="2330",
                event_at=as_of,
                current_price="95",
                parameters={
                    "rsi_period": 14,
                    "oversold_threshold": "30",
                    "entry_window_start": "09:15",
                    "entry_window_end": "12:45",
                },
                features=features,
            )
        )

    assert evaluate("30").status is AtomicEvaluationStatus.TRIGGERED
    assert evaluate("30.0001").status is AtomicEvaluationStatus.NOT_TRIGGERED


def test_rsi_exact_version_snapshot_preserves_feature_identity() -> None:
    version = _version(
        {
            "rsi_period": 14,
            "oversold_threshold": "30",
            "entry_window_start": "09:15",
            "entry_window_end": "12:45",
        }
    )
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-rsi-v1",
        strategy_set_id="set-rsi",
        version_number=1,
        display_name_zh_tw="RSI oversold golden set",
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

    assert request["feature_id"] == "wilder_rsi_v1"
    assert request["parameters"] == {"rsi_period": 14}
    assert len(request["specification_digest"]) == 64
    assert len(request["runtime_identity_digest"]) == 64


def test_local_paper_rsi_projection_uses_existing_feature_engine() -> None:
    bars = IntradayBarStore(
        SESSION_DATE,
        retention=timedelta(minutes=20),
        bar_retention=timedelta(hours=6),
    )
    engine = FeatureEngine(
        references=InstrumentReferenceStore(SESSION_DATE),
        bars=bars,
        books=OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20)),
    )
    current = None
    for sequence, minute in enumerate(range(16), start=1):
        current = _tick(minute, str(100 - minute), sequence=sequence)
        bars.apply(current)
    assert current is not None

    request = FeatureRequestSpec("wilder_rsi_v1", {"rsi_period": 14})
    projection = engine.evaluate_requests(current, (request,))[0]

    assert projection.value.status is FeatureStatus.VALID
    assert projection.value.value == Decimal("0")
    assert projection.request_digest == request.request_digest
    assert projection.evidence["average_gain"] == "0"
    assert Decimal(projection.evidence["average_loss"]) > 0


def test_atomic_registry_exposes_rsi_as_one_independent_strategy() -> None:
    implementation = AtomicStrategyRegistry().strategy("rsi_oversold_entry")

    assert isinstance(implementation, RsiOversoldEntryStrategy)
    assert implementation.template.display_name_zh_tw == "RSI 超賣"
