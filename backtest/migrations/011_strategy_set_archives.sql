CREATE TABLE IF NOT EXISTS backtest.strategy_set_archives (
    strategy_set_id TEXT PRIMARY KEY,
    source_strategy_set_version_id TEXT NOT NULL
        REFERENCES backtest.strategy_set_versions(strategy_set_version_id),
    archived_by TEXT NOT NULL,
    archive_note TEXT NOT NULL,
    archive_digest TEXT NOT NULL UNIQUE,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS strategy_set_archives_time_index
    ON backtest.strategy_set_archives (archived_at DESC, strategy_set_id);
