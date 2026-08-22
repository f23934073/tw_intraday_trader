DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM backtest.backtest_experiment_families
        WHERE contract_version = 'backtest-experiment-family-v1'
          AND head_sequence > 0
    ) THEN
        RAISE EXCEPTION
            'legacy experiment families require explicit research identity migration';
    END IF;
END
$$;

ALTER TABLE backtest.backtest_experiment_families
    DROP CONSTRAINT IF EXISTS backtest_experiment_families_contract_version_check,
    ADD COLUMN IF NOT EXISTS research_baseline_digest TEXT NULL,
    ADD COLUMN IF NOT EXISTS research_protocol_identity_json JSONB NULL,
    ADD CONSTRAINT backtest_experiment_families_contract_version_check CHECK (
        contract_version IN (
            'backtest-experiment-family-v1',
            'backtest-experiment-family-v2'
        )
    );

ALTER TABLE backtest.backtest_experiment_families
    DROP CONSTRAINT IF EXISTS backtest_experiment_families_research_identity_key,
    ADD CONSTRAINT backtest_experiment_families_research_identity_key
        UNIQUE (research_baseline_digest),
    DROP CONSTRAINT IF EXISTS backtest_experiment_families_v2_identity_check,
    ADD CONSTRAINT backtest_experiment_families_v2_identity_check CHECK (
        contract_version <> 'backtest-experiment-family-v2'
        OR (
            research_baseline_digest IS NOT NULL
            AND research_protocol_identity_json IS NOT NULL
        )
    );

ALTER TABLE backtest.backtest_qualifications
    ADD COLUMN IF NOT EXISTS family_snapshot_json JSONB NULL;

ALTER TABLE backtest.backtest_qualifications
    DROP CONSTRAINT IF EXISTS backtest_qualifications_family_v2_check,
    ADD CONSTRAINT backtest_qualifications_family_v2_check CHECK (
        protocol_json->>'contract_version' <> 'backtest-qualification-protocol-v2'
        OR (
            family_id IS NOT NULL
            AND attempt_number IS NOT NULL
            AND family_head_sequence IS NOT NULL
            AND family_snapshot_digest IS NOT NULL
            AND family_snapshot_json IS NOT NULL
        )
    );
