import pytest

from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)


def test_trading_persistence_defaults_to_explicit_memory_mode() -> None:
    config = TradingPersistenceConfig.from_environment({})

    assert config.backend is TradingJournalBackend.MEMORY
    assert config.database_url is None
    assert config.pool_min_size == 1
    assert config.pool_max_size == 4


def test_postgresql_mode_requires_dsn_without_leaking_it_in_repr() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        TradingPersistenceConfig.from_environment(
            {"TRADING_JOURNAL_BACKEND": "postgresql"}
        )

    secret_dsn = "postgresql://user:secret@localhost/db"
    config = TradingPersistenceConfig.from_environment(
        {
            "TRADING_JOURNAL_BACKEND": "postgresql",
            "DATABASE_URL": secret_dsn,
        }
    )

    assert config.backend is TradingJournalBackend.POSTGRESQL
    assert config.database_url == secret_dsn
    assert secret_dsn not in repr(config)


def test_legacy_postgresql_dsn_is_supported_during_config_migration() -> None:
    config = TradingPersistenceConfig.from_environment(
        {
            "TRADING_JOURNAL_BACKEND": "postgresql",
            "PostgreSQL_DSN": "postgresql://legacy/db",
        }
    )

    assert config.database_url == "postgresql://legacy/db"


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"TRADING_JOURNAL_BACKEND": "automatic"}, "memory or postgresql"),
        ({"TRADING_POSTGRES_POOL_MIN_SIZE": "0"}, "must be positive"),
        (
            {
                "TRADING_POSTGRES_POOL_MIN_SIZE": "5",
                "TRADING_POSTGRES_POOL_MAX_SIZE": "4",
            },
            "greater than or equal",
        ),
    ],
)
def test_invalid_persistence_configuration_fails_closed(
    environment: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        TradingPersistenceConfig.from_environment(environment)
