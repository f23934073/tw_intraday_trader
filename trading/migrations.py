"""Forward-only SQL migration runner for the optional PostgreSQL adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


def migration_files() -> tuple[Path, ...]:
    return tuple(sorted(MIGRATIONS_DIRECTORY.glob("*.sql")))


def apply_migrations(connection: Any) -> tuple[str, ...]:
    """Apply each unrecorded SQL migration transactionally and in filename order."""

    applied: list[str] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for path in migration_files():
                version = path.name
                cursor.execute(
                    "SELECT 1 FROM journal_schema_migrations WHERE version = %s",
                    (version,),
                )
                if cursor.fetchone() is not None:
                    continue
                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO journal_schema_migrations (version) VALUES (%s)",
                    (version,),
                )
                applied.append(version)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return tuple(applied)
