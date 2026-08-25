\set ON_ERROR_STOP on

-- Fail-closed reviewer evidence for one completed R5 control.
-- Product code MUST complete the same postflight before exposing performance;
-- this script is a second-layer audit, not the first enforcement boundary.
--
-- Usage:
-- psql ... \
--   -v baseline_run_id=run-91ad87981676414da87b928398fa43c9 \
--   -v control_run_id=<completed-accepted-control-run> \
--   -f r5_control_acceptance_queries.sql

\if :{?baseline_run_id}
\else
  \echo 'baseline_run_id is required'
  SELECT 1 / 0 AS r5_required_variable_missing;
\endif

\if :{?control_run_id}
\else
  \echo 'control_run_id is required'
  SELECT 1 / 0 AS r5_required_variable_missing;
\endif

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- A single statement calculates every Gate condition from one MVCC snapshot.
-- EXCEPT ALL preserves multiplicity, so duplicate signal keys cannot disappear.
WITH baseline_rows AS (
    SELECT *
    FROM backtest.backtest_runs
    WHERE run_id = :'baseline_run_id'
), control_rows AS (
    SELECT *
    FROM backtest.backtest_runs
    WHERE run_id = :'control_run_id'
), baseline_results AS (
    SELECT *
    FROM backtest.backtest_results
    WHERE run_id = :'baseline_run_id'
), control_results AS (
    SELECT *
    FROM backtest.backtest_results
    WHERE run_id = :'control_run_id'
), control_registrations AS (
    SELECT *
    FROM backtest.backtest_cash_admission_control_registrations
    WHERE baseline_run_id = :'baseline_run_id'
      AND control_run_id = :'control_run_id'
), baseline_entries AS (
    SELECT item->>'symbol' AS symbol,
           item->>'created_at' AS created_at,
           item->>'primary_strategy_id' AS primary_strategy_id,
           item->'triggered_strategy_ids' AS triggered_strategy_ids
    FROM backtest.backtest_result_chunks AS chunks
    CROSS JOIN LATERAL jsonb_array_elements(chunks.payload_json) AS item
    WHERE chunks.run_id = :'baseline_run_id'
      AND chunks.field_name = 'orders'
      AND item->>'side' = 'ENTRY'
), control_entry_orders AS (
    SELECT item
    FROM backtest.backtest_result_chunks AS chunks
    CROSS JOIN LATERAL jsonb_array_elements(chunks.payload_json) AS item
    WHERE chunks.run_id = :'control_run_id'
      AND chunks.field_name = 'orders'
      AND item->>'side' = 'ENTRY'
), control_entry_fills AS (
    SELECT item
    FROM backtest.backtest_result_chunks AS chunks
    CROSS JOIN LATERAL jsonb_array_elements(chunks.payload_json) AS item
    WHERE chunks.run_id = :'control_run_id'
      AND chunks.field_name = 'fills'
      AND item->>'side' = 'ENTRY'
), control_entries AS (
    SELECT item->>'symbol' AS symbol,
           item->>'created_at' AS created_at,
           item->>'primary_strategy_id' AS primary_strategy_id,
           item->'triggered_strategy_ids' AS triggered_strategy_ids
    FROM control_entry_orders
), missing_from_control AS (
    SELECT * FROM baseline_entries
    EXCEPT ALL
    SELECT * FROM control_entries
), extra_in_control AS (
    SELECT * FROM control_entries
    EXCEPT ALL
    SELECT * FROM baseline_entries
), configs AS (
    SELECT baseline.config_json AS baseline_config,
           control.config_json AS control_config
    FROM baseline_rows AS baseline
    CROSS JOIN control_rows AS control
), config_keys AS (
    SELECT DISTINCT jsonb_object_keys(
        configs.baseline_config || configs.control_config
    ) AS field
    FROM configs
), unapproved_config_deltas AS (
    SELECT keys.field
    FROM configs
    CROSS JOIN config_keys AS keys
    WHERE keys.field NOT IN (
              'starting_cash',
              'position_fraction',
              'parent_run_id',
              'change_note',
              'research_control_snapshot',
              'atomic_run_request',
              'atomic_run_request_digest'
          )
      AND configs.baseline_config->keys.field
          IS DISTINCT FROM configs.control_config->keys.field
), gate_values AS (
    SELECT
        (SELECT COUNT(*) FROM baseline_rows) AS baseline_row_count,
        (SELECT COUNT(*) FROM control_rows) AS control_row_count,
        (SELECT COUNT(*) FROM baseline_results) AS baseline_result_count,
        (SELECT COUNT(*) FROM control_results) AS control_result_count,
        (SELECT COUNT(*) FROM control_registrations) AS control_registration_count,
        COALESCE((SELECT status FROM baseline_rows), '') AS baseline_status,
        COALESCE((SELECT status FROM control_rows), '') AS control_status,
        COALESCE((SELECT status FROM control_registrations), '')
            AS control_registration_status,
        (:'baseline_run_id' <> :'control_run_id') AS distinct_run_ids,
        COALESCE(
            (SELECT config_json->>'parent_run_id' = :'baseline_run_id'
             FROM control_rows),
            FALSE
        ) AS parent_lineage_matches,
        (SELECT COUNT(*) FROM unapproved_config_deltas)
            AS unapproved_config_delta_count,
        COALESCE(
            (SELECT (
                preflight_json->'statistics'
                    ->>'candidate_order_count'
            )::bigint FROM control_registrations),
            -1
        ) AS candidate_order_count,
        COALESCE(
            (SELECT (
                preflight_json->'statistics'
                    ->>'matched_next_bar_count'
            )::bigint FROM control_registrations),
            -1
        ) AS matched_next_bar_count,
        COALESCE(
            (SELECT (
                preflight_json->'statistics'
                    ->>'missing_next_bar_count'
            )::bigint FROM control_registrations),
            -1
        ) AS missing_next_bar_count,
        COALESCE(
            (SELECT NULLIF(
                config_json->'research_control_snapshot'->>'snapshot_digest',
                ''
            ) IS NOT NULL FROM control_rows),
            FALSE
        ) AS control_snapshot_digest_present,
        COALESCE(
            (SELECT preflight_digest ~ '^[0-9a-f]{64}$'
                AND preflight_digest = preflight_json->>'artifact_digest'
             FROM control_registrations),
            FALSE
        ) AS preflight_digest_present,
        COALESCE(
            (SELECT status = 'ACCEPTED'
                AND postflight_json->>'verdict' = 'ACCEPTED'
             FROM control_registrations),
            FALSE
        ) AS postflight_accepted,
        COALESCE(
            (SELECT postflight_digest ~ '^[0-9a-f]{64}$'
                AND postflight_digest = postflight_json->>'postflight_digest'
             FROM control_registrations),
            FALSE
        ) AS postflight_digest_present,
        COALESCE(
            (SELECT postflight_json->>'control_admission_projection_digest'
                ~ '^[0-9a-f]{64}$'
             FROM control_registrations),
            FALSE
        ) AS admission_projection_digest_present,
        (SELECT COUNT(*) FROM baseline_entries) AS baseline_entry_count,
        (SELECT COUNT(*) FROM control_entry_orders) AS control_entry_order_count,
        (SELECT COUNT(*) FROM control_entry_fills) AS control_entry_fill_count,
        (SELECT COUNT(*) FROM control_entry_orders
         WHERE item->>'status' IS DISTINCT FROM 'FILLED')
            AS control_non_filled_entry_count,
        (SELECT COUNT(*) FROM control_entry_orders
         WHERE item->>'status' IS DISTINCT FROM 'FILLED'
           AND NULLIF(item->>'reason', '') IS NOT NULL)
            AS control_rejection_reason_count,
        (SELECT COUNT(*) FROM missing_from_control) AS missing_from_control_count,
        (SELECT COUNT(*) FROM extra_in_control) AS extra_in_control_count
), gate AS (
    SELECT *,
        baseline_row_count = 1
        AND control_row_count = 1
        AND baseline_result_count = 1
        AND control_result_count = 1
        AND control_registration_count = 1
        AND baseline_status = 'COMPLETED'
        AND control_status = 'COMPLETED'
        AND control_registration_status = 'ACCEPTED'
        AND distinct_run_ids
        AND parent_lineage_matches
        AND unapproved_config_delta_count = 0
        AND candidate_order_count >= 0
        AND matched_next_bar_count = candidate_order_count
        AND missing_next_bar_count = 0
        AND control_snapshot_digest_present
        AND preflight_digest_present
        AND postflight_accepted
        AND postflight_digest_present
        AND admission_projection_digest_present
        AND baseline_entry_count = candidate_order_count
        AND control_entry_order_count = candidate_order_count
        AND control_entry_fill_count = candidate_order_count
        AND control_non_filled_entry_count = 0
        AND control_rejection_reason_count = 0
        AND missing_from_control_count = 0
        AND extra_in_control_count = 0
        AS gate_pass
    FROM gate_values
)
SELECT * FROM gate
\gset r5_

