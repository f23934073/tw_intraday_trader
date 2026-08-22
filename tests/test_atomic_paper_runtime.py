from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from features.engine import FeatureEngine
from features.specifications import FeatureRequestSpec, FeatureSpecificationRegistry
from simulation.atomic_runtime import (
    PaperSetStatus,
    resolve_atomic_paper_entry_set,
)
from strategy_catalog.domain import StrategyRole
from strategy_catalog.drafts import StrategyVersion
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.lifecycle import StrategyLifecycleStatus
from strategy_catalog.paper_activation import (
    PaperActivationCatalogSnapshot,
    PaperActivationMember,
    StrategyLifecycleProjection,
)
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


AT = datetime.fromisoformat("2026-08-21T10:30:00+08:00")


class FakeCatalog:
    def __init__(
        self,
        snapshot: ExactStrategySetSnapshot,
        versions: tuple[StrategyVersion, ...],
        *,
        lifecycle_status: StrategyLifecycleStatus = StrategyLifecycleStatus.PAPER_APPROVED,
    ) -> None:
        self.snapshot = snapshot
        self.versions = {item.strategy_version_id: item for item in versions}
        self.lifecycle_status = lifecycle_status

    def get_paper_activation_snapshot(self, strategy_set_version_id: str):
        assert strategy_set_version_id == self.snapshot.strategy_set_version_id
        members = []
        for version_id in self.snapshot.runtime_member_ids:
            projection_document = {
                "strategy_version_id": version_id,
                "status": self.lifecycle_status.value,
                "last_sequence": 4,
                "last_event_id": f"event-{version_id}",
            }
            members.append(
                PaperActivationMember(
                    version=self.versions[version_id],
                    lifecycle=StrategyLifecycleProjection(
                        strategy_version_id=version_id,
                        status=self.lifecycle_status,
                        last_sequence=4,
                        last_event_id=f"event-{version_id}",
                        projection_digest=canonical_digest(projection_document),
                    ),
                )
            )
        return PaperActivationCatalogSnapshot(
            strategy_set=self.snapshot,
            members=tuple(members),
        )


def version(strategy_id: str, number: int, parameters: dict) -> StrategyVersion:
    template = AtomicStrategyRegistry().strategy(strategy_id).template
    canonical = template.validate_parameters(parameters)
    return StrategyVersion(
        strategy_version_id=f"{strategy_id}:v{number}",
        strategy_id=strategy_id,
        source_draft_id=f"draft-{strategy_id}",
        version_number=number,
        parameters=canonical,
        parameter_schema_version=template.parameter_schema.version,
        parameter_schema_digest=template.parameter_schema.schema_digest,
        parameters_digest=canonical_digest(canonical),
        template_digest=template.template_digest,
        implementation_digest=template.implementation_digest,
        configuration_digest=f"config-{strategy_id}-{number}",
        change_note="paper runtime test",
        created_by="tester",
        created_at=AT,
        published_at=AT,
    )


def entry_set(
    versions: tuple[StrategyVersion, ...],
    *,
    policy: CompositionPolicy = CompositionPolicy.ANY,
    minimum_trigger_count: int = 1,
) -> ExactStrategySetSnapshot:
    return ExactStrategySetSnapshot(
        strategy_set_version_id=f"paper-set-{policy.value.lower()}-v1",
        strategy_set_id=f"paper-set-{policy.value.lower()}",
        version_number=1,
        display_name_zh_tw="本機模擬原子策略",
        stage=StrategyRole.ENTRY,
        policy=policy,
        minimum_trigger_count=minimum_trigger_count,
        members=tuple(
            StrategySetMemberSnapshot(
                strategy_version_id=item.strategy_version_id,
                strategy_id=item.strategy_id,
                role=StrategyRole.ENTRY,
                configuration_digest=item.configuration_digest,
                implementation_digest=item.implementation_digest,
                member_order=index,
                attribution_priority=index,
            )
            for index, item in enumerate(versions)
        ),
    )


def projection(
    *,
    at: datetime = AT,
    price: str = "101",
    requested_features: list[dict] | None = None,
) -> dict:
    feature = lambda value: {
        "value": value,
        "status": "VALID",
        "source_as_of": at.isoformat(),
        "reason": None,
    }
    return {
        "status": "live",
        "source": {
            "is_live": True,
            "connection_state": "RUNNING",
            "data_health": "HEALTHY",
        },
        "items": [
            {
                "symbol": "3231",
                "availability": "EVALUATED",
                "execution_book": {
                    "status": "VALID",
                    "best_bid": "100.5",
                    "best_ask": "101.5",
                    "received_at": at.isoformat(),
                },
                "intraday": {
                    "price": feature(price),
                    "vwap": feature("100"),
                    "previous_intraday_high": feature("102"),
                },
                "requested_features": requested_features or [],
            }
        ],
    }


