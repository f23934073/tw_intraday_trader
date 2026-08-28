"""Verify one immutable FinMind selection-provenance bundle offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.finmind_selection_bundle import verify_selection_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline verification for a sealed FinMind selection bundle"
    )
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/finmind_sponsor/history.sqlite3"),
    )
    args = parser.parse_args()
    bundle = args.bundle if args.bundle.is_absolute() else PROJECT_ROOT / args.bundle
    database = (
        args.database
        if args.database.is_absolute()
        else PROJECT_ROOT / args.database
    )
    result = verify_selection_bundle(
        bundle,
        project_root=PROJECT_ROOT,
        database_path=database,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
