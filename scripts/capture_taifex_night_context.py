"""Capture the current as-of TAIFEX night-session Context Artifact once."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import build_provider  # noqa: E402
from config.premarket import PREMARKET_CONTEXT_V0  # noqa: E402
from premarket.artifacts import FilePremarketArtifactRepository  # noqa: E402
from premarket.calendar import TaifexTradingCalendar  # noqa: E402
from premarket.service import PremarketContextService  # noqa: E402
from runtime.clock import SystemClock  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture one current as-of TAIFEX night-session context",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=PREMARKET_CONTEXT_V0.artifact_dir,
        help="Content-addressed premarket evidence directory",
    )
    args = parser.parse_args()

    provider = build_provider()
    try:
        projection = PremarketContextService(
            source=provider,
            calendar=TaifexTradingCalendar.from_path(
                PREMARKET_CONTEXT_V0.calendar_path
            ),
            config=PREMARKET_CONTEXT_V0,
            artifacts=FilePremarketArtifactRepository(args.artifact_dir),
            now=SystemClock().now,
        ).projection()
        print(json.dumps(projection, ensure_ascii=False, indent=2))
        return 0
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
