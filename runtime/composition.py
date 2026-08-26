"""The sole construction point for the current local runtime."""

from __future__ import annotations

from dataclasses import dataclass

from config.trading_persistence import TradingPersistenceConfig
from config.premarket import PREMARKET_CONTEXT_V0
from dashboard.service import DashboardService
from market_data.provider import MarketDataProvider
from premarket.artifacts import (
    FilePremarketArtifactRepository,
    PremarketArtifactRepository,
)
from premarket.calendar import TaifexTradingCalendar
from premarket.service import PremarketContextService
from runtime.clock import Clock, SystemClock
from runtime.in_memory import InMemoryProjectionRepository
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
from trading.postgres_journal import PostgresJournalRepository
from trading.local_paper import (
    daily_baseline_record,
    latest_local_paper_daily_baseline,
    latest_local_paper_order_states,
    rebuild_local_paper_projection,
    write_local_paper_checkpoint,
)


_LEGACY_LOCAL_PAPER_SESSION_ID = "local-paper-runtime-v1"
_FEE_ROUNDING_POLICY = "ROUND_HALF_UP_0.01_TWD"
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
    if session.mode != "LOCAL_PAPER_SIMULATION" or any(
        metadata.get(key) != value for key, value in expected.items()
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
        resolved_persistence = persistence_config or (
            TradingPersistenceConfig.from_environment()
            if journal is None
            else TradingPersistenceConfig()
        )
        resolved_journal = (
            journal
            if journal is not None
            else build_journal_repository(resolved_persistence)
        )
        kill_switch = DurableLocalPaperKillSwitch.recover(
            journal=resolved_journal,
            clock=resolved_clock,
            durability=(
                KillSwitchDurability.POSTGRESQL
                if isinstance(resolved_journal, PostgresJournalRepository)
                else KillSwitchDurability.EPHEMERAL_MEMORY
            ),
        )
        resolved_settings = local_paper_settings or LocalPaperSettings.defaults()
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
        if (
            local_paper_settings is not None
            and resolved_simulation.settings != resolved_settings
        ):
            if simulation_service is None:
                resolved_simulation.close()
            if journal is None:
                resolved_journal.close()
            raise ValueError("local-paper simulation settings mismatch")
        local_paper_session = resolved_journal.session(local_paper_session_id)
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
                if simulation_service is None:
                    resolved_simulation.close()
                if journal is None:
                    resolved_journal.close()
                raise
        try:
            resolved_journal.start_session(local_paper_session)
            existing_records = resolved_journal.records(local_paper_session.session_id)
            if existing_records:
                recovered = rebuild_local_paper_projection(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                    settings_digest=(
                        resolved_simulation.settings.digest
                        if settings_bound
                        else None
                    ),
                )
                resolved_simulation.restore_state(
                    cash=recovered.cash,
                    positions=[
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
                    ],
                    realized_pnl_by_symbol=dict(recovered.realized_pnl_by_symbol),
                    order_states=[
                        dict(state)
                        for state in latest_local_paper_order_states(
                            resolved_journal,
                            session_id=local_paper_session.session_id,
                            require_integrity=(
                                resolved_settings.schema_version
                                == SETTINGS_SCHEMA_V2
                            ),
                        )
                    ],
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
                    daily_filled_buy_notional=(
                        recovered.buy_notional_for_date(
                            resolved_clock.session_date()
                        )
                    ),
                )
            else:
                write_local_paper_checkpoint(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                    settings_digest=(
                        resolved_simulation.settings.digest
                        if settings_bound
                        else None
                    ),
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
                    settings_digest=(
                        resolved_simulation.settings.digest
                        if settings_bound
                        else None
                    ),
                )
            local_paper_commands = LocalPaperCommandService(
                simulation=resolved_simulation,
                journal=resolved_journal,
                session_id=local_paper_session.session_id,
                clock=resolved_clock,
                settings_digest=(
                    resolved_simulation.settings.digest
                    if settings_bound
                    else None
                ),
            )
        except Exception:
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
        )

    def close(self) -> None:
        """Release local-paper workers before closing the provider connection."""

        close_simulation = getattr(self.simulation_service, "close", None)
        if callable(close_simulation):
            close_simulation()
        close_journal = getattr(self.journal, "close", None)
        if callable(close_journal):
            close_journal()
        self.provider.close()
