"""Pure contracts for R5 revision-2 signal-ledger research replay.

This module has no repository, HTTP, provider, broker, or filesystem artifact
dependency.  It builds exact canonical rows and deterministic one-lot episode
economics from verified baseline decisions and ordered immutable bars.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo

from backtest.domain import HistoricalBar, canonical_json, digest


CONTROL_CONTRACT_VERSION = "r5-signal-ledger-replay-v2"
LEDGER_ROW_SCHEMA_VERSION = "r5-signal-ledger-row-v2"
ORDER_ROW_SCHEMA_VERSION = "r5-order-derivation-row-v2"
MATCH_ROW_SCHEMA_VERSION = "r5-match-plan-row-v2"
MODELED_ENTRY_SCHEMA_VERSION = "r5-modeled-entry-row-v2"
MODELED_EXIT_SCHEMA_VERSION = "r5-modeled-exit-row-v2"
EPISODE_SCHEMA_VERSION = "r5-replay-episode-row-v2"
SUMMARY_SCHEMA_VERSION = "r5-replay-summary-v2"
LEDGER_MANIFEST_SCHEMA_VERSION = "r5-signal-ledger-manifest-v2"
MATCH_MANIFEST_SCHEMA_VERSION = "r5-match-plan-manifest-v2"
RESULT_MANIFEST_SCHEMA_VERSION = "r5-signal-ledger-replay-result-v2"
POSTFLIGHT_SCHEMA_VERSION = "r5-signal-ledger-replay-postflight-v2"

_TAIPEI = ZoneInfo("Asia/Taipei")
_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
_RETURN_QUANTUM = Decimal("0.000000000000000001")
_SHA256_CHARS = frozenset("0123456789abcdef")

ALGORITHM_CONTRACT_PROJECTION: dict[str, Any] = {
    "calculation_precision": 38,
    "calculation_rounding": "ROUND_HALF_EVEN",
    "canonical_json": "BACKTEST_CANONICAL_JSON_V1",
    "contract_version": CONTROL_CONTRACT_VERSION,
    "entry_semantics": "NEXT_OBSERVED_SYMBOL_KBAR_OPEN_STRICTLY_AFTER_SIGNAL_V1",
    "exit_semantics": "FIRST_LATER_OBSERVED_SYMBOL_SESSION_CLOSE_V1",
    "name": "independent-one-lot-next-open-to-session-close-v2",
    "return_scale": 18,
    "shares_semantics": "EXACT_BASELINE_MIN_LOT_SHARES_V1",
    "timezone": "Asia/Taipei",
}
ALGORITHM_CONTRACT_DIGEST = digest(ALGORITHM_CONTRACT_PROJECTION)


class ResearchReplayIntegrityError(ValueError):
    """Frozen R5 revision-2 evidence is incomplete or non-canonical."""


def algorithm_implementation_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def require_sha256(value: object, label: str) -> str:
    resolved = str(value or "")
    if len(resolved) != 64 or any(char not in _SHA256_CHARS for char in resolved):
        raise ResearchReplayIntegrityError(f"{label} 必須是 lowercase SHA-256")
    return resolved


def require_exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ResearchReplayIntegrityError(
            f"{label} schema 不一致：missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _require_nfc(value: object, label: str) -> None:
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise ResearchReplayIntegrityError(f"{label} 必須是 Unicode NFC")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _require_nfc(key, f"{label}.key")
            _require_nfc(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_nfc(item, f"{label}[{index}]")


def canonical_object_bytes(value: Mapping[str, Any]) -> bytes:
    _require_nfc(value, "canonical object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchReplayIntegrityError(f"{label} 必須是 non-empty string")
    _require_nfc(value, label)
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ResearchReplayIntegrityError(f"{label} 必須是 integer >= {minimum}")
    return value


def canonical_timestamp(value: datetime | str, label: str) -> str:
    try:
        resolved = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ResearchReplayIntegrityError(f"{label} 不是有效 timestamp") from error
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ResearchReplayIntegrityError(f"{label} 必須包含 timezone")
    resolved = resolved.astimezone(_TAIPEI)
    if resolved.microsecond:
        raise ResearchReplayIntegrityError(f"{label} 不可包含 microseconds")
    return resolved.isoformat(timespec="seconds")


def require_canonical_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ResearchReplayIntegrityError(f"{label} 必須是 canonical timestamp string")
    resolved = canonical_timestamp(value, label)
    if resolved != value:
        raise ResearchReplayIntegrityError(f"{label} timestamp alias 不被接受")
    return resolved


def require_canonical_date(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ResearchReplayIntegrityError(f"{label} 必須是 canonical date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ResearchReplayIntegrityError(f"{label} 不是有效日期") from error
    if parsed.isoformat() != value:
        raise ResearchReplayIntegrityError(f"{label} 日期格式不 canonical")
    return value


def decimal_text(
    value: Decimal | str | int,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> str:
    if isinstance(value, bool) or isinstance(value, float):
        raise ResearchReplayIntegrityError(f"{label} 不接受 bool 或 binary float")
    try:
        resolved = value if isinstance(value, Decimal) else Decimal(str(value))
    except (DecimalException, ValueError) as error:
        raise ResearchReplayIntegrityError(f"{label} 不是有效 Decimal") from error
    if not resolved.is_finite():
        raise ResearchReplayIntegrityError(f"{label} 必須是 finite Decimal")
    if positive and resolved <= 0:
        raise ResearchReplayIntegrityError(f"{label} 必須大於 0")
    if nonnegative and resolved < 0:
        raise ResearchReplayIntegrityError(f"{label} 不可小於 0")
    if resolved == 0:
        return "0"
    rendered = format(resolved, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def require_decimal_text(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
    maximum_scale: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise ResearchReplayIntegrityError(f"{label} 必須是 Decimal string")
    rendered = decimal_text(value, label, positive=positive, nonnegative=nonnegative)
    if rendered != value:
        raise ResearchReplayIntegrityError(f"{label} Decimal bytes 不 canonical")
    if maximum_scale is not None:
        scale = len(value.partition(".")[2])
        if scale > maximum_scale:
            raise ResearchReplayIntegrityError(f"{label} scale 不可超過 {maximum_scale}")
    return value


def _quantized_text(value: Decimal, label: str) -> str:
    try:
        with localcontext(_CONTEXT):
            quantized = value.quantize(_RETURN_QUANTUM, rounding=ROUND_HALF_EVEN)
    except DecimalException as error:
        raise ResearchReplayIntegrityError(f"{label} 無法量化至 scale 18") from error
    return decimal_text(quantized, label)


def _rows_payload(
    rows: Iterable[Mapping[str, Any]], verifier: Any
) -> tuple[tuple[dict[str, Any], ...], bytes]:
    verified = tuple(verifier(row) for row in rows)
    ordered = tuple(sorted(verified, key=lambda item: int(item["sequence"])))
    seen_signals: set[str] = set()
    for expected, row in enumerate(ordered, start=1):
        if row["sequence"] != expected:
            raise ResearchReplayIntegrityError("row sequence 必須從 1 連續且 unique")
        if row["signal_id"] in seen_signals:
            raise ResearchReplayIntegrityError("row signal_id 必須 unique")
        seen_signals.add(row["signal_id"])
    payload = b"".join(canonical_object_bytes(row) for row in ordered)
    return ordered, payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


_LEDGER_FIELDS = frozenset(
    {
        "authoritative_decision_digest",
        "baseline_decision_id",
        "baseline_run_id",
        "execution_horizon",
        "policy",
        "primary_strategy_id",
        "schema_version",
        "semantic_key",
        "sequence",
        "side",
        "signal_id",
        "signal_at",
        "signal_session_date",
        "symbol",
        "triggered_strategy_ids",
    }
)
_ORDER_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "signal_id",
        "semantic_key",
        "baseline_run_id",
        "baseline_decision_id",
        "baseline_order_id",
        "symbol",
        "signal_at",
        "side",
        "execution_horizon",
        "primary_strategy_id",
        "triggered_strategy_ids",
    }
)
_MATCH_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "match_id",
        "signal_id",
        "semantic_key",
        "symbol",
        "signal_at",
        "signal_session_date",
        "entry_bar_at",
        "entry_session_date",
        "entry_raw_open",
        "entry_bar_digest",
        "exit_bar_at",
        "exit_session_date",
        "exit_raw_close",
        "exit_bar_digest",
        "holding_minutes",
        "cross_session_entry",
        "entry_on_session_close",
        "cross_session_exit",
    }
)
_MODELED_COMMON_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "episode_id",
        "match_id",
        "signal_id",
        "semantic_key",
        "symbol",
        "filled_at",
        "session_date",
        "source",
        "raw_price",
        "fill_price",
        "shares",
        "gross",
        "commission",
        "tax",
        "total_cost",
    }
)
_EPISODE_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "episode_id",
        "signal_id",
        "semantic_key",
        "match_id",
        "modeled_entry_id",
        "modeled_exit_id",
        "symbol",
        "signal_at",
        "signal_session_date",
        "entry_at",
        "entry_session_date",
        "exit_at",
        "exit_session_date",
        "holding_minutes",
        "shares",
        "raw_entry_open",
        "raw_exit_close",
        "pre_slippage_price_pnl",
        "post_slippage_gross_pnl",
        "explicit_costs",
        "net_pnl",
        "pre_slippage_return",
        "net_return_on_raw_entry_notional",
        "outcome",
    }
)


def verify_ledger_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _LEDGER_FIELDS, "Signal Ledger row")
    if row["schema_version"] != LEDGER_ROW_SCHEMA_VERSION or row["side"] != "ENTRY":
        raise ResearchReplayIntegrityError("Signal Ledger schema/side 不支援")
    _integer(row["sequence"], "ledger sequence", minimum=1)
    for field in ("authoritative_decision_digest", "signal_id", "semantic_key"):
        require_sha256(row[field], field)
    for field in (
        "baseline_decision_id",
        "baseline_run_id",
        "policy",
        "primary_strategy_id",
        "symbol",
    ):
        _nonempty_string(row[field], field)
    if row["execution_horizon"] != "INTRADAY_NEXT_BAR":
        raise ResearchReplayIntegrityError("ledger execution_horizon 不支援")
    signal_at = require_canonical_timestamp(row["signal_at"], "signal_at")
    session_date = require_canonical_date(row["signal_session_date"], "signal_session_date")
    if datetime.fromisoformat(signal_at).date().isoformat() != session_date:
        raise ResearchReplayIntegrityError("signal timestamp/session date 不一致")
    if not isinstance(row["triggered_strategy_ids"], list) or not row[
        "triggered_strategy_ids"
    ]:
        raise ResearchReplayIntegrityError("triggered_strategy_ids 必須是 non-empty array")
    for item in row["triggered_strategy_ids"]:
        _nonempty_string(item, "triggered_strategy_id")
    expected_signal = digest(
        {
            "baseline_decision_id": row["baseline_decision_id"],
            "baseline_run_id": row["baseline_run_id"],
        }
    )
    expected_semantic = digest(
        {
            "execution_horizon": row["execution_horizon"],
            "policy": row["policy"],
            "primary_strategy_id": row["primary_strategy_id"],
            "signal_at": row["signal_at"],
            "symbol": row["symbol"],
            "triggered_strategy_ids": row["triggered_strategy_ids"],
        }
    )
    if row["signal_id"] != expected_signal or row["semantic_key"] != expected_semantic:
        raise ResearchReplayIntegrityError("Signal Ledger identity 無法重建")
    canonical_object_bytes(row)
    return row


@dataclass(frozen=True)
class LedgerBuild:
    rows: tuple[dict[str, Any], ...]
    authoritative_rows: tuple[dict[str, Any], ...]
    decision_projection_digest: str
    semantic_multiplicity_digest: str
    rows_sha256: str


def build_ledger(
    *, baseline_run_id: str, decisions: Iterable[Mapping[str, Any]]
) -> LedgerBuild:
    run_id = _nonempty_string(baseline_run_id, "baseline_run_id")
    authoritative: list[dict[str, Any]] = []
    sortable: list[tuple[str, str, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for source in decisions:
        decision = dict(source)
        if decision.get("side") != "ENTRY":
            continue
        decision_id = _nonempty_string(decision.get("decision_id"), "decision_id")
        if decision_id in seen:
            raise ResearchReplayIntegrityError("authoritative decision_id 不可重複")
        seen.add(decision_id)
        symbol = _nonempty_string(decision.get("symbol"), "decision symbol")
        signal_at = canonical_timestamp(decision.get("event_at"), "decision event_at")
        policy = _nonempty_string(decision.get("policy"), "decision policy")
        primary = _nonempty_string(
            decision.get("primary_strategy_id"), "primary_strategy_id"
        )
        triggered_raw = decision.get("triggered_strategy_ids")
        if not isinstance(triggered_raw, (list, tuple)) or not triggered_raw:
            raise ResearchReplayIntegrityError("decision triggered_strategy_ids 不完整")
        triggered = [_nonempty_string(item, "triggered_strategy_id") for item in triggered_raw]
        horizon = (
            "INTRADAY_NEXT_BAR"
            if "execution_horizon" not in decision
            or decision["execution_horizon"] is None
            else decision["execution_horizon"]
        )
        if horizon != "INTRADAY_NEXT_BAR":
            raise ResearchReplayIntegrityError("只支援 INTRADAY_NEXT_BAR ENTRY decision")
        authoritative_digest = digest(decision)
        authoritative.append(
            {
                "authoritative_decision_digest": authoritative_digest,
                "baseline_decision_id": decision_id,
            }
        )
        sortable.append(
            (
                signal_at,
                symbol,
                decision_id,
                {
                    "authoritative_decision_digest": authoritative_digest,
                    "baseline_decision_id": decision_id,
                    "baseline_run_id": run_id,
                    "execution_horizon": horizon,
                    "policy": policy,
                    "primary_strategy_id": primary,
                    "schema_version": LEDGER_ROW_SCHEMA_VERSION,
                    "side": "ENTRY",
                    "signal_at": signal_at,
                    "signal_session_date": datetime.fromisoformat(signal_at).date().isoformat(),
                    "symbol": symbol,
                    "triggered_strategy_ids": triggered,
                },
            )
        )
    if not sortable:
        raise ResearchReplayIntegrityError("baseline 沒有 authoritative ENTRY decisions")
    rows: list[dict[str, Any]] = []
    for sequence, (_, _, _, body) in enumerate(sorted(sortable), start=1):
        signal_id = digest(
            {
                "baseline_decision_id": body["baseline_decision_id"],
                "baseline_run_id": run_id,
            }
        )
        semantic_key = digest(
            {
                "execution_horizon": body["execution_horizon"],
                "policy": body["policy"],
                "primary_strategy_id": body["primary_strategy_id"],
                "signal_at": body["signal_at"],
                "symbol": body["symbol"],
                "triggered_strategy_ids": body["triggered_strategy_ids"],
            }
        )
        rows.append(
            verify_ledger_row(
                {
                    **body,
                    "semantic_key": semantic_key,
                    "sequence": sequence,
                    "signal_id": signal_id,
                }
            )
        )
    _, payload = _rows_payload(rows, verify_ledger_row)
    counts = Counter(row["semantic_key"] for row in rows)
    return LedgerBuild(
        rows=tuple(rows),
        authoritative_rows=tuple(authoritative),
        decision_projection_digest=digest(
            {
                "entries": authoritative,
                "schema_version": "r5-entry-decision-projection-v2",
            }
        ),
        semantic_multiplicity_digest=digest(
            {
                "schema_version": "r5-signal-multiplicity-v2",
                "tokens": dict(sorted(counts.items())),
            }
        ),
        rows_sha256=_sha256_bytes(payload),
    )


def verify_order_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _ORDER_FIELDS, "order derivation row")
    if row["schema_version"] != ORDER_ROW_SCHEMA_VERSION or row["side"] != "ENTRY":
        raise ResearchReplayIntegrityError("order derivation schema/side 不支援")
    _integer(row["sequence"], "order sequence", minimum=1)
    for field in ("signal_id", "semantic_key"):
        require_sha256(row[field], field)
    for field in (
        "baseline_run_id",
        "baseline_decision_id",
        "baseline_order_id",
        "symbol",
        "primary_strategy_id",
    ):
        _nonempty_string(row[field], field)
    require_canonical_timestamp(row["signal_at"], "order signal_at")
    if row["execution_horizon"] != "INTRADAY_NEXT_BAR":
        raise ResearchReplayIntegrityError("order execution horizon 不支援")
    if not isinstance(row["triggered_strategy_ids"], list) or not row[
        "triggered_strategy_ids"
    ]:
        raise ResearchReplayIntegrityError("order triggered_strategy_ids 不完整")
    for item in row["triggered_strategy_ids"]:
        _nonempty_string(item, "order triggered_strategy_id")
    canonical_object_bytes(row)
    return row


@dataclass(frozen=True)
class OrderDerivationBuild:
    rows: tuple[dict[str, Any], ...]
    rows_sha256: str
    projection_digest: str


def build_order_derivation(
    *, ledger_rows: Iterable[Mapping[str, Any]], orders: Iterable[Mapping[str, Any]]
) -> OrderDerivationBuild:
    ledger, _ = _rows_payload(ledger_rows, verify_ledger_row)
    by_decision = {row["baseline_decision_id"]: row for row in ledger}
    order_by_decision: dict[str, dict[str, Any]] = {}
    seen_order_ids: set[str] = set()
    for source in orders:
        order = dict(source)
        if order.get("side") != "ENTRY":
            continue
        decision_id = _nonempty_string(order.get("decision_id"), "order decision_id")
        order_id = _nonempty_string(order.get("order_id"), "order_id")
        if decision_id in order_by_decision or order_id in seen_order_ids:
            raise ResearchReplayIntegrityError("ENTRY order derivation 不可重複")
        order_by_decision[decision_id] = order
        seen_order_ids.add(order_id)
    if set(order_by_decision) != set(by_decision):
        raise ResearchReplayIntegrityError("decision/order derivation 必須一對一雙向完整")
    rows: list[dict[str, Any]] = []
    for ledger_row in ledger:
        order = order_by_decision[ledger_row["baseline_decision_id"]]
        horizon = (
            "INTRADAY_NEXT_BAR"
            if "execution_horizon" not in order
            or order["execution_horizon"] is None
            else order["execution_horizon"]
        )
        triggered = list(order.get("triggered_strategy_ids") or ())
        candidate = {
            "schema_version": ORDER_ROW_SCHEMA_VERSION,
            "sequence": ledger_row["sequence"],
            "signal_id": ledger_row["signal_id"],
            "semantic_key": ledger_row["semantic_key"],
            "baseline_run_id": ledger_row["baseline_run_id"],
            "baseline_decision_id": ledger_row["baseline_decision_id"],
            "baseline_order_id": order["order_id"],
            "symbol": _nonempty_string(order.get("symbol"), "order symbol"),
            "signal_at": canonical_timestamp(order.get("created_at"), "order created_at"),
            "side": "ENTRY",
            "execution_horizon": horizon,
            "primary_strategy_id": _nonempty_string(
                order.get("primary_strategy_id"), "order primary_strategy_id"
            ),
            "triggered_strategy_ids": triggered,
        }
        for field in (
            "symbol",
            "signal_at",
            "execution_horizon",
            "primary_strategy_id",
            "triggered_strategy_ids",
        ):
            if candidate[field] != ledger_row[field]:
                raise ResearchReplayIntegrityError(f"decision/order {field} 不一致")
        rows.append(verify_order_row(candidate))
    ordered, payload = _rows_payload(rows, verify_order_row)
    projection = {
        "row_count": len(ordered),
        "rows_sha256": _sha256_bytes(payload),
        "schema_version": "r5-order-derivation-projection-v2",
    }
    return OrderDerivationBuild(
        rows=ordered,
        rows_sha256=projection["rows_sha256"],
        projection_digest=digest(projection),
    )


@dataclass(frozen=True)
class ObservedBar:
    bar: HistoricalBar
    source_json: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.bar, HistoricalBar):
            raise ResearchReplayIntegrityError("ObservedBar 必須持有 HistoricalBar")
        if not self.source_json or b"\n" in self.source_json or b"\r" in self.source_json:
            raise ResearchReplayIntegrityError("source bar bytes 不可為空或包含換行")
        try:
            parsed = json.loads(self.source_json)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResearchReplayIntegrityError("source bar bytes 不是 JSON") from error
        _require_nfc(parsed, "source bar")
        if not isinstance(parsed, Mapping) or canonical_json(parsed).encode("utf-8") != self.source_json:
            raise ResearchReplayIntegrityError("source bar bytes 必須是 canonical JSON object")
        try:
            source_bar = HistoricalBar.from_dict(parsed)
        except (KeyError, TypeError, ValueError, DecimalException) as error:
            raise ResearchReplayIntegrityError("source bar 無法解析為 HistoricalBar") from error
        if canonical_json(source_bar.to_dict()).encode("utf-8") != self.source_json:
            raise ResearchReplayIntegrityError("source bar 必須是 exact HistoricalBar projection")
        if canonical_json(self.bar.to_dict()).encode("utf-8") != self.source_json:
            raise ResearchReplayIntegrityError(
                "source bar 與 matcher HistoricalBar 不一致"
            )

    @classmethod
    def from_historical_bar(
        cls, bar: HistoricalBar, *, source_json: bytes
    ) -> "ObservedBar":
        return cls(bar=bar, source_json=source_json)

    @property
    def symbol(self) -> str:
        return self.bar.symbol

    @property
    def timestamp(self) -> datetime:
        return self.bar.timestamp

    @property
    def session_date(self) -> date:
        return self.bar.session_date or self.bar.timestamp.astimezone(_TAIPEI).date()

    @property
    def open(self) -> Decimal:
        return self.bar.open

    @property
    def close(self) -> Decimal:
        return self.bar.close

    @property
    def source_digest(self) -> str:
        return _sha256_bytes(self.source_json)


def verify_match_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _MATCH_FIELDS, "match-plan row")
    if row["schema_version"] != MATCH_ROW_SCHEMA_VERSION:
        raise ResearchReplayIntegrityError("match-plan schema version 不支援")
    _integer(row["sequence"], "match sequence", minimum=1)
    _integer(row["holding_minutes"], "holding_minutes")
    for field in (
        "match_id",
        "signal_id",
        "semantic_key",
        "entry_bar_digest",
        "exit_bar_digest",
    ):
        require_sha256(row[field], field)
    for field in ("symbol",):
        _nonempty_string(row[field], field)
    signal_at = require_canonical_timestamp(row["signal_at"], "match signal_at")
    entry_at = require_canonical_timestamp(row["entry_bar_at"], "entry_bar_at")
    exit_at = require_canonical_timestamp(row["exit_bar_at"], "exit_bar_at")
    for field in ("signal_session_date", "entry_session_date", "exit_session_date"):
        require_canonical_date(row[field], field)
    if not datetime.fromisoformat(signal_at) < datetime.fromisoformat(entry_at) < datetime.fromisoformat(exit_at):
        raise ResearchReplayIntegrityError("match timestamps 必須 signal < entry < exit")
    if (
        datetime.fromisoformat(signal_at).date().isoformat()
        != row["signal_session_date"]
        or datetime.fromisoformat(entry_at).date().isoformat()
        != row["entry_session_date"]
        or datetime.fromisoformat(exit_at).date().isoformat()
        != row["exit_session_date"]
    ):
        raise ResearchReplayIntegrityError("match timestamp/session date 不一致")
    expected_holding = int(
        (datetime.fromisoformat(exit_at) - datetime.fromisoformat(entry_at)).total_seconds()
        // 60
    )
    if row["holding_minutes"] != expected_holding:
        raise ResearchReplayIntegrityError("match holding_minutes 無法重建")
    require_decimal_text(row["entry_raw_open"], "entry_raw_open", positive=True)
    require_decimal_text(row["exit_raw_close"], "exit_raw_close", positive=True)
    for field in ("cross_session_entry", "entry_on_session_close", "cross_session_exit"):
        if not isinstance(row[field], bool):
            raise ResearchReplayIntegrityError(f"{field} 必須是 boolean")
    if row["cross_session_entry"] != (
        row["entry_session_date"] != row["signal_session_date"]
    ) or row["cross_session_exit"] != (
        row["exit_session_date"] != row["entry_session_date"]
    ):
        raise ResearchReplayIntegrityError("match cross-session evidence 無法重建")
    expected_match_id = digest(
        {
            "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
            "entry_bar_digest": row["entry_bar_digest"],
            "exit_bar_digest": row["exit_bar_digest"],
            "signal_id": row["signal_id"],
        }
    )
    if row["match_id"] != expected_match_id:
        raise ResearchReplayIntegrityError("match_id 無法重建")
    canonical_object_bytes(row)
    return row


@dataclass(frozen=True)
class MatchPlanBuild:
    rows: tuple[dict[str, Any], ...]
    signal_count: int
    missing_entry_count: int
    missing_exit_count: int
    duplicate_match_count: int
    rows_sha256: str
    signal_multiplicity_digest: str


@dataclass
class _PendingEntry:
    signal: dict[str, Any]
    entry: ObservedBar
    entry_on_session_close: bool = False


@dataclass
class MatchPlanStreamState:
    """Mutable evidence populated only after the one-pass stream is exhausted."""

    signal_count: int = 0
    missing_entry_count: int = 0
    missing_exit_count: int = 0
    max_waiting_count: int = 0
    max_pending_count: int = 0
    complete: bool = False


def _match_row(pending: _PendingEntry, exit_bar: ObservedBar) -> dict[str, Any]:
    signal = pending.signal
    match_id = digest(
        {
            "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
            "entry_bar_digest": pending.entry.source_digest,
            "exit_bar_digest": exit_bar.source_digest,
            "signal_id": signal["signal_id"],
        }
    )
    entry_at = canonical_timestamp(pending.entry.timestamp, "entry timestamp")
    exit_at = canonical_timestamp(exit_bar.timestamp, "exit timestamp")
    holding = int(
        (datetime.fromisoformat(exit_at) - datetime.fromisoformat(entry_at)).total_seconds()
        // 60
    )
    return verify_match_row(
        {
            "schema_version": MATCH_ROW_SCHEMA_VERSION,
            "sequence": signal["sequence"],
            "match_id": match_id,
            "signal_id": signal["signal_id"],
            "semantic_key": signal["semantic_key"],
            "symbol": signal["symbol"],
            "signal_at": signal["signal_at"],
            "signal_session_date": signal["signal_session_date"],
            "entry_bar_at": entry_at,
            "entry_session_date": pending.entry.session_date.isoformat(),
            "entry_raw_open": decimal_text(pending.entry.open, "entry open", positive=True),
            "entry_bar_digest": pending.entry.source_digest,
            "exit_bar_at": exit_at,
            "exit_session_date": exit_bar.session_date.isoformat(),
            "exit_raw_close": decimal_text(exit_bar.close, "exit close", positive=True),
            "exit_bar_digest": exit_bar.source_digest,
            "holding_minutes": holding,
            "cross_session_entry": (
                pending.entry.session_date.isoformat() != signal["signal_session_date"]
            ),
            "entry_on_session_close": pending.entry_on_session_close,
            "cross_session_exit": exit_bar.session_date != pending.entry.session_date,
        }
    )


def iter_match_plan_rows(
    *,
    ledger_rows: Iterable[Mapping[str, Any]],
    bars: Iterable[ObservedBar],
    state: MatchPlanStreamState,
) -> Iterator[dict[str, Any]]:
    """Match an ordered ledger against bars without retaining historical Kbars/results."""

    if state.complete or any(
        (
            state.signal_count,
            state.missing_entry_count,
            state.missing_exit_count,
            state.max_waiting_count,
            state.max_pending_count,
        )
    ):
        raise ResearchReplayIntegrityError("match stream state 必須是全新 instance")
    ledger = iter(ledger_rows)
    expected_sequence = 1
    previous_ledger_key: tuple[str, str, str] | None = None

    def pull_signal() -> dict[str, Any] | None:
        nonlocal expected_sequence, previous_ledger_key
        try:
            row = verify_ledger_row(next(ledger))
        except StopIteration:
            return None
        if row["sequence"] != expected_sequence:
            raise ResearchReplayIntegrityError("ledger stream sequence 必須從 1 連續")
        key = (row["signal_at"], row["symbol"], row["baseline_decision_id"])
        if previous_ledger_key is not None and key <= previous_ledger_key:
            raise ResearchReplayIntegrityError("ledger stream 不符合 canonical order")
        previous_ledger_key = key
        expected_sequence += 1
        state.signal_count += 1
        return row

    next_signal = pull_signal()
    waiting: dict[str, list[dict[str, Any]]] = {}
    previous: dict[str, ObservedBar] = {}
    pending: dict[str, list[_PendingEntry]] = {}
    previous_global: tuple[datetime, str] | None = None

    def close_session(symbol: str, close_bar: ObservedBar) -> list[dict[str, Any]]:
        remaining: list[_PendingEntry] = []
        completed: list[dict[str, Any]] = []
        for item in pending.get(symbol, ()):
            if item.entry.timestamp == close_bar.timestamp:
                item.entry_on_session_close = True
                remaining.append(item)
            elif item.entry.timestamp < close_bar.timestamp:
                completed.append(_match_row(item, close_bar))
            else:
                raise ResearchReplayIntegrityError("pending entry 晚於 session close")
        pending[symbol] = remaining
        return completed

    for bar in bars:
        key = (bar.timestamp, bar.symbol)
        if previous_global is not None and key <= previous_global:
            raise ResearchReplayIntegrityError("Dataset bars 必須依 timestamp/symbol unique 排序")
        previous_global = key
        while next_signal is not None and datetime.fromisoformat(
            next_signal["signal_at"]
        ) < bar.timestamp:
            waiting.setdefault(next_signal["symbol"], []).append(next_signal)
            next_signal = pull_signal()
        state.max_waiting_count = max(
            state.max_waiting_count, sum(len(rows) for rows in waiting.values())
        )
        prior = previous.get(bar.symbol)
        if prior is not None and prior.session_date != bar.session_date:
            yield from close_session(bar.symbol, prior)
        incoming = waiting.pop(bar.symbol, ())
        if incoming:
            pending.setdefault(bar.symbol, []).extend(
                _PendingEntry(signal=signal, entry=bar) for signal in incoming
            )
        if pending.get(bar.symbol):
            previous[bar.symbol] = bar
        else:
            previous.pop(bar.symbol, None)
        state.max_pending_count = max(
            state.max_pending_count, sum(len(rows) for rows in pending.values())
        )

    while next_signal is not None:
        waiting.setdefault(next_signal["symbol"], []).append(next_signal)
        next_signal = pull_signal()
    state.max_waiting_count = max(
        state.max_waiting_count, sum(len(rows) for rows in waiting.values())
    )
    for symbol, close_bar in previous.items():
        yield from close_session(symbol, close_bar)
    state.missing_entry_count = sum(len(rows) for rows in waiting.values())
    state.missing_exit_count = sum(len(values) for values in pending.values())
    state.complete = True


def build_match_plan(
    *, ledger_rows: Iterable[Mapping[str, Any]], bars: Iterable[ObservedBar]
) -> MatchPlanBuild:
    state = MatchPlanStreamState()
    matches = tuple(
        iter_match_plan_rows(ledger_rows=ledger_rows, bars=bars, state=state)
    )
    if not state.complete:
        raise ResearchReplayIntegrityError("match stream 未完整消耗")
    ordered, payload = _rows_payload(matches, verify_match_row) if matches else ((), b"")
    match_counts = Counter(row["match_id"] for row in ordered)
    return MatchPlanBuild(
        rows=ordered,
        signal_count=state.signal_count,
        missing_entry_count=state.missing_entry_count,
        missing_exit_count=state.missing_exit_count,
        duplicate_match_count=sum(max(value - 1, 0) for value in match_counts.values()),
        rows_sha256=_sha256_bytes(payload),
        signal_multiplicity_digest=layer_multiplicity_digest(ordered),
    )


def _verify_modeled_row(value: Mapping[str, Any], *, side: str) -> dict[str, Any]:
    row = dict(value)
    id_field = "modeled_entry_id" if side == "ENTRY" else "modeled_exit_id"
    expected = _MODELED_COMMON_FIELDS | frozenset({id_field})
    require_exact_fields(row, expected, f"modeled {side.lower()} row")
    expected_schema = MODELED_ENTRY_SCHEMA_VERSION if side == "ENTRY" else MODELED_EXIT_SCHEMA_VERSION
    expected_source = (
        "NEXT_OBSERVED_SYMBOL_KBAR_OPEN"
        if side == "ENTRY"
        else "FIRST_LATER_SYMBOL_SESSION_CLOSE"
    )
    if row["schema_version"] != expected_schema or row["source"] != expected_source:
        raise ResearchReplayIntegrityError(f"modeled {side} schema/source 不支援")
    _integer(row["sequence"], f"modeled {side} sequence", minimum=1)
    _integer(row["shares"], f"modeled {side} shares", minimum=1)
    for field in (id_field, "episode_id", "match_id", "signal_id", "semantic_key"):
        require_sha256(row[field], field)
    _nonempty_string(row["symbol"], "modeled symbol")
    require_canonical_timestamp(row["filled_at"], "modeled filled_at")
    require_canonical_date(row["session_date"], "modeled session_date")
    for field in ("raw_price", "fill_price", "gross"):
        require_decimal_text(row[field], field, positive=True)
    for field in ("commission", "tax", "total_cost"):
        require_decimal_text(row[field], field, nonnegative=True)
    if side == "ENTRY" and row["tax"] != "0":
        raise ResearchReplayIntegrityError("modeled ENTRY tax 必須為 0")
    if datetime.fromisoformat(row["filled_at"]).date().isoformat() != row["session_date"]:
        raise ResearchReplayIntegrityError(f"modeled {side} timestamp/session date 不一致")
    expected_id = digest({"episode_id": row["episode_id"], "side": side})
    if row[id_field] != expected_id:
        raise ResearchReplayIntegrityError(f"modeled {side} id 無法重建")
    try:
        with localcontext(_CONTEXT):
            expected_gross = Decimal(row["fill_price"]) * Decimal(row["shares"])
            expected_total_cost = Decimal(row["commission"]) + Decimal(row["tax"])
    except DecimalException as error:
        raise ResearchReplayIntegrityError(f"modeled {side} Decimal 計算失敗") from error
    if row["gross"] != decimal_text(expected_gross, f"modeled {side} gross"):
        raise ResearchReplayIntegrityError(f"modeled {side} gross 無法重建")
    if row["total_cost"] != decimal_text(
        expected_total_cost, f"modeled {side} total_cost", nonnegative=True
    ):
        raise ResearchReplayIntegrityError(f"modeled {side} total_cost 無法重建")
    canonical_object_bytes(row)
    return row


def verify_modeled_entry_row(value: Mapping[str, Any]) -> dict[str, Any]:
    return _verify_modeled_row(value, side="ENTRY")


def verify_modeled_exit_row(value: Mapping[str, Any]) -> dict[str, Any]:
    return _verify_modeled_row(value, side="EXIT")


def verify_episode_row(value: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(value)
    require_exact_fields(row, _EPISODE_FIELDS, "Replay Episode row")
    if row["schema_version"] != EPISODE_SCHEMA_VERSION or row["outcome"] not in {
        "WIN",
        "LOSS",
        "TIE",
    }:
        raise ResearchReplayIntegrityError("episode schema/outcome 不支援")
    _integer(row["sequence"], "episode sequence", minimum=1)
    _integer(row["holding_minutes"], "episode holding_minutes")
    _integer(row["shares"], "episode shares", minimum=1)
    for field in (
        "episode_id",
        "signal_id",
        "semantic_key",
        "match_id",
        "modeled_entry_id",
        "modeled_exit_id",
    ):
        require_sha256(row[field], field)
    _nonempty_string(row["symbol"], "episode symbol")
    for field in ("signal_at", "entry_at", "exit_at"):
        require_canonical_timestamp(row[field], field)
    for field in ("signal_session_date", "entry_session_date", "exit_session_date"):
        require_canonical_date(row[field], field)
    for field in ("raw_entry_open", "raw_exit_close"):
        require_decimal_text(row[field], field, positive=True)
    require_decimal_text(row["explicit_costs"], "explicit_costs", nonnegative=True)
    for field in (
        "pre_slippage_price_pnl",
        "post_slippage_gross_pnl",
        "net_pnl",
    ):
        require_decimal_text(row[field], field)
    for field in ("pre_slippage_return", "net_return_on_raw_entry_notional"):
        require_decimal_text(row[field], field, maximum_scale=18)
    signal_at = datetime.fromisoformat(row["signal_at"])
    entry_at = datetime.fromisoformat(row["entry_at"])
    exit_at = datetime.fromisoformat(row["exit_at"])
    if not signal_at < entry_at < exit_at:
        raise ResearchReplayIntegrityError("episode timestamps 必須 signal < entry < exit")
    if (
        signal_at.date().isoformat() != row["signal_session_date"]
        or entry_at.date().isoformat() != row["entry_session_date"]
        or exit_at.date().isoformat() != row["exit_session_date"]
    ):
        raise ResearchReplayIntegrityError("episode timestamp/session date 不一致")
    expected_holding = int((exit_at - entry_at).total_seconds() // 60)
    if row["holding_minutes"] != expected_holding:
        raise ResearchReplayIntegrityError("episode holding_minutes 無法重建")
    expected_episode_id = digest(
        {
            "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
            "signal_id": row["signal_id"],
        }
    )
    if row["episode_id"] != expected_episode_id:
        raise ResearchReplayIntegrityError("episode_id 無法重建")
    if row["modeled_entry_id"] != digest(
        {"episode_id": row["episode_id"], "side": "ENTRY"}
    ) or row["modeled_exit_id"] != digest(
        {"episode_id": row["episode_id"], "side": "EXIT"}
    ):
        raise ResearchReplayIntegrityError("episode modeled row identity 無法重建")
    net_pnl = Decimal(row["net_pnl"])
    expected_outcome = "WIN" if net_pnl > 0 else "LOSS" if net_pnl < 0 else "TIE"
    if row["outcome"] != expected_outcome:
        raise ResearchReplayIntegrityError("episode outcome 無法重建")
    canonical_object_bytes(row)
    return row


@dataclass(frozen=True)
class ReplayBuild:
    episodes: tuple[dict[str, Any], ...]
    modeled_entries: tuple[dict[str, Any], ...]
    modeled_exits: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    episode_rows_sha256: str
    modeled_entry_rows_sha256: str
    modeled_exit_rows_sha256: str
    cost_identity: dict[str, Any]
    cost_identity_digest: str


def _summary(episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not episodes:
        raise ResearchReplayIntegrityError("空 replay 不可建立 result")
    try:
        with localcontext(_CONTEXT):
            pre = [Decimal(str(row["pre_slippage_price_pnl"])) for row in episodes]
            gross = [Decimal(str(row["post_slippage_gross_pnl"])) for row in episodes]
            costs = [Decimal(str(row["explicit_costs"])) for row in episodes]
            net = [Decimal(str(row["net_pnl"])) for row in episodes]
            pre_returns = [Decimal(str(row["pre_slippage_return"])) for row in episodes]
            net_returns = [
                Decimal(str(row["net_return_on_raw_entry_notional"])) for row in episodes
            ]
            count = Decimal(len(episodes))

            def median(values: list[Decimal]) -> Decimal:
                ordered = sorted(values)
                middle = len(ordered) // 2
                return ordered[middle] if len(ordered) % 2 else (
                    ordered[middle - 1] + ordered[middle]
                ) / Decimal(2)

            gains = sum((value for value in net if value > 0), Decimal(0))
            losses_abs = abs(sum((value for value in net if value < 0), Decimal(0)))
            if losses_abs > 0:
                pf_state = "FINITE"
                pf_value: str | None = _quantized_text(gains / losses_abs, "profit_factor")
            elif gains > 0:
                pf_state = "POSITIVE_INFINITY"
                pf_value = None
            else:
                pf_state = "UNDEFINED"
                pf_value = None
            result = {
                "schema_version": SUMMARY_SCHEMA_VERSION,
                "episode_count": len(episodes),
                "win_count": sum(row["outcome"] == "WIN" for row in episodes),
                "loss_count": sum(row["outcome"] == "LOSS" for row in episodes),
                "tie_count": sum(row["outcome"] == "TIE" for row in episodes),
                "sum_pre_slippage_price_pnl": decimal_text(sum(pre, Decimal(0)), "sum pre"),
                "sum_post_slippage_gross_pnl": decimal_text(sum(gross, Decimal(0)), "sum gross"),
                "sum_explicit_costs": decimal_text(sum(costs, Decimal(0)), "sum costs"),
                "sum_net_pnl": decimal_text(sum(net, Decimal(0)), "sum net"),
                "mean_pre_slippage_return": _quantized_text(sum(pre_returns, Decimal(0)) / count, "mean pre return"),
                "mean_net_return": _quantized_text(sum(net_returns, Decimal(0)) / count, "mean net return"),
                "median_pre_slippage_return": _quantized_text(median(pre_returns), "median pre return"),
                "median_net_return": _quantized_text(median(net_returns), "median net return"),
                "profit_factor_state": pf_state,
                "profit_factor": pf_value,
            }
    except DecimalException as error:
        raise ResearchReplayIntegrityError("Replay summary Decimal 計算失敗") from error
    verify_summary(result)
    return result


_SUMMARY_FIELDS = frozenset(
    {
        "schema_version",
        "episode_count",
        "win_count",
        "loss_count",
        "tie_count",
        "sum_pre_slippage_price_pnl",
        "sum_post_slippage_gross_pnl",
        "sum_explicit_costs",
        "sum_net_pnl",
        "mean_pre_slippage_return",
        "mean_net_return",
        "median_pre_slippage_return",
        "median_net_return",
        "profit_factor_state",
        "profit_factor",
    }
)


def verify_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(value)
    require_exact_fields(summary, _SUMMARY_FIELDS, "Replay summary")
    if summary["schema_version"] != SUMMARY_SCHEMA_VERSION:
        raise ResearchReplayIntegrityError("summary schema version 不支援")
    for field in ("episode_count", "win_count", "loss_count", "tie_count"):
        _integer(summary[field], field)
    if summary["episode_count"] < 1 or (
        summary["win_count"] + summary["loss_count"] + summary["tie_count"]
        != summary["episode_count"]
    ):
        raise ResearchReplayIntegrityError("summary outcome counts 不一致")
    for field in (
        "sum_pre_slippage_price_pnl",
        "sum_post_slippage_gross_pnl",
        "sum_net_pnl",
    ):
        require_decimal_text(summary[field], field)
    require_decimal_text(summary["sum_explicit_costs"], "sum_explicit_costs", nonnegative=True)
    for field in (
        "mean_pre_slippage_return",
        "mean_net_return",
        "median_pre_slippage_return",
        "median_net_return",
    ):
        require_decimal_text(summary[field], field, maximum_scale=18)
    state = summary["profit_factor_state"]
    if state == "FINITE":
        require_decimal_text(summary["profit_factor"], "profit_factor", nonnegative=True, maximum_scale=18)
    elif state in {"POSITIVE_INFINITY", "UNDEFINED"}:
        if summary["profit_factor"] is not None:
            raise ResearchReplayIntegrityError("non-finite profit factor value 必須是 null")
    else:
        raise ResearchReplayIntegrityError("profit_factor_state 不支援")
    canonical_object_bytes(summary)
    return summary


def build_replay(
    *,
    match_rows: Iterable[Mapping[str, Any]],
    min_lot_shares: int,
    slippage_bps: Decimal | str | int,
    commission_rate: Decimal | str | int,
    sell_tax_rate: Decimal | str | int,
) -> ReplayBuild:
    matches, _ = _rows_payload(match_rows, verify_match_row)
    replay_cost_identity = cost_identity(
        min_lot_shares=min_lot_shares,
        slippage_bps=slippage_bps,
        commission_rate=commission_rate,
        sell_tax_rate=sell_tax_rate,
    )
    shares = replay_cost_identity["min_lot_shares"]
    slippage_bps_text = replay_cost_identity["slippage_bps"]
    commission_text = replay_cost_identity["commission_rate"]
    sell_tax_text = replay_cost_identity["sell_tax_rate"]
    episodes: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    try:
        with localcontext(_CONTEXT):
            slippage = Decimal(slippage_bps_text) / Decimal(10000)
            commission_rate_value = Decimal(commission_text)
            sell_tax_rate_value = Decimal(sell_tax_text)
            for match in matches:
                raw_entry = Decimal(match["entry_raw_open"])
                raw_exit = Decimal(match["exit_raw_close"])
                entry_fill = raw_entry * (Decimal(1) + slippage)
                exit_fill = raw_exit * (Decimal(1) - slippage)
                if exit_fill <= 0:
                    raise ResearchReplayIntegrityError("slippage 後 exit fill price 必須大於 0")
                entry_gross = entry_fill * Decimal(shares)
                exit_gross = exit_fill * Decimal(shares)
                entry_commission = entry_gross * commission_rate_value
                exit_commission = exit_gross * commission_rate_value
                sell_tax = exit_gross * sell_tax_rate_value
                pre_pnl = (raw_exit - raw_entry) * Decimal(shares)
                gross_pnl = (exit_fill - entry_fill) * Decimal(shares)
                explicit_costs = entry_commission + exit_commission + sell_tax
                net_pnl = gross_pnl - explicit_costs
                pre_return = raw_exit / raw_entry - Decimal(1)
                net_return = net_pnl / (raw_entry * Decimal(shares))
                episode_id = digest(
                    {
                        "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
                        "signal_id": match["signal_id"],
                    }
                )
                entry_id = digest({"episode_id": episode_id, "side": "ENTRY"})
                exit_id = digest({"episode_id": episode_id, "side": "EXIT"})
                entry = verify_modeled_entry_row(
                    {
                        "schema_version": MODELED_ENTRY_SCHEMA_VERSION,
                        "sequence": match["sequence"],
                        "modeled_entry_id": entry_id,
                        "episode_id": episode_id,
                        "match_id": match["match_id"],
                        "signal_id": match["signal_id"],
                        "semantic_key": match["semantic_key"],
                        "symbol": match["symbol"],
                        "filled_at": match["entry_bar_at"],
                        "session_date": match["entry_session_date"],
                        "source": "NEXT_OBSERVED_SYMBOL_KBAR_OPEN",
                        "raw_price": decimal_text(raw_entry, "entry raw", positive=True),
                        "fill_price": decimal_text(entry_fill, "entry fill", positive=True),
                        "shares": shares,
                        "gross": decimal_text(entry_gross, "entry gross", positive=True),
                        "commission": decimal_text(entry_commission, "entry commission", nonnegative=True),
                        "tax": "0",
                        "total_cost": decimal_text(entry_commission, "entry total cost", nonnegative=True),
                    }
                )
                exit_row = verify_modeled_exit_row(
                    {
                        "schema_version": MODELED_EXIT_SCHEMA_VERSION,
                        "sequence": match["sequence"],
                        "modeled_exit_id": exit_id,
                        "episode_id": episode_id,
                        "match_id": match["match_id"],
                        "signal_id": match["signal_id"],
                        "semantic_key": match["semantic_key"],
                        "symbol": match["symbol"],
                        "filled_at": match["exit_bar_at"],
                        "session_date": match["exit_session_date"],
                        "source": "FIRST_LATER_SYMBOL_SESSION_CLOSE",
                        "raw_price": decimal_text(raw_exit, "exit raw", positive=True),
                        "fill_price": decimal_text(exit_fill, "exit fill", positive=True),
                        "shares": shares,
                        "gross": decimal_text(exit_gross, "exit gross", positive=True),
                        "commission": decimal_text(exit_commission, "exit commission", nonnegative=True),
                        "tax": decimal_text(sell_tax, "sell tax", nonnegative=True),
                        "total_cost": decimal_text(exit_commission + sell_tax, "exit total cost", nonnegative=True),
                    }
                )
                outcome = "WIN" if net_pnl > 0 else "LOSS" if net_pnl < 0 else "TIE"
                episode = verify_episode_row(
                    {
                        "schema_version": EPISODE_SCHEMA_VERSION,
                        "sequence": match["sequence"],
                        "episode_id": episode_id,
                        "signal_id": match["signal_id"],
                        "semantic_key": match["semantic_key"],
                        "match_id": match["match_id"],
                        "modeled_entry_id": entry_id,
                        "modeled_exit_id": exit_id,
                        "symbol": match["symbol"],
                        "signal_at": match["signal_at"],
                        "signal_session_date": match["signal_session_date"],
                        "entry_at": match["entry_bar_at"],
                        "entry_session_date": match["entry_session_date"],
                        "exit_at": match["exit_bar_at"],
                        "exit_session_date": match["exit_session_date"],
                        "holding_minutes": match["holding_minutes"],
                        "shares": shares,
                        "raw_entry_open": decimal_text(raw_entry, "raw entry", positive=True),
                        "raw_exit_close": decimal_text(raw_exit, "raw exit", positive=True),
                        "pre_slippage_price_pnl": decimal_text(pre_pnl, "pre pnl"),
                        "post_slippage_gross_pnl": decimal_text(gross_pnl, "gross pnl"),
                        "explicit_costs": decimal_text(explicit_costs, "explicit costs", nonnegative=True),
                        "net_pnl": decimal_text(net_pnl, "net pnl"),
                        "pre_slippage_return": _quantized_text(pre_return, "pre return"),
                        "net_return_on_raw_entry_notional": _quantized_text(net_return, "net return"),
                        "outcome": outcome,
                    }
                )
                entries.append(entry)
                exits.append(exit_row)
                episodes.append(episode)
    except DecimalException as error:
        raise ResearchReplayIntegrityError("Episode Decimal 計算失敗") from error
    episode_rows, episode_payload = _rows_payload(episodes, verify_episode_row)
    entry_rows, entry_payload = _rows_payload(entries, verify_modeled_entry_row)
    exit_rows, exit_payload = _rows_payload(exits, verify_modeled_exit_row)
    summary = _summary(episode_rows)
    reconstructed_cost_identity = verify_replay_consistency(
        episode_rows=episode_rows,
        modeled_entry_rows=entry_rows,
        modeled_exit_rows=exit_rows,
        summary=summary,
    )
    if reconstructed_cost_identity != replay_cost_identity:
        raise ResearchReplayIntegrityError("Replay cost identity 無法由 rows 重建")
    return ReplayBuild(
        episodes=episode_rows,
        modeled_entries=entry_rows,
        modeled_exits=exit_rows,
        summary=summary,
        episode_rows_sha256=_sha256_bytes(episode_payload),
        modeled_entry_rows_sha256=_sha256_bytes(entry_payload),
        modeled_exit_rows_sha256=_sha256_bytes(exit_payload),
        cost_identity=replay_cost_identity,
        cost_identity_digest=digest(replay_cost_identity),
    )


def verify_replay_consistency(
    *,
    episode_rows: Iterable[Mapping[str, Any]],
    modeled_entry_rows: Iterable[Mapping[str, Any]],
    modeled_exit_rows: Iterable[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild row lineage, one-lot economics, and summary from artifact rows."""

    episodes, _ = _rows_payload(episode_rows, verify_episode_row)
    entries, _ = _rows_payload(modeled_entry_rows, verify_modeled_entry_row)
    exits, _ = _rows_payload(modeled_exit_rows, verify_modeled_exit_row)
    if not episodes or not (
        len(episodes) == len(entries) == len(exits)
        and compare_layers(episodes, entries).equal
        and compare_layers(episodes, exits).equal
    ):
        raise ResearchReplayIntegrityError("result replay layers 無法一對一重建")
    entries_by_sequence = {row["sequence"]: row for row in entries}
    exits_by_sequence = {row["sequence"]: row for row in exits}
    if len(entries_by_sequence) != len(entries) or len(exits_by_sequence) != len(exits):
        raise ResearchReplayIntegrityError("result replay sequence 重複")
    reconstructed_cost_identity: dict[str, Any] | None = None
    try:
        with localcontext(_CONTEXT):
            for episode in episodes:
                entry = entries_by_sequence.get(episode["sequence"])
                exit_row = exits_by_sequence.get(episode["sequence"])
                if entry is None or exit_row is None:
                    raise ResearchReplayIntegrityError("result replay sequence 無對應 row")
                common = (
                    "episode_id",
                    "match_id",
                    "signal_id",
                    "semantic_key",
                    "symbol",
                    "shares",
                )
                if any(
                    entry[field] != episode[field] or exit_row[field] != episode[field]
                    for field in common
                ):
                    raise ResearchReplayIntegrityError("result replay lineage 無法重建")
                if (
                    entry["modeled_entry_id"] != episode["modeled_entry_id"]
                    or exit_row["modeled_exit_id"] != episode["modeled_exit_id"]
                    or entry["filled_at"] != episode["entry_at"]
                    or exit_row["filled_at"] != episode["exit_at"]
                    or entry["session_date"] != episode["entry_session_date"]
                    or exit_row["session_date"] != episode["exit_session_date"]
                    or entry["raw_price"] != episode["raw_entry_open"]
                    or exit_row["raw_price"] != episode["raw_exit_close"]
                ):
                    raise ResearchReplayIntegrityError("result replay row references 無法重建")

                shares = Decimal(episode["shares"])
                raw_entry = Decimal(episode["raw_entry_open"])
                raw_exit = Decimal(episode["raw_exit_close"])
                entry_fill = Decimal(entry["fill_price"])
                exit_fill = Decimal(exit_row["fill_price"])
                pre_pnl = (raw_exit - raw_entry) * shares
                gross_pnl = (exit_fill - entry_fill) * shares
                costs = Decimal(entry["total_cost"]) + Decimal(exit_row["total_cost"])
                net_pnl = gross_pnl - costs
                pre_return = raw_exit / raw_entry - Decimal(1)
                net_return = net_pnl / (raw_entry * shares)
                entry_slippage_bps = (entry_fill / raw_entry - Decimal(1)) * Decimal(
                    10000
                )
                exit_slippage_bps = (Decimal(1) - exit_fill / raw_exit) * Decimal(
                    10000
                )
                entry_commission_rate = Decimal(entry["commission"]) / Decimal(
                    entry["gross"]
                )
                exit_commission_rate = Decimal(exit_row["commission"]) / Decimal(
                    exit_row["gross"]
                )
                sell_tax_rate = Decimal(exit_row["tax"]) / Decimal(exit_row["gross"])
                if (
                    entry_slippage_bps != exit_slippage_bps
                    or entry_commission_rate != exit_commission_rate
                ):
                    raise ResearchReplayIntegrityError(
                        "result replay cost rates 無法一致重建"
                    )
                row_cost_identity = cost_identity(
                    min_lot_shares=episode["shares"],
                    slippage_bps=entry_slippage_bps,
                    commission_rate=entry_commission_rate,
                    sell_tax_rate=sell_tax_rate,
                )
                if reconstructed_cost_identity is None:
                    reconstructed_cost_identity = row_cost_identity
                elif reconstructed_cost_identity != row_cost_identity:
                    raise ResearchReplayIntegrityError(
                        "result replay cost identity 在 episodes 間不一致"
                    )
                expected = {
                    "pre_slippage_price_pnl": decimal_text(pre_pnl, "pre pnl"),
                    "post_slippage_gross_pnl": decimal_text(gross_pnl, "gross pnl"),
                    "explicit_costs": decimal_text(costs, "explicit costs", nonnegative=True),
                    "net_pnl": decimal_text(net_pnl, "net pnl"),
                    "pre_slippage_return": _quantized_text(pre_return, "pre return"),
                    "net_return_on_raw_entry_notional": _quantized_text(
                        net_return, "net return"
                    ),
                }
                if any(episode[field] != value for field, value in expected.items()):
                    raise ResearchReplayIntegrityError("result replay economic formula 無法重建")
    except DecimalException as error:
        raise ResearchReplayIntegrityError("result replay Decimal 計算失敗") from error
    verified_summary = verify_summary(summary)
    if verified_summary != _summary(episodes):
        raise ResearchReplayIntegrityError("result replay summary 無法由 episodes 重建")
    if reconstructed_cost_identity is None:
        raise ResearchReplayIntegrityError("result replay 無法重建 cost identity")
    return reconstructed_cost_identity


