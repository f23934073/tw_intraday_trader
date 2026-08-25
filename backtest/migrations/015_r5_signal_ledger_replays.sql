CREATE TABLE backtest.r5_signal_ledger_replay_heads (
    baseline_run_id TEXT NOT NULL
        REFERENCES backtest.backtest_runs(run_id),
    control_contract_version TEXT NOT NULL,
    current_revision BIGINT NOT NULL,
    replay_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (baseline_run_id, control_contract_version),
    CONSTRAINT r5_signal_replay_head_revision_positive
        CHECK (current_revision >= 1),
    CONSTRAINT r5_signal_replay_head_status
        CHECK (status IN (
            'SEALED', 'RUNNING', 'POSTFLIGHT', 'CANCELLING', 'CANCELLED',
            'FAILED', 'ACCEPTED', 'INVALID'
        ))
);

CREATE TABLE backtest.r5_signal_ledger_replay_registrations (
    baseline_run_id TEXT NOT NULL,
    control_contract_version TEXT NOT NULL,
    revision BIGINT NOT NULL,
    replay_id TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    request_json JSONB NOT NULL,
    preflight_digest TEXT NOT NULL,
    ledger_manifest_digest TEXT NOT NULL,
    ledger_manifest_json JSONB NOT NULL,
    match_plan_manifest_digest TEXT NOT NULL,
    match_plan_manifest_json JSONB NOT NULL,
    order_derivation_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    progress NUMERIC(7, 6) NOT NULL DEFAULT 0,
    progress_message TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    postflight_digest TEXT NULL,
    postflight_json JSONB NULL,
    result_manifest_digest TEXT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (baseline_run_id, control_contract_version, revision),
    FOREIGN KEY (baseline_run_id, control_contract_version)
        REFERENCES backtest.r5_signal_ledger_replay_heads(
            baseline_run_id, control_contract_version
        ),
    CONSTRAINT r5_signal_replay_registration_revision_positive
        CHECK (revision >= 1),
    CONSTRAINT r5_signal_replay_registration_request_sha256
        CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_registration_preflight_sha256
        CHECK (preflight_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_registration_ledger_sha256
        CHECK (ledger_manifest_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_registration_match_sha256
        CHECK (match_plan_manifest_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_registration_order_sha256
        CHECK (order_derivation_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_registration_postflight_sha256
        CHECK (postflight_digest IS NULL OR postflight_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_registration_result_sha256
        CHECK (
            result_manifest_digest IS NULL
            OR result_manifest_digest ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT r5_signal_replay_registration_status
        CHECK (status IN (
            'SEALED', 'RUNNING', 'POSTFLIGHT', 'CANCELLING', 'CANCELLED',
            'FAILED', 'ACCEPTED', 'INVALID'
        )),
    CONSTRAINT r5_signal_replay_registration_progress
        CHECK (progress >= 0 AND progress <= 1),
    CONSTRAINT r5_signal_replay_registration_actor_nonempty
        CHECK (btrim(actor_id) <> ''),
    CONSTRAINT r5_signal_replay_registration_note_nonempty
        CHECK (btrim(change_note) <> ''),
    CONSTRAINT r5_signal_replay_registration_postflight_pair
        CHECK ((postflight_digest IS NULL) = (postflight_json IS NULL)),
    CONSTRAINT r5_signal_replay_registration_terminal_evidence
        CHECK (
            (status = 'ACCEPTED'
             AND postflight_digest IS NOT NULL
             AND result_manifest_digest IS NOT NULL
             AND error_message IS NULL)
            OR
            (status = 'INVALID'
             AND postflight_digest IS NOT NULL
             AND result_manifest_digest IS NULL
             AND error_message IS NULL)
            OR
            (status = 'FAILED'
             AND postflight_digest IS NULL
             AND result_manifest_digest IS NULL
             AND btrim(COALESCE(error_message, '')) <> '')
            OR
            (status NOT IN ('ACCEPTED', 'INVALID', 'FAILED')
             AND postflight_digest IS NULL
             AND result_manifest_digest IS NULL
             AND error_message IS NULL)
        )
);

CREATE TABLE backtest.r5_signal_ledger_replay_operations (
    baseline_run_id TEXT NOT NULL,
    control_contract_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    request_json JSONB NOT NULL,
    result_digest TEXT NOT NULL,
    result_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        baseline_run_id, control_contract_version, idempotency_key
    ),
    FOREIGN KEY (baseline_run_id, control_contract_version)
        REFERENCES backtest.r5_signal_ledger_replay_heads(
            baseline_run_id, control_contract_version
        ),
    CONSTRAINT r5_signal_replay_operation_key_nonempty
        CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT r5_signal_replay_operation_request_sha256
        CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_operation_result_sha256
        CHECK (result_digest ~ '^[0-9a-f]{64}$')
);

CREATE TABLE backtest.r5_signal_ledger_replay_results (
    replay_id TEXT PRIMARY KEY
        REFERENCES backtest.r5_signal_ledger_replay_registrations(replay_id),
    result_manifest_digest TEXT NOT NULL,
    result_manifest_json JSONB NOT NULL,
    postflight_digest TEXT NOT NULL,
    postflight_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT r5_signal_replay_result_manifest_sha256
        CHECK (result_manifest_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT r5_signal_replay_result_postflight_sha256
        CHECK (postflight_digest ~ '^[0-9a-f]{64}$')
);

CREATE TABLE backtest.r5_signal_ledger_replay_result_chunks (
    replay_id TEXT NOT NULL
        REFERENCES backtest.r5_signal_ledger_replay_results(replay_id),
    field_name TEXT NOT NULL,
    chunk_sequence INTEGER NOT NULL,
    item_count INTEGER NOT NULL,
    payload_json JSONB NOT NULL,
    payload_digest TEXT NOT NULL,
    PRIMARY KEY (replay_id, field_name, chunk_sequence),
    CONSTRAINT r5_signal_replay_chunk_field
        CHECK (field_name IN ('episodes', 'modeled_entries', 'modeled_exits')),
    CONSTRAINT r5_signal_replay_chunk_sequence
        CHECK (chunk_sequence >= 0),
    CONSTRAINT r5_signal_replay_chunk_count
        CHECK (item_count > 0 AND item_count <= 100),
    CONSTRAINT r5_signal_replay_chunk_sha256
        CHECK (payload_digest ~ '^[0-9a-f]{64}$')
);

CREATE INDEX r5_signal_replay_registration_status_index
    ON backtest.r5_signal_ledger_replay_registrations (status, updated_at DESC);

CREATE INDEX r5_signal_replay_operation_created_index
    ON backtest.r5_signal_ledger_replay_operations (created_at DESC);

CREATE INDEX r5_signal_replay_result_chunk_index
    ON backtest.r5_signal_ledger_replay_result_chunks (
        replay_id, field_name, chunk_sequence
    );
