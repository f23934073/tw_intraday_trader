CREATE TABLE IF NOT EXISTS journal_sessions (
    session_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    mode TEXT NOT NULL,
    metadata_json JSONB NOT NULL,
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_records (
    journal_sequence BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES journal_sessions(session_id),
    record_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL,
    idempotency_scope TEXT NULL,
    idempotency_key TEXT NULL,
    schema_version TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    CONSTRAINT journal_records_idempotency_pair
        CHECK (
            (idempotency_scope IS NULL AND idempotency_key IS NULL)
            OR (idempotency_scope IS NOT NULL AND idempotency_key IS NOT NULL)
        ),
    CONSTRAINT journal_records_session_record_unique UNIQUE (session_id, record_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS journal_records_idempotency_unique
    ON journal_records (idempotency_scope, idempotency_key)
    WHERE idempotency_scope IS NOT NULL;

CREATE INDEX IF NOT EXISTS journal_records_session_sequence_index
    ON journal_records (session_id, journal_sequence);

CREATE TABLE IF NOT EXISTS projection_checkpoints (
    session_id TEXT NOT NULL REFERENCES journal_sessions(session_id),
    projection_name TEXT NOT NULL,
    journal_sequence BIGINT NOT NULL CHECK (journal_sequence >= 0),
    digest TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, projection_name)
);