def layer_multiplicity_projection(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for source in rows:
        token = {
            "semantic_key": require_sha256(source.get("semantic_key"), "semantic_key"),
            "sequence": _integer(source.get("sequence"), "sequence", minimum=1),
            "signal_id": require_sha256(source.get("signal_id"), "signal_id"),
        }
        counts[canonical_json(token)] += 1
    return {
        "schema_version": "r5-layer-parity-projection-v2",
        "tokens": dict(sorted(counts.items())),
    }


def layer_multiplicity_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    return digest(layer_multiplicity_projection(rows))


@dataclass(frozen=True)
class LayerDifference:
    left_minus_right_count: int
    right_minus_left_count: int
    left_digest: str
    right_digest: str

    @property
    def equal(self) -> bool:
        return self.left_minus_right_count == self.right_minus_left_count == 0


def compare_layers(
    left: Iterable[Mapping[str, Any]], right: Iterable[Mapping[str, Any]]
) -> LayerDifference:
    left_projection = layer_multiplicity_projection(left)
    right_projection = layer_multiplicity_projection(right)
    left_counts = Counter(left_projection["tokens"])
    right_counts = Counter(right_projection["tokens"])
    return LayerDifference(
        left_minus_right_count=sum((left_counts - right_counts).values()),
        right_minus_left_count=sum((right_counts - left_counts).values()),
        left_digest=digest(left_projection),
        right_digest=digest(right_projection),
    )


_LEDGER_IDENTITY_FIELDS = frozenset(
    {
        "baseline_run_id",
        "baseline_config_digest",
        "baseline_result_digest",
        "v1_preflight_digest",
        "v1_signal_multiplicity_digest",
        "v1_invalid_postflight_digest",
        "atomic_strategy_run_snapshot_digest",
        "dataset_id",
        "dataset_digest",
        "dataset_manifest_digest",
        "dataset_bars_sha256",
        "dataset_binding_revision",
        "dataset_amount_contract_digest",
    }
)
_LEDGER_MANIFEST_FIELDS = _LEDGER_IDENTITY_FIELDS | frozenset(
    {
        "schema_version",
        "control_contract_version",
        "baseline_entry_decision_count",
        "baseline_entry_decision_projection_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "order_derivation_row_schema_version",
        "v2_inception_order_derivation_count",
        "v2_inception_order_derivation_rows_sha256",
        "v2_inception_order_derivation_digest",
        "ledger_row_schema_version",
        "ledger_signal_count",
        "ledger_rows_sha256",
        "ledger_semantic_multiplicity_digest",
        "ledger_manifest_digest",
    }
)
_MATCH_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "control_contract_version",
        "baseline_run_id",
        "ledger_manifest_digest",
        "ledger_rows_sha256",
        "dataset_id",
        "dataset_digest",
        "dataset_manifest_digest",
        "dataset_bars_sha256",
        "dataset_binding_revision",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "match_row_schema_version",
        "signal_count",
        "matched_entry_count",
        "matched_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_match_count",
        "match_rows_sha256",
        "match_signal_multiplicity_digest",
        "match_plan_manifest_digest",
    }
)
_RESULT_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "control_contract_version",
        "replay_id",
        "baseline_run_id",
        "registration_revision",
        "ledger_manifest_digest",
        "match_plan_manifest_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "cost_identity_digest",
        "episode_row_schema_version",
        "modeled_entry_row_schema_version",
        "modeled_exit_row_schema_version",
        "episode_count",
        "modeled_entry_count",
        "modeled_exit_count",
        "episode_rows_sha256",
        "modeled_entry_rows_sha256",
        "modeled_exit_rows_sha256",
        "episode_signal_multiplicity_digest",
        "modeled_entry_signal_multiplicity_digest",
        "modeled_exit_signal_multiplicity_digest",
        "summary",
        "summary_digest",
        "result_projection_digest",
        "result_manifest_digest",
    }
)


