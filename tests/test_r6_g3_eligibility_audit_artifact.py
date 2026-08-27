from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backtest.atomic_benchmark.domain import canonical_object_bytes
from backtest.atomic_benchmark.preflight import verify_eligibility_audit


ARTIFACT = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "atomic_entry_benchmark"
    / "eligibility_audit"
    / "2e4f8590d0de3f963e4d41bc17d87fd859809053f9f2206015ba69d46863131d.json"
)
SIDECAR = ARTIFACT.with_suffix(".canonical.sha256")


def test_r6_g3_source_only_audit_artifact_is_canonical_and_replayable() -> None:
    payload = ARTIFACT.read_bytes()
    expected_file_sha256 = SIDECAR.read_text(encoding="utf-8").strip()
    assert hashlib.sha256(payload).hexdigest() == expected_file_sha256

    raw = json.loads(payload)
    assert isinstance(raw, dict)
    verified = verify_eligibility_audit(raw)
    assert canonical_object_bytes(verified) == payload
    assert verified["audit_digest"] == ARTIFACT.stem
    assert verified["source_bar_count"] == 28_325_340
    assert verified["observed_symbol_session_count"] == 132_234
    assert verified["eligible_symbol_session_count"] == 131_691
    assert verified["eligible_symbol_session_ratio"] == "0.995893643087254413"
    assert verified["family_head_sequence"] == 0
    assert verified["attempt_count"] == 0
