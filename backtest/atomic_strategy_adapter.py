"""Thin bridge from exact atomic versions into the existing Kbar engine."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date

from atomic_strategies.protocol import AtomicEvaluationStatus, AtomicStrategy, AtomicStrategyContext
from atomic_strategies.compatibility import backtest_compatible_template_digests
from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.domain import (
    AggregationPolicy,
    EvaluationStatus,
    StrategyEvaluation,
    StrategySetSnapshot,
)
from backtest.feature_adapters import (
    CompletedOneMinuteKbarFeatureAdapter,
    verify_vwap_amount_contract,
)
from features.specifications import FeatureRequestSpec, FeatureSpecificationRegistry
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
    def __init__(
        self,
        strategy: AtomicStrategy,
        version: StrategyVersion,
        requests: tuple[FeatureRequestSpec, ...],
        *,
        dataset_amount_contract: Mapping[str, object] | None = None,
        require_dataset_amount_contract: bool = False,
    ) -> None:
        if strategy.template.strategy_id != version.strategy_id:
            raise ValueError("atomic strategy implementation 與 Version strategy_id 不一致")
        if version.template_digest not in backtest_compatible_template_digests(
            strategy
        ):
            raise ValueError("atomic strategy Template digest 與 Version 不一致")
        if strategy.template.parameter_schema.schema_digest != version.parameter_schema_digest:
            raise ValueError("atomic strategy parameter schema digest 與 Version 不一致")
        if strategy.template.implementation_digest != version.implementation_digest:
            raise ValueError("atomic strategy implementation digest 與 Version 不一致")
        parameters = strategy.template.validate_parameters(version.parameters)
        self._strategy = strategy
        self._version = version
        self._parameters = parameters
        self._features = CompletedOneMinuteKbarFeatureAdapter(
            tuple(requests),
            dataset_amount_contract=dataset_amount_contract,
            require_dataset_amount_contract=require_dataset_amount_contract,
        )
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

    def reset_runtime(self) -> None:
        self._features.reset()

    def begin_session(self, session_date: date) -> None:
        self._features.begin_session(session_date.isoformat())

    def evaluate(self, context: StrategyContext) -> StrategyEvaluation:
        features = self._features.normalize(context)
        atomic = self._strategy.evaluate(
            AtomicStrategyContext(
                strategy_version_id=self._version.strategy_version_id,
                symbol=context.symbol,
                event_at=context.bar.timestamp,
                current_price=str(context.bar.close),
                parameters=self._parameters,
                features=features,
            )
        )
        observed = dict(atomic.observed)
        input_evidence = self._features.evaluation_input_evidence(features)
        if input_evidence is not None:
            observed["feature_input_evidence"] = input_evidence
        return StrategyEvaluation(
            strategy_id=atomic.strategy_id,
            strategy_name=self.definition.display_name_zh_tw,
            strategy_version=str(self._version.version_number),
            side=StrategySide.ENTRY,
            status=_STATUS[atomic.status],
            symbol=atomic.symbol,
            event_at=atomic.event_at,
            reason=atomic.reason,
            observed=observed,
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


def bind_dataset_feature_evidence(
    run_snapshot: Mapping[str, object],
    *,
    dataset_id: str,
    dataset_digest: str,
    amount_contract: Mapping[str, object] | None,
) -> dict[str, object]:
    """Bind immutable Dataset input semantics to a resolved Atomic snapshot."""

    value = deepcopy(dict(run_snapshot))
    value.pop("snapshot_digest", None)
    amount = dict(amount_contract) if amount_contract is not None else None
    value["dataset_feature_evidence"] = {
        "dataset_id": dataset_id,
        "dataset_digest": dataset_digest,
        "amount_contract": amount,
    }
    for strategy in value.get("feature_requests", []):
        if not isinstance(strategy, dict):
            continue
        for request in strategy.get("requests", []):
            if isinstance(request, dict) and request.get("feature_id") == "vwap_session_v1":
                verified_amount = verify_vwap_amount_contract(amount)
                dataset_input_contract = {"amount_contract": verified_amount}
                existing_contract = request.get("dataset_input_contract")
                if (
                    existing_contract is not None
                    and existing_contract != dataset_input_contract
                ):
                    raise ValueError("VWAP runtime Dataset input contract 已漂移")
                request["dataset_input_contract"] = dataset_input_contract
                request["feature_input_contract_digest"] = canonical_digest(
                    {
                        "request_digest": request["request_digest"],
                        "adapter_identity": value["feature_adapter_identity"],
                        "dataset_input_contract": dataset_input_contract,
                    }
                )
    value["snapshot_digest"] = canonical_digest(value)
    return value


def resolve_atomic_entry_set(
    repository: AtomicStrategyRepository,
    atomic_registry: AtomicStrategyRegistry,
    snapshot: ExactStrategySetSnapshot,
    *,
    exit_strategy_ids: tuple[str, ...] = ("end_of_day_exit_v1",),
    dataset_amount_contract: Mapping[str, object] | None = None,
    require_dataset_amount_contract: bool = False,
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
        parameters = implementation.template.validate_parameters(version.parameters)
        requests = resolve_feature_requests(implementation.template, parameters)
        feature_registry.validate_requests(requests)
        resolved_requests = []
        for request in requests:
            specification = feature_registry.get(request.feature_id)
            request_document: dict[str, object] = {
                "feature_id": request.feature_id,
                "parameters": dict(request.parameters),
                "parameter_digest": request.parameter_digest,
                "request_digest": request.request_digest,
                "specification_digest": specification.specification_digest,
                "feature_implementation_digest": specification.implementation_digest,
                "as_of_semantics": specification.as_of_semantics,
                "runtime_identity_digest": request.runtime_identity_digest(
                    adapter_identity=CompletedOneMinuteKbarFeatureAdapter.identity,
                    cadence=specification.cadence,
                ),
            }
            if request.feature_id == "vwap_session_v1" and (
                require_dataset_amount_contract or dataset_amount_contract is not None
            ):
                verified_amount = verify_vwap_amount_contract(
                    dataset_amount_contract
                )
                dataset_input_contract = {"amount_contract": verified_amount}
                request_document["dataset_input_contract"] = dataset_input_contract
                request_document["feature_input_contract_digest"] = canonical_digest(
                    {
                        "request_digest": request.request_digest,
                        "adapter_identity": CompletedOneMinuteKbarFeatureAdapter.identity,
                        "dataset_input_contract": dataset_input_contract,
                    }
                )
            resolved_requests.append(request_document)
        feature_request_documents.append(
            {
                "strategy_version_id": version.strategy_version_id,
                "requests": resolved_requests,
            }
        )
        adapters.append(
            AtomicBacktestStrategyAdapter(
                implementation,
                version,
                requests,
                dataset_amount_contract=dataset_amount_contract,
                require_dataset_amount_contract=require_dataset_amount_contract,
            )
        )
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
