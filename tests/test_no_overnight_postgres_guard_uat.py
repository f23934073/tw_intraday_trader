import pytest

from runtime.no_overnight_guard import (
    NoOvernightGuardUnavailable,
    PostgresNoOvernightControllerGuard,
)


def _guard(dsn: str) -> PostgresNoOvernightControllerGuard:
    return PostgresNoOvernightControllerGuard.connect(
        database_url=dsn,
        connect_timeout_seconds=5,
        account_scope_id="postgres-uat-account-scope",
        policy_family_id="postgres-uat-policy-family",
    )


def test_disposable_postgres_allows_only_one_guard_owner(
    postgres_test_dsn: str,
) -> None:
    first = _guard(postgres_test_dsn)
    duplicate = _guard(postgres_test_dsn)
    successor = None
    try:
        first.acquire()
        with pytest.raises(NoOvernightGuardUnavailable, match="already owned"):
            duplicate.acquire()
        first.close()
        successor = _guard(postgres_test_dsn)
        successor.acquire()
        assert successor.is_owned_and_healthy() is True
    finally:
        first.close()
        duplicate.close()
        if successor is not None:
            successor.close()
