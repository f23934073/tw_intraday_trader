"""Framework-free contracts for the historical backtest bounded context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum
from typing import Any, Mapping

from strategy_catalog.domain import StrategyDefinition, StrategySide

__all__ = ["StrategyDefinition", "StrategySide"]


def decimal(value: Decimal | int | float | str) -> Decimal:
    """Build a Decimal without carrying binary-float rounding into accounting."""

    return value if isinstance(value, Decimal) else Decimal(str(value))


def canonical_json(value: Mapping[str, Any] | list[Any]) -> str:
    """Stable JSON used for snapshots, idempotency and reproducibility digests."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Mapping[str, Any] | list[Any] | str) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_sha256_hex(value: str) -> bool:
    """True for a lowercase 64-char SHA-256 hex string."""

    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def verify_contract_snapshot(
    snapshot: Mapping[str, Any],
    *,
    label: str,
    expected_contract_version: str | None = None,
) -> dict[str, Any]:
    """Validate an immutable, self-describing contract snapshot.

    Every snapshot carries a ``contract_version`` and a ``snapshot_digest``
    equal to the SHA-256 of its body with ``snapshot_digest`` removed. Any
    mismatch fails closed with a ``ValueError``.
    """

    body = dict(snapshot)
    contract_version = body.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version:
        raise ValueError(f"{label} 缺少 contract_version")
    if expected_contract_version is not None and contract_version != expected_contract_version:
        raise ValueError(f"{label} contract_version 未知：{contract_version}")
    snapshot_digest = str(body.get("snapshot_digest") or "")
    if not is_sha256_hex(snapshot_digest):
        raise ValueError(f"{label} snapshot_digest 必須是 lowercase SHA-256")
    recomputed = digest({key: value for key, value in body.items() if key != "snapshot_digest"})
    if recomputed != snapshot_digest:
        raise ValueError(f"{label} snapshot_digest 與 evidence 不一致")
    return body


class AggregationPolicy(StrEnum):
    ANY = "ANY"
    ALL = "ALL"
    AT_LEAST_N = "AT_LEAST_N"


class EvaluationStatus(StrEnum):
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    BLOCKED = "BLOCKED"


class ExecutionHorizon(StrEnum):
    """Code-owned fill semantics; not a browser/configurable free-form value."""

    INTRADAY_NEXT_BAR = "INTRADAY_NEXT_BAR"
    DAILY_NEXT_BAR = "DAILY_NEXT_BAR"
    SESSION_CLOSE = "SESSION_CLOSE"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    PREFLIGHT = "PREFLIGHT"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    CONTROL_POSTFLIGHT = "CONTROL_POSTFLIGHT"
    INVALID_CASH_ADMISSION_CONTROL = "INVALID_CASH_ADMISSION_CONTROL"
    COMPLETED = "COMPLETED"


# --- Frozen v3-tw seam ------------------------------------------------------
# Engine identities are code-owned. Legacy v1/v2 remain byte- and behaviour
# compatible; ``backtest-engine-v3-tw`` is an explicit opt-in and is the only
# identity that activates the Taiwan formal execution/cost/research contracts.
ENGINE_V1 = "backtest-engine-v1"
ENGINE_V2 = "backtest-engine-v2"
ENGINE_V3_TW = "backtest-engine-v3-tw"
LEGACY_ENGINE_VERSIONS = frozenset({ENGINE_V1, ENGINE_V2})

# Contract version tags carried inside the immutable RunConfig snapshots and the
# serialized formal-evidence object. Consumers (Package B) read these but never
# redefine them.
FORMAL_EVIDENCE_VERSION = "tw-formal-evidence-v1"
EXECUTION_POLICY_CONTRACT_VERSION = "tw-execution-policy-v1"
COST_POLICY_CONTRACT_VERSION = "tw-cost-policy-v1"
RESEARCH_TRUTH_CONTRACT_VERSION = "tw-research-truth-v1"

FORMAL_SPECIAL_REGIME_REASONS = frozenset(
    {
        "MISSING_SESSION_REGIME",
        "UNKNOWN_SESSION_REGIME",
        "UNSUPPORTED_IPO_NO_LIMIT_WINDOW",
        "UNSUPPORTED_DISPOSITION_PERIODIC_AUCTION",
    }
)


class MarketPhase(StrEnum):
    """PIT trading phase of a historical bar. Only these values are known;
    formal v3 fails closed on anything absent or unknown."""

    CONTINUOUS = "CONTINUOUS"
    CLOSING_AUCTION = "CLOSING_AUCTION"


class FormalEvidenceError(ValueError):
    """Raised when the sole downstream ``summary.formal_evidence`` input is
    absent, carries an unknown version, or fails its digest check. It always
    fails closed — there is no lenient/fallback path."""


