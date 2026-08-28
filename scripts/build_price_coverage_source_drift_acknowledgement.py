"""Build or check the reviewed r2 price-coverage source-drift acknowledgement."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from institutional_data.serialization import canonical_json, sha256_text  # noqa: E402


ACQUISITION = PROJECT_ROOT / "research/institutional_evaluation/acquisition"
R2_CONFIGURATION = (
    ACQUISITION / "price_coverage_scan_configuration_v1_2026-08-21-r2.json"
)
ACKNOWLEDGEMENT = (
    ACQUISITION / "price_coverage_source_drift_acknowledgement_v1.json"
)
ACKNOWLEDGED_ON = "2026-08-28"
DRIFT_STATUS = "ACKNOWLEDGED_POST_FREEZE_EVOLUTION"
SOURCE_FIELDS = (
    ("backtest/historical_download.py", "historical_downloader_source_sha256"),
    ("scripts/download_backtest_history.py", "cli_source_sha256"),
)
RATIONALE = (
    "r2 是 2026-08-21 凍結的一次性 scan 設定；其 pin 記錄的是當時執行 "
    "scan 的原始碼身分，不是對未來原始碼的約束。此後的合法演進不使 r2 "
    "失效，也不改變已產生的 coverage 觀測。"
)
REUSE_CONSTRAINT = (
    "任何重新執行、續跑或延伸此 r2 coverage scan 的行為，必須先重新凍結一份新的 "
    "scan configuration（r3 或更新），不得沿用 r2 的 pin 宣稱原始碼身分。"
)


class SourceDriftAcknowledgementError(RuntimeError):
    """The acknowledgement cannot be built or treated as reviewed-current."""


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SourceDriftAcknowledgementError(f"{path.name} must be a JSON object")
    return payload


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def canonical_seal_errors(
    payload: Mapping[str, object], expected_digest: object, *, label: str
) -> list[str]:
    if not _is_sha256(expected_digest):
        return [f"{label} canonical sidecar is not a lowercase SHA-256"]
    observed_digest = sha256_text(canonical_json(payload))
    if observed_digest != expected_digest:
        return [
            f"{label} canonical digest mismatch: "
            f"expected {expected_digest}, observed {observed_digest}"
        ]
    return []


def evaluate_source_drift(
    pins: Mapping[str, str],
    live_shas: Mapping[str, str],
    acknowledgement: Mapping[str, object],
) -> list[str]:
    """Return every fail-closed violation in the reviewed source-drift binding."""

    errors: list[str] = []
    raw_entries = acknowledgement.get("pinned_sources")
    if not isinstance(raw_entries, list):
        return ["source drift acknowledgement pinned_sources must be a list"]

    entries: dict[str, Mapping[str, object]] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            errors.append("source drift acknowledgement entry must be an object")
            continue
        path = raw_entry.get("path")
        if not isinstance(path, str) or not path:
            errors.append("source drift acknowledgement entry path is invalid")
            continue
        if path in entries:
            errors.append(f"duplicate source drift acknowledgement: {path}")
            continue
        entries[path] = raw_entry

    for path, pinned_sha in pins.items():
        live_sha = live_shas.get(path)
        if not _is_sha256(pinned_sha):
            errors.append(f"artifact source pin is invalid: {path}")
            continue
        if not _is_sha256(live_sha):
            errors.append(f"live source SHA is unavailable or invalid: {path}")
            continue
        entry = entries.pop(path, None)
        if live_sha == pinned_sha:
            if entry is not None:
                errors.append(f"source drift acknowledgement is no longer needed: {path}")
            continue
        if entry is None:
            errors.append(f"unacknowledged source drift: {path}")
            continue
        if entry.get("pinned_sha256") != pinned_sha:
            errors.append(f"source drift acknowledgement pin mismatch: {path}")
        if entry.get("observed_sha256_at_acknowledgement") != live_sha:
            errors.append(f"stale source drift acknowledgement: {path}")
        if entry.get("drift_status") != DRIFT_STATUS:
            errors.append(f"source drift acknowledgement status is not reviewed: {path}")

    for path in sorted(entries):
        errors.append(f"unexpected source drift acknowledgement entry: {path}")
    return errors


def _commits_since_freeze(path: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "log",
            "--format=%h",
            "--since=2026-08-21",
            "--",
            path,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SourceDriftAcknowledgementError(
            f"cannot derive causing commits for {path}: {result.stderr.strip()}"
        )
    commits = [line for line in result.stdout.splitlines() if line]
    if not commits:
        raise SourceDriftAcknowledgementError(
            f"drifted source has no post-freeze commit history: {path}"
        )
    return commits


def _configuration_and_digest() -> tuple[dict[str, Any], str]:
    configuration = _load_object(R2_CONFIGURATION)
    digest = R2_CONFIGURATION.with_suffix(".canonical.sha256").read_text(
        encoding="utf-8"
    ).strip()
    errors = canonical_seal_errors(configuration, digest, label="r2 configuration")
    if errors:
        raise SourceDriftAcknowledgementError("; ".join(errors))
    return configuration, digest


def build_acknowledgement() -> dict[str, object]:
    configuration, configuration_digest = _configuration_and_digest()
    scan = configuration.get("scan_configuration")
    if not isinstance(scan, Mapping):
        raise SourceDriftAcknowledgementError(
            "r2 scan_configuration must be a JSON object"
        )

    pinned_sources: list[dict[str, object]] = []
    for path, field in SOURCE_FIELDS:
        pinned_sha = scan.get(field)
        if not _is_sha256(pinned_sha):
            raise SourceDriftAcknowledgementError(
                f"r2 scan_configuration source pin is invalid: {field}"
            )
        live_sha = _source_sha256(PROJECT_ROOT / path)
        if live_sha == pinned_sha:
            continue
        pinned_sources.append(
            {
                "path": path,
                "pinned_sha256": pinned_sha,
                "observed_sha256_at_acknowledgement": live_sha,
                "drift_status": DRIFT_STATUS,
                "causing_commits": _commits_since_freeze(path),
                "rationale": RATIONALE,
            }
        )

    return {
        "artifact_id": "price-coverage-source-drift-acknowledgement-v1",
        "acknowledged_on": ACKNOWLEDGED_ON,
        "pinned_configuration": {
            "artifact_path": str(R2_CONFIGURATION.relative_to(PROJECT_ROOT)),
            "artifact_canonical_sha256": configuration_digest,
        },
        "pinned_sources": pinned_sources,
        "reuse_constraint": REUSE_CONSTRAINT,
    }


def check_acknowledgement() -> list[str]:
    expected = build_acknowledgement()
    try:
        observed = _load_object(ACKNOWLEDGEMENT)
        sidecar_digest = ACKNOWLEDGEMENT.with_suffix(
            ".canonical.sha256"
        ).read_text(encoding="utf-8").strip()
    except (OSError, json.JSONDecodeError) as error:
        return [f"source drift acknowledgement cannot be read: {error}"]

    errors = canonical_seal_errors(
        observed, sidecar_digest, label="source drift acknowledgement"
    )
    if observed != expected:
        errors.append(
            "source drift acknowledgement is stale or differs from the reviewed builder"
        )

    pins = {
        path: str(
            _load_object(R2_CONFIGURATION)["scan_configuration"][field]
        )
        for path, field in SOURCE_FIELDS
    }
    live_shas = {
        path: _source_sha256(PROJECT_ROOT / path) for path, _field in SOURCE_FIELDS
    }
    errors.extend(evaluate_source_drift(pins, live_shas, observed))
    return errors


def _write_acknowledgement(payload: Mapping[str, object]) -> str:
    serialized = canonical_json(payload)
    digest = sha256_text(serialized)
    ACKNOWLEDGEMENT.write_text(serialized + "\n", encoding="utf-8")
    ACKNOWLEDGEMENT.with_suffix(".canonical.sha256").write_text(
        digest + "\n", encoding="utf-8"
    )
    return digest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing acknowledgement without writing files",
    )
    args = parser.parse_args(argv)

    try:
        if args.check:
            errors = check_acknowledgement()
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            print("price coverage source drift acknowledgement is current")
            return 0
        payload = build_acknowledgement()
        digest = _write_acknowledgement(payload)
    except (OSError, json.JSONDecodeError, SourceDriftAcknowledgementError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "wrote price coverage source drift acknowledgement "
        f"entries={len(payload['pinned_sources'])} digest={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
