\set ON_ERROR_STOP on
\if :{?baseline_run_id}
\else
  \echo 'baseline_run_id is required'
  \quit 2
\endif
\if :{?replay_id}
\else
  \echo 'replay_id is required'
  \quit 2
\endif
\if :{?expected_result_manifest_digest}
\else
  \echo 'expected_result_manifest_digest is required'
  \quit 2
\endif
\if :{?expected_postflight_digest}
\else
  \echo 'expected_postflight_digest is required'
  \quit 2
\endif

BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH
registration_rows AS (
    SELECT *
    FROM backtest.r5_signal_ledger_replay_registrations
    WHERE baseline_run_id = :'baseline_run_id'
      AND control_contract_version = 'r5-signal-ledger-replay-v2'
      AND replay_id = :'replay_id'
),
registration AS (
    SELECT * FROM registration_rows LIMIT 1
),
head_rows AS (
    SELECT *
    FROM backtest.r5_signal_ledger_replay_heads
    WHERE baseline_run_id = :'baseline_run_id'
      AND control_contract_version = 'r5-signal-ledger-replay-v2'
      AND replay_id = :'replay_id'
),
result_rows AS (
    SELECT *
    FROM backtest.r5_signal_ledger_replay_results
    WHERE replay_id = :'replay_id'
),
result_root AS (
    SELECT * FROM result_rows LIMIT 1
),
operation_rows AS (
    SELECT *
    FROM backtest.r5_signal_ledger_replay_operations
    WHERE baseline_run_id = :'baseline_run_id'
      AND control_contract_version = 'r5-signal-ledger-replay-v2'
      AND result_json->>'replay_id' = :'replay_id'
),
chunk_stats AS (
    SELECT
        field_name,
        COUNT(*) AS chunk_count,
        MIN(chunk_sequence) AS minimum_sequence,
        MAX(chunk_sequence) AS maximum_sequence,
        SUM(item_count) AS item_count
    FROM backtest.r5_signal_ledger_replay_result_chunks
    WHERE replay_id = :'replay_id'
    GROUP BY field_name
),
episode_tokens AS (
    SELECT
        (item->>'sequence')::bigint AS sequence,
        item->>'signal_id' AS signal_id,
        item->>'semantic_key' AS semantic_key
    FROM backtest.r5_signal_ledger_replay_result_chunks AS chunk
    CROSS JOIN LATERAL jsonb_array_elements(chunk.payload_json) AS item
    WHERE chunk.replay_id = :'replay_id'
      AND chunk.field_name = 'episodes'
),
entry_tokens AS (
    SELECT
        (item->>'sequence')::bigint AS sequence,
        item->>'signal_id' AS signal_id,
        item->>'semantic_key' AS semantic_key
    FROM backtest.r5_signal_ledger_replay_result_chunks AS chunk
    CROSS JOIN LATERAL jsonb_array_elements(chunk.payload_json) AS item
    WHERE chunk.replay_id = :'replay_id'
      AND chunk.field_name = 'modeled_entries'
),
exit_tokens AS (
    SELECT
        (item->>'sequence')::bigint AS sequence,
        item->>'signal_id' AS signal_id,
        item->>'semantic_key' AS semantic_key
    FROM backtest.r5_signal_ledger_replay_result_chunks AS chunk
    CROSS JOIN LATERAL jsonb_array_elements(chunk.payload_json) AS item
    WHERE chunk.replay_id = :'replay_id'
      AND chunk.field_name = 'modeled_exits'
),
episode_minus_entry AS (
    SELECT * FROM episode_tokens
    EXCEPT ALL
    SELECT * FROM entry_tokens
),
entry_minus_episode AS (
    SELECT * FROM entry_tokens
    EXCEPT ALL
    SELECT * FROM episode_tokens
),
episode_minus_exit AS (
    SELECT * FROM episode_tokens
    EXCEPT ALL
    SELECT * FROM exit_tokens
),
exit_minus_episode AS (
    SELECT * FROM exit_tokens
    EXCEPT ALL
    SELECT * FROM episode_tokens
),
state AS (
    SELECT
        (SELECT COUNT(*) FROM registration_rows) AS registration_count,
        (SELECT COUNT(*) FROM head_rows) AS head_count,
        (SELECT COUNT(*) FROM result_rows) AS result_count,
        (SELECT COUNT(*) FROM operation_rows) AS operation_count,
        COALESCE((SELECT status = 'ACCEPTED' FROM registration), false)
            AS registration_accepted,
        COALESCE((SELECT progress = 1 FROM registration), false)
            AS progress_complete,
        COALESCE((
            SELECT head.status = registration.status
               AND head.current_revision = registration.revision
               AND head.replay_id = registration.replay_id
            FROM head_rows AS head, registration
        ), false) AS head_matches,
        COALESCE((
            SELECT result.result_manifest_digest = registration.result_manifest_digest
               AND result.postflight_digest = registration.postflight_digest
               AND result.postflight_json = registration.postflight_json
               AND result.result_manifest_digest = :'expected_result_manifest_digest'
               AND result.postflight_digest = :'expected_postflight_digest'
               AND result.result_manifest_json->>'result_manifest_digest'
                   = :'expected_result_manifest_digest'
               AND result.postflight_json->>'postflight_digest'
                   = :'expected_postflight_digest'
            FROM result_root AS result, registration
        ), false) AS terminal_evidence_matches,
        :'expected_result_manifest_digest' ~ '^[0-9a-f]{64}$'
          AND :'expected_postflight_digest' ~ '^[0-9a-f]{64}$'
            AS expected_digest_format_valid,
        COALESCE((
            SELECT registration.ledger_manifest_json->>'schema_version'
                       = 'r5-signal-ledger-manifest-v2'
               AND registration.match_plan_manifest_json->>'schema_version'
                       = 'r5-match-plan-manifest-v2'
               AND result.result_manifest_json->>'schema_version'
                       = 'r5-signal-ledger-replay-result-v2'
               AND result.result_manifest_json->'summary'->>'schema_version'
                       = 'r5-replay-summary-v2'
               AND result.postflight_json->>'schema_version'
                       = 'r5-signal-ledger-replay-postflight-v2'
               AND result.postflight_json->'conditions'->>'schema_version'
                       = 'r5-replay-postflight-conditions-v2'
               AND result.postflight_json->'diagnostics'->>'schema_version'
                       = 'r5-replay-postflight-diagnostics-v2'
               AND registration.ledger_manifest_json->>'control_contract_version'
                       = 'r5-signal-ledger-replay-v2'
               AND registration.match_plan_manifest_json->>'control_contract_version'
                       = 'r5-signal-ledger-replay-v2'
               AND result.result_manifest_json->>'control_contract_version'
                       = 'r5-signal-ledger-replay-v2'
               AND result.postflight_json->>'control_contract_version'
                       = 'r5-signal-ledger-replay-v2'
            FROM result_root AS result, registration
        ), false) AS schema_versions_match,
        COALESCE((
            SELECT ARRAY(
                       SELECT jsonb_object_keys(result.result_manifest_json)
                       ORDER BY 1
                   ) = ARRAY[
                       'algorithm_contract_digest', 'algorithm_implementation_digest',
                       'baseline_run_id', 'control_contract_version',
                       'cost_identity_digest', 'episode_count',
                       'episode_row_schema_version', 'episode_rows_sha256',
                       'episode_signal_multiplicity_digest', 'ledger_manifest_digest',
                       'match_plan_manifest_digest', 'modeled_entry_count',
                       'modeled_entry_row_schema_version', 'modeled_entry_rows_sha256',
                       'modeled_entry_signal_multiplicity_digest', 'modeled_exit_count',
                       'modeled_exit_row_schema_version', 'modeled_exit_rows_sha256',
                       'modeled_exit_signal_multiplicity_digest', 'registration_revision',
                       'replay_id', 'result_manifest_digest', 'result_projection_digest',
                       'schema_version', 'summary', 'summary_digest'
                   ]::text[]
               AND ARRAY(
                       SELECT jsonb_object_keys(result.result_manifest_json->'summary')
                       ORDER BY 1
                   ) = ARRAY[
                       'episode_count', 'loss_count', 'mean_net_return',
                       'mean_pre_slippage_return', 'median_net_return',
                       'median_pre_slippage_return', 'profit_factor',
                       'profit_factor_state', 'schema_version', 'sum_explicit_costs',
                       'sum_net_pnl', 'sum_post_slippage_gross_pnl',
                       'sum_pre_slippage_price_pnl', 'tie_count', 'win_count'
                   ]::text[]
               AND ARRAY(
                       SELECT jsonb_object_keys(result.postflight_json)
                       ORDER BY 1
                   ) = ARRAY[
                       'baseline_result_digest', 'baseline_run_id', 'conditions',
                       'control_contract_version', 'diagnostics',
                       'identity_validation_digest', 'ledger_manifest_digest',
                       'match_plan_manifest_digest', 'postflight_digest',
                       'registration_revision', 'replay_id', 'result_manifest_digest',
                       'schema_version', 'verdict'
                   ]::text[]
               AND ARRAY(
                       SELECT jsonb_object_keys(result.postflight_json->'conditions')
                       ORDER BY 1
                   ) = ARRAY[
                       'all_formulas_rebuild', 'all_layer_counts_equal',
                       'all_shares_exact_min_lot', 'baseline_identity_valid',
                       'decision_ledger_bidirectional_parity',
                       'duplicate_match_count_zero',
                       'episode_modeled_entry_bidirectional_parity',
                       'episode_modeled_exit_bidirectional_parity',
                       'frozen_signal_count_matches', 'ledger_artifact_valid',
                       'ledger_match_bidirectional_parity',
                       'match_episode_bidirectional_parity',
                       'match_plan_artifact_valid', 'no_duplicate_rows',
                       'no_missing_entry_or_exit', 'no_provider_or_broker_calls',
                       'no_strategy_evaluation', 'order_inception_seal_valid',
                       'order_ledger_bidirectional_parity', 'result_artifact_valid',
                       'schema_version', 'v1_invalid_lineage_valid'
                   ]::text[]
               AND ARRAY(
                       SELECT jsonb_object_keys(result.postflight_json->'diagnostics')
                       ORDER BY 1
                   ) = ARRAY[
                       'authoritative_entry_decision_count', 'broker_call_count',
                       'decision_minus_ledger_count',
                       'decision_signal_multiplicity_digest',
                       'duplicate_decision_count', 'duplicate_episode_count',
                       'duplicate_ledger_count', 'duplicate_match_count',
                       'duplicate_modeled_entry_count', 'duplicate_modeled_exit_count',
                       'duplicate_order_derivation_count', 'episode_count',
                       'episode_minus_match_count',
                       'episode_minus_modeled_entry_count',
                       'episode_minus_modeled_exit_count',
                       'episode_signal_multiplicity_digest', 'formula_mismatch_count',
                       'ledger_minus_decision_count', 'ledger_minus_match_count',
                       'ledger_minus_order_count', 'ledger_signal_count',
                       'ledger_signal_multiplicity_digest', 'match_count',
                       'match_minus_episode_count', 'match_minus_ledger_count',
                       'match_signal_multiplicity_digest', 'missing_entry_count',
                       'missing_exit_count', 'modeled_entry_count',
                       'modeled_entry_minus_episode_count',
                       'modeled_entry_signal_multiplicity_digest', 'modeled_exit_count',
                       'modeled_exit_minus_episode_count',
                       'modeled_exit_signal_multiplicity_digest',
                       'order_derivation_count', 'order_minus_ledger_count',
                       'order_signal_multiplicity_digest', 'provider_call_count',
                       'schema_version', 'share_mismatch_count',
                       'strategy_evaluation_count'
                   ]::text[]
            FROM result_root AS result
        ), false) AS exact_terminal_schemas_match,
        COALESCE((
            SELECT result.result_manifest_json->>'ledger_manifest_digest'
                       = registration.ledger_manifest_digest
               AND result.result_manifest_json->>'match_plan_manifest_digest'
                       = registration.match_plan_manifest_digest
               AND result.postflight_json->>'ledger_manifest_digest'
                       = registration.ledger_manifest_digest
               AND result.postflight_json->>'match_plan_manifest_digest'
                       = registration.match_plan_manifest_digest
               AND result.postflight_json->>'result_manifest_digest'
                       = :'expected_result_manifest_digest'
               AND registration.ledger_manifest_json->>'ledger_manifest_digest'
                       = registration.ledger_manifest_digest
               AND registration.match_plan_manifest_json->>'match_plan_manifest_digest'
                       = registration.match_plan_manifest_digest
               AND registration.match_plan_manifest_json->>'ledger_manifest_digest'
                       = registration.ledger_manifest_digest
               AND registration.match_plan_manifest_json->>'ledger_rows_sha256'
                       = registration.ledger_manifest_json->>'ledger_rows_sha256'
               AND result.result_manifest_json->>'baseline_run_id'
                       = :'baseline_run_id'
               AND result.postflight_json->>'baseline_run_id'
                       = :'baseline_run_id'
               AND result.result_manifest_json->>'replay_id' = :'replay_id'
               AND result.postflight_json->>'replay_id' = :'replay_id'
               AND (result.result_manifest_json->>'registration_revision')::bigint
                       = registration.revision
               AND (result.postflight_json->>'registration_revision')::bigint
                       = registration.revision
            FROM result_root AS result, registration
        ), false) AS lineage_digests_match,
        COALESCE((
            SELECT result_manifest_json->>'replay_id' = :'replay_id'
               AND result_manifest_json->>'baseline_run_id' = :'baseline_run_id'
               AND (result_manifest_json->>'episode_count')::bigint = 128802
               AND (result_manifest_json->>'modeled_entry_count')::bigint = 128802
               AND (result_manifest_json->>'modeled_exit_count')::bigint = 128802
               AND (result_manifest_json->'summary'->>'episode_count')::bigint = 128802
            FROM result_root
        ), false) AS result_manifest_counts_match,
        COALESCE((
            SELECT postflight_json->>'verdict' = 'ACCEPTED'
               AND postflight_json->>'replay_id' = :'replay_id'
               AND postflight_json->>'baseline_run_id' = :'baseline_run_id'
               AND (postflight_json->'diagnostics'->>'episode_count')::bigint = 128802
               AND (postflight_json->'diagnostics'->>'modeled_entry_count')::bigint = 128802
               AND (postflight_json->'diagnostics'->>'modeled_exit_count')::bigint = 128802
               AND (postflight_json->'diagnostics'->>'provider_call_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'broker_call_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'strategy_evaluation_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'missing_entry_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'missing_exit_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_match_count')::bigint = 0
               AND NOT EXISTS (
                   SELECT 1
                   FROM jsonb_each(postflight_json->'conditions') AS condition
                   WHERE condition.key <> 'schema_version'
                     AND condition.value <> 'true'::jsonb
               )
            FROM registration
        ), false) AS postflight_acceptance_matches,
        COALESCE((
            SELECT (result.postflight_json->'diagnostics'->>'authoritative_entry_decision_count')::bigint
                       = (registration.ledger_manifest_json->>'baseline_entry_decision_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'order_derivation_count')::bigint
                       = (registration.ledger_manifest_json->>'v2_inception_order_derivation_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'ledger_signal_count')::bigint
                       = (registration.ledger_manifest_json->>'ledger_signal_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'match_count')::bigint
                       = (registration.match_plan_manifest_json->>'signal_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'episode_count')::bigint
                       = (result.result_manifest_json->>'episode_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'modeled_entry_count')::bigint
                       = (result.result_manifest_json->>'modeled_entry_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'modeled_exit_count')::bigint
                       = (result.result_manifest_json->>'modeled_exit_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'missing_entry_count')::bigint
                       = (registration.match_plan_manifest_json->>'missing_entry_count')::bigint
               AND (result.postflight_json->'diagnostics'->>'missing_exit_count')::bigint
                       = (registration.match_plan_manifest_json->>'missing_exit_count')::bigint
            FROM result_root AS result, registration
        ), false) AS diagnostic_counts_match,
        COALESCE((
            SELECT (postflight_json->'diagnostics'->>'decision_minus_ledger_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'ledger_minus_decision_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'order_minus_ledger_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'ledger_minus_order_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'ledger_minus_match_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'match_minus_ledger_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'match_minus_episode_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'episode_minus_match_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'episode_minus_modeled_entry_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'modeled_entry_minus_episode_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'episode_minus_modeled_exit_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'modeled_exit_minus_episode_count')::bigint = 0
            FROM result_root
        ), false) AS diagnostic_differences_zero,
        COALESCE((
            SELECT (postflight_json->'diagnostics'->>'duplicate_decision_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_order_derivation_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_ledger_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_match_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_episode_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_modeled_entry_count')::bigint = 0
               AND (postflight_json->'diagnostics'->>'duplicate_modeled_exit_count')::bigint = 0
            FROM result_root
        ), false) AS diagnostic_duplicates_zero,
        COALESCE((
            SELECT result.postflight_json->'diagnostics'->>'decision_signal_multiplicity_digest'
                       = result.postflight_json->'diagnostics'->>'ledger_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'order_signal_multiplicity_digest'
                       = result.postflight_json->'diagnostics'->>'ledger_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'ledger_signal_multiplicity_digest'
                       = result.postflight_json->'diagnostics'->>'match_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'match_signal_multiplicity_digest'
                       = registration.match_plan_manifest_json->>'match_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'match_signal_multiplicity_digest'
                       = result.postflight_json->'diagnostics'->>'episode_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'episode_signal_multiplicity_digest'
                       = result.result_manifest_json->>'episode_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'episode_signal_multiplicity_digest'
                       = result.postflight_json->'diagnostics'->>'modeled_entry_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'modeled_entry_signal_multiplicity_digest'
                       = result.result_manifest_json->>'modeled_entry_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'episode_signal_multiplicity_digest'
                       = result.postflight_json->'diagnostics'->>'modeled_exit_signal_multiplicity_digest'
               AND result.postflight_json->'diagnostics'->>'modeled_exit_signal_multiplicity_digest'
                       = result.result_manifest_json->>'modeled_exit_signal_multiplicity_digest'
            FROM result_root AS result, registration
        ), false) AS diagnostic_multiplicity_chain_matches,
        COALESCE((
            SELECT COUNT(*) = 3
               AND BOOL_AND(item_count = 128802)
               AND BOOL_AND(minimum_sequence = 0)
               AND BOOL_AND(maximum_sequence + 1 = chunk_count)
            FROM chunk_stats
        ), false) AS chunk_counts_match,
        (SELECT COUNT(*) FROM episode_minus_entry) AS episode_minus_entry_count,
        (SELECT COUNT(*) FROM entry_minus_episode) AS entry_minus_episode_count,
        (SELECT COUNT(*) FROM episode_minus_exit) AS episode_minus_exit_count,
        (SELECT COUNT(*) FROM exit_minus_episode) AS exit_minus_episode_count
),
gate AS (
    SELECT *,
        registration_count = 1
        AND head_count = 1
        AND result_count = 1
        AND operation_count = 1
        AND registration_accepted
        AND progress_complete
        AND head_matches
        AND terminal_evidence_matches
        AND expected_digest_format_valid
        AND schema_versions_match
        AND exact_terminal_schemas_match
        AND lineage_digests_match
        AND result_manifest_counts_match
        AND postflight_acceptance_matches
        AND diagnostic_counts_match
        AND diagnostic_differences_zero
        AND diagnostic_duplicates_zero
        AND diagnostic_multiplicity_chain_matches
        AND chunk_counts_match
        AND episode_minus_entry_count = 0
        AND entry_minus_episode_count = 0
        AND episode_minus_exit_count = 0
        AND exit_minus_episode_count = 0 AS gate_ok
    FROM state
)
SELECT
    gate_ok,
    jsonb_build_object(
        'registration_count', registration_count,
        'head_count', head_count,
        'result_count', result_count,
        'operation_count', operation_count,
        'registration_accepted', registration_accepted,
        'progress_complete', progress_complete,
        'head_matches', head_matches,
        'terminal_evidence_matches', terminal_evidence_matches,
        'expected_digest_format_valid', expected_digest_format_valid,
        'schema_versions_match', schema_versions_match,
        'exact_terminal_schemas_match', exact_terminal_schemas_match,
        'lineage_digests_match', lineage_digests_match,
        'result_manifest_counts_match', result_manifest_counts_match,
        'postflight_acceptance_matches', postflight_acceptance_matches,
        'diagnostic_counts_match', diagnostic_counts_match,
        'diagnostic_differences_zero', diagnostic_differences_zero,
        'diagnostic_duplicates_zero', diagnostic_duplicates_zero,
        'diagnostic_multiplicity_chain_matches', diagnostic_multiplicity_chain_matches,
        'chunk_counts_match', chunk_counts_match,
        'episode_minus_entry_count', episode_minus_entry_count,
        'entry_minus_episode_count', entry_minus_episode_count,
        'episode_minus_exit_count', episode_minus_exit_count,
        'exit_minus_episode_count', exit_minus_episode_count
    )::text AS evidence
FROM gate
\gset r5_v2_

\echo :r5_v2_evidence
SELECT 1 / CASE WHEN :'r5_v2_gate_ok'::boolean THEN 1 ELSE 0 END
    AS r5_v2_gate_assertion;

COMMIT;
