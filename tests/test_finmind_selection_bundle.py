from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from backtest.finmind_selection_bundle import (
    FinMindSelectionBundleError,
    _verify_target_job_state,
    seal_bundle,
    validate_bundle_document,
    verify_file_reference,
    verify_selection_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = (
    PROJECT_ROOT
    / "data/finmind_sponsor/universes/selections/"
    "phase82_selection_e9faeaddafc8a81b60289b07ec56571615b623b80f9d7a8d47912e7bf4af7d97.json"
)


def _bundle() -> dict[str, object]:
    return json.loads(BUNDLE_PATH.read_bytes())


def test_phase82_bundle_reproduces_selection_and_status_only_job() -> None:
    result = verify_selection_bundle(
        BUNDLE_PATH,
        project_root=PROJECT_ROOT,
        database_path=PROJECT_ROOT / "data/finmind_sponsor/history.sqlite3",
    )

    assert result == {
        "bundle_digest": "e9faeaddafc8a81b60289b07ec56571615b623b80f9d7a8d47912e7bf4af7d97",
        "eligible_count": 1284,
        "job_id": "finmind-sponsor-3fb900f8f272077e",
        "quick_check": "ok",
        "ranked_candidate_count": 29,
        "selected_symbols": [
            "4114",
            "4438",
            "1603",
            "1718",
            "1536",
            "1702",
            "2901",
            "2607",
        ],
        "status": "VERIFIED",
    }


def test_target_job_lifecycle_progress_does_not_relax_identity() -> None:
    expected_state = copy.deepcopy(_bundle()["job_binding"]["post_create_state"])
    observed = copy.deepcopy(expected_state["row"])
    raw_calendar = b'{"data":[]}'
    observed.update(
        {
            "calendar_raw_payload_is_null": False,
            "calendar_raw_sha256": hashlib.sha256(raw_calendar).hexdigest(),
            "status": "COMPLETED",
            "status_message": "All symbol-days checkpointed",
            "trading_dates_json": "[]",
            "updated_at": "2026-08-27T14:31:10.035404+08:00",
        }
    )

    _verify_target_job_state(
        observed_row=observed,
        expected_state=expected_state,
        partition_count=5816,
        attempt_count=5817,
        calendar_raw_payload=gzip.compress(raw_calendar, mtime=0),
    )

    observed["source_version"] = "TAMPERED"
    with pytest.raises(FinMindSelectionBundleError, match="job identity drifted"):
        _verify_target_job_state(
            observed_row=observed,
            expected_state=expected_state,
            partition_count=5816,
            attempt_count=5817,
            calendar_raw_payload=gzip.compress(raw_calendar, mtime=0),
        )


def test_verifier_rejects_tampered_official_bytes(tmp_path: Path) -> None:
    bundle = _bundle()
    reference = dict(bundle["source_evidence"]["official_twse_company"])
    original = (PROJECT_ROOT / reference["path"]).read_bytes()
    tampered = bytearray(original)
    tampered[-2] = tampered[-2] ^ 1
    path = tmp_path / "official.json"
    path.write_bytes(tampered)
    reference["path"] = path.name

    with pytest.raises(FinMindSelectionBundleError, match="evidence digest mismatch"):
        verify_file_reference(tmp_path, reference)


def test_verifier_rejects_tampered_alias_map() -> None:
    bundle = copy.deepcopy(_bundle())
    bundle["selector_contract"]["broad_industry_aliases"]["金融業"] = "金融服務"

    with pytest.raises(FinMindSelectionBundleError, match="contract/alias map"):
        validate_bundle_document(seal_bundle(bundle))


def test_verifier_rejects_tampered_exclusion_set() -> None:
    bundle = copy.deepcopy(_bundle())
    bundle["exclusion_evidence"]["excluded_symbols"].pop()

    with pytest.raises(FinMindSelectionBundleError, match="exclusion set"):
        validate_bundle_document(seal_bundle(bundle))


def test_verifier_rejects_tampered_selected_ordering() -> None:
    bundle = copy.deepcopy(_bundle())
    selected = bundle["selection"]["selected"]
    selected[0], selected[1] = selected[1], selected[0]

    with pytest.raises(FinMindSelectionBundleError, match="selected ordering"):
        validate_bundle_document(seal_bundle(bundle))
