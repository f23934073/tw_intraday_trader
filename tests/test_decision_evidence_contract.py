from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

import pytest

import signals as signals_package
import signals.decision_evidence as decision_module
import signals.entry_specification as entry_module
import signals.gate_taxonomy as gate_module
import signals.selection as selection_module
from signals.decision_evidence import (
    UNDECIDED,
    DecisionEvidence,
    DecisionEvidenceEnvelope,
    RetroactiveLabel,
    StructuralCompleteness,
    decode_decision_evidence,
    encode_decision_evidence,
)


PURE_MODULES = (
    entry_module,
    gate_module,
    selection_module,
    decision_module,
)


def test_package_surface_does_not_advertise_a_universal_undecided_sentinel():
    assert "UNDECIDED" not in signals_package.__all__
    assert "Undecided" not in signals_package.__all__
    assert not hasattr(signals_package, "UNDECIDED")
    assert not hasattr(signals_package, "Undecided")
    assert UNDECIDED is decision_module.UNDECIDED


def sha(character: str) -> str:
    return character * 64


def complete_evidence() -> DecisionEvidence:
    return DecisionEvidence(
        decision_evidence_contract_version="decision-evidence-v1",
        structural_completeness=StructuralCompleteness.STRUCTURALLY_COMPLETE,
        signal_digest=sha("a"),
        evidence_vector_digest=sha("b"),
        stage_gate_digest=sha("c"),
        candidate_set_digest=sha("d"),
        selection_policy_digest=sha("e"),
        execution_policy_digest=sha("f"),
        cost_policy_digest=sha("0"),
        entry_decision_digest=sha("1"),
    )


def test_decision_evidence_has_exact_ten_fields_and_derived_completeness():
    assert tuple(item.name for item in fields(DecisionEvidence)) == (
        "decision_evidence_contract_version",
        "structural_completeness",
        "signal_digest",
        "evidence_vector_digest",
        "stage_gate_digest",
        "candidate_set_digest",
        "selection_policy_digest",
        "execution_policy_digest",
        "cost_policy_digest",
        "entry_decision_digest",
    )
    evidence = complete_evidence()
    assert evidence.structural_completeness is (
        StructuralCompleteness.STRUCTURALLY_COMPLETE
    )
    assert len(evidence.evidence_digest) == 64
    assert "entry_specification_digest" not in evidence.to_wire()
    assert "evidence_digest" not in evidence.to_wire()

    with pytest.raises(ValueError, match="disagrees"):
        DecisionEvidence(
            decision_evidence_contract_version="decision-evidence-v1",
            structural_completeness=StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
            signal_digest=sha("a"),
            evidence_vector_digest=sha("b"),
            stage_gate_digest=sha("c"),
            candidate_set_digest=sha("d"),
            selection_policy_digest=sha("e"),
            execution_policy_digest=sha("f"),
            cost_policy_digest=sha("0"),
            entry_decision_digest=sha("1"),
        )


def test_partial_is_structurally_incomplete_and_all_undecided_requires_factory():
    partial = DecisionEvidence(
        decision_evidence_contract_version="decision-evidence-v1",
        structural_completeness=StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
        signal_digest=sha("a"),
        evidence_vector_digest=UNDECIDED,
        stage_gate_digest=UNDECIDED,
        candidate_set_digest=UNDECIDED,
        selection_policy_digest=UNDECIDED,
        execution_policy_digest=UNDECIDED,
        cost_policy_digest=UNDECIDED,
        entry_decision_digest=UNDECIDED,
    )
    assert partial.to_wire()["evidence_vector_digest"] == "__UNDECIDED__"

    kwargs = {
        "decision_evidence_contract_version": "decision-evidence-v1",
        "structural_completeness": StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
        "signal_digest": UNDECIDED,
        "evidence_vector_digest": UNDECIDED,
        "stage_gate_digest": UNDECIDED,
        "candidate_set_digest": UNDECIDED,
        "selection_policy_digest": UNDECIDED,
        "execution_policy_digest": UNDECIDED,
        "cost_policy_digest": UNDECIDED,
        "entry_decision_digest": UNDECIDED,
    }
    with pytest.raises(ValueError, match="explicit legacy context"):
        DecisionEvidence(**kwargs)  # type: ignore[arg-type]
    for context in ("RETROACTIVE_LABEL", "LEGACY_IMPORT"):
        legacy = DecisionEvidence.undecided_all(context=context)  # type: ignore[arg-type]
        assert legacy.structural_completeness is (
            StructuralCompleteness.STRUCTURALLY_INCOMPLETE
        )
        assert set(legacy.to_wire().values()) >= {"__UNDECIDED__"}
    with pytest.raises(ValueError, match="requires RETROACTIVE_LABEL"):
        DecisionEvidence.undecided_all(context="NEW_INTENT")  # type: ignore[arg-type]


