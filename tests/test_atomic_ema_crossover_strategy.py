from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.entries.ema_crossover import EmaCrossoverEntryStrategy
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


def _tick(minute: int, price: str, *, sequence: int) -> TickEvent:
    occurred_at = datetime(2026, 8, 24, 9, minute, 1, tzinfo=TAIPEI)
    decimal_price = Decimal(price)
    return TickEvent(
        event_id=f"ema-tick-{minute}-{sequence}",
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
    template = EmaCrossoverEntryStrategy.template
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
        strategy_version_id="ema-crossover:v1",
        strategy_id=template.strategy_id,
        source_draft_id="draft-ema-crossover-v1",
        version_number=1,
        parameters=canonical,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(canonical),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=configuration_digest,
        change_note="EMA crossover golden test",
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


def test_ema_template_schema_and_request_are_parameterized() -> None:
    template = EmaCrossoverEntryStrategy.template
    parameters = template.validate_parameters(
        {
            "fast_period": 5,
            "slow_period": 20,
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        }
    )
    requests = resolve_feature_requests(template, parameters)
    FeatureSpecificationRegistry().validate_requests(requests)

    assert requests[0].feature_id == "ema_cross_up_v1"
    assert requests[0].parameters == {"fast_period": 5, "slow_period": 20}
    assert set(template.runtime_bindings) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }
    with pytest.raises(ValueError, match="fast_period 必須小於 slow_period"):
        template.validate_parameters({"fast_period": 20, "slow_period": 20})


def test_completed_kbar_ema_triggers_once_on_cross_up() -> None:
    request = FeatureRequestSpec(
        "ema_cross_up_v1",
        {"fast_period": 5, "slow_period": 20},
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for index in range(22):
        bar = _bar(index, "100" if index < 20 else str(81 + index))
        snapshot = adapter.normalize(_context(bar, bars_seen=index + 1))
        if index < 20:
            assert snapshot.values["ema_cross_up_v1"] is None

    assert snapshot is not None
    assert snapshot.values["ema_cross_up_v1"] is False

    crossing_adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    crossing_snapshot = None
    for index in range(21):
        bar = _bar(index, "100" if index < 20 else "101")
        crossing_snapshot = crossing_adapter.normalize(
            _context(bar, bars_seen=index + 1)
        )
    assert crossing_snapshot is not None
    assert crossing_snapshot.values["ema_cross_up_v1"] is True


def test_completed_kbar_ema_rejects_middle_session_gap() -> None:
    request = FeatureRequestSpec(
        "ema_cross_up_v1",
        {"fast_period": 5, "slow_period": 20},
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for index, minute in enumerate((*range(10), *range(11, 22)), start=1):
        bar = _bar(minute, "100")
        snapshot = adapter.normalize(_context(bar, bars_seen=index))

    assert snapshot is not None
    assert snapshot.values["ema_cross_up_v1"] is None
    assert snapshot.missing_reasons["ema_cross_up_v1"] == (
        "ema_session_kbars_non_contiguous"
    )


def test_ema_strategy_consumes_boolean_crossing_without_retriggering() -> None:
    strategy = EmaCrossoverEntryStrategy()
    as_of = datetime(2026, 8, 24, 9, 20, tzinfo=TAIPEI)

    def evaluate(value: bool | None, missing_reason: str | None = None):
        features = NormalizedFeatureSnapshot(
            symbol="2330",
            session=SESSION_DATE.isoformat(),
            as_of=as_of,
            adapter_identity="ema-boundary-test",
            values={"ema_cross_up_v1": value},
            input_digest=f"ema-{value}",
            missing_reasons=(
                {"ema_cross_up_v1": missing_reason} if missing_reason else {}
            ),
        )
        return strategy.evaluate(
            AtomicStrategyContext(
                strategy_version_id="ema-crossover:v1",
                symbol="2330",
                event_at=as_of,
                current_price="101",
                parameters={
                    "fast_period": 5,
                    "slow_period": 20,
                    "entry_window_start": "09:20",
                    "entry_window_end": "12:45",
                },
                features=features,
            )
        )

    assert evaluate(True).status is AtomicEvaluationStatus.TRIGGERED
    assert evaluate(False).status is AtomicEvaluationStatus.NOT_TRIGGERED
    missing = evaluate(None, "ema_warmup_incomplete")
    assert missing.status is AtomicEvaluationStatus.INSUFFICIENT_DATA
    assert missing.reason == "ema_warmup_incomplete"


def test_ema_exact_version_snapshot_preserves_feature_identity() -> None:
    version = _version(
        {
            "fast_period": 5,
            "slow_period": 20,
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        }
    )
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-ema-v1",
        strategy_set_id="set-ema",
        version_number=1,
        display_name_zh_tw="EMA crossover golden set",
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

    assert request["feature_id"] == "ema_cross_up_v1"
    assert request["parameters"] == {"fast_period": 5, "slow_period": 20}
    assert len(request["specification_digest"]) == 64
    assert len(request["runtime_identity_digest"]) == 64


def test_local_paper_ema_projection_uses_existing_feature_engine() -> None:
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
    for sequence, minute in enumerate(range(22), start=1):
        current = _tick(
            minute,
            "100" if minute < 20 else "101",
            sequence=sequence,
        )
        bars.apply(current)
    assert current is not None

    request = FeatureRequestSpec(
        "ema_cross_up_v1",
        {"fast_period": 5, "slow_period": 20},
    )
    projection = engine.evaluate_requests(current, (request,))[0]

    assert projection.value.status is FeatureStatus.VALID
    assert projection.value.value is True
    assert projection.request_digest == request.request_digest
    assert projection.evidence["previous_fast_ema"] == "100"
    assert Decimal(projection.evidence["current_fast_ema"]) > Decimal(
        projection.evidence["current_slow_ema"]
    )


def test_atomic_registry_exposes_ema_as_one_independent_strategy() -> None:
    implementation = AtomicStrategyRegistry().strategy("ema_crossover_entry")

    assert isinstance(implementation, EmaCrossoverEntryStrategy)
    assert implementation.template.display_name_zh_tw == "EMA 黃金交叉"
