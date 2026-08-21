"""Framework-free domain model for all strategy definitions.

The catalog describes strategy intent and configuration.  It deliberately does
not execute Python supplied by a database row; executable implementations are
still selected through server-side bindings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class StrategySide(StrEnum):
    """Backward-compatible trading direction for executable strategies."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"


class StrategyRole(StrEnum):
    FILTER = "FILTER"
    CONTEXT = "CONTEXT"
    CANDIDATE = "CANDIDATE"
    SCORE = "SCORE"
    SIGNAL = "SIGNAL"
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class SessionPhase(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    OPENING = "OPENING"
    INTRADAY = "INTRADAY"
    END_OF_DAY = "END_OF_DAY"
    POST_MARKET = "POST_MARKET"
    POSITION_LIFECYCLE = "POSITION_LIFECYCLE"
    ALL_SESSION = "ALL_SESSION"


class StrategyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPERIMENTAL = "EXPERIMENTAL"
    DRAFT = "DRAFT"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class StrategySource(StrEnum):
    CODE = "CODE"
    DATABASE = "DATABASE"


def _canonical_json(value: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, Any] | list[Any] | str) -> str:
    payload = value if isinstance(value, str) else _canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _enum(value: Any, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().upper())
    except ValueError as error:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{field_name} 必須是：{allowed}") from error


@dataclass(frozen=True)
class StrategyDefinition:
    """Versioned metadata shared by candidate, signal, entry and exit logic.

    ``side`` remains optional because candidate/scoring/signal strategies do
    not necessarily place an order.  ENTRY/EXIT roles automatically populate
    the legacy side field, so the historical backtest contract remains intact.
    A changed definition must receive a new version; the repository rejects a
    different digest for an existing ``strategy_id`` + ``version`` pair.
    """

    strategy_id: str
    display_name_zh_tw: str
    version: str
    role: StrategyRole | None = None
    side: StrategySide | None = None
    session_phase: SessionPhase = SessionPhase.ALL_SESSION
    status: StrategyStatus = StrategyStatus.ACTIVE
    description_zh_tw: str = ""
    execution_binding: str = ""
    required_capabilities: tuple[str, ...] = ("OHLCV",)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    code_identity: str = "strategy-v1"
    source: StrategySource = StrategySource.CODE

    def __post_init__(self) -> None:
        strategy_id = self.strategy_id.strip()
        display_name = self.display_name_zh_tw.strip()
        version = self.version.strip()
        if not strategy_id:
            raise ValueError("strategy_id 不可為空")
        if not display_name:
            raise ValueError("display_name_zh_tw 不可為空")
        if not version:
            raise ValueError("version 不可為空")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("parameters 必須是 JSON object")

        role = self.role
        side = self.side
        if role is not None:
            role = _enum(role, StrategyRole, "role")  # type: ignore[assignment]
        if side is not None:
            side = _enum(side, StrategySide, "side")  # type: ignore[assignment]
        if role is None and side is not None:
            role = StrategyRole(side.value)
        if side is None and role in {StrategyRole.ENTRY, StrategyRole.EXIT}:
            side = StrategySide(role.value)
        if role in {StrategyRole.ENTRY, StrategyRole.EXIT} and side is not None and role.value != side.value:
            raise ValueError("role 與 side 不一致")
        if role is None:
            raise ValueError("role 或 side 至少要提供一個")

        phase = _enum(self.session_phase, SessionPhase, "session_phase")
        status = _enum(self.status, StrategyStatus, "status")
        source = _enum(self.source, StrategySource, "source")
        capabilities = tuple(str(item).strip().upper() for item in self.required_capabilities if str(item).strip())
        tags = tuple(str(item).strip() for item in self.tags if str(item).strip())
        try:
            _canonical_json(dict(self.parameters))
        except (TypeError, ValueError) as error:
            raise ValueError("parameters 必須只能包含 JSON 可序列化值") from error

        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "display_name_zh_tw", display_name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "session_phase", phase)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "description_zh_tw", self.description_zh_tw.strip())
        object.__setattr__(self, "execution_binding", self.execution_binding.strip())
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "parameters", dict(self.parameters))
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "code_identity", self.code_identity.strip())
        object.__setattr__(self, "source", source)

    @property
    def version_id(self) -> str:
        return f"{self.strategy_id}:{self.version}"

    @property
    def definition_digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "display_name_zh_tw": self.display_name_zh_tw,
            "version": self.version,
            "role": self.role.value if self.role is not None else None,
            "side": self.side.value if self.side is not None else None,
            "session_phase": self.session_phase.value,
            "status": self.status.value,
            "description_zh_tw": self.description_zh_tw,
            "execution_binding": self.execution_binding,
            "required_capabilities": list(self.required_capabilities),
            "parameters": dict(self.parameters),
            "tags": list(self.tags),
            "code_identity": self.code_identity,
            "source": self.source.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StrategyDefinition":
        return cls(
            strategy_id=str(value["strategy_id"]),
            display_name_zh_tw=str(value["display_name_zh_tw"]),
            version=str(value["version"]),
            role=value.get("role"),
            side=value.get("side"),
            session_phase=value.get("session_phase", SessionPhase.ALL_SESSION),
            status=value.get("status", StrategyStatus.ACTIVE),
            description_zh_tw=str(value.get("description_zh_tw") or ""),
            execution_binding=str(value.get("execution_binding") or ""),
            required_capabilities=tuple(value.get("required_capabilities", ("OHLCV",))),
            parameters=dict(value.get("parameters") or {}),
            tags=tuple(value.get("tags", ())),
            code_identity=str(value.get("code_identity") or "strategy-v1"),
            source=value.get("source", StrategySource.DATABASE),
        )