def requested_feature(
    request: FeatureRequestSpec,
    *,
    value: str | None,
    reason: str | None = None,
) -> dict:
    specification = FeatureSpecificationRegistry().get(request.feature_id)
    return {
        "feature_id": request.feature_id,
        "adapter_identity": FeatureEngine.requested_feature_adapter_identity,
        "request_digest": request.request_digest,
        "parameter_digest": request.parameter_digest,
        "specification_digest": specification.specification_digest,
        "implementation_digest": specification.implementation_digest,
        "parameters": dict(request.parameters),
        "state_key": request.state_key(
            adapter_identity=FeatureEngine.requested_feature_adapter_identity,
            cadence=specification.cadence,
            symbol="3231",
            session=AT.date().isoformat(),
        ),
        "value": {
            "value": value,
            "status": "VALID" if value is not None else "MISSING",
            "source_as_of": AT.replace(minute=29).isoformat(),
            "reason": reason,
        },
        "evidence": {},
    }


@pytest.fixture
def versions() -> tuple[StrategyVersion, ...]:
    return (
        version(
            "above_vwap_entry",
            1,
            {
                "minimum_distance_bps": "0",
                "entry_window_start": "09:01",
                "entry_window_end": "12:45",
            },
        ),
        version(
            "breakout_previous_high_entry",
            1,
            {
                "buffer_bps": "0",
                "entry_window_start": "09:02",
                "entry_window_end": "12:45",
            },
        ),
    )


def test_exact_any_set_uses_each_version_and_preserves_attribution(versions) -> None:
    snapshot = entry_set(versions)
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, versions),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )

    result = runtime.evaluate_projection(
        projection(),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert runtime.pipeline.entry_strategy_set.snapshot_digest == snapshot.snapshot_digest
    assert runtime.pipeline.owner_strategy_id == (
        f"atomic-set:{snapshot.strategy_set_version_id}"
    )
    assert runtime.pipeline.lifecycle_admissions[0]["status"] == "PAPER_APPROVED"
    assert len(result.triggered) == 1
    decision = result.triggered[0]
    assert decision.status is PaperSetStatus.TRIGGERED
    assert decision.primary_strategy_version_id == "above_vwap_entry:v1"
    assert decision.entry_limit_price == "101.5"
    assert [item.status.value for item in decision.evaluations] == [
        "TRIGGERED",
        "NOT_TRIGGERED",
    ]
    assert decision.evidence()["decision_digest"] == decision.decision_digest


def test_all_set_does_not_trigger_when_only_one_member_matches(versions) -> None:
    snapshot = entry_set(versions, policy=CompositionPolicy.ALL)
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, versions), AtomicStrategyRegistry(), snapshot.strategy_set_version_id
    )

    result = runtime.evaluate_projection(
        projection(), evaluated_at=AT, max_age_seconds=5
    )

    assert result.candidates[0].status is PaperSetStatus.NOT_TRIGGERED
    assert result.triggered == ()


def test_all_set_preserves_unavailable_member_even_when_another_is_false(
    versions,
) -> None:
    snapshot = entry_set(versions, policy=CompositionPolicy.ALL)
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, versions),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    value = projection(price="99")
    value["items"][0]["intraday"]["previous_intraday_high"] = {
        "value": None,
        "status": "MISSING",
        "source_as_of": AT.isoformat(),
        "reason": "warmup",
    }

    result = runtime.evaluate_projection(
        value,
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert [item.status.value for item in result.candidates[0].evaluations] == [
        "NOT_TRIGGERED",
        "INSUFFICIENT_DATA",
    ]
    assert result.candidates[0].status is PaperSetStatus.INSUFFICIENT_DATA


def test_stale_candidate_is_blocked_before_atomic_evaluation(versions) -> None:
    snapshot = entry_set(versions[:1])
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, versions[:1]),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )

    result = runtime.evaluate_projection(
        projection(),
        evaluated_at=datetime.fromisoformat("2026-08-21T10:30:06+08:00"),
        max_age_seconds=5,
    )

    assert result.candidates == ()
    assert result.blocked_reasons == ("3231: 即時 Feature 價格已過期",)


def test_resolution_fails_closed_on_version_identity_drift(versions) -> None:
    snapshot = entry_set(versions[:1])
    drifted = replace(versions[0], configuration_digest="tampered")

    with pytest.raises(Exception, match="configuration digest"):
        resolve_atomic_paper_entry_set(
            FakeCatalog(snapshot, (drifted,)),
            AtomicStrategyRegistry(),
            snapshot.strategy_set_version_id,
        )