def _verify_identity_sha_fields(value: Mapping[str, Any]) -> None:
    for field in (
        "baseline_config_digest",
        "baseline_result_digest",
        "v1_preflight_digest",
        "v1_signal_multiplicity_digest",
        "v1_invalid_postflight_digest",
        "atomic_strategy_run_snapshot_digest",
        "dataset_digest",
        "dataset_manifest_digest",
        "dataset_bars_sha256",
        "dataset_amount_contract_digest",
    ):
        require_sha256(value[field], field)


def build_ledger_manifest(
    *,
    identity: Mapping[str, Any],
    ledger: LedgerBuild,
    order_derivation: OrderDerivationBuild,
) -> dict[str, Any]:
    canonical_identity = dict(identity)
    require_exact_fields(canonical_identity, _LEDGER_IDENTITY_FIELDS, "ledger identity")
    _nonempty_string(canonical_identity["baseline_run_id"], "baseline_run_id")
    _nonempty_string(canonical_identity["dataset_id"], "dataset_id")
    _integer(canonical_identity["dataset_binding_revision"], "dataset_binding_revision")
    _verify_identity_sha_fields(canonical_identity)
    if len(ledger.rows) != len(order_derivation.rows):
        raise ResearchReplayIntegrityError("ledger/order derivation count 不一致")
    body = {
        "schema_version": LEDGER_MANIFEST_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        **canonical_identity,
        "baseline_entry_decision_count": len(ledger.authoritative_rows),
        "baseline_entry_decision_projection_digest": ledger.decision_projection_digest,
        "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
        "algorithm_implementation_digest": algorithm_implementation_digest(),
        "order_derivation_row_schema_version": ORDER_ROW_SCHEMA_VERSION,
        "v2_inception_order_derivation_count": len(order_derivation.rows),
        "v2_inception_order_derivation_rows_sha256": order_derivation.rows_sha256,
        "v2_inception_order_derivation_digest": order_derivation.projection_digest,
        "ledger_row_schema_version": LEDGER_ROW_SCHEMA_VERSION,
        "ledger_signal_count": len(ledger.rows),
        "ledger_rows_sha256": ledger.rows_sha256,
        "ledger_semantic_multiplicity_digest": ledger.semantic_multiplicity_digest,
    }
    manifest = {**body, "ledger_manifest_digest": digest(body)}
    return verify_ledger_manifest(manifest)


