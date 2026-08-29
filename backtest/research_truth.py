"""Fail-closed Taiwan Dataset research-truth projection for formal v3 runs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from backtest.dataset import DatasetManifest
from backtest.domain import (
    RESEARCH_TRUTH_CONTRACT_VERSION,
    decimal,
    digest,
    is_sha256_hex,
    verify_contract_snapshot,
)


RESEARCH_COVERAGE_MINIMUM = Decimal("0.95")

REQUIRED_DATASET_CONTRACTS: Mapping[str, str] = {
    "universe_contract": "tw-pit-universe-v1",
    "listing_contract": "tw-pit-listing-v1",
    "session_contract": "tw-session-v1",
    "calendar_contract": "tw-calendar-v1",
    "closing_auction_event_contract": "tw-closing-auction-event-v1",
    "corporate_action_contract": "tw-corporate-action-v1",
    "reference_price_contract": "tw-reference-price-v1",
    "price_limit_contract": "tw-price-limit-v1",
    "volume_contract": "tw-volume-v1",
    "amount_contract": "tw-amount-v1",
    "special_regime_contract": "tw-special-regime-v1",
    "completeness_contract": "tw-completeness-v1",
    "execution_calibration_contract": "tw-participation-calibration-v1",
    "slippage_calibration_contract": "tw-slippage-calibration-v1",
}

_SNAPSHOT_KEYS = {
    "contract_version",
    "status",
    "dataset_id",
    "dataset_manifest_digest",
    "universe_scope",
    "reason_codes",
    "contract_digests",
    "closing_auction_event_contract",
    "execution_calibration_contract",
    "slippage_calibration_contract",
    "completeness",
    "snapshot_digest",
}


class ResearchTruthUnavailable(ValueError):
    """Raised when formal data truth is absent, unknown, or drifted."""


def build_research_truth_snapshot(manifest: DatasetManifest) -> dict[str, Any]:
    """Build one deterministic truth snapshot from an immutable manifest."""

    reasons: list[str] = []
    if manifest.universe_scope != "DATE_EFFECTIVE":
        reasons.append("CURRENT_SNAPSHOT_UNIVERSE")
    if not manifest.research_eligible:
        reasons.append("MANIFEST_NOT_RESEARCH_ELIGIBLE")
    if manifest.issues:
        reasons.append("MANIFEST_ISSUES_PRESENT")

    verified: dict[str, dict[str, Any]] = {}
    for field_name, contract_version in REQUIRED_DATASET_CONTRACTS.items():
        raw = getattr(manifest, field_name)
        if not isinstance(raw, Mapping):
            reasons.append(f"MISSING_{field_name.upper()}")
            continue
        try:
            contract = verify_contract_snapshot(
                raw,
                label=f"DatasetManifest.{field_name}",
                expected_contract_version=contract_version,
            )
        except ValueError:
            reasons.append(f"INVALID_{field_name.upper()}")
            continue
        if contract.get("status") != "VERIFIED":
            reasons.append(f"UNKNOWN_{field_name.upper()}_STATUS")
            continue
        verified[field_name] = contract

    reasons.extend(_semantic_reasons(manifest, verified))
    reasons = list(dict.fromkeys(reasons))
    auction = verified.get("closing_auction_event_contract", {})
    execution = verified.get("execution_calibration_contract", {})
    slippage = verified.get("slippage_calibration_contract", {})
    completeness = verified.get("completeness_contract", {})
    body: dict[str, Any] = {
        "contract_version": RESEARCH_TRUTH_CONTRACT_VERSION,
        "status": "VERIFIED" if not reasons else "FAIL_CLOSED",
        "dataset_id": manifest.dataset_id,
        "dataset_manifest_digest": manifest.manifest_digest,
        "universe_scope": manifest.universe_scope,
        "reason_codes": reasons,
        "contract_digests": {
            field_name: (
                str(getattr(manifest, field_name).get("snapshot_digest"))
                if isinstance(getattr(manifest, field_name), Mapping)
                else None
            )
            for field_name in REQUIRED_DATASET_CONTRACTS
        },
        "closing_auction_event_contract": {
            "status": auction.get("status", "UNKNOWN"),
            "event_time": auction.get("event_time"),
            "price_semantics": auction.get("price_semantics", "UNKNOWN"),
            "volume_semantics": auction.get("volume_semantics", "UNKNOWN"),
        },
        "execution_calibration_contract": {
            "status": execution.get("status", "UNKNOWN"),
            "max_participation_rate": execution.get("max_participation_rate"),
            "bar_volume_unit": execution.get("bar_volume_unit"),
            "participation_calibration_digest": execution.get("participation_calibration_digest"),
        },
        "slippage_calibration_contract": {
            "status": slippage.get("status", "UNKNOWN"),
            "slippage_bps": slippage.get("slippage_bps"),
            "slippage_calibration_digest": slippage.get("slippage_calibration_digest"),
        },
        "completeness": {
            "status": completeness.get("status", "UNKNOWN"),
            "coverage_ratio": completeness.get("coverage_ratio"),
            "minimum": str(RESEARCH_COVERAGE_MINIMUM),
        },
    }
    return {**body, "snapshot_digest": digest(body)}


def verify_research_truth_snapshot(
    snapshot: Mapping[str, Any],
    *,
    manifest: DatasetManifest | None = None,
) -> dict[str, Any]:
    """Verify schema/digest and optionally bind it back to its manifest."""

    value = verify_contract_snapshot(
        snapshot,
        label="research_truth_snapshot",
        expected_contract_version=RESEARCH_TRUTH_CONTRACT_VERSION,
    )
    if set(value) != _SNAPSHOT_KEYS:
        raise ResearchTruthUnavailable("research_truth_snapshot 欄位未知或缺漏")
    if value.get("status") not in {"VERIFIED", "FAIL_CLOSED"}:
        raise ResearchTruthUnavailable("research_truth_snapshot status 未知")
    reasons = value.get("reason_codes")
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise ResearchTruthUnavailable("research_truth_snapshot reason_codes 不合法")
    if (value["status"] == "VERIFIED") != (not reasons):
        raise ResearchTruthUnavailable("research_truth_snapshot status/reasons 不一致")
    digests = value.get("contract_digests")
    if not isinstance(digests, Mapping) or set(digests) != set(REQUIRED_DATASET_CONTRACTS):
        raise ResearchTruthUnavailable("research_truth_snapshot contract digests 不完整")
    if value["status"] == "VERIFIED" and any(
        not isinstance(item, str) or not is_sha256_hex(item) for item in digests.values()
    ):
        raise ResearchTruthUnavailable("research_truth_snapshot contract digest 未驗證")
    if manifest is not None and value != build_research_truth_snapshot(manifest):
        raise ResearchTruthUnavailable("research_truth_snapshot 與 DatasetManifest 不一致")
    return value


def require_formal_research_truth(
    snapshot: Mapping[str, Any],
    *,
    manifest: DatasetManifest | None = None,
) -> dict[str, Any]:
    value = verify_research_truth_snapshot(snapshot, manifest=manifest)
    if value["status"] != "VERIFIED":
        reasons = ",".join(value["reason_codes"]) or "UNKNOWN_RESEARCH_TRUTH"
        raise ResearchTruthUnavailable(f"FORMAL_DATA_FAIL:{reasons}")
    return value


def research_readiness_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    value = verify_research_truth_snapshot(snapshot)
    ready = value["status"] == "VERIFIED"
    return {
        "ready": ready,
        "status": "DATA_READY" if ready else "DATA_NOT_READY",
        "reason_codes": list(value["reason_codes"]),
        "research_truth_snapshot_digest": value["snapshot_digest"],
    }


def _semantic_reasons(
    manifest: DatasetManifest,
    contracts: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []

    def require(field_name: str, key: str, expected: Any) -> None:
        contract = contracts.get(field_name)
        if contract is not None and contract.get(key) != expected:
            reasons.append(f"UNKNOWN_{field_name.upper()}_{key.upper()}")

    require("universe_contract", "scope", "DATE_EFFECTIVE")
    require("universe_contract", "survivorship_free", True)
    require("listing_contract", "semantics", "POINT_IN_TIME")
    require("listing_contract", "delisted_included", True)
    require("session_contract", "timezone", "Asia/Taipei")
    require("session_contract", "phase_semantics", "EXPLICIT")
    require("calendar_contract", "semantics", "DATE_EFFECTIVE")
    require("closing_auction_event_contract", "event_time", "13:30:00+08:00")
    require("closing_auction_event_contract", "price_semantics", "AUCTION_ONLY")
    require("closing_auction_event_contract", "volume_semantics", "AUCTION_ONLY")
    require("corporate_action_contract", "semantics", "POINT_IN_TIME")
    require("reference_price_contract", "semantics", "DATE_EFFECTIVE")
    require("price_limit_contract", "semantics", "POINT_IN_TIME")
    require("volume_contract", "phase_semantics", "EXPLICIT")
    require("amount_contract", "unit", "TWD")
    require("amount_contract", "semantics", "TURNOVER")
    require("special_regime_contract", "classification", "COMPLETE")
    require("special_regime_contract", "unknown_count", 0)

    volume = contracts.get("volume_contract")
    execution = contracts.get("execution_calibration_contract")
    if volume is not None and volume.get("unit") not in {"SHARES", "COMMON_LOTS"}:
        reasons.append("UNKNOWN_VOLUME_CONTRACT_UNIT")
    if execution is not None:
        if execution.get("bar_volume_unit") != (volume or {}).get("unit"):
            reasons.append("EXECUTION_CALIBRATION_VOLUME_UNIT_MISMATCH")
        if str(execution.get("max_participation_rate")) != "0.05":
            reasons.append("UNKNOWN_MAX_PARTICIPATION_RATE")
        if not is_sha256_hex(str(execution.get("participation_calibration_digest") or "")):
            reasons.append("UNKNOWN_PARTICIPATION_CALIBRATION")
    slippage = contracts.get("slippage_calibration_contract")
    if slippage is not None:
        try:
            slippage_bps = decimal(slippage.get("slippage_bps"))
        except Exception:
            slippage_bps = Decimal("-1")
        if not slippage_bps.is_finite() or slippage_bps < 0:
            reasons.append("UNKNOWN_SLIPPAGE_BPS")
        if not is_sha256_hex(str(slippage.get("slippage_calibration_digest") or "")):
            reasons.append("UNKNOWN_SLIPPAGE_CALIBRATION")

    completeness = contracts.get("completeness_contract")
    if completeness is not None:
        try:
            ratio = decimal(completeness.get("coverage_ratio"))
        except Exception:
            ratio = Decimal("-1")
        if not ratio.is_finite() or ratio < RESEARCH_COVERAGE_MINIMUM or ratio > 1:
            reasons.append("COMPLETENESS_COVERAGE_BELOW_MINIMUM")
        for field_name in (
            "missing_count",
            "duplicate_count",
            "out_of_order_count",
            "invalid_ohlc_count",
        ):
            if completeness.get(field_name) != 0:
                reasons.append(f"COMPLETENESS_{field_name.upper()}")
        for key, expected in (
            ("start_date", manifest.start_date),
            ("end_date", manifest.end_date),
        ):
            if completeness.get(key) != expected:
                reasons.append(f"COMPLETENESS_{key.upper()}_MISMATCH")
    try:
        if date.fromisoformat(manifest.start_date) > date.fromisoformat(manifest.end_date):
            reasons.append("MANIFEST_DATE_RANGE_INVALID")
    except ValueError:
        reasons.append("MANIFEST_DATE_RANGE_INVALID")
    return reasons
