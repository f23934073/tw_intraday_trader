"""Validated transport settings for the realtime Momentum dashboard stream."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


def _flag(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environment.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean flag")


def _positive_float(
    environment: Mapping[str, str],
    name: str,
    default: float,
) -> float:
    value = float(environment.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    value = int(environment.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class MomentumStreamConfig:
    enabled: bool = True
    coalesce_seconds: float = 0.5
    heartbeat_seconds: float = 10.0
    replay_capacity: int = 256
    send_timeout_seconds: float = 2.0
    max_clients: int = 32

    def __post_init__(self) -> None:
        if self.coalesce_seconds <= 0:
            raise ValueError("coalesce_seconds must be positive")
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if self.replay_capacity <= 0:
            raise ValueError("replay_capacity must be positive")
        if self.send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be positive")
        if self.max_clients <= 0:
            raise ValueError("max_clients must be positive")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> MomentumStreamConfig:
        values = os.environ if environment is None else environment
        return cls(
            enabled=_flag(
                values,
                "MOMENTUM_DASHBOARD_WS_ENABLED",
                True,
            ),
            coalesce_seconds=_positive_float(
                values,
                "MOMENTUM_DASHBOARD_WS_COALESCE_SECONDS",
                0.5,
            ),
            heartbeat_seconds=_positive_float(
                values,
                "MOMENTUM_DASHBOARD_WS_HEARTBEAT_SECONDS",
                10.0,
            ),
            replay_capacity=_positive_int(
                values,
                "MOMENTUM_DASHBOARD_WS_REPLAY_CAPACITY",
                256,
            ),
            send_timeout_seconds=_positive_float(
                values,
                "MOMENTUM_DASHBOARD_WS_SEND_TIMEOUT_SECONDS",
                2.0,
            ),
            max_clients=_positive_int(
                values,
                "MOMENTUM_DASHBOARD_WS_MAX_CLIENTS",
                32,
            ),
        )


MOMENTUM_STREAM_CONFIG = MomentumStreamConfig.from_environment()
