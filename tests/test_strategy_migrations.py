from __future__ import annotations

from backtest.migrations import apply_migrations, migration_files


def test_atomic_strategy_migration_is_numbered_and_owned_by_runner() -> None:
    files = migration_files()
    assert files[-1].name == "005_atomic_strategy_platform.sql"
    sql = files[-1].read_text(encoding="utf-8")
    for table in (
        "strategy_templates",
        "strategy_version_drafts",
        "strategy_versions",
        "strategy_publish_operations",
        "strategy_version_events",
        "strategy_version_state",
        "strategy_lifecycle_outbox",
        "strategy_set_versions",
        "strategy_set_members",
    ):
        assert f"backtest.{table}" in sql


def test_atomic_strategy_migration_applies_once_to_postgresql(
    postgres_test_connection,
) -> None:
    first = apply_migrations(postgres_test_connection)
    second = apply_migrations(postgres_test_connection)

    assert "005_atomic_strategy_platform.sql" in first
    assert second == ()
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                to_regclass('backtest.strategy_templates'),
                to_regclass('backtest.strategy_publish_operations'),
                to_regclass('backtest.strategy_lifecycle_outbox')
            """
        )
        assert cursor.fetchone() == (
            "backtest.strategy_templates",
            "backtest.strategy_publish_operations",
            "backtest.strategy_lifecycle_outbox",
        )
