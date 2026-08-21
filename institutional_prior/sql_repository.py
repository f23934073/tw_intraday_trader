"""Shared DB-API implementation for Candidate Prior persistence adapters."""

from __future__ import annotations

import json
from contextlib import contextmanager
from threading import RLock
from typing import Any, Iterator, Mapping

from institutional_data.serialization import canonical_json

from .domain import CandidatePriorArtifact, CandidatePriorEntry
from .repository import (
    ARTIFACT_CONTRACT_MISMATCH,
    NON_DETERMINISTIC_REPLAY,
    PERSISTED_ARTIFACT_MISMATCH,
    CandidatePriorPersistenceError,
)
from .serialization import (
    CANDIDATE_PRIOR_ARTIFACT_SCHEMA_VERSION,
    candidate_prior_run_identity_sha256,
    deserialize_candidate_prior_artifact,
    serialize_candidate_prior_entry_payload,
)

_ARTIFACT_COLUMNS = (
    "artifact_id",
    "run_identity_digest",
    "artifact_digest",
    "schema_version",
    "target_session",
    "as_of_session",
    "generated_at",
    "factor_prior_id",
    "factor_prior_digest",
    "price_prior_id",
    "price_prior_digest",
    "universe_id",
    "universe_digest",
    "calendar_id",
    "calendar_digest",
    "hypothesis_definitions_json",
    "research_status",
    "strategy_ready",
    "production_ready",
    "live_admission_ready",
    "execution_allowed",
    "issue_codes_json",
    "entry_count",
    "projected_candidate_count",
    "entries_digest",
    "artifact_json",
)

_ENTRY_COLUMNS = (
    "artifact_id",
    "entry_ordinal",
    "market",
    "symbol",
    "candidate_rank",
    "price_rank",
    "cohorts_json",
    "matched_hypotheses_json",
    "selection_reason_codes_json",
    "foreign_5d_value",
    "foreign_5d_percentile",
    "trust_5d_value",
    "trust_5d_percentile",
    "entry_digest",
    "entry_json",
)


