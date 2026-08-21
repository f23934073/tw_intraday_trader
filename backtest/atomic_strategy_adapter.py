"""Thin bridge from exact atomic versions into the existing Kbar engine."""

from __future__ import annotations

from dataclasses import dataclass

from atomic_strategies.protocol import AtomicEvaluationStatus, AtomicStrategy, AtomicStrategyContext
from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.domain import (
    AggregationPolicy,
    EvaluationStatus,
    StrategyEvaluation,
    StrategySetSnapshot,
)
from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
from features.specifications import FeatureSpecificationRegistry
from backtest.strategies import StrategyContext, StrategyRegistry
from strategy_catalog.domain import StrategyDefinition, StrategySide, StrategySource, StrategyStatus
from strategy_catalog.drafts import StrategyVersion
from strategy_catalog.repository import AtomicStrategyRepository, StrategyCatalogConflict
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.sets import ExactStrategySetSnapshot


_STATUS = {
    AtomicEvaluationStatus.TRIGGERED: EvaluationStatus.TRIGGERED,
    AtomicEvaluationStatus.NOT_TRIGGERED: EvaluationStatus.NOT_TRIGGERED,
    AtomicEvaluationStatus.INSUFFICIENT_DATA: EvaluationStatus.INSUFFICIENT_DATA,
    AtomicEvaluationStatus.BLOCKED: EvaluationStatus.BLOCKED,
}


class AtomicBacktestStrategyAdapter:
    def __init__(self, strategy: AtomicStrategy, version: StrategyVersion) -> None:
        if strategy.template.strategy_id != version.strategy_id:
            raise ValueError("atomic strategy implementation 與 Version strategy_id 不一致")
        if strategy.template.template_digest != version.template_digest:
            raise ValueError("atomic strategy Template digest 與 Version 不一致")
        if strategy.template.parameter_schema.schema_digest != version.parameter_schema_digest:
            raise ValueError("atomic strategy parameter schema digest 與 Version 不一致")
        if strategy.template.implementation_digest != version.implementation_digest:
            raise ValueError("atomic strategy implementation digest 與 Version 不一致")
        parameters = strategy.template.validate_parameters(version.parameters)
        self._strategy = strategy
        self._version = version
        self._parameters = parameters
        self._features = CompletedOneMinuteKbarFeatureAdapter()
        self.selection_id = version.strategy_version_id
        self.definition = StrategyDefinition(
            strategy_id=strategy.template.strategy_id,
            display_name_zh_tw=strategy.template.display_name_zh_tw,
            version=str(version.version_number),
            side=StrategySide.ENTRY,
            session_phase=strategy.template.session_phase,
            status=StrategyStatus.EXPERIMENTAL,
            description_zh_tw=strategy.template.description_zh_tw,
            execution_binding=strategy.template.runtime_bindings["BACKTEST_KBAR_1M"],
            required_capabilities=strategy.template.required_capabilities,
            parameters=parameters,
            tags=("原子策略", "exact-version"),
            code_identity=strategy.template.implementation_digest,
            source=StrategySource.DATABASE,
        )

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        atomic = self._strategy.evaluate(
            AtomicStrategyContext(
                strategy_version_id=self._version.strategy_version_id,
                symbol=context.symbol,
                event_at=context.bar.timestamp,
                current_price=str(context.bar.close),
                parameters=self._parameters,
                features=self._features.normalize(context),
            )
        )
        return StrategyEvaluation(
            strategy_id=atomic.strategy_id,
            strategy_name=self.definition.display_name_zh_tw,
            strategy_version=str(self._version.version_number),
            side=StrategySide.ENTRY,
            status=_STATUS[atomic.status],
            symbol=atomic.symbol,
            event_at=atomic.event_at,
            reason=atomic.reason,
            observed=atomic.observed,
            threshold=atomic.threshold,
            strategy_version_id=atomic.strategy_version_id,
        )


@dataclass(frozen=True)
class AtomicBacktestResolution:
    registry: StrategyRegistry
    engine_strategy_set: StrategySetSnapshot
    exact_snapshot: ExactStrategySetSnapshot
    feature_requests: tuple[dict[str, object], ...]

    @property
    def run_snapshot(self) -> dict[str, object]:
        value: dict[str, object] = {
            "contract_version": "atomic-backtest-run-snapshot-v2",
            "strategy_set": self.exact_snapshot.to_dict(),
            "feature_adapter_identity": CompletedOneMinuteKbarFeatureAdapter.identity,
            "feature_requests": list(self.feature_requests),
        }
        value["snapshot_digest"] = canonical_digest(value)
        return value


def resolve_atomic_entry_set(
    repository: AtomicStrategyRepository,
    atomic_registry: AtomicStrategyRegistry,
    snapshot: ExactStrategySetSnapshot,
    *,
    exit_strategy_ids: tuple[str, ...] = ("end_of_day_exit_v1",),
) -> AtomicBacktestResolution:
    if snapshot.stage.value != "ENTRY":
        raise ValueError("Phase 1 atomic backtest resolver 只接受 ENTRY Strategy Set")
    adapters = []
    feature_registry = FeatureSpecificationRegistry()
    feature_request_documents: list[dict[str, object]] = []
    members_by_version = {item.strategy_version_id: item for item in snapshot.members}
    for version_id in snapshot.runtime_member_ids:
        member = members_by_version[version_id]
        version = repository.get_version(version_id)
        if version.strategy_id != member.strategy_id:
            raise StrategyCatalogConflict("STRATEGY_SET_MEMBER_MISMATCH", "member strategy_id 不一致")
        if version.configuration_digest != member.configuration_digest:
            raise StrategyCatalogConflict("STRATEGY_SET_MEMBER_MISMATCH", "member configuration digest 不一致")
        if version.implementation_digest != member.implementation_digest:
            raise StrategyCatalogConflict("STRATEGY_SET_MEMBER_MISMATCH", "member implementation digest 不一致")
        implementation = atomic_registry.strategy(version.strategy_id)
        requests = resolve_feature_requests(implementation.template)
        feature_registry.validate_requests(requests)
        resolved_requests = []
        for request in requests:
            specification = feature_registry.get(request.feature_id)
            resolved_requests.append(
                {
                    "feature_id": request.feature_id,
                    "parameters": dict(request.parameters),
                    "parameter_digest": request.parameter_digest,
                    "request_digest": request.request_digest,
                    "specification_digest": specification.specification_digest,
                    "feature_implementation_digest": specification.implementation_digest,
                    "as_of_semantics": specification.as_of_semantics,
                }
            )
        feature_request_documents.append(
            {
                "strategy_version_id": version.strategy_version_id,
                "requests": resolved_requests,
            }
        )
        adapters.append(AtomicBacktestStrategyAdapter(implementation, version))
    policy = AggregationPolicy(snapshot.policy.value)
    engine_set = StrategySetSnapshot(
        entry_strategy_ids=snapshot.runtime_member_ids,
        exit_strategy_ids=exit_strategy_ids,
        entry_policy=policy,
        entry_min_trigger_count=snapshot.minimum_trigger_count,
        priority_order=snapshot.priority_order,
        version="exact-strategy-set-v1",
    )
    return AtomicBacktestResolution(
        registry=StrategyRegistry(tuple(adapters)),
        engine_strategy_set=engine_set,
        exact_snapshot=snapshot,
        feature_requests=tuple(feature_request_documents),
    )