def _require_exact_keys(value: Mapping[str, Any], *, expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unknown:
            details.append("unknown=" + ",".join(unknown))
        raise FormalEvidenceError(f"{label} schema mismatch ({'; '.join(details)})")


def _non_negative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise FormalEvidenceError(f"{label} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise FormalEvidenceError(f"{label} must be a non-negative integer") from exc
    if parsed < 0 or str(parsed) != str(value):
        raise FormalEvidenceError(f"{label} must be a non-negative integer")
    return parsed


def _non_negative_decimal(value: Any, *, label: str) -> Decimal:
    try:
        parsed = decimal(value)
    except Exception as exc:
        raise FormalEvidenceError(f"{label} must be a non-negative decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise FormalEvidenceError(f"{label} must be a non-negative decimal")
    return parsed


@dataclass(frozen=True)
class FormalEvidence:
    """Frozen v3 evidence shared by the engine and downstream qualification.

    ``summary.formal_evidence`` is the only supported downstream projection.
    The top-level copy exists to make the complete immutable result auditable;
    :func:`formal_evidence_from_result` requires both copies to match exactly.
    """

    active_dates: int
    coverage_eligible_count: int
    coverage_evaluable_count: int
    coverage_unavailable_count: int
    coverage_ratio: Decimal
    coverage_minimum: Decimal
    execution_fallback_count: int
    execution_locked_limit_count: int
    execution_partial_fill_count: int
    execution_residual_count: int
    execution_auction_close_count: int
    execution_overnight_breach_count: int
    special_regime_denominator_count: int
    special_regime_reason_counts: Mapping[str, int]
    capacity_before_cost_shares: int
    capacity_after_cost_shares: int
    version: str = FORMAL_EVIDENCE_VERSION

    def __post_init__(self) -> None:
        if self.version != FORMAL_EVIDENCE_VERSION:
            raise FormalEvidenceError(f"unknown formal evidence version: {self.version}")
        integer_fields = (
            "active_dates",
            "coverage_eligible_count",
            "coverage_evaluable_count",
            "coverage_unavailable_count",
            "execution_fallback_count",
            "execution_locked_limit_count",
            "execution_partial_fill_count",
            "execution_residual_count",
            "execution_auction_close_count",
            "execution_overnight_breach_count",
            "special_regime_denominator_count",
            "capacity_before_cost_shares",
            "capacity_after_cost_shares",
        )
        for field_name in integer_fields:
            object.__setattr__(
                self,
                field_name,
                _non_negative_int(getattr(self, field_name), label=field_name),
            )
        for field_name in ("coverage_ratio", "coverage_minimum"):
            parsed = _non_negative_decimal(getattr(self, field_name), label=field_name)
            if parsed > 1:
                raise FormalEvidenceError(f"{field_name} must be between 0 and 1")
            object.__setattr__(self, field_name, parsed)
        if (
            self.coverage_evaluable_count + self.coverage_unavailable_count
            != self.coverage_eligible_count
        ):
            raise FormalEvidenceError("coverage evaluable + unavailable must equal eligible")
        expected_ratio = (
            Decimal("0")
            if self.coverage_eligible_count == 0
            else Decimal(self.coverage_evaluable_count) / Decimal(self.coverage_eligible_count)
        )
        tolerance = Decimal("0.000000000000000001")
        if abs(self.coverage_ratio - expected_ratio) > tolerance:
            raise FormalEvidenceError("coverage ratio does not match counts")
        if self.capacity_after_cost_shares > self.capacity_before_cost_shares:
            raise FormalEvidenceError("capacity after cost cannot exceed capacity before cost")
        reasons: dict[str, int] = {}
        for reason, count in self.special_regime_reason_counts.items():
            reason = str(reason)
            if reason not in FORMAL_SPECIAL_REGIME_REASONS:
                raise FormalEvidenceError(f"unknown special-regime reason: {reason}")
            reasons[reason] = _non_negative_int(
                count, label=f"special_regime_reason_counts.{reason}"
            )
        if sum(reasons.values()) != self.special_regime_denominator_count:
            raise FormalEvidenceError("special-regime reason counts must equal denominator")
        object.__setattr__(self, "special_regime_reason_counts", reasons)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "version": self.version,
            "active_dates": self.active_dates,
            "coverage": {
                "eligible_count": self.coverage_eligible_count,
                "evaluable_count": self.coverage_evaluable_count,
                "unavailable_count": self.coverage_unavailable_count,
                "ratio": str(self.coverage_ratio),
                "minimum": str(self.coverage_minimum),
            },
            "execution": {
                "fallback_count": self.execution_fallback_count,
                "locked_limit_count": self.execution_locked_limit_count,
                "partial_fill_count": self.execution_partial_fill_count,
                "residual_count": self.execution_residual_count,
                "auction_close_count": self.execution_auction_close_count,
                "overnight_breach_count": self.execution_overnight_breach_count,
            },
            "special_regime": {
                "denominator_count": self.special_regime_denominator_count,
                "reason_counts": dict(sorted(self.special_regime_reason_counts.items())),
            },
            "capacity": {
                "before_cost_shares": self.capacity_before_cost_shares,
                "after_cost_shares": self.capacity_after_cost_shares,
            },
        }
        return {**body, "evidence_digest": digest(body)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FormalEvidence":
        raw = dict(value)
        _require_exact_keys(
            raw,
            expected={
                "version",
                "active_dates",
                "coverage",
                "execution",
                "special_regime",
                "capacity",
                "evidence_digest",
            },
            label="formal_evidence",
        )
        stored_digest = str(raw.pop("evidence_digest"))
        if not is_sha256_hex(stored_digest) or digest(raw) != stored_digest:
            raise FormalEvidenceError("formal_evidence digest mismatch")
        coverage = dict(raw["coverage"])
        execution = dict(raw["execution"])
        special_regime = dict(raw["special_regime"])
        capacity = dict(raw["capacity"])
        _require_exact_keys(
            coverage,
            expected={
                "eligible_count",
                "evaluable_count",
                "unavailable_count",
                "ratio",
                "minimum",
            },
            label="formal_evidence.coverage",
        )
        _require_exact_keys(
            execution,
            expected={
                "fallback_count",
                "locked_limit_count",
                "partial_fill_count",
                "residual_count",
                "auction_close_count",
                "overnight_breach_count",
            },
            label="formal_evidence.execution",
        )
        _require_exact_keys(
            special_regime,
            expected={"denominator_count", "reason_counts"},
            label="formal_evidence.special_regime",
        )
        _require_exact_keys(
            capacity,
            expected={"before_cost_shares", "after_cost_shares"},
            label="formal_evidence.capacity",
        )
        if not isinstance(special_regime["reason_counts"], Mapping):
            raise FormalEvidenceError(
                "formal_evidence.special_regime.reason_counts must be an object"
            )
        return cls(
            version=str(raw["version"]),
            active_dates=raw["active_dates"],
            coverage_eligible_count=coverage["eligible_count"],
            coverage_evaluable_count=coverage["evaluable_count"],
            coverage_unavailable_count=coverage["unavailable_count"],
            coverage_ratio=decimal(coverage["ratio"]),
            coverage_minimum=decimal(coverage["minimum"]),
            execution_fallback_count=execution["fallback_count"],
            execution_locked_limit_count=execution["locked_limit_count"],
            execution_partial_fill_count=execution["partial_fill_count"],
            execution_residual_count=execution["residual_count"],
            execution_auction_close_count=execution["auction_close_count"],
            execution_overnight_breach_count=execution["overnight_breach_count"],
            special_regime_denominator_count=special_regime["denominator_count"],
            special_regime_reason_counts=dict(special_regime["reason_counts"]),
            capacity_before_cost_shares=capacity["before_cost_shares"],
            capacity_after_cost_shares=capacity["after_cost_shares"],
        )


def formal_evidence_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the verified sole downstream evidence, or fail closed.

    Both serialized locations are mandatory and must be byte-equivalent as
    canonical JSON. Downstream qualification and UI code must call this helper
    and consume only the returned ``summary.formal_evidence`` value.
    """

    top_level = result.get("formal_evidence")
    summary = result.get("summary")
    if not isinstance(top_level, Mapping) or not isinstance(summary, Mapping):
        raise FormalEvidenceError("formal_evidence and summary are required")
    downstream = summary.get("formal_evidence")
    if not isinstance(downstream, Mapping):
        raise FormalEvidenceError("summary.formal_evidence is required")
    if canonical_json(dict(top_level)) != canonical_json(dict(downstream)):
        raise FormalEvidenceError("formal_evidence copies do not match")
    return FormalEvidence.from_dict(downstream).to_dict()


@dataclass(frozen=True)
class HistoricalBar:
    """A canonical historical OHLCV bar.  Timestamps must be timezone aware."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    name: str = ""
    market: str = ""
    amount: Decimal | None = None
    # Legacy datasets omit this value entirely. New derived-daily datasets must
    # persist a calendar-resolved trading date instead of deriving it from the
    # timestamp in the engine.
    session_date: date | None = None
    # A derived daily bar is timestamped at the completed session close so its
    # signal cannot look ahead. Preserve the first source-bar time separately
    # for truthful next-session-open fill audit records.
    session_open_at: datetime | None = None
    # --- Optional v3-tw PIT fields ------------------------------------------
    # Legacy engines (v1/v2) omit these entirely and serialize byte-identically.
    # The formal ``backtest-engine-v3-tw`` engine rejects a bar whose formal
    # fields are absent or unknown (see execution_policy_tw.require_formal_bar).
    market_phase: str | None = None
    session_regime: str | None = None
    reference_price: Decimal | None = None
    lower_limit_price: Decimal | None = None
    upper_limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol 不可為空")
        if self.timestamp.tzinfo is None:
            raise ValueError("歷史 Kbar timestamp 必須包含 timezone")
        if self.session_open_at is not None:
            if self.session_open_at.tzinfo is None:
                raise ValueError("歷史 Kbar session_open_at 必須包含 timezone")
            if self.session_open_at > self.timestamp:
                raise ValueError("歷史 Kbar session_open_at 不可晚於 timestamp")
            if self.session_date is not None and self.session_open_at.date() != self.session_date:
                raise ValueError("歷史 Kbar session_open_at 與 session_date 不符")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC 必須大於 0")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC 範圍不合法")
        if self.volume < 0:
            raise ValueError("volume 不可小於 0")
        # Optional v3 fields are validated only when present so legacy bars stay
        # constructible; presence itself is enforced per-engine by the policy.
        if self.market_phase is not None:
            try:
                phase = MarketPhase(self.market_phase)
            except ValueError as exc:
                raise ValueError("market_phase 必須是已知的 MarketPhase") from exc
            object.__setattr__(self, "market_phase", phase.value)
        if self.session_regime is not None and not str(self.session_regime).strip():
            raise ValueError("session_regime 不可為空字串")
        for field_name in ("reference_price", "lower_limit_price", "upper_limit_price"):
            value = getattr(self, field_name)
            if value is not None:
                value = decimal(value)
                object.__setattr__(self, field_name, value)
                if value <= 0:
                    raise ValueError(f"{field_name} 必須大於 0")
        if self.lower_limit_price is not None and self.upper_limit_price is not None:
            if self.lower_limit_price > self.upper_limit_price:
                raise ValueError("lower_limit_price 不可高於 upper_limit_price")
            if self.reference_price is not None and not (
                self.lower_limit_price <= self.reference_price <= self.upper_limit_price
            ):
                raise ValueError("reference_price 必須落在漲跌停區間內")

    def to_dict(self) -> dict[str, Any]:
        value = {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "timestamp": self.timestamp.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
            "amount": str(self.amount) if self.amount is not None else None,
        }
        if self.session_date is not None:
            value["session_date"] = self.session_date.isoformat()
        if self.session_open_at is not None:
            value["session_open_at"] = self.session_open_at.isoformat()
        if self.market_phase is not None:
            value["market_phase"] = self.market_phase
        if self.session_regime is not None:
            value["session_regime"] = self.session_regime
        if self.reference_price is not None:
            value["reference_price"] = str(self.reference_price)
        if self.lower_limit_price is not None:
            value["lower_limit_price"] = str(self.lower_limit_price)
        if self.upper_limit_price is not None:
            value["upper_limit_price"] = str(self.upper_limit_price)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HistoricalBar":
        timestamp = datetime.fromisoformat(str(value["timestamp"]))
        return cls(
            symbol=str(value["symbol"]),
            name=str(value.get("name") or ""),
            market=str(value.get("market") or ""),
            timestamp=timestamp,
            open=decimal(value["open"]),
            high=decimal(value["high"]),
            low=decimal(value["low"]),
            close=decimal(value["close"]),
            volume=int(value["volume"]),
            amount=(decimal(value["amount"]) if value.get("amount") is not None else None),
            session_date=(
                date.fromisoformat(str(value["session_date"]))
                if value.get("session_date") is not None
                else None
            ),
            session_open_at=(
                datetime.fromisoformat(str(value["session_open_at"]))
                if value.get("session_open_at") is not None
                else None
            ),
            market_phase=(
                str(value["market_phase"]) if value.get("market_phase") is not None else None
            ),
            session_regime=(
                str(value["session_regime"]) if value.get("session_regime") is not None else None
            ),
            reference_price=(
                decimal(value["reference_price"])
                if value.get("reference_price") is not None
                else None
            ),
            lower_limit_price=(
                decimal(value["lower_limit_price"])
                if value.get("lower_limit_price") is not None
                else None
            ),
            upper_limit_price=(
                decimal(value["upper_limit_price"])
                if value.get("upper_limit_price") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class StrategySetSnapshot:
    """Immutable entry/exit selections and aggregation rules for one run."""

    entry_strategy_ids: tuple[str, ...]
    exit_strategy_ids: tuple[str, ...]
    entry_policy: AggregationPolicy = AggregationPolicy.ANY
    exit_policy: AggregationPolicy = AggregationPolicy.ANY
    entry_min_trigger_count: int = 1
    exit_min_trigger_count: int = 1
    priority_order: tuple[str, ...] = ()
    version: str = "v1"

    def __post_init__(self) -> None:
        entries = tuple(str(item).strip() for item in self.entry_strategy_ids)
        exits = tuple(str(item).strip() for item in self.exit_strategy_ids)
        priority = tuple(str(item).strip() for item in self.priority_order)
        object.__setattr__(self, "entry_strategy_ids", entries)
        object.__setattr__(self, "exit_strategy_ids", exits)
        object.__setattr__(self, "priority_order", priority)
        if not entries or any(not item for item in entries):
            raise ValueError("至少要選擇一個買入策略")
        if not exits or any(not item for item in exits):
            raise ValueError("至少要選擇一個賣出策略")
        if len(set(entries)) != len(entries):
            raise ValueError("買入策略不可重複選擇")
        if len(set(exits)) != len(exits):
            raise ValueError("賣出策略不可重複選擇")
        if len(set(priority)) != len(priority):
            raise ValueError("策略優先順序不可重複")
        unknown_priority = set(priority) - set(entries) - set(exits)
        if unknown_priority:
            raise ValueError("策略優先順序只能包含本次已選策略")
        self._validate_policy(
            self.entry_policy,
            self.entry_min_trigger_count,
            len(entries),
            "買入",
        )
        self._validate_policy(
            self.exit_policy,
            self.exit_min_trigger_count,
            len(exits),
            "賣出",
        )

    @staticmethod
    def _validate_policy(
        policy: AggregationPolicy,
        minimum: int,
        count: int,
        label: str,
    ) -> None:
        if policy is AggregationPolicy.AT_LEAST_N and not 1 <= minimum <= count:
            raise ValueError(f"{label} AT_LEAST_N 必須介於 1 與已選策略數量")

    @property
    def snapshot_digest(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_strategy_ids": list(self.entry_strategy_ids),
            "exit_strategy_ids": list(self.exit_strategy_ids),
            "entry_policy": self.entry_policy.value,
            "exit_policy": self.exit_policy.value,
            "entry_min_trigger_count": self.entry_min_trigger_count,
            "exit_min_trigger_count": self.exit_min_trigger_count,
            "priority_order": list(self.priority_order),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StrategySetSnapshot":
        return cls(
            entry_strategy_ids=tuple(str(item) for item in value["entry_strategy_ids"]),
            exit_strategy_ids=tuple(str(item) for item in value["exit_strategy_ids"]),
            entry_policy=AggregationPolicy(str(value.get("entry_policy", "ANY"))),
            exit_policy=AggregationPolicy(str(value.get("exit_policy", "ANY"))),
            entry_min_trigger_count=int(value.get("entry_min_trigger_count", 1)),
            exit_min_trigger_count=int(value.get("exit_min_trigger_count", 1)),
            priority_order=tuple(str(item) for item in value.get("priority_order", ())),
            version=str(value.get("version", "v1")),
        )


@dataclass(frozen=True)
class BacktestRunConfig:
    dataset_id: str
    dataset_digest: str
    strategy_set: StrategySetSnapshot
    starting_cash: Decimal = Decimal("10000000")
    position_fraction: Decimal = Decimal("0.10")
    commission_rate: Decimal = Decimal("0.001425")
    sell_tax_rate: Decimal = Decimal("0.003")
    slippage_bps: Decimal = Decimal("5")
    min_lot_shares: int = 1000
    target_win_rate: Decimal = Decimal("0.50")
    minimum_oos_trades: int = 30
    max_drawdown_guardrail: Decimal = Decimal("0.20")
    engine_version: str = "backtest-engine-v2"
    experiment_id: str | None = None
    baseline_run_id: str | None = None
    research_baseline_digest: str | None = None
    parent_run_id: str | None = None
    change_note: str = ""
    atomic_strategy_run_snapshot: Mapping[str, Any] | None = None
    atomic_run_request: Mapping[str, Any] | None = None
    atomic_run_request_digest: str | None = None
    dataset_binding_snapshot: Mapping[str, Any] | None = None
    dataset_amount_contract: Mapping[str, Any] | None = None
    research_control_snapshot: Mapping[str, Any] | None = None
    # --- Immutable v3-tw seam snapshots -------------------------------------
    # Each carries a ``contract_version`` and a verified ``snapshot_digest``.
    # They are absent for legacy engines and mandatory (all three) for
    # ``backtest-engine-v3-tw``. Package B builds/binds ``research_truth_snapshot``
    # but cannot change any of the three field contracts.
    execution_policy_snapshot: Mapping[str, Any] | None = None
    cost_policy_snapshot: Mapping[str, Any] | None = None
    research_truth_snapshot: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "starting_cash",
            "position_fraction",
            "commission_rate",
            "sell_tax_rate",
            "slippage_bps",
            "target_win_rate",
            "max_drawdown_guardrail",
        ):
            object.__setattr__(self, field_name, decimal(getattr(self, field_name)))
        if self.starting_cash <= 0:
            raise ValueError("starting_cash 必須大於 0")
        if not Decimal("0") < self.position_fraction <= Decimal("1"):
            raise ValueError("position_fraction 必須介於 0 與 1")
        if self.min_lot_shares <= 0:
            raise ValueError("min_lot_shares 必須大於 0")
        if self.atomic_strategy_run_snapshot is not None:
            object.__setattr__(
                self,
                "atomic_strategy_run_snapshot",
                dict(self.atomic_strategy_run_snapshot),
            )
        for field_name in (
            "atomic_run_request",
            "dataset_binding_snapshot",
            "dataset_amount_contract",
            "research_control_snapshot",
            "execution_policy_snapshot",
            "cost_policy_snapshot",
            "research_truth_snapshot",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, dict(value))
        # v3 seam snapshots are self-verifying whenever present, and all three
        # are mandatory for the opt-in Taiwan engine. Legacy engines omit them.
        v3_snapshots = {
            "execution_policy_snapshot": self.execution_policy_snapshot,
            "cost_policy_snapshot": self.cost_policy_snapshot,
            "research_truth_snapshot": self.research_truth_snapshot,
        }
        expected_versions = {
            "execution_policy_snapshot": EXECUTION_POLICY_CONTRACT_VERSION,
            "cost_policy_snapshot": COST_POLICY_CONTRACT_VERSION,
            "research_truth_snapshot": RESEARCH_TRUTH_CONTRACT_VERSION,
        }
        for field_name, snapshot in v3_snapshots.items():
            if snapshot is not None:
                verify_contract_snapshot(
                    snapshot,
                    label=field_name,
                    expected_contract_version=expected_versions[field_name],
                )
        if self.engine_version == ENGINE_V3_TW:
            missing = sorted(name for name, snap in v3_snapshots.items() if snap is None)
            if missing:
                raise ValueError(
                    "backtest-engine-v3-tw 需要三個 seam snapshots，缺少：" + ", ".join(missing)
                )
        elif any(snapshot is not None for snapshot in v3_snapshots.values()):
            raise ValueError("v3 seam snapshots 僅可搭配 backtest-engine-v3-tw")
        if self.research_control_snapshot is not None:
            snapshot = dict(self.research_control_snapshot)
            snapshot_digest = str(snapshot.get("snapshot_digest") or "")
            if len(snapshot_digest) != 64 or any(
                character not in "0123456789abcdef" for character in snapshot_digest
            ):
                raise ValueError("research control snapshot digest 必須是 lowercase SHA-256")
            snapshot_body = {
                key: value for key, value in snapshot.items() if key != "snapshot_digest"
            }
            if digest(snapshot_body) != snapshot_digest:
                raise ValueError("research control snapshot digest 與 evidence 不一致")
        if (self.atomic_run_request is None) != (self.atomic_run_request_digest is None):
            raise ValueError("atomic Run request evidence 與 digest 必須同時存在")
        if self.atomic_run_request_digest is not None:
            request_digest = str(self.atomic_run_request_digest)
            if len(request_digest) != 64 or any(
                character not in "0123456789abcdef" for character in request_digest
            ):
                raise ValueError("atomic_run_request_digest 必須是 lowercase SHA-256")
            if self.atomic_run_request is None or digest(self.atomic_run_request) != request_digest:
                raise ValueError("atomic Run request digest 與 request evidence 不一致")
        if self.dataset_binding_snapshot is not None:
            binding = dict(self.dataset_binding_snapshot)
            if (
                binding.get("dataset_id") != self.dataset_id
                or binding.get("dataset_digest") != self.dataset_digest
            ):
                raise ValueError("Dataset binding snapshot 與 Run Dataset identity 不一致")
            if self.atomic_run_request is not None and self.baseline_run_id is None:
                if (
                    self.atomic_run_request.get("expected_binding_revision")
                    != binding.get("revision")
                    or self.atomic_run_request.get("expected_dataset_digest") != self.dataset_digest
                ):
                    raise ValueError("Atomic Run binding precondition evidence 不一致")

    @property
    def config_digest(self) -> str:
        return digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = {
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "strategy_set": self.strategy_set.to_dict(),
            "starting_cash": str(self.starting_cash),
            "position_fraction": str(self.position_fraction),
            "commission_rate": str(self.commission_rate),
            "sell_tax_rate": str(self.sell_tax_rate),
            "slippage_bps": str(self.slippage_bps),
            "min_lot_shares": self.min_lot_shares,
            "target_win_rate": str(self.target_win_rate),
            "minimum_oos_trades": self.minimum_oos_trades,
            "max_drawdown_guardrail": str(self.max_drawdown_guardrail),
            "engine_version": self.engine_version,
            "experiment_id": self.experiment_id,
            "baseline_run_id": self.baseline_run_id,
            "parent_run_id": self.parent_run_id,
            "change_note": self.change_note,
        }
        if self.research_baseline_digest is not None:
            value["research_baseline_digest"] = self.research_baseline_digest
        if self.atomic_strategy_run_snapshot is not None:
            value["atomic_strategy_run_snapshot"] = dict(self.atomic_strategy_run_snapshot)
        if self.atomic_run_request is not None:
            value["atomic_run_request"] = dict(self.atomic_run_request)
        if self.atomic_run_request_digest is not None:
            value["atomic_run_request_digest"] = self.atomic_run_request_digest
        if self.dataset_binding_snapshot is not None:
            value["dataset_binding_snapshot"] = dict(self.dataset_binding_snapshot)
        if self.dataset_amount_contract is not None:
            value["dataset_amount_contract"] = dict(self.dataset_amount_contract)
        if self.research_control_snapshot is not None:
            value["research_control_snapshot"] = dict(self.research_control_snapshot)
        if self.execution_policy_snapshot is not None:
            value["execution_policy_snapshot"] = dict(self.execution_policy_snapshot)
        if self.cost_policy_snapshot is not None:
            value["cost_policy_snapshot"] = dict(self.cost_policy_snapshot)
        if self.research_truth_snapshot is not None:
            value["research_truth_snapshot"] = dict(self.research_truth_snapshot)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BacktestRunConfig":
        return cls(
            dataset_id=str(value["dataset_id"]),
            dataset_digest=str(value["dataset_digest"]),
            strategy_set=StrategySetSnapshot.from_dict(value["strategy_set"]),
            starting_cash=decimal(value.get("starting_cash", "10000000")),
            position_fraction=decimal(value.get("position_fraction", "0.10")),
            commission_rate=decimal(value.get("commission_rate", "0.001425")),
            sell_tax_rate=decimal(value.get("sell_tax_rate", "0.003")),
            slippage_bps=decimal(value.get("slippage_bps", "5")),
            min_lot_shares=int(value.get("min_lot_shares", 1000)),
            target_win_rate=decimal(value.get("target_win_rate", "0.50")),
            minimum_oos_trades=int(value.get("minimum_oos_trades", 30)),
            max_drawdown_guardrail=decimal(value.get("max_drawdown_guardrail", "0.20")),
            engine_version=str(value.get("engine_version", "backtest-engine-v1")),
            experiment_id=value.get("experiment_id"),
            baseline_run_id=value.get("baseline_run_id"),
            research_baseline_digest=value.get("research_baseline_digest"),
            parent_run_id=value.get("parent_run_id"),
            change_note=str(value.get("change_note", "")),
            atomic_strategy_run_snapshot=(
                dict(value["atomic_strategy_run_snapshot"])
                if value.get("atomic_strategy_run_snapshot") is not None
                else None
            ),
            atomic_run_request=(
                dict(value["atomic_run_request"])
                if value.get("atomic_run_request") is not None
                else None
            ),
            atomic_run_request_digest=(
                str(value["atomic_run_request_digest"])
                if value.get("atomic_run_request_digest") is not None
                else None
            ),
            dataset_binding_snapshot=(
                dict(value["dataset_binding_snapshot"])
                if value.get("dataset_binding_snapshot") is not None
                else None
            ),
            dataset_amount_contract=(
                dict(value["dataset_amount_contract"])
                if value.get("dataset_amount_contract") is not None
                else None
            ),
            research_control_snapshot=(
                dict(value["research_control_snapshot"])
                if value.get("research_control_snapshot") is not None
                else None
            ),
            execution_policy_snapshot=(
                dict(value["execution_policy_snapshot"])
                if value.get("execution_policy_snapshot") is not None
                else None
            ),
            cost_policy_snapshot=(
                dict(value["cost_policy_snapshot"])
                if value.get("cost_policy_snapshot") is not None
                else None
            ),
            research_truth_snapshot=(
                dict(value["research_truth_snapshot"])
                if value.get("research_truth_snapshot") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class StrategyEvaluation:
    strategy_id: str
    strategy_name: str
    strategy_version: str
    side: StrategySide
    status: EvaluationStatus
    symbol: str
    event_at: datetime
    reason: str
    observed: Mapping[str, Any] = field(default_factory=dict)
    threshold: Mapping[str, Any] = field(default_factory=dict)
    execution_horizon: ExecutionHorizon | None = None
    strategy_version_id: str | None = None

    @property
    def member_id(self) -> str:
        return self.strategy_version_id or self.strategy_id

    def to_dict(self) -> dict[str, Any]:
        value = {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "side": self.side.value,
            "status": self.status.value,
            "symbol": self.symbol,
            "event_at": self.event_at.isoformat(),
            "reason": self.reason,
            "observed": dict(self.observed),
            "threshold": dict(self.threshold),
        }
        if self.execution_horizon is not None:
            value["execution_horizon"] = self.execution_horizon.value
        if self.strategy_version_id is not None:
            value["strategy_version_id"] = self.strategy_version_id
        return value


@dataclass(frozen=True)
class TradeDecision:
    decision_id: str
    symbol: str
    side: StrategySide
    event_at: datetime
    policy: AggregationPolicy
    triggered_strategy_ids: tuple[str, ...]
    primary_strategy_id: str
    evaluations: tuple[StrategyEvaluation, ...]
    execution_horizon: ExecutionHorizon | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "event_at": self.event_at.isoformat(),
            "policy": self.policy.value,
            "triggered_strategy_ids": list(self.triggered_strategy_ids),
            "primary_strategy_id": self.primary_strategy_id,
            "evaluations": [evaluation.to_dict() for evaluation in self.evaluations],
        }
        if self.execution_horizon is not None:
            value["execution_horizon"] = self.execution_horizon.value
        return value


@dataclass(frozen=True)
class HistoricalFill:
    fill_id: str
    decision_id: str
    symbol: str
    side: StrategySide
    filled_at: datetime
    price: Decimal
    shares: int
    commission: Decimal
    tax: Decimal
    source: str
    # Formal-v3 execution/accounting evidence. Legacy fills leave every field
    # unset, so their serialized bytes remain unchanged.
    requested_shares: int | None = None
    residual_shares: int | None = None
    pre_cost_price: Decimal | None = None
    slippage: Decimal | None = None
    execution_policy_contract_version: str | None = None
    execution_policy_snapshot_digest: str | None = None
    cost_policy_contract_version: str | None = None
    cost_policy_snapshot_digest: str | None = None

    def __post_init__(self) -> None:
        if self.shares < 0:
            raise ValueError("filled shares 不可小於 0")
        if self.requested_shares is not None:
            if self.requested_shares <= 0 or self.shares <= 0:
                raise ValueError("formal fill 的 requested/filled shares 必須大於 0")
            if self.requested_shares < self.shares:
                raise ValueError("requested shares 不可小於 filled shares")
            expected_residual = self.requested_shares - self.shares
            if self.residual_shares != expected_residual:
                raise ValueError("residual shares 必須等於 requested - filled")
            required_formal_fields = {
                "pre_cost_price": self.pre_cost_price,
                "slippage": self.slippage,
                "execution_policy_contract_version": self.execution_policy_contract_version,
                "execution_policy_snapshot_digest": self.execution_policy_snapshot_digest,
                "cost_policy_contract_version": self.cost_policy_contract_version,
                "cost_policy_snapshot_digest": self.cost_policy_snapshot_digest,
            }
            missing = sorted(
                name for name, value in required_formal_fields.items() if value is None
            )
            if missing:
                raise ValueError(f"formal fill 缺少欄位：{','.join(missing)}")
            if self.execution_policy_contract_version != EXECUTION_POLICY_CONTRACT_VERSION:
                raise ValueError("formal fill execution policy contract_version 未知")
            if self.cost_policy_contract_version != COST_POLICY_CONTRACT_VERSION:
                raise ValueError("formal fill cost policy contract_version 未知")
            for label, value in (
                ("execution policy", self.execution_policy_snapshot_digest),
                ("cost policy", self.cost_policy_snapshot_digest),
            ):
                if not isinstance(value, str) or not is_sha256_hex(value):
                    raise ValueError(f"formal fill {label} digest 必須是 lowercase SHA-256")
        elif self.residual_shares is not None:
            raise ValueError("residual shares 需要 requested shares")
        if self.pre_cost_price is not None:
            object.__setattr__(self, "pre_cost_price", decimal(self.pre_cost_price))
        if self.slippage is not None:
            parsed_slippage = decimal(self.slippage)
            if parsed_slippage < 0:
                raise ValueError("slippage 不可小於 0")
            object.__setattr__(self, "slippage", parsed_slippage)

    @property
    def total_cost(self) -> Decimal:
        return self.commission + self.tax

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "fill_id": self.fill_id,
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "filled_at": self.filled_at.isoformat(),
            "price": float(self.price),
            "shares": self.shares,
            "commission": float(self.commission),
            "tax": float(self.tax),
            "total_cost": float(self.total_cost),
            "source": self.source,
        }
        if self.requested_shares is not None:
            value.update(
                {
                    "requested_shares": self.requested_shares,
                    "filled_shares": self.shares,
                    "residual_shares": self.residual_shares,
                    "pre_cost_price": str(self.pre_cost_price),
                    "post_cost_price": str(self.price),
                    "cost_breakdown": {
                        "commission": str(self.commission),
                        "tax": str(self.tax),
                        "slippage": str(self.slippage),
                        "total": str(self.commission + self.tax + (self.slippage or Decimal("0"))),
                    },
                    "policy_identity": {
                        "execution_contract_version": (self.execution_policy_contract_version),
                        "execution_snapshot_digest": (self.execution_policy_snapshot_digest),
                        "cost_contract_version": self.cost_policy_contract_version,
                        "cost_snapshot_digest": self.cost_policy_snapshot_digest,
                    },
                }
            )
        return value


@dataclass(frozen=True)
class ClosedTrade:
    trade_id: str
    symbol: str
    name: str
    entry_decision: TradeDecision
    exit_decision: TradeDecision
    entry_fill: HistoricalFill
    exit_fill: HistoricalFill
    gross_pnl: Decimal
    net_pnl: Decimal
    holding_minutes: int

    def to_dict(self) -> dict[str, Any]:
        entry_evaluations = [
            value.to_dict()
            for value in self.entry_decision.evaluations
            if value.status is EvaluationStatus.TRIGGERED
        ]
        exit_evaluations = [
            value.to_dict()
            for value in self.exit_decision.evaluations
            if value.status is EvaluationStatus.TRIGGERED
        ]
        entry_cost = self.entry_fill.price * self.entry_fill.shares + self.entry_fill.total_cost
        value: dict[str, Any] = {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "name": self.name,
            "entry": self.entry_fill.to_dict(),
            "exit": self.exit_fill.to_dict(),
            "gross_pnl": float(self.gross_pnl),
            "net_pnl": float(self.net_pnl),
            "net_pnl_pct": float(self.net_pnl / entry_cost * Decimal("100")) if entry_cost else 0.0,
            "holding_minutes": self.holding_minutes,
            "entry_decision": self.entry_decision.to_dict(),
            "exit_decision": self.exit_decision.to_dict(),
            "entry_strategies": entry_evaluations,
            "exit_strategies": exit_evaluations,
        }
        if self.entry_fill.requested_shares is not None:
            entry_slippage = self.entry_fill.slippage or Decimal("0")
            exit_slippage = self.exit_fill.slippage or Decimal("0")
            value["formal_execution"] = {
                "requested_shares": self.entry_fill.requested_shares,
                "filled_shares": self.entry_fill.shares,
                "residual_shares": self.exit_fill.residual_shares,
                "pre_cost_entry_price": str(self.entry_fill.pre_cost_price),
                "post_cost_entry_price": str(self.entry_fill.price),
                "pre_cost_exit_price": str(self.exit_fill.pre_cost_price),
                "post_cost_exit_price": str(self.exit_fill.price),
                "cost_breakdown": {
                    "commission": str(self.entry_fill.commission + self.exit_fill.commission),
                    "tax": str(self.entry_fill.tax + self.exit_fill.tax),
                    "slippage": str(entry_slippage + exit_slippage),
                    "total": str(
                        self.entry_fill.commission
                        + self.exit_fill.commission
                        + self.entry_fill.tax
                        + self.exit_fill.tax
                        + entry_slippage
                        + exit_slippage
                    ),
                },
                "policy_identity": self.entry_fill.to_dict()["policy_identity"],
            }
        return value


def lot_floor(shares: Decimal, lot_size: int) -> int:
    return int((shares / lot_size).to_integral_value(rounding=ROUND_DOWN) * lot_size)
