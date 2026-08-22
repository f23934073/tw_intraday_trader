CREATE TABLE IF NOT EXISTS backtest.strategy_mutation_operations (
    operation_scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    result_json JSONB NOT NULL,
    result_digest TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (operation_scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS backtest.strategy_audit_events (
    audit_event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    before_digest TEXT NULL,
    after_digest TEXT NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    operation_scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (operation_scope, idempotency_key)
);

CREATE INDEX IF NOT EXISTS strategy_mutation_operations_actor_index
    ON backtest.strategy_mutation_operations (actor_id, committed_at DESC);
CREATE INDEX IF NOT EXISTS strategy_audit_resource_index
    ON backtest.strategy_audit_events (resource_type, resource_id, occurred_at DESC);