class SqlCandidatePriorRepository:
    """Persist canonical bytes and verify every normalized row projection."""

    def __init__(self, connection: Any, *, placeholder: str) -> None:
        if placeholder not in {"?", "%s"}:
            raise ValueError("unsupported DB-API placeholder")
        self._connection = connection
        self._placeholder = placeholder
        self._lock = RLock()

    def close(self) -> None:
        self._connection.close()

    def save(self, artifact: CandidatePriorArtifact) -> bool:
        canonical_artifact = self._validate_input(artifact)
        run_identity = candidate_prior_run_identity_sha256(
            canonical_artifact.manifest.run
        )
        header = _artifact_row(canonical_artifact, run_identity)
        entries = tuple(
            _entry_row(canonical_artifact.artifact_id, ordinal, entry)
            for ordinal, entry in enumerate(canonical_artifact.entries)
        )
        with self._transaction() as cursor:
            self._execute(
                cursor,
                f"""
                INSERT INTO institutional_candidate_prior_artifacts (
                    {", ".join(_ARTIFACT_COLUMNS)}
                ) VALUES ({", ".join("?" for _ in _ARTIFACT_COLUMNS)})
                ON CONFLICT DO NOTHING
                """,
                tuple(header[column] for column in _ARTIFACT_COLUMNS),
            )
            if cursor.rowcount == 0:
                existing_id = self._conflicting_artifact_id(
                    cursor,
                    artifact_id=canonical_artifact.artifact_id,
                    run_identity=run_identity,
                )
                if existing_id is None:
                    raise CandidatePriorPersistenceError(
                        NON_DETERMINISTIC_REPLAY,
                        "a uniqueness conflict could not be resolved",
                    )
                existing = self._load_verified(cursor, existing_id)
                if existing == canonical_artifact:
                    return False
                raise CandidatePriorPersistenceError(
                    NON_DETERMINISTIC_REPLAY,
                    "the same run identity produced different artifact bytes",
                )
            self._executemany(
                cursor,
                f"""
                INSERT INTO institutional_candidate_prior_entries (
                    {", ".join(_ENTRY_COLUMNS)}
                ) VALUES ({", ".join("?" for _ in _ENTRY_COLUMNS)})
                """,
                tuple(
                    tuple(row[column] for column in _ENTRY_COLUMNS) for row in entries
                ),
            )
            self._load_verified(cursor, canonical_artifact.artifact_id)
        return True

    def get(self, artifact_id: str) -> CandidatePriorArtifact | None:
        with self._cursor() as cursor:
            if not self._artifact_exists(cursor, artifact_id):
                return None
            return self._load_verified(cursor, artifact_id)

    def _validate_input(
        self, artifact: CandidatePriorArtifact
    ) -> CandidatePriorArtifact:
        try:
            rebuilt = deserialize_candidate_prior_artifact(
                artifact.artifact_json,
                expected_digest=artifact.artifact_digest,
            )
        except (TypeError, ValueError) as error:
            raise CandidatePriorPersistenceError(
                ARTIFACT_CONTRACT_MISMATCH,
                str(error),
            ) from error
        if rebuilt != artifact:
            raise CandidatePriorPersistenceError(
                ARTIFACT_CONTRACT_MISMATCH,
                "domain object differs from its canonical artifact bytes",
            )
        return rebuilt

    def _load_verified(self, cursor: Any, artifact_id: str) -> CandidatePriorArtifact:
        header = self._select_one(
            cursor,
            f"SELECT {', '.join(_ARTIFACT_COLUMNS)} "
            "FROM institutional_candidate_prior_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        )
        if header is None:
            raise CandidatePriorPersistenceError(
                PERSISTED_ARTIFACT_MISMATCH,
                "artifact header disappeared during verification",
            )
        try:
            artifact = deserialize_candidate_prior_artifact(
                str(header["artifact_json"]),
                expected_digest=str(header["artifact_digest"]),
            )
        except (TypeError, ValueError) as error:
            raise CandidatePriorPersistenceError(
                PERSISTED_ARTIFACT_MISMATCH,
                str(error),
            ) from error
        run_identity = candidate_prior_run_identity_sha256(artifact.manifest.run)
        expected_header = _artifact_row(artifact, run_identity)
        _require_row_parity(
            header,
            expected_header,
            _ARTIFACT_COLUMNS,
            "artifact header",
        )
        self._execute(
            cursor,
            f"SELECT {', '.join(_ENTRY_COLUMNS)} "
            "FROM institutional_candidate_prior_entries "
            "WHERE artifact_id = ? ORDER BY entry_ordinal",
            (artifact_id,),
        )
        rows = tuple(self._row(cursor, row) for row in cursor.fetchall())
        expected_entries = tuple(
            _entry_row(artifact_id, ordinal, entry)
            for ordinal, entry in enumerate(artifact.entries)
        )
        if len(rows) != len(expected_entries):
            raise CandidatePriorPersistenceError(
                PERSISTED_ARTIFACT_MISMATCH,
                "persisted entry count differs from canonical bytes",
            )
        for ordinal, (row, expected) in enumerate(zip(rows, expected_entries)):
            _require_row_parity(
                row,
                expected,
                _ENTRY_COLUMNS,
                f"entry row {ordinal}",
            )
        return artifact

    def _conflicting_artifact_id(
        self,
        cursor: Any,
        *,
        artifact_id: str,
        run_identity: str,
    ) -> str | None:
        row = self._select_one(
            cursor,
            "SELECT artifact_id FROM institutional_candidate_prior_artifacts "
            "WHERE run_identity_digest = ? OR artifact_id = ?",
            (run_identity, artifact_id),
        )
        return None if row is None else str(row["artifact_id"])

    def _artifact_exists(self, cursor: Any, artifact_id: str) -> bool:
        row = self._select_one(
            cursor,
            "SELECT artifact_id FROM institutional_candidate_prior_artifacts "
            "WHERE artifact_id = ?",
            (artifact_id,),
        )
        return row is not None

    def _select_one(
        self,
        cursor: Any,
        sql: str,
        params: tuple[Any, ...],
    ) -> Mapping[str, Any] | None:
        self._execute(cursor, sql, params)
        row = cursor.fetchone()
        return None if row is None else self._row(cursor, row)

    def _execute(
        self,
        cursor: Any,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> None:
        cursor.execute(self._translate(sql), params)

    def _executemany(
        self,
        cursor: Any,
        sql: str,
        params: tuple[tuple[Any, ...], ...],
    ) -> None:
        cursor.executemany(self._translate(sql), params)

    def _translate(self, sql: str) -> str:
        return sql if self._placeholder == "?" else sql.replace("?", "%s")

    @staticmethod
    def _row(cursor: Any, row: Any) -> Mapping[str, Any]:
        if isinstance(row, Mapping):
            return row
        return {
            description[0]: value for description, value in zip(cursor.description, row)
        }

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()


def _artifact_row(
    artifact: CandidatePriorArtifact,
    run_identity: str,
) -> dict[str, Any]:
    manifest = artifact.manifest
    run = manifest.run
    return {
        "artifact_id": artifact.artifact_id,
        "run_identity_digest": run_identity,
        "artifact_digest": artifact.artifact_digest,
        "schema_version": CANDIDATE_PRIOR_ARTIFACT_SCHEMA_VERSION,
        "target_session": run.target_session.isoformat(),
        "as_of_session": run.as_of_session.isoformat(),
        "generated_at": run.generated_at.isoformat(),
        "factor_prior_id": run.factor_prior.artifact_id,
        "factor_prior_digest": run.factor_prior.digest,
        "price_prior_id": run.price_momentum_prior.artifact_id,
        "price_prior_digest": run.price_momentum_prior.digest,
        "universe_id": run.universe.artifact_id,
        "universe_digest": run.universe.digest,
        "calendar_id": run.calendar.artifact_id,
        "calendar_digest": run.calendar.digest,
        "hypothesis_definitions_json": canonical_json(
            json.loads(artifact.artifact_json)["manifest"]["run"][
                "hypothesis_definitions"
            ]
        ),
        "research_status": manifest.research_status.value,
        "strategy_ready": int(manifest.strategy_ready),
        "production_ready": int(manifest.production_ready),
        "live_admission_ready": int(manifest.live_admission_ready),
        "execution_allowed": int(manifest.execution_allowed),
        "issue_codes_json": canonical_json(list(manifest.issue_codes)),
        "entry_count": manifest.entry_count,
        "projected_candidate_count": manifest.projected_candidate_count,
        "entries_digest": manifest.entries_digest,
        "artifact_json": artifact.artifact_json,
    }


def _entry_row(
    artifact_id: str,
    ordinal: int,
    entry: CandidatePriorEntry,
) -> dict[str, Any]:
    payload = entry.payload
    return {
        "artifact_id": artifact_id,
        "entry_ordinal": ordinal,
        "market": payload.market.value,
        "symbol": payload.symbol,
        "candidate_rank": payload.candidate_rank,
        "price_rank": payload.price_rank,
        "cohorts_json": canonical_json([item.value for item in payload.cohorts]),
        "matched_hypotheses_json": canonical_json(
            [item.value for item in payload.matched_hypotheses]
        ),
        "selection_reason_codes_json": canonical_json(
            list(payload.selection_reason_codes)
        ),
        "foreign_5d_value": _decimal_text(payload.foreign_5d_value),
        "foreign_5d_percentile": _decimal_text(payload.foreign_5d_percentile),
        "trust_5d_value": _decimal_text(payload.trust_5d_value),
        "trust_5d_percentile": _decimal_text(payload.trust_5d_percentile),
        "entry_digest": entry.entry_digest,
        "entry_json": serialize_candidate_prior_entry_payload(payload),
    }


def _decimal_text(value: Any) -> str | None:
    return None if value is None else format(value, "f")


def _require_row_parity(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    columns: tuple[str, ...],
    label: str,
) -> None:
    differences = [
        column for column in columns if actual.get(column) != expected.get(column)
    ]
    if differences:
        raise CandidatePriorPersistenceError(
            PERSISTED_ARTIFACT_MISMATCH,
            f"{label} differs in: {', '.join(differences)}",
        )
