from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.migrations import apply_migrations
from simulation.atomic_runtime import resolve_atomic_paper_entry_set
from strategy_catalog.application import (
    AtomicStrategyCatalogService,
    build_atomic_strategy_service,
)
from strategy_catalog.drafts import PublishStrategyRequest, PublishStrategyResult
from strategy_catalog.domain import StrategyRole
from strategy_catalog.lifecycle import StrategyLifecycleStatus
from strategy_catalog.parameter_schema import canonical_digest, canonical_json
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository
from strategy_catalog.repository import StrategyCatalogConflict
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


def _request(draft_id: str, *, key: str = "publish-key", note: str = "reviewed"):
    return PublishStrategyRequest(
        draft_id=draft_id,
        idempotency_key=key,
        expected_draft_revision=1,
        actor_id="researcher",
        actor_session_id="local-session",
        change_note=note,
    )


def _append_lifecycle_transitions(
    connection,
    *,
    strategy_version_id: str,
    initial_event_id: str,
    targets: tuple[StrategyLifecycleStatus, ...],
) -> None:
    """Test helper that mirrors the frozen append-only lifecycle transaction."""

    current = StrategyLifecycleStatus.PUBLISHED
    last_event_id = initial_event_id
    occurred_at = datetime(2026, 8, 22, 2, 0, tzinfo=timezone.utc)
    with connection.cursor() as cursor:
        for sequence, target in enumerate(targets, start=2):
            event_id = str(uuid4())
            idempotency_key = f"test-transition-{sequence}-{target.value}"
            evidence = {"test_evidence": target.value}
            evidence_digest = canonical_digest(evidence)
            request_digest = canonical_digest(
                {
                    "strategy_version_id": strategy_version_id,
                    "to_status": target.value,
                    "expected_sequence": sequence - 1,
                    "evidence": evidence,
                }
            )
            event_time = occurred_at + timedelta(seconds=sequence)
            event_document = {
                "event_id": event_id,
                "strategy_version_id": strategy_version_id,
                "sequence": sequence,
                "event_type": "STATUS_TRANSITION",
                "from_status": current.value,
                "to_status": target.value,
                "evidence_digest": evidence_digest,
                "actor_id": "test-reviewer",
                "actor_session_id": "test-session",
                "idempotency_key": idempotency_key,
                "request_digest": request_digest,
                "expected_sequence": sequence - 1,
                "occurred_at": event_time.isoformat(),
            }
            event_digest = canonical_digest(event_document)
            projection_document = {
                "strategy_version_id": strategy_version_id,
                "status": target.value,
                "last_sequence": sequence,
                "last_event_id": event_id,
            }
            projection_digest = canonical_digest(projection_document)
            outbox_payload = {**event_document, "event_digest": event_digest}
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_events (
                    event_id, strategy_version_id, sequence, event_type,
                    from_status, to_status, evidence_json, evidence_digest,
                    reason, actor_id, actor_session_id, idempotency_key,
                    request_digest, expected_sequence, occurred_at, event_digest
                ) VALUES (
                    %s, %s, %s, 'STATUS_TRANSITION', %s, %s, %s::jsonb, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    event_id,
                    strategy_version_id,
                    sequence,
                    current.value,
                    target.value,
                    canonical_json(evidence),
                    evidence_digest,
                    "test lifecycle admission",
                    "test-reviewer",
                    "test-session",
                    idempotency_key,
                    request_digest,
                    sequence - 1,
                    event_time,
                    event_digest,
                ),
            )
            cursor.execute(
                """
                UPDATE backtest.strategy_version_state
                SET status = %s, last_sequence = %s, last_event_id = %s,
                    projection_digest = %s, updated_at = %s
                WHERE strategy_version_id = %s
                  AND last_sequence = %s AND last_event_id = %s
                """,
                (
                    target.value,
                    sequence,
                    event_id,
                    projection_digest,
                    event_time,
                    strategy_version_id,
                    sequence - 1,
                    last_event_id,
                ),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                """
                INSERT INTO backtest.strategy_lifecycle_outbox (
                    outbox_id, event_id, event_digest, topic, payload_json,
                    payload_digest, delivery_status, delivery_attempts, created_at
                ) VALUES (
                    %s, %s, %s, 'strategy.lifecycle.v1', %s::jsonb, %s,
                    'PENDING', 0, %s
                )
                """,
                (
                    str(uuid4()),
                    event_id,
                    event_digest,
                    canonical_json(outbox_payload),
                    canonical_digest(outbox_payload),
                    event_time,
                ),
            )
            current = target
            last_event_id = event_id
    connection.commit()


