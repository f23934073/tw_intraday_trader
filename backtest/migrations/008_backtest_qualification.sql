CREATE TABLE IF NOT EXISTS backtest.backtest_qualifications (
    qualification_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    request_json JSONB NOT NULL,
    baseline_run_id TEXT NOT NULL REFERENCES backtest.backtest_runs(run_id),
    challenger_run_id TEXT NOT NULL REFERENCES backtest.backtest_runs(run_id),
    protocol_digest TEXT NOT NULL,
    protocol_json JSONB NOT NULL,
    evidence_digest TEXT NOT NULL,
    evidence_json JSONB NOT NULL,
    verdict TEXT NOT NULL CHECK (
        verdict IN ('ELIGIBLE_FOR_PROMOTION_REVIEW', 'INSUFFICIENT_EVIDENCE')
    ),
    actor_id TEXT NOT NULL CHECK (btrim(actor_id) <> ''),
    change_note TEXT NOT NULL CHECK (btrim(change_note) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (baseline_run_id <> challenger_run_id)
);

CREATE INDEX IF NOT EXISTS backtest_qualifications_created_index
    ON backtest.backtest_qualifications (created_at DESC);

CREATE INDEX IF NOT EXISTS backtest_qualifications_runs_index
    ON backtest.backtest_qualifications (baseline_run_id, challenger_run_id);

CREATE INDEX IF NOT EXISTS backtest_qualifications_family_index
    ON backtest.backtest_qualifications (
        (request_json->'protocol'->'multiple_testing'->>'family_id'),
        created_at DESC
    );
