CREATE OR REPLACE FUNCTION backtest.atomic_entry_benchmark_diagnostic_codes_valid(
    value JSONB
) RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    item JSONB;
    code TEXT;
    seen TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF jsonb_typeof(value) <> 'array' THEN
        RETURN FALSE;
    END IF;
    FOR item IN SELECT jsonb_array_elements(value)
    LOOP
        IF jsonb_typeof(item) <> 'string' THEN
            RETURN FALSE;
        END IF;
        code := item #>> '{}';
        IF code NOT IN (
            'DATASET_IDENTITY_VERIFIED', 'VERSION_IDENTITY_VERIFIED',
            'FEATURE_IDENTITY_VERIFIED', 'CANONICAL_BYTES_VERIFIED',
            'PARITY_VERIFIED', 'COST_IDENTITY_VERIFIED',
            'SUMMARY_REBUILD_VERIFIED', 'POSTFLIGHT_VERIFIED',
            'DATASET_IDENTITY_REJECTED', 'VERSION_IDENTITY_REJECTED',
            'FEATURE_IDENTITY_REJECTED', 'CANONICAL_BYTES_REJECTED',
            'PARITY_REJECTED', 'COST_IDENTITY_REJECTED',
            'SUMMARY_REBUILD_REJECTED', 'POSTFLIGHT_REJECTED'
        ) OR code = ANY(seen) THEN
            RETURN FALSE;
        END IF;
        seen := array_append(seen, code);
    END LOOP;
    RETURN TRUE;
END;
$$;

