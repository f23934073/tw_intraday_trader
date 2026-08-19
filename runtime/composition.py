"""The sole construction point for the current local runtime."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

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
from runtime.in_memory import InMemoryJournalRepository, InMemoryProjectionRepository
from runtime.ports import JournalRepository, OrderCommandHandler, ProjectionRepository
from simulation.application import LocalPaperCommandService
from simulation.service import SimulationService
from trading.journal import JournalSession


@dataclass
class RuntimeComposition:
    """Wires concrete local adapters while keeping services API-compatible."""

    provider: MarketDataProvider
    dashboard_service: DashboardService
    premarket_service: PremarketContextService
    premarket_artifacts: PremarketArtifactRepository
    simulation_service: OrderCommandHandler
    local_paper_commands: LocalPaperCommandService
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
    ) -> "RuntimeComposition":
        """Build the current ephemeral composition without provider I/O."""

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
        resolved_simulation = simulation_service or SimulationService(provider)
        resolved_journal = journal or InMemoryJournalRepository()
        local_paper_session = JournalSession(
            session_id=f"local-paper-{uuid4().hex}",
            started_at=resolved_clock.now(),
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "starting_cash": str(resolved_simulation.starting_cash),
                "execution_boundary": "LOCAL_ONLY",
            },
        )
        resolved_journal.start_session(local_paper_session)
        return cls(
            provider=provider,
            dashboard_service=dashboard_service or DashboardService(
                provider,
                premarket_service=resolved_premarket,
            ),
            premarket_service=resolved_premarket,
            premarket_artifacts=resolved_premarket_artifacts,
            simulation_service=resolved_simulation,
            local_paper_commands=LocalPaperCommandService(
                simulation=resolved_simulation,
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
        self.provider.close()
