"""Application service that builds the observation-only premarket projection."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from config.premarket import PremarketContextConfig
from premarket.artifacts import (
    PremarketArtifactRepository,
    create_context_artifact,
    create_raw_source_artifact,
)
from premarket.calendar import CalendarCoverageError, TaifexTradingCalendar
from premarket.models import (
    CompletenessStatus,
    ContextHealth,
    ContractIdentityStatus,
    NightBar,
    SessionWindow,
    SourceObservation,
    TaifexNightContextArtifact,
)
from premarket.reconciliation import ReconciliationService


class PremarketContextSource(Protocol):
    def supports_premarket_context(self) -> bool: ...

    def get_taifex_night_session(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> SourceObservation | None: ...


class PremarketContextService:
    def __init__(
        self,
        *,
        source: PremarketContextSource,
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
        self._ready: dict[date, TaifexNightContextArtifact] = {}
        self._last_attempt_at: dict[date, datetime] = {}
        self._last_projection: dict[date, dict[str, Any]] = {}

    def projection(self) -> dict[str, Any]:
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("premarket clock must return a timezone-aware datetime")
        local_now = now.astimezone(ZoneInfo(self._config.timezone))
        try:
            trading_date = self._calendar.trading_date_for(local_now)
            window = self._calendar.session_window(trading_date, self._config.query_delay)
        except CalendarCoverageError:
            return self._empty_projection(
                health=ContextHealth.UNAVAILABLE,
                reasons=("CALENDAR_COVERAGE_UNAVAILABLE",),
            )

        if not self._config.capture_enabled or not self._config.dashboard_enabled:
            return self._empty_projection(
                health=ContextHealth.UNAVAILABLE,
                reasons=("FEATURE_DISABLED",),
                window=window,
            )
        cached = self._ready.get(trading_date)
        if cached is not None:
            reconciliation = self._artifacts.latest_reconciliation(
                cached.context_digest
            )
            return self._project_artifact(cached, reconciliation)
        if local_now < window.query_not_before:
            return self._empty_projection(
                health=ContextHealth.PENDING,
                reasons=("QUERY_NOT_YET_ELIGIBLE",),
                window=window,
            )
        last_attempt = self._last_attempt_at.get(trading_date)
        if last_attempt is not None and local_now - last_attempt < self._config.retry_interval:
            return self._last_projection[trading_date]
        self._last_attempt_at[trading_date] = local_now

        if not self._source.supports_premarket_context():
            projection = self._empty_projection(
                health=ContextHealth.UNAVAILABLE,
                reasons=("SOURCE_CAPABILITY_UNAVAILABLE",),
                window=window,
            )
            self._last_projection[trading_date] = projection
            return projection
        try:
            observation = self._source.get_taifex_night_session(
                window,
                self._config.contract_alias,
            )
        except Exception:
            projection = self._empty_projection(
                health=ContextHealth.UNAVAILABLE,
                reasons=("SOURCE_QUERY_FAILED",),
                window=window,
            )
            self._last_projection[trading_date] = projection
            return projection
        if observation is None:
            projection = self._empty_projection(
                health=ContextHealth.NOT_APPLICABLE,
                reasons=("SESSION_NOT_APPLICABLE",),
                window=window,
            )
            self._last_projection[trading_date] = projection
            return projection

        if observation.raw_source_json is not None:
            self._artifacts.save_raw(
                create_raw_source_artifact(
                    source=observation.source,
                    captured_at=observation.received_at,
                    payload_json=observation.raw_source_json,
                )
            )

        artifact = self._build_artifact(window, observation)
        if artifact is None:
            projection = self._empty_projection(
                health=ContextHealth.UNAVAILABLE,
                reasons=("SOURCE_CORE_FIELDS_INVALID",),
                window=window,
            )
        else:
            self._artifacts.save_context(artifact)
            reconciliation = self._artifacts.latest_reconciliation(artifact.context_digest)
            projection = self._project_artifact(artifact, reconciliation)
            if artifact.health is ContextHealth.READY:
                self._ready[trading_date] = artifact
        self._last_projection[trading_date] = projection
        return projection

    def _build_artifact(
        self,
        window: SessionWindow,
        observation: SourceObservation,
    ) -> TaifexNightContextArtifact | None:
        if observation.trading_date != window.trading_date:
            return None
        raw_bars = observation.bars
        if any(current.timestamp <= previous.timestamp for previous, current in zip(raw_bars, raw_bars[1:])):
            return None
        bars = tuple(bar for bar in raw_bars if window.start <= bar.timestamp < window.end)
        if not bars:
            return None
        open_price = bars[0].open
        high = max(bar.high for bar in bars)
        low = min(bar.low for bar in bars)
        close = bars[-1].close
        volume = sum(bar.volume for bar in bars)
        reasons: list[str] = []
        if bars[0].timestamp > window.start + self._config.session_start_tolerance:
            reasons.append("SESSION_START_NOT_OBSERVED")
        if bars[-1].timestamp < window.end - self._config.session_end_tolerance:
            reasons.append("SESSION_END_NOT_OBSERVED")
        qualified = (
            observation.completeness_status is CompletenessStatus.COMPLETE
            and self._config.completion_is_qualified(
                observation.source,
                observation.completeness_evidence,
            )
        )
        if not qualified:
            reasons.append("SOURCE_COMPLETENESS_UNQUALIFIED")
        if observation.contract_identity.status is ContractIdentityStatus.UNRESOLVED:
            reasons.append("CONTRACT_IDENTITY_UNRESOLVED")
        if observation.provider_reference_price is None:
            reasons.append("PROVIDER_REFERENCE_UNAVAILABLE")

        if "CONTRACT_IDENTITY_UNRESOLVED" in reasons:
            health = ContextHealth.DEGRADED
        elif any(reason in reasons for reason in (
            "SESSION_START_NOT_OBSERVED",
            "SESSION_END_NOT_OBSERVED",
            "SOURCE_COMPLETENESS_UNQUALIFIED",
        )):
            health = ContextHealth.PENDING
        elif reasons:
            health = ContextHealth.DEGRADED
        else:
            health = ContextHealth.READY

        return create_context_artifact(
            schema_version=self._config.schema_version,
            readiness_predicate_version=self._config.readiness_predicate_version,
            trading_date=window.trading_date,
            timezone=self._config.timezone,
            product_root=self._config.product_root,
            contract_alias=self._config.contract_alias,
            contract_identity=observation.contract_identity,
            session_start=window.start,
            session_end=window.end,
            query_not_before=window.query_not_before,
            queried_at=observation.queried_at,
            received_at=observation.received_at,
            provider_reference_price=observation.provider_reference_price,
            provider_reference_updated_at=observation.provider_reference_updated_at,
            provider_reference_source=observation.provider_reference_source,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            first_event_at=bars[0].timestamp,
            last_event_at=bars[-1].timestamp,
            completeness_status=observation.completeness_status,
            completeness_evidence=observation.completeness_evidence,
            health=health,
            reasons=tuple(reasons),
            source=observation.source,
            raw_source_digest=observation.raw_source_digest,
        )

    def _project_artifact(self, artifact: TaifexNightContextArtifact, reconciliation: Any) -> dict[str, Any]:
        identity = artifact.contract_identity
        return {
            "status": artifact.health.value,
            "artifact_id": artifact.artifact_id,
            "context_digest": artifact.context_digest,
            "trading_date": artifact.trading_date.isoformat(),
            "product": "臺股期貨近月",
            "contract_alias": artifact.contract_alias,
            "contract_identity": {
                "status": identity.status.value,
                "resolved_contract_code": identity.resolved_contract_code,
                "resolution_method": identity.resolution_method,
                "delivery_month": identity.delivery_month,
                "last_trading_date": identity.last_trading_date.isoformat() if identity.last_trading_date else None,
            },
            "provider_reference": {
                "source": artifact.provider_reference_source,
                "price": self._number(artifact.provider_reference_price),
                "updated_at": artifact.provider_reference_updated_at.isoformat() if artifact.provider_reference_updated_at else None,
            },
            "metrics": {
                "open": self._number(artifact.open),
                "high": self._number(artifact.high),
                "low": self._number(artifact.low),
                "close": self._number(artifact.close),
                "volume": artifact.volume,
                "session_move_pct": self._number(artifact.session_move_pct),
                "session_range_pct": self._number(artifact.session_range_pct),
                "provider_reference_change_pct": self._number(artifact.provider_reference_change_pct),
                "close_location": self._number(artifact.close_location),
            },
            "session_start": artifact.session_start.isoformat(),
            "session_end": artifact.session_end.isoformat(),
            "query_not_before": artifact.query_not_before.isoformat(),
            "queried_at": artifact.queried_at.isoformat(),
            "first_event_at": artifact.first_event_at.isoformat(),
            "last_event_at": artifact.last_event_at.isoformat(),
            "completeness": {
                "status": artifact.completeness_status.value,
                "evidence": list(artifact.completeness_evidence),
                "predicate_version": artifact.readiness_predicate_version,
            },
            "health": {
                "state": artifact.health.value,
                "reasons": list(artifact.reasons),
            },
            "source": artifact.source,
            "raw_source_digest": artifact.raw_source_digest,
            "reconciliation": ReconciliationService.project_summary(artifact, reconciliation),
        }

    def _empty_projection(
        self,
        *,
        health: ContextHealth,
        reasons: tuple[str, ...],
        window: SessionWindow | None = None,
    ) -> dict[str, Any]:
        trading_date = window.trading_date.isoformat() if window else None
        return {
            "status": health.value,
            "artifact_id": None,
            "context_digest": None,
            "trading_date": trading_date,
            "product": "臺股期貨近月",
            "contract_alias": self._config.contract_alias,
            "contract_identity": {
                "status": "UNRESOLVED",
                "resolved_contract_code": None,
                "resolution_method": "NOT_QUERIED",
                "delivery_month": None,
                "last_trading_date": None,
            },
            "provider_reference": {"source": None, "price": None, "updated_at": None},
            "metrics": {
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "volume": None,
                "session_move_pct": None,
                "session_range_pct": None,
                "provider_reference_change_pct": None,
                "close_location": None,
            },
            "session_start": window.start.isoformat() if window else None,
            "session_end": window.end.isoformat() if window else None,
            "query_not_before": window.query_not_before.isoformat() if window else None,
            "queried_at": None,
            "first_event_at": None,
            "last_event_at": None,
            "completeness": {
                "status": CompletenessStatus.UNKNOWN.value,
                "evidence": [],
                "predicate_version": self._config.readiness_predicate_version,
            },
            "health": {"state": health.value, "reasons": list(reasons)},
            "source": None,
            "raw_source_digest": None,
            "reconciliation": {
                "status": "PENDING",
                "artifact_id": None,
                "context_digest": None,
                "settlement_change_pct": None,
                "reasons": [],
            },
        }

    @staticmethod
    def _number(value: Decimal | None) -> float | None:
        return float(value) if value is not None else None
