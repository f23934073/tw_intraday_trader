CREATE TABLE IF NOT EXISTS backtest_datasets (
    dataset_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    request_json JSONB NOT NULL,
    resource_id TEXT NULL,
    progress DOUBLE PRECISION NOT NULL,
    progress_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    config_json JSONB NOT NULL,
    config_digest TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_digest TEXT NOT NULL,
    progress DOUBLE PRECISION NOT NULL,
    progress_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT NULL,
    result_digest TEXT NULL
);

CREATE TABLE IF NOT EXISTS backtest_results (
    run_id TEXT PRIMARY KEY REFERENCES backtest_runs(run_id),
    result_json JSONB NOT NULL,
    summary_json JSONB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_decisions (
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    decision_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_at TEXT NOT NULL,
    side TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (run_id, decision_id)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    trade_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_at TEXT NOT NULL,
    exit_at TEXT NOT NULL,
    net_pnl DOUBLE PRECISION NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (run_id, trade_id)
);

CREATE TABLE IF NOT EXISTS backtest_daily_equity (
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    session_date TEXT NOT NULL,
    equity DOUBLE PRECISION NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (run_id, session_date)
);

CREATE TABLE IF NOT EXISTS backtest_comparisons (
    comparison_id TEXT PRIMARY KEY,
    baseline_run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    challenger_run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    payload_json JSONB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS backtest_runs_created_index ON backtest_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS backtest_jobs_created_index ON backtest_jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS backtest_decisions_run_event_index ON backtest_decisions (run_id, event_at);
CREATE INDEX IF NOT EXISTS backtest_trades_run_entry_index ON backtest_trades (run_id, entry_at);
