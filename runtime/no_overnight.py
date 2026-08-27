"""No-overnight application controller and local-paper enforcement adapters."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
from threading import Event, RLock, Thread
from typing import Protocol, TypeVar
from zoneinfo import ZoneInfo

from config.no_overnight import NoOvernightMode, NoOvernightPolicyConfig
from market_data.equity_calendar import ReviewedEquityCalendar
from runtime.clock import Clock
from trading.canonical_values import canonical_decimal_string
from trading.journal import (
    JournalConflictError,
    JournalRecord,
    JournalRepository,
    JournalSession,
)
from trading.application import order_command_from_record
from trading.exposure import (
    ExposureIdentity,
    build_semantic_action_key,
)
from trading.local_paper import (
    LOCAL_PAPER_FILL_V4_KIND,
    LOCAL_PAPER_CANCEL_INTENT_V2_KIND,
    LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
    LOCAL_PAPER_ORDER_STATE_V2_KIND,
    LOCAL_PAPER_REJECTION_V2_KIND,
    LocalPaperExposureFill,
    OrderStateReconciliationConflict,
    canonical_v2_order_state_from_simulation_order,
    latest_local_paper_order_states,
    rebuild_local_paper_v2_projection,
)
from trading.no_overnight import (
    ExposureQuantity,
    ManagedExposureEvidence,
    NoOvernightEvidence,
    NoOvernightState,
    NoOvernightWouldAction,
    ReconciliationStatus,
    ReviewedSessionWindow,
    plan_no_overnight_transition,
    strict_flat_proof,
)
from trading.no_overnight_journal import (
    NO_OVERNIGHT_PROJECTION_NAME,
    NO_OVERNIGHT_RESULT_KIND,
    NoOvernightProjection,
    NoOvernightProjectionError,
    breach_id_for,
    execution_fact_observed_record,
    no_overnight_breach_acknowledged_record,
    no_overnight_breach_record,
    no_overnight_breach_resolved_record,
    no_overnight_result_record,
    no_overnight_reconciliation_record,
    rebuild_no_overnight_projection,
    snapshot_record,
    transition_record,
    validate_breach_evidence_reference,
    write_no_overnight_checkpoint,
)
from trading.no_overnight_admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionSnapshot,
    evaluate_execution_admission,
)
from trading.risk import OrderCommand


NO_OVERNIGHT_CONTROLLER_POLL_SECONDS = 1.0
NO_OVERNIGHT_SESSION_ID_PREFIX = "no-overnight-v1-"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, order=True)
class ExecutionFactReference:
    journal_sequence: int
    kind: str
    record_id: str
    entry_session_date: date

    def __post_init__(self) -> None:
        if type(self.journal_sequence) is not int or self.journal_sequence <= 0:
            raise ValueError("execution fact sequence must be a positive integer")
        if not self.kind.strip() or not self.record_id.strip():
            raise ValueError("execution fact identity must not be empty")
        if type(self.entry_session_date) is not date:
            raise ValueError("execution fact entry session date is invalid")


@dataclass(frozen=True, order=True)
class OpenBreachFence:
    session_date: date
    revision: int
    breach_id: str
    reconciliation_digest: str

    def __post_init__(self) -> None:
        if type(self.session_date) is not date:
            raise ValueError("open breach session date is invalid")
        if type(self.revision) is not int or self.revision <= 0:
            raise ValueError("open breach revision must be positive")
        if not self.breach_id.strip():
            raise ValueError("open breach identity must not be empty")
        if len(self.reconciliation_digest) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.reconciliation_digest
        ):
            raise ValueError("open breach reconciliation digest is invalid")


class NoOvernightBreachConflict(RuntimeError):
    """A breach mutation did not target the latest durable revision."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NoOvernightEvidenceBundle:
    evidence: NoOvernightEvidence
    execution_facts: tuple[ExecutionFactReference, ...]
    prior_session_execution_facts: tuple[ExecutionFactReference, ...] = ()

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.execution_facts))
        if ordered != self.execution_facts:
            raise ValueError("execution facts must be sorted")
        if len({item.journal_sequence for item in ordered}) != len(ordered):
            raise ValueError("execution fact sequences must be unique")
        if ordered and (
            ordered[-1].journal_sequence
            != self.evidence.last_execution_fact_journal_sequence
        ):
            raise ValueError("execution fact bundle fence mismatch")
        prior_ordered = tuple(sorted(self.prior_session_execution_facts))
        if prior_ordered != self.prior_session_execution_facts:
            raise ValueError("prior-session execution facts must be sorted")
        if len({item.journal_sequence for item in prior_ordered}) != len(prior_ordered):
            raise ValueError("prior-session execution fact sequences must be unique")


class NoOvernightReconciliationRequired(ValueError):
    """A well-formed Local Paper projection differs from durable evidence."""

    def __init__(
        self,
        message: str,
        *,
        bundle: NoOvernightEvidenceBundle,
    ) -> None:
        super().__init__(message)
        self.bundle = bundle


class NoOvernightEvidenceReader(Protocol):
    def read(
        self,
        *,
        now: datetime,
        session_date: date,
    ) -> NoOvernightEvidenceBundle: ...


class NoOvernightCommandPort(Protocol):
    def execute(self, action: object) -> bool: ...


_T = TypeVar("_T")


class NoOvernightControllerGuard(Protocol):
    guard_identity: str

    def acquire(self) -> None: ...

    def is_owned_and_healthy(self) -> bool: ...

    def execute_if_owned(self, operation: Callable[[], _T]) -> _T: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class NoOvernightEnforcementAction:
    kind: str
    account_scope_id: str
    policy_family_id: str
    session_date: date
    state: NoOvernightState
    state_revision: int
    requested_at: datetime

    def __post_init__(self) -> None:
        allowed_states = {
            "CANCEL_MANAGED_BUY_REMAINDER": {
                NoOvernightState.CANCEL_ENTRY,
                NoOvernightState.FLATTENING,
                NoOvernightState.AGGRESSIVE_EXIT,
                NoOvernightState.FINAL_RECONCILIATION,
                NoOvernightState.CONFIRMED_FLAT,
                NoOvernightState.OVERNIGHT_BREACH,
            },
            "FLATTEN_MANAGED_EXPOSURES": {NoOvernightState.FLATTENING},
            "AGGRESSIVE_EXIT_MANAGED_EXPOSURES": {NoOvernightState.AGGRESSIVE_EXIT},
        }
        if self.kind not in allowed_states:
            raise ValueError("unsupported no-overnight enforcement action")
        if self.state not in allowed_states[self.kind]:
            raise ValueError("enforcement action does not match controller state")
        if not self.account_scope_id.strip() or not self.policy_family_id.strip():
            raise ValueError("enforcement action identity must not be empty")
        if type(self.state_revision) is not int or self.state_revision < 0:
            raise ValueError("enforcement action revision is invalid")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("enforcement action time must be timezone-aware")
        if self.requested_at.date() != self.session_date:
            raise ValueError("enforcement action session date mismatch")


class LocalPaperCancellationCommands(Protocol):
    def cancel_order(
        self,
        order_id: str,
        idempotency_key: str,
    ) -> tuple[dict[str, object], bool]: ...


class LocalPaperNoOvernightCommands(LocalPaperCancellationCommands, Protocol):
    def has_recorded_order_attempt(self, idempotency_key: str) -> bool: ...

    def submit_no_overnight_exit(
        self,
        *,
        exposure: ExposureIdentity,
        symbol: str,
        quantity_shares: int,
        limit_price: Decimal | str,
        idempotency_key: str,
        owner_strategy_version: str | None,
    ) -> tuple[dict[str, object], bool]: ...

    def retry_order(
        self,
        order_id: str,
        idempotency_key: str,
        *,
        limit_price: Decimal | str,
    ) -> tuple[dict[str, object], bool]: ...


class LocalPaperManagedEntryCancellationPort:
    """Cancel active managed BUY remainder without ever creating a SELL."""

    def __init__(
        self,
        *,
        commands: LocalPaperCancellationCommands,
        simulation: LocalPaperEvidenceSource,
    ) -> None:
        self._commands = commands
        self._simulation = simulation

    def execute(self, action: object) -> bool:
        if not isinstance(action, NoOvernightEnforcementAction):
            raise TypeError("no-overnight action type is invalid")
        if action.kind != "CANCEL_MANAGED_BUY_REMAINDER":
            raise ValueError("entry cancellation port received an exit action")
        return _cancel_managed_buy_remainders(
            commands=self._commands,
            simulation=self._simulation,
            action=action,
        )


def _cancel_managed_buy_remainders(
    *,
    commands: LocalPaperCancellationCommands,
    simulation: LocalPaperEvidenceSource,
    action: NoOvernightEnforcementAction,
) -> bool:
    active_states = {"SUBMITTED", "PENDING", "PARTIALLY_FILLED"}
    cancelled = False
    for order in simulation.orders():
        if order.get("status") not in active_states or order.get("side") != "BUY":
            continue
        raw_identity = order.get("exposure_identity")
        if not isinstance(raw_identity, Mapping):
            raise ValueError("active BUY is missing exposure identity")
        exposure = ExposureIdentity.from_payload(raw_identity)
        if not exposure.no_overnight_managed:
            continue
        if (
            exposure.account_scope_id != action.account_scope_id
            or exposure.policy_family_id != action.policy_family_id
        ):
            raise ValueError("active BUY exposure identity conflicts with controller")
        order_id = order.get("order_id")
        remaining_quantity = order.get("remaining_quantity")
        if type(order_id) is not str or not order_id:
            raise ValueError("managed BUY order identity is invalid")
        if type(remaining_quantity) is not int or remaining_quantity < 0:
            raise ValueError("managed BUY remaining quantity is invalid")
        if remaining_quantity == 0:
            continue
        cancel_key = build_semantic_action_key(
            account_scope_id=action.account_scope_id,
            policy_family_id=action.policy_family_id,
            session_date=action.session_date,
            exposure_id=exposure.exposure_id,
            action="CANCEL_ENTRY_REMAINDER",
            attempt=1,
            target_order_id=order_id,
        )
        commands.cancel_order(order_id, cancel_key)
        cancelled = True
    return cancelled


