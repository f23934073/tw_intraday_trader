"""Dedicated PostgreSQL advisory-lock guard for no-overnight ENFORCING."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from threading import RLock
from typing import Any
from typing import TypeVar


_T = TypeVar("_T")


NO_OVERNIGHT_GUARD_KEY_VERSION = "no_overnight_guard_key_v1"


class NoOvernightGuardUnavailable(RuntimeError):
    """The singleton guard could not be exclusively acquired or verified."""


def advisory_lock_key(*, account_scope_id: str, policy_family_id: str) -> int:
    for value, field_name in (
        (account_scope_id, "account_scope_id"),
        (policy_family_id, "policy_family_id"),
    ):
        if not value.strip():
            raise ValueError(f"{field_name} must not be empty")
    encoded = json.dumps(
        {
            "key_version": NO_OVERNIGHT_GUARD_KEY_VERSION,
            "account_scope_id": account_scope_id,
            "policy_family_id": policy_family_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    unsigned = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big")
    return unsigned - 2**64 if unsigned >= 2**63 else unsigned


def no_overnight_guard_identity(
    *,
    account_scope_id: str,
    policy_family_id: str,
) -> str:
    lock_key = advisory_lock_key(
        account_scope_id=account_scope_id,
        policy_family_id=policy_family_id,
    )
    return f"{NO_OVERNIGHT_GUARD_KEY_VERSION}:{lock_key}"


class PostgresNoOvernightControllerGuard:
    """Hold one advisory lock on a connection that is never returned to a pool."""

    def __init__(
        self,
        *,
        connection: Any,
        account_scope_id: str,
        policy_family_id: str,
    ) -> None:
        self._connection = connection
        self._lifecycle_lock = RLock()
        self._lock_key = advisory_lock_key(
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
        )
        self._owned = False
        self.guard_identity = no_overnight_guard_identity(
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
        )

    @classmethod
    def connect(
        cls,
        *,
        database_url: str,
        connect_timeout_seconds: int,
        account_scope_id: str,
        policy_family_id: str,
    ) -> "PostgresNoOvernightControllerGuard":
        try:
            import psycopg
        except ImportError as error:
            raise NoOvernightGuardUnavailable(
                "PostgreSQL guard requires the project postgres extra"
            ) from error
        try:
            connection = psycopg.connect(
                database_url,
                connect_timeout=connect_timeout_seconds,
                autocommit=True,
            )
        except Exception as error:
            raise NoOvernightGuardUnavailable(
                "PostgreSQL guard connection failed"
            ) from error
        return cls(
            connection=connection,
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
        )

    def acquire(self) -> None:
        with self._lifecycle_lock:
            if self._owned:
                if self.is_owned_and_healthy():
                    return
                raise NoOvernightGuardUnavailable(
                    "PostgreSQL guard ownership was lost"
                )
            try:
                with self._connection.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", (self._lock_key,))
                    row = cursor.fetchone()
            except Exception as error:
                self.close()
                raise NoOvernightGuardUnavailable(
                    "PostgreSQL guard acquisition failed"
                ) from error
            if row is None or len(row) != 1 or row[0] is not True:
                self.close()
                raise NoOvernightGuardUnavailable(
                    "PostgreSQL no-overnight guard is already owned"
                )
            self._owned = True

    def is_owned_and_healthy(self) -> bool:
        with self._lifecycle_lock:
            if not self._owned:
                return False
            try:
                with self._connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    row = cursor.fetchone()
            except Exception:
                self._owned = False
                return False
            if row != (1,):
                self._owned = False
                return False
            return True

    def execute_if_owned(self, operation: Callable[[], _T]) -> _T:
        """Keep local ownership and close ordering stable through one mutation."""

        with self._lifecycle_lock:
            if not self.is_owned_and_healthy():
                raise NoOvernightGuardUnavailable(
                    "PostgreSQL guard ownership was lost"
                )
            return operation()

    def close(self) -> None:
        with self._lifecycle_lock:
            connection = self._connection
            if self._owned:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock(%s)",
                            (self._lock_key,),
                        )
                        cursor.fetchone()
                except Exception:
                    pass
                self._owned = False
            try:
                connection.close()
            except Exception:
                pass
