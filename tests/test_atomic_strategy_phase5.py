from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_strategy_adapter import resolve_atomic_entry_set
from backtest.domain import BacktestRunConfig, HistoricalBar, StrategySide
from backtest.engine import HistoricalBacktestEngine
from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
from features.specifications import FeatureRequestSpec
from strategy_catalog.domain import StrategyRole
from strategy_catalog.drafts import StrategyVersion
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _bar(
    minute: int,
    close: str,
    volume: int = 100,
    *,
    session_date: date = date(2026, 8, 21),
) -> HistoricalBar:
    price = Decimal(close)
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime.combine(
            session_date,
            datetime.min.time(),
            tzinfo=TAIPEI,
        ).replace(hour=9, minute=minute),
        open=price,
        high=price + Decimal("0.5"),
        low=price - Decimal("0.5"),
        close=price,
        volume=volume,
    )


def _version(
    strategy_id: str,
    version_id: str,
    parameters: dict,
) -> StrategyVersion:
    template = AtomicStrategyRegistry().strategy(strategy_id).template
    canonical = template.validate_parameters(parameters)
    configuration_digest = canonical_digest(
        {
            "strategy_id": strategy_id,
            "parameters": canonical,
            "parameter_schema_version": template.parameter_schema.version,
            "parameter_schema_digest": template.parameter_schema.schema_digest,
            "parameters_digest": canonical_digest(canonical),
            "template_digest": template.template_digest,
            "implementation_digest": template.implementation_digest,
        }
    )
    now = datetime.now(timezone.utc)
    return StrategyVersion(
        strategy_version_id=version_id,
        strategy_id=strategy_id,
        source_draft_id=f"draft-{version_id}",
        version_number=1,
        parameters=canonical,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(canonical),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=configuration_digest,
        change_note="Phase 5 golden test",
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


def _resolve(version: StrategyVersion):
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id=f"set-{version.strategy_version_id}",
        strategy_set_id=f"set-{version.strategy_id}",
        version_number=1,
        display_name_zh_tw="Phase 5 golden set",
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
    return resolve_atomic_entry_set(
        _VersionRepository(version),
        AtomicStrategyRegistry(),
        snapshot,
    )


def _config(resolved) -> BacktestRunConfig:
    return BacktestRunConfig(
        dataset_id="dataset-phase5-golden",
        dataset_digest="dataset-phase5-golden-digest",
        strategy_set=resolved.engine_strategy_set,
        engine_version="backtest-engine-v2",
        atomic_strategy_run_snapshot=resolved.run_snapshot,
        minimum_oos_trades=1,
    )


def test_completed_kbar_runtime_uses_parameterized_state_key_and_reset() -> None:
    request = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshots = []
    for index, close in enumerate(("100", "100", "100", "102")):
        bar = _bar(index, close)
        snapshots.append(
            adapter.normalize(
                SimpleNamespace(
                    symbol=bar.symbol,
                    bar=bar,
                    resolved_session_date=bar.session_date,
                    vwap=bar.close,
                    session_high_before=None,
                    cumulative_volume=(index + 1) * 100,
                    bars_seen=index + 1,
                )
            )
        )

    final = snapshots[-1]
    assert final.values["rolling_return_v1"] == "0.02"
    assert final.state_keys["rolling_return_v1"] == request.state_key(
        adapter_identity=adapter.identity,
        cadence="COMPLETED_KBAR_1M",
        symbol="2330",
        session="2026-08-21",
    )
    adapter.reset()
    restarted = adapter.normalize(
        SimpleNamespace(
            symbol="2330",
            bar=_bar(0, "100"),
            resolved_session_date=_bar(0, "100").session_date,
            vwap=Decimal("100"),
            session_high_before=None,
            cumulative_volume=100,
            bars_seen=1,
        )
    )
    assert restarted.values["rolling_return_v1"] is None


def test_completed_kbar_runtime_evicts_previous_sessions() -> None:
    request = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))

    first_session = date(2026, 1, 1)
    for offset in range(100):
        session_date = first_session + timedelta(days=offset)
        bar = _bar(0, "100", session_date=session_date)
        adapter.normalize(
            SimpleNamespace(
                symbol=bar.symbol,
                bar=bar,
                resolved_session_date=session_date,
                vwap=bar.close,
                session_high_before=None,
                cumulative_volume=100,
                bars_seen=1,
            )
        )

        assert adapter.active_session == session_date.isoformat()
        assert adapter.active_state_count == 1


def test_three_minute_return_version_drives_real_window_and_snapshot() -> None:
    version = _version(
        "rolling_return_entry",
        "rolling-return:v1",
        {
            "window_minutes": 3,
            "minimum_return_pct": "2",
            "entry_window_start": "09:00",
            "entry_window_end": "12:45",
        },
    )
    resolved = _resolve(version)
    bars = (
        _bar(0, "100"),
        _bar(1, "100"),
        _bar(2, "100"),
        _bar(3, "102"),
        _bar(4, "102"),
    )

    first = HistoricalBacktestEngine(resolved.registry).run(
        config=_config(resolved),
        bars=bars,
    )
    second = HistoricalBacktestEngine(resolved.registry).run(
        config=_config(resolved),
        bars=bars,
    )
    entry = next(item for item in first.decisions if item.side is StrategySide.ENTRY)
    request = resolved.run_snapshot["feature_requests"][0]["requests"][0]

    assert entry.triggered_strategy_ids == (version.strategy_version_id,)
    assert request["parameters"] == {"window_minutes": 3}
    assert first.to_dict() == second.to_dict()


