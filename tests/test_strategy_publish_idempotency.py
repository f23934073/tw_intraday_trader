from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.migrations import apply_migrations
from strategy_catalog.application import (
    AtomicStrategyCatalogService,
    build_atomic_strategy_service,
)
from strategy_catalog.drafts import PublishStrategyRequest, PublishStrategyResult
from strategy_catalog.domain import StrategyRole
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
    unrelated_template = AtomicStrategyRegistry().strategy(
        "breakout_previous_high_entry"
    ).template
    service = AtomicStrategyCatalogService(repository, (unrelated_template,))

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
        (registry.strategy("breakout_previous_high_entry").template,),
    )
    replay_after_removal = service_without_original_template.publish(request)
    assert replay_after_removal.replayed is True
    assert replay_after_removal.strategy_version_id == first.strategy_version_id


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
