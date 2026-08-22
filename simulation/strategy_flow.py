"""Versioned strategy intents for local-only paper trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from runtime.clock import TAIPEI, Clock
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationStateError, SimulationValidationError
from trading.canonical_values import canonical_decimal_string
from trading.journal import JournalConflictError, JournalRecord, JournalRepository
from trading.risk import CommandSide


STRATEGY_PAPER_INTENT_VERSION = "strategy-paper-intent-v1"
STRATEGY_PAPER_INTENT_KIND = "strategy_paper_intent.v1"


@dataclass(frozen=True)
class StrategyPaperIntent:
    """One auditable strategy decision that may create one local-paper order."""

    intent_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    side: CommandSide
    limit_price: Decimal
    signaled_at: datetime
    quantity_shares: int | None = None
    lots: int | None = None
    schema_version: str = STRATEGY_PAPER_INTENT_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.intent_id, "intent_id"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
            (self.symbol, "symbol"),
        ):
            if not value.strip():
                raise SimulationValidationError(f"{field_name} 不可為空")
        if len(self.intent_id) > 96:
            raise SimulationValidationError("intent_id 過長")
        if self.symbol != self.symbol.strip().upper():
            raise SimulationValidationError("股票代碼必須先正規化")
        if not isinstance(self.side, CommandSide):
            raise SimulationValidationError("交易方向只支援 BUY 或 SELL")
        if self.quantity_shares is not None and self.lots is not None:
            raise SimulationValidationError("股數與張數不可同時提供")
        if self.quantity_shares is not None:
            quantity_shares = self.quantity_shares
            if (
                isinstance(quantity_shares, bool)
                or not isinstance(quantity_shares, int)
                or quantity_shares <= 0
            ):
                raise SimulationValidationError("股數必須是大於 0 的整數")
        elif self.lots is not None:
            if (
                isinstance(self.lots, bool)
                or not isinstance(self.lots, int)
                or self.lots <= 0
            ):
                raise SimulationValidationError("張數必須是大於 0 的整數")
            quantity_shares = self.lots * 1_000
        else:
            raise SimulationValidationError("請輸入股數")
        object.__setattr__(self, "quantity_shares", quantity_shares)
        object.__setattr__(
            self,
            "lots",
            quantity_shares // 1_000 if quantity_shares % 1_000 == 0 else None,
        )
        if not self.limit_price.is_finite() or self.limit_price <= 0:
            raise SimulationValidationError("限價必須是大於 0 的有限數字")
        if self.signaled_at.tzinfo is None or self.signaled_at.utcoffset() is None:
            raise SimulationValidationError("signal_at 必須包含時區")
        if self.schema_version != STRATEGY_PAPER_INTENT_VERSION:
            raise SimulationValidationError("不支援的策略紙上意圖版本")

    @classmethod
    def create(
        cls,
        *,
        intent_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: str,
        limit_price: Decimal | float | int | str,
        signaled_at: datetime,
        quantity_shares: int | None = None,
        lots: int | None = None,
    ) -> "StrategyPaperIntent":
        try:
            normalized_side = CommandSide(str(side).strip().upper())
        except ValueError as error:
            raise SimulationValidationError("交易方向只支援 BUY 或 SELL") from error
        try:
            normalized_price = Decimal(str(limit_price))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise SimulationValidationError("限價必須是數字") from error
        return cls(
            intent_id=str(intent_id).strip(),
            strategy_id=str(strategy_id).strip(),
            strategy_version=str(strategy_version).strip(),
            symbol=str(symbol).strip().upper(),
            side=normalized_side,
            limit_price=normalized_price,
            signaled_at=signaled_at,
            quantity_shares=quantity_shares,
            lots=lots,
        )

    def journal_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "intent_id": self.intent_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "side": self.side.value,
            "lots": self.lots,
            "quantity_shares": self.quantity_shares,
            "limit_price": canonical_decimal_string(self.limit_price),
            "signaled_at": self.signaled_at.isoformat(),
            "execution_boundary": "LOCAL_ONLY",
        }


class StrategyPaperFlowService:
    """Journal one strategy intent, then route it through the shared paper path."""

    def __init__(
        self,
        *,
        commands: LocalPaperCommandService,
        journal: JournalRepository,
        session_id: str,
        clock: Clock,
    ) -> None:
        self._commands = commands
        self._journal = journal
        self._session_id = session_id
        self._clock = clock

    def submit(self, intent: StrategyPaperIntent) -> dict[str, Any]:
        if intent.signaled_at > self._clock.now():
            raise SimulationValidationError("策略訊號時間不可晚於目前時間")
        if intent.signaled_at.astimezone(TAIPEI).date() != self._clock.session_date():
            raise SimulationValidationError("策略訊號必須屬於目前本機模擬交易日")
        try:
            appended = self._journal.append(
                JournalRecord(
                    record_id=f"strategy-paper-intent:{intent.intent_id}",
                    session_id=self._session_id,
                    kind=STRATEGY_PAPER_INTENT_KIND,
                    occurred_at=intent.signaled_at,
                    payload=intent.journal_payload(),
                    idempotency_scope=f"{self._session_id}:strategy-paper-intent",
                    idempotency_key=intent.intent_id,
                )
            )
        except JournalConflictError as error:
            raise SimulationStateError("策略意圖識別碼與既有內容衝突") from error

        order, order_idempotent = self._commands.submit_strategy_order(
            intent_id=intent.intent_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            symbol=intent.symbol,
            side=intent.side.value,
            quantity_shares=intent.quantity_shares,
            limit_price=intent.limit_price,
        )
        return {
            "mode": "LOCAL_PAPER_SIMULATION",
            "session_id": self._session_id,
            "intent": intent.journal_payload(),
            "intent_sequence": appended.sequence,
            "intent_idempotent": appended.idempotent,
            "order_idempotent": order_idempotent,
            "order": order,
        }

    def cancel(self, order_id: str, idempotency_key: str) -> dict[str, Any]:
        """Cancel one local-paper order through the existing journal-first path."""

        order, idempotent = self._commands.cancel_order(order_id, idempotency_key)
        return {"order": order, "idempotent": idempotent}

    def retry(
        self,
        order_id: str,
        idempotency_key: str,
        *,
        limit_price: Decimal | float | int | str | None = None,
    ) -> dict[str, Any]:
        """Create one bounded successor order through the journal-first path."""

        order, idempotent = self._commands.retry_order(
            order_id,
            idempotency_key,
            limit_price=limit_price,
        )
        return {"order": order, "idempotent": idempotent}
