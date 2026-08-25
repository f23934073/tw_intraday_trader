\set ON_ERROR_STOP on
\set run_id 'run-91ad87981676414da87b928398fa43c9'

BEGIN READ ONLY;

\echo 'run_identity'
SELECT run_id, status, config_digest, dataset_id, dataset_digest, result_digest,
       created_at, updated_at
FROM backtest.backtest_runs
WHERE run_id = :'run_id';

\echo 'projection_counts'
SELECT
    (SELECT COUNT(*) FROM backtest.backtest_decisions WHERE run_id = :'run_id') AS decisions,
    (SELECT COUNT(*) FROM backtest.backtest_trades WHERE run_id = :'run_id') AS trades,
    (SELECT COUNT(*) FROM backtest.backtest_daily_equity WHERE run_id = :'run_id') AS daily_equity,
    (SELECT COALESCE(SUM(item_count), 0) FROM backtest.backtest_result_chunks WHERE run_id = :'run_id' AND field_name = 'orders') AS orders,
    (SELECT COALESCE(SUM(item_count), 0) FROM backtest.backtest_result_chunks WHERE run_id = :'run_id' AND field_name = 'fills') AS fills;

\echo 'order_outcomes'
WITH order_items AS (
    SELECT jsonb_array_elements(payload_json) AS item
    FROM backtest.backtest_result_chunks
    WHERE run_id = :'run_id' AND field_name = 'orders'
)
SELECT item->>'side' AS side,
       item->>'status' AS status,
       item->>'reason' AS reason,
       COUNT(*) AS orders
FROM order_items
GROUP BY 1, 2, 3
ORDER BY 1, 2, 4 DESC;

\echo 'daily_signal_admission'
WITH order_items AS (
    SELECT jsonb_array_elements(payload_json) AS item
    FROM backtest.backtest_result_chunks
    WHERE run_id = :'run_id' AND field_name = 'orders'
), daily AS (
    SELECT ((item->>'created_at')::timestamptz AT TIME ZONE 'Asia/Taipei')::date AS session_date,
           COUNT(*) AS signals,
           COUNT(*) FILTER (WHERE item->>'status' = 'FILLED') AS filled
    FROM order_items
    WHERE item->>'side' = 'ENTRY'
    GROUP BY 1
)
SELECT COUNT(*) AS signal_days,
       AVG(signals) AS average_signals,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY signals) AS median_signals,
       AVG(filled) AS average_filled,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY filled) AS median_filled,
       SUM(filled)::numeric / SUM(signals) AS fill_rate
FROM daily;

\echo 'r5_daily_signal_ceiling'
WITH order_items AS (
    SELECT jsonb_array_elements(payload_json) AS item
    FROM backtest.backtest_result_chunks
    WHERE run_id = :'run_id' AND field_name = 'orders'
), daily AS (
    SELECT ((item->>'created_at')::timestamptz AT TIME ZONE 'Asia/Taipei')::date
             AS session_date,
           COUNT(*) AS entry_signals,
           COUNT(DISTINCT item->>'symbol') AS distinct_entry_symbols
    FROM order_items
    WHERE item->>'side' = 'ENTRY'
    GROUP BY 1
)
SELECT MAX(entry_signals) AS s_max,
       MAX(distinct_entry_symbols) AS distinct_s_max,
       COUNT(*) AS observed_sessions
FROM daily;

\echo 'gross_cost_net_reconciliation'
WITH trades AS (
    SELECT (payload_json->>'gross_pnl')::numeric AS gross_pnl,
           (payload_json->>'net_pnl')::numeric AS net_pnl,
           (payload_json->'entry'->>'commission')::numeric AS entry_commission,
           (payload_json->'exit'->>'commission')::numeric AS exit_commission,
           (payload_json->'exit'->>'tax')::numeric AS sell_tax
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
)
SELECT COUNT(*) AS trades,
       SUM(gross_pnl) AS gross_pnl,
       SUM(entry_commission) AS entry_commission,
       SUM(exit_commission) AS exit_commission,
       SUM(sell_tax) AS sell_tax,
       SUM(entry_commission + exit_commission + sell_tax) AS explicit_costs,
       SUM(net_pnl) AS net_pnl,
       SUM(gross_pnl - entry_commission - exit_commission - sell_tax - net_pnl) AS reconciliation_error,
       SUM(CASE WHEN gross_pnl > 0 THEN gross_pnl ELSE 0 END)
         / NULLIF(ABS(SUM(CASE WHEN gross_pnl < 0 THEN gross_pnl ELSE 0 END)), 0) AS gross_profit_factor
FROM trades;

