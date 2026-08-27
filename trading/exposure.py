"""Framework-free ownership and holding-horizon identities for Local Paper."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any


ACCOUNT_SCOPE_IDENTITY_VERSION = "account-scope-identity-v1"
POLICY_FAMILY_IDENTITY_VERSION = "policy-family-identity-v1"
EXPOSURE_IDENTITY_VERSION = "exposure-identity-v1"
LEGACY_EXPOSURE_POLICY_VERSION = "legacy-exposure-import-v1"
SEMANTIC_ACTION_IDENTITY_VERSION = "no-overnight-action-v1"

_MANAGED_ORIGINS = frozenset({"MANUAL_WEB", "STRATEGY_AUTOMATED"})
_EXPOSURE_FIELDS = frozenset(
    {
        "exposure_id",
        "account_scope_id",
        "policy_family_id",
        "owner_origin",
        "owner_id",
        "holding_horizon",
        "entry_session_date",
        "entry_policy_version",
        "entry_policy_digest",
        "identity_schema_version",
    }
)


class HoldingHorizon(StrEnum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    LONG_TERM = "LONG_TERM"
    UNCLASSIFIED_LEGACY = "UNCLASSIFIED_LEGACY"


class PositionAction(StrEnum):
    OPEN_LONG = "OPEN_LONG"
    CLOSE_LONG = "CLOSE_LONG"


class ExecutionReasonCategory(StrEnum):
    STRATEGY = "STRATEGY"
    OPERATIONAL_RISK = "OPERATIONAL_RISK"


def _require_identity(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"{field_name} must be normalized without whitespace")
    return value


def _require_digest(value: str, field_name: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _canonical_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AccountScopeIdentity:
    account_scope_id: str
    execution_mode: str
    ledger_id: str
    identity_schema_version: str = ACCOUNT_SCOPE_IDENTITY_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.account_scope_id, "account_scope_id"),
            (self.execution_mode, "execution_mode"),
            (self.ledger_id, "ledger_id"),
            (self.identity_schema_version, "identity_schema_version"),
        ):
            _require_identity(value, field_name)
        if self.identity_schema_version != ACCOUNT_SCOPE_IDENTITY_VERSION:
            raise ValueError("unsupported account scope identity schema")

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, str]:
        return {
            "account_scope_id": self.account_scope_id,
            "execution_mode": self.execution_mode,
            "ledger_id": self.ledger_id,
            "identity_schema_version": self.identity_schema_version,
        }


@dataclass(frozen=True)
class PolicyFamilyIdentity:
    policy_family_id: str
    account_scope_id: str
    policy_kind: str = "NO_OVERNIGHT"
    identity_schema_version: str = POLICY_FAMILY_IDENTITY_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.policy_family_id, "policy_family_id"),
            (self.account_scope_id, "account_scope_id"),
            (self.policy_kind, "policy_kind"),
            (self.identity_schema_version, "identity_schema_version"),
        ):
            _require_identity(value, field_name)
        if self.policy_kind != "NO_OVERNIGHT":
            raise ValueError("policy_kind must be NO_OVERNIGHT")
        if self.identity_schema_version != POLICY_FAMILY_IDENTITY_VERSION:
            raise ValueError("unsupported policy family identity schema")

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, str]:
        return {
            "policy_family_id": self.policy_family_id,
            "account_scope_id": self.account_scope_id,
            "policy_kind": self.policy_kind,
            "identity_schema_version": self.identity_schema_version,
        }


@dataclass(frozen=True)
class ExposureIdentity:
    exposure_id: str
    account_scope_id: str
    policy_family_id: str
    owner_origin: str
    owner_id: str
    holding_horizon: HoldingHorizon
    entry_session_date: date | None
    entry_policy_version: str
    entry_policy_digest: str
    identity_schema_version: str = EXPOSURE_IDENTITY_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.exposure_id, "exposure_id"),
            (self.account_scope_id, "account_scope_id"),
            (self.policy_family_id, "policy_family_id"),
            (self.owner_origin, "owner_origin"),
            (self.owner_id, "owner_id"),
            (self.entry_policy_version, "entry_policy_version"),
            (self.identity_schema_version, "identity_schema_version"),
        ):
            _require_identity(value, field_name)
        if self.owner_origin not in _MANAGED_ORIGINS:
            raise ValueError("owner_origin is unsupported")
        if not isinstance(self.holding_horizon, HoldingHorizon):
            raise ValueError("holding_horizon is unsupported")
        if (
            self.entry_session_date is None
            and self.holding_horizon is not HoldingHorizon.UNCLASSIFIED_LEGACY
        ):
            raise ValueError("classified exposure requires entry_session_date")
        _require_digest(self.entry_policy_digest, "entry_policy_digest")
        if self.identity_schema_version != EXPOSURE_IDENTITY_VERSION:
            raise ValueError("unsupported exposure identity schema")

    @property
    def no_overnight_managed(self) -> bool:
        return (
            self.holding_horizon is HoldingHorizon.INTRADAY
            and self.owner_origin in _MANAGED_ORIGINS
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "exposure_id": self.exposure_id,
            "account_scope_id": self.account_scope_id,
            "policy_family_id": self.policy_family_id,
            "owner_origin": self.owner_origin,
            "owner_id": self.owner_id,
            "holding_horizon": self.holding_horizon.value,
            "entry_session_date": (
                self.entry_session_date.isoformat()
                if self.entry_session_date is not None
                else None
            ),
            "entry_policy_version": self.entry_policy_version,
            "entry_policy_digest": self.entry_policy_digest,
            "identity_schema_version": self.identity_schema_version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ExposureIdentity:
        unknown = set(payload) - _EXPOSURE_FIELDS
        missing = _EXPOSURE_FIELDS - set(payload)
        if unknown:
            raise ValueError(f"unknown exposure identity fields: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing exposure identity fields: {sorted(missing)}")
        string_fields = (
            "exposure_id",
            "account_scope_id",
            "policy_family_id",
            "owner_origin",
            "owner_id",
            "holding_horizon",
            "entry_policy_version",
            "entry_policy_digest",
            "identity_schema_version",
        )
        if any(not isinstance(payload[field], str) for field in string_fields):
            raise ValueError("exposure identity string field has invalid type")
        raw_date = payload["entry_session_date"]
        if raw_date is not None and not isinstance(raw_date, str):
            raise ValueError("entry_session_date has invalid type")
        return cls(
            exposure_id=payload["exposure_id"],
            account_scope_id=payload["account_scope_id"],
            policy_family_id=payload["policy_family_id"],
            owner_origin=payload["owner_origin"],
            owner_id=payload["owner_id"],
            holding_horizon=HoldingHorizon(payload["holding_horizon"]),
            entry_session_date=(
                date.fromisoformat(raw_date) if raw_date is not None else None
            ),
            entry_policy_version=payload["entry_policy_version"],
            entry_policy_digest=payload["entry_policy_digest"],
            identity_schema_version=payload["identity_schema_version"],
        )


def build_exposure_identity(
    *,
    account_scope_id: str,
    policy_family_id: str,
    owner_origin: str,
    owner_id: str,
    holding_horizon: HoldingHorizon,
    entry_session_date: date,
    entry_policy_version: str,
    entry_policy_digest: str,
    entry_identity: str,
) -> ExposureIdentity:
    payload = {
        "identity_version": EXPOSURE_IDENTITY_VERSION,
        "account_scope_id": _require_identity(account_scope_id, "account_scope_id"),
        "policy_family_id": _require_identity(policy_family_id, "policy_family_id"),
        "owner_origin": _require_identity(owner_origin, "owner_origin"),
        "owner_id": _require_identity(owner_id, "owner_id"),
        "holding_horizon": holding_horizon.value,
        "entry_session_date": entry_session_date.isoformat(),
        "entry_policy_version": _require_identity(
            entry_policy_version, "entry_policy_version"
        ),
        "entry_policy_digest": _require_digest(
            entry_policy_digest, "entry_policy_digest"
        ),
        "entry_identity": _require_identity(entry_identity, "entry_identity"),
    }
    return ExposureIdentity(
        exposure_id=f"exposure_v1_{_canonical_digest(payload)}",
        account_scope_id=account_scope_id,
        policy_family_id=policy_family_id,
        owner_origin=owner_origin,
        owner_id=owner_id,
        holding_horizon=holding_horizon,
        entry_session_date=entry_session_date,
        entry_policy_version=entry_policy_version,
        entry_policy_digest=entry_policy_digest,
    )


def build_legacy_exposure_identity(
    *,
    account_scope_id: str,
    policy_family_id: str,
    source_session_id: str,
    symbol: str,
    owner_origin: str,
    owner_id: str,
) -> ExposureIdentity:
    payload = {
        "identity_version": "legacy-exposure-v1",
        "account_scope_id": _require_identity(account_scope_id, "account_scope_id"),
        "policy_family_id": _require_identity(policy_family_id, "policy_family_id"),
        "source_session_id": _require_identity(source_session_id, "source_session_id"),
        "symbol": _require_identity(symbol, "symbol"),
        "owner_origin": _require_identity(owner_origin, "owner_origin"),
        "owner_id": _require_identity(owner_id, "owner_id"),
    }
    policy_digest = _canonical_digest(
        {
            "policy_version": LEGACY_EXPOSURE_POLICY_VERSION,
            **payload,
        }
    )
    return ExposureIdentity(
        exposure_id=f"legacy_exposure_v1_{_canonical_digest(payload)}",
        account_scope_id=account_scope_id,
        policy_family_id=policy_family_id,
        owner_origin=owner_origin,
        owner_id=owner_id,
        holding_horizon=HoldingHorizon.UNCLASSIFIED_LEGACY,
        entry_session_date=None,
        entry_policy_version=LEGACY_EXPOSURE_POLICY_VERSION,
        entry_policy_digest=policy_digest,
    )


def build_exit_chain_id(
    *,
    account_scope_id: str,
    policy_family_id: str,
    session_date: date,
    exposure_id: str,
) -> str:
    payload = {
        "identity_version": "no-overnight-exit-chain-v1",
        "account_scope_id": _require_identity(account_scope_id, "account_scope_id"),
        "policy_family_id": _require_identity(policy_family_id, "policy_family_id"),
        "session_date": session_date.isoformat(),
        "exposure_id": _require_identity(exposure_id, "exposure_id"),
        "position_action": PositionAction.CLOSE_LONG.value,
    }
    return f"no_overnight_exit_chain_v1_{_canonical_digest(payload)}"


def build_semantic_action_key(
    *,
    account_scope_id: str,
    policy_family_id: str,
    session_date: date,
    exposure_id: str,
    action: str,
    attempt: int,
    target_order_id: str | None = None,
) -> str:
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
        raise ValueError("attempt must be positive")
    normalized_action = _require_identity(action, "action")
    if normalized_action != normalized_action.upper():
        raise ValueError("action must be normalized")
    payload = {
        "identity_version": SEMANTIC_ACTION_IDENTITY_VERSION,
        "account_scope_id": _require_identity(account_scope_id, "account_scope_id"),
        "policy_family_id": _require_identity(policy_family_id, "policy_family_id"),
        "session_date": session_date.isoformat(),
        "exposure_id": _require_identity(exposure_id, "exposure_id"),
        "exit_chain_id": build_exit_chain_id(
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
            session_date=session_date,
            exposure_id=exposure_id,
        ),
        "action": normalized_action,
        "attempt": attempt,
        "target_order_id": (
            _require_identity(target_order_id, "target_order_id")
            if target_order_id is not None
            else None
        ),
    }
    return f"no_overnight_action_v1_{_canonical_digest(payload)}"
