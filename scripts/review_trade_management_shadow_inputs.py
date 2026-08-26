"""Approve one immutable Shadow input draft without promoting it."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.trade_management_artifact_io import write_json_digest_pair_exclusive
from runtime.trade_management_input_review import (
    REVIEW_APPROVAL_VERSION,
    SOURCE_FILENAMES,
    canonical_digest,
    load_verified_review_packet,
    require_approval_fields,
    require_review_approval_path,
)
from runtime.trade_management_runtime_identity import runtime_code_identity


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-packet", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-note", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    observed_at = now or datetime.now(TAIPEI)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("operation time must be timezone-aware")
    observed_at = observed_at.astimezone(TAIPEI)
    reviewer_id = args.reviewer_id.strip()
    review_note = args.review_note.strip()
    if not reviewer_id or not review_note:
        raise ValueError("reviewer-id and review-note must not be empty")
    if args.reviewed_at.tzinfo is None or args.reviewed_at.utcoffset() is None:
        raise ValueError("reviewed-at must be timezone-aware")
    code_identity = runtime_code_identity()
    packet, _ = load_verified_review_packet(
        args.review_packet,
        project_root=PROJECT_ROOT,
        current_code_identity=code_identity,
        observed_at=observed_at,
    )
    market_date = str(packet["market_date"])
    attempt_id = str(packet["attempt_id"])
    require_review_approval_path(
        args.output,
        project_root=PROJECT_ROOT,
        market_date=date.fromisoformat(market_date),
        attempt_id=attempt_id,
    )
    raw_sources = packet["candidate_sources"]
    assert isinstance(raw_sources, dict)
    approval: dict[str, object] = {
        "artifact_type": "TradeManagementShadowInputReviewApproval",
        "version": REVIEW_APPROVAL_VERSION,
        "approval_status": "APPROVED_FOR_CANONICAL_PROMOTION",
        "market_date": market_date,
        "attempt_id": attempt_id,
        "review_packet_path": str(args.review_packet.resolve()),
        "review_packet_digest": packet["packet_digest"],
        "reviewer_id": reviewer_id,
        "reviewed_at": args.reviewed_at.isoformat(),
        "review_note": review_note,
        "runtime_code_identity": code_identity,
        "approved_sources": {
            name: {
                "filename": SOURCE_FILENAMES[name],
                "sha256": raw_sources[name]["sha256"],
            }
            for name in SOURCE_FILENAMES
        },
        "binding": packet["binding"],
        "reviewed": True,
        "formal_c1_eligible": True,
        "execution_authority": False,
        "execution_enabled": False,
        "evidence_only": True,
        "production_shadow_gate": "NOT_PASSED",
    }
    require_approval_fields(approval, observed_at=observed_at)
    digest = canonical_digest(approval)
    approval["approval_digest"] = digest
    args.output.parent.mkdir(parents=True, exist_ok=False)
    write_json_digest_pair_exclusive(args.output, approval, digest)
    print(
        json.dumps(
            {
                "status": "APPROVED_FOR_CANONICAL_PROMOTION",
                "artifact": str(args.output.resolve()),
                "digest": digest,
                "canonical_inputs_created": False,
                "production_shadow_gate": "NOT_PASSED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
