"""Canonical JSON codecs for the frozen Trade Management v1 contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from trading.canonical_values import canonical_decimal_string
from trading.trade_management import (
    BreakoutLevelLostSpec,
    ComparisonOperator,
    CompletionPolicy,
    DECISION_LIFECYCLE_TRANSITIONS,
    DECISION_TERMINAL_STATES,
    EntryEvidence,
    EntryEvidenceStatus,
    EvidenceValue,
    EvidenceValueKind,
    ExitLeg,
    ExitReason,
    ORDER_LIFECYCLE_TRANSITIONS,
    ORDER_TERMINAL_STATES,
    PnlBasis,
    PostEntryVolumeExpansionSpec,
    PriceReference,
    SessionDataBlockedSpec,
    TRADE_LIFECYCLE_TRANSITIONS,
    TRADE_MANAGEMENT_SCHEMA_VERSION,
    TRADE_TERMINAL_STATES,
    TRADE_TIMEZONE,
    TAIPEI,
    ThesisType,
    TimestampPrecision,
    TimestampRole,
    TimestampSource,
    TradeSide,
    TradeThesisDraft,
    VolumeBaselineKind,
    VolumeUnit,
    VwapConfirmationLostSpec,
    DecisionLifecycleState,
    ExitRecommendationStatus,
    ExitRecommendation,
    ExpectedBehaviorPolicy,
    HoldAboveVwapSpec,
    LiveEntryDecision,
    NewHighExtensionSpec,
    OrderLifecycleState,
    ReplayVerification,
    TradeLifecycleState,
    TradeOutcome,
    TradeThesis,
    TradeTimestamp,
)


class TradeManagementDeserializationError(ValueError):
    """A canonical Trade Management payload cannot be read as frozen v1."""


def _normalize(value: object) -> object:
    if isinstance(value, TradeTimestamp):
        return {
            "precision": value.precision.value,
            "role": value.role.value,
            "source": value.source.value,
            "source_identity": value.source_identity,
            "timezone": TRADE_TIMEZONE,
            "value": value.isoformat,
        }
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
        if not seconds.is_integer():
            raise ValueError("timedelta contract values must use whole seconds")
        return int(seconds)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _normalize(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported trade contract value: {type(value).__name__}")


def _serialize(contract_type: str, value: object) -> str:
    payload = {
        "contract_type": contract_type,
        "payload": _normalize(value),
        "schema_version": TRADE_MANAGEMENT_SCHEMA_VERSION,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_trade_thesis(value: TradeThesis) -> str:
    return _serialize("TradeThesis", value)


def serialize_trade_thesis_draft(value: TradeThesisDraft) -> str:
    return _serialize("TradeThesisDraft", value)


def serialize_live_entry_decision(value: LiveEntryDecision) -> str:
    return _serialize("LiveEntryDecision", value)


def serialize_exit_recommendation(value: ExitRecommendation) -> str:
    return _serialize("ExitRecommendation", value)


def serialize_trade_outcome(value: TradeOutcome) -> str:
    return _serialize("TradeOutcome", value)


def serialize_replay_verification(value: ReplayVerification) -> str:
    return _serialize("ReplayVerification", value)


def _transitions(
    values: frozenset[tuple[Enum, Enum]],
) -> list[dict[str, str]]:
    return [
        {"from": start.value, "to": end.value}
        for start, end in sorted(
            values,
            key=lambda item: (item[0].value, item[1].value),
        )
    ]


def serialize_lifecycle_contract() -> str:
    payload: dict[str, Any] = {
        "decision": {
            "states": [item.value for item in DecisionLifecycleState],
            "terminal_states": sorted(item.value for item in DECISION_TERMINAL_STATES),
            "transitions": _transitions(DECISION_LIFECYCLE_TRANSITIONS),
        },
        "order": {
            "states": [item.value for item in OrderLifecycleState],
            "terminal_states": sorted(item.value for item in ORDER_TERMINAL_STATES),
            "transitions": _transitions(ORDER_LIFECYCLE_TRANSITIONS),
        },
        "trade": {
            "states": [item.value for item in TradeLifecycleState],
            "terminal_states": sorted(item.value for item in TRADE_TERMINAL_STATES),
            "transitions": _transitions(TRADE_LIFECYCLE_TRANSITIONS),
        },
    }
    return _serialize("LifecycleContract", payload)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TradeManagementDeserializationError(
            f"{field_name} must be a JSON object"
        )
    return value


def _exact_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    field_name: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise TradeManagementDeserializationError(
            f"{field_name} fields mismatch: missing={missing}, unknown={unknown}"
        )


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TradeManagementDeserializationError(f"{field_name} must be a string")
    return value


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TradeManagementDeserializationError(f"{field_name} must be an integer")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TradeManagementDeserializationError(f"{field_name} must be a boolean")
    return value


def _decimal(value: object, field_name: str) -> Decimal:
    raw = _string(value, field_name)
    try:
        parsed = Decimal(raw)
    except InvalidOperation as error:
        raise TradeManagementDeserializationError(
            f"{field_name} must be a decimal string"
        ) from error
    try:
        canonical = canonical_decimal_string(parsed)
    except ValueError as error:
        raise TradeManagementDeserializationError(
            f"{field_name} must be a finite decimal string"
        ) from error
    if canonical != raw:
        raise TradeManagementDeserializationError(
            f"{field_name} must use canonical decimal notation"
        )
    return parsed


def _enum(enum_type: type[Enum], value: object, field_name: str) -> Any:
    raw = _string(value, field_name)
    try:
        return enum_type(raw)
    except ValueError as error:
        raise TradeManagementDeserializationError(
            f"{field_name} has an unsupported v1 value"
        ) from error


def _list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise TradeManagementDeserializationError(f"{field_name} must be a list")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise TradeManagementDeserializationError(
                f"duplicate JSON object key: {key}"
            )
        value[key] = item
    return value


def _envelope(serialized: str, expected_contract_type: str) -> Mapping[str, object]:
    try:
        raw = json.loads(serialized, object_pairs_hook=_json_object)
    except (json.JSONDecodeError, TypeError) as error:
        raise TradeManagementDeserializationError(
            "trade-management contract must be valid JSON"
        ) from error
    envelope = _mapping(raw, "contract envelope")
    _exact_fields(
        envelope,
        frozenset({"contract_type", "payload", "schema_version"}),
        "contract envelope",
    )
    schema_version = _string(envelope["schema_version"], "schema_version")
    if schema_version != TRADE_MANAGEMENT_SCHEMA_VERSION:
        raise TradeManagementDeserializationError(
            f"unsupported trade-management schema: {schema_version}"
        )
    contract_type = _string(envelope["contract_type"], "contract_type")
    if contract_type != expected_contract_type:
        raise TradeManagementDeserializationError(
            f"expected {expected_contract_type}, got {contract_type}"
        )
    return _mapping(envelope["payload"], f"{expected_contract_type} payload")


def _trade_timestamp(value: object, field_name: str) -> TradeTimestamp:
    payload = _mapping(value, field_name)
    _exact_fields(
        payload,
        frozenset(
            {"precision", "role", "source", "source_identity", "timezone", "value"}
        ),
        field_name,
    )
    timezone = _string(payload["timezone"], f"{field_name}.timezone")
    if timezone != TRADE_TIMEZONE:
        raise TradeManagementDeserializationError(
            f"{field_name}.timezone must be {TRADE_TIMEZONE}"
        )
    raw_value = _string(payload["value"], f"{field_name}.value")
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as error:
        raise TradeManagementDeserializationError(
            f"{field_name}.value must be ISO-8601"
        ) from error
    if parsed.utcoffset() != TAIPEI.utcoffset(parsed):
        raise TradeManagementDeserializationError(
            f"{field_name}.value must use the {TRADE_TIMEZONE} offset"
        )
    timestamp = TradeTimestamp(
        role=_enum(TimestampRole, payload["role"], f"{field_name}.role"),
        value=parsed.replace(tzinfo=TAIPEI),
        source=_enum(TimestampSource, payload["source"], f"{field_name}.source"),
        source_identity=_string(
            payload["source_identity"], f"{field_name}.source_identity"
        ),
        precision=_enum(
            TimestampPrecision,
            payload["precision"],
            f"{field_name}.precision",
        ),
    )
    if timestamp.isoformat != raw_value:
        raise TradeManagementDeserializationError(
            f"{field_name}.value must use canonical microsecond precision"
        )
    return timestamp


def _evidence_value(value: object, field_name: str) -> EvidenceValue:
    payload = _mapping(value, field_name)
    _exact_fields(payload, frozenset({"kind", "name", "value"}), field_name)
    raw_value = payload["value"]
    if raw_value is not None and not isinstance(raw_value, str):
        raise TradeManagementDeserializationError(
            f"{field_name}.value must be a string or null"
        )
    return EvidenceValue(
        name=_string(payload["name"], f"{field_name}.name"),
        kind=_enum(EvidenceValueKind, payload["kind"], f"{field_name}.kind"),
        value=raw_value,
    )


def _entry_evidence(value: object, field_name: str) -> EntryEvidence:
    payload = _mapping(value, field_name)
    _exact_fields(
        payload,
        frozenset(
            {
                "evidence_id",
                "kind",
                "market_event_id",
                "observed",
                "observed_at",
                "source_component",
                "source_version",
                "status",
                "threshold",
            }
        ),
        field_name,
    )
    return EntryEvidence(
        evidence_id=_string(payload["evidence_id"], f"{field_name}.evidence_id"),
        kind=_string(payload["kind"], f"{field_name}.kind"),
        source_component=_string(
            payload["source_component"], f"{field_name}.source_component"
        ),
        source_version=_string(
            payload["source_version"], f"{field_name}.source_version"
        ),
        status=_enum(
            EntryEvidenceStatus,
            payload["status"],
            f"{field_name}.status",
        ),
        observed=tuple(
            _evidence_value(item, f"{field_name}.observed[{index}]")
            for index, item in enumerate(_list(payload["observed"], f"{field_name}.observed"))
        ),
        threshold=tuple(
            _evidence_value(item, f"{field_name}.threshold[{index}]")
            for index, item in enumerate(
                _list(payload["threshold"], f"{field_name}.threshold")
            )
        ),
        market_event_id=_string(
            payload["market_event_id"], f"{field_name}.market_event_id"
        ),
        observed_at=_trade_timestamp(
            payload["observed_at"], f"{field_name}.observed_at"
        ),
    )


def _expected_condition(value: object, field_name: str) -> object:
    payload = _mapping(value, field_name)
    kind = _string(payload.get("kind"), f"{field_name}.kind")
    if kind == "NEW_HIGH_EXTENSION":
        _exact_fields(
            payload,
            frozenset({"buffer", "comparison", "kind", "reference"}),
            field_name,
        )
        return NewHighExtensionSpec(
            reference=_enum(
                PriceReference,
                payload["reference"],
                f"{field_name}.reference",
            ),
            buffer=_decimal(payload["buffer"], f"{field_name}.buffer"),
            comparison=_enum(
                ComparisonOperator,
                payload["comparison"],
                f"{field_name}.comparison",
            ),
        )
    if kind == "POST_ENTRY_VOLUME_EXPANSION":
        _exact_fields(
            payload,
            frozenset(
                {
                    "baseline_kind",
                    "comparison",
                    "kind",
                    "minimum_samples",
                    "ratio",
                    "volume_unit",
                }
            ),
            field_name,
        )
        return PostEntryVolumeExpansionSpec(
            baseline_kind=_enum(
                VolumeBaselineKind,
                payload["baseline_kind"],
                f"{field_name}.baseline_kind",
            ),
            ratio=_decimal(payload["ratio"], f"{field_name}.ratio"),
            minimum_samples=_integer(
                payload["minimum_samples"], f"{field_name}.minimum_samples"
            ),
            volume_unit=_enum(
                VolumeUnit,
                payload["volume_unit"],
                f"{field_name}.volume_unit",
            ),
            comparison=_enum(
                ComparisonOperator,
                payload["comparison"],
                f"{field_name}.comparison",
            ),
        )
    if kind == "HOLD_ABOVE_VWAP":
        _exact_fields(
            payload,
            frozenset({"allowed_completed_bars_below", "comparison", "kind"}),
            field_name,
        )
        return HoldAboveVwapSpec(
            allowed_completed_bars_below=_integer(
                payload["allowed_completed_bars_below"],
                f"{field_name}.allowed_completed_bars_below",
            ),
            comparison=_enum(
                ComparisonOperator,
                payload["comparison"],
                f"{field_name}.comparison",
            ),
        )
    raise TradeManagementDeserializationError(
        f"{field_name}.kind has an unsupported v1 value"
    )


def _invalid_condition(value: object, field_name: str) -> object:
    payload = _mapping(value, field_name)
    kind = _string(payload.get("kind"), f"{field_name}.kind")
    if kind == "BREAKOUT_LEVEL_LOST":
        _exact_fields(
            payload,
            frozenset(
                {
                    "breakout_level",
                    "comparison",
                    "confirmation_completed_bars",
                    "kind",
                }
            ),
            field_name,
        )
        return BreakoutLevelLostSpec(
            breakout_level=_decimal(
                payload["breakout_level"], f"{field_name}.breakout_level"
            ),
            confirmation_completed_bars=_integer(
                payload["confirmation_completed_bars"],
                f"{field_name}.confirmation_completed_bars",
            ),
            comparison=_enum(
                ComparisonOperator,
                payload["comparison"],
                f"{field_name}.comparison",
            ),
        )
    if kind == "VWAP_CONFIRMATION_LOST":
        _exact_fields(
            payload,
            frozenset({"comparison", "confirmation_completed_bars", "kind"}),
            field_name,
        )
        return VwapConfirmationLostSpec(
            confirmation_completed_bars=_integer(
                payload["confirmation_completed_bars"],
                f"{field_name}.confirmation_completed_bars",
            ),
            comparison=_enum(
                ComparisonOperator,
                payload["comparison"],
                f"{field_name}.comparison",
            ),
        )
    if kind == "SESSION_DATA_BLOCKED":
        _exact_fields(
            payload,
            frozenset(
                {
                    "block_on_session_mismatch",
                    "blocked_health_states",
                    "kind",
                }
            ),
            field_name,
        )
        return SessionDataBlockedSpec(
            blocked_health_states=tuple(
                _string(item, f"{field_name}.blocked_health_states[{index}]")
                for index, item in enumerate(
                    _list(
                        payload["blocked_health_states"],
                        f"{field_name}.blocked_health_states",
                    )
                )
            ),
            block_on_session_mismatch=_boolean(
                payload["block_on_session_mismatch"],
                f"{field_name}.block_on_session_mismatch",
            ),
        )
    raise TradeManagementDeserializationError(
        f"{field_name}.kind has an unsupported v1 value"
    )


def _expected_behavior(value: object, field_name: str) -> ExpectedBehaviorPolicy:
    payload = _mapping(value, field_name)
    _exact_fields(
        payload,
        frozenset(
            {
                "completion_policy",
                "conditions",
                "observation_window",
                "policy_id",
                "version",
                "warning_after",
            }
        ),
        field_name,
    )
    raw_warning = payload["warning_after"]
    warning_after = (
        None
        if raw_warning is None
        else timedelta(seconds=_integer(raw_warning, f"{field_name}.warning_after"))
    )
    return ExpectedBehaviorPolicy(
        policy_id=_string(payload["policy_id"], f"{field_name}.policy_id"),
        version=_string(payload["version"], f"{field_name}.version"),
        observation_window=timedelta(
            seconds=_integer(
                payload["observation_window"],
                f"{field_name}.observation_window",
            )
        ),
        warning_after=warning_after,
        completion_policy=_enum(
            CompletionPolicy,
            payload["completion_policy"],
            f"{field_name}.completion_policy",
        ),
        conditions=tuple(
            _expected_condition(item, f"{field_name}.conditions[{index}]")
            for index, item in enumerate(
                _list(payload["conditions"], f"{field_name}.conditions")
            )
        ),
    )


_DRAFT_FIELDS = frozenset(
    {
        "created_at",
        "decision_id",
        "entry_evidence",
        "expected_behavior",
        "invalid_conditions",
        "schema_version",
        "session_id",
        "side",
        "signal_at",
        "strategy_id",
        "strategy_version",
        "symbol",
        "thesis_id",
        "thesis_type",
        "thesis_version",
    }
)


_LIVE_ENTRY_DECISION_FIELDS = frozenset(
    {
        "decided_at",
        "decision_id",
        "builder_version",
        "entry_evidence",
        "market_context_digest",
        "matched_rules",
        "schema_version",
        "score",
        "session_id",
        "side",
        "signal_at",
        "strategy_id",
        "strategy_version",
        "symbol",
    }
)


def _live_entry_decision(value: object, field_name: str) -> LiveEntryDecision:
    payload = _mapping(value, field_name)
    _exact_fields(payload, _LIVE_ENTRY_DECISION_FIELDS, field_name)
    return LiveEntryDecision(
        decision_id=_string(payload["decision_id"], f"{field_name}.decision_id"),
        builder_version=_string(
            payload["builder_version"], f"{field_name}.builder_version"
        ),
        session_id=_string(payload["session_id"], f"{field_name}.session_id"),
        symbol=_string(payload["symbol"], f"{field_name}.symbol"),
        side=_enum(TradeSide, payload["side"], f"{field_name}.side"),
        strategy_id=_string(payload["strategy_id"], f"{field_name}.strategy_id"),
        strategy_version=_string(
            payload["strategy_version"], f"{field_name}.strategy_version"
        ),
        signal_at=_trade_timestamp(payload["signal_at"], f"{field_name}.signal_at"),
        decided_at=_trade_timestamp(
            payload["decided_at"], f"{field_name}.decided_at"
        ),
        score=_decimal(payload["score"], f"{field_name}.score"),
        matched_rules=tuple(
            _string(item, f"{field_name}.matched_rules[{index}]")
            for index, item in enumerate(
                _list(payload["matched_rules"], f"{field_name}.matched_rules")
            )
        ),
        market_context_digest=_string(
            payload["market_context_digest"],
            f"{field_name}.market_context_digest",
        ),
        entry_evidence=tuple(
            _entry_evidence(item, f"{field_name}.entry_evidence[{index}]")
            for index, item in enumerate(
                _list(payload["entry_evidence"], f"{field_name}.entry_evidence")
            )
        ),
        schema_version=_string(
            payload["schema_version"], f"{field_name}.schema_version"
        ),
    )


def _trade_thesis_draft(value: object, field_name: str) -> TradeThesisDraft:
    payload = _mapping(value, field_name)
    _exact_fields(payload, _DRAFT_FIELDS, field_name)
    return TradeThesisDraft(
        thesis_id=_string(payload["thesis_id"], f"{field_name}.thesis_id"),
        session_id=_string(payload["session_id"], f"{field_name}.session_id"),
        symbol=_string(payload["symbol"], f"{field_name}.symbol"),
        side=_enum(TradeSide, payload["side"], f"{field_name}.side"),
        strategy_id=_string(payload["strategy_id"], f"{field_name}.strategy_id"),
        strategy_version=_string(
            payload["strategy_version"], f"{field_name}.strategy_version"
        ),
        thesis_type=_enum(
            ThesisType,
            payload["thesis_type"],
            f"{field_name}.thesis_type",
        ),
        thesis_version=_string(
            payload["thesis_version"], f"{field_name}.thesis_version"
        ),
        decision_id=_string(payload["decision_id"], f"{field_name}.decision_id"),
        signal_at=_trade_timestamp(payload["signal_at"], f"{field_name}.signal_at"),
        created_at=_trade_timestamp(
            payload["created_at"], f"{field_name}.created_at"
        ),
        entry_evidence=tuple(
            _entry_evidence(item, f"{field_name}.entry_evidence[{index}]")
            for index, item in enumerate(
                _list(payload["entry_evidence"], f"{field_name}.entry_evidence")
            )
        ),
        expected_behavior=_expected_behavior(
            payload["expected_behavior"], f"{field_name}.expected_behavior"
        ),
        invalid_conditions=tuple(
            _invalid_condition(item, f"{field_name}.invalid_conditions[{index}]")
            for index, item in enumerate(
                _list(
                    payload["invalid_conditions"],
                    f"{field_name}.invalid_conditions",
                )
            )
        ),
        schema_version=_string(
            payload["schema_version"], f"{field_name}.schema_version"
        ),
    )


def deserialize_trade_thesis_draft(serialized: str) -> TradeThesisDraft:
    payload = _envelope(serialized, "TradeThesisDraft")
    try:
        return _trade_thesis_draft(payload, "TradeThesisDraft payload")
    except TradeManagementDeserializationError:
        raise
    except (TypeError, ValueError) as error:
        raise TradeManagementDeserializationError(
            "invalid TradeThesisDraft v1 payload"
        ) from error


def deserialize_live_entry_decision(serialized: str) -> LiveEntryDecision:
    payload = _envelope(serialized, "LiveEntryDecision")
    try:
        return _live_entry_decision(payload, "LiveEntryDecision payload")
    except TradeManagementDeserializationError:
        raise
    except (TypeError, ValueError) as error:
        raise TradeManagementDeserializationError(
            "invalid LiveEntryDecision v1 payload"
        ) from error


def deserialize_trade_thesis(serialized: str) -> TradeThesis:
    payload = _envelope(serialized, "TradeThesis")
    _exact_fields(
        payload,
        frozenset(
            {
                "draft",
                "entry_reference_price",
                "filled_at",
                "opening_fill_id",
                "opening_order_id",
                "schema_version",
                "thesis_id",
                "trade_id",
            }
        ),
        "TradeThesis payload",
    )
    try:
        return TradeThesis(
            thesis_id=_string(payload["thesis_id"], "thesis_id"),
            trade_id=_string(payload["trade_id"], "trade_id"),
            draft=_trade_thesis_draft(payload["draft"], "draft"),
            opening_order_id=_string(payload["opening_order_id"], "opening_order_id"),
            opening_fill_id=_string(payload["opening_fill_id"], "opening_fill_id"),
            entry_reference_price=_decimal(
                payload["entry_reference_price"], "entry_reference_price"
            ),
            filled_at=_trade_timestamp(payload["filled_at"], "filled_at"),
            schema_version=_string(payload["schema_version"], "schema_version"),
        )
    except TradeManagementDeserializationError:
        raise
    except (TypeError, ValueError) as error:
        raise TradeManagementDeserializationError(
            "invalid TradeThesis v1 payload"
        ) from error


def deserialize_exit_recommendation(serialized: str) -> ExitRecommendation:
    payload = _envelope(serialized, "ExitRecommendation")
    _exact_fields(
        payload,
        frozenset(
            {
                "closing_fill_id",
                "created_at",
                "exit_policy_version",
                "first_trigger_decision_id",
                "first_trigger_event_id",
                "latest_decision_id",
                "latest_evidence_event_id",
                "primary_reason",
                "recommendation_id",
                "resolved_at",
                "schema_version",
                "session_id",
                "status",
                "thesis_id",
                "trade_id",
                "triggered_reasons",
                "updated_at",
            }
        ),
        "ExitRecommendation payload",
    )
    raw_resolved_at = payload["resolved_at"]
    try:
        return ExitRecommendation(
            recommendation_id=_string(
                payload["recommendation_id"], "recommendation_id"
            ),
            session_id=_string(payload["session_id"], "session_id"),
            trade_id=_string(payload["trade_id"], "trade_id"),
            thesis_id=_string(payload["thesis_id"], "thesis_id"),
            exit_policy_version=_string(
                payload["exit_policy_version"], "exit_policy_version"
            ),
            status=_enum(
                ExitRecommendationStatus,
                payload["status"],
                "status",
            ),
            first_trigger_decision_id=_string(
                payload["first_trigger_decision_id"],
                "first_trigger_decision_id",
            ),
            first_trigger_event_id=_string(
                payload["first_trigger_event_id"], "first_trigger_event_id"
            ),
            latest_decision_id=_string(
                payload["latest_decision_id"], "latest_decision_id"
            ),
            latest_evidence_event_id=_string(
                payload["latest_evidence_event_id"],
                "latest_evidence_event_id",
            ),
            primary_reason=_enum(
                ExitReason,
                payload["primary_reason"],
                "primary_reason",
            ),
            triggered_reasons=tuple(
                _enum(ExitReason, item, f"triggered_reasons[{index}]")
                for index, item in enumerate(
                    _list(payload["triggered_reasons"], "triggered_reasons")
                )
            ),
            created_at=_trade_timestamp(payload["created_at"], "created_at"),
            updated_at=_trade_timestamp(payload["updated_at"], "updated_at"),
            resolved_at=(
                None
                if raw_resolved_at is None
                else _trade_timestamp(raw_resolved_at, "resolved_at")
            ),
            closing_fill_id=_optional_string(
                payload["closing_fill_id"], "closing_fill_id"
            ),
            schema_version=_string(payload["schema_version"], "schema_version"),
        )
    except TradeManagementDeserializationError:
        raise
    except (TypeError, ValueError) as error:
        raise TradeManagementDeserializationError(
            "invalid ExitRecommendation v1 payload"
        ) from error


def _exit_leg(value: object, field_name: str) -> ExitLeg:
    payload = _mapping(value, field_name)
    _exact_fields(
        payload,
        frozenset(
            {
                "exit_recommendation_id",
                "fill_id",
                "fill_price",
                "filled_at",
                "order_id",
                "quantity_shares",
                "reason",
            }
        ),
        field_name,
    )
    return ExitLeg(
        fill_id=_string(payload["fill_id"], f"{field_name}.fill_id"),
        order_id=_string(payload["order_id"], f"{field_name}.order_id"),
        exit_recommendation_id=_optional_string(
            payload["exit_recommendation_id"],
            f"{field_name}.exit_recommendation_id",
        ),
        reason=_enum(ExitReason, payload["reason"], f"{field_name}.reason"),
        quantity_shares=_integer(
            payload["quantity_shares"], f"{field_name}.quantity_shares"
        ),
        fill_price=_decimal(payload["fill_price"], f"{field_name}.fill_price"),
        filled_at=_trade_timestamp(payload["filled_at"], f"{field_name}.filled_at"),
    )


def deserialize_trade_outcome(serialized: str) -> TradeOutcome:
    payload = _envelope(serialized, "TradeOutcome")
    _exact_fields(
        payload,
        frozenset(
            {
                "closed_at",
                "closing_exit_reason",
                "exit_legs",
                "initiating_exit_reason",
                "pnl_basis",
                "realized_pnl",
                "schema_version",
                "trade_id",
            }
        ),
        "TradeOutcome payload",
    )
    try:
        return TradeOutcome(
            trade_id=_string(payload["trade_id"], "trade_id"),
            exit_legs=tuple(
                _exit_leg(item, f"exit_legs[{index}]")
                for index, item in enumerate(
                    _list(payload["exit_legs"], "exit_legs")
                )
            ),
            initiating_exit_reason=_enum(
                ExitReason,
                payload["initiating_exit_reason"],
                "initiating_exit_reason",
            ),
            closing_exit_reason=_enum(
                ExitReason,
                payload["closing_exit_reason"],
                "closing_exit_reason",
            ),
            realized_pnl=_decimal(payload["realized_pnl"], "realized_pnl"),
            pnl_basis=_enum(PnlBasis, payload["pnl_basis"], "pnl_basis"),
            closed_at=_trade_timestamp(payload["closed_at"], "closed_at"),
            schema_version=_string(payload["schema_version"], "schema_version"),
        )
    except TradeManagementDeserializationError:
        raise
    except (TypeError, ValueError) as error:
        raise TradeManagementDeserializationError(
            "invalid TradeOutcome v1 payload"
        ) from error
