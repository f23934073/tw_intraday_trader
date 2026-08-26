"""Journal-derived local-paper projection, kept separate from the legacy UI service."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import StrEnum
from collections.abc import Mapping

from market_data.models import (
    LocalPaperInstrumentDescriptorV1,
    LocalPaperProductClass,
)
from simulation.execution_costs import (
    FEE_POLICY_VERSION,
    MONEY_QUANTUM,
    PRICE_TICK_POLICY_VERSION,
    ROUNDING_POLICY_VERSION,
    SELL_TAX_RATE,
    SLIPPAGE_POLICY_VERSION,
    ReferenceSource,
    cumulative_commission_for,
    decide_fixed_adverse_slippage,
    is_valid_common_stock_tick,
)
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
LOCAL_PAPER_FILL_V3_KIND = "local_paper_fill.v3"
LOCAL_PAPER_ORDER_STATE_KIND = "local_paper_order_state.v1"
LOCAL_PAPER_CANCEL_COMMAND_KIND = "local_paper_cancel_command.v1"
LOCAL_PAPER_DAILY_BASELINE_KIND = "local_paper_daily_baseline.v1"
LOCAL_PAPER_SESSION_ARCHIVE_KIND = "local_paper_session_archive.v1"
LOCAL_PAPER_PROJECTION_NAME = "local_paper.v1"
_LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD = "order_state_digest"
_LOCAL_PAPER_CHECKPOINT_MUTATION_KINDS = frozenset(
    {
        LOCAL_PAPER_FILL_KIND,
        LOCAL_PAPER_FILL_V2_KIND,
        LOCAL_PAPER_FILL_V3_KIND,
        LOCAL_PAPER_ORDER_STATE_KIND,
        LOCAL_PAPER_CANCEL_COMMAND_KIND,
        LOCAL_PAPER_DAILY_BASELINE_KIND,
    }
)


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
    tax: Decimal = Decimal("0")
    gross_amount: Decimal | None = None
    net_cash_effect: Decimal | None = None
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
        if not self.fill_price.is_finite() or self.fill_price <= 0:
            raise ValueError("fill_price must be positive")
        if not self.commission.is_finite() or self.commission < 0:
            raise ValueError("commission must not be negative")
        if not self.tax.is_finite() or self.tax < 0:
            raise ValueError("tax must not be negative")
        if self.gross_amount is not None and not self.gross_amount.is_finite():
            raise ValueError("gross_amount must be finite")
        if self.net_cash_effect is not None and not self.net_cash_effect.is_finite():
            raise ValueError("net_cash_effect must be finite")

    @property
    def cash_effect(self) -> Decimal:
        if self.net_cash_effect is not None:
            return self.net_cash_effect
        gross = self.fill_price * self.quantity_shares
        return (
            -(gross + self.commission)
            if self.side is LocalPaperSide.BUY
            else gross - self.commission - self.tax
        )

    @classmethod
    def from_record(cls, record: JournalRecord) -> "LocalPaperFill":
        if record.kind not in {
            LOCAL_PAPER_FILL_KIND,
            LOCAL_PAPER_FILL_V2_KIND,
            LOCAL_PAPER_FILL_V3_KIND,
        }:
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
                tax=(
                    Decimal(str(record.payload["tax"]))
                    if record.kind == LOCAL_PAPER_FILL_V3_KIND
                    else Decimal("0")
                ),
                gross_amount=(
                    Decimal(
                        str(
                            record.payload.get("gross_amount")
                            or record.payload.get("gross_notional")
                        )
                    )
                    if record.kind
                    in {LOCAL_PAPER_FILL_V2_KIND, LOCAL_PAPER_FILL_V3_KIND}
                    else None
                ),
                net_cash_effect=(
                    Decimal(str(record.payload["net_cash_effect"]))
                    if record.kind
                    in {LOCAL_PAPER_FILL_V2_KIND, LOCAL_PAPER_FILL_V3_KIND}
                    else None
                ),
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
                gross_notional = fill.gross_amount
                net_cash_effect = fill.net_cash_effect
                assert gross_notional is not None
                assert net_cash_effect is not None
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
            elif record.kind == LOCAL_PAPER_FILL_V3_KIND:
                _validate_v3_fill(record, fill)
            return fill
        except (InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError(
                f"invalid local-paper fill record {record.record_id}"
            ) from error


def _validate_sha256(value: object, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64:
        raise ValueError(f"{field_name} must be SHA-256")
    int(normalized, 16)
    return normalized


def _validate_v3_fill(record: JournalRecord, fill: LocalPaperFill) -> None:
    payload = record.payload
    required_fields = {
        "commission",
        "tax",
        "gross_amount",
        "net_cash_effect",
        "reference_price",
        "reference_source",
        "configured_slippage_bps",
        "realized_slippage_bps",
        "slippage_cost",
        "cumulative_order_gross",
        "cumulative_order_commission",
        "cumulative_order_tax",
        "fee_policy_version",
        "rounding_policy_version",
        "slippage_policy_version",
        "price_tick_policy_version",
        "settings_digest",
        "instrument_descriptor_snapshot",
        "instrument_descriptor_digest",
        "limit_price",
        "fill_source",
        "provider_identity",
        "execution_authority",
        "fill_sequence",
    }
    if not required_fields.issubset(payload):
        raise ValueError("local-paper v3 evidence is incomplete")
    assert fill.gross_amount is not None
    assert fill.net_cash_effect is not None
    expected_gross = fill.fill_price * fill.quantity_shares
    expected_net = (
        -(expected_gross + fill.commission)
        if fill.side is LocalPaperSide.BUY
        else expected_gross - fill.commission - fill.tax
    )
    cumulative_commission = Decimal(
        str(payload["cumulative_order_commission"])
    )
    cumulative_gross = Decimal(str(payload["cumulative_order_gross"]))
    cumulative_tax = Decimal(str(payload["cumulative_order_tax"]))
    reference_price = Decimal(str(payload["reference_price"]))
    configured_bps = Decimal(str(payload["configured_slippage_bps"]))
    realized_bps = Decimal(str(payload["realized_slippage_bps"]))
    slippage_cost = Decimal(str(payload["slippage_cost"]))
    limit_price = Decimal(str(payload["limit_price"]))
    reference_source = ReferenceSource(str(payload["reference_source"]))
    fill_sequence = payload["fill_sequence"]
    if (
        isinstance(fill_sequence, bool)
        or not isinstance(fill_sequence, int)
        or fill_sequence <= 0
    ):
        raise ValueError("fill_sequence must be positive")
    if not all(
        value.is_finite()
        for value in (
            cumulative_commission,
            cumulative_gross,
            cumulative_tax,
            reference_price,
            configured_bps,
            realized_bps,
            slippage_cost,
            limit_price,
        )
    ):
        raise ValueError("local-paper v3 contains non-finite evidence")
    if fill.gross_amount != expected_gross or fill.net_cash_effect != expected_net:
        raise ValueError("invalid local-paper v3 monetary evidence")
    if fill.side is LocalPaperSide.SELL and fill.net_cash_effect < 0:
        raise ValueError("SELL net cash effect must not be negative")
    if cumulative_commission < fill.commission or cumulative_tax < fill.tax:
        raise ValueError("invalid local-paper v3 cumulative accounting")
    previous_gross = cumulative_gross - expected_gross
    expected_cumulative_commission = cumulative_commission_for(cumulative_gross)
    expected_previous_commission = cumulative_commission_for(previous_gross)
    if (
        previous_gross < 0
        or cumulative_commission != expected_cumulative_commission
        or fill.commission
        != expected_cumulative_commission - expected_previous_commission
    ):
        raise ValueError("invalid local-paper v3 commission evidence")
    if fill_sequence == 1 and (
        cumulative_gross != expected_gross
        or cumulative_commission != fill.commission
        or cumulative_tax != fill.tax
    ):
        raise ValueError("invalid first local-paper v3 cumulative evidence")
    if any(
        value != value.quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
        for value in (
            fill.commission,
            fill.tax,
            cumulative_commission,
            cumulative_tax,
        )
    ):
        raise ValueError("local-paper v3 costs must use whole-TWD rounding")
    if fill.side is LocalPaperSide.BUY and fill.tax != 0:
        raise ValueError("BUY tax must be zero")
    expected_tax = (
        Decimal("0")
        if fill.side is LocalPaperSide.BUY
        else (expected_gross * SELL_TAX_RATE).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_DOWN,
        )
    )
    if fill.tax != expected_tax:
        raise ValueError("invalid local-paper v3 tax evidence")
    if reference_price <= 0 or not 0 <= configured_bps <= 100:
        raise ValueError("invalid local-paper v3 slippage inputs")
    if not is_valid_common_stock_tick(fill.fill_price):
        raise ValueError("fill price violates common-stock tick policy")
    if not is_valid_common_stock_tick(reference_price):
        raise ValueError("reference price violates common-stock tick policy")
    if not is_valid_common_stock_tick(limit_price):
        raise ValueError("limit price violates common-stock tick policy")
    if fill.side is LocalPaperSide.BUY:
        if fill.fill_price < reference_price or fill.fill_price > limit_price:
            raise ValueError("BUY fill violates adverse price or limit")
        if reference_source not in {
            ReferenceSource.BEST_ASK,
            ReferenceSource.SNAPSHOT_COMPATIBILITY,
        }:
            raise ValueError("BUY reference source is invalid")
    else:
        if fill.fill_price > reference_price or fill.fill_price < limit_price:
            raise ValueError("SELL fill violates adverse price or limit")
        if reference_source not in {
            ReferenceSource.BEST_BID,
            ReferenceSource.SNAPSHOT_COMPATIBILITY,
        }:
            raise ValueError("SELL reference source is invalid")
    expected_slippage = decide_fixed_adverse_slippage(
        side=fill.side.value,
        reference_price=reference_price,
        reference_source=reference_source,
        configured_slippage_bps=configured_bps,
        limit_price=limit_price,
    )
    if (
        not expected_slippage.limit_satisfied
        or expected_slippage.adjusted_price != fill.fill_price
    ):
        raise ValueError("invalid local-paper v3 adverse slippage evidence")
    expected_slippage_cost = (
        abs(fill.fill_price - reference_price) * fill.quantity_shares
    )
    expected_realized_bps = (
        abs(fill.fill_price - reference_price)
        / reference_price
        * Decimal("10000")
    )
    if (
        slippage_cost != expected_slippage_cost
        or realized_bps != expected_realized_bps
    ):
        raise ValueError("invalid local-paper v3 slippage evidence")
    if str(payload["fee_policy_version"]) != FEE_POLICY_VERSION:
        raise ValueError("invalid local-paper v3 fee policy")
    if str(payload["rounding_policy_version"]) != ROUNDING_POLICY_VERSION:
        raise ValueError("invalid local-paper v3 rounding policy")
    if str(payload["slippage_policy_version"]) != SLIPPAGE_POLICY_VERSION:
        raise ValueError("invalid local-paper v3 slippage policy")
    if str(payload["price_tick_policy_version"]) != PRICE_TICK_POLICY_VERSION:
        raise ValueError("invalid local-paper v3 tick policy")
    _validate_sha256(payload["settings_digest"], "settings_digest")
    snapshot = payload["instrument_descriptor_snapshot"]
    if not isinstance(snapshot, Mapping):
        raise ValueError("instrument descriptor snapshot must be a mapping")
    if snapshot.get("schema_version") != "local-paper-instrument-descriptor-v1":
        raise ValueError("instrument descriptor schema is invalid")
    descriptor_fields = (
        "symbol",
        "exchange_raw",
        "security_type_raw",
        "product_category_raw",
        "normalized_product_class",
        "source_identity",
    )
    if any(not isinstance(snapshot.get(field), str) for field in descriptor_fields):
        raise ValueError("instrument descriptor fields must be strings")
    descriptor = LocalPaperInstrumentDescriptorV1(
        symbol=str(snapshot["symbol"]),
        exchange_raw=str(snapshot["exchange_raw"]),
        security_type_raw=str(snapshot["security_type_raw"]),
        product_category_raw=str(snapshot["product_category_raw"]),
        normalized_product_class=LocalPaperProductClass(
            str(snapshot["normalized_product_class"])
        ),
        source_identity=str(snapshot["source_identity"]),
    )
    if (
        descriptor.symbol != fill.symbol
        or descriptor.normalized_product_class
        is not LocalPaperProductClass.COMMON_STOCK
        or descriptor.exchange_raw not in {"TWSE", "TPEX", "TSE", "OTC"}
        or descriptor.digest
        != _validate_sha256(
            payload["instrument_descriptor_digest"],
            "instrument_descriptor_digest",
        )
    ):
        raise ValueError("instrument descriptor evidence is invalid")
    if payload["execution_authority"] is not False:
        raise ValueError("local-paper execution authority must be false")
    if not isinstance(payload["fill_source"], str) or not payload[
        "fill_source"
    ].strip():
        raise ValueError("fill_source must not be empty")
    if not isinstance(payload["provider_identity"], str) or not payload[
        "provider_identity"
    ].strip():
        raise ValueError("provider_identity must not be empty")
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
            str(
                order.get("last_fill_price_decimal")
                or order.get("last_fill_price")
                or order["filled_price"]
            )
        )
        fill = LocalPaperFill(
            order_id=order_id,
            symbol=str(order["symbol"]),
            name=str(order["name"]),
            side=LocalPaperSide(str(order["side"])),
            quantity_shares=fill_quantity,
            fill_price=fill_price,
            commission=Decimal(
                str(
                    order.get("last_fill_commission_decimal")
                    or order.get("last_fill_commission")
                    or "0"
                )
            ),
            tax=Decimal(str(order.get("last_fill_tax") or "0")),
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
        str(
            order.get("filled_commission_decimal")
            or order.get("filled_commission")
            or "0"
        )
    )
    if cumulative_order_commission < fill.commission:
        raise ProjectionRecoveryError("invalid cumulative order commission")
    net_cash_effect = (
        -gross_notional - fill.commission
        if fill.side is LocalPaperSide.BUY
        else gross_notional - fill.commission - fill.tax
    )
    v3_requested = order.get("fee_policy_version") is not None
    if v3_requested and normalized_settings_digest is None:
        raise ProjectionRecoveryError("local-paper v3 requires settings digest")
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
    v3_payload: dict[str, object] = {}
    if v3_requested:
        try:
            stored_net_cash_effect = Decimal(
                str(order["last_net_cash_effect"])
            )
            cumulative_order_tax = Decimal(str(order["filled_tax"]))
            reference_price = Decimal(str(order["last_reference_price"]))
            configured_slippage_bps = Decimal(
                str(order["configured_slippage_bps"])
            )
            realized_slippage_bps = Decimal(
                str(order["last_realized_slippage_bps"])
            )
            slippage_cost = Decimal(str(order["last_slippage_cost"]))
            limit_price = Decimal(
                str(order.get("limit_price_decimal") or order["limit_price"])
            )
            descriptor_snapshot = order["instrument_descriptor_snapshot"]
            if not isinstance(descriptor_snapshot, Mapping):
                raise ValueError("instrument descriptor must be a mapping")
            v3_payload = {
                "reference_price": canonical_decimal_string(reference_price),
                "reference_source": str(order["last_reference_source"]),
                "configured_slippage_bps": canonical_decimal_string(
                    configured_slippage_bps
                ),
                "realized_slippage_bps": canonical_decimal_string(
                    realized_slippage_bps
                ),
                "slippage_cost": canonical_decimal_string(slippage_cost),
                "gross_amount": canonical_decimal_string(gross_notional),
                "cumulative_order_gross": canonical_decimal_string(
                    Decimal(
                        str(
                            order.get("filled_amount_decimal")
                            or order["filled_amount"]
                        )
                    )
                ),
                "commission": canonical_decimal_string(fill.commission),
                "cumulative_order_commission": canonical_decimal_string(
                    cumulative_order_commission
                ),
                "tax": canonical_decimal_string(fill.tax),
                "cumulative_order_tax": canonical_decimal_string(
                    cumulative_order_tax
                ),
                "net_cash_effect": canonical_decimal_string(
                    stored_net_cash_effect
                ),
                "fee_policy_version": str(order["fee_policy_version"]),
                "rounding_policy_version": str(
                    order["rounding_policy_version"]
                ),
                "slippage_policy_version": str(
                    order["slippage_policy_version"]
                ),
                "price_tick_policy_version": str(
                    order["price_tick_policy_version"]
                ),
                "settings_digest": normalized_settings_digest,
                "instrument_descriptor_snapshot": dict(descriptor_snapshot),
                "instrument_descriptor_digest": str(
                    order["instrument_descriptor_digest"]
                ),
                "limit_price": canonical_decimal_string(limit_price),
            }
        except (InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError(
                "incomplete local-paper v3 fill evidence"
            ) from error
    record = JournalRecord(
        record_id=f"local-paper-fill:{order_id}:{occurred_at.isoformat()}",
        session_id=session_id,
        kind=(
            LOCAL_PAPER_FILL_V3_KIND
            if v3_requested
            else LOCAL_PAPER_FILL_V2_KIND
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
            **v3_payload,
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
                if normalized_settings_digest is not None and not v3_requested
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
    if v3_requested:
        LocalPaperFill.from_record(record)
    return record


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
        "limit_price_decimal",
        "status",
        "submitted_at",
        "updated_at",
        "filled_price",
        "filled_quantity",
        "filled_amount",
        "filled_amount_decimal",
        "filled_commission",
        "filled_commission_decimal",
        "filled_tax",
        "filled_slippage_cost",
        "last_fill_price",
        "last_fill_price_decimal",
        "last_fill_quantity",
        "last_fill_commission",
        "last_fill_commission_decimal",
        "last_fill_tax",
        "last_reference_price",
        "last_reference_source",
        "configured_slippage_bps",
        "last_realized_slippage_bps",
        "last_slippage_cost",
        "last_net_cash_effect",
        "fee_policy_version",
        "rounding_policy_version",
        "slippage_policy_version",
        "price_tick_policy_version",
        "instrument_descriptor_snapshot",
        "instrument_descriptor_digest",
        "fill_sequence",
        "reason",
        "waiting_reason",
        "attempt",
        "predecessor_order_id",
        "timeout_at",
        "expires_at",
        "trading_date",
        "opening_equity",
    )
    unsigned = JournalRecord(
        record_id=f"local-paper-order-state:{order_id}:{identity}",
        session_id=session_id,
        kind=LOCAL_PAPER_ORDER_STATE_KIND,
        occurred_at=updated_at,
        payload={field: order.get(field) for field in payload_fields},
        idempotency_scope=f"{session_id}:local-paper-order-state",
        idempotency_key=f"{order_id}:{identity}",
    )
    return JournalRecord(
        record_id=unsigned.record_id,
        session_id=unsigned.session_id,
        kind=unsigned.kind,
        occurred_at=unsigned.occurred_at,
        payload={
            **unsigned.payload,
            _LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD: hashlib.sha256(
                unsigned.payload_bytes
            ).hexdigest(),
        },
        idempotency_scope=unsigned.idempotency_scope,
        idempotency_key=unsigned.idempotency_key,
        schema_version=unsigned.schema_version,
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
        self._v3_order_accounting: dict[
            str,
            tuple[int, Decimal, Decimal, Decimal],
        ] = {}
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
        if result.record.kind in {
            LOCAL_PAPER_FILL_KIND,
            LOCAL_PAPER_FILL_V2_KIND,
            LOCAL_PAPER_FILL_V3_KIND,
        }:
            if (
                result.record.kind == LOCAL_PAPER_FILL_V3_KIND
                and self._settings_digest is None
            ):
                raise ProjectionRecoveryError(
                    "local-paper v3 recovery requires session settings digest"
                )
            if self._settings_digest is not None and (
                result.record.kind
                not in {LOCAL_PAPER_FILL_V2_KIND, LOCAL_PAPER_FILL_V3_KIND}
                or result.record.payload.get("settings_digest")
                != self._settings_digest
            ):
                raise ProjectionRecoveryError(
                    "Journal fill settings digest conflicts with session"
                )
            fill = LocalPaperFill.from_record(result.record)
            v3_accounting = (
                self._validated_v3_order_accounting(result.record, fill)
                if result.record.kind == LOCAL_PAPER_FILL_V3_KIND
                else None
            )
            self._apply_fill(fill, occurred_at=result.record.occurred_at)
            if v3_accounting is not None:
                self._v3_order_accounting[fill.order_id] = v3_accounting
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
        value = fill.gross_amount or fill.quantity_shares * fill.fill_price
        current = self._positions.get(fill.symbol)
        if fill.side is LocalPaperSide.BUY:
            if -fill.cash_effect > self._cash:
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
            self._cash += fill.cash_effect
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
        self._cash += fill.cash_effect
        self._realized_pnl[fill.symbol] = (
            self.realized_pnl(fill.symbol)
            + (fill.fill_price - current.average_price) * fill.quantity_shares
            - allocated_buy_commission
            - fill.commission
            - fill.tax
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

    def _validated_v3_order_accounting(
        self,
        record: JournalRecord,
        fill: LocalPaperFill,
    ) -> tuple[int, Decimal, Decimal, Decimal]:
        payload = record.payload
        sequence = int(payload["fill_sequence"])
        cumulative_gross = Decimal(str(payload["cumulative_order_gross"]))
        cumulative_commission = Decimal(
            str(payload["cumulative_order_commission"])
        )
        cumulative_tax = Decimal(str(payload["cumulative_order_tax"]))
        previous = self._v3_order_accounting.get(
            fill.order_id,
            (0, Decimal("0"), Decimal("0"), Decimal("0")),
        )
        expected = (
            previous[0] + 1,
            previous[1] + (fill.gross_amount or Decimal("0")),
            previous[2] + fill.commission,
            previous[3] + fill.tax,
        )
        actual = (
            sequence,
            cumulative_gross,
            cumulative_commission,
            cumulative_tax,
        )
        if actual != expected:
            raise ProjectionRecoveryError(
                "local-paper v3 cumulative order evidence is inconsistent"
            )
        return actual


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
    uncheckpointed_mutation = False
    for result in journal.records(session_id):
        projection.apply(result)
        if checkpoint is not None and result.sequence == checkpoint.journal_sequence:
            checkpoint_digest = projection.digest
        elif (
            checkpoint is not None
            and result.sequence > checkpoint.journal_sequence
            and result.record.kind in _LOCAL_PAPER_CHECKPOINT_MUTATION_KINDS
        ):
            uncheckpointed_mutation = True

    if checkpoint is not None:
        if checkpoint_digest is None:
            raise ProjectionRecoveryError("checkpoint sequence is absent from Journal")
        if checkpoint_digest != checkpoint.digest:
            raise ProjectionRecoveryError("local-paper checkpoint digest mismatch")
        if require_checkpoint and uncheckpointed_mutation:
            raise ProjectionRecoveryError(
                "local-paper checkpoint does not cover Journal tail"
            )
    return projection


def latest_local_paper_order_states(
    journal: JournalRepository,
    *,
    session_id: str,
    require_integrity: bool = False,
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
        payload = _verified_order_state_payload(
            result.record,
            require_integrity=require_integrity,
        )
        order_id = str(payload.get("order_id") or "")
        if not order_id:
            raise ProjectionRecoveryError("order state record is missing order_id")
        latest[order_id] = payload
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


def _verified_order_state_payload(
    record: JournalRecord,
    *,
    require_integrity: bool,
) -> Mapping[str, object]:
    stored_digest = record.payload.get(_LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD)
    if stored_digest is None:
        if require_integrity:
            raise ProjectionRecoveryError("order state integrity evidence is missing")
        return record.payload
    unsigned_payload = {
        key: value
        for key, value in record.payload.items()
        if key != _LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD
    }
    unsigned = JournalRecord(
        record_id=record.record_id,
        session_id=record.session_id,
        kind=record.kind,
        occurred_at=record.occurred_at,
        payload=unsigned_payload,
        idempotency_scope=record.idempotency_scope,
        idempotency_key=record.idempotency_key,
        schema_version=record.schema_version,
    )
    expected_digest = hashlib.sha256(unsigned.payload_bytes).hexdigest()
    if stored_digest != expected_digest:
        raise ProjectionRecoveryError("order state integrity digest mismatch")
    return record.payload


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
