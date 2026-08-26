"""Run only the activation-bound fresh-r3 raw historical coverage scan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from backtest.dataset import HistoricalDatasetCatalog
from backtest.historical_download import (
    HistoricalDownloadPaused,
    ResumableHistoricalDownloader,
)
from backtest.price_coverage_activation import (
    ACTIVATION_ARTIFACT_NAME,
    QUARANTINE_ARTIFACT_NAME,
    TARGET_ARTIFACT_NAME,
    PriceCoverageActivationError,
    verify_price_coverage_activation,
)
from backtest.price_coverage_initialization import locked_artifact_store
from backtest.price_coverage_repository import build_price_coverage_repository
from config import backtest as backtest_settings
from market_data.provider import ShioajiProvider


ACQUISITION_ROOT = PROJECT_ROOT / "research/institutional_evaluation/acquisition"


def _activation_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("activation digest must be lowercase SHA-256")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the dedicated fresh-r3 raw coverage scan",
    )
    parser.add_argument("--activation-digest", required=True, type=_activation_digest)
    args = parser.parse_args()

    try:
        with locked_artifact_store(ACQUISITION_ROOT) as store:
            repository = None
            provider: ShioajiProvider | None = None
            try:
                target = store.load(TARGET_ARTIFACT_NAME)
                quarantine = store.load(QUARANTINE_ARTIFACT_NAME)
                activation = store.load(ACTIVATION_ARTIFACT_NAME)
                repository = build_price_coverage_repository()
                verified = verify_price_coverage_activation(
                    activation=activation,
                    activation_digest=args.activation_digest,
                    target_manifest=target,
                    quarantine_revision=quarantine,
                    repository=repository,
                    source_root=PROJECT_ROOT,
                )
                job, _replayed = repository.activate_price_coverage_scan_job(
                    verified.job_id,
                    expected_request_digest=verified.request_digest,
                    activation_digest=verified.activation_digest,
                )
                if job["status"] == "SCAN_COMPLETE":
                    raise PriceCoverageActivationError(
                        "raw scan is already complete; use the metadata inventory gate"
                    )
                os.environ["PROVIDER"] = "shioaji"
                provider = ShioajiProvider()
                if (
                    provider.environment_identity
                    != verified.provider_environment_identity
                ):
                    raise PriceCoverageActivationError(
                        "runtime Shioaji environment does not match activation evidence"
                    )
                catalog = HistoricalDatasetCatalog(backtest_settings.BACKTEST_DATA_DIR)
                downloader = ResumableHistoricalDownloader(
                    provider=provider,
                    repository=repository,
                    catalog=catalog,
                    report=lambda message: print(message, flush=True),
                    coverage_scan_mode=True,
                )
                summary = downloader.run_price_coverage_scan(
                    verified.job_id,
                    activation_digest=verified.activation_digest,
                )
                print(
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                    flush=True,
                )
            finally:
                if provider is not None:
                    provider.close()
                close = getattr(repository, "close", None)
                if callable(close):
                    close()
    except HistoricalDownloadPaused as error:
        print(f"raw coverage scan safely paused: {error}", file=sys.stderr, flush=True)
        raise SystemExit(75)


if __name__ == "__main__":
    main()
