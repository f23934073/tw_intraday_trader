CREATE TABLE IF NOT EXISTS backtest.strategy_templates (
    strategy_id TEXT PRIMARY KEY,
    display_name_zh_tw TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('FILTER', 'ENTRY', 'EXIT', 'CONTEXT')),
    session_phase TEXT NOT NULL,
    implementation_version TEXT NOT NULL,
    implementation_digest TEXT NOT NULL,
    parameter_schema_version TEXT NOT NULL,
    parameter_schema_digest TEXT NOT NULL,
    parameter_schema_json JSONB NOT NULL,
    required_capabilities_json JSONB NOT NULL,
    feature_requirements_json JSONB NOT NULL,
    runtime_bindings_json JSONB NOT NULL,
    description_zh_tw TEXT NOT NULL DEFAULT '',
    template_digest TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest.strategy_version_drafts (
    draft_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES backtest.strategy_templates(strategy_id),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0),
    parameters_json JSONB NOT NULL,
    parameters_digest TEXT NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    published_strategy_version_id TEXT NULL,
    published_event_id TEXT NULL,
    published_operation_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL,
    CHECK (
        (published_at IS NULL AND published_strategy_version_id IS NULL
            AND published_event_id IS NULL AND published_operation_id IS NULL)
        OR
        (published_at IS NOT NULL AND published_strategy_version_id IS NOT NULL
            AND published_event_id IS NOT NULL AND published_operation_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS backtest.strategy_versions (
    strategy_version_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES backtest.strategy_templates(strategy_id),
    source_draft_id TEXT NOT NULL UNIQUE REFERENCES backtest.strategy_version_drafts(draft_id),
    version_number BIGINT NOT NULL CHECK (version_number > 0),
    parameters_json JSONB NOT NULL,
    parameter_schema_version TEXT NOT NULL,
    parameter_schema_digest TEXT NOT NULL,
    parameters_digest TEXT NOT NULL,
    template_digest TEXT NOT NULL,
    implementation_digest TEXT NOT NULL,
    configuration_digest TEXT NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (strategy_id, version_number)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_version_events (
    event_id TEXT PRIMARY KEY,
    strategy_version_id TEXT NOT NULL REFERENCES backtest.strategy_versions(strategy_version_id),
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL CHECK (event_type IN ('PUBLISHED', 'STATUS_TRANSITION')),
    from_status TEXT NULL,
    to_status TEXT NOT NULL,
    evidence_json JSONB NOT NULL,
    evidence_digest TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL,
    actor_session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    expected_sequence BIGINT NOT NULL CHECK (expected_sequence >= 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_digest TEXT NOT NULL UNIQUE,
    UNIQUE (strategy_version_id, sequence),
    UNIQUE (strategy_version_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_version_state (
    strategy_version_id TEXT PRIMARY KEY REFERENCES backtest.strategy_versions(strategy_version_id),
    status TEXT NOT NULL,
    last_sequence BIGINT NOT NULL CHECK (last_sequence > 0),
    last_event_id TEXT NOT NULL UNIQUE REFERENCES backtest.strategy_version_events(event_id),
    projection_digest TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest.strategy_lifecycle_outbox (
    outbox_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES backtest.strategy_version_events(event_id),
    event_digest TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    payload_digest TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (delivery_status IN ('PENDING', 'DELIVERED', 'DEAD_LETTER')),
    delivery_attempts INTEGER NOT NULL DEFAULT 0 CHECK (delivery_attempts >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ NULL,
    UNIQUE (event_id, topic)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_publish_operations (
    publish_operation_id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL UNIQUE REFERENCES backtest.strategy_version_drafts(draft_id),
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    expected_draft_revision BIGINT NOT NULL CHECK (expected_draft_revision > 0),
    strategy_version_id TEXT NOT NULL UNIQUE REFERENCES backtest.strategy_versions(strategy_version_id),
    published_event_id TEXT NOT NULL UNIQUE REFERENCES backtest.strategy_version_events(event_id),
    result_digest TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (draft_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_set_versions (
    strategy_set_version_id TEXT PRIMARY KEY,
    strategy_set_id TEXT NOT NULL,
    version_number BIGINT NOT NULL CHECK (version_number > 0),
    display_name_zh_tw TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('FILTER', 'ENTRY', 'EXIT')),
    aggregation_policy TEXT NOT NULL CHECK (aggregation_policy IN ('ANY', 'ALL', 'AT_LEAST_N')),
    minimum_trigger_count INTEGER NOT NULL DEFAULT 1 CHECK (minimum_trigger_count > 0),
    snapshot_json JSONB NOT NULL,
    snapshot_digest TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (strategy_set_id, version_number)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_set_members (
    strategy_set_version_id TEXT NOT NULL REFERENCES backtest.strategy_set_versions(strategy_set_version_id),
    strategy_version_id TEXT NOT NULL REFERENCES backtest.strategy_versions(strategy_version_id),
    member_order INTEGER NOT NULL CHECK (member_order >= 0),
    attribution_priority INTEGER NOT NULL CHECK (attribution_priority >= 0),
    member_role TEXT NOT NULL CHECK (member_role IN ('FILTER', 'ENTRY', 'EXIT')),
    configuration_digest TEXT NOT NULL,
    implementation_digest TEXT NOT NULL,
    PRIMARY KEY (strategy_set_version_id, strategy_version_id),
    UNIQUE (strategy_set_version_id, member_order),
    UNIQUE (strategy_set_version_id, attribution_priority)
);

CREATE INDEX IF NOT EXISTS strategy_version_drafts_strategy_index
    ON backtest.strategy_version_drafts (strategy_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS strategy_versions_strategy_index
    ON backtest.strategy_versions (strategy_id, version_number DESC);
CREATE INDEX IF NOT EXISTS strategy_version_events_stream_index
    ON backtest.strategy_version_events (strategy_version_id, sequence);
CREATE INDEX IF NOT EXISTS strategy_lifecycle_outbox_pending_index
    ON backtest.strategy_lifecycle_outbox (delivery_status, created_at)
    WHERE delivery_status = 'PENDING';
