"""Freeze the D-HEALTH-LATE-001 campaign cohort from official TWSE quotes."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from market_data.late_delivery_cohort import (
    build_late_delivery_cohort,
    fetch_twse_daily_quotes,
    write_frozen_cohort,
)
from market_data.late_delivery_evidence import LateDeliveryCohort


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create one immutable 7-symbol passive late-delivery cohort from "
            "a completed official TWSE daily-quotes source."
        )
    )
    parser.add_argument("--source-date", required=True, type=_date)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--source-json",
        type=Path,
        help="Previously captured official TWSE MI_INDEX JSON; skips network retrieval.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.source_json is None:
            raw_bytes, source_identity = fetch_twse_daily_quotes(args.source_date)
        else:
            raw_bytes = args.source_json.read_bytes()
            source_identity = f"file:{args.source_json.name}"
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict):
            raise ValueError("official quote source root must be an object")
        manifest = build_late_delivery_cohort(
            raw_response=raw,
            source_date=args.source_date,
            source_identity=source_identity,
        )
        cohort = LateDeliveryCohort.from_mapping(manifest)
        output = write_frozen_cohort(args.output, manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("late_delivery_cohort: FAILED")
        print(f"reason: {type(error).__name__}:{error}")
        return 2
    print("late_delivery_cohort: PASS")
    print(f"cohort: {output}")
    print(f"symbols: {','.join(cohort.symbols)}")
    print(f"manifest_sha256: {cohort.manifest_digest}")
    print("selection: fixed_high=2330,2317,2454 + deterministic_mid_low_from_completed_TWSE")
    return 0


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("source date must be YYYY-MM-DD") from error


if __name__ == "__main__":
    raise SystemExit(main())
