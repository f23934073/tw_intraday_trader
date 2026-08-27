"""Pure domain contracts for the R6 atomic-entry benchmark.

The module owns immutable identity construction, first-trigger admission,
same-session bar matching, independent one-lot economics, and the frozen
research disposition.  It intentionally has no PostgreSQL, filesystem, HTTP,
provider, broker, or Local Paper dependency.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from backtest.domain import HistoricalBar, canonical_json, digest


VERSION_BINDING_SCHEMA = "r6-version-binding-v1"
HYPOTHESIS_ID_SCHEMA = "r6-hypothesis-id-v1"
SLOT_BINDING_SCHEMA = "r6-slot-binding-v1"
LEDGER_ROW_SCHEMA = "r6-signal-ledger-row-v1"
MATCH_ROW_SCHEMA = "r6-match-row-v1"
EPISODE_ROW_SCHEMA = "r6-episode-row-v1"
SUMMARY_SCHEMA = "r6-result-summary-v1"
BOOTSTRAP_SCHEMA = "r6-daily-cluster-bootstrap-v1"
PARITY_SCHEMA = "r6-layer-parity-projection-v1"
BENCHMARK_BUILD_BINDING_SCHEMA_V1 = "r6-benchmark-build-binding-v1"
BENCHMARK_BUILD_BINDING_SCHEMA = "r6-benchmark-build-binding-v2"
MATRIX_CORE_SCHEMA = "r6-matrix-core-v1"
MATRIX_REGISTRATION_SCHEMA = "r6-matrix-registration-v1"

RESEARCH_BASELINE_DIGEST = (
    "75f9efda41f843d95ddc324d2db7756d33415bcc8dbd274e7bc079062a7d4543"
)
FAMILY_ID = f"r6-family-sha256-{RESEARCH_BASELINE_DIGEST}"
PROTOCOL_CORE_DIGEST_V1 = (
    "1cdd8bf6b30ce0d8334463665ab794b7dd3419273dd4e1c33a03357f30c44ac1"
)
PROTOCOL_CORE_DIGEST = (
    "a4d645b5ea59fca5a90a00c9e14ca117366d87e4f310b88354fc73d03272f471"
)

ALGORITHM_CONTRACT: dict[str, Any] = {
    "calculation_precision": 38,
    "calculation_rounding": "ROUND_HALF_EVEN",
    "canonical_json": "BACKTEST_CANONICAL_JSON_V1",
    "common_signal_cutoff_comparator": "STRICT_LT",
    "common_signal_cutoff_time": "12:45",
    "contract_version": "r6-atomic-entry-benchmark-v2",
    "eligibility_ratio_comparator": "GTE",
    "eligibility_ratio_scale": 18,
    "entry_fill_deadline_comparator": "LTE",
    "entry_fill_deadline_time": "12:45",
    "entry_semantics": (
        "NEXT_OBSERVED_SAME_SYMBOL_SAME_SESSION_KBAR_OPEN_"
        "STRICTLY_AFTER_SIGNAL_AND_NOT_AFTER_COMMON_ENTRY_DEADLINE_V2"
    ),
    "exit_semantics": (
        "EXACT_SAME_SYMBOL_SAME_SESSION_13_30_KBAR_CLOSE_"
        "STRICTLY_AFTER_ENTRY_V2"
    ),
    "incomplete_signal_semantics": (
        "EXCLUDE_INELIGIBLE_SYMBOL_SESSION_BEFORE_ALL_SLOT_ADMISSION_V1"
    ),
    "minimum_eligible_symbol_session_ratio": "0.95",
    "name": "independent-one-lot-atomic-entry-zero-edge-v2",
    "required_terminal_exit_time": "13:30",
    "return_scale": 18,
    "session_eligibility_semantics": (
        "REQUIRE_EXACT_12_45_ENTRY_RESERVE_AND_13_30_TERMINAL_BAR_V1"
    ),
    "shares_semantics": "EXACT_ONE_LOT_1000_SHARES_V1",
    "signal_admission": (
        "FIRST_TRIGGER_PER_SLOT_SYMBOL_ELIGIBLE_SESSION_"
        "BEFORE_COMMON_CUTOFF_V2"
    ),
    "timezone": "Asia/Taipei",
}
ALGORITHM_CONTRACT_DIGEST = digest(ALGORITHM_CONTRACT)
ALGORITHM_CONTRACT_DIGEST_V1 = (
    "ab68f293290ca9e0263c4381ad0984133773f28112c636fe5def6db27210a200"
)

COST_IDENTITY: dict[str, Any] = {
    "commission_rate": "0.001425",
    "entry_slippage_bps": "5",
    "exit_slippage_bps": "5",
    "sell_tax_rate": "0.003",
    "shares": 1000,
}
COST_IDENTITY_DIGEST = digest(COST_IDENTITY)

COMPLETE_QUARTERS = (
    "2023Q4",
    "2024Q1",
    "2024Q2",
    "2024Q3",
    "2024Q4",
    "2025Q1",
    "2025Q2",
    "2025Q3",
    "2025Q4",
    "2026Q1",
    "2026Q2",
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
_RETURN_QUANTUM = Decimal("0.000000000000000001")
_SHA256_CHARS = frozenset("0123456789abcdef")


class AtomicBenchmarkIntegrityError(ValueError):
    """Frozen R6 evidence is incomplete, non-canonical, or inconsistent."""


class WorkerProcessInterrupted(RuntimeError):
    """The benchmark worker stopped before completing the generation."""


class PostgresTransientUnavailable(RuntimeError):
    """A transient PostgreSQL failure interrupted benchmark work."""


class TempStorageUnavailable(RuntimeError):
    """Temporary storage required by the benchmark was unavailable."""


class DatasetIdentityRejected(AtomicBenchmarkIntegrityError):
    """The immutable Dataset identity could not be verified."""


class VersionIdentityRejected(AtomicBenchmarkIntegrityError):
    """The sealed Strategy Version identity could not be verified."""


class FeatureIdentityRejected(AtomicBenchmarkIntegrityError):
    """The frozen Feature identity could not be verified."""


class CanonicalBytesRejected(AtomicBenchmarkIntegrityError):
    """Canonical evidence bytes could not be verified."""


class ParityRejected(AtomicBenchmarkIntegrityError):
    """Adjacent replay layers did not preserve exact multiplicity."""


class CostIdentityRejected(AtomicBenchmarkIntegrityError):
    """The frozen cost identity could not be verified."""


class SummaryRebuildRejected(AtomicBenchmarkIntegrityError):
    """The result summary could not be rebuilt from episodes."""


class PostflightRejected(AtomicBenchmarkIntegrityError):
    """The formal postflight did not accept the replay evidence."""


def require_exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise AtomicBenchmarkIntegrityError(
            f"{label} schema mismatch: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in _SHA256_CHARS for char in value)
    ):
        raise AtomicBenchmarkIntegrityError(f"{label} must be lowercase SHA-256")
    return value


def _require_nfc(value: object, label: str) -> None:
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise AtomicBenchmarkIntegrityError(f"{label} must be Unicode NFC")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _require_nfc(key, f"{label}.key")
            _require_nfc(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_nfc(item, f"{label}[{index}]")


def canonical_object_bytes(value: Mapping[str, Any]) -> bytes:
    _require_nfc(value, "canonical object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AtomicBenchmarkIntegrityError(f"{label} must be integer >= {minimum}")
    return value


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AtomicBenchmarkIntegrityError(f"{label} must be a non-empty string")
    _require_nfc(value, label)
    return value


def decimal_text(
    value: Decimal | str | int,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise AtomicBenchmarkIntegrityError(f"{label} rejects bool/binary float")
    try:
        resolved = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, ValueError) as error:
        raise AtomicBenchmarkIntegrityError(f"{label} is not Decimal") from error
    if not resolved.is_finite():
        raise AtomicBenchmarkIntegrityError(f"{label} must be finite")
    if positive and resolved <= 0:
        raise AtomicBenchmarkIntegrityError(f"{label} must be positive")
    if nonnegative and resolved < 0:
        raise AtomicBenchmarkIntegrityError(f"{label} must be nonnegative")
    if resolved == 0:
        return "0"
    rendered = format(resolved, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def require_decimal_text(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
    maximum_scale: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise AtomicBenchmarkIntegrityError(f"{label} must be Decimal string")
    rendered = decimal_text(value, label, positive=positive, nonnegative=nonnegative)
    if rendered != value:
        raise AtomicBenchmarkIntegrityError(f"{label} Decimal is not canonical")
    if maximum_scale is not None and len(value.partition(".")[2]) > maximum_scale:
        raise AtomicBenchmarkIntegrityError(f"{label} scale exceeds {maximum_scale}")
    return value


def _quantized(value: Decimal, label: str) -> str:
    try:
        with localcontext(_CONTEXT):
            result = value.quantize(_RETURN_QUANTUM, rounding=ROUND_HALF_EVEN)
    except DecimalException as error:
        raise AtomicBenchmarkIntegrityError(f"{label} cannot quantize") from error
    return decimal_text(result, label)


def canonical_timestamp(value: datetime | str, label: str) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise AtomicBenchmarkIntegrityError(f"{label} is not a timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AtomicBenchmarkIntegrityError(f"{label} requires timezone")
    parsed = parsed.astimezone(_TAIPEI)
    if parsed.microsecond:
        raise AtomicBenchmarkIntegrityError(f"{label} rejects microseconds")
    return parsed.isoformat(timespec="seconds")


def require_canonical_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or canonical_timestamp(value, label) != value:
        raise AtomicBenchmarkIntegrityError(f"{label} timestamp is not canonical")
    return value


def require_canonical_date(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AtomicBenchmarkIntegrityError(f"{label} must be date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise AtomicBenchmarkIntegrityError(f"{label} is not a date") from error
    if parsed.isoformat() != value:
        raise AtomicBenchmarkIntegrityError(f"{label} date is not canonical")
    return value


_VERSION_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "hypothesis_spec_digest",
        "strategy_version_id",
        "version_number",
        "strategy_configuration_digest",
        "lifecycle_status",
        "lifecycle_sequence",
        "lifecycle_event_id",
        "lifecycle_projection_digest",
    }
)


def build_version_binding(
    *,
    hypothesis_spec_digest: str,
    strategy_version_id: str,
    version_number: int,
    strategy_configuration_digest: str,
    lifecycle_status: str,
    lifecycle_sequence: int,
    lifecycle_event_id: str,
    lifecycle_projection_digest: str,
) -> dict[str, Any]:
    value = {
        "schema_version": VERSION_BINDING_SCHEMA,
        "hypothesis_spec_digest": hypothesis_spec_digest,
        "strategy_version_id": strategy_version_id,
        "version_number": version_number,
        "strategy_configuration_digest": strategy_configuration_digest,
        "lifecycle_status": lifecycle_status,
        "lifecycle_sequence": lifecycle_sequence,
        "lifecycle_event_id": lifecycle_event_id,
        "lifecycle_projection_digest": lifecycle_projection_digest,
    }
    return verify_version_binding(value)


def verify_version_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    binding = dict(value)
    require_exact_fields(binding, _VERSION_BINDING_FIELDS, "version binding")
    if binding["schema_version"] != VERSION_BINDING_SCHEMA:
        raise AtomicBenchmarkIntegrityError("version binding schema drift")
    for field in (
        "hypothesis_spec_digest",
        "strategy_configuration_digest",
        "lifecycle_projection_digest",
    ):
        require_sha256(binding[field], field)
    _nonempty(binding["strategy_version_id"], "strategy_version_id")
    _integer(binding["version_number"], "version_number", minimum=1)
    _integer(binding["lifecycle_sequence"], "lifecycle_sequence", minimum=1)
    _nonempty(binding["lifecycle_event_id"], "lifecycle_event_id")
    if binding["lifecycle_status"] != "PUBLISHED" or binding["lifecycle_sequence"] != 1:
        raise AtomicBenchmarkIntegrityError("R6 Version must be PUBLISHED sequence 1")
    expected_projection = digest(
        {
            "strategy_version_id": binding["strategy_version_id"],
            "status": "PUBLISHED",
            "last_sequence": 1,
            "last_event_id": binding["lifecycle_event_id"],
        }
    )
    if binding["lifecycle_projection_digest"] != expected_projection:
        raise AtomicBenchmarkIntegrityError("lifecycle projection cannot rebuild")
    canonical_object_bytes(binding)
    return binding


def build_slot_binding(
    *, slot_sequence: int, hypothesis_spec_digest: str, version_binding: Mapping[str, Any]
) -> dict[str, Any]:
    binding = verify_version_binding(version_binding)
    if binding["hypothesis_spec_digest"] != hypothesis_spec_digest:
        raise AtomicBenchmarkIntegrityError("Version binding/spec mismatch")
    version_binding_digest = digest(binding)
    hypothesis_id = digest(
        {
            "schema_version": HYPOTHESIS_ID_SCHEMA,
            "hypothesis_spec_digest": hypothesis_spec_digest,
            "version_binding_digest": version_binding_digest,
        }
    )
    slot = {
        "schema_version": SLOT_BINDING_SCHEMA,
        "slot_sequence": _integer(slot_sequence, "slot_sequence", minimum=1),
        "hypothesis_id": hypothesis_id,
        "hypothesis_spec_digest": hypothesis_spec_digest,
        "version_binding_digest": version_binding_digest,
    }
    canonical_object_bytes(slot)
    return slot


_BUILD_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "protocol_core_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "preflight_implementation_digest",
        "persistence_schema_digest",
    }
)
_BUILD_BINDING_FIELDS_V1 = _BUILD_BINDING_FIELDS - {
    "preflight_implementation_digest"
}
_HYPOTHESIS_SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "slot_sequence",
        "strategy_id",
        "parameters",
        "parameters_digest",
        "strategy_configuration_digest",
        "template_digest",
        "parameter_schema_digest",
        "strategy_implementation_digest",
        "backtest_runtime_binding",
        "feature_id",
        "feature_parameters",
        "feature_parameter_digest",
        "feature_request_identity_digest",
        "feature_specification_digest",
        "feature_implementation_digest",
        "feature_runtime_identity_digest",
        "protocol_core_digest",
    }
)
HYPOTHESIS_SPEC_DIGESTS_V1 = {
    1: "ef5541b185951aca1b83a35ff582b3489669381ec5ce99289b8f1c73b5fe08cd",
    2: "c15bc531dba13bb829fc9c171c3dd8da277115e159a668e40eedf3837b864e7a",
    3: "fb155920d9fcb96e777404a89ee167b1819b1965d5f502b4b9c5d28a7699e4c9",
    4: "8e4a3cd8d37c072ca00157c5aec3bed184eaaa285c243202e663bac74e869dcb",
    5: "858b863d0cd4abbbb563b3d52e9d1ec8b16e289b4f19b532c188716ed939f465",
    6: "cd3c57ae47e6b95064f8ba561015addef4ba0201d4e44f38b66539c8f7ce1aad",
    7: "c80f7edd7ce1452401a249c347c70796d807e0ba21f2440bdff3c6acb9274612",
}
SLOT_DIGESTS_V1 = {
    1: "dfb3a41a9ba880c61c2897690d146e52642f605f3bfa97c8c547a66f119e5c7e",
    2: "7cf95ee37e0f0b9ac2b1a18e82e1af5f10133167c21f23132633f82ec31240cf",
    3: "edf3e9c08121ab4e5c71b7c57b0da3ecb139d8729711dfbc02aa06042c59a483",
    4: "2e33035647874afa21d03239a79bd8011b8b6bf68547db41d5097ee4b2419bf1",
    5: "9475da43957e66dcde83469fc3a88f1489ed356add6d3cf019b4bccfc3c927ee",
    6: "49c8492d106f91bc964ff0c04e62ee79ba7923c2ff6b9a9c97eac01f0f56a343",
    7: "fff002b9862d8d487a8e4cf9e4ac16763732d8337702d18645ddd70c4111f148",
}
HYPOTHESIS_SPEC_DIGESTS = {
    1: "2a5f55b98acc6ed066bedfad66525c5c04b6312e374fd32b9d44bd00ee9682e2",
    2: "2659227c74c384f7c5516c7755cb5f54b96db07b9b16b5f3cd0a14a39ddd9b6e",
    3: "f19f183392093fe598a28beef08964354bca88600325fb32639ab0dfda1a760e",
    4: "b6480d5e63adbdcfc8ce0e42b235414bd7dfc0076ecf06be22cde58a1bcc17c9",
    5: "fc753e5b692552389c55a01a71926d04b32ff5c0ab23e0ddb70a277277e2111a",
    6: "d1c4b77a0d9e09eba0162615cb171236c05c603bf649662be37981d11cea5791",
    7: "3c61fc9fdc1f86043fee1289d81c88d6458071fb5925ccbcaa53a2d4f8fbb7d2",
}
SLOT_DIGESTS = {
    1: "8deab12b0aac8f79063712f7b96c9f6cf715baaa3f6dcdf26d171c4462faf86a",
    2: "34a1c40eadf50d15d01fdefbe47576598599640117eb5274c750ac92e84e5a8f",
    3: "025bb8ea052778bdf4e2319d03bed3462dbe28cc6e5be7518bcf088dd3c5dd7c",
    4: "263ba9b2b9ef7cddcadacea42a2b52cd3614a6f0f0362f7f15679317f4bd27bf",
    5: "b88590c1c02e1bcb2522f1c9e5fda82e76c3934c841c98df3528a6a96636a003",
    6: "0a2350ccb0b2a516f72b944b10cfc9be9556f0ce93682cadfa7e861387543d61",
    7: "723d1708f4627d0cf2759a2842401ae55cc8575bf79651a0e73eaab974996716",
}

RETRYABLE_INFRASTRUCTURE_CODES = frozenset(
    {
        "WORKER_PROCESS_INTERRUPTED",
        "POSTGRES_TRANSIENT_UNAVAILABLE",
        "TEMP_STORAGE_UNAVAILABLE",
    }
)
INTEGRITY_REJECTION_CODES = frozenset(
    {
        "DATASET_IDENTITY_REJECTED",
        "VERSION_IDENTITY_REJECTED",
        "FEATURE_IDENTITY_REJECTED",
        "CANONICAL_BYTES_REJECTED",
        "PARITY_REJECTED",
        "COST_IDENTITY_REJECTED",
        "SUMMARY_REBUILD_REJECTED",
        "POSTFLIGHT_REJECTED",
    }
)

INTEGRITY_DIAGNOSTIC_CODES = frozenset(
    {
        "DATASET_IDENTITY_VERIFIED",
        "VERSION_IDENTITY_VERIFIED",
        "FEATURE_IDENTITY_VERIFIED",
        "CANONICAL_BYTES_VERIFIED",
        "PARITY_VERIFIED",
        "COST_IDENTITY_VERIFIED",
        "SUMMARY_REBUILD_VERIFIED",
        "POSTFLIGHT_VERIFIED",
        *INTEGRITY_REJECTION_CODES,
    }
)

_FAILURE_OUTCOME_BY_EXACT_TYPE: dict[type[BaseException], str] = {
    WorkerProcessInterrupted: "WORKER_PROCESS_INTERRUPTED",
    PostgresTransientUnavailable: "POSTGRES_TRANSIENT_UNAVAILABLE",
    TempStorageUnavailable: "TEMP_STORAGE_UNAVAILABLE",
    DatasetIdentityRejected: "DATASET_IDENTITY_REJECTED",
    VersionIdentityRejected: "VERSION_IDENTITY_REJECTED",
    FeatureIdentityRejected: "FEATURE_IDENTITY_REJECTED",
    CanonicalBytesRejected: "CANONICAL_BYTES_REJECTED",
    ParityRejected: "PARITY_REJECTED",
    CostIdentityRejected: "COST_IDENTITY_REJECTED",
    SummaryRebuildRejected: "SUMMARY_REBUILD_REJECTED",
    PostflightRejected: "POSTFLIGHT_REJECTED",
}


def classify_attempt_failure(error: BaseException) -> str:
    """Map an observed worker error to one frozen server-owned outcome code."""

    return _FAILURE_OUTCOME_BY_EXACT_TYPE.get(type(error), "UNCLASSIFIED_FAILURE")


def verify_integrity_diagnostic_codes(value: object) -> list[str]:
    """Reject diagnostic values outside the frozen non-observational allowlist."""

    if not isinstance(value, list):
        raise AtomicBenchmarkIntegrityError("integrity diagnostic codes must be a list")
    if any(type(code) is not str for code in value):
        raise AtomicBenchmarkIntegrityError("integrity diagnostic code must be a string")
    if len(value) != len(set(value)):
        raise AtomicBenchmarkIntegrityError("integrity diagnostic codes must be unique")
    unknown = set(value) - INTEGRITY_DIAGNOSTIC_CODES
    if unknown:
        raise AtomicBenchmarkIntegrityError(
            f"integrity diagnostic code is not allowed: {sorted(unknown)}"
        )
    return list(value)


def validate_attempt_transition(
    *,
    current_status: str | None,
    next_status: str,
    retry_generation: int,
    outcome_code: str,
) -> int:
    """Validate the frozen attempt state machine and return next generation."""

    generation = _integer(
        retry_generation, "retry_generation", minimum=1
    )
    if generation > 4:
        raise AtomicBenchmarkIntegrityError("retry_generation exceeds 4")
    transition = (current_status, next_status)
    if transition == (None, "RUNNING") and outcome_code == "ATTEMPT_STARTED":
        if generation != 1:
            raise AtomicBenchmarkIntegrityError("initial attempt must be generation 1")
        return 1
    if transition == ("RUNNING", "CANCELLING") and outcome_code == "OPERATOR_CANCELLED":
        return generation
    if current_status == "CANCELLING" and outcome_code == "OPERATOR_CANCELLED":
        expected = "CANCELLED_FINAL" if generation == 4 else "CANCELLED_RETRYABLE"
        if next_status == expected:
            return generation
    if current_status == "RUNNING" and outcome_code in RETRYABLE_INFRASTRUCTURE_CODES:
        expected = "FAILED_FINAL" if generation == 4 else "FAILED_RETRYABLE"
        if next_status == expected:
            return generation
    if (
        current_status == "RUNNING"
        and next_status == "FAILED_FINAL"
        and outcome_code == "UNCLASSIFIED_FAILURE"
    ):
        return generation
    if (
        current_status == "RUNNING"
        and next_status == "REJECTED_FINAL"
        and outcome_code in INTEGRITY_REJECTION_CODES
    ):
        return generation
    if (
        current_status == "RUNNING"
        and next_status == "ACCEPTED"
        and outcome_code == "POSTFLIGHT_ACCEPTED"
    ):
        return generation
    if (
        current_status in {"FAILED_RETRYABLE", "CANCELLED_RETRYABLE"}
        and next_status == "RUNNING"
        and outcome_code == "ATTEMPT_RETRY_STARTED"
        and generation < 4
    ):
        return generation + 1
    if (
        current_status == "FAILED_RETRYABLE"
        and next_status == "FAILED_FINAL"
        and outcome_code == "OPERATOR_SEALED_TECHNICAL_FAILURE"
        and generation < 4
    ):
        return generation
    if (
        current_status == "CANCELLED_RETRYABLE"
        and next_status == "CANCELLED_FINAL"
        and outcome_code == "OPERATOR_SEALED_CANCELLATION"
        and generation < 4
    ):
        return generation
    raise AtomicBenchmarkIntegrityError(
        f"R6 attempt transition rejected: {current_status}->{next_status}/{outcome_code}"
    )


def verify_hypothesis_spec(value: Mapping[str, Any]) -> dict[str, Any]:
    specification = dict(value)
    require_exact_fields(specification, _HYPOTHESIS_SPEC_FIELDS, "hypothesis spec")
    if specification["schema_version"] != "r6-hypothesis-spec-v1":
        raise AtomicBenchmarkIntegrityError("hypothesis spec schema drift")
    slot = _integer(specification["slot_sequence"], "slot_sequence", minimum=1)
    if slot not in HYPOTHESIS_SPEC_DIGESTS:
        raise AtomicBenchmarkIntegrityError("R6 slot must be in 1..7")
    protocol_digest = specification["protocol_core_digest"]
    if protocol_digest not in {PROTOCOL_CORE_DIGEST_V1, PROTOCOL_CORE_DIGEST}:
        raise AtomicBenchmarkIntegrityError("hypothesis protocol core drift")
    for field in (
        "parameters_digest",
        "strategy_configuration_digest",
        "template_digest",
        "parameter_schema_digest",
        "strategy_implementation_digest",
        "feature_parameter_digest",
        "feature_request_identity_digest",
        "feature_specification_digest",
        "feature_implementation_digest",
        "feature_runtime_identity_digest",
    ):
        require_sha256(specification[field], field)
    _nonempty(specification["strategy_id"], "strategy_id")
    _nonempty(specification["backtest_runtime_binding"], "backtest_runtime_binding")
    _nonempty(specification["feature_id"], "feature_id")
    if not isinstance(specification["parameters"], Mapping) or not isinstance(
        specification["feature_parameters"], Mapping
    ):
        raise AtomicBenchmarkIntegrityError("hypothesis parameters must be objects")
    expected_digests = (
        HYPOTHESIS_SPEC_DIGESTS
        if protocol_digest == PROTOCOL_CORE_DIGEST
        else HYPOTHESIS_SPEC_DIGESTS_V1
    )
    if digest(specification) != expected_digests[slot]:
        raise AtomicBenchmarkIntegrityError("hypothesis spec digest drift")
    canonical_object_bytes(specification)
    return specification


def build_benchmark_build_binding(
    *,
    algorithm_implementation_digest: str,
    persistence_schema_digest: str,
    preflight_implementation_digest: str | None = None,
) -> dict[str, Any]:
    if preflight_implementation_digest is None:
        return verify_benchmark_build_binding(
            {
                "schema_version": BENCHMARK_BUILD_BINDING_SCHEMA_V1,
                "protocol_core_digest": PROTOCOL_CORE_DIGEST_V1,
                "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST_V1,
                "algorithm_implementation_digest": algorithm_implementation_digest,
                "persistence_schema_digest": persistence_schema_digest,
            }
        )
    return verify_benchmark_build_binding(
        {
            "schema_version": BENCHMARK_BUILD_BINDING_SCHEMA,
            "protocol_core_digest": PROTOCOL_CORE_DIGEST,
            "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
            "algorithm_implementation_digest": algorithm_implementation_digest,
            "preflight_implementation_digest": preflight_implementation_digest,
            "persistence_schema_digest": persistence_schema_digest,
        }
    )


def verify_benchmark_build_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    binding = dict(value)
    schema = binding.get("schema_version")
    expected_fields = (
        _BUILD_BINDING_FIELDS
        if schema == BENCHMARK_BUILD_BINDING_SCHEMA
        else _BUILD_BINDING_FIELDS_V1
    )
    require_exact_fields(binding, expected_fields, "benchmark build binding")
    if schema not in {
        BENCHMARK_BUILD_BINDING_SCHEMA_V1,
        BENCHMARK_BUILD_BINDING_SCHEMA,
    }:
        raise AtomicBenchmarkIntegrityError("benchmark build binding schema drift")
    sha_fields = [
        "protocol_core_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "persistence_schema_digest",
    ]
    if schema == BENCHMARK_BUILD_BINDING_SCHEMA:
        sha_fields.append("preflight_implementation_digest")
    for field in sha_fields:
        require_sha256(binding[field], field)
    expected_protocol = (
        PROTOCOL_CORE_DIGEST
        if schema == BENCHMARK_BUILD_BINDING_SCHEMA
        else PROTOCOL_CORE_DIGEST_V1
    )
    expected_algorithm = (
        ALGORITHM_CONTRACT_DIGEST
        if schema == BENCHMARK_BUILD_BINDING_SCHEMA
        else ALGORITHM_CONTRACT_DIGEST_V1
    )
    if binding["protocol_core_digest"] != expected_protocol:
        raise AtomicBenchmarkIntegrityError("build binding protocol drift")
    if binding["algorithm_contract_digest"] != expected_algorithm:
        raise AtomicBenchmarkIntegrityError("algorithm contract drift")
    canonical_object_bytes(binding)
    return binding


@dataclass(frozen=True)
class MatrixSealBuild:
    family_id: str
    research_baseline: dict[str, Any]
    protocol_core: dict[str, Any]
    benchmark_build_binding: dict[str, Any]
    matrix_core: dict[str, Any]
    registration: dict[str, Any]
    slots: tuple[dict[str, Any], ...]

    @property
    def matrix_id(self) -> str:
        return str(self.registration["matrix_id"])

    @property
    def registration_digest(self) -> str:
        return digest(self.registration)


def build_matrix_seal(
    *,
    research_baseline: Mapping[str, Any],
    protocol_core: Mapping[str, Any],
    benchmark_build_binding: Mapping[str, Any],
    slot_inputs: Sequence[Mapping[str, Any]],
) -> MatrixSealBuild:
    baseline = dict(research_baseline)
    protocol = dict(protocol_core)
    if digest(baseline) != RESEARCH_BASELINE_DIGEST:
        raise AtomicBenchmarkIntegrityError("research baseline digest drift")
    protocol_digest = digest(protocol)
    if protocol_digest not in {PROTOCOL_CORE_DIGEST_V1, PROTOCOL_CORE_DIGEST}:
        raise AtomicBenchmarkIntegrityError("protocol core digest drift")
    build_binding = verify_benchmark_build_binding(benchmark_build_binding)
    if len(slot_inputs) != 7:
        raise AtomicBenchmarkIntegrityError("R6 matrix requires exactly seven slots")

    slots: list[dict[str, Any]] = []
    for expected_slot, source in enumerate(slot_inputs, start=1):
        if frozenset(source) != {"hypothesis_spec", "version_binding"}:
            raise AtomicBenchmarkIntegrityError("slot input schema mismatch")
        specification = verify_hypothesis_spec(source["hypothesis_spec"])
        if specification["slot_sequence"] != expected_slot:
            raise AtomicBenchmarkIntegrityError("slot order drift")
        version_binding = verify_version_binding(source["version_binding"])
        specification_digest = digest(specification)
        if (
            version_binding["strategy_configuration_digest"]
            != specification["strategy_configuration_digest"]
        ):
            raise AtomicBenchmarkIntegrityError(
                "Version binding/strategy configuration mismatch"
            )
        slot_binding = build_slot_binding(
            slot_sequence=expected_slot,
            hypothesis_spec_digest=specification_digest,
            version_binding=version_binding,
        )
        expected_slot_digests = (
            SLOT_DIGESTS
            if protocol_digest == PROTOCOL_CORE_DIGEST
            else SLOT_DIGESTS_V1
        )
        if digest(slot_binding) != expected_slot_digests[expected_slot]:
            raise AtomicBenchmarkIntegrityError("G1 slot binding drift")
        slots.append(
            {
                "slot_sequence": expected_slot,
                "hypothesis_spec": specification,
                "hypothesis_spec_digest": specification_digest,
                "version_binding": version_binding,
                "version_binding_digest": digest(version_binding),
                "hypothesis_id": slot_binding["hypothesis_id"],
                "slot_binding": slot_binding,
                "slot_digest": digest(slot_binding),
            }
        )

    build_binding_digest = digest(build_binding)
    ordered_slot_digests = [slot["slot_digest"] for slot in slots]
    matrix_revision = 2 if protocol_digest == PROTOCOL_CORE_DIGEST else 1
    matrix_core = {
        "schema_version": MATRIX_CORE_SCHEMA,
        "family_id": FAMILY_ID,
        "research_baseline_digest": RESEARCH_BASELINE_DIGEST,
        "protocol_core_digest": protocol_digest,
        "benchmark_build_binding_digest": build_binding_digest,
        "ordered_slot_digests": ordered_slot_digests,
        "registered_slots": list(range(1, 8)),
        "unavailable_slots": list(range(8, 21)),
        "matrix_revision": matrix_revision,
    }
    matrix_core_digest = digest(matrix_core)
    matrix_id = f"r6-matrix-sha256-{matrix_core_digest}"
    registration = {
        "schema_version": MATRIX_REGISTRATION_SCHEMA,
        "matrix_id": matrix_id,
        "matrix_core_digest": matrix_core_digest,
        "family_id": FAMILY_ID,
        "research_baseline_digest": RESEARCH_BASELINE_DIGEST,
        "protocol_core_digest": protocol_digest,
        "benchmark_build_binding_digest": build_binding_digest,
        "ordered_slot_digests": ordered_slot_digests,
        "registered_slots": list(range(1, 8)),
        "matrix_revision": matrix_revision,
    }
    canonical_object_bytes(matrix_core)
    canonical_object_bytes(registration)
    return MatrixSealBuild(
        family_id=FAMILY_ID,
        research_baseline=baseline,
        protocol_core=protocol,
        benchmark_build_binding=build_binding,
        matrix_core=matrix_core,
        registration=registration,
        slots=tuple(slots),
    )


@dataclass(frozen=True)
class ObservedBar:
    bar: HistoricalBar
    source_json: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.bar, HistoricalBar):
            raise AtomicBenchmarkIntegrityError("ObservedBar requires HistoricalBar")
        if not self.source_json or b"\n" in self.source_json or b"\r" in self.source_json:
            raise AtomicBenchmarkIntegrityError("source bytes must be one non-empty JSON row")
        try:
            parsed = json.loads(self.source_json)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AtomicBenchmarkIntegrityError("source bytes are not JSON") from error
        if not isinstance(parsed, Mapping):
            raise AtomicBenchmarkIntegrityError("source bar must be JSON object")
        _require_nfc(parsed, "source bar")
        if canonical_json(parsed).encode("utf-8") != self.source_json:
            raise AtomicBenchmarkIntegrityError("source bar bytes are not canonical")
        try:
            source_bar = HistoricalBar.from_dict(parsed)
        except (KeyError, TypeError, ValueError, DecimalException) as error:
            raise AtomicBenchmarkIntegrityError("source bar cannot parse") from error
        if canonical_json(source_bar.to_dict()).encode("utf-8") != self.source_json:
            raise AtomicBenchmarkIntegrityError("source bytes are not exact bar projection")
        if canonical_json(self.bar.to_dict()).encode("utf-8") != self.source_json:
            raise AtomicBenchmarkIntegrityError("matcher bar differs from source bytes")

    @property
    def symbol(self) -> str:
        return self.bar.symbol

    @property
    def timestamp(self) -> datetime:
        return self.bar.timestamp.astimezone(_TAIPEI)

    @property
    def session_date(self) -> date:
        return self.bar.session_date or self.timestamp.date()

    @property
    def open(self) -> Decimal:
        return self.bar.open

    @property
    def close(self) -> Decimal:
        return self.bar.close

    @property
    def source_digest(self) -> str:
        return hashlib.sha256(self.source_json).hexdigest()


_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "matrix_id",
        "registration_digest",
        "slot_sequence",
        "hypothesis_id",
        "strategy_id",
        "strategy_version_id",
        "strategy_configuration_digest",
        "strategy_implementation_digest",
        "feature_request_identity_digest",
        "sequence",
        "signal_id",
        "semantic_key",
        "symbol",
        "session_date",
        "signal_at",
        "side",
        "execution_horizon",
        "current_close",
        "source_bar_digest",
        "evaluation_status",
        "evaluation_document",
        "evaluation_digest",
        "feature_input_evidence",
        "feature_input_evidence_digest",
    }
)


def verify_ledger_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _LEDGER_FIELDS, "signal ledger row")
    if (
        row["schema_version"] != LEDGER_ROW_SCHEMA
        or row["side"] != "ENTRY"
        or row["execution_horizon"] != "INTRADAY_NEXT_BAR"
        or row["evaluation_status"] != "TRIGGERED"
    ):
        raise AtomicBenchmarkIntegrityError("signal ledger literals drift")
    _integer(row["slot_sequence"], "slot_sequence", minimum=1)
    _integer(row["sequence"], "sequence", minimum=1)
    for field in (
        "registration_digest",
        "hypothesis_id",
        "strategy_configuration_digest",
        "strategy_implementation_digest",
        "feature_request_identity_digest",
        "signal_id",
        "semantic_key",
        "source_bar_digest",
        "evaluation_digest",
        "feature_input_evidence_digest",
    ):
        require_sha256(row[field], field)
    for field in ("matrix_id", "strategy_id", "strategy_version_id", "symbol"):
        _nonempty(row[field], field)
    require_canonical_date(row["session_date"], "session_date")
    signal_at = require_canonical_timestamp(row["signal_at"], "signal_at")
    if datetime.fromisoformat(signal_at).date().isoformat() != row["session_date"]:
        raise AtomicBenchmarkIntegrityError("signal timestamp/session mismatch")
    require_decimal_text(row["current_close"], "current_close", positive=True)
    if not isinstance(row["evaluation_document"], Mapping) or not isinstance(
        row["feature_input_evidence"], Mapping
    ):
        raise AtomicBenchmarkIntegrityError("evaluation/feature evidence must be objects")
    if digest(dict(row["evaluation_document"])) != row["evaluation_digest"]:
        raise AtomicBenchmarkIntegrityError("evaluation digest cannot rebuild")
    if digest(dict(row["feature_input_evidence"])) != row["feature_input_evidence_digest"]:
        raise AtomicBenchmarkIntegrityError("feature evidence digest cannot rebuild")
    signal_projection = {
        "schema_version": "r6-signal-id-v1",
        "matrix_id": row["matrix_id"],
        "slot_sequence": row["slot_sequence"],
        "hypothesis_id": row["hypothesis_id"],
        "strategy_version_id": row["strategy_version_id"],
        "symbol": row["symbol"],
        "session_date": row["session_date"],
        "signal_at": row["signal_at"],
    }
    if row["signal_id"] != digest(signal_projection):
        raise AtomicBenchmarkIntegrityError("signal_id cannot rebuild")
    semantic_projection = {
        "schema_version": "r6-semantic-key-v1",
        "slot_sequence": row["slot_sequence"],
        "hypothesis_id": row["hypothesis_id"],
        "strategy_version_id": row["strategy_version_id"],
        "strategy_configuration_digest": row["strategy_configuration_digest"],
        "symbol": row["symbol"],
        "session_date": row["session_date"],
        "signal_at": row["signal_at"],
        "execution_horizon": row["execution_horizon"],
    }
    if row["semantic_key"] != digest(semantic_projection):
        raise AtomicBenchmarkIntegrityError("semantic_key cannot rebuild")
    canonical_object_bytes(row)
    return row


@dataclass
class FirstTriggerAdmission:
    """Bounded first-trigger owner for one immutable slot."""

    sequence: int = 0
    current_session: date | None = None
    max_symbols_in_session: int = 0

    def __post_init__(self) -> None:
        self._admitted_symbols: set[str] = set()

    @property
    def state_count(self) -> int:
        return len(self._admitted_symbols)

    def consider(
        self,
        *,
        matrix_id: str,
        registration_digest: str,
        slot_sequence: int,
        hypothesis_id: str,
        strategy_id: str,
        strategy_version_id: str,
        strategy_configuration_digest: str,
        strategy_implementation_digest: str,
        feature_request_identity_digest: str,
        source_bar: ObservedBar,
        evaluation_status: str,
        evaluation_document: Mapping[str, Any],
        feature_input_evidence: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        session = source_bar.session_date
        if self.current_session is None or session > self.current_session:
            self.current_session = session
            self._admitted_symbols.clear()
        elif session < self.current_session:
            raise AtomicBenchmarkIntegrityError("admission session order regressed")
        if evaluation_status not in {
            "TRIGGERED",
            "NOT_TRIGGERED",
            "INSUFFICIENT_DATA",
            "BLOCKED",
        }:
            raise AtomicBenchmarkIntegrityError("evaluation status unsupported")
        if evaluation_status != "TRIGGERED" or source_bar.symbol in self._admitted_symbols:
            return None
        self._admitted_symbols.add(source_bar.symbol)
        self.max_symbols_in_session = max(
            self.max_symbols_in_session, len(self._admitted_symbols)
        )
        self.sequence += 1
        signal_at = canonical_timestamp(source_bar.timestamp, "signal_at")
        session_text = session.isoformat()
        signal_projection = {
            "schema_version": "r6-signal-id-v1",
            "matrix_id": matrix_id,
            "slot_sequence": slot_sequence,
            "hypothesis_id": hypothesis_id,
            "strategy_version_id": strategy_version_id,
            "symbol": source_bar.symbol,
            "session_date": session_text,
            "signal_at": signal_at,
        }
        semantic_projection = {
            "schema_version": "r6-semantic-key-v1",
            "slot_sequence": slot_sequence,
            "hypothesis_id": hypothesis_id,
            "strategy_version_id": strategy_version_id,
            "strategy_configuration_digest": strategy_configuration_digest,
            "symbol": source_bar.symbol,
            "session_date": session_text,
            "signal_at": signal_at,
            "execution_horizon": "INTRADAY_NEXT_BAR",
        }
        row = {
            "schema_version": LEDGER_ROW_SCHEMA,
            "matrix_id": matrix_id,
            "registration_digest": registration_digest,
            "slot_sequence": slot_sequence,
            "hypothesis_id": hypothesis_id,
            "strategy_id": strategy_id,
            "strategy_version_id": strategy_version_id,
            "strategy_configuration_digest": strategy_configuration_digest,
            "strategy_implementation_digest": strategy_implementation_digest,
            "feature_request_identity_digest": feature_request_identity_digest,
            "sequence": self.sequence,
            "signal_id": digest(signal_projection),
            "semantic_key": digest(semantic_projection),
            "symbol": source_bar.symbol,
            "session_date": session_text,
            "signal_at": signal_at,
            "side": "ENTRY",
            "execution_horizon": "INTRADAY_NEXT_BAR",
            "current_close": decimal_text(source_bar.close, "current_close", positive=True),
            "source_bar_digest": source_bar.source_digest,
            "evaluation_status": "TRIGGERED",
            "evaluation_document": dict(evaluation_document),
            "evaluation_digest": digest(dict(evaluation_document)),
            "feature_input_evidence": dict(feature_input_evidence),
            "feature_input_evidence_digest": digest(dict(feature_input_evidence)),
        }
        return verify_ledger_row(row)


_MATCH_FIELDS = frozenset(
    {
        "schema_version",
        "matrix_id",
        "registration_digest",
        "slot_sequence",
        "hypothesis_id",
        "sequence",
        "match_id",
        "signal_id",
        "semantic_key",
        "symbol",
        "signal_session_date",
        "signal_at",
        "signal_source_bar_digest",
        "entry_session_date",
        "entry_at",
        "raw_entry_open",
        "entry_bar_digest",
        "exit_session_date",
        "exit_at",
        "raw_exit_close",
        "exit_bar_digest",
        "shares",
        "match_status",
    }
)


def verify_match_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _MATCH_FIELDS, "match row")
    if row["schema_version"] != MATCH_ROW_SCHEMA or row["match_status"] != "COMPLETE":
        raise AtomicBenchmarkIntegrityError("match schema/status drift")
    for field in ("slot_sequence", "sequence"):
        _integer(row[field], field, minimum=1)
    if row["shares"] != 1000 or isinstance(row["shares"], bool):
        raise AtomicBenchmarkIntegrityError("match shares must be exact one lot")
    for field in (
        "registration_digest",
        "hypothesis_id",
        "match_id",
        "signal_id",
        "semantic_key",
        "signal_source_bar_digest",
        "entry_bar_digest",
        "exit_bar_digest",
    ):
        require_sha256(row[field], field)
    for field in ("matrix_id", "symbol"):
        _nonempty(row[field], field)
    for field in ("signal_session_date", "entry_session_date", "exit_session_date"):
        require_canonical_date(row[field], field)
    signal_at = datetime.fromisoformat(require_canonical_timestamp(row["signal_at"], "signal_at"))
    entry_at = datetime.fromisoformat(require_canonical_timestamp(row["entry_at"], "entry_at"))
    exit_at = datetime.fromisoformat(require_canonical_timestamp(row["exit_at"], "exit_at"))
    if not signal_at < entry_at < exit_at:
        raise AtomicBenchmarkIntegrityError("match requires signal < entry < exit")
    if not (
        row["signal_session_date"]
        == row["entry_session_date"]
        == row["exit_session_date"]
        == signal_at.date().isoformat()
        == entry_at.date().isoformat()
        == exit_at.date().isoformat()
    ):
        raise AtomicBenchmarkIntegrityError("match must remain in one session")
    require_decimal_text(row["raw_entry_open"], "raw_entry_open", positive=True)
    require_decimal_text(row["raw_exit_close"], "raw_exit_close", positive=True)
    expected = digest(
        {
            "schema_version": "r6-match-id-v1",
            "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
            "signal_id": row["signal_id"],
            "entry_bar_digest": row["entry_bar_digest"],
            "exit_bar_digest": row["exit_bar_digest"],
        }
    )
    if row["match_id"] != expected:
        raise AtomicBenchmarkIntegrityError("match_id cannot rebuild")
    canonical_object_bytes(row)
    return row


@dataclass(frozen=True)
class MatchPlanBuild:
    rows: tuple[dict[str, Any], ...]
    signal_count: int
    missing_entry_count: int
    missing_exit_count: int
    duplicate_match_count: int
    rows_sha256: str
    signal_multiplicity_digest: str
    source_bar_count: int
    source_bars_sha256: str
    max_waiting_count: int
    max_active_count: int


@dataclass
class _ActiveMatch:
    signal: dict[str, Any]
    entry: ObservedBar
    latest: ObservedBar | None = None


def _make_match(signal: Mapping[str, Any], entry: ObservedBar, exit_bar: ObservedBar) -> dict[str, Any]:
    body = {
        "schema_version": MATCH_ROW_SCHEMA,
        "matrix_id": signal["matrix_id"],
        "registration_digest": signal["registration_digest"],
        "slot_sequence": signal["slot_sequence"],
        "hypothesis_id": signal["hypothesis_id"],
        "sequence": signal["sequence"],
        "match_id": digest(
            {
                "schema_version": "r6-match-id-v1",
                "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
                "signal_id": signal["signal_id"],
                "entry_bar_digest": entry.source_digest,
                "exit_bar_digest": exit_bar.source_digest,
            }
        ),
        "signal_id": signal["signal_id"],
        "semantic_key": signal["semantic_key"],
        "symbol": signal["symbol"],
        "signal_session_date": signal["session_date"],
        "signal_at": signal["signal_at"],
        "signal_source_bar_digest": signal["source_bar_digest"],
        "entry_session_date": entry.session_date.isoformat(),
        "entry_at": canonical_timestamp(entry.timestamp, "entry_at"),
        "raw_entry_open": decimal_text(entry.open, "raw_entry_open", positive=True),
        "entry_bar_digest": entry.source_digest,
        "exit_session_date": exit_bar.session_date.isoformat(),
        "exit_at": canonical_timestamp(exit_bar.timestamp, "exit_at"),
        "raw_exit_close": decimal_text(exit_bar.close, "raw_exit_close", positive=True),
        "exit_bar_digest": exit_bar.source_digest,
        "shares": 1000,
        "match_status": "COMPLETE",
    }
    return verify_match_row(body)


def build_match_plan(
    *, ledger_rows: Iterable[Mapping[str, Any]], bars: Iterable[ObservedBar]
) -> MatchPlanBuild:
    ledger = iter(ledger_rows)
    expected_sequence = 1
    previous_signal_key: tuple[datetime, str] | None = None

    def next_signal() -> dict[str, Any] | None:
        nonlocal expected_sequence, previous_signal_key
        try:
            row = verify_ledger_row(next(ledger))
        except StopIteration:
            return None
        if row["sequence"] != expected_sequence:
            raise AtomicBenchmarkIntegrityError("ledger sequence must be contiguous")
        key = (datetime.fromisoformat(row["signal_at"]), row["symbol"])
        if previous_signal_key is not None and key <= previous_signal_key:
            raise AtomicBenchmarkIntegrityError("ledger order must follow Dataset traversal")
        previous_signal_key = key
        expected_sequence += 1
        return row

    pending_signal = next_signal()
    waiting: dict[tuple[str, str], dict[str, Any]] = {}
    active: dict[tuple[str, str], _ActiveMatch] = {}
    rows: list[dict[str, Any]] = []
    previous_bar_key: tuple[datetime, str] | None = None
    current_session: date | None = None
    source_hasher = hashlib.sha256()
    source_count = 0
    max_waiting = 0
    max_active = 0
    missing_entry = 0
    missing_exit = 0

    def pull_before(timestamp: datetime) -> None:
        nonlocal pending_signal
        while pending_signal is not None and datetime.fromisoformat(
            pending_signal["signal_at"]
        ) < timestamp:
            key = (pending_signal["symbol"], pending_signal["session_date"])
            if key in waiting or key in active:
                raise AtomicBenchmarkIntegrityError("duplicate signal match key")
            waiting[key] = pending_signal
            pending_signal = next_signal()

    def close_session(session: date) -> None:
        nonlocal missing_entry, missing_exit
        session_text = session.isoformat()
        for key in tuple(waiting):
            if key[1] == session_text:
                missing_entry += 1
                waiting.pop(key)
        for key in tuple(active):
            item = active[key]
            if key[1] != session_text:
                continue
            if item.latest is None:
                missing_exit += 1
            else:
                rows.append(_make_match(item.signal, item.entry, item.latest))
            active.pop(key)

    for bar in bars:
        key = (bar.timestamp, bar.symbol)
        if previous_bar_key is not None and key <= previous_bar_key:
            raise AtomicBenchmarkIntegrityError("Dataset bars must be timestamp/symbol ordered")
        previous_bar_key = key
        source_hasher.update(bar.source_json + b"\n")
        source_count += 1
        pull_before(bar.timestamp)
        if current_session is None:
            current_session = bar.session_date
        elif bar.session_date > current_session:
            close_session(current_session)
            current_session = bar.session_date
        elif bar.session_date < current_session:
            raise AtomicBenchmarkIntegrityError("Dataset session order regressed")
        match_key = (bar.symbol, bar.session_date.isoformat())
        signal = waiting.pop(match_key, None)
        if signal is not None:
            active[match_key] = _ActiveMatch(signal=signal, entry=bar)
        item = active.get(match_key)
        if item is not None and bar.timestamp > item.entry.timestamp:
            item.latest = bar
        max_waiting = max(max_waiting, len(waiting))
        max_active = max(max_active, len(active))

    while pending_signal is not None:
        key = (pending_signal["symbol"], pending_signal["session_date"])
        if key in waiting or key in active:
            raise AtomicBenchmarkIntegrityError("duplicate signal match key")
        waiting[key] = pending_signal
        pending_signal = next_signal()
    if current_session is not None:
        close_session(current_session)
    missing_entry += len(waiting)
    missing_exit += len(active)
    verified, payload = canonical_rows(rows, verify_match_row)
    duplicates = Counter(row["match_id"] for row in verified)
    return MatchPlanBuild(
        rows=verified,
        signal_count=expected_sequence - 1,
        missing_entry_count=missing_entry,
        missing_exit_count=missing_exit,
        duplicate_match_count=sum(max(count - 1, 0) for count in duplicates.values()),
        rows_sha256=hashlib.sha256(payload).hexdigest(),
        signal_multiplicity_digest=layer_multiplicity_digest(verified),
        source_bar_count=source_count,
        source_bars_sha256=source_hasher.hexdigest(),
        max_waiting_count=max_waiting,
        max_active_count=max_active,
    )


_EPISODE_FIELDS = frozenset(
    {
        "schema_version",
        "matrix_id",
        "registration_digest",
        "slot_sequence",
        "hypothesis_id",
        "sequence",
        "episode_id",
        "match_id",
        "signal_id",
        "semantic_key",
        "symbol",
        "shares",
        "entry_session_date",
        "entry_at",
        "raw_entry_open",
        "entry_fill_price",
        "exit_session_date",
        "exit_at",
        "raw_exit_close",
        "exit_fill_price",
        "entry_commission",
        "exit_commission",
        "sell_tax",
        "pre_slippage_price_pnl",
        "post_slippage_gross_pnl",
        "explicit_costs",
        "net_pnl",
        "pre_slippage_return",
        "net_return_on_raw_entry_notional",
        "cost_identity_digest",
    }
)


def _episode_values(match: Mapping[str, Any]) -> dict[str, str]:
    try:
        with localcontext(_CONTEXT):
            raw_entry = Decimal(match["raw_entry_open"])
            raw_exit = Decimal(match["raw_exit_close"])
            shares = Decimal(1000)
            entry_fill = raw_entry * (Decimal(1) + Decimal("5") / Decimal(10000))
            exit_fill = raw_exit * (Decimal(1) - Decimal("5") / Decimal(10000))
            entry_commission = entry_fill * shares * Decimal("0.001425")
            exit_commission = exit_fill * shares * Decimal("0.001425")
            sell_tax = exit_fill * shares * Decimal("0.003")
            pre_pnl = (raw_exit - raw_entry) * shares
            gross_pnl = (exit_fill - entry_fill) * shares
            explicit = entry_commission + exit_commission + sell_tax
            net_pnl = gross_pnl - explicit
            pre_return = raw_exit / raw_entry - Decimal(1)
            net_return = net_pnl / (raw_entry * shares)
    except (DecimalException, KeyError) as error:
        raise AtomicBenchmarkIntegrityError("episode economics failed") from error
    if exit_fill <= 0:
        raise AtomicBenchmarkIntegrityError("exit fill must be positive")
    return {
        "entry_fill_price": decimal_text(entry_fill, "entry_fill_price", positive=True),
        "exit_fill_price": decimal_text(exit_fill, "exit_fill_price", positive=True),
        "entry_commission": decimal_text(entry_commission, "entry_commission", nonnegative=True),
        "exit_commission": decimal_text(exit_commission, "exit_commission", nonnegative=True),
        "sell_tax": decimal_text(sell_tax, "sell_tax", nonnegative=True),
        "pre_slippage_price_pnl": decimal_text(pre_pnl, "pre_slippage_price_pnl"),
        "post_slippage_gross_pnl": decimal_text(gross_pnl, "post_slippage_gross_pnl"),
        "explicit_costs": decimal_text(explicit, "explicit_costs", nonnegative=True),
        "net_pnl": decimal_text(net_pnl, "net_pnl"),
        "pre_slippage_return": _quantized(pre_return, "pre_slippage_return"),
        "net_return_on_raw_entry_notional": _quantized(net_return, "net_return"),
    }


def build_episode(match_row: Mapping[str, Any]) -> dict[str, Any]:
    match = verify_match_row(match_row)
    episode_id = digest(
        {
            "schema_version": "r6-episode-id-v1",
            "match_id": match["match_id"],
            "cost_identity_digest": COST_IDENTITY_DIGEST,
        }
    )
    row = {
        "schema_version": EPISODE_ROW_SCHEMA,
        "matrix_id": match["matrix_id"],
        "registration_digest": match["registration_digest"],
        "slot_sequence": match["slot_sequence"],
        "hypothesis_id": match["hypothesis_id"],
        "sequence": match["sequence"],
        "episode_id": episode_id,
        "match_id": match["match_id"],
        "signal_id": match["signal_id"],
        "semantic_key": match["semantic_key"],
        "symbol": match["symbol"],
        "shares": 1000,
        "entry_session_date": match["entry_session_date"],
        "entry_at": match["entry_at"],
        "raw_entry_open": match["raw_entry_open"],
        "exit_session_date": match["exit_session_date"],
        "exit_at": match["exit_at"],
        "raw_exit_close": match["raw_exit_close"],
        **_episode_values(match),
        "cost_identity_digest": COST_IDENTITY_DIGEST,
    }
    return verify_episode_row(row)


def verify_episode_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _EPISODE_FIELDS, "episode row")
    if row["schema_version"] != EPISODE_ROW_SCHEMA:
        raise AtomicBenchmarkIntegrityError("episode schema drift")
    for field in ("slot_sequence", "sequence"):
        _integer(row[field], field, minimum=1)
    if row["shares"] != 1000 or isinstance(row["shares"], bool):
        raise AtomicBenchmarkIntegrityError("episode shares must be 1000")
    for field in (
        "registration_digest",
        "hypothesis_id",
        "episode_id",
        "match_id",
        "signal_id",
        "semantic_key",
        "cost_identity_digest",
    ):
        require_sha256(row[field], field)
    if row["cost_identity_digest"] != COST_IDENTITY_DIGEST:
        raise AtomicBenchmarkIntegrityError("episode cost identity drift")
    for field in ("matrix_id", "symbol"):
        _nonempty(row[field], field)
    for field in ("entry_session_date", "exit_session_date"):
        require_canonical_date(row[field], field)
    entry_at = datetime.fromisoformat(require_canonical_timestamp(row["entry_at"], "entry_at"))
    exit_at = datetime.fromisoformat(require_canonical_timestamp(row["exit_at"], "exit_at"))
    if not entry_at < exit_at or row["entry_session_date"] != row["exit_session_date"]:
        raise AtomicBenchmarkIntegrityError("episode must exit later in same session")
    for field in ("raw_entry_open", "entry_fill_price", "raw_exit_close", "exit_fill_price"):
        require_decimal_text(row[field], field, positive=True)
    for field in ("entry_commission", "exit_commission", "sell_tax", "explicit_costs"):
        require_decimal_text(row[field], field, nonnegative=True)
    for field in ("pre_slippage_price_pnl", "post_slippage_gross_pnl", "net_pnl"):
        require_decimal_text(row[field], field)
    for field in ("pre_slippage_return", "net_return_on_raw_entry_notional"):
        require_decimal_text(row[field], field, maximum_scale=18)
    expected_id = digest(
        {
            "schema_version": "r6-episode-id-v1",
            "match_id": row["match_id"],
            "cost_identity_digest": COST_IDENTITY_DIGEST,
        }
    )
    if row["episode_id"] != expected_id:
        raise AtomicBenchmarkIntegrityError("episode_id cannot rebuild")
    formula_input = {
        "raw_entry_open": row["raw_entry_open"],
        "raw_exit_close": row["raw_exit_close"],
    }
    expected_values = _episode_values(formula_input)
    if any(row[field] != expected for field, expected in expected_values.items()):
        raise AtomicBenchmarkIntegrityError("episode economics cannot rebuild")
    canonical_object_bytes(row)
    return row


def canonical_rows(
    rows: Iterable[Mapping[str, Any]], verifier: Any
) -> tuple[tuple[dict[str, Any], ...], bytes]:
    verified = tuple(verifier(row) for row in rows)
    ordered = tuple(sorted(verified, key=lambda row: int(row["sequence"])))
    for expected, row in enumerate(ordered, start=1):
        if row["sequence"] != expected:
            raise AtomicBenchmarkIntegrityError("row sequence must be contiguous from 1")
    return ordered, b"".join(canonical_object_bytes(row) for row in ordered)


def layer_multiplicity_projection(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for row in rows:
        token = {
            "sequence": _integer(row.get("sequence"), "sequence", minimum=1),
            "signal_id": require_sha256(row.get("signal_id"), "signal_id"),
            "semantic_key": require_sha256(row.get("semantic_key"), "semantic_key"),
        }
        counts[canonical_json(token)] += 1
    return {"schema_version": PARITY_SCHEMA, "tokens": dict(sorted(counts.items()))}


def layer_multiplicity_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    return digest(layer_multiplicity_projection(rows))


@dataclass(frozen=True)
class LayerDifference:
    left_minus_right_count: int
    right_minus_left_count: int
    left_digest: str
    right_digest: str

    @property
    def equal(self) -> bool:
        return self.left_minus_right_count == self.right_minus_left_count == 0


def compare_layers(
    left: Iterable[Mapping[str, Any]], right: Iterable[Mapping[str, Any]]
) -> LayerDifference:
    left_projection = layer_multiplicity_projection(left)
    right_projection = layer_multiplicity_projection(right)
    left_counts = Counter(left_projection["tokens"])
    right_counts = Counter(right_projection["tokens"])
    return LayerDifference(
        left_minus_right_count=sum((left_counts - right_counts).values()),
        right_minus_left_count=sum((right_counts - left_counts).values()),
        left_digest=digest(left_projection),
        right_digest=digest(right_projection),
    )


def _profit_factor(values: Sequence[Decimal]) -> dict[str, Any]:
    gains = sum((value for value in values if value > 0), Decimal(0))
    losses = abs(sum((value for value in values if value < 0), Decimal(0)))
    if losses > 0:
        with localcontext(_CONTEXT):
            return {"status": "FINITE", "value": _quantized(gains / losses, "profit factor")}
    if gains > 0:
        return {"status": "POSITIVE_INFINITY", "value": None}
    return {"status": "UNDEFINED", "value": None}


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _quarter(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.year}Q{((parsed.month - 1) // 3) + 1}"


def _daily_equal_signal_max_drawdown(
    daily_clusters: Mapping[str, Sequence[Decimal]],
) -> Decimal:
    wealth = Decimal(1)
    peak = Decimal(1)
    max_drawdown = Decimal(0)
    with localcontext(_CONTEXT):
        for session_date in sorted(daily_clusters):
            cluster = daily_clusters[session_date]
            daily_return = Decimal(
                _quantized(
                    sum(cluster, Decimal(0)) / Decimal(len(cluster)),
                    "daily equal-signal return",
                )
            )
            wealth *= Decimal(1) + daily_return
            if not wealth.is_finite() or wealth <= 0:
                raise AtomicBenchmarkIntegrityError(
                    "daily compounded wealth is non-positive"
                )
            peak = max(peak, wealth)
            max_drawdown = max(max_drawdown, (peak - wealth) / peak)
    return max_drawdown


def _bootstrap(
    daily_clusters: Mapping[str, Sequence[Decimal]], *, family_id: str, hypothesis_id: str
) -> dict[str, Any]:
    dates = tuple(sorted(daily_clusters))
    seed = f"{family_id}:{hypothesis_id}:bootstrap-v1".encode("ascii")
    lower_bound: str | None = None
    if len(dates) >= 20:
        estimates: list[Decimal] = []
        for sample in range(20000):
            total = Decimal(0)
            count = 0
            for draw in range(len(dates)):
                token = hashlib.sha256(
                    seed + sample.to_bytes(8, "big") + draw.to_bytes(4, "big")
                ).digest()
                selected = dates[int.from_bytes(token[:8], "big") % len(dates)]
                cluster = daily_clusters[selected]
                total += sum(cluster, Decimal(0))
                count += len(cluster)
            if count < 1:
                raise AtomicBenchmarkIntegrityError("bootstrap selected empty evidence")
            estimates.append(Decimal(_quantized(total / Decimal(count), "bootstrap estimate")))
        estimates.sort()
        lower_bound = decimal_text(estimates[49], "bootstrap lower bound")
    return {
        "schema_version": BOOTSTRAP_SCHEMA,
        "cluster_unit": "COMPLETE_EXIT_SESSION_DATE",
        "sample_count": 20000,
        "adjusted_alpha": "0.0025",
        "independent_date_count": len(dates),
        "seed_digest": hashlib.sha256(seed).hexdigest(),
        "lower_bound": lower_bound,
    }


def _pf_passes(value: Mapping[str, Any]) -> bool:
    if value["status"] == "POSITIVE_INFINITY":
        return True
    return value["status"] == "FINITE" and Decimal(value["value"]) > Decimal(1)


def build_summary(
    episode_rows: Iterable[Mapping[str, Any]],
    *,
    family_id: str,
    hypothesis_id: str,
    dataset_limitations: Sequence[str] = (),
) -> dict[str, Any]:
    episodes, _ = canonical_rows(episode_rows, verify_episode_row)
    pre_returns: list[Decimal] = []
    net_returns: list[Decimal] = []
    pre_pnls: list[Decimal] = []
    gross_pnls: list[Decimal] = []
    costs: list[Decimal] = []
    net_pnls: list[Decimal] = []
    daily: dict[str, list[Decimal]] = defaultdict(list)
    quarterly: dict[str, list[Decimal]] = defaultdict(list)
    for row in episodes:
        with localcontext(_CONTEXT):
            raw_entry = Decimal(row["raw_entry_open"])
            raw_exit = Decimal(row["raw_exit_close"])
            pre_return = raw_exit / raw_entry - Decimal(1)
            net_return = Decimal(row["net_pnl"]) / (raw_entry * Decimal(1000))
        pre_returns.append(pre_return)
        net_returns.append(net_return)
        pre_pnls.append(Decimal(row["pre_slippage_price_pnl"]))
        gross_pnls.append(Decimal(row["post_slippage_gross_pnl"]))
        costs.append(Decimal(row["explicit_costs"]))
        net_pnls.append(Decimal(row["net_pnl"]))
        daily[row["exit_session_date"]].append(net_return)
        quarterly[_quarter(row["exit_session_date"])].append(net_return)
    count = len(episodes)
    denominator = Decimal(count) if count else Decimal(1)
    max_drawdown = _daily_equal_signal_max_drawdown(daily)
    canonical_max_drawdown = _quantized(max_drawdown, "max drawdown")
    quarter_metrics: list[dict[str, Any]] = []
    positive_quarters = 0
    missing_quarter = False
    for quarter in COMPLETE_QUARTERS:
        values = quarterly.get(quarter, [])
        if not values:
            missing_quarter = True
            mean = "0"
        else:
            with localcontext(_CONTEXT):
                mean = _quantized(sum(values, Decimal(0)) / Decimal(len(values)), "quarter mean")
            if Decimal(mean) > 0:
                positive_quarters += 1
        quarter_metrics.append(
            {"quarter": quarter, "episode_count": len(values), "mean_net_return": mean}
        )
    bootstrap = _bootstrap(daily, family_id=family_id, hypothesis_id=hypothesis_id)
    return_pf = _profit_factor(net_returns)
    pnl_pf = _profit_factor(net_pnls)
    evidence_ok = count >= 30 and len(daily) >= 20 and not missing_quarter
    if not evidence_ok or bootstrap["lower_bound"] is None:
        disposition = "INSUFFICIENT_EVIDENCE"
    else:
        mean_pre = sum(pre_returns, Decimal(0)) / denominator
        mean_net = sum(net_returns, Decimal(0)) / denominator
        passes = (
            mean_pre > 0
            and mean_net > 0
            and _pf_passes(return_pf)
            and Decimal(bootstrap["lower_bound"]) > 0
            and positive_quarters >= 7
            and Decimal(canonical_max_drawdown) <= Decimal("0.20")
        )
        disposition = "PASS_EXPLORATORY_SCREEN" if passes else "RESEARCH_REJECT"
    limitations = ["EXPLORATORY_ONLY_NO_PROMOTION"]
    for item in dataset_limitations:
        resolved = _nonempty(item, "dataset limitation")
        if resolved not in limitations:
            limitations.append(resolved)
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "episode_count": count,
        "independent_exit_day_count": len(daily),
        "win_count": sum(value > 0 for value in net_pnls),
        "loss_count": sum(value < 0 for value in net_pnls),
        "tie_count": sum(value == 0 for value in net_pnls),
        "sum_pre_slippage_return": decimal_text(sum(pre_returns, Decimal(0)), "sum pre return"),
        "mean_pre_slippage_return": _quantized(sum(pre_returns, Decimal(0)) / denominator, "mean pre return"),
        "median_pre_slippage_return": _quantized(_median(pre_returns), "median pre return"),
        "sum_net_return": decimal_text(sum(net_returns, Decimal(0)), "sum net return"),
        "mean_net_return": _quantized(sum(net_returns, Decimal(0)) / denominator, "mean net return"),
        "median_net_return": _quantized(_median(net_returns), "median net return"),
        "sum_pre_slippage_price_pnl": decimal_text(sum(pre_pnls, Decimal(0)), "sum pre pnl"),
        "sum_post_slippage_gross_pnl": decimal_text(sum(gross_pnls, Decimal(0)), "sum gross pnl"),
        "sum_explicit_costs": decimal_text(sum(costs, Decimal(0)), "sum costs", nonnegative=True),
        "sum_net_pnl": decimal_text(sum(net_pnls, Decimal(0)), "sum net pnl"),
        "return_profit_factor": return_pf,
        "pnl_profit_factor": pnl_pf,
        "daily_equal_signal_max_drawdown": canonical_max_drawdown,
        "complete_quarter_count": len(COMPLETE_QUARTERS),
        "positive_complete_quarter_count": positive_quarters,
        "positive_complete_quarter_ratio": _quantized(
            Decimal(positive_quarters) / Decimal(len(COMPLETE_QUARTERS)),
            "positive quarter ratio",
        ),
        "quarter_metrics": quarter_metrics,
        "bootstrap": bootstrap,
        "disposition": disposition,
        "limitations": limitations,
    }
    return verify_summary(summary)


_SUMMARY_FIELDS = frozenset(
    {
        "schema_version",
        "episode_count",
        "independent_exit_day_count",
        "win_count",
        "loss_count",
        "tie_count",
        "sum_pre_slippage_return",
        "mean_pre_slippage_return",
        "median_pre_slippage_return",
        "sum_net_return",
        "mean_net_return",
        "median_net_return",
        "sum_pre_slippage_price_pnl",
        "sum_post_slippage_gross_pnl",
        "sum_explicit_costs",
        "sum_net_pnl",
        "return_profit_factor",
        "pnl_profit_factor",
        "daily_equal_signal_max_drawdown",
        "complete_quarter_count",
        "positive_complete_quarter_count",
        "positive_complete_quarter_ratio",
        "quarter_metrics",
        "bootstrap",
        "disposition",
        "limitations",
    }
)


def verify_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(value)
    require_exact_fields(summary, _SUMMARY_FIELDS, "result summary")
    if summary["schema_version"] != SUMMARY_SCHEMA:
        raise AtomicBenchmarkIntegrityError("summary schema drift")
    for field in (
        "episode_count",
        "independent_exit_day_count",
        "win_count",
        "loss_count",
        "tie_count",
        "complete_quarter_count",
        "positive_complete_quarter_count",
    ):
        _integer(summary[field], field)
    if summary["win_count"] + summary["loss_count"] + summary["tie_count"] != summary["episode_count"]:
        raise AtomicBenchmarkIntegrityError("summary outcome count mismatch")
    if summary["complete_quarter_count"] != 11:
        raise AtomicBenchmarkIntegrityError("complete quarter count drift")
    for field in (
        "sum_pre_slippage_return",
        "mean_pre_slippage_return",
        "median_pre_slippage_return",
        "sum_net_return",
        "mean_net_return",
        "median_net_return",
        "sum_pre_slippage_price_pnl",
        "sum_post_slippage_gross_pnl",
        "sum_net_pnl",
        "daily_equal_signal_max_drawdown",
        "positive_complete_quarter_ratio",
    ):
        require_decimal_text(summary[field], field, maximum_scale=18 if "sum_" not in field else None)
    require_decimal_text(summary["sum_explicit_costs"], "sum_explicit_costs", nonnegative=True)
    for name in ("return_profit_factor", "pnl_profit_factor"):
        pf = summary[name]
        require_exact_fields(dict(pf), frozenset({"status", "value"}), name)
        if pf["status"] == "FINITE":
            require_decimal_text(pf["value"], f"{name}.value", nonnegative=True, maximum_scale=18)
        elif pf["status"] in {"POSITIVE_INFINITY", "UNDEFINED"}:
            if pf["value"] is not None:
                raise AtomicBenchmarkIntegrityError(f"{name} special value must be null")
        else:
            raise AtomicBenchmarkIntegrityError(f"{name} status unsupported")
    if not isinstance(summary["quarter_metrics"], list) or len(summary["quarter_metrics"]) != 11:
        raise AtomicBenchmarkIntegrityError("quarter metrics must contain eleven rows")
    for expected, row in zip(COMPLETE_QUARTERS, summary["quarter_metrics"], strict=True):
        require_exact_fields(dict(row), frozenset({"quarter", "episode_count", "mean_net_return"}), "quarter metric")
        if row["quarter"] != expected:
            raise AtomicBenchmarkIntegrityError("quarter metric order drift")
        _integer(row["episode_count"], "quarter episode_count")
        require_decimal_text(row["mean_net_return"], "quarter mean", maximum_scale=18)
    bootstrap = dict(summary["bootstrap"])
    require_exact_fields(
        bootstrap,
        frozenset(
            {
                "schema_version",
                "cluster_unit",
                "sample_count",
                "adjusted_alpha",
                "independent_date_count",
                "seed_digest",
                "lower_bound",
            }
        ),
        "bootstrap",
    )
    if (
        bootstrap["schema_version"] != BOOTSTRAP_SCHEMA
        or bootstrap["cluster_unit"] != "COMPLETE_EXIT_SESSION_DATE"
        or bootstrap["sample_count"] != 20000
        or bootstrap["adjusted_alpha"] != "0.0025"
    ):
        raise AtomicBenchmarkIntegrityError("bootstrap contract drift")
    _integer(bootstrap["independent_date_count"], "independent_date_count")
    require_sha256(bootstrap["seed_digest"], "seed_digest")
    if bootstrap["lower_bound"] is not None:
        require_decimal_text(bootstrap["lower_bound"], "bootstrap lower_bound", maximum_scale=18)
    if summary["disposition"] not in {
        "PASS_EXPLORATORY_SCREEN",
        "RESEARCH_REJECT",
        "INSUFFICIENT_EVIDENCE",
    }:
        raise AtomicBenchmarkIntegrityError("disposition unsupported")
    if not isinstance(summary["limitations"], list) or not summary["limitations"]:
        raise AtomicBenchmarkIntegrityError("limitations must be non-empty array")
    if summary["limitations"][0] != "EXPLORATORY_ONLY_NO_PROMOTION":
        raise AtomicBenchmarkIntegrityError("exploratory limitation must be first")
    canonical_object_bytes(summary)
    return summary
