CREATE TABLE backtest.backtest_result_chunks (
    run_id TEXT NOT NULL
        REFERENCES backtest.backtest_results(run_id),
    field_name TEXT NOT NULL,
    chunk_sequence INTEGER NOT NULL,
    item_count INTEGER NOT NULL,
    payload_json JSONB NOT NULL,
    payload_digest TEXT NOT NULL,
    PRIMARY KEY (run_id, field_name, chunk_sequence),
    CONSTRAINT backtest_result_chunks_field_name_check
        CHECK (field_name IN (
            'decisions',
            'fills',
            'trades',
            'orders',
            'daily_equity',
            'unresolved_positions'
        )),
    CONSTRAINT backtest_result_chunks_sequence_check
        CHECK (chunk_sequence >= 0),
    CONSTRAINT backtest_result_chunks_item_count_check
        CHECK (item_count > 0 AND item_count <= 100),
    CONSTRAINT backtest_result_chunks_payload_digest_check
        CHECK (payload_digest ~ '^[0-9a-f]{64}$')
);

CREATE INDEX backtest_result_chunks_run_field_index
    ON backtest.backtest_result_chunks (run_id, field_name, chunk_sequence);
