from __future__ import annotations

import json
from datetime import datetime

import pytest

from scripts.inspect_no_overnight_evidence import main
from trading.no_overnight_evidence import (
    NoOvernightDrillEvidence,
    NoOvernightDrillKind,
    NoOvernightDrillStatus,
    write_no_overnight_drill_evidence,
)


def test_cli_prints_canonical_strict_drill(capsys, tmp_path) -> None:
    drill = NoOvernightDrillEvidence(
        campaign_id="campaign-v1",
        kind=NoOvernightDrillKind.RESTART_RECOVERY,
        status=NoOvernightDrillStatus.PASSED,
        observed_at=datetime.fromisoformat("2026-08-26T13:45:00+08:00"),
        evidence_digest="a" * 64,
        account_scope_id="local-paper-account-v1",
        policy_family_id="no-overnight-family-v1",
        policy_digest="b" * 64,
        deployment_manifest_digest="c" * 64,
    )
    path = tmp_path / "drill.json"
    write_no_overnight_drill_evidence(path, drill)

    assert main(["drill", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == drill.payload()


def test_cli_rejects_unsealed_campaign_artifact(tmp_path) -> None:
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps({"status": "READY_FOR_INDEPENDENT_REVIEW"}))

    with pytest.raises(ValueError, match="fields"):
        main(["campaign", str(path)])


def test_cli_bundle_requires_complete_canonical_directory(tmp_path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "drills").mkdir()

    with pytest.raises(ValueError, match="campaign_report.json"):
        main(["bundle", str(tmp_path)])
