"""Forward-only migrations for Candidate Prior durable persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


def migration_files() -> tuple[Path, ...]:
    return tuple(sorted(MIGRATIONS_DIRECTORY.glob("*.sql")))


def apply_migrations(
    connection: Any,
    *,
    placeholder: str,
) -> tuple[str, ...]:
    """Apply each unapplied migration in one DB-API transaction."""

    if placeholder not in {"?", "%s"}:
        raise ValueError("unsupported DB-API placeholder")
    cursor = connection.cursor()
    applied: list[str] = []
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS institutional_prior_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (CAST(CURRENT_TIMESTAMP AS TEXT))
            )
            """
        )
        for path in migration_files():
            cursor.execute(
                "SELECT 1 FROM institutional_prior_schema_migrations "
                f"WHERE version = {placeholder}",
                (path.name,),
            )
            if cursor.fetchone() is not None:
                continue
            for statement in _migration_statements(path.read_text(encoding="utf-8")):
                cursor.execute(statement)
            cursor.execute(
                "INSERT INTO institutional_prior_schema_migrations (version) "
                f"VALUES ({placeholder})",
                (path.name,),
            )
            applied.append(path.name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return tuple(applied)


def _migration_statements(sql: str) -> tuple[str, ...]:
    """Split the project's statement-only migration files for DB-API parity."""

    return tuple(statement.strip() for statement in sql.split(";") if statement.strip())
