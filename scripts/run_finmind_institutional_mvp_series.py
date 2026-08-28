"""Freeze and execute a 60-session FinMind institutional candidate series."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.dataset_binding import canonical_registration_manifest  # noqa: E402
from config import twse_calendar_2026  # noqa: E402
from config.institutional_mvp import (  # noqa: E402
    ACQUISITION_LOCK_PATH,
    CALENDAR_SCOPE,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PRICE_DATASET_MANIFEST,
    DEFAULT_PRICE_DATASET_PLAN,
    EXPECTED_BASE_POLICY_DIGEST,
    EXPECTED_CALENDAR_SCHEMA_VERSION,
    EXPECTED_CALENDAR_SOURCE_DIGEST,
    EXPECTED_CALENDAR_TIMEZONE,
    MINIMUM_REMAINING_AFTER_BATCH,
    load_daily_policy,
)
from institutional_data.serialization import canonical_json, sha256_text  # noqa: E402
from institutional_mvp.application import DailyInstitutionalMvpService  # noqa: E402
from institutional_mvp.artifacts import (  # noqa: E402
    DirectoryInstitutionalMvpCandidateBatchRepository,
    InstitutionalMvpArtifactError,
)
from institutional_mvp.domain import (  # noqa: E402
    InstitutionalMvpDailyPolicy,
    InstitutionalMvpDailyError,
    InstitutionalMvpSourceNotReady,
)
from institutional_mvp.finmind_adapter import FinMindInstitutionalFlowProvider  # noqa: E402
from institutional_mvp.series import (  # noqa: E402
    MINIMUM_OVERLAPPING_TARGET_SESSIONS,
    InstitutionalMvpSeriesError,
    build_candidate_series_manifest,
    build_candidate_series_plan,
    dataset_reference,
    load_canonical_artifact,
    publish_content_addressed_json,
    verify_candidate_series_manifest,
    verify_candidate_series_plan,
)
from market_data.equity_calendar import ReviewedEquityCalendar  # noqa: E402


DEFAULT_TARGET_END = date(2026, 8, 18)
TEMPORARY_CODES = {
    "PROVIDER_PREFLIGHT_FAILED",
    "PROVIDER_QUOTA_INSUFFICIENT",
    "PROVIDER_QUOTA_REACHED",
    "PROVIDER_REQUEST_FAILED",
    "SOURCE_NOT_READY",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser(
        "plan", help="Freeze session identities without any provider request"
    )
    _add_metadata_arguments(plan_parser)
    plan_parser.add_argument(
        "--target-end", type=_iso_date, required=True, help="Final target session"
    )
    plan_parser.add_argument(
        "--session-count",
        type=int,
        default=MINIMUM_OVERLAPPING_TARGET_SESSIONS,
    )

    execute_parser = subparsers.add_parser(
        "execute", help="Acquire only the sessions pinned by one exact plan"
    )
    _add_metadata_arguments(execute_parser)
    execute_parser.add_argument("--plan-file", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        policy = load_daily_policy()
        calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
        price_reference = load_price_dataset_reference(
            manifest_path=args.dataset_manifest,
            dataset_plan_path=args.dataset_plan,
        )
        if args.command == "plan":
            plan = build_candidate_series_plan(
                calendar=calendar,
                policy=policy,
                price_dataset_reference=price_reference,
                target_end=args.target_end,
                session_count=args.session_count,
            )
            path, created = publish_content_addressed_json(
                args.output_root, category="plans", payload=plan
            )
            print(
                f"status={'PUBLISHED' if created else 'IDEMPOTENT_REPLAY'} "
                f"artifact_id={plan['artifact_id']} digest={plan['artifact_digest']} "
                f"session_count={plan['planned_session_count']} "
                f"first_target={plan['session_pairs'][0]['target_session']} "
                f"last_target={plan['session_pairs'][-1]['target_session']} path={path}"
            )
            return 0

        plan = load_canonical_artifact(args.plan_file)
        pairs = verify_candidate_series_plan(
            plan,
            calendar=calendar,
            policy=policy,
            price_dataset_reference=price_reference,
        )
        return _execute_series(
            plan=plan,
            pairs=pairs,
            output_root=args.output_root,
            calendar=calendar,
            policy=policy,
        )
    except (InstitutionalMvpArtifactError, InstitutionalMvpSeriesError, OSError, RuntimeError, ValueError) as error:
        print(
            f"ERROR code=INSTITUTIONAL_SERIES_FAILED type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1


def _execute_series(
    *,
    plan: Mapping[str, object],
    pairs: Sequence[tuple[date, date]],
    output_root: Path,
    calendar: ReviewedEquityCalendar,
    policy: InstitutionalMvpDailyPolicy,
) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.environ.get("FINMIND_API_TOKEN", "").strip()
    if not token:
        print("ERROR code=FINMIND_API_TOKEN_MISSING", file=sys.stderr)
        return 2
    repository = DirectoryInstitutionalMvpCandidateBatchRepository(
        output_root,
        calendar=calendar,
        expected_policy_digest=policy.canonical_sha256,
        expected_base_policy_digest=EXPECTED_BASE_POLICY_DIGEST,
        expected_calendar_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
    )
    service = DailyInstitutionalMvpService(
        provider=FinMindInstitutionalFlowProvider(
            token,
            minimum_remaining_after_batch=MINIMUM_REMAINING_AFTER_BATCH,
            acquisition_lock_path=ACQUISITION_LOCK_PATH,
        ),
        repository=repository,
        calendar=calendar,
        policy=policy,
        expected_calendar_schema_version=EXPECTED_CALENDAR_SCHEMA_VERSION,
        expected_calendar_timezone=EXPECTED_CALENDAR_TIMEZONE,
        expected_calendar_source_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        calendar_scope=CALENDAR_SCOPE,
    )
    batches: list[Mapping[str, object]] = []
    for source_session, target_session in pairs:
        try:
            batch = repository.get_by_target_session(target_session)
            if batch is None:
                publication = service.run(source_session)
                batch = repository.get_by_digest(
                    target_session=target_session,
                    artifact_digest=publication.artifact_digest,
                )
                if batch is None:
                    raise InstitutionalMvpSeriesError(
                        "published batch could not be replayed by exact digest"
                    )
            elif batch.get("source_session") != source_session.isoformat():
                raise InstitutionalMvpSeriesError(
                    "existing target-session batch differs from frozen plan"
                )
            batches.append(batch)
        except InstitutionalMvpSourceNotReady as error:
            print(
                f"WAIT code={error.code} source_session={source_session.isoformat()} "
                f"completed_batches={len(batches)}"
            )
            return 75
        except InstitutionalMvpDailyError as error:
            prefix = "WAIT" if error.code in TEMPORARY_CODES else "ERROR"
            stream = sys.stdout if prefix == "WAIT" else sys.stderr
            print(
                f"{prefix} code={error.code} source_session={source_session.isoformat()} "
                f"completed_batches={len(batches)}",
                file=stream,
            )
            return 75 if prefix == "WAIT" else 1

    series = build_candidate_series_manifest(
        plan=plan,
        batches=batches,
        calendar=calendar,
        policy=policy,
    )
    verify_candidate_series_manifest(
        series,
        plan=plan,
        batches=batches,
        calendar=calendar,
        policy=policy,
    )
    path, created = publish_content_addressed_json(
        output_root, category="series", payload=series
    )
    print(
        f"status={'PUBLISHED' if created else 'IDEMPOTENT_REPLAY'} "
        f"artifact_id={series['artifact_id']} digest={series['artifact_digest']} "
        f"overlapping_target_sessions={series['overlapping_target_session_count']} "
        f"path={path}"
    )
    return 0


def _add_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--dataset-manifest", type=Path, default=DEFAULT_PRICE_DATASET_MANIFEST
    )
    parser.add_argument("--dataset-plan", type=Path, default=DEFAULT_PRICE_DATASET_PLAN)


def load_price_dataset_reference(
    *, manifest_path: Path, dataset_plan_path: Path
) -> dict[str, object]:
    manifest_raw = json.loads(manifest_path.read_bytes())
    if not isinstance(manifest_raw, Mapping):
        raise ValueError("Dataset manifest must be one object")
    manifest = canonical_registration_manifest(manifest_raw)
    plan_raw = json.loads(dataset_plan_path.read_bytes())
    if not isinstance(plan_raw, Mapping):
        raise ValueError("Dataset plan must be one object")
    if plan_raw.get("schema_version") != "finmind-backtest-snapshot-plan-v1":
        raise ValueError("Dataset plan schema drifted")
    identity = plan_raw.get("identity")
    selection = plan_raw.get("selection_audit")
    if not isinstance(identity, Mapping) or not isinstance(selection, Mapping):
        raise ValueError("Dataset plan identity or selection audit is invalid")
    plan_identity_digest = str(plan_raw.get("plan_identity_digest") or "")
    selection_audit_digest = str(plan_raw.get("selection_audit_digest") or "")
    if sha256_text(canonical_json(identity)) != plan_identity_digest:
        raise ValueError("Dataset plan identity digest drifted")
    if sha256_text(canonical_json(selection)) != selection_audit_digest:
        raise ValueError("Dataset selection audit digest drifted")
    if manifest.get("plan_identity") != dict(identity):
        raise ValueError("Dataset manifest and plan identity differ")
    if manifest.get("plan_identity_digest") != plan_identity_digest:
        raise ValueError("Dataset manifest plan digest drifted")
    return dataset_reference(
        manifest, selection_audit_digest=selection_audit_digest
    )


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


if __name__ == "__main__":
    raise SystemExit(main())
