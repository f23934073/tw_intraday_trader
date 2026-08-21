from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from institutional_data.serialization import canonical_json
from institutional_prior.migrations import apply_migrations, migration_files
from institutional_prior.postgres_repository import PostgresCandidatePriorRepository
from institutional_prior.repository import (
    NON_DETERMINISTIC_REPLAY,
    PERSISTED_ARTIFACT_MISMATCH,
    CandidatePriorPersistenceError,
)
from institutional_prior.serialization import (
    FORBIDDEN_CANDIDATE_PRIOR_FIELDS,
    CandidatePriorSerializationError,
    build_candidate_prior_artifact,
    candidate_prior_run_identity_sha256,
    deserialize_candidate_prior_artifact,
)
from institutional_prior.sqlite_repository import SQLiteCandidatePriorRepository
from tests.test_institutional_candidate_prior import _build

_DELETE = object()


def test_candidate_prior_v0_round_trips_canonically() -> None:
    artifact = _build()

    assert (
        deserialize_candidate_prior_artifact(
            artifact.artifact_json,
            expected_digest=artifact.artifact_digest,
        )
        == artifact
    )

    with pytest.raises(CandidatePriorSerializationError, match="canonical"):
        deserialize_candidate_prior_artifact(f"{artifact.artifact_json}\n")


@pytest.mark.parametrize("field_name", sorted(FORBIDDEN_CANDIDATE_PRIOR_FIELDS))
def test_candidate_prior_v0_rejects_every_performance_field(
    field_name: str,
) -> None:
    payload = json.loads(_build().artifact_json)
    payload["manifest"][field_name] = "forbidden"

    with pytest.raises(CandidatePriorSerializationError, match="forbidden"):
        deserialize_candidate_prior_artifact(canonical_json(payload))


def test_candidate_prior_v0_rejects_invalid_json_shape_and_digest() -> None:
    artifact = _build()

    with pytest.raises(CandidatePriorSerializationError, match="valid JSON"):
        deserialize_candidate_prior_artifact("{")
    with pytest.raises(CandidatePriorSerializationError, match="must be an object"):
        deserialize_candidate_prior_artifact("[]")
    with pytest.raises(CandidatePriorSerializationError, match="digest"):
        deserialize_candidate_prior_artifact(
            artifact.artifact_json,
            expected_digest="0" * 64,
        )


@pytest.mark.parametrize(
    ("path", "value", "match"),
    (
        (("schema_version",), "unknown", "schema_version"),
        (("entries",), {}, "entries must be a list"),
        (("manifest", "entries_digest"), _DELETE, "missing fields"),
        (("manifest", "unknown"), True, "unexpected fields"),
        (("manifest", "research_status"), "VALIDATED", "artifact manifest"),
        (("manifest", "strategy_ready"), "false", "must be a boolean"),
        (
            ("manifest", "run", "hypothesis_definitions"),
            {},
            "hypothesis_definitions must be a list",
        ),
        (("manifest", "run", "factor_prior", "digest"), None, "digest"),
        (("manifest", "run", "target_session"), "not-a-date", "ISO-8601"),
        (("manifest", "run", "generated_at"), "not-a-time", "ISO-8601"),
        (("manifest", "run", "generated_at"), "2026-08-20T07:00:00", "timezone"),
        (("entries", 0, "cohorts"), {}, "cohorts must be a list"),
        (
            ("entries", 0, "matched_hypotheses"),
            {},
            "matched_hypotheses must be a list",
        ),
        (("entries", 0, "symbol"), 2330, "must be a string"),
        (("entries", 0, "candidate_rank"), True, "must be an integer"),
        (("entries", 0, "foreign_5d_value"), 1, "must be a string"),
        (("entries", 0, "foreign_5d_value"), "NaN", "must be finite"),
        (
            ("entries", 0, "selection_reason_codes"),
            "MATCHED",
            "must be a list",
        ),
        (("entries", 0, "entry_digest"), "0", "Candidate Prior entry"),
    ),
)
def test_candidate_prior_v0_rejects_schema_and_type_drift(
    path: tuple[str | int, ...],
    value: object,
    match: str,
) -> None:
    payload = json.loads(_build().artifact_json)
    target = payload
    for component in path[:-1]:
        target = target[component]
    key = path[-1]
    if value is _DELETE:
        del target[key]
    else:
        target[key] = value

    with pytest.raises(CandidatePriorSerializationError, match=match):
        deserialize_candidate_prior_artifact(canonical_json(payload))


def test_candidate_prior_explicit_status_fields_fail_closed() -> None:
    artifact = _build()
    payload = json.loads(artifact.artifact_json)
    payload["manifest"]["execution_allowed"] = True

    with pytest.raises(CandidatePriorSerializationError, match="execution-ready"):
        deserialize_candidate_prior_artifact(canonical_json(payload))


def test_run_identity_excludes_non_causal_generation_timestamp() -> None:
    run = _build().manifest.run
    retried = replace(run, generated_at=run.generated_at + timedelta(minutes=5))

    assert candidate_prior_run_identity_sha256(retried) == (
        candidate_prior_run_identity_sha256(run)
    )


def test_migration_is_forward_only_and_idempotent(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "migration.sqlite3")
    try:
        assert tuple(path.name for path in migration_files()) == (
            "001_candidate_prior.sql",
        )
        assert apply_migrations(connection, placeholder="?") == (
            "001_candidate_prior.sql",
        )
        assert apply_migrations(connection, placeholder="?") == ()
        versions = connection.execute(
            "SELECT version FROM institutional_prior_schema_migrations"
        ).fetchall()
        assert versions == [("001_candidate_prior.sql",)]
    finally:
        connection.close()


