from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_strategy_adapter import resolve_atomic_entry_set
from backtest.domain import BacktestRunConfig, HistoricalBar, StrategySide
from backtest.engine import HistoricalBacktestEngine
from strategy_catalog.domain import StrategyRole
from strategy_catalog.drafts import StrategyVersion
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _version(strategy_id: str, version_id: str, number: int) -> StrategyVersion:
    template = AtomicStrategyRegistry().strategy(strategy_id).template
    parameters = template.validate_parameters({})
    configuration_digest = canonical_digest(
        {
            "strategy_id": strategy_id,
            "parameters": parameters,
            "parameter_schema_version": template.parameter_schema.version,
            "parameter_schema_digest": template.parameter_schema.schema_digest,
            "parameters_digest": canonical_digest(parameters),
            "template_digest": template.template_digest,
            "implementation_digest": template.implementation_digest,
        }
    )
    now = datetime.now(timezone.utc)
    return StrategyVersion(
        strategy_version_id=version_id,
        strategy_id=strategy_id,
        source_draft_id=f"draft-{number}",
        version_number=number,
        parameters=parameters,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(parameters),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=configuration_digest,
        change_note="fixture",
        created_by="test",
        created_at=now,
        published_at=now,
    )


class _VersionRepository:
    def __init__(self, versions: tuple[StrategyVersion, ...]) -> None:
        self._versions = {item.strategy_version_id: item for item in versions}

    def get_version(self, strategy_version_id: str) -> StrategyVersion:
        return self._versions[strategy_version_id]


def _bar(minute: int, close: str, high: str) -> HistoricalBar:
    return HistoricalBar(
        symbol="2330",
        name="台積電",
        market="TWSE",
        timestamp=datetime(2026, 8, 21, 9, minute, tzinfo=TAIPEI),
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal("99"),
        close=Decimal(close),
        volume=10_000,
    )


def _bars() -> tuple[HistoricalBar, ...]:
    return (
        _bar(0, "100", "101"),
        _bar(1, "103", "104"),
        _bar(2, "106", "107"),
        _bar(3, "106", "107"),
    )


def _member(version: StrategyVersion, order: int = 0) -> StrategySetMemberSnapshot:
    return StrategySetMemberSnapshot(
        strategy_version_id=version.strategy_version_id,
        strategy_id=version.strategy_id,
        role=StrategyRole.ENTRY,
        configuration_digest=version.configuration_digest,
        implementation_digest=version.implementation_digest,
        member_order=order,
        attribution_priority=order,
    )


def _proxy_amount_contract(
    *,
    kind: str = "DERIVED_CLOSE_X_VOLUME_PROXY",
) -> dict[str, object]:
    contract: dict[str, object] = {
        "is_actual_turnover": False,
        "kind": kind,
        "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
    }
    contract["digest"] = canonical_digest(contract)
    return contract


@pytest.mark.parametrize(
    ("strategy_id", "version_id"),
    (
        ("above_vwap_entry", "version-above-only"),
        ("breakout_previous_high_entry", "version-breakout-only"),
    ),
)
def test_each_exact_atomic_entry_runs_independently(
    strategy_id: str,
    version_id: str,
) -> None:
    version = _version(strategy_id, version_id, 1)
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id=f"set-{version_id}",
        strategy_set_id=f"set-{strategy_id}",
        version_number=1,
        display_name_zh_tw="單一原子策略",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(_member(version),),
    )
    resolved = resolve_atomic_entry_set(
        _VersionRepository((version,)),
        AtomicStrategyRegistry(),
        snapshot,
    )
    config = BacktestRunConfig(
        dataset_id="dataset-atomic-fixture",
        dataset_digest="dataset-digest",
        strategy_set=resolved.engine_strategy_set,
        engine_version="backtest-engine-v2",
        atomic_strategy_run_snapshot=resolved.run_snapshot,
        minimum_oos_trades=1,
    )

    result = HistoricalBacktestEngine(resolved.registry).run(config=config, bars=_bars())
    entry = next(item for item in result.decisions if item.side is StrategySide.ENTRY)

    assert entry.triggered_strategy_ids == (version_id,)
    assert entry.primary_strategy_id == version_id


