"""Provision or render the disabled PR-TM-012C1 external runtime candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.trade_management_external_readiness import (
    ReadinessBlocked,
    provision_owner_only_environment,
    render_disabled_deployment_candidates,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    provision = subparsers.add_parser("provision-environment")
    provision.add_argument("--source", type=Path, required=True)
    provision.add_argument("--target", type=Path, required=True)

    render = subparsers.add_parser("render-deployment")
    render.add_argument("--project-root", type=Path, required=True)
    render.add_argument("--environment-file", type=Path, required=True)
    render.add_argument("--artifact-root", type=Path, required=True)
    render.add_argument("--records-root", type=Path, required=True)
    render.add_argument("--ownership-lock-root", type=Path, required=True)
    render.add_argument("--tmp-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "provision-environment":
            result = provision_owner_only_environment(
                source=args.source,
                target=args.target,
            )
        else:
            result = render_disabled_deployment_candidates(
                project_root=args.project_root,
                environment_file=args.environment_file,
                artifact_root=args.artifact_root,
                records_root=args.records_root,
                ownership_lock_root=args.ownership_lock_root,
                tmp_root=args.tmp_root,
            )
    except ReadinessBlocked as error:
        print(json.dumps({"status": "BLOCKED", "reason_code": error.code}))
        return 2
    print(
        json.dumps(
            {"status": "READINESS_STEP_COMPLETE", **result},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
