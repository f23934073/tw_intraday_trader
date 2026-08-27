from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from backtest.atomic_benchmark.application import (
    FROZEN_VERSION_INVENTORY,
    AtomicBenchmarkApplicationService,
    current_benchmark_build_binding,
    frozen_hypothesis_specs,
    historical_protocol_core,
    matrix_activation_request_from_inventory,
    matrix_seal_request_from_inventory,
    verify_matrix_seal_request,
)
from backtest.atomic_benchmark.domain import (
    DatasetIdentityRejected,
    HYPOTHESIS_SPEC_DIGESTS,
    PostgresTransientUnavailable,
    PROTOCOL_CORE_DIGEST,
    RESEARCH_BASELINE_DIGEST,
    validate_attempt_transition,
    verify_integrity_diagnostic_codes,
)
from backtest.atomic_benchmark.result_reader import BenchmarkResultReader
from backtest.atomic_benchmark.repository import AtomicBenchmarkConflict
from backtest.domain import digest


ROOT = Path(__file__).resolve().parents[1]


def _request():
    return matrix_seal_request_from_inventory(
        version_inventory=FROZEN_VERSION_INVENTORY,
        repository_root=ROOT,
        actor_id="local-researcher",
        change_note="seal frozen R6 matrix",
    )


class _MatrixRepository:
    def __init__(self) -> None:
        self.operations = {}
        self.mutations = 0

    def seal_matrix(self, **values):
        key = values["idempotency_key"]
        operation = self.operations.get(key)
        if operation is not None:
            if operation[0] != values["request_digest"]:
                raise AtomicBenchmarkConflict("R6_IDEMPOTENCY_CONFLICT")
            return operation[1], True
        build = values["build"]
        result = {
            "schema_version": "r6-matrix-seal-result-v1",
            "family_id": build.family_id,
            "matrix_id": build.matrix_id,
            "matrix_revision": 1,
            "registration_digest": build.registration_digest,
            "family_head_sequence": 0,
            "status": "SEALED",
        }
        self.operations[key] = (values["request_digest"], result)
        self.mutations += 1
        return result, False

    def get_matrix(self, family_id):
        return {"family_id": family_id, "status": "SEALED"}

    def register_preflight(self, **values):
        request = values["request"]
        key = values["idempotency_key"]
        operation = self.operations.get(key)
        if operation is not None:
            if operation[0] != values["request_digest"]:
                raise AtomicBenchmarkConflict("R6_IDEMPOTENCY_CONFLICT")
            return operation[1], True
        result = {
            "schema_version": "r6-preflight-register-result-v1",
            "family_id": request["family_id"],
            "matrix_id": request["matrix_id"],
            "matrix_revision": 2,
            "preflight_id": request["preflight_id"],
            "preflight_digest": request["preflight_digest"],
            "eligibility_manifest_digest": request[
                "eligibility_manifest_digest"
            ],
            "preflight_registration_digest": request[
                "preflight_registration_digest"
            ],
            "status": "ACCEPTED",
            "family_head_sequence": 0,
            "attempt_count": 0,
        }
        self.operations[key] = (values["request_digest"], result)
        self.mutations += 1
        return result, False


def test_frozen_identity_bodies_rebuild_exact_g0_roots() -> None:
    request = _request()
    assert digest(request["research_baseline"]) == RESEARCH_BASELINE_DIGEST
    assert request["protocol_core"] == historical_protocol_core()
    assert [digest(row) for row in frozen_hypothesis_specs()] == [
        HYPOTHESIS_SPEC_DIGESTS[index] for index in range(1, 8)
    ]
    _, build = verify_matrix_seal_request(request)
    assert len(build.slots) == 7
    assert build.registration["registered_slots"] == list(range(1, 8))

    activation = matrix_activation_request_from_inventory(
        version_inventory=FROZEN_VERSION_INVENTORY,
        repository_root=ROOT,
        actor_id="local-researcher",
        change_note="activate A1 matrix revision 2",
    )
    assert digest(activation["protocol_core"]) == PROTOCOL_CORE_DIGEST


def test_build_binding_covers_six_sources_and_migration_bytes() -> None:
    binding = current_benchmark_build_binding(ROOT)
    assert binding["protocol_core_digest"] == PROTOCOL_CORE_DIGEST
    assert len(binding["algorithm_implementation_digest"]) == 64
    assert len(binding["persistence_schema_digest"]) == 64
    assert len(binding["preflight_implementation_digest"]) == 64


def test_preflight_registration_builds_exact_durable_identity() -> None:
    repository = _MatrixRepository()
    service = AtomicBenchmarkApplicationService(repository)
    manifest = {
        "family_id": "family-test",
        "matrix_id": "matrix-test",
        "protocol_core_digest": "a" * 64,
        "dataset_id": "dataset-test",
        "dataset_digest": "b" * 64,
        "dataset_bars_sha256": "c" * 64,
        "dataset_binding_revision": 1,
        "eligibility_manifest_digest": "d" * 64,
        "preflight_digest": "e" * 64,
        "preflight_implementation_digest": "f" * 64,
    }
    first = service.register_preflight(
        manifest=manifest,
        matrix_registration_digest="9" * 64,
        artifact_locator="/tmp/r6-preflight",
        idempotency_key="register-preflight",
        actor_id="operator",
        change_note="register verified A1 root",
    )
    second = service.register_preflight(
        manifest=manifest,
        matrix_registration_digest="9" * 64,
        artifact_locator="/tmp/r6-preflight",
        idempotency_key="register-preflight",
        actor_id="operator",
        change_note="register verified A1 root",
    )
    assert first["preflight_id"] == f"r6-preflight-sha256-{'e' * 64}"
    assert second["replayed"] is True


