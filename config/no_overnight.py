"""Typed no-overnight policy configuration with canonical identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import time
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


NO_OVERNIGHT_POLICY_SCHEMA_VERSION = "no_overnight_policy_config_v1"
NO_OVERNIGHT_POLICY_VALIDATION_VERSION = "ordered_session_cutoffs_v1"
NO_OVERNIGHT_DEPLOYMENT_MANIFEST_VERSION = "no_overnight_deployment_manifest_v1"


class NoOvernightMode(StrEnum):
    DISABLED = "DISABLED"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    ENFORCING = "ENFORCING"


class ControllerHostingMode(StrEnum):
    SINGLE_HOST_SINGLE_WORKER = "SINGLE_HOST_SINGLE_WORKER"


class ControllerGuardKind(StrEnum):
    POSTGRES_ADVISORY_LOCK = "POSTGRES_ADVISORY_LOCK"


@dataclass(frozen=True)
class NoOvernightDeploymentManifest:
    """Explicit reviewed declaration for the PR-NO-003 single-worker boundary."""

    source: str
    process_count: int
    workers_per_process: int
    hosting_mode: ControllerHostingMode = (
        ControllerHostingMode.SINGLE_HOST_SINGLE_WORKER
    )
    schema_version: str = NO_OVERNIGHT_DEPLOYMENT_MANIFEST_VERSION

    def __post_init__(self) -> None:
        if type(self.source) is not str:
            raise ValueError("deployment manifest source must be a string")
        object.__setattr__(self, "source", _require_text(self.source, "source"))
        if self.schema_version != NO_OVERNIGHT_DEPLOYMENT_MANIFEST_VERSION:
            raise ValueError("deployment manifest schema is unsupported")
        if self.hosting_mode is not ControllerHostingMode.SINGLE_HOST_SINGLE_WORKER:
            raise ValueError("deployment hosting mode is unsupported")
        if (
            type(self.process_count) is not int
            or type(self.workers_per_process) is not int
            or self.process_count != 1
            or self.workers_per_process != 1
        ):
            raise ValueError("ENFORCING requires exactly one process and one worker")

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            {
                "schema_version": self.schema_version,
                "source": self.source,
                "process_count": self.process_count,
                "workers_per_process": self.workers_per_process,
                "hosting_mode": self.hosting_mode.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _time_payload(value: time | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds")


@dataclass(frozen=True)
class NoOvernightPolicyConfig:
    """Immutable configuration; OBSERVE_ONLY/ENFORCING require explicit cutoffs."""

    mode: NoOvernightMode
    account_scope_id: str
    policy_family_id: str
    policy_version: str
    timezone: str
    market_open: time | None = None
    no_new_entry_at: time | None = None
    cancel_entry_at: time | None = None
    flatten_at: time | None = None
    aggressive_exit_at: time | None = None
    final_reconciliation_at: time | None = None
    reviewed_session_close: time | None = None
    max_exit_attempts: int | None = None
    retry_cooldown_seconds: int | None = None
    executable_book_policy_id: str | None = None
    controller_hosting_mode: ControllerHostingMode = (
        ControllerHostingMode.SINGLE_HOST_SINGLE_WORKER
    )
    controller_guard_kind: ControllerGuardKind = (
        ControllerGuardKind.POSTGRES_ADVISORY_LOCK
    )
    schema_version: str = NO_OVERNIGHT_POLICY_SCHEMA_VERSION
    validation_algorithm_version: str = NO_OVERNIGHT_POLICY_VALIDATION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.mode, NoOvernightMode):
            raise ValueError("mode must be a NoOvernightMode")
        if not isinstance(self.controller_hosting_mode, ControllerHostingMode):
            raise ValueError("controller_hosting_mode is unsupported")
        if not isinstance(self.controller_guard_kind, ControllerGuardKind):
            raise ValueError("controller_guard_kind is unsupported")
        for field_name in (
            "account_scope_id",
            "policy_family_id",
            "policy_version",
            "timezone",
            "schema_version",
            "validation_algorithm_version",
        ):
            value = getattr(self, field_name)
            if type(value) is not str:
                raise ValueError(f"{field_name} must be a string")
            object.__setattr__(self, field_name, _require_text(value, field_name))
        if self.schema_version != NO_OVERNIGHT_POLICY_SCHEMA_VERSION:
            raise ValueError("schema_version is unsupported")
        if (
            self.validation_algorithm_version
            != NO_OVERNIGHT_POLICY_VALIDATION_VERSION
        ):
            raise ValueError("validation_algorithm_version is unsupported")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a recognized IANA timezone") from error

        cutoff_fields = (
            "market_open",
            "no_new_entry_at",
            "cancel_entry_at",
            "flatten_at",
            "aggressive_exit_at",
            "final_reconciliation_at",
            "reviewed_session_close",
        )
        for field_name in cutoff_fields:
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, time):
                raise ValueError(f"{field_name} must be a time")
            if value is not None and value.tzinfo is not None:
                raise ValueError(f"{field_name} must be a local wall-clock time")
            if value is not None and value.fold != 0:
                raise ValueError(f"{field_name} fold is unsupported")

        if self.mode is NoOvernightMode.DISABLED:
            return

        if any(getattr(self, field_name) is None for field_name in cutoff_fields):
            raise ValueError("OBSERVE_ONLY/ENFORCING require every session cutoff")
        ordered = tuple(getattr(self, field_name) for field_name in cutoff_fields)
        if tuple(sorted(ordered)) != ordered or len(set(ordered)) != len(ordered):
            raise ValueError("no-overnight session cutoffs must be strictly ordered")
        if type(self.max_exit_attempts) is not int or self.max_exit_attempts <= 0:
            raise ValueError("max_exit_attempts must be a positive integer")
        if (
            type(self.retry_cooldown_seconds) is not int
            or self.retry_cooldown_seconds <= 0
        ):
            raise ValueError("retry_cooldown_seconds must be a positive integer")
        if self.executable_book_policy_id is None:
            raise ValueError("executable_book_policy_id is required")
        object.__setattr__(
            self,
            "executable_book_policy_id",
            _require_text(
                self.executable_book_policy_id,
                "executable_book_policy_id",
            ),
        )

    @classmethod
    def disabled(
        cls,
        *,
        account_scope_id: str,
        policy_family_id: str,
        policy_version: str = "disabled-v1",
        timezone: str = "Asia/Taipei",
    ) -> "NoOvernightPolicyConfig":
        return cls(
            mode=NoOvernightMode.DISABLED,
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
            policy_version=policy_version,
            timezone=timezone,
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "validation_algorithm_version": self.validation_algorithm_version,
            "mode": self.mode.value,
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "policy_version": self.policy_version,
            "timezone": self.timezone,
            "market_open": _time_payload(self.market_open),
            "no_new_entry_at": _time_payload(self.no_new_entry_at),
            "cancel_entry_at": _time_payload(self.cancel_entry_at),
            "flatten_at": _time_payload(self.flatten_at),
            "aggressive_exit_at": _time_payload(self.aggressive_exit_at),
            "final_reconciliation_at": _time_payload(
                self.final_reconciliation_at
            ),
            "reviewed_session_close": _time_payload(
                self.reviewed_session_close
            ),
            "max_exit_attempts": self.max_exit_attempts,
            "retry_cooldown_seconds": self.retry_cooldown_seconds,
            "executable_book_policy_id": self.executable_book_policy_id,
            "controller_hosting_mode": self.controller_hosting_mode.value,
            "controller_guard_kind": self.controller_guard_kind.value,
        }

    @property
    def policy_digest(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def constructor_values(self) -> dict[str, object]:
        """Return exact dataclass constructor values for explicit test/config revision."""

        return {item.name: getattr(self, item.name) for item in fields(self)}
