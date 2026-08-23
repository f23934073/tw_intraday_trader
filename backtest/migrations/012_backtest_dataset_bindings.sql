CREATE TABLE IF NOT EXISTS backtest.backtest_dataset_bindings (
    binding_name TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL
        REFERENCES backtest.backtest_datasets(dataset_id),
    dataset_digest TEXT NOT NULL,
    plan_identity_digest TEXT NOT NULL,
    revision BIGINT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT backtest_dataset_bindings_name_nonempty
        CHECK (btrim(binding_name) <> ''),
    CONSTRAINT backtest_dataset_bindings_dataset_digest_sha256
        CHECK (dataset_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_bindings_plan_digest_sha256
        CHECK (plan_identity_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_bindings_revision_positive
        CHECK (revision >= 1),
    CONSTRAINT backtest_dataset_bindings_actor_nonempty
        CHECK (btrim(actor_id) <> ''),
    CONSTRAINT backtest_dataset_bindings_note_nonempty
        CHECK (btrim(change_note) <> '')
);

CREATE TABLE IF NOT EXISTS backtest.backtest_dataset_binding_revisions (
    binding_name TEXT NOT NULL,
    revision BIGINT NOT NULL,
    dataset_id TEXT NOT NULL
        REFERENCES backtest.backtest_datasets(dataset_id),
    dataset_digest TEXT NOT NULL,
    plan_identity_digest TEXT NOT NULL,
    previous_dataset_id TEXT NULL,
    previous_dataset_digest TEXT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (binding_name, revision),
    CONSTRAINT backtest_dataset_binding_revisions_dataset_digest_sha256
        CHECK (dataset_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_binding_revisions_plan_digest_sha256
        CHECK (plan_identity_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_binding_revisions_previous_digest_sha256
        CHECK (
            previous_dataset_digest IS NULL
            OR previous_dataset_digest ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT backtest_dataset_binding_revisions_revision_positive
        CHECK (revision >= 1),
    CONSTRAINT backtest_dataset_binding_revisions_actor_nonempty
        CHECK (btrim(actor_id) <> ''),
    CONSTRAINT backtest_dataset_binding_revisions_note_nonempty
        CHECK (btrim(change_note) <> ''),
    CONSTRAINT backtest_dataset_binding_revisions_key_nonempty
        CHECK (btrim(idempotency_key) <> '')
);

CREATE TABLE IF NOT EXISTS backtest.backtest_dataset_binding_operations (
    binding_name TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    expected_revision BIGINT NOT NULL,
    target_dataset_id TEXT NOT NULL,
    target_dataset_digest TEXT NOT NULL,
    target_plan_identity_digest TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    result_kind TEXT NOT NULL,
    result_revision BIGINT NOT NULL,
    result_json JSONB NOT NULL,
    result_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (binding_name, idempotency_key),
    CONSTRAINT backtest_dataset_binding_operations_request_digest_sha256
        CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_binding_operations_expected_revision_nonnegative
        CHECK (expected_revision >= 0),
    CONSTRAINT backtest_dataset_binding_operations_target_digest_sha256
        CHECK (target_dataset_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_binding_operations_plan_digest_sha256
        CHECK (target_plan_identity_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_dataset_binding_operations_actor_nonempty
        CHECK (btrim(actor_id) <> ''),
    CONSTRAINT backtest_dataset_binding_operations_note_nonempty
        CHECK (btrim(change_note) <> ''),
    CONSTRAINT backtest_dataset_binding_operations_result_kind
        CHECK (result_kind IN ('BOUND', 'NOOP_ALREADY_BOUND')),
    CONSTRAINT backtest_dataset_binding_operations_result_revision_positive
        CHECK (result_revision >= 1),
    CONSTRAINT backtest_dataset_binding_operations_result_digest_sha256
        CHECK (result_digest ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS backtest_dataset_bindings_dataset_index
    ON backtest.backtest_dataset_bindings (dataset_id, dataset_digest);

CREATE INDEX IF NOT EXISTS backtest_dataset_binding_revisions_dataset_index
    ON backtest.backtest_dataset_binding_revisions (dataset_id, dataset_digest);

CREATE INDEX IF NOT EXISTS backtest_dataset_binding_operations_actor_index
    ON backtest.backtest_dataset_binding_operations (actor_id, created_at DESC);
