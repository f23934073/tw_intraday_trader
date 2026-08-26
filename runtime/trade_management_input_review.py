"""Pure contracts for draft review and canonical input approval."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

from runtime.trade_management_artifact_io import (
    digest_path,
    require_complete_artifact_pair,
)
from runtime.trade_management_input_loading import (
    parse_risk_snapshot_document,
    parse_shadow_policy,
    require_risk_snapshot_capture_window,
    reviewed_risk_snapshot_preopen_window,
)
from trading.live_entry_thesis_draft import (
    LiveThesisDraftPolicy,
    LiveTradeThesisDraftBuilder,
)
from trading.trade_management_serialization import (
    deserialize_live_entry_decision,
    deserialize_trade_thesis_draft,
)


REVIEW_PACKET_VERSION = "trade-management-shadow-input-review-v2"
REVIEW_APPROVAL_VERSION = "trade-management-shadow-input-approval-v1"
SOURCE_FILENAMES = {
    "entry_decision": "live_entry_decision.json",
    "thesis_draft": "trade_thesis_draft.json",
    "shadow_policy": "shadow_policy.json",
    "risk_snapshot": "risk_snapshot.json",
}
ATTEMPT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{2,63}\Z")


def require_attempt_id(value: str) -> str:
    if ATTEMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("attempt_id must use 3-64 lowercase safe characters")
    return value


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_candidate_bytes(
    paths: dict[str, Path],
) -> tuple[dict[str, bytes], dict[str, dict[str, str]]]:
    contents: dict[str, bytes] = {}
    metadata: dict[str, dict[str, str]] = {}
    for name in SOURCE_FILENAMES:
        path = paths[name].resolve()
        content = path.read_bytes()
        contents[name] = content
        metadata[name] = {
            "path": str(path),
            "sha256": sha256_bytes(content),
        }
    return contents, metadata


def validate_candidate_bytes(
    contents: dict[str, bytes],
    *,
    market_date: date,
    code_identity: str,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    decision = deserialize_live_entry_decision(
        contents["entry_decision"].decode("utf-8")
    )
    draft = deserialize_trade_thesis_draft(
        contents["thesis_draft"].decode("utf-8")
    )
    draft_policy = LiveThesisDraftPolicy(
        policy_id=draft.expected_behavior.policy_id,
        strategy_id=draft.strategy_id,
        strategy_version=draft.strategy_version,
        thesis_type=draft.thesis_type,
        thesis_version=draft.thesis_version,
        side=draft.side,
        expected_behavior=draft.expected_behavior,
        invalid_conditions=draft.invalid_conditions,
    )
    if LiveTradeThesisDraftBuilder().build(decision, draft_policy) != draft:
        raise ValueError("ENTRY_DECISION_DRAFT_PARITY_MISMATCH")
    if decision.signal_at.value.date() != market_date:
        raise ValueError("ENTRY_DECISION_MARKET_DATE_MISMATCH")
    shadow_policy = parse_shadow_policy(
        contents["shadow_policy"],
        code_identity=code_identity,
    )
    if (
        not shadow_policy.exit_policy_version.strip()
        or not shadow_policy.risk_policy.version.strip()
        or shadow_policy.volume_baseline_shares <= 0
        or shadow_policy.shares_per_lot <= 0
        or shadow_policy.remaining_quantity_shares <= 0
        or not shadow_policy.fill_model_version.strip()
    ):
        raise ValueError("SHADOW_POLICY_INVALID")
    risk_snapshot, provenance = parse_risk_snapshot_document(
        contents["risk_snapshot"]
    )
    window_start, window_end = reviewed_risk_snapshot_preopen_window(market_date)
    require_risk_snapshot_capture_window(
        provenance,
        window_start=window_start,
        window_end=window_end,
    )
    if observed_at is not None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if provenance.captured_at > observed_at:
            raise ValueError("RISK_SNAPSHOT_CAPTURE_AFTER_OBSERVATION")
    if (
        provenance.session_id != decision.session_id
        or provenance.symbol != decision.symbol
        or provenance.market_date != market_date
    ):
        raise ValueError("RISK_SNAPSHOT_PROVENANCE_MISMATCH")
    return {
        "session_id": decision.session_id,
        "symbol": decision.symbol,
        "strategy_id": draft.strategy_id,
        "strategy_version": draft.strategy_version,
        "thesis_version": draft.thesis_version,
        "exit_policy_version": shadow_policy.exit_policy_version,
        "risk_policy_version": shadow_policy.risk_policy.version,
        "fill_model_version": shadow_policy.fill_model_version,
        "risk_data_health_state": risk_snapshot.data_health_state,
        "risk_snapshot_provenance": provenance.to_dict(),
    }


def load_digest_bound_json(path: Path, *, digest_field: str) -> dict[str, object]:
    sidecar = require_complete_artifact_pair(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    claimed = str(value.get(digest_field, ""))
    unsigned = dict(value)
    unsigned.pop(digest_field, None)
    if canonical_digest(unsigned) != claimed:
        raise RuntimeError("ARTIFACT_CANONICAL_DIGEST_MISMATCH")
    if digest_path(path) != sidecar or sidecar.read_text(encoding="utf-8").strip() != claimed:
        raise RuntimeError("ARTIFACT_SIDECAR_DIGEST_MISMATCH")
    return value


def require_review_packet_path(
    path: Path,
    *,
    project_root: Path,
    market_date: date,
    attempt_id: str,
) -> None:
    root = (
        project_root / "research/trade_management_shadow/session_input_drafts"
    ).absolute()
    expected = (
        root
        / market_date.isoformat()
        / "attempts"
        / require_attempt_id(attempt_id)
        / "review_packet.json"
    ).absolute()
    if path.absolute() != expected:
        raise ValueError("REVIEW_PACKET_PATH_MISMATCH")
    reject_symlink_components(path.absolute(), root=root)


def require_review_approval_path(
    path: Path,
    *,
    project_root: Path,
    market_date: date,
    attempt_id: str,
) -> None:
    root = (
        project_root / "research/trade_management_shadow/session_input_approvals"
    ).absolute()
    expected = (
        root
        / market_date.isoformat()
        / "attempts"
        / require_attempt_id(attempt_id)
        / "review_approval.json"
    ).absolute()
    if path.absolute() != expected:
        raise ValueError("REVIEW_APPROVAL_PATH_MISMATCH")
    reject_symlink_components(path.absolute(), root=root)


def reject_symlink_components(path: Path, *, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("ARTIFACT_PATH_OUTSIDE_ROOT") from error
    cursor = root
    if cursor.is_symlink():
        raise RuntimeError("ARTIFACT_PATH_SYMLINK_REJECTED")
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeError("ARTIFACT_PATH_SYMLINK_REJECTED")


def canonical_promotion_lock_path(
    session_inputs_root: Path,
    market_date: date,
) -> Path:
    return session_inputs_root / f".{market_date.isoformat()}.promotion.lock"


def require_approval_fields(
    value: dict[str, object],
    *,
    observed_at: datetime | None = None,
) -> None:
    if (
        value.get("artifact_type") != "TradeManagementShadowInputReviewApproval"
        or value.get("version") != REVIEW_APPROVAL_VERSION
        or value.get("approval_status") != "APPROVED_FOR_CANONICAL_PROMOTION"
        or value.get("reviewed") is not True
        or value.get("formal_c1_eligible") is not True
        or value.get("execution_authority") is not False
        or value.get("execution_enabled") is not False
        or value.get("evidence_only") is not True
        or value.get("production_shadow_gate") != "NOT_PASSED"
    ):
        raise RuntimeError("INPUT_REVIEW_APPROVAL_INVALID")
    if not str(value.get("reviewer_id", "")).strip():
        raise RuntimeError("INPUT_REVIEWER_ID_MISSING")
    reviewed_at = datetime.fromisoformat(str(value["reviewed_at"]))
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise RuntimeError("INPUT_REVIEW_TIME_MUST_BE_AWARE")
    if observed_at is not None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise RuntimeError("INPUT_REVIEW_OBSERVATION_TIME_MUST_BE_AWARE")
        if reviewed_at > observed_at:
            raise RuntimeError("INPUT_REVIEW_TIME_AFTER_OBSERVATION")
    binding = value.get("binding")
    if not isinstance(binding, dict):
        raise RuntimeError("INPUT_REVIEW_BINDING_MISSING")
    provenance = binding.get("risk_snapshot_provenance")
    if not isinstance(provenance, dict):
        raise RuntimeError("INPUT_REVIEW_RISK_PROVENANCE_MISSING")
    captured_at = datetime.fromisoformat(str(provenance["captured_at"]))
    if reviewed_at < captured_at:
        raise RuntimeError("INPUT_REVIEW_PRECEDES_RISK_CAPTURE")


def load_verified_review_packet(
    path: Path,
    *,
    project_root: Path,
    current_code_identity: str,
    observed_at: datetime | None = None,
) -> tuple[dict[str, object], dict[str, bytes]]:
    packet = load_digest_bound_json(path, digest_field="packet_digest")
    if (
        packet.get("artifact_type") != "TradeManagementShadowInputReviewPacket"
        or packet.get("version") != REVIEW_PACKET_VERSION
        or packet.get("status") != "PENDING_REVIEW"
        or packet.get("candidate_valid") is not True
        or packet.get("blockers") != []
        or packet.get("reviewed") is not False
        or packet.get("formal_c1_eligible") is not False
        or packet.get("execution_authority") is not False
        or packet.get("execution_enabled") is not False
        or packet.get("evidence_only") is not True
        or packet.get("production_shadow_gate") != "NOT_PASSED"
    ):
        raise RuntimeError("REVIEW_PACKET_NOT_APPROVABLE")
    market_date = date.fromisoformat(str(packet["market_date"]))
    attempt_id = require_attempt_id(str(packet["attempt_id"]))
    require_review_packet_path(
        path,
        project_root=project_root,
        market_date=market_date,
        attempt_id=attempt_id,
    )
    if packet.get("runtime_code_identity") != current_code_identity:
        raise RuntimeError("REVIEW_PACKET_RUNTIME_IDENTITY_CHANGED")
    raw_sources = packet.get("candidate_sources")
    if not isinstance(raw_sources, dict) or set(raw_sources) != set(SOURCE_FILENAMES):
        raise RuntimeError("REVIEW_PACKET_SOURCE_SET_MISMATCH")
    paths: dict[str, Path] = {}
    expected_digests: dict[str, str] = {}
    for name in SOURCE_FILENAMES:
        item = raw_sources[name]
        if not isinstance(item, dict):
            raise RuntimeError("REVIEW_PACKET_SOURCE_METADATA_INVALID")
        paths[name] = Path(str(item["path"]))
        expected_digests[name] = str(item["sha256"])
    contents, metadata = read_candidate_bytes(paths)
    if any(
        metadata[name]["sha256"] != expected_digests[name]
        for name in SOURCE_FILENAMES
    ):
        raise RuntimeError("APPROVED_SOURCE_DIGEST_MISMATCH")
    binding = validate_candidate_bytes(
        contents,
        market_date=market_date,
        code_identity=current_code_identity,
        observed_at=observed_at,
    )
    if binding != packet.get("binding"):
        raise RuntimeError("REVIEW_PACKET_BINDING_MISMATCH")
    return packet, contents


def load_verified_review_approval(
    path: Path,
    *,
    project_root: Path,
    current_code_identity: str,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    approval = load_digest_bound_json(path, digest_field="approval_digest")
    require_approval_fields(approval, observed_at=observed_at)
    market_date = date.fromisoformat(str(approval["market_date"]))
    attempt_id = require_attempt_id(str(approval["attempt_id"]))
    require_review_approval_path(
        path,
        project_root=project_root,
        market_date=market_date,
        attempt_id=attempt_id,
    )
    if approval.get("runtime_code_identity") != current_code_identity:
        raise RuntimeError("INPUT_APPROVAL_RUNTIME_IDENTITY_CHANGED")
    return approval
