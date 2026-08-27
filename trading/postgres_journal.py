"""Optional PostgreSQL implementation of the shared Journal port."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from trading.journal import (
    JournalAppendResult,
    JournalClockRegressionError,
    JournalConflictError,
    JournalCutoffExceededError,
    JournalRecord,
    JournalRepository,
    JournalSession,
    ProjectionCheckpoint,
)


PostgresDatabaseLocator = tuple[tuple[str, str], ...]
PostgresDatabaseIdentity = tuple[tuple[str, str], ...]
_DATABASE_IDENTITY_FIELDS = ("dbname", "user", "host", "hostaddr", "port")
_DATABASE_IDENTITY_QUERY = """
    SELECT current_database(),
           (SELECT oid::text FROM pg_database WHERE datname = current_database()),
           pg_postmaster_start_time(),
           COALESCE(inet_server_addr()::text, ''),
           COALESCE(inet_server_port()::text, '')
"""


def postgres_database_locator(database_url: str) -> PostgresDatabaseLocator:
    """Parse the credential-free endpoint declaration from one PostgreSQL DSN."""

    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("database_url must not be empty")
    value = database_url.strip()
    try:
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        parameters = _postgres_uri_parameters(value)
    else:
        try:
            parameters = conninfo_to_dict(value)
        except Exception:
            raise ValueError("database_url identity could not be inspected") from None
    identity = tuple(
        (field, str(parameters[field]))
        for field in _DATABASE_IDENTITY_FIELDS
        if parameters.get(field) not in (None, "")
    )
    if not any(field == "dbname" for field, _value in identity):
        raise ValueError("database_url must identify one PostgreSQL database")
    return identity


def _postgres_uri_parameters(database_url: str) -> dict[str, str]:
    try:
        parsed = urlsplit(database_url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise ValueError
        parameters = dict(parse_qsl(parsed.query, keep_blank_values=False))
        if parsed.path and parsed.path != "/":
            parameters["dbname"] = unquote(parsed.path.removeprefix("/"))
        if parsed.username is not None:
            parameters["user"] = unquote(parsed.username)
        if parsed.hostname is not None:
            parameters["host"] = parsed.hostname
        if parsed.port is not None:
            parameters["port"] = str(parsed.port)
    except (TypeError, ValueError):
        raise ValueError("database_url identity could not be inspected") from None
    return parameters


def postgres_resource_identity(connection: Any) -> PostgresDatabaseIdentity:
    """Read the actual database and postmaster that scope advisory locks."""

    try:
        with connection.cursor() as cursor:
            cursor.execute(_DATABASE_IDENTITY_QUERY)
            row = cursor.fetchone()
    except Exception:
        if not getattr(connection, "autocommit", False):
            try:
                connection.rollback()
            except Exception:
                pass
        raise ValueError("PostgreSQL resource identity could not be inspected") from None
    if not getattr(connection, "autocommit", False):
        try:
            connection.rollback()
        except Exception:
            raise ValueError(
                "PostgreSQL resource identity transaction could not be closed"
            ) from None
    if row is None or len(row) != 5 or not isinstance(row[2], datetime):
        raise ValueError("PostgreSQL resource identity returned an invalid row")
    started_at = row[2]
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("PostgreSQL postmaster start time must be timezone-aware")
    return (
        ("dbname", str(row[0])),
        ("database_oid", str(row[1])),
        (
            "postmaster_started_at",
            started_at.astimezone(timezone.utc).isoformat(),
        ),
        ("server_address", str(row[3])),
        ("server_port", str(row[4])),
    )


def _resource_database_identity(
    *,
    connection: Any | None,
    pool: Any | None,
) -> PostgresDatabaseIdentity:
    if connection is not None:
        return postgres_resource_identity(connection)
    connection_context = getattr(pool, "connection", None)
    if not callable(connection_context):
        raise ValueError("PostgreSQL pool cannot provide an identity connection")
    try:
        with connection_context() as pooled_connection:
            return postgres_resource_identity(pooled_connection)
    except ValueError:
        raise
    except Exception:
        raise ValueError("PostgreSQL pool identity could not be inspected") from None


def _validate_database_locator(
    *,
    database_locator: PostgresDatabaseLocator,
    database_identity: PostgresDatabaseIdentity,
) -> None:
    locator_database = dict(database_locator).get("dbname")
    actual_database = dict(database_identity).get("dbname")
    if locator_database != actual_database:
        raise ValueError(
            "database_url connection identity conflicts with PostgreSQL resource"
        )


class PostgresJournalRepository(JournalRepository):
    """Sync PostgreSQL adapter using one test connection or a runtime pool."""

    def __init__(
        self,
        connection: Any | None = None,
        *,
        pool: Any | None = None,
        owns_pool: bool = False,
        database_url: str | None = None,
    ) -> None:
        if (connection is None) == (pool is None):
            raise ValueError("provide exactly one PostgreSQL connection or pool")
        if owns_pool and pool is None:
            raise ValueError("owns_pool requires a pool")
        database_locator = (
            postgres_database_locator(database_url)
            if database_url is not None
            else None
        )
        database_identity = None
        if database_locator is not None:
            database_identity = _resource_database_identity(
                connection=connection,
                pool=pool,
            )
            _validate_database_locator(
                database_locator=database_locator,
                database_identity=database_identity,
            )
        self._connection = connection
        self._pool = pool
        self._owns_pool = owns_pool
        self._database_url = database_url.strip() if database_url is not None else None
        self._database_locator = database_locator
        self._database_identity = database_identity

    @property
    def database_url(self) -> str | None:
        """Return only the original DSN explicitly retained for a sibling guard."""

        return self._database_url

    @property
    def database_identity(self) -> PostgresDatabaseIdentity | None:
        """Return the actual database/postmaster identity read from the resource."""

        return self._database_identity

    @property
    def database_locator(self) -> PostgresDatabaseLocator | None:
        """Return the credential-free endpoint declaration retained for checks."""

        return self._database_locator

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        if self._pool is not None:
            with self._pool.connection() as connection:
                try:
                    if self._database_identity is not None:
                        current_identity = postgres_resource_identity(connection)
                        if current_identity != self._database_identity:
                            raise ValueError(
                                "PostgreSQL pool resource identity changed"
                            )
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
                self._start_session(cursor, session)

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

    def sessions(
        self,
        *,
        session_id_prefix: str,
    ) -> tuple[JournalSession, ...]:
        if type(session_id_prefix) is not str or not session_id_prefix.strip():
            raise ValueError("session_id_prefix must not be empty")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT session_id, started_at, mode, metadata_json::text,
                           schema_version
                    FROM trading.journal_sessions
                    WHERE LEFT(session_id, CHAR_LENGTH(%s)) = %s
                    ORDER BY session_id
                    """,
                    (session_id_prefix, session_id_prefix),
                )
                rows = cursor.fetchall()
        return tuple(
            JournalSession(
                session_id=row[0],
                started_at=row[1],
                mode=row[2],
                metadata=json.loads(row[3]),
                schema_version=row[4],
            )
            for row in rows
        )

    def append(self, record: JournalRecord) -> JournalAppendResult:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                return self._append(cursor, record)

    def start_session_and_append_before(
        self,
        session: JournalSession,
        record: JournalRecord,
        *,
        latest_allowed_at: datetime,
        authoritative_now: Callable[[], datetime] | None = None,
    ) -> JournalAppendResult:
        del authoritative_now
        if session.session_id != record.session_id:
            raise ValueError("atomic Journal session and record identity differ")
        _require_aware(latest_allowed_at, "latest_allowed_at")
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                accepted_at = self._server_time(cursor)
                self._require_monotonic_before_cutoff(
                    accepted_at,
                    latest_allowed_at,
                )
                existing_session = self._find_session(cursor, session.session_id)
                session_started_at = (
                    existing_session[0]
                    if existing_session is not None
                    else accepted_at
                )
                stored_session = replace(session, started_at=session_started_at)
                self._start_session(cursor, stored_session)
                after_session = self._server_time(cursor)
                self._require_monotonic_before_cutoff(
                    after_session,
                    latest_allowed_at,
                    previous=accepted_at,
                )
                stored_record_at = accepted_at
                if existing_session is not None:
                    existing_record = self._find_existing(cursor, record)
                    if existing_record is None:
                        raise JournalConflictError(
                            "atomic Journal session exists without its open record"
                        )
                    stored_record_at = _matching_stored_occurred_at(
                        record,
                        persisted_at=session_started_at,
                        stored_fingerprint=existing_record[1],
                    )
                stored_record = replace(record, occurred_at=stored_record_at)
                appended = self._append(cursor, stored_record)
                self._require_monotonic_before_cutoff(
                    self._server_time(cursor),
                    latest_allowed_at,
                    previous=after_session,
                )
                return appended

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
            record = _record_from_postgres_row(session_id, row)
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
    def _start_session(cursor: Any, session: JournalSession) -> None:
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
            existing = PostgresJournalRepository._find_session(
                cursor,
                session.session_id,
            )
            if existing is None or (
                existing[0] != session.started_at
                or existing[1] != session.mode
                or _json_text(existing[2]) != session.metadata_json
                or existing[3] != session.schema_version
            ):
                raise JournalConflictError(
                    "session metadata conflicts with existing session"
                )

    @staticmethod
    def _append(cursor: Any, record: JournalRecord) -> JournalAppendResult:
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
                _postgres_storage_fingerprint(record),
            ),
        )
        created = cursor.fetchone()
        if created is not None:
            return JournalAppendResult(record, int(created[0]), False)

        existing = PostgresJournalRepository._find_existing(cursor, record)
        if existing is None or not _stored_fingerprint_matches(
            record,
            existing[1],
        ):
            raise JournalConflictError(
                "Journal identity conflicts with existing record"
            )
        return JournalAppendResult(record, int(existing[0]), True)

    @staticmethod
    def _find_session(cursor: Any, session_id: str) -> tuple[Any, ...] | None:
        cursor.execute(
            """
            SELECT started_at, mode, metadata_json::text, schema_version
            FROM trading.journal_sessions
            WHERE session_id = %s
            """,
            (session_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def _server_time(cursor: Any) -> datetime:
        cursor.execute("SELECT clock_timestamp()")
        row = cursor.fetchone()
        if row is None or len(row) != 1 or not isinstance(row[0], datetime):
            raise RuntimeError("PostgreSQL Journal server clock is unavailable")
        _require_aware(row[0], "PostgreSQL Journal server time")
        return row[0]

    @staticmethod
    def _require_monotonic_before_cutoff(
        value: datetime,
        cutoff: datetime,
        *,
        previous: datetime | None = None,
    ) -> None:
        if previous is not None and value < previous:
            raise JournalClockRegressionError(
                "authoritative Journal time moved backwards"
            )
        if value > cutoff:
            raise JournalCutoffExceededError(
                "atomic Journal mutation exceeded its durable cutoff"
            )

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


_POSTGRES_FINGERPRINT_PREFIX = "postgres-journal-fingerprint-v2:"
_UTC = timezone.utc
_TAIPEI_FIXED_OFFSET = timezone(timedelta(hours=8))


def _postgres_storage_fingerprint(record: JournalRecord) -> str:
    """Bind the domain fingerprint to the original aware timestamp text.

    PostgreSQL ``TIMESTAMPTZ`` preserves the instant but renders it in the
    connection timezone.  The Journal fingerprint intentionally includes the
    original ISO offset, so the adapter must retain that representation too.
    """

    envelope = json.dumps(
        {
            "occurred_at": record.occurred_at.isoformat(),
            "record_fingerprint": record.fingerprint,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{_POSTGRES_FINGERPRINT_PREFIX}{envelope}"


def _stored_fingerprint_matches(record: JournalRecord, stored: object) -> bool:
    if not isinstance(stored, str):
        return False
    if stored.startswith(_POSTGRES_FINGERPRINT_PREFIX):
        return stored == _postgres_storage_fingerprint(record)
    return stored == record.fingerprint


def _matching_stored_occurred_at(
    record: JournalRecord,
    *,
    persisted_at: object,
    stored_fingerprint: object,
) -> datetime:
    """Recover the timestamp representation that produced a stored digest."""

    if not isinstance(persisted_at, datetime) or not isinstance(
        stored_fingerprint,
        str,
    ):
        raise JournalConflictError(
            "Journal identity conflicts with existing record"
        )
    candidates: list[datetime] = []
    if stored_fingerprint.startswith(_POSTGRES_FINGERPRINT_PREFIX):
        try:
            envelope = json.loads(
                stored_fingerprint.removeprefix(_POSTGRES_FINGERPRINT_PREFIX)
            )
            original = datetime.fromisoformat(envelope["occurred_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise JournalConflictError(
                "Journal identity conflicts with existing record"
            ) from error
        candidates.append(original)
    candidates.extend(
        (
            persisted_at,
            persisted_at.astimezone(_UTC),
            persisted_at.astimezone(_TAIPEI_FIXED_OFFSET),
        )
    )
    checked: set[str] = set()
    for candidate in candidates:
        if candidate.tzinfo is None or candidate.utcoffset() is None:
            continue
        identity = candidate.isoformat()
        if identity in checked:
            continue
        checked.add(identity)
        if _stored_fingerprint_matches(
            replace(record, occurred_at=candidate),
            stored_fingerprint,
        ):
            return candidate
    raise JournalConflictError("Journal identity conflicts with existing record")


def _record_from_postgres_row(
    session_id: str,
    row: tuple[object, ...],
) -> JournalRecord:
    stored = row[8]
    if not isinstance(stored, str):
        raise JournalConflictError(
            "stored fingerprint conflicts with reconstructed Journal record"
        )

    occurred_at = row[3]
    if not isinstance(occurred_at, datetime):
        raise JournalConflictError(
            "stored fingerprint conflicts with reconstructed Journal record"
        )

    if stored.startswith(_POSTGRES_FINGERPRINT_PREFIX):
        try:
            envelope = json.loads(stored.removeprefix(_POSTGRES_FINGERPRINT_PREFIX))
            original_occurred_at = datetime.fromisoformat(envelope["occurred_at"])
            expected_fingerprint = envelope["record_fingerprint"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise JournalConflictError(
                "stored fingerprint conflicts with reconstructed Journal record"
            ) from error
        if (
            original_occurred_at.tzinfo is None
            or original_occurred_at.utcoffset() is None
            or original_occurred_at != occurred_at
            or not isinstance(expected_fingerprint, str)
        ):
            raise JournalConflictError(
                "stored fingerprint conflicts with reconstructed Journal record"
            )
        record = _build_record_from_postgres_row(
            session_id,
            row,
            occurred_at=original_occurred_at,
        )
        if record.fingerprint != expected_fingerprint:
            raise JournalConflictError(
                "stored fingerprint conflicts with reconstructed Journal record"
            )
        return record

    # Legacy rows stored only the domain digest. PostgreSQL may return their
    # TIMESTAMPTZ in UTC even when the original Taiwan record used +08:00.
    # Try the persisted rendering plus the repository's two historical clock
    # representations; never accept a row whose digest matches none of them.
    candidates = (
        occurred_at,
        occurred_at.astimezone(_UTC),
        occurred_at.astimezone(_TAIPEI_FIXED_OFFSET),
    )
    checked: set[str] = set()
    for candidate in candidates:
        identity = candidate.isoformat()
        if identity in checked:
            continue
        checked.add(identity)
        record = _build_record_from_postgres_row(
            session_id,
            row,
            occurred_at=candidate,
        )
        if record.fingerprint == stored:
            return record
    raise JournalConflictError(
        "stored fingerprint conflicts with reconstructed Journal record"
    )


def _build_record_from_postgres_row(
    session_id: str,
    row: tuple[object, ...],
    *,
    occurred_at: datetime,
) -> JournalRecord:
    return JournalRecord(
        record_id=str(row[1]),
        session_id=session_id,
        kind=str(row[2]),
        occurred_at=occurred_at,
        payload=json.loads(str(row[4])),
        idempotency_scope=None if row[5] is None else str(row[5]),
        idempotency_key=None if row[6] is None else str(row[6]),
        schema_version=str(row[7]),
    )


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
