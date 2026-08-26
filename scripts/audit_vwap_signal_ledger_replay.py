#!/usr/bin/env python3
"""Rebuild and audit canonical R5 v2 G3 ledger/match-plan evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.domain import canonical_json
from backtest.research_replay.artifact_store import ReplayArtifactStore
from backtest.research_replay.domain import (
    ResearchReplayIntegrityError,
    compare_layers,
    require_sha256,
)


_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "baseline_run_id",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "ledger_manifest_digest",
        "preflight_digest",
        "signal_count",
        "matched_entry_count",
        "matched_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_match_count",
        "strategy_evaluation_count",
        "provider_call_count",
        "broker_call_count",
        "ledger_path",
        "match_plan_path",
    }
)
_AUDIT_SCHEMA_VERSION = "r5-signal-ledger-preflight-operation-audit-v2"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit canonical R5 v2 G3 preflight artifacts",
    )
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--preflight-digest", required=True)
    parser.add_argument("--operation-audit", required=True, type=Path)
    return parser


def _load_operation_audit(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResearchReplayIntegrityError("G3 operation audit 無法讀取") from error
    if not isinstance(parsed, Mapping) or set(parsed) != _AUDIT_FIELDS:
        raise ResearchReplayIntegrityError("G3 operation audit schema 不一致")
    audit = dict(parsed)
    if raw != (canonical_json(audit) + "\n").encode("utf-8"):
        raise ResearchReplayIntegrityError("G3 operation audit bytes 不 canonical")
    if audit["schema_version"] != _AUDIT_SCHEMA_VERSION:
        raise ResearchReplayIntegrityError("G3 operation audit schema identity 不一致")
    for field in (
        "dataset_digest",
        "dataset_bars_sha256",
        "ledger_manifest_digest",
        "preflight_digest",
    ):
        require_sha256(audit[field], field)
    for field in (
        "signal_count",
        "matched_entry_count",
        "matched_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_match_count",
        "strategy_evaluation_count",
        "provider_call_count",
        "broker_call_count",
    ):
        if type(audit[field]) is not int or audit[field] < 0:
            raise ResearchReplayIntegrityError(f"G3 audit {field} 不合法")
    return audit


def audit_preflight(
    *, artifact_root: Path, preflight_digest: str, operation_audit: Path
) -> dict[str, Any]:
    expected_digest = require_sha256(preflight_digest, "preflight_digest")
    audit = _load_operation_audit(operation_audit)
    if audit["preflight_digest"] != expected_digest:
        raise ResearchReplayIntegrityError("G3 audit/preflight locator 不一致")
    store = ReplayArtifactStore(artifact_root)
    match = store.load_match_plan(expected_digest)
    ledger = store.load_ledger(match.manifest["ledger_manifest_digest"])
    parity = compare_layers(ledger.ledger_rows, match.rows)
    if not parity.equal or parity.left_digest != parity.right_digest:
        raise ResearchReplayIntegrityError("G3 ledger/match bidirectional parity 失敗")
    manifest = match.manifest
    if not (
        audit["baseline_run_id"]
        == ledger.manifest["baseline_run_id"]
        == manifest["baseline_run_id"]
        and audit["dataset_id"]
        == ledger.manifest["dataset_id"]
        == manifest["dataset_id"]
        and audit["dataset_digest"]
        == ledger.manifest["dataset_digest"]
        == manifest["dataset_digest"]
        and audit["dataset_bars_sha256"]
        == ledger.manifest["dataset_bars_sha256"]
        == manifest["dataset_bars_sha256"]
        and audit["ledger_manifest_digest"]
        == ledger.manifest["ledger_manifest_digest"]
        == manifest["ledger_manifest_digest"]
        and audit["signal_count"] == manifest["signal_count"] == len(ledger.ledger_rows)
        and audit["matched_entry_count"] == manifest["matched_entry_count"]
        and audit["matched_exit_count"] == manifest["matched_exit_count"] == len(match.rows)
        and audit["missing_entry_count"] == manifest["missing_entry_count"] == 0
        and audit["missing_exit_count"] == manifest["missing_exit_count"] == 0
        and audit["duplicate_match_count"] == manifest["duplicate_match_count"] == 0
        and audit["strategy_evaluation_count"]
        == audit["provider_call_count"]
        == audit["broker_call_count"]
        == 0
    ):
        raise ResearchReplayIntegrityError("G3 operation audit/artifact evidence 不一致")
    return {
        "schema_version": "r5-signal-ledger-preflight-verification-v2",
        "baseline_run_id": manifest["baseline_run_id"],
        "ledger_manifest_digest": ledger.manifest["ledger_manifest_digest"],
        "preflight_digest": manifest["match_plan_manifest_digest"],
        "signal_count": manifest["signal_count"],
        "matched_entry_count": manifest["matched_entry_count"],
        "matched_exit_count": manifest["matched_exit_count"],
        "ledger_minus_match_count": parity.left_minus_right_count,
        "match_minus_ledger_count": parity.right_minus_left_count,
        "provider_call_count": audit["provider_call_count"],
        "broker_call_count": audit["broker_call_count"],
        "verified": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = audit_preflight(
        artifact_root=args.artifact_root,
        preflight_digest=args.preflight_digest,
        operation_audit=args.operation_audit,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