def test_vwap_runtime_requires_and_persists_verified_amount_input_evidence() -> None:
    version = _version("above_vwap_entry", "version-vwap-amount", 1)
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-vwap-amount",
        strategy_set_id="set-vwap",
        version_number=1,
        display_name_zh_tw="VWAP amount contract",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(_member(version),),
    )
    repository = _VersionRepository((version,))

    with pytest.raises(ValueError, match="amount contract"):
        resolve_atomic_entry_set(
            repository,
            AtomicStrategyRegistry(),
            snapshot,
            require_dataset_amount_contract=True,
        )
    with pytest.raises(ValueError, match="amount contract"):
        resolve_atomic_entry_set(
            repository,
            AtomicStrategyRegistry(),
            snapshot,
            dataset_amount_contract=_proxy_amount_contract(kind="UNKNOWN_AMOUNT"),
            require_dataset_amount_contract=True,
        )

    amount_contract = _proxy_amount_contract()
    resolved = resolve_atomic_entry_set(
        repository,
        AtomicStrategyRegistry(),
        snapshot,
        dataset_amount_contract=amount_contract,
        require_dataset_amount_contract=True,
    )
    request = resolved.run_snapshot["feature_requests"][0]["requests"][0]
    assert request["dataset_input_contract"]["amount_contract"] == amount_contract
    assert len(request["feature_input_contract_digest"]) == 64
    config = BacktestRunConfig(
        dataset_id="dataset-vwap-amount",
        dataset_digest="dataset-vwap-amount-digest",
        strategy_set=resolved.engine_strategy_set,
        engine_version="backtest-engine-v2",
        atomic_strategy_run_snapshot=resolved.run_snapshot,
        dataset_amount_contract=amount_contract,
        minimum_oos_trades=1,
    )

    result = HistoricalBacktestEngine(resolved.registry).run(
        config=config,
        bars=_bars(),
    )
    entry = next(item for item in result.decisions if item.side is StrategySide.ENTRY)
    evidence = entry.evaluations[0].observed["feature_input_evidence"]
    assert evidence["dataset_input_contract"]["amount_contract"] == amount_contract
    assert evidence["feature_id"] == "vwap_session_v1"
    assert len(evidence["feature_input_digest"]) == 64


def test_two_exact_atomic_entries_run_combined_with_version_attribution() -> None:
    versions = (
        _version("above_vwap_entry", "version-above", 1),
        _version("breakout_previous_high_entry", "version-breakout", 1),
    )
    members = tuple(_member(item, index) for index, item in enumerate(versions))
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="set-version-1",
        strategy_set_id="set-1",
        version_number=1,
        display_name_zh_tw="原子進場組合",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ALL,
        members=members,
    )
    resolved = resolve_atomic_entry_set(
        _VersionRepository(versions),
        AtomicStrategyRegistry(),
        snapshot,
    )
    config = BacktestRunConfig(
        dataset_id="dataset-atomic-fixture",
        dataset_digest="dataset-digest",
        strategy_set=resolved.engine_strategy_set,
        engine_version="backtest-engine-v2",
        atomic_strategy_run_snapshot=resolved.run_snapshot,
        minimum_oos_trades=1,
    )
    first = HistoricalBacktestEngine(resolved.registry).run(config=config, bars=_bars())
    second = HistoricalBacktestEngine(resolved.registry).run(config=config, bars=_bars())
    entry = next(item for item in first.decisions if item.side is StrategySide.ENTRY)

    assert entry.triggered_strategy_ids == ("version-above", "version-breakout")
    assert entry.primary_strategy_id == "version-above"
    atomic_snapshot = config.to_dict()["atomic_strategy_run_snapshot"]
    assert atomic_snapshot["strategy_set"]["members"][0]["strategy_version_id"] == (
        "version-above"
    )
    assert atomic_snapshot["feature_adapter_identity"] == (
        "backtest.completed-kbar-1m-feature-adapter-v1"
    )
    assert atomic_snapshot["contract_version"] == "atomic-backtest-run-snapshot-v2"
    for strategy_requests in atomic_snapshot["feature_requests"]:
        for request in strategy_requests["requests"]:
            assert len(request["specification_digest"]) == 64
            assert len(request["feature_implementation_digest"]) == 64
            assert request["as_of_semantics"] in {
                "CURRENT_COMPLETED_BAR_CLOSE_INCLUSIVE",
                "STRICTLY_BEFORE_CURRENT_COMPLETED_BAR",
            }
    assert first.to_dict() == second.to_dict()
