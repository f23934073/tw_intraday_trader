from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
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


def projection(*, at: datetime = AT, price: str = "101") -> dict:
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
            }
        ],
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


def test_parameterized_rolling_strategy_fails_closed_without_tick_adapter() -> None:
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

    with pytest.raises(ValueError, match="沒有 LOCAL_PAPER_TICK_BIDASK binding"):
        resolve_atomic_paper_entry_set(
            FakeCatalog(snapshot, (rolling,)),
            AtomicStrategyRegistry(),
            snapshot.strategy_set_version_id,
        )
