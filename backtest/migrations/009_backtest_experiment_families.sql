CREATE TABLE IF NOT EXISTS backtest.backtest_experiment_families (
    family_id TEXT PRIMARY KEY,
    baseline_run_id TEXT NOT NULL UNIQUE
        REFERENCES backtest.backtest_runs(run_id),
    contract_version TEXT NOT NULL
        CHECK (contract_version = 'backtest-experiment-family-v1'),
    planned_attempts INTEGER NOT NULL
        CHECK (planned_attempts = 20),
    alpha NUMERIC NOT NULL
        CHECK (alpha = 0.05),
    adjustment_method TEXT NOT NULL
        CHECK (adjustment_method = 'BONFERRONI'),
    policy_json JSONB NOT NULL,
    policy_digest TEXT NOT NULL,
    comparability_digest TEXT NOT NULL,
    definition_digest TEXT NOT NULL,
    head_sequence INTEGER NOT NULL DEFAULT 0
        CHECK (head_sequence BETWEEN 0 AND 20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest.backtest_experiment_attempts (
    family_id TEXT NOT NULL
        REFERENCES backtest.backtest_experiment_families(family_id),
    attempt_sequence INTEGER NOT NULL CHECK (attempt_sequence > 0),
    run_id TEXT NOT NULL UNIQUE REFERENCES backtest.backtest_runs(run_id),
    hypothesis_id TEXT NULL,
    qualification_id TEXT NULL UNIQUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    qualified_at TIMESTAMPTZ NULL,
    PRIMARY KEY (family_id, attempt_sequence),
    UNIQUE (family_id, run_id)
);

ALTER TABLE backtest.backtest_qualifications
    ADD COLUMN IF NOT EXISTS family_id TEXT NULL
        REFERENCES backtest.backtest_experiment_families(family_id),
    ADD COLUMN IF NOT EXISTS attempt_number INTEGER NULL,
    ADD COLUMN IF NOT EXISTS family_head_sequence INTEGER NULL,
    ADD COLUMN IF NOT EXISTS family_snapshot_digest TEXT NULL;

ALTER TABLE backtest.backtest_qualifications
    DROP CONSTRAINT IF EXISTS backtest_qualifications_family_v2_check,
    ADD CONSTRAINT backtest_qualifications_family_v2_check CHECK (
        protocol_json->>'contract_version' <> 'backtest-qualification-protocol-v2'
        OR (
            family_id IS NOT NULL
            AND attempt_number IS NOT NULL
            AND family_head_sequence IS NOT NULL
            AND family_snapshot_digest IS NOT NULL
        )
    );

ALTER TABLE backtest.backtest_experiment_attempts
    DROP CONSTRAINT IF EXISTS backtest_experiment_attempts_qualification_fk,
    ADD CONSTRAINT backtest_experiment_attempts_qualification_fk
        FOREIGN KEY (qualification_id)
        REFERENCES backtest.backtest_qualifications(qualification_id);

CREATE INDEX IF NOT EXISTS backtest_experiment_families_created_index
    ON backtest.backtest_experiment_families (created_at DESC);

CREATE INDEX IF NOT EXISTS backtest_experiment_attempts_family_index
    ON backtest.backtest_experiment_attempts (family_id, attempt_sequence);

CREATE INDEX IF NOT EXISTS backtest_qualifications_family_sequence_index
    ON backtest.backtest_qualifications (family_id, attempt_number);
