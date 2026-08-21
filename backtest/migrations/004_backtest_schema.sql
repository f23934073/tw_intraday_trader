CREATE SCHEMA IF NOT EXISTS backtest;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'backtest_datasets',
        'strategy_definitions',
        'backtest_jobs',
        'backtest_history_partitions',
        'backtest_runs',
        'backtest_results',
        'backtest_decisions',
        'backtest_trades',
        'backtest_daily_equity',
        'backtest_comparisons'
    ]
    LOOP
        IF to_regclass(format('public.%I', table_name)) IS NOT NULL THEN
            IF to_regclass(format('backtest.%I', table_name)) IS NOT NULL THEN
                RAISE EXCEPTION
                    'cannot migrate %.%: backtest.% already exists',
                    'public', table_name, table_name;
            END IF;
            EXECUTE format(
                'ALTER TABLE public.%I SET SCHEMA backtest',
                table_name
            );
        END IF;
    END LOOP;
END
$$;