class _ReplayOnlyRepository:
    def __init__(self, result: PublishStrategyResult) -> None:
        self.result = result
        self.replay_calls = 0

    def replay_publish(self, request: PublishStrategyRequest) -> PublishStrategyResult:
        self.replay_calls += 1
        assert request.draft_id == self.result.draft_id
        return self.result

    def get_draft(self, draft_id: str):
        raise AssertionError("durable replay must not read the Draft through the Registry path")


def test_committed_publish_replay_does_not_require_current_template_registry() -> None:
    result = PublishStrategyResult(
        publish_operation_id="operation-1",
        draft_id="removed-strategy-draft",
        strategy_version_id="version-1",
        published_event_id="event-1",
        version_number=1,
        configuration_digest="configuration-digest",
        result_digest="result-digest",
        replayed=True,
    )
    repository = _ReplayOnlyRepository(result)
    service = AtomicStrategyCatalogService(repository, ())

    replay = service.publish(_request(result.draft_id))

    assert replay == result
    assert repository.replay_calls == 1


def test_atomic_strategy_factory_rejects_sqlite_and_unavailable_postgresql() -> None:
    templates = AtomicStrategyRegistry().templates()
    with pytest.raises(ValueError, match="只支援 PostgreSQL"):
        build_atomic_strategy_service(
            database_backend="sqlite",
            connection=None,
            templates=templates,
        )
    with pytest.raises(ValueError, match="無可用 PostgreSQL"):
        build_atomic_strategy_service(
            database_backend="postgresql",
            connection=None,
            templates=templates,
        )


