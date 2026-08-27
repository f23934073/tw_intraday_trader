"""Build one immutable FinMind institutional MVP batch for an explicit session."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import twse_calendar_2026  # noqa: E402
from config.institutional_mvp import (  # noqa: E402
    ACQUISITION_LOCK_PATH,
    CALENDAR_SCOPE,
    DEFAULT_OUTPUT_ROOT,
    EXPECTED_BASE_POLICY_DIGEST,
    EXPECTED_CALENDAR_SCHEMA_VERSION,
    EXPECTED_CALENDAR_SOURCE_DIGEST,
    EXPECTED_CALENDAR_TIMEZONE,
    MINIMUM_REMAINING_AFTER_BATCH,
    load_daily_policy,
)
from institutional_mvp.application import DailyInstitutionalMvpService  # noqa: E402
from institutional_mvp.artifacts import (  # noqa: E402
    DirectoryInstitutionalMvpCandidateBatchRepository,
    InstitutionalMvpArtifactError,
)
from institutional_mvp.domain import (  # noqa: E402
    InstitutionalMvpDailyError,
    InstitutionalMvpSourceNotReady,
)
from institutional_mvp.finmind_adapter import (  # noqa: E402
    FinMindInstitutionalFlowProvider,
)
from market_data.equity_calendar import ReviewedEquityCalendar  # noqa: E402


TEMPORARY_CODES = {
    "PROVIDER_PREFLIGHT_FAILED",
    "PROVIDER_QUOTA_INSUFFICIENT",
    "PROVIDER_QUOTA_REACHED",
    "PROVIDER_REQUEST_FAILED",
    "SOURCE_NOT_READY",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-session",
        required=True,
        type=_iso_date,
        help="Explicit post-close institutional source session (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Append-only candidate batch repository root",
    )
    args = parser.parse_args(argv)

    load_dotenv(PROJECT_ROOT / ".env")
    token = os.environ.get("FINMIND_API_TOKEN", "").strip()
    if not token:
        print("ERROR code=FINMIND_API_TOKEN_MISSING", file=sys.stderr)
        return 2

    try:
        policy = load_daily_policy()
        calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
        service = DailyInstitutionalMvpService(
            provider=FinMindInstitutionalFlowProvider(
                token,
                minimum_remaining_after_batch=MINIMUM_REMAINING_AFTER_BATCH,
                acquisition_lock_path=ACQUISITION_LOCK_PATH,
            ),
            repository=DirectoryInstitutionalMvpCandidateBatchRepository(
                args.output_root,
                calendar=calendar,
                expected_policy_digest=policy.canonical_sha256,
                expected_base_policy_digest=EXPECTED_BASE_POLICY_DIGEST,
                expected_calendar_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
            ),
            calendar=calendar,
            policy=policy,
            expected_calendar_schema_version=EXPECTED_CALENDAR_SCHEMA_VERSION,
            expected_calendar_timezone=EXPECTED_CALENDAR_TIMEZONE,
            expected_calendar_source_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
            calendar_scope=CALENDAR_SCOPE,
        )
        publication = service.run(args.source_session)
    except InstitutionalMvpSourceNotReady as error:
        print(f"WAIT code={error.code} source_session={args.source_session}")
        return 75
    except InstitutionalMvpDailyError as error:
        prefix = "WAIT" if error.code in TEMPORARY_CODES else "ERROR"
        stream = sys.stdout if prefix == "WAIT" else sys.stderr
        print(
            f"{prefix} code={error.code} source_session={args.source_session}",
            file=stream,
        )
        return 75 if prefix == "WAIT" else 1
    except (InstitutionalMvpArtifactError, OSError, RuntimeError, ValueError) as error:
        print(
            f"ERROR code=DAILY_BATCH_FAILED type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    print(
        f"status={publication.status.value} "
        f"source_session={publication.source_session.isoformat()} "
        f"target_session={publication.target_session.isoformat()} "
        f"artifact_id={publication.artifact_id} "
        f"digest={publication.artifact_digest} "
        f"path={publication.path}"
    )
    return 0


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("source session must be YYYY-MM-DD") from error


if __name__ == "__main__":
    raise SystemExit(main())
