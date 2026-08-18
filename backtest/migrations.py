"""Forward-only PostgreSQL migrations for platform backtest persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


def migration_files() -> tuple[Path, ...]:
    return tuple(sorted(MIGRATIONS_DIRECTORY.glob("*.sql")))


def apply_migrations(connection: Any) -> tuple[str, ...]:
    """Apply each previously unapplied migration in one DB-API transaction."""

    applied: list[str] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for path in migration_files():
                cursor.execute(
                    "SELECT 1 FROM backtest_schema_migrations WHERE version = %s",
                    (path.name,),
                )
                if cursor.fetchone() is not None:
                    continue
                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO backtest_schema_migrations (version) VALUES (%s)",
                    (path.name,),
                )
                applied.append(path.name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return tuple(applied)