def verify_ledger_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(value)
    require_exact_fields(manifest, _LEDGER_MANIFEST_FIELDS, "ledger manifest")
    if (
        manifest["schema_version"] != LEDGER_MANIFEST_SCHEMA_VERSION
        or manifest["control_contract_version"] != CONTROL_CONTRACT_VERSION
        or manifest["ledger_row_schema_version"] != LEDGER_ROW_SCHEMA_VERSION
        or manifest["order_derivation_row_schema_version"] != ORDER_ROW_SCHEMA_VERSION
    ):
        raise ResearchReplayIntegrityError("ledger manifest schema identity 不支援")
    if manifest["algorithm_contract_digest"] != ALGORITHM_CONTRACT_DIGEST:
        raise ResearchReplayIntegrityError("algorithm contract digest 已漂移")
    if manifest["algorithm_implementation_digest"] != algorithm_implementation_digest():
        raise ResearchReplayIntegrityError("algorithm implementation digest 已漂移")
    _verify_identity_sha_fields(manifest)
    for field in (
        "baseline_entry_decision_projection_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "v2_inception_order_derivation_rows_sha256",
        "v2_inception_order_derivation_digest",
        "ledger_rows_sha256",
        "ledger_semantic_multiplicity_digest",
        "ledger_manifest_digest",
    ):
        require_sha256(manifest[field], field)
    for field in (
        "dataset_binding_revision",
        "baseline_entry_decision_count",
        "v2_inception_order_derivation_count",
        "ledger_signal_count",
    ):
        _integer(manifest[field], field)
    if not (
        manifest["baseline_entry_decision_count"]
        == manifest["v2_inception_order_derivation_count"]
        == manifest["ledger_signal_count"]
    ):
        raise ResearchReplayIntegrityError("ledger manifest counts 不一致")
    body = {key: item for key, item in manifest.items() if key != "ledger_manifest_digest"}
    if digest(body) != manifest["ledger_manifest_digest"]:
        raise ResearchReplayIntegrityError("ledger manifest digest 無法重建")
    canonical_object_bytes(manifest)
    return manifest


