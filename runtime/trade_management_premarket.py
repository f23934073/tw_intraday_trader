"""Pure PR-TM-012C0 pre-market readiness contracts and evaluator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from trading.journal import JOURNAL_SCHEMA_VERSION


TRADE_MANAGEMENT_PREMARKET_VERSION = "trade-management-premarket-v1"
EXPECTED_JOURNAL_TABLES = (
    "journal_records",
    "journal_schema_migrations",
    "journal_sessions",
    "projection_checkpoints",
)
AUTHORITATIVE_EVIDENCE_TABLES = (
    "journal_sessions",
    "journal_records",
    "projection_checkpoints",
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class PremarketReadinessStatus(StrEnum):
    READY_FOR_SESSION = "READY_FOR_SESSION"
    BLOCKED = "BLOCKED"


class PremarketBlocker(StrEnum):
    UNREVIEWED_TRADING_DATE = "UNREVIEWED_TRADING_DATE"
    SESSION_WINDOW_NOT_FUTURE = "SESSION_WINDOW_NOT_FUTURE"
    CREDENTIALS_MISSING = "CREDENTIALS_MISSING"
    PROVIDER_PREFLIGHT_FAILED = "PROVIDER_PREFLIGHT_FAILED"
    PROVIDER_IDENTITY_MISMATCH = "PROVIDER_IDENTITY_MISMATCH"
    PROVIDER_NOT_SIMULATION = "PROVIDER_NOT_SIMULATION"
    TRADE_SUBSCRIPTION_ENABLED = "TRADE_SUBSCRIPTION_ENABLED"
    POSTGRES_DSN_MISSING = "POSTGRES_DSN_MISSING"
    POSTGRES_DRIVER_MISSING = "POSTGRES_DRIVER_MISSING"
    POSTGRES_PREFLIGHT_FAILED = "POSTGRES_PREFLIGHT_FAILED"
    POSTGRES_NOT_READ_ONLY = "POSTGRES_NOT_READ_ONLY"
    POSTGRES_SCHEMA_MISMATCH = "POSTGRES_SCHEMA_MISMATCH"
    POSTGRES_MIGRATION_MISMATCH = "POSTGRES_MIGRATION_MISMATCH"
    POSTGRES_EVIDENCE_SCOPE_MISMATCH = "POSTGRES_EVIDENCE_SCOPE_MISMATCH"
    POSTGRES_EVIDENCE_NOT_EMPTY = "POSTGRES_EVIDENCE_NOT_EMPTY"
    REHEARSAL_FAILED = "REHEARSAL_FAILED"


@dataclass(frozen=True)
class ShadowPremarketManifest:
    prepared_at: datetime
    market_date: date
    scheduled_open: datetime
    scheduled_close: datetime
    calendar_schema_version: str
    calendar_digest: str
    session_id: str
    symbol: str
    provider: str
    provider_version: str
    provider_simulation: bool
    connection_session_id: str
    code_identity: str
    migration_versions: tuple[str, ...]
    strategy_id: str
    strategy_version: str
    thesis_version: str
    exit_policy_version: str
    risk_policy_version: str
    fill_model_version: str
    validator_version: str
    execution_authority: bool = False
    execution_enabled: bool = False
    evidence_only: bool = True
    qualifying_real_session: bool = False
    version: str = TRADE_MANAGEMENT_PREMARKET_VERSION
    journal_schema_version: str = JOURNAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.version != TRADE_MANAGEMENT_PREMARKET_VERSION:
            raise ValueError("unsupported pre-market manifest version")
        for value, field_name in (
            (self.calendar_schema_version, "calendar_schema_version"),
            (self.calendar_digest, "calendar_digest"),
            (self.session_id, "session_id"),
            (self.symbol, "symbol"),
            (self.provider, "provider"),
            (self.provider_version, "provider_version"),
            (self.connection_session_id, "connection_session_id"),
            (self.code_identity, "code_identity"),
            (self.strategy_id, "strategy_id"),
            (self.strategy_version, "strategy_version"),
            (self.thesis_version, "thesis_version"),
            (self.exit_policy_version, "exit_policy_version"),
            (self.risk_policy_version, "risk_policy_version"),
            (self.fill_model_version, "fill_model_version"),
            (self.validator_version, "validator_version"),
            (self.journal_schema_version, "journal_schema_version"),
        ):
            _require_non_empty(value, field_name)
        for value, field_name in (
            (self.prepared_at, "prepared_at"),
            (self.scheduled_open, "scheduled_open"),
            (self.scheduled_close, "scheduled_close"),
        ):
            _require_aware(value, field_name)
        if self.scheduled_open.date() != self.market_date:
            raise ValueError("scheduled_open must match market_date")
        if self.scheduled_close.date() != self.market_date:
            raise ValueError("scheduled_close must match market_date")
        if self.scheduled_close <= self.scheduled_open:
            raise ValueError("scheduled_close must follow scheduled_open")
        if self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be normalized")
        if not self.migration_versions:
            raise ValueError("migration_versions must not be empty")
        if self.migration_versions != tuple(sorted(set(self.migration_versions))):
            raise ValueError("migration_versions must be unique and sorted")
        if self.execution_authority:
            raise ValueError("pre-market manifest cannot grant execution authority")
        if self.execution_enabled or not self.evidence_only:
            raise ValueError("pre-market manifest must remain evidence-only")
        if self.qualifying_real_session:
            raise ValueError("pre-market artifacts cannot qualify as real sessions")

    @property
    def provider_identity(self) -> str:
        return (
            f"{self.provider}:{self.provider_version}:"
            f"simulation={str(self.provider_simulation).lower()}"
        )

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "prepared_at": self.prepared_at.isoformat(),
            "market_date": self.market_date.isoformat(),
            "scheduled_open": self.scheduled_open.isoformat(),
            "scheduled_close": self.scheduled_close.isoformat(),
            "calendar_schema_version": self.calendar_schema_version,
            "calendar_digest": self.calendar_digest,
            "session_id": self.session_id,
            "symbol": self.symbol,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "provider_simulation": self.provider_simulation,
            "provider_identity": self.provider_identity,
            "connection_session_id": self.connection_session_id,
            "code_identity": self.code_identity,
            "journal_schema_version": self.journal_schema_version,
            "migration_versions": list(self.migration_versions),
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "thesis_version": self.thesis_version,
            "exit_policy_version": self.exit_policy_version,
            "risk_policy_version": self.risk_policy_version,
            "fill_model_version": self.fill_model_version,
            "validator_version": self.validator_version,
            "execution_authority": self.execution_authority,
            "execution_enabled": self.execution_enabled,
            "evidence_only": self.evidence_only,
            "qualifying_real_session": self.qualifying_real_session,
        }


@dataclass(frozen=True)
class DataOnlyProviderPreflight:
    credential_keys_present: tuple[str, ...]
    login_succeeded: bool
    logout_succeeded: bool
    subscribe_trade: bool
    environment_identity: str | None
    error_code: str | None = None

    @property
    def passed(self) -> bool:
        return (
            len(self.credential_keys_present) == 2
            and self.login_succeeded
            and self.logout_succeeded
            and not self.subscribe_trade
            and self.environment_identity is not None
            and self.error_code is None
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "credential_keys_present": list(self.credential_keys_present),
                "login_succeeded": self.login_succeeded,
                "logout_succeeded": self.logout_succeeded,
                "subscribe_trade": self.subscribe_trade,
                "environment_identity": self.environment_identity,
                "error_code": self.error_code,
            }
        )


@dataclass(frozen=True)
class PostgresReadOnlyPreflight:
    dsn_configured: bool
    driver_version: str | None
    connected: bool
    transaction_read_only: bool
    server_major: int | None
    table_names: tuple[str, ...]
    migration_versions: tuple[str, ...]
    evidence_row_counts: tuple[tuple[str, int], ...]
    evidence_scope_session_id: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.table_names != tuple(sorted(set(self.table_names))):
            raise ValueError("table_names must be unique and sorted")
        if self.migration_versions != tuple(sorted(set(self.migration_versions))):
            raise ValueError("migration_versions must be unique and sorted")
        names = tuple(item[0] for item in self.evidence_row_counts)
        if names != AUTHORITATIVE_EVIDENCE_TABLES:
            raise ValueError("evidence row counts must use the authoritative table order")
        if any(count < 0 for _, count in self.evidence_row_counts):
            raise ValueError("evidence row counts must not be negative")
        _require_non_empty(
            self.evidence_scope_session_id,
            "evidence_scope_session_id",
        )

    @property
    def evidence_empty(self) -> bool:
        return all(count == 0 for _, count in self.evidence_row_counts)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "dsn_configured": self.dsn_configured,
                "driver_version": self.driver_version,
                "connected": self.connected,
                "transaction_read_only": self.transaction_read_only,
                "server_major": self.server_major,
                "table_names": list(self.table_names),
                "migration_versions": list(self.migration_versions),
                "evidence_row_counts": [list(item) for item in self.evidence_row_counts],
                "evidence_scope_session_id": self.evidence_scope_session_id,
                "error_code": self.error_code,
            }
        )


@dataclass(frozen=True)
class ShadowRehearsalEvidence:
    test_targets: tuple[str, ...]
    historical_replay_verified: bool
    operational_composition_verified: bool
    journal_recovery_verified: bool
    replay_parity_matched: bool
    readiness_report_deterministic: bool
    execution_enabled: bool = False
    qualifying_real_session: bool = False

    def __post_init__(self) -> None:
        if self.test_targets != tuple(sorted(set(self.test_targets))):
            raise ValueError("test_targets must be unique and sorted")
        if self.execution_enabled or self.qualifying_real_session:
            raise ValueError("rehearsal cannot enable execution or qualify as live evidence")

    @property
    def passed(self) -> bool:
        return all(
            (
                self.historical_replay_verified,
                self.operational_composition_verified,
                self.journal_recovery_verified,
                self.replay_parity_matched,
                self.readiness_report_deterministic,
            )
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "test_targets": list(self.test_targets),
                "historical_replay_verified": self.historical_replay_verified,
                "operational_composition_verified": self.operational_composition_verified,
                "journal_recovery_verified": self.journal_recovery_verified,
                "replay_parity_matched": self.replay_parity_matched,
                "readiness_report_deterministic": self.readiness_report_deterministic,
                "execution_enabled": self.execution_enabled,
                "qualifying_real_session": self.qualifying_real_session,
            }
        )


@dataclass(frozen=True)
class ShadowPremarketReadinessReport:
    report_id: str
    manifest_digest: str
    provider_preflight_digest: str
    postgres_preflight_digest: str
    rehearsal_digest: str
    status: PremarketReadinessStatus
    blockers: tuple[PremarketBlocker, ...]
    execution_authority: bool = False
    execution_enabled: bool = False
    qualifying_real_session: bool = False

    def __post_init__(self) -> None:
        if (
            self.execution_authority
            or self.execution_enabled
            or self.qualifying_real_session
        ):
            raise ValueError("pre-market report cannot enable or qualify execution")
        if self.status is PremarketReadinessStatus.READY_FOR_SESSION and self.blockers:
            raise ValueError("ready pre-market report cannot contain blockers")
        if self.status is PremarketReadinessStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked pre-market report requires blockers")

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "version": TRADE_MANAGEMENT_PREMARKET_VERSION,
            "report_id": self.report_id,
            "manifest_digest": self.manifest_digest,
            "provider_preflight_digest": self.provider_preflight_digest,
            "postgres_preflight_digest": self.postgres_preflight_digest,
            "rehearsal_digest": self.rehearsal_digest,
            "status": self.status.value,
            "blockers": [item.value for item in self.blockers],
            "execution_authority": self.execution_authority,
            "execution_enabled": self.execution_enabled,
            "qualifying_real_session": self.qualifying_real_session,
        }


class ShadowPremarketReadinessEvaluator:
    """Classify only injected evidence; no environment, DB, or provider access."""

    __slots__ = ()

    def evaluate(
        self,
        manifest: ShadowPremarketManifest,
        *,
        trading_date_reviewed: bool,
        provider: DataOnlyProviderPreflight,
        postgres: PostgresReadOnlyPreflight,
        rehearsal: ShadowRehearsalEvidence,
    ) -> ShadowPremarketReadinessReport:
        blockers: set[PremarketBlocker] = set()
        if not trading_date_reviewed:
            blockers.add(PremarketBlocker.UNREVIEWED_TRADING_DATE)
        if manifest.prepared_at >= manifest.scheduled_open:
            blockers.add(PremarketBlocker.SESSION_WINDOW_NOT_FUTURE)
        if len(provider.credential_keys_present) != 2:
            blockers.add(PremarketBlocker.CREDENTIALS_MISSING)
        if not provider.passed:
            blockers.add(PremarketBlocker.PROVIDER_PREFLIGHT_FAILED)
        if provider.subscribe_trade:
            blockers.add(PremarketBlocker.TRADE_SUBSCRIPTION_ENABLED)
        if provider.environment_identity != manifest.provider_identity:
            blockers.add(PremarketBlocker.PROVIDER_IDENTITY_MISMATCH)
        if not manifest.provider_simulation:
            blockers.add(PremarketBlocker.PROVIDER_NOT_SIMULATION)
        if not postgres.dsn_configured:
            blockers.add(PremarketBlocker.POSTGRES_DSN_MISSING)
        if postgres.driver_version is None:
            blockers.add(PremarketBlocker.POSTGRES_DRIVER_MISSING)
        if not postgres.connected:
            blockers.add(PremarketBlocker.POSTGRES_PREFLIGHT_FAILED)
        if not postgres.transaction_read_only:
            blockers.add(PremarketBlocker.POSTGRES_NOT_READ_ONLY)
        if postgres.table_names != EXPECTED_JOURNAL_TABLES:
            blockers.add(PremarketBlocker.POSTGRES_SCHEMA_MISMATCH)
        if postgres.migration_versions != manifest.migration_versions:
            blockers.add(PremarketBlocker.POSTGRES_MIGRATION_MISMATCH)
        if postgres.evidence_scope_session_id != manifest.session_id:
            blockers.add(PremarketBlocker.POSTGRES_EVIDENCE_SCOPE_MISMATCH)
        if not postgres.evidence_empty:
            blockers.add(PremarketBlocker.POSTGRES_EVIDENCE_NOT_EMPTY)
        if not rehearsal.passed:
            blockers.add(PremarketBlocker.REHEARSAL_FAILED)
        ordered = tuple(item for item in PremarketBlocker if item in blockers)
        input_digest = _digest(
            {
                "version": TRADE_MANAGEMENT_PREMARKET_VERSION,
                "manifest_digest": manifest.digest,
                "trading_date_reviewed": trading_date_reviewed,
                "provider_digest": provider.digest,
                "postgres_digest": postgres.digest,
                "rehearsal_digest": rehearsal.digest,
            }
        )
        return ShadowPremarketReadinessReport(
            report_id=f"shadow_premarket_v1_{input_digest}",
            manifest_digest=manifest.digest,
            provider_preflight_digest=provider.digest,
            postgres_preflight_digest=postgres.digest,
            rehearsal_digest=rehearsal.digest,
            status=(
                PremarketReadinessStatus.READY_FOR_SESSION
                if not ordered
                else PremarketReadinessStatus.BLOCKED
            ),
            blockers=ordered,
        )
