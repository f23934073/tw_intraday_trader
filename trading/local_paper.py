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
from trading.canonical_values import (
    canonical_decimal_string,
    require_aware_datetime_string,
    require_canonical_decimal_string,
    require_json_fields,
    require_json_integer,
    require_json_string,
    require_optional_json_string,
)
from trading.journal import (
    JournalAppendResult,
    JournalRecord,
    JournalRepository,
    ProjectionCheckpoint,
)
from trading.no_overnight_admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionStatus,
)
from trading.exposure import (
    ExecutionReasonCategory,
    ExposureIdentity,
    PositionAction,
    build_legacy_exposure_identity,
)
from trading.risk import OrderCommand
from trading.trade_management import OrderLifecycleState


LOCAL_PAPER_FILL_KIND = "local_paper_fill.v1"
LOCAL_PAPER_FILL_V2_KIND = "local_paper_fill.v2"
LOCAL_PAPER_FILL_V3_KIND = "local_paper_fill.v3"
LOCAL_PAPER_FILL_V4_KIND = "local_paper_fill.v4"
LOCAL_PAPER_ORDER_STATE_KIND = "local_paper_order_state.v1"
LOCAL_PAPER_CANCEL_COMMAND_KIND = "local_paper_cancel_command.v1"
LOCAL_PAPER_REJECTION_KIND = "local_paper_rejection.v1"
LOCAL_PAPER_DAILY_BASELINE_KIND = "local_paper_daily_baseline.v1"
LOCAL_PAPER_SESSION_ARCHIVE_KIND = "local_paper_session_archive.v1"
LOCAL_PAPER_PROJECTION_NAME = "local_paper.v1"
_LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD = "order_state_digest"
_LOCAL_PAPER_CHECKPOINT_MUTATION_KINDS = frozenset(
    {
        LOCAL_PAPER_FILL_KIND,
        LOCAL_PAPER_FILL_V2_KIND,
        LOCAL_PAPER_FILL_V3_KIND,
        LOCAL_PAPER_FILL_V4_KIND,
        LOCAL_PAPER_ORDER_STATE_KIND,
        LOCAL_PAPER_CANCEL_COMMAND_KIND,
        LOCAL_PAPER_DAILY_BASELINE_KIND,
    }
)
LOCAL_PAPER_ORDER_STATE_V2_KIND = "local_paper_order_state.v2"
LOCAL_PAPER_REJECTION_V2_KIND = "local_paper_rejection.v2"
LOCAL_PAPER_CANCEL_INTENT_V2_KIND = "local_paper_cancel_intent.v2"
LOCAL_PAPER_CANCEL_RESULT_V2_KIND = "local_paper_cancel_result.v2"
LOCAL_PAPER_V1_IMPORTED_KIND = "local_paper_v1_imported.v1"
LOCAL_PAPER_V2_PROJECTION_NAME = "local_paper.v2"
_LOCAL_PAPER_V2_CHECKPOINT_MUTATION_KINDS = frozenset(
    {
        LOCAL_PAPER_FILL_V4_KIND,
        LOCAL_PAPER_V1_IMPORTED_KIND,
    }
)

