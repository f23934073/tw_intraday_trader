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
from simulation.service import SimulationService
from simulation.strategy_flow import StrategyPaperFlowService
from trading.journal import JournalSession
from trading.local_paper import (
    daily_baseline_record,
    latest_local_paper_daily_baseline,
    latest_local_paper_order_states,
    rebuild_local_paper_projection,
    write_local_paper_checkpoint,
)


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
    ) -> "RuntimeComposition":
        """Build one LOCAL_PAPER composition without broker-order I/O."""

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
        resolved_simulation = simulation_service or SimulationService(
            provider,
            clock=resolved_clock,
        )
        local_paper_session_id = "local-paper-runtime-v1"
        local_paper_session = resolved_journal.session(local_paper_session_id)
        if local_paper_session is None:
            local_paper_session = JournalSession(
                session_id=local_paper_session_id,
                started_at=resolved_clock.now(),
                mode="LOCAL_PAPER_SIMULATION",
                metadata={
                    "starting_cash": str(resolved_simulation.starting_cash),
                    "execution_boundary": "LOCAL_ONLY",
                    "journal_backend": (
                        "INJECTED"
                        if journal is not None
                        else resolved_persistence.backend.value.upper()
                    ),
                    "restart_policy": "RESUME_CHECKPOINTED_LOCAL_PAPER_SESSION",
                },
            )
        elif local_paper_session.metadata.get("starting_cash") != str(
            resolved_simulation.starting_cash
        ):
            if simulation_service is None:
                resolved_simulation.close()
            if journal is None:
                resolved_journal.close()
            raise ValueError("local-paper recovery starting_cash conflicts with Journal")
        try:
            resolved_journal.start_session(local_paper_session)
            existing_records = resolved_journal.records(local_paper_session.session_id)
            if existing_records:
                recovered = rebuild_local_paper_projection(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
                )
                resolved_simulation.restore_state(
                    cash=recovered.cash,
                    positions=[
                        {
                            "symbol": position.symbol,
                            "name": position.name,
                            "quantity": position.quantity_shares,
                            "average_price": position.average_price,
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
                )
            else:
                write_local_paper_checkpoint(
                    resolved_journal,
                    session_id=local_paper_session.session_id,
                    starting_cash=resolved_simulation.starting_cash,
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
                )
            local_paper_commands = LocalPaperCommandService(
                simulation=resolved_simulation,
                journal=resolved_journal,
                session_id=local_paper_session.session_id,
                clock=resolved_clock,
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
            ),
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