@pytest.mark.parametrize(
    "status",
    [
        StrategyLifecycleStatus.PUBLISHED,
        StrategyLifecycleStatus.REVIEWED,
        StrategyLifecycleStatus.BACKTESTED,
        StrategyLifecycleStatus.PAUSED,
        StrategyLifecycleStatus.RETIRED,
    ],
)
def test_resolution_rejects_every_non_paper_approved_lifecycle(
    versions,
    status: StrategyLifecycleStatus,
) -> None:
    snapshot = entry_set(versions[:1])

    with pytest.raises(ValueError, match="尚未 PAPER_APPROVED"):
        resolve_atomic_paper_entry_set(
            FakeCatalog(snapshot, versions[:1], lifecycle_status=status),
            AtomicStrategyRegistry(),
            snapshot.strategy_set_version_id,
        )


def test_resolution_requires_transactional_lifecycle_catalog_api(versions) -> None:
    snapshot = entry_set(versions[:1])

    class RawVersionCatalog:
        def get_strategy_set(self, strategy_set_version_id: str):
            return snapshot

        def get_version(self, strategy_version_id: str):
            return versions[0]

    with pytest.raises(AttributeError, match="get_paper_activation_snapshot"):
        resolve_atomic_paper_entry_set(
            RawVersionCatalog(),  # type: ignore[arg-type]
            AtomicStrategyRegistry(),
            snapshot.strategy_set_version_id,
        )