class LocalPaperNoOvernightCommandPort:
    """Execute only bounded Local Paper no-overnight cancellation and exits."""

    _ACTIVE_STATES = frozenset({"SUBMITTED", "PENDING", "PARTIALLY_FILLED"})
    _SUCCESSOR_STATES = frozenset({"CANCELLED", "EXPIRED"})
    _FAIL_CLOSED_STATES = frozenset({"REJECTED", "RECOVERY_REQUIRED", "SUBMIT_UNKNOWN"})

    def __init__(
        self,
        *,
        commands: LocalPaperNoOvernightCommands,
        simulation: LocalPaperExecutionContextSource,
        max_exit_attempts: int,
        retry_cooldown_seconds: int,
    ) -> None:
        if type(max_exit_attempts) is not int or max_exit_attempts <= 0:
            raise ValueError("max_exit_attempts must be positive")
        if type(retry_cooldown_seconds) is not int or retry_cooldown_seconds <= 0:
            raise ValueError("retry_cooldown_seconds must be positive")
        self._commands = commands
        self._simulation = simulation
        self._max_exit_attempts = max_exit_attempts
        self._retry_cooldown_seconds = retry_cooldown_seconds

    def execute(self, action: object) -> bool:
        if not isinstance(action, NoOvernightEnforcementAction):
            raise TypeError("no-overnight action type is invalid")
        if action.kind == "CANCEL_MANAGED_BUY_REMAINDER":
            return _cancel_managed_buy_remainders(
                commands=self._commands,
                simulation=self._simulation,
                action=action,
            )
        if action.kind == "FLATTEN_MANAGED_EXPOSURES":
            return self._flatten(action, aggressive=False)
        if action.kind == "AGGRESSIVE_EXIT_MANAGED_EXPOSURES":
            return self._flatten(action, aggressive=True)
        raise ValueError("unsupported no-overnight action")

    def _flatten(
        self,
        action: NoOvernightEnforcementAction,
        *,
        aggressive: bool,
    ) -> bool:
        changed = False
        orders = self._simulation.orders()
        for raw_exposure in self._managed_exposures(action):
            exposure = ExposureIdentity.from_payload(
                self._identity_payload(raw_exposure)
            )
            quantity = raw_exposure.get("quantity")
            symbol = raw_exposure.get("symbol")
            if type(quantity) is not int or quantity <= 0:
                raise ValueError("managed exposure quantity is invalid")
            if type(symbol) is not str or not symbol.strip():
                raise ValueError("managed exposure symbol is invalid")

            exposure_orders = self._exit_orders(
                orders,
                exposure_id=exposure.exposure_id,
            )
            active = [
                item
                for item in exposure_orders
                if item.get("status") in self._ACTIVE_STATES
            ]
            if len(active) > 1:
                raise ValueError("managed exposure has multiple active exits")
            if active:
                if aggressive and self._active_exit_is_stale(
                    active[0],
                    requested_at=action.requested_at,
                ):
                    order_id = self._order_id(active[0])
                    attempt = self._attempt(active[0])
                    cancel_key = build_semantic_action_key(
                        account_scope_id=action.account_scope_id,
                        policy_family_id=action.policy_family_id,
                        session_date=action.session_date,
                        exposure_id=exposure.exposure_id,
                        action="CANCEL_EXIT_ATTEMPT",
                        attempt=attempt,
                        target_order_id=order_id,
                    )
                    self._commands.cancel_order(order_id, cancel_key)
                    changed = True
                continue

            policy_orders = [
                item
                for item in exposure_orders
                if item.get("execution_reason_code") == "NO_OVERNIGHT_EXIT"
            ]
            if not policy_orders:
                price = self._executable_sell_price(symbol)
                if price is None:
                    continue
                owner_strategy_version = raw_exposure.get("owner_strategy_version")
                if (
                    owner_strategy_version is not None
                    and type(owner_strategy_version) is not str
                ):
                    raise ValueError("managed exposure strategy version is invalid")
                action_key = build_semantic_action_key(
                    account_scope_id=action.account_scope_id,
                    policy_family_id=action.policy_family_id,
                    session_date=action.session_date,
                    exposure_id=exposure.exposure_id,
                    action="FLATTEN_EXPOSURE",
                    attempt=1,
                )
                if self._commands.has_recorded_order_attempt(action_key):
                    continue
                self._commands.submit_no_overnight_exit(
                    exposure=exposure,
                    symbol=symbol,
                    quantity_shares=quantity,
                    limit_price=price,
                    idempotency_key=action_key,
                    owner_strategy_version=owner_strategy_version,
                )
                changed = True
                continue
            if not aggressive:
                continue

            latest = max(
                policy_orders,
                key=lambda item: (
                    self._attempt(item),
                    str(item.get("updated_at") or ""),
                    self._order_id(item),
                ),
            )
            status = latest.get("status")
            if (
                status in self._FAIL_CLOSED_STATES
                or status not in self._SUCCESSOR_STATES
            ):
                continue
            attempt = self._attempt(latest)
            if attempt >= self._max_exit_attempts:
                continue
            remaining = latest.get("remaining_quantity")
            if type(remaining) is not int or remaining <= 0 or remaining != quantity:
                continue
            price = self._executable_sell_price(symbol)
            if price is None:
                continue
            next_attempt = attempt + 1
            retry_key = build_semantic_action_key(
                account_scope_id=action.account_scope_id,
                policy_family_id=action.policy_family_id,
                session_date=action.session_date,
                exposure_id=exposure.exposure_id,
                action="AGGRESSIVE_EXIT",
                attempt=next_attempt,
            )
            if self._commands.has_recorded_order_attempt(retry_key):
                continue
            self._commands.retry_order(
                self._order_id(latest),
                retry_key,
                limit_price=price,
            )
            changed = True
        return changed

    def _managed_exposures(
        self,
        action: NoOvernightEnforcementAction,
    ) -> list[dict[str, object]]:
        managed: list[tuple[str, dict[str, object]]] = []
        for raw in self._simulation.exposures():
            exposure = ExposureIdentity.from_payload(self._identity_payload(raw))
            if not exposure.no_overnight_managed:
                continue
            if (
                exposure.account_scope_id != action.account_scope_id
                or exposure.policy_family_id != action.policy_family_id
            ):
                raise ValueError("managed exposure identity conflicts with controller")
            managed.append((exposure.exposure_id, dict(raw)))
        return [raw for _, raw in sorted(managed)]

    @staticmethod
    def _identity_payload(raw: Mapping[str, object]) -> Mapping[str, object]:
        payload = raw.get("exposure_identity")
        if not isinstance(payload, Mapping):
            raise ValueError("managed exposure identity is missing")
        return payload

    @staticmethod
    def _exit_orders(
        orders: list[dict[str, object]],
        *,
        exposure_id: str,
    ) -> list[dict[str, object]]:
        return [
            item
            for item in orders
            if item.get("side") == "SELL"
            and item.get("target_exposure_id") == exposure_id
        ]

    def _active_exit_is_stale(
        self,
        order: Mapping[str, object],
        *,
        requested_at: datetime,
    ) -> bool:
        updated_at = order.get("updated_at")
        if type(updated_at) is not str:
            raise ValueError("active exit updated_at is invalid")
        parsed = datetime.fromisoformat(updated_at)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("active exit updated_at must be timezone-aware")
        age = (requested_at - parsed).total_seconds()
        return age >= self._retry_cooldown_seconds

    def _executable_sell_price(self, symbol: str) -> str | None:
        context = self._simulation.execution_admission_context(
            symbol,
            "SELL",
            max_book_age_seconds=self._simulation.max_book_age_seconds,
        )
        if not (
            context.get("instrument_tradable") is True
            and context.get("executable_book_ready") is True
            and context.get("data_health_state") == "HEALTHY"
        ):
            return None
        raw_price = context.get("executable_price")
        if isinstance(raw_price, bool) or not isinstance(
            raw_price, (Decimal, str, int, float)
        ):
            return None
        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError):
            return None
        if not price.is_finite() or price <= 0:
            return None
        limit_resolver = getattr(
            self._simulation,
            "no_overnight_sell_limit_price",
            None,
        )
        if callable(limit_resolver):
            try:
                price = Decimal(str(limit_resolver(price)))
            except (TypeError, ValueError, InvalidOperation):
                return None
            if not price.is_finite() or price <= 0:
                return None
        return format(price, "f")

    @staticmethod
    def _attempt(order: Mapping[str, object]) -> int:
        attempt = order.get("attempt")
        if type(attempt) is not int or attempt <= 0:
            raise ValueError("exit attempt is invalid")
        return attempt

    @staticmethod
    def _order_id(order: Mapping[str, object]) -> str:
        order_id = order.get("order_id")
        if type(order_id) is not str or not order_id:
            raise ValueError("exit order identity is invalid")
        return order_id


class LocalPaperEvidenceSource(Protocol):
    def exposures(self) -> list[dict[str, object]]: ...

    def orders(self) -> list[dict[str, object]]: ...

    def no_overnight_reconciliation_context(self) -> dict[str, object]: ...


class LocalPaperExecutionContextSource(LocalPaperEvidenceSource, Protocol):
    @property
    def max_book_age_seconds(self) -> int: ...

    def execution_admission_context(
        self,
        symbol: str,
        side: str,
        *,
        max_book_age_seconds: int,
    ) -> dict[str, object]: ...


_LOCAL_EXECUTION_FACT_KINDS = frozenset(
    {
        "order_command.v2",
        LOCAL_PAPER_ORDER_STATE_V2_KIND,
        LOCAL_PAPER_FILL_V4_KIND,
        LOCAL_PAPER_REJECTION_V2_KIND,
        LOCAL_PAPER_CANCEL_INTENT_V2_KIND,
        LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
    }
)
_ACTIVE_ORDER_STATES = frozenset({"SUBMITTED", "PENDING", "PARTIALLY_FILLED"})


