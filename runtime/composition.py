"""The sole construction point for the current local runtime."""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.service import DashboardService
from market_data.provider import MarketDataProvider
from runtime.clock import Clock, SystemClock
from runtime.in_memory import InMemoryJournalRepository, InMemoryProjectionRepository
from runtime.ports import JournalRepository, OrderCommandHandler, ProjectionRepository
from simulation.service import SimulationService


@dataclass
class RuntimeComposition:
    """Wires concrete local adapters while keeping services API-compatible."""

    provider: MarketDataProvider
    dashboard_service: DashboardService
    simulation_service: OrderCommandHandler
    clock: Clock
    journal: JournalRepository
    projections: ProjectionRepository

    @classmethod
    def create(
        cls,
        provider: MarketDataProvider,
        *,
        dashboard_service: DashboardService | None = None,
        simulation_service: SimulationService | None = None,
        clock: Clock | None = None,
        journal: JournalRepository | None = None,
        projections: ProjectionRepository | None = None,
    ) -> "RuntimeComposition":
        """Build the current ephemeral composition without provider I/O."""

        return cls(
            provider=provider,
            dashboard_service=dashboard_service or DashboardService(provider),
            simulation_service=simulation_service or SimulationService(provider),
            clock=clock or SystemClock(),
            journal=journal or InMemoryJournalRepository(),
            projections=projections or InMemoryProjectionRepository(),
        )

    def close(self) -> None:
        """Release local-paper workers before closing the provider connection."""

        close_simulation = getattr(self.simulation_service, "close", None)
        if callable(close_simulation):
            close_simulation()
        self.provider.close()