\echo 'slippage_and_total_friction'
WITH trades AS (
    SELECT (payload_json->>'gross_pnl')::numeric AS post_slippage_gross,
           (payload_json->>'net_pnl')::numeric AS net_pnl,
           (payload_json->'entry'->>'price')::numeric AS entry_fill_price,
           (payload_json->'exit'->>'price')::numeric AS exit_fill_price,
           (payload_json->'entry'->>'shares')::numeric AS shares,
           (payload_json->'entry'->>'total_cost')::numeric
             + (payload_json->'exit'->>'total_cost')::numeric AS explicit_costs
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
), reconstructed AS (
    SELECT *,
           ((exit_fill_price / 0.9995) - (entry_fill_price / 1.0005)) * shares
             AS pre_slippage_gross
    FROM trades
)
SELECT SUM(pre_slippage_gross) AS pre_slippage_gross,
       SUM(pre_slippage_gross - post_slippage_gross) AS slippage_drag,
       SUM(explicit_costs) AS explicit_costs,
       SUM(pre_slippage_gross - net_pnl) AS total_friction,
       SUM(net_pnl) AS net_pnl
FROM reconstructed;

\echo 'performance_by_year'
WITH trades AS (
    SELECT EXTRACT(YEAR FROM entry_at::timestamptz AT TIME ZONE 'Asia/Taipei')::integer AS year,
           (payload_json->>'gross_pnl')::numeric AS gross_pnl,
           (payload_json->>'net_pnl')::numeric AS net_pnl,
           (payload_json->>'net_pnl_pct')::numeric AS net_pnl_pct,
           (payload_json->'entry'->>'total_cost')::numeric
             + (payload_json->'exit'->>'total_cost')::numeric AS explicit_costs
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
)
SELECT year, COUNT(*) AS trades,
       COUNT(*) FILTER (WHERE net_pnl > 0) AS wins,
       ROUND(AVG((net_pnl > 0)::integer)::numeric, 6) AS win_rate,
       SUM(gross_pnl) AS gross_pnl,
       SUM(explicit_costs) AS explicit_costs,
       SUM(net_pnl) AS net_pnl,
       AVG(net_pnl) AS expectancy,
       AVG(net_pnl_pct) AS average_net_pnl_pct,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_pnl_pct) AS median_net_pnl_pct
FROM trades
GROUP BY year
ORDER BY year;

\echo 'entry_time_distribution'
WITH trades AS (
    SELECT TO_CHAR(entry_at::timestamptz AT TIME ZONE 'Asia/Taipei', 'HH24:MI') AS entry_minute,
           (payload_json->>'net_pnl')::numeric AS net_pnl
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
)
SELECT entry_minute, COUNT(*) AS trades,
       ROUND(AVG((net_pnl > 0)::integer)::numeric, 6) AS win_rate,
       SUM(net_pnl) AS net_pnl
FROM trades
GROUP BY entry_minute
ORDER BY trades DESC, entry_minute
LIMIT 20;

\echo 'entry_signal_time_distribution'
WITH order_items AS (
    SELECT jsonb_array_elements(payload_json) AS item
    FROM backtest.backtest_result_chunks
    WHERE run_id = :'run_id' AND field_name = 'orders'
), entries AS (
    SELECT TO_CHAR((item->>'created_at')::timestamptz AT TIME ZONE 'Asia/Taipei', 'HH24:MI') AS signal_minute,
           item->>'status' AS status
    FROM order_items
    WHERE item->>'side' = 'ENTRY'
)
SELECT signal_minute, COUNT(*) AS signals,
       COUNT(*) FILTER (WHERE status = 'FILLED') AS filled,
       AVG((status = 'FILLED')::integer) AS fill_rate
FROM entries
GROUP BY signal_minute
ORDER BY signals DESC, signal_minute
LIMIT 20;

\echo 'same_day_signal_rank_bias'
WITH order_items AS (
    SELECT jsonb_array_elements(payload_json) AS item
    FROM backtest.backtest_result_chunks
    WHERE run_id = :'run_id' AND field_name = 'orders'
), entries AS (
    SELECT (item->>'created_at')::timestamptz AS created_at,
           item->>'symbol' AS symbol,
           item->>'status' AS status
    FROM order_items
    WHERE item->>'side' = 'ENTRY'
), ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY (created_at AT TIME ZONE 'Asia/Taipei')::date
               ORDER BY created_at, symbol
           ) AS signal_rank
    FROM entries
)
SELECT CASE
           WHEN signal_rank <= 10 THEN '001-010'
           WHEN signal_rank <= 20 THEN '011-020'
           WHEN signal_rank <= 50 THEN '021-050'
           WHEN signal_rank <= 100 THEN '051-100'
           ELSE '101+'
       END AS rank_bucket,
       COUNT(*) AS signals,
       COUNT(*) FILTER (WHERE status = 'FILLED') AS filled,
       AVG((status = 'FILLED')::integer) AS fill_rate
