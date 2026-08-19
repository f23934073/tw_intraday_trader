"""Capture and reconcile one official TAIFEX after-hours daily report."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.premarket import PREMARKET_CONTEXT_V0  # noqa: E402
from premarket.artifacts import FilePremarketArtifactRepository  # noqa: E402
from premarket.reconciliation import ReconciliationService  # noqa: E402
from premarket.taifex_reconciliation import (  # noqa: E402
    fetch_taifex_daily_report,
    parse_taifex_after_hours_observation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one official TAIFEX after-hours report and write a separate "
            "reconciliation artifact"
        ),
    )
    parser.add_argument(
        "--context-digest",
        required=True,
        help="Exact existing Context Artifact SHA256 digest",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=PREMARKET_CONTEXT_V0.artifact_dir,
        help="Content-addressed premarket evidence directory",
    )
    args = parser.parse_args()

    repository = FilePremarketArtifactRepository(args.artifact_dir)
    contexts = tuple(
        context
        for context in repository.contexts()
        if context.context_digest == args.context_digest
    )
    if len(contexts) != 1:
        parser.error("context digest does not identify exactly one stored artifact")
    context = contexts[0]
    captured_at = datetime.now(ZoneInfo(PREMARKET_CONTEXT_V0.timezone))
    capture = fetch_taifex_daily_report(
        trading_date=context.trading_date,
        product_code="TX",
        retrieved_at=captured_at,
    )
    observation = parse_taifex_after_hours_observation(
        capture,
        context=context,
    )
    artifact = ReconciliationService(repository).reconcile(context, observation)
    print(
        json.dumps(
            asdict(artifact),
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
