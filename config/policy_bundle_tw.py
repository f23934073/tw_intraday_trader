"""Unwired, fail-closed Taiwan policy bundle contract.

This module seals current policy inputs for review.  It is deliberately not a
runtime admission API: evidence cross-binding is deferred until a real Wave-2
consumer has an approved evidence scope.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn, cast

from backtest.cost_policy_tw import (
    cost_policy_readiness_reason,
    verify_cost_policy_snapshot,
)
from backtest.execution_policy_tw import (
    execution_policy_readiness_reason,
    verify_execution_policy_snapshot,
)
from config.no_overnight import (
    ControllerGuardKind,
    ControllerHostingMode,
    NoOvernightMode,
    NoOvernightPolicyConfig,
)

__all__ = [
    "ACTIVATION_AUTHORITY",
    "BROKER_MARKET_ACCEPTANCE_STATUS",
    "POLICY_BUNDLE_CONTRACT_VERSION",
    "POLICY_BUNDLE_VALIDATION_VERSION",
    "RUNTIME_CONSUMER_STATUS",
    "WIRING_STATUS",
    "BrokerPolicyTW",
    "ExitOwnershipTW",
    "LegalReferenceTW",
    "PolicyBundleError",
    "PolicyBundleProvenanceTW",
    "PolicyBundleTW",
    "RiskExitRatios",
    "SessionCalendarTW",
    "verify_policy_bundle_snapshot",
]


POLICY_BUNDLE_CONTRACT_VERSION = "tw-policy-bundle-v2"
POLICY_BUNDLE_VALIDATION_VERSION = "current-api-sa2c-self-pin-exact-v1"
WIRING_STATUS = "NOT_WIRED"
RUNTIME_CONSUMER_STATUS = "NO_RUNTIME_CONSUMER"
ACTIVATION_AUTHORITY = "NO_ACTIVATION_AUTHORITY"
BROKER_MARKET_ACCEPTANCE_STATUS = "MARKET_ACCEPTANCE_BLOCKED_COMMISSION_SOT"

_EXPECTED_SOURCE_COMMIT = "dbcd9bcb0ba0c13f889f21575bdf0b6d3e5887af"
_EXPECTED_SOURCE_TREE = "6dba3bf2f44aac7080abb9001626efb43cc94e78"
_EXPECTED_REQUIREMENTS_DIGEST = "21b845278395117a4460b8e6bbae8208488bc09e7718fcf4489954c730ffaa71"

_TOP_LEVEL_KEYS = frozenset(
    {
        "contract_version",
        "validation_algorithm_version",
        "execution_policy_snapshot",
        "cost_policy_snapshot",
        "no_overnight_policy",
        "legal_reference",
        "broker_policy",
        "exit_ratios",
        "session_calendar",
        "exit_ownership",
        "provenance",
        "wiring_status",
        "runtime_consumer_status",
        "activation_authority",
        "bundle_digest",
    }
)
_NO_OVERNIGHT_KEYS = frozenset(
    {
        "schema_version",
        "validation_algorithm_version",
        "mode",
        "account_scope_id",
        "policy_family_id",
        "policy_version",
        "timezone",
        "market_open",
        "no_new_entry_at",
        "cancel_entry_at",
        "flatten_at",
        "aggressive_exit_at",
        "final_reconciliation_at",
        "reviewed_session_close",
        "max_exit_attempts",
        "retry_cooldown_seconds",
        "executable_book_policy_id",
        "controller_hosting_mode",
        "controller_guard_kind",
    }
)


class PolicyBundleError(ValueError):
    """A deterministic fail-closed PolicyBundle validation error."""

    code = "BUNDLE_INVALID"


def _refuse(message: str) -> NoReturn:
    raise PolicyBundleError(f"BUNDLE_INVALID: {message}")


def _as_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _refuse(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact_mapping(
    value: Any,
    *,
    keys: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    mapping = _as_mapping(value, label=label)
    if any(type(key) is not str for key in mapping):
        _refuse(f"{label} keys must be strings")
    actual = set(mapping)
    missing = sorted(keys - actual)
    unknown = sorted(actual - keys)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unknown:
            details.append("unknown=" + ",".join(unknown))
        _refuse(f"{label} exact-key mismatch ({'; '.join(details)})")
    return mapping


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise PolicyBundleError("BUNDLE_INVALID: payload is not canonical JSON") from error


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_text(value: Any, *, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        _refuse(f"{label} must be a non-empty trimmed string")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    parsed = _require_text(value, label=label)
    if len(parsed) != 64 or any(character not in "0123456789abcdef" for character in parsed):
        _refuse(f"{label} must be a lowercase SHA-256")
    return parsed


def _require_git_oid(value: Any, *, label: str) -> str:
    parsed = _require_text(value, label=label)
    if len(parsed) != 40 or any(character not in "0123456789abcdef" for character in parsed):
        _refuse(f"{label} must be a lowercase 40-character Git object id")
    return parsed


def _require_positive_int(value: Any, *, label: str) -> int:
    if type(value) is not int or value <= 0:
        _refuse(f"{label} must be a positive integer")
    return value


def _require_date(value: Any, *, label: str) -> date:
    if type(value) is not date:
        _refuse(f"{label} must be a date")
    return value


def _date_from_payload(value: Any, *, label: str) -> date:
    text = _require_text(value, label=label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise PolicyBundleError(f"BUNDLE_INVALID: {label} must be an ISO date") from error
    if parsed.isoformat() != text:
        _refuse(f"{label} must be a canonical ISO date")
    return parsed


def _optional_date_from_payload(value: Any, *, label: str) -> date | None:
    return None if value is None else _date_from_payload(value, label=label)


def _require_decimal_text(value: Any, *, label: str) -> str:
    text = _require_text(value, label=label)
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise PolicyBundleError(f"BUNDLE_INVALID: {label} must be a decimal") from error
    if not parsed.is_finite():
        _refuse(f"{label} must be finite")
    return text


def _require_string_tuple(value: Any, *, label: str) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        _refuse(f"{label} must be a non-empty tuple of strings")
    parsed = tuple(_require_text(item, label=f"{label}[]") for item in value)
    if len(parsed) != len(set(parsed)):
        _refuse(f"{label} must not contain duplicates")
    return parsed


def _string_list_from_payload(value: Any, *, label: str) -> tuple[str, ...]:
    if type(value) is not list or not value:
        _refuse(f"{label} must be a non-empty JSON list of strings")
    parsed = tuple(_require_text(item, label=f"{label}[]") for item in value)
    if len(parsed) != len(set(parsed)):
        _refuse(f"{label} must not contain duplicates")
    return parsed


def _validate_window(
    *,
    effective_from: date,
    effective_through: date | None,
    reviewed_on: date,
    label: str,
) -> None:
    if effective_through is not None and effective_through < effective_from:
        _refuse(f"{label} effective window is reversed")
    if reviewed_on < effective_from:
        _refuse(f"{label} review predates the effective window")


def _time_from_payload(value: Any, *, label: str) -> time | None:
    if value is None:
        return None
    text = _require_text(value, label=label)
    try:
        parsed = time.fromisoformat(text)
    except ValueError as error:
        raise PolicyBundleError(f"BUNDLE_INVALID: {label} must be an ISO time") from error
    if parsed.isoformat(timespec="microseconds") != text:
        _refuse(f"{label} must preserve microseconds canonically")
    return parsed


def _optional_positive_int(value: Any, *, label: str) -> int | None:
    return None if value is None else _require_positive_int(value, label=label)


def _no_overnight_from_payload(value: Any) -> NoOvernightPolicyConfig:
    payload = _exact_mapping(value, keys=_NO_OVERNIGHT_KEYS, label="no_overnight_policy")
    try:
        policy = NoOvernightPolicyConfig(
            mode=NoOvernightMode(_require_text(payload["mode"], label="policy.mode")),
            account_scope_id=_require_text(
                payload["account_scope_id"], label="policy.account_scope_id"
            ),
            policy_family_id=_require_text(
                payload["policy_family_id"], label="policy.policy_family_id"
            ),
            policy_version=_require_text(payload["policy_version"], label="policy.policy_version"),
            timezone=_require_text(payload["timezone"], label="policy.timezone"),
            market_open=_time_from_payload(payload["market_open"], label="policy.market_open"),
            no_new_entry_at=_time_from_payload(
                payload["no_new_entry_at"], label="policy.no_new_entry_at"
            ),
            cancel_entry_at=_time_from_payload(
                payload["cancel_entry_at"], label="policy.cancel_entry_at"
            ),
            flatten_at=_time_from_payload(payload["flatten_at"], label="policy.flatten_at"),
            aggressive_exit_at=_time_from_payload(
                payload["aggressive_exit_at"], label="policy.aggressive_exit_at"
            ),
            final_reconciliation_at=_time_from_payload(
                payload["final_reconciliation_at"],
                label="policy.final_reconciliation_at",
            ),
            reviewed_session_close=_time_from_payload(
                payload["reviewed_session_close"],
                label="policy.reviewed_session_close",
            ),
            max_exit_attempts=_optional_positive_int(
                payload["max_exit_attempts"], label="policy.max_exit_attempts"
            ),
            retry_cooldown_seconds=_optional_positive_int(
                payload["retry_cooldown_seconds"],
                label="policy.retry_cooldown_seconds",
            ),
            executable_book_policy_id=(
                None
                if payload["executable_book_policy_id"] is None
                else _require_text(
                    payload["executable_book_policy_id"],
                    label="policy.executable_book_policy_id",
                )
            ),
            controller_hosting_mode=ControllerHostingMode(
                _require_text(
                    payload["controller_hosting_mode"],
                    label="policy.controller_hosting_mode",
                )
            ),
            controller_guard_kind=ControllerGuardKind(
                _require_text(
                    payload["controller_guard_kind"],
                    label="policy.controller_guard_kind",
                )
            ),
            schema_version=_require_text(payload["schema_version"], label="policy.schema_version"),
            validation_algorithm_version=_require_text(
                payload["validation_algorithm_version"],
                label="policy.validation_algorithm_version",
            ),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, PolicyBundleError):
            raise
        raise PolicyBundleError("BUNDLE_INVALID: no_overnight_policy is invalid") from error
    if policy.canonical_payload() != dict(payload):
        _refuse("no_overnight_policy is not canonical")
    return policy


@dataclass(frozen=True, slots=True)
class LegalReferenceTW:
    authority: str
    rule_id: str
    source_ids: tuple[str, ...]
    instrument_class_scope: tuple[str, ...]
    effective_from: date
    effective_through: date | None
    reviewed_on: date
    source_digest: str
    schema_version: str = "tw-legal-reference-v2"

    _KEYS = frozenset(
        {
            "schema_version",
            "authority",
            "rule_id",
            "source_ids",
            "instrument_class_scope",
            "effective_from",
            "effective_through",
            "reviewed_on",
            "source_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != "tw-legal-reference-v2":
            _refuse("legal_reference schema_version is unsupported")
        for field_name in ("authority", "rule_id"):
            _require_text(getattr(self, field_name), label=f"legal_reference.{field_name}")
        _require_string_tuple(self.source_ids, label="legal_reference.source_ids")
        _require_string_tuple(
            self.instrument_class_scope,
            label="legal_reference.instrument_class_scope",
        )
        _require_date(self.effective_from, label="legal_reference.effective_from")
        if self.effective_through is not None:
            _require_date(self.effective_through, label="legal_reference.effective_through")
        _require_date(self.reviewed_on, label="legal_reference.reviewed_on")
        _validate_window(
            effective_from=self.effective_from,
            effective_through=self.effective_through,
            reviewed_on=self.reviewed_on,
            label="legal_reference",
        )
        _require_sha256(self.source_digest, label="legal_reference.source_digest")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authority": self.authority,
            "rule_id": self.rule_id,
            "source_ids": list(self.source_ids),
            "instrument_class_scope": list(self.instrument_class_scope),
            "effective_from": self.effective_from.isoformat(),
            "effective_through": (
                None if self.effective_through is None else self.effective_through.isoformat()
            ),
            "reviewed_on": self.reviewed_on.isoformat(),
            "source_digest": self.source_digest,
        }

    @classmethod
    def from_payload(cls, value: Any) -> "LegalReferenceTW":
        payload = _exact_mapping(value, keys=cls._KEYS, label="legal_reference")
        return cls(
            authority=_require_text(payload["authority"], label="legal_reference.authority"),
            rule_id=_require_text(payload["rule_id"], label="legal_reference.rule_id"),
            source_ids=_string_list_from_payload(
                payload["source_ids"], label="legal_reference.source_ids"
            ),
            instrument_class_scope=_string_list_from_payload(
                payload["instrument_class_scope"],
                label="legal_reference.instrument_class_scope",
            ),
            effective_from=_date_from_payload(
                payload["effective_from"], label="legal_reference.effective_from"
            ),
            effective_through=_optional_date_from_payload(
                payload["effective_through"],
                label="legal_reference.effective_through",
            ),
            reviewed_on=_date_from_payload(
                payload["reviewed_on"], label="legal_reference.reviewed_on"
            ),
            source_digest=_require_sha256(
                payload["source_digest"], label="legal_reference.source_digest"
            ),
            schema_version=_require_text(
                payload["schema_version"], label="legal_reference.schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class BrokerPolicyTW:
    broker_id: str
    account_scope_id: str
    terms_version: str
    commission_rate: str
    min_commission_twd: str
    effective_from: date
    effective_through: date | None
    reviewed_on: date
    terms_evidence_digest: str
    market_acceptance_status: str = BROKER_MARKET_ACCEPTANCE_STATUS
    schema_version: str = "tw-broker-policy-v2"

    _KEYS = frozenset(
        {
            "schema_version",
            "broker_id",
            "account_scope_id",
            "terms_version",
            "commission_rate",
            "min_commission_twd",
            "effective_from",
            "effective_through",
            "reviewed_on",
            "terms_evidence_digest",
            "market_acceptance_status",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != "tw-broker-policy-v2":
            _refuse("broker_policy schema_version is unsupported")
        for field_name in ("broker_id", "account_scope_id", "terms_version"):
            _require_text(getattr(self, field_name), label=f"broker_policy.{field_name}")
        commission = Decimal(
            _require_decimal_text(self.commission_rate, label="broker_policy.commission_rate")
        )
        minimum = Decimal(
            _require_decimal_text(self.min_commission_twd, label="broker_policy.min_commission_twd")
        )
        if commission < 0 or minimum < 0:
            _refuse("broker_policy rates must be non-negative")
        _require_date(self.effective_from, label="broker_policy.effective_from")
        if self.effective_through is not None:
            _require_date(self.effective_through, label="broker_policy.effective_through")
        _require_date(self.reviewed_on, label="broker_policy.reviewed_on")
        _validate_window(
            effective_from=self.effective_from,
            effective_through=self.effective_through,
            reviewed_on=self.reviewed_on,
            label="broker_policy",
        )
        _require_sha256(
            self.terms_evidence_digest,
            label="broker_policy.terms_evidence_digest",
        )
        if self.market_acceptance_status != BROKER_MARKET_ACCEPTANCE_STATUS:
            _refuse("broker_policy market acceptance status is unsupported")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "broker_id": self.broker_id,
            "account_scope_id": self.account_scope_id,
            "terms_version": self.terms_version,
            "commission_rate": self.commission_rate,
            "min_commission_twd": self.min_commission_twd,
            "effective_from": self.effective_from.isoformat(),
            "effective_through": (
                None if self.effective_through is None else self.effective_through.isoformat()
            ),
            "reviewed_on": self.reviewed_on.isoformat(),
            "terms_evidence_digest": self.terms_evidence_digest,
            "market_acceptance_status": self.market_acceptance_status,
        }

    @classmethod
    def from_payload(cls, value: Any) -> "BrokerPolicyTW":
        payload = _exact_mapping(value, keys=cls._KEYS, label="broker_policy")
        return cls(
            broker_id=_require_text(payload["broker_id"], label="broker_policy.broker_id"),
            account_scope_id=_require_text(
                payload["account_scope_id"], label="broker_policy.account_scope_id"
            ),
            terms_version=_require_text(
                payload["terms_version"], label="broker_policy.terms_version"
            ),
            commission_rate=_require_decimal_text(
                payload["commission_rate"], label="broker_policy.commission_rate"
            ),
            min_commission_twd=_require_decimal_text(
                payload["min_commission_twd"], label="broker_policy.min_commission_twd"
            ),
            effective_from=_date_from_payload(
                payload["effective_from"], label="broker_policy.effective_from"
            ),
            effective_through=_optional_date_from_payload(
                payload["effective_through"], label="broker_policy.effective_through"
            ),
            reviewed_on=_date_from_payload(
                payload["reviewed_on"], label="broker_policy.reviewed_on"
            ),
            terms_evidence_digest=_require_sha256(
                payload["terms_evidence_digest"],
                label="broker_policy.terms_evidence_digest",
            ),
            market_acceptance_status=_require_text(
                payload["market_acceptance_status"],
                label="broker_policy.market_acceptance_status",
            ),
            schema_version=_require_text(
                payload["schema_version"], label="broker_policy.schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class RiskExitRatios:
    stop_loss_ratio: str
    take_profit_ratio: str
    schema_version: str = "tw-risk-exit-ratios-v2"

    _KEYS = frozenset({"schema_version", "stop_loss_ratio", "take_profit_ratio"})

    def __post_init__(self) -> None:
        if self.schema_version != "tw-risk-exit-ratios-v2":
            _refuse("exit_ratios schema_version is unsupported")
        stop_loss = Decimal(
            _require_decimal_text(self.stop_loss_ratio, label="exit_ratios.stop_loss_ratio")
        )
        take_profit = Decimal(
            _require_decimal_text(self.take_profit_ratio, label="exit_ratios.take_profit_ratio")
        )
        if not Decimal("0") < stop_loss < Decimal("1"):
            _refuse("stop_loss_ratio must be strictly between 0 and 1")
        if not Decimal("0") < take_profit < Decimal("1"):
            _refuse("take_profit_ratio must be strictly between 0 and 1")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "stop_loss_ratio": self.stop_loss_ratio,
            "take_profit_ratio": self.take_profit_ratio,
        }

    @classmethod
    def from_payload(cls, value: Any) -> "RiskExitRatios":
        payload = _exact_mapping(value, keys=cls._KEYS, label="exit_ratios")
        return cls(
            stop_loss_ratio=_require_decimal_text(
                payload["stop_loss_ratio"], label="exit_ratios.stop_loss_ratio"
            ),
            take_profit_ratio=_require_decimal_text(
                payload["take_profit_ratio"], label="exit_ratios.take_profit_ratio"
            ),
            schema_version=_require_text(
                payload["schema_version"], label="exit_ratios.schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class SessionCalendarTW:
    calendar_id: str
    calendar_digest: str
    timezone: str
    trading_date: date
    covered_from: date
    covered_through: date
    reviewed_on: date
    session_kind: str = "REGULAR"
    schema_version: str = "tw-session-calendar-v2"

    _KEYS = frozenset(
        {
            "schema_version",
            "calendar_id",
            "calendar_digest",
            "timezone",
            "trading_date",
            "covered_from",
            "covered_through",
            "reviewed_on",
            "session_kind",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != "tw-session-calendar-v2":
            _refuse("session_calendar schema_version is unsupported")
        _require_text(self.calendar_id, label="session_calendar.calendar_id")
        _require_sha256(self.calendar_digest, label="session_calendar.calendar_digest")
        _require_text(self.timezone, label="session_calendar.timezone")
        for field_name in ("trading_date", "covered_from", "covered_through", "reviewed_on"):
            _require_date(getattr(self, field_name), label=f"session_calendar.{field_name}")
        if self.covered_through < self.covered_from:
            _refuse("session_calendar coverage is reversed")
        if not self.covered_from <= self.trading_date <= self.covered_through:
            _refuse("session_calendar does not cover trading_date")
        if self.reviewed_on > self.trading_date:
            _refuse("session_calendar review is after trading_date")
        if self.session_kind != "REGULAR":
            _refuse("session_calendar session_kind is unsupported")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "calendar_id": self.calendar_id,
            "calendar_digest": self.calendar_digest,
            "timezone": self.timezone,
            "trading_date": self.trading_date.isoformat(),
            "covered_from": self.covered_from.isoformat(),
            "covered_through": self.covered_through.isoformat(),
            "reviewed_on": self.reviewed_on.isoformat(),
            "session_kind": self.session_kind,
        }

    @classmethod
    def from_payload(cls, value: Any) -> "SessionCalendarTW":
        payload = _exact_mapping(value, keys=cls._KEYS, label="session_calendar")
        return cls(
            calendar_id=_require_text(payload["calendar_id"], label="session_calendar.calendar_id"),
            calendar_digest=_require_sha256(
                payload["calendar_digest"], label="session_calendar.calendar_digest"
            ),
            timezone=_require_text(payload["timezone"], label="session_calendar.timezone"),
            trading_date=_date_from_payload(
                payload["trading_date"], label="session_calendar.trading_date"
            ),
            covered_from=_date_from_payload(
                payload["covered_from"], label="session_calendar.covered_from"
            ),
            covered_through=_date_from_payload(
                payload["covered_through"], label="session_calendar.covered_through"
            ),
            reviewed_on=_date_from_payload(
                payload["reviewed_on"], label="session_calendar.reviewed_on"
            ),
            session_kind=_require_text(
                payload["session_kind"], label="session_calendar.session_kind"
            ),
            schema_version=_require_text(
                payload["schema_version"], label="session_calendar.schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class ExitOwnershipTW:
    revision: int
    account_scope_id: str
    policy_family_id: str
    entry_owner: str
    stop_loss_owner: str
    take_profit_owner: str
    end_of_day_owner: str
    priority_order: tuple[str, ...]
    schema_version: str = "tw-exit-ownership-v2"

    _KEYS = frozenset(
        {
            "schema_version",
            "revision",
            "account_scope_id",
            "policy_family_id",
            "entry_owner",
            "stop_loss_owner",
            "take_profit_owner",
            "end_of_day_owner",
            "priority_order",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != "tw-exit-ownership-v2":
            _refuse("exit_ownership schema_version is unsupported")
        _require_positive_int(self.revision, label="exit_ownership.revision")
        for field_name in (
            "account_scope_id",
            "policy_family_id",
            "entry_owner",
            "stop_loss_owner",
            "take_profit_owner",
            "end_of_day_owner",
        ):
            _require_text(getattr(self, field_name), label=f"exit_ownership.{field_name}")
        priority = _require_string_tuple(
            self.priority_order,
            label="exit_ownership.priority_order",
        )
        expected = {
            self.stop_loss_owner,
            self.take_profit_owner,
            self.end_of_day_owner,
        }
        if set(priority) != expected:
            _refuse("exit_ownership priority_order must contain every exit owner exactly once")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "entry_owner": self.entry_owner,
            "stop_loss_owner": self.stop_loss_owner,
            "take_profit_owner": self.take_profit_owner,
            "end_of_day_owner": self.end_of_day_owner,
            "priority_order": list(self.priority_order),
        }

    @classmethod
    def from_payload(cls, value: Any) -> "ExitOwnershipTW":
        payload = _exact_mapping(value, keys=cls._KEYS, label="exit_ownership")
        return cls(
            revision=_require_positive_int(payload["revision"], label="exit_ownership.revision"),
            account_scope_id=_require_text(
                payload["account_scope_id"], label="exit_ownership.account_scope_id"
            ),
            policy_family_id=_require_text(
                payload["policy_family_id"], label="exit_ownership.policy_family_id"
            ),
            entry_owner=_require_text(payload["entry_owner"], label="exit_ownership.entry_owner"),
            stop_loss_owner=_require_text(
                payload["stop_loss_owner"], label="exit_ownership.stop_loss_owner"
            ),
            take_profit_owner=_require_text(
                payload["take_profit_owner"], label="exit_ownership.take_profit_owner"
            ),
            end_of_day_owner=_require_text(
                payload["end_of_day_owner"], label="exit_ownership.end_of_day_owner"
            ),
            priority_order=_string_list_from_payload(
                payload["priority_order"], label="exit_ownership.priority_order"
            ),
            schema_version=_require_text(
                payload["schema_version"], label="exit_ownership.schema_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class PolicyBundleProvenanceTW:
    source_commit: str
    source_tree: str
    requirements_digest: str
    builder_identity: str
    fixture_id: str
    schema_version: str = "tw-policy-bundle-provenance-v2"

    _BASE_KEYS = frozenset(
        {
            "schema_version",
            "source_commit",
            "source_tree",
            "requirements_digest",
            "builder_identity",
            "fixture_id",
        }
    )
    _SEALED_KEYS = _BASE_KEYS | frozenset({"derived_policy_digests", "calibration_reasons"})

    def __post_init__(self) -> None:
        if self.schema_version != "tw-policy-bundle-provenance-v2":
            _refuse("provenance schema_version is unsupported")
        _require_git_oid(self.source_commit, label="provenance.source_commit")
        _require_git_oid(self.source_tree, label="provenance.source_tree")
        _require_sha256(self.requirements_digest, label="provenance.requirements_digest")
        _require_text(self.builder_identity, label="provenance.builder_identity")
        _require_text(self.fixture_id, label="provenance.fixture_id")
        if self.source_commit != _EXPECTED_SOURCE_COMMIT:
            _refuse("provenance source_commit is not the approved current parent")
        if self.source_tree != _EXPECTED_SOURCE_TREE:
            _refuse("provenance source_tree is not the approved current tree")
        if self.requirements_digest != _EXPECTED_REQUIREMENTS_DIGEST:
            _refuse("provenance requirements_digest is not the approved Task356 SoT")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "requirements_digest": self.requirements_digest,
            "builder_identity": self.builder_identity,
            "fixture_id": self.fixture_id,
        }

    @classmethod
    def from_sealed_payload(cls, value: Any) -> "PolicyBundleProvenanceTW":
        payload = _exact_mapping(value, keys=cls._SEALED_KEYS, label="provenance")
        return cls(
            source_commit=_require_git_oid(
                payload["source_commit"], label="provenance.source_commit"
            ),
            source_tree=_require_git_oid(payload["source_tree"], label="provenance.source_tree"),
            requirements_digest=_require_sha256(
                payload["requirements_digest"], label="provenance.requirements_digest"
            ),
            builder_identity=_require_text(
                payload["builder_identity"], label="provenance.builder_identity"
            ),
            fixture_id=_require_text(payload["fixture_id"], label="provenance.fixture_id"),
            schema_version=_require_text(
                payload["schema_version"], label="provenance.schema_version"
            ),
        )


@dataclass(frozen=True, init=False, slots=True)
class PolicyBundleTW:
    """A sealed v2 review artifact with no runtime or activation authority."""

    _canonical_body_json: str
    _bundle_digest: str

    def __init__(
        self,
        *,
        execution_policy_snapshot: Mapping[str, Any],
        cost_policy_snapshot: Mapping[str, Any],
        no_overnight_policy: NoOvernightPolicyConfig,
        legal_reference: LegalReferenceTW,
        broker_policy: BrokerPolicyTW,
        exit_ratios: RiskExitRatios,
        session_calendar: SessionCalendarTW,
        exit_ownership: ExitOwnershipTW,
        provenance: PolicyBundleProvenanceTW,
    ) -> None:
        for value, expected_type, label in (
            (no_overnight_policy, NoOvernightPolicyConfig, "no_overnight_policy"),
            (legal_reference, LegalReferenceTW, "legal_reference"),
            (broker_policy, BrokerPolicyTW, "broker_policy"),
            (exit_ratios, RiskExitRatios, "exit_ratios"),
            (session_calendar, SessionCalendarTW, "session_calendar"),
            (exit_ownership, ExitOwnershipTW, "exit_ownership"),
            (provenance, PolicyBundleProvenanceTW, "provenance"),
        ):
            if type(value) is not expected_type:
                _refuse(f"{label} must use its closed v2 type")

        try:
            execution_input = copy.deepcopy(dict(execution_policy_snapshot))
            cost_input = copy.deepcopy(dict(cost_policy_snapshot))
            execution = copy.deepcopy(verify_execution_policy_snapshot(execution_input))
            cost = copy.deepcopy(verify_cost_policy_snapshot(cost_input))
        except Exception as error:
            if isinstance(error, PolicyBundleError):
                raise
            raise PolicyBundleError("BUNDLE_INVALID: child policy verification failed") from error

        execution_reason = execution_policy_readiness_reason(execution)
        cost_reason = cost_policy_readiness_reason(cost)
        if execution_reason is not None:
            _refuse(f"execution policy is not calibrated: {execution_reason}")
        if cost_reason is not None:
            _refuse(f"cost policy is not calibrated: {cost_reason}")

        policy_payload = copy.deepcopy(no_overnight_policy.canonical_payload())
        parsed_policy = _no_overnight_from_payload(policy_payload)
        if parsed_policy.timezone != "Asia/Taipei":
            _refuse("no_overnight_policy timezone must be exactly Asia/Taipei")
        if session_calendar.timezone != "Asia/Taipei":
            _refuse("session_calendar timezone must be exactly Asia/Taipei")
        if parsed_policy.timezone != session_calendar.timezone:
            _refuse("policy and calendar timezone mismatch")
        if parsed_policy.account_scope_id != broker_policy.account_scope_id:
            _refuse("broker account scope does not match policy")
        if parsed_policy.account_scope_id != exit_ownership.account_scope_id:
            _refuse("exit ownership account scope does not match policy")
        if parsed_policy.policy_family_id != exit_ownership.policy_family_id:
            _refuse("exit ownership policy family does not match policy")
        trading_date = session_calendar.trading_date
        if not legal_reference.effective_from <= trading_date or (
            legal_reference.effective_through is not None
            and trading_date > legal_reference.effective_through
        ):
            _refuse("legal_reference is not effective for trading_date")
        if not broker_policy.effective_from <= trading_date or (
            broker_policy.effective_through is not None
            and trading_date > broker_policy.effective_through
        ):
            _refuse("broker_policy is not effective for trading_date")
        if broker_policy.reviewed_on > trading_date:
            _refuse("broker_policy review is after trading_date")
        if legal_reference.reviewed_on > trading_date:
            _refuse("legal_reference review is after trading_date")
        if broker_policy.commission_rate != cost["commission_rate"]:
            _refuse("broker commission_rate does not exactly mirror cost snapshot")
        if broker_policy.min_commission_twd != cost["min_commission_twd"]:
            _refuse("broker minimum commission does not exactly mirror cost snapshot")

        execution_digest = _require_sha256(
            execution.get("snapshot_digest"),
            label="execution_policy_snapshot.snapshot_digest",
        )
        cost_digest = _require_sha256(
            cost.get("snapshot_digest"),
            label="cost_policy_snapshot.snapshot_digest",
        )
        provenance_payload: dict[str, Any] = {
            **provenance.canonical_payload(),
            "derived_policy_digests": {
                "execution_policy_digest": execution_digest,
                "cost_policy_digest": cost_digest,
                "session_policy_digest": parsed_policy.policy_digest,
            },
            "calibration_reasons": {
                "execution_policy": execution_reason,
                "cost_policy": cost_reason,
            },
        }
        body: dict[str, Any] = {
            "contract_version": POLICY_BUNDLE_CONTRACT_VERSION,
            "validation_algorithm_version": POLICY_BUNDLE_VALIDATION_VERSION,
            "execution_policy_snapshot": execution,
            "cost_policy_snapshot": cost,
            "no_overnight_policy": policy_payload,
            "legal_reference": legal_reference.canonical_payload(),
            "broker_policy": broker_policy.canonical_payload(),
            "exit_ratios": exit_ratios.canonical_payload(),
            "session_calendar": session_calendar.canonical_payload(),
            "exit_ownership": exit_ownership.canonical_payload(),
            "provenance": provenance_payload,
            "wiring_status": WIRING_STATUS,
            "runtime_consumer_status": RUNTIME_CONSUMER_STATUS,
            "activation_authority": ACTIVATION_AUTHORITY,
        }
        canonical_body_json = _canonical_json(body)
        object.__setattr__(self, "_canonical_body_json", canonical_body_json)
        object.__setattr__(
            self,
            "_bundle_digest",
            hashlib.sha256(canonical_body_json.encode("utf-8")).hexdigest(),
        )

    def _body_copy(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._canonical_body_json))

    @property
    def bundle_digest(self) -> str:
        return self._bundle_digest

    @property
    def execution_policy_digest(self) -> str:
        body = self._body_copy()
        derived = cast(
            Mapping[str, Any],
            body["provenance"]["derived_policy_digests"],
        )
        return cast(str, derived["execution_policy_digest"])

    @property
    def cost_policy_digest(self) -> str:
        body = self._body_copy()
        derived = cast(
            Mapping[str, Any],
            body["provenance"]["derived_policy_digests"],
        )
        return cast(str, derived["cost_policy_digest"])

    @property
    def session_policy_digest(self) -> str:
        body = self._body_copy()
        derived = cast(
            Mapping[str, Any],
            body["provenance"]["derived_policy_digests"],
        )
        return cast(str, derived["session_policy_digest"])

    @property
    def execution_policy_snapshot(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._body_copy()["execution_policy_snapshot"])

    @property
    def cost_policy_snapshot(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._body_copy()["cost_policy_snapshot"])

    @property
    def no_overnight_policy(self) -> NoOvernightPolicyConfig:
        return _no_overnight_from_payload(self._body_copy()["no_overnight_policy"])

    @property
    def wiring_status(self) -> str:
        return WIRING_STATUS

    @property
    def runtime_consumer_status(self) -> str:
        return RUNTIME_CONSUMER_STATUS

    @property
    def activation_authority(self) -> str:
        return ACTIVATION_AUTHORITY

    def canonical_payload(self) -> dict[str, Any]:
        return self._body_copy()

    def sealed_snapshot(self) -> dict[str, Any]:
        return {**self.canonical_payload(), "bundle_digest": self.bundle_digest}

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> "PolicyBundleTW":
        payload = _exact_mapping(snapshot, keys=_TOP_LEVEL_KEYS, label="policy_bundle")
        if payload["contract_version"] != POLICY_BUNDLE_CONTRACT_VERSION:
            _refuse("policy_bundle contract_version is unsupported")
        if payload["validation_algorithm_version"] != POLICY_BUNDLE_VALIDATION_VERSION:
            _refuse("policy_bundle validation_algorithm_version is unsupported")
        for field_name, expected in (
            ("wiring_status", WIRING_STATUS),
            ("runtime_consumer_status", RUNTIME_CONSUMER_STATUS),
            ("activation_authority", ACTIVATION_AUTHORITY),
        ):
            if payload[field_name] != expected:
                _refuse(f"policy_bundle {field_name} is unsupported")
        supplied_digest = _require_sha256(
            payload["bundle_digest"], label="policy_bundle.bundle_digest"
        )
        body = {
            key: copy.deepcopy(value) for key, value in payload.items() if key != "bundle_digest"
        }
        if _digest(body) != supplied_digest:
            _refuse("policy_bundle bundle_digest does not match payload")

        legal = LegalReferenceTW.from_payload(payload["legal_reference"])
        broker = BrokerPolicyTW.from_payload(payload["broker_policy"])
        exit_ratios = RiskExitRatios.from_payload(payload["exit_ratios"])
        calendar = SessionCalendarTW.from_payload(payload["session_calendar"])
        ownership = ExitOwnershipTW.from_payload(payload["exit_ownership"])
        provenance = PolicyBundleProvenanceTW.from_sealed_payload(payload["provenance"])
        rebuilt = cls(
            execution_policy_snapshot=_as_mapping(
                payload["execution_policy_snapshot"], label="execution_policy_snapshot"
            ),
            cost_policy_snapshot=_as_mapping(
                payload["cost_policy_snapshot"], label="cost_policy_snapshot"
            ),
            no_overnight_policy=_no_overnight_from_payload(payload["no_overnight_policy"]),
            legal_reference=legal,
            broker_policy=broker,
            exit_ratios=exit_ratios,
            session_calendar=calendar,
            exit_ownership=ownership,
            provenance=provenance,
        )
        if rebuilt.sealed_snapshot() != dict(payload):
            _refuse("policy_bundle contains caller-supplied or non-canonical derived values")
        return rebuilt


def verify_policy_bundle_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive canonical copy after exact v2 verification."""

    return PolicyBundleTW.from_snapshot(snapshot).sealed_snapshot()
