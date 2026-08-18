"""Journal-derived local-paper projection, kept separate from the legacy UI service."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from collections.abc import Mapping

from trading.journal import (
    JournalAppendResult,
    JournalRecord,
    JournalRepository,
    ProjectionCheckpoint,
)
from trading.risk import OrderCommand


LOCAL_PAPER_FILL_KIND = "local_paper_fill.v1"
LOCAL_PAPER_PROJECTION_NAME = "local_paper.v1"


class LocalPaperSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ProjectionRecoveryError(ValueError):
    """The Journal cannot prove a safe local-paper recovery."""


@dataclass(frozen=True)
class LocalPaperFill:
    order_id: str
    symbol: str
    name: str
    side: LocalPaperSide
    quantity_shares: int
    fill_price: Decimal

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("order_id must not be empty")
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.quantity_shares <= 0:
            raise ValueError("quantity_shares must be positive")
        if self.fill_price <= 0:
            raise ValueError("fill_price must be positive")

    @classmethod
    def from_record(cls, record: JournalRecord) -> "LocalPaperFill":
        if record.kind != LOCAL_PAPER_FILL_KIND:
            raise ValueError("record is not a local-paper fill")
        try:
            return cls(
                order_id=str(record.payload["order_id"]),
                symbol=str(record.payload["symbol"]),
                name=str(record.payload["name"]),
                side=LocalPaperSide(str(record.payload["side"])),
                quantity_shares=int(record.payload["quantity_shares"]),
                fill_price=Decimal(str(record.payload["fill_price"])),
            )
        except (InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError(
                f"invalid local-paper fill record {record.record_id}"
            ) from error


@dataclass(frozen=True)
class LocalPaperPosition:
    symbol: str
    name: str
    quantity_shares: int
    average_price: Decimal


def journal_record_from_simulation_order(
    order: Mapping[str, object],
    *,
    session_id: str,
) -> JournalRecord | None:
    """Convert a legacy full-fill payload into one immutable Journal record."""

    if str(order.get("status", "")) != "FILLED":
        return None
    try:
        order_id = str(order["order_id"])
        occurred_at = datetime.fromisoformat(str(order["updated_at"]))
        fill = LocalPaperFill(
            order_id=order_id,
            symbol=str(order["symbol"]),
            name=str(order["name"]),
            side=LocalPaperSide(str(order["side"])),
            quantity_shares=int(order["filled_quantity"]),
            fill_price=Decimal(str(order["filled_price"])),
        )
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ProjectionRecoveryError("invalid simulation fill payload") from error
    return JournalRecord(
        record_id=f"local-paper-fill:{order_id}:{occurred_at.isoformat()}",
        session_id=session_id,
        kind=LOCAL_PAPER_FILL_KIND,
        occurred_at=occurred_at,
        payload={
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "name": fill.name,
            "side": fill.side.value,
            "quantity_shares": fill.quantity_shares,
            "fill_price": str(fill.fill_price),
        },
        idempotency_scope=f"{session_id}:legacy_simulation_fill",
        idempotency_key=order_id,
    )


class LocalPaperFillOutcomeRecorder:
    """Records only completed legacy local-paper fills after acknowledgement."""

    def records_for(
        self,
        command: OrderCommand,
        handler_result: Mapping[str, object],
    ) -> tuple[JournalRecord, ...]:
        record = journal_record_from_simulation_order(
            handler_result,
            session_id=command.session_id,
        )
        if record is None:
            return ()
        return (
            JournalRecord(
                record_id=record.record_id,
                session_id=record.session_id,
                kind=record.kind,
                occurred_at=record.occurred_at,
                payload={
                    **record.payload,
                    "command_id": command.command_id,
                    "command_idempotency_key": command.idempotency_key,
                },
                idempotency_scope=record.idempotency_scope,
                idempotency_key=record.idempotency_key,
            ),
        )


class LocalPaperProjection:
    """Pure reducer for append-order Journal results.

    This intentionally does not call providers, brokers, or the existing
    ``SimulationService``.  It is the recovery/parity target before any UI
    cutover.
    """

    def __init__(self, *, starting_cash: Decimal) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._positions: dict[str, LocalPaperPosition] = {}
        self._realized_pnl: dict[str, Decimal] = {}
        self._last_sequence = 0

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def position(self, symbol: str) -> LocalPaperPosition | None:
        return self._positions.get(symbol)

    def realized_pnl(self, symbol: str) -> Decimal:
        return self._realized_pnl.get(symbol, Decimal("0"))

    def apply(self, result: JournalAppendResult) -> None:
        if result.sequence <= self._last_sequence:
            raise ProjectionRecoveryError("Journal sequence must be strictly increasing")
        if result.record.kind == LOCAL_PAPER_FILL_KIND:
            self._apply_fill(LocalPaperFill.from_record(result.record))
        self._last_sequence = result.sequence

    @property
    def digest(self) -> str:
        payload = {
            "starting_cash": str(self._starting_cash),
            "cash": str(self._cash),
            "last_sequence": self._last_sequence,
            "positions": [
                {
                    "symbol": position.symbol,
                    "name": position.name,
                    "quantity_shares": position.quantity_shares,
                    "average_price": str(position.average_price),
                }
                for position in sorted(self._positions.values(), key=lambda item: item.symbol)
            ],
            "realized_pnl": {
                symbol: str(value)
                for symbol, value in sorted(self._realized_pnl.items())
            },
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _apply_fill(self, fill: LocalPaperFill) -> None:
        value = fill.quantity_shares * fill.fill_price
        current = self._positions.get(fill.symbol)
        if fill.side is LocalPaperSide.BUY:
            if value > self._cash:
                raise ProjectionRecoveryError("Journal fill exceeds available cash")
            if current is None:
                self._positions[fill.symbol] = LocalPaperPosition(
                    symbol=fill.symbol,
                    name=fill.name,
                    quantity_shares=fill.quantity_shares,
                    average_price=fill.fill_price,
                )
            else:
                quantity = current.quantity_shares + fill.quantity_shares
                self._positions[fill.symbol] = replace(
                    current,
                    quantity_shares=quantity,
                    average_price=(
                        current.average_price * current.quantity_shares + value
                    ) / quantity,
                )
            self._cash -= value
            return

        if current is None or current.quantity_shares < fill.quantity_shares:
            raise ProjectionRecoveryError("Journal sell fill exceeds held quantity")
        self._cash += value
        self._realized_pnl[fill.symbol] = self.realized_pnl(fill.symbol) + (
            fill.fill_price - current.average_price
        ) * fill.quantity_shares
        remaining = current.quantity_shares - fill.quantity_shares
        if remaining == 0:
            del self._positions[fill.symbol]
        else:
            self._positions[fill.symbol] = replace(current, quantity_shares=remaining)


def rebuild_local_paper_projection(
    journal: JournalRepository,
    *,
    session_id: str,
    starting_cash: Decimal,
    require_checkpoint: bool = True,
) -> LocalPaperProjection:
    """Replay one session and fail closed when its checkpoint is untrustworthy."""

    checkpoint = journal.latest_checkpoint(session_id, LOCAL_PAPER_PROJECTION_NAME)
    if require_checkpoint and checkpoint is None:
        raise ProjectionRecoveryError("local-paper recovery requires a checkpoint")

    projection = LocalPaperProjection(starting_cash=starting_cash)
    checkpoint_digest = projection.digest if checkpoint and checkpoint.journal_sequence == 0 else None
    for result in journal.records(session_id):
        projection.apply(result)
        if checkpoint is not None and result.sequence == checkpoint.journal_sequence:
            checkpoint_digest = projection.digest

    if checkpoint is not None:
        if checkpoint_digest is None:
            raise ProjectionRecoveryError("checkpoint sequence is absent from Journal")
        if checkpoint_digest != checkpoint.digest:
            raise ProjectionRecoveryError("local-paper checkpoint digest mismatch")
    return projection


def write_local_paper_checkpoint(
    journal: JournalRepository,
    *,
    session_id: str,
    starting_cash: Decimal,
) -> LocalPaperProjection:
    """Write one administrative checkpoint after a full deterministic replay.

    The caller invokes this explicitly for recovery administration.  It does
    not run in a Dashboard request and does not establish a persistence mode.
    """

    projection = rebuild_local_paper_projection(
        journal,
        session_id=session_id,
        starting_cash=starting_cash,
        require_checkpoint=False,
    )
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=session_id,
            projection_name=LOCAL_PAPER_PROJECTION_NAME,
            journal_sequence=projection.last_sequence,
            digest=projection.digest,
        )
    )
    return projection