_V4_FILL_REQUIRED_FIELDS = frozenset(
    {
        "order_id",
        "symbol",
        "name",
        "side",
        "quantity_shares",
        "fill_price",
        "fill_sequence",
        "owner_origin",
        "owner_strategy_id",
        "owner_strategy_version",
        "exposure_identity",
        "position_action",
        "target_exposure_id",
        "execution_reason_category",
        "execution_reason_code",
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
    }
)
_V4_FILL_ALLOWED_FIELDS = _V4_FILL_REQUIRED_FIELDS | frozenset(
    {
        "command_id",
        "command_idempotency_key",
    }
)
_ORDER_STATE_BASE_FIELDS = (
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
_ORDER_STATE_V2_IDENTITY_FIELDS = (
    "exposure_identity",
    "position_action",
    "target_exposure_id",
    "execution_reason_category",
    "execution_reason_code",
)
_ORDER_STATE_V2_FIELDS = frozenset(
    (*_ORDER_STATE_BASE_FIELDS, *_ORDER_STATE_V2_IDENTITY_FIELDS)
)


class LocalPaperSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ProjectionRecoveryError(ValueError):
    """The Journal cannot prove a safe local-paper recovery."""


class OrderStateReconciliationConflict(ProjectionRecoveryError):
    """A typed decimal alias is valid by itself but conflicts with its peer."""


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
            LOCAL_PAPER_FILL_V4_KIND,
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
                    if record.kind
                    in {LOCAL_PAPER_FILL_V3_KIND, LOCAL_PAPER_FILL_V4_KIND}
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
                    in {
                        LOCAL_PAPER_FILL_V2_KIND,
                        LOCAL_PAPER_FILL_V3_KIND,
                        LOCAL_PAPER_FILL_V4_KIND,
                    }
                    else None
                ),
                net_cash_effect=(
                    Decimal(str(record.payload["net_cash_effect"]))
                    if record.kind
                    in {
                        LOCAL_PAPER_FILL_V2_KIND,
                        LOCAL_PAPER_FILL_V3_KIND,
                        LOCAL_PAPER_FILL_V4_KIND,
                    }
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
            elif record.kind in {
                LOCAL_PAPER_FILL_V3_KIND,
                LOCAL_PAPER_FILL_V4_KIND,
            }:
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


@dataclass(frozen=True)
class LocalPaperExposurePosition:
    exposure: ExposureIdentity
    symbol: str
    name: str
    quantity_shares: int
    average_price: Decimal
    commission_cost: Decimal = Decimal("0")
    owner_strategy_version: str | None = None


@dataclass(frozen=True)
class LocalPaperExposureFill:
    order_id: str
    symbol: str
    name: str
    side: LocalPaperSide
    quantity_shares: int
    fill_price: Decimal
    exposure: ExposureIdentity
    position_action: PositionAction
    target_exposure_id: str | None
    execution_reason_category: ExecutionReasonCategory
    execution_reason_code: str
    commission: Decimal
    tax: Decimal
    net_cash_effect: Decimal
    owner_strategy_version: str | None = None

    @property
    def cash_effect(self) -> Decimal:
        return self.net_cash_effect

    @classmethod
    def from_record(cls, record: JournalRecord) -> "LocalPaperExposureFill":
        if record.kind != LOCAL_PAPER_FILL_V4_KIND:
            raise ValueError("record is not a local-paper v4 fill")
        try:
            require_json_fields(
                record.payload,
                required=_V4_FILL_REQUIRED_FIELDS,
                allowed=_V4_FILL_ALLOWED_FIELDS,
                field_name="v4 fill",
            )
            require_json_integer(
                record.payload["quantity_shares"], "quantity_shares"
            )
            monetary_fill = LocalPaperFill.from_record(record)
            exposure_payload = record.payload["exposure_identity"]
            if not isinstance(exposure_payload, Mapping):
                raise ValueError("exposure_identity must be an object")
            exposure = ExposureIdentity.from_payload(exposure_payload)
            fill_sequence = require_json_integer(
                record.payload["fill_sequence"], "fill_sequence"
            )
            if fill_sequence <= 0:
                raise ValueError("fill_sequence must be positive")
            owner_origin = require_json_string(
                record.payload["owner_origin"], "owner_origin"
            )
            owner_strategy_id = require_optional_json_string(
                record.payload["owner_strategy_id"], "owner_strategy_id"
            )
            owner_strategy_version = require_optional_json_string(
                record.payload["owner_strategy_version"],
                "owner_strategy_version",
            )
            if exposure.owner_origin != owner_origin:
                raise ValueError("exposure owner_origin mismatch")
            if (
                owner_origin == "STRATEGY_AUTOMATED"
                and exposure.owner_id != owner_strategy_id
            ):
                raise ValueError("exposure owner_strategy_id mismatch")
            if owner_origin == "STRATEGY_AUTOMATED":
                if owner_strategy_version is None:
                    raise ValueError("strategy fill requires owner_strategy_version")
            elif owner_strategy_id is not None or owner_strategy_version is not None:
                raise ValueError("manual fill cannot carry strategy identity")
            provenance_fields = {
                "fill_source",
                "provider_identity",
                "execution_authority",
            }
            present_provenance = provenance_fields & set(record.payload)
            if present_provenance and present_provenance != provenance_fields:
                raise ValueError("v4 fill provenance fields are incomplete")
            if present_provenance:
                require_json_string(record.payload["fill_source"], "fill_source")
                require_json_string(
                    record.payload["provider_identity"], "provider_identity"
                )
                if not isinstance(record.payload["execution_authority"], bool):
                    raise ValueError("execution_authority must be a boolean")
            command_fields = {"command_id", "command_idempotency_key"}
            present_command_fields = command_fields & set(record.payload)
            if present_command_fields and present_command_fields != command_fields:
                raise ValueError("v4 fill command linkage fields are incomplete")
            if present_command_fields:
                require_json_string(record.payload["command_id"], "command_id")
                require_json_string(
                    record.payload["command_idempotency_key"],
                    "command_idempotency_key",
                )
            fill = cls(
                order_id=require_json_string(
                    record.payload["order_id"], "order_id"
                ),
                symbol=require_json_string(record.payload["symbol"], "symbol"),
                name=require_json_string(record.payload["name"], "name"),
                side=LocalPaperSide(
                    require_json_string(record.payload["side"], "side")
                ),
                quantity_shares=require_json_integer(
                    record.payload["quantity_shares"], "quantity_shares"
                ),
                fill_price=require_canonical_decimal_string(
                    record.payload["fill_price"],
                    "fill_price",
                    positive=True,
                ),
                exposure=exposure,
                position_action=PositionAction(
                    require_json_string(
                        record.payload["position_action"], "position_action"
                    )
                ),
                target_exposure_id=require_optional_json_string(
                    record.payload["target_exposure_id"],
                    "target_exposure_id",
                ),
                execution_reason_category=ExecutionReasonCategory(
                    require_json_string(
                        record.payload["execution_reason_category"],
                        "execution_reason_category",
                    )
                ),
                execution_reason_code=require_json_string(
                    record.payload["execution_reason_code"],
                    "execution_reason_code",
                ),
                commission=monetary_fill.commission,
                tax=monetary_fill.tax,
                net_cash_effect=monetary_fill.cash_effect,
                owner_strategy_version=owner_strategy_version,
            )
        except (InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError(
                f"invalid local-paper v4 fill record {record.record_id}: {error}"
            ) from error
        if fill.symbol != fill.symbol.strip().upper():
            raise ProjectionRecoveryError("v4 fill symbol is not normalized")
        if fill.quantity_shares <= 0 or fill.fill_price <= 0:
            raise ProjectionRecoveryError("v4 fill quantity or price is invalid")
        if not fill.execution_reason_code.strip():
            raise ProjectionRecoveryError("v4 fill reason code is empty")
        if fill.execution_reason_code != fill.execution_reason_code.strip().upper():
            raise ProjectionRecoveryError("v4 fill reason code is not normalized")
        if fill.side is LocalPaperSide.BUY:
            if fill.position_action is not PositionAction.OPEN_LONG:
                raise ProjectionRecoveryError("BUY fill must OPEN_LONG")
            if fill.target_exposure_id is not None:
                raise ProjectionRecoveryError("BUY fill cannot target exposure")
        elif (
            fill.position_action is not PositionAction.CLOSE_LONG
            or fill.target_exposure_id != fill.exposure.exposure_id
        ):
            raise ProjectionRecoveryError("SELL fill target exposure mismatch")
        return fill


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
    identity_requested = (
        order.get("execution_reason_category") is not None
        or order.get("execution_reason_code") is not None
    )
    identity_payload: dict[str, object] = {}
    if identity_requested:
        if not v3_requested:
            raise ProjectionRecoveryError(
                "managed identity fill requires local-paper v3 monetary evidence"
            )
        try:
            raw_exposure = order["exposure_identity"]
            if not isinstance(raw_exposure, Mapping):
                raise ValueError("exposure identity must be an object")
            exposure = ExposureIdentity.from_payload(raw_exposure)
            action = PositionAction(str(order["position_action"]))
            target = (
                str(order["target_exposure_id"])
                if order.get("target_exposure_id") is not None
                else None
            )
            category = ExecutionReasonCategory(
                str(order["execution_reason_category"])
            )
            reason_code = str(order["execution_reason_code"]).strip()
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError(
                "invalid simulation v4 fill identity"
            ) from error
        if not reason_code or reason_code != reason_code.strip().upper():
            raise ProjectionRecoveryError("invalid simulation v4 fill reason")
        if fill.side is LocalPaperSide.BUY:
            if action is not PositionAction.OPEN_LONG or target is not None:
                raise ProjectionRecoveryError("BUY fill exposure action mismatch")
        elif (
            action is not PositionAction.CLOSE_LONG
            or target != exposure.exposure_id
        ):
            raise ProjectionRecoveryError("SELL fill target exposure mismatch")
        if exposure.owner_origin != fill.owner_origin:
            raise ProjectionRecoveryError("fill exposure owner mismatch")
        if (
            exposure.owner_origin == "STRATEGY_AUTOMATED"
            and exposure.owner_id != fill.owner_strategy_id
        ):
            raise ProjectionRecoveryError("fill exposure strategy mismatch")
        identity_payload = {
            "exposure_identity": exposure.to_payload(),
            "position_action": action.value,
            "target_exposure_id": target,
            "execution_reason_category": category.value,
            "execution_reason_code": reason_code,
        }
    kind = (
        LOCAL_PAPER_FILL_V4_KIND
        if identity_requested
        else LOCAL_PAPER_FILL_V3_KIND
        if v3_requested
        else LOCAL_PAPER_FILL_V2_KIND
        if normalized_settings_digest is not None
        else LOCAL_PAPER_FILL_KIND
    )
    record_prefix = (
        "local-paper-fill-v4"
        if identity_requested
        else "local-paper-fill"
    )
    record = JournalRecord(
        record_id=f"{record_prefix}:{order_id}:{occurred_at.isoformat()}",
        session_id=session_id,
        kind=kind,
        occurred_at=occurred_at,
        payload={
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "name": fill.name,
            "side": fill.side.value,
            "quantity_shares": fill.quantity_shares,
            "fill_price": canonical_decimal_string(fill.fill_price),
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
            **identity_payload,
            **provenance,
        },
        idempotency_scope=(
            f"{session_id}:simulation_fill_v4"
            if identity_requested
            else f"{session_id}:legacy_simulation_fill"
        ),
        idempotency_key=(
            order_id if fill_sequence == 1 else f"{order_id}:{fill_sequence}"
        ),
    )
    if identity_requested:
        LocalPaperExposureFill.from_record(record)
    elif v3_requested:
        LocalPaperFill.from_record(record)
    return record


def _canonical_simulation_decimal(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ProjectionRecoveryError(f"{field_name} must be a finite number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ProjectionRecoveryError(f"{field_name} must be a finite number") from error
    if not parsed.is_finite():
        raise ProjectionRecoveryError(f"{field_name} must be a finite number")
    return canonical_decimal_string(parsed)


def _optional_v2_state_decimal(
    payload: dict[str, object],
    field_name: str,
) -> None:
    value = payload[field_name]
    if value is not None:
        payload[field_name] = _canonical_simulation_decimal(value, field_name)


def _require_v2_state_decimal_alias(
    payload: Mapping[str, object],
    primary_field: str,
    decimal_field: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> None:
    primary = payload[primary_field]
    decimal_alias = payload[decimal_field]
    if primary is None or decimal_alias is None:
        if primary is not None or decimal_alias is not None:
            raise OrderStateReconciliationConflict(
                f"{primary_field} and {decimal_field} nullability must match"
            )
        return
    primary_value = Decimal(
        _canonical_simulation_decimal(primary, primary_field)
    )
    alias_value = Decimal(
        _canonical_simulation_decimal(
            require_json_string(decimal_alias, decimal_field),
            decimal_field,
        )
    )
    if positive and alias_value <= 0:
        raise ValueError(f"{decimal_field} must be positive")
    if non_negative and alias_value < 0:
        raise ValueError(f"{decimal_field} must not be negative")
    if primary_value != alias_value:
        raise OrderStateReconciliationConflict(
            f"{decimal_field} must match {primary_field}"
        )


def _validated_v2_order_state_payload(
    record: JournalRecord,
) -> Mapping[str, object]:
    payload = dict(
        _verified_order_state_payload(record, require_integrity=True)
        if _LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD in record.payload
        else record.payload
    )
    payload.pop(_LOCAL_PAPER_ORDER_STATE_DIGEST_FIELD, None)
    try:
        require_json_fields(
            payload,
            required=_ORDER_STATE_V2_FIELDS,
            field_name="v2 order state",
        )
        order_id = require_json_string(payload["order_id"], "order_id")
        require_json_string(payload["idempotency_key"], "idempotency_key")
        origin = require_json_string(payload["origin"], "origin")
        strategy_id = require_optional_json_string(
            payload["strategy_id"], "strategy_id"
        )
        strategy_version = require_optional_json_string(
            payload["strategy_version"], "strategy_version"
        )
        symbol = require_json_string(payload["symbol"], "symbol")
        if symbol != symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        require_json_string(payload["name"], "name")
        side = LocalPaperSide(require_json_string(payload["side"], "side"))
        lots = payload["lots"]
        if lots is not None:
            lots = require_json_integer(lots, "lots")
            if lots <= 0:
                raise ValueError("lots must be positive")
        quantity_shares = require_json_integer(
            payload["quantity_shares"], "quantity_shares"
        )
        quantity = require_json_integer(payload["quantity"], "quantity")
        remaining_quantity = require_json_integer(
            payload["remaining_quantity"], "remaining_quantity"
        )
        filled_quantity = require_json_integer(
            payload["filled_quantity"], "filled_quantity"
        )
        last_fill_quantity = require_json_integer(
            payload["last_fill_quantity"], "last_fill_quantity"
        )
        fill_sequence = require_json_integer(
            payload["fill_sequence"], "fill_sequence"
        )
        attempt = require_json_integer(payload["attempt"], "attempt")
        if quantity_shares <= 0 or quantity != quantity_shares:
            raise ValueError("quantity_shares and quantity must match and be positive")
        if (
            filled_quantity < 0
            or remaining_quantity < 0
            or remaining_quantity != quantity - filled_quantity
        ):
            raise ValueError("filled and remaining quantities are inconsistent")
        if last_fill_quantity < 0 or fill_sequence < 0 or attempt <= 0:
            raise ValueError("fill quantities, sequence, and attempt are invalid")
        expected_lots = quantity // 1_000 if quantity % 1_000 == 0 else None
        if lots != expected_lots:
            raise ValueError("lots is inconsistent with quantity_shares")
        require_canonical_decimal_string(
            payload["limit_price"], "limit_price", positive=True
        )
        _require_v2_state_decimal_alias(
            payload,
            "limit_price",
            "limit_price_decimal",
            positive=True,
        )
        for field_name in ("filled_price", "filled_amount", "last_fill_price"):
            if payload[field_name] is not None:
                require_canonical_decimal_string(
                    payload[field_name], field_name, positive=True
                )
        _require_v2_state_decimal_alias(
            payload,
            "filled_amount",
            "filled_amount_decimal",
            positive=True,
        )
        _require_v2_state_decimal_alias(
            payload,
            "last_fill_price",
            "last_fill_price_decimal",
            positive=True,
        )
        _require_v2_state_decimal_alias(
            payload,
            "filled_commission",
            "filled_commission_decimal",
            non_negative=True,
        )
        _require_v2_state_decimal_alias(
            payload,
            "last_fill_commission",
            "last_fill_commission_decimal",
            non_negative=True,
        )
        if payload["opening_equity"] is not None:
            require_canonical_decimal_string(
                payload["opening_equity"], "opening_equity", positive=True
            )
        OrderLifecycleState(require_json_string(payload["status"], "status"))
        require_aware_datetime_string(payload["submitted_at"], "submitted_at")
        updated_at = require_aware_datetime_string(
            payload["updated_at"], "updated_at"
        )
        if updated_at != record.occurred_at:
            raise ValueError("updated_at must match Journal occurred_at")
        require_optional_json_string(payload["reason"], "reason")
        predecessor_order_id = require_optional_json_string(
            payload["predecessor_order_id"], "predecessor_order_id"
        )
        if (attempt == 1) != (predecessor_order_id is None):
            raise ValueError("predecessor_order_id must match attempt")
        for field_name in ("timeout_at", "expires_at"):
            if payload[field_name] is not None:
                require_aware_datetime_string(payload[field_name], field_name)
        if payload["trading_date"] is not None:
            raw_date = require_json_string(payload["trading_date"], "trading_date")
            date.fromisoformat(raw_date)
        exposure_payload = payload["exposure_identity"]
        if not isinstance(exposure_payload, Mapping):
            raise ValueError("exposure_identity must be an object")
        exposure = ExposureIdentity.from_payload(exposure_payload)
        if exposure.owner_origin != origin:
            raise ValueError("exposure owner_origin mismatch")
        if origin == "STRATEGY_AUTOMATED":
            if exposure.owner_id != strategy_id:
                raise ValueError("exposure strategy owner mismatch")
            if strategy_version is None:
                raise ValueError("strategy order state requires strategy_version")
        elif strategy_id is not None or strategy_version is not None:
            raise ValueError("manual order state cannot carry strategy identity")
        action = PositionAction(
            require_json_string(payload["position_action"], "position_action")
        )
        target = require_optional_json_string(
            payload["target_exposure_id"], "target_exposure_id"
        )
        ExecutionReasonCategory(
            require_json_string(
                payload["execution_reason_category"],
                "execution_reason_category",
            )
        )
        reason_code = require_json_string(
            payload["execution_reason_code"], "execution_reason_code"
        )
        if reason_code != reason_code.strip().upper():
            raise ValueError("execution_reason_code must be normalized")
        if side is LocalPaperSide.BUY:
            if action is not PositionAction.OPEN_LONG or target is not None:
                raise ValueError("BUY order state exposure action mismatch")
        elif action is not PositionAction.CLOSE_LONG or target != exposure.exposure_id:
            raise ValueError("SELL order state target exposure mismatch")
        if record.record_id and not order_id:
            raise ValueError("order_id must not be empty")
    except OrderStateReconciliationConflict:
        raise
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ProjectionRecoveryError(
            f"invalid local-paper v2 order state {record.record_id}: {error}"
        ) from error
    return payload


def _require_v2_state_command_match(
    state: Mapping[str, object],
    command: OrderCommand,
) -> None:
    if command.exposure is None:
        raise ProjectionRecoveryError("v2 order state references a v1 command")
    comparisons = {
        "idempotency_key": command.idempotency_key,
        "origin": command.origin.value,
        "strategy_id": command.strategy_id,
        "strategy_version": command.strategy_version,
        "symbol": command.symbol,
        "side": command.side.value,
        "quantity_shares": command.quantity_shares,
        "limit_price": canonical_decimal_string(command.limit_price),
        "attempt": command.attempt,
        "predecessor_order_id": command.predecessor_order_id,
        "exposure_identity": command.exposure.to_payload(),
        "position_action": command.position_action.value,
        "target_exposure_id": command.target_exposure_id,
        "execution_reason_category": command.execution_reason_category.value,
        "execution_reason_code": command.execution_reason_code,
    }
    for field_name, expected in comparisons.items():
        actual = state[field_name]
        if isinstance(actual, Mapping) and isinstance(expected, Mapping):
            matches = dict(actual) == dict(expected)
        else:
            matches = actual == expected
        if not matches:
            raise ProjectionRecoveryError(
                f"v2 order state {field_name} does not match command"
            )


def _require_v4_fill_command_match(
    fill: LocalPaperExposureFill,
    command: OrderCommand,
    *,
    expected_order_id: str,
    payload: Mapping[str, object],
) -> None:
    comparisons = {
        "order_id": (fill.order_id, expected_order_id),
        "symbol": (fill.symbol, command.symbol),
        "side": (fill.side.value, command.side.value),
        "limit_price": (
            payload.get("limit_price"),
            canonical_decimal_string(command.limit_price),
        ),
        "owner_strategy_version": (
            fill.owner_strategy_version,
            command.strategy_version,
        ),
        "exposure_identity": (fill.exposure, command.exposure),
        "position_action": (fill.position_action, command.position_action),
        "target_exposure_id": (
            fill.target_exposure_id,
            command.target_exposure_id,
        ),
        "execution_reason_category": (
            fill.execution_reason_category,
            command.execution_reason_category,
        ),
        "execution_reason_code": (
            fill.execution_reason_code,
            command.execution_reason_code,
        ),
    }
    for field_name, (actual, expected) in comparisons.items():
        if actual != expected:
            raise ProjectionRecoveryError(
                f"v4 fill {field_name} does not match command"
            )
    if fill.quantity_shares > command.quantity_shares:
        raise ProjectionRecoveryError("v4 fill quantity exceeds command")


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
    payload_fields = _ORDER_STATE_BASE_FIELDS
    is_v2 = order.get("execution_reason_category") is not None
    if is_v2:
        payload_fields = (*payload_fields, *_ORDER_STATE_V2_IDENTITY_FIELDS)
    payload = {field: order.get(field) for field in payload_fields}
    if is_v2:
        for field_name in (
            "limit_price",
            "filled_price",
            "filled_amount",
            "last_fill_price",
            "opening_equity",
        ):
            _optional_v2_state_decimal(payload, field_name)
    unsigned = JournalRecord(
        record_id=(
            f"local-paper-order-state-v2:{order_id}:{identity}"
            if is_v2
            else f"local-paper-order-state:{order_id}:{identity}"
        ),
        session_id=session_id,
        kind=(
            LOCAL_PAPER_ORDER_STATE_V2_KIND
            if is_v2
            else LOCAL_PAPER_ORDER_STATE_KIND
        ),
        occurred_at=updated_at,
        payload=payload,
        idempotency_scope=f"{session_id}:local-paper-order-state",
        idempotency_key=f"{order_id}:{identity}",
    )
    if is_v2:
        _validated_v2_order_state_payload(unsigned)
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


def canonical_v2_order_state_from_simulation_order(
    order: Mapping[str, object],
    *,
    session_id: str,
) -> Mapping[str, object]:
    """Return the strict canonical v2 state used for reconciliation."""

    record = order_state_record_from_simulation_order(
        order,
        session_id=session_id,
    )
    if record.kind != LOCAL_PAPER_ORDER_STATE_V2_KIND:
        raise ProjectionRecoveryError(
            "managed simulator order does not provide v2 identity"
        )
    return dict(_validated_v2_order_state_payload(record))


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
        state_record = order_state_record_from_simulation_order(
            handler_result,
            session_id=command.session_id,
        )
        if state_record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND:
            state = _validated_v2_order_state_payload(state_record)
            _require_v2_state_command_match(state, command)
        records.append(state_record)
        return tuple(records)


@dataclass
class _OrderExecutionLineage:
    command: OrderCommand
    command_sequence: int
    risk_status: str | None
    initial_admission: ExecutionAdmissionDecision | None
    final_admission: ExecutionAdmissionDecision | None = None
    final_admission_sequence: int | None = None
    final_admission_failure_sequence: int | None = None
    order_id: str | None = None
    latest_state_record_sequence: int = 0
    latest_fill_record_sequence: int = 0


def _state_decimal(state: Mapping[str, object], field_name: str) -> Decimal:
    try:
        value = Decimal(str(state[field_name]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise ProjectionRecoveryError(
            f"v2 order state {field_name} is invalid"
        ) from error
    if not value.is_finite():
        raise ProjectionRecoveryError(
            f"v2 order state {field_name} is invalid"
        )
    return value


def _require_v2_state_fill_match(
    state: Mapping[str, object],
    command: OrderCommand,
    *,
    filled_quantity: int,
    fill_count: int,
    cumulative_gross: Decimal,
    cumulative_commission: Decimal,
    cumulative_tax: Decimal,
    cumulative_slippage: Decimal,
) -> None:
    expected_remaining = command.quantity_shares - filled_quantity
    if (
        state["filled_quantity"] != filled_quantity
        or state["remaining_quantity"] != expected_remaining
        or state["fill_sequence"] != fill_count
    ):
        raise ProjectionRecoveryError(
            "v2 order state fill progression does not match v4 fills"
        )
    status = OrderLifecycleState(str(state["status"]))
    fully_filled = filled_quantity == command.quantity_shares
    if fully_filled and status not in {
        OrderLifecycleState.FILLED,
        OrderLifecycleState.RECOVERY_REQUIRED,
    }:
        raise ProjectionRecoveryError(
            "v2 fully filled order state must be FILLED or RECOVERY_REQUIRED"
        )
    if status is OrderLifecycleState.FILLED and not fully_filled:
        raise ProjectionRecoveryError(
            "v2 FILLED order state must have zero remaining quantity"
        )
    if status is OrderLifecycleState.PARTIALLY_FILLED and not (
        0 < filled_quantity < command.quantity_shares
    ):
        raise ProjectionRecoveryError(
            "v2 PARTIALLY_FILLED order state quantity is invalid"
        )
    if status in {
        OrderLifecycleState.CREATED,
        OrderLifecycleState.SUBMITTED,
        OrderLifecycleState.PENDING,
        OrderLifecycleState.REJECTED,
    } and filled_quantity != 0:
        raise ProjectionRecoveryError(
            "v2 unfilled or rejected order state cannot carry fills"
        )
    if filled_quantity == 0:
        if state["filled_amount"] is not None:
            raise ProjectionRecoveryError(
                "v2 unfilled order state cannot carry filled amount"
            )
    elif _state_decimal(state, "filled_amount") != cumulative_gross:
        raise ProjectionRecoveryError(
            "v2 order state cumulative gross does not match v4 fills"
        )
    monetary_comparisons = {
        "filled_commission_decimal": cumulative_commission,
        "filled_tax": cumulative_tax,
        "filled_slippage_cost": cumulative_slippage,
    }
    for field_name, expected in monetary_comparisons.items():
        if _state_decimal(state, field_name) != expected:
            raise ProjectionRecoveryError(
                f"v2 order state {field_name} does not match v4 fills"
            )


def _require_execution_fact_admission(
    lineage: _OrderExecutionLineage,
    *,
    fact_kind: str,
    fact_sequence: int,
    state_status: object | None = None,
) -> None:
    if fact_sequence <= lineage.command_sequence:
        raise ProjectionRecoveryError("execution fact append order is invalid")
    failure_sequence = lineage.final_admission_failure_sequence
    if failure_sequence is not None and fact_sequence > failure_sequence:
        raise ProjectionRecoveryError(
            "execution fact follows a final admission failure"
        )
    initial = lineage.initial_admission
    if initial is None:
        return
    if lineage.risk_status != "APPROVED":
        if fact_kind == LOCAL_PAPER_ORDER_STATE_V2_KIND and state_status == "REJECTED":
            return
        raise ProjectionRecoveryError(
            "execution fact follows a non-approved risk decision"
        )
    if initial.status is not ExecutionAdmissionStatus.APPROVED:
        raise ProjectionRecoveryError(
            "execution fact follows a non-approved initial admission"
        )
    final = lineage.final_admission
    final_sequence = lineage.final_admission_sequence
    if final is None or final_sequence is None:
        raise ProjectionRecoveryError(
            "execution fact has no approved final admission"
        )
    if not lineage.command_sequence < final_sequence < fact_sequence:
        raise ProjectionRecoveryError("execution fact append order is invalid")
    if final.status is ExecutionAdmissionStatus.BLOCKED:
        raise ProjectionRecoveryError(
            "execution fact follows a blocked final admission"
        )
    if final.status is not ExecutionAdmissionStatus.APPROVED:
        raise ProjectionRecoveryError(
            "execution fact follows a non-approved final admission"
        )
    if final.admission_revision != initial.admission_revision:
        raise ProjectionRecoveryError("final admission lineage is invalid")


def _validated_order_execution_lineages(
    records: tuple[JournalAppendResult, ...],
) -> dict[str, _OrderExecutionLineage]:
    from trading.application import order_command_from_record

    lineages: dict[str, _OrderExecutionLineage] = {}
    command_keys_by_id: dict[str, str] = {}
    for result in records:
        record = result.record
        if record.kind in {"order_command.v1", "order_command.v2"}:
            try:
                command = order_command_from_record(record)
            except (KeyError, TypeError, ValueError) as error:
                raise ProjectionRecoveryError(
                    f"invalid order command record {record.record_id}: {error}"
                ) from error
            if (
                command.idempotency_key in lineages
                or command.command_id in command_keys_by_id
            ):
                raise ProjectionRecoveryError("order command lineage is duplicated")
            raw_admission = record.payload.get("no_overnight_admission")
            initial = None
            if raw_admission is not None:
                if not isinstance(raw_admission, Mapping):
                    raise ProjectionRecoveryError(
                        "order command admission payload is invalid"
                    )
                try:
                    initial = ExecutionAdmissionDecision.from_payload(raw_admission)
                except (KeyError, TypeError, ValueError) as error:
                    raise ProjectionRecoveryError(
                        "order command admission payload is invalid"
                    ) from error
            raw_risk_status = record.payload.get("risk_status")
            risk_status = (
                raw_risk_status if type(raw_risk_status) is str else None
            )
            lineage = _OrderExecutionLineage(
                command=command,
                command_sequence=result.sequence,
                risk_status=risk_status,
                initial_admission=initial,
            )
            lineages[command.idempotency_key] = lineage
            command_keys_by_id[command.command_id] = command.idempotency_key
            continue
        if record.kind == "no_overnight_final_admission_failure.v1":
            if set(record.payload) != {"command_id", "error_type"}:
                raise ProjectionRecoveryError(
                    "final admission failure fields are invalid"
                )
            try:
                command_id = require_json_string(
                    record.payload.get("command_id"),
                    "command_id",
                )
                require_json_string(
                    record.payload.get("error_type"),
                    "error_type",
                )
            except ValueError as error:
                raise ProjectionRecoveryError(
                    "final admission failure payload is invalid"
                ) from error
            idempotency_key = command_keys_by_id.get(command_id)
            lineage = (
                lineages.get(idempotency_key)
                if idempotency_key is not None
                else None
            )
            if (
                lineage is None
                or lineage.command.command_id != command_id
                or lineage.final_admission_failure_sequence is not None
            ):
                raise ProjectionRecoveryError(
                    "final admission failure lineage is invalid"
                )
            lineage.final_admission_failure_sequence = result.sequence
            continue
        if record.kind != "no_overnight_final_admission.v1":
            continue
        if set(record.payload) != {
            "command_id",
            "idempotency_key",
            "expected_admission_revision",
            "decision",
        }:
            raise ProjectionRecoveryError("final admission fields are invalid")
        raw_decision = record.payload.get("decision")
        idempotency_key = record.payload.get("idempotency_key")
        command_id = record.payload.get("command_id")
        expected_revision = record.payload.get("expected_admission_revision")
        if (
            not isinstance(raw_decision, Mapping)
            or type(idempotency_key) is not str
            or type(command_id) is not str
            or type(expected_revision) is not str
        ):
            raise ProjectionRecoveryError("final admission payload is invalid")
        try:
            decision = ExecutionAdmissionDecision.from_payload(raw_decision)
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError("final admission payload is invalid") from error
        lineage = lineages.get(idempotency_key)
        initial = None if lineage is None else lineage.initial_admission
        if (
            lineage is None
            or lineage.command.command_id != command_id
            or command_keys_by_id.get(command_id) != idempotency_key
            or lineage.risk_status != "APPROVED"
            or initial is None
            or initial.status is not ExecutionAdmissionStatus.APPROVED
            or initial.admission_revision != expected_revision
            or not decision.final_check
            or lineage.final_admission is not None
            or result.sequence <= lineage.command_sequence
            or lineage.final_admission_failure_sequence is not None
            or (
                decision.status is ExecutionAdmissionStatus.APPROVED
                and decision.admission_revision != expected_revision
            )
        ):
            raise ProjectionRecoveryError("final admission lineage is invalid")
        lineage.final_admission = decision
        lineage.final_admission_sequence = result.sequence

    for result in records:
        record = result.record
        if record.kind != LOCAL_PAPER_ORDER_STATE_V2_KIND:
            continue
        state = _validated_v2_order_state_payload(record)
        idempotency_key = require_json_string(
            state["idempotency_key"], "idempotency_key"
        )
        lineage = lineages.get(idempotency_key)
        if lineage is None:
            raise ProjectionRecoveryError(
                "v2 order state has no matching order command"
            )
        _require_v2_state_command_match(state, lineage.command)
        order_id = require_json_string(state["order_id"], "order_id")
        if lineage.order_id is not None and lineage.order_id != order_id:
            raise ProjectionRecoveryError(
                "v2 order state order_id conflicts within command lineage"
            )
        lineage.order_id = order_id

    admission_boundary_seen = False
    filled_quantity_by_command: dict[str, int] = {}
    fill_count_by_command: dict[str, int] = {}
    cumulative_gross_by_command: dict[str, Decimal] = {}
    cumulative_commission_by_command: dict[str, Decimal] = {}
    cumulative_tax_by_command: dict[str, Decimal] = {}
    cumulative_slippage_by_command: dict[str, Decimal] = {}
    for result in records:
        record = result.record
        if record.kind in {"order_command.v1", "order_command.v2"}:
            if record.payload.get("no_overnight_admission") is not None:
                admission_boundary_seen = True
            continue
        if record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND:
            state = _validated_v2_order_state_payload(record)
            idempotency_key = require_json_string(
                state["idempotency_key"], "idempotency_key"
            )
            lineage = lineages[idempotency_key]
            _require_execution_fact_admission(
                lineage,
                fact_kind=record.kind,
                fact_sequence=result.sequence,
                state_status=state["status"],
            )
            _require_v2_state_fill_match(
                state,
                lineage.command,
                filled_quantity=filled_quantity_by_command.get(
                    idempotency_key, 0
                ),
                fill_count=fill_count_by_command.get(idempotency_key, 0),
                cumulative_gross=cumulative_gross_by_command.get(
                    idempotency_key, Decimal("0")
                ),
                cumulative_commission=cumulative_commission_by_command.get(
                    idempotency_key, Decimal("0")
                ),
                cumulative_tax=cumulative_tax_by_command.get(
                    idempotency_key, Decimal("0")
                ),
                cumulative_slippage=cumulative_slippage_by_command.get(
                    idempotency_key, Decimal("0")
                ),
            )
            lineage.latest_state_record_sequence = result.sequence
            continue
        if record.kind != LOCAL_PAPER_FILL_V4_KIND:
            continue
        fill = LocalPaperExposureFill.from_record(record)
        raw_command_id = record.payload.get("command_id")
        raw_idempotency_key = record.payload.get("command_idempotency_key")
        if raw_command_id is None and raw_idempotency_key is None:
            if admission_boundary_seen:
                raise ProjectionRecoveryError(
                    "unlinked v4 fill follows an admission-bearing command"
                )
            continue
        command_id = require_json_string(raw_command_id, "command_id")
        idempotency_key = require_json_string(
            raw_idempotency_key,
            "command_idempotency_key",
        )
        lineage = lineages.get(idempotency_key)
        if lineage is None or lineage.command.command_id != command_id:
            raise ProjectionRecoveryError("v4 fill command lineage is invalid")
        _require_execution_fact_admission(
            lineage,
            fact_kind=record.kind,
            fact_sequence=result.sequence,
        )
        if lineage.order_id is None:
            lineage.order_id = fill.order_id
        elif lineage.order_id != fill.order_id:
            raise ProjectionRecoveryError(
                "v4 fill order_id does not match command"
            )
        _require_v4_fill_command_match(
            fill,
            lineage.command,
            expected_order_id=lineage.order_id,
            payload=record.payload,
        )
        filled_quantity = (
            filled_quantity_by_command.get(idempotency_key, 0)
            + fill.quantity_shares
        )
        fill_count = fill_count_by_command.get(idempotency_key, 0) + 1
        if filled_quantity > lineage.command.quantity_shares:
            raise ProjectionRecoveryError("v4 cumulative fill exceeds command")
        if record.payload.get("fill_sequence") != fill_count:
            raise ProjectionRecoveryError("v4 fill sequence does not match command")
        cumulative_gross = (
            cumulative_gross_by_command.get(idempotency_key, Decimal("0"))
            + Decimal(str(record.payload["gross_amount"]))
        )
        cumulative_commission = (
            cumulative_commission_by_command.get(
                idempotency_key, Decimal("0")
            )
            + fill.commission
        )
        cumulative_tax = (
            cumulative_tax_by_command.get(idempotency_key, Decimal("0"))
            + fill.tax
        )
        cumulative_slippage = (
            cumulative_slippage_by_command.get(
                idempotency_key, Decimal("0")
            )
            + Decimal(str(record.payload["slippage_cost"]))
        )
        if (
            Decimal(str(record.payload["cumulative_order_gross"]))
            != cumulative_gross
            or Decimal(str(record.payload["cumulative_order_commission"]))
            != cumulative_commission
            or Decimal(str(record.payload["cumulative_order_tax"]))
            != cumulative_tax
        ):
            raise ProjectionRecoveryError(
                "v4 fill cumulative accounting does not match command lineage"
            )
        filled_quantity_by_command[idempotency_key] = filled_quantity
        fill_count_by_command[idempotency_key] = fill_count
        cumulative_gross_by_command[idempotency_key] = cumulative_gross
        cumulative_commission_by_command[idempotency_key] = cumulative_commission
        cumulative_tax_by_command[idempotency_key] = cumulative_tax
        cumulative_slippage_by_command[idempotency_key] = cumulative_slippage
        lineage.latest_fill_record_sequence = result.sequence
    return lineages


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
        self._v4_exposure_projection: LocalPaperExposureProjection | None = None
        self._last_sequence = 0

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def starting_cash(self) -> Decimal:
        return self._starting_cash

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
        if result.record.kind == LOCAL_PAPER_V1_IMPORTED_KIND:
            self._activate_v4_exposure_projection(result)
        elif result.record.kind in {
            LOCAL_PAPER_FILL_KIND,
            LOCAL_PAPER_FILL_V2_KIND,
            LOCAL_PAPER_FILL_V3_KIND,
            LOCAL_PAPER_FILL_V4_KIND,
        }:
            if (
                result.record.kind
                in {LOCAL_PAPER_FILL_V3_KIND, LOCAL_PAPER_FILL_V4_KIND}
                and self._settings_digest is None
            ):
                raise ProjectionRecoveryError(
                    "local-paper v3 recovery requires session settings digest"
                )
            if self._settings_digest is not None and (
                result.record.kind
                not in {
                    LOCAL_PAPER_FILL_V2_KIND,
                    LOCAL_PAPER_FILL_V3_KIND,
                    LOCAL_PAPER_FILL_V4_KIND,
                }
                or result.record.payload.get("settings_digest")
                != self._settings_digest
            ):
                raise ProjectionRecoveryError(
                    "Journal fill settings digest conflicts with session"
                )
            fill = LocalPaperFill.from_record(result.record)
            v3_accounting = (
                self._validated_v3_order_accounting(result.record, fill)
                if result.record.kind
                in {LOCAL_PAPER_FILL_V3_KIND, LOCAL_PAPER_FILL_V4_KIND}
                else None
            )
            if result.record.kind == LOCAL_PAPER_FILL_V4_KIND:
                self._apply_v4_fill(
                    result,
                    fill=fill,
                    occurred_at=result.record.occurred_at,
                )
            else:
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

    def _activate_v4_exposure_projection(
        self,
        result: JournalAppendResult,
    ) -> None:
        if self._v4_exposure_projection is not None:
            raise ProjectionRecoveryError("local-paper v1 import is duplicated")
        account_scope_id = result.record.payload.get("account_scope_id")
        policy_family_id = result.record.payload.get("policy_family_id")
        if type(account_scope_id) is not str or type(policy_family_id) is not str:
            raise ProjectionRecoveryError(
                "local-paper v1 import identity is invalid"
            )
        projection = LocalPaperExposureProjection(
            starting_cash=self._starting_cash,
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
            settings_digest=self._settings_digest,
        )
        projection.apply(result)
        if projection.cash != self._cash:
            raise ProjectionRecoveryError(
                "local-paper v1 import cash conflicts with monetary projection"
            )
        self._require_v4_projection_parity(projection)
        self._v4_exposure_projection = projection

    def _apply_v4_fill(
        self,
        result: JournalAppendResult,
        *,
        fill: LocalPaperFill,
        occurred_at: datetime,
    ) -> None:
        projection = self._v4_exposure_projection
        if projection is None:
            raise ProjectionRecoveryError(
                "local-paper v4 fill requires a prior identity import"
            )
        projection.apply(result)
        self._cash = projection.cash
        self._refresh_v4_aggregate(projection)
        if fill.side is LocalPaperSide.BUY:
            value = fill.gross_amount or fill.quantity_shares * fill.fill_price
            trading_date = occurred_at.date()
            self._buy_notional_by_date[trading_date] = (
                self._buy_notional_by_date.get(trading_date, Decimal("0"))
                + value
            )

    def _require_v4_projection_parity(
        self,
        projection: "LocalPaperExposureProjection",
    ) -> None:
        aggregated = self._v4_aggregate(projection)
        current = {
            symbol: (
                position.quantity_shares,
                position.average_price,
                position.commission_cost,
            )
            for symbol, position in self._positions.items()
        }
        projected = {
            symbol: (
                int(state["quantity"]),
                Decimal(str(state["average_price"])),
                Decimal(str(state["commission_cost"])),
            )
            for symbol, state in aggregated.items()
        }
        if current != projected:
            raise ProjectionRecoveryError(
                "local-paper v1 import positions conflict with monetary projection"
            )
        realized: dict[str, Decimal] = {}
        symbols_by_exposure = {
            str(dict(state["exposure_identity"])["exposure_id"]): str(
                state["symbol"]
            )
            for state in projection.exposure_states
        }
        for exposure_id, value in projection.realized_pnl_by_exposure.items():
            symbol = symbols_by_exposure[exposure_id]
            realized[symbol] = realized.get(symbol, Decimal("0")) + value
        symbols = set(realized) | set(self._realized_pnl)
        if any(
            realized.get(symbol, Decimal("0"))
            != self._realized_pnl.get(symbol, Decimal("0"))
            for symbol in symbols
        ):
            raise ProjectionRecoveryError(
                "local-paper v1 import realized PnL conflicts with monetary projection"
            )

    @staticmethod
    def _v4_aggregate(
        projection: "LocalPaperExposureProjection",
    ) -> dict[str, dict[str, object]]:
        aggregated: dict[str, dict[str, object]] = {}
        for state in projection.exposure_states:
            quantity = int(state["quantity"])
            if quantity <= 0:
                continue
            symbol = str(state["symbol"])
            current = aggregated.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "name": str(state["name"]),
                    "quantity": 0,
                    "basis": Decimal("0"),
                    "commission_cost": Decimal("0"),
                    "owners": [],
                },
            )
            current["quantity"] = int(current["quantity"]) + quantity
            current["basis"] = Decimal(str(current["basis"])) + (
                Decimal(str(state["average_price"])) * quantity
            )
            current["commission_cost"] = Decimal(
                str(current["commission_cost"])
            ) + Decimal(str(state["commission_cost"]))
            owners = current["owners"]
            assert isinstance(owners, list)
            owners.append(state)
        return aggregated

    def _refresh_v4_aggregate(
        self,
        projection: "LocalPaperExposureProjection",
    ) -> None:
        aggregated = self._v4_aggregate(projection)
        positions: dict[str, LocalPaperPosition] = {}
        for symbol, state in aggregated.items():
            quantity = int(state["quantity"])
            owners = state["owners"]
            assert isinstance(owners, list) and owners
            first = owners[0]
            assert isinstance(first, Mapping)
            same_owner = all(
                item.get("owner_origin") == first.get("owner_origin")
                and item.get("owner_strategy_id")
                == first.get("owner_strategy_id")
                and item.get("owner_strategy_version")
                == first.get("owner_strategy_version")
                for item in owners
                if isinstance(item, Mapping)
            )
            positions[symbol] = LocalPaperPosition(
                symbol=symbol,
                name=str(state["name"]),
                quantity_shares=quantity,
                average_price=Decimal(str(state["basis"])) / quantity,
                commission_cost=Decimal(str(state["commission_cost"])),
                owner_origin=(
                    str(first["owner_origin"])
                    if same_owner
                    else "MIXED_EXPOSURE"
                ),
                owner_strategy_id=(
                    first.get("owner_strategy_id") if same_owner else None
                ),
                owner_strategy_version=(
                    first.get("owner_strategy_version") if same_owner else None
                ),
            )
        self._positions = positions
        symbols_by_exposure = {
            str(dict(state["exposure_identity"])["exposure_id"]): str(
                state["symbol"]
            )
            for state in projection.exposure_states
        }
        realized: dict[str, Decimal] = {}
        for exposure_id, value in projection.realized_pnl_by_exposure.items():
            symbol = symbols_by_exposure[exposure_id]
            realized[symbol] = realized.get(symbol, Decimal("0")) + value
        self._realized_pnl = realized

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


class LocalPaperExposureProjection:
    """Pure v2 reducer whose accounting mutation key is `exposure_id`."""

    def __init__(
        self,
        *,
        starting_cash: Decimal,
        account_scope_id: str,
        policy_family_id: str,
        settings_digest: str | None = None,
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        if not account_scope_id.strip() or not policy_family_id.strip():
            raise ValueError("v2 projection identity must not be empty")
        if settings_digest is not None:
            _validate_sha256(settings_digest, "settings_digest")
        self._starting_cash = starting_cash
        self._cash = starting_cash
        self._account_scope_id = account_scope_id
        self._policy_family_id = policy_family_id
        self._settings_digest = settings_digest
        self._positions: dict[str, LocalPaperExposurePosition] = {}
        self._identities: dict[str, ExposureIdentity] = {}
        self._symbols: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._strategy_versions: dict[str, str | None] = {}
        self._realized_pnl: dict[str, Decimal] = {}
        self._last_sequence = 0
        self._import_source_digest: str | None = None

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    @property
    def positions(self) -> tuple[LocalPaperExposurePosition, ...]:
        return tuple(
            sorted(
                self._positions.values(),
                key=lambda item: (item.symbol, item.exposure.exposure_id),
            )
        )

    @property
    def realized_pnl_by_exposure(self) -> Mapping[str, Decimal]:
        return dict(self._realized_pnl)

    @property
    def exposure_states(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            {
                "exposure_identity": identity.to_payload(),
                "symbol": self._symbols[exposure_id],
                "name": self._names[exposure_id],
                "quantity": (
                    self._positions[exposure_id].quantity_shares
                    if exposure_id in self._positions
                    else 0
                ),
                "average_price": (
                    self._positions[exposure_id].average_price
                    if exposure_id in self._positions
                    else Decimal("0")
                ),
                "commission_cost": (
                    self._positions[exposure_id].commission_cost
                    if exposure_id in self._positions
                    else Decimal("0")
                ),
                "owner_origin": identity.owner_origin,
                "owner_strategy_id": (
                    identity.owner_id
                    if identity.owner_origin == "STRATEGY_AUTOMATED"
                    else None
                ),
                "owner_strategy_version": self._strategy_versions.get(exposure_id),
            }
            for exposure_id, identity in sorted(self._identities.items())
        )

    def position(self, exposure_id: str) -> LocalPaperExposurePosition | None:
        return self._positions.get(exposure_id)

    def realized_pnl(self, exposure_id: str) -> Decimal:
        return self._realized_pnl.get(exposure_id, Decimal("0"))

    def aggregate_quantity(self, symbol: str) -> int:
        return sum(
            position.quantity_shares
            for position in self._positions.values()
            if position.symbol == symbol
        )

    def apply(self, result: JournalAppendResult) -> None:
        if result.sequence <= self._last_sequence:
            raise ProjectionRecoveryError("Journal sequence must be strictly increasing")
        record = result.record
        if record.kind == LOCAL_PAPER_V1_IMPORTED_KIND:
            self._apply_import(record)
        elif record.kind == LOCAL_PAPER_FILL_V4_KIND:
            if self._settings_digest is None:
                raise ProjectionRecoveryError(
                    "local-paper v4 recovery requires session settings digest"
                )
            if record.payload.get("settings_digest") != self._settings_digest:
                raise ProjectionRecoveryError(
                    "Journal v4 fill settings digest conflicts with session"
                )
            self._apply_fill(LocalPaperExposureFill.from_record(record))
        self._last_sequence = result.sequence

    @property
    def digest(self) -> str:
        payload = {
            "projection_name": LOCAL_PAPER_V2_PROJECTION_NAME,
            "starting_cash": str(self._starting_cash),
            "cash": str(self._cash),
            "account_scope_id": self._account_scope_id,
            "policy_family_id": self._policy_family_id,
            **(
                {"settings_digest": self._settings_digest}
                if self._settings_digest is not None
                else {}
            ),
            "last_sequence": self._last_sequence,
            "import_source_digest": self._import_source_digest,
            "exposures": [
                {
                    "exposure_identity": identity.to_payload(),
                    "symbol": self._symbols[exposure_id],
                    "name": self._names[exposure_id],
                    "owner_strategy_version": self._strategy_versions.get(
                        exposure_id
                    ),
                    "quantity_shares": (
                        self._positions[exposure_id].quantity_shares
                        if exposure_id in self._positions
                        else 0
                    ),
                    "average_price": (
                        str(self._positions[exposure_id].average_price)
                        if exposure_id in self._positions
                        else "0"
                    ),
                    "commission_cost": (
                        str(self._positions[exposure_id].commission_cost)
                        if exposure_id in self._positions
                        else "0"
                    ),
                    "realized_pnl": str(
                        self._realized_pnl.get(exposure_id, Decimal("0"))
                    ),
                }
                for exposure_id, identity in sorted(self._identities.items())
            ],
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def _validate_identity(self, exposure: ExposureIdentity) -> None:
        if exposure.account_scope_id != self._account_scope_id:
            raise ProjectionRecoveryError("exposure account scope mismatch")
        if exposure.policy_family_id != self._policy_family_id:
            raise ProjectionRecoveryError("exposure policy family mismatch")

    def _register_identity(
        self,
        exposure: ExposureIdentity,
        symbol: str,
        *,
        name: str,
        owner_strategy_version: str | None = None,
    ) -> None:
        self._validate_identity(exposure)
        existing = self._identities.get(exposure.exposure_id)
        if existing is not None and existing != exposure:
            raise ProjectionRecoveryError("exposure identity content mismatch")
        existing_symbol = self._symbols.get(exposure.exposure_id)
        if existing_symbol is not None and existing_symbol != symbol:
            raise ProjectionRecoveryError("exposure symbol mismatch")
        self._identities[exposure.exposure_id] = exposure
        self._symbols[exposure.exposure_id] = symbol
        existing_name = self._names.get(exposure.exposure_id)
        if existing_name is not None and existing_name != name:
            raise ProjectionRecoveryError("exposure name mismatch")
        self._names[exposure.exposure_id] = name
        existing_version = self._strategy_versions.get(exposure.exposure_id)
        if (
            existing_version is not None
            and owner_strategy_version is not None
            and existing_version != owner_strategy_version
        ):
            raise ProjectionRecoveryError("exposure strategy version mismatch")
        if owner_strategy_version is not None:
            self._strategy_versions[exposure.exposure_id] = owner_strategy_version
        else:
            self._strategy_versions.setdefault(exposure.exposure_id, None)

    def _apply_fill(self, fill: LocalPaperExposureFill) -> None:
        exposure_id = fill.exposure.exposure_id
        self._register_identity(
            fill.exposure,
            fill.symbol,
            name=fill.name,
            owner_strategy_version=fill.owner_strategy_version,
        )
        value = fill.quantity_shares * fill.fill_price
        current = self._positions.get(exposure_id)
        if fill.side is LocalPaperSide.BUY:
            if -fill.cash_effect > self._cash:
                raise ProjectionRecoveryError("Journal fill exceeds available cash")
            if current is None:
                self._positions[exposure_id] = LocalPaperExposurePosition(
                    exposure=fill.exposure,
                    symbol=fill.symbol,
                    name=fill.name,
                    quantity_shares=fill.quantity_shares,
                    average_price=fill.fill_price,
                    commission_cost=fill.commission,
                    owner_strategy_version=fill.owner_strategy_version,
                )
            else:
                quantity = current.quantity_shares + fill.quantity_shares
                self._positions[exposure_id] = replace(
                    current,
                    quantity_shares=quantity,
                    average_price=(
                        current.average_price * current.quantity_shares + value
                    )
                    / quantity,
                    commission_cost=current.commission_cost + fill.commission,
                )
            self._cash += fill.cash_effect
            return

        if current is None or current.quantity_shares < fill.quantity_shares:
            raise ProjectionRecoveryError("Journal sell fill exceeds target exposure")
        allocated_buy_commission = (
            current.commission_cost * fill.quantity_shares / current.quantity_shares
        )
        self._cash += fill.cash_effect
        self._realized_pnl[exposure_id] = (
            self.realized_pnl(exposure_id)
            + (fill.fill_price - current.average_price) * fill.quantity_shares
            - allocated_buy_commission
            - fill.commission
            - fill.tax
        )
        remaining = current.quantity_shares - fill.quantity_shares
        if remaining == 0:
            del self._positions[exposure_id]
        else:
            self._positions[exposure_id] = replace(
                current,
                quantity_shares=remaining,
                commission_cost=current.commission_cost - allocated_buy_commission,
            )

    def _apply_import(self, record: JournalRecord) -> None:
        if self._import_source_digest is not None or self._identities:
            raise ProjectionRecoveryError("v1 import manifest may be applied only once")
        payload = record.payload
        try:
            if str(payload["account_scope_id"]) != self._account_scope_id:
                raise ProjectionRecoveryError("v1 import account scope mismatch")
            if str(payload["policy_family_id"]) != self._policy_family_id:
                raise ProjectionRecoveryError("v1 import policy family mismatch")
            if Decimal(str(payload["source_starting_cash"])) != self._starting_cash:
                raise ProjectionRecoveryError("v1 import starting cash mismatch")
            source_cash = Decimal(str(payload["source_cash"]))
            source_digest = str(payload["source_digest"])
            exposures = payload["exposures"]
            if not isinstance(exposures, tuple):
                raise ValueError("import exposures must be an array")
        except (InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise ProjectionRecoveryError("invalid v1 import manifest") from error
        if len(source_digest) != 64:
            raise ProjectionRecoveryError("v1 import source digest is invalid")
        for raw in exposures:
            if not isinstance(raw, Mapping):
                raise ProjectionRecoveryError("invalid imported exposure")
            try:
                raw_identity = raw["exposure_identity"]
                if not isinstance(raw_identity, Mapping):
                    raise ValueError("identity must be an object")
                exposure = ExposureIdentity.from_payload(raw_identity)
                symbol = str(raw["symbol"])
                name = str(raw["name"])
                quantity = int(raw["quantity_shares"])
                average_price = Decimal(str(raw["average_price"]))
                commission_cost = Decimal(str(raw.get("commission_cost", "0")))
                realized = Decimal(str(raw["realized_pnl"]))
            except (InvalidOperation, KeyError, TypeError, ValueError) as error:
                raise ProjectionRecoveryError("invalid imported exposure") from error
            if exposure.no_overnight_managed:
                raise ProjectionRecoveryError("legacy import cannot create managed exposure")
            if (
                quantity < 0
                or average_price < 0
                or commission_cost < 0
                or not average_price.is_finite()
                or not commission_cost.is_finite()
                or not realized.is_finite()
            ):
                raise ProjectionRecoveryError("invalid imported exposure accounting")
            self._register_identity(exposure, symbol, name=name)
            self._realized_pnl[exposure.exposure_id] = realized
            if quantity > 0:
                self._positions[exposure.exposure_id] = LocalPaperExposurePosition(
                    exposure=exposure,
                    symbol=symbol,
                    name=name,
                    quantity_shares=quantity,
                    average_price=average_price,
                    commission_cost=commission_cost,
                )
        if not source_cash.is_finite() or source_cash < 0:
            raise ProjectionRecoveryError("invalid v1 import cash")
        self._cash = source_cash
        self._import_source_digest = source_digest


def build_local_paper_v1_import_record(
    *,
    source_projection: LocalPaperProjection,
    source_session_id: str,
    target_session_id: str,
    account_scope_id: str,
    policy_family_id: str,
    occurred_at: datetime,
) -> JournalRecord:
    """Freeze one deterministic snapshot manifest from immutable v1 facts."""

    active = {position.symbol: position for position in source_projection.positions}
    symbols = sorted({*active, *source_projection.realized_pnl_by_symbol})
    exposures: list[dict[str, object]] = []
    for symbol in symbols:
        position = active.get(symbol)
        owner_origin = position.owner_origin if position is not None else "MANUAL_WEB"
        owner_id = (
            position.owner_strategy_id
            if position is not None and position.owner_strategy_id is not None
            else "manual-web"
        )
        exposure = build_legacy_exposure_identity(
            account_scope_id=account_scope_id,
            policy_family_id=policy_family_id,
            source_session_id=source_session_id,
            symbol=symbol,
            owner_origin=owner_origin,
            owner_id=owner_id,
        )
        exposures.append(
            {
                "exposure_identity": exposure.to_payload(),
                "symbol": symbol,
                "name": position.name if position is not None else symbol,
                "quantity_shares": (
                    position.quantity_shares if position is not None else 0
                ),
                "average_price": (
                    str(position.average_price) if position is not None else "0"
                ),
                "commission_cost": (
                    str(position.commission_cost) if position is not None else "0"
                ),
                "realized_pnl": str(source_projection.realized_pnl(symbol)),
            }
        )
    return JournalRecord(
        record_id=f"local-paper-v1-imported:{source_session_id}",
        session_id=target_session_id,
        kind=LOCAL_PAPER_V1_IMPORTED_KIND,
        occurred_at=occurred_at,
        payload={
            "source_session_id": source_session_id,
            "source_terminal_sequence": source_projection.last_sequence,
            "source_digest": source_projection.digest,
            "source_starting_cash": str(source_projection.starting_cash),
            "source_cash": str(source_projection.cash),
            "account_scope_id": account_scope_id,
            "policy_family_id": policy_family_id,
            "exposures": exposures,
        },
        idempotency_scope=f"{target_session_id}:v1-import-manifest",
        idempotency_key=source_session_id,
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


def rebuild_local_paper_v2_projection(
    journal: JournalRepository,
    *,
    session_id: str,
    starting_cash: Decimal,
    account_scope_id: str,
    policy_family_id: str,
    settings_digest: str | None = None,
    require_checkpoint: bool = True,
) -> LocalPaperExposureProjection:
    """Replay one identity-enabled ledger and verify its exposure checkpoint."""

    session = journal.session(session_id)
    if session is None:
        raise ProjectionRecoveryError("local-paper v2 session is missing")
    metadata_scope = session.metadata.get("account_scope_id")
    if metadata_scope is not None and metadata_scope != account_scope_id:
        raise ProjectionRecoveryError("local-paper v2 session scope mismatch")
    metadata_family = session.metadata.get("policy_family_id")
    if metadata_family is not None and metadata_family != policy_family_id:
        raise ProjectionRecoveryError("local-paper v2 session family mismatch")
    records = journal.records(session_id)
    _validated_order_execution_lineages(records)
    manifests = [
        result.record
        for result in records
        if result.record.kind == LOCAL_PAPER_V1_IMPORTED_KIND
    ]
    if len(manifests) != 1:
        raise ProjectionRecoveryError(
            "local-paper v2 requires exactly one v1 import manifest"
        )
    manifest = manifests[0]
    expected_predecessor = session.metadata.get("predecessor_session_id")
    expected_sequence = session.metadata.get("predecessor_terminal_sequence")
    expected_digest = session.metadata.get("predecessor_digest")
    predecessor_fence = (
        expected_predecessor,
        expected_sequence,
        expected_digest,
    )
    if any(value is not None for value in predecessor_fence):
        if not isinstance(expected_predecessor, str) or not expected_predecessor:
            raise ProjectionRecoveryError(
                "local-paper v2 predecessor session is missing"
            )
        if isinstance(expected_sequence, bool) or not isinstance(
            expected_sequence, int
        ):
            raise ProjectionRecoveryError(
                "local-paper v2 predecessor sequence is invalid"
            )
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise ProjectionRecoveryError(
                "local-paper v2 predecessor digest is invalid"
            )
        if (
            manifest.payload.get("source_session_id") != expected_predecessor
            or manifest.payload.get("source_terminal_sequence") != expected_sequence
            or manifest.payload.get("source_digest") != expected_digest
        ):
            raise ProjectionRecoveryError(
                "local-paper v1 import manifest conflicts with predecessor fence"
            )
    elif manifest.payload.get("source_session_id") != session_id:
        raise ProjectionRecoveryError(
            "local-paper in-place import source session mismatch"
        )
    checkpoint = journal.latest_checkpoint(
        session_id,
        LOCAL_PAPER_V2_PROJECTION_NAME,
    )
    if require_checkpoint and checkpoint is None:
        raise ProjectionRecoveryError("local-paper v2 recovery requires a checkpoint")
    projection = LocalPaperExposureProjection(
        starting_cash=starting_cash,
        account_scope_id=account_scope_id,
        policy_family_id=policy_family_id,
        settings_digest=settings_digest,
    )
    checkpoint_digest = (
        projection.digest
        if checkpoint is not None and checkpoint.journal_sequence == 0
        else None
    )
    uncheckpointed_mutation = False
    for result in records:
        projection.apply(result)
        if checkpoint is not None and result.sequence == checkpoint.journal_sequence:
            checkpoint_digest = projection.digest
        elif (
            checkpoint is not None
            and result.sequence > checkpoint.journal_sequence
            and result.record.kind in _LOCAL_PAPER_V2_CHECKPOINT_MUTATION_KINDS
        ):
            uncheckpointed_mutation = True
    if checkpoint is not None:
        if checkpoint_digest is None:
            raise ProjectionRecoveryError(
                "local-paper v2 checkpoint sequence is absent from Journal"
            )
        if checkpoint_digest != checkpoint.digest:
            raise ProjectionRecoveryError(
                "local-paper v2 checkpoint digest mismatch"
            )
        if require_checkpoint and uncheckpointed_mutation:
            raise ProjectionRecoveryError(
                "local-paper v2 checkpoint does not cover Journal tail"
            )
    return projection


def write_local_paper_v2_checkpoint(
    journal: JournalRepository,
    *,
    session_id: str,
    starting_cash: Decimal,
    account_scope_id: str,
    policy_family_id: str,
    settings_digest: str | None = None,
) -> LocalPaperExposureProjection:
    projection = rebuild_local_paper_v2_projection(
        journal,
        session_id=session_id,
        starting_cash=starting_cash,
        account_scope_id=account_scope_id,
        policy_family_id=policy_family_id,
        settings_digest=settings_digest,
        require_checkpoint=False,
    )
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=session_id,
            projection_name=LOCAL_PAPER_V2_PROJECTION_NAME,
            journal_sequence=projection.last_sequence,
            digest=projection.digest,
        )
    )
    return projection


def latest_local_paper_order_states(
    journal: JournalRepository,
    *,
    session_id: str,
    require_integrity: bool = False,
) -> tuple[Mapping[str, object], ...]:
    """Return the latest durable state snapshot for every local-paper order."""

    from trading.application import order_command_from_record
    records = journal.records(session_id)
    lineages = _validated_order_execution_lineages(records)
    latest: dict[str, Mapping[str, object]] = {}
    commands_by_key: dict[str, OrderCommand] = {}
    approved_commands: dict[str, tuple[OrderCommand, JournalRecord]] = {}
    initial_admissions: dict[str, ExecutionAdmissionDecision] = {}
    for result in records:
        if result.record.kind in {"order_command.v1", "order_command.v2"}:
            try:
                command = order_command_from_record(result.record)
            except (KeyError, TypeError, ValueError) as error:
                raise ProjectionRecoveryError(
                    f"invalid order command record {result.record.record_id}: {error}"
                ) from error
            commands_by_key[command.idempotency_key] = command
            raw_admission = result.record.payload.get("no_overnight_admission")
            admission_approved = True
            if raw_admission is not None:
                if not isinstance(raw_admission, Mapping):
                    raise ProjectionRecoveryError(
                        "order command admission payload is invalid"
                    )
                admission_approved = (
                    admission := ExecutionAdmissionDecision.from_payload(raw_admission)
                ).status is ExecutionAdmissionStatus.APPROVED
                initial_admissions[command.command_id] = admission
            if (
                result.record.payload.get("risk_status") == "APPROVED"
                and admission_approved
            ):
                approved_commands[command.idempotency_key] = (
                    command,
                    result.record,
                )
            continue
        if result.record.kind == "no_overnight_final_admission.v1":
            if set(result.record.payload) != {
                "command_id",
                "idempotency_key",
                "expected_admission_revision",
                "decision",
            }:
                raise ProjectionRecoveryError("final admission fields are invalid")
            raw_decision = result.record.payload.get("decision")
            idempotency_key = result.record.payload.get("idempotency_key")
            command_id = result.record.payload.get("command_id")
            expected_revision = result.record.payload.get("expected_admission_revision")
            if (
                not isinstance(raw_decision, Mapping)
                or type(idempotency_key) is not str
                or type(command_id) is not str
                or type(expected_revision) is not str
            ):
                raise ProjectionRecoveryError("final admission payload is invalid")
            decision = ExecutionAdmissionDecision.from_payload(raw_decision)
            command = commands_by_key.get(idempotency_key)
            initial = initial_admissions.get(command_id)
            if (
                command is None
                or command.command_id != command_id
                or initial is None
                or initial.admission_revision != expected_revision
                or not decision.final_check
            ):
                raise ProjectionRecoveryError("final admission lineage is invalid")
            if decision.status is not ExecutionAdmissionStatus.APPROVED:
                approved_commands.pop(idempotency_key, None)
            continue
        if result.record.kind not in {
            LOCAL_PAPER_ORDER_STATE_KIND,
            LOCAL_PAPER_ORDER_STATE_V2_KIND,
        }:
            continue
        payload = _verified_order_state_payload(
            result.record,
            require_integrity=require_integrity,
        )
        state = (
            _validated_v2_order_state_payload(result.record)
            if result.record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND
            else payload
        )
        order_id = str(state.get("order_id") or "")
        if not order_id:
            raise ProjectionRecoveryError("order state record is missing order_id")
        if result.record.kind == LOCAL_PAPER_ORDER_STATE_V2_KIND:
            idempotency_key = require_json_string(
                state["idempotency_key"], "idempotency_key"
            )
            command = commands_by_key.get(idempotency_key)
            if command is None:
                raise ProjectionRecoveryError(
                    "v2 order state has no matching order command"
                )
            _require_v2_state_command_match(state, command)
        latest[order_id] = state
    for lineage in lineages.values():
        if (
            lineage.order_id is not None
            and lineage.latest_fill_record_sequence
            > lineage.latest_state_record_sequence
        ):
            latest.pop(lineage.order_id, None)
    represented_keys = {
        str(state.get("idempotency_key") or "") for state in latest.values()
    }
    for idempotency_key, (command, command_record) in approved_commands.items():
        if idempotency_key in represented_keys:
            continue
        quantity = command.quantity_shares
        latest[f"recovery-required:{command.command_id}"] = {
            "order_id": f"recovery-required:{command.command_id}",
            "idempotency_key": idempotency_key,
            "origin": command.origin.value,
            "strategy_id": command.strategy_id,
            "strategy_version": command.strategy_version,
            "symbol": command.symbol,
            "name": command.symbol,
            "side": command.side.value,
            "lots": quantity // 1_000 if quantity % 1_000 == 0 else None,
            "quantity_shares": quantity,
            "quantity": quantity,
            "remaining_quantity": quantity,
            "limit_price": canonical_decimal_string(command.limit_price),
            "status": "RECOVERY_REQUIRED",
            "submitted_at": command.requested_at.isoformat(),
            "updated_at": command_record.occurred_at.isoformat(),
            "filled_price": None,
            "filled_quantity": 0,
            "filled_amount": None,
            "last_fill_price": None,
            "last_fill_quantity": 0,
            "fill_sequence": 0,
            "reason": "COMMAND_ACKNOWLEDGEMENT_MISSING",
            "attempt": command.attempt,
            "predecessor_order_id": command.predecessor_order_id,
            "timeout_at": None,
            "expires_at": None,
            "trading_date": None,
            "opening_equity": None,
            **(
                {
                    "exposure_identity": command.exposure.to_payload(),
                    "position_action": command.position_action.value,
                    "target_exposure_id": command.target_exposure_id,
                    "execution_reason_category": (
                        command.execution_reason_category.value
                    ),
                    "execution_reason_code": command.execution_reason_code,
                }
                if command.exposure is not None
                else {}
            ),
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