def test_sqlite_save_replay_reopen_and_row_parity(tmp_path: Path) -> None:
    path = tmp_path / "candidate_prior.sqlite3"
    artifact = _build()
    repository = SQLiteCandidatePriorRepository(path)
    try:
        assert repository.get("missing") is None
        assert repository.save(artifact)
        assert not repository.save(artifact)
        assert repository.get(artifact.artifact_id) == artifact
    finally:
        repository.close()

    connection = sqlite3.connect(path)
    try:
        header = connection.execute(
            """
            SELECT run_identity_digest, artifact_digest, research_status,
                   strategy_ready, production_ready, live_admission_ready,
                   execution_allowed, entry_count, projected_candidate_count,
                   artifact_json
            FROM institutional_candidate_prior_artifacts
            """
        ).fetchone()
        assert header == (
            candidate_prior_run_identity_sha256(artifact.manifest.run),
            artifact.artifact_digest,
            "EXPLORATORY",
            0,
            0,
            0,
            0,
            len(artifact.entries),
            len(artifact.projections),
            artifact.artifact_json,
        )
        rows = connection.execute(
            """
            SELECT entry_ordinal, symbol, candidate_rank, entry_digest
            FROM institutional_candidate_prior_entries
            ORDER BY entry_ordinal
            """
        ).fetchall()
        assert rows == [
            (
                ordinal,
                entry.payload.symbol,
                entry.payload.candidate_rank,
                entry.entry_digest,
            )
            for ordinal, entry in enumerate(artifact.entries)
        ]
    finally:
        connection.close()

    reopened = SQLiteCandidatePriorRepository(path)
    try:
        assert reopened.get(artifact.artifact_id) == artifact
    finally:
        reopened.close()


def test_same_run_identity_with_different_bytes_fails_closed(tmp_path: Path) -> None:
    artifact = _build()
    divergent = build_candidate_prior_artifact(
        manifest=replace(
            artifact.manifest,
            issue_codes=(*artifact.manifest.issue_codes, "DIVERGENT_REPLAY"),
        ),
        entries=artifact.entries,
    )
    assert divergent.artifact_digest != artifact.artifact_digest
    assert candidate_prior_run_identity_sha256(divergent.manifest.run) == (
        candidate_prior_run_identity_sha256(artifact.manifest.run)
    )

    repository = SQLiteCandidatePriorRepository(tmp_path / "conflict.sqlite3")
    try:
        assert repository.save(artifact)
        with pytest.raises(CandidatePriorPersistenceError) as captured:
            repository.save(divergent)
        assert captured.value.code == NON_DETERMINISTIC_REPLAY
        assert repository.get(artifact.artifact_id) == artifact
        assert repository.get(divergent.artifact_id) is None
    finally:
        repository.close()


def test_entry_publish_failure_rolls_back_artifact_header(tmp_path: Path) -> None:
    path = tmp_path / "rollback.sqlite3"
    repository = SQLiteCandidatePriorRepository(path)
    setup = sqlite3.connect(path)
    try:
        setup.execute(
            """
            CREATE TRIGGER reject_candidate_entry
            BEFORE INSERT ON institutional_candidate_prior_entries
            BEGIN
                SELECT RAISE(ABORT, 'forced entry failure');
            END
            """
        )
        setup.commit()
    finally:
        setup.close()

    try:
        with pytest.raises(sqlite3.IntegrityError, match="forced entry failure"):
            repository.save(_build())
    finally:
        repository.close()

    inspection = sqlite3.connect(path)
    try:
        count = inspection.execute(
            "SELECT COUNT(*) FROM institutional_candidate_prior_artifacts"
        ).fetchone()[0]
        assert count == 0
    finally:
        inspection.close()


def test_persisted_row_tampering_is_never_repaired_or_returned(tmp_path: Path) -> None:
    path = tmp_path / "tampered.sqlite3"
    artifact = _build()
    repository = SQLiteCandidatePriorRepository(path)
    try:
        repository.save(artifact)
    finally:
        repository.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            UPDATE institutional_candidate_prior_entries
            SET selection_reason_codes_json = '[]'
            WHERE artifact_id = ? AND entry_ordinal = 0
            """,
            (artifact.artifact_id,),
        )
        connection.commit()
    finally:
        connection.close()

    reopened = SQLiteCandidatePriorRepository(path)
    try:
        with pytest.raises(CandidatePriorPersistenceError) as captured:
            reopened.get(artifact.artifact_id)
        assert captured.value.code == PERSISTED_ARTIFACT_MISMATCH
    finally:
        reopened.close()


def test_postgres_contract_when_disposable_database_is_configured() -> None:
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    sql = pytest.importorskip("psycopg.sql")
    schema = f"test_institutional_prior_{uuid4().hex}"
    artifact = _build()

    connection = psycopg.connect(dsn)
    schema_created = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
        connection.commit()
        schema_created = True
        repository = PostgresCandidatePriorRepository(connection)
        assert repository.save(artifact)
        assert not repository.save(artifact)
        assert repository.get(artifact.artifact_id) == artifact
        repository.close()
    finally:
        if not connection.closed:
            connection.close()
        if schema_created:
            cleanup = psycopg.connect(dsn)
            try:
                with cleanup.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(schema)
                        )
                    )
                cleanup.commit()
            finally:
                cleanup.close()
