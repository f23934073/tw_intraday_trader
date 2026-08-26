"""Pure loaders for reviewed Trade Management Shadow input candidates."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from runtime.trade_management_operational_composition import LiveShadowDecisionPolicy
from trading.risk import CommandSide, RiskPolicy, RiskSnapshot


RISK_SNAPSHOT_PROVENANCE_VERSION = (
    "trade-management-risk-snapshot-provenance-v1"
)
TAIPEI_FIXED_OFFSET = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class RiskSnapshotProvenance:
    session_id: str
    symbol: str
    market_date: date
    captured_at: datetime
    source_identity: str
    version: str = RISK_SNAPSHOT_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        if self.version != RISK_SNAPSHOT_PROVENANCE_VERSION:
            raise ValueError("unsupported RiskSnapshot provenance version")
        if not self.session_id.strip() or not self.source_identity.strip():
            raise ValueError("RiskSnapshot provenance identity must not be empty")
        if self.symbol != self.symbol.strip().upper() or not self.symbol:
            raise ValueError("RiskSnapshot provenance symbol must be normalized")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("RiskSnapshot captured_at must be timezone-aware")
        if self.captured_at.utcoffset() != timedelta(hours=8):
            raise ValueError("RiskSnapshot captured_at must use Asia/Taipei offset")
        if self.captured_at.date() != self.market_date:
            raise ValueError("RiskSnapshot captured_at must match market_date")

    def to_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "symbol": self.symbol,
            "market_date": self.market_date.isoformat(),
            "captured_at": self.captured_at.isoformat(),
            "source_identity": self.source_identity,
        }


def reviewed_risk_snapshot_preopen_window(
    market_date: date,
) -> tuple[datetime, datetime]:
    return (
        datetime.combine(market_date, time(8, 30), tzinfo=TAIPEI_FIXED_OFFSET),
        datetime.combine(market_date, time(9), tzinfo=TAIPEI_FIXED_OFFSET),
    )


def require_risk_snapshot_capture_window(
    provenance: RiskSnapshotProvenance,
    *,
    window_start: datetime,
    window_end: datetime,
    admitted_at: datetime | None = None,
) -> None:
    for value, field_name in (
        (window_start, "window_start"),
        (window_end, "window_end"),
        (admitted_at, "admitted_at"),
    ):
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError(f"{field_name} must be timezone-aware")
    if window_start >= window_end:
        raise ValueError("RiskSnapshot capture window must be positive")
    if not window_start <= provenance.captured_at < window_end:
        raise ValueError("RISK_SNAPSHOT_CAPTURE_OUTSIDE_PREOPEN_WINDOW")
    if admitted_at is not None and provenance.captured_at > admitted_at:
        raise ValueError("RISK_SNAPSHOT_CAPTURE_AFTER_ADMISSION")


def load_shadow_policy(
    path: Path,
    *,
    code_identity: str,
) -> LiveShadowDecisionPolicy:
    return parse_shadow_policy(path.read_bytes(), code_identity=code_identity)


def parse_shadow_policy(
    content: bytes,
    *,
    code_identity: str,
) -> LiveShadowDecisionPolicy:
    value = _read_json_bytes(content, "shadow_policy")
    risk = _mapping(value.get("risk_policy"), "risk_policy")
    sides = frozenset(
        CommandSide(str(item)) for item in risk.get("fresh_book_sides", ())
    )
    return LiveShadowDecisionPolicy(
        exit_policy_version=str(value["exit_policy_version"]),
        risk_policy=RiskPolicy(
            version=str(risk["version"]),
            allow_strategy_origin=_bool(
                risk["allow_strategy_origin"],
                "risk_policy.allow_strategy_origin",
            ),
            max_order_notional=Decimal(str(risk["max_order_notional"])),
            max_position_notional=Decimal(str(risk["max_position_notional"])),
            max_daily_loss=Decimal(str(risk["max_daily_loss"])),
            max_daily_buy_notional=(
                None
                if risk.get("max_daily_buy_notional") is None
                else Decimal(str(risk["max_daily_buy_notional"]))
            ),
            commission_rate=Decimal(str(risk.get("commission_rate", "0"))),
            minimum_commission=Decimal(str(risk.get("minimum_commission", "0"))),
            require_fresh_book=_bool(
                risk.get("require_fresh_book", False),
                "risk_policy.require_fresh_book",
            ),
            max_book_age_seconds=int(risk.get("max_book_age_seconds", 15)),
            fresh_book_sides=sides or frozenset(CommandSide),
        ),
        volume_baseline_shares=Decimal(str(value["volume_baseline_shares"])),
        shares_per_lot=int(value["shares_per_lot"]),
        remaining_quantity_shares=int(value["remaining_quantity_shares"]),
        fill_model_version=str(value["fill_model_version"]),
        code_identity=code_identity,
    )


def load_risk_snapshot(path: Path) -> RiskSnapshot:
    snapshot, _ = parse_risk_snapshot_document(path.read_bytes())
    return snapshot


def load_risk_snapshot_document(
    path: Path,
) -> tuple[RiskSnapshot, RiskSnapshotProvenance]:
    return parse_risk_snapshot_document(path.read_bytes())


def parse_risk_snapshot_document(
    content: bytes,
) -> tuple[RiskSnapshot, RiskSnapshotProvenance]:
    value = _read_json_bytes(content, "risk_snapshot")
    snapshot = RiskSnapshot(
        data_health_state=str(value["data_health_state"]),
        market_open=_bool(value["market_open"], "market_open"),
        instrument_tradable=_bool(
            value["instrument_tradable"],
            "instrument_tradable",
        ),
        available_cash=Decimal(str(value["available_cash"])),
        current_position_shares=int(value["current_position_shares"]),
        pending_buy_shares=int(value["pending_buy_shares"]),
        pending_sell_shares=int(value["pending_sell_shares"]),
        daily_realized_pnl=Decimal(str(value["daily_realized_pnl"])),
        daily_filled_buy_notional=Decimal(
            str(value.get("daily_filled_buy_notional", "0"))
        ),
        pending_buy_notional=Decimal(str(value.get("pending_buy_notional", "0"))),
        same_side_pending_order=_bool(
            value.get("same_side_pending_order", False),
            "same_side_pending_order",
        ),
        book_age_seconds=(
            None
            if value.get("book_age_seconds") is None
            else int(value["book_age_seconds"])
        ),
        daily_loss=(
            None
            if value.get("daily_loss") is None
            else Decimal(str(value["daily_loss"]))
        ),
    )
    provenance_value = _mapping(value.get("provenance"), "provenance")
    provenance = RiskSnapshotProvenance(
        version=str(provenance_value["version"]),
        session_id=str(provenance_value["session_id"]),
        symbol=str(provenance_value["symbol"]),
        market_date=date.fromisoformat(str(provenance_value["market_date"])),
        captured_at=datetime.fromisoformat(str(provenance_value["captured_at"])),
        source_identity=str(provenance_value["source_identity"]),
    )
    return snapshot, provenance


def _read_json_bytes(content: bytes, source_name: str) -> dict[str, object]:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError(f"{source_name} must contain one JSON object")
    return value


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a JSON boolean")
    return value
