#!/usr/bin/env python3
"""Build the provider-free R5 v2 G3 full-Dataset preflight artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from backtest.domain import canonical_json
from backtest.research_replay.application import SignalReplayPreflightService
from backtest.research_replay.artifact_store import ReplayArtifactStore
from backtest.research_replay.dataset_adapter import CanonicalFullDatasetAdapter
from backtest.research_replay.postgres_repository import (
    SignalReplayPostgresRepository,
)


class ProviderFreeExternalCallAudit:
    """Structural audit for a composition with no evaluation/provider/broker ports."""

    @staticmethod
    def snapshot() -> dict[str, int]:
        return {
            "strategy_evaluation_count": 0,
            "provider_call_count": 0,
            "broker_call_count": 0,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the read-only, provider-free R5 v2 G3 preflight",
    )
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="defaults to BACKTEST_DATA_DIR/research_replay",
    )
    parser.add_argument(
        "--audit-out",
        type=Path,
        default=None,
        help="optional canonical operation-audit output path",
    )
    parser.add_argument("--chunk-size", type=int, default=4096)
    parser.add_argument("--merge-fan-in", type=int, default=64)
    parser.add_argument("--progress-every", type=int, default=1_000_000)
    return parser


def _progress(current: int, total: int) -> None:
    print(
        json.dumps(
            {
                "event": "r5_v2_g3_dataset_progress",
                "bars_read": current,
                "bars_total": total,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _write_audit(path: Path, audit: dict[str, object]) -> None:
    payload = (canonical_json(audit) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"G3 operation audit conflict：{path}")
        return
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.chunk_size < 1 or args.merge_fan_in < 2 or args.progress_every < 1:
        raise ValueError("chunk/progress 必須為正數，merge fan-in 至少為 2")

    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R5 v2 G3 preflight requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error

    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        repository = SignalReplayPostgresRepository(
            connection,
            apply_schema=False,
        )
        evidence = repository.load_preflight_evidence(args.baseline_run_id)

    artifact_root = args.artifact_root or (
        backtest_settings.BACKTEST_DATA_DIR / "research_replay"
    )
    dataset = CanonicalFullDatasetAdapter(
        root=backtest_settings.BACKTEST_DATA_DIR,
        registered_manifest=evidence.dataset_manifest,
        progress_every=args.progress_every,
        progress=_progress,
    )
    service = SignalReplayPreflightService(
        artifacts=ReplayArtifactStore(
            artifact_root,
            chunk_size=args.chunk_size,
            merge_fan_in=args.merge_fan_in,
        )
    )
    result = service.build_full_preflight(
        evidence=evidence,
        dataset=dataset,
        external_calls=ProviderFreeExternalCallAudit(),
    )
    audit = result.to_audit_dict()
    audit_out = args.audit_out or (
        artifact_root
        / "preflight_audits"
        / f"{audit['preflight_digest']}.json"
    )
    _write_audit(audit_out, audit)
    print(
        json.dumps(
            {**audit, "audit_path": str(audit_out)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
