"""Journal-derived local-paper projection, kept separate from the legacy UI service."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
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
LOCAL_PAPER_ORDER_STATE_KIND = "local_paper_order_state.v1"
LOCAL_PAPER_DAILY_BASELINE_KIND = "local_paper_daily_baseline.v1"
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
    owner_origin: str = "MANUAL_WEB"
    owner_strategy_id: str | None = None
    owner_strategy_version: str | None = None

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
                owner_origin=str(record.payload.get("owner_origin", "MANUAL_WEB")),
                owner_strategy_id=(
                    str(record.payload["owner_strategy_id"])
                    if record.payload.get("owner_strategy_id") is not None
                    else None
                ),
                owner_strategy_version=(
                    str(record.payload["owner_strategy_version"])
                    if record.payload.get("owner_strategy_version") is not None
                    else None
                ),
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
    owner_origin: str = "MANUAL_WEB"
    owner_strategy_id: str | None = None
    owner_strategy_version: str | None = None


def journal_record_from_simulation_order(
    order: Mapping[str, object],
    *,
    session_id: str,
) -> JournalRecord | None:
    """Convert a legacy full-fill payload into one immutable Journal record."""

    status = str(order.get("status", ""))
    if status not in {"PARTIALLY_FILLED", "FILLED"}:
        return None
    try:
        order_id = str(order["order_id"])
        occurred_at = datetime.fromisoformat(str(order["updated_at"]))
        fill_sequence = int(order.get("fill_sequence") or 1)
        fill_quantity = int(
            order.get("last_fill_quantity") or order["filled_quantity"]
        )
        fill_price = Decimal(
            str(order.get("last_fill_price") or order["filled_price"])
        )
        fill = LocalPaperFill(
            order_id=order_id,
            symbol=str(order["symbol"]),
            name=str(order["name"]),
            side=LocalPaperSide(str(order["side"])),
            quantity_shares=fill_quantity,
            fill_price=fill_price,
            owner_origin=str(order.get("origin", "MANUAL_WEB")),
            owner_strategy_id=(
                str(order["strategy_id"])
                if order.get("strategy_id") is not None
                else None
            ),
            owner_strategy_version=(
                str(order["strategy_version"])
                if order.get("strategy_version") is not None
                else None
            ),
        )
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ProjectionRecoveryError("invalid simulation fill payload") from error
    provenance: dict[str, object] = {}
    provenance_fields = (
        "fill_source",
        "provider_identity",
        "execution_authority",
    )
    if any(field_name in order for field_name in provenance_fields):
        if not all(field_name in order for field_name in provenance_fields):
            raise ProjectionRecoveryError("incomplete simulation fill provenance")
        if not isinstance(order["execution_authority"], bool):
            raise ProjectionRecoveryError("invalid simulation execution authority")
        fill_source = str(order["fill_source"]).strip()
        provider_identity = str(order["provider_identity"]).strip()
        if not fill_source or not provider_identity:
            raise ProjectionRecoveryError("invalid simulation fill provenance")
        provenance = {
            "fill_source": fill_source,
            "provider_identity": provider_identity,
            "execution_authority": order["execution_authority"],
        }
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
            "fill_sequence": fill_sequence,
            "owner_origin": fill.owner_origin,
            "owner_strategy_id": fill.owner_strategy_id,
            "owner_strategy_version": fill.owner_strategy_version,
            **provenance,
        },
        idempotency_scope=f"{session_id}:legacy_simulation_fill",
        idempotency_key=(
            order_id if fill_sequence == 1 else f"{order_id}:{fill_sequence}"
        ),
    )


def order_state_record_from_simulation_order(
    order: Mapping[str, object],
    *,
    session_id: str,
) -> JournalRecord:
    """Persist one retry-stable simulator order-state snapshot."""

    order_id = str(order["order_id"])
    status = str(order["status"])
    updated_at = datetime.fromisoformat(str(order["updated_at"]))
    fill_sequence = int(order.get("fill_sequence") or 0)
    identity = f"{status}:{fill_sequence}:{updated_at.isoformat()}"
    payload_fields = (
        "order_id",
        "idempotency_key",
        "origin",
        "strategy_id",
        "strategy_version",
        "symbol",
        "name",
        "side",
        "lots",
        "quantity",
        "remaining_quantity",
        "limit_price",
        "status",
        "submitted_at",
        "updated_at",
        "filled_price",
        "filled_quantity",
        "filled_amount",
        "last_fill_price",
        "last_fill_quantity",
        "fill_sequence",
        "reason",
        "attempt",
        "predecessor_order_id",
        "timeout_at",
        "expires_at",
        "trading_date",
        "opening_equity",
    )
    return JournalRecord(
        record_id=f"local-paper-order-state:{order_id}:{identity}",
        session_id=session_id,
        kind=LOCAL_PAPER_ORDER_STATE_KIND,
        occurred_at=updated_at,
        payload={field: order.get(field) for field in payload_fields},
        idempotency_scope=f"{session_id}:local-paper-order-state",
        idempotency_key=f"{order_id}:{identity}",
    )


def daily_baseline_record(
    *,
    session_id: str,
    trading_date: date | str,
    opening_equity: Decimal | str,
    opening_realized_pnl: Decimal | str,
    occurred_at: datetime,
) -> JournalRecord:
    """Persist one immutable trading-day opening-equity risk baseline."""

    normalized_date = (
        trading_date if isinstance(trading_date, date) else date.fromisoformat(trading_date)
    )
    normalized_equity = Decimal(str(opening_equity))
    normalized_realized = Decimal(str(opening_realized_pnl))
    if normalized_equity <= 0 or not normalized_equity.is_finite():
        raise ValueError("opening_equity must be a positive finite value")
    if not normalized_realized.is_finite():
        raise ValueError("opening_realized_pnl must be finite")
    return JournalRecord(
        record_id=f"local-paper-daily-baseline:{normalized_date.isoformat()}",
        session_id=session_id,
        kind=LOCAL_PAPER_DAILY_BASELINE_KIND,
        occurred_at=occurred_at,
        payload={
            "trading_date": normalized_date.isoformat(),
            "opening_equity": str(normalized_equity),
            "opening_realized_pnl": str(normalized_realized),
            "includes_unrealized_pnl": True,
        },
        idempotency_scope=f"{session_id}:local-paper-daily-baseline",
        idempotency_key=normalized_date.isoformat(),
    )


class LocalPaperFillOutcomeRecorder:
    """Record every fill delta and every acknowledged simulator state."""

    def records_for(
        self,
        command: OrderCommand,
        handler_result: Mapping[str, object],
    ) -> tuple[JournalRecord, ...]:
        fill_record = journal_record_from_simulation_order(
            handler_result,
            session_id=command.session_id,
        )
        records: list[JournalRecord] = []
        if fill_record is not None:
            records.append(
                JournalRecord(
                    record_id=fill_record.record_id,
                    session_id=fill_record.session_id,
                    kind=fill_record.kind,
                    occurred_at=fill_record.occurred_at,
                    payload={
                        **fill_record.payload,
                        "command_id": command.command_id,
                        "command_idempotency_key": command.idempotency_key,
                    },
                    idempotency_scope=fill_record.idempotency_scope,
                    idempotency_key=fill_record.idempotency_key,
                )
            )
        records.append(
            order_state_record_from_simulation_order(
                handler_result,
                session_id=command.session_id,
            )
        )
        return tuple(records)


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

    @property
    def positions(self) -> tuple[LocalPaperPosition, ...]:
        return tuple(sorted(self._positions.values(), key=lambda item: item.symbol))

    @property
    def realized_pnl_by_symbol(self) -> Mapping[str, Decimal]:
        return dict(self._realized_pnl)

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
                    "owner_origin": position.owner_origin,
                    "owner_strategy_id": position.owner_strategy_id,
                    "owner_strategy_version": position.owner_strategy_version,
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
                    owner_origin=fill.owner_origin,
                    owner_strategy_id=fill.owner_strategy_id,
                    owner_strategy_version=fill.owner_strategy_version,
                )
            else:
                if (
                    current.owner_origin != fill.owner_origin
                    or current.owner_strategy_id != fill.owner_strategy_id
                ):
                    raise ProjectionRecoveryError("Journal fill ownership conflict")
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


def latest_local_paper_order_states(
    journal: JournalRepository,
    *,
    session_id: str,
) -> tuple[Mapping[str, object], ...]:
    """Return the latest durable state snapshot for every local-paper order."""

    latest: dict[str, Mapping[str, object]] = {}
    approved_commands: dict[str, JournalRecord] = {}
    for result in journal.records(session_id):
        if result.record.kind == "order_command.v1":
            if result.record.payload.get("risk_status") == "APPROVED":
                approved_commands[str(result.record.payload["idempotency_key"])] = (
                    result.record
                )
            continue
        if result.record.kind != LOCAL_PAPER_ORDER_STATE_KIND:
            continue
        order_id = str(result.record.payload.get("order_id") or "")
        if not order_id:
            raise ProjectionRecoveryError("order state record is missing order_id")
        latest[order_id] = result.record.payload
    represented_keys = {
        str(state.get("idempotency_key") or "") for state in latest.values()
    }
    for idempotency_key, command in approved_commands.items():
        if idempotency_key in represented_keys:
            continue
        payload = command.payload
        quantity = int(payload["quantity_shares"])
        latest[f"recovery-required:{payload['command_id']}"] = {
            "order_id": f"recovery-required:{payload['command_id']}",
            "idempotency_key": idempotency_key,
            "origin": payload["origin"],
            "strategy_id": payload.get("strategy_id"),
            "strategy_version": payload.get("strategy_version"),
            "symbol": payload["symbol"],
            "name": payload["symbol"],
            "side": payload["side"],
            "lots": quantity // 1_000,
            "quantity": quantity,
            "remaining_quantity": quantity,
            "limit_price": payload["limit_price"],
            "status": "RECOVERY_REQUIRED",
            "submitted_at": command.occurred_at.isoformat(),
            "updated_at": command.occurred_at.isoformat(),
            "filled_price": None,
            "filled_quantity": 0,
            "filled_amount": None,
            "last_fill_price": None,
            "last_fill_quantity": 0,
            "fill_sequence": 0,
            "reason": "COMMAND_ACKNOWLEDGEMENT_MISSING",
            "attempt": int(payload.get("attempt") or 1),
            "predecessor_order_id": payload.get("predecessor_order_id"),
            "timeout_at": None,
            "expires_at": None,
            "trading_date": None,
            "opening_equity": None,
        }
    return tuple(
        latest[order_id]
        for order_id in sorted(
            latest,
            key=lambda value: (
                str(latest[value].get("submitted_at") or ""),
                value,
            ),
        )
    )


def latest_local_paper_daily_baseline(
    journal: JournalRepository,
    *,
    session_id: str,
) -> Mapping[str, object] | None:
    """Return the most recently appended frozen daily risk baseline."""

    latest: Mapping[str, object] | None = None
    for result in journal.records(session_id):
        if result.record.kind != LOCAL_PAPER_DAILY_BASELINE_KIND:
            continue
        payload = result.record.payload
        try:
            date.fromisoformat(str(payload["trading_date"]))
            opening_equity = Decimal(str(payload["opening_equity"]))
            opening_realized_pnl = Decimal(str(payload["opening_realized_pnl"]))
        except (KeyError, ValueError, InvalidOperation) as error:
            raise ProjectionRecoveryError("daily baseline record is invalid") from error
        if opening_equity <= 0 or not opening_equity.is_finite():
            raise ProjectionRecoveryError("daily baseline opening equity is invalid")
        if not opening_realized_pnl.is_finite():
            raise ProjectionRecoveryError("daily baseline realized PnL is invalid")
        if payload.get("includes_unrealized_pnl") is not True:
            raise ProjectionRecoveryError("daily baseline PnL policy is not frozen")
        latest = payload
    return latest


def write_local_paper_checkpoint(
    journal: JournalRepository,
    *,
    session_id: str,
    starting_cash: Decimal,
) -> LocalPaperProjection:
    """Write one checkpoint after a full deterministic Journal replay.

    Replaying the complete session keeps intent/command/fill sequence handling
    correct while LOCAL_PAPER volume is bounded.  Persistence mode is still
    selected only by the composition root.
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
