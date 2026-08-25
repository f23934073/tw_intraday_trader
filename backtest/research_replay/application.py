"""Application use cases for sealed R5 revision-2 research replays."""

from __future__ import annotations

import unicodedata
from typing import Any, Mapping
from uuid import uuid4

from backtest.domain import digest

from .domain import (
    CONTROL_CONTRACT_VERSION,
    ResearchReplayIntegrityError,
    require_sha256,
    verify_postflight,
)
from .ports import ReplayArtifactStorePort, SignalReplayRepositoryPort


REQUEST_SCHEMA_VERSION = "r5-signal-ledger-replay-request-v2"
_REQUEST_FIELDS = frozenset(
    {
        "request_schema_version",
        "control_contract_version",
        "preflight_digest",
        "expected_registration_revision",
        "actor_id",
        "change_note",
    }
)


class SignalReplayConflict(ValueError):
    """A replay mutation conflicts with an already sealed operation."""


class SignalReplayNotAccepted(ValueError):
    """Economics were requested before an accepted postflight exists."""


def _strict_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} 必須是無前後空白的 non-empty string")
    if len(value) > maximum or unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{label} 長度或 Unicode 格式不合法")
    return value


def verify_create_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(value)
    if set(request) != _REQUEST_FIELDS:
        missing = sorted(_REQUEST_FIELDS - set(request))
        unknown = sorted(set(request) - _REQUEST_FIELDS)
        raise ValueError(
            f"R5 v2 request schema 不一致：missing={missing}, unknown={unknown}"
        )
    if request["request_schema_version"] != REQUEST_SCHEMA_VERSION:
        raise ValueError("R5 v2 request schema version 不支援")
    if request["control_contract_version"] != CONTROL_CONTRACT_VERSION:
        raise ValueError("R5 v2 control contract version 不支援")
    require_sha256(request["preflight_digest"], "preflight_digest")
    expected = request["expected_registration_revision"]
    if type(expected) is not int or expected != 0:
        raise ValueError("R5 v2 initial expected registration revision 必須是 0")
    _strict_text(request["actor_id"], "actor_id", maximum=200)
    _strict_text(request["change_note"], "change_note", maximum=2000)
    return request


def verify_idempotency_key(value: str) -> str:
    key = _strict_text(value, "Idempotency-Key", maximum=200)
    if len(key) < 8:
        raise ValueError("Idempotency-Key 長度必須介於 8 與 200")
    return key


class SignalReplayApplicationService:
    """Orchestrate immutable artifacts and the durable replay aggregate."""

    def __init__(
        self,
        *,
        repository: SignalReplayRepositoryPort,
        artifacts: ReplayArtifactStorePort,
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts

    def create_replay(
        self,
        *,
        baseline_run_id: str,
        idempotency_key: str,
        request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        baseline = _strict_text(baseline_run_id, "baseline_run_id", maximum=200)
        key = verify_idempotency_key(idempotency_key)
        body = verify_create_request(request)
        request_digest = digest(body)
        replayed = self._repository.replay_create_operation(
            baseline_run_id=baseline,
            idempotency_key=key,
            request_digest=request_digest,
        )
        if replayed is not None:
            return replayed, True
        match = self._artifacts.load_match_plan(body["preflight_digest"])
        match_manifest = dict(match.manifest)
        if match_manifest["baseline_run_id"] != baseline:
            raise ResearchReplayIntegrityError(
                "preflight baseline identity 與 request path 不一致"
            )
        ledger = self._artifacts.load_ledger(
            match_manifest["ledger_manifest_digest"]
        )
        return self._repository.create_replay(
            replay_id=f"replay-{uuid4().hex}",
            baseline_run_id=baseline,
            idempotency_key=key,
            request=body,
            request_digest=request_digest,
            ledger_manifest=ledger.manifest,
            match_manifest=match_manifest,
            ledger_rows=ledger.ledger_rows,
            order_rows=ledger.order_rows,
        )

    def get_replay(self, replay_id: str) -> dict[str, Any]:
        return self._repository.get_replay(
            _strict_text(replay_id, "replay_id", maximum=200)
        )

    def start_replay(self, replay_id: str) -> tuple[dict[str, Any], bool]:
        return self._repository.transition_replay_status(
            _strict_text(replay_id, "replay_id", maximum=200),
            expected_statuses=("SEALED",),
            status="RUNNING",
            progress="0",
            progress_message="R5 v2 replay 已開始",
        )

    def cancel_replay(self, replay_id: str) -> tuple[dict[str, Any], bool]:
        return self._repository.transition_replay_status(
            _strict_text(replay_id, "replay_id", maximum=200),
            expected_statuses=("RUNNING",),
            status="CANCELLING",
            progress=None,
            progress_message="R5 v2 replay 正在取消",
        )

    def mark_cancelled(
        self, replay_id: str, *, progress: str
    ) -> tuple[dict[str, Any], bool]:
        return self._repository.transition_replay_status(
            _strict_text(replay_id, "replay_id", maximum=200),
            expected_statuses=("CANCELLING",),
            status="CANCELLED",
            progress=progress,
            progress_message="R5 v2 replay 已取消",
        )

    def mark_failed(
        self, replay_id: str, *, progress: str, error_message: str
    ) -> tuple[dict[str, Any], bool]:
        return self._repository.transition_replay_status(
            _strict_text(replay_id, "replay_id", maximum=200),
            expected_statuses=("RUNNING",),
            status="FAILED",
            progress=progress,
            progress_message="R5 v2 replay 失敗",
            error_message=_strict_text(
                error_message, "error_message", maximum=4000
            ),
        )

    def publish_result(
        self,
        replay_id: str,
        *,
        result_manifest_digest: str,
        postflight: Mapping[str, Any],
    ) -> dict[str, Any]:
        replay = self.get_replay(replay_id)
        result = self._artifacts.load_result(result_manifest_digest)
        match = self._artifacts.load_match_plan(replay["preflight_digest"])
        ledger = self._artifacts.load_ledger(replay["ledger_manifest_digest"])
        verified_postflight = verify_postflight(postflight)
        return self._repository.publish_result(
            replay["replay_id"],
            ledger_rows=ledger.ledger_rows,
            order_rows=ledger.order_rows,
            match_rows=match.rows,
            result_manifest=result.manifest,
            episode_rows=result.episodes,
            modeled_entry_rows=result.modeled_entries,
            modeled_exit_rows=result.modeled_exits,
            postflight=verified_postflight,
        )

    def get_economics(self, replay_id: str) -> dict[str, Any]:
        replay = _strict_text(replay_id, "replay_id", maximum=200)
        registration = self.get_replay(replay)
        if registration["status"] != "ACCEPTED":
            raise SignalReplayNotAccepted("R5_V2_POSTFLIGHT_NOT_ACCEPTED")
        ledger = self._artifacts.load_ledger(
            registration["ledger_manifest_digest"]
        )
        match = self._artifacts.load_match_plan(registration["preflight_digest"])
        artifact = self._artifacts.load_result(
            registration["result_manifest_digest"]
        )
        durable = self._repository.get_accepted_result(
            replay,
            ledger_rows=ledger.ledger_rows,
            order_rows=ledger.order_rows,
            match_rows=match.rows,
        )
        if (
            artifact.manifest != durable["result_manifest"]
            or list(artifact.episodes) != durable["episodes"]
            or list(artifact.modeled_entries) != durable["modeled_entries"]
            or list(artifact.modeled_exits) != durable["modeled_exits"]
        ):
            raise ResearchReplayIntegrityError(
                "accepted PostgreSQL result 與 immutable artifact 不一致"
            )
        return durable