def test_envelope_absent_empty_present_are_exact_inverses():
    evidence = complete_evidence()
    encoded_absent = encode_decision_evidence(None)
    encoded_empty = encode_decision_evidence({})
    encoded_present = encode_decision_evidence(evidence)

    assert encoded_absent == {
        "envelope_version": "decision-evidence-envelope-v1",
        "presence": "ABSENT",
    }
    assert encoded_empty == {
        "envelope_version": "decision-evidence-envelope-v1",
        "presence": "EMPTY",
        "evidence": {},
    }
    assert encoded_present["presence"] == "PRESENT"
    assert decode_decision_evidence(encoded_absent) is None
    assert decode_decision_evidence(encoded_empty) == {}
    assert decode_decision_evidence(encoded_present) == evidence

    factory_evidence = DecisionEvidence.undecided_all(context="LEGACY_IMPORT")
    assert decode_decision_evidence(encode_decision_evidence(factory_evidence)) == (
        factory_evidence
    )


@pytest.mark.parametrize(
    "payload",
    (
        {
            "envelope_version": "decision-evidence-envelope-v1",
            "presence": "ABSENT",
            "evidence": None,
        },
        {
            "envelope_version": "decision-evidence-envelope-v1",
            "presence": "EMPTY",
        },
        {
            "envelope_version": "decision-evidence-envelope-v1",
            "presence": "PRESENT",
            "evidence": {},
        },
    ),
)
def test_envelope_rejects_every_noncanonical_presence_combination(payload):
    with pytest.raises(ValueError):
        DecisionEvidenceEnvelope.decode(payload)


def test_retroactive_label_is_provenance_only_and_structurally_incomplete():
    labelled_at = datetime.fromisoformat("2026-08-29T10:00:00+08:00")
    label = RetroactiveLabel(
        schema_version="retroactive-label-v1",
        target_record_id="intent-1",
        target_record_kind="strategy_paper_intent.v1",
        target_journal_sequence=42,
        assigned_completeness=StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
        rule_id="legacy-evidence-gap",
        rule_version="v1",
        labelled_by="research-review",
        labelled_at=labelled_at,
        provenance_note="target replay bytes remain unchanged",
    )

    assert len(label.label_digest) == 64
    assert label.to_wire()["labelled_at"] == labelled_at.isoformat()
    assert not hasattr(label, "target_record")
    with pytest.raises(ValueError, match="only structural incompleteness"):
        RetroactiveLabel(
            **{
                **label.__dict__,
                "assigned_completeness": StructuralCompleteness.STRUCTURALLY_COMPLETE,
            }
        )


def test_structural_enum_has_no_legacy_or_qualification_level_members():
    assert tuple(StructuralCompleteness) == (
        StructuralCompleteness.STRUCTURALLY_COMPLETE,
        StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
    )
    assert not hasattr(decision_module, "EvidenceCompleteness")
    assert not hasattr(decision_module, "LEGACY_ABSENT")


def test_m_t7_ast_import_firewall_allows_only_stdlib_and_two_named_repo_imports():
    allowed_repo_imports = {
        "signals.models": {"MomentumStage"},
        "signals._contract_wire": {
            "UNDECIDED",
            "UNDECIDED_WIRE",
            "Undecided",
            "digest",
            "to_wire",
        },
    }
    forbidden_roots = {
        "simulation",
        "trading",
        "runtime",
        "dashboard",
        "config",
        "features",
        "strategy_catalog",
    }
    for module in PURE_MODULES:
        path = Path(module.__file__ or "")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in sys.stdlib_module_names
            elif isinstance(node, ast.ImportFrom):
                imported_module = node.module or ""
                root = imported_module.split(".")[0]
                assert root not in forbidden_roots
                if imported_module in allowed_repo_imports:
                    assert {alias.name for alias in node.names} <= allowed_repo_imports[
                        imported_module
                    ]
                else:
                    assert imported_module == "__future__" or root in sys.stdlib_module_names
                if root == "signals":
                    assert imported_module in {"signals.models", "signals._contract_wire"}


