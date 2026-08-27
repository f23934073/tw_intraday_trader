#!/usr/bin/env python3
"""Verify the accepted A2 audit and apply schema-only Migration 018."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.atomic_benchmark.application import (
    AtomicBenchmarkApplicationService,
    amendment_a2_protocol_core,
)
from backtest.atomic_benchmark.domain import FAMILY_ID, canonical_object_bytes
from backtest.atomic_benchmark.postgres_repository import (
    AtomicBenchmarkPostgresRepository,
)
from backtest.atomic_benchmark.preflight import (
    MINIMUM_ELIGIBLE_RATIO,
    eligibility_audit_implementation_digest,
    verify_eligibility_audit,
)
from backtest.domain import digest
from backtest.migrations import apply_migrations, migration_files


MIGRATION = "018_r6_dynamic_entry_reserve.sql"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--family-id", default=FAMILY_ID)
    parser.add_argument("--audit-path", type=Path, required=True)
    return parser


def _audit_scope(
    *, context: Mapping[str, Any], repository_root: Path
) -> dict[str, object]:
    return {
        "family_id": context["family_id"],
        "active_matrix_id": context["matrix_id"],
        "active_matrix_revision": context["matrix_revision"],
        "active_matrix_registration_digest": context["registration_digest"],
        "active_protocol_core_digest": context["protocol_core_digest"],
        "active_benchmark_build_binding_digest": digest(
            context["benchmark_build_binding"]
        ),
        "research_baseline_digest": context["research_baseline_digest"],
        "dataset_binding_revision": context["research_baseline"][
            "dataset_binding_revision"
        ],
        "family_head_sequence": context["family_head_sequence"],
        "attempt_count": context["attempt_count"],
        "candidate_protocol_core_digest": digest(amendment_a2_protocol_core()),
        "candidate_eligibility_audit_implementation_digest": (
            eligibility_audit_implementation_digest(repository_root)
        ),
    }


def _load_accepted_audit(
    *,
    path: Path,
    context: Mapping[str, Any],
    repository_root: Path,
) -> dict[str, object]:
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("R6 Migration 018 audit artifact cannot parse") from error
    if not isinstance(parsed, Mapping):
        raise RuntimeError("R6 Migration 018 audit artifact is not an object")
    audit = verify_eligibility_audit(
        parsed,
        expected_scope=_audit_scope(
            context=context,
            repository_root=repository_root,
        ),
    )
    if (
        path.is_symlink()
        or not path.is_file()
        or raw != canonical_object_bytes(audit)
        or path.stem != audit["audit_digest"]
        or audit["dataset_id"] != context["registered_manifest"]["dataset_id"]
        or audit["dataset_digest"]
        != context["registered_manifest"]["manifest_digest"]
        or audit["dataset_bars_sha256"]
        != context["registered_manifest"]["bars_sha256"]
        or audit["dataset_bar_count"]
        != context["registered_manifest"]["bar_count"]
        or Decimal(str(audit["eligible_symbol_session_ratio"]))
        < MINIMUM_ELIGIBLE_RATIO
    ):
        raise RuntimeError("R6 Migration 018 audit authority conflict")
    return audit


def _verify_post_migration(connection: Any, family_id: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT active_matrix_revision, head_sequence, release_state,
                   (SELECT COUNT(*)
                      FROM backtest.atomic_entry_benchmark_attempts
                     WHERE family_id = family.family_id) AS attempt_count,
                   (SELECT COUNT(*)
                      FROM backtest.atomic_entry_benchmark_matrices
                     WHERE family_id = family.family_id
                       AND matrix_revision = 3) AS revision3_count
            FROM backtest.atomic_entry_benchmark_families AS family
            WHERE family_id = %s
            """,
            (family_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT to_regclass(
                'backtest.atomic_entry_benchmark_eligibility_audits'
            ) IS NOT NULL
            """
        )
        audit_table = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM backtest.atomic_entry_benchmark_eligibility_audits
            WHERE family_id = %s
            """,
            (family_id,),
        )
        audit_registration_count = int(cursor.fetchone()[0])
    if row is None or (
        int(row[0]) != 2
        or int(row[1]) != 0
        or str(row[2]) != "NOT_READY"
        or int(row[3]) != 0
        or int(row[4]) != 0
        or audit_table is not True
        or audit_registration_count != 0
    ):
        raise RuntimeError("R6 Migration 018 postcondition conflict")
    return {
        "active_matrix_revision": int(row[0]),
        "family_head_sequence": int(row[1]),
        "release_state": str(row[2]),
        "formal_attempts_created": int(row[3]),
        "revision3_matrix_count": int(row[4]),
        "audit_registration_count": audit_registration_count,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R6 Migration 018 requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error
    repository_root = Path(__file__).resolve().parents[1]
    if migration_files()[-1].name != MIGRATION:
        raise RuntimeError("R6 Migration 018 is not the latest forward migration")
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        context = AtomicBenchmarkApplicationService(
            AtomicBenchmarkPostgresRepository(connection, apply_schema=False)
        ).get_preflight_context(arguments.family_id)
        audit = _load_accepted_audit(
            path=arguments.audit_path.resolve(),
            context=context,
            repository_root=repository_root,
        )
        preview = {
            "executed": False,
            "migration": MIGRATION,
            "family_id": arguments.family_id,
            "audit_digest": audit["audit_digest"],
            "coverage": audit["eligible_symbol_session_ratio"],
            "active_matrix_revision": context["matrix_revision"],
            "formal_attempts_created": context["attempt_count"],
        }
        if not arguments.execute:
            print(json.dumps(preview, sort_keys=True))
            return 0
        applied = apply_migrations(connection)
        if applied not in {(MIGRATION,), ()}:
            raise RuntimeError("R6 Migration 018 unexpected migration set")
        postcondition = _verify_post_migration(connection, arguments.family_id)
    print(
        json.dumps(
            {
                **preview,
                **postcondition,
                "executed": True,
                "migration_applied": MIGRATION in applied,
                "migration_replayed": not applied,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
