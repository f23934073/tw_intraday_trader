"""Optional PostgreSQL implementation of the shared Journal port."""

from __future__ import annotations

import json
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
    """Sync PostgreSQL adapter; callers own connection lifecycle and migrations."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def start_session(self, session: JournalSession) -> None:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO journal_sessions
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
                        FROM journal_sessions
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
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def append(self, record: JournalRecord) -> JournalAppendResult:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO journal_records (
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
                    self._connection.commit()
                    return JournalAppendResult(record, int(created[0]), False)

                existing = self._find_existing(cursor, record)
                if existing is None or existing[1] != record.fingerprint:
                    raise JournalConflictError(
                        "Journal identity conflicts with existing record"
                    )
                self._connection.commit()
                return JournalAppendResult(record, int(existing[0]), True)
        except Exception:
            self._connection.rollback()
            raise

    def records(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[JournalAppendResult, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT journal_sequence, record_id, kind, occurred_at,
                       payload_json::text, idempotency_scope, idempotency_key,
                       schema_version
                FROM journal_records
                WHERE session_id = %s AND journal_sequence > %s
                ORDER BY journal_sequence
                """,
                (session_id, after_sequence),
            )
            rows = cursor.fetchall()
        return tuple(
            JournalAppendResult(
                record=JournalRecord(
                    record_id=row[1],
                    session_id=session_id,
                    kind=row[2],
                    occurred_at=row[3],
                    payload=json.loads(row[4]),
                    idempotency_scope=row[5],
                    idempotency_key=row[6],
                    schema_version=row[7],
                ),
                sequence=int(row[0]),
                idempotent=False,
            )
            for row in rows
        )

    def save_checkpoint(self, checkpoint: ProjectionCheckpoint) -> None:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO projection_checkpoints (
                        session_id, projection_name, journal_sequence, digest,
                        schema_version
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, projection_name) DO UPDATE
                    SET journal_sequence = EXCLUDED.journal_sequence,
                        digest = EXCLUDED.digest,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE projection_checkpoints.journal_sequence
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
                        FROM projection_checkpoints
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
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def latest_checkpoint(
        self,
        session_id: str,
        projection_name: str,
    ) -> ProjectionCheckpoint | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT journal_sequence, digest, schema_version
                FROM projection_checkpoints
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

    @staticmethod
    def _find_existing(cursor: Any, record: JournalRecord) -> tuple[Any, ...] | None:
        cursor.execute(
            """
            SELECT journal_sequence, fingerprint
            FROM journal_records
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
            FROM journal_records
            WHERE idempotency_scope = %s AND idempotency_key = %s
            """,
            (record.idempotency_scope, record.idempotency_key),
        )
        return cursor.fetchone()


def _json_text(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(json.loads(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
