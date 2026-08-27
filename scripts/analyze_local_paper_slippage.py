"""Seal and analyze Local Paper model-stress evidence without live access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.slippage_calibration import (
    CalibrationContractError,
    seal_clock_disposition,
    seal_fill_export,
    seal_input_manifest,
    write_analysis_report_once,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "只讀既有 canonical evidence，產出 Local Paper model-stress proxy；"
            "不連線券商、不代表真實成交滑價"
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    seal_input = commands.add_parser("seal-input", help="封存 checksummed input manifest")
    seal_input.add_argument("--draft", type=Path, required=True)
    seal_input.add_argument("--output", type=Path, required=True)

    seal_clock = commands.add_parser(
        "seal-clock-disposition",
        help="封存 reviewer-approved timestamp comparability disposition",
    )
    seal_clock.add_argument("--draft", type=Path, required=True)
    seal_clock.add_argument("--output", type=Path, required=True)

    seal_fill = commands.add_parser(
        "seal-fill-export",
        help="驗證並封存既有 local_paper_fill.v3 Journal export",
    )
    seal_fill.add_argument("--draft", type=Path, required=True)
    seal_fill.add_argument("--output", type=Path, required=True)

    analyze = commands.add_parser("analyze", help="執行 deterministic offline analysis")
    analyze.add_argument("--manifest", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "seal-input":
            artifact = seal_input_manifest(args.draft, args.output)
        elif args.command == "seal-clock-disposition":
            artifact = seal_clock_disposition(args.draft, args.output)
        elif args.command == "seal-fill-export":
            artifact = seal_fill_export(args.draft, args.output)
        else:
            artifact = write_analysis_report_once(args.manifest, args.output)
    except (CalibrationContractError, FileExistsError, OSError, ValueError) as error:
        print(
            json.dumps(
                {"status": "FAILED", "error": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "SEALED",
                "schema_version": artifact["schema_version"],
                "content_sha256": artifact["content_sha256"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
