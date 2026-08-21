"""Build the immutable result from already sealed credentialed captures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text
from institutional_research.intraday_source_probe import build_probe_result


BASE = PROJECT_ROOT / "research" / "institutional_evaluation" / "acquisition"
PROTOCOL = BASE / "credentialed_intraday_source_probe_protocol_v1_2026-08-20.json"
PROTOCOL_DIGEST = PROTOCOL.with_suffix(".canonical.sha256")
FUGLE_CAPTURE = BASE / "credentialed_intraday_source_probe_capture_v1_2026-08-20-r1"
REFERENCE_CAPTURE = (
    BASE / "credentialed_intraday_source_reference_capture_v1_2026-08-20-r1"
)
RESULT = BASE / "credentialed_intraday_source_probe_result_v1_2026-08-20.json"
RESULT_DIGEST = RESULT.with_suffix(".canonical.sha256")


def main() -> None:
    if RESULT.exists() or RESULT_DIGEST.exists():
        raise RuntimeError("Immutable result artifact already exists")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    protocol_digest = sha256_text(canonical_json(protocol))
    if protocol_digest != PROTOCOL_DIGEST.read_text().strip():
        raise RuntimeError("Probe protocol digest drift detected")
    result = build_probe_result(
        protocol=protocol,
        protocol_digest=protocol_digest,
        fugle_capture_dir=FUGLE_CAPTURE,
        reference_capture_dir=REFERENCE_CAPTURE,
    )
    RESULT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    RESULT_DIGEST.write_text(
        sha256_text(canonical_json(result)) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
