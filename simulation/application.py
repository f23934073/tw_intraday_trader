"""Journaled command facade for the local paper-simulation HTTP boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any
from uuid import uuid4

from runtime.clock import Clock
from simulation.application_adapter import LocalPaperSimulationCommandAdapter
from simulation.service import (
    SimulationService,
    SimulationStateError,
    SimulationValidationError,
)
from trading.application import (
    ApplicationStatus,
    CommandOutcomeRecorder,
    OrderApplicationService,
)
from trading.journal import JournalRecord, JournalRepository
from trading.local_paper import (
    LocalPaperFillOutcomeRecorder,
    daily_baseline_record,
    write_local_paper_checkpoint,
)
from trading.risk import (
    CommandOrigin,
    CommandSide,
    OrderCommand,
    RiskGate,
    RiskPolicy,
    RiskSnapshot,
)


class LocalPaperTerminalOutcomeRecorder(CommandOutcomeRecorder):
    """Persist fills and simulator-level rejections after a command is handled."""

    def __init__(self) -> None:
        self._fill_recorder = LocalPaperFillOutcomeRecorder()

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
        records.append(
            JournalRecord(
                record_id=f"local-paper-rejection:{order_id}",
                session_id=command.session_id,
                kind="local_paper_rejection.v1",
                occurred_at=occurred_at,
                payload={
                    "command_id": command.command_id,
                    "order_id": order_id,
                    "symbol": str(handler_result["symbol"]),
                    "side": str(handler_result["side"]),
                    "reason": str(handler_result.get("reason") or "SIMULATION_REJECTED"),
                },
                idempotency_scope=f"{command.session_id}:local-paper-rejection",
                idempotency_key=order_id,
            )
        )
        return tuple(records)


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
    ) -> None:
        self._simulation = simulation
        self._journal = journal
        self._session_id = session_id
        self._clock = clock
        self._lock = RLock()
        self._commands_by_key: dict[str, OrderCommand] = {}
        self._outcome_recorder = LocalPaperTerminalOutcomeRecorder()
        self._handler = LocalPaperSimulationCommandAdapter(simulation)
        self._base_risk_policy = RiskPolicy(
            version="local-paper-risk-v1",
            allow_strategy_origin=True,
            max_order_notional=simulation.starting_cash,
            max_position_notional=simulation.starting_cash,
            max_daily_loss=simulation.starting_cash,
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

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        quantity_shares: int | None = None,
        lots: int | None = None,
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
        )

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
            allow_strategy_origin=(
                self._base_risk_policy.allow_strategy_origin and True
            ),
            max_order_notional=self._base_risk_policy.max_order_notional,
            max_position_notional=self._base_risk_policy.max_position_notional,
            max_daily_loss=effective_limit,
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
            self._strategy_applications[owner] = (
                policy,
                self._application_for_policy(policy),
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
            existing = self._simulation.order_for_idempotency_key(normalized_key)
            if existing is not None:
                return existing, True

            now = self._clock.now()
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
            )
            self._commands_by_key[normalized_key] = command
            application = self._application
            if origin is CommandOrigin.STRATEGY_AUTOMATED and strategy_id is not None:
                admitted = self._strategy_applications.get(strategy_id)
                if strategy_id.startswith("atomic-set:") and admitted is None:
                    raise SimulationStateError(
                        "exact Strategy Set 尚未安裝 Effective Hard Risk Policy"
                    )
                if admitted is not None:
                    application = admitted[1]
            result = application.apply(
                command,
                self._risk_snapshot(
                    normalized_symbol,
                    normalized_side,
                    reject_same_side_pending=(
                        origin is CommandOrigin.STRATEGY_AUTOMATED
                    ),
                ),
                evaluated_at=now,
            )
            if result.status is ApplicationStatus.APPLIED:
                assert result.handler_result is not None
                self._write_checkpoint()
                return dict(result.handler_result), False
            if result.status in {ApplicationStatus.BLOCKED, ApplicationStatus.REJECTED}:
                reason = ", ".join(reason.value for reason in result.risk.reasons)
                order = self._simulation.record_risk_rejection(
                    symbol=normalized_symbol,
                    side=normalized_side.value,
                    quantity_shares=normalized_quantity_shares,
                    limit_price=normalized_price,
                    idempotency_key=normalized_key,
                    reason=f"風控拒絕：{reason}",
                    origin=origin.value,
                )
                self._append_rejection_outcome(command, order)
                self._write_checkpoint()
                return order, False
            raise SimulationStateError("委託稽核未完成，請勿重送並檢查本機 Journal")

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
            return self._submit_order(
                symbol=str(source["symbol"]),
                side=str(source["side"]),
                quantity_shares=remaining,
                lots=None,
                limit_price=(source["limit_price"] if limit_price is None else limit_price),
                idempotency_key=normalized_key,
                command_id=f"local-paper-retry:{order_id}:{attempt}:{normalized_key}",
                origin=CommandOrigin(str(source["origin"])),
                strategy_id=(
                    str(source["strategy_id"])
                    if source.get("strategy_id") is not None
                    else None
                ),
                strategy_version=(
                    str(source["strategy_version"])
                    if source.get("strategy_version") is not None
                    else None
                ),
                attempt=attempt,
                predecessor_order_id=order_id,
            )

    def _record_later_terminal_order(self, order: Mapping[str, Any]) -> None:
        """Append a fill/rejection produced by a later snapshot or BidAsk."""
        normalized_key = self._normalize_key(str(order.get("idempotency_key", "")))
        with self._lock:
            command = self._commands_by_key.get(normalized_key)
            if command is None:
                raise SimulationStateError("找不到模擬終態對應的原始委託")
            records = self._outcome_recorder.records_for(command, order)
            if not records:
                raise SimulationStateError("模擬終態沒有可寫入的成交或拒絕紀錄")
            for record in records:
                self._journal.append(record)
            self._write_checkpoint()

    def _record_daily_baseline(self, baseline: Mapping[str, Any]) -> None:
        """Persist a newly frozen trading-day equity baseline outside sim lock."""
        with self._lock:
            self._journal.append(
                daily_baseline_record(
                    session_id=self._session_id,
                    trading_date=str(baseline["trading_date"]),
                    opening_equity=str(baseline["opening_equity"]),
                    opening_realized_pnl=str(baseline["opening_realized_pnl"]),
                    occurred_at=datetime.fromisoformat(str(baseline["created_at"])),
                )
            )
            self._write_checkpoint()

    def _restore_commands_from_journal(self) -> None:
        for result in self._journal.records(self._session_id):
            record = result.record
            if record.kind != "order_command.v1":
                continue
            payload = record.payload
            command = OrderCommand(
                command_id=str(payload["command_id"]),
                session_id=self._session_id,
                origin=CommandOrigin(str(payload["origin"])),
                symbol=str(payload["symbol"]),
                side=CommandSide(str(payload["side"])),
                quantity_shares=int(payload["quantity_shares"]),
                limit_price=Decimal(str(payload["limit_price"])),
                idempotency_key=str(payload["idempotency_key"]),
                requested_at=record.occurred_at,
                strategy_id=(
                    str(payload["strategy_id"])
                    if payload.get("strategy_id") is not None
                    else None
                ),
                strategy_version=(
                    str(payload["strategy_version"])
                    if payload.get("strategy_version") is not None
                    else None
                ),
                attempt=int(payload.get("attempt") or 1),
                predecessor_order_id=(
                    str(payload["predecessor_order_id"])
                    if payload.get("predecessor_order_id") is not None
                    else None
                ),
            )
            self._commands_by_key[command.idempotency_key] = command

    def cancel_order(
        self,
        order_id: str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """Journal the cancellation intent before mutating the local projection."""
        normalized_key = self._normalize_key(idempotency_key)
        with self._lock:
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

            now = self._clock.now()
            intent = self._journal.append(
                JournalRecord(
                    record_id=f"local-paper-cancel-command:{order_id}:{normalized_key}",
                    session_id=self._session_id,
                    kind="local_paper_cancel_command.v1",
                    occurred_at=now,
                    payload={
                        "order_id": order_id,
                        "idempotency_key": normalized_key,
                    },
                    idempotency_scope=f"{self._session_id}:local-paper-cancel-command",
                    idempotency_key=normalized_key,
                )
            )
            if intent.idempotent:
                raise SimulationStateError("取消委託稽核需要復原，請勿重送")
            order, _ = self._simulation.cancel_order(order_id, normalized_key)
            command = self._commands_by_key.get(str(pending["idempotency_key"]))
            if command is None:
                raise SimulationStateError("找不到取消委託對應的原始命令")
            for record in self._outcome_recorder.records_for(command, order):
                self._journal.append(record)
            self._journal.append(
                JournalRecord(
                    record_id=f"local-paper-cancellation:{order_id}",
                    session_id=self._session_id,
                    kind="local_paper_cancellation.v1",
                    occurred_at=datetime.fromisoformat(str(order["updated_at"])),
                    payload={
                        "order_id": order_id,
                        "symbol": str(order["symbol"]),
                        "side": str(order["side"]),
                    },
                    idempotency_scope=f"{self._session_id}:local-paper-cancellation",
                    idempotency_key=order_id,
                )
            )
            self._write_checkpoint()
            return order, False

    def _write_checkpoint(self) -> None:
        """Persist a verified fill/accounting projection after a complete mutation."""

        try:
            write_local_paper_checkpoint(
                self._journal,
                session_id=self._session_id,
                starting_cash=self._simulation.starting_cash,
            )
        except Exception as error:
            raise SimulationStateError(
                "模擬交易已寫入 Journal，但投影 checkpoint 未完成，請勿重送"
            ) from error

    def _risk_snapshot(
        self,
        symbol: str,
        side: CommandSide,
        *,
        reject_same_side_pending: bool,
    ) -> RiskSnapshot:
        raw = self._simulation.risk_snapshot(symbol)
        return RiskSnapshot(
            data_health_state=str(raw["data_health_state"]),
            # Local paper simulation has no exchange session gate; quote freshness
            # is enforced only when the streaming mode requires it.
            market_open=True,
            instrument_tradable=True,
            available_cash=Decimal(raw["available_cash"]),
            current_position_shares=int(raw["current_position_shares"]),
            pending_buy_shares=int(raw["pending_buy_shares"]),
            pending_sell_shares=int(raw["pending_sell_shares"]),
            daily_realized_pnl=Decimal(raw["daily_realized_pnl"]),
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
        )

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