def build_match_manifest(
    *, ledger_manifest: Mapping[str, Any], match_plan: MatchPlanBuild
) -> dict[str, Any]:
    ledger = verify_ledger_manifest(ledger_manifest)
    body = {
        "schema_version": MATCH_MANIFEST_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "baseline_run_id": ledger["baseline_run_id"],
        "ledger_manifest_digest": ledger["ledger_manifest_digest"],
        "ledger_rows_sha256": ledger["ledger_rows_sha256"],
        "dataset_id": ledger["dataset_id"],
        "dataset_digest": ledger["dataset_digest"],
        "dataset_manifest_digest": ledger["dataset_manifest_digest"],
        "dataset_bars_sha256": ledger["dataset_bars_sha256"],
        "dataset_binding_revision": ledger["dataset_binding_revision"],
        "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
        "algorithm_implementation_digest": algorithm_implementation_digest(),
        "match_row_schema_version": MATCH_ROW_SCHEMA_VERSION,
        "signal_count": match_plan.signal_count,
        "matched_entry_count": len(match_plan.rows) + match_plan.missing_exit_count,
        "matched_exit_count": len(match_plan.rows),
        "missing_entry_count": match_plan.missing_entry_count,
        "missing_exit_count": match_plan.missing_exit_count,
        "duplicate_match_count": match_plan.duplicate_match_count,
        "match_rows_sha256": match_plan.rows_sha256,
        "match_signal_multiplicity_digest": match_plan.signal_multiplicity_digest,
    }
    manifest = {**body, "match_plan_manifest_digest": digest(body)}
    return verify_match_manifest(manifest)


