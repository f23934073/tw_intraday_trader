"""Persistent, editable settings for the local-only paper account."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from threading import RLock
from typing import Mapping
from uuid import uuid4

from config.local_paper import (
    LOCAL_PAPER_DEFAULT_COMMISSION_RATE,
    LOCAL_PAPER_DEFAULT_DAILY_BUY_LIMIT_TWD,
    LOCAL_PAPER_DEFAULT_MINIMUM_COMMISSION_TWD,
    LOCAL_PAPER_DEFAULT_STARTING_CASH_TWD,
    LOCAL_PAPER_V2_DEFAULT_SLIPPAGE_BPS,
)
from simulation.execution_costs import (
    CALIBRATION_STATUS,
    COMMISSION_RATE,
    FEE_POLICY_VERSION,
    MINIMUM_COMMISSION_TWD,
    MONEY_QUANTUM as V2_MONEY_QUANTUM,
    PRICE_TICK_POLICY_VERSION,
    ROUNDING_POLICY_VERSION,
    SELL_TAX_RATE,
    SLIPPAGE_POLICY_VERSION,
    cumulative_commission_for,
)
from trading.canonical_values import canonical_decimal_string


SETTINGS_SCHEMA_V1 = "local-paper-settings-v1"
SETTINGS_SCHEMA_V2 = "local-paper-settings-v2"
SETTINGS_SCHEMA_VERSION = SETTINGS_SCHEMA_V1
MONEY_QUANTUM = Decimal("0.01")


class LocalPaperSettingsConflict(ValueError):
    """A stale browser revision attempted to overwrite newer settings."""


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 必須是有限數字") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} 必須是有限數字")
    return parsed


@dataclass(frozen=True)
class LocalPaperSettings:
    starting_cash_twd: Decimal
    max_daily_buy_notional_twd: Decimal
    commission_rate: Decimal
    minimum_commission_twd: Decimal
    slippage_bps: Decimal = Decimal("0")
    schema_version: str = SETTINGS_SCHEMA_V1

    def __post_init__(self) -> None:
        for field_name in (
            "starting_cash_twd",
            "max_daily_buy_notional_twd",
            "commission_rate",
            "minimum_commission_twd",
            "slippage_bps",
        ):
            object.__setattr__(
                self,
                field_name,
                _decimal(getattr(self, field_name), field_name),
            )
        normalized_schema = str(self.schema_version).strip()
        if normalized_schema not in {SETTINGS_SCHEMA_V1, SETTINGS_SCHEMA_V2}:
            raise ValueError("不支援的 local-paper settings schema")
        object.__setattr__(self, "schema_version", normalized_schema)
        if self.starting_cash_twd <= 0:
            raise ValueError("starting_cash_twd 必須大於 0")
        if self.max_daily_buy_notional_twd <= 0:
            raise ValueError("max_daily_buy_notional_twd 必須大於 0")
        if not Decimal("0") <= self.commission_rate <= Decimal("0.01"):
            raise ValueError("commission_rate 必須介於 0 與 0.01")
        if self.minimum_commission_twd < 0:
            raise ValueError("minimum_commission_twd 不可小於 0")
        if not Decimal("0") <= self.slippage_bps <= Decimal("100"):
            raise ValueError("slippage_bps 必須介於 0 與 100")
        try:
            normalized_minimum = self.minimum_commission_twd.quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
        except InvalidOperation as error:
            raise ValueError("minimum_commission_twd 必須是有效金額") from error
        if normalized_minimum != self.minimum_commission_twd:
            raise ValueError("minimum_commission_twd 必須以 0.01 元為單位")
        if self.schema_version == SETTINGS_SCHEMA_V1:
            if self.slippage_bps != 0:
                raise ValueError("v1 settings 不支援 slippage_bps")
        elif (
            self.commission_rate != COMMISSION_RATE
            or self.minimum_commission_twd != MINIMUM_COMMISSION_TWD
        ):
            raise ValueError("v2 fee policy 必須使用 tw_stock_standard_v1")

    @classmethod
    def defaults(cls) -> "LocalPaperSettings":
        return cls(
            starting_cash_twd=Decimal(LOCAL_PAPER_DEFAULT_STARTING_CASH_TWD),
            max_daily_buy_notional_twd=Decimal(
                LOCAL_PAPER_DEFAULT_DAILY_BUY_LIMIT_TWD
            ),
            commission_rate=Decimal(LOCAL_PAPER_DEFAULT_COMMISSION_RATE),
            minimum_commission_twd=Decimal(
                LOCAL_PAPER_DEFAULT_MINIMUM_COMMISSION_TWD
            ),
        )

    @classmethod
    def v2_from_v1(
        cls,
        settings: "LocalPaperSettings",
    ) -> "LocalPaperSettings":
        return cls(
            starting_cash_twd=settings.starting_cash_twd,
            max_daily_buy_notional_twd=settings.max_daily_buy_notional_twd,
            commission_rate=COMMISSION_RATE,
            minimum_commission_twd=MINIMUM_COMMISSION_TWD,
            slippage_bps=Decimal(LOCAL_PAPER_V2_DEFAULT_SLIPPAGE_BPS),
            schema_version=SETTINGS_SCHEMA_V2,
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
        *,
        schema_version: str | None = None,
    ) -> "LocalPaperSettings":
        if not isinstance(value, Mapping):
            raise ValueError("local-paper settings 必須是 mapping")
        resolved_schema = str(
            schema_version
            or value.get("settings_schema_version")
            or SETTINGS_SCHEMA_V1
        ).strip()
        if resolved_schema == SETTINGS_SCHEMA_V2:
            if "slippage_bps" not in value:
                raise ValueError("v2 settings 缺少 slippage_bps")
            required = {
                "security_scope": "TWSE_TPEX_COMMON_STOCK",
                "order_condition": "CASH",
                "commission_rate": canonical_decimal_string(COMMISSION_RATE),
                "minimum_commission_twd": canonical_decimal_string(
                    MINIMUM_COMMISSION_TWD
                ),
                "sell_tax_rate": canonical_decimal_string(SELL_TAX_RATE),
                "money_quantum_twd": canonical_decimal_string(V2_MONEY_QUANTUM),
                "fee_policy_version": FEE_POLICY_VERSION,
                "rounding_policy_version": ROUNDING_POLICY_VERSION,
                "slippage_policy_version": SLIPPAGE_POLICY_VERSION,
                "price_tick_policy_version": PRICE_TICK_POLICY_VERSION,
                "calibration_status": CALIBRATION_STATUS,
            }
            if (
                value.get("day_trade") is not False
                or any(value.get(key) != expected for key, expected in required.items())
            ):
                raise ValueError("v2 settings policy identity 不完整或不一致")
        return cls(
            starting_cash_twd=_decimal(value["starting_cash_twd"], "starting_cash_twd"),
            max_daily_buy_notional_twd=_decimal(
                value["max_daily_buy_notional_twd"],
                "max_daily_buy_notional_twd",
            ),
            commission_rate=_decimal(value["commission_rate"], "commission_rate"),
            minimum_commission_twd=_decimal(
                value.get("minimum_commission_twd", "0"),
                "minimum_commission_twd",
            ),
            slippage_bps=_decimal(
                value.get("slippage_bps", "0"),
                "slippage_bps",
            ),
            schema_version=resolved_schema,
        )

    def to_dict(self) -> dict[str, object]:
        base = {
            "starting_cash_twd": canonical_decimal_string(
                self.starting_cash_twd
            ),
            "max_daily_buy_notional_twd": canonical_decimal_string(
                self.max_daily_buy_notional_twd
            ),
            "commission_rate": canonical_decimal_string(self.commission_rate),
            "minimum_commission_twd": canonical_decimal_string(
                self.minimum_commission_twd
            ),
        }
        if self.schema_version == SETTINGS_SCHEMA_V1:
            return base
        return {
            "settings_schema_version": SETTINGS_SCHEMA_V2,
            "starting_cash_twd": base["starting_cash_twd"],
            "max_daily_buy_notional_twd": base["max_daily_buy_notional_twd"],
            "slippage_bps": canonical_decimal_string(self.slippage_bps),
            "security_scope": "TWSE_TPEX_COMMON_STOCK",
            "order_condition": "CASH",
            "day_trade": False,
            "commission_rate": canonical_decimal_string(COMMISSION_RATE),
            "minimum_commission_twd": canonical_decimal_string(
                MINIMUM_COMMISSION_TWD
            ),
            "sell_tax_rate": canonical_decimal_string(SELL_TAX_RATE),
            "money_quantum_twd": canonical_decimal_string(V2_MONEY_QUANTUM),
            "fee_policy_version": FEE_POLICY_VERSION,
            "rounding_policy_version": ROUNDING_POLICY_VERSION,
            "slippage_policy_version": SLIPPAGE_POLICY_VERSION,
            "price_tick_policy_version": PRICE_TICK_POLICY_VERSION,
            "calibration_status": CALIBRATION_STATUS,
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def commission_for(self, gross: Decimal) -> Decimal:
        normalized = _decimal(gross, "gross")
        if normalized <= 0:
            return Decimal("0")
        if self.schema_version == SETTINGS_SCHEMA_V2:
            return cumulative_commission_for(normalized)
        calculated = (normalized * self.commission_rate).quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        return max(self.minimum_commission_twd, calculated)


@dataclass(frozen=True)
class LocalPaperSettingsState:
    revision: int
    active: LocalPaperSettings
    draft: LocalPaperSettings
    active_session_id: str
    active_settings_revision: int = 0
    draft_settings_revision: int = 0
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise ValueError("settings revision 不可小於 0")
        if self.active_settings_revision < 0 or self.draft_settings_revision < 0:
            raise ValueError("settings policy revision 不可小於 0")
        if self.active_settings_revision > self.revision:
            raise ValueError("active settings revision 不可超過 document revision")
        if self.draft_settings_revision > self.revision:
            raise ValueError("draft settings revision 不可超過 document revision")
        if not self.active_session_id.strip():
            raise ValueError("active_session_id 不可為空")

    @classmethod
    def defaults(cls) -> "LocalPaperSettingsState":
        settings = LocalPaperSettings.defaults()
        return cls(
            revision=0,
            active=settings,
            draft=settings,
            active_session_id="local-paper-runtime-v1",
            active_settings_revision=0,
            draft_settings_revision=0,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.document_schema_version,
            "revision": self.revision,
            "active": self.active.to_dict(),
            "draft": self.draft.to_dict(),
            "active_session_id": self.active_session_id,
            "active_settings_revision": self.active_settings_revision,
            "draft_settings_revision": self.draft_settings_revision,
            "updated_at": self.updated_at,
        }

    @property
    def document_schema_version(self) -> str:
        if (
            self.active.schema_version == SETTINGS_SCHEMA_V2
            or self.draft.schema_version == SETTINGS_SCHEMA_V2
        ):
            return SETTINGS_SCHEMA_V2
        return SETTINGS_SCHEMA_V1

    def v2_draft(self) -> LocalPaperSettings:
        if self.draft.schema_version == SETTINGS_SCHEMA_V2:
            return self.draft
        return LocalPaperSettings.v2_from_v1(self.draft)


class JsonLocalPaperSettingsRepository:
    """Single-process file store with revision checks and atomic replacement."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = RLock()

    def load(self) -> LocalPaperSettingsState:
        with self._lock:
            if not self._path.exists():
                return LocalPaperSettingsState.defaults()
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if not isinstance(raw, Mapping):
                    raise ValueError("local-paper settings document 必須是 mapping")
                document_schema = str(raw.get("schema_version") or "")
                if document_schema not in {SETTINGS_SCHEMA_V1, SETTINGS_SCHEMA_V2}:
                    raise ValueError("不支援的 local-paper settings schema")
                return LocalPaperSettingsState(
                    revision=int(raw["revision"]),
                    active=LocalPaperSettings.from_mapping(
                        raw["active"],
                        schema_version=(
                            SETTINGS_SCHEMA_V1
                            if document_schema == SETTINGS_SCHEMA_V1
                            else None
                        ),
                    ),
                    draft=LocalPaperSettings.from_mapping(
                        raw["draft"],
                        schema_version=(
                            SETTINGS_SCHEMA_V1
                            if document_schema == SETTINGS_SCHEMA_V1
                            else None
                        ),
                    ),
                    active_session_id=str(raw["active_session_id"]),
                    active_settings_revision=int(raw["active_settings_revision"]),
                    draft_settings_revision=int(raw["draft_settings_revision"]),
                    updated_at=(
                        str(raw["updated_at"])
                        if raw.get("updated_at") is not None
                        else None
                    ),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError("本機模擬設定檔損壞，已停止載入") from error

    def save_draft(
        self,
        settings: LocalPaperSettings,
        *,
        expected_revision: int,
        updated_at: datetime,
    ) -> LocalPaperSettingsState:
        with self._lock:
            current = self.load()
            self._require_revision(current, expected_revision)
            next_state = LocalPaperSettingsState(
                revision=current.revision + 1,
                active=current.active,
                draft=settings,
                active_session_id=current.active_session_id,
                active_settings_revision=current.active_settings_revision,
                draft_settings_revision=current.revision + 1,
                updated_at=updated_at.isoformat(),
            )
            self._write(next_state)
            return next_state

    def activate_draft(
        self,
        *,
        expected_revision: int,
        updated_at: datetime,
        session_id: str | None = None,
    ) -> LocalPaperSettingsState:
        with self._lock:
            current = self.load()
            self._require_revision(current, expected_revision)
            next_state = LocalPaperSettingsState(
                revision=current.revision + 1,
                active=current.draft,
                draft=current.draft,
                active_session_id=session_id or f"local-paper-runtime-{uuid4().hex}",
                active_settings_revision=current.draft_settings_revision,
                draft_settings_revision=current.draft_settings_revision,
                updated_at=updated_at.isoformat(),
            )
            self._write(next_state)
            return next_state

    def restore_active(
        self,
        previous: LocalPaperSettingsState,
        *,
        expected_revision: int,
        updated_at: datetime,
    ) -> LocalPaperSettingsState:
        """Restore the old active pointer after a post-activation apply failure."""

        with self._lock:
            current = self.load()
            self._require_revision(current, expected_revision)
            next_state = LocalPaperSettingsState(
                revision=current.revision + 1,
                active=previous.active,
                draft=current.draft,
                active_session_id=previous.active_session_id,
                active_settings_revision=previous.active_settings_revision,
                draft_settings_revision=current.draft_settings_revision,
                updated_at=updated_at.isoformat(),
            )
            self._write(next_state)
            return next_state

    @staticmethod
    def _require_revision(
        current: LocalPaperSettingsState,
        expected_revision: int,
    ) -> None:
        if current.revision != expected_revision:
            raise LocalPaperSettingsConflict("本機模擬設定已被其他頁面更新")

    def _write(self, state: LocalPaperSettingsState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f".{self._path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(
                    state.to_dict(),
                    stream,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            if temporary.exists():
                temporary.unlink()
