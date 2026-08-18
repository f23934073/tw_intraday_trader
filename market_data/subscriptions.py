"""Capacity-safe subscription allocation and acknowledgement lifecycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from candidate.pool import CandidatePoolEntry
from config.momentum import QuoteSubscriptionMode, SubscriptionCapacityConfig


class SubscriptionState(StrEnum):
    SUBSCRIBE_REQUESTED = "SUBSCRIBE_REQUESTED"
    ACKED = "ACKED"
    ACK_TIMEOUT = "ACK_TIMEOUT"
    SUBSCRIBE_FAILED = "SUBSCRIBE_FAILED"
    UNSUBSCRIBE_REQUESTED = "UNSUBSCRIBE_REQUESTED"
    UNSUBSCRIBE_FAILED = "UNSUBSCRIBE_FAILED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    DISCONNECTED = "DISCONNECTED"


class SubscriptionEventType(StrEnum):
    SUBSCRIBE_REQUESTED = "SUBSCRIBE_REQUESTED"
    SUBSCRIBE_ACKED = "SUBSCRIBE_ACKED"
    SUBSCRIBE_ACK_TIMEOUT = "SUBSCRIBE_ACK_TIMEOUT"
    SUBSCRIBE_FAILED = "SUBSCRIBE_FAILED"
    SUBSCRIBE_ROLLBACK_REQUESTED = "SUBSCRIBE_ROLLBACK_REQUESTED"
    UNSUBSCRIBE_REQUESTED = "UNSUBSCRIBE_REQUESTED"
    UNSUBSCRIBE_ACKED = "UNSUBSCRIBE_ACKED"
    UNSUBSCRIBE_FAILED = "UNSUBSCRIBE_FAILED"
    DISCONNECTED = "DISCONNECTED"


class MissReason(StrEnum):
    NOT_DISCOVERED = "not_discovered"
    ADMISSION_PENDING = "admission_pending"
    CAPACITY_EVICTED = "capacity_evicted"
    SUBSCRIPTION_NOT_ACKED = "subscription_not_acked"
    DATA_INCOMPLETE = "data_incomplete"
    SIGNAL_FALSE = "signal_false"


@dataclass(frozen=True)
class SubscriptionPolicy:
    version: str
    capacity: SubscriptionCapacityConfig
    ack_timeout: timedelta
    retry_backoff: timedelta
    minimum_dwell: timedelta

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Subscription policy version must not be empty")
        if self.capacity.max_symbols is None:
            raise ValueError(
                "Subscription capacity requires reviewed headroom and mode"
            )
        if self.ack_timeout <= timedelta(0):
            raise ValueError("ack_timeout must be positive")
        if self.retry_backoff < timedelta(0):
            raise ValueError("retry_backoff cannot be negative")
        if self.minimum_dwell < timedelta(0):
            raise ValueError("minimum_dwell cannot be negative")

    @property
    def max_symbols(self) -> int:
        value = self.capacity.max_symbols
        assert value is not None
        return value

    @property
    def mode(self) -> QuoteSubscriptionMode:
        value = self.capacity.mode
        assert value is not None
        return value


@dataclass(frozen=True)
class SubscriptionRecord:
    symbol: str
    mode: QuoteSubscriptionMode
    state: SubscriptionState
    requested_at: datetime | None = None
    acked_at: datetime | None = None
    state_changed_at: datetime | None = None
    failed_at: datetime | None = None
    attempts: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class SubscriptionEvent:
    sequence: int
    occurred_at: datetime
    symbol: str
    event_type: SubscriptionEventType
    from_state: SubscriptionState | None
    to_state: SubscriptionState
    reason: str
    mode: QuoteSubscriptionMode


@dataclass(frozen=True)
class SubscriptionDecision:
    evaluated_at: datetime
    policy_version: str
    mode: QuoteSubscriptionMode
    max_symbols: int
    desired_symbols: tuple[str, ...]
    request_symbols: tuple[str, ...]
    unsubscribe_symbols: tuple[str, ...]
    retained_symbols: tuple[str, ...]
    deferred_symbols: tuple[str, ...]
    capacity_evicted_symbols: tuple[str, ...]
    consuming_symbols: tuple[str, ...]
    covered_symbols: tuple[str, ...]

    @property
    def digest(self) -> str:
        payload = {
            "evaluated_at": self.evaluated_at.isoformat(),
            "policy_version": self.policy_version,
            "mode": self.mode.value,
            "max_symbols": self.max_symbols,
            "desired_symbols": list(self.desired_symbols),
            "request_symbols": list(self.request_symbols),
            "unsubscribe_symbols": list(self.unsubscribe_symbols),
            "retained_symbols": list(self.retained_symbols),
            "deferred_symbols": list(self.deferred_symbols),
            "capacity_evicted_symbols": list(self.capacity_evicted_symbols),
            "consuming_symbols": list(self.consuming_symbols),
            "covered_symbols": list(self.covered_symbols),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class ProtectedCapacityError(RuntimeError):
    pass


class SubscriptionManager:
    """Produce subscription operations without directly calling a broker SDK.

    `SUBSCRIBE_REQUESTED`, `ACK_TIMEOUT`, and unsubscribe-failure states still
    consume capacity.  This fail-closed accounting prevents a replacement from
    exceeding the account limit while the provider's actual state is unknown.
    """

    _CONSUMING_STATES = frozenset(
        {
            SubscriptionState.SUBSCRIBE_REQUESTED,
            SubscriptionState.ACKED,
            SubscriptionState.ACK_TIMEOUT,
            SubscriptionState.UNSUBSCRIBE_REQUESTED,
            SubscriptionState.UNSUBSCRIBE_FAILED,
        }
    )

    def __init__(self, policy: SubscriptionPolicy) -> None:
        self.policy = policy
        self._records: dict[str, SubscriptionRecord] = {}
        self._events: list[SubscriptionEvent] = []
        self._decisions: list[SubscriptionDecision] = []
        self._sequence = 0

    @property
    def records(self) -> tuple[SubscriptionRecord, ...]:
        return tuple(self._records[symbol] for symbol in sorted(self._records))

    @property
    def events(self) -> tuple[SubscriptionEvent, ...]:
        return tuple(self._events)

    @property
    def decisions(self) -> tuple[SubscriptionDecision, ...]:
        return tuple(self._decisions)

    @property
    def consuming_symbols(self) -> frozenset[str]:
        return frozenset(
            symbol
            for symbol, record in self._records.items()
            if record.state in self._CONSUMING_STATES
        )

    @property
    def covered_symbols(self) -> frozenset[str]:
        return frozenset(
            symbol
            for symbol, record in self._records.items()
            if record.state is SubscriptionState.ACKED
        )

    @property
    def subscriptions_in_use(self) -> int:
        per_symbol = self.policy.capacity.subscriptions_per_symbol
        assert per_symbol is not None
        return len(self.consuming_symbols) * per_symbol

    def reconcile(
        self,
        entries: tuple[CandidatePoolEntry, ...] | list[CandidatePoolEntry],
        *,
        evaluated_at: datetime,
        active_episode_symbols: frozenset[str] = frozenset(),
    ) -> SubscriptionDecision:
        self._require_aware(evaluated_at)
        self._mark_ack_timeouts(evaluated_at)

        admitted = {
            entry.symbol: entry for entry in entries if entry.admitted
        }
        active = {
            str(symbol).strip().upper()
            for symbol in active_episode_symbols
            if str(symbol).strip()
        }
        protected = {
            entry.symbol for entry in admitted.values() if entry.protected
        } | (active & (set(admitted) | set(self._records)))
        if len(protected) > self.policy.max_symbols:
            raise ProtectedCapacityError(
                f"{len(protected)} protected symbols exceed capacity "
                f"{self.policy.max_symbols}"
            )

        ordered_entries = sorted(admitted.values(), key=CandidatePoolEntry.selection_key)
        desired: list[str] = sorted(protected)

        sticky = [
            entry
            for entry in ordered_entries
            if entry.symbol not in protected
            and self._within_minimum_dwell(entry.symbol, evaluated_at)
        ]
        remaining = [
            entry
            for entry in ordered_entries
            if entry.symbol not in protected
            and entry.symbol not in {item.symbol for item in sticky}
        ]
        for entry in sticky + remaining:
            if len(desired) >= self.policy.max_symbols:
                break
            desired.append(entry.symbol)
        desired = list(dict.fromkeys(desired))
        desired_set = set(desired)
        capacity_evicted = tuple(sorted(set(admitted) - desired_set))

        unsubscribe: list[str] = []
        for symbol in sorted(self.consuming_symbols - desired_set):
            record = self._records[symbol]
            if record.state is SubscriptionState.UNSUBSCRIBE_REQUESTED:
                continue
            if (
                record.state is SubscriptionState.UNSUBSCRIBE_FAILED
                and not self._retry_ready(record, evaluated_at)
            ):
                continue
            self._transition(
                symbol,
                SubscriptionState.UNSUBSCRIBE_REQUESTED,
                SubscriptionEventType.UNSUBSCRIBE_REQUESTED,
                evaluated_at,
                "not_in_desired_universe",
            )
            unsubscribe.append(symbol)

        available_slots = self.policy.max_symbols - len(self.consuming_symbols)
        request: list[str] = []
        deferred: list[str] = []
        for symbol in desired:
            record = self._records.get(symbol)
            if record is not None and record.state in self._CONSUMING_STATES:
                continue
            if not self._retry_ready(record, evaluated_at):
                deferred.append(symbol)
                continue
            if available_slots <= 0:
                deferred.append(symbol)
                continue
            self._request(symbol, evaluated_at)
            request.append(symbol)
            available_slots -= 1

        consuming = tuple(sorted(self.consuming_symbols))
        if len(consuming) > self.policy.max_symbols:
            raise AssertionError("subscription capacity invariant violated")
        retained = tuple(
            sorted(
                desired_set
                & {
                    symbol
                    for symbol, record in self._records.items()
                    if record.state in {
                        SubscriptionState.SUBSCRIBE_REQUESTED,
                        SubscriptionState.ACKED,
                        SubscriptionState.ACK_TIMEOUT,
                    }
                    and symbol not in request
                }
            )
        )
        decision = SubscriptionDecision(
            evaluated_at=evaluated_at,
            policy_version=self.policy.version,
            mode=self.policy.mode,
            max_symbols=self.policy.max_symbols,
            desired_symbols=tuple(desired),
            request_symbols=tuple(request),
            unsubscribe_symbols=tuple(unsubscribe),
            retained_symbols=retained,
            deferred_symbols=tuple(deferred),
            capacity_evicted_symbols=capacity_evicted,
            consuming_symbols=consuming,
            covered_symbols=tuple(sorted(self.covered_symbols)),
        )
        self._decisions.append(decision)
        return decision

    def ack_subscribe(self, symbol: str, *, occurred_at: datetime) -> None:
        self._require_aware(occurred_at)
        normalized = self._normalize_symbol(symbol)
        record = self._records.get(normalized)
        if record is None or record.state not in {
            SubscriptionState.SUBSCRIBE_REQUESTED,
            SubscriptionState.ACK_TIMEOUT,
        }:
            raise ValueError(f"{normalized} has no pending subscribe request")
        self._transition(
            normalized,
            SubscriptionState.ACKED,
            SubscriptionEventType.SUBSCRIBE_ACKED,
            occurred_at,
            "provider_ack",
            acked_at=occurred_at,
        )

    def fail_subscribe(
        self,
        symbol: str,
        *,
        occurred_at: datetime,
        reason: str,
    ) -> None:
        self._require_aware(occurred_at)
        normalized = self._normalize_symbol(symbol)
        record = self._records.get(normalized)
        if record is None or record.state is not SubscriptionState.SUBSCRIBE_REQUESTED:
            raise ValueError(f"{normalized} has no pending subscribe request")
        self._transition(
            normalized,
            SubscriptionState.SUBSCRIBE_FAILED,
            SubscriptionEventType.SUBSCRIBE_FAILED,
            occurred_at,
            reason,
            failed_at=occurred_at,
        )

    def begin_subscribe_rollback(
        self,
        symbol: str,
        *,
        occurred_at: datetime,
        reason: str,
    ) -> None:
        """Retain capacity until a partial subscribe is positively removed."""
        self._require_aware(occurred_at)
        normalized = self._normalize_symbol(symbol)
        record = self._records.get(normalized)
        if record is None or record.state not in {
            SubscriptionState.SUBSCRIBE_REQUESTED,
            SubscriptionState.ACK_TIMEOUT,
        }:
            raise ValueError(f"{normalized} has no subscribe to roll back")
        self._transition(
            normalized,
            SubscriptionState.UNSUBSCRIBE_REQUESTED,
            SubscriptionEventType.SUBSCRIBE_ROLLBACK_REQUESTED,
            occurred_at,
            reason,
        )

    def ack_unsubscribe(self, symbol: str, *, occurred_at: datetime) -> None:
        self._require_aware(occurred_at)
        normalized = self._normalize_symbol(symbol)
        record = self._records.get(normalized)
        if record is None or record.state not in {
            SubscriptionState.UNSUBSCRIBE_REQUESTED,
            SubscriptionState.UNSUBSCRIBE_FAILED,
        }:
            raise ValueError(f"{normalized} has no pending unsubscribe request")
        self._transition(
            normalized,
            SubscriptionState.UNSUBSCRIBED,
            SubscriptionEventType.UNSUBSCRIBE_ACKED,
            occurred_at,
            "provider_ack",
        )

    def fail_unsubscribe(
        self,
        symbol: str,
        *,
        occurred_at: datetime,
        reason: str,
    ) -> None:
        self._require_aware(occurred_at)
        normalized = self._normalize_symbol(symbol)
        record = self._records.get(normalized)
        if record is None or record.state is not SubscriptionState.UNSUBSCRIBE_REQUESTED:
            raise ValueError(f"{normalized} has no pending unsubscribe request")
        self._transition(
            normalized,
            SubscriptionState.UNSUBSCRIBE_FAILED,
            SubscriptionEventType.UNSUBSCRIBE_FAILED,
            occurred_at,
            reason,
            failed_at=occurred_at,
        )

    def mark_disconnected(self, *, occurred_at: datetime) -> None:
        self._require_aware(occurred_at)
        for symbol in sorted(self.consuming_symbols):
            self._transition(
                symbol,
                SubscriptionState.DISCONNECTED,
                SubscriptionEventType.DISCONNECTED,
                occurred_at,
                "provider_disconnected",
            )

    def classify_miss(
        self,
        symbol: str,
        *,
        discovered_symbols: frozenset[str],
        admitted_symbols: frozenset[str],
        capacity_evicted_symbols: frozenset[str],
        data_complete: bool,
        signal_emitted: bool,
    ) -> MissReason | None:
        normalized = self._normalize_symbol(symbol)
        if normalized not in discovered_symbols:
            return MissReason.NOT_DISCOVERED
        if normalized not in admitted_symbols:
            return MissReason.ADMISSION_PENDING
        if normalized in capacity_evicted_symbols:
            return MissReason.CAPACITY_EVICTED
        if normalized not in self.covered_symbols:
            return MissReason.SUBSCRIPTION_NOT_ACKED
        if not data_complete:
            return MissReason.DATA_INCOMPLETE
        if not signal_emitted:
            return MissReason.SIGNAL_FALSE
        return None

    def _request(self, symbol: str, occurred_at: datetime) -> None:
        previous = self._records.get(symbol)
        attempts = (previous.attempts if previous is not None else 0) + 1
        self._transition(
            symbol,
            SubscriptionState.SUBSCRIBE_REQUESTED,
            SubscriptionEventType.SUBSCRIBE_REQUESTED,
            occurred_at,
            "selected_by_allocator",
            requested_at=occurred_at,
            attempts=attempts,
            failed_at=None,
            acked_at=None,
        )

    def _mark_ack_timeouts(self, evaluated_at: datetime) -> None:
        for symbol, record in sorted(self._records.items()):
            if (
                record.state is SubscriptionState.SUBSCRIBE_REQUESTED
                and record.requested_at is not None
                and evaluated_at - record.requested_at >= self.policy.ack_timeout
            ):
                self._transition(
                    symbol,
                    SubscriptionState.ACK_TIMEOUT,
                    SubscriptionEventType.SUBSCRIBE_ACK_TIMEOUT,
                    evaluated_at,
                    "subscribe_ack_timeout",
                    failed_at=evaluated_at,
                )

    def _within_minimum_dwell(self, symbol: str, evaluated_at: datetime) -> bool:
        record = self._records.get(symbol)
        return bool(
            record is not None
            and record.state in self._CONSUMING_STATES
            and record.requested_at is not None
            and evaluated_at - record.requested_at < self.policy.minimum_dwell
        )

    def _retry_ready(
        self,
        record: SubscriptionRecord | None,
        evaluated_at: datetime,
    ) -> bool:
        if record is None:
            return True
        if record.state in {
            SubscriptionState.SUBSCRIBE_FAILED,
            SubscriptionState.UNSUBSCRIBE_FAILED,
            SubscriptionState.DISCONNECTED,
            SubscriptionState.UNSUBSCRIBED,
        }:
            return (
                record.failed_at is None
                or evaluated_at - record.failed_at >= self.policy.retry_backoff
            )
        return False

    def _transition(
        self,
        symbol: str,
        to_state: SubscriptionState,
        event_type: SubscriptionEventType,
        occurred_at: datetime,
        reason: str,
        **changes: object,
    ) -> None:
        previous = self._records.get(symbol)
        if (
            previous is not None
            and previous.state_changed_at is not None
            and occurred_at < previous.state_changed_at
        ):
            raise ValueError("subscription transition cannot move backward in time")
        base = previous or SubscriptionRecord(
            symbol=symbol,
            mode=self.policy.mode,
            state=to_state,
        )
        record = replace(
            base,
            state=to_state,
            state_changed_at=occurred_at,
            reason=reason,
            **changes,
        )
        self._records[symbol] = record
        self._sequence += 1
        self._events.append(
            SubscriptionEvent(
                sequence=self._sequence,
                occurred_at=occurred_at,
                symbol=symbol,
                event_type=event_type,
                from_state=previous.state if previous is not None else None,
                to_state=to_state,
                reason=reason,
                mode=self.policy.mode,
            )
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()
        if not normalized:
            raise ValueError("subscription symbol must not be empty")
        return normalized

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("subscription timestamps must be timezone-aware")
