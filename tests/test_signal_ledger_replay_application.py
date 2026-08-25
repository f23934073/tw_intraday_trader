from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from backtest.research_replay.application import (
    REQUEST_SCHEMA_VERSION,
    SignalReplayApplicationService,
    SignalReplayNotAccepted,
    verify_create_request,
)
from backtest.research_replay.domain import CONTROL_CONTRACT_VERSION
from tests.test_signal_ledger_replay_artifacts import _publish_all


def _request(preflight_digest: str) -> dict[str, object]:
    return {
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "preflight_digest": preflight_digest,
        "expected_registration_revision": 0,
        "actor_id": "local-researcher",
        "change_note": "seal independent one-lot replay",
    }


class _Repository:
    def __init__(self, registration, accepted_result=None):
        self.registration = registration
        self.accepted_result = accepted_result
        self.created = None
        self.transitions = []
        self.published = None
        self.accepted_read = None
        self.operation_replay = None

    def replay_create_operation(self, **values):
        self.operation_replay_request = values
        return deepcopy(self.operation_replay)

    def create_replay(self, **values):
        self.created = values
        return {
            "schema_version": "r5-signal-ledger-replay-operation-result-v2",
            "baseline_run_id": values["baseline_run_id"],
            "control_contract_version": CONTROL_CONTRACT_VERSION,
            "revision": 1,
            "replay_id": "replay-1",
            "preflight_digest": values["request"]["preflight_digest"],
            "ledger_manifest_digest": values["ledger_manifest"][
                "ledger_manifest_digest"
            ],
            "status": "SEALED",
            "postflight_digest": None,
            "result_manifest_digest": None,
        }, False

    def get_replay(self, replay_id):
        assert replay_id == "replay-1"
        return dict(self.registration)

    def transition_replay_status(self, replay_id, **values):
        self.transitions.append((replay_id, values))
        return {**self.registration, "status": values["status"]}, False

    def publish_result(self, replay_id, **values):
        self.published = (replay_id, values)
        return {**self.registration, "status": values["postflight"]["verdict"]}

    def get_accepted_result(self, replay_id, **values):
        self.accepted_read = (replay_id, values)
        return deepcopy(self.accepted_result)


def _service(tmp_path, *, status="SEALED"):
    published = _publish_all(tmp_path)
    (
        store,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
        *_paths,
    ) = published
    registration = {
        "replay_id": "replay-1",
        "baseline_run_id": "run-baseline",
        "revision": 1,
        "status": status,
        "preflight_digest": match_manifest["match_plan_manifest_digest"],
        "ledger_manifest_digest": ledger_manifest["ledger_manifest_digest"],
        "result_manifest_digest": (
            result_manifest["result_manifest_digest"]
            if status == "ACCEPTED"
            else None
        ),
    }
    accepted = {
        "result_manifest_digest": result_manifest["result_manifest_digest"],
        "result_manifest": result_manifest,
        "postflight": {},
        "episodes": list(replay.episodes),
        "modeled_entries": list(replay.modeled_entries),
        "modeled_exits": list(replay.modeled_exits),
    }
    repository = _Repository(registration, accepted)
    return (
        SignalReplayApplicationService(repository=repository, artifacts=store),
        repository,
        ledger,
        derivation,
        match,
        result_manifest,
    )


def test_request_is_strict_and_rejects_hidden_execution_overrides(tmp_path) -> None:
    service, *_ = _service(tmp_path)
    request = _request(service.get_replay("replay-1")["preflight_digest"])
    assert verify_create_request(request) == request

    for field, value in (
        ("shares", 1000),
        ("commission_rate", "0"),
        ("dataset_id", "other"),
        ("strategy_id", "other"),
    ):
        hostile = {**request, field: value}
        with pytest.raises(ValueError, match="unknown"):
            verify_create_request(hostile)

    for alias in (False, 0.0, Decimal("0"), "0"):
        invalid_revision = {**request, "expected_registration_revision": alias}
        with pytest.raises(ValueError, match="revision"):
            verify_create_request(invalid_revision)


