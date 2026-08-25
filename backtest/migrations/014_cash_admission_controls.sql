CREATE TABLE backtest.backtest_cash_admission_control_heads (
    baseline_run_id TEXT NOT NULL
        REFERENCES backtest.backtest_runs(run_id),
    contract_version TEXT NOT NULL,
    current_revision BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (baseline_run_id, contract_version),
    CONSTRAINT backtest_cash_control_head_revision_positive
        CHECK (current_revision >= 1),
    CONSTRAINT backtest_cash_control_head_status
        CHECK (status IN ('SEALED', 'RUN_CREATED', 'ACCEPTED', 'INVALID'))
);

CREATE TABLE backtest.backtest_cash_admission_control_registrations (
    baseline_run_id TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    revision BIGINT NOT NULL,
    control_run_id TEXT NOT NULL UNIQUE
        REFERENCES backtest.backtest_runs(run_id),
    preflight_digest TEXT NOT NULL,
    preflight_json JSONB NOT NULL,
    sizing_digest TEXT NOT NULL,
    sizing_json JSONB NOT NULL,
    research_control_snapshot_digest TEXT NOT NULL,
    research_control_snapshot_json JSONB NOT NULL,
    status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    postflight_digest TEXT NULL,
    postflight_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (baseline_run_id, contract_version, revision),
    FOREIGN KEY (baseline_run_id, contract_version)
        REFERENCES backtest.backtest_cash_admission_control_heads(
            baseline_run_id, contract_version
        ),
    CONSTRAINT backtest_cash_control_registration_revision_positive
        CHECK (revision >= 1),
    CONSTRAINT backtest_cash_control_registration_preflight_sha256
        CHECK (preflight_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_cash_control_registration_sizing_sha256
        CHECK (sizing_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_cash_control_registration_snapshot_sha256
        CHECK (research_control_snapshot_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_cash_control_registration_postflight_sha256
        CHECK (postflight_digest IS NULL OR postflight_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_cash_control_registration_status
        CHECK (status IN ('RUN_CREATED', 'ACCEPTED', 'INVALID')),
    CONSTRAINT backtest_cash_control_registration_actor_nonempty
        CHECK (btrim(actor_id) <> ''),
    CONSTRAINT backtest_cash_control_registration_note_nonempty
        CHECK (btrim(change_note) <> ''),
    CONSTRAINT backtest_cash_control_registration_postflight_pair
        CHECK ((postflight_digest IS NULL) = (postflight_json IS NULL))
);

CREATE TABLE backtest.backtest_cash_admission_control_operations (
    baseline_run_id TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    request_json JSONB NOT NULL,
    result_digest TEXT NOT NULL,
    result_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (baseline_run_id, contract_version, idempotency_key),
    FOREIGN KEY (baseline_run_id, contract_version)
        REFERENCES backtest.backtest_cash_admission_control_heads(
            baseline_run_id, contract_version
        ),
    CONSTRAINT backtest_cash_control_operation_key_nonempty
        CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT backtest_cash_control_operation_request_sha256
        CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT backtest_cash_control_operation_result_sha256
        CHECK (result_digest ~ '^[0-9a-f]{64}$')
);

CREATE INDEX backtest_cash_control_registration_status_index
    ON backtest.backtest_cash_admission_control_registrations (status, updated_at DESC);

CREATE INDEX backtest_cash_control_operation_created_index
    ON backtest.backtest_cash_admission_control_operations (created_at DESC);