FROM ranked
GROUP BY 1
ORDER BY 1;

\echo 'holding_time_distribution'
WITH trades AS (
    SELECT (payload_json->>'holding_minutes')::numeric AS holding_minutes,
           (payload_json->>'net_pnl')::numeric AS net_pnl
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
)
SELECT PERCENTILE_CONT(ARRAY[0, 0.25, 0.5, 0.75, 1]) WITHIN GROUP (ORDER BY holding_minutes) AS minute_quantiles,
       AVG(holding_minutes) AS average_minutes,
       CORR(holding_minutes, net_pnl) AS pnl_correlation
FROM trades;

\echo 'trade_return_distribution'
WITH trades AS (
    SELECT (payload_json->>'net_pnl_pct')::numeric AS net_pnl_pct
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
)
SELECT AVG(net_pnl_pct) AS average_net_pnl_pct,
       PERCENTILE_CONT(ARRAY[0, 0.05, 0.25, 0.5, 0.75, 0.95, 1])
         WITHIN GROUP (ORDER BY net_pnl_pct) AS return_pct_quantiles
FROM trades;

\echo 'daily_concentration'
WITH daily AS (
    SELECT (entry_at::timestamptz AT TIME ZONE 'Asia/Taipei')::date AS session_date,
           COUNT(*) AS trades,
           SUM((payload_json->>'net_pnl')::numeric) AS net_pnl
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
    GROUP BY 1
)
SELECT COUNT(*) AS active_days,
       MIN(trades) AS min_trades,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trades) AS median_trades,
       AVG(trades) AS average_trades,
       MAX(trades) AS max_trades,
       COUNT(*) FILTER (WHERE net_pnl > 0) AS profitable_days,
       AVG((net_pnl > 0)::integer) AS profitable_day_rate
FROM daily;

\echo 'symbol_concentration_summary'
WITH symbols AS (
    SELECT symbol, COUNT(*) AS trades,
           SUM((payload_json->>'net_pnl')::numeric) AS net_pnl
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
    GROUP BY symbol
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY trades DESC, symbol) AS trade_rank
    FROM symbols
)
SELECT COUNT(*) AS traded_symbols,
       SUM(trades) AS trades,
       SUM(trades) FILTER (WHERE trade_rank <= 10) AS top_10_symbol_trades,
       SUM(net_pnl) FILTER (WHERE trade_rank <= 10) AS top_10_symbol_net_pnl
FROM ranked;

\echo 'most_traded_symbols'
SELECT symbol, COUNT(*) AS trades,
       ROUND(AVG(((payload_json->>'net_pnl')::numeric > 0)::integer)::numeric, 6) AS win_rate,
       SUM((payload_json->>'gross_pnl')::numeric) AS gross_pnl,
       SUM((payload_json->>'net_pnl')::numeric) AS net_pnl
FROM backtest.backtest_trades
WHERE run_id = :'run_id'
GROUP BY symbol
ORDER BY trades DESC, symbol
LIMIT 20;

\echo 'worst_symbols'
SELECT symbol, COUNT(*) AS trades,
       SUM((payload_json->>'net_pnl')::numeric) AS net_pnl
FROM backtest.backtest_trades
WHERE run_id = :'run_id'
GROUP BY symbol
ORDER BY net_pnl ASC
LIMIT 15;

\echo 'best_symbols'
SELECT symbol, COUNT(*) AS trades,
       SUM((payload_json->>'net_pnl')::numeric) AS net_pnl
FROM backtest.backtest_trades
WHERE run_id = :'run_id'
GROUP BY symbol
ORDER BY net_pnl DESC
LIMIT 15;

\echo 'entry_distance_quintiles'
WITH base AS (
    SELECT (payload_json->'entry_decision'->'evaluations'->0->'observed'->>'price')::numeric AS signal_price,
           (payload_json->'entry_decision'->'evaluations'->0->'observed'->>'vwap')::numeric AS vwap,
           (payload_json->>'net_pnl')::numeric AS net_pnl
    FROM backtest.backtest_trades
    WHERE run_id = :'run_id'
), ranked AS (
    SELECT *, ((signal_price / NULLIF(vwap, 0)) - 1) * 10000 AS distance_bps,
           NTILE(5) OVER (ORDER BY ((signal_price / NULLIF(vwap, 0)) - 1) * 10000) AS quintile
    FROM base
)
SELECT quintile, COUNT(*) AS trades,
       MIN(distance_bps) AS min_distance_bps,
       MAX(distance_bps) AS max_distance_bps,
       ROUND(AVG((net_pnl > 0)::integer)::numeric, 6) AS win_rate,
       SUM(net_pnl) AS net_pnl,
       AVG(net_pnl) AS expectancy
FROM ranked
GROUP BY quintile
ORDER BY quintile;

COMMIT;
