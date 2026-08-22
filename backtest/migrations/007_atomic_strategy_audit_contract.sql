ALTER TABLE backtest.strategy_audit_events
    DROP CONSTRAINT IF EXISTS strategy_audit_events_operation_scope_idempotency_key_key;

ALTER TABLE backtest.strategy_audit_events
    ALTER COLUMN after_digest DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS outcome TEXT NOT NULL DEFAULT 'SUCCESS',
    ADD COLUMN IF NOT EXISTS request_digest TEXT NULL,
    ADD COLUMN IF NOT EXISTS details_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS strategy_audit_operation_index
    ON backtest.strategy_audit_events (operation_scope, idempotency_key, occurred_at DESC);
CREATE INDEX IF NOT EXISTS strategy_audit_outcome_index
    ON backtest.strategy_audit_events (outcome, occurred_at DESC);
