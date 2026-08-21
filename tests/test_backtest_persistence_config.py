from __future__ import annotations

import pytest

from config import backtest


_DATABASE_ENV_NAMES = (
    "BACKTEST_DATABASE_BACKEND",
    "BACKTEST_DATABASE_URL",
    "DATABASE_URL",
    "POSTGRESQL_DSN",
    "PostgreSQL_DSN",
)


def _clear_database_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _DATABASE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_sqlite_backend_must_be_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv("BACKTEST_DATABASE_BACKEND", "sqlite")
    assert backtest._database_settings() == ("sqlite", "")


def test_default_backend_without_shared_dsn_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    with pytest.raises(ValueError, match="必須設定"):
        backtest._database_settings()


def test_explicit_postgresql_backend_reuses_shared_legacy_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv("BACKTEST_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("PostgreSQL_DSN", "postgresql://localhost/backtest")
    assert backtest._database_settings() == (
        "postgresql",
        "postgresql://localhost/backtest",
    )


def test_legacy_backtest_database_url_still_selects_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv(
        "BACKTEST_DATABASE_URL",
        "postgresql://localhost/backtest",
    )
    assert backtest._database_settings() == (
        "postgresql",
        "postgresql://localhost/backtest",
    )


def test_postgresql_backend_without_dsn_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv("BACKTEST_DATABASE_BACKEND", "postgresql")
    with pytest.raises(ValueError, match="必須設定"):
        backtest._database_settings()
