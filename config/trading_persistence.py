"""Typed persistence settings for the LOCAL_PAPER Trading Journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import os
from typing import Mapping


class TradingJournalBackend(StrEnum):
    """Supported Journal persistence adapters."""

    MEMORY = "memory"
    POSTGRESQL = "postgresql"


def _positive_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    try:
        value = int(environment.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class TradingPersistenceConfig:
    """Infrastructure-only settings; the database URL is never shown in repr."""

    backend: TradingJournalBackend = TradingJournalBackend.MEMORY
    database_url: str | None = field(default=None, repr=False)
    pool_min_size: int = 1
    pool_max_size: int = 4
    connect_timeout_seconds: int = 5

    def __post_init__(self) -> None:
        if self.pool_min_size <= 0:
            raise ValueError("pool_min_size must be positive")
        if self.pool_max_size < self.pool_min_size:
            raise ValueError("pool_max_size must be greater than or equal to pool_min_size")
        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
        if (
            self.backend is TradingJournalBackend.POSTGRESQL
            and not (self.database_url or "").strip()
        ):
            raise ValueError(
                "DATABASE_URL is required when TRADING_JOURNAL_BACKEND=postgresql"
            )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> TradingPersistenceConfig:
        values = os.environ if environment is None else environment
        raw_backend = values.get("TRADING_JOURNAL_BACKEND", "memory").strip().lower()
        try:
            backend = TradingJournalBackend(raw_backend)
        except ValueError as error:
            raise ValueError(
                "TRADING_JOURNAL_BACKEND must be memory or postgresql"
            ) from error

        database_url = next(
            (
                value.strip()
                for name in ("DATABASE_URL", "POSTGRESQL_DSN", "PostgreSQL_DSN")
                if (value := values.get(name)) and value.strip()
            ),
            None,
        )
        return cls(
            backend=backend,
            database_url=database_url,
            pool_min_size=_positive_int(
                values,
                "TRADING_POSTGRES_POOL_MIN_SIZE",
                1,
            ),
            pool_max_size=_positive_int(
                values,
                "TRADING_POSTGRES_POOL_MAX_SIZE",
                4,
            ),
            connect_timeout_seconds=_positive_int(
                values,
                "TRADING_POSTGRES_CONNECT_TIMEOUT_SECONDS",
                5,
            ),
        )
