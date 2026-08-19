"""Fail-closed Tick/Kbar evidence capture for TAIFEX night sessions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from config.premarket import PremarketContextConfig
from premarket.artifacts import (
    PremarketArtifactRepository,
    canonical_json,
    create_raw_source_artifact,
    sha256_digest,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.models import (
    ContractIdentityStatus,
    QualificationCapture,
    QualificationReport,
    QualificationStatus,
    SessionWindow,
)


class QualificationNotEligible(RuntimeError):
    """The completed-session query cutoff has not been reached."""


class QualificationSource(Protocol):
    def supports_premarket_qualification(self) -> bool: ...

    def capture_taifex_night_qualification(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> QualificationCapture: ...


class PremarketQualificationService:
    def __init__(
        self,
        *,
        source: QualificationSource,
        calendar: TaifexTradingCalendar,
        config: PremarketContextConfig,
        artifacts: PremarketArtifactRepository,
        now: Callable[[], datetime],
    ) -> None:
        self._source = source
        self._calendar = calendar
        self._config = config
        self._artifacts = artifacts
        self._now = now

    def capture(self) -> QualificationReport:
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("qualification clock must be timezone-aware")
        local_now = now.astimezone(ZoneInfo(self._config.timezone))
        trading_date = self._calendar.trading_date_for(local_now)
        window = self._calendar.session_window(trading_date, self._config.query_delay)
        if local_now < window.query_not_before:
            raise QualificationNotEligible(
                f"qualification query is eligible at {window.query_not_before.isoformat()}"
            )
        if not self._source.supports_premarket_qualification():
            raise RuntimeError("provider does not support TAIFEX qualification capture")

        capture = self._source.capture_taifex_night_qualification(
            window,
            self._config.contract_alias,
        )
        if capture.trading_date != trading_date:
            raise ValueError("qualification capture trading date does not match requested session")
        self._artifacts.save_raw(
            create_raw_source_artifact(
                source=capture.source,
                captured_at=capture.captured_at,
                payload_json=capture.raw_source_json,
            )
        )
        report, report_json = self._evaluate(window, capture)
        self._artifacts.save_raw(
            create_raw_source_artifact(
                source="TAIFEX_NIGHT_QUALIFICATION_REPORT",
                captured_at=local_now,
                payload_json=report_json,
            )
        )
        return report

    def _evaluate(
        self,
        window: SessionWindow,
        capture: QualificationCapture,
    ) -> tuple[QualificationReport, str]:
        bars = tuple(bar for bar in capture.bars if window.start <= bar.timestamp < window.end)
        ticks = tuple(tick for tick in capture.ticks if window.start <= tick.timestamp < window.end)
        reasons: list[str] = []
        if capture.contract_identity.status is ContractIdentityStatus.UNRESOLVED:
            reasons.append("CONTRACT_IDENTITY_UNRESOLVED")
        if not bars:
            reasons.append("KBAR_SESSION_EMPTY")
        if not ticks:
            reasons.append("TICK_SESSION_EMPTY")
        if any(current.timestamp <= previous.timestamp for previous, current in zip(bars, bars[1:])):
            reasons.append("KBAR_ORDER_INVALID")
        if any(current.timestamp < previous.timestamp for previous, current in zip(ticks, ticks[1:])):
            reasons.append("TICK_ORDER_INVALID")
        if bars and (
            bars[0].timestamp > window.start + self._config.session_start_tolerance
            or bars[-1].timestamp < window.end - self._config.session_end_tolerance
        ):
            reasons.append("KBAR_SESSION_BOUNDARY_NOT_OBSERVED")

        field_deltas: tuple[tuple[str, Decimal], ...] = ()
        if bars and ticks:
            kbar_values = {
                "open": bars[0].open,
                "high": max(bar.high for bar in bars),
                "low": min(bar.low for bar in bars),
                "close": bars[-1].close,
                "volume": Decimal(sum(bar.volume for bar in bars)),
            }
            tick_values = {
                "open": ticks[0].close,
                "high": max(tick.close for tick in ticks),
                "low": min(tick.close for tick in ticks),
                "close": ticks[-1].close,
                "volume": Decimal(sum(tick.volume for tick in ticks)),
            }
            field_deltas = tuple(
                (field, tick_values[field] - kbar_values[field])
                for field in ("open", "high", "low", "close", "volume")
            )
            if any(delta != 0 for _, delta in field_deltas):
                reasons.append("TICK_KBAR_MISMATCH")

        blocking_reasons = tuple(reasons)
        reasons.append("SOURCE_COMPLETION_REVIEW_REQUIRED")
        status = (
            QualificationStatus.INVALID
            if blocking_reasons
            else QualificationStatus.CAPTURED_UNQUALIFIED
        )
        body = {
            "schema_version": "taifex_night_source_qualification_v0",
            "trading_date": window.trading_date,
            "contract_identity": {
                "status": capture.contract_identity.status,
                "resolution_method": capture.contract_identity.resolution_method,
                "resolved_contract_code": capture.contract_identity.resolved_contract_code,
                "delivery_month": capture.contract_identity.delivery_month,
                "last_trading_date": capture.contract_identity.last_trading_date,
            },
            "session_start": window.start,
            "session_end": window.end,
            "captured_at": capture.captured_at,
            "source": capture.source,
            "raw_source_digest": capture.raw_source_digest,
            "kbar_count": len(bars),
            "tick_count": len(ticks),
            "kbar_first_at": bars[0].timestamp if bars else None,
            "kbar_last_at": bars[-1].timestamp if bars else None,
            "tick_first_at": ticks[0].timestamp if ticks else None,
            "tick_last_at": ticks[-1].timestamp if ticks else None,
            "field_deltas": field_deltas,
            "status": status,
            "reasons": tuple(reasons),
        }
        digest = sha256_digest(body)
        report = QualificationReport(
            qualification_id=f"taifex-qualification-{digest[:16]}",
            qualification_digest=digest,
            **{**body, "contract_identity": capture.contract_identity},
        )
        return report, canonical_json(body)