def verify_match_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(value)
    require_exact_fields(manifest, _MATCH_MANIFEST_FIELDS, "match-plan manifest")
    if (
        manifest["schema_version"] != MATCH_MANIFEST_SCHEMA_VERSION
        or manifest["control_contract_version"] != CONTROL_CONTRACT_VERSION
        or manifest["match_row_schema_version"] != MATCH_ROW_SCHEMA_VERSION
    ):
        raise ResearchReplayIntegrityError("match-plan manifest schema 不支援")
    if (
        manifest["algorithm_contract_digest"] != ALGORITHM_CONTRACT_DIGEST
        or manifest["algorithm_implementation_digest"] != algorithm_implementation_digest()
    ):
        raise ResearchReplayIntegrityError("match-plan algorithm identity 已漂移")
    for field in (
        "ledger_manifest_digest",
        "ledger_rows_sha256",
        "dataset_digest",
        "dataset_manifest_digest",
        "dataset_bars_sha256",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "match_rows_sha256",
        "match_signal_multiplicity_digest",
        "match_plan_manifest_digest",
    ):
        require_sha256(manifest[field], field)
    for field in (
        "dataset_binding_revision",
        "signal_count",
        "matched_entry_count",
        "matched_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_match_count",
    ):
        _integer(manifest[field], field)
    if (
        manifest["signal_count"]
        != manifest["matched_entry_count"] + manifest["missing_entry_count"]
        or manifest["matched_entry_count"]
        != manifest["matched_exit_count"] + manifest["missing_exit_count"]
    ):
        raise ResearchReplayIntegrityError("match-plan manifest count equations 不一致")
    body = {
        key: item for key, item in manifest.items() if key != "match_plan_manifest_digest"
    }
    if digest(body) != manifest["match_plan_manifest_digest"]:
        raise ResearchReplayIntegrityError("match-plan manifest digest 無法重建")
    canonical_object_bytes(manifest)
    return manifest


_COST_IDENTITY_FIELDS = frozenset(
    {"commission_rate", "min_lot_shares", "sell_tax_rate", "slippage_bps"}
)


def verify_cost_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    identity = dict(value)
    require_exact_fields(identity, _COST_IDENTITY_FIELDS, "cost identity")
    _integer(identity["min_lot_shares"], "min_lot_shares", minimum=1)
    for field in ("commission_rate", "sell_tax_rate", "slippage_bps"):
        require_decimal_text(identity[field], field, nonnegative=True)
    canonical_object_bytes(identity)
    return identity


def cost_identity(
    *,
    min_lot_shares: int,
    slippage_bps: Decimal | str | int,
    commission_rate: Decimal | str | int,
    sell_tax_rate: Decimal | str | int,
) -> dict[str, Any]:
    return verify_cost_identity({
        "commission_rate": decimal_text(commission_rate, "commission_rate", nonnegative=True),
        "min_lot_shares": _integer(min_lot_shares, "min_lot_shares", minimum=1),
        "sell_tax_rate": decimal_text(sell_tax_rate, "sell_tax_rate", nonnegative=True),
        "slippage_bps": decimal_text(slippage_bps, "slippage_bps", nonnegative=True),
    })


