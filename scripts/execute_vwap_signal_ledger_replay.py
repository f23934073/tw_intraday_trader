#!/usr/bin/env python3
"""Execute the provider-free R5 v2 G4 formal one-lot replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from backtest.research_replay.application import (
    REQUEST_SCHEMA_VERSION,
    SignalReplayApplicationService,
)
from backtest.research_replay.artifact_store import ReplayArtifactStore
from backtest.research_replay.domain import CONTROL_CONTRACT_VERSION
from backtest.research_replay.postgres_repository import (
    SignalReplayPostgresRepository,
)


class ProviderFreeExternalCallAudit:
    """Structural evidence for a composition with no external call ports."""

    @staticmethod
    def snapshot() -> dict[str, int]:
        return {
            "strategy_evaluation_count": 0,
            "provider_call_count": 0,
            "broker_call_count": 0,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute the provider-free R5 v2 G4 formal replay",
    )
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--preflight-digest", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--change-note", required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="defaults to BACKTEST_DATA_DIR/research_replay",
    )
    parser.add_argument("--chunk-size", type=int, default=4096)
    parser.add_argument("--merge-fan-in", type=int, default=64)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.chunk_size < 1 or args.merge_fan_in < 2:
        raise ValueError("chunk-size 必須為正數，merge-fan-in 至少為 2")

    from config import backtest as backtest_settings

    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R5 v2 G4 replay requires application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請先安裝 tw-intraday-trader[postgres]") from error

    artifact_root = args.artifact_root or (
        backtest_settings.BACKTEST_DATA_DIR / "research_replay"
    )
    artifacts = ReplayArtifactStore(
        artifact_root,
        chunk_size=args.chunk_size,
        merge_fan_in=args.merge_fan_in,
    )
    request = {
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "preflight_digest": args.preflight_digest,
        "expected_registration_revision": 0,
        "actor_id": args.actor_id,
        "change_note": args.change_note,
    }
    replay_id: str | None = None
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        repository = SignalReplayPostgresRepository(connection)
        service = SignalReplayApplicationService(
            repository=repository,
            artifacts=artifacts,
        )
        created, _ = service.create_replay(
            baseline_run_id=args.baseline_run_id,
            idempotency_key=args.idempotency_key,
            request=request,
        )
        replay_id = created["replay_id"]
        try:
            executed = service.execute_replay(
                replay_id,
                external_calls=ProviderFreeExternalCallAudit(),
            )
        except Exception as error:
            try:
                current = service.get_replay(replay_id)
                if current["status"] == "CANCELLING":
                    service.mark_cancelled(
                        replay_id,
                        progress=current["progress"],
                    )
                elif current["status"] == "RUNNING":
                    service.mark_failed(
                        replay_id,
                        progress=current["progress"],
                        error_message=(
                            f"{type(error).__name__}: {error}"
                        )[:4000],
                    )
            except Exception:
                pass
            raise

    registration = executed["registration"]
    postflight = executed["postflight"]
    output = {
        "schema_version": "r5-signal-ledger-replay-execution-output-v2",
        "baseline_run_id": registration["baseline_run_id"],
        "replay_id": registration["replay_id"],
        "registration_revision": registration["revision"],
        "status": registration["status"],
        "preflight_digest": registration["preflight_digest"],
        "ledger_manifest_digest": registration["ledger_manifest_digest"],
        "result_manifest_digest": executed["result_manifest"][
            "result_manifest_digest"
        ],
        "postflight_digest": postflight["postflight_digest"],
        "episode_count": postflight["diagnostics"]["episode_count"],
        "provider_call_count": postflight["diagnostics"]["provider_call_count"],
        "broker_call_count": postflight["diagnostics"]["broker_call_count"],
        "summary": executed["result_manifest"]["summary"],
        "result_path": executed["result_path"],
        "replayed": executed["replayed"],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if registration["status"] == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
