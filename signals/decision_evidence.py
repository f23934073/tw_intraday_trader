"""Pure decision-evidence identity, envelope, and retroactive-label contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, cast

from signals._contract_wire import UNDECIDED, Undecided
from signals._contract_wire import UNDECIDED_WIRE as _UNDECIDED_WIRE
from signals._contract_wire import digest as _digest
from signals._contract_wire import to_wire as _to_wire


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIGEST_FIELD_NAMES = (
    "signal_digest",
    "evidence_vector_digest",
    "stage_gate_digest",
    "candidate_set_digest",
    "selection_policy_digest",
    "execution_policy_digest",
    "cost_policy_digest",
    "entry_decision_digest",
)


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_sha256_or_undecided(value: str | Undecided, field_name: str) -> None:
    if value is UNDECIDED:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 digest or UNDECIDED")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class StructuralCompleteness(StrEnum):
    STRUCTURALLY_COMPLETE = "STRUCTURALLY_COMPLETE"
    STRUCTURALLY_INCOMPLETE = "STRUCTURALLY_INCOMPLETE"


@dataclass(frozen=True, init=False)
class DecisionEvidence:
    decision_evidence_contract_version: Literal["decision-evidence-v1"]
    structural_completeness: StructuralCompleteness
    signal_digest: str | Undecided
    evidence_vector_digest: str | Undecided
    stage_gate_digest: str | Undecided
    candidate_set_digest: str | Undecided
    selection_policy_digest: str | Undecided
    execution_policy_digest: str | Undecided
    cost_policy_digest: str | Undecided
    entry_decision_digest: str | Undecided

    def __init__(
        self,
        *,
        decision_evidence_contract_version: Literal["decision-evidence-v1"],
        structural_completeness: StructuralCompleteness,
        signal_digest: str | Undecided,
        evidence_vector_digest: str | Undecided,
        stage_gate_digest: str | Undecided,
        candidate_set_digest: str | Undecided,
        selection_policy_digest: str | Undecided,
        execution_policy_digest: str | Undecided,
        cost_policy_digest: str | Undecided,
        entry_decision_digest: str | Undecided,
    ) -> None:
        values = {
            "decision_evidence_contract_version": decision_evidence_contract_version,
            "structural_completeness": structural_completeness,
            "signal_digest": signal_digest,
            "evidence_vector_digest": evidence_vector_digest,
            "stage_gate_digest": stage_gate_digest,
            "candidate_set_digest": candidate_set_digest,
            "selection_policy_digest": selection_policy_digest,
            "execution_policy_digest": execution_policy_digest,
            "cost_policy_digest": cost_policy_digest,
            "entry_decision_digest": entry_decision_digest,
        }
        self._assign(values)
        self._validate(allow_all_undecided=False)

    def _assign(self, values: Mapping[str, object]) -> None:
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def _validate(self, *, allow_all_undecided: bool) -> None:
        if self.decision_evidence_contract_version != "decision-evidence-v1":
            raise ValueError("unsupported decision evidence contract version")
        if not isinstance(self.structural_completeness, StructuralCompleteness):
            raise TypeError("structural_completeness must be StructuralCompleteness")
        digest_values = tuple(getattr(self, name) for name in _DIGEST_FIELD_NAMES)
        for name, value in zip(_DIGEST_FIELD_NAMES, digest_values, strict=True):
            _require_sha256_or_undecided(value, name)
        all_decided = all(value is not UNDECIDED for value in digest_values)
        all_undecided = all(value is UNDECIDED for value in digest_values)
        derived = (
            StructuralCompleteness.STRUCTURALLY_COMPLETE
            if all_decided
            else StructuralCompleteness.STRUCTURALLY_INCOMPLETE
        )
        if self.structural_completeness is not derived:
            raise ValueError("structural_completeness disagrees with the eight digest inputs")
        if all_undecided and not allow_all_undecided:
            raise ValueError("all-UNDECIDED evidence requires an explicit legacy context factory")

    @classmethod
    def undecided_all(
        cls,
        *,
        context: Literal["RETROACTIVE_LABEL", "LEGACY_IMPORT"],
    ) -> DecisionEvidence:
        if context not in {"RETROACTIVE_LABEL", "LEGACY_IMPORT"}:
            raise ValueError("all-UNDECIDED evidence requires RETROACTIVE_LABEL or LEGACY_IMPORT")
        evidence = object.__new__(cls)
        evidence._assign(
            {
                "decision_evidence_contract_version": "decision-evidence-v1",
                "structural_completeness": StructuralCompleteness.STRUCTURALLY_INCOMPLETE,
                **{name: UNDECIDED for name in _DIGEST_FIELD_NAMES},
            }
        )
        evidence._validate(allow_all_undecided=True)
        return evidence

    @classmethod
    def from_wire(cls, payload: Mapping[str, object]) -> DecisionEvidence:
        expected = {
            "decision_evidence_contract_version",
            "structural_completeness",
            *_DIGEST_FIELD_NAMES,
        }
        if set(payload) != expected:
            raise ValueError("decision evidence wire payload has unexpected fields")
        try:
            completeness = StructuralCompleteness(str(payload["structural_completeness"]))
        except ValueError as error:
            raise ValueError("invalid structural_completeness") from error
        digests = {
            name: (
                UNDECIDED if payload[name] == _UNDECIDED_WIRE else payload[name]
            )
            for name in _DIGEST_FIELD_NAMES
        }
        if all(value is UNDECIDED for value in digests.values()):
            evidence = cls.undecided_all(context="LEGACY_IMPORT")
            if payload["decision_evidence_contract_version"] != "decision-evidence-v1":
                raise ValueError("unsupported decision evidence contract version")
            if completeness is not evidence.structural_completeness:
                raise ValueError("structural_completeness disagrees with the eight digest inputs")
            return evidence
        return cls(
            decision_evidence_contract_version=cast(
                Literal["decision-evidence-v1"],
                payload["decision_evidence_contract_version"],
            ),
            structural_completeness=completeness,
            **cast(dict[str, str | Undecided], digests),
        )

    @property
    def evidence_digest(self) -> str:
        return _digest(self)

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


@dataclass(frozen=True)
class DecisionEvidenceEnvelope:
    envelope_version: Literal["decision-evidence-envelope-v1"]
    presence: Literal["ABSENT", "EMPTY", "PRESENT"]
    evidence: DecisionEvidence | Mapping[str, object] | None

    def __post_init__(self) -> None:
        if self.envelope_version != "decision-evidence-envelope-v1":
            raise ValueError("unsupported decision evidence envelope version")
        if self.presence not in {"ABSENT", "EMPTY", "PRESENT"}:
            raise ValueError("invalid decision evidence envelope presence")
        if self.presence == "ABSENT":
            if self.evidence is not None:
                raise ValueError("ABSENT envelope must not carry evidence")
        elif self.presence == "EMPTY":
            if not isinstance(self.evidence, Mapping) or dict(self.evidence) != {}:
                raise ValueError("EMPTY envelope must carry exactly an empty object")
        elif not isinstance(self.evidence, DecisionEvidence):
            raise ValueError("PRESENT envelope must carry DecisionEvidence")

    @classmethod
    def from_value(
        cls,
        value: DecisionEvidence | Mapping[str, object] | None,
    ) -> DecisionEvidenceEnvelope:
        if value is None:
            return cls(
                envelope_version="decision-evidence-envelope-v1",
                presence="ABSENT",
                evidence=None,
            )
        if isinstance(value, Mapping):
            if dict(value) != {}:
                raise ValueError("only an explicit empty mapping is a legacy EMPTY envelope")
            return cls(
                envelope_version="decision-evidence-envelope-v1",
                presence="EMPTY",
                evidence={},
            )
        if isinstance(value, DecisionEvidence):
            return cls(
                envelope_version="decision-evidence-envelope-v1",
                presence="PRESENT",
                evidence=value,
            )
        raise TypeError("envelope value must be None, {}, or DecisionEvidence")

    @classmethod
    def encode(
        cls,
        value: DecisionEvidence | Mapping[str, object] | None,
    ) -> dict[str, object]:
        return cls.from_value(value).to_wire()

    @classmethod
    def decode(
        cls,
        payload: Mapping[str, object],
    ) -> DecisionEvidence | dict[str, object] | None:
        if not isinstance(payload, Mapping):
            raise TypeError("decision evidence envelope must be a mapping")
        try:
            version = payload["envelope_version"]
            presence = str(payload["presence"])
        except KeyError as error:
            raise ValueError("decision evidence envelope is missing required fields") from error
        if version != "decision-evidence-envelope-v1":
            raise ValueError("unsupported decision evidence envelope version")
        if presence not in {"ABSENT", "EMPTY", "PRESENT"}:
            raise ValueError("invalid decision evidence envelope presence")
        if presence == "ABSENT":
            if set(payload) != {"envelope_version", "presence"}:
                raise ValueError("ABSENT envelope must omit evidence")
            return None
        if presence == "EMPTY":
            if set(payload) != {"envelope_version", "presence", "evidence"} or payload.get(
                "evidence"
            ) != {}:
                raise ValueError("EMPTY envelope must carry exactly an empty object")
            return {}
        if set(payload) != {"envelope_version", "presence", "evidence"} or not isinstance(
            payload.get("evidence"),
            Mapping,
        ):
            raise ValueError("PRESENT envelope must carry a decision evidence object")
        return DecisionEvidence.from_wire(cast(Mapping[str, object], payload["evidence"]))

    def to_wire(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "envelope_version": self.envelope_version,
            "presence": self.presence,
        }
        if self.presence == "EMPTY":
            payload["evidence"] = {}
        elif self.presence == "PRESENT":
            assert isinstance(self.evidence, DecisionEvidence)
            payload["evidence"] = self.evidence.to_wire()
        return payload


@dataclass(frozen=True)
class RetroactiveLabel:
    schema_version: Literal["retroactive-label-v1"]
    target_record_id: str
    target_record_kind: str
    target_journal_sequence: int
    assigned_completeness: StructuralCompleteness
    rule_id: str
    rule_version: str
    labelled_by: str
    labelled_at: datetime
    provenance_note: str

    def __post_init__(self) -> None:
        if self.schema_version != "retroactive-label-v1":
            raise ValueError("unsupported retroactive label schema")
        for value, name in (
            (self.target_record_id, "target_record_id"),
            (self.target_record_kind, "target_record_kind"),
            (self.rule_id, "rule_id"),
            (self.rule_version, "rule_version"),
            (self.labelled_by, "labelled_by"),
            (self.provenance_note, "provenance_note"),
        ):
            _require_non_empty(value, name)
        if (
            isinstance(self.target_journal_sequence, bool)
            or not isinstance(self.target_journal_sequence, int)
            or self.target_journal_sequence < 0
        ):
            raise ValueError("target_journal_sequence must be a non-negative integer")
        if self.assigned_completeness is not (
            StructuralCompleteness.STRUCTURALLY_INCOMPLETE
        ):
            raise ValueError("Slice 1 retroactive labels may assign only structural incompleteness")
        _require_aware(self.labelled_at, "labelled_at")

    @property
    def label_digest(self) -> str:
        return _digest(self)

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


def encode_decision_evidence(
    value: DecisionEvidence | Mapping[str, object] | None,
) -> dict[str, object]:
    return DecisionEvidenceEnvelope.encode(value)


def decode_decision_evidence(
    payload: Mapping[str, object],
) -> DecisionEvidence | dict[str, object] | None:
    return DecisionEvidenceEnvelope.decode(payload)
