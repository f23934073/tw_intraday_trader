import hashlib
import json
from pathlib import Path


ARTIFACT = (
    Path(__file__).parents[1]
    / "research"
    / "trade_management_shadow"
    / "premarket_20260821.json"
)


def test_reviewed_c0_artifact_is_ready_redacted_and_nonqualifying() -> None:
    payload = ARTIFACT.read_text(encoding="utf-8")
    value = json.loads(payload)

    assert value["readiness_report"]["status"] == "READY_FOR_SESSION"
    assert value["readiness_report"]["blockers"] == []
    assert value["production_shadow_gate"] == "NOT_PASSED"
    assert value["manifest"]["execution_enabled"] is False
    assert value["manifest"]["qualifying_real_session"] is False
    assert value["provider_preflight"]["subscribe_trade"] is False
    assert value["postgres_preflight"]["transaction_read_only"] is True
    assert set(value["postgres_preflight"]["evidence_row_counts"].values()) == {0}
    assert value["rehearsal"]["qualifying_real_session"] is False
    assert "postgresql://" not in payload
    assert "SHIOAJI_SECRET" not in payload


def test_c0_artifact_digest_sidecar_matches_the_sealed_report() -> None:
    value = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    sidecar = ARTIFACT.with_suffix(".json.sha256").read_text().strip()

    assert sidecar == value["readiness_report_digest"]
    assert len(sidecar) == hashlib.sha256().digest_size * 2