def build_result_manifest(
    *,
    replay_id: str,
    registration_revision: int,
    ledger_manifest: Mapping[str, Any],
    match_manifest: Mapping[str, Any],
    replay: ReplayBuild,
    min_lot_shares: int,
    slippage_bps: Decimal | str | int,
    commission_rate: Decimal | str | int,
    sell_tax_rate: Decimal | str | int,
) -> dict[str, Any]:
    ledger = verify_ledger_manifest(ledger_manifest)
    match = verify_match_manifest(match_manifest)
    if match["ledger_manifest_digest"] != ledger["ledger_manifest_digest"]:
        raise ResearchReplayIntegrityError("result lineage ledger/match 不一致")
    cost = cost_identity(
        min_lot_shares=min_lot_shares,
        slippage_bps=slippage_bps,
        commission_rate=commission_rate,
        sell_tax_rate=sell_tax_rate,
    )
    replay_cost = verify_cost_identity(replay.cost_identity)
    reconstructed_cost = verify_replay_consistency(
        episode_rows=replay.episodes,
        modeled_entry_rows=replay.modeled_entries,
        modeled_exit_rows=replay.modeled_exits,
        summary=replay.summary,
    )
    if (
        replay_cost != cost
        or reconstructed_cost != replay_cost
        or replay.cost_identity_digest != digest(replay_cost)
        or replay.cost_identity_digest != digest(cost)
    ):
        raise ResearchReplayIntegrityError("ReplayBuild cost identity 不一致")
    summary = verify_summary(replay.summary)
    summary_digest = digest(summary)
    projection = {
        "episode_rows_sha256": replay.episode_rows_sha256,
        "modeled_entry_rows_sha256": replay.modeled_entry_rows_sha256,
        "modeled_exit_rows_sha256": replay.modeled_exit_rows_sha256,
        "summary_digest": summary_digest,
    }
    body = {
        "schema_version": RESULT_MANIFEST_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "replay_id": _nonempty_string(replay_id, "replay_id"),
        "baseline_run_id": ledger["baseline_run_id"],
        "registration_revision": _integer(
            registration_revision, "registration_revision", minimum=1
        ),
        "ledger_manifest_digest": ledger["ledger_manifest_digest"],
        "match_plan_manifest_digest": match["match_plan_manifest_digest"],
        "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
        "algorithm_implementation_digest": algorithm_implementation_digest(),
        "cost_identity_digest": replay.cost_identity_digest,
        "episode_row_schema_version": EPISODE_SCHEMA_VERSION,
        "modeled_entry_row_schema_version": MODELED_ENTRY_SCHEMA_VERSION,
        "modeled_exit_row_schema_version": MODELED_EXIT_SCHEMA_VERSION,
        "episode_count": len(replay.episodes),
        "modeled_entry_count": len(replay.modeled_entries),
        "modeled_exit_count": len(replay.modeled_exits),
        "episode_rows_sha256": replay.episode_rows_sha256,
        "modeled_entry_rows_sha256": replay.modeled_entry_rows_sha256,
        "modeled_exit_rows_sha256": replay.modeled_exit_rows_sha256,
        "episode_signal_multiplicity_digest": layer_multiplicity_digest(replay.episodes),
        "modeled_entry_signal_multiplicity_digest": layer_multiplicity_digest(
            replay.modeled_entries
        ),
        "modeled_exit_signal_multiplicity_digest": layer_multiplicity_digest(
            replay.modeled_exits
        ),
        "summary": summary,
        "summary_digest": summary_digest,
        "result_projection_digest": digest(projection),
    }
    manifest = {**body, "result_manifest_digest": digest(body)}
    return verify_result_manifest(manifest)


def verify_result_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(value)
    require_exact_fields(manifest, _RESULT_MANIFEST_FIELDS, "result manifest")
    if (
        manifest["schema_version"] != RESULT_MANIFEST_SCHEMA_VERSION
        or manifest["control_contract_version"] != CONTROL_CONTRACT_VERSION
        or manifest["episode_row_schema_version"] != EPISODE_SCHEMA_VERSION
        or manifest["modeled_entry_row_schema_version"] != MODELED_ENTRY_SCHEMA_VERSION
        or manifest["modeled_exit_row_schema_version"] != MODELED_EXIT_SCHEMA_VERSION
    ):
        raise ResearchReplayIntegrityError("result manifest schema identity 不支援")
    if (
        manifest["algorithm_contract_digest"] != ALGORITHM_CONTRACT_DIGEST
        or manifest["algorithm_implementation_digest"] != algorithm_implementation_digest()
    ):
        raise ResearchReplayIntegrityError("result algorithm identity 已漂移")
    _nonempty_string(manifest["replay_id"], "replay_id")
    _nonempty_string(manifest["baseline_run_id"], "baseline_run_id")
    for field in (
        "registration_revision",
        "episode_count",
        "modeled_entry_count",
        "modeled_exit_count",
    ):
        _integer(manifest[field], field, minimum=1)
    if not (
        manifest["episode_count"]
        == manifest["modeled_entry_count"]
        == manifest["modeled_exit_count"]
    ):
        raise ResearchReplayIntegrityError("result layer counts 不一致")
    for field in _RESULT_MANIFEST_FIELDS:
        if field.endswith("_digest") or field.endswith("_sha256"):
            require_sha256(manifest[field], field)
    summary = verify_summary(manifest["summary"])
    if digest(summary) != manifest["summary_digest"]:
        raise ResearchReplayIntegrityError("summary digest 無法重建")
    projection = {
        "episode_rows_sha256": manifest["episode_rows_sha256"],
        "modeled_entry_rows_sha256": manifest["modeled_entry_rows_sha256"],
        "modeled_exit_rows_sha256": manifest["modeled_exit_rows_sha256"],
        "summary_digest": manifest["summary_digest"],
    }
    if digest(projection) != manifest["result_projection_digest"]:
        raise ResearchReplayIntegrityError("result projection digest 無法重建")
    body = {key: item for key, item in manifest.items() if key != "result_manifest_digest"}
    if digest(body) != manifest["result_manifest_digest"]:
        raise ResearchReplayIntegrityError("result manifest digest 無法重建")
    canonical_object_bytes(manifest)
    return manifest


_POSTFLIGHT_CONDITION_FIELDS = frozenset(
    {
        "schema_version",
        "baseline_identity_valid",
        "v1_invalid_lineage_valid",
        "order_inception_seal_valid",
        "ledger_artifact_valid",
        "match_plan_artifact_valid",
        "result_artifact_valid",
        "decision_ledger_bidirectional_parity",
        "order_ledger_bidirectional_parity",
        "ledger_match_bidirectional_parity",
        "match_episode_bidirectional_parity",
        "episode_modeled_entry_bidirectional_parity",
        "episode_modeled_exit_bidirectional_parity",
        "all_layer_counts_equal",
        "frozen_signal_count_matches",
        "no_missing_entry_or_exit",
        "no_duplicate_rows",
        "duplicate_match_count_zero",
        "all_shares_exact_min_lot",
        "all_formulas_rebuild",
        "no_strategy_evaluation",
        "no_provider_or_broker_calls",
    }
)
_POSTFLIGHT_DIAGNOSTIC_COUNT_FIELDS = frozenset(
    {
        "authoritative_entry_decision_count",
        "order_derivation_count",
        "ledger_signal_count",
        "match_count",
        "episode_count",
        "modeled_entry_count",
        "modeled_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_decision_count",
        "duplicate_order_derivation_count",
        "duplicate_ledger_count",
        "duplicate_match_count",
        "duplicate_episode_count",
        "duplicate_modeled_entry_count",
        "duplicate_modeled_exit_count",
        "decision_minus_ledger_count",
        "ledger_minus_decision_count",
        "order_minus_ledger_count",
        "ledger_minus_order_count",
        "ledger_minus_match_count",
        "match_minus_ledger_count",
        "match_minus_episode_count",
        "episode_minus_match_count",
        "episode_minus_modeled_entry_count",
        "modeled_entry_minus_episode_count",
        "episode_minus_modeled_exit_count",
        "modeled_exit_minus_episode_count",
        "share_mismatch_count",
        "formula_mismatch_count",
        "strategy_evaluation_count",
        "provider_call_count",
        "broker_call_count",
    }
)
_POSTFLIGHT_DIAGNOSTIC_DIGEST_FIELDS = frozenset(
    {
        "decision_signal_multiplicity_digest",
        "order_signal_multiplicity_digest",
        "ledger_signal_multiplicity_digest",
        "match_signal_multiplicity_digest",
        "episode_signal_multiplicity_digest",
        "modeled_entry_signal_multiplicity_digest",
        "modeled_exit_signal_multiplicity_digest",
    }
)
_POSTFLIGHT_DIAGNOSTIC_FIELDS = (
    frozenset({"schema_version"})
    | _POSTFLIGHT_DIAGNOSTIC_COUNT_FIELDS
    | _POSTFLIGHT_DIAGNOSTIC_DIGEST_FIELDS
)
_POSTFLIGHT_FIELDS = frozenset(
    {
        "schema_version",
        "control_contract_version",
        "replay_id",
        "baseline_run_id",
        "registration_revision",
        "baseline_result_digest",
        "ledger_manifest_digest",
        "match_plan_manifest_digest",
        "result_manifest_digest",
        "identity_validation_digest",
        "conditions",
        "diagnostics",
        "verdict",
        "postflight_digest",
    }
)


def _duplicates(rows: Sequence[Mapping[str, Any]], primary_id: str) -> int:
    counts = Counter(str(row.get(primary_id) or "") for row in rows)
    return sum(max(count - 1, 0) for count in counts.values())


def _formula_difference_count(
    expected: Sequence[Mapping[str, Any]], observed: Sequence[Mapping[str, Any]]
) -> int:
    expected_counts = Counter(canonical_json(dict(row)) for row in expected)
    observed_counts = Counter(canonical_json(dict(row)) for row in observed)
    return sum((expected_counts - observed_counts).values()) + sum(
        (observed_counts - expected_counts).values()
    )


