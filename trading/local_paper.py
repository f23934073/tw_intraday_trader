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
from trading.canonical_values import canonical_decimal_string
from trading.risk import OrderCommand


LOCAL_PAPER_FILL_KIND = "local_paper_fill.v1"
LOCAL_PAPER_FILL_V2_KIND = "local_paper_fill.v2"
LOCAL_PAPER_ORDER_STATE_KIND = "local_paper_order_state.v1"
LOCAL_PAPER_DAILY_BASELINE_KIND = "local_paper_daily_baseline.v1"
LOCAL_PAPER_SESSION_ARCHIVE_KIND = "local_paper_session_archive.v1"
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
    commission: Decimal = Decimal("0")
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
        if self.commission < 0:
            raise ValueError("commission must not be negative")

    @classmethod
    def from_record(cls, record: JournalRecord) -> "LocalPaperFill":
        if record.kind not in {LOCAL_PAPER_FILL_KIND, LOCAL_PAPER_FILL_V2_KIND}:
            raise ValueError("record is not a local-paper fill")
        try:
            fill = cls(
                order_id=str(record.payload["order_id"]),
                symbol=str(record.payload["symbol"]),
                name=str(record.payload["name"]),
                side=LocalPaperSide(str(record.payload["side"])),
                quantity_shares=int(record.payload["quantity_shares"]),
                fill_price=Decimal(str(record.payload["fill_price"])),
                commission=Decimal(str(record.payload.get("commission", "0"))),
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
            if record.kind == LOCAL_PAPER_FILL_V2_KIND:
                gross_notional = Decimal(str(record.payload["gross_notional"]))
                net_cash_effect = Decimal(str(record.payload["net_cash_effect"]))
                cumulative_commission = Decimal(
                    str(record.payload["cumulative_order_commission"])
                )
                settings_digest = str(record.payload["settings_digest"])
                expected_gross = fill.fill_price * fill.quantity_shares
                expected_net = (
                    -expected_gross - fill.commission
                    if fill.side is LocalPaperSide.BUY
                    else expected_gross - fill.commission
                )
                if (
                    gross_notional != expected_gross
                    or net_cash_effect != expected_net
                    or cumulative_commission < fill.commission
                    or len(settings_digest) != 64
                ):
                    raise ValueError("invalid local-paper v2 accounting evidence")
                int(settings_digest, 16)
            return fill
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
    commission_cost: Decimal = Decimal("0")
    owner_strategy_id: str | None = None
    owner_strategy_version: str | None = None


def journal_record_from_simulation_order(
    order: Mapping[str, object],
    *,
    session_id: str,
    settings_digest: str | None = None,
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
            commission=Decimal(str(order.get("last_fill_commission") or "0")),
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
    normalized_settings_digest: str | None = None
    if settings_digest is not None:
        normalized_settings_digest = str(settings_digest).strip().lower()
        try:
            if len(normalized_settings_digest) != 64:
                raise ValueError("settings digest must be SHA-256")
            int(normalized_settings_digest, 16)
        except ValueError as error:
            raise ProjectionRecoveryError("invalid settings digest") from error
    gross_notional = fill.quantity_shares * fill.fill_price
    cumulative_order_commission = Decimal(
        str(order.get("filled_commission") or "0")
    )
    if cumulative_order_commission < fill.commission:
        raise ProjectionRecoveryError("invalid cumulative order commission")
    net_cash_effect = (
        -gross_notional - fill.commission
        if fill.side is LocalPaperSide.BUY
        else gross_notional - fill.commission
    )
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
        kind=(
            LOCAL_PAPER_FILL_V2_KIND
            if normalized_settings_digest is not None
            else LOCAL_PAPER_FILL_KIND
        ),
        occurred_at=occurred_at,
        payload={
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "name": fill.name,
            "side": fill.side.value,
            "quantity_shares": fill.quantity_shares,
            "fill_price": str(fill.fill_price),
            **(
                {
                    "gross_notional": canonical_decimal_string(gross_notional),
                    "commission": canonical_decimal_string(fill.commission),
                    "net_cash_effect": canonical_decimal_string(net_cash_effect),
                    "cumulative_order_commission": canonical_decimal_string(
                        cumulative_order_commission
                    ),
                    "settings_digest": normalized_settings_digest,
                }
                if normalized_settings_digest is not None
                else {}
            ),
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
        "quantity_shares",
        "quantity",
        "remaining_quantity",
        "limit_price",
        "status",
        "submitted_at",
        "updated_at",
        "filled_price",
        "filled_quantity",
        "filled_amount",
        "filled_commission",
        "last_fill_price",
        "last_fill_quantity",
        "last_fill_commission",
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


def session_archive_record(
    *,
    session_id: str,
    replacement_session_id: str,
    replacement_settings_digest: str,
    active_order_count: int,
    position_count: int,
    occurred_at: datetime,
) -> JournalRecord:
    """Record the successful replacement of one local-paper session."""

    normalized_replacement = replacement_session_id.strip()
    normalized_digest = replacement_settings_digest.strip().lower()
    if not normalized_replacement:
        raise ValueError("replacement_session_id must not be empty")
    if active_order_count < 0 or position_count < 0:
        raise ValueError("archive counts must not be negative")
    try:
        if len(normalized_digest) != 64:
            raise ValueError("settings digest must be SHA-256")
        int(normalized_digest, 16)
    except ValueError as error:
        raise ValueError("replacement_settings_digest must be SHA-256") from error
    return JournalRecord(
        record_id=f"local-paper-session-archive:{normalized_replacement}",
        session_id=session_id,
        kind=LOCAL_PAPER_SESSION_ARCHIVE_KIND,
        occurred_at=occurred_at,
        payload={
            "status": "ARCHIVED",
            "replacement_session_id": normalized_replacement,
            "replacement_settings_digest": normalized_digest,
            "active_order_count": active_order_count,
            "position_count": position_count,
        },
        idempotency_scope=f"{session_id}:local-paper-session-archive",
        idempotency_key=normalized_replacement,
    )


class LocalPaperFillOutcomeRecorder:
    """Record every fill delta and every acknowledged simulator state."""

    def __init__(self, *, settings_digest: str | None = None) -> None:
        self._settings_digest = settings_digest

    def records_for(
        self,
        command: OrderCommand,
        handler_result: Mapping[str, object],
    ) -> tuple[JournalRecord, ...]:
        fill_record = journal_record_from_simulation_order(
            handler_result,
            session_id=command.session_id,
            settings_digest=self._settings_digest,
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

    def __init__(
        self,
        *,
        starting_cash: Decimal,
        settings_digest: str | None = None,
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        if settings_digest is not None:
            try:
                if len(settings_digest) != 64:
                    raise ValueError("settings digest must be SHA-256")
                int(settings_digest, 16)
            except ValueError as error:
                raise ValueError("settings_digest must be SHA-256") from error
        self._starting_cash = starting_cash
        self._settings_digest = settings_digest
        self._cash = starting_cash
        self._positions: dict[str, LocalPaperPosition] = {}
        self._realized_pnl: dict[str, Decimal] = {}
        self._buy_notional_by_date: dict[date, Decimal] = {}
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

    def buy_notional_for_date(self, trading_date: date) -> Decimal:
        return self._buy_notional_by_date.get(trading_date, Decimal("0"))

    @property
    def positions(self) -> tuple[LocalPaperPosition, ...]:
        return tuple(sorted(self._positions.values(), key=lambda item: item.symbol))

    @property
    def realized_pnl_by_symbol(self) -> Mapping[str, Decimal]:
        return dict(self._realized_pnl)

    def apply(self, result: JournalAppendResult) -> None:
        if result.sequence <= self._last_sequence:
            raise ProjectionRecoveryError("Journal sequence must be strictly increasing")
        if result.record.kind in {LOCAL_PAPER_FILL_KIND, LOCAL_PAPER_FILL_V2_KIND}:
            if self._settings_digest is not None and (
                result.record.kind != LOCAL_PAPER_FILL_V2_KIND
                or result.record.payload.get("settings_digest")
                != self._settings_digest
            ):
                raise ProjectionRecoveryError(
                    "Journal fill settings digest conflicts with session"
                )
            self._apply_fill(
                LocalPaperFill.from_record(result.record),
                occurred_at=result.record.occurred_at,
            )
        self._last_sequence = result.sequence

    @property
    def digest(self) -> str:
        payload = {
            "starting_cash": str(self._starting_cash),
            **(
                {"settings_digest": self._settings_digest}
                if self._settings_digest is not None
                else {}
            ),
            "cash": str(self._cash),
            "last_sequence": self._last_sequence,
            "positions": [
                {
                    "symbol": position.symbol,
                    "name": position.name,
                    "quantity_shares": position.quantity_shares,
                    "average_price": str(position.average_price),
                    **(
                        {"commission_cost": str(position.commission_cost)}
                        if position.commission_cost != 0
                        else {}
                    ),
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

    def _apply_fill(self, fill: LocalPaperFill, *, occurred_at: datetime) -> None:
        value = fill.quantity_shares * fill.fill_price
        current = self._positions.get(fill.symbol)
        if fill.side is LocalPaperSide.BUY:
            if value + fill.commission > self._cash:
                raise ProjectionRecoveryError("Journal fill exceeds available cash")
            if current is None:
                self._positions[fill.symbol] = LocalPaperPosition(
                    symbol=fill.symbol,
                    name=fill.name,
                    quantity_shares=fill.quantity_shares,
                    average_price=fill.fill_price,
                    owner_origin=fill.owner_origin,
                    commission_cost=fill.commission,
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
                    commission_cost=current.commission_cost + fill.commission,
                )
            self._cash -= value + fill.commission
            trading_date = occurred_at.date()
            self._buy_notional_by_date[trading_date] = (
                self._buy_notional_by_date.get(trading_date, Decimal("0"))
                + value
            )
            return

        if current is None or current.quantity_shares < fill.quantity_shares:
            raise ProjectionRecoveryError("Journal sell fill exceeds held quantity")
        allocated_buy_commission = (
            current.commission_cost * fill.quantity_shares / current.quantity_shares
        )
        self._cash += value - fill.commission
        self._realized_pnl[fill.symbol] = (
            self.realized_pnl(fill.symbol)
            + (fill.fill_price - current.average_price) * fill.quantity_shares
            - allocated_buy_commission
            - fill.commission
        )
        remaining = current.quantity_shares - fill.quantity_shares
        if remaining == 0:
            del self._positions[fill.symbol]
        else:
            self._positions[fill.symbol] = replace(
                current,
                quantity_shares=remaining,
                commission_cost=current.commission_cost - allocated_buy_commission,
            )


def rebuild_local_paper_projection(
    journal: JournalRepository,
    *,
    session_id: str,
    starting_cash: Decimal,
    settings_digest: str | None = None,
    require_checkpoint: bool = True,
) -> LocalPaperProjection:
    """Replay one session and fail closed when its checkpoint is untrustworthy."""

    checkpoint = journal.latest_checkpoint(session_id, LOCAL_PAPER_PROJECTION_NAME)
    if require_checkpoint and checkpoint is None:
        raise ProjectionRecoveryError("local-paper recovery requires a checkpoint")

    projection = LocalPaperProjection(
        starting_cash=starting_cash,
        settings_digest=settings_digest,
    )
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
            "lots": quantity // 1_000 if quantity % 1_000 == 0 else None,
            "quantity_shares": quantity,
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
    settings_digest: str | None = None,
) -> LocalPaperProjection:
    """Write one checkpoint after a full deterministic Journal replay.

    Replaying the complete session keeps intent/command/fill sequence handling
    correct while LOCAL_PAPER volume is bounded.  Persistence mode is still
    selected only by the composition root.
    """

    resolved_settings_digest = settings_digest
    if resolved_settings_digest is None:
        session = journal.session(session_id)
        if (
            session is not None
            and session.metadata.get("settings_schema") is not None
        ):
            resolved_settings_digest = str(
                session.metadata.get("settings_digest") or ""
            )
    projection = rebuild_local_paper_projection(
        journal,
        session_id=session_id,
        starting_cash=starting_cash,
        settings_digest=resolved_settings_digest,
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
