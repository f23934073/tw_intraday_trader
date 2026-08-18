CREATE TABLE IF NOT EXISTS strategy_definitions (
    strategy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    role TEXT NOT NULL,
    side TEXT NULL,
    session_phase TEXT NOT NULL,
    status TEXT NOT NULL,
    display_name_zh_tw TEXT NOT NULL,
    execution_binding TEXT NOT NULL,
    source TEXT NOT NULL,
    definition_digest TEXT NOT NULL,
    definition_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (strategy_id, version)
);

CREATE INDEX IF NOT EXISTS strategy_definitions_role_phase_index
    ON strategy_definitions (role, session_phase, status);