\echo 'R5 fail-closed acceptance snapshot'
\echo 'baseline/control rows: ' :r5_baseline_row_count ' / ' :r5_control_row_count
\echo 'baseline/control results: ' :r5_baseline_result_count ' / ' :r5_control_result_count
\echo 'control registration rows/status: ' :r5_control_registration_count ' / ' :r5_control_registration_status
\echo 'baseline/control status: ' :r5_baseline_status ' / ' :r5_control_status
\echo 'distinct IDs / parent lineage: ' :r5_distinct_run_ids ' / ' :r5_parent_lineage_matches
\echo 'unapproved config deltas: ' :r5_unapproved_config_delta_count
\echo 'candidate/matched/missing next bar: ' :r5_candidate_order_count ' / ' :r5_matched_next_bar_count ' / ' :r5_missing_next_bar_count
\echo 'baseline/control ENTRY orders/control fills: ' :r5_baseline_entry_count ' / ' :r5_control_entry_order_count ' / ' :r5_control_entry_fill_count
\echo 'non-FILLED ENTRY/rejection reasons: ' :r5_control_non_filled_entry_count ' / ' :r5_control_rejection_reason_count
\echo 'multiplicity parity missing/extra: ' :r5_missing_from_control_count ' / ' :r5_extra_in_control_count
\echo 'snapshot/preflight/postflight digests: ' :r5_control_snapshot_digest_present ' / ' :r5_preflight_digest_present ' / ' :r5_postflight_digest_present
\echo 'admission projection digest: ' :r5_admission_projection_digest_present
\echo 'server postflight accepted: ' :r5_postflight_accepted

\if :r5_gate_pass
  \echo 'R5_ACCEPTED'
  COMMIT;
\else
  ROLLBACK;
  \echo 'R5_REJECTED: at least one frozen acceptance condition failed'
  SELECT 1 / 0 AS r5_acceptance_failed;
\endif