def build_postflight(
    *,
    replay_id: str,
    registration_revision: int,
    baseline_result_digest: str,
    ledger_manifest: Mapping[str, Any],
    match_manifest: Mapping[str, Any],
    result_manifest: Mapping[str, Any],
    decision_rows: Iterable[Mapping[str, Any]],
    order_rows: Iterable[Mapping[str, Any]],
    ledger_rows: Iterable[Mapping[str, Any]],
    match_rows: Iterable[Mapping[str, Any]],
    episode_rows: Iterable[Mapping[str, Any]],
    modeled_entry_rows: Iterable[Mapping[str, Any]],
    modeled_exit_rows: Iterable[Mapping[str, Any]],
    min_lot_shares: int,
    slippage_bps: Decimal | str | int,
    commission_rate: Decimal | str | int,
    sell_tax_rate: Decimal | str | int,
    baseline_identity_valid: bool,
    v1_invalid_lineage_valid: bool,
    order_inception_seal_valid: bool,
    ledger_artifact_valid: bool,
    match_plan_artifact_valid: bool,
    result_artifact_valid: bool,
    v1_signal_multiplicity_valid: bool,
    strategy_evaluation_count: int = 0,
    provider_call_count: int = 0,
    broker_call_count: int = 0,
) -> dict[str, Any]:
    ledger_meta = verify_ledger_manifest(ledger_manifest)
    match_meta = verify_match_manifest(match_manifest)
    result_meta = verify_result_manifest(result_manifest)
    expected_baseline_result_digest = require_sha256(
        baseline_result_digest, "baseline_result_digest"
    )
    postflight_cost_identity = cost_identity(
        min_lot_shares=min_lot_shares,
        slippage_bps=slippage_bps,
        commission_rate=commission_rate,
        sell_tax_rate=sell_tax_rate,
    )
    if (
        match_meta["ledger_manifest_digest"]
        != ledger_meta["ledger_manifest_digest"]
        or result_meta["ledger_manifest_digest"]
        != ledger_meta["ledger_manifest_digest"]
        or result_meta["match_plan_manifest_digest"]
        != match_meta["match_plan_manifest_digest"]
        or result_meta["replay_id"] != replay_id
        or result_meta["baseline_run_id"] != ledger_meta["baseline_run_id"]
        or result_meta["registration_revision"] != registration_revision
        or ledger_meta["baseline_result_digest"] != expected_baseline_result_digest
        or result_meta["cost_identity_digest"] != digest(postflight_cost_identity)
    ):
        raise ResearchReplayIntegrityError("postflight artifact lineage 無法重建")
    decisions = tuple(dict(row) for row in decision_rows)
    orders = tuple(verify_order_row(row) for row in order_rows)
    ledger, _ = _rows_payload(ledger_rows, verify_ledger_row)
    matches, _ = _rows_payload(match_rows, verify_match_row)
    episodes, _ = _rows_payload(episode_rows, verify_episode_row)
    entries, _ = _rows_payload(modeled_entry_rows, verify_modeled_entry_row)
    exits, _ = _rows_payload(modeled_exit_rows, verify_modeled_exit_row)
    current_result_cost = verify_replay_consistency(
        episode_rows=episodes,
        modeled_entry_rows=entries,
        modeled_exit_rows=exits,
        summary=result_meta["summary"],
    )
    if digest(current_result_cost) != result_meta["cost_identity_digest"]:
        raise ResearchReplayIntegrityError("postflight current result cost identity 不一致")
    for row in decisions:
        layer_multiplicity_projection((row,))

    decision_ledger = compare_layers(decisions, ledger)
    order_ledger = compare_layers(orders, ledger)
    ledger_match = compare_layers(ledger, matches)
    match_episode = compare_layers(matches, episodes)
    episode_entry = compare_layers(episodes, entries)
    episode_exit = compare_layers(episodes, exits)
    counts = (
        len(decisions),
        len(orders),
        len(ledger),
        len(matches),
        len(episodes),
        len(entries),
        len(exits),
    )
    duplicate_counts = {
        "duplicate_decision_count": _duplicates(decisions, "baseline_decision_id"),
        "duplicate_order_derivation_count": _duplicates(orders, "baseline_order_id"),
        "duplicate_ledger_count": _duplicates(ledger, "signal_id"),
        "duplicate_match_count": _duplicates(matches, "match_id"),
        "duplicate_episode_count": _duplicates(episodes, "episode_id"),
        "duplicate_modeled_entry_count": _duplicates(entries, "modeled_entry_id"),
        "duplicate_modeled_exit_count": _duplicates(exits, "modeled_exit_id"),
    }
    expected_replay = build_replay(
        match_rows=matches,
        min_lot_shares=min_lot_shares,
        slippage_bps=slippage_bps,
        commission_rate=commission_rate,
        sell_tax_rate=sell_tax_rate,
    )
    formula_mismatch_count = (
        _formula_difference_count(expected_replay.episodes, episodes)
        + _formula_difference_count(expected_replay.modeled_entries, entries)
        + _formula_difference_count(expected_replay.modeled_exits, exits)
    )
    share_mismatch_count = sum(
        int(row["shares"] != min_lot_shares) for row in (*episodes, *entries, *exits)
    )
    strategy_calls = _integer(
        strategy_evaluation_count, "strategy_evaluation_count"
    )
    provider_calls = _integer(provider_call_count, "provider_call_count")
    broker_calls = _integer(broker_call_count, "broker_call_count")
    conditions = {
        "schema_version": "r5-replay-postflight-conditions-v2",
        "baseline_identity_valid": baseline_identity_valid is True,
        "v1_invalid_lineage_valid": v1_invalid_lineage_valid is True,
        "order_inception_seal_valid": order_inception_seal_valid is True,
        "ledger_artifact_valid": ledger_artifact_valid is True,
        "match_plan_artifact_valid": match_plan_artifact_valid is True,
        "result_artifact_valid": result_artifact_valid is True,
        "decision_ledger_bidirectional_parity": decision_ledger.equal,
        "order_ledger_bidirectional_parity": order_ledger.equal,
        "ledger_match_bidirectional_parity": ledger_match.equal,
        "match_episode_bidirectional_parity": match_episode.equal,
        "episode_modeled_entry_bidirectional_parity": episode_entry.equal,
        "episode_modeled_exit_bidirectional_parity": episode_exit.equal,
        "all_layer_counts_equal": len(set(counts)) == 1,
        "frozen_signal_count_matches": (
            len(decisions) == 128802
            and len(ledger) == 128802
            and v1_signal_multiplicity_valid is True
        ),
        "no_missing_entry_or_exit": (
            match_meta["missing_entry_count"] == match_meta["missing_exit_count"] == 0
        ),
        "no_duplicate_rows": all(value == 0 for value in duplicate_counts.values()),
        "duplicate_match_count_zero": duplicate_counts["duplicate_match_count"] == 0,
        "all_shares_exact_min_lot": share_mismatch_count == 0,
        "all_formulas_rebuild": formula_mismatch_count == 0,
        "no_strategy_evaluation": strategy_calls == 0,
        "no_provider_or_broker_calls": provider_calls == broker_calls == 0,
    }
    diagnostics = {
        "schema_version": "r5-replay-postflight-diagnostics-v2",
        "authoritative_entry_decision_count": len(decisions),
        "order_derivation_count": len(orders),
        "ledger_signal_count": len(ledger),
        "match_count": len(matches),
        "episode_count": len(episodes),
        "modeled_entry_count": len(entries),
        "modeled_exit_count": len(exits),
        "missing_entry_count": match_meta["missing_entry_count"],
        "missing_exit_count": match_meta["missing_exit_count"],
        **duplicate_counts,
        "decision_minus_ledger_count": decision_ledger.left_minus_right_count,
        "ledger_minus_decision_count": decision_ledger.right_minus_left_count,
        "order_minus_ledger_count": order_ledger.left_minus_right_count,
        "ledger_minus_order_count": order_ledger.right_minus_left_count,
        "ledger_minus_match_count": ledger_match.left_minus_right_count,
        "match_minus_ledger_count": ledger_match.right_minus_left_count,
        "match_minus_episode_count": match_episode.left_minus_right_count,
        "episode_minus_match_count": match_episode.right_minus_left_count,
        "episode_minus_modeled_entry_count": episode_entry.left_minus_right_count,
        "modeled_entry_minus_episode_count": episode_entry.right_minus_left_count,
        "episode_minus_modeled_exit_count": episode_exit.left_minus_right_count,
        "modeled_exit_minus_episode_count": episode_exit.right_minus_left_count,
        "share_mismatch_count": share_mismatch_count,
        "formula_mismatch_count": formula_mismatch_count,
        "strategy_evaluation_count": strategy_calls,
        "provider_call_count": provider_calls,
        "broker_call_count": broker_calls,
        "decision_signal_multiplicity_digest": decision_ledger.left_digest,
        "order_signal_multiplicity_digest": order_ledger.left_digest,
        "ledger_signal_multiplicity_digest": ledger_match.left_digest,
        "match_signal_multiplicity_digest": match_episode.left_digest,
        "episode_signal_multiplicity_digest": episode_entry.left_digest,
        "modeled_entry_signal_multiplicity_digest": episode_entry.right_digest,
        "modeled_exit_signal_multiplicity_digest": episode_exit.right_digest,
    }
    identity_projection = {
        "baseline_result_digest": expected_baseline_result_digest,
        "ledger_manifest_digest": ledger_meta["ledger_manifest_digest"],
        "match_plan_manifest_digest": match_meta["match_plan_manifest_digest"],
        "registration_revision": _integer(
            registration_revision, "registration_revision", minimum=1
        ),
        "replay_id": _nonempty_string(replay_id, "replay_id"),
        "result_manifest_digest": result_meta["result_manifest_digest"],
    }
    body = {
        "schema_version": POSTFLIGHT_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "replay_id": identity_projection["replay_id"],
        "baseline_run_id": ledger_meta["baseline_run_id"],
        "registration_revision": identity_projection["registration_revision"],
        "baseline_result_digest": identity_projection["baseline_result_digest"],
        "ledger_manifest_digest": identity_projection["ledger_manifest_digest"],
        "match_plan_manifest_digest": identity_projection["match_plan_manifest_digest"],
        "result_manifest_digest": identity_projection["result_manifest_digest"],
        "identity_validation_digest": digest(identity_projection),
        "conditions": conditions,
        "diagnostics": diagnostics,
        "verdict": (
            "ACCEPTED"
            if all(value is True for key, value in conditions.items() if key != "schema_version")
            else "INVALID"
        ),
    }
    return verify_postflight({**body, "postflight_digest": digest(body)})


def verify_postflight(value: Mapping[str, Any]) -> dict[str, Any]:
    postflight = dict(value)
    require_exact_fields(postflight, _POSTFLIGHT_FIELDS, "postflight")
    if (
        postflight["schema_version"] != POSTFLIGHT_SCHEMA_VERSION
        or postflight["control_contract_version"] != CONTROL_CONTRACT_VERSION
    ):
        raise ResearchReplayIntegrityError("postflight schema identity 不支援")
    _nonempty_string(postflight["replay_id"], "postflight replay_id")
    _nonempty_string(postflight["baseline_run_id"], "postflight baseline_run_id")
    _integer(postflight["registration_revision"], "registration_revision", minimum=1)
    for field in (
        "baseline_result_digest",
        "ledger_manifest_digest",
        "match_plan_manifest_digest",
        "result_manifest_digest",
        "identity_validation_digest",
        "postflight_digest",
    ):
        require_sha256(postflight[field], field)
    conditions = dict(postflight["conditions"])
    diagnostics = dict(postflight["diagnostics"])
    require_exact_fields(conditions, _POSTFLIGHT_CONDITION_FIELDS, "postflight conditions")
    require_exact_fields(
        diagnostics, _POSTFLIGHT_DIAGNOSTIC_FIELDS, "postflight diagnostics"
    )
    if conditions["schema_version"] != "r5-replay-postflight-conditions-v2":
        raise ResearchReplayIntegrityError("postflight conditions schema 不支援")
    if diagnostics["schema_version"] != "r5-replay-postflight-diagnostics-v2":
        raise ResearchReplayIntegrityError("postflight diagnostics schema 不支援")
    for field in _POSTFLIGHT_CONDITION_FIELDS - {"schema_version"}:
        if not isinstance(conditions[field], bool):
            raise ResearchReplayIntegrityError(f"postflight condition {field} 必須是 boolean")
    for field in _POSTFLIGHT_DIAGNOSTIC_COUNT_FIELDS:
        _integer(diagnostics[field], field)
    for field in _POSTFLIGHT_DIAGNOSTIC_DIGEST_FIELDS:
        require_sha256(diagnostics[field], field)
    expected_verdict = (
        "ACCEPTED"
        if all(value is True for key, value in conditions.items() if key != "schema_version")
        else "INVALID"
    )
    if postflight["verdict"] != expected_verdict:
        raise ResearchReplayIntegrityError("postflight verdict 與 conditions 不一致")
    identity_projection = {
        "baseline_result_digest": postflight["baseline_result_digest"],
        "ledger_manifest_digest": postflight["ledger_manifest_digest"],
        "match_plan_manifest_digest": postflight["match_plan_manifest_digest"],
        "registration_revision": postflight["registration_revision"],
        "replay_id": postflight["replay_id"],
        "result_manifest_digest": postflight["result_manifest_digest"],
    }
    if digest(identity_projection) != postflight["identity_validation_digest"]:
        raise ResearchReplayIntegrityError("postflight identity digest 無法重建")
    body = {key: item for key, item in postflight.items() if key != "postflight_digest"}
    if digest(body) != postflight["postflight_digest"]:
        raise ResearchReplayIntegrityError("postflight digest 無法重建")
    canonical_object_bytes(postflight)
    return postflight
