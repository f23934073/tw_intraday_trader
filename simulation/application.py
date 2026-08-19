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
from trading.local_paper import LocalPaperFillOutcomeRecorder
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
        fill_records = self._fill_recorder.records_for(command, handler_result)
        if fill_records:
            return fill_records
        if handler_result.get("status") != "REJECTED":
            return ()
        order_id = str(handler_result["order_id"])
        occurred_at = datetime.fromisoformat(str(handler_result["updated_at"]))
        return (
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
            ),
        )


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
        self._application = OrderApplicationService(
            journal=journal,
            risk_gate=RiskGate(
                RiskPolicy(
                    version="local-paper-risk-v1",
                    allow_strategy_origin=False,
                    max_order_notional=simulation.starting_cash,
                    max_position_notional=simulation.starting_cash,
                    max_daily_loss=simulation.starting_cash,
                )
            ),
            handler=LocalPaperSimulationCommandAdapter(simulation),
            outcome_recorder=LocalPaperTerminalOutcomeRecorder(),
        )

    @property
    def session_id(self) -> str:
        """Expose the local process Journal session for diagnostics only."""
        return self._session_id

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        lots: int,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """Record, risk-check, and apply one local-paper limit order."""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_lots = self._normalize_lots(lots)
        normalized_price = self._normalize_price(limit_price)
        normalized_key = self._normalize_key(idempotency_key)

        with self._lock:
            existing = self._simulation.order_for_idempotency_key(normalized_key)
            if existing is not None:
                return existing, True

            now = self._clock.now()
            command = OrderCommand(
                command_id=uuid4().hex,
                session_id=self._session_id,
                origin=CommandOrigin.MANUAL_WEB,
                symbol=normalized_symbol,
                side=normalized_side,
                quantity_shares=normalized_lots * 1_000,
                limit_price=normalized_price,
                idempotency_key=normalized_key,
                requested_at=now,
            )
            result = self._application.apply(
                command,
                self._risk_snapshot(normalized_symbol),
                evaluated_at=now,
            )
            if result.status is ApplicationStatus.APPLIED:
                assert result.handler_result is not None
                return dict(result.handler_result), False
            if result.status in {ApplicationStatus.BLOCKED, ApplicationStatus.REJECTED}:
                reason = ", ".join(reason.value for reason in result.risk.reasons)
                order = self._simulation.record_risk_rejection(
                    symbol=normalized_symbol,
                    side=normalized_side.value,
                    lots=normalized_lots,
                    limit_price=normalized_price,
                    idempotency_key=normalized_key,
                    reason=f"風控拒絕：{reason}",
                )
                self._append_rejection_outcome(command, order)
                return order, False
            raise SimulationStateError("委託稽核未完成，請勿重送並檢查本機 Journal")

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
            if pending["status"] != "SUBMITTED":
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
            return order, False

    def _risk_snapshot(self, symbol: str) -> RiskSnapshot:
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
            # Cash/share reservations allow independent pending limit orders.
            same_side_pending_order=False,
            book_age_seconds=raw["book_age_seconds"],
        )

    def _append_rejection_outcome(
        self,
        command: OrderCommand,
        order: Mapping[str, Any],
    ) -> None:
        self._journal.append(
            JournalRecord(
                record_id=f"local-paper-rejection:{order['order_id']}",
                session_id=self._session_id,
                kind="local_paper_rejection.v1",
                occurred_at=datetime.fromisoformat(str(order["updated_at"])),
                payload={
                    "command_id": command.command_id,
                    "order_id": str(order["order_id"]),
                    "symbol": str(order["symbol"]),
                    "side": str(order["side"]),
                    "reason": str(order.get("reason") or "RISK_REJECTED"),
                },
                idempotency_scope=f"{self._session_id}:local-paper-rejection",
                idempotency_key=str(order["order_id"]),
            )
        )

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
