from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.entries.bollinger_lower_reentry import (
    BollingerLowerReentryEntryStrategy,
)
from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.protocol import AtomicEvaluationStatus, AtomicStrategyContext
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_strategy_adapter import resolve_atomic_entry_set
from backtest.domain import HistoricalBar
from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
from backtest.indicators import bollinger_bands
from features.bollinger import (
    BollingerBar,
    evaluate_bollinger_lower_reentry,
    lower_band_reentry_triggered,
)
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


def _snapshot(
    prices: tuple[str, ...],
    *,
    period: int = 20,
    multiplier: str = "2",
):
    request = FeatureRequestSpec(
        "bollinger_lower_reentry_v1",
        {
            "bollinger_period": period,
            "stddev_multiplier": multiplier,
        },
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    result = None
    for minute, price in enumerate(prices):
        bar = _bar(minute, price)
        result = adapter.normalize(_context(bar, bars_seen=minute + 1))
    assert result is not None
    return result


def _feature(
    prices: tuple[str, ...],
    *,
    period: int = 20,
    multiplier: str = "2",
):
    bars = tuple(
        BollingerBar(
            timestamp=datetime(2026, 8, 24, 9, minute, tzinfo=TAIPEI),
            close=Decimal(price),
        )
        for minute, price in enumerate(prices)
    )
    return evaluate_bollinger_lower_reentry(
        {
            "bollinger_period": period,
            "stddev_multiplier": multiplier,
        },
        bars,
    )


def _tick(minute: int, price: str, *, sequence: int) -> TickEvent:
    occurred_at = datetime(2026, 8, 24, 9, minute, 1, tzinfo=TAIPEI)
    decimal_price = Decimal(price)
    return TickEvent(
        event_id=f"bollinger-tick-{minute}-{sequence}",
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
    template = BollingerLowerReentryEntryStrategy.template
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
        strategy_version_id="bollinger-lower-reentry:v1",
        strategy_id=template.strategy_id,
        source_draft_id="draft-bollinger-lower-reentry-v1",
        version_number=1,
        parameters=canonical,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(canonical),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=configuration_digest,
        change_note="Bollinger lower-band re-entry golden test",
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


def test_bollinger_template_schema_and_request_are_parameterized() -> None:
    template = BollingerLowerReentryEntryStrategy.template
    parameters = template.validate_parameters(
        {
            "bollinger_period": 20,
            "stddev_multiplier": "2",
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        }
    )
    requests = resolve_feature_requests(template, parameters)
    FeatureSpecificationRegistry().validate_requests(requests)

    assert requests[0].feature_id == "bollinger_lower_reentry_v1"
    assert requests[0].parameters == {
        "bollinger_period": 20,
        "stddev_multiplier": "2",
    }
    assert set(template.runtime_bindings) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }
    with pytest.raises(ValueError, match="stddev_multiplier 小於 minimum"):
        template.validate_parameters({"stddev_multiplier": "0"})


def test_bollinger_population_variance_matches_existing_formula() -> None:
    prices = tuple(Decimal(item) for item in ("100", "102", "101", "99", "100"))
    result = _feature(tuple(str(item) for item in prices), period=4, multiplier="1.5")
    previous = bollinger_bands(prices[:-1], 4, Decimal("1.5"))
    current = bollinger_bands(prices[1:], 4, Decimal("1.5"))

    assert previous is not None
    assert current is not None
    assert result.evidence["previous_middle_band"] == str(previous[0])
    assert result.evidence["previous_upper_band"] == str(previous[1])
    assert result.evidence["previous_lower_band"] == str(previous[2])
    assert result.evidence["current_middle_band"] == str(current[0])
    assert result.evidence["current_upper_band"] == str(current[1])
    assert result.evidence["current_lower_band"] == str(current[2])


def test_bollinger_zero_variance_is_stable_and_not_triggered() -> None:
    result = _feature(("100",) * 21)

    assert result.value is False
    assert result.evidence["previous_lower_band"] == "100"
    assert result.evidence["current_lower_band"] == "100"


def test_bollinger_reentry_triggers_once_on_default_pattern() -> None:
    prices = ("100",) * 19 + ("80", "100")
    triggered = _snapshot(prices)
    no_repeat = _snapshot(prices + ("100",))

    assert triggered.values["bollinger_lower_reentry_v1"] is True
    assert no_repeat.values["bollinger_lower_reentry_v1"] is False


def test_bollinger_reentry_boundaries_are_strict_then_inclusive() -> None:
    assert lower_band_reentry_triggered(
        previous_close=Decimal("99"),
        previous_lower_band=Decimal("100"),
        current_close=Decimal("101"),
        current_lower_band=Decimal("101"),
    )
    assert not lower_band_reentry_triggered(
        previous_close=Decimal("100"),
        previous_lower_band=Decimal("100"),
        current_close=Decimal("101"),
        current_lower_band=Decimal("101"),
    )


def test_bollinger_strategy_consumes_boolean_reentry_event() -> None:
    strategy = BollingerLowerReentryEntryStrategy()
    as_of = datetime(2026, 8, 24, 9, 21, tzinfo=TAIPEI)

    def evaluate(value: object):
        features = NormalizedFeatureSnapshot(
            symbol="2330",
            session=SESSION_DATE.isoformat(),
            as_of=as_of,
            adapter_identity="bollinger-kernel-test",
            values={"bollinger_lower_reentry_v1": value},
            input_digest=f"bollinger-{value}",
        )
        return strategy.evaluate(
            AtomicStrategyContext(
                strategy_version_id="bollinger-lower-reentry:v1",
                symbol="2330",
                event_at=as_of,
                current_price="100",
                parameters={
                    "bollinger_period": 20,
                    "stddev_multiplier": "2",
                    "entry_window_start": "09:20",
                    "entry_window_end": "12:45",
                },
                features=features,
            )
        )

    assert evaluate(True).status is AtomicEvaluationStatus.TRIGGERED
    assert evaluate(False).status is AtomicEvaluationStatus.NOT_TRIGGERED
    assert evaluate("true").status is AtomicEvaluationStatus.INSUFFICIENT_DATA


def test_bollinger_requires_period_plus_one_bars() -> None:
    snapshot = _snapshot(("100",) * 20)

    assert snapshot.values["bollinger_lower_reentry_v1"] is None
    assert snapshot.missing_reasons["bollinger_lower_reentry_v1"] == (
        "bollinger_warmup_incomplete"
    )


def test_completed_kbar_bollinger_rejects_middle_session_gap() -> None:
    request = FeatureRequestSpec(
        "bollinger_lower_reentry_v1",
        {"bollinger_period": 20, "stddev_multiplier": "2"},
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for index, minute in enumerate((*range(10), *range(11, 22)), start=1):
        bar = _bar(minute, "100")
        snapshot = adapter.normalize(_context(bar, bars_seen=index))

    assert snapshot is not None
    assert snapshot.values["bollinger_lower_reentry_v1"] is None
    assert snapshot.missing_reasons["bollinger_lower_reentry_v1"] == (
        "bollinger_session_kbars_non_contiguous"
    )


def test_bollinger_exact_version_snapshot_preserves_feature_identity() -> None:
    version = _version(
        {
            "bollinger_period": 20,
            "stddev_multiplier": "2",
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        }
    )
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-bollinger-v1",
        strategy_set_id="set-bollinger",
        version_number=1,
        display_name_zh_tw="Bollinger lower re-entry golden set",
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

    assert request["feature_id"] == "bollinger_lower_reentry_v1"
    assert request["parameters"] == {
        "bollinger_period": 20,
        "stddev_multiplier": "2",
    }
    assert len(request["specification_digest"]) == 64
    assert len(request["runtime_identity_digest"]) == 64


def test_local_paper_bollinger_projection_uses_existing_feature_engine() -> None:
    bars = IntradayBarStore(
        SESSION_DATE,
        retention=timedelta(minutes=30),
        bar_retention=timedelta(hours=6),
    )
    engine = FeatureEngine(
        references=InstrumentReferenceStore(SESSION_DATE),
        bars=bars,
        books=OrderBookStore(SESSION_DATE, retention=timedelta(minutes=30)),
    )
    prices = ("100",) * 19 + ("80", "100", "100")
    current = None
    for sequence, (minute, price) in enumerate(enumerate(prices), start=1):
        current = _tick(minute, price, sequence=sequence)
        bars.apply(current)
    assert current is not None

    request = FeatureRequestSpec(
        "bollinger_lower_reentry_v1",
        {"bollinger_period": 20, "stddev_multiplier": "2"},
    )
    projection = engine.evaluate_requests(current, (request,))[0]

    assert projection.value.status is FeatureStatus.VALID
    assert projection.value.value is True
    assert projection.request_digest == request.request_digest
    assert projection.evidence["previous_close"] == "80"
    assert projection.evidence["current_close"] == "100"


def test_atomic_registry_exposes_bollinger_as_independent_strategy() -> None:
    implementation = AtomicStrategyRegistry().strategy(
        "bollinger_lower_reentry_entry"
    )

    assert isinstance(implementation, BollingerLowerReentryEntryStrategy)
    assert implementation.template.display_name_zh_tw == "Bollinger 下軌回歸"