def test_parameterized_rolling_strategy_uses_exact_request_projection() -> None:
    rolling = version(
        "rolling_return_entry",
        1,
        {
            "window_minutes": 3,
            "minimum_return_pct": "2",
            "entry_window_start": "09:03",
            "entry_window_end": "12:45",
        },
    )
    snapshot = entry_set((rolling,))

    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (rolling,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    request = runtime.projection_requests[0]

    result = runtime.evaluate_projection(
        projection(requested_features=[requested_feature(request, value="0.03")]),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert request.parameters == {"window_minutes": 3}
    assert result.candidates[0].status is PaperSetStatus.TRIGGERED
    assert result.candidates[0].evaluations[0].observed[
        "window_minutes"
    ] == 3


def test_parameterized_orb_uses_exact_request_projection() -> None:
    orb = version(
        "opening_range_breakout_entry",
        1,
        {
            "opening_range_minutes": 15,
            "breakout_buffer_pct": "0.5",
            "entry_window_start": "09:15",
            "entry_window_end": "11:00",
        },
    )
    snapshot = entry_set((orb,))
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (orb,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    request = runtime.projection_requests[0]

    result = runtime.evaluate_projection(
        projection(
            price="101",
            requested_features=[requested_feature(request, value="100")],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert request.feature_id == "opening_range_high_v1"
    assert request.parameters == {"opening_range_minutes": 15}
    assert result.candidates[0].status is PaperSetStatus.TRIGGERED
    assert result.candidates[0].evaluations[0].threshold[
        "breakout_price"
    ] == "100.500"


def test_parameterized_ema_uses_exact_boolean_request_projection() -> None:
    ema = version(
        "ema_crossover_entry",
        1,
        {
            "fast_period": 5,
            "slow_period": 20,
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        },
    )
    snapshot = entry_set((ema,))
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (ema,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    request = runtime.projection_requests[0]

    triggered = runtime.evaluate_projection(
        projection(
            price="101",
            requested_features=[requested_feature(request, value=True)],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )
    not_triggered = runtime.evaluate_projection(
        projection(
            price="101",
            requested_features=[requested_feature(request, value=False)],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert request.feature_id == "ema_cross_up_v1"
    assert request.parameters == {"fast_period": 5, "slow_period": 20}
    assert triggered.candidates[0].status is PaperSetStatus.TRIGGERED
    assert not_triggered.candidates[0].status is PaperSetStatus.NOT_TRIGGERED


def test_parameterized_rsi_uses_exact_request_projection() -> None:
    rsi = version(
        "rsi_oversold_entry",
        1,
        {
            "rsi_period": 14,
            "oversold_threshold": "30",
            "entry_window_start": "09:15",
            "entry_window_end": "12:45",
        },
    )
    snapshot = entry_set((rsi,))
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (rsi,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    request = runtime.projection_requests[0]

    triggered = runtime.evaluate_projection(
        projection(
            price="95",
            requested_features=[requested_feature(request, value="25")],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )
    not_triggered = runtime.evaluate_projection(
        projection(
            price="101",
            requested_features=[requested_feature(request, value="31")],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert request.feature_id == "wilder_rsi_v1"
    assert request.parameters == {"rsi_period": 14}
    assert triggered.candidates[0].status is PaperSetStatus.TRIGGERED
    assert not_triggered.candidates[0].status is PaperSetStatus.NOT_TRIGGERED


def test_parameterized_bollinger_uses_exact_boolean_request_projection() -> None:
    bollinger = version(
        "bollinger_lower_reentry_entry",
        1,
        {
            "bollinger_period": 10,
            "stddev_multiplier": "1.5",
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        },
    )
    snapshot = entry_set((bollinger,))
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (bollinger,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    request = runtime.projection_requests[0]

    triggered = runtime.evaluate_projection(
        projection(
            price="100",
            requested_features=[requested_feature(request, value=True)],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )
    not_triggered = runtime.evaluate_projection(
        projection(
            price="100",
            requested_features=[requested_feature(request, value=False)],
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert request.feature_id == "bollinger_lower_reentry_v1"
    assert request.parameters == {
        "bollinger_period": 10,
        "stddev_multiplier": "1.5",
    }
    assert triggered.candidates[0].status is PaperSetStatus.TRIGGERED
    assert not_triggered.candidates[0].status is PaperSetStatus.NOT_TRIGGERED


def test_pre_g6_backtest_only_version_does_not_gain_paper_admission() -> None:
    rolling = version(
        "rolling_return_entry",
        1,
        {
            "window_minutes": 3,
            "minimum_return_pct": "2",
            "entry_window_start": "09:03",
            "entry_window_end": "12:45",
        },
    )
    template = AtomicStrategyRegistry().strategy(rolling.strategy_id).template
    legacy_document = template.template_document
    legacy_document["runtime_bindings"] = {
        "BACKTEST_KBAR_1M": template.runtime_bindings["BACKTEST_KBAR_1M"]
    }
    legacy = replace(
        rolling,
        template_digest=canonical_digest(legacy_document),
        configuration_digest="legacy-backtest-only-config",
    )
    snapshot = entry_set((legacy,))

    with pytest.raises(ValueError, match="Template digest"):
        resolve_atomic_paper_entry_set(
            FakeCatalog(snapshot, (legacy,)),
            AtomicStrategyRegistry(),
            snapshot.strategy_set_version_id,
        )


def test_parameterized_projection_identity_drift_fails_closed() -> None:
    rolling = version(
        "rolling_return_entry",
        1,
        {
            "window_minutes": 3,
            "minimum_return_pct": "2",
            "entry_window_start": "09:03",
            "entry_window_end": "12:45",
        },
    )
    snapshot = entry_set((rolling,))
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (rolling,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    row = requested_feature(runtime.projection_requests[0], value="0.03")
    row["implementation_digest"] = "tampered"

    result = runtime.evaluate_projection(
        projection(requested_features=[row]),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    assert result.candidates == ()
    assert "implementation_digest" in result.blocked_reasons[0]


def test_same_feature_with_different_parameters_keeps_member_identity() -> None:
    two_minute = version(
        "rolling_return_entry",
        1,
        {
            "window_minutes": 2,
            "minimum_return_pct": "2",
            "entry_window_start": "09:03",
            "entry_window_end": "12:45",
        },
    )
    three_minute = version(
        "rolling_return_entry",
        2,
        {
            "window_minutes": 3,
            "minimum_return_pct": "2",
            "entry_window_start": "09:03",
            "entry_window_end": "12:45",
        },
    )
    versions = (two_minute, three_minute)
    snapshot = entry_set(versions)
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, versions),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    requests = {
        request.parameters["window_minutes"]: request
        for request in runtime.projection_requests
    }

    result = runtime.evaluate_projection(
        projection(
            requested_features=[
                requested_feature(requests[2], value="0.01"),
                requested_feature(requests[3], value="0.03"),
            ]
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    evaluations = result.candidates[0].evaluations
    assert [item.status.value for item in evaluations] == [
        "NOT_TRIGGERED",
        "TRIGGERED",
    ]
    assert [item.observed["window_minutes"] for item in evaluations] == [2, 3]


def test_volume_missing_reason_is_preserved_for_strategy_evaluation() -> None:
    volume = version(
        "volume_acceleration_entry",
        1,
        {
            "window_minutes": 2,
            "baseline_window_count": 5,
            "minimum_complete_baseline_windows": 4,
            "baseline_method": "MEDIAN",
            "minimum_acceleration_ratio": "1.5",
            "entry_window_start": "09:10",
            "entry_window_end": "12:45",
        },
    )
    snapshot = entry_set((volume,))
    runtime = resolve_atomic_paper_entry_set(
        FakeCatalog(snapshot, (volume,)),
        AtomicStrategyRegistry(),
        snapshot.strategy_set_version_id,
    )
    request = runtime.projection_requests[0]

    result = runtime.evaluate_projection(
        projection(
            requested_features=[
                requested_feature(
                    request,
                    value=None,
                    reason="baseline_volume_windows_non_contiguous",
                )
            ]
        ),
        evaluated_at=AT,
        max_age_seconds=5,
    )

    candidate = result.candidates[0]
    assert candidate.status is PaperSetStatus.INSUFFICIENT_DATA
    assert candidate.evaluations[0].reason == (
        "baseline_volume_windows_non_contiguous"
    )
