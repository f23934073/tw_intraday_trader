"""Seal the already-created Phase 82 status-only job's offline provenance."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.domain import canonical_json  # noqa: E402
from backtest.finmind_selection_bundle import build_selection_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build one content-addressed Phase 82 selection bundle offline"
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/finmind_sponsor/history.sqlite3"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/finmind_sponsor/universes/selections"),
    )
    args = parser.parse_args()
    database = args.database if args.database.is_absolute() else PROJECT_ROOT / args.database
    output_dir = (
        args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    )
    bundle = build_selection_bundle(
        project_root=PROJECT_ROOT,
        database_path=database,
        stock_info_path=PROJECT_ROOT
        / "data/finmind_sponsor/universes/raw/"
        "TaiwanStockInfo_0353f33f0b2f36a12bf0c9d30a802423352ba460f6e113012e7ff5f32b5315ad.json.gz",
        market_value_path=PROJECT_ROOT
        / "data/finmind_sponsor/universes/raw/"
        "TaiwanStockMarketValue_06d1b32269d379e4eabcfade1b51ee94a4df56bf4ec9a8f9769f63f8962532b2.json.gz",
        twse_path=PROJECT_ROOT
        / "data/finmind_sponsor/universes/official/twse/"
        "company_efdb1688c5683a6574c84ec93af90e95715f0d454ca2a6daaab584f776272f69.json",
        tpex_path=PROJECT_ROOT
        / "data/finmind_sponsor/universes/official/tpex/"
        "company_4f055c3c035d84c75b299211f36ef2dbe01b700c58c2115aeb6630c7628ce835.json",
        dataset_manifest_path=PROJECT_ROOT
        / "data/backtest/"
        "dataset-finmind-sponsor-sha256-4defb3967d4e89f87d920197877358a8237cdf9baa51be1001fb156b70310ce4/"
        "manifest.json",
        snapshot_plan_path=PROJECT_ROOT
        / "data/backtest/finmind_plans/repair_9960_20260827_v1/snapshot-plan.json",
        target_job_id="finmind-sponsor-3fb900f8f272077e",
        window_start=date(2023, 8, 19),
        window_end=date(2026, 8, 18),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"phase82_selection_{bundle['bundle_digest']}.json"
    with output.open("x", encoding="utf-8") as handle:
        handle.write(canonical_json(bundle))
        handle.write("\n")
    print(
        json.dumps(
            {
                "bundle_digest": bundle["bundle_digest"],
                "path": output.relative_to(PROJECT_ROOT).as_posix(),
                "status": "SEALED",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
