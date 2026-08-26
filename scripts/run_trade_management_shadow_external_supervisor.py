"""Run the approved external PR-TM-012C1 control plane without retries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.trade_management_external_adapters import (
    LocalSupervisorAdapter,
    load_approved_execution_spec,
)
from runtime.trade_management_external_supervisor import (
    SupervisorBlocked,
    SupervisorStatus,
    run_supervisor,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approval-spec",
        type=Path,
        required=True,
        help="Immutable independently approved execution spec and digest sidecar.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        spec, approved_files = load_approved_execution_spec(args.approval_spec)
        adapter = LocalSupervisorAdapter(
            spec_path=args.approval_spec,
            spec=spec,
            approved_files=approved_files,
        )
        market_date = adapter.now().date()
        disposition = run_supervisor(
            spec=spec,
            market_date=market_date,
            ports=adapter,
        )
    except Exception as error:
        reason_code = (
            error.code
            if isinstance(error, SupervisorBlocked)
            else type(error).__name__.upper()
        )
        print(
            json.dumps(
                {
                    "status": SupervisorStatus.BLOCKED.value,
                    "reason_code": reason_code,
                    "execution_authority": False,
                    "execution_enabled": False,
                    "evidence_only": True,
                    "production_shadow_gate": "NOT_PASSED",
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": disposition["status"],
                "reason_code": disposition["reason_code"],
                "market_date": disposition["market_date"],
                "session_id": disposition["session_id"],
                "artifact": disposition["publication"]["artifact"],
                "digest": disposition["publication"]["digest"],
                "production_shadow_gate": "NOT_PASSED",
            },
            sort_keys=True,
        )
    )
    return (
        0
        if disposition["status"]
        in {
            SupervisorStatus.C1_TERMINAL.value,
            SupervisorStatus.SKIPPED_CLOSED_DATE.value,
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
