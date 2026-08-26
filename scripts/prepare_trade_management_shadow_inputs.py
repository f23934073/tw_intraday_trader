"""Prepare an immutable, non-canonical C1 input packet for human review."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import twse_calendar_2026
from market_data.equity_calendar import ReviewedEquityCalendar
from runtime.trade_management_artifact_io import (
    write_json_digest_pair_exclusive,
)
from runtime.trade_management_input_review import (
    REVIEW_PACKET_VERSION,
    canonical_digest,
    require_attempt_id,
    require_review_packet_path,
    sha256_bytes,
    validate_candidate_bytes,
)
from runtime.trade_management_runtime_identity import runtime_code_identity


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE_ARGUMENTS = {
    "entry_decision": "entry_decision_source",
    "thesis_draft": "thesis_draft_source",
    "shadow_policy": "shadow_policy_source",
    "risk_snapshot": "risk_snapshot_source",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", type=date.fromisoformat, required=True)
    parser.add_argument("--attempt-id", type=require_attempt_id, required=True)
    parser.add_argument("--entry-decision-source", type=Path)
    parser.add_argument("--thesis-draft-source", type=Path)
    parser.add_argument("--shadow-policy-source", type=Path)
    parser.add_argument("--risk-snapshot-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    prepared_at = now or datetime.now(TAIPEI)
    if prepared_at.tzinfo is None or prepared_at.utcoffset() is None:
        raise ValueError("operation time must be timezone-aware")
    prepared_at = prepared_at.astimezone(TAIPEI)
    require_review_packet_path(
        args.output,
        project_root=PROJECT_ROOT,
        market_date=args.market_date,
        attempt_id=args.attempt_id,
    )
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    blockers: list[str] = []
    if not calendar.is_trading_day(args.market_date):
        blockers.append("NOT_A_REVIEWED_TRADING_DAY")

    candidates: dict[str, dict[str, str]] = {}
    source_contents: dict[str, bytes] = {}
    for candidate_name, argument_name in SOURCE_ARGUMENTS.items():
        source = getattr(args, argument_name)
        if source is None or not source.is_file():
            blockers.append(f"MISSING_SOURCE:{candidate_name}")
            continue
        resolved = source.resolve()
        content = resolved.read_bytes()
        source_contents[candidate_name] = content
        candidates[candidate_name] = {
            "path": str(resolved),
            "sha256": sha256_bytes(content),
        }

    binding: dict[str, object] | None = None
    code_identity = runtime_code_identity()
    if not blockers:
        try:
            binding = validate_candidate_bytes(
                source_contents,
                market_date=args.market_date,
                code_identity=code_identity,
                observed_at=prepared_at,
            )
        except Exception as error:
            blockers.append(
                f"CANDIDATE_VALIDATION_FAILED:{type(error).__name__}:{error}"
            )

    packet: dict[str, object] = {
        "artifact_type": "TradeManagementShadowInputReviewPacket",
        "version": REVIEW_PACKET_VERSION,
        "attempt_id": args.attempt_id,
        "prepared_at": prepared_at.isoformat(),
        "status": "PENDING_REVIEW",
        "market_date": args.market_date.isoformat(),
        "calendar_schema_version": calendar.schema_version,
        "calendar_digest": calendar.source_digest,
        "runtime_code_identity": code_identity,
        "candidate_sources": candidates,
        "candidate_valid": not blockers,
        "binding": binding,
        "blockers": sorted(blockers),
        "reviewed": False,
        "review_approval": None,
        "formal_c1_eligible": False,
        "canonical_input_dir": str(
            (
                PROJECT_ROOT
                / "research"
                / "trade_management_shadow"
                / "session_inputs"
                / args.market_date.isoformat()
            ).resolve()
        ),
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }
    digest = canonical_digest(packet)
    packet["packet_digest"] = digest
    args.output.parent.mkdir(parents=True, exist_ok=False)
    write_json_digest_pair_exclusive(
        args.output,
        packet,
        digest,
    )
    print(
        json.dumps(
            {
                "status": "PENDING_REVIEW",
                "candidate_valid": not blockers,
                "blockers": sorted(blockers),
                "artifact": str(args.output.resolve()),
                "digest": digest,
                "formal_c1_eligible": False,
                "production_shadow_gate": "NOT_PASSED",
            },
            sort_keys=True,
        )
    )
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
