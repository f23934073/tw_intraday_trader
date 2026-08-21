"""Typed, deterministic evidence snapshots for an existing BuyScore result.

This adapter records a score breakdown.  It does not decide whether a score is
good enough, select matched rules, or create an entry decision.
"""

from __future__ import annotations

import hashlib
import json

from scoring.models import BuyScoreResult
from trading.trade_management import (
    EntryEvidence,
    EntryEvidenceStatus,
    EvidenceValue,
    EvidenceValueKind,
    TradeTimestamp,
)


BUY_SCORE_ENTRY_EVIDENCE_VERSION = "buy-score-entry-evidence-v1"


class BuyScoreEntryEvidenceAdapter:
    """Freeze caller-classified BuyScore details as typed entry evidence."""

    __slots__ = ()

    def capture(
        self,
        result: BuyScoreResult,
        *,
        source_component: str,
        strategy_version: str,
        status: EntryEvidenceStatus,
        market_event_id: str,
        observed_at: TradeTimestamp,
    ) -> EntryEvidence:
        for value, field_name in (
            (source_component, "source_component"),
            (strategy_version, "strategy_version"),
            (market_event_id, "market_event_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if result.symbol != result.symbol.strip().upper() or not result.symbol:
            raise ValueError("BuyScore symbol must be normalized")
        if result.total_score < 0:
            raise ValueError("BuyScore total_score must not be negative")
        details = tuple(sorted(result.details, key=lambda item: item.rule))
        rules = tuple(item.rule for item in details)
        if not rules:
            raise ValueError("BuyScore details must not be empty")
        if any(not rule.strip() for rule in rules):
            raise ValueError("BuyScore rule must not be empty")
        if len(rules) != len(set(rules)):
            raise ValueError("BuyScore rules must be unique")
        if any(item.score < 0 or item.max_score < 0 for item in details):
            raise ValueError("BuyScore detail values must not be negative")
        if any(item.score > item.max_score for item in details):
            raise ValueError("BuyScore rule score cannot exceed max_score")

        observed = [
            EvidenceValue(
                name="total_score",
                kind=EvidenceValueKind.INTEGER,
                value=str(result.total_score),
            )
        ]
        thresholds: list[EvidenceValue] = []
        wire_details: list[dict[str, object]] = []
        for index, detail in enumerate(details):
            prefix = f"rule_{index:03d}"
            observed.extend(
                (
                    EvidenceValue(
                        name=f"{prefix}_name",
                        kind=EvidenceValueKind.TEXT,
                        value=detail.rule,
                    ),
                    EvidenceValue(
                        name=f"{prefix}_score",
                        kind=EvidenceValueKind.INTEGER,
                        value=str(detail.score),
                    ),
                )
            )
            thresholds.append(
                EvidenceValue(
                    name=f"{prefix}_max_score",
                    kind=EvidenceValueKind.INTEGER,
                    value=str(detail.max_score),
                )
            )
            wire_details.append(
                {
                    "rule": detail.rule,
                    "score": detail.score,
                    "max_score": detail.max_score,
                }
            )

        digest = hashlib.sha256(
            json.dumps(
                {
                    "version": BUY_SCORE_ENTRY_EVIDENCE_VERSION,
                    "symbol": result.symbol,
                    "source_component": source_component,
                    "strategy_version": strategy_version,
                    "status": status.value,
                    "market_event_id": market_event_id,
                    "observed_at": {
                        "role": observed_at.role.value,
                        "value": observed_at.isoformat,
                        "source": observed_at.source.value,
                        "source_identity": observed_at.source_identity,
                        "precision": observed_at.precision.value,
                    },
                    "total_score": result.total_score,
                    "details": wire_details,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return EntryEvidence(
            evidence_id=f"buy_score_evidence_v1_{digest}",
            kind="BUY_SCORE_BREAKDOWN",
            source_component=source_component,
            source_version=strategy_version,
            status=status,
            observed=tuple(observed),
            threshold=tuple(thresholds),
            market_event_id=market_event_id,
            observed_at=observed_at,
        )
