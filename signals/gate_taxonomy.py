"""Pure declaration table for the seven observed Momentum Entry gates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any, Literal, cast

from strategy_catalog.parameter_schema import canonical_digest


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UNDECIDED_WIRE = "__UNDECIDED__"


class Undecided:
    """Singleton marker used by the shared canonicalization contract."""

    _instance: Undecided | None = None

    def __new__(cls) -> Undecided:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNDECIDED"


UNDECIDED = Undecided()


def _to_wire(value: object) -> object:
    if isinstance(value, Undecided):
        return _UNDECIDED_WIRE
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _to_wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: _to_wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_to_wire(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _to_wire(value.value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise ValueError("float values are forbidden in canonical wire contracts")
    raise ValueError(f"unsupported canonical wire type: {type(value).__name__}")


def _digest(value: object) -> str:
    wire = cast(Mapping[str, Any] | list[Any], _to_wire(value))
    return canonical_digest(wire)


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class GateClass(StrEnum):
    ALPHA = "ALPHA"
    CONFIG_DEPENDENT_DUPLICATE = "CONFIG_DEPENDENT_DUPLICATE"
    DEFENSIVE_CONTRACT = "DEFENSIVE_CONTRACT"
    EFFECTIVE_UNSOUND = "EFFECTIVE_UNSOUND"


class FalsifyingCaseKind(StrEnum):
    LEGAL_REACHABLE = "LEGAL_REACHABLE"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    NONE = "NONE"


class RemediationStatus(StrEnum):
    NONE_REQUIRED = "NONE_REQUIRED"
    OPEN = "OPEN"
    SLICE1_PRODUCER_PAYLOAD_FIX = "SLICE1_PRODUCER_PAYLOAD_FIX"
    PENDING_D3 = "PENDING_D3"


@dataclass(frozen=True)
class GateDeclaration:
    gate_id: str
    gate_class: GateClass
    consumer_site: str
    producer_contract: str | None
    depends_on: tuple[str, ...]
    falsifying_case_kind: FalsifyingCaseKind
    bypass_path: str | None
    remediation_status: RemediationStatus
    disposition_gate: Literal["D3"] | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.gate_id, "gate_id")
        if not isinstance(self.gate_class, GateClass):
            raise TypeError("gate_class must be GateClass")
        _require_non_empty(self.consumer_site, "consumer_site")
        if self.producer_contract is not None:
            _require_non_empty(self.producer_contract, "producer_contract")
        if not isinstance(self.depends_on, tuple):
            raise TypeError("depends_on must be a tuple")
        for gate_id in self.depends_on:
            _require_non_empty(gate_id, "depends_on gate_id")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on must not contain duplicates")
        if not isinstance(self.falsifying_case_kind, FalsifyingCaseKind):
            raise TypeError("falsifying_case_kind must be FalsifyingCaseKind")
        if self.bypass_path is not None:
            _require_non_empty(self.bypass_path, "bypass_path")
        if not isinstance(self.remediation_status, RemediationStatus):
            raise TypeError("remediation_status must be RemediationStatus")
        if self.disposition_gate not in {None, "D3"}:
            raise ValueError("disposition_gate must be D3 or None")
        if not isinstance(self.evidence_refs, tuple):
            raise TypeError("evidence_refs must be a tuple")
        for reference in self.evidence_refs:
            _require_non_empty(reference, "evidence_ref")

    @property
    def digest(self) -> str:
        return _digest(self)

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


G1_EVALUATION_STATUS_TRIGGERED = "gate.evaluation_status_triggered"
G2_MOMENTUM_ACCELERATION_CONFIRMED = "gate.momentum_acceleration_confirmed"
G3_ENABLED_SIGNAL_FAMILIES = "gate.enabled_signal_families"
G4_AVAILABILITY_EVALUATED = "gate.availability_evaluated"
G5_SIGNAL_DATA_HEALTH_HEALTHY = "gate.signal_data_health_healthy"
G6_PRICE_STATUS_VALID = "gate.price_status_valid"
G7_ENABLED_STAGES = "gate.enabled_stages"


GATE_DECLARATIONS = (
    GateDeclaration(
        gate_id=G1_EVALUATION_STATUS_TRIGGERED,
        gate_class=GateClass.ALPHA,
        consumer_site="simulation/continuous_strategy.py:612",
        producer_contract="signals/opening_momentum.py:81 / signals/momentum.py",
        depends_on=(),
        falsifying_case_kind=FalsifyingCaseKind.LEGAL_REACHABLE,
        bypass_path=None,
        remediation_status=RemediationStatus.NONE_REQUIRED,
        disposition_gate=None,
        evidence_refs=(
            "simulation/continuous_strategy.py:612",
            "signals/opening_momentum.py:81",
            "signals/momentum.py",
        ),
    ),
    GateDeclaration(
        gate_id=G2_MOMENTUM_ACCELERATION_CONFIRMED,
        gate_class=GateClass.CONFIG_DEPENDENT_DUPLICATE,
        consumer_site="simulation/continuous_strategy.py:613",
        producer_contract="config/momentum.py:49, :199, :223",
        depends_on=(G1_EVALUATION_STATUS_TRIGGERED,),
        falsifying_case_kind=FalsifyingCaseKind.LEGAL_REACHABLE,
        bypass_path=None,
        remediation_status=RemediationStatus.PENDING_D3,
        disposition_gate="D3",
        evidence_refs=(
            "simulation/continuous_strategy.py:613",
            "config/momentum.py:49",
            "config/momentum.py:199",
            "config/momentum.py:223",
        ),
    ),
    GateDeclaration(
        gate_id=G3_ENABLED_SIGNAL_FAMILIES,
        gate_class=GateClass.DEFENSIVE_CONTRACT,
        consumer_site="simulation/continuous_strategy.py:611",
        producer_contract="signals/models.py:19",
        depends_on=(),
        falsifying_case_kind=FalsifyingCaseKind.CONTRACT_VIOLATION,
        bypass_path=None,
        remediation_status=RemediationStatus.NONE_REQUIRED,
        disposition_gate="D3",
        evidence_refs=(
            "simulation/continuous_strategy.py:31",
            "simulation/continuous_strategy.py:611",
            "signals/models.py:19",
        ),
    ),
    GateDeclaration(
        gate_id=G4_AVAILABILITY_EVALUATED,
        gate_class=GateClass.DEFENSIVE_CONTRACT,
        consumer_site="simulation/continuous_strategy.py:609",
        producer_contract="dashboard/momentum.py:369",
        depends_on=(),
        falsifying_case_kind=FalsifyingCaseKind.CONTRACT_VIOLATION,
        bypass_path=None,
        remediation_status=RemediationStatus.NONE_REQUIRED,
        disposition_gate="D3",
        evidence_refs=(
            "simulation/continuous_strategy.py:609",
            "dashboard/momentum.py:369",
        ),
    ),
    GateDeclaration(
        gate_id=G5_SIGNAL_DATA_HEALTH_HEALTHY,
        gate_class=GateClass.DEFENSIVE_CONTRACT,
        consumer_site="simulation/continuous_strategy.py:614",
        producer_contract="features/engine.py:152-164",
        depends_on=(),
        falsifying_case_kind=FalsifyingCaseKind.CONTRACT_VIOLATION,
        bypass_path=None,
        remediation_status=RemediationStatus.NONE_REQUIRED,
        disposition_gate="D3",
        evidence_refs=(
            "simulation/continuous_strategy.py:614",
            "features/engine.py:152-164",
        ),
    ),
    GateDeclaration(
        gate_id=G6_PRICE_STATUS_VALID,
        gate_class=GateClass.DEFENSIVE_CONTRACT,
        consumer_site="simulation/continuous_strategy.py:615",
        producer_contract=None,
        depends_on=(),
        falsifying_case_kind=FalsifyingCaseKind.CONTRACT_VIOLATION,
        bypass_path=None,
        remediation_status=RemediationStatus.NONE_REQUIRED,
        disposition_gate="D3",
        evidence_refs=(
            "simulation/continuous_strategy.py:615",
            "dashboard/momentum.py:_serialize_candidate",
        ),
    ),
    GateDeclaration(
        gate_id=G7_ENABLED_STAGES,
        gate_class=GateClass.EFFECTIVE_UNSOUND,
        consumer_site="simulation/continuous_strategy.py:610",
        producer_contract="signals/momentum_state.py:487-525 + dashboard/momentum.py:369",
        depends_on=(),
        falsifying_case_kind=FalsifyingCaseKind.LEGAL_REACHABLE,
        bypass_path=(
            "episode-close tick: update/projection current_stage=ACCELERATING with "
            "episode_closed_status=INVALIDATED; realtime payload lacks episode.status"
        ),
        remediation_status=RemediationStatus.SLICE1_PRODUCER_PAYLOAD_FIX,
        disposition_gate="D3",
        evidence_refs=(
            "simulation/continuous_strategy.py:32",
            "simulation/continuous_strategy.py:610",
            "signals/momentum_state.py:487-525",
            "dashboard/momentum.py:369",
        ),
    ),
)


if len({item.gate_id for item in GATE_DECLARATIONS}) != len(GATE_DECLARATIONS):
    raise ValueError("gate declaration ids must be unique")
_GATE_IDS = {item.gate_id for item in GATE_DECLARATIONS}
if any(not set(item.depends_on) <= _GATE_IDS for item in GATE_DECLARATIONS):
    raise ValueError("gate dependency references an unknown gate")


GATE_DECLARATION_BY_ID = {item.gate_id: item for item in GATE_DECLARATIONS}
GATE_TAXONOMY_DIGEST = _digest(GATE_DECLARATIONS)


def get_gate_declaration(gate_id: str) -> GateDeclaration:
    try:
        return GATE_DECLARATION_BY_ID[gate_id]
    except KeyError as error:
        raise KeyError(f"unknown gate declaration: {gate_id}") from error