class LocalPaperNoOvernightEvidenceReader:
    """Derive managed evidence from authoritative v2 facts and simulator state."""

    def __init__(
        self,
        *,
        journal: JournalRepository,
        local_paper_session_id: str,
        simulation: LocalPaperEvidenceSource,
        account_scope_id: str,
        policy_family_id: str,
    ) -> None:
        self._journal = journal
        self._session_id = local_paper_session_id
        self._simulation = simulation
        self._account_scope_id = account_scope_id
        self._policy_family_id = policy_family_id

    def read(
        self,
        *,
        now: datetime,
        session_date: date,
    ) -> NoOvernightEvidenceBundle:
        balances: dict[str, int] = {}
        maximums: dict[str, int] = {}
        opened: dict[str, int] = {}
        closed: dict[str, int] = {}
        entry_session_dates: dict[str, date] = {}
        fact_items: list[tuple[str, ExecutionFactReference]] = []
        current_session_fact_ids: set[str] = set()
        last_fill_by_exposure: dict[str, int] = {}
        cancel_intents: dict[str, str] = {}
        cancel_results: set[str] = set()

        for appended in self._journal.records(self._session_id):
            record = appended.record
            if record.kind not in _LOCAL_EXECUTION_FACT_KINDS:
                continue
            exposure = self._record_exposure(record)
            if not self._is_family_managed(exposure):
                continue
            exposure_id = exposure.exposure_id
            self._bind_entry_session_date(entry_session_dates, exposure)
            fact_items.append(
                (
                    exposure_id,
                    ExecutionFactReference(
                        appended.sequence,
                        record.kind,
                        record.record_id,
                        exposure.entry_session_date,
                    ),
                )
            )
            if record.occurred_at.astimezone(now.tzinfo).date() == session_date:
                current_session_fact_ids.add(exposure_id)
            if record.kind in {
                LOCAL_PAPER_CANCEL_INTENT_V2_KIND,
                LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
            }:
                cancel_key = record.payload.get("cancel_idempotency_key")
                order_id = record.payload.get("order_id")
                if (
                    type(cancel_key) is not str
                    or not cancel_key
                    or type(order_id) is not str
                    or not order_id
                ):
                    raise ValueError("managed cancel execution identity is invalid")
                if record.kind == LOCAL_PAPER_CANCEL_INTENT_V2_KIND:
                    existing_order_id = cancel_intents.setdefault(cancel_key, order_id)
                    if existing_order_id != order_id:
                        raise ValueError("managed cancel intent identity conflicts")
                else:
                    if cancel_intents.get(cancel_key) != order_id:
                        raise ValueError(
                            "managed cancel result is missing matching intent"
                        )
                    cancel_results.add(cancel_key)
            if record.kind != LOCAL_PAPER_FILL_V4_KIND:
                continue
            fill = LocalPaperExposureFill.from_record(record)
            current = balances.get(exposure_id, 0)
            if fill.side.value == "BUY":
                opened[exposure_id] = opened.get(exposure_id, 0) + fill.quantity_shares
                current += fill.quantity_shares
                maximums[exposure_id] = max(maximums.get(exposure_id, 0), current)
            else:
                closed[exposure_id] = closed.get(exposure_id, 0) + fill.quantity_shares
                current -= fill.quantity_shares
                if current < 0:
                    raise ValueError(
                        "managed close fill exceeds authoritative open fills"
                    )
            balances[exposure_id] = current
            last_fill_by_exposure[exposure_id] = appended.sequence

        simulator_quantities: dict[str, int] = {}
        simulator_exposure_ids: set[str] = set()
        for raw in self._simulation.exposures():
            raw_identity = raw.get("exposure_identity")
            if not isinstance(raw_identity, Mapping):
                raise ValueError("simulator exposure identity is missing")
            exposure = ExposureIdentity.from_payload(raw_identity)
            if exposure.exposure_id in simulator_exposure_ids:
                raise ValueError("simulator exposure identity is duplicated")
            simulator_exposure_ids.add(exposure.exposure_id)
            if not self._is_family_managed(exposure):
                continue
            self._bind_entry_session_date(entry_session_dates, exposure)
            quantity = raw.get("quantity")
            if type(quantity) is not int or quantity < 0:
                raise ValueError("simulator managed quantity is invalid")
            simulator_quantities[exposure.exposure_id] = quantity

        pending_entries: dict[str, int] = {}
        pending_exits: dict[str, int] = {}
        unresolved: list[str] = []
        active_order_exposure_ids: set[str] = set()
        durable_managed_orders: dict[str, Mapping[str, object]] = {}
        for state in latest_local_paper_order_states(
            self._journal,
            session_id=self._session_id,
        ):
            raw_identity = state.get("exposure_identity")
            if not isinstance(raw_identity, Mapping):
                continue
            exposure = ExposureIdentity.from_payload(raw_identity)
            if not self._is_family_managed(exposure):
                continue
            order_id = state.get("order_id")
            if type(order_id) is not str or not order_id:
                raise ValueError("durable managed order identity is invalid")
            durable_managed_orders[order_id] = (
                self._canonical_order_reconciliation_projection(state)
            )

        simulator_managed_orders: dict[str, Mapping[str, object]] = {}
        for raw in self._simulation.orders():
            raw_identity = raw.get("exposure_identity")
            if not isinstance(raw_identity, Mapping):
                continue
            exposure = ExposureIdentity.from_payload(raw_identity)
            if not self._is_family_managed(exposure):
                continue
            self._bind_entry_session_date(entry_session_dates, exposure)
            status = raw.get("status")
            order_id = raw.get("order_id")
            if type(status) is not str or type(order_id) is not str:
                raise ValueError("simulator managed order identity is invalid")
            if order_id in simulator_managed_orders:
                raise ValueError("simulator managed order identity is duplicated")
            try:
                simulator_managed_orders[order_id] = (
                    self._canonical_order_reconciliation_projection(
                        canonical_v2_order_state_from_simulation_order(
                            raw,
                            session_id=self._session_id,
                        )
                    )
                )
            except OrderStateReconciliationConflict:
                simulator_managed_orders[order_id] = {
                    "order_id": order_id,
                    "order_state_validation": "INVALID",
                }
            if status == "RECOVERY_REQUIRED":
                unresolved.append(order_id)
                active_order_exposure_ids.add(exposure.exposure_id)
            if status not in _ACTIVE_ORDER_STATES:
                continue
            active_order_exposure_ids.add(exposure.exposure_id)
            remaining = raw.get("remaining_quantity")
            if type(remaining) is not int or remaining < 0:
                raise ValueError("simulator remaining quantity is invalid")
            target = pending_entries if raw.get("side") == "BUY" else pending_exits
            target[exposure.exposure_id] = (
                target.get(exposure.exposure_id, 0) + remaining
            )
        mismatch_messages: list[str] = []
        mismatch_codes: list[str] = []
        if set(durable_managed_orders) != set(simulator_managed_orders):
            mismatch_messages.append(
                "managed order Journal/simulator identity mismatch"
            )
            mismatch_codes.append("ORDER_IDENTITY_MISMATCH")
        elif any(
            dict(durable_managed_orders[order_id])
            != dict(simulator_managed_orders[order_id])
            for order_id in durable_managed_orders
        ):
            mismatch_messages.append("managed order Journal/simulator state mismatch")
            mismatch_codes.append("ORDER_STATE_MISMATCH")
        unresolved.extend(
            f"cancel:{cancel_key}"
            for cancel_key in sorted(set(cancel_intents) - cancel_results)
        )

        exposure_ids = sorted(
            {
                exposure_id
                for exposure_id, entry_date in entry_session_dates.items()
                if entry_date == session_date
            }
            | {
                exposure_id
                for exposure_id, quantity in balances.items()
                if quantity > 0
            }
            | {
                exposure_id
                for exposure_id, quantity in simulator_quantities.items()
                if quantity > 0
            }
            | active_order_exposure_ids
            | current_session_fact_ids
        )
        if any(
            balances.get(exposure_id, 0) != simulator_quantities.get(exposure_id, 0)
            for exposure_id in exposure_ids
        ):
            mismatch_messages.append(
                "managed exposure Journal/simulator reconciliation mismatch"
            )
            mismatch_codes.append("EXPOSURE_QUANTITY_MISMATCH")
        session = self._journal.session(self._session_id)
        if session is None:
            raise ValueError("Local Paper Journal session is missing")
        raw_starting_cash = session.metadata.get("starting_cash")
        if type(raw_starting_cash) is not str:
            raise ValueError("Local Paper starting cash identity is invalid")
        try:
            starting_cash = Decimal(raw_starting_cash)
        except InvalidOperation as error:
            raise ValueError("Local Paper starting cash identity is invalid") from error
        raw_settings_digest = session.metadata.get("settings_digest")
        if type(raw_settings_digest) is not str:
            raise ValueError("Local Paper settings digest identity is invalid")
        durable_projection = rebuild_local_paper_v2_projection(
            self._journal,
            session_id=self._session_id,
            starting_cash=starting_cash,
            account_scope_id=self._account_scope_id,
            policy_family_id=self._policy_family_id,
            settings_digest=raw_settings_digest,
            require_checkpoint=True,
        )
        simulator_accounting = self._simulation.no_overnight_reconciliation_context()
        expected_accounting = self._canonical_accounting_context(
            {
                "starting_cash": format(starting_cash, "f"),
                "cash": format(durable_projection.cash, "f"),
                "realized_pnl_by_exposure": {
                    exposure_id: format(value, "f")
                    for exposure_id, value in sorted(
                        durable_projection.realized_pnl_by_exposure.items()
                    )
                },
            }
        )
        normalized_simulator_accounting = self._canonical_accounting_context(
            simulator_accounting
        )
        if normalized_simulator_accounting != expected_accounting:
            mismatch_messages.append("managed accounting Journal/simulator mismatch")
            mismatch_codes.append("ACCOUNTING_MISMATCH")
        facts = [
            fact for exposure_id, fact in fact_items if exposure_id in exposure_ids
        ]
        last_fill_sequence = max(
            (
                sequence
                for exposure_id, sequence in last_fill_by_exposure.items()
                if exposure_id in exposure_ids
            ),
            default=0,
        )

        normalized = {
            "managed_exposures": [
                {
                    "exposure_id": exposure_id,
                    "current_quantity": balances.get(exposure_id, 0),
                    "max_quantity_during_session": maximums.get(exposure_id, 0),
                    "authoritative_open_fill_quantity": opened.get(exposure_id, 0),
                    "authoritative_close_fill_quantity": closed.get(exposure_id, 0),
                }
                for exposure_id in exposure_ids
            ],
            "pending_entry_quantity": sorted(pending_entries.items()),
            "pending_exit_quantity": sorted(pending_exits.items()),
            "unresolved_execution_ids": sorted(unresolved),
            "reconciliation": {
                "mismatch_codes": sorted(mismatch_codes),
                "durable_exposure_quantity": sorted(
                    (exposure_id, balances.get(exposure_id, 0))
                    for exposure_id in exposure_ids
                ),
                "simulator_exposure_quantity": sorted(
                    (exposure_id, simulator_quantities.get(exposure_id, 0))
                    for exposure_id in exposure_ids
                ),
                "durable_orders": [
                    self._json_safe_value(durable_managed_orders[order_id])
                    for order_id in sorted(durable_managed_orders)
                ],
                "simulator_orders": [
                    self._json_safe_value(simulator_managed_orders[order_id])
                    for order_id in sorted(simulator_managed_orders)
                ],
                "durable_accounting": expected_accounting,
                "simulator_accounting": normalized_simulator_accounting,
            },
        }
        reconciliation_digest = hashlib.sha256(
            json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        last_execution_sequence = facts[-1].journal_sequence if facts else 0
        evidence = NoOvernightEvidence(
            session_date=session_date,
            managed_exposures=tuple(
                ManagedExposureEvidence(**item)
                for item in normalized["managed_exposures"]
            ),
            pending_entry_quantity=tuple(
                ExposureQuantity(exposure_id=key, quantity=value)
                for key, value in normalized["pending_entry_quantity"]
            ),
            pending_exit_quantity=tuple(
                ExposureQuantity(exposure_id=key, quantity=value)
                for key, value in normalized["pending_exit_quantity"]
            ),
            unresolved_execution_ids=tuple(normalized["unresolved_execution_ids"]),
            reconciliation_status=(
                ReconciliationStatus.REQUIRED
                if mismatch_messages
                else ReconciliationStatus.MATCH
            ),
            reconciliation_digest=reconciliation_digest,
            last_fill_journal_sequence=last_fill_sequence,
            last_execution_fact_journal_sequence=last_execution_sequence,
            snapshot_covers_through_journal_sequence=last_execution_sequence,
            snapshot_journal_sequence=0,
            snapshot_source_as_of=now,
            snapshot_received_at=now,
        )
        bundle = NoOvernightEvidenceBundle(
            evidence=evidence,
            execution_facts=tuple(facts),
            prior_session_execution_facts=tuple(
                fact for _, fact in fact_items if fact.entry_session_date < session_date
            ),
        )
        if mismatch_messages:
            raise NoOvernightReconciliationRequired(
                "; ".join(mismatch_messages),
                bundle=bundle,
            )
        return bundle

    def _record_exposure(self, record: JournalRecord) -> ExposureIdentity | None:
        if record.kind == "order_command.v2":
            return order_command_from_record(record).exposure
        raw_identity = record.payload.get("exposure_identity")
        if not isinstance(raw_identity, Mapping):
            raise ValueError("v2 execution fact exposure identity is missing")
        return ExposureIdentity.from_payload(raw_identity)

    @classmethod
    def _json_safe_value(cls, value: object) -> object:
        """Copy immutable Journal payload containers into canonical JSON values."""

        if isinstance(value, Mapping):
            return {
                str(key): cls._json_safe_value(nested)
                for key, nested in value.items()
            }
        if isinstance(value, (tuple, list)):
            return [cls._json_safe_value(nested) for nested in value]
        if value is None or type(value) in {bool, int, float, str}:
            return value
        raise ValueError(
            f"managed reconciliation contains non-JSON value {type(value).__name__}"
        )

    def _is_family_managed(
        self,
        exposure: ExposureIdentity | None,
    ) -> bool:
        if exposure is None or not exposure.no_overnight_managed:
            return False
        if (
            exposure.account_scope_id != self._account_scope_id
            or exposure.policy_family_id != self._policy_family_id
        ):
            raise ValueError("managed exposure identity conflicts with controller")
        return True

    @staticmethod
    def _bind_entry_session_date(
        entry_session_dates: dict[str, date],
        exposure: ExposureIdentity,
    ) -> None:
        existing = entry_session_dates.setdefault(
            exposure.exposure_id,
            exposure.entry_session_date,
        )
        if existing != exposure.entry_session_date:
            raise ValueError("managed exposure entry session identity changed")

    @staticmethod
    def _canonical_accounting_context(
        raw: Mapping[str, object],
    ) -> dict[str, object]:
        required = {"starting_cash", "cash", "realized_pnl_by_exposure"}
        if set(raw) != required:
            raise ValueError("managed accounting context fields are invalid")

        def canonical_amount(value: object, field_name: str) -> str:
            if type(value) is not str:
                raise ValueError(f"managed accounting {field_name} is invalid")
            try:
                parsed = Decimal(value)
            except InvalidOperation as error:
                raise ValueError(
                    f"managed accounting {field_name} is invalid"
                ) from error
            if not parsed.is_finite():
                raise ValueError(f"managed accounting {field_name} is invalid")
            return canonical_decimal_string(parsed)

        realized = raw["realized_pnl_by_exposure"]
        if not isinstance(realized, Mapping):
            raise ValueError("managed accounting realized PnL is invalid")
        normalized_realized: dict[str, str] = {}
        for exposure_id, value in realized.items():
            if type(exposure_id) is not str or not exposure_id:
                raise ValueError("managed accounting exposure identity is invalid")
            normalized_realized[exposure_id] = canonical_amount(
                value,
                f"realized PnL {exposure_id}",
            )
        return {
            "starting_cash": canonical_amount(raw["starting_cash"], "starting_cash"),
            "cash": canonical_amount(raw["cash"], "cash"),
            "realized_pnl_by_exposure": {
                exposure_id: normalized_realized[exposure_id]
                for exposure_id in sorted(normalized_realized)
            },
        }

    @staticmethod
    def _canonical_order_reconciliation_projection(
        raw: Mapping[str, object],
    ) -> dict[str, object]:
        normalized = dict(raw)
        identity = normalized.get("exposure_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("managed order exposure identity is invalid")
        normalized["exposure_identity"] = dict(
            ExposureIdentity.from_payload(identity).to_payload()
        )
        return normalized


def _durable_breach_projections(
    *,
    journal: JournalRepository,
    config: NoOvernightPolicyConfig,
    current_session_date: date,
    before_session_date: date | None = None,
) -> tuple[NoOvernightProjection, ...]:
    projections: list[NoOvernightProjection] = []
    sessions = journal.sessions(
        session_id_prefix=NO_OVERNIGHT_SESSION_ID_PREFIX,
    )
    for session in sessions:
        raw_session_date = session.metadata.get("session_date")
        raw_account_scope_id = session.metadata.get("account_scope_id")
        raw_policy_family_id = session.metadata.get("policy_family_id")
        if (
            type(raw_session_date) is not str
            or type(raw_account_scope_id) is not str
            or type(raw_policy_family_id) is not str
        ):
            raise ValueError("no-overnight session identity is incomplete")
        session_date = date.fromisoformat(raw_session_date)
        if session.session_id != no_overnight_session_id(session_date):
            raise ValueError("no-overnight session identity conflicts")
        if session_date > current_session_date:
            raise ValueError("future no-overnight session is not admissible")
        if (
            raw_account_scope_id != config.account_scope_id
            or raw_policy_family_id != config.policy_family_id
        ):
            raise ValueError("no-overnight scope or policy family conflicts")
        if before_session_date is not None and session_date >= before_session_date:
            continue
        projection = rebuild_no_overnight_projection(
            journal,
            session_id=session.session_id,
            require_checkpoint=True,
        )
        if projection.state is NoOvernightState.OVERNIGHT_BREACH:
            if projection.breach_id is None:
                raise NoOvernightProjectionError("durable breach identity is missing")
            validate_breach_evidence_reference(journal, projection)
            projections.append(projection)
        elif projection.breach_id is not None:
            raise NoOvernightProjectionError(
                "breach identity exists outside OVERNIGHT_BREACH"
            )
    return tuple(
        sorted(
            projections,
            key=lambda item: (
                item.session_date or date.min,
                item.breach_id or "",
            ),
        )
    )


def _historical_policy_identity(
    *,
    journal: JournalRepository,
    session_id: str,
    projection: NoOvernightProjection,
) -> tuple[str, str]:
    policy_version = projection.policy_version
    policy_digest = projection.policy_digest
    if (
        type(policy_version) is not str
        or not policy_version.strip()
        or type(policy_digest) is not str
        or len(policy_digest) != 64
        or any(character not in "0123456789abcdef" for character in policy_digest)
    ):
        raise NoOvernightProjectionError(
            "historical no-overnight policy identity is incomplete"
        )
    session = journal.session(session_id)
    if session is None or (
        session.metadata.get("policy_version") != policy_version
        or session.metadata.get("policy_digest") != policy_digest
    ):
        raise NoOvernightProjectionError(
            "historical no-overnight policy identity conflicts"
        )
    return policy_version, policy_digest


def _breach_released(
    projection: NoOvernightProjection,
    *,
    current_session_date: date,
    calendar: ReviewedEquityCalendar,
) -> bool:
    eligible_by_date = bool(
        projection.breach_resolved
        and projection.breach_acknowledged
        and projection.breach_ack_session_date is not None
        and current_session_date > projection.breach_ack_session_date
    )
    if not eligible_by_date:
        return False
    try:
        return calendar.is_trading_day(current_session_date)
    except ValueError:
        return False


def _breach_reason_for(evidence: NoOvernightEvidence) -> str:
    if evidence.reconciliation_status is not ReconciliationStatus.MATCH:
        return "RECONCILIATION_REQUIRED"
    if any(item.current_quantity > 0 for item in evidence.managed_exposures):
        return "MANAGED_EXPOSURE_OPEN"
    if evidence.pending_entry_quantity or evidence.pending_exit_quantity:
        return "PENDING_ORDER"
    if evidence.unresolved_execution_ids:
        return "UNRESOLVED_EXECUTION"
    return "STRICT_FLAT_PROOF_MISSING"


def _breach_summary(
    projection: NoOvernightProjection,
    *,
    current_session_date: date,
    calendar: ReviewedEquityCalendar,
) -> dict[str, object]:
    if (
        projection.breach_id is None
        or projection.session_date is None
        or projection.breach_reconciliation_digest is None
    ):
        raise NoOvernightProjectionError("breach summary identity is incomplete")
    released = _breach_released(
        projection,
        current_session_date=current_session_date,
        calendar=calendar,
    )
    return {
        "schema_version": "no_overnight_breach_status_v1",
        "breach_id": projection.breach_id,
        "originating_session_date": projection.session_date.isoformat(),
        "open": not released,
        "released": released,
        "breach_revision": projection.breach_revision,
        "breach_reason": projection.breach_reason,
        "revision_reason": projection.breach_revision_reason,
        "severity": projection.breach_severity,
        "managed_open_quantity": projection.breach_managed_open_quantity,
        "pending_entry_quantity": projection.breach_pending_entry_quantity,
        "pending_exit_quantity": projection.breach_pending_exit_quantity,
        "unresolved_execution_count": (projection.breach_unresolved_execution_count),
        "evidence_session_date": (
            None
            if projection.breach_evidence_session_date is None
            else projection.breach_evidence_session_date.isoformat()
        ),
        "evidence_through_journal_sequence": (
            projection.breach_evidence_through_journal_sequence
        ),
        "reconciliation_digest": projection.breach_reconciliation_digest,
        "strict_flat_proof_mode": projection.breach_strict_flat_proof_mode,
        "resolved": projection.breach_resolved,
        "resolved_session_date": (
            None
            if projection.breach_resolution_session_date is None
            else projection.breach_resolution_session_date.isoformat()
        ),
        "resolution_journal_sequence": (projection.breach_resolution_sequence or None),
        "acknowledged": projection.breach_acknowledged,
        "acknowledged_by": projection.breach_ack_actor_id,
        "acknowledged_session_date": (
            None
            if projection.breach_ack_session_date is None
            else projection.breach_ack_session_date.isoformat()
        ),
        "acknowledgement_journal_sequence": (projection.breach_ack_sequence or None),
        "release_requires_later_reviewed_session": bool(
            projection.breach_acknowledged and not released
        ),
    }


class LocalPaperExecutionAdmissionReader:
    """Re-read calendar, projection, instrument, book, and guard server facts."""

    def __init__(
        self,
        *,
        config: NoOvernightPolicyConfig,
        calendar: ReviewedEquityCalendar,
        journal: JournalRepository,
        clock: Clock,
        simulation: LocalPaperExecutionContextSource,
        guard: NoOvernightControllerGuard | None,
    ) -> None:
        if config.mode is NoOvernightMode.ENFORCING and guard is None:
            raise ValueError("ENFORCING execution admission requires a guard")
        if calendar.timezone != config.timezone:
            raise ValueError("admission calendar timezone conflicts with policy")
        if guard is not None and not callable(
            getattr(guard, "execute_if_owned", None)
        ):
            raise ValueError("admission guard does not provide an ownership fence")
        self._config = config
        self._calendar = calendar
        self._journal = journal
        self._clock = clock
        self._simulation = simulation
        self._guard = guard
        self._local_fence = RLock()

    def execute_under_admission_fence(self, operation: Callable[[], _T]) -> _T:
        if self._guard is not None:
            return self._guard.execute_if_owned(operation)
        with self._local_fence:
            return operation()

    def read(
        self,
        command: OrderCommand,
        *,
        expected_revision: str | None = None,
    ) -> ExecutionAdmissionDecision:
        return self.read_at(
            command,
            expected_revision=expected_revision,
            evaluated_at=self._clock.now(),
        )

    def read_at(
        self,
        command: OrderCommand,
        *,
        expected_revision: str | None = None,
        evaluated_at: datetime,
    ) -> ExecutionAdmissionDecision:
        now = evaluated_at
        zone = ZoneInfo(self._config.timezone)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("admission clock must be timezone-aware")
        local_now = now.astimezone(zone)
        session_date = local_now.date()
        if self._config.mode is not NoOvernightMode.ENFORCING:
            recovery_required = False
            open_breach: OpenBreachFence | None = None
            try:
                open_breach = self._open_breach_fence(session_date)
            except Exception:
                recovery_required = True
            snapshot = ExecutionAdmissionSnapshot(
                evaluated_at=local_now,
                session_date=session_date,
                state=NoOvernightState.NORMAL,
                state_revision=0,
                policy_digest=self._config.policy_digest,
                calendar_digest=self._calendar.source_digest,
                session_open=True,
                instrument_tradable=True,
                executable_book_ready=True,
                guard_owned=True,
                guard_healthy=True,
                recovery_required=recovery_required,
                breach_latched=open_breach is not None,
                breach_session_date=(
                    None if open_breach is None else open_breach.session_date
                ),
                breach_revision=(
                    0 if open_breach is None else open_breach.revision
                ),
            )
            return evaluate_execution_admission(
                command=command,
                config=self._config,
                snapshot=snapshot,
                expected_revision=expected_revision,
                final_check=expected_revision is not None,
            )
        recovery_required = False
        try:
            reviewed_trading_day = self._calendar.is_trading_day(session_date)
        except ValueError:
            reviewed_trading_day = False
            recovery_required = True
        wall_time = local_now.timetz().replace(tzinfo=None)
        session_open = (
            reviewed_trading_day
            and self._config.market_open <= wall_time
            and wall_time < self._config.reviewed_session_close
        )

        state = NoOvernightState.NORMAL
        revision = 0
        session_id = no_overnight_session_id(session_date)
        if self._journal.session(session_id) is None:
            recovery_required = True
        else:
            try:
                projection = rebuild_no_overnight_projection(
                    self._journal,
                    session_id=session_id,
                    require_checkpoint=True,
                )
                state = projection.state
                revision = projection.revision
                if projection.policy_digest not in {
                    None,
                    self._config.policy_digest,
                }:
                    recovery_required = True
                if (
                    projection.evidence is None
                    or projection.evidence.reconciliation_status
                    is not ReconciliationStatus.MATCH
                ):
                    recovery_required = True
            except Exception:
                recovery_required = True

        open_breach: OpenBreachFence | None = None
        try:
            open_breach = self._open_breach_fence(session_date)
        except Exception:
            recovery_required = True
        if state is NoOvernightState.OVERNIGHT_BREACH and open_breach is None:
            recovery_required = True

        try:
            context = self._simulation.execution_admission_context(
                command.symbol,
                command.side.value,
                max_book_age_seconds=self._simulation.max_book_age_seconds,
            )
            instrument_tradable = context.get("instrument_tradable") is True
            executable_book_ready = context.get("executable_book_ready") is True
            if context.get("data_health_state") != "HEALTHY":
                recovery_required = True
        except Exception:
            instrument_tradable = False
            executable_book_ready = False
            recovery_required = True

        assert self._guard is not None
        guard_healthy = self._guard.is_owned_and_healthy()
        snapshot = ExecutionAdmissionSnapshot(
            evaluated_at=local_now,
            session_date=session_date,
            state=state,
            state_revision=revision,
            policy_digest=self._config.policy_digest,
            calendar_digest=self._calendar.source_digest,
            session_open=session_open,
            instrument_tradable=instrument_tradable,
            executable_book_ready=executable_book_ready,
            guard_owned=guard_healthy,
            guard_healthy=guard_healthy,
            recovery_required=recovery_required,
            breach_latched=open_breach is not None,
            breach_session_date=(
                None if open_breach is None else open_breach.session_date
            ),
            breach_revision=0 if open_breach is None else open_breach.revision,
        )
        return evaluate_execution_admission(
            command=command,
            config=self._config,
            snapshot=snapshot,
            expected_revision=expected_revision,
            final_check=expected_revision is not None,
        )

    def _open_breach_fence(
        self,
        current_session_date: date,
    ) -> OpenBreachFence | None:
        earliest: OpenBreachFence | None = None
        for projection in _durable_breach_projections(
            journal=self._journal,
            config=self._config,
            current_session_date=current_session_date,
        ):
            if _breach_released(
                projection,
                current_session_date=current_session_date,
                calendar=self._calendar,
            ):
                continue
            if (
                projection.session_date is None
                or projection.breach_id is None
                or projection.breach_reconciliation_digest is None
            ):
                raise NoOvernightProjectionError(
                    "open breach fence identity is incomplete"
                )
            fence = OpenBreachFence(
                session_date=projection.session_date,
                revision=projection.breach_revision,
                breach_id=projection.breach_id,
                reconciliation_digest=projection.breach_reconciliation_digest,
            )
            if earliest is None or fence < earliest:
                earliest = fence
        return earliest


def no_overnight_session_id(session_date: date) -> str:
    return f"{NO_OVERNIGHT_SESSION_ID_PREFIX}{session_date.isoformat()}"


class NoOvernightController:
    """Project controller state and enforce bounded Local Paper close actions."""

    def __init__(
        self,
        *,
        config: NoOvernightPolicyConfig,
        calendar: ReviewedEquityCalendar,
        journal: JournalRepository,
        evidence_reader: NoOvernightEvidenceReader,
        command_port: NoOvernightCommandPort | None = None,
        guard: NoOvernightControllerGuard | None = None,
        deployment_manifest_digest: str | None = None,
    ) -> None:
        if config.mode is NoOvernightMode.ENFORCING and (
            command_port is None or guard is None or deployment_manifest_digest is None
        ):
            raise ValueError(
                "ENFORCING requires guard and command port plus deployment manifest"
            )
        if config.mode is NoOvernightMode.ENFORCING and not callable(
            getattr(guard, "execute_if_owned", None)
        ):
            raise ValueError("ENFORCING guard does not provide an ownership fence")
        if deployment_manifest_digest is not None and (
            len(deployment_manifest_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in deployment_manifest_digest
            )
        ):
            raise ValueError("deployment manifest digest is invalid")
        if calendar.timezone != config.timezone:
            raise ValueError("reviewed calendar timezone conflicts with policy")
        self._config = config
        self._calendar = calendar
        self._journal = journal
        self._evidence_reader = evidence_reader
        self._command_port = command_port
        self._guard = guard
        self._deployment_manifest_digest = deployment_manifest_digest
        self._status: dict[str, object] = {
            "schema_version": "no_overnight_status_v1",
            "mode": config.mode.value,
            "enforcing": config.mode is NoOvernightMode.ENFORCING,
            "state": "DISABLED"
            if config.mode is NoOvernightMode.DISABLED
            else "NORMAL",
            "revision": 0,
            "session_date": None,
            "policy_version": config.policy_version,
            "policy_digest": config.policy_digest,
            "deployment_manifest_digest": deployment_manifest_digest,
            "guard_identity": (
                guard.guard_identity
                if config.mode is NoOvernightMode.ENFORCING and guard is not None
                else None
            ),
            "would_actions": [],
            "flat_proof_mode": None,
            "result_status": None,
            "reconciliation_status": None,
            "reconciliation_digest": None,
            "last_execution_fact_journal_sequence": 0,
            "snapshot_covers_through_journal_sequence": 0,
            "breach": None,
            "message": (
                "收盤風控未啟用，不會阻擋或送出委託。"
                if config.mode is NoOvernightMode.DISABLED
                else (
                    "收盤風控執行中，會阻擋新當沖、取消進場餘量並集中平倉。"
                    if config.mode is NoOvernightMode.ENFORCING
                    else "收盤風控僅觀察，不會阻擋、取消或送出委託。"
                )
            ),
        }

    @property
    def config(self) -> NoOvernightPolicyConfig:
        return self._config

    @property
    def calendar(self) -> ReviewedEquityCalendar:
        return self._calendar

    def status(self) -> dict[str, object]:
        return dict(self._status)

    def run_once(self, now: datetime) -> dict[str, object]:
        if self._config.mode is NoOvernightMode.DISABLED:
            return self.status()
        if self._config.mode is NoOvernightMode.ENFORCING:
            assert self._guard is not None
            return self._guard.execute_if_owned(lambda: self._run_once(now))
        return self._run_once(now)

    def _run_once(self, now: datetime) -> dict[str, object]:
        self._require_healthy_guard()
        zone = ZoneInfo(self._config.timezone)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("controller clock must be timezone-aware")
        local_now = now.astimezone(zone)
        if local_now.replace(tzinfo=None) != now.replace(tzinfo=None):
            raise ValueError("controller clock timezone differs from policy timezone")
        session_date = local_now.date()
        if not self._calendar.is_trading_day(session_date):
            raise ValueError("controller date is not a reviewed trading day")
        window = self._window(session_date)
        session_id = no_overnight_session_id(session_date)
        self._start_or_validate_session(session_id, window, local_now)
        projection = rebuild_no_overnight_projection(
            self._journal,
            session_id=session_id,
            require_checkpoint=True,
        )
        self._bootstrap_legacy_breaches(
            before_session_date=session_date,
        )
        evidence: NoOvernightEvidence | None = None
        for _ in range(3):
            bundle = self._read_evidence_bundle(
                now=local_now,
                session_date=session_date,
            )
            self._route_prior_session_execution_facts(
                bundle.prior_session_execution_facts,
                current_session_date=session_date,
                observed_at=local_now,
            )
            for fact in bundle.execution_facts:
                if (
                    fact.journal_sequence
                    <= projection.last_execution_fact_journal_sequence
                ):
                    continue
                self._journal.append(
                    execution_fact_observed_record(
                        session_id=session_id,
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        session_date=session_date,
                        source_journal_sequence=fact.journal_sequence,
                        source_kind=fact.kind,
                        source_record_id=fact.record_id,
                        occurred_at=local_now,
                    )
                )
                projection = rebuild_no_overnight_projection(
                    self._journal,
                    session_id=session_id,
                    require_checkpoint=False,
                )

            snapshot_payload = {
                "account_scope_id": self._config.account_scope_id,
                "policy_family_id": self._config.policy_family_id,
                **bundle.evidence.payload(),
            }
            self._journal.append(
                snapshot_record(session_id=session_id, payload=snapshot_payload)
            )
            projection = rebuild_no_overnight_projection(
                self._journal,
                session_id=session_id,
                require_checkpoint=False,
            )
            if projection.evidence is None:
                raise ValueError("no-overnight snapshot append was not projected")
            post_snapshot = self._read_evidence_bundle(
                now=local_now,
                session_date=session_date,
            )
            if (
                post_snapshot.evidence.last_execution_fact_journal_sequence
                == bundle.evidence.last_execution_fact_journal_sequence
                and post_snapshot.prior_session_execution_facts
                == bundle.prior_session_execution_facts
                and post_snapshot.evidence.reconciliation_status
                is bundle.evidence.reconciliation_status
                and post_snapshot.evidence.reconciliation_digest
                == bundle.evidence.reconciliation_digest
            ):
                evidence = projection.evidence
                break
        if evidence is None:
            write_no_overnight_checkpoint(self._journal, session_id=session_id)
            raise ValueError(
                "execution facts advanced repeatedly during no-overnight snapshot"
            )
        prior_breach_exists = any(
            not _breach_released(
                item,
                current_session_date=session_date,
                calendar=self._calendar,
            )
            for item in _durable_breach_projections(
                journal=self._journal,
                config=self._config,
                current_session_date=session_date,
                before_session_date=session_date,
            )
        )
        latest_flat_proof = strict_flat_proof(evidence)
        terminal_proof_changed = (
            projection.state is NoOvernightState.CONFIRMED_FLAT
            and projection.result_status is None
            and latest_flat_proof is not None
            and latest_flat_proof.value != projection.flat_proof_mode
        )
        plan = plan_no_overnight_transition(
            config=self._config,
            window=window,
            now=local_now,
            current_state=projection.state,
            current_revision=projection.revision,
            evidence=evidence,
            result_superseded=(
                projection.result_status == "SUPERSEDED" or terminal_proof_changed
            ),
        )
        if self._config.mode is NoOvernightMode.ENFORCING and plan.state in {
            NoOvernightState.CANCEL_ENTRY,
            NoOvernightState.FLATTENING,
            NoOvernightState.AGGRESSIVE_EXIT,
            NoOvernightState.FINAL_RECONCILIATION,
            NoOvernightState.CONFIRMED_FLAT,
            NoOvernightState.OVERNIGHT_BREACH,
        }:
            self._require_healthy_guard()
            assert self._command_port is not None
            action_kinds = ["CANCEL_MANAGED_BUY_REMAINDER"]
            if plan.state is NoOvernightState.FLATTENING:
                action_kinds.append("FLATTEN_MANAGED_EXPOSURES")
            elif plan.state is NoOvernightState.AGGRESSIVE_EXIT:
                action_kinds.append("AGGRESSIVE_EXIT_MANAGED_EXPOSURES")
            for action_kind in action_kinds:
                changed = self._command_port.execute(
                    NoOvernightEnforcementAction(
                        kind=action_kind,
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        session_date=session_date,
                        state=plan.state,
                        state_revision=plan.revision,
                        requested_at=local_now,
                    )
                )
                if changed is True:
                    return self.run_once(local_now)
        transition_appended = plan.revision > projection.revision
        if transition_appended:
            self._journal.append(
                transition_record(
                    session_id=session_id,
                    account_scope_id=self._config.account_scope_id,
                    policy_family_id=self._config.policy_family_id,
                    session_date=session_date,
                    policy_version=self._config.policy_version,
                    policy_digest=self._config.policy_digest,
                    previous_state=plan.previous_state,
                    state=plan.state,
                    revision=plan.revision,
                    planned_at=plan.planned_at,
                    would_actions=tuple(action.value for action in plan.would_actions),
                    planner_input_digest=plan.planner_input_digest,
                    transition_digest=plan.digest,
                    flat_proof_mode=plan.flat_proof_mode,
                )
            )
        reconciliation_appended = None
        if (
            NoOvernightWouldAction.WOULD_RECONCILE in plan.would_actions
            or prior_breach_exists
        ):
            reconciliation_appended = self._journal.append(
                no_overnight_reconciliation_record(
                    session_id=session_id,
                    account_scope_id=self._config.account_scope_id,
                    policy_family_id=self._config.policy_family_id,
                    session_date=session_date,
                    policy_version=self._config.policy_version,
                    policy_digest=self._config.policy_digest,
                    evidence=evidence,
                    reconciled_at=local_now,
                )
            )
        result_appended = None
        if plan.state in {
            NoOvernightState.CONFIRMED_FLAT,
            NoOvernightState.OVERNIGHT_BREACH,
        } and (transition_appended or projection.result_status is None):
            transition_planned_at = (
                plan.planned_at
                if transition_appended
                else projection.last_transition_planned_at
            )
            if transition_planned_at is None:
                raise ValueError("terminal result is missing transition evidence")
            result_appended = self._journal.append(
                no_overnight_result_record(
                    session_id=session_id,
                    account_scope_id=self._config.account_scope_id,
                    policy_family_id=self._config.policy_family_id,
                    session_date=session_date,
                    policy_version=self._config.policy_version,
                    policy_digest=self._config.policy_digest,
                    state=plan.state,
                    revision=plan.revision,
                    flat_proof_mode=plan.flat_proof_mode,
                    evidence=evidence,
                    transition_planned_at=transition_planned_at,
                    result_at=local_now,
                )
            )
        projection = rebuild_no_overnight_projection(
            self._journal,
            session_id=session_id,
            require_checkpoint=False,
        )
        if plan.state is NoOvernightState.OVERNIGHT_BREACH:
            if reconciliation_appended is None or projection.evidence is None:
                raise ValueError("breach is missing reconciliation evidence")
            evidence_changed = (
                projection.breach_id is None
                or projection.breach_evidence_through_journal_sequence
                != projection.evidence.snapshot_covers_through_journal_sequence
                or projection.breach_reconciliation_digest
                != projection.evidence.reconciliation_digest
            )
            if evidence_changed:
                first_revision = projection.breach_id is None
                latest_breach_proof = strict_flat_proof(projection.evidence)
                source_result_sequence = (
                    0
                    if not first_revision
                    else (
                        result_appended.sequence
                        if result_appended is not None
                        else projection.latest_result_journal_sequence or 0
                    )
                )
                breach_reason = (
                    _breach_reason_for(projection.evidence)
                    if first_revision
                    else projection.breach_reason
                )
                if breach_reason is None:
                    raise ValueError("originating breach reason is missing")
                breached = self._journal.append(
                    no_overnight_breach_record(
                        session_id=session_id,
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        originating_session_date=session_date,
                        policy_version=self._config.policy_version,
                        policy_digest=self._config.policy_digest,
                        breach_id=breach_id_for(
                            account_scope_id=self._config.account_scope_id,
                            policy_family_id=self._config.policy_family_id,
                            originating_session_date=session_date,
                        ),
                        breach_revision=projection.breach_revision + 1,
                        breach_reason=breach_reason,
                        revision_reason=(
                            breach_reason
                            if first_revision
                            else (
                                "STRICT_FLAT_REESTABLISHED"
                                if latest_breach_proof is not None
                                else "EVIDENCE_CHANGED"
                            )
                        ),
                        evidence=projection.evidence,
                        evidence_session_date=session_date,
                        evidence_reconciliation_journal_sequence=(
                            reconciliation_appended.sequence
                        ),
                        source_result_journal_sequence=source_result_sequence,
                        breached_at=local_now,
                    )
                )
                if not breached.idempotent:
                    _LOGGER.critical(
                        "no_overnight_breach",
                        extra={
                            "event": "NO_OVERNIGHT_BREACH",
                            "severity": "CRITICAL",
                            "account_scope_id": self._config.account_scope_id,
                            "policy_family_id": self._config.policy_family_id,
                            "session_date": session_date.isoformat(),
                            "breach_revision": projection.breach_revision + 1,
                        },
                    )
            projection = rebuild_no_overnight_projection(
                self._journal,
                session_id=session_id,
                require_checkpoint=False,
            )
            if (
                projection.breach_strict_flat_proof_mode is not None
                and not projection.breach_resolved
            ):
                if (
                    projection.breach_id is None
                    or projection.breach_reconciliation_digest is None
                ):
                    raise NoOvernightProjectionError(
                        "breach resolution identity is incomplete"
                    )
                self._journal.append(
                    no_overnight_breach_resolved_record(
                        session_id=session_id,
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        originating_session_date=session_date,
                        breach_id=projection.breach_id,
                        breach_revision=projection.breach_revision,
                        reconciliation_digest=(projection.breach_reconciliation_digest),
                        evidence_through_journal_sequence=(
                            projection.breach_evidence_through_journal_sequence
                        ),
                        evidence_snapshot_journal_sequence=(
                            projection.breach_evidence_snapshot_journal_sequence
                        ),
                        evidence_reconciliation_journal_sequence=(
                            projection.breach_evidence_reconciliation_journal_sequence
                        ),
                        strict_flat_proof_mode=(
                            projection.breach_strict_flat_proof_mode
                        ),
                        resolved_session_date=session_date,
                        resolved_at=local_now,
                    )
                )
        write_no_overnight_checkpoint(self._journal, session_id=session_id)
        projection = rebuild_no_overnight_projection(
            self._journal,
            session_id=session_id,
            require_checkpoint=True,
        )
        self._refresh_prior_breaches(
            current_projection=projection,
            evidence_reconciliation_journal_sequence=(
                None
                if reconciliation_appended is None
                else reconciliation_appended.sequence
            ),
            refreshed_at=local_now,
        )
        self._status = {
            "schema_version": "no_overnight_status_v1",
            "mode": self._config.mode.value,
            "enforcing": self._config.mode is NoOvernightMode.ENFORCING,
            "state": projection.state.value,
            "revision": projection.revision,
            "session_date": session_date.isoformat(),
            "policy_version": self._config.policy_version,
            "policy_digest": self._config.policy_digest,
            "deployment_manifest_digest": self._deployment_manifest_digest,
            "guard_identity": (
                self._guard.guard_identity if self._guard is not None else None
            ),
            "would_actions": [action.value for action in projection.would_actions],
            "flat_proof_mode": projection.flat_proof_mode,
            "result_status": projection.result_status,
            "reconciliation_status": projection.last_reconciliation_status,
            "reconciliation_digest": projection.last_reconciliation_digest,
            "last_execution_fact_journal_sequence": (
                projection.last_execution_fact_journal_sequence
            ),
            "snapshot_covers_through_journal_sequence": (
                0
                if projection.evidence is None
                else projection.evidence.snapshot_covers_through_journal_sequence
            ),
            "breach": self._global_breach_summary(session_date),
            "message": (
                "收盤風控執行中，會阻擋新當沖、取消進場餘量並集中平倉。"
                if self._config.mode is NoOvernightMode.ENFORCING
                else "收盤風控僅觀察，不會阻擋、取消或送出委託。"
            ),
        }
        return self.status()

    def _global_breach_summary(
        self,
        current_session_date: date,
    ) -> dict[str, object] | None:
        durable_breaches = _durable_breach_projections(
            journal=self._journal,
            config=self._config,
            current_session_date=current_session_date,
        )
        open_breaches = tuple(
            item
            for item in durable_breaches
            if not _breach_released(
                item,
                current_session_date=current_session_date,
                calendar=self._calendar,
            )
        )
        displayed = (
            open_breaches[0]
            if open_breaches
            else (durable_breaches[-1] if durable_breaches else None)
        )
        return (
            None
            if displayed is None
            else _breach_summary(
                displayed,
                current_session_date=current_session_date,
                calendar=self._calendar,
            )
        )

    def acknowledge_breach(
        self,
        *,
        breach_id: str,
        breach_revision: int,
        reconciliation_digest: str,
        actor_id: str,
        idempotency_key: str,
        acknowledged_at: datetime,
    ) -> dict[str, object]:
        if self._config.mode is not NoOvernightMode.ENFORCING:
            raise NoOvernightBreachConflict(
                "NOT_ENFORCING",
                "breach acknowledgement requires ENFORCING mode",
            )
        if (
            type(breach_id) is not str
            or not breach_id.strip()
            or type(actor_id) is not str
            or not actor_id.strip()
            or type(idempotency_key) is not str
            or not idempotency_key.strip()
        ):
            raise ValueError("breach acknowledgement identity is invalid")
        if type(breach_revision) is not int or breach_revision <= 0:
            raise ValueError("breach acknowledgement revision is invalid")
        if len(reconciliation_digest) != 64 or any(
            character not in "0123456789abcdef" for character in reconciliation_digest
        ):
            raise ValueError("breach acknowledgement digest is invalid")
        zone = ZoneInfo(self._config.timezone)
        if acknowledged_at.tzinfo is None or acknowledged_at.utcoffset() is None:
            raise ValueError("breach acknowledgement time must be timezone-aware")
        local_at = acknowledged_at.astimezone(zone)
        if local_at.replace(tzinfo=None) != acknowledged_at.replace(tzinfo=None):
            raise ValueError(
                "breach acknowledgement timezone differs from policy timezone"
            )
        if not self._calendar.is_trading_day(local_at.date()):
            raise ValueError("breach acknowledgement requires a reviewed session")
        assert self._guard is not None
        return self._guard.execute_if_owned(
            lambda: self._acknowledge_breach(
                breach_id=breach_id,
                breach_revision=breach_revision,
                reconciliation_digest=reconciliation_digest,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                acknowledged_at=local_at,
            )
        )

    def _acknowledge_breach(
        self,
        *,
        breach_id: str,
        breach_revision: int,
        reconciliation_digest: str,
        actor_id: str,
        idempotency_key: str,
        acknowledged_at: datetime,
    ) -> dict[str, object]:
        self._require_healthy_guard()
        matches = tuple(
            item
            for item in _durable_breach_projections(
                journal=self._journal,
                config=self._config,
                current_session_date=acknowledged_at.date(),
            )
            if item.breach_id == breach_id
        )
        if not matches:
            raise NoOvernightBreachConflict(
                "BREACH_NOT_FOUND",
                "durable breach was not found",
            )
        if len(matches) != 1:
            raise NoOvernightProjectionError("breach identity is duplicated")
        projection = matches[0]
        if breach_revision != projection.breach_revision:
            raise NoOvernightBreachConflict(
                "STALE_BREACH_REVISION",
                "breach revision is no longer current",
            )
        if reconciliation_digest != projection.breach_reconciliation_digest:
            raise NoOvernightBreachConflict(
                "STALE_RECONCILIATION_DIGEST",
                "breach reconciliation digest is no longer current",
            )
        if not projection.breach_resolved:
            raise NoOvernightBreachConflict(
                "BREACH_NOT_RESOLVED",
                "latest breach revision is not resolved",
            )
        if projection.breach_acknowledged:
            if (
                projection.breach_ack_idempotency_key == idempotency_key
                and projection.breach_ack_actor_id == actor_id
            ):
                result = _breach_summary(
                    projection,
                    current_session_date=acknowledged_at.date(),
                    calendar=self._calendar,
                )
                result["idempotent"] = True
                self._status["breach"] = self._global_breach_summary(
                    acknowledged_at.date()
                )
                return result
            raise NoOvernightBreachConflict(
                "BREACH_ALREADY_ACKNOWLEDGED",
                "latest breach revision is already acknowledged",
            )
        if projection.session_date is None:
            raise NoOvernightProjectionError("breach session identity is missing")
        record = no_overnight_breach_acknowledged_record(
            session_id=no_overnight_session_id(projection.session_date),
            account_scope_id=self._config.account_scope_id,
            policy_family_id=self._config.policy_family_id,
            originating_session_date=projection.session_date,
            breach_id=breach_id,
            breach_revision=breach_revision,
            reconciliation_digest=reconciliation_digest,
            actor_id=actor_id,
            resolution_journal_sequence=projection.breach_resolution_sequence,
            acknowledged_session_date=acknowledged_at.date(),
            acknowledged_at=acknowledged_at,
            idempotency_key=idempotency_key,
        )
        try:
            appended = self._journal.append(record)
        except JournalConflictError as error:
            raise NoOvernightBreachConflict(
                "IDEMPOTENCY_CONFLICT",
                "breach acknowledgement idempotency conflict",
            ) from error
        write_no_overnight_checkpoint(
            self._journal,
            session_id=no_overnight_session_id(projection.session_date),
        )
        recovered = rebuild_no_overnight_projection(
            self._journal,
            session_id=no_overnight_session_id(projection.session_date),
            require_checkpoint=True,
        )
        validate_breach_evidence_reference(self._journal, recovered)
        result = _breach_summary(
            recovered,
            current_session_date=acknowledged_at.date(),
            calendar=self._calendar,
        )
        result["idempotent"] = appended.idempotent
        self._status["breach"] = self._global_breach_summary(acknowledged_at.date())
        return result

    def _bootstrap_legacy_breaches(
        self,
        *,
        before_session_date: date,
    ) -> None:
        """Append the first G5 breach revision for trusted PR-NO-004 results."""

        for session in self._journal.sessions(
            session_id_prefix=NO_OVERNIGHT_SESSION_ID_PREFIX,
        ):
            raw_session_date = session.metadata.get("session_date")
            if type(raw_session_date) is not str:
                raise NoOvernightProjectionError(
                    "legacy breach session date is incomplete"
                )
            session_date = date.fromisoformat(raw_session_date)
            if session_date >= before_session_date:
                continue
            if session.session_id != no_overnight_session_id(session_date) or (
                session.metadata.get("account_scope_id")
                != self._config.account_scope_id
                or session.metadata.get("policy_family_id")
                != self._config.policy_family_id
            ):
                raise NoOvernightProjectionError(
                    "legacy breach session identity conflicts"
                )
            projection = rebuild_no_overnight_projection(
                self._journal,
                session_id=session.session_id,
                require_checkpoint=True,
            )
            if (
                projection.state is not NoOvernightState.OVERNIGHT_BREACH
                or projection.breach_id is not None
            ):
                continue
            if (
                projection.result_status != "CURRENT"
                or projection.latest_result_journal_sequence is None
                or projection.evidence is None
                or projection.last_reconciliation_journal_sequence <= 0
                or projection.last_reconciled_at is None
            ):
                raise NoOvernightProjectionError(
                    "legacy breach is missing trusted terminal evidence"
                )
            checkpoint = self._journal.latest_checkpoint(
                session.session_id,
                NO_OVERNIGHT_PROJECTION_NAME,
            )
            if checkpoint is None or checkpoint.journal_sequence < max(
                projection.latest_result_journal_sequence,
                projection.last_reconciliation_journal_sequence,
                projection.evidence.snapshot_journal_sequence,
            ):
                raise NoOvernightProjectionError(
                    "legacy breach evidence is not checkpointed"
                )
            records = {
                appended.sequence: appended
                for appended in self._journal.records(session.session_id)
            }
            result_record = records.get(projection.latest_result_journal_sequence)
            if (
                result_record is None
                or result_record.record.kind != NO_OVERNIGHT_RESULT_KIND
            ):
                raise NoOvernightProjectionError(
                    "legacy breach terminal result is missing"
                )
            breached_at = max(
                result_record.record.occurred_at,
                projection.evidence.snapshot_received_at,
                projection.last_reconciled_at,
            )
            breach_reason = _breach_reason_for(projection.evidence)
            policy_version, policy_digest = _historical_policy_identity(
                journal=self._journal,
                session_id=session.session_id,
                projection=projection,
            )
            appended = self._journal.append(
                no_overnight_breach_record(
                    session_id=session.session_id,
                    account_scope_id=self._config.account_scope_id,
                    policy_family_id=self._config.policy_family_id,
                    originating_session_date=session_date,
                    policy_version=policy_version,
                    policy_digest=policy_digest,
                    breach_id=breach_id_for(
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        originating_session_date=session_date,
                    ),
                    breach_revision=1,
                    breach_reason=breach_reason,
                    revision_reason=breach_reason,
                    evidence=projection.evidence,
                    evidence_session_date=session_date,
                    evidence_reconciliation_journal_sequence=(
                        projection.last_reconciliation_journal_sequence
                    ),
                    source_result_journal_sequence=(
                        projection.latest_result_journal_sequence
                    ),
                    breached_at=breached_at,
                )
            )
            write_no_overnight_checkpoint(
                self._journal,
                session_id=session.session_id,
            )
            rebuilt = rebuild_no_overnight_projection(
                self._journal,
                session_id=session.session_id,
                require_checkpoint=True,
            )
            validate_breach_evidence_reference(self._journal, rebuilt)
            if not appended.idempotent:
                _LOGGER.critical(
                    "no_overnight_legacy_breach_bootstrapped",
                    extra={
                        "event": "NO_OVERNIGHT_LEGACY_BREACH_BOOTSTRAPPED",
                        "severity": "CRITICAL",
                        "breach_id": rebuilt.breach_id,
                        "originating_session_date": session_date.isoformat(),
                    },
                )

    def _refresh_prior_breaches(
        self,
        *,
        current_projection: NoOvernightProjection,
        evidence_reconciliation_journal_sequence: int | None,
        refreshed_at: datetime,
    ) -> None:
        if current_projection.session_date is None:
            raise NoOvernightProjectionError(
                "current no-overnight session identity is missing"
            )
        prior = tuple(
            item
            for item in _durable_breach_projections(
                journal=self._journal,
                config=self._config,
                current_session_date=current_projection.session_date,
                before_session_date=current_projection.session_date,
            )
            if not _breach_released(
                item,
                current_session_date=current_projection.session_date,
                calendar=self._calendar,
            )
        )
        if not prior:
            return
        evidence = current_projection.evidence
        if evidence is None or evidence_reconciliation_journal_sequence is None:
            raise NoOvernightProjectionError(
                "prior breach refresh requires reconciled current evidence"
            )
        for existing in prior:
            if (
                existing.session_date is None
                or existing.breach_id is None
                or existing.breach_reason is None
            ):
                raise NoOvernightProjectionError("prior breach identity is incomplete")
            changed = (
                existing.breach_evidence_through_journal_sequence
                != evidence.snapshot_covers_through_journal_sequence
                or existing.breach_reconciliation_digest
                != evidence.reconciliation_digest
            )
            session_id = no_overnight_session_id(existing.session_date)
            projection = existing
            if changed:
                policy_version, policy_digest = _historical_policy_identity(
                    journal=self._journal,
                    session_id=session_id,
                    projection=existing,
                )
                proof = strict_flat_proof(evidence)
                appended = self._journal.append(
                    no_overnight_breach_record(
                        session_id=session_id,
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        originating_session_date=existing.session_date,
                        policy_version=policy_version,
                        policy_digest=policy_digest,
                        breach_id=existing.breach_id,
                        breach_revision=existing.breach_revision + 1,
                        breach_reason=existing.breach_reason,
                        revision_reason=(
                            "STRICT_FLAT_REESTABLISHED"
                            if proof is not None
                            else "EVIDENCE_CHANGED"
                        ),
                        evidence=evidence,
                        evidence_session_date=current_projection.session_date,
                        evidence_reconciliation_journal_sequence=(
                            evidence_reconciliation_journal_sequence
                        ),
                        source_result_journal_sequence=0,
                        breached_at=refreshed_at,
                    )
                )
                if not appended.idempotent:
                    _LOGGER.critical(
                        "no_overnight_breach_revised",
                        extra={
                            "event": "NO_OVERNIGHT_BREACH_REVISED",
                            "severity": "CRITICAL",
                            "breach_id": existing.breach_id,
                            "breach_revision": existing.breach_revision + 1,
                            "evidence_session_date": (
                                current_projection.session_date.isoformat()
                            ),
                        },
                    )
                write_no_overnight_checkpoint(
                    self._journal,
                    session_id=session_id,
                )
                projection = rebuild_no_overnight_projection(
                    self._journal,
                    session_id=session_id,
                    require_checkpoint=True,
                )
                validate_breach_evidence_reference(self._journal, projection)
            if (
                projection.breach_strict_flat_proof_mode is not None
                and not projection.breach_resolved
            ):
                if projection.breach_reconciliation_digest is None:
                    raise NoOvernightProjectionError(
                        "breach resolution digest is missing"
                    )
                self._journal.append(
                    no_overnight_breach_resolved_record(
                        session_id=session_id,
                        account_scope_id=self._config.account_scope_id,
                        policy_family_id=self._config.policy_family_id,
                        originating_session_date=projection.session_date,
                        breach_id=projection.breach_id or "",
                        breach_revision=projection.breach_revision,
                        reconciliation_digest=(projection.breach_reconciliation_digest),
                        evidence_through_journal_sequence=(
                            projection.breach_evidence_through_journal_sequence
                        ),
                        evidence_snapshot_journal_sequence=(
                            projection.breach_evidence_snapshot_journal_sequence
                        ),
                        evidence_reconciliation_journal_sequence=(
                            projection.breach_evidence_reconciliation_journal_sequence
                        ),
                        strict_flat_proof_mode=(
                            projection.breach_strict_flat_proof_mode
                        ),
                        resolved_session_date=current_projection.session_date,
                        resolved_at=refreshed_at,
                    )
                )
                write_no_overnight_checkpoint(
                    self._journal,
                    session_id=session_id,
                )

    def _read_evidence_bundle(
        self,
        *,
        now: datetime,
        session_date: date,
    ) -> NoOvernightEvidenceBundle:
        try:
            return self._evidence_reader.read(
                now=now,
                session_date=session_date,
            )
        except NoOvernightReconciliationRequired as error:
            return error.bundle

    def _require_healthy_guard(self) -> None:
        if self._config.mode is not NoOvernightMode.ENFORCING:
            return
        if self._guard is None or not self._guard.is_owned_and_healthy():
            raise ValueError("no-overnight guard ownership was lost")

    def _route_prior_session_execution_facts(
        self,
        facts: tuple[ExecutionFactReference, ...],
        *,
        current_session_date: date,
        observed_at: datetime,
    ) -> None:
        touched_session_ids: set[str] = set()
        for fact in facts:
            if fact.entry_session_date >= current_session_date:
                raise ValueError(
                    "prior-session execution fact has invalid session identity"
                )
            affected_date = fact.entry_session_date
            while affected_date < current_session_date:
                session_id = no_overnight_session_id(affected_date)
                if self._journal.session(session_id) is not None:
                    projection = rebuild_no_overnight_projection(
                        self._journal,
                        session_id=session_id,
                        require_checkpoint=True,
                    )
                    if (
                        fact.journal_sequence
                        > projection.last_execution_fact_journal_sequence
                    ):
                        self._journal.append(
                            execution_fact_observed_record(
                                session_id=session_id,
                                account_scope_id=self._config.account_scope_id,
                                policy_family_id=self._config.policy_family_id,
                                session_date=affected_date,
                                source_journal_sequence=fact.journal_sequence,
                                source_kind=fact.kind,
                                source_record_id=fact.record_id,
                                occurred_at=observed_at,
                            )
                        )
                        touched_session_ids.add(session_id)
                affected_date += timedelta(days=1)
        for session_id in sorted(touched_session_ids):
            write_no_overnight_checkpoint(self._journal, session_id=session_id)

    def _window(self, session_date: date) -> ReviewedSessionWindow:
        zone = ZoneInfo(self._config.timezone)
        return ReviewedSessionWindow(
            session_date=session_date,
            timezone=self._config.timezone,
            opens_at=datetime.combine(
                session_date,
                self._config.market_open,
                zone,
            ),
            closes_at=datetime.combine(
                session_date,
                self._config.reviewed_session_close,
                zone,
            ),
            calendar_schema_version=self._calendar.schema_version,
            calendar_digest=self._calendar.source_digest,
        )

    def _start_or_validate_session(
        self,
        session_id: str,
        window: ReviewedSessionWindow,
        now: datetime,
    ) -> None:
        metadata = {
            "account_scope_id": self._config.account_scope_id,
            "policy_family_id": self._config.policy_family_id,
            "session_date": window.session_date.isoformat(),
            "policy_version": self._config.policy_version,
            "policy_digest": self._config.policy_digest,
            "policy_schema_version": self._config.schema_version,
            "policy_validation_algorithm_version": (
                self._config.validation_algorithm_version
            ),
            "calendar_schema_version": window.calendar_schema_version,
            "calendar_digest": window.calendar_digest,
            "timezone": window.timezone,
            "mode": self._config.mode.value,
            "hosting_mode": self._config.controller_hosting_mode.value,
            "guard_kind": self._config.controller_guard_kind.value,
            "execution_boundary": (
                "ENFORCING_CENTRAL_MANAGED_FLATTEN_V1"
                if self._config.mode is NoOvernightMode.ENFORCING
                else "OBSERVE_ONLY_NO_COMMANDS"
            ),
        }
        if self._config.mode is NoOvernightMode.ENFORCING:
            metadata["deployment_manifest_digest"] = self._deployment_manifest_digest
            assert self._guard is not None
            metadata["guard_identity"] = self._guard.guard_identity
        existing = self._journal.session(session_id)
        if existing is None:
            self._journal.start_session(
                JournalSession(
                    session_id=session_id,
                    started_at=now,
                    mode=(
                        "NO_OVERNIGHT_ENFORCING"
                        if self._config.mode is NoOvernightMode.ENFORCING
                        else "NO_OVERNIGHT_OBSERVE_ONLY"
                    ),
                    metadata=metadata,
                )
            )
            write_no_overnight_checkpoint(self._journal, session_id=session_id)
            return
        expected_mode = (
            "NO_OVERNIGHT_ENFORCING"
            if self._config.mode is NoOvernightMode.ENFORCING
            else "NO_OVERNIGHT_OBSERVE_ONLY"
        )
        if existing.mode != expected_mode or dict(existing.metadata) != metadata:
            raise ValueError("no-overnight immutable session metadata conflicts")


class NoOvernightControllerWorker:
    """Own the B-mode polling loop independently from strategy lifecycle."""

    def __init__(
        self,
        *,
        controller: NoOvernightController,
        clock: Clock,
        on_failure: Callable[[], None],
        poll_seconds: float = NO_OVERNIGHT_CONTROLLER_POLL_SECONDS,
    ) -> None:
        if controller.config.mode is not NoOvernightMode.ENFORCING:
            raise ValueError("controller worker requires ENFORCING mode")
        if (
            type(poll_seconds) not in {int, float}
            or not isfinite(poll_seconds)
            or poll_seconds <= 0
        ):
            raise ValueError("controller poll_seconds must be positive")
        self._controller = controller
        self._clock = clock
        self._on_failure = on_failure
        self._poll_seconds = poll_seconds
        self._stop = Event()
        self._lock = RLock()
        self._thread: Thread | None = None
        self._last_error_type: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._last_error_type = None
            self._thread = Thread(
                target=self._run,
                name="no-overnight-controller",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is None:
            return
        thread.join(timeout=max(5.0, self._poll_seconds * 2))
        if thread.is_alive():
            raise RuntimeError("no-overnight controller worker did not stop")
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "poll_seconds": self._poll_seconds,
                "last_error_type": self._last_error_type,
            }

    def _run(self) -> None:
        while not self._stop.wait(self._poll_seconds):
            try:
                self._controller.run_once(self._clock.now())
            except Exception as error:
                with self._lock:
                    self._last_error_type = type(error).__name__
                _LOGGER.critical(
                    "no_overnight_worker_failed",
                    extra={
                        "event": "NO_OVERNIGHT_WORKER_FAILED",
                        "severity": "CRITICAL",
                        "error_type": type(error).__name__,
                    },
                )
                try:
                    self._on_failure()
                finally:
                    self._stop.set()
                return
