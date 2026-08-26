"""Create the fresh PR-008 r3 job without reading Snapshot or Kbar payloads."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backtest.application import BacktestApplicationService
from backtest.price_coverage_initialization import (
    PriceCoverageInitializationError,
    assert_no_secret_values,
    build_r3_configuration,
    build_target_manifest,
    git_source_snapshot,
    locked_artifact_store,
    persist_fresh_job_exactly_once,
    prepare_fresh_job,
    targets_from_contract_catalog,
)
from market_data.provider import ShioajiProvider


TAIPEI = ZoneInfo("Asia/Taipei")
PINNED_SOURCE_PATHS = (
    "market_data/provider.py",
    "backtest/historical_download.py",
    "scripts/download_backtest_history.py",
    "backtest/domain.py",
    "backtest/repository.py",
    "backtest/price_coverage_initialization.py",
    "scripts/create_price_coverage_r3_job.py",
)
ACQUISITION_ROOT = PROJECT_ROOT / "research/institutional_evaluation/acquisition"
TARGET_ARTIFACT_NAME = "price_coverage_target_order_v1_2026-08-26-r3.json"
CONFIG_ARTIFACT_NAME = "price_coverage_scan_configuration_v2_2026-08-26-r3.json"


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a metadata-only fresh r3 price-coverage job",
    )
    parser.add_argument("--end-date", required=True, type=_iso_date)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ACQUISITION_ROOT,
    )
    args = parser.parse_args()
    if args.end_date != date(2026, 8, 18):
        parser.error("fresh r3 requires the frozen end date 2026-08-18")
    output_root = Path(os.path.abspath(args.output_dir))
    if output_root != ACQUISITION_ROOT:
        parser.error("fresh r3 artifacts must use the fixed acquisition root")

    os.environ["PROVIDER"] = "shioaji"
    with locked_artifact_store(output_root) as artifact_store:
        source_snapshot = git_source_snapshot(
            root=PROJECT_ROOT,
            source_paths=PINNED_SOURCE_PATHS,
        )
        provider: ShioajiProvider | None = None
        repository = None
        try:
            provider = ShioajiProvider()
            environment_identity = provider.environment_identity
            if environment_identity != "shioaji:1.7.2:simulation=true":
                raise PriceCoverageInitializationError(
                    "Fresh r3 requires shioaji 1.7.2 simulation=true"
                )
            targets = targets_from_contract_catalog(provider)
            prepared = prepare_fresh_job(
                targets=targets,
                provider_environment_identity=environment_identity,
                end_date=args.end_date,
            )
            proposed_at = datetime.now(TAIPEI)
            repository = BacktestApplicationService._build_repository()
            stored_job, created = persist_fresh_job_exactly_once(
                repository=repository,
                prepared=prepared,
                created_at=proposed_at,
            )
            captured_at = datetime.fromisoformat(str(stored_job["created_at"]))
            target_manifest = build_target_manifest(
                prepared=prepared,
                captured_at=captured_at,
                provider_environment_identity=environment_identity,
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
            assert_no_secret_values((target_manifest,), secrets)
            target_digest = artifact_store.publish(
                TARGET_ARTIFACT_NAME,
                target_manifest,
            )
            configuration = build_r3_configuration(
                prepared=prepared,
                stored_job=stored_job,
                registered_at=captured_at,
                target_manifest_digest=target_digest,
                source_snapshot=source_snapshot,
                provider_environment_identity=environment_identity,
            )
            assert_no_secret_values((target_manifest, configuration), secrets)
            configuration_digest = artifact_store.publish(
                CONFIG_ARTIFACT_NAME,
                configuration,
            )
            print(
                json.dumps(
                    {
                        "status": "CREATED" if created else "IDEMPOTENT_REPLAY",
                        "job_id": prepared.job_id,
                        "job_status": stored_job["status"],
                        "target_count": len(prepared.targets),
                        "checkpointed_partition_count": 0,
                        "target_manifest_digest": target_digest,
                        "configuration_digest": configuration_digest,
                        "historical_kbar_requests_issued": False,
                        "scan_authorized": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            close_repository = getattr(repository, "close", None)
            if callable(close_repository):
                close_repository()
            if provider is not None:
                provider.close()


if __name__ == "__main__":
    main()
