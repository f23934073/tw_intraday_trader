#!/usr/bin/env python3
"""Strictly validate and print sealed no-overnight evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading.no_overnight_evidence import (
    read_no_overnight_campaign_bundle,
    read_no_overnight_campaign_report,
    read_no_overnight_drill_evidence,
    read_no_overnight_parameter_review,
    read_no_overnight_session_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=(
            "session",
            "parameter-review",
            "drill",
            "campaign",
            "bundle",
        ),
    )
    parser.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reader = {
        "session": read_no_overnight_session_report,
        "parameter-review": read_no_overnight_parameter_review,
        "drill": read_no_overnight_drill_evidence,
        "campaign": read_no_overnight_campaign_report,
        "bundle": read_no_overnight_campaign_bundle,
    }[args.kind]
    artifact = reader(args.path)
    print(
        json.dumps(
            artifact.payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
