"""Exact-version atomic Strategy Set evaluation for local-paper entry decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from atomic_strategies.protocol import (
    AtomicEvaluationStatus,
    AtomicStrategy,
    AtomicStrategyContext,
    AtomicStrategyEvaluation,
)
from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.registry import AtomicStrategyRegistry
from features.engine import FeatureEngine
from features.specifications import (
    FeatureRequestSpec,
    FeatureSpecificationRegistry,
    NormalizedFeatureSnapshot,
)
from strategy_catalog.domain import StrategyRole
from strategy_catalog.drafts import StrategyTemplate, StrategyVersion
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.repository import StrategyCatalogConflict
from strategy_catalog.paper_activation import PaperActivationCatalogSnapshot
from strategy_catalog.lifecycle import StrategyLifecycleStatus
from strategy_catalog.sets import CompositionPolicy, ExactStrategySetSnapshot


LOCAL_PAPER_RUNTIME_BINDING = "LOCAL_PAPER_TICK_BIDASK"
LOCAL_PAPER_FEATURE_ADAPTER_IDENTITY = (
    "momentum-feature-engine-projection.local-paper-tick-bidask-v2"
)
REQUESTED_PROJECTION_FEATURE_IDS = frozenset(
    {
        "rolling_return_v1",
        "rolling_volume_ratio_v1",
        "opening_range_high_v1",
    }
)


class _AtomicPaperCatalog(Protocol):
    def get_paper_activation_snapshot(
        self,
        strategy_set_version_id: str,
    ) -> PaperActivationCatalogSnapshot: ...


class PaperSetStatus(StrEnum):
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class LocalPaperPipelineSnapshot:
    entry_strategy_set: ExactStrategySetSnapshot
    runtime_bindings: tuple[Mapping[str, str], ...]
    feature_contracts: tuple[Mapping[str, Any], ...]
    lifecycle_admissions: tuple[Mapping[str, Any], ...]
    execution_policy_identity: str = "local-paper-limit-best-offer-v1"
    hard_risk_policy_identity: str = "local-paper-hard-risk-v1"
    exit_policy_identity: str = "fixed-stop-take-profit-eod-v1"
    feature_adapter_identity: str = LOCAL_PAPER_FEATURE_ADAPTER_IDENTITY
    contract_version: str = "local-paper-pipeline-snapshot-v2"

    def __post_init__(self) -> None:
        if not self.runtime_bindings:
            raise ValueError("Local Paper Pipeline 至少需要一個 resolved runtime binding")
        if not self.feature_contracts:
            raise ValueError("Local Paper Pipeline 至少需要一個 Feature contract")
        if not self.lifecycle_admissions:
            raise ValueError("Local Paper Pipeline 至少需要一筆 lifecycle admission")
        object.__setattr__(
            self, "runtime_bindings", tuple(dict(item) for item in self.runtime_bindings)
        )
        object.__setattr__(
            self, "feature_contracts", tuple(dict(item) for item in self.feature_contracts)
        )
        object.__setattr__(
            self,
            "lifecycle_admissions",
            tuple(dict(item) for item in self.lifecycle_admissions),
        )

    @property
    def owner_strategy_id(self) -> str:
        return f"atomic-set:{self.entry_strategy_set.strategy_set_version_id}"

    @property
    def snapshot_digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "entry_strategy_set": self.entry_strategy_set.to_dict(),
            "runtime_bindings": [dict(item) for item in self.runtime_bindings],
            "feature_contracts": [dict(item) for item in self.feature_contracts],
            "lifecycle_admissions": [
                dict(item) for item in self.lifecycle_admissions
            ],
            "execution_policy_identity": self.execution_policy_identity,
            "hard_risk_policy_identity": self.hard_risk_policy_identity,
            "exit_policy_identity": self.exit_policy_identity,
            "feature_adapter_identity": self.feature_adapter_identity,
        }


@dataclass(frozen=True)
class ResolvedPaperStrategy:
    implementation: AtomicStrategy
    template: StrategyTemplate
    version: StrategyVersion
    parameters: Mapping[str, Any]
    runtime_binding: str
    feature_requests: tuple[FeatureRequestSpec, ...]


@dataclass(frozen=True)
class AtomicPaperCandidateDecision:
    status: PaperSetStatus
    symbol: str
    event_at: datetime
    current_price: str
    entry_limit_price: str
    decision_digest: str
    primary_strategy_version_id: str | None
    evaluations: tuple[AtomicStrategyEvaluation, ...]

    def evidence(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "symbol": self.symbol,
            "event_at": self.event_at.isoformat(),
            "current_price": self.current_price,
            "entry_limit_price": self.entry_limit_price,
            "decision_digest": self.decision_digest,
            "primary_strategy_version_id": self.primary_strategy_version_id,
            "evaluations": [
                {
                    "strategy_id": item.strategy_id,
                    "strategy_version_id": item.strategy_version_id,
                    "status": item.status.value,
                    "reason": item.reason,
                    "observed": dict(item.observed),
                    "threshold": dict(item.threshold),
                }
                for item in self.evaluations
            ],
        }


@dataclass(frozen=True)
class AtomicPaperProjectionDecision:
    candidates: tuple[AtomicPaperCandidateDecision, ...]
    blocked_reasons: tuple[str, ...]

    @property
    def triggered(self) -> tuple[AtomicPaperCandidateDecision, ...]:
        return tuple(
            item for item in self.candidates if item.status is PaperSetStatus.TRIGGERED
        )


@dataclass(frozen=True)
class AtomicPaperRuntimeResolution:
    pipeline: LocalPaperPipelineSnapshot
    members: tuple[ResolvedPaperStrategy, ...]

    @property
    def projection_requests(self) -> tuple[FeatureRequestSpec, ...]:
        unique: dict[str, FeatureRequestSpec] = {}
        for member in self.members:
            for request in member.feature_requests:
                if request.feature_id in REQUESTED_PROJECTION_FEATURE_IDS:
                    unique.setdefault(request.request_digest, request)
        return tuple(unique[key] for key in sorted(unique))

    def evaluate_projection(
        self,
        projection: Mapping[str, Any],
        *,
        evaluated_at: datetime,
        max_age_seconds: float,
    ) -> AtomicPaperProjectionDecision:
        source = _mapping(projection.get("source"), "atomic-paper.source")
        if not (
            projection.get("status") == "live"
            and source.get("is_live") is True
            and source.get("connection_state") == "RUNNING"
            and source.get("data_health") == "HEALTHY"
        ):
            return AtomicPaperProjectionDecision((), ("即時 Feature 來源尚未 ready",))

        decisions: list[AtomicPaperCandidateDecision] = []
        blocked: list[str] = []
        for raw_item in _mapping_list(projection.get("items"), "atomic-paper.items"):
            try:
                member_inputs = tuple(
                    (
                        member,
                        _normalize_candidate(
                            raw_item,
                            evaluated_at=evaluated_at,
                            max_age_seconds=max_age_seconds,
                            requests=member.feature_requests,
                        ),
                    )
                    for member in self.members
                )
            except ValueError as error:
                symbol = str(raw_item.get("symbol") or "?").strip().upper()
                blocked.append(f"{symbol}: {error}")
                continue
            normalized = member_inputs[0][1]
            evaluations = tuple(
                member.implementation.evaluate(
                    AtomicStrategyContext(
                        strategy_version_id=member.version.strategy_version_id,
                        symbol=member_input.symbol,
                        event_at=member_input.as_of,
                        current_price=str(member_input.values["current_price"]),
                        parameters=member.parameters,
                        features=member_input,
                    )
                )
                for member, member_input in member_inputs
            )
            status = _compose(self.pipeline.entry_strategy_set, evaluations)
            triggered_ids = {
                item.strategy_version_id
                for item in evaluations
                if item.status is AtomicEvaluationStatus.TRIGGERED
            }
            primary = next(
                (
                    version_id
                    for version_id in self.pipeline.entry_strategy_set.priority_order
                    if version_id in triggered_ids
                ),
                None,
            )
            evidence_body = {
                "pipeline_digest": self.pipeline.snapshot_digest,
                "symbol": normalized.symbol,
                "event_at": normalized.as_of.isoformat(),
                "input_digests": {
                    member.version.strategy_version_id: member_input.input_digest
                    for member, member_input in member_inputs
                },
                "status": status.value,
                "evaluations": [
                    {
                        "strategy_version_id": item.strategy_version_id,
                        "status": item.status.value,
                        "reason": item.reason,
                        "observed": dict(item.observed),
                        "threshold": dict(item.threshold),
                    }
                    for item in evaluations
                ],
            }
            decisions.append(
                AtomicPaperCandidateDecision(
                    status=status,
                    symbol=normalized.symbol,
                    event_at=normalized.as_of,
                    current_price=str(normalized.values["current_price"]),
                    entry_limit_price=str(normalized.values["best_ask"]),
                    decision_digest=canonical_digest(evidence_body),
                    primary_strategy_version_id=primary,
                    evaluations=evaluations,
                )
            )
        return AtomicPaperProjectionDecision(tuple(decisions), tuple(blocked))


def resolve_atomic_paper_entry_set(
    catalog: _AtomicPaperCatalog,
    atomic_registry: AtomicStrategyRegistry,
    strategy_set_version_id: str,
) -> AtomicPaperRuntimeResolution:
    activation = catalog.get_paper_activation_snapshot(strategy_set_version_id)
    snapshot = activation.strategy_set
    if snapshot.stage is not StrategyRole.ENTRY:
        raise ValueError("Local Paper runtime 只接受 ENTRY Strategy Set")
    members_by_version = {item.strategy_version_id: item for item in snapshot.members}
    resolved: list[ResolvedPaperStrategy] = []
    activation_by_version = {
        item.version.strategy_version_id: item for item in activation.members
    }
    for version_id in snapshot.runtime_member_ids:
        member = members_by_version[version_id]
        activation_member = activation_by_version[version_id]
        version = activation_member.version
        if (
            activation_member.lifecycle.status
            is not StrategyLifecycleStatus.PAPER_APPROVED
        ):
            raise ValueError(
                f"Strategy Version {version_id} 尚未 PAPER_APPROVED"
            )
        if version.strategy_id != member.strategy_id:
            raise StrategyCatalogConflict(
                "STRATEGY_SET_MEMBER_MISMATCH", "member strategy_id 不一致"
            )
        if version.configuration_digest != member.configuration_digest:
            raise StrategyCatalogConflict(
                "STRATEGY_SET_MEMBER_MISMATCH", "member configuration digest 不一致"
            )
        if version.implementation_digest != member.implementation_digest:
            raise StrategyCatalogConflict(
                "STRATEGY_SET_MEMBER_MISMATCH", "member implementation digest 不一致"
            )
        implementation = atomic_registry.strategy(version.strategy_id)
        template = implementation.template
        if template.template_digest != version.template_digest:
            raise ValueError("Local Paper Template digest 與 Strategy Version 不一致")
        if template.parameter_schema.schema_digest != version.parameter_schema_digest:
            raise ValueError("Local Paper parameter schema digest 與 Version 不一致")
        if template.implementation_digest != version.implementation_digest:
            raise ValueError("Local Paper implementation digest 與 Version 不一致")
        binding = str(template.runtime_bindings.get(LOCAL_PAPER_RUNTIME_BINDING) or "")
        if not binding:
            raise ValueError(
                f"策略 {version.strategy_version_id} 沒有 {LOCAL_PAPER_RUNTIME_BINDING} binding"
            )
        parameters = template.validate_parameters(version.parameters)
        feature_requests = resolve_feature_requests(template, parameters)
        FeatureSpecificationRegistry().validate_requests(feature_requests)
        resolved.append(
            ResolvedPaperStrategy(
                implementation=implementation,
                template=template,
                version=version,
                parameters=parameters,
                runtime_binding=binding,
                feature_requests=feature_requests,
            )
        )
    unique_requests: dict[str, FeatureRequestSpec] = {}
    for resolved_member in resolved:
        for request in resolved_member.feature_requests:
            unique_requests.setdefault(request.request_digest, request)
    return AtomicPaperRuntimeResolution(
        pipeline=LocalPaperPipelineSnapshot(
            entry_strategy_set=snapshot,
            runtime_bindings=tuple(
                {
                    "strategy_version_id": member.version.strategy_version_id,
                    "binding": member.runtime_binding,
                    "implementation_digest": member.version.implementation_digest,
                }
                for member in resolved
            ),
            feature_contracts=tuple(
                _local_paper_feature_contract(unique_requests[request_digest])
                for request_digest in sorted(unique_requests)
            ),
            lifecycle_admissions=tuple(
                item.lifecycle.to_dict() for item in activation.members
            ),
        ),
        members=tuple(resolved),
    )


def _local_paper_feature_contract(
    request: FeatureRequestSpec,
) -> Mapping[str, Any]:
    feature_id = request.feature_id
    registry = FeatureSpecificationRegistry()
    specification = registry.get(feature_id)
    specification.validate_request(request)
    contracts = {
        "vwap_session_v1": {
            "feature_id": "vwap_session_v1",
            "source_projection": "IntradayFeatureSnapshot.vwap",
            "as_of_semantics": "CURRENT_TICK_AVERAGE_PRICE",
            "implementation_identity": "FeatureEngine.intraday_features_v0",
        },
        "previous_intraday_high_v1": {
            "feature_id": "previous_intraday_high_v1",
            "source_projection": "IntradayFeatureSnapshot.previous_intraday_high",
            "as_of_semantics": "STRICTLY_BEFORE_CURRENT_TICK",
            "implementation_identity": "FeatureEngine.intraday_features_v0",
        },
    }
    base = contracts.get(feature_id)
    if feature_id in REQUESTED_PROJECTION_FEATURE_IDS:
        base = {
            "feature_id": feature_id,
            "source_projection": "RequestedFeatureProjection",
            "projection_adapter_identity": (
                FeatureEngine.requested_feature_adapter_identity
            ),
            "as_of_semantics": specification.as_of_semantics,
        }
    if base is None:
        raise ValueError(
            f"Local Paper adapter 尚未定義 Feature contract：{feature_id}"
        )
    return {
        **base,
        "request_digest": request.request_digest,
        "parameter_digest": request.parameter_digest,
        "parameters": dict(request.parameters),
        "specification_digest": specification.specification_digest,
        "feature_implementation_digest": (
            specification.implementation_digest
        ),
        "cadence": specification.cadence,
        "completed_data_only": specification.completed_data_only,
        "missing_semantics": specification.missing_semantics,
        "specification_as_of_semantics": specification.as_of_semantics,
    }


def _normalize_candidate(
    item: Mapping[str, Any],
    *,
    evaluated_at: datetime,
    max_age_seconds: float,
    requests: tuple[FeatureRequestSpec, ...] = (),
) -> NormalizedFeatureSnapshot:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol or item.get("availability") != "EVALUATED":
        raise ValueError("候選尚未完成即時 Feature 評估")
    intraday = _mapping(item.get("intraday"), "candidate.intraday")
    execution_book = _mapping(
        item.get("execution_book"), "candidate.execution_book"
    )
    if execution_book.get("status") != "VALID":
        raise ValueError("execution book 尚無有效買一／賣一")
    price = _valid_feature(intraday, "price", required=True)
    source_at = _aware_datetime(price["source_as_of"], "price.source_as_of")
    age_seconds = (evaluated_at - source_at).total_seconds()
    if age_seconds < 0 or age_seconds > max_age_seconds:
        raise ValueError("即時 Feature 價格已過期")
    book_received_at = _aware_datetime(
        execution_book.get("received_at"), "execution_book.received_at"
    )
    book_age_seconds = (evaluated_at - book_received_at).total_seconds()
    if book_age_seconds < 0 or book_age_seconds > max_age_seconds:
        raise ValueError("execution book 已過期")
    if execution_book.get("best_ask") is None:
        raise ValueError("execution book 缺少賣一")
    values: dict[str, Any] = {
        "current_price": price["value"],
        "best_bid": execution_book.get("best_bid"),
        "best_ask": execution_book["best_ask"],
    }
    missing_reasons: dict[str, str] = {}
    request_digests: dict[str, str] = {}
    state_keys: dict[str, str] = {}
    for projection_name, feature_id in (
        ("vwap", "vwap_session_v1"),
        ("previous_intraday_high", "previous_intraday_high_v1"),
    ):
        feature = _valid_feature(intraday, projection_name, required=False)
        values[feature_id] = feature["value"] if feature is not None else None
        if feature is None:
            raw_feature = intraday.get(projection_name)
            if isinstance(raw_feature, Mapping) and raw_feature.get("reason"):
                missing_reasons[feature_id] = str(raw_feature["reason"])

    requested_rows = _requested_feature_rows(item)
    registry = FeatureSpecificationRegistry()
    for request in requests:
        if request.feature_id in values:
            request_digests[request.feature_id] = request.request_digest
            continue
        if request.feature_id not in REQUESTED_PROJECTION_FEATURE_IDS:
            raise ValueError(
                f"Local Paper 不支援 Feature：{request.feature_id}"
            )
        if request.feature_id in request_digests:
            raise ValueError(
                f"單一策略不可重複要求 Feature：{request.feature_id}"
            )
        try:
            row = requested_rows[request.request_digest]
        except KeyError as error:
            raise ValueError(
                f"缺少 exact Feature Request evidence：{request.feature_id}"
            ) from error
        specification = registry.get(request.feature_id)
        expected_state_key = request.state_key(
            adapter_identity=FeatureEngine.requested_feature_adapter_identity,
            cadence=specification.cadence,
            symbol=symbol,
            session=source_at.date().isoformat(),
        )
        _verify_requested_feature_identity(
            row,
            request=request,
            specification=specification,
            expected_state_key=expected_state_key,
        )
        feature_value = _mapping(
            row.get("value"),
            f"requested-feature.{request.feature_id}.value",
        )
        status = str(feature_value.get("status") or "")
        value = feature_value.get("value")
        if status == "VALID" and value is not None:
            requested_as_of = _aware_datetime(
                feature_value.get("source_as_of"),
                f"requested-feature.{request.feature_id}.source_as_of",
            )
            requested_age = (source_at - requested_as_of).total_seconds()
            if requested_age < 0 or requested_age >= 120:
                raise ValueError(
                    f"{request.feature_id} 完整 Kbar evidence 時間不一致"
                )
            values[request.feature_id] = value
        else:
            values[request.feature_id] = None
            missing_reasons[request.feature_id] = str(
                feature_value.get("reason")
                or f"{request.feature_id} evidence unavailable"
            )
        request_digests[request.feature_id] = request.request_digest
        state_keys[request.feature_id] = expected_state_key
    input_body = {
        "adapter_identity": LOCAL_PAPER_FEATURE_ADAPTER_IDENTITY,
        "symbol": symbol,
        "as_of": source_at.isoformat(),
        "values": values,
        "missing_reasons": missing_reasons,
        "request_digests": request_digests,
        "state_keys": state_keys,
    }
    return NormalizedFeatureSnapshot(
        symbol=symbol,
        session=source_at.date().isoformat(),
        as_of=source_at,
        adapter_identity=LOCAL_PAPER_FEATURE_ADAPTER_IDENTITY,
        values=values,
        input_digest=canonical_digest(input_body),
        missing_reasons=missing_reasons,
        request_digests=request_digests,
        state_keys=state_keys,
    )


def _requested_feature_rows(
    item: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in _mapping_list(
        item.get("requested_features", []),
        "candidate.requested_features",
    ):
        request_digest = str(row.get("request_digest") or "").strip()
        if not request_digest:
            raise ValueError("requested Feature evidence 缺少 request_digest")
        if request_digest in rows:
            raise ValueError("requested Feature evidence request_digest 重複")
        rows[request_digest] = row
    return rows


def _verify_requested_feature_identity(
    row: Mapping[str, Any],
    *,
    request: FeatureRequestSpec,
    specification,
    expected_state_key: str,
) -> None:
    expected = {
        "feature_id": request.feature_id,
        "adapter_identity": FeatureEngine.requested_feature_adapter_identity,
        "request_digest": request.request_digest,
        "parameter_digest": request.parameter_digest,
        "specification_digest": specification.specification_digest,
        "implementation_digest": specification.implementation_digest,
        "state_key": expected_state_key,
    }
    for field_name, expected_value in expected.items():
        if str(row.get(field_name) or "") != expected_value:
            raise ValueError(
                f"{request.feature_id} Feature evidence identity mismatch: "
                f"{field_name}"
            )
    if dict(_mapping(row.get("parameters"), "requested-feature.parameters")) != dict(
        request.parameters
    ):
        raise ValueError(
            f"{request.feature_id} Feature evidence parameters mismatch"
        )


def _compose(
    snapshot: ExactStrategySetSnapshot,
    evaluations: tuple[AtomicStrategyEvaluation, ...],
) -> PaperSetStatus:
    triggered = sum(
        item.status is AtomicEvaluationStatus.TRIGGERED for item in evaluations
    )
    not_triggered = sum(
        item.status is AtomicEvaluationStatus.NOT_TRIGGERED for item in evaluations
    )
    blocked = sum(item.status is AtomicEvaluationStatus.BLOCKED for item in evaluations)
    insufficient = sum(
        item.status is AtomicEvaluationStatus.INSUFFICIENT_DATA for item in evaluations
    )
    if snapshot.policy is CompositionPolicy.ALL:
        if triggered == len(evaluations):
            return PaperSetStatus.TRIGGERED
        if blocked:
            return PaperSetStatus.BLOCKED
        if insufficient:
            return PaperSetStatus.INSUFFICIENT_DATA
        return PaperSetStatus.NOT_TRIGGERED
    required = (
        1
        if snapshot.policy is CompositionPolicy.ANY
        else snapshot.minimum_trigger_count
    )
    if triggered >= required:
        return PaperSetStatus.TRIGGERED
    unresolved = blocked + insufficient
    if triggered + unresolved < required or not_triggered > len(evaluations) - required:
        return PaperSetStatus.NOT_TRIGGERED
    if blocked:
        return PaperSetStatus.BLOCKED
    if insufficient:
        return PaperSetStatus.INSUFFICIENT_DATA
    return PaperSetStatus.NOT_TRIGGERED


def _valid_feature(
    intraday: Mapping[str, Any],
    name: str,
    *,
    required: bool,
) -> Mapping[str, Any] | None:
    value = intraday.get(name)
    if not isinstance(value, Mapping) or value.get("status") != "VALID":
        if required:
            raise ValueError(f"{name} Feature 無有效值")
        return None
    if value.get("value") is None or value.get("source_as_of") is None:
        if required:
            raise ValueError(f"{name} Feature 缺少 value/source_as_of")
        return None
    return value


def _aware_datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{field_name} 必須是 ISO datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} 必須包含 timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} 必須是 object")
    return value


def _mapping_list(value: object, field_name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{field_name} 必須是 object list")
    return list(value)
