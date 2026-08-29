from __future__ import annotations

from dataclasses import replace

import pytest

from signals.gate_taxonomy import (
    G1_EVALUATION_STATUS_TRIGGERED,
    G2_MOMENTUM_ACCELERATION_CONFIRMED,
    G3_ENABLED_SIGNAL_FAMILIES,
    G4_AVAILABILITY_EVALUATED,
    G5_SIGNAL_DATA_HEALTH_HEALTHY,
    G6_PRICE_STATUS_VALID,
    G7_ENABLED_STAGES,
    GATE_DECLARATIONS,
    GATE_TAXONOMY_DIGEST,
    FalsifyingCaseKind,
    GateClass,
    RemediationStatus,
    _digest,
    get_gate_declaration,
)


def test_seven_gate_ids_classes_and_remediation_are_stable():
    assert tuple(item.gate_id for item in GATE_DECLARATIONS) == (
        G1_EVALUATION_STATUS_TRIGGERED,
        G2_MOMENTUM_ACCELERATION_CONFIRMED,
        G3_ENABLED_SIGNAL_FAMILIES,
        G4_AVAILABILITY_EVALUATED,
        G5_SIGNAL_DATA_HEALTH_HEALTHY,
        G6_PRICE_STATUS_VALID,
        G7_ENABLED_STAGES,
    )
    assert tuple(item.gate_class for item in GATE_DECLARATIONS) == (
        GateClass.ALPHA,
        GateClass.CONFIG_DEPENDENT_DUPLICATE,
        GateClass.DEFENSIVE_CONTRACT,
        GateClass.DEFENSIVE_CONTRACT,
        GateClass.DEFENSIVE_CONTRACT,
        GateClass.DEFENSIVE_CONTRACT,
        GateClass.EFFECTIVE_UNSOUND,
    )
    assert GATE_DECLARATIONS[0].remediation_status is RemediationStatus.NONE_REQUIRED
    assert GATE_DECLARATIONS[1].remediation_status is RemediationStatus.PENDING_D3
    assert GATE_DECLARATIONS[-1].remediation_status is (
        RemediationStatus.SLICE1_PRODUCER_PAYLOAD_FIX
    )
    assert GATE_DECLARATIONS[-1].bypass_path is not None


def test_corrected_consumer_and_producer_evidence_lines_are_exact():
    assert tuple(item.consumer_site for item in GATE_DECLARATIONS) == (
        "simulation/continuous_strategy.py:612",
        "simulation/continuous_strategy.py:613",
        "simulation/continuous_strategy.py:611",
        "simulation/continuous_strategy.py:609",
        "simulation/continuous_strategy.py:614",
        "simulation/continuous_strategy.py:615",
        "simulation/continuous_strategy.py:610",
    )
    assert get_gate_declaration(G2_MOMENTUM_ACCELERATION_CONFIRMED).producer_contract == (
        "config/momentum.py:49, :199, :223"
    )
    assert get_gate_declaration(G5_SIGNAL_DATA_HEALTH_HEALTHY).producer_contract == (
        "features/engine.py:152-164"
    )
    assert get_gate_declaration(G7_ENABLED_STAGES).producer_contract == (
        "signals/momentum_state.py:487-525 + dashboard/momentum.py:369"
    )
    assert GATE_DECLARATIONS[2].falsifying_case_kind is (
        FalsifyingCaseKind.CONTRACT_VIOLATION
    )


def test_gate_table_digest_is_ordered_and_declarations_are_individually_identified():
    assert GATE_TAXONOMY_DIGEST == _digest(GATE_DECLARATIONS)
    assert GATE_TAXONOMY_DIGEST != _digest(tuple(reversed(GATE_DECLARATIONS)))
    assert len({item.digest for item in GATE_DECLARATIONS}) == 7


def test_gate_validation_rejects_invalid_dependencies_and_lookup():
    declaration = GATE_DECLARATIONS[0]
    with pytest.raises(ValueError, match="duplicates"):
        replace(declaration, depends_on=("gate.x", "gate.x"))
    with pytest.raises(ValueError, match="consumer_site"):
        replace(declaration, consumer_site="")
    with pytest.raises(KeyError, match="unknown gate"):
        get_gate_declaration("gate.missing")
