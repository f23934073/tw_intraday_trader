"""Capture fixed Shioaji control Kbars for the frozen Fugle probe."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text
from market_data.daily_kbar_qualification import build_capture_artifact
from market_data.provider import ShioajiProvider


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "research"
    / "institutional_evaluation"
    / "acquisition"
    / "credentialed_intraday_source_probe_protocol_v1_2026-08-20.json"
)
PROTOCOL_DIGEST_PATH = PROTOCOL_PATH.with_suffix(".canonical.sha256")
OUTPUT_PATH = PROTOCOL_PATH.with_name(
    "credentialed_intraday_source_reference_capture_v1_2026-08-20-r1"
)


def main() -> None:
    if OUTPUT_PATH.exists():
        raise RuntimeError(f"Immutable capture already exists: {OUTPUT_PATH}")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol_digest = sha256_text(canonical_json(protocol))
    if protocol_digest != PROTOCOL_DIGEST_PATH.read_text(encoding="utf-8").strip():
        raise RuntimeError("Probe protocol digest drift detected")

    load_dotenv(PROJECT_ROOT / ".env")
    os.environ["SJ_SIMULATION"] = "true"
    symbols = ["1240", "12561", "2330", "2317"]
    session_date = date.fromisoformat("2026-08-18")
    staging = Path(tempfile.mkdtemp(prefix="shioaji-probe-", dir=OUTPUT_PATH.parent))
    provider: ShioajiProvider | None = None
    records: list[dict[str, object]] = []
    try:
        provider = ShioajiProvider()
        sdk_version = provider.environment_identity.split(":")[1]
        for symbol in symbols:
            contract = provider._api.Contracts.Stocks[symbol]
            if contract is None:
                raise RuntimeError(f"Shioaji contract missing: {symbol}")
            queried_at = datetime.now().astimezone()
            raw_kbars = provider._query_contract_kbars(
                contract=contract,
                label=symbol,
                start=session_date,
                end=session_date,
            )
            capture = build_capture_artifact(
                capture_name=f"credentialed_intraday_probe_reference_{symbol}",
                symbol=symbol,
                query_start=session_date,
                query_end=session_date,
                queried_at=queried_at,
                sdk_version=sdk_version,
                raw_kbars=raw_kbars,
                extra_fields=("Amount",),
            )
            capture_name = f"shioaji_{symbol}.capture.json"
            capture_text = canonical_json(capture)
            (staging / capture_name).write_text(
                json.dumps(capture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            records.append(
                {
                    "capture_file": capture_name,
                    "capture_sha256": sha256_text(capture_text),
                    "field_counts": capture["field_counts"],
                    "queried_at": capture["queried_at"],
                    "raw_rows_digest": capture["raw_rows_digest"],
                    "symbol": symbol,
                }
            )
            print(
                f"captured reference symbol={symbol} "
                f"rows={capture['field_counts']['ts']}"
            )

        manifest = {
            "artifact_id": (
                "credentialed-intraday-source-reference-capture-v1-2026-08-20-r1"
            ),
            "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
            "environment_identity": provider.environment_identity,
            "protocol_reference": {
                "artifact_id": protocol["artifact_id"],
                "canonical_sha256": protocol_digest,
            },
            "records": records,
            "schema_version": "credentialed_intraday_source_reference_capture_v1",
            "trade_subscription_enabled": False,
        }
        manifest_text = canonical_json(manifest)
        (staging / "capture_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "capture_manifest.canonical.sha256").write_text(
            sha256_text(manifest_text) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, OUTPUT_PATH)
        print(f"sealed reference capture={OUTPUT_PATH}")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    main()