def test_volume_acceleration_uses_current_window_over_prior_median() -> None:
    version = _version(
        "volume_acceleration_entry",
        "volume-acceleration:v1",
        {
            "window_minutes": 2,
            "baseline_window_count": 5,
            "minimum_complete_baseline_windows": 4,
            "baseline_method": "MEDIAN",
            "minimum_acceleration_ratio": "1.75",
            "entry_window_start": "09:00",
            "entry_window_end": "12:45",
        },
    )
    resolved = _resolve(version)
    bars = tuple(
        _bar(minute, "100", 200 if minute in {10, 11} else 100)
        for minute in range(13)
    )

    result = HistoricalBacktestEngine(resolved.registry).run(
        config=_config(resolved),
        bars=bars,
    )
    entry = next(item for item in result.decisions if item.side is StrategySide.ENTRY)

    assert entry.triggered_strategy_ids == (version.strategy_version_id,)
    assert entry.event_at.minute == 11
    assert entry.evaluations[0].observed["volume_acceleration_ratio"] == "2"


def test_volume_baseline_allows_only_oldest_warmup_suffix() -> None:
    request = FeatureRequestSpec(
        "rolling_volume_ratio_v1",
        {
            "window_minutes": 2,
            "baseline_window_count": 5,
            "minimum_complete_baseline_windows": 4,
            "baseline_method": "MEDIAN",
        },
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for minute in range(10):
        bar = _bar(minute, "100", 100)
        snapshot = adapter.normalize(
            SimpleNamespace(
                symbol=bar.symbol,
                bar=bar,
                resolved_session_date=bar.session_date,
                vwap=bar.close,
                session_high_before=None,
                cumulative_volume=(minute + 1) * 100,
                bars_seen=minute + 1,
            )
        )

    assert snapshot is not None
    assert snapshot.values["rolling_volume_ratio_v1"] == "1"
    assert "rolling_volume_ratio_v1" not in snapshot.missing_reasons


def test_volume_baseline_middle_gap_fails_closed() -> None:
    request = FeatureRequestSpec(
        "rolling_volume_ratio_v1",
        {
            "window_minutes": 2,
            "baseline_window_count": 5,
            "minimum_complete_baseline_windows": 4,
            "baseline_method": "MEDIAN",
        },
    )
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for minute in (*range(5), *range(6, 12)):
        bar = _bar(minute, "100", 200 if minute in {10, 11} else 100)
        snapshot = adapter.normalize(
            SimpleNamespace(
                symbol=bar.symbol,
                bar=bar,
                resolved_session_date=bar.session_date,
                vwap=bar.close,
                session_high_before=None,
                cumulative_volume=(minute + 1) * 100,
                bars_seen=minute + 1,
            )
        )

    assert snapshot is not None
    assert snapshot.values["rolling_volume_ratio_v1"] is None
    assert snapshot.missing_reasons["rolling_volume_ratio_v1"] == (
        "baseline_volume_windows_non_contiguous"
    )


def test_gap_in_rolling_window_fails_closed() -> None:
    request = FeatureRequestSpec("rolling_return_v1", {"window_minutes": 3})
    adapter = CompletedOneMinuteKbarFeatureAdapter((request,))
    snapshot = None
    for minute in (0, 1, 3):
        bar = _bar(minute, "102" if minute == 3 else "100")
        snapshot = adapter.normalize(
            SimpleNamespace(
                symbol=bar.symbol,
                bar=bar,
                resolved_session_date=bar.session_date,
                vwap=bar.close,
                session_high_before=None,
                cumulative_volume=100,
                bars_seen=minute + 1,
            )
        )

    assert snapshot is not None
    assert snapshot.values["rolling_return_v1"] is None
    assert snapshot.missing_reasons["rolling_return_v1"] == (
        "rolling_return_window_incomplete"
    )


def test_phase5_strategy_exposes_parameterized_local_paper_binding() -> None:
    template = AtomicStrategyRegistry().strategy("rolling_return_entry").template
    assert template.runtime_bindings["LOCAL_PAPER_TICK_BIDASK"] == (
        "rolling_return.local_paper_completed_kbar_v1"
    )
    requests = resolve_feature_requests(template, {"window_minutes": 3})
    assert requests[0].parameters == {"window_minutes": 3}


def test_pre_g6_version_remains_replayable_in_backtest() -> None:
    current = _version(
        "rolling_return_entry",
        "rolling-return:pre-g6",
        {
            "window_minutes": 3,
            "minimum_return_pct": "2",
            "entry_window_start": "09:03",
            "entry_window_end": "12:45",
        },
    )
    template = AtomicStrategyRegistry().strategy(
        current.strategy_id
    ).template
    legacy_document = template.template_document
    legacy_document["runtime_bindings"] = {
        "BACKTEST_KBAR_1M": template.runtime_bindings["BACKTEST_KBAR_1M"]
    }
    legacy_template_digest = canonical_digest(legacy_document)
    legacy_configuration_digest = canonical_digest(
        {
            "strategy_id": current.strategy_id,
            "parameters": dict(current.parameters),
            "parameter_schema_version": current.parameter_schema_version,
            "parameter_schema_digest": current.parameter_schema_digest,
            "parameters_digest": current.parameters_digest,
            "template_digest": legacy_template_digest,
            "implementation_digest": current.implementation_digest,
        }
    )
    legacy = replace(
        current,
        template_digest=legacy_template_digest,
        configuration_digest=legacy_configuration_digest,
    )

    resolved = _resolve(legacy)

    assert legacy.template_digest != template.template_digest
    assert resolved.engine_strategy_set.entry_strategy_ids == (
        legacy.strategy_version_id,
    )
