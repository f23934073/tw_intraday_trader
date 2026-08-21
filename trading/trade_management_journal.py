"""Journal persistence and replay reconstruction for Trade Management v1.

This module records already-created domain facts.  It does not evaluate a
thesis, decide an exit, call RiskGate, or submit an order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading.journal import (
    JournalAppendResult,
    JournalRecord,
    JournalRepository,
    ProjectionCheckpoint,
)
from trading.trade_management import (
    TRADE_MANAGEMENT_SCHEMA_VERSION,
    TRADE_MANAGEMENT_SERIALIZER_VERSION,
    ExitRecommendation,
    ExitRecommendationStatus,
    TradeOutcome,
    TradeThesis,
    TradeThesisDraft,
)
from trading.trade_management_serialization import (
    TradeManagementDeserializationError,
    deserialize_exit_recommendation,
    deserialize_trade_outcome,
    deserialize_trade_thesis,
    deserialize_trade_thesis_draft,
    serialize_exit_recommendation,
    serialize_trade_outcome,
    serialize_trade_thesis,
    serialize_trade_thesis_draft,
)


TRADE_MANAGEMENT_PROJECTION_NAME = "trade_management.v1"


class TradeManagementJournalKind(StrEnum):
    THESIS_DRAFTED = "trade_thesis_draft.v1"
    THESIS_ACTIVATED = "trade_thesis_activated.v1"
    EXIT_RECOMMENDATION_CREATED = "exit_recommendation_created.v1"
    EXIT_RECOMMENDATION_UPDATED = "exit_recommendation_updated.v1"
    EXIT_RECOMMENDATION_RESOLVED = "exit_recommendation_resolved.v1"
    TRADE_CLOSED = "trade_closed.v1"


class TradeManagementJournalError(ValueError):
    """A Trade Management record or replay stream violates the v1 contract."""


TradeManagementContract = (
    TradeThesisDraft | TradeThesis | ExitRecommendation | TradeOutcome
)


@dataclass(frozen=True)
class TradeManagementJournalEvent:
    kind: TradeManagementJournalKind
    session_id: str
    contract: TradeManagementContract


def _contract_digest(contract_json: str) -> str:
    return hashlib.sha256(contract_json.encode("utf-8")).hexdigest()


def _record_id(
    session_id: str,
    kind: TradeManagementJournalKind,
    event_identity: str,
) -> str:
    identity = "\x1f".join(
        (
            "trade-management-journal-id-v1",
            session_id,
            kind.value,
            event_identity,
        )
    )
    return f"trade_management_event_v1_{hashlib.sha256(identity.encode()).hexdigest()}"


def _journal_record(
    *,
    session_id: str,
    kind: TradeManagementJournalKind,
    event_identity: str,
    occurred_at: datetime,
    contract_json: str,
) -> JournalRecord:
    record_id = _record_id(session_id, kind, event_identity)
    return JournalRecord(
        record_id=record_id,
        session_id=session_id,
        kind=kind.value,
        occurred_at=occurred_at,
        payload={
            "contract_digest": _contract_digest(contract_json),
            "contract_json": contract_json,
            "serializer_version": TRADE_MANAGEMENT_SERIALIZER_VERSION,
        },
        idempotency_scope=f"{session_id}:trade_management:{kind.value}",
        idempotency_key=record_id,
    )


def journal_record_for_trade_thesis_draft(
    draft: TradeThesisDraft,
) -> JournalRecord:
    return _journal_record(
        session_id=draft.session_id,
        kind=TradeManagementJournalKind.THESIS_DRAFTED,
        event_identity=draft.thesis_id,
        occurred_at=draft.created_at.value,
        contract_json=serialize_trade_thesis_draft(draft),
    )


def journal_record_for_trade_thesis(thesis: TradeThesis) -> JournalRecord:
    return _journal_record(
        session_id=thesis.draft.session_id,
        kind=TradeManagementJournalKind.THESIS_ACTIVATED,
        event_identity=f"{thesis.thesis_id}:{thesis.opening_fill_id}",
        occurred_at=thesis.filled_at.value,
        contract_json=serialize_trade_thesis(thesis),
    )


def journal_record_for_exit_recommendation_created(
    recommendation: ExitRecommendation,
) -> JournalRecord:
    if recommendation.status is not ExitRecommendationStatus.ACTIVE:
        raise ValueError("created recommendation must be ACTIVE")
    if (
        recommendation.latest_decision_id
        != recommendation.first_trigger_decision_id
        or recommendation.latest_evidence_event_id
        != recommendation.first_trigger_event_id
        or recommendation.updated_at != recommendation.created_at
    ):
        raise ValueError("created recommendation must contain first-trigger state")
    return _journal_record(
        session_id=recommendation.session_id,
        kind=TradeManagementJournalKind.EXIT_RECOMMENDATION_CREATED,
        event_identity=recommendation.recommendation_id,
        occurred_at=recommendation.created_at.value,
        contract_json=serialize_exit_recommendation(recommendation),
    )


def journal_record_for_exit_recommendation_updated(
    recommendation: ExitRecommendation,
) -> JournalRecord:
    if recommendation.status is not ExitRecommendationStatus.ACTIVE:
        raise ValueError("updated recommendation must remain ACTIVE")
    return _journal_record(
        session_id=recommendation.session_id,
        kind=TradeManagementJournalKind.EXIT_RECOMMENDATION_UPDATED,
        event_identity=(
            f"{recommendation.recommendation_id}:"
            f"{recommendation.latest_decision_id}"
        ),
        occurred_at=recommendation.updated_at.value,
        contract_json=serialize_exit_recommendation(recommendation),
    )


def journal_record_for_exit_recommendation_resolved(
    recommendation: ExitRecommendation,
) -> JournalRecord:
    if recommendation.status is not ExitRecommendationStatus.RESOLVED_ON_CLOSE:
        raise ValueError("resolved recommendation must be RESOLVED_ON_CLOSE")
    if recommendation.resolved_at is None or recommendation.closing_fill_id is None:
        raise ValueError("resolved recommendation requires close metadata")
    return _journal_record(
        session_id=recommendation.session_id,
        kind=TradeManagementJournalKind.EXIT_RECOMMENDATION_RESOLVED,
        event_identity=(
            f"{recommendation.recommendation_id}:"
            f"{recommendation.closing_fill_id}"
        ),
        occurred_at=recommendation.resolved_at.value,
        contract_json=serialize_exit_recommendation(recommendation),
    )


def journal_record_for_trade_outcome(
    outcome: TradeOutcome,
    *,
    session_id: str,
) -> JournalRecord:
    return _journal_record(
        session_id=session_id,
        kind=TradeManagementJournalKind.TRADE_CLOSED,
        event_identity=outcome.trade_id,
        occurred_at=outcome.closed_at.value,
        contract_json=serialize_trade_outcome(outcome),
    )


_PAYLOAD_FIELDS = frozenset(
    {"contract_digest", "contract_json", "serializer_version"}
)


def _record_contract_json(record: JournalRecord) -> str:
    if frozenset(record.payload) != _PAYLOAD_FIELDS:
        raise TradeManagementJournalError(
            f"invalid Trade Management Journal payload fields for {record.record_id}"
        )
    serializer_version = record.payload["serializer_version"]
    if serializer_version != TRADE_MANAGEMENT_SERIALIZER_VERSION:
        raise TradeManagementJournalError(
            f"unsupported Trade Management serializer for {record.record_id}"
        )
    contract_json = record.payload["contract_json"]
    contract_digest = record.payload["contract_digest"]
    if not isinstance(contract_json, str) or not isinstance(contract_digest, str):
        raise TradeManagementJournalError(
            f"invalid Trade Management Journal payload types for {record.record_id}"
        )
    if _contract_digest(contract_json) != contract_digest:
        raise TradeManagementJournalError(
            f"Trade Management contract digest mismatch for {record.record_id}"
        )
    return contract_json


def _expected_record(
    kind: TradeManagementJournalKind,
    contract: TradeManagementContract,
    *,
    session_id: str,
) -> JournalRecord:
    if kind is TradeManagementJournalKind.THESIS_DRAFTED:
        if not isinstance(contract, TradeThesisDraft):
            raise TradeManagementJournalError("draft record has wrong contract type")
        return journal_record_for_trade_thesis_draft(contract)
    if kind is TradeManagementJournalKind.THESIS_ACTIVATED:
        if not isinstance(contract, TradeThesis):
            raise TradeManagementJournalError("activation record has wrong contract type")
        return journal_record_for_trade_thesis(contract)
    if kind is TradeManagementJournalKind.EXIT_RECOMMENDATION_CREATED:
        if not isinstance(contract, ExitRecommendation):
            raise TradeManagementJournalError(
                "recommendation-created record has wrong contract type"
            )
        return journal_record_for_exit_recommendation_created(contract)
    if kind is TradeManagementJournalKind.EXIT_RECOMMENDATION_UPDATED:
        if not isinstance(contract, ExitRecommendation):
            raise TradeManagementJournalError(
                "recommendation-updated record has wrong contract type"
            )
        return journal_record_for_exit_recommendation_updated(contract)
    if kind is TradeManagementJournalKind.EXIT_RECOMMENDATION_RESOLVED:
        if not isinstance(contract, ExitRecommendation):
            raise TradeManagementJournalError(
                "recommendation-resolved record has wrong contract type"
            )
        return journal_record_for_exit_recommendation_resolved(contract)
    if not isinstance(contract, TradeOutcome):
        raise TradeManagementJournalError("trade-closed record has wrong contract type")
    return journal_record_for_trade_outcome(contract, session_id=session_id)


def read_trade_management_record(
    record: JournalRecord,
) -> TradeManagementJournalEvent | None:
    """Decode one supported v1 record; return ``None`` for unrelated kinds."""

    try:
        kind = TradeManagementJournalKind(record.kind)
    except ValueError:
        if record.kind.startswith(
            ("trade_thesis_", "exit_recommendation_", "trade_closed.")
        ):
            raise TradeManagementJournalError(
                f"unsupported Trade Management Journal kind: {record.kind}"
            )
        return None

    contract_json = _record_contract_json(record)
    try:
        if kind is TradeManagementJournalKind.THESIS_DRAFTED:
            contract: TradeManagementContract = deserialize_trade_thesis_draft(
                contract_json
            )
        elif kind is TradeManagementJournalKind.THESIS_ACTIVATED:
            contract = deserialize_trade_thesis(contract_json)
        elif kind is TradeManagementJournalKind.TRADE_CLOSED:
            contract = deserialize_trade_outcome(contract_json)
        else:
            contract = deserialize_exit_recommendation(contract_json)
    except TradeManagementDeserializationError as error:
        raise TradeManagementJournalError(
            f"cannot decode Trade Management record {record.record_id}"
        ) from error

    try:
        expected = _expected_record(kind, contract, session_id=record.session_id)
    except (TypeError, ValueError) as error:
        raise TradeManagementJournalError(
            f"invalid Trade Management event semantics for {record.record_id}"
        ) from error
    if record.fingerprint != expected.fingerprint:
        raise TradeManagementJournalError(
            f"non-canonical Trade Management record {record.record_id}"
        )
    return TradeManagementJournalEvent(
        kind=kind,
        session_id=record.session_id,
        contract=contract,
    )


class TradeManagementProjection:
    """Pure append-order reconstruction of already-recorded domain facts."""

    def __init__(self) -> None:
        self._drafts: dict[str, TradeThesisDraft] = {}
        self._theses_by_trade: dict[str, TradeThesis] = {}
        self._trade_id_by_thesis: dict[str, str] = {}
        self._recommendations: dict[str, ExitRecommendation] = {}
        self._recommendation_id_by_trade: dict[str, str] = {}
        self._outcomes: dict[str, TradeOutcome] = {}
        self._session_id: str | None = None
        self._last_sequence = 0

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    def draft(self, thesis_id: str) -> TradeThesisDraft | None:
        return self._drafts.get(thesis_id)

    def thesis_for_trade(self, trade_id: str) -> TradeThesis | None:
        return self._theses_by_trade.get(trade_id)

    def recommendation_for_trade(
        self,
        trade_id: str,
    ) -> ExitRecommendation | None:
        recommendation_id = self._recommendation_id_by_trade.get(trade_id)
        if recommendation_id is None:
            return None
        return self._recommendations[recommendation_id]

    def outcome(self, trade_id: str) -> TradeOutcome | None:
        return self._outcomes.get(trade_id)

    def apply(self, result: JournalAppendResult) -> None:
        if result.sequence <= self._last_sequence:
            raise TradeManagementJournalError(
                "Journal sequence must be strictly increasing"
            )
        event = read_trade_management_record(result.record)
        if event is not None:
            self._apply_event(event)
        self._last_sequence = result.sequence

    def _apply_event(self, event: TradeManagementJournalEvent) -> None:
        if self._session_id is None:
            self._session_id = event.session_id
        elif event.session_id != self._session_id:
            raise TradeManagementJournalError(
                "projection cannot mix Journal sessions"
            )
        contract = event.contract
        if event.kind is TradeManagementJournalKind.THESIS_DRAFTED:
            assert isinstance(contract, TradeThesisDraft)
            if contract.thesis_id in self._drafts:
                raise TradeManagementJournalError("thesis draft was journaled twice")
            self._drafts[contract.thesis_id] = contract
            return

        if event.kind is TradeManagementJournalKind.THESIS_ACTIVATED:
            assert isinstance(contract, TradeThesis)
            draft = self._drafts.get(contract.thesis_id)
            if draft is None:
                raise TradeManagementJournalError(
                    "thesis activation requires a journaled draft"
                )
            if draft != contract.draft:
                raise TradeManagementJournalError(
                    "activated thesis does not match its journaled draft"
                )
            if (
                contract.trade_id in self._theses_by_trade
                or contract.thesis_id in self._trade_id_by_thesis
            ):
                raise TradeManagementJournalError("thesis was activated twice")
            self._theses_by_trade[contract.trade_id] = contract
            self._trade_id_by_thesis[contract.thesis_id] = contract.trade_id
            return

        if event.kind is TradeManagementJournalKind.TRADE_CLOSED:
            assert isinstance(contract, TradeOutcome)
            self._apply_outcome(contract)
            return

        assert isinstance(contract, ExitRecommendation)
        if event.kind is TradeManagementJournalKind.EXIT_RECOMMENDATION_CREATED:
            self._apply_recommendation_created(contract)
        elif event.kind is TradeManagementJournalKind.EXIT_RECOMMENDATION_UPDATED:
            self._apply_recommendation_updated(contract)
        else:
            self._apply_recommendation_resolved(contract)

    def _require_recommendation_trade(
        self,
        recommendation: ExitRecommendation,
    ) -> TradeThesis:
        thesis = self._theses_by_trade.get(recommendation.trade_id)
        if thesis is None or thesis.thesis_id != recommendation.thesis_id:
            raise TradeManagementJournalError(
                "exit recommendation requires its activated trade and thesis"
            )
        if thesis.draft.session_id != recommendation.session_id:
            raise TradeManagementJournalError(
                "exit recommendation session does not match activated trade"
            )
        if recommendation.trade_id in self._outcomes:
            raise TradeManagementJournalError(
                "exit recommendation cannot change after trade close"
            )
        return thesis

    def _apply_recommendation_created(
        self,
        recommendation: ExitRecommendation,
    ) -> None:
        self._require_recommendation_trade(recommendation)
        if (
            recommendation.recommendation_id in self._recommendations
            or recommendation.trade_id in self._recommendation_id_by_trade
        ):
            raise TradeManagementJournalError(
                "trade already has an exit recommendation"
            )
        self._recommendations[recommendation.recommendation_id] = recommendation
        self._recommendation_id_by_trade[
            recommendation.trade_id
        ] = recommendation.recommendation_id

    @staticmethod
    def _require_same_recommendation_identity(
        previous: ExitRecommendation,
        current: ExitRecommendation,
    ) -> None:
        immutable_previous = (
            previous.recommendation_id,
            previous.session_id,
            previous.trade_id,
            previous.thesis_id,
            previous.exit_policy_version,
            previous.first_trigger_decision_id,
            previous.first_trigger_event_id,
            previous.created_at,
        )
        immutable_current = (
            current.recommendation_id,
            current.session_id,
            current.trade_id,
            current.thesis_id,
            current.exit_policy_version,
            current.first_trigger_decision_id,
            current.first_trigger_event_id,
            current.created_at,
        )
        if immutable_previous != immutable_current:
            raise TradeManagementJournalError(
                "exit recommendation immutable identity changed"
            )

    def _previous_recommendation(
        self,
        recommendation: ExitRecommendation,
    ) -> ExitRecommendation:
        self._require_recommendation_trade(recommendation)
        previous = self._recommendations.get(recommendation.recommendation_id)
        if previous is None:
            raise TradeManagementJournalError(
                "exit recommendation update requires a created recommendation"
            )
        self._require_same_recommendation_identity(previous, recommendation)
        if previous.status is not ExitRecommendationStatus.ACTIVE:
            raise TradeManagementJournalError(
                "resolved exit recommendation cannot change"
            )
        if recommendation.updated_at.value < previous.updated_at.value:
            raise TradeManagementJournalError(
                "exit recommendation updated_at moved backward"
            )
        if not set(previous.triggered_reasons).issubset(
            recommendation.triggered_reasons
        ):
            raise TradeManagementJournalError(
                "exit recommendation cannot remove triggered reasons"
            )
        return previous

    def _apply_recommendation_updated(
        self,
        recommendation: ExitRecommendation,
    ) -> None:
        previous = self._previous_recommendation(recommendation)
        if recommendation.status is not ExitRecommendationStatus.ACTIVE:
            raise TradeManagementJournalError(
                "recommendation update must remain ACTIVE"
            )
        if recommendation == previous:
            raise TradeManagementJournalError(
                "recommendation update must change its snapshot"
            )
        self._recommendations[recommendation.recommendation_id] = recommendation

    def _apply_recommendation_resolved(
        self,
        recommendation: ExitRecommendation,
    ) -> None:
        self._previous_recommendation(recommendation)
        if recommendation.status is not ExitRecommendationStatus.RESOLVED_ON_CLOSE:
            raise TradeManagementJournalError(
                "recommendation resolution must be RESOLVED_ON_CLOSE"
            )
        self._recommendations[recommendation.recommendation_id] = recommendation

    def _apply_outcome(self, outcome: TradeOutcome) -> None:
        thesis = self._theses_by_trade.get(outcome.trade_id)
        if thesis is None:
            raise TradeManagementJournalError(
                "trade close requires an activated thesis"
            )
        if outcome.trade_id in self._outcomes:
            raise TradeManagementJournalError("trade outcome was journaled twice")
        if outcome.closed_at.value < thesis.filled_at.value:
            raise TradeManagementJournalError("trade cannot close before opening fill")
        recommendation_id = self._recommendation_id_by_trade.get(outcome.trade_id)
        if recommendation_id is not None:
            recommendation = self._recommendations[recommendation_id]
            if recommendation.status is not ExitRecommendationStatus.RESOLVED_ON_CLOSE:
                raise TradeManagementJournalError(
                    "trade close requires recommendation resolution first"
                )
            if (
                recommendation.closing_fill_id != outcome.exit_legs[-1].fill_id
                or recommendation.resolved_at != outcome.closed_at
            ):
                raise TradeManagementJournalError(
                    "recommendation resolution does not match final exit fill"
                )
        for leg in outcome.exit_legs:
            if leg.exit_recommendation_id is None:
                continue
            recommendation = self._recommendations.get(leg.exit_recommendation_id)
            if recommendation is None or recommendation.trade_id != outcome.trade_id:
                raise TradeManagementJournalError(
                    "exit leg references an unknown recommendation"
                )
            if recommendation.status is not ExitRecommendationStatus.RESOLVED_ON_CLOSE:
                raise TradeManagementJournalError(
                    "trade close requires recommendation resolution first"
                )
        self._outcomes[outcome.trade_id] = outcome

    @property
    def digest(self) -> str:
        payload = {
            "projection_name": TRADE_MANAGEMENT_PROJECTION_NAME,
            "schema_version": TRADE_MANAGEMENT_SCHEMA_VERSION,
            "session_id": self._session_id,
            "last_sequence": self._last_sequence,
            "drafts": [
                json.loads(serialize_trade_thesis_draft(item))
                for item in sorted(
                    self._drafts.values(),
                    key=lambda value: value.thesis_id,
                )
            ],
            "theses": [
                json.loads(serialize_trade_thesis(item))
                for item in sorted(
                    self._theses_by_trade.values(),
                    key=lambda value: value.trade_id,
                )
            ],
            "recommendations": [
                json.loads(serialize_exit_recommendation(item))
                for item in sorted(
                    self._recommendations.values(),
                    key=lambda value: value.recommendation_id,
                )
            ],
            "outcomes": [
                json.loads(serialize_trade_outcome(item))
                for item in sorted(
                    self._outcomes.values(),
                    key=lambda value: value.trade_id,
                )
            ],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def rebuild_trade_management_projection(
    journal: JournalRepository,
    *,
    session_id: str,
    require_checkpoint: bool = True,
) -> TradeManagementProjection:
    checkpoint = journal.latest_checkpoint(
        session_id,
        TRADE_MANAGEMENT_PROJECTION_NAME,
    )
    if require_checkpoint and checkpoint is None:
        raise TradeManagementJournalError(
            "Trade Management recovery requires a checkpoint"
        )

    projection = TradeManagementProjection()
    checkpoint_digest = (
        projection.digest
        if checkpoint is not None and checkpoint.journal_sequence == 0
        else None
    )
    for result in journal.records(session_id):
        projection.apply(result)
        if checkpoint is not None and result.sequence == checkpoint.journal_sequence:
            checkpoint_digest = projection.digest

    if checkpoint is not None:
        if checkpoint_digest is None:
            raise TradeManagementJournalError(
                "Trade Management checkpoint sequence is absent from Journal"
            )
        if checkpoint_digest != checkpoint.digest:
            raise TradeManagementJournalError(
                "Trade Management checkpoint digest mismatch"
            )
    return projection


def write_trade_management_checkpoint(
    journal: JournalRepository,
    *,
    session_id: str,
) -> TradeManagementProjection:
    projection = rebuild_trade_management_projection(
        journal,
        session_id=session_id,
        require_checkpoint=False,
    )
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=session_id,
            projection_name=TRADE_MANAGEMENT_PROJECTION_NAME,
            journal_sequence=projection.last_sequence,
            digest=projection.digest,
        )
    )
    return projection
