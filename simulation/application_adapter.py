"""Adapter from the framework-free command path to legacy local-paper simulation."""

from __future__ import annotations

from typing import Any

from simulation.service import SimulationService
from trading.application import ApprovedOrderCommand


class LocalPaperSimulationCommandAdapter:
    """Compatibility adapter; routes do not use it until the migration gate passes."""

    def __init__(self, service: SimulationService) -> None:
        self._service = service

    def submit(self, approved: ApprovedOrderCommand) -> dict[str, Any]:
        if not isinstance(approved, ApprovedOrderCommand):
            raise TypeError("Local Paper adapter 只接受 ApprovedOrderCommand")
        command = approved.command
        order, _ = self._service.submit_order(
            symbol=command.symbol,
            side=command.side.value,
            quantity_shares=command.quantity_shares,
            limit_price=command.limit_price,
            idempotency_key=command.idempotency_key,
            origin=command.origin.value,
            strategy_id=command.strategy_id,
            strategy_version=command.strategy_version,
            attempt=command.attempt,
            predecessor_order_id=command.predecessor_order_id,
        )
        return order
