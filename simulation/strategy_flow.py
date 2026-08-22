"""Versioned strategy intents for local-only paper trading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from runtime.clock import TAIPEI, Clock
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationStateError, SimulationValidationError
from trading.canonical_values import canonical_decimal_string
from trading.journal import (
    JournalAppendResult,
    JournalConflictError,
    JournalRecord,
    JournalRepository,
)
from trading.risk import CommandSide
from trading.risk import RiskPolicy
from strategy_catalog.parameter_schema import canonical_digest


STRATEGY_PAPER_INTENT_VERSION = "strategy-paper-intent-v1"
STRATEGY_PAPER_INTENT_KIND = "strategy_paper_intent.v1"
STRATEGY_RUNTIME_CHECKPOINT_KIND = "strategy_runtime_checkpoint.v1"


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
    decision_evidence: Mapping[str, Any] | None = None
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
        if self.decision_evidence is not None:
            object.__setattr__(self, "decision_evidence", dict(self.decision_evidence))

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
        decision_evidence: Mapping[str, Any] | None = None,
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
            decision_evidence=decision_evidence,
        )

    def journal_payload(self) -> dict[str, object]:
        payload = {
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
        if self.decision_evidence is not None:
            payload["decision_evidence"] = dict(self.decision_evidence)
        return payload


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

    def activate_run(
        self,
        *,
        owner_strategy_id: str,
        operator_max_daily_loss: Decimal,
        activation_config: Mapping[str, Any],
        actor_id: str,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        """Journal one exact-set activation before installing its Risk Policy."""

        policy, risk_evidence = self._commands.prepare_strategy_risk_policy(
            owner_strategy_id=owner_strategy_id,
            operator_max_daily_loss=operator_max_daily_loss,
        )
        payload = {
            "contract_version": "strategy-runtime-activation-v1",
            "owner_strategy_id": owner_strategy_id,
            "actor_id": actor_id,
            "idempotency_key": idempotency_key,
            "activation_config": dict(activation_config),
            "effective_risk": dict(risk_evidence),
        }
        record = JournalRecord(
            record_id=(
                f"strategy-runtime-activation:{owner_strategy_id}:"
                f"{idempotency_key}"
            ),
            session_id=self._session_id,
            kind="strategy_runtime_activation.v1",
            occurred_at=occurred_at,
            payload=payload,
            idempotency_scope=(
                f"{self._session_id}:strategy-runtime-activation:"
                f"{owner_strategy_id}"
            ),
            idempotency_key=idempotency_key,
        )
        try:
            existing = self._activation_record(
                owner_strategy_id=owner_strategy_id,
                idempotency_key=idempotency_key,
            )
            appended = (
                self._activation_replay(existing, record)
                if existing is not None
                else self._journal.append(record)
            )
        except JournalConflictError as error:
            existing = self._activation_record(
                owner_strategy_id=owner_strategy_id,
                idempotency_key=idempotency_key,
            )
            try:
                if existing is None:
                    raise error
                appended = self._activation_replay(existing, record)
            except JournalConflictError as replay_error:
                raise SimulationStateError(
                    "Local Paper activation 內容與既有紀錄衝突"
                ) from replay_error
        self._commands.activate_strategy_risk_policy(
            owner_strategy_id=owner_strategy_id,
            policy=policy,
        )
        return {
            **risk_evidence,
            "actor_id": actor_id,
            "activation_idempotency_key": idempotency_key,
            "activation_sequence": appended.sequence,
            "activation_idempotent": appended.idempotent,
        }

    def _activation_record(
        self,
        *,
        owner_strategy_id: str,
        idempotency_key: str,
    ) -> JournalAppendResult | None:
        scope = (
            f"{self._session_id}:strategy-runtime-activation:"
            f"{owner_strategy_id}"
        )
        return next(
            (
                item
                for item in self._journal.records(self._session_id)
                if item.record.idempotency_scope == scope
                and item.record.idempotency_key == idempotency_key
            ),
            None,
        )

    @staticmethod
    def _activation_replay(
        existing: JournalAppendResult,
        requested: JournalRecord,
    ) -> JournalAppendResult:
        if (
            existing.record.record_id != requested.record_id
            or existing.record.kind != requested.kind
            or existing.record.payload_json != requested.payload_json
        ):
            raise JournalConflictError(
                "Local Paper activation request conflicts with existing result"
            )
        return JournalAppendResult(
            record=existing.record,
            sequence=existing.sequence,
            idempotent=True,
        )

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

    def checkpoint(self, payload: Mapping[str, Any], *, occurred_at: datetime) -> None:
        """Persist a content-addressed controller checkpoint in the same Journal."""

        canonical = dict(payload)
        digest = canonical_digest(canonical)
        self._journal.append(
            JournalRecord(
                record_id=f"strategy-runtime-checkpoint:{digest}",
                session_id=self._session_id,
                kind=STRATEGY_RUNTIME_CHECKPOINT_KIND,
                occurred_at=occurred_at,
                payload={**canonical, "checkpoint_digest": digest},
                idempotency_scope=f"{self._session_id}:strategy-runtime-checkpoint",
                idempotency_key=digest,
            )
        )

    def latest_checkpoint(
        self,
        *,
        owner_strategy_id: str,
        pipeline_digest: str | None,
    ) -> Mapping[str, Any] | None:
        """Return the newest verified checkpoint for one exact runtime owner."""

        matches = []
        for stored in self._journal.records(self._session_id):
            record = stored.record
            if record.kind != STRATEGY_RUNTIME_CHECKPOINT_KIND:
                continue
            payload = json.loads(record.payload_json)
            saved_digest = str(payload.pop("checkpoint_digest", ""))
            if not saved_digest or canonical_digest(payload) != saved_digest:
                raise SimulationStateError("策略 runtime checkpoint digest 不一致")
            if payload.get("owner_strategy_id") != owner_strategy_id:
                continue
            if payload.get("pipeline_digest") != pipeline_digest:
                continue
            matches.append((stored.sequence, payload))
        return dict(max(matches, key=lambda item: item[0])[1]) if matches else None
