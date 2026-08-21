"""Decision-only live Shadow consumer for Trade Management.

The pipeline accepts canonical events after market-data admission, applies the
same kernel used by Historical Replay, and emits immutable observation records.
It has no Journal, Position, Order, broker, filesystem, or network authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from market_data.events import EventEnvelope, MARKET_EVENT_SCHEMA_VERSION
from market_data.serialization import serialize_event_envelope
from trading.canonical_values import canonical_decimal_string
from trading.risk import RiskPolicy, RiskSnapshot
from trading.trade_management import ReplayRunIdentity, TradeThesis
from trading.trade_management_replay import (
    TradeManagementDecisionConfig,
    TradeManagementDecisionKernel,
    TradeManagementDecisionState,
    TradeManagementReplayInput,
    TradeManagementReplayResult,
    TradeManagementReplayRunner,
    TradeManagementReplayStep,
    build_market_manifest_digest,
)


SHADOW_PIPELINE_VERSION = "trade-management-shadow-v1"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _risk_snapshot_wire(snapshot: RiskSnapshot) -> dict[str, object]:
    return {
        "data_health_state": snapshot.data_health_state,
        "market_open": snapshot.market_open,
        "instrument_tradable": snapshot.instrument_tradable,
        "available_cash": canonical_decimal_string(snapshot.available_cash),
        "current_position_shares": snapshot.current_position_shares,
        "pending_buy_shares": snapshot.pending_buy_shares,
        "pending_sell_shares": snapshot.pending_sell_shares,
        "daily_realized_pnl": canonical_decimal_string(
            snapshot.daily_realized_pnl
        ),
        "same_side_pending_order": snapshot.same_side_pending_order,
        "book_age_seconds": snapshot.book_age_seconds,
    }


@dataclass(frozen=True)
class ShadowDecisionConfig:
    thesis: TradeThesis
    exit_policy_version: str
    risk_policy: RiskPolicy
    volume_baseline_shares: Decimal
    shares_per_lot: int
    remaining_quantity_shares: int
    fill_model_version: str
    code_identity: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.exit_policy_version, "exit_policy_version"),
            (self.fill_model_version, "fill_model_version"),
            (self.code_identity, "code_identity"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        TradeManagementDecisionConfig(
            thesis=self.thesis,
            exit_policy_version=self.exit_policy_version,
            volume_baseline_shares=self.volume_baseline_shares,
            shares_per_lot=self.shares_per_lot,
            remaining_quantity_shares=self.remaining_quantity_shares,
            risk_policy=self.risk_policy,
        )

    @property
    def decision_config(self) -> TradeManagementDecisionConfig:
        return TradeManagementDecisionConfig(
            thesis=self.thesis,
            exit_policy_version=self.exit_policy_version,
            volume_baseline_shares=self.volume_baseline_shares,
            shares_per_lot=self.shares_per_lot,
            remaining_quantity_shares=self.remaining_quantity_shares,
            risk_policy=self.risk_policy,
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "pipeline_version": SHADOW_PIPELINE_VERSION,
                "session_id": self.thesis.draft.session_id,
                "trade_id": self.thesis.trade_id,
                "thesis_id": self.thesis.thesis_id,
                "strategy_id": self.thesis.draft.strategy_id,
                "strategy_version": self.thesis.draft.strategy_version,
                "thesis_version": self.thesis.draft.thesis_version,
                "exit_policy_version": self.exit_policy_version,
                "risk_policy": {
                    "version": self.risk_policy.version,
                    "allow_strategy_origin": self.risk_policy.allow_strategy_origin,
                    "max_order_notional": canonical_decimal_string(
                        self.risk_policy.max_order_notional
                    ),
                    "max_position_notional": canonical_decimal_string(
                        self.risk_policy.max_position_notional
                    ),
                    "max_daily_loss": canonical_decimal_string(
                        self.risk_policy.max_daily_loss
                    ),
                    "require_fresh_book": self.risk_policy.require_fresh_book,
                    "max_book_age_seconds": self.risk_policy.max_book_age_seconds,
                },
                "volume_baseline_shares": canonical_decimal_string(
                    self.volume_baseline_shares
                ),
                "shares_per_lot": self.shares_per_lot,
                "remaining_quantity_shares": self.remaining_quantity_shares,
                "fill_model_version": self.fill_model_version,
                "code_identity": self.code_identity,
            }
        )


@dataclass(frozen=True)
class ShadowDecisionRecord:
    record_id: str
    config_digest: str
    source_event_digest: str
    risk_snapshot_digest: str
    decision_chain_digest: str
    risk_snapshot: RiskSnapshot
    step: TradeManagementReplayStep

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.record_id, "record_id"),
            (self.config_digest, "config_digest"),
            (self.source_event_digest, "source_event_digest"),
            (self.risk_snapshot_digest, "risk_snapshot_digest"),
            (self.decision_chain_digest, "decision_chain_digest"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.risk_snapshot_digest != _digest(
            _risk_snapshot_wire(self.risk_snapshot)
        ):
            raise ValueError("risk_snapshot_digest does not match RiskSnapshot")


@dataclass(frozen=True)
class ShadowDecisionSnapshot:
    config_digest: str
    records: tuple[ShadowDecisionRecord, ...]
    decision_chain_digest: str
    consumed_event_count: int
    finalized: bool


class ShadowParityStatus(StrEnum):
    MATCHED = "MATCHED"
    DIVERGED = "DIVERGED"


@dataclass(frozen=True)
class ShadowParityReport:
    status: ShadowParityStatus
    shadow_decision_digest: str
    replay_decision_digest: str
    first_divergent_sequence: int | None = None

    def __post_init__(self) -> None:
        if self.status is ShadowParityStatus.MATCHED:
            if self.shadow_decision_digest != self.replay_decision_digest:
                raise ValueError("MATCHED parity requires equal decision digests")
            if self.first_divergent_sequence is not None:
                raise ValueError("MATCHED parity cannot have a divergent sequence")
        elif self.first_divergent_sequence is None:
            raise ValueError("DIVERGED parity requires first_divergent_sequence")


@dataclass(frozen=True)
class ShadowDecisionSession:
    manifest_sha256: str
    records: tuple[ShadowDecisionRecord, ...]
    parity: ShadowParityReport
    replay_result: TradeManagementReplayResult

    def __post_init__(self) -> None:
        if self.manifest_sha256 != self.replay_result.run_identity.manifest_sha256:
            raise ValueError("Shadow session manifest must bind to Replay result")


class ShadowDecisionPipeline:
    """Incremental consumer for an already-canonical live event stream."""

    def __init__(self, config: ShadowDecisionConfig) -> None:
        self._config = config
        self._kernel = TradeManagementDecisionKernel()
        self._state = TradeManagementDecisionState()
        self._events: list[EventEnvelope] = []
        self._risk_snapshots: list[RiskSnapshot] = []
        self._records: list[ShadowDecisionRecord] = []
        self._duplicates: dict[
            str,
            tuple[str, str, ShadowDecisionRecord | None],
        ] = {}
        self._finalized = False

    def consume(
        self,
        event: EventEnvelope,
        *,
        risk_snapshot: RiskSnapshot,
    ) -> ShadowDecisionRecord | None:
        if self._finalized:
            raise RuntimeError("Shadow Decision Pipeline is finalized")
        event_digest = hashlib.sha256(
            serialize_event_envelope(event).encode()
        ).hexdigest()
        risk_digest = _digest(_risk_snapshot_wire(risk_snapshot))
        duplicate = self._duplicates.get(event.event_id)
        if duplicate is not None:
            if duplicate[:2] != (event_digest, risk_digest):
                raise ValueError("duplicate event conflict")
            return duplicate[2]

        next_state, step = self._kernel.apply(
            self._config.decision_config,
            self._state,
            event,
            risk_snapshot=risk_snapshot,
        )
        record = None
        if step is not None:
            record_id = "shadow_decision_v1_" + _digest(
                [
                    SHADOW_PIPELINE_VERSION,
                    self._config.digest,
                    event.event_id,
                    next_state.decision_digest,
                ]
            )
            record = ShadowDecisionRecord(
                record_id=record_id,
                config_digest=self._config.digest,
                source_event_digest=event_digest,
                risk_snapshot_digest=risk_digest,
                decision_chain_digest=next_state.decision_digest,
                risk_snapshot=risk_snapshot,
                step=step,
            )
        self._state = next_state
        self._events.append(event)
        self._risk_snapshots.append(risk_snapshot)
        self._duplicates[event.event_id] = (event_digest, risk_digest, record)
        if record is not None:
            self._records.append(record)
        return record

    def snapshot(self) -> ShadowDecisionSnapshot:
        return ShadowDecisionSnapshot(
            config_digest=self._config.digest,
            records=tuple(self._records),
            decision_chain_digest=self._state.decision_digest,
            consumed_event_count=len(self._events),
            finalized=self._finalized,
        )

    def finalize(self) -> ShadowDecisionSession:
        if self._finalized:
            raise RuntimeError("Shadow Decision Pipeline is already finalized")
        if not self._events:
            raise ValueError("Shadow Decision Pipeline has no canonical events")
        manifest_sha256 = build_market_manifest_digest(tuple(self._events))
        thesis = self._config.thesis
        run_identity = ReplayRunIdentity(
            manifest_sha256=manifest_sha256,
            canonical_event_schema_version=MARKET_EVENT_SCHEMA_VERSION,
            strategy_id=thesis.draft.strategy_id,
            strategy_version=thesis.draft.strategy_version,
            thesis_type=thesis.draft.thesis_type,
            thesis_version=thesis.draft.thesis_version,
            exit_policy_version=self._config.exit_policy_version,
            guard_policy_version=self._config.risk_policy.version,
            fill_model_version=self._config.fill_model_version,
            code_identity=self._config.code_identity,
        )
        replay_result = TradeManagementReplayRunner().run(
            TradeManagementReplayInput(
                run_identity=run_identity,
                thesis=thesis,
                events=tuple(self._events),
                volume_baseline_shares=self._config.volume_baseline_shares,
                shares_per_lot=self._config.shares_per_lot,
                remaining_quantity_shares=self._config.remaining_quantity_shares,
                risk_snapshot=self._risk_snapshots[0],
                risk_policy=self._config.risk_policy,
                risk_snapshots=tuple(self._risk_snapshots),
            )
        )
        replay_digest = replay_result.verification.output.decision_digest
        first_divergent_sequence = self._first_divergent_sequence(replay_result)
        if (
            self._state.decision_digest != replay_digest
            and first_divergent_sequence is None
        ):
            first_divergent_sequence = len(self._records) + 1
        status = (
            ShadowParityStatus.MATCHED
            if self._state.decision_digest == replay_digest
            and first_divergent_sequence is None
            else ShadowParityStatus.DIVERGED
        )
        parity = ShadowParityReport(
            status=status,
            shadow_decision_digest=self._state.decision_digest,
            replay_decision_digest=replay_digest,
            first_divergent_sequence=first_divergent_sequence,
        )
        self._finalized = True
        return ShadowDecisionSession(
            manifest_sha256=manifest_sha256,
            records=tuple(self._records),
            parity=parity,
            replay_result=replay_result,
        )

    def _first_divergent_sequence(
        self,
        replay_result: TradeManagementReplayResult,
    ) -> int | None:
        live_steps = tuple(record.step for record in self._records)
        for sequence, (live, replay) in enumerate(
            zip(live_steps, replay_result.steps),
            start=1,
        ):
            if live != replay:
                return sequence
        if len(live_steps) != len(replay_result.steps):
            return min(len(live_steps), len(replay_result.steps)) + 1
        return None
