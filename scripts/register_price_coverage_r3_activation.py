"""Publish reviewed fresh-r3 scan authority without constructing a provider."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backtest.price_coverage_activation import (
    ACTIVATION_ARTIFACT_NAME,
    PINNED_ACTIVATION_SOURCE_PATHS,
    QUARANTINE_ARTIFACT_NAME,
    QUARANTINE_DIGEST,
    TARGET_ARTIFACT_NAME,
    TARGET_DIGEST,
    build_price_coverage_activation,
)
from backtest.price_coverage_initialization import (
    PriceCoverageInitializationError,
    assert_no_secret_values,
    git_source_snapshot,
    locked_artifact_store,
)
from backtest.price_coverage_repository import build_price_coverage_repository


ACQUISITION_ROOT = PROJECT_ROOT / "research/institutional_evaluation/acquisition"


def _authorized_at(value: str) -> datetime:
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("authorized-at must be ISO-8601") from error
    if resolved.utcoffset() != timedelta(hours=8):
        raise argparse.ArgumentTypeError("authorized-at must use Asia/Taipei offset")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish immutable authority for the dedicated fresh-r3 raw scan",
    )
    parser.add_argument(
        "--authorize-scan",
        action="store_true",
        help="Explicitly authorize historical Kbar coverage acquisition only",
    )
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorized-at", required=True, type=_authorized_at)
    args = parser.parse_args()
    if not args.authorize_scan:
        parser.error("--authorize-scan is required; registration is fail closed")

    repository = None
    with locked_artifact_store(ACQUISITION_ROOT) as store:
        target = store.load(TARGET_ARTIFACT_NAME)
        quarantine = store.load(QUARANTINE_ARTIFACT_NAME)
        if store.publish(TARGET_ARTIFACT_NAME, target) != TARGET_DIGEST:
            raise PriceCoverageInitializationError("r3 target manifest drifted")
        if store.publish(QUARANTINE_ARTIFACT_NAME, quarantine) != QUARANTINE_DIGEST:
            raise PriceCoverageInitializationError("r3 quarantine revision drifted")
        source_snapshot = git_source_snapshot(
            root=PROJECT_ROOT,
            source_paths=PINNED_ACTIVATION_SOURCE_PATHS,
        )
        try:
            repository = build_price_coverage_repository()
            job = repository.get_job(
                "dataset-download-r3-e9981217a1d36c213e121db3ebaa26e7"
            )
            if repository.list_history_partitions(job["job_id"]):
                raise PriceCoverageInitializationError(
                    "r3 activation registration requires zero existing partitions"
                )
            try:
                repository.get_dataset(job["request"]["target_dataset_id"])
            except KeyError:
                pass
            else:
                raise PriceCoverageInitializationError(
                    "r3 activation registration found an existing target Dataset"
                )
            activation = build_price_coverage_activation(
                job=job,
                source_snapshot=source_snapshot,
                authorized_at=args.authorized_at,
                authorized_by=args.authorized_by,
            )
            secrets = tuple(
                os.environ.get(name, "")
                for name in (
                    "SHIOAJI_API_KEY",
                    "SHIOAJI_SECRET",
                    "SJ_API_KEY",
                    "SJ_SECRET_KEY",
                    "SJ_SEC_KEY",
                )
            )
            assert_no_secret_values((target, quarantine, activation), secrets)
            activation_digest = store.publish(
                ACTIVATION_ARTIFACT_NAME,
                activation,
            )
        finally:
            close = getattr(repository, "close", None)
            if callable(close):
                close()
    print(
        json.dumps(
            {
                "status": "ACTIVATION_AUTHORITY_PUBLISHED",
                "activation_artifact": ACTIVATION_ARTIFACT_NAME,
                "activation_digest": activation_digest,
                "job_mutated": False,
                "provider_built": False,
                "historical_kbar_requests_issued": False,
                "dataset_materialization_allowed": False,
                "outcome_generation_allowed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
