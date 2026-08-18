CREATE TABLE IF NOT EXISTS backtest_history_partitions (
    job_id TEXT NOT NULL REFERENCES backtest_jobs(job_id),
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    start_date TEXT NULL,
    end_date TEXT NULL,
    bar_count INTEGER NOT NULL,
    bars_sha256 TEXT NOT NULL,
    bars_payload BYTEA NOT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, symbol)
);

CREATE INDEX IF NOT EXISTS backtest_history_partitions_job_symbol_index
    ON backtest_history_partitions (job_id, symbol);
