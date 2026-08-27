"""Journaled command facade for the local paper-simulation HTTP boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any, Protocol, TypeVar
from uuid import uuid4

from runtime.clock import Clock
from simulation.application_adapter import LocalPaperSimulationCommandAdapter
from simulation.service import (
    SimulationService,
    SimulationStateError,
    SimulationValidationError,
)
from simulation.settings import SETTINGS_SCHEMA_V2
from trading.application import (
    ApplicationStatus,
    CommandOutcomeRecorder,
    OrderApplicationService,
    order_command_from_record,
)
from trading.exposure import (
    AccountScopeIdentity,
    ExecutionReasonCategory,
    ExposureIdentity,
    HoldingHorizon,
    PolicyFamilyIdentity,
    PositionAction,
    build_exposure_identity,
    build_legacy_exposure_identity,
)
from trading.journal import JournalRecord, JournalRepository
from trading.no_overnight_admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionStatus,
)
from trading.local_paper import (
    LOCAL_PAPER_CANCEL_COMMAND_KIND,
    LOCAL_PAPER_REJECTION_KIND,
    LOCAL_PAPER_REJECTION_V2_KIND,
    LOCAL_PAPER_CANCEL_INTENT_V2_KIND,
    LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
    LocalPaperFillOutcomeRecorder,
    ProjectionRecoveryError,
    daily_baseline_record,
    latest_local_paper_order_states,
    write_local_paper_checkpoint,
    write_local_paper_v2_checkpoint,
)
from trading.risk import (
    COMMISSION_ROUNDING_TWD_DOWN,
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskGate,
    RiskPolicy,
    RiskSnapshot,
)


_T = TypeVar("_T")


class LocalPaperTerminalOutcomeRecorder(CommandOutcomeRecorder):
    """Persist fills and simulator-level rejections after a command is handled."""

    def __init__(self, *, settings_digest: str | None = None) -> None:
        self._fill_recorder = LocalPaperFillOutcomeRecorder(
            settings_digest=settings_digest
        )

    def records_for(
        self,
        command: OrderCommand,
        handler_result: Mapping[str, Any],
    ) -> tuple[JournalRecord, ...]:
        records = list(self._fill_recorder.records_for(command, handler_result))
        if handler_result.get("status") != "REJECTED":
            return tuple(records)
        order_id = str(handler_result["order_id"])
        occurred_at = datetime.fromisoformat(str(handler_result["updated_at"]))
        is_v2 = command.exposure is not None
        payload: dict[str, object] = {
            "command_id": command.command_id,
            "order_id": order_id,
            "idempotency_key": command.idempotency_key,
            "symbol": str(handler_result["symbol"]),
            "side": str(handler_result["side"]),
            "reason": str(handler_result.get("reason") or "SIMULATION_REJECTED"),
        }
        if is_v2:
            assert command.exposure is not None
            assert command.position_action is not None
            assert command.execution_reason_category is not None
            payload.update(
                {
                    "exposure_identity": command.exposure.to_payload(),
                    "position_action": command.position_action.value,
                    "target_exposure_id": command.target_exposure_id,
                    "execution_reason_category": (
                        command.execution_reason_category.value
                    ),
                    "execution_reason_code": command.execution_reason_code,
                }
            )
        records.append(
            JournalRecord(
                record_id=(
                    f"local-paper-rejection-v2:{order_id}"
                    if is_v2
                    else f"local-paper-rejection:{order_id}"
                ),
                session_id=command.session_id,
                kind=(
                    LOCAL_PAPER_REJECTION_V2_KIND
                    if is_v2
                    else LOCAL_PAPER_REJECTION_KIND
                ),
                occurred_at=occurred_at,
                payload=payload,
                idempotency_scope=f"{command.session_id}:local-paper-rejection",
                idempotency_key=order_id,
            )
        )
        return tuple(records)


class ExecutionAdmissionReader(Protocol):
    """Central and final no-overnight admission reader."""

    def read(
        self,
        command: OrderCommand,
        *,
        expected_revision: str | None = None,
    ) -> ExecutionAdmissionDecision: ...

    def execute_under_admission_fence(self, operation: Callable[[], _T]) -> _T: ...


class LocalPaperCommandService:
    """One journal-first command entrypoint for local-paper order lifecycle.

    This facade is intentionally local-only: it delegates approved commands to
    ``SimulationService`` and never exposes a broker-order or account port.
    """

    def __init__(
        self,
        *,
        simulation: SimulationService,
        journal: JournalRepository,
        session_id: str,
        clock: Clock,
        settings_digest: str | None = None,
        account_scope: AccountScopeIdentity | None = None,
        policy_family: PolicyFamilyIdentity | None = None,
        entry_policy_version: str | None = None,
        entry_policy_digest: str | None = None,
        manual_owner_id: str = "manual-web",
        execution_admission_reader: ExecutionAdmissionReader | None = None,
        durable_breach_reader: ExecutionAdmissionReader | None = None,
    ) -> None:
        self._simulation = simulation
        self._journal = journal
        self._session_id = session_id
        self._settings_digest = settings_digest
        self._clock = clock
        identity_values = (
            account_scope,
            policy_family,
            entry_policy_version,
            entry_policy_digest,
        )
        if any(value is not None for value in identity_values) and not all(
            value is not None for value in identity_values
        ):
            raise ValueError("Local Paper v2 identity context is incomplete")
        if (
            account_scope is not None
            and policy_family is not None
            and policy_family.account_scope_id != account_scope.account_scope_id
        ):
            raise ValueError("Local Paper v2 scope/family mismatch")
        if account_scope is not None and (
            settings_digest is None
            or simulation.settings.schema_version != SETTINGS_SCHEMA_V2
        ):
            raise ValueError("managed Local Paper requires settings v2 digest")
        self._account_scope = account_scope
        self._policy_family = policy_family
        self._entry_policy_version = entry_policy_version
        self._entry_policy_digest = entry_policy_digest
        self._manual_owner_id = self._normalize_key(manual_owner_id)
        self._execution_admission_reader = execution_admission_reader
        self._durable_breach_reader = durable_breach_reader
        if (
            execution_admission_reader is not None
            and durable_breach_reader is not None
        ):
            raise ValueError("execution and durable breach readers are mutually exclusive")
        self._lock = RLock()
        self._recovery_required_error: str | None = None
        self._runtime_handoff_suspended = False
        self._runtime_handoff_revoked = False
        self._commands_by_key: dict[str, OrderCommand] = {}
        self._cancel_results_by_key: dict[str, Mapping[str, object]] = {}
        self._unresolved_cancel_keys: set[str] = set()
        self._outcome_recorder = LocalPaperTerminalOutcomeRecorder(
            settings_digest=settings_digest
        )
        self._handler = LocalPaperSimulationCommandAdapter(simulation)
        self._base_risk_policy = RiskPolicy(
            version="local-paper-risk-v1",
            allow_strategy_origin=True,
            max_order_notional=simulation.starting_cash,
            max_position_notional=simulation.starting_cash,
            max_daily_loss=simulation.starting_cash,
            max_daily_buy_notional=simulation.max_daily_buy_notional,
            commission_rate=simulation.settings.commission_rate,
            minimum_commission=(
                simulation.settings.minimum_commission_twd
            ),
            commission_rounding_policy=(
                COMMISSION_ROUNDING_TWD_DOWN
                if simulation.settings.schema_version == SETTINGS_SCHEMA_V2
                else "ROUND_HALF_UP_0.01_TWD"
            ),
            require_fresh_book=simulation.requires_fresh_book,
            max_book_age_seconds=simulation.max_book_age_seconds,
            fresh_book_sides=frozenset({CommandSide.SELL}),
        )
        self._application = self._application_for_policy(self._base_risk_policy)
        self._strategy_applications: dict[
            str, tuple[RiskPolicy, OrderApplicationService]
        ] = {}
        self._restore_commands_from_journal()
        simulation.set_terminal_order_handler(self._record_later_terminal_order)
        simulation.set_daily_baseline_handler(self._record_daily_baseline)

    @property
    def session_id(self) -> str:
        """Expose the local process Journal session for diagnostics only."""
        return self._session_id

    def assert_mutation_allowed(self) -> None:
        """Fail before Journal mutation when durable recovery is required."""

        with self._lock:
            self._assert_mutation_allowed_locked()

    def prepare_runtime_handoff(self) -> None:
        """Quiesce this command authority before a reversible runtime swap."""

        with self._lock:
            self._assert_mutation_allowed_locked()
            self._runtime_handoff_suspended = True

    def rollback_runtime_handoff(self) -> None:
        """Restore this authority when the replacement did not commit."""

        with self._lock:
            if not self._runtime_handoff_revoked:
                self._runtime_handoff_suspended = False

    def finalize_runtime_handoff(self) -> None:
        """Permanently revoke stale references after durable activation."""

        with self._lock:
            self._runtime_handoff_revoked = True
            self._runtime_handoff_suspended = False

    def admit_automated_intent(
        self,
        operation: Callable[[], _T],
    ) -> _T:
        """Linearize runtime authority with one complete Journal mutation flow."""

        with self._lock:
            self._assert_mutation_allowed_locked()
            return operation()

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        quantity_shares: int | None = None,
        lots: int | None = None,
        holding_horizon: HoldingHorizon | str | None = None,
        target_exposure_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Record, risk-check, and apply one manual local-paper limit order."""
        return self._submit_order(
            symbol=symbol,
            side=side,
            quantity_shares=quantity_shares,
            lots=lots,
            limit_price=limit_price,
            idempotency_key=idempotency_key,
            command_id=uuid4().hex,
            origin=CommandOrigin.MANUAL_WEB,
            strategy_id=None,
            strategy_version=None,
            holding_horizon=holding_horizon,
            target_exposure_id=target_exposure_id,
            execution_reason_code="MANUAL_ORDER",
        )

    def submit_strategy_order(
        self,
        *,
        intent_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: str,
        limit_price: Decimal | float | int | str,
        quantity_shares: int | None = None,
        lots: int | None = None,
        holding_horizon: HoldingHorizon | str | None = None,
        target_exposure_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Apply one explicit strategy intent through the local-only path."""
        normalized_intent_id = self._normalize_key(intent_id)
        return self._submit_order(
            symbol=symbol,
            side=side,
            quantity_shares=quantity_shares,
            lots=lots,
            limit_price=limit_price,
            idempotency_key=f"strategy-paper:{normalized_intent_id}",
            command_id=f"strategy-paper-command:{normalized_intent_id}",
            origin=CommandOrigin.STRATEGY_AUTOMATED,
            strategy_id=self._normalize_key(strategy_id),
            strategy_version=self._normalize_key(strategy_version),
            holding_horizon=holding_horizon,
            target_exposure_id=target_exposure_id,
            execution_reason_code="STRATEGY_ORDER",
        )

    def submit_no_overnight_exit(
        self,
        *,
        exposure: ExposureIdentity,
        symbol: str,
        quantity_shares: int,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        owner_strategy_version: str | None,
    ) -> tuple[dict[str, Any], bool]:
        """Build one controller-owned risk-reducing CLOSE_LONG command."""

        if not isinstance(exposure, ExposureIdentity):
            raise SimulationValidationError("no-overnight exposure identity 格式錯誤")
        if not exposure.no_overnight_managed:
            raise SimulationValidationError("no-overnight 只能平 managed exposure")
        try:
            origin = CommandOrigin(exposure.owner_origin)
        except ValueError as error:
            raise SimulationValidationError(
                "no-overnight exposure owner 不支援"
            ) from error
        strategy_id = (
            exposure.owner_id
            if origin is CommandOrigin.STRATEGY_AUTOMATED
            else None
        )
        strategy_version = None
        if origin is CommandOrigin.STRATEGY_AUTOMATED:
            if type(owner_strategy_version) is not str:
                raise SimulationValidationError(
                    "no-overnight 自動 exposure 缺少 strategy version"
                )
            strategy_version = self._normalize_key(owner_strategy_version)
        elif owner_strategy_version is not None:
            raise SimulationValidationError(
                "no-overnight 手動 exposure 不可帶 strategy version"
            )
        normalized_key = self._normalize_key(idempotency_key)
        return self._submit_order(
            symbol=symbol,
            side=CommandSide.SELL.value,
            quantity_shares=quantity_shares,
            lots=None,
            limit_price=limit_price,
            idempotency_key=normalized_key,
            command_id=f"no-overnight-exit-command:{normalized_key}",
            origin=origin,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            target_exposure_id=exposure.exposure_id,
            exposure_override=exposure,
            execution_reason_code="NO_OVERNIGHT_EXIT",
        )

    def has_recorded_order_attempt(self, idempotency_key: str) -> bool:
        """Return whether an immutable command attempt already exists."""

        normalized_key = self._normalize_key(idempotency_key)
        with self._lock:
            return normalized_key in self._commands_by_key

    def prepare_strategy_risk_policy(
        self,
        *,
        owner_strategy_id: str,
        operator_max_daily_loss: Decimal | float | int | str,
    ) -> tuple[RiskPolicy, dict[str, Any]]:
        """Build the monotonic per-run policy without mutating runtime state."""

        owner = self._normalize_key(owner_strategy_id)
        operator_limit = self._normalize_price(operator_max_daily_loss)
        system_ceiling = self._base_risk_policy.max_daily_loss
        effective_limit = min(system_ceiling, operator_limit)
        policy = RiskPolicy(
            version="local-paper-risk-v1:effective-strategy-v1",
            allow_strategy_origin=self._base_risk_policy.allow_strategy_origin,
            max_order_notional=self._base_risk_policy.max_order_notional,
            max_position_notional=self._base_risk_policy.max_position_notional,
            max_daily_loss=effective_limit,
            max_daily_buy_notional=(
                self._base_risk_policy.max_daily_buy_notional
            ),
            commission_rate=self._base_risk_policy.commission_rate,
            minimum_commission=self._base_risk_policy.minimum_commission,
            commission_rounding_policy=(
                self._base_risk_policy.commission_rounding_policy
            ),
            require_fresh_book=self._base_risk_policy.require_fresh_book,
            max_book_age_seconds=self._base_risk_policy.max_book_age_seconds,
            fresh_book_sides=frozenset(CommandSide),
        )
        return policy, {
            "contract_version": "effective-local-paper-risk-v1",
            "owner_strategy_id": owner,
            "merge_rule": "MIN_SYSTEM_OPERATOR",
            "system_max_daily_loss": str(system_ceiling),
            "operator_max_daily_loss": str(operator_limit),
            "effective_max_daily_loss": str(effective_limit),
            "policy": policy.to_dict(),
            "effective_policy_digest": policy.policy_digest,
        }

    def activate_strategy_risk_policy(
        self,
        *,
        owner_strategy_id: str,
        policy: RiskPolicy,
    ) -> None:
        """Install an already-journaled effective policy for one exact owner."""

        owner = self._normalize_key(owner_strategy_id)
        with self._lock:
            self._assert_mutation_allowed_locked()
            self._strategy_applications[owner] = (
                policy,
                self._application_for_policy(policy),
            )

    def strategy_risk_policy(
        self,
        *,
        owner_strategy_id: str,
    ) -> dict[str, Any] | None:
        """Return the installed policy identity for diagnostics and recovery checks."""

        owner = self._normalize_key(owner_strategy_id)
        with self._lock:
            admitted = self._strategy_applications.get(owner)
            if admitted is None:
                return None
            policy = admitted[0]
            return {
                "owner_strategy_id": owner,
                "policy": policy.to_dict(),
                "effective_policy_digest": policy.policy_digest,
            }

    def prepare_strategy_entry_quote(
        self,
        *,
        owner_strategy_id: str,
        symbol: str,
    ) -> dict[str, Any]:
        """Acquire one bounded watch and report canonical BidAsk readiness."""

        owner = self._normalize_key(owner_strategy_id)
        with self._lock:
            admitted = self._strategy_applications.get(owner)
            if admitted is None:
                raise SimulationStateError(
                    "exact Strategy Set 尚未安裝 Effective Hard Risk Policy"
                )
            maximum_age = admitted[0].max_book_age_seconds
        self._simulation.watch_quote(owner_id=owner, symbol=symbol)
        return self._simulation.quote_watch_status(
            owner_id=owner,
            symbol=symbol,
            max_book_age_seconds=maximum_age,
        )

    def clear_strategy_entry_quote(self, *, owner_strategy_id: str) -> None:
        """Release the owner's pre-order watch; orders/positions remain subscribed."""

        self._simulation.clear_quote_watch(
            owner_id=self._normalize_key(owner_strategy_id)
        )

    def _submit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity_shares: int | None,
        lots: int | None,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        command_id: str,
        origin: CommandOrigin,
        strategy_id: str | None,
        strategy_version: str | None,
        holding_horizon: HoldingHorizon | str | None = None,
        target_exposure_id: str | None = None,
        exposure_override: ExposureIdentity | None = None,
        execution_reason_code: str = "STRATEGY_ORDER",
        attempt: int = 1,
        predecessor_order_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        def execute() -> tuple[dict[str, Any], bool]:
            return self._submit_order_locked(
                symbol=symbol,
                side=side,
                quantity_shares=quantity_shares,
                lots=lots,
                limit_price=limit_price,
                idempotency_key=idempotency_key,
                command_id=command_id,
                origin=origin,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                holding_horizon=holding_horizon,
                target_exposure_id=target_exposure_id,
                exposure_override=exposure_override,
                execution_reason_code=execution_reason_code,
                attempt=attempt,
                predecessor_order_id=predecessor_order_id,
            )

        admission_fence = (
            self._execution_admission_reader or self._durable_breach_reader
        )
        if admission_fence is None:
            return execute()
        return admission_fence.execute_under_admission_fence(execute)

    def _submit_order_locked(
        self,
        *,
        symbol: str,
        side: str,
        quantity_shares: int | None,
        lots: int | None,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        command_id: str,
        origin: CommandOrigin,
        strategy_id: str | None,
        strategy_version: str | None,
        holding_horizon: HoldingHorizon | str | None = None,
        target_exposure_id: str | None = None,
        exposure_override: ExposureIdentity | None = None,
        execution_reason_code: str = "STRATEGY_ORDER",
        attempt: int = 1,
        predecessor_order_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_quantity_shares = self._resolve_quantity_shares(
            quantity_shares=quantity_shares,
            lots=lots,
        )
        normalized_price = self._normalize_price(limit_price)
        normalized_key = self._normalize_key(idempotency_key)

        with self._lock:
            self._assert_mutation_allowed_locked()
            existing = self._simulation.order_for_idempotency_key(normalized_key)
            if existing is not None:
                return existing, True
            if normalized_key in self._commands_by_key:
                raise SimulationStateError(
                    "同一委託嘗試已有 Journal 證據，需先完成復原"
                )

            now = self._clock.now()
            exposure, action, resolved_target = self._resolve_exposure_intent(
                symbol=normalized_symbol,
                side=normalized_side,
                origin=origin,
                strategy_id=strategy_id,
                idempotency_key=normalized_key,
                requested_at=now,
                holding_horizon=holding_horizon,
                target_exposure_id=target_exposure_id,
                exposure_override=exposure_override,
            )
            command = OrderCommand(
                command_id=command_id,
                session_id=self._session_id,
                origin=origin,
                symbol=normalized_symbol,
                side=normalized_side,
                quantity_shares=normalized_quantity_shares,
                limit_price=normalized_price,
                idempotency_key=normalized_key,
                requested_at=now,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                attempt=attempt,
                predecessor_order_id=predecessor_order_id,
                exposure=exposure,
                position_action=action,
                target_exposure_id=resolved_target,
                execution_reason_category=(
                    ExecutionReasonCategory.STRATEGY
                    if exposure is not None
                    else None
                ),
                execution_reason_code=(
                    execution_reason_code if exposure is not None else None
                ),
            )
            if self._durable_breach_reader is not None:
                breach_admission = self._durable_breach_reader.read(command)
                if breach_admission.status is not ExecutionAdmissionStatus.APPROVED:
                    reasons = ",".join(
                        reason.value for reason in breach_admission.reasons
                    )
                    raise SimulationStateError(
                        f"No-Overnight durable breach blocks BUY admission: {reasons}"
                    )
            self._simulation.validate_order_admission(
                symbol=normalized_symbol,
                limit_price=normalized_price,
            )
            execution_admission = (
                self._execution_admission_reader.read(command)
                if self._execution_admission_reader is not None
                else None
            )
            self._commands_by_key[normalized_key] = command
            application = self._application
            if origin is CommandOrigin.STRATEGY_AUTOMATED and strategy_id is not None:
                admitted = self._strategy_applications.get(strategy_id)
                if (
                    strategy_id.startswith("atomic-set:")
                    and admitted is None
                    and execution_reason_code != "NO_OVERNIGHT_EXIT"
                ):
                    raise SimulationStateError(
                        "exact Strategy Set 尚未安裝 Effective Hard Risk Policy"
                    )
                if admitted is not None:
                    application = admitted[1]
            try:
                result = application.apply(
                    command,
                    self._risk_snapshot(
                        normalized_symbol,
                        normalized_side,
                        target_exposure_id=resolved_target,
                        reject_same_side_pending=(
                            origin is CommandOrigin.STRATEGY_AUTOMATED
                        ),
                        execution_admission=execution_admission,
                    ),
                    evaluated_at=now,
                    execution_admission=execution_admission,
                )
            except Exception as error:
                self._enter_recovery_required_locked(
                    f"command application failure: {type(error).__name__}"
                )
                raise
            if result.status is ApplicationStatus.APPLIED:
                assert result.handler_result is not None
                self._write_checkpoint()
                return dict(result.handler_result), False
            if (
                result.execution_admission is not None
                and result.execution_admission.status
                is not ExecutionAdmissionStatus.APPROVED
            ):
                return self._admission_block_payload(
                    command,
                    result.execution_admission,
                ), False
            if result.status in {ApplicationStatus.BLOCKED, ApplicationStatus.REJECTED}:
                try:
                    reason = ", ".join(
                        reason.value for reason in result.risk.reasons
                    )
                    order = self._simulation.record_risk_rejection(
                        command=command,
                        reason=f"風控拒絕：{reason}",
                    )
                    self._append_rejection_outcome(command, order)
                    self._write_checkpoint()
                except Exception as error:
                    self._enter_recovery_required_locked(
                        "rejection persistence failure: "
                        f"{type(error).__name__}"
                    )
                    raise
                return order, False
            self._enter_recovery_required_locked(
                f"command application ended in {result.status.value}"
            )
            raise SimulationStateError(
                "LOCAL_PAPER_RECOVERY_REQUIRED：委託稽核未完成，"
                "請勿重送並檢查本機 Journal"
            )

    def _resolve_exposure_intent(
        self,
        *,
        symbol: str,
        side: CommandSide,
        origin: CommandOrigin,
        strategy_id: str | None,
        idempotency_key: str,
        requested_at: datetime,
        holding_horizon: HoldingHorizon | str | None,
        target_exposure_id: str | None,
        exposure_override: ExposureIdentity | None,
    ) -> tuple[
        ExposureIdentity | None,
        PositionAction | None,
        str | None,
    ]:
        if self._account_scope is None or self._policy_family is None:
            if any(
                value is not None
                for value in (
                    holding_horizon,
                    target_exposure_id,
                    exposure_override,
                )
            ):
                raise SimulationValidationError(
                    "此 Local Paper session 尚未啟用 exposure identity v2"
                )
            return None, None, None

        owner_id = strategy_id or self._manual_owner_id
        if exposure_override is not None:
            exposure = exposure_override
        elif side is CommandSide.BUY:
            if (
                holding_horizon is None
                and origin is CommandOrigin.STRATEGY_AUTOMATED
            ):
                holding_horizon = HoldingHorizon.INTRADAY
            if holding_horizon is None:
                exposure = build_legacy_exposure_identity(
                    account_scope_id=self._account_scope.account_scope_id,
                    policy_family_id=self._policy_family.policy_family_id,
                    source_session_id=self._session_id,
                    symbol=symbol,
                    owner_origin=origin.value,
                    owner_id=owner_id,
                )
            else:
                try:
                    normalized_horizon = (
                        holding_horizon
                        if isinstance(holding_horizon, HoldingHorizon)
                        else HoldingHorizon(str(holding_horizon).strip().upper())
                    )
                except ValueError as error:
                    raise SimulationValidationError("holding_horizon 不支援") from error
                if normalized_horizon is HoldingHorizon.UNCLASSIFIED_LEGACY:
                    raise SimulationValidationError(
                        "新委託不可直接指定 UNCLASSIFIED_LEGACY"
                    )
                assert self._entry_policy_version is not None
                assert self._entry_policy_digest is not None
                exposure = build_exposure_identity(
                    account_scope_id=self._account_scope.account_scope_id,
                    policy_family_id=self._policy_family.policy_family_id,
                    owner_origin=origin.value,
                    owner_id=owner_id,
                    holding_horizon=normalized_horizon,
                    entry_session_date=requested_at.date(),
                    entry_policy_version=self._entry_policy_version,
                    entry_policy_digest=self._entry_policy_digest,
                    entry_identity=idempotency_key,
                )
        else:
            normalized_target = (
                self._normalize_key(target_exposure_id)
                if target_exposure_id is not None
                else None
            )
            candidates: list[ExposureIdentity] = []
            for raw in self._simulation.exposures():
                raw_identity = raw.get("exposure_identity")
                if not isinstance(raw_identity, Mapping):
                    raise SimulationStateError(
                        "模擬持倉缺少 exposure identity，禁止賣出"
                    )
                candidate = ExposureIdentity.from_payload(raw_identity)
                if str(raw.get("symbol")) != symbol:
                    continue
                if candidate.owner_origin != origin.value:
                    continue
                if (
                    origin is CommandOrigin.STRATEGY_AUTOMATED
                    and candidate.owner_id != strategy_id
                ):
                    continue
                if normalized_target is None or candidate.exposure_id == normalized_target:
                    candidates.append(candidate)
            if len(candidates) != 1:
                if normalized_target is not None:
                    raise SimulationValidationError(
                        "target_exposure_id 不存在或不屬於此委託 owner"
                    )
                if len(candidates) > 1:
                    raise SimulationValidationError(
                        "同股票有多個 exposure，SELL 必須指定 target_exposure_id"
                    )
                raise SimulationValidationError("找不到可賣出的 exposure")
            exposure = candidates[0]

        if exposure.account_scope_id != self._account_scope.account_scope_id:
            raise SimulationValidationError("exposure account scope mismatch")
        if exposure.policy_family_id != self._policy_family.policy_family_id:
            raise SimulationValidationError("exposure policy family mismatch")
        if exposure.owner_origin != origin.value or exposure.owner_id != owner_id:
            raise SimulationValidationError("exposure owner mismatch")
        if side is CommandSide.BUY:
            if target_exposure_id is not None:
                raise SimulationValidationError("BUY 不可指定 target_exposure_id")
            return exposure, PositionAction.OPEN_LONG, None
        return exposure, PositionAction.CLOSE_LONG, exposure.exposure_id

    def retry_order(
        self,
        order_id: str,
        idempotency_key: str,
        *,
        limit_price: Decimal | float | int | str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Create one bounded successor for the unfilled remainder."""

        with self._lock:
            source = next(
                (item for item in self._simulation.orders() if item["order_id"] == order_id),
                None,
            )
            if source is None:
                raise SimulationValidationError("找不到欲重試的委託")
            if source["status"] not in {"CANCELLED", "EXPIRED"}:
                raise SimulationStateError("只有已取消或到期委託可以重試")
            attempt = int(source.get("attempt") or 1) + 1
            if attempt > self._simulation.max_retry_attempts:
                raise SimulationStateError("委託重試次數已達上限")
            remaining = int(source.get("remaining_quantity") or 0)
            if remaining <= 0:
                raise SimulationStateError("委託沒有可安全重試的未成交餘量")
            normalized_key = self._normalize_key(idempotency_key)
            raw_exposure = source.get("exposure_identity")
            retry_exposure = (
                ExposureIdentity.from_payload(raw_exposure)
                if self._account_scope is not None
                and isinstance(raw_exposure, Mapping)
                else None
            )
            retry_values = {
                "symbol": str(source["symbol"]),
                "side": str(source["side"]),
                "quantity_shares": remaining,
                "lots": None,
                "limit_price": (
                    source["limit_price"] if limit_price is None else limit_price
                ),
                "idempotency_key": normalized_key,
                "command_id": (
                    f"local-paper-retry:{order_id}:{attempt}:{normalized_key}"
                ),
                "origin": CommandOrigin(str(source["origin"])),
                "strategy_id": (
                    str(source["strategy_id"])
                    if source.get("strategy_id") is not None
                    else None
                ),
                "strategy_version": (
                    str(source["strategy_version"])
                    if source.get("strategy_version") is not None
                    else None
                ),
                "target_exposure_id": (
                    str(source["target_exposure_id"])
                    if self._account_scope is not None
                    and source.get("target_exposure_id") is not None
                    else None
                ),
                "exposure_override": retry_exposure,
                "execution_reason_code": str(
                    source.get("execution_reason_code") or "RETRY_ORDER"
                ),
                "attempt": attempt,
                "predecessor_order_id": order_id,
            }
        return self._submit_order(
            **retry_values,
        )

    def _record_later_terminal_order(self, order: Mapping[str, Any]) -> None:
        """Append a fill/rejection produced by a later snapshot or BidAsk."""
        normalized_key = self._normalize_key(str(order.get("idempotency_key", "")))
        with self._lock:
            self._assert_mutation_allowed_locked()
            try:
                command = self._commands_by_key.get(normalized_key)
                if command is None:
                    raise SimulationStateError("找不到模擬終態對應的原始委託")
                records = self._outcome_recorder.records_for(command, order)
                if not records:
                    raise SimulationStateError("模擬終態沒有可寫入的成交或拒絕紀錄")
                for record in records:
                    self._journal.append(record)
                self._write_checkpoint()
            except Exception as error:
                self._enter_recovery_required_locked(
                    "terminal outcome persistence failure: "
                    f"{type(error).__name__}"
                )
                raise

    def _record_daily_baseline(self, baseline: Mapping[str, Any]) -> None:
        """Persist a newly frozen trading-day equity baseline outside sim lock."""
        with self._lock:
            self._assert_mutation_allowed_locked()
            try:
                self._journal.append(
                    daily_baseline_record(
                        session_id=self._session_id,
                        trading_date=str(baseline["trading_date"]),
                        opening_equity=str(baseline["opening_equity"]),
                        opening_realized_pnl=str(baseline["opening_realized_pnl"]),
                        occurred_at=datetime.fromisoformat(
                            str(baseline["created_at"])
                        ),
                    )
                )
                self._write_checkpoint()
            except Exception as error:
                self._enter_recovery_required_locked(
                    "daily baseline persistence failure: "
                    f"{type(error).__name__}"
                )
                raise

    def _restore_commands_from_journal(self) -> None:
        records = self._journal.records(self._session_id)
        try:
            latest_local_paper_order_states(
                self._journal,
                session_id=self._session_id,
            )
        except ProjectionRecoveryError as error:
            raise SimulationStateError(
                "restored order execution lineage is invalid"
            ) from error
        initial_admissions: dict[str, ExecutionAdmissionDecision] = {}
        for result in records:
            record = result.record
            if record.kind not in {"order_command.v1", "order_command.v2"}:
                continue
            command = order_command_from_record(record)
            if self._account_scope is not None and self._policy_family is not None:
                if command.exposure is None:
                    raise SimulationStateError(
                        "v2 Local Paper session contains a v1 order command"
                    )
                if (
                    command.exposure.account_scope_id
                    != self._account_scope.account_scope_id
                    or command.exposure.policy_family_id
                    != self._policy_family.policy_family_id
                ):
                    raise SimulationStateError(
                        "restored order command exposure identity mismatch"
                    )
            self._commands_by_key[command.idempotency_key] = command
            raw_admission = record.payload.get("no_overnight_admission")
            if raw_admission is not None:
                if not isinstance(raw_admission, Mapping):
                    raise SimulationStateError(
                        "restored command admission payload is invalid"
                    )
                initial_admissions[command.command_id] = (
                    ExecutionAdmissionDecision.from_payload(raw_admission)
                )
        for result in records:
            record = result.record
            if record.kind != "no_overnight_final_admission.v1":
                continue
            if set(record.payload) != {
                "command_id",
                "idempotency_key",
                "expected_admission_revision",
                "decision",
            }:
                raise SimulationStateError("final admission fields are invalid")
            command_id = record.payload["command_id"]
            idempotency_key = record.payload["idempotency_key"]
            expected_revision = record.payload["expected_admission_revision"]
            raw_decision = record.payload["decision"]
            if (
                type(command_id) is not str
                or type(idempotency_key) is not str
                or type(expected_revision) is not str
                or not isinstance(raw_decision, Mapping)
            ):
                raise SimulationStateError("final admission identity is invalid")
            command = self._commands_by_key.get(idempotency_key)
            initial = initial_admissions.get(command_id)
            final = ExecutionAdmissionDecision.from_payload(raw_decision)
            if (
                command is None
                or command.command_id != command_id
                or initial is None
                or initial.admission_revision != expected_revision
                or not final.final_check
                or (
                    final.status is ExecutionAdmissionStatus.APPROVED
                    and final.admission_revision != expected_revision
                )
            ):
                raise SimulationStateError("final admission lineage is invalid")
        intents: dict[str, Mapping[str, object]] = {}
        for result in records:
            record = result.record
            if record.kind not in {
                LOCAL_PAPER_CANCEL_INTENT_V2_KIND,
                LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
            }:
                continue
            payload = self._validated_v2_cancel_payload(
                record.payload,
                result=record.kind == LOCAL_PAPER_CANCEL_RESULT_V2_KIND,
            )
            cancel_key = str(payload["cancel_idempotency_key"])
            source_key = str(payload["source_order_idempotency_key"])
            command = self._commands_by_key.get(source_key)
            if command is None or command.exposure is None:
                raise SimulationStateError(
                    "v2 cancellation references an unknown source command"
                )
            if (
                payload["command_id"] != command.command_id
                or payload["symbol"] != command.symbol
                or payload["side"] != command.side.value
                or payload["exposure_identity"] != command.exposure.to_payload()
                or payload["position_action"] != command.position_action.value
                or payload["target_exposure_id"] != command.target_exposure_id
                or payload["order_attempt"] != command.attempt
                or payload["predecessor_order_id"] != command.predecessor_order_id
            ):
                raise SimulationStateError("v2 cancellation source identity mismatch")
            if record.kind == LOCAL_PAPER_CANCEL_INTENT_V2_KIND:
                if cancel_key in intents and intents[cancel_key] != payload:
                    raise SimulationStateError("v2 cancellation intent conflicts")
                intents[cancel_key] = payload
                continue
            intent = intents.get(cancel_key)
            if intent is None:
                raise SimulationStateError("v2 cancellation result is missing intent")
            comparable = {
                key: value
                for key, value in payload.items()
                if key
                not in {"status", "result_filled_quantity", "result_remaining_quantity"}
            }
            if comparable != intent:
                raise SimulationStateError("v2 cancellation result identity mismatch")
            self._cancel_results_by_key[cancel_key] = payload
        self._unresolved_cancel_keys = set(intents) - set(self._cancel_results_by_key)

    def cancel_order(
        self,
        order_id: str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """Journal the cancellation intent before mutating the local projection."""
        normalized_key = self._normalize_key(idempotency_key)
        with self._lock:
            self._assert_mutation_allowed_locked()
            recovered_result = self._cancel_results_by_key.get(normalized_key)
            if recovered_result is not None:
                recovered_order_id = str(recovered_result["order_id"])
                recovered = next(
                    (
                        item
                        for item in self._simulation.orders()
                        if item["order_id"] == recovered_order_id
                    ),
                    None,
                )
                if (
                    recovered is None
                    or recovered["status"] != "CANCELLED"
                    or recovered["filled_quantity"]
                    != recovered_result["result_filled_quantity"]
                    or recovered["remaining_quantity"]
                    != recovered_result["result_remaining_quantity"]
                ):
                    raise SimulationStateError(
                        "v2 cancellation result conflicts with restored simulator state"
                    )
                return recovered, True
            if normalized_key in self._unresolved_cancel_keys:
                raise SimulationStateError("取消委託稽核需要復原，請勿重送")
            existing = self._simulation.cancel_order_for_idempotency_key(normalized_key)
            if existing is not None:
                return existing, True
            pending = next(
                (item for item in self._simulation.orders() if item["order_id"] == order_id),
                None,
            )
            if pending is None:
                raise SimulationValidationError("找不到委託")
            if pending["status"] not in {"SUBMITTED", "PENDING", "PARTIALLY_FILLED"}:
                raise SimulationStateError("只有已送出的委託可以取消")
            command = self._commands_by_key.get(str(pending["idempotency_key"]))
            if command is None:
                raise SimulationStateError("找不到取消委託對應的原始命令")

            now = self._clock.now()
            is_v2 = command.exposure is not None
            intent_payload = (
                self._v2_cancel_identity_payload(
                    command=command,
                    order=pending,
                    cancel_idempotency_key=normalized_key,
                )
                if is_v2
                else {
                    "order_id": order_id,
                    "idempotency_key": normalized_key,
                }
            )
            intent = self._journal.append(
                JournalRecord(
                    record_id=(
                        f"local-paper-cancel-intent-v2:{normalized_key}"
                        if is_v2
                        else f"local-paper-cancel-command:{order_id}:{normalized_key}"
                    ),
                    session_id=self._session_id,
                    kind=(
                        LOCAL_PAPER_CANCEL_INTENT_V2_KIND
                        if is_v2
                        else "local_paper_cancel_command.v1"
                    ),
                    occurred_at=now,
                    payload=intent_payload,
                    idempotency_scope=(
                        f"{self._session_id}:local-paper-cancel-intent-v2"
                        if is_v2
                        else f"{self._session_id}:local-paper-cancel-command"
                    ),
                    idempotency_key=normalized_key,
                )
            )
            if intent.idempotent:
                raise SimulationStateError("取消委託稽核需要復原，請勿重送")
            order, _ = self._simulation.cancel_order(order_id, normalized_key)
            for record in self._outcome_recorder.records_for(command, order):
                self._journal.append(record)
            result_payload = (
                {
                    **intent_payload,
                    "status": str(order["status"]),
                    "result_filled_quantity": int(order["filled_quantity"]),
                    "result_remaining_quantity": int(order["remaining_quantity"]),
                }
                if is_v2
                else {
                    "order_id": order_id,
                    "symbol": str(order["symbol"]),
                    "side": str(order["side"]),
                }
            )
            self._journal.append(
                JournalRecord(
                    record_id=(
                        f"local-paper-cancel-result-v2:{normalized_key}"
                        if is_v2
                        else f"local-paper-cancellation:{order_id}"
                    ),
                    session_id=self._session_id,
                    kind=(
                        LOCAL_PAPER_CANCEL_RESULT_V2_KIND
                        if is_v2
                        else "local_paper_cancellation.v1"
                    ),
                    occurred_at=datetime.fromisoformat(str(order["updated_at"])),
                    payload=result_payload,
                    idempotency_scope=(
                        f"{self._session_id}:local-paper-cancel-result-v2"
                        if is_v2
                        else f"{self._session_id}:local-paper-cancellation"
                    ),
                    idempotency_key=normalized_key if is_v2 else order_id,
                )
            )
            if is_v2:
                self._cancel_results_by_key[normalized_key] = result_payload
            self._write_checkpoint()
            return order, False

    def _v2_cancel_identity_payload(
        self,
        *,
        command: OrderCommand,
        order: Mapping[str, Any],
        cancel_idempotency_key: str,
    ) -> dict[str, object]:
        if command.exposure is None or command.position_action is None:
            raise SimulationStateError("v2 cancellation source identity is incomplete")
        return {
            "account_scope_id": command.exposure.account_scope_id,
            "policy_family_id": command.exposure.policy_family_id,
            "order_id": str(order["order_id"]),
            "command_id": command.command_id,
            "source_order_idempotency_key": command.idempotency_key,
            "cancel_idempotency_key": cancel_idempotency_key,
            "symbol": command.symbol,
            "side": command.side.value,
            "exposure_identity": command.exposure.to_payload(),
            "position_action": command.position_action.value,
            "target_exposure_id": command.target_exposure_id,
            "original_quantity_shares": command.quantity_shares,
            "filled_quantity_at_intent": int(order["filled_quantity"]),
            "remaining_quantity_at_intent": int(order["remaining_quantity"]),
            "order_attempt": command.attempt,
            "predecessor_order_id": command.predecessor_order_id,
        }

    @staticmethod
    def _validated_v2_cancel_payload(
        payload: Mapping[str, object],
        *,
        result: bool,
    ) -> Mapping[str, object]:
        base_fields = {
            "account_scope_id",
            "policy_family_id",
            "order_id",
            "command_id",
            "source_order_idempotency_key",
            "cancel_idempotency_key",
            "symbol",
            "side",
            "exposure_identity",
            "position_action",
            "target_exposure_id",
            "original_quantity_shares",
            "filled_quantity_at_intent",
            "remaining_quantity_at_intent",
            "order_attempt",
            "predecessor_order_id",
        }
        expected = base_fields | (
            {"status", "result_filled_quantity", "result_remaining_quantity"}
            if result
            else set()
        )
        if set(payload) != expected:
            raise SimulationStateError("v2 cancellation fields are invalid")
        for field_name in (
            "account_scope_id",
            "policy_family_id",
            "order_id",
            "command_id",
            "source_order_idempotency_key",
            "cancel_idempotency_key",
            "symbol",
            "side",
            "position_action",
        ):
            if (
                type(payload[field_name]) is not str
                or not str(payload[field_name]).strip()
            ):
                raise SimulationStateError(f"v2 cancellation {field_name} is invalid")
        raw_exposure = payload["exposure_identity"]
        if not isinstance(raw_exposure, Mapping):
            raise SimulationStateError("v2 cancellation exposure is invalid")
        exposure = ExposureIdentity.from_payload(raw_exposure)
        numeric_fields = (
            "original_quantity_shares",
            "filled_quantity_at_intent",
            "remaining_quantity_at_intent",
            "order_attempt",
        ) + (("result_filled_quantity", "result_remaining_quantity") if result else ())
        for field_name in numeric_fields:
            value = payload[field_name]
            if type(value) is not int or value < 0:
                raise SimulationStateError(f"v2 cancellation {field_name} is invalid")
        if payload["original_quantity_shares"] <= 0 or payload["order_attempt"] <= 0:
            raise SimulationStateError("v2 cancellation quantity/attempt is invalid")
        if (
            payload["filled_quantity_at_intent"]
            + payload["remaining_quantity_at_intent"]
            != payload["original_quantity_shares"]
        ):
            raise SimulationStateError(
                "v2 cancellation intent quantity is inconsistent"
            )
        side = payload["side"]
        if side not in {"BUY", "SELL"}:
            raise SimulationStateError("v2 cancellation side is invalid")
        action_and_target_match = (
            payload["position_action"] == PositionAction.OPEN_LONG.value
            and payload["target_exposure_id"] is None
            if side == "BUY"
            else payload["position_action"] == PositionAction.CLOSE_LONG.value
            and payload["target_exposure_id"] == exposure.exposure_id
        )
        if (
            payload["account_scope_id"] != exposure.account_scope_id
            or payload["policy_family_id"] != exposure.policy_family_id
            or not action_and_target_match
        ):
            raise SimulationStateError(
                "v2 cancellation exposure identity is inconsistent"
            )
        if result and payload["status"] != "CANCELLED":
            raise SimulationStateError("v2 cancellation result must be CANCELLED")
        if result and (
            payload["result_filled_quantity"] != payload["filled_quantity_at_intent"]
            or payload["result_remaining_quantity"]
            != payload["remaining_quantity_at_intent"]
        ):
            raise SimulationStateError(
                "v2 cancellation result quantity is inconsistent"
            )
        for optional_field in ("target_exposure_id", "predecessor_order_id"):
            if (
                payload[optional_field] is not None
                and type(payload[optional_field]) is not str
            ):
                raise SimulationStateError(
                    f"v2 cancellation {optional_field} is invalid"
                )
        return dict(payload)

    def _write_checkpoint(self) -> None:
        """Persist a verified fill/accounting projection after a complete mutation."""

        try:
            write_local_paper_checkpoint(
                self._journal,
                session_id=self._session_id,
                starting_cash=self._simulation.starting_cash,
                settings_digest=self._settings_digest,
            )
            if self._account_scope is not None and self._policy_family is not None:
                write_local_paper_v2_checkpoint(
                    self._journal,
                    session_id=self._session_id,
                    starting_cash=self._simulation.starting_cash,
                    account_scope_id=self._account_scope.account_scope_id,
                    policy_family_id=self._policy_family.policy_family_id,
                    settings_digest=self._settings_digest,
                )
        except Exception as error:
            self._enter_recovery_required_locked(
                f"checkpoint failure: {type(error).__name__}"
            )
            raise SimulationStateError(
                "模擬交易已寫入 Journal，但投影 checkpoint 未完成，請勿重送"
            ) from error

    def _assert_mutation_allowed_locked(self) -> None:
        if self._runtime_handoff_revoked:
            raise SimulationStateError(
                "LOCAL_PAPER_RUNTIME_REPLACED：舊 runtime 已永久撤銷"
            )
        if self._runtime_handoff_suspended:
            raise SimulationStateError(
                "LOCAL_PAPER_RUNTIME_HANDOFF：runtime 切換期間禁止 mutation"
            )
        if self._recovery_required_error is not None:
            raise SimulationStateError(
                "LOCAL_PAPER_RECOVERY_REQUIRED："
                f"{self._recovery_required_error}"
            )

    def _enter_recovery_required_locked(self, reason: str) -> None:
        if self._recovery_required_error is None:
            self._recovery_required_error = reason
        self._simulation.mark_persistence_recovery_required(
            self._recovery_required_error
        )

    def _risk_snapshot(
        self,
        symbol: str,
        side: CommandSide,
        *,
        target_exposure_id: str | None = None,
        reject_same_side_pending: bool,
        execution_admission: ExecutionAdmissionDecision | None = None,
    ) -> RiskSnapshot:
        raw = self._simulation.risk_snapshot(
            symbol,
            target_exposure_id=target_exposure_id,
        )
        return RiskSnapshot(
            data_health_state=str(raw["data_health_state"]),
            market_open=(
                execution_admission.snapshot.session_open
                if execution_admission is not None
                else True
            ),
            instrument_tradable=(
                execution_admission.snapshot.instrument_tradable
                if execution_admission is not None
                else True
            ),
            available_cash=Decimal(raw["available_cash"]),
            current_position_shares=int(raw["current_position_shares"]),
            pending_buy_shares=int(raw["pending_buy_shares"]),
            pending_sell_shares=int(raw["pending_sell_shares"]),
            daily_realized_pnl=Decimal(raw["daily_realized_pnl"]),
            daily_filled_buy_notional=Decimal(
                raw["daily_filled_buy_notional"]
            ),
            pending_buy_notional=Decimal(raw["pending_buy_notional"]),
            same_side_pending_order=(
                reject_same_side_pending
                and (
                    int(raw["pending_buy_shares"]) > 0
                    if side is CommandSide.BUY
                    else int(raw["pending_sell_shares"]) > 0
                )
            ),
            book_age_seconds=raw["book_age_seconds"],
            daily_loss=Decimal(raw["daily_loss"]),
        )

    def _application_for_policy(
        self,
        policy: RiskPolicy,
    ) -> OrderApplicationService:
        return OrderApplicationService(
            journal=self._journal,
            risk_gate=RiskGate(policy),
            handler=self._handler,
            outcome_recorder=self._outcome_recorder,
            final_admission_reader=self._execution_admission_reader,
        )

    @staticmethod
    def _admission_block_payload(
        command: OrderCommand,
        decision: ExecutionAdmissionDecision,
    ) -> dict[str, Any]:
        return {
            "order_id": None,
            "command_id": command.command_id,
            "symbol": command.symbol,
            "side": command.side.value,
            "quantity_shares": command.quantity_shares,
            "quantity": command.quantity_shares,
            "status": decision.status.value,
            "reason": ", ".join(reason.value for reason in decision.reasons),
            "admission_reasons": [reason.value for reason in decision.reasons],
            "admission_revision": decision.admission_revision,
            "updated_at": decision.snapshot.evaluated_at.isoformat(),
        }

    def _append_rejection_outcome(
        self,
        command: OrderCommand,
        order: Mapping[str, Any],
    ) -> None:
        for record in self._outcome_recorder.records_for(command, order):
            self._journal.append(record)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()
        if not normalized:
            raise SimulationValidationError("請輸入股票代碼")
        return normalized

    @staticmethod
    def _normalize_side(side: str) -> CommandSide:
        try:
            return CommandSide(str(side).strip().upper())
        except ValueError as error:
            raise SimulationValidationError("交易方向只支援 BUY 或 SELL") from error

    @staticmethod
    def _normalize_lots(lots: int) -> int:
        if isinstance(lots, bool) or not isinstance(lots, int) or lots <= 0:
            raise SimulationValidationError("張數必須是大於 0 的整數")
        return lots

    @staticmethod
    def _normalize_quantity_shares(quantity_shares: int) -> int:
        if (
            isinstance(quantity_shares, bool)
            or not isinstance(quantity_shares, int)
            or quantity_shares <= 0
        ):
            raise SimulationValidationError("股數必須是大於 0 的整數")
        return quantity_shares

    @classmethod
    def _resolve_quantity_shares(
        cls,
        *,
        quantity_shares: int | None,
        lots: int | None,
    ) -> int:
        if quantity_shares is not None and lots is not None:
            raise SimulationValidationError("股數與張數不可同時提供")
        if quantity_shares is not None:
            return cls._normalize_quantity_shares(quantity_shares)
        if lots is not None:
            return cls._normalize_lots(lots) * 1_000
        raise SimulationValidationError("請輸入股數")

    @staticmethod
    def _normalize_price(limit_price: Decimal | float | int | str) -> Decimal:
        try:
            price = Decimal(str(limit_price))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise SimulationValidationError("限價必須是數字") from error
        if not price.is_finite() or price <= 0:
            raise SimulationValidationError("限價必須是大於 0 的有限數字")
        return price

    @staticmethod
    def _normalize_key(idempotency_key: str) -> str:
        normalized = str(idempotency_key).strip()
        if not normalized:
            raise SimulationValidationError("缺少冪等識別碼")
        if len(normalized) > 128:
            raise SimulationValidationError("冪等識別碼過長")
        return normalized