def test_application_replays_same_key_without_second_mutation() -> None:
    repository = _MatrixRepository()
    service = AtomicBenchmarkApplicationService(repository)
    first = service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    second = service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert first["matrix_id"] == second["matrix_id"]
    assert repository.mutations == 1


def test_same_key_different_digest_conflicts() -> None:
    repository = _MatrixRepository()
    service = AtomicBenchmarkApplicationService(repository)
    service.seal_matrix(request=_request(), idempotency_key="seal-r6")
    changed = _request()
    changed["change_note"] = "different note"
    with pytest.raises(AtomicBenchmarkConflict, match="IDEMPOTENCY"):
        service.seal_matrix(request=changed, idempotency_key="seal-r6")


@pytest.mark.parametrize("invalid_revision", (False, 0.0, "0", 1))
def test_expected_head_requires_exact_integer_zero(invalid_revision) -> None:
    request = _request()
    request["expected_family_head_sequence"] = invalid_revision
    with pytest.raises(AtomicBenchmarkConflict, match="HEAD_SEQUENCE"):
        verify_matrix_seal_request(request)


def test_slot_or_version_identity_drift_fails_closed() -> None:
    request = _request()
    changed = deepcopy(request)
    changed["slots"][0]["version_binding"]["strategy_version_id"] = "other-version"
    with pytest.raises(ValueError, match="projection|slot binding"):
        verify_matrix_seal_request(changed)


class _VisibilityRepository:
    def __init__(self, released: bool) -> None:
        self.released = released
        self.public_reads = 0

    def get_family_visibility(self, family_id):
        return {
            "schema_version": "r6-family-visibility-v1",
            "family_id": family_id,
            "release_state": "RELEASED" if self.released else "NOT_READY",
            "attempts": [],
        }

    def get_verified_public_bundle(self, family_id):
        self.public_reads += 1
        return None


def test_result_reader_never_reads_public_payload_before_release() -> None:
    repository = _VisibilityRepository(released=False)
    result = BenchmarkResultReader(repository).read_family("family")
    assert result["release_state"] == "NOT_READY"
    assert repository.public_reads == 0


def test_released_state_without_verified_bundle_fails_closed() -> None:
    repository = _VisibilityRepository(released=True)
    with pytest.raises(RuntimeError, match="PUBLIC_BUNDLE_INTEGRITY"):
        BenchmarkResultReader(repository).read_family("family")


def test_attempt_state_machine_freezes_retry_and_generation_four_terminals() -> None:
    assert validate_attempt_transition(
        current_status="FAILED_RETRYABLE",
        next_status="RUNNING",
        retry_generation=3,
        outcome_code="ATTEMPT_RETRY_STARTED",
    ) == 4
    assert validate_attempt_transition(
        current_status="RUNNING",
        next_status="FAILED_FINAL",
        retry_generation=4,
        outcome_code="POSTGRES_TRANSIENT_UNAVAILABLE",
    ) == 4
    assert validate_attempt_transition(
        current_status="CANCELLING",
        next_status="CANCELLED_FINAL",
        retry_generation=4,
        outcome_code="OPERATOR_CANCELLED",
    ) == 4
    with pytest.raises(ValueError, match="transition rejected"):
        validate_attempt_transition(
            current_status="RUNNING",
            next_status="FAILED_RETRYABLE",
            retry_generation=4,
            outcome_code="POSTGRES_TRANSIENT_UNAVAILABLE",
        )


class _TransitionRepository:
    def __init__(self) -> None:
        self.last = None

    def transition_attempt(self, **values):
        self.last = values
        return {
            "schema_version": "r6-attempt-transition-result-v1",
            "family_id": values["family_id"],
            "matrix_id": values["matrix_id"],
            "attempt_id": values["attempt_id"],
            "status": values["next_status"],
            "attempt_revision": values["expected_revision"] + 1,
            "retry_generation": values["retry_generation"],
            "progress": values["progress"],
            "outcome_code": values["outcome_code"],
        }, False


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_outcome"),
    (
        (
            DatasetIdentityRejected("dataset drift"),
            "REJECTED_FINAL",
            "DATASET_IDENTITY_REJECTED",
        ),
        (
            PostgresTransientUnavailable("temporary"),
            "FAILED_RETRYABLE",
            "POSTGRES_TRANSIENT_UNAVAILABLE",
        ),
        (RuntimeError("unknown"), "FAILED_FINAL", "UNCLASSIFIED_FAILURE"),
    ),
)
def test_worker_failure_classification_is_server_owned(
    error, expected_status, expected_outcome
) -> None:
    repository = _TransitionRepository()
    service = AtomicBenchmarkApplicationService(repository)
    result = service.record_attempt_failure(
        family_id="family",
        matrix_id="matrix",
        attempt_id="attempt",
        expected_revision=1,
        retry_generation=1,
        progress="0.25",
        error=error,
        idempotency_key=f"failure-{expected_outcome}",
        actor_id="worker",
    )
    assert result["status"] == expected_status
    assert repository.last["outcome_code"] == expected_outcome
    assert not hasattr(service, "transition_attempt")


def test_integrity_diagnostic_codes_reject_observed_values_and_aliases() -> None:
    assert verify_integrity_diagnostic_codes(
        ["DATASET_IDENTITY_VERIFIED", "PARITY_VERIFIED"]
    ) == ["DATASET_IDENTITY_VERIFIED", "PARITY_VERIFIED"]
    for value in (["secret_pnl=999"], ["PARITY_VERIFIED", 1], ["PARITY_VERIFIED"] * 2):
        with pytest.raises(ValueError, match="diagnostic"):
            verify_integrity_diagnostic_codes(value)