def test_create_loads_exact_artifacts_and_passes_no_locator_to_repository(tmp_path) -> None:
    service, repository, ledger, derivation, match, _ = _service(tmp_path)
    preflight = service.get_replay("replay-1")["preflight_digest"]

    result, replayed = service.create_replay(
        baseline_run_id="run-baseline",
        idempotency_key="replay-key-0001",
        request=_request(preflight),
    )

    assert replayed is False
    assert result["status"] == "SEALED"
    assert repository.created["ledger_rows"] == ledger.rows
    assert repository.created["order_rows"] == derivation.rows
    assert repository.created["match_manifest"]["matched_exit_count"] == len(
        match.rows
    )
    assert not any("path" in key or "locator" in key for key in repository.created)


def test_response_loss_replay_does_not_reload_current_artifacts(tmp_path) -> None:
    service, repository, *_ = _service(tmp_path)
    preflight = service.get_replay("replay-1")["preflight_digest"]
    repository.operation_replay = {
        "schema_version": "r5-signal-ledger-replay-operation-result-v2",
        "baseline_run_id": "run-baseline",
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "revision": 1,
        "replay_id": "replay-1",
        "preflight_digest": preflight,
        "ledger_manifest_digest": "a" * 64,
        "status": "SEALED",
        "postflight_digest": None,
        "result_manifest_digest": None,
    }
    service._artifacts.load_match_plan = lambda _digest: pytest.fail(
        "durable response-loss replay must not reload artifacts"
    )

    result, replayed = service.create_replay(
        baseline_run_id="run-baseline",
        idempotency_key="replay-key-0001",
        request=_request(preflight),
    )

    assert replayed is True
    assert result == repository.operation_replay
    assert repository.created is None


def test_short_idempotency_key_and_baseline_artifact_mismatch_fail_closed(tmp_path) -> None:
    service, *_ = _service(tmp_path)
    preflight = service.get_replay("replay-1")["preflight_digest"]
    with pytest.raises(ValueError, match="Idempotency-Key"):
        service.create_replay(
            baseline_run_id="run-baseline",
            idempotency_key="short",
            request=_request(preflight),
        )
    with pytest.raises(ValueError, match="baseline"):
        service.create_replay(
            baseline_run_id="other-baseline",
            idempotency_key="replay-key-0002",
            request=_request(preflight),
        )


def test_cancel_and_failure_use_explicit_status_cas_contract(tmp_path) -> None:
    service, repository, *_ = _service(tmp_path, status="RUNNING")

    service.cancel_replay("replay-1")
    service.mark_cancelled("replay-1", progress="0.125")
    service.mark_failed(
        "replay-1", progress="0.5", error_message="synthetic worker failure"
    )

    assert repository.transitions[0][1]["expected_statuses"] == ("RUNNING",)
    assert repository.transitions[0][1]["status"] == "CANCELLING"
    assert repository.transitions[0][1]["progress"] is None
    assert repository.transitions[1][1]["expected_statuses"] == ("CANCELLING",)
    assert repository.transitions[2][1]["status"] == "FAILED"


def test_economics_are_redacted_before_result_artifact_lookup(tmp_path) -> None:
    service, repository, *_ = _service(tmp_path, status="INVALID")

    with pytest.raises(SignalReplayNotAccepted, match="POSTFLIGHT_NOT_ACCEPTED"):
        service.get_economics("replay-1")

    assert repository.accepted_read is None


def test_accepted_economics_require_postgresql_and_artifact_parity(tmp_path) -> None:
    service, repository, ledger, derivation, match, _ = _service(
        tmp_path, status="ACCEPTED"
    )

    result = service.get_economics("replay-1")

    assert result["result_manifest"]["summary"]["episode_count"] == 2
    assert repository.accepted_read[1]["ledger_rows"] == ledger.rows
    assert repository.accepted_read[1]["order_rows"] == derivation.rows
    assert repository.accepted_read[1]["match_rows"] == match.rows
