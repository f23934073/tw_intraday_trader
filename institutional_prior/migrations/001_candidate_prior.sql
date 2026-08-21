CREATE TABLE IF NOT EXISTS institutional_candidate_prior_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_identity_digest TEXT NOT NULL UNIQUE,
    artifact_digest TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    target_session TEXT NOT NULL,
    as_of_session TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    factor_prior_id TEXT NOT NULL,
    factor_prior_digest TEXT NOT NULL,
    price_prior_id TEXT NOT NULL,
    price_prior_digest TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    universe_digest TEXT NOT NULL,
    calendar_id TEXT NOT NULL,
    calendar_digest TEXT NOT NULL,
    hypothesis_definitions_json TEXT NOT NULL,
    research_status TEXT NOT NULL CHECK (research_status = 'EXPLORATORY'),
    strategy_ready INTEGER NOT NULL CHECK (strategy_ready = 0),
    production_ready INTEGER NOT NULL CHECK (production_ready = 0),
    live_admission_ready INTEGER NOT NULL CHECK (live_admission_ready = 0),
    execution_allowed INTEGER NOT NULL CHECK (execution_allowed = 0),
    issue_codes_json TEXT NOT NULL,
    entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
    projected_candidate_count INTEGER NOT NULL
        CHECK (projected_candidate_count >= 0),
    entries_digest TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (CAST(CURRENT_TIMESTAMP AS TEXT)),
    CHECK (projected_candidate_count <= entry_count)
);

CREATE TABLE IF NOT EXISTS institutional_candidate_prior_entries (
    artifact_id TEXT NOT NULL REFERENCES institutional_candidate_prior_artifacts(artifact_id),
    entry_ordinal INTEGER NOT NULL CHECK (entry_ordinal >= 0),
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    candidate_rank INTEGER NULL CHECK (candidate_rank IS NULL OR candidate_rank > 0),
    price_rank INTEGER NULL CHECK (price_rank IS NULL OR price_rank > 0),
    cohorts_json TEXT NOT NULL,
    matched_hypotheses_json TEXT NOT NULL,
    selection_reason_codes_json TEXT NOT NULL,
    foreign_5d_value TEXT NULL,
    foreign_5d_percentile TEXT NULL,
    trust_5d_value TEXT NULL,
    trust_5d_percentile TEXT NULL,
    entry_digest TEXT NOT NULL,
    entry_json TEXT NOT NULL,
    PRIMARY KEY (artifact_id, entry_ordinal),
    UNIQUE (artifact_id, market, symbol)
);

CREATE INDEX IF NOT EXISTS institutional_candidate_prior_target_index
    ON institutional_candidate_prior_artifacts (target_session, as_of_session);

CREATE INDEX IF NOT EXISTS institutional_candidate_prior_rank_index
    ON institutional_candidate_prior_entries (artifact_id, candidate_rank);
