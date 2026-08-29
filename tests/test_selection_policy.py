from __future__ import annotations

from datetime import datetime

import pytest

from signals.selection import (
    UNDECIDED,
    LEGACY_ATOMIC_V0,
    LEGACY_MOMENTUM_V0,
    CandidateSetEvidence,
    SelectionCandidate,
    SelectionContractError,
    SelectionPolicy,
    SelectionReason,
    SortKey,
    candidate_set_digest,
    select,
)


NOW = datetime.fromisoformat("2026-08-29T09:15:00+08:00")


def candidate(
    symbol: str,
    *,
    score: int | None,
    source_path: str = "LEGACY_MOMENTUM",
) -> SelectionCandidate:
    return SelectionCandidate(
        candidate_id=symbol,
        symbol=symbol,
        source_path=source_path,  # type: ignore[arg-type]
        evidence_score=score,
        evidence_signature="breakout+volume",
        signal_digest="a" * 64,
        current_stage="ACCELERATING",
        episode_status="ACTIVE",
    )


def test_legacy_policy_identities_preserve_per_evaluation_cap_and_undecided_session():
    assert LEGACY_MOMENTUM_V0.policy_id == "legacy_momentum_score_desc_symbol_asc_v0"
    assert LEGACY_MOMENTUM_V0.sort_keys == (SortKey("evidence_score", "DESC"),)
    assert LEGACY_MOMENTUM_V0.tie_breakers == (SortKey("symbol", "ASC"),)
    assert LEGACY_ATOMIC_V0.policy_id == "legacy_atomic_symbol_asc_v0"
    assert LEGACY_ATOMIC_V0.sort_keys == (SortKey("symbol", "ASC"),)
    assert LEGACY_ATOMIC_V0.tie_breakers == ()
    for policy in (LEGACY_MOMENTUM_V0, LEGACY_ATOMIC_V0):
        assert policy.max_entries_per_evaluation == 1
        assert policy.max_entries_per_session is UNDECIDED
        assert policy.deduplication_key_rule is UNDECIDED


def test_momentum_selection_ranks_score_desc_and_resolves_tie_by_symbol():
    result = select(
        LEGACY_MOMENTUM_V0,
        (candidate("2603", score=80), candidate("2330", score=80), candidate("8039", score=70)),
        NOW,
    )

    assert result.selected_candidate_ids == ("2330",)
    assert result.selection_reason is SelectionReason.TIE_RESOLVED_BY_TIE_BREAKER
    assert [item.candidate_id for item in result.ranked_candidates] == [
        "2330",
        "2603",
        "8039",
    ]
    assert [item.rank for item in result.ranked_candidates] == [1, 1, 3]
    assert result.ranked_candidates[0].status == "SELECTED"
    assert result.ranked_candidates[1].reason is (
        SelectionReason.TIE_RESOLVED_BY_TIE_BREAKER
    )


def test_atomic_selection_is_symbol_ascending_and_still_selects_only_one():
    result = select(
        LEGACY_ATOMIC_V0,
        (
            candidate("8039", score=None, source_path="ATOMIC_STRATEGY_SET"),
            candidate("2330", score=None, source_path="ATOMIC_STRATEGY_SET"),
        ),
        NOW,
    )

    assert result.selected_candidate_ids == ("2330",)
    assert result.selection_reason is SelectionReason.SELECTED_RANK_1
    assert [item.candidate_id for item in result.ranked_candidates] == ["2330", "8039"]


def test_candidate_set_digest_is_input_order_independent_but_record_keeps_input_order():
    first = candidate("2330", score=90)
    second = candidate("8039", score=80)
    forward = (first, second)
    reverse = (second, first)
    result = select(LEGACY_MOMENTUM_V0, forward, NOW)

    assert candidate_set_digest(forward) == candidate_set_digest(reverse)
    evidence = CandidateSetEvidence(
        schema_version="candidate-set-evidence-v1",
        candidate_set_digest=result.candidate_set_digest,
        candidates=reverse,
        result=result,
    )
    assert evidence.candidates == reverse
    assert evidence.to_wire()["candidates"][0]["candidate_id"] == "8039"  # type: ignore[index]
    assert len(evidence.digest) == 64


def test_empty_duplicate_and_missing_sort_fields_fail_closed_as_declared():
    empty = select(LEGACY_MOMENTUM_V0, (), NOW)
    assert empty.selected_candidate_ids == ()
    assert empty.ranked_candidates == ()
    assert empty.selection_reason is SelectionReason.EMPTY_CANDIDATE_SET
    assert empty.candidate_set_digest == candidate_set_digest(())

    duplicate = candidate("2330", score=90)
    with pytest.raises(SelectionContractError, match="duplicate candidate_id"):
        select(LEGACY_MOMENTUM_V0, (duplicate, duplicate), NOW)

    missing = select(
        LEGACY_MOMENTUM_V0,
        (candidate("2330", score=None), candidate("8039", score=80)),
        NOW,
    )
    assert missing.selected_candidate_ids == ("8039",)
    assert missing.ranked_candidates[-1].candidate_id == "2330"
    assert missing.ranked_candidates[-1].status == "ELIMINATED"
    assert missing.ranked_candidates[-1].reason is (
        SelectionReason.ELIMINATED_MISSING_SORT_FIELD
    )


def test_tie_remaining_after_all_tie_breakers_selects_nothing():
    unresolved_policy = SelectionPolicy(
        schema_version="selection-policy-v1",
        policy_id="unresolved-fixture",
        sort_keys=(SortKey("evidence_score", "DESC"),),
        tie_breakers=(),
        max_entries_per_evaluation=1,
        max_entries_per_session=UNDECIDED,
        deduplication_key_rule=UNDECIDED,
    )
    result = select(
        unresolved_policy,
        (candidate("2330", score=80), candidate("8039", score=80)),
        NOW,
    )

    assert result.selected_candidate_ids == ()
    assert result.selection_reason is SelectionReason.TIE_UNRESOLVED_FAIL_CLOSED
    assert {item.reason for item in result.ranked_candidates} == {
        SelectionReason.TIE_UNRESOLVED_FAIL_CLOSED
    }


def test_candidate_normalization_passthrough_status_and_policy_validation():
    normalized = candidate("aapl", score=1)
    assert normalized.symbol == "AAPL"
    assert normalized.candidate_id == "AAPL"
    assert normalized.episode_status == "ACTIVE"

    with pytest.raises(ValueError, match="must equal"):
        SelectionCandidate(
            candidate_id="2330",
            symbol="8039",
            source_path="LEGACY_MOMENTUM",
            evidence_score=1,
            evidence_signature=None,
            signal_digest=None,
            current_stage=None,
            episode_status="FUTURE_TERMINAL_VALUE",
        )
    with pytest.raises(ValueError, match="fixes max_entries"):
        SelectionPolicy(
            schema_version="selection-policy-v1",
            policy_id="bad-cap",
            sort_keys=(SortKey("symbol", "ASC"),),
            tie_breakers=(),
            max_entries_per_evaluation=2,
            max_entries_per_session=UNDECIDED,
            deduplication_key_rule=UNDECIDED,
        )
