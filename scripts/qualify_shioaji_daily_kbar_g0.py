"""Re-evaluate existing G0 Shioaji Kbar fixtures without network or SDK access."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from market_data.daily_kbar_qualification import (
    qualify_daily_kbar_source,
    read_json,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay daily-Kbar G0 qualification")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=PROJECT_ROOT / "research" / "daily_kbar_g0",
    )
    args = parser.parse_args()
    root: Path = args.artifact_dir
    fixtures = root / "fixtures"
    existing_resolution = read_json(root / "qualification" / "session_resolution.json")
    contract = existing_resolution.get("session_contract")
    if not isinstance(contract, dict):
        raise ValueError("session_resolution.json does not contain a session contract")
    reconciliation_path = root / "qualification" / "twse_daily_reconciliation.json"
    reconciliation = read_json(reconciliation_path) if reconciliation_path.exists() else None
    reports = qualify_daily_kbar_source(
        daily_capture=read_json(fixtures / "shioaji_daily_sample.json"),
        full_session_capture=read_json(fixtures / "shioaji_intraday_full_session_sample.json"),
        partial_session_capture=read_json(fixtures / "shioaji_partial_session_sample.json"),
        chunk_boundary_capture=read_json(fixtures / "shioaji_chunk_boundary_sample.json"),
        session_contract=contract,
        now=datetime.now(ZoneInfo("Asia/Taipei")),
        completion_reconciliation=reconciliation,
    )
    output = root / "qualification"
    for name, report in reports.items():
        write_json(output / f"{name}.json", report)
    print(
        f"G0 qualification replayed: {root}; selected_path="
        f"{reports['qualification_result']['selected_path']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
