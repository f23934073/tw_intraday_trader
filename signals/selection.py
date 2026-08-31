"""Pure, deterministic candidate selection contracts for Momentum Entry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import cmp_to_key
from typing import Any, Literal, cast

from signals._contract_wire import UNDECIDED, Undecided
from signals._contract_wire import digest as _digest
from signals._contract_wire import to_wire as _to_wire


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class SelectionContractError(ValueError):
    """Raised when a candidate set violates a defensive selection contract."""


class SelectionReason(StrEnum):
    SELECTED_RANK_1 = "SELECTED_RANK_1"
    RANKED_NOT_SELECTED = "RANKED_NOT_SELECTED"
    TIE_RESOLVED_BY_TIE_BREAKER = "TIE_RESOLVED_BY_TIE_BREAKER"
    TIE_UNRESOLVED_FAIL_CLOSED = "TIE_UNRESOLVED_FAIL_CLOSED"
    EMPTY_CANDIDATE_SET = "EMPTY_CANDIDATE_SET"
    ELIMINATED_MISSING_SORT_FIELD = "ELIMINATED_MISSING_SORT_FIELD"


@dataclass(frozen=True)
class SelectionCandidate:
    candidate_id: str
    symbol: str
    source_path: Literal["LEGACY_MOMENTUM", "ATOMIC_STRATEGY_SET"]
    evidence_score: int | None
    evidence_signature: str | None
    signal_digest: str | None
    current_stage: str | None
    episode_status: str | None

    def __post_init__(self) -> None:
        _require_non_empty(self.candidate_id, "candidate_id")
        _require_non_empty(self.symbol, "symbol")
        normalized_symbol = self.symbol.strip().upper()
        normalized_candidate_id = self.candidate_id.strip().upper()
        if normalized_candidate_id != normalized_symbol:
            raise ValueError("candidate_id must equal normalized symbol in selection-policy-v1")
        object.__setattr__(self, "candidate_id", normalized_candidate_id)
        object.__setattr__(self, "symbol", normalized_symbol)
        if self.source_path not in {"LEGACY_MOMENTUM", "ATOMIC_STRATEGY_SET"}:
            raise ValueError("invalid selection candidate source_path")
        if self.evidence_score is not None and (
            isinstance(self.evidence_score, bool) or not isinstance(self.evidence_score, int)
        ):
            raise TypeError("evidence_score must be int or None")
        if self.evidence_signature is not None:
            _require_non_empty(self.evidence_signature, "evidence_signature")
        if self.signal_digest is not None:
            _require_sha256(self.signal_digest, "signal_digest")
        if self.current_stage is not None:
            _require_non_empty(self.current_stage, "current_stage")
        if self.episode_status is not None:
            _require_non_empty(self.episode_status, "episode_status")

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


@dataclass(frozen=True)
class SortKey:
    field: Literal["evidence_score", "symbol"]
    direction: Literal["ASC", "DESC"]

    def __post_init__(self) -> None:
        if self.field not in {"evidence_score", "symbol"}:
            raise ValueError("invalid sort field")
        if self.direction not in {"ASC", "DESC"}:
            raise ValueError("invalid sort direction")


@dataclass(frozen=True)
class SelectionPolicy:
    schema_version: Literal["selection-policy-v1"]
    policy_id: str
    sort_keys: tuple[SortKey, ...]
    tie_breakers: tuple[SortKey, ...]
    max_entries_per_evaluation: int
    max_entries_per_session: int | Undecided
    deduplication_key_rule: str | Undecided

    def __post_init__(self) -> None:
        if self.schema_version != "selection-policy-v1":
            raise ValueError("unsupported selection policy schema")
        _require_non_empty(self.policy_id, "policy_id")
        for value, name in (
            (self.sort_keys, "sort_keys"),
            (self.tie_breakers, "tie_breakers"),
        ):
            if not isinstance(value, tuple) or any(not isinstance(item, SortKey) for item in value):
                raise TypeError(f"{name} must be a tuple of SortKey")
        if not self.sort_keys:
            raise ValueError("selection policy requires at least one sort key")
        if self.max_entries_per_evaluation != 1:
            raise ValueError("selection-policy-v1 fixes max_entries_per_evaluation at 1")
        if self.max_entries_per_session is not UNDECIDED and (
            isinstance(self.max_entries_per_session, bool)
            or not isinstance(self.max_entries_per_session, int)
            or self.max_entries_per_session <= 0
        ):
            raise ValueError("max_entries_per_session must be positive or UNDECIDED")
        if self.deduplication_key_rule is not UNDECIDED:
            _require_non_empty(self.deduplication_key_rule, "deduplication_key_rule")

    @property
    def policy_digest(self) -> str:
        return _digest(self)

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


@dataclass(frozen=True)
class RankedCandidate:
    rank: int
    candidate_id: str
    sort_key_values: tuple[str, ...]
    status: Literal["SELECTED", "RANKED_NOT_SELECTED", "ELIMINATED"]
    reason: SelectionReason

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        _require_non_empty(self.candidate_id, "ranked candidate_id")
        if not isinstance(self.sort_key_values, tuple) or any(
            not isinstance(item, str) for item in self.sort_key_values
        ):
            raise TypeError("sort_key_values must be a tuple of strings")
        if self.status not in {"SELECTED", "RANKED_NOT_SELECTED", "ELIMINATED"}:
            raise ValueError("invalid ranked candidate status")
        if not isinstance(self.reason, SelectionReason):
            raise TypeError("ranked candidate reason must be SelectionReason")


@dataclass(frozen=True)
class SelectionResult:
    schema_version: Literal["selection-result-v1"]
    policy_id: str
    policy_digest: str
    candidate_set_digest: str
    ranked_candidates: tuple[RankedCandidate, ...]
    selected_candidate_ids: tuple[str, ...]
    selection_reason: SelectionReason
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != "selection-result-v1":
            raise ValueError("unsupported selection result schema")
        _require_non_empty(self.policy_id, "result policy_id")
        _require_sha256(self.policy_digest, "result policy_digest")
        _require_sha256(self.candidate_set_digest, "result candidate_set_digest")
        if not isinstance(self.ranked_candidates, tuple) or any(
            not isinstance(item, RankedCandidate) for item in self.ranked_candidates
        ):
            raise TypeError("ranked_candidates must be a tuple of RankedCandidate")
        if not isinstance(self.selected_candidate_ids, tuple) or len(
            self.selected_candidate_ids
        ) > 1:
            raise ValueError("selected_candidate_ids must be a tuple with at most one item")
        for candidate_id in self.selected_candidate_ids:
            _require_non_empty(candidate_id, "selected candidate_id")
        if not isinstance(self.selection_reason, SelectionReason):
            raise TypeError("selection_reason must be SelectionReason")
        _require_aware(self.evaluated_at, "evaluated_at")

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


@dataclass(frozen=True)
class CandidateSetEvidence:
    schema_version: Literal["candidate-set-evidence-v1"]
    candidate_set_digest: str
    candidates: tuple[SelectionCandidate, ...]
    result: SelectionResult

    def __post_init__(self) -> None:
        if self.schema_version != "candidate-set-evidence-v1":
            raise ValueError("unsupported candidate-set evidence schema")
        _require_sha256(self.candidate_set_digest, "candidate_set_digest")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, SelectionCandidate) for item in self.candidates
        ):
            raise TypeError("candidates must be a tuple of SelectionCandidate")
        expected = candidate_set_digest(self.candidates)
        if self.candidate_set_digest != expected:
            raise ValueError("candidate_set_digest does not match candidates")
        if not isinstance(self.result, SelectionResult):
            raise TypeError("result must be SelectionResult")
        if self.result.candidate_set_digest != expected:
            raise ValueError("result candidate_set_digest does not match candidates")

    @property
    def digest(self) -> str:
        return _digest(self)

    def to_wire(self) -> dict[str, object]:
        return cast(dict[str, object], _to_wire(self))


LEGACY_MOMENTUM_V0 = SelectionPolicy(
    schema_version="selection-policy-v1",
    policy_id="legacy_momentum_score_desc_symbol_asc_v0",
    sort_keys=(SortKey("evidence_score", "DESC"),),
    tie_breakers=(SortKey("symbol", "ASC"),),
    max_entries_per_evaluation=1,
    max_entries_per_session=UNDECIDED,
    deduplication_key_rule=UNDECIDED,
)

LEGACY_ATOMIC_V0 = SelectionPolicy(
    schema_version="selection-policy-v1",
    policy_id="legacy_atomic_symbol_asc_v0",
    sort_keys=(SortKey("symbol", "ASC"),),
    tie_breakers=(),
    max_entries_per_evaluation=1,
    max_entries_per_session=UNDECIDED,
    deduplication_key_rule=UNDECIDED,
)


def candidate_set_digest(candidates: tuple[SelectionCandidate, ...]) -> str:
    if not isinstance(candidates, tuple) or any(
        not isinstance(item, SelectionCandidate) for item in candidates
    ):
        raise TypeError("candidates must be a tuple of SelectionCandidate")
    ordered = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    return _digest(ordered)


def _candidate_value(candidate: SelectionCandidate, key: SortKey) -> int | str | None:
    return cast(int | str | None, getattr(candidate, key.field))


def _compare_candidates(
    left: SelectionCandidate,
    right: SelectionCandidate,
    keys: tuple[SortKey, ...],
) -> int:
    for key in keys:
        left_value = _candidate_value(left, key)
        right_value = _candidate_value(right, key)
        if left_value == right_value:
            continue
        comparison = -1 if cast(Any, left_value) < cast(Any, right_value) else 1
        return comparison if key.direction == "ASC" else -comparison
    return 0


def _sort_values(candidate: SelectionCandidate, keys: tuple[SortKey, ...]) -> tuple[str, ...]:
    return tuple(str(_candidate_value(candidate, key)) for key in keys)


def select(
    policy: SelectionPolicy,
    candidates: tuple[SelectionCandidate, ...],
    evaluated_at: datetime,
) -> SelectionResult:
    if not isinstance(policy, SelectionPolicy):
        raise TypeError("policy must be SelectionPolicy")
    if not isinstance(candidates, tuple) or any(
        not isinstance(item, SelectionCandidate) for item in candidates
    ):
        raise TypeError("candidates must be a tuple of SelectionCandidate")
    _require_aware(evaluated_at, "evaluated_at")
    candidate_ids = tuple(item.candidate_id for item in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise SelectionContractError("duplicate candidate_id")
    set_digest = candidate_set_digest(candidates)
    if not candidates:
        return SelectionResult(
            schema_version="selection-result-v1",
            policy_id=policy.policy_id,
            policy_digest=policy.policy_digest,
            candidate_set_digest=set_digest,
            ranked_candidates=(),
            selected_candidate_ids=(),
            selection_reason=SelectionReason.EMPTY_CANDIDATE_SET,
            evaluated_at=evaluated_at,
        )

    all_keys = (*policy.sort_keys, *policy.tie_breakers)
    eligible: list[SelectionCandidate] = []
    eliminated: list[SelectionCandidate] = []
    for candidate in candidates:
        if any(_candidate_value(candidate, key) is None for key in all_keys):
            eliminated.append(candidate)
        else:
            eligible.append(candidate)
    eligible.sort(key=cmp_to_key(lambda left, right: _compare_candidates(left, right, all_keys)))

    primary_top_tie = (
        len(eligible) > 1
        and _compare_candidates(eligible[0], eligible[1], policy.sort_keys) == 0
    )
    unresolved_top_tie = (
        len(eligible) > 1
        and _compare_candidates(eligible[0], eligible[1], all_keys) == 0
    )
    selected_id: str | None = None if unresolved_top_tie or not eligible else eligible[0].candidate_id
    selection_reason = (
        SelectionReason.TIE_UNRESOLVED_FAIL_CLOSED
        if unresolved_top_tie
        else SelectionReason.TIE_RESOLVED_BY_TIE_BREAKER
        if primary_top_tie
        else SelectionReason.SELECTED_RANK_1
        if eligible
        else SelectionReason.ELIMINATED_MISSING_SORT_FIELD
    )

    ranked: list[RankedCandidate] = []
    prior_primary: tuple[str, ...] | None = None
    current_rank = 0
    for index, candidate in enumerate(eligible, start=1):
        primary_values = _sort_values(candidate, policy.sort_keys)
        if primary_values != prior_primary:
            current_rank = index
            prior_primary = primary_values
        tied_at_top = current_rank == 1 and primary_top_tie
        reason = (
            SelectionReason.TIE_UNRESOLVED_FAIL_CLOSED
            if unresolved_top_tie and current_rank == 1
            else SelectionReason.TIE_RESOLVED_BY_TIE_BREAKER
            if tied_at_top
            else SelectionReason.SELECTED_RANK_1
            if candidate.candidate_id == selected_id
            else SelectionReason.RANKED_NOT_SELECTED
        )
        ranked.append(
            RankedCandidate(
                rank=current_rank,
                candidate_id=candidate.candidate_id,
                sort_key_values=_sort_values(candidate, all_keys),
                status=(
                    "SELECTED"
                    if candidate.candidate_id == selected_id
                    else "RANKED_NOT_SELECTED"
                ),
                reason=reason,
            )
        )
    for index, candidate in enumerate(eliminated, start=len(eligible) + 1):
        ranked.append(
            RankedCandidate(
                rank=index,
                candidate_id=candidate.candidate_id,
                sort_key_values=tuple(
                    "" if _candidate_value(candidate, key) is None else str(
                        _candidate_value(candidate, key)
                    )
                    for key in all_keys
                ),
                status="ELIMINATED",
                reason=SelectionReason.ELIMINATED_MISSING_SORT_FIELD,
            )
        )
    return SelectionResult(
        schema_version="selection-result-v1",
        policy_id=policy.policy_id,
        policy_digest=policy.policy_digest,
        candidate_set_digest=set_digest,
        ranked_candidates=tuple(ranked),
        selected_candidate_ids=(() if selected_id is None else (selected_id,)),
        selection_reason=selection_reason,
        evaluated_at=evaluated_at,
    )
