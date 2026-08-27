"""Optional PostgreSQL implementation of the shared Journal port."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from trading.journal import (
    JournalAppendResult,
    JournalConflictError,
    JournalRecord,
    JournalRepository,
    JournalSession,
    ProjectionCheckpoint,
)


class PostgresJournalRepository(JournalRepository):
    """Sync PostgreSQL adapter using one test connection or a runtime pool."""

    def __init__(
        self,
        connection: Any | None = None,
        *,
        pool: Any | None = None,
        owns_pool: bool = False,
    ) -> None:
        if (connection is None) == (pool is None):
            raise ValueError("provide exactly one PostgreSQL connection or pool")
        if owns_pool and pool is None:
            raise ValueError("owns_pool requires a pool")
        self._connection = connection
        self._pool = pool
        self._owns_pool = owns_pool

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        if self._pool is not None:
            with self._pool.connection() as connection:
                try:
                    yield connection
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            return

        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def start_session(self, session: JournalSession) -> None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO trading.journal_sessions
                        (session_id, started_at, mode, metadata_json, schema_version)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        session.session_id,
                        session.started_at,
                        session.mode,
                        session.metadata_json,
                        session.schema_version,
                    ),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        SELECT started_at, mode, metadata_json::text, schema_version
                        FROM trading.journal_sessions
                        WHERE session_id = %s
                        """,
                        (session.session_id,),
                    )
                    existing = cursor.fetchone()
                    if existing is None or (
                        existing[0] != session.started_at
                        or existing[1] != session.mode
                        or _json_text(existing[2]) != session.metadata_json
                        or existing[3] != session.schema_version
                    ):
                        raise JournalConflictError(
                            "session metadata conflicts with existing session"
                        )

    def session(self, session_id: str) -> JournalSession | None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT started_at, mode, metadata_json::text, schema_version
                    FROM trading.journal_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return JournalSession(
            session_id=session_id,
            started_at=row[0],
            mode=row[1],
            metadata=json.loads(row[2]),
            schema_version=row[3],
        )

    def append(self, record: JournalRecord) -> JournalAppendResult:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO trading.journal_records (
                        session_id, record_id, kind, occurred_at, payload_json,
                        idempotency_scope, idempotency_key, schema_version, fingerprint
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING journal_sequence
                    """,
                    (
                        record.session_id,
                        record.record_id,
                        record.kind,
                        record.occurred_at,
                        record.payload_json,
                        record.idempotency_scope,
                        record.idempotency_key,
                        record.schema_version,
                        record.fingerprint,
                    ),
                )
                created = cursor.fetchone()
                if created is not None:
                    return JournalAppendResult(record, int(created[0]), False)

                existing = self._find_existing(cursor, record)
                if existing is None or existing[1] != record.fingerprint:
                    raise JournalConflictError(
                        "Journal identity conflicts with existing record"
                    )
                return JournalAppendResult(record, int(existing[0]), True)

    def records(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[JournalAppendResult, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT journal_sequence, record_id, kind, occurred_at,
                           payload_json::text, idempotency_scope, idempotency_key,
                           schema_version, fingerprint
                    FROM trading.journal_records
                    WHERE session_id = %s AND journal_sequence > %s
                    ORDER BY journal_sequence
                    """,
                    (session_id, after_sequence),
                )
                rows = cursor.fetchall()
        results: list[JournalAppendResult] = []
        for row in rows:
            record = JournalRecord(
                record_id=row[1],
                session_id=session_id,
                kind=row[2],
                occurred_at=row[3],
                payload=json.loads(row[4]),
                idempotency_scope=row[5],
                idempotency_key=row[6],
                schema_version=row[7],
            )
            if record.fingerprint != row[8]:
                raise JournalConflictError(
                    "stored fingerprint conflicts with reconstructed Journal record"
                )
            results.append(
                JournalAppendResult(
                    record=record,
                    sequence=int(row[0]),
                    idempotent=False,
                )
            )
        return tuple(results)

    def save_checkpoint(self, checkpoint: ProjectionCheckpoint) -> None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO trading.projection_checkpoints AS current_checkpoint (
                        session_id, projection_name, journal_sequence, digest,
                        schema_version
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, projection_name) DO UPDATE
                    SET journal_sequence = EXCLUDED.journal_sequence,
                        digest = EXCLUDED.digest,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE current_checkpoint.journal_sequence
                        < EXCLUDED.journal_sequence
                    """,
                    (
                        checkpoint.session_id,
                        checkpoint.projection_name,
                        checkpoint.journal_sequence,
                        checkpoint.digest,
                        checkpoint.schema_version,
                    ),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        SELECT journal_sequence, digest, schema_version
                        FROM trading.projection_checkpoints
                        WHERE session_id = %s AND projection_name = %s
                        """,
                        (checkpoint.session_id, checkpoint.projection_name),
                    )
                    existing = cursor.fetchone()
                    if existing is None or existing != (
                        checkpoint.journal_sequence,
                        checkpoint.digest,
                        checkpoint.schema_version,
                    ):
                        raise JournalConflictError(
                            "projection checkpoint cannot move backward"
                        )

    def latest_checkpoint(
        self,
        session_id: str,
        projection_name: str,
    ) -> ProjectionCheckpoint | None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT journal_sequence, digest, schema_version
                    FROM trading.projection_checkpoints
                    WHERE session_id = %s AND projection_name = %s
                    """,
                    (session_id, projection_name),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return ProjectionCheckpoint(
            session_id=session_id,
            projection_name=projection_name,
            journal_sequence=int(row[0]),
            digest=row[1],
            schema_version=row[2],
        )

    def check_health(self) -> None:
        """Fail if the pool/connection cannot complete a round trip."""

        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("PostgreSQL Journal health check returned no row")

    def close(self) -> None:
        """Close only the production pool explicitly owned by this adapter."""

        if self._owns_pool and self._pool is not None:
            self._pool.close()

    @staticmethod
    def _find_existing(cursor: Any, record: JournalRecord) -> tuple[Any, ...] | None:
        cursor.execute(
            """
            SELECT journal_sequence, fingerprint
            FROM trading.journal_records
            WHERE session_id = %s AND record_id = %s
            """,
            (record.session_id, record.record_id),
        )
        existing = cursor.fetchone()
        if existing is not None or record.idempotency_scope is None:
            return existing
        cursor.execute(
            """
            SELECT journal_sequence, fingerprint
            FROM trading.journal_records
            WHERE idempotency_scope = %s AND idempotency_key = %s
            """,
            (record.idempotency_scope, record.idempotency_key),
        )
        return cursor.fetchone()


def _json_text(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(json.loads(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
