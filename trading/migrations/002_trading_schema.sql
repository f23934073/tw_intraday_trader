CREATE SCHEMA IF NOT EXISTS trading;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'journal_sessions',
        'journal_records',
        'projection_checkpoints'
    ]
    LOOP
        IF to_regclass(format('public.%I', table_name)) IS NOT NULL THEN
            IF to_regclass(format('trading.%I', table_name)) IS NOT NULL THEN
                RAISE EXCEPTION
                    'cannot migrate %.%: trading.% already exists',
                    'public', table_name, table_name;
            END IF;
            EXECUTE format(
                'ALTER TABLE public.%I SET SCHEMA trading',
                table_name
            );
        END IF;
    END LOOP;
END
$$;
