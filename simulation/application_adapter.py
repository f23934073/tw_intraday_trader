"""Adapter from the framework-free command path to legacy local-paper simulation."""

from __future__ import annotations

from typing import Any

from simulation.service import SimulationService
from trading.risk import OrderCommand


class LocalPaperSimulationCommandAdapter:
    """Compatibility adapter; routes do not use it until the migration gate passes."""

    def __init__(self, service: SimulationService) -> None:
        self._service = service

    def submit(self, command: OrderCommand) -> dict[str, Any]:
        if command.quantity_shares % 1_000 != 0:
            raise ValueError("local-paper adapter only supports common-lot quantities")
        order, _ = self._service.submit_order(
            symbol=command.symbol,
            side=command.side.value,
            lots=command.quantity_shares // 1_000,
            limit_price=float(command.limit_price),
            idempotency_key=command.idempotency_key,
            origin=command.origin.value,
        )
        return order
