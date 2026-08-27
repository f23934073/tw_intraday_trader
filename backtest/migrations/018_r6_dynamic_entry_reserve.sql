-- R6 Amendment A2: admit matrix/preflight revision 3 and durable source audit.
--
-- This migration is schema-only.  It never creates or activates revision 3.
-- The application must first register the accepted source-only audit, then use
-- a separately reviewed CAS transaction to activate the new matrix graph.

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
            FROM backtest.atomic_entry_benchmark_families AS family
            WHERE family.family_id = family_row.family_id
              AND (
                  family.active_matrix_revision IS DISTINCT FROM 2
                  OR family.head_sequence <> 0
                  OR family.release_state <> 'NOT_READY'
              )
        ) OR EXISTS (
            SELECT 1
            FROM backtest.atomic_entry_benchmark_attempts AS attempt
            WHERE attempt.family_id = family_row.family_id
        ) OR EXISTS (
            SELECT 1
            FROM backtest.atomic_entry_benchmark_preflights AS preflight
            WHERE preflight.family_id = family_row.family_id
        ) OR NOT EXISTS (
            SELECT 1
            FROM backtest.atomic_entry_benchmark_matrices AS matrix
            JOIN backtest.atomic_entry_benchmark_releases AS release
              ON release.family_id = matrix.family_id
             AND release.matrix_id = matrix.matrix_id
             AND release.matrix_revision = matrix.matrix_revision
            WHERE matrix.family_id = family_row.family_id
              AND matrix.matrix_revision = 2
              AND matrix.status = 'SEALED'
              AND release.release_state = 'NOT_READY'
        ) THEN
            RAISE EXCEPTION
                'R6_MIGRATION_018_PRECONDITION_CONFLICT family=%',
                family_row.family_id;
        END IF;
    END LOOP;
END;
$$;

ALTER TABLE backtest.atomic_entry_benchmark_matrices
    DROP CONSTRAINT atomic_benchmark_matrix_revision,
    ADD CONSTRAINT atomic_benchmark_matrix_revision
        CHECK (matrix_revision IN (1, 2, 3));

ALTER TABLE backtest.atomic_entry_benchmark_families
    DROP CONSTRAINT atomic_benchmark_family_active_revision,
    ADD CONSTRAINT atomic_benchmark_family_active_revision
        CHECK (active_matrix_revision IN (1, 2, 3));

ALTER TABLE backtest.atomic_entry_benchmark_matrix_protocols
    DROP CONSTRAINT atomic_benchmark_matrix_protocol_revision,
    ADD CONSTRAINT atomic_benchmark_matrix_protocol_revision
        CHECK (matrix_revision IN (1, 2, 3));

ALTER TABLE backtest.atomic_entry_benchmark_preflights
    DROP CONSTRAINT atomic_benchmark_preflight_revision,
    ADD CONSTRAINT atomic_benchmark_preflight_revision
        CHECK (matrix_revision IN (2, 3));

ALTER TABLE backtest.atomic_entry_benchmark_releases
    DROP CONSTRAINT atomic_benchmark_release_revision,
    ADD CONSTRAINT atomic_benchmark_release_revision
        CHECK (matrix_revision IN (1, 2, 3));

ALTER TABLE backtest.atomic_entry_benchmark_operations
    DROP CONSTRAINT atomic_benchmark_operation_scope,
    ADD CONSTRAINT atomic_benchmark_operation_scope CHECK (
        (
            attempt_id IS NULL
            AND operation_type IN (
                'SEAL_MATRIX',
                'ACTIVATE_MATRIX_REVISION_2',
                'REGISTER_PREFLIGHT_V2',
                'REGISTER_ELIGIBILITY_AUDIT_V2',
                'ACTIVATE_MATRIX_REVISION_3',
                'REGISTER_PREFLIGHT_V3'
            )
        ) OR (
            attempt_id IS NOT NULL
            AND operation_type IN (
                'START_ATTEMPT', 'TRANSITION_ATTEMPT'
            )
        )
    );

CREATE TABLE backtest.atomic_entry_benchmark_eligibility_audits (
    audit_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    active_matrix_id TEXT NOT NULL,
    active_matrix_revision INTEGER NOT NULL,
    candidate_matrix_revision INTEGER NOT NULL,
    audit_json JSONB NOT NULL,
    audit_digest TEXT NOT NULL UNIQUE,
    candidate_protocol_core_digest TEXT NOT NULL,
    candidate_eligibility_audit_implementation_digest TEXT NOT NULL,
    eligible_symbol_session_ratio TEXT NOT NULL,
    minimum_eligible_symbol_session_ratio TEXT NOT NULL,
    status TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    artifact_locator TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    change_note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (family_id, candidate_matrix_revision),
    CONSTRAINT atomic_benchmark_eligibility_audit_active_revision CHECK (
        active_matrix_revision = 2
    ),
    CONSTRAINT atomic_benchmark_eligibility_audit_candidate_revision CHECK (
        candidate_matrix_revision = 3
    ),
    CONSTRAINT atomic_benchmark_eligibility_audit_sha CHECK (
        audit_digest ~ '^[0-9a-f]{64}$'
        AND candidate_protocol_core_digest ~ '^[0-9a-f]{64}$'
        AND candidate_eligibility_audit_implementation_digest
            ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT atomic_benchmark_eligibility_audit_ratio CHECK (
        eligible_symbol_session_ratio
            ~ '^(0|1)\.[0-9]{18}$'
        AND minimum_eligible_symbol_session_ratio = '0.95'
        AND eligible_symbol_session_ratio::NUMERIC >= 0.95
    ),
    CONSTRAINT atomic_benchmark_eligibility_audit_status CHECK (
        status = 'ACCEPTED'
    ),
    CONSTRAINT atomic_benchmark_eligibility_audit_identity CHECK (
        audit_id = 'r6-eligibility-audit-sha256-' || audit_digest
        AND btrim(artifact_locator) <> ''
        AND btrim(actor_id) <> ''
        AND btrim(change_note) <> ''
    ),
    CONSTRAINT atomic_benchmark_eligibility_audit_matrix_fk
        FOREIGN KEY (
            active_matrix_id, family_id, active_matrix_revision
        ) REFERENCES backtest.atomic_entry_benchmark_matrices (
            matrix_id, family_id, matrix_revision
        ),
    CONSTRAINT atomic_benchmark_eligibility_audit_operation_fk
        FOREIGN KEY (operation_id, family_id, active_matrix_id)
        REFERENCES backtest.atomic_entry_benchmark_operations (
            operation_id, family_id, matrix_id
        )
);

CREATE INDEX atomic_benchmark_eligibility_audit_created_index
    ON backtest.atomic_entry_benchmark_eligibility_audits (
        family_id, created_at DESC
    );
