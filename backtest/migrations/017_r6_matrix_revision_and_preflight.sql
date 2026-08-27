-- R6 Amendment A1: additive matrix revision 2 and durable G3 preflight.
--
-- Existing revision-1 evidence remains immutable.  On an upgrade database we
-- serialize every existing R6 family and reject the migration if any formal
-- attempt was consumed.  A clean database has no family yet, so only the
-- forward schema is installed and the normal application transaction creates
-- revision 1 before a separately authorized revision-2 activation.

DO $$
DECLARE
    family_row RECORD;
BEGIN
    FOR family_row IN
        SELECT family_id
        FROM backtest.atomic_entry_benchmark_families
        ORDER BY family_id
    LOOP
        PERFORM 1
        FROM backtest.atomic_entry_benchmark_families
        WHERE family_id = family_row.family_id
        FOR UPDATE;

        IF EXISTS (
            SELECT 1
            FROM backtest.atomic_entry_benchmark_families
            WHERE family_id = family_row.family_id
              AND (
                  active_matrix_revision IS DISTINCT FROM 1
                  OR head_sequence <> 0
              )
        ) OR EXISTS (
            SELECT 1
            FROM backtest.atomic_entry_benchmark_attempts
            WHERE family_id = family_row.family_id
        ) THEN
            RAISE EXCEPTION
                'R6_MIGRATION_017_PRECONDITION_CONFLICT family=%',
                family_row.family_id;
        END IF;
    END LOOP;
END;
$$;

ALTER TABLE backtest.atomic_entry_benchmark_matrices
    DROP CONSTRAINT atomic_benchmark_matrix_revision,
    ADD CONSTRAINT atomic_benchmark_matrix_revision
        CHECK (matrix_revision IN (1, 2)),
    ADD CONSTRAINT atomic_benchmark_matrix_identity_pair
        UNIQUE (matrix_id, family_id),
    ADD CONSTRAINT atomic_benchmark_matrix_identity_revision
        UNIQUE (matrix_id, family_id, matrix_revision);

ALTER TABLE backtest.atomic_entry_benchmark_families
    ALTER COLUMN active_matrix_revision SET NOT NULL,
    ADD CONSTRAINT atomic_benchmark_family_active_revision
        CHECK (active_matrix_revision IN (1, 2));

CREATE TABLE backtest.atomic_entry_benchmark_matrix_protocols (
    matrix_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    matrix_revision INTEGER NOT NULL,
    protocol_core_json JSONB NOT NULL,
    protocol_core_digest TEXT NOT NULL,
    UNIQUE (family_id, matrix_revision),
    UNIQUE (matrix_id, family_id, matrix_revision),
    CONSTRAINT atomic_benchmark_matrix_protocol_revision CHECK (
        matrix_revision IN (1, 2)
    ),
    CONSTRAINT atomic_benchmark_matrix_protocol_sha CHECK (
        protocol_core_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_matrix_protocol_matrix_fk
        FOREIGN KEY (matrix_id, family_id, matrix_revision)
        REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id, matrix_revision
        )
);

INSERT INTO backtest.atomic_entry_benchmark_matrix_protocols (
    matrix_id, family_id, matrix_revision,
    protocol_core_json, protocol_core_digest
)
SELECT
    matrix.matrix_id,
    matrix.family_id,
    matrix.matrix_revision,
    family.protocol_core_json,
    family.protocol_core_digest
FROM backtest.atomic_entry_benchmark_matrices AS matrix
JOIN backtest.atomic_entry_benchmark_families AS family
  ON family.family_id = matrix.family_id
WHERE matrix.matrix_revision = 1;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM backtest.atomic_entry_benchmark_matrices AS matrix
        JOIN backtest.atomic_entry_benchmark_families AS family
          ON family.family_id = matrix.family_id
        JOIN backtest.atomic_entry_benchmark_matrix_protocols AS protocol
          ON protocol.matrix_id = matrix.matrix_id
         AND protocol.family_id = matrix.family_id
         AND protocol.matrix_revision = matrix.matrix_revision
        WHERE matrix.matrix_revision = 1
          AND (
              matrix.matrix_core_json->>'protocol_core_digest'
                  IS DISTINCT FROM family.protocol_core_digest
              OR matrix.registration_json->>'protocol_core_digest'
                  IS DISTINCT FROM family.protocol_core_digest
              OR matrix.benchmark_build_binding_json->>'protocol_core_digest'
                  IS DISTINCT FROM family.protocol_core_digest
              OR protocol.protocol_core_json IS DISTINCT FROM family.protocol_core_json
              OR protocol.protocol_core_digest
                  IS DISTINCT FROM family.protocol_core_digest
          )
    ) THEN
        RAISE EXCEPTION 'R6_MIGRATION_017_PROTOCOL_BACKFILL_CONFLICT';
    END IF;
END;
$$;

ALTER TABLE backtest.atomic_entry_benchmark_slots
    DROP CONSTRAINT atomic_entry_benchmark_slots_family_id_slot_sequence_key,
    ADD CONSTRAINT atomic_benchmark_slot_matrix_family_fk
        FOREIGN KEY (matrix_id, family_id)
        REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id
        ),
    ADD CONSTRAINT atomic_benchmark_slot_attempt_identity
        UNIQUE (
            matrix_id, family_id, slot_sequence, hypothesis_id
        );