CREATE TABLE backtest.atomic_entry_benchmark_families (
    family_id TEXT PRIMARY KEY,
    source_lineage_run_id TEXT NOT NULL REFERENCES backtest.backtest_runs(run_id),
    research_baseline_json JSONB NOT NULL,
    research_baseline_digest TEXT NOT NULL UNIQUE,
    protocol_core_json JSONB NOT NULL,
    protocol_core_digest TEXT NOT NULL,
    planned_attempts INTEGER NOT NULL,
    family_alpha NUMERIC NOT NULL,
    adjustment_method TEXT NOT NULL,
    head_sequence INTEGER NOT NULL DEFAULT 0,
    active_matrix_revision INTEGER NULL,
    release_state TEXT NOT NULL DEFAULT 'NOT_READY',
    actor_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT atomic_benchmark_family_research_sha CHECK (
        research_baseline_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_family_protocol_sha CHECK (
        protocol_core_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_family_policy CHECK (
        planned_attempts = 20
        AND family_alpha = 0.05
        AND adjustment_method = 'BONFERRONI'
    ),
    CONSTRAINT atomic_benchmark_family_head CHECK (
        head_sequence >= 0 AND head_sequence <= 7
    ),
    CONSTRAINT atomic_benchmark_family_release_state CHECK (
        release_state IN (
            'NOT_READY', 'READY_TO_RELEASE', 'MATERIALIZING', 'RELEASED',
            'BLOCKED_FINAL'
        )
    ),
    CONSTRAINT atomic_benchmark_family_actor CHECK (btrim(actor_id) <> '')
);

CREATE TABLE backtest.atomic_entry_benchmark_matrices (
    matrix_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    matrix_revision INTEGER NOT NULL,
    matrix_core_json JSONB NOT NULL,
    matrix_core_digest TEXT NOT NULL UNIQUE,
    benchmark_build_binding_json JSONB NOT NULL,
    benchmark_build_binding_digest TEXT NOT NULL,
    registration_json JSONB NOT NULL,
    registration_digest TEXT NOT NULL UNIQUE,
    registered_slots_json JSONB NOT NULL,
    status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    sealed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (family_id, matrix_revision),
    CONSTRAINT atomic_benchmark_matrix_revision CHECK (matrix_revision = 1),
    CONSTRAINT atomic_benchmark_matrix_core_sha CHECK (
        matrix_core_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_matrix_build_sha CHECK (
        benchmark_build_binding_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_matrix_registration_sha CHECK (
        registration_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_matrix_status CHECK (status = 'SEALED'),
    CONSTRAINT atomic_benchmark_matrix_audit CHECK (
        btrim(actor_id) <> '' AND btrim(change_note) <> ''
    )
);

CREATE TABLE backtest.atomic_entry_benchmark_slots (
    matrix_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_matrices(matrix_id),
    family_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    slot_sequence INTEGER NOT NULL,
    strategy_version_id TEXT NOT NULL REFERENCES backtest.strategy_versions(strategy_version_id),
    hypothesis_spec_json JSONB NOT NULL,
    hypothesis_spec_digest TEXT NOT NULL,
    version_binding_json JSONB NOT NULL,
    version_binding_digest TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL UNIQUE,
    slot_binding_json JSONB NOT NULL,
    slot_digest TEXT NOT NULL UNIQUE,
    PRIMARY KEY (matrix_id, slot_sequence),
    UNIQUE (family_id, slot_sequence),
    CONSTRAINT atomic_benchmark_slot_sequence CHECK (
        slot_sequence >= 1 AND slot_sequence <= 7
    ),
    CONSTRAINT atomic_benchmark_slot_spec_sha CHECK (
        hypothesis_spec_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_slot_version_sha CHECK (
        version_binding_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_slot_hypothesis_sha CHECK (
        hypothesis_id ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_slot_digest_sha CHECK (
        slot_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE backtest.atomic_entry_benchmark_attempts (
    attempt_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    matrix_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_matrices(matrix_id),
    attempt_sequence INTEGER NOT NULL,
    slot_sequence INTEGER NOT NULL,
    hypothesis_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_slots(hypothesis_id),
    request_json JSONB NOT NULL,
    request_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_revision INTEGER NOT NULL,
    retry_generation INTEGER NOT NULL,
    progress NUMERIC(7, 6) NOT NULL DEFAULT 0,
    integrity_status TEXT NOT NULL DEFAULT 'PENDING',
    integrity_diagnostic_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    preflight_id TEXT NULL,
    replay_id TEXT NULL UNIQUE,
    result_projection_digest TEXT NULL,
    postflight_digest TEXT NULL,
    failure_code TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    terminal_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (family_id, attempt_sequence),
    UNIQUE (family_id, slot_sequence),
    CONSTRAINT atomic_benchmark_attempt_sequence CHECK (
        attempt_sequence = slot_sequence AND slot_sequence >= 1 AND slot_sequence <= 7
    ),
    CONSTRAINT atomic_benchmark_attempt_request_sha CHECK (
        request_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_attempt_revision CHECK (attempt_revision >= 1),
    CONSTRAINT atomic_benchmark_attempt_generation CHECK (
        retry_generation >= 1 AND retry_generation <= 4
    ),
    CONSTRAINT atomic_benchmark_attempt_progress CHECK (
        progress >= 0 AND progress <= 1
    ),
    CONSTRAINT atomic_benchmark_attempt_status CHECK (
        status IN (
            'RUNNING', 'CANCELLING', 'CANCELLED_RETRYABLE', 'CANCELLED_FINAL',
            'FAILED_RETRYABLE', 'FAILED_FINAL', 'REJECTED_FINAL', 'ACCEPTED'
        )
    ),
    CONSTRAINT atomic_benchmark_attempt_integrity CHECK (
        integrity_status IN ('PENDING', 'VERIFIED', 'REJECTED')
    ),
    CONSTRAINT atomic_benchmark_attempt_diagnostic_codes CHECK (
        backtest.atomic_entry_benchmark_diagnostic_codes_valid(
            integrity_diagnostic_codes_json
        )
    ),
    CONSTRAINT atomic_benchmark_attempt_result_sha CHECK (
        result_projection_digest IS NULL
        OR result_projection_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_attempt_postflight_sha CHECK (
        postflight_digest IS NULL OR postflight_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE backtest.atomic_entry_benchmark_operations (
    operation_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    matrix_id TEXT NULL REFERENCES backtest.atomic_entry_benchmark_matrices(matrix_id),
    attempt_id TEXT NULL REFERENCES backtest.atomic_entry_benchmark_attempts(attempt_id),
    operation_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_json JSONB NOT NULL,
    request_digest TEXT NOT NULL,
    result_json JSONB NOT NULL,
    result_digest TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (family_id, operation_type, idempotency_key),
    CONSTRAINT atomic_benchmark_operation_key CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT atomic_benchmark_operation_request_sha CHECK (
        request_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_operation_result_sha CHECK (
        result_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_operation_actor CHECK (btrim(actor_id) <> '')
);

CREATE TABLE backtest.atomic_entry_benchmark_transition_evidence (
    operation_id TEXT PRIMARY KEY
        REFERENCES backtest.atomic_entry_benchmark_operations(operation_id),
    family_id TEXT NOT NULL
        REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    matrix_id TEXT NOT NULL
        REFERENCES backtest.atomic_entry_benchmark_matrices(matrix_id),
    attempt_id TEXT NOT NULL
        REFERENCES backtest.atomic_entry_benchmark_attempts(attempt_id),
    from_revision INTEGER NOT NULL,
    to_revision INTEGER NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    retry_generation INTEGER NOT NULL,
    next_retry_generation INTEGER NOT NULL,
    from_progress NUMERIC(7, 6) NOT NULL,
    requested_progress NUMERIC(7, 6) NULL,
    result_progress NUMERIC(7, 6) NOT NULL,
    outcome_code TEXT NOT NULL,
    evidence_json JSONB NOT NULL,
    evidence_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (attempt_id, to_revision),
    CONSTRAINT atomic_benchmark_transition_revision CHECK (
        from_revision >= 1 AND to_revision = from_revision + 1
    ),
    CONSTRAINT atomic_benchmark_transition_generation CHECK (
        retry_generation >= 1 AND retry_generation <= 4
        AND next_retry_generation >= 1 AND next_retry_generation <= 4
    ),
    CONSTRAINT atomic_benchmark_transition_status CHECK (
        from_status IN (
            'RUNNING', 'CANCELLING', 'CANCELLED_RETRYABLE',
            'FAILED_RETRYABLE'
        )
        AND to_status IN (
            'RUNNING', 'CANCELLING', 'CANCELLED_RETRYABLE',
            'CANCELLED_FINAL', 'FAILED_RETRYABLE', 'FAILED_FINAL',
            'REJECTED_FINAL'
        )
    ),
    CONSTRAINT atomic_benchmark_transition_progress CHECK (
        from_progress >= 0 AND from_progress <= 1
        AND (requested_progress IS NULL OR (
            requested_progress >= 0 AND requested_progress <= 1
        ))
        AND result_progress = CASE
            WHEN requested_progress IS NULL THEN from_progress
            ELSE GREATEST(from_progress, requested_progress)
        END
    ),
    CONSTRAINT atomic_benchmark_transition_outcome CHECK (
        btrim(outcome_code) <> ''
    ),
    CONSTRAINT atomic_benchmark_transition_evidence_sha CHECK (
        evidence_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE backtest.atomic_entry_benchmark_outbox (
    outbox_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    matrix_id TEXT NULL REFERENCES backtest.atomic_entry_benchmark_matrices(matrix_id),
    attempt_id TEXT NULL REFERENCES backtest.atomic_entry_benchmark_attempts(attempt_id),
    operation_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_operations(operation_id),
    topic TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    payload_digest TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'PENDING',
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ NULL,
    UNIQUE (operation_id, topic),
    CONSTRAINT atomic_benchmark_outbox_payload_sha CHECK (
        payload_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_outbox_status CHECK (
        delivery_status IN ('PENDING', 'DELIVERED', 'DEAD_LETTER')
    ),
    CONSTRAINT atomic_benchmark_outbox_attempts CHECK (delivery_attempts >= 0)
);

CREATE TABLE backtest.atomic_entry_benchmark_result_chunks (
    attempt_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_attempts(attempt_id),
    retry_generation INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    chunk_sequence INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    payload_bytes BYTEA NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (attempt_id, retry_generation, field_name, chunk_sequence),
    CONSTRAINT atomic_benchmark_result_generation CHECK (
        retry_generation >= 1 AND retry_generation <= 4
    ),
    CONSTRAINT atomic_benchmark_result_field CHECK (
        field_name IN ('episodes', 'result_manifest', 'summary', 'postflight')
    ),
    CONSTRAINT atomic_benchmark_result_chunk CHECK (
        chunk_sequence >= 0 AND row_count >= 0 AND row_count <= 10000
    ),
    CONSTRAINT atomic_benchmark_result_payload_sha CHECK (
        payload_sha256 ~ '^[0-9a-f]{64}$'
    )
);

CREATE TABLE backtest.atomic_entry_benchmark_releases (
    family_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_families(family_id),
    matrix_id TEXT NOT NULL REFERENCES backtest.atomic_entry_benchmark_matrices(matrix_id),
    matrix_revision INTEGER NOT NULL,
    release_state TEXT NOT NULL,
    release_json JSONB NULL,
    release_digest TEXT NULL,
    public_bundle_digest TEXT NULL,
    public_bundle_locator TEXT NULL,
    actor_id TEXT NULL,
    change_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMPTZ NULL,
    PRIMARY KEY (family_id, matrix_revision),
    UNIQUE (matrix_id),
    CONSTRAINT atomic_benchmark_release_revision CHECK (matrix_revision = 1),
    CONSTRAINT atomic_benchmark_release_state CHECK (
        release_state IN (
            'NOT_READY', 'READY_TO_RELEASE', 'MATERIALIZING', 'RELEASED',
            'BLOCKED_FINAL'
        )
    ),
    CONSTRAINT atomic_benchmark_release_digest CHECK (
        release_digest IS NULL OR release_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_bundle_digest CHECK (
        public_bundle_digest IS NULL OR public_bundle_digest ~ '^[0-9a-f]{64}$'
    )
);

CREATE INDEX atomic_benchmark_attempt_status_index
    ON backtest.atomic_entry_benchmark_attempts (family_id, status, slot_sequence);
CREATE INDEX atomic_benchmark_outbox_pending_index
    ON backtest.atomic_entry_benchmark_outbox (delivery_status, created_at)
    WHERE delivery_status = 'PENDING';
CREATE INDEX atomic_benchmark_operation_created_index
    ON backtest.atomic_entry_benchmark_operations (family_id, created_at DESC);
