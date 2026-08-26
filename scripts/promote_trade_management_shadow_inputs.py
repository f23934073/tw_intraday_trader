"""Promote one reviewed Shadow input approval into canonical C1 files."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.trade_management_artifact_io import write_json_digest_pair_exclusive
from runtime.trade_management_input_review import (
    SOURCE_FILENAMES,
    canonical_promotion_lock_path,
    canonical_digest,
    load_verified_review_approval,
    load_verified_review_packet,
    reject_symlink_components,
)
from runtime.trade_management_runtime_identity import runtime_code_identity


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-approval", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
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
    code_identity = runtime_code_identity()
    approval = load_verified_review_approval(
        args.review_approval,
        project_root=PROJECT_ROOT,
        current_code_identity=code_identity,
        observed_at=observed_at,
    )
    market_date = date.fromisoformat(str(approval["market_date"]))
    expected_output = (
        PROJECT_ROOT
        / "research/trade_management_shadow/session_inputs"
        / market_date.isoformat()
    ).absolute()
    if args.output_dir.absolute() != expected_output:
        raise ValueError("CANONICAL_INPUT_OUTPUT_PATH_MISMATCH")
    reject_symlink_components(
        args.output_dir.absolute(),
        root=(
            PROJECT_ROOT / "research/trade_management_shadow/session_inputs"
        ).absolute(),
    )
    packet_path = Path(str(approval["review_packet_path"]))
    packet, source_contents = load_verified_review_packet(
        packet_path,
        project_root=PROJECT_ROOT,
        current_code_identity=code_identity,
        observed_at=observed_at,
    )
    if (
        approval.get("review_packet_digest") != packet.get("packet_digest")
        or approval.get("attempt_id") != packet.get("attempt_id")
        or approval.get("market_date") != packet.get("market_date")
        or approval.get("binding") != packet.get("binding")
    ):
        raise RuntimeError("INPUT_APPROVAL_PACKET_BINDING_MISMATCH")
    approved_sources = approval.get("approved_sources")
    packet_sources = packet.get("candidate_sources")
    if not isinstance(approved_sources, dict) or not isinstance(packet_sources, dict):
        raise RuntimeError("INPUT_APPROVAL_SOURCE_SET_INVALID")
    for name, filename in SOURCE_FILENAMES.items():
        approved = approved_sources.get(name)
        packet_source = packet_sources.get(name)
        if (
            not isinstance(approved, dict)
            or not isinstance(packet_source, dict)
            or approved.get("filename") != filename
            or approved.get("sha256") != packet_source.get("sha256")
        ):
            raise RuntimeError("INPUT_APPROVAL_SOURCE_DIGEST_MISMATCH")

    parent = args.output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    lock = canonical_promotion_lock_path(parent, market_date)
    lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    committed = False
    publication_started = False
    try:
        os.write(lock_fd, str(approval["approval_digest"]).encode("ascii") + b"\n")
        os.fsync(lock_fd)
        if args.output_dir.exists():
            raise FileExistsError(f"canonical input directory exists: {args.output_dir}")
        args.output_dir.mkdir(mode=0o700)
        publication_started = True
        for name, filename in SOURCE_FILENAMES.items():
            _write_bytes_exclusive(args.output_dir / filename, source_contents[name])
        approval_digest = str(approval["approval_digest"])
        write_json_digest_pair_exclusive(
            args.output_dir / "review_approval.json",
            approval,
            approval_digest,
        )
        bundle = {
            "artifact_type": "TradeManagementShadowCanonicalInputBundle",
            "version": "trade-management-shadow-canonical-input-bundle-v1",
            "market_date": market_date.isoformat(),
            "attempt_id": approval["attempt_id"],
            "approval_digest": approval_digest,
            "review_packet_digest": approval["review_packet_digest"],
            "runtime_code_identity": code_identity,
            "file_digests": {
                name: approved_sources[name]["sha256"]
                for name in SOURCE_FILENAMES
            },
            "execution_authority": False,
            "execution_enabled": False,
            "evidence_only": True,
            "production_shadow_gate": "NOT_PASSED",
        }
        bundle_digest = canonical_digest(bundle)
        bundle["bundle_digest"] = bundle_digest
        write_json_digest_pair_exclusive(
            args.output_dir / "bundle_manifest.json",
            bundle,
            bundle_digest,
        )
        _fsync_directory(args.output_dir)
        _fsync_directory(parent)
        committed = True
    finally:
        os.close(lock_fd)
        if committed or not publication_started:
            lock.unlink(missing_ok=True)
            _fsync_directory(parent)
    print(
        json.dumps(
            {
                "status": "PROMOTED_REVIEWED_INPUTS",
                "canonical_input_dir": str(args.output_dir.absolute()),
                "approval_digest": approval["approval_digest"],
                "production_shadow_gate": "NOT_PASSED",
            },
            sort_keys=True,
        )
    )
    return 0


def _write_bytes_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
