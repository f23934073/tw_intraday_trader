from __future__ import annotations

import json

import pytest

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.migrations import apply_migrations
from scripts.publish_r6_g1_strategy_versions import (
    FROZEN_ADMISSIONS,
    _existing_version,
    publish_versions,
)
from strategy_catalog.application import AtomicStrategyCatalogService
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository


def _publish_frozen_versions(connection):
    apply_migrations(connection)
    registry = AtomicStrategyRegistry()
    AtomicStrategyCatalogService(
        PostgresAtomicStrategyRepository(connection), registry.templates()
    ).sync_templates()
    values = publish_versions(connection, execute=True)
    assert len(values) == 4
    return registry, FROZEN_ADMISSIONS[0]


def test_g1_durable_publication_evidence_rebuilds_from_postgresql(
    postgres_test_connection,
) -> None:
    registry, frozen = _publish_frozen_versions(postgres_test_connection)
    evidence = _existing_version(postgres_test_connection, frozen, registry)
    assert evidence is not None
    assert evidence["publish_actor_id"] == "r6-g1-research-operator"
    assert evidence["lifecycle_status"] == "PUBLISHED"
    assert evidence["lifecycle_sequence"] == 1


@pytest.mark.parametrize(
    "tamper_sql",
    (
        """
        UPDATE backtest.strategy_versions
        SET parameters_json = %s::jsonb
        WHERE strategy_id = 'breakout_previous_high_entry'
        """,
        """
        UPDATE backtest.strategy_version_events
        SET actor_id = 'tampered-actor'
        WHERE strategy_version_id = (
            SELECT strategy_version_id
            FROM backtest.strategy_versions
            WHERE strategy_id = 'breakout_previous_high_entry'
        )
        """,
        """
        UPDATE backtest.strategy_publish_operations
        SET result_digest = repeat('b', 64)
        WHERE strategy_version_id = (
            SELECT strategy_version_id
            FROM backtest.strategy_versions
            WHERE strategy_id = 'breakout_previous_high_entry'
        )
        """,
    ),
)
def test_g1_durable_publication_tamper_fails_closed(
    postgres_test_connection,
    tamper_sql: str,
) -> None:
    registry, frozen = _publish_frozen_versions(postgres_test_connection)
    parameters = {
        "buffer_bps": "1",
        "entry_window_start": "09:02",
        "entry_window_end": "12:45",
    }
    with postgres_test_connection.cursor() as cursor:
        if "%s" in tamper_sql:
            cursor.execute(tamper_sql, (json.dumps(parameters),))
        else:
            cursor.execute(tamper_sql)
    postgres_test_connection.commit()

    with pytest.raises(RuntimeError, match="drift|重建"):
        _existing_version(postgres_test_connection, frozen, registry)