CREATE TABLE backtest.atomic_entry_benchmark_preflights (
    preflight_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    matrix_id TEXT NOT NULL,
    matrix_revision INTEGER NOT NULL,
    preflight_json JSONB NOT NULL,
    preflight_digest TEXT NOT NULL UNIQUE,
    eligibility_manifest_digest TEXT NOT NULL,
    preflight_registration_json JSONB NOT NULL,
    preflight_registration_digest TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    artifact_locator TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (matrix_id),
    UNIQUE (family_id, matrix_revision),
    UNIQUE (preflight_id, matrix_id),
    CONSTRAINT atomic_benchmark_preflight_revision CHECK (
        matrix_revision = 2
    ),
    CONSTRAINT atomic_benchmark_preflight_status CHECK (
        status = 'ACCEPTED'
    ),
    CONSTRAINT atomic_benchmark_preflight_sha CHECK (
        preflight_digest ~ '^[0-9a-f]{64}$'
        AND eligibility_manifest_digest ~ '^[0-9a-f]{64}$'
        AND preflight_registration_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_preflight_audit CHECK (
        btrim(artifact_locator) <> ''
        AND btrim(actor_id) <> ''
        AND btrim(change_note) <> ''
    ),
    CONSTRAINT atomic_benchmark_preflight_matrix_fk
        FOREIGN KEY (matrix_id, family_id, matrix_revision)
        REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id, matrix_revision
        )
);

ALTER TABLE backtest.atomic_entry_benchmark_attempts
    ADD CONSTRAINT atomic_benchmark_attempt_identity
        UNIQUE (attempt_id, family_id, matrix_id),
    ADD CONSTRAINT atomic_benchmark_attempt_slot_fk
        FOREIGN KEY (
            matrix_id, family_id, slot_sequence, hypothesis_id
        ) REFERENCES backtest.atomic_entry_benchmark_slots (
            matrix_id, family_id, slot_sequence, hypothesis_id
        );

ALTER TABLE backtest.atomic_entry_benchmark_attempts
    ALTER COLUMN preflight_id SET NOT NULL,
    ADD CONSTRAINT atomic_benchmark_attempt_preflight_fk
        FOREIGN KEY (preflight_id, matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_preflights (
            preflight_id, matrix_id
        );

ALTER TABLE backtest.atomic_entry_benchmark_operations
    ALTER COLUMN matrix_id SET NOT NULL,
    ADD CONSTRAINT atomic_benchmark_operation_matrix_fk
        FOREIGN KEY (matrix_id, family_id)
        REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id
        ),
    ADD CONSTRAINT atomic_benchmark_operation_identity
        UNIQUE (operation_id, family_id, matrix_id),
    ADD CONSTRAINT atomic_benchmark_operation_attempt_identity
        UNIQUE (operation_id, family_id, matrix_id, attempt_id),
    ADD CONSTRAINT atomic_benchmark_operation_attempt_fk
        FOREIGN KEY (attempt_id, family_id, matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_attempts (
            attempt_id, family_id, matrix_id
        ),
    ADD CONSTRAINT atomic_benchmark_operation_scope CHECK (
        (
            attempt_id IS NULL
            AND operation_type IN (
                'SEAL_MATRIX', 'ACTIVATE_MATRIX_REVISION_2',
                'REGISTER_PREFLIGHT_V2'
            )
        ) OR (
            attempt_id IS NOT NULL
            AND operation_type IN (
                'START_ATTEMPT', 'TRANSITION_ATTEMPT'
            )
        )
    );

ALTER TABLE backtest.atomic_entry_benchmark_transition_evidence
    ADD CONSTRAINT atomic_benchmark_transition_attempt_fk
        FOREIGN KEY (attempt_id, family_id, matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_attempts (
            attempt_id, family_id, matrix_id
        ),
    ADD CONSTRAINT atomic_benchmark_transition_operation_fk
        FOREIGN KEY (operation_id, family_id, matrix_id, attempt_id)
        REFERENCES backtest.atomic_entry_benchmark_operations (
            operation_id, family_id, matrix_id, attempt_id
        );

ALTER TABLE backtest.atomic_entry_benchmark_outbox
    ALTER COLUMN matrix_id SET NOT NULL,
    ADD CONSTRAINT atomic_benchmark_outbox_matrix_fk
        FOREIGN KEY (matrix_id, family_id)
        REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id
        ),
    ADD CONSTRAINT atomic_benchmark_outbox_operation_fk
        FOREIGN KEY (operation_id, family_id, matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_operations (
            operation_id, family_id, matrix_id
        ),
    ADD CONSTRAINT atomic_benchmark_outbox_attempt_fk
        FOREIGN KEY (attempt_id, family_id, matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_attempts (
            attempt_id, family_id, matrix_id
        );

ALTER TABLE backtest.atomic_entry_benchmark_releases
    DROP CONSTRAINT atomic_benchmark_release_revision,
    ADD CONSTRAINT atomic_benchmark_release_revision
        CHECK (matrix_revision IN (1, 2)),
    ADD CONSTRAINT atomic_benchmark_release_matrix_fk
        FOREIGN KEY (matrix_id, family_id, matrix_revision)
        REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id, matrix_revision
        );

ALTER TABLE backtest.atomic_entry_benchmark_preflights
    ADD CONSTRAINT atomic_benchmark_preflight_operation_fk
        FOREIGN KEY (operation_id, family_id, matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_operations (
            operation_id, family_id, matrix_id
        );

CREATE INDEX atomic_benchmark_preflight_created_index
    ON backtest.atomic_entry_benchmark_preflights (family_id, created_at DESC);