@dataclass(frozen=True)
class WireFixture:
    amount: Decimal
    occurred_at: datetime
    session_date: date
    status: StructuralCompleteness
    values: tuple[str, ...]
    metadata: dict[str, object]


# Regression lock for the shared canonical wire of WIRE_FIXTURE. The four
# contract modules now delegate to the single signals._contract_wire helper, so
# this digest must stay byte-identical across all of them and across edits.
WIRE_FIXTURE_DIGEST = (
    "301441422bc16e600c0c7095ffc8346a27052d33948b3adb60f567090ecd4e53"
)

# Frozen public contract digests that Slice 2 must not disturb.
GATE_TAXONOMY_DIGEST_FROZEN = (
    "a294aecb7466a046001b8ad41d2a559ae4b77f3b81fbaff594d6c3f161a1b035"
)
LEGACY_MOMENTUM_V0_DIGEST_FROZEN = (
    "f2f0c7fcbdcfdc9d520c8650341dbd72cd0b34ddd1b26abe8920706339356c6b"
)
LEGACY_ATOMIC_V0_DIGEST_FROZEN = (
    "ffe5e892132de0f10020076b25895334a9e153a32a9626be832d3519944330f8"
)


def test_m_t8_four_way_to_wire_identity_and_m_t9_idempotence():
    fixture = WireFixture(
        amount=Decimal("1.00"),
        occurred_at=datetime.fromisoformat("2026-08-29T09:15:00+08:00"),
        session_date=date(2026, 8, 29),
        status=StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
        values=("first", "second"),
        metadata={"enabled": True, "missing": None, "count": 2},
    )
    outputs = tuple(module._to_wire(fixture) for module in PURE_MODULES)

    assert outputs[1:] == outputs[:-1]
    for module, output in zip(PURE_MODULES, outputs, strict=True):
        assert module._to_wire(output) == output

    # All four modules now share one Undecided class and one UNDECIDED instance.
    sentinels = tuple(module.UNDECIDED for module in PURE_MODULES)
    classes = tuple(module.Undecided for module in PURE_MODULES)
    assert all(sentinel is sentinels[0] for sentinel in sentinels)
    assert all(cls is classes[0] for cls in classes)

    # Every module accepts every other module's singleton (cross-composition).
    for producer in PURE_MODULES:
        for consumer in PURE_MODULES:
            assert consumer._to_wire(producer.UNDECIDED) == "__UNDECIDED__"

    # The fixture wire and its hard-coded digest remain byte-identical.
    digests = tuple(module._digest(fixture) for module in PURE_MODULES)
    assert all(digest == digests[0] for digest in digests)
    assert digests[0] == WIRE_FIXTURE_DIGEST

    # The three public contract digests remain unchanged.
    assert gate_module.GATE_TAXONOMY_DIGEST == GATE_TAXONOMY_DIGEST_FROZEN
    assert (
        selection_module.LEGACY_MOMENTUM_V0.policy_digest
        == LEGACY_MOMENTUM_V0_DIGEST_FROZEN
    )
    assert (
        selection_module.LEGACY_ATOMIC_V0.policy_digest
        == LEGACY_ATOMIC_V0_DIGEST_FROZEN
    )


def test_m_t10_key_order_is_digest_independent_and_tuple_order_is_significant():
    for module in PURE_MODULES:
        assert module._digest({"a": 1, "b": 2}) == module._digest({"b": 2, "a": 1})
        assert module._digest(("a", "b")) != module._digest(("b", "a"))


class FixtureEnum(StrEnum):
    VALUE = "VALUE"


@pytest.mark.parametrize("module", PURE_MODULES)
def test_m_t11_naive_datetime_float_and_unknown_type_are_rejected(module):
    with pytest.raises(ValueError, match="timezone-aware"):
        module._to_wire(datetime(2026, 8, 29, 9, 15))
    with pytest.raises(ValueError, match="float"):
        module._to_wire(1.5)
    with pytest.raises(ValueError, match="unsupported"):
        module._to_wire(object())
    assert module._to_wire(FixtureEnum.VALUE) == "VALUE"


def test_m_t12_each_module_undecided_token_changes_digest():
    for module in PURE_MODULES:
        assert module._to_wire(module.UNDECIDED) == "__UNDECIDED__"
        assert module._digest({"value": module.UNDECIDED}) != module._digest(
            {"value": "decided"}
        )
