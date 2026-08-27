"""The sole construction point for the current local runtime."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from config import twse_calendar_2026
from config.local_paper_identity import (
    LOCAL_PAPER_ACCOUNT_SCOPE,
    LOCAL_PAPER_ENTRY_POLICY_DIGEST,
    LOCAL_PAPER_ENTRY_POLICY_VERSION,
    LOCAL_PAPER_POLICY_FAMILY,
    LOCAL_PAPER_RUNTIME_IDENTITY_VERSION,
    LOCAL_PAPER_V2_SESSION_ID,
)
from config.no_overnight import (
    NoOvernightDeploymentManifest,
    NoOvernightMode,
    NoOvernightPolicyConfig,
)
from config.trading_persistence import (
    TradingJournalBackend,
    TradingPersistenceConfig,
)
from config.premarket import PREMARKET_CONTEXT_V0
from dashboard.service import DashboardService
from market_data.provider import MarketDataProvider
from market_data.equity_calendar import ReviewedEquityCalendar
from premarket.artifacts import (
    FilePremarketArtifactRepository,
    PremarketArtifactRepository,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.service import PremarketContextService
from runtime.clock import Clock, SystemClock
from runtime.in_memory import InMemoryProjectionRepository
from runtime.no_overnight import (
    LocalPaperExecutionAdmissionReader,
    LocalPaperNoOvernightCommandPort,
    LocalPaperNoOvernightEvidenceReader,
    NoOvernightController,
    NoOvernightControllerGuard,
    NoOvernightControllerWorker,
)
from runtime.no_overnight_guard import (
    PostgresNoOvernightControllerGuard,
    no_overnight_guard_identity,
)
from runtime.ports import JournalRepository, OrderCommandHandler, ProjectionRepository
from runtime.trading_persistence import build_journal_repository
from simulation.application import LocalPaperCommandService
from simulation.kill_switch import (
    DurableLocalPaperKillSwitch,
    KillSwitchDurability,
)
from simulation.service import SimulationService
from simulation.settings import (
    LocalPaperSettings,
    SETTINGS_SCHEMA_V1,
    SETTINGS_SCHEMA_V2,
)
from simulation.strategy_flow import StrategyPaperFlowService
from trading.journal import JournalSession
from trading.postgres_journal import (
    PostgresJournalRepository,
    postgres_database_locator,
)
from trading.local_paper import (
    LOCAL_PAPER_V1_IMPORTED_KIND,
    build_local_paper_v1_import_record,
    daily_baseline_record,
    latest_local_paper_daily_baseline,
    latest_local_paper_order_states,
    rebuild_local_paper_projection,
    rebuild_local_paper_v2_projection,
    write_local_paper_checkpoint,
    write_local_paper_v2_checkpoint,
)


_LEGACY_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v1"
_FEE_ROUNDING_POLICY = "ROUND_HALF_UP_0.01_TWD"
_LOGGER = logging.getLogger(__name__)
_IDENTITY_BINDING_METADATA_KEYS = frozenset(
    {
        "runtime_identity_version",
        "identity_anchor_session_id",
        "account_scope_id",
        "account_scope_identity_version",
        "policy_family_id",
        "policy_family_identity_version",
        "ledger_id",
    }
)
_SETTINGS_BINDING_METADATA_KEYS = frozenset(
    {
        "settings_revision",
        "settings_digest",
        "max_daily_buy_notional",
        "commission_rate",
        "minimum_commission",
        "fee_rounding_policy",
        "sell_tax_rate",
        "money_quantum",
        "fee_policy_version",
        "rounding_policy_version",
        "slippage_policy_version",
        "price_tick_policy_version",
        "configured_slippage_bps",
        "calibration_status",
        "security_scope",
        "order_condition",
        "day_trade",
        "instrument_descriptor_schema",
        "instrument_admission_policy",
        "runtime_identity_version",
        "identity_anchor_session_id",
        "account_scope_id",
        "account_scope_identity_version",
        "policy_family_id",
        "policy_family_identity_version",
        "ledger_id",
    }
)


def _settings_metadata(
    settings: LocalPaperSettings,
    *,
    revision: int,
) -> dict[str, object]:
    serialized = settings.to_dict()
    metadata: dict[str, object] = {
        "settings_schema": settings.schema_version,
        "settings_revision": revision,
        "settings_digest": settings.digest,
        "starting_cash": serialized["starting_cash_twd"],
        "max_daily_buy_notional": serialized["max_daily_buy_notional_twd"],
        "commission_rate": serialized["commission_rate"],
        "minimum_commission": serialized["minimum_commission_twd"],
        "fee_rounding_policy": _FEE_ROUNDING_POLICY,
        "execution_boundary": "LOCAL_ONLY",
    }
    if settings.schema_version == SETTINGS_SCHEMA_V1:
        return metadata
    metadata.update(
        {
            "sell_tax_rate": serialized["sell_tax_rate"],
            "money_quantum": serialized["money_quantum_twd"],
            "fee_policy_version": serialized["fee_policy_version"],
            "rounding_policy_version": serialized["rounding_policy_version"],
            "slippage_policy_version": serialized[
                "slippage_policy_version"
            ],
            "price_tick_policy_version": serialized[
                "price_tick_policy_version"
            ],
            "configured_slippage_bps": serialized["slippage_bps"],
            "calibration_status": serialized["calibration_status"],
            "security_scope": serialized["security_scope"],
            "order_condition": serialized["order_condition"],
            "day_trade": serialized["day_trade"],
            "instrument_descriptor_schema": (
                "local-paper-instrument-descriptor-v1"
            ),
            "instrument_admission_policy": (
                "twse-tpex-common-stock-admission-v1"
            ),
            "fee_rounding_policy": serialized["rounding_policy_version"],
            "runtime_identity_version": LOCAL_PAPER_RUNTIME_IDENTITY_VERSION,
            "identity_anchor_session_id": LOCAL_PAPER_V2_SESSION_ID,
            "account_scope_id": LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
            "account_scope_identity_version": (
                LOCAL_PAPER_ACCOUNT_SCOPE.identity_schema_version
            ),
            "policy_family_id": LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            "policy_family_identity_version": (
                LOCAL_PAPER_POLICY_FAMILY.identity_schema_version
            ),
            "ledger_id": LOCAL_PAPER_ACCOUNT_SCOPE.ledger_id,
        }
    )
    return metadata


def _validate_session_settings(
    session: JournalSession,
    *,
    settings: LocalPaperSettings,
    revision: int,
) -> bool:
    """Return whether this is a settings-bound session or fail closed."""

    expected = _settings_metadata(settings, revision=revision)
    metadata = session.metadata
    if "settings_schema" not in metadata:
        if _SETTINGS_BINDING_METADATA_KEYS.intersection(metadata):
            raise ValueError("local-paper settings conflicts with Journal")
        if (
            session.session_id != _LEGACY_LOCAL_PAPER_SESSION_ID
            or session.mode != "LOCAL_PAPER_SIMULATION"
            or revision != 0
            or settings != LocalPaperSettings.defaults()
            or metadata.get("starting_cash") != expected["starting_cash"]
            or metadata.get("execution_boundary", "LOCAL_ONLY") != "LOCAL_ONLY"
        ):
            raise ValueError("local-paper legacy settings conflicts with Journal")
        return False
    legacy_expected = {
        key: value
        for key, value in expected.items()
        if key not in _IDENTITY_BINDING_METADATA_KEYS
    }
    exact_current = all(
        metadata.get(key) == value for key, value in expected.items()
    )
    exact_pre_identity = (
        not _IDENTITY_BINDING_METADATA_KEYS.intersection(metadata)
        and all(metadata.get(key) == value for key, value in legacy_expected.items())
    )
    if session.mode != "LOCAL_PAPER_SIMULATION" or not (
        exact_current or exact_pre_identity
    ):
        raise ValueError("local-paper settings conflicts with Journal")
    return True


@dataclass
class RuntimeComposition:
    """Wires concrete local adapters while keeping services API-compatible."""

    provider: MarketDataProvider
    dashboard_service: DashboardService
    premarket_service: PremarketContextService
    premarket_artifacts: PremarketArtifactRepository
    simulation_service: OrderCommandHandler
    local_paper_commands: LocalPaperCommandService
    strategy_paper_flow: StrategyPaperFlowService
    kill_switch: DurableLocalPaperKillSwitch
    clock: Clock
    journal: JournalRepository
    projections: ProjectionRepository
    no_overnight_controller: NoOvernightController
    no_overnight_guard: NoOvernightControllerGuard | None
    no_overnight_worker: NoOvernightControllerWorker | None

    @classmethod
    def create(
        cls,
        provider: MarketDataProvider,
        *,
        dashboard_service: DashboardService | None = None,
        premarket_service: PremarketContextService | None = None,
        premarket_artifacts: PremarketArtifactRepository | None = None,
        simulation_service: SimulationService | None = None,
        clock: Clock | None = None,
        journal: JournalRepository | None = None,
        projections: ProjectionRepository | None = None,
        persistence_config: TradingPersistenceConfig | None = None,
        local_paper_settings: LocalPaperSettings | None = None,
        local_paper_settings_revision: int = 0,
        local_paper_session_id: str = "local-paper-runtime-v1",
        start_simulation_streaming: bool = True,
        no_overnight_config: NoOvernightPolicyConfig | None = None,
        equity_calendar: ReviewedEquityCalendar | None = None,
        no_overnight_deployment_manifest: NoOvernightDeploymentManifest | None = None,
        no_overnight_guard: NoOvernightControllerGuard | None = None,
        local_paper_kill_switch: DurableLocalPaperKillSwitch | None = None,
    ) -> "RuntimeComposition":
        """Build one LOCAL_PAPER composition without broker-order I/O."""

        if (
            isinstance(local_paper_settings_revision, bool)
            or not isinstance(local_paper_settings_revision, int)
            or local_paper_settings_revision < 0
        ):
            raise ValueError("local_paper_settings_revision must be non-negative")

        resolved_clock = clock or SystemClock()
        resolved_premarket_artifacts = (
            premarket_artifacts
            or FilePremarketArtifactRepository(PREMARKET_CONTEXT_V0.artifact_dir)
        )
        resolved_premarket = premarket_service or PremarketContextService(
            source=provider,
            calendar=TaifexTradingCalendar.from_path(
                PREMARKET_CONTEXT_V0.calendar_path
            ),
            config=PREMARKET_CONTEXT_V0,
            artifacts=resolved_premarket_artifacts,
            now=resolved_clock.now,
        )
        resolved_no_overnight_config = (
            no_overnight_config
            or NoOvernightPolicyConfig.disabled(
                account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
                policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
            )
        )
        if (
            resolved_no_overnight_config.account_scope_id
            != LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id
            or resolved_no_overnight_config.policy_family_id
            != LOCAL_PAPER_POLICY_FAMILY.policy_family_id
        ):
            raise ValueError(
                "no-overnight config identity conflicts with Local Paper"
            )
        resolved_equity_calendar = equity_calendar or ReviewedEquityCalendar.from_path(
            twse_calendar_2026.PATH
        )
        resolved_persistence = persistence_config or (
            TradingPersistenceConfig.from_environment()
            if journal is None
            else TradingPersistenceConfig()
        )
        enforcing = resolved_no_overnight_config.mode is NoOvernightMode.ENFORCING
        if enforcing:
            if (
                resolved_persistence.backend is not TradingJournalBackend.POSTGRESQL
                or journal is not None
            ):
                raise ValueError(
                    "no-overnight ENFORCING requires the PostgreSQL Journal backend"
                )
            if no_overnight_deployment_manifest is None:
                raise ValueError(
                    "no-overnight ENFORCING requires a single-worker deployment manifest"
                )
            if (
                no_overnight_deployment_manifest.hosting_mode
                is not resolved_no_overnight_config.controller_hosting_mode
            ):
                raise ValueError(
                    "no-overnight deployment manifest conflicts with policy"
                )
        try:
            resolved_journal = (
                journal
                if journal is not None
                else build_journal_repository(resolved_persistence)
            )
        except Exception as error:
            if enforcing:
                _LOGGER.critical(
                    "no_overnight_startup_failed",
                    extra={
                        "event": "NO_OVERNIGHT_STARTUP_FAILED",
                        "severity": "CRITICAL",
                        "mode": resolved_no_overnight_config.mode.value,
                        "stage": "JOURNAL_INITIALIZATION",
                        "error_type": type(error).__name__,
                    },
                )
            raise
        postgres_mutation_guard_required = isinstance(
            resolved_journal,
            PostgresJournalRepository,
        )
        guard_database_url = resolved_persistence.database_url
        if postgres_mutation_guard_required:
            journal_database_url = resolved_journal.database_url
            journal_database_identity = resolved_journal.database_identity
            try:
                if (
                    journal_database_url is None
                    or journal_database_identity is None
                ):
                    raise ValueError(
                        "injected PostgreSQL Journal requires an explicit database_url"
                    )
                if (
                    journal is not None
                    and resolved_persistence.database_url is not None
                    and postgres_database_locator(
                        resolved_persistence.database_url
                    )
                    != resolved_journal.database_locator
                ):
                    raise ValueError(
                        "persistence database identity conflicts with injected Journal"
                    )
                if (
                    no_overnight_guard is not None
                    and getattr(no_overnight_guard, "database_identity", None)
                    != journal_database_identity
                ):
                    raise ValueError(
                        "PostgreSQL guard database identity conflicts with Journal"
                    )
                guard_database_url = journal_database_url
            except Exception:
                if journal is None:
                    resolved_journal.close()
                raise
        kill_switch_durability = (
            KillSwitchDurability.POSTGRESQL
            if isinstance(resolved_journal, PostgresJournalRepository)
            else KillSwitchDurability.EPHEMERAL_MEMORY
        )
        resolved_settings = local_paper_settings or LocalPaperSettings.defaults()
        if (
            resolved_no_overnight_config.mode is not NoOvernightMode.DISABLED
            and resolved_settings.schema_version != SETTINGS_SCHEMA_V2
        ):
            if journal is None:
                close_journal = getattr(resolved_journal, "close", None)
                if callable(close_journal):
                    close_journal()
            raise ValueError(
                "OBSERVE_ONLY/ENFORCING no-overnight requires Local Paper settings v2"
            )
        resolved_guard = no_overnight_guard
        guard_was_injected = resolved_guard is not None

        def close_guard_created_here() -> None:
            if resolved_guard is not None and not guard_was_injected:
                resolved_guard.close()

        cross_process_guard_required = enforcing or postgres_mutation_guard_required
        if cross_process_guard_required:
            try:
                if resolved_guard is None:
                    if guard_database_url is None:
                        raise ValueError(
                            "PostgreSQL Local Paper v2 requires an advisory guard DSN"
                        )
                    resolved_guard = PostgresNoOvernightControllerGuard.connect(
                        database_url=guard_database_url,
                        connect_timeout_seconds=(
                            resolved_persistence.connect_timeout_seconds
                        ),
                        account_scope_id=(
                            resolved_no_overnight_config.account_scope_id
                        ),
                        policy_family_id=(
                            resolved_no_overnight_config.policy_family_id
                        ),
                    )
                if (
                    postgres_mutation_guard_required
                    and getattr(resolved_guard, "database_identity", None)
                    != resolved_journal.database_identity
                ):
                    raise ValueError(
                        "PostgreSQL guard database identity conflicts with Journal"
                    )
                expected_guard_identity = no_overnight_guard_identity(
                    account_scope_id=resolved_no_overnight_config.account_scope_id,
                    policy_family_id=resolved_no_overnight_config.policy_family_id,
                )
                if resolved_guard.guard_identity != expected_guard_identity:
                    raise ValueError(
                        "no-overnight PostgreSQL guard identity conflicts with policy"
                    )
                resolved_guard.acquire()
                if not resolved_guard.is_owned_and_healthy():
                    raise ValueError(
                        "no-overnight PostgreSQL guard health check failed"
                    )
            except Exception:
                close_guard_created_here()
                if journal is None:
                    resolved_journal.close()
                raise
        try:
            if local_paper_kill_switch is not None:
                if not local_paper_kill_switch.is_bound_to(
                    journal=resolved_journal,
                    clock=resolved_clock,
                    durability=kill_switch_durability,
                ):
                    raise ValueError(
                        "injected Local Paper kill switch has incompatible runtime "
                        "binding"
                    )
                kill_switch = local_paper_kill_switch
            else:
                kill_switch = DurableLocalPaperKillSwitch.recover(
                    journal=resolved_journal,
                    clock=resolved_clock,
                    durability=kill_switch_durability,
                )
        except Exception:
            close_guard_created_here()
            if journal is None:
                resolved_journal.close()
            raise
        resolved_worker: NoOvernightControllerWorker | None = None
        try:
            resolved_simulation = simulation_service or SimulationService(
                provider,
                starting_cash=resolved_settings.starting_cash_twd,
                max_daily_buy_notional=(
                    resolved_settings.max_daily_buy_notional_twd
                ),
                commission_rate=resolved_settings.commission_rate,
                minimum_commission=resolved_settings.minimum_commission_twd,
                slippage_bps=resolved_settings.slippage_bps,
                cost_policy_enabled=(
                    resolved_settings.schema_version == SETTINGS_SCHEMA_V2
                ),
                clock=resolved_clock,
                start_streaming=start_simulation_streaming,
            )
        except Exception:
            close_guard_created_here()
            if journal is None:
                resolved_journal.close()
            raise
        if (
            local_paper_settings is not None
            and resolved_simulation.settings != resolved_settings
        ):
            if simulation_service is None:
                resolved_simulation.close()
            close_guard_created_here()
            if journal is None:
                resolved_journal.close()
            raise ValueError("local-paper simulation settings mismatch")
        try:
            local_paper_session = resolved_journal.session(local_paper_session_id)
        except Exception:
            close_guard_created_here()
            if simulation_service is None:
                resolved_simulation.close()
            if journal is None:
                resolved_journal.close()
            raise
        settings_bound = True
        if local_paper_session is None:
            local_paper_session = JournalSession(
                session_id=local_paper_session_id,
                started_at=resolved_clock.now(),
                mode="LOCAL_PAPER_SIMULATION",
                metadata={
                    **_settings_metadata(
                        resolved_simulation.settings,
                        revision=local_paper_settings_revision,
                    ),
                    "journal_backend": (
                        "INJECTED"
                        if journal is not None
                        else resolved_persistence.backend.value.upper()
                    ),
                    "restart_policy": "RESUME_CHECKPOINTED_LOCAL_PAPER_SESSION",
                },
            )
        else:
            try:
                settings_bound = _validate_session_settings(
                    local_paper_session,
                    settings=resolved_simulation.settings,
                    revision=local_paper_settings_revision,
                )
            except Exception:
                close_guard_created_here()
                if simulation_service is None:
                    resolved_simulation.close()
                if journal is None:
                    resolved_journal.close()
                raise
        settings_digest = (
            resolved_simulation.settings.digest if settings_bound else None
        )
        identity_enabled = (
            settings_bound
            and resolved_simulation.settings.schema_version == SETTINGS_SCHEMA_V2
        )
        try:
            if identity_enabled and local_paper_session.session_id == LOCAL_PAPER_V2_SESSION_ID:
                raise ValueError(
                    "active Local Paper ledger must be separate from identity anchor"
                )
            resolved_journal.start_session(local_paper_session)
            existing_records = resolved_journal.records(local_paper_session.session_id)
            if not existing_records:
                write_local_paper_checkpoint(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                    settings_digest=settings_digest,
                )
                baseline = resolved_simulation.daily_baseline()
                resolved_journal.append(
                    daily_baseline_record(
                        session_id=local_paper_session.session_id,
                        trading_date=str(baseline["trading_date"]),
                        opening_equity=str(baseline["opening_equity"]),
                        opening_realized_pnl=str(
                            baseline["opening_realized_pnl"]
                        ),
                        occurred_at=resolved_clock.now(),
                    )
                )
                write_local_paper_checkpoint(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                    settings_digest=settings_digest,
                )

            recovered = rebuild_local_paper_projection(
                resolved_journal,
                session_id=local_paper_session.session_id,
                starting_cash=resolved_simulation.starting_cash,
                settings_digest=settings_digest,
            )
            order_states = [
                dict(state)
                for state in latest_local_paper_order_states(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    require_integrity=(
                        resolved_settings.schema_version == SETTINGS_SCHEMA_V2
                    ),
                )
            ]
            restore_positions: list[dict[str, object]]
            realized_pnl_by_symbol: dict[str, Decimal]
            realized_pnl_by_exposure: dict[str, Decimal] | None = None
            if identity_enabled:
                anchor_metadata = {
                    "runtime_identity_version": LOCAL_PAPER_RUNTIME_IDENTITY_VERSION,
                    "account_scope_id": LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
                    "account_scope_identity_version": (
                        LOCAL_PAPER_ACCOUNT_SCOPE.identity_schema_version
                    ),
                    "policy_family_id": LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
                    "policy_family_identity_version": (
                        LOCAL_PAPER_POLICY_FAMILY.identity_schema_version
                    ),
                    "ledger_id": LOCAL_PAPER_ACCOUNT_SCOPE.ledger_id,
                    "execution_boundary": "LOCAL_ONLY",
                }
                identity_anchor = resolved_journal.session(LOCAL_PAPER_V2_SESSION_ID)
                if identity_anchor is None:
                    identity_anchor = JournalSession(
                        session_id=LOCAL_PAPER_V2_SESSION_ID,
                        started_at=resolved_clock.now(),
                        mode="LOCAL_PAPER_IDENTITY_ANCHOR",
                        metadata=anchor_metadata,
                    )
                elif (
                    identity_anchor.mode != "LOCAL_PAPER_IDENTITY_ANCHOR"
                    or dict(identity_anchor.metadata) != anchor_metadata
                ):
                    raise ValueError(
                        "Local Paper identity anchor conflicts with Journal"
                    )
                resolved_journal.start_session(identity_anchor)

                manifests = [
                    result.record
                    for result in resolved_journal.records(
                        local_paper_session.session_id
                    )
                    if result.record.kind == LOCAL_PAPER_V1_IMPORTED_KIND
                ]
                if len(manifests) > 1:
                    raise ValueError("Local Paper identity import is duplicated")
                if not manifests:
                    if any(
                        str(state.get("status"))
                        in {
                            "SUBMITTED",
                            "PENDING",
                            "PARTIALLY_FILLED",
                            "RECOVERY_REQUIRED",
                        }
                        for state in order_states
                    ):
                        raise ValueError(
                            "active Local Paper orders make identity import unsafe"
                        )
                    resolved_journal.append(
                        build_local_paper_v1_import_record(
                            source_projection=recovered,
                            source_session_id=local_paper_session.session_id,
                            target_session_id=local_paper_session.session_id,
                            account_scope_id=(
                                LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id
                            ),
                            policy_family_id=(
                                LOCAL_PAPER_POLICY_FAMILY.policy_family_id
                            ),
                            occurred_at=resolved_clock.now(),
                        )
                    )
                    write_local_paper_checkpoint(
                        resolved_journal,
                        session_id=local_paper_session.session_id,
                        starting_cash=resolved_simulation.starting_cash,
                        settings_digest=settings_digest,
                    )
                    write_local_paper_v2_checkpoint(
                        resolved_journal,
                        session_id=local_paper_session.session_id,
                        starting_cash=resolved_simulation.starting_cash,
                        account_scope_id=(
                            LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id
                        ),
                        policy_family_id=(
                            LOCAL_PAPER_POLICY_FAMILY.policy_family_id
                        ),
                        settings_digest=settings_digest,
                    )
                exposure_projection = rebuild_local_paper_v2_projection(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                    account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
                    policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
                    settings_digest=settings_digest,
                )
                recovered = rebuild_local_paper_projection(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                    settings_digest=settings_digest,
                )
                if exposure_projection.cash != recovered.cash:
                    raise ValueError("Local Paper v1/v2 cash projections diverged")
                monetary_quantity = {
                    position.symbol: position.quantity_shares
                    for position in recovered.positions
                }
                exposure_quantity: dict[str, int] = {}
                exposure_symbols: dict[str, str] = {}
                for state in exposure_projection.exposure_states:
                    symbol = str(state["symbol"])
                    exposure_id = str(
                        dict(state["exposure_identity"])["exposure_id"]
                    )
                    exposure_symbols[exposure_id] = symbol
                    quantity = int(state["quantity"])
                    if quantity > 0:
                        exposure_quantity[symbol] = (
                            exposure_quantity.get(symbol, 0) + quantity
                        )
                if exposure_quantity != monetary_quantity:
                    raise ValueError("Local Paper v1/v2 position projections diverged")
                monetary_realized = dict(recovered.realized_pnl_by_symbol)
                exposure_realized: dict[str, Decimal] = {}
                for exposure_id, value in (
                    exposure_projection.realized_pnl_by_exposure.items()
                ):
                    symbol = exposure_symbols[exposure_id]
                    exposure_realized[symbol] = (
                        exposure_realized.get(symbol, Decimal("0")) + value
                    )
                realized_symbols = set(exposure_realized) | set(monetary_realized)
                if any(
                    exposure_realized.get(symbol, Decimal("0"))
                    != monetary_realized.get(symbol, Decimal("0"))
                    for symbol in realized_symbols
                ):
                    raise ValueError("Local Paper v1/v2 realized PnL diverged")
                restore_positions = [
                    dict(state) for state in exposure_projection.exposure_states
                ]
                realized_pnl_by_symbol = {}
                realized_pnl_by_exposure = dict(
                    exposure_projection.realized_pnl_by_exposure
                )
            else:
                restore_positions = [
                    {
                        "symbol": position.symbol,
                        "name": position.name,
                        "quantity": position.quantity_shares,
                        "average_price": position.average_price,
                        "commission_cost": position.commission_cost,
                        "owner_origin": position.owner_origin,
                        "owner_strategy_id": position.owner_strategy_id,
                        "owner_strategy_version": position.owner_strategy_version,
                    }
                    for position in recovered.positions
                ]
                realized_pnl_by_symbol = dict(recovered.realized_pnl_by_symbol)

            resolved_simulation.restore_state(
                cash=recovered.cash,
                positions=restore_positions,
                realized_pnl_by_symbol=realized_pnl_by_symbol,
                realized_pnl_by_exposure=realized_pnl_by_exposure,
                order_states=order_states,
                daily_baseline=(
                    dict(baseline)
                    if (
                        baseline := latest_local_paper_daily_baseline(
                            resolved_journal,
                            session_id=local_paper_session.session_id,
                        )
                    )
                    is not None
                    else None
                ),
                daily_filled_buy_notional=recovered.buy_notional_for_date(
                    resolved_clock.session_date()
                ),
            )
            execution_admission_reader = (
                LocalPaperExecutionAdmissionReader(
                    config=resolved_no_overnight_config,
                    calendar=resolved_equity_calendar,
                    journal=resolved_journal,
                    clock=resolved_clock,
                    simulation=resolved_simulation,
                    guard=resolved_guard,
                )
                if enforcing and resolved_guard is not None
                else None
            )
            durable_breach_reader = (
                LocalPaperExecutionAdmissionReader(
                    config=resolved_no_overnight_config,
                    calendar=resolved_equity_calendar,
                    journal=resolved_journal,
                    clock=resolved_clock,
                    simulation=resolved_simulation,
                    guard=(
                        resolved_guard
                        if postgres_mutation_guard_required
                        else None
                    ),
                )
                if not enforcing
                else None
            )
            local_paper_commands = LocalPaperCommandService(
                simulation=resolved_simulation,
                journal=resolved_journal,
                session_id=local_paper_session.session_id,
                clock=resolved_clock,
                settings_digest=settings_digest,
                account_scope=LOCAL_PAPER_ACCOUNT_SCOPE if identity_enabled else None,
                policy_family=LOCAL_PAPER_POLICY_FAMILY if identity_enabled else None,
                entry_policy_version=(
                    LOCAL_PAPER_ENTRY_POLICY_VERSION if identity_enabled else None
                ),
                entry_policy_digest=(
                    LOCAL_PAPER_ENTRY_POLICY_DIGEST if identity_enabled else None
                ),
                execution_admission_reader=execution_admission_reader,
                durable_breach_reader=durable_breach_reader,
            )
            no_overnight_controller = NoOvernightController(
                config=resolved_no_overnight_config,
                calendar=resolved_equity_calendar,
                journal=resolved_journal,
                evidence_reader=LocalPaperNoOvernightEvidenceReader(
                    journal=resolved_journal,
                    local_paper_session_id=local_paper_session.session_id,
                    simulation=resolved_simulation,
                    account_scope_id=LOCAL_PAPER_ACCOUNT_SCOPE.account_scope_id,
                    policy_family_id=LOCAL_PAPER_POLICY_FAMILY.policy_family_id,
                ),
                command_port=(
                    LocalPaperNoOvernightCommandPort(
                        commands=local_paper_commands,
                        simulation=resolved_simulation,
                        max_exit_attempts=(
                            resolved_no_overnight_config.max_exit_attempts
                        ),
                        retry_cooldown_seconds=(
                            resolved_no_overnight_config.retry_cooldown_seconds
                        ),
                    )
                    if enforcing
                    else None
                ),
                guard=resolved_guard,
                deployment_manifest_digest=(
                    no_overnight_deployment_manifest.digest
                    if no_overnight_deployment_manifest is not None
                    else None
                ),
            )
            if resolved_no_overnight_config.mode in {
                NoOvernightMode.OBSERVE_ONLY,
                NoOvernightMode.ENFORCING,
            }:
                no_overnight_controller.run_once(resolved_clock.now())
            if enforcing:
                assert resolved_guard is not None
                resolved_worker = NoOvernightControllerWorker(
                    controller=no_overnight_controller,
                    clock=resolved_clock,
                    on_failure=resolved_guard.close,
                )
                resolved_worker.start()
        except Exception as error:
            if enforcing:
                _LOGGER.critical(
                    "no_overnight_startup_failed",
                    extra={
                        "event": "NO_OVERNIGHT_STARTUP_FAILED",
                        "severity": "CRITICAL",
                        "mode": resolved_no_overnight_config.mode.value,
                        "stage": "RECOVERY_OR_CONTROLLER_START",
                        "error_type": type(error).__name__,
                    },
                )
            if resolved_worker is not None:
                resolved_worker.stop()
            close_guard_created_here()
            if simulation_service is None:
                close_simulation = getattr(resolved_simulation, "close", None)
                if callable(close_simulation):
                    close_simulation()
            if journal is None:
                close_journal = getattr(resolved_journal, "close", None)
                if callable(close_journal):
                    close_journal()
            raise
        return cls(
            provider=provider,
            dashboard_service=dashboard_service or DashboardService(
                provider,
                premarket_service=resolved_premarket,
            ),
            premarket_service=resolved_premarket,
            premarket_artifacts=resolved_premarket_artifacts,
            simulation_service=resolved_simulation,
            local_paper_commands=local_paper_commands,
            strategy_paper_flow=StrategyPaperFlowService(
                commands=local_paper_commands,
                journal=resolved_journal,
                session_id=local_paper_session.session_id,
                clock=resolved_clock,
                kill_switch=kill_switch,
            ),
            kill_switch=kill_switch,
            clock=resolved_clock,
            journal=resolved_journal,
            projections=projections or InMemoryProjectionRepository(),
            no_overnight_controller=no_overnight_controller,
            no_overnight_guard=resolved_guard,
            no_overnight_worker=resolved_worker,
        )

    def prepare_local_paper_handoff_to(
        self,
        replacement: "RuntimeComposition",
    ) -> None:
        """Quiesce old commands and validate a reversible in-process handoff."""

        guard = self.no_overnight_guard
        if (
            replacement.no_overnight_guard is not guard
            or replacement.kill_switch is not self.kill_switch
            or self.no_overnight_worker is not None
            or replacement.no_overnight_worker is not None
        ):
            raise ValueError("Local Paper authority handoff is invalid")
        if guard is not None and not guard.is_owned_and_healthy():
            raise ValueError("no-overnight guard is unhealthy during handoff")
        self.local_paper_commands.prepare_runtime_handoff()

    def execute_prepared_local_paper_handoff(
        self,
        operation: Callable[[], None],
    ) -> None:
        """Run durable activation while the guard cannot be closed locally."""

        guard = self.no_overnight_guard
        if guard is None:
            operation()
            return
        guard.execute_if_owned(operation)

    def commit_local_paper_handoff(self) -> None:
        """Irreversibly revoke old command references and transfer guard ownership."""

        self.local_paper_commands.finalize_runtime_handoff()
        self.no_overnight_guard = None

    def rollback_local_paper_handoff(self) -> None:
        """Resume the old command authority after a pre-commit failure."""

        self.local_paper_commands.rollback_runtime_handoff()

    def close(self) -> None:
        """Release local-paper workers before closing the provider connection."""

        if self.no_overnight_worker is not None:
            self.no_overnight_worker.stop()
        close_simulation = getattr(self.simulation_service, "close", None)
        if callable(close_simulation):
            close_simulation()
        close_journal = getattr(self.journal, "close", None)
        if callable(close_journal):
            close_journal()
        if self.no_overnight_guard is not None:
            self.no_overnight_guard.close()
        self.provider.close()
