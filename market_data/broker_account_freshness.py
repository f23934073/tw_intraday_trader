"""Redacted, read-only Shioaji broker/account freshness evidence capture.

This module is intentionally an evidence collector, not a Portfolio adapter.
It never submits or cancels an order, activates a certificate, registers a
trade callback, or calls ``update_status``.  It retains timing and capability
metadata only; provider response values and account identifiers never enter an
artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic_ns
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
BROKER_ACCOUNT_CAPTURE_SCHEMA_VERSION = "broker_account_freshness_v1"
_ORDER_GAP_REASON = "REQUIRES_EXCLUDED_UPDATE_STATUS_OR_TRADE_CALLBACK"
_BUYING_POWER_LIMITATION = "ACCOUNT_BALANCE_NOT_CONFIRMED_AS_BUYING_POWER"


class BrokerEvidenceKind(StrEnum):
    POSITIONS = "POSITIONS"
    ORDERS = "ORDERS"
    ACCOUNTING = "ACCOUNTING"
    BUYING_POWER = "BUYING_POWER"


class BrokerEvidenceOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    AUTH_DENIED = "AUTH_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    SOURCE_ERROR = "SOURCE_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    CA_REQUIRED_BUT_PROHIBITED = "CA_REQUIRED_BUT_PROHIBITED"
    UNSUPPORTED_FOR_EVIDENCE_KIND = "UNSUPPORTED_FOR_EVIDENCE_KIND"


class BrokerAccountFreshnessArtifactError(ValueError):
    """A broker/account capture artifact is structurally unsafe or invalid."""


@dataclass(frozen=True)
class BrokerAccountRuntimeConfig:
    api_key: str
    secret_key: str
    simulation: bool
    sdk_version: str

    @property
    def environment(self) -> str:
        return f"shioaji:{self.sdk_version}:simulation={str(self.simulation).lower()}"


def load_broker_account_runtime_config(
    environ: Mapping[str, str] | None = None,
    *,
    sdk_version: str,
) -> BrokerAccountRuntimeConfig:
    """Read credentials without logging or returning them to a caller artifact."""
    values = os.environ if environ is None else environ
    api_key = values.get("SHIOAJI_API_KEY") or values.get("SJ_API_KEY")
    secret_key = (
        values.get("SHIOAJI_SECRET")
        or values.get("SHIOAJI_SECRET_KEY")
        or values.get("SJ_SECRET_KEY")
        or values.get("SJ_SEC_KEY")
    )
    if not api_key or not secret_key:
        raise ValueError("Shioaji broker/account credentials are not configured")
    return BrokerAccountRuntimeConfig(
        api_key=api_key,
        secret_key=secret_key,
        simulation=values.get("SJ_SIMULATION", "true").lower() != "false",
        sdk_version=sdk_version,
    )


def run_broker_account_freshness_capture(
    *,
    api_factory: Callable[[bool], object],
    config: BrokerAccountRuntimeConfig,
    output_directory: Path,
    observed_at: datetime | None = None,
    timeout_ms: int = 30_000,
) -> Path:
    """Capture one bounded, synchronous, redacted evidence artifact.

    ``ORDERS`` deliberately has no provider call.  Fresh order state requires
    an excluded action-like refresh or a prohibited callback, so the artifact
    records this as a gap instead of treating a local order cache as fresh.
    """
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be positive")
    capture_started_at = _aware_now(observed_at)
    api = api_factory(config.simulation)
    observations: list[dict[str, object]] = []
    try:
        api.login(
            api_key=config.api_key,
            secret_key=config.secret_key,
            subscribe_trade=False,
        )
        stock_account = _select_stock_account(api.list_accounts())
        observed_date = capture_started_at.date()
        observations.append(
            _observe(
                BrokerEvidenceKind.POSITIONS,
                "shioaji.api.list_positions",
                lambda: api.list_positions(account=stock_account, timeout=timeout_ms),
            )
        )
        observations.append(
            _observe(
                BrokerEvidenceKind.ACCOUNTING,
                "shioaji.api.list_profit_loss",
                lambda: api.list_profit_loss(
                    account=stock_account,
                    begin_date=observed_date.isoformat(),
                    end_date=observed_date.isoformat(),
                    timeout=timeout_ms,
                ),
            )
        )
        balance = _observe(
            BrokerEvidenceKind.BUYING_POWER,
            "shioaji.api.account_balance",
            lambda: api.account_balance(account=stock_account, timeout=timeout_ms),
        )
        # Shioaji account balance is useful account metadata, but it is not a
        # documented buying-power authority. Preserve its timing/availability
        # without allowing a later reviewer to select buying-power SLA from it.
        if balance["outcome"] == BrokerEvidenceOutcome.SUCCESS.value:
            balance.update(
                outcome=BrokerEvidenceOutcome.UNSUPPORTED_FOR_EVIDENCE_KIND.value,
                error_class=_BUYING_POWER_LIMITATION,
                capability_disposition=_BUYING_POWER_LIMITATION,
            )
        observations.append(balance)
    finally:
        try:
            api.logout()
        except Exception:
            # Logout must never mask a collected observation. It is not written
            # to the evidence artifact because it is not one of the four kinds.
            pass

    capture_completed_at = _aware_now()
    payload = {
        "schema_version": BROKER_ACCOUNT_CAPTURE_SCHEMA_VERSION,
        "artifact_kind": "BROKER_ACCOUNT_READ_ONLY_FRESHNESS_EVIDENCE",
        "capture_id": str(uuid4()),
        "captured_at": capture_started_at.isoformat(),
        "completed_at": capture_completed_at.isoformat(),
        "environment": config.environment,
        "account_scope": "STOCK_ACCOUNT_SELECTED_REDACTED",
        "projection_boundary": "broker_account_calibration_metadata_only",
        "guardrails": {
            "submit_order": False,
            "cancel_order": False,
            "modify_order": False,
            "activate_ca": False,
            "subscribe_trade": False,
            "trade_callback": False,
            "update_status": False,
            "retry": False,
        },
        "observations": observations,
        "evidence_gaps": [
            {
                "evidence_kind": BrokerEvidenceKind.ORDERS.value,
                "source_reference": "shioaji.api.update_status + shioaji.api.list_trades",
                "invoked": False,
                "reason": _ORDER_GAP_REASON,
                "threshold_supported": False,
            }
        ],
        "threshold_selection": "PROHIBITED_IN_CAPTURE_ARTIFACT",
        "limitations": [
            "No raw provider response, credential, account identifier, position, balance, PnL, or order detail is persisted.",
            "Successful response receipt is not a source-as-of guarantee when the provider omits an explicit as-of timestamp.",
            "Account balance is not treated as a documented buying-power authority.",
            "Orders freshness is unavailable under the approved no-update-status/no-callback constraint.",
        ],
    }
    validate_broker_account_freshness_payload(payload)
    output_path = _artifact_path(output_directory, capture_started_at, payload["capture_id"])
    _write_json_once(output_path, payload)
    return output_path


def inspect_broker_account_freshness_artifact(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BrokerAccountFreshnessArtifactError("artifact must be valid JSON") from error
    if not isinstance(payload, Mapping):
        raise BrokerAccountFreshnessArtifactError("artifact must be an object")
    validate_broker_account_freshness_payload(payload)
    observations = payload["observations"]
    assert isinstance(observations, list)
    return {
        "artifact_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
        "schema_version": BROKER_ACCOUNT_CAPTURE_SCHEMA_VERSION,
        "observation_count": len(observations),
        "evidence_kinds": [item["evidence_kind"] for item in observations],
        "evidence_gaps": payload["evidence_gaps"],
        "threshold_candidates": None,
        "review_status": "REVIEW_REQUIRED",
    }


def validate_broker_account_freshness_payload(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != BROKER_ACCOUNT_CAPTURE_SCHEMA_VERSION:
        raise BrokerAccountFreshnessArtifactError("unexpected schema_version")
    if payload.get("artifact_kind") != "BROKER_ACCOUNT_READ_ONLY_FRESHNESS_EVIDENCE":
        raise BrokerAccountFreshnessArtifactError("unexpected artifact_kind")
    if payload.get("threshold_selection") != "PROHIBITED_IN_CAPTURE_ARTIFACT":
        raise BrokerAccountFreshnessArtifactError("artifact must not select thresholds")
    guardrails = payload.get("guardrails")
    if not isinstance(guardrails, Mapping) or any(value is not False for value in guardrails.values()):
        raise BrokerAccountFreshnessArtifactError("read-only guardrails must all be false")
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise BrokerAccountFreshnessArtifactError("observations must be a list")
    expected = {
        BrokerEvidenceKind.POSITIONS.value,
        BrokerEvidenceKind.ACCOUNTING.value,
        BrokerEvidenceKind.BUYING_POWER.value,
    }
    actual = {item.get("evidence_kind") for item in observations if isinstance(item, Mapping)}
    if actual != expected or len(observations) != len(expected):
        raise BrokerAccountFreshnessArtifactError("missing or duplicate endpoint observation")
    for item in observations:
        if not isinstance(item, Mapping):
            raise BrokerAccountFreshnessArtifactError("observation must be an object")
        _validate_observation(item)
    gaps = payload.get("evidence_gaps")
    if not isinstance(gaps, list) or len(gaps) != 1 or not isinstance(gaps[0], Mapping):
        raise BrokerAccountFreshnessArtifactError("orders evidence gap is required")
    gap = gaps[0]
    if gap.get("evidence_kind") != BrokerEvidenceKind.ORDERS.value:
        raise BrokerAccountFreshnessArtifactError("orders gap has the wrong evidence kind")
    if gap.get("invoked") is not False or gap.get("reason") != _ORDER_GAP_REASON:
        raise BrokerAccountFreshnessArtifactError("orders gap must show the excluded source was not invoked")


def _observe(
    evidence_kind: BrokerEvidenceKind,
    source_reference: str,
    call: Callable[[], object],
) -> dict[str, object]:
    request_started_at = _aware_now()
    request_started_monotonic_ns = monotonic_ns()
    try:
        response = call()
    except Exception as error:
        response_received_at = _aware_now()
        response_received_monotonic_ns = monotonic_ns()
        outcome, error_class = _classify_exception(error)
        observation = _observation_base(
            evidence_kind,
            source_reference,
            request_started_at,
            response_received_at,
            request_started_monotonic_ns,
            response_received_monotonic_ns,
        )
        observation.update(
            outcome=outcome.value,
            error_class=error_class,
            source_as_of_at=None,
            source_as_of_disposition="UNAVAILABLE_DUE_TO_REQUEST_FAILURE",
            response_shape=None,
            capability_disposition="UNAVAILABLE",
        )
        return observation
    response_received_at = _aware_now()
    response_received_monotonic_ns = monotonic_ns()
    source_as_of_at, source_as_of_disposition = _extract_source_as_of(response)
    observation = _observation_base(
        evidence_kind,
        source_reference,
        request_started_at,
        response_received_at,
        request_started_monotonic_ns,
        response_received_monotonic_ns,
    )
    observation.update(
        outcome=BrokerEvidenceOutcome.SUCCESS.value,
        error_class=None,
        source_as_of_at=(source_as_of_at.isoformat() if source_as_of_at is not None else None),
        source_as_of_disposition=source_as_of_disposition,
        response_shape=_response_shape(response),
        capability_disposition="ENDPOINT_RESPONSE_RECEIVED",
    )
    return observation


def _observation_base(
    evidence_kind: BrokerEvidenceKind,
    source_reference: str,
    request_started_at: datetime,
    response_received_at: datetime,
    request_started_monotonic_ns: int,
    response_received_monotonic_ns: int,
) -> dict[str, object]:
    projection_updated_at = _aware_now()
    return {
        "probe_id": str(uuid4()),
        "evidence_kind": evidence_kind.value,
        "source_reference": source_reference,
        "request_started_at": request_started_at.isoformat(),
        "response_received_at": response_received_at.isoformat(),
        "projection_updated_at": projection_updated_at.isoformat(),
        "round_trip_ms": max(
            0.0,
            (response_received_monotonic_ns - request_started_monotonic_ns) / 1_000_000,
        ),
    }


def _select_stock_account(accounts: Sequence[object]) -> object:
    for account in accounts:
        account_type = str(getattr(account, "account_type", "")).upper()
        if account_type == "S":
            return account
    raise RuntimeError("STOCK_ACCOUNT_UNAVAILABLE")


def _extract_source_as_of(response: object) -> tuple[datetime | None, str]:
    """Use only explicit timestamp fields; a business date alone is not as-of."""
    candidates = _response_items(response)
    parsed: set[datetime] = set()
    for item in candidates:
        for field_name in ("as_of", "as_of_at", "updated_at", "timestamp", "datetime"):
            value = getattr(item, field_name, None)
            if isinstance(value, datetime):
                if value.tzinfo is not None and value.utcoffset() is not None:
                    parsed.add(value.astimezone(TAIPEI))
    if len(parsed) == 1:
        return parsed.pop(), "EXPLICIT_PROVIDER_TIMESTAMP"
    if parsed:
        return None, "MULTIPLE_PROVIDER_TIMESTAMPS_NOT_A_SINGLE_AS_OF"
    if any(hasattr(item, "date") for item in candidates):
        return None, "DATE_ONLY_NOT_AS_OF"
    return None, "UNAVAILABLE"


def _response_shape(response: object) -> dict[str, object]:
    items = _response_items(response)
    field_names: set[str] = set()
    item_types: set[str] = set()
    for item in items[:3]:
        item_types.add(type(item).__name__)
        if isinstance(item, Mapping):
            field_names.update(str(key) for key in item.keys())
        else:
            field_names.update(
                name for name in vars(item).keys() if not name.startswith("_")
            )
    return {
        "container_type": type(response).__name__,
        "item_count": len(items),
        "item_types": sorted(item_types),
        "field_names": sorted(field_names),
    }


def _response_items(response: object) -> list[object]:
    if isinstance(response, (str, bytes, bytearray, Mapping)):
        return [response]
    if isinstance(response, Sequence):
        return list(response)
    return [response]


def _classify_exception(error: Exception) -> tuple[BrokerEvidenceOutcome, str]:
    detail = str(error).upper()
    if ("CA" in detail or "CERTIFICATE" in detail) and "REQUIRED" in detail:
        return BrokerEvidenceOutcome.CA_REQUIRED_BUT_PROHIBITED, "CA_REQUIRED_BUT_PROHIBITED"
    if "TIMEOUT" in detail or "TIMED OUT" in detail:
        return BrokerEvidenceOutcome.TIMEOUT, type(error).__name__
    if "AUTH" in detail or "PERMISSION" in detail or "UNAUTHORIZED" in detail:
        return BrokerEvidenceOutcome.AUTH_DENIED, type(error).__name__
    if "RATE" in detail or "TOO MANY" in detail:
        return BrokerEvidenceOutcome.RATE_LIMITED, type(error).__name__
    return BrokerEvidenceOutcome.SOURCE_ERROR, type(error).__name__


def _validate_observation(item: Mapping[str, object]) -> None:
    required = {
        "probe_id",
        "evidence_kind",
        "source_reference",
        "request_started_at",
        "response_received_at",
        "projection_updated_at",
        "round_trip_ms",
        "outcome",
        "error_class",
        "source_as_of_at",
        "source_as_of_disposition",
        "response_shape",
        "capability_disposition",
    }
    if set(item) != required:
        raise BrokerAccountFreshnessArtifactError("observation fields do not match the redacted schema")
    for field_name in ("request_started_at", "response_received_at", "projection_updated_at"):
        value = item[field_name]
        if not isinstance(value, str) or _parse_aware(value) is None:
            raise BrokerAccountFreshnessArtifactError(f"{field_name} must be timezone-aware")
    if item["source_as_of_at"] is not None:
        if not isinstance(item["source_as_of_at"], str) or _parse_aware(item["source_as_of_at"]) is None:
            raise BrokerAccountFreshnessArtifactError("source_as_of_at must be timezone-aware or null")
    if not isinstance(item["round_trip_ms"], (int, float)) or item["round_trip_ms"] < 0:
        raise BrokerAccountFreshnessArtifactError("round_trip_ms must be non-negative")


def _parse_aware(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _artifact_path(directory: Path, captured_at: datetime, capture_id: object) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = captured_at.astimezone(TAIPEI).strftime("%Y%m%dT%H%M%S%z")
    return directory / f"broker_account_{stamp}_{str(capture_id)[:8]}.json"


def _write_json_once(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _aware_now(value: datetime | None = None) -> datetime:
    current = datetime.now(TAIPEI) if value is None else value
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return current.astimezone(TAIPEI)
