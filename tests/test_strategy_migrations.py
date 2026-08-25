from __future__ import annotations

from backtest.migrations import apply_migrations, migration_files
from tests.conftest import postgres_test_database_is_safe


ATOMIC_TABLES = (
    "strategy_templates",
    "strategy_version_drafts",
    "strategy_versions",
    "strategy_publish_operations",
    "strategy_version_events",
    "strategy_version_state",
    "strategy_lifecycle_outbox",
    "strategy_set_versions",
    "strategy_set_members",
    "strategy_set_archives",
    "strategy_mutation_operations",
    "strategy_audit_events",
    "backtest_qualifications",
    "backtest_experiment_families",
    "backtest_experiment_attempts",
    "backtest_cash_admission_control_heads",
    "backtest_cash_admission_control_registrations",
    "backtest_cash_admission_control_operations",
)

EXPECTED_CONSTRAINT_COUNTS = {
    "strategy_templates": 3,
    "strategy_version_drafts": 4,
    "strategy_versions": 6,
    "strategy_publish_operations": 9,
    "strategy_version_events": 8,
    "strategy_version_state": 5,
    "strategy_lifecycle_outbox": 5,
    "strategy_set_versions": 7,
    "strategy_set_members": 8,
    "strategy_set_archives": 3,
    "strategy_mutation_operations": 1,
    "strategy_audit_events": 1,
    "backtest_qualifications": 10,
    "backtest_experiment_families": 10,
    "backtest_experiment_attempts": 8,
    "backtest_cash_admission_control_heads": 4,
    "backtest_cash_admission_control_registrations": 13,
    "backtest_cash_admission_control_operations": 5,
}

ATOMIC_INDEXES = (
    "strategy_version_drafts_strategy_index",
    "strategy_versions_strategy_index",
    "strategy_version_events_stream_index",
    "strategy_lifecycle_outbox_pending_index",
    "strategy_mutation_operations_actor_index",
    "strategy_audit_resource_index",
    "strategy_audit_operation_index",
    "strategy_audit_outcome_index",
    "strategy_set_archives_time_index",
    "backtest_qualifications_created_index",
    "backtest_qualifications_runs_index",
    "backtest_qualifications_family_index",
    "backtest_experiment_families_created_index",
    "backtest_experiment_attempts_family_index",
    "backtest_qualifications_family_sequence_index",
    "backtest_cash_control_registration_status_index",
    "backtest_cash_control_operation_created_index",
)


def test_atomic_strategy_migration_is_numbered_and_owned_by_runner() -> None:
    files = migration_files()
    assert files[-1].name == "014_cash_admission_controls.sql"
    sql = "\n".join(file.read_text(encoding="utf-8") for file in files[-10:])
    for table in ATOMIC_TABLES:
        assert f"backtest.{table}" in sql


def test_postgresql_fixture_requires_test_database_name_or_explicit_sentinel() -> None:
    assert postgres_test_database_is_safe("tw_intraday_trader_test", False) is True
    assert postgres_test_database_is_safe("postgres", True) is True
    assert postgres_test_database_is_safe("trading_dev", False) is False
    assert postgres_test_database_is_safe("contest_prod", False) is False


def test_atomic_strategy_migration_applies_once_to_postgresql(
    postgres_test_connection,
) -> None:
    first = apply_migrations(postgres_test_connection)
    second = apply_migrations(postgres_test_connection)

    assert "005_atomic_strategy_platform.sql" in first
    assert "006_atomic_strategy_web_management.sql" in first
    assert "007_atomic_strategy_audit_contract.sql" in first
    assert "008_backtest_qualification.sql" in first
    assert "009_backtest_experiment_families.sql" in first
    assert "010_backtest_experiment_family_identity.sql" in first
    assert "011_strategy_set_archives.sql" in first
    assert "012_backtest_dataset_bindings.sql" in first
    assert "013_backtest_result_chunks.sql" in first
    assert "014_cash_admission_controls.sql" in first
    assert second == ()
    with postgres_test_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'backtest'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (list(ATOMIC_TABLES),),
        )
        assert tuple(row[0] for row in cursor.fetchall()) == tuple(sorted(ATOMIC_TABLES))

        cursor.execute(
            """
            SELECT relation.relname, COUNT(*)
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'backtest'
              AND relation.relname = ANY(%s)
            GROUP BY relation.relname
            ORDER BY relation.relname
            """,
            (list(ATOMIC_TABLES),),
        )
        assert dict(cursor.fetchall()) == EXPECTED_CONSTRAINT_COUNTS

        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'backtest'
              AND indexname = ANY(%s)
            ORDER BY indexname
            """,
            (list(ATOMIC_INDEXES),),
        )
        assert tuple(row[0] for row in cursor.fetchall()) == tuple(sorted(ATOMIC_INDEXES))