def test_phase5_templates_sync_to_postgresql_with_parameter_bindings(
    postgres_test_connection,
) -> None:
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    service = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    service.sync_templates()

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT strategy_id, feature_requirements_json, runtime_bindings_json
            FROM backtest.strategy_templates
            ORDER BY strategy_id
            """
        )
        rows = cursor.fetchall()

    assert {row[0] for row in rows} == {
        template.strategy_id for template in registry.templates()
    }
    rolling = next(row for row in rows if row[0] == "rolling_return_entry")
    assert rolling[1][0]["parameter_bindings"] == {
        "window_minutes": "window_minutes"
    }
    assert set(rolling[2]) == {
        "BACKTEST_KBAR_1M",
        "LOCAL_PAPER_TICK_BIDASK",
    }


def test_first_publish_replays_and_seals_draft_in_one_postgresql_transaction(
    postgres_test_connection,
) -> None:
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    service = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    draft = service.create_draft(
        "above_vwap_entry",
        {},
        actor_id="researcher",
        change_note="first version",
    )
    request = _request(draft.draft_id)

    first = service.publish(request)
    replay = service.publish(request)

    assert replay.replayed is True
    assert replay.strategy_version_id == first.strategy_version_id
    assert replay.published_event_id == first.published_event_id
    assert replay.result_digest == first.result_digest
    sealed = service.get_draft(draft.draft_id)
    assert sealed.is_sealed is True
    assert sealed.revision == 2

    with pytest.raises(StrategyCatalogConflict) as different_digest:
        service.publish(_request(draft.draft_id, note="different request"))
    assert different_digest.value.code == "IDEMPOTENCY_CONFLICT"

    with pytest.raises(StrategyCatalogConflict) as different_key:
        service.publish(_request(draft.draft_id, key="another-key"))
    assert different_key.value.code == "DRAFT_ALREADY_PUBLISHED"

    with postgres_test_connection.cursor() as cursor:
        counts = {}
        for table in (
            "strategy_versions",
            "strategy_version_events",
            "strategy_version_state",
            "strategy_lifecycle_outbox",
            "strategy_publish_operations",
        ):
            cursor.execute(f"SELECT COUNT(*) FROM backtest.{table}")
            counts[table] = cursor.fetchone()[0]
    assert set(counts.values()) == {1}

    service_without_original_template = AtomicStrategyCatalogService(
        PostgresAtomicStrategyRepository(postgres_test_connection),
        (),
    )
    replay_after_removal = service_without_original_template.publish(request)
    assert replay_after_removal.replayed is True
    assert replay_after_removal.strategy_version_id == first.strategy_version_id
    with pytest.raises(StrategyCatalogConflict) as different_key_after_removal:
        service_without_original_template.publish(
            _request(draft.draft_id, key="different-key-after-removal")
        )
    assert different_key_after_removal.value.code == "DRAFT_ALREADY_PUBLISHED"


def test_concurrent_same_publish_key_returns_one_version_and_one_replay(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    setup = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    draft = setup.create_draft("above_vwap_entry", {}, actor_id="researcher")
    request = _request(draft.draft_id)
    barrier = Barrier(2)

    def publish_once():
        connection = psycopg.connect(postgres_test_dsn)
        try:
            service = AtomicStrategyCatalogService(
                PostgresAtomicStrategyRepository(connection),
                registry.templates(),
            )
            barrier.wait()
            return service.publish(request)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: publish_once(), range(2)))

    assert {item.replayed for item in results} == {False, True}
    assert len({item.strategy_version_id for item in results}) == 1
    assert len({item.published_event_id for item in results}) == 1


def test_concurrent_drafts_allocate_unique_monotonic_versions(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    setup = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    drafts = (
        setup.create_draft("above_vwap_entry", {}, actor_id="researcher-a"),
        setup.create_draft("above_vwap_entry", {}, actor_id="researcher-b"),
    )
    requests = tuple(
        PublishStrategyRequest(
            draft_id=draft.draft_id,
            idempotency_key=f"publish-{index}",
            expected_draft_revision=1,
            actor_id=f"researcher-{index}",
            actor_session_id=f"session-{index}",
        )
        for index, draft in enumerate(drafts)
    )
    barrier = Barrier(2)

    def publish_once(request: PublishStrategyRequest):
        connection = psycopg.connect(postgres_test_dsn)
        try:
            service = AtomicStrategyCatalogService(
                PostgresAtomicStrategyRepository(connection),
                registry.templates(),
            )
            barrier.wait()
            return service.publish(request)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(publish_once, requests))

    assert {item.version_number for item in results} == {1, 2}
    assert len({item.strategy_version_id for item in results}) == 2


def test_exact_strategy_set_is_immutable_and_reloads_from_postgresql(
    postgres_test_connection,
) -> None:
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    service = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    draft = service.create_draft("above_vwap_entry", {}, actor_id="researcher")
    published = service.publish(_request(draft.draft_id))
    version = service.get_version(published.strategy_version_id)
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="entry-set-version-1",
        strategy_set_id="entry-set",
        version_number=1,
        display_name_zh_tw="VWAP 進場組合",
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

    assert service.save_strategy_set(snapshot, actor_id="researcher") is True
    assert service.save_strategy_set(snapshot, actor_id="researcher") is False
    loaded = service.get_strategy_set(snapshot.strategy_set_version_id)

    assert loaded.to_dict() == snapshot.to_dict()
    assert loaded.snapshot_digest == snapshot.snapshot_digest

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.strategy_set_members
            SET attribution_priority = 1
            WHERE strategy_set_version_id = %s
            """,
            (snapshot.strategy_set_version_id,),
        )
    postgres_test_connection.commit()
    with pytest.raises(StrategyCatalogConflict) as relational_drift:
        service.get_strategy_set(snapshot.strategy_set_version_id)
    assert relational_drift.value.code == "STRATEGY_SET_INTEGRITY_ERROR"

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.strategy_set_members
            SET attribution_priority = 0
            WHERE strategy_set_version_id = %s
            """,
            (snapshot.strategy_set_version_id,),
        )
        cursor.execute(
            """
            UPDATE backtest.strategy_set_versions
            SET snapshot_json = jsonb_set(
                snapshot_json,
                '{display_name_zh_tw}',
                '"tampered"'::jsonb
            )
            WHERE strategy_set_version_id = %s
            """,
            (snapshot.strategy_set_version_id,),
        )
    postgres_test_connection.commit()
    with pytest.raises(StrategyCatalogConflict) as snapshot_drift:
        service.get_strategy_set(snapshot.strategy_set_version_id)
    assert snapshot_drift.value.code == "STRATEGY_SET_INTEGRITY_ERROR"


def test_strategy_set_archive_hides_family_but_preserves_exact_versions(
    postgres_test_connection,
) -> None:
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    service = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    draft = service.create_draft("above_vwap_entry", {}, actor_id="researcher")
    published = service.publish(_request(draft.draft_id, key="archive-family-publish"))
    version = service.get_version(published.strategy_version_id)
    member = StrategySetMemberSnapshot(
        strategy_version_id=version.strategy_version_id,
        strategy_id=version.strategy_id,
        role=StrategyRole.ENTRY,
        configuration_digest=version.configuration_digest,
        implementation_digest=version.implementation_digest,
        member_order=0,
        attribution_priority=0,
    )
    first = ExactStrategySetSnapshot(
        strategy_set_version_id="archive-family-version-1",
        strategy_set_id="archive-family",
        version_number=1,
        display_name_zh_tw="封存測試初版",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(member,),
    )
    second = ExactStrategySetSnapshot(
        strategy_set_version_id="archive-family-version-2",
        strategy_set_id=first.strategy_set_id,
        version_number=2,
        display_name_zh_tw="封存測試新版",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ALL,
        members=(member,),
    )
    service.save_strategy_set(
        first,
        actor_id="researcher",
        idempotency_key="archive-family-create",
        change_note="建立初版",
    )
    service.save_strategy_set(
        second,
        actor_id="researcher",
        idempotency_key="archive-family-revise",
        change_note="建立新版",
    )

    assert service.archive_strategy_set(
        second.strategy_set_version_id,
        actor_id="researcher",
        idempotency_key="archive-family-remove",
        change_note="不再提供新操作",
    ) is True
    assert service.is_strategy_set_archived(first.strategy_set_version_id) is True
    assert service.list_strategy_sets() == ()
    assert service.get_strategy_set(first.strategy_set_version_id).to_dict() == first.to_dict()
    assert service.get_strategy_set(second.strategy_set_version_id).to_dict() == second.to_dict()
    assert service.archive_strategy_set(
        second.strategy_set_version_id,
        actor_id="researcher",
        idempotency_key="archive-family-remove",
        change_note="不再提供新操作",
    ) is False

    with pytest.raises(StrategyCatalogConflict) as idempotency_conflict:
        service.archive_strategy_set(
            second.strategy_set_version_id,
            actor_id="researcher",
            idempotency_key="archive-family-remove",
            change_note="同 key 不同內容",
        )
    assert idempotency_conflict.value.code == "IDEMPOTENCY_CONFLICT"

    third = ExactStrategySetSnapshot(
        strategy_set_version_id="archive-family-version-3",
        strategy_set_id=first.strategy_set_id,
        version_number=3,
        display_name_zh_tw="不應建立的版本",
        stage=StrategyRole.ENTRY,
        policy=CompositionPolicy.ANY,
        members=(member,),
    )
    with pytest.raises(StrategyCatalogConflict) as archived_conflict:
        service.save_strategy_set(
            third,
            actor_id="researcher",
            idempotency_key="archive-family-revise-after-archive",
            change_note="封存後不可修訂",
        )
    assert archived_conflict.value.code == "STRATEGY_SET_ARCHIVED"


def test_paper_activation_requires_locked_paper_approved_lifecycle_evidence(
    postgres_test_connection,
) -> None:
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    service = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    draft = service.create_draft(
        "above_vwap_entry",
        {},
        actor_id="researcher",
    )
    published = service.publish(_request(draft.draft_id, key="paper-publish"))
    version = service.get_version(published.strategy_version_id)
    snapshot = ExactStrategySetSnapshot(
        strategy_set_version_id="paper-approved-set-version-1",
        strategy_set_id="paper-approved-set",
        version_number=1,
        display_name_zh_tw="Paper 核准組合",
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
    service.save_strategy_set(snapshot, actor_id="researcher")

    with pytest.raises(StrategyCatalogConflict) as not_approved:
        service.get_paper_activation_snapshot(snapshot.strategy_set_version_id)
    assert not_approved.value.code == "STRATEGY_VERSION_NOT_PAPER_APPROVED"
    assert not_approved.value.details["status"] == "PUBLISHED"

    _append_lifecycle_transitions(
        postgres_test_connection,
        strategy_version_id=version.strategy_version_id,
        initial_event_id=published.published_event_id,
        targets=(
            StrategyLifecycleStatus.REVIEWED,
            StrategyLifecycleStatus.BACKTESTED,
            StrategyLifecycleStatus.PAPER_APPROVED,
        ),
    )
    activation = service.get_paper_activation_snapshot(
        snapshot.strategy_set_version_id
    )

    assert activation.strategy_set.snapshot_digest == snapshot.snapshot_digest
    assert len(activation.members) == 1
    lifecycle = activation.members[0].lifecycle
    assert lifecycle.status is StrategyLifecycleStatus.PAPER_APPROVED
    assert lifecycle.last_sequence == 4
    assert lifecycle.last_event_id
    assert lifecycle.projection_digest == canonical_digest(
        lifecycle.projection_document
    )
    runtime = resolve_atomic_paper_entry_set(
        service,
        registry,
        snapshot.strategy_set_version_id,
    )
    assert runtime.pipeline.lifecycle_admissions == (lifecycle.to_dict(),)
    assert runtime.pipeline.snapshot_digest

    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE backtest.strategy_version_state
            SET status = 'RETIRED', projection_digest = %s
            WHERE strategy_version_id = %s
            """,
            (
                canonical_digest(
                    {
                        **lifecycle.projection_document,
                        "status": "RETIRED",
                    }
                ),
                version.strategy_version_id,
            ),
        )
    postgres_test_connection.commit()
    with pytest.raises(StrategyCatalogConflict) as event_drift:
        service.get_paper_activation_snapshot(snapshot.strategy_set_version_id)
    assert event_drift.value.code == "STRATEGY_LIFECYCLE_INTEGRITY_ERROR"


