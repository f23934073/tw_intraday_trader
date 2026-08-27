"""Derive a reviewed-ready candidate from one sealed Fugle HTTP capture."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.domain import canonical_json  # noqa: E402
from backtest.fugle_source_repair import build_fugle_repair_candidate  # noqa: E402


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive canonical bars offline from a sealed Fugle capture"
    )
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--official-evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    capture_dir = (
        args.capture_dir
        if args.capture_dir.is_absolute()
        else PROJECT_ROOT / args.capture_dir
    )
    evidence_path = (
        args.official_evidence
        if args.official_evidence.is_absolute()
        else PROJECT_ROOT / args.official_evidence
    )
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else PROJECT_ROOT / args.output_dir
    )
    if output_dir.exists():
        raise RuntimeError(f"immutable derived candidate already exists: {output_dir}")

    metadata = _load_object(capture_dir / "metadata.json")
    capture_manifest = _load_object(capture_dir / "manifest.json")
    official = _load_object(evidence_path)
    target = official.get("target")
    reference = official.get("official_reference")
    if not isinstance(target, dict) or not isinstance(reference, dict):
        raise ValueError("official evidence has an unsupported schema")
    symbol = str(target.get("symbol"))
    session_text = str(target.get("session_date"))
    if metadata.get("symbol") != symbol or metadata.get("session_date") != session_text:
        raise ValueError("capture and official evidence targets differ")

    raw_body = (capture_dir / "raw_response.bin").read_bytes()
    raw_sha256 = hashlib.sha256(raw_body).hexdigest()
    if raw_sha256 != metadata.get("raw_response_sha256"):
        raise ValueError("sealed Fugle raw response digest mismatch")
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError("Fugle response root is not an object")
    candidate = build_fugle_repair_candidate(
        payload,
        symbol=symbol,
        session_date=date.fromisoformat(session_text),
        official_reference=reference,
    )
    bars = [bar.to_dict() for bar in candidate.bars]
    validation = dict(candidate.validation)
    validation.update(
        {
            "parent_capture_status": capture_manifest.get("status"),
            "raw_response_sha256": raw_sha256,
            "status": "ACCEPTED_FOR_PROPOSAL",
        }
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="fugle-derived-", dir=output_dir.parent))
    try:
        _write_json(staging / "canonical_bars.json", bars)
        _write_json(staging / "validation.json", validation)
        manifest = {
            "artifact_id": f"fugle-source-repair-candidate-{symbol}-{session_text.replace('-', '')}-v1",
            "bar_count": len(bars),
            "canonical_bars_sha256": hashlib.sha256(
                canonical_json(bars).encode("utf-8")
            ).hexdigest(),
            "case_id": metadata["case_id"],
            "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
            "observed_at": metadata["retrieved_at"],
            "parent_capture_manifest_sha256": hashlib.sha256(
                canonical_json(capture_manifest).encode("utf-8")
            ).hexdigest(),
            "raw_response_sha256": raw_sha256,
            "schema_version": "fugle-source-repair-derived-candidate-v1",
            "source_uri": metadata["source_uri"],
            "status": "ACCEPTED_FOR_PROPOSAL",
            "validation_sha256": hashlib.sha256(
                canonical_json(validation).encode("utf-8")
            ).hexdigest(),
        }
        _write_json(staging / "manifest.json", manifest)
        (staging / "manifest.canonical.sha256").write_text(
            hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
            + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output_dir)
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True), flush=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
