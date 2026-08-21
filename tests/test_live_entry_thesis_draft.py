from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.test_trade_management_replay import THESIS
from trading.live_entry_thesis_draft import (
    LIVE_ENTRY_DECISION_BUILDER_VERSION,
    LIVE_THESIS_DRAFT_BUILDER_VERSION,
    LiveEntryDecisionBuilder,
    LiveThesisDraftPolicy,
    LiveTradeThesisDraftBuilder,
)
from trading.trade_management import EntryEvidence, TradeSide, build_thesis_id
from trading.trade_management_serialization import (
    TradeManagementDeserializationError,
    deserialize_live_entry_decision,
    serialize_live_entry_decision,
    serialize_trade_thesis_draft,
)


MARKET_CONTEXT_DIGEST = hashlib.sha256(b"live-market-context-2330").hexdigest()


def policy(**changes) -> LiveThesisDraftPolicy:
    draft = THESIS.draft
    values = {
        "policy_id": draft.expected_behavior.policy_id,
        "strategy_id": draft.strategy_id,
        "strategy_version": draft.strategy_version,
        "thesis_type": draft.thesis_type,
        "thesis_version": draft.thesis_version,
        "side": draft.side,
        "expected_behavior": draft.expected_behavior,
        "invalid_conditions": draft.invalid_conditions,
    }
    values.update(changes)
    return LiveThesisDraftPolicy(**values)


def entry_evidence() -> tuple[EntryEvidence, ...]:
    first = THESIS.draft.entry_evidence[0]
    second = replace(
        first,
        evidence_id="evidence-live-score-002",
        kind="BUY_SCORE_THRESHOLD",
    )
    return (second, first)


def decision():
    draft = THESIS.draft
    return LiveEntryDecisionBuilder().build(
        session_id=draft.session_id,
        symbol=draft.symbol,
        side=TradeSide.LONG,
        strategy_id=draft.strategy_id,
        strategy_version=draft.strategy_version,
        signal_at=draft.signal_at,
        decided_at=draft.created_at,
        score=Decimal("85"),
        matched_rules=("RVOL_HIGH", "BREAKOUT", "ABOVE_VWAP"),
        market_context_digest=MARKET_CONTEXT_DIGEST,
        entry_evidence=entry_evidence(),
    )


def test_entry_decision_builder_is_deterministic_content_bound_and_immutable() -> None:
    first = decision()
    second = decision()

    assert first == second
    assert first.decision_id == second.decision_id
    assert first.input_digest == second.input_digest
    assert first.matched_rules == ("ABOVE_VWAP", "BREAKOUT", "RVOL_HIGH")
    assert tuple(item.evidence_id for item in first.entry_evidence) == tuple(
        sorted(item.evidence_id for item in entry_evidence())
    )
    assert first.score == Decimal("85")
    assert first.market_context_digest == MARKET_CONTEXT_DIGEST
    with pytest.raises(FrozenInstanceError):
        first.score = Decimal("90")  # type: ignore[misc]
    with pytest.raises(ValueError, match="deterministic content"):
        replace(first, score=Decimal("86"))


def test_entry_decision_canonical_round_trip_and_digest_are_stable() -> None:
    value = decision()
    serialized = serialize_live_entry_decision(value)

    assert deserialize_live_entry_decision(serialized) == value
    assert len({serialize_live_entry_decision(value) for _ in range(10)}) == 1
    assert hashlib.sha256(serialized.encode()).hexdigest() == (
        "0cb58de58c918b94b0d9a224152d98c683b4df237d247cc134b919fabe01290d"
    )


@pytest.mark.parametrize("mutation", ("unknown", "decimal", "duplicate"))
def test_entry_decision_reader_rejects_noncanonical_artifacts(mutation: str) -> None:
    payload = json.loads(serialize_live_entry_decision(decision()))
    if mutation == "unknown":
        payload["payload"]["unexpected"] = True
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif mutation == "decimal":
        payload["payload"]["score"] = "85.0"
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    else:
        serialized = serialize_live_entry_decision(decision()).replace(
            '"score":"85"',
            '"score":"85","score":"85"',
        )

    with pytest.raises(TradeManagementDeserializationError):
        deserialize_live_entry_decision(serialized)


def test_thesis_draft_builder_applies_versioned_policy_without_activation() -> None:
    entry = decision()
    draft_policy = policy()

    first = LiveTradeThesisDraftBuilder().build(entry, draft_policy)
    second = LiveTradeThesisDraftBuilder().build(entry, draft_policy)

    assert first == second
    assert first.decision_id == entry.decision_id
    assert first.thesis_id == build_thesis_id(
        entry.session_id,
        entry.decision_id,
        draft_policy.thesis_type,
        draft_policy.thesis_version,
    )
    assert first.entry_evidence == entry.entry_evidence
    assert first.expected_behavior == draft_policy.expected_behavior
    assert first.invalid_conditions == draft_policy.invalid_conditions
    assert "opening_fill_id" not in json.loads(
        serialize_trade_thesis_draft(first)
    )["payload"]


def test_thesis_draft_builder_rejects_strategy_policy_mismatch() -> None:
    with pytest.raises(ValueError, match="strategy_version"):
        LiveTradeThesisDraftBuilder().build(
            decision(),
            policy(strategy_version="opening-range-entry-v2"),
        )


def test_builder_versions_and_authority_boundary_are_frozen() -> None:
    assert LIVE_ENTRY_DECISION_BUILDER_VERSION == "live-entry-decision-builder-v1"
    assert LIVE_THESIS_DRAFT_BUILDER_VERSION == "live-thesis-draft-builder-v1"
    root = Path(__file__).parents[1]
    source = (root / "trading" / "live_entry_thesis_draft.py").read_text()
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported_names.isdisjoint(
        {
            "Candidate",
            "BuyScoreResult",
            "JournalRepository",
            "PaperFillThesisBuilder",
            "TradeThesis",
            "RiskGate",
            "OrderCommand",
            "SimulationService",
        }
    )
    assert referenced_names.isdisjoint(
        {"Broker", "SELL", "Position", "Shioaji", "ShadowDecisionPipeline"}
    )