def test_web_draft_mutations_are_idempotent_and_audited(
    postgres_test_connection,
) -> None:
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    service = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )

    first = service.create_draft(
        "above_vwap_entry",
        {"minimum_distance_bps": "10"},
        actor_id="local-researcher",
        change_note="web draft",
        idempotency_key="web-draft-create-1",
    )
    replay = service.create_draft(
        "above_vwap_entry",
        {"minimum_distance_bps": "10"},
        actor_id="local-researcher",
        change_note="web draft",
        idempotency_key="web-draft-create-1",
    )
    assert replay.draft_id == first.draft_id

    with pytest.raises(StrategyCatalogConflict) as conflict:
        service.create_draft(
            "above_vwap_entry",
            {"minimum_distance_bps": "11"},
            actor_id="local-researcher",
            change_note="web draft",
            idempotency_key="web-draft-create-1",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"

    updated = service.update_draft(
        first.draft_id,
        {"minimum_distance_bps": "15"},
        expected_revision=1,
        actor_id="local-researcher",
        change_note="raise threshold",
        idempotency_key="web-draft-update-1",
    )
    update_replay = service.update_draft(
        first.draft_id,
        {"minimum_distance_bps": "15"},
        expected_revision=1,
        actor_id="local-researcher",
        change_note="raise threshold",
        idempotency_key="web-draft-update-1",
    )
    assert updated.revision == 2
    assert update_replay.revision == 2
    assert updated.parameters["minimum_distance_bps"] == "15"

    advanced = service.update_draft(
        first.draft_id,
        {"minimum_distance_bps": "25"},
        expected_revision=2,
        actor_id="local-researcher",
        change_note="advance mutable draft",
        idempotency_key="web-draft-update-2",
    )
    original_create_replay = service.create_draft(
        "above_vwap_entry",
        {"minimum_distance_bps": "10"},
        actor_id="local-researcher",
        change_note="web draft",
        idempotency_key="web-draft-create-1",
    )
    original_update_replay = service.update_draft(
        first.draft_id,
        {"minimum_distance_bps": "15"},
        expected_revision=1,
        actor_id="local-researcher",
        change_note="raise threshold",
        idempotency_key="web-draft-update-1",
    )
    assert advanced.revision == 3
    assert original_create_replay.revision == 1
    assert original_create_replay.parameters["minimum_distance_bps"] == "10"
    assert original_update_replay.revision == 2
    assert original_update_replay.parameters["minimum_distance_bps"] == "15"

    with postgres_test_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM backtest.strategy_mutation_operations")
        assert cursor.fetchone()[0] == 3
        cursor.execute("SELECT COUNT(*) FROM backtest.strategy_audit_events")
        assert cursor.fetchone()[0] == 3


def test_concurrent_web_draft_create_replays_one_durable_result(
    postgres_test_connection,
    postgres_test_dsn,
) -> None:
    psycopg = pytest.importorskip("psycopg")
    apply_migrations(postgres_test_connection)
    registry = AtomicStrategyRegistry()
    setup = build_atomic_strategy_service(
        database_backend="postgresql",
        connection=postgres_test_connection,
        templates=registry.templates(),
    )
    setup.sync_templates()
    barrier = Barrier(2)

    def create_once():
        connection = psycopg.connect(postgres_test_dsn)
        try:
            service = AtomicStrategyCatalogService(
                PostgresAtomicStrategyRepository(connection),
                registry.templates(),
            )
            barrier.wait()
            return service.create_draft(
                "above_vwap_entry",
                {"minimum_distance_bps": "20"},
                actor_id="local-researcher",
                change_note="concurrent web request",
                idempotency_key="web-draft-concurrent-1",
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: create_once(), range(2)))

    assert len({item.draft_id for item in results}) == 1
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM backtest.strategy_mutation_operations
            WHERE operation_scope = 'strategy-draft:create:above_vwap_entry'
              AND idempotency_key = 'web-draft-concurrent-1'
            """
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM backtest.strategy_audit_events
            WHERE operation_scope = 'strategy-draft:create:above_vwap_entry'
              AND idempotency_key = 'web-draft-concurrent-1'
            """
        )
        assert cursor.fetchone()[0] == 1
