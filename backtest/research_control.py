"""Frozen R5 cash-admission-neutral research-control contracts.

This module is intentionally framework- and repository-free.  PostgreSQL,
worker, CLI, and HTTP adapters all use these canonical builders and verifiers
so no boundary can reinterpret the deterministic sizing or postflight Gate.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from pathlib import Path
from typing import Any, Iterable, Mapping

from backtest.domain import HistoricalBar, canonical_json, decimal, digest


REQUEST_SCHEMA_VERSION = "cash-admission-control-request-v1"
CONTROL_CONTRACT_VERSION = "cash-admission-control-v1"
PREFLIGHT_SCHEMA_VERSION = "cash-admission-control-preflight-v1"
POSTFLIGHT_SCHEMA_VERSION = "cash-admission-control-postflight-v2"
ALGORITHM_IDENTITY = {
    "implementation": "cash-admission-control-sizing-v1",
    "buffer_ratio": "0.80",
    "position_fraction_scale": 12,
    "position_fraction_rounding": "ROUND_DOWN",
    "starting_cash_scale": 0,
    "starting_cash_rounding": "ROUND_CEILING",
}
ALGORITHM_IMPLEMENTATION_DIGEST = digest(ALGORITHM_IDENTITY)

_SHA256_CHARACTERS = frozenset("0123456789abcdef")
_IDENTITY_FIELDS = frozenset(
    {
        "baseline_run_id",
        "baseline_config_digest",
        "baseline_result_digest",
        "dataset_id",
        "dataset_digest",
        "dataset_manifest_digest",
        "dataset_bars_sha256",
        "dataset_binding_revision",
        "strategy_set_snapshot_digest",
        "atomic_strategy_run_snapshot_digest",
        "dataset_amount_contract_digest",
        "engine_version",
        "commission_rate",
        "sell_tax_rate",
        "slippage_bps",
        "min_lot_shares",
    }
)
_STATISTIC_FIELDS = frozenset(
    {
        "s_max",
        "p_max",
        "candidate_order_count",
        "matched_next_bar_count",
        "missing_next_bar_count",
        "baseline_signal_multiplicity_digest",
    }
)
_SIZING_FIELDS = frozenset(
    {
        "algorithm_implementation_digest",
        "buffer_ratio",
        "entry_cost_multiplier",
        "position_fraction_raw",
        "position_fraction",
        "position_fraction_scale",
        "position_fraction_rounding",
        "starting_cash_raw",
        "starting_cash",
        "starting_cash_scale",
        "starting_cash_rounding",
        "minimum_lot_notional",
        "maximum_session_allocation_ratio",
    }
)


class CashAdmissionControlError(ValueError):
    """Base class for frozen R5 contract failures."""


class CashAdmissionControlConflict(CashAdmissionControlError):
    """A sealed authoritative registration conflicts with a new request."""


class CashAdmissionControlNotAccepted(CashAdmissionControlError):
    """Performance evidence was requested before server postflight acceptance."""


class CashAdmissionControlIntegrityError(CashAdmissionControlError):
    """Durable R5 evidence cannot be cryptographically reconstructed."""


def require_sha256(value: object, label: str) -> str:
    resolved = str(value or "")
    if len(resolved) != 64 or any(
        character not in _SHA256_CHARACTERS for character in resolved
    ):
        raise CashAdmissionControlIntegrityError(
            f"{label} 必須是 lowercase SHA-256"
        )
    return resolved


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise CashAdmissionControlIntegrityError(
            f"{label} schema 不一致：missing={missing}, unknown={unknown}"
        )


@dataclass(frozen=True)
class CashAdmissionSizing:
    entry_cost_multiplier: Decimal
    position_fraction_raw: Decimal
    position_fraction: Decimal
    starting_cash_raw: Decimal
    starting_cash: Decimal
    minimum_lot_notional: Decimal
    maximum_session_allocation_ratio: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm_implementation_digest": ALGORITHM_IMPLEMENTATION_DIGEST,
            "buffer_ratio": ALGORITHM_IDENTITY["buffer_ratio"],
            "entry_cost_multiplier": str(self.entry_cost_multiplier),
            "position_fraction_raw": str(self.position_fraction_raw),
            "position_fraction": str(self.position_fraction),
            "position_fraction_scale": ALGORITHM_IDENTITY["position_fraction_scale"],
            "position_fraction_rounding": ALGORITHM_IDENTITY["position_fraction_rounding"],
            "starting_cash_raw": str(self.starting_cash_raw),
            "starting_cash": str(self.starting_cash),
            "starting_cash_scale": ALGORITHM_IDENTITY["starting_cash_scale"],
            "starting_cash_rounding": ALGORITHM_IDENTITY["starting_cash_rounding"],
            "minimum_lot_notional": str(self.minimum_lot_notional),
            "maximum_session_allocation_ratio": str(
                self.maximum_session_allocation_ratio
            ),
        }


@dataclass(frozen=True)
class CashAdmissionPreflightStatistics:
    s_max: int
    p_max: Decimal
    candidate_order_count: int
    matched_next_bar_count: int
    missing_next_bar_count: int
    baseline_signal_multiplicity_digest: str


def compute_cash_admission_preflight_statistics(
    *,
    baseline_orders: Iterable[Mapping[str, Any]],
    bars: Iterable[HistoricalBar],
) -> CashAdmissionPreflightStatistics:
    """Stream exact intraday next-bar opens without loading Dataset bars."""

    by_symbol: dict[str, list[tuple[datetime, str]]] = {}
    distinct_daily: dict[str, set[str]] = {}
    baseline_signal_keys: Counter[str] = Counter()
    candidate_count = 0
    for raw_order in baseline_orders:
        order = dict(raw_order)
        if order.get("side") != "ENTRY":
            continue
        if order.get("execution_horizon") not in (None, "INTRADAY_NEXT_BAR"):
            raise CashAdmissionControlIntegrityError(
                "R5 v1 preflight 只支援 INTRADAY_NEXT_BAR ENTRY"
            )
        signal_keys = _entry_signal_keys((order,))
        signal_key = next(iter(signal_keys))
        baseline_signal_keys.update(signal_keys)
        created_at = datetime.fromisoformat(str(order["created_at"]))
        if created_at.tzinfo is None:
            raise CashAdmissionControlIntegrityError("R5 ENTRY created_at 必須含 timezone")
        symbol = str(order["symbol"])
        by_symbol.setdefault(symbol, []).append((created_at, signal_key))
        distinct_daily.setdefault(created_at.date().isoformat(), set()).add(signal_key)
        candidate_count += 1
    if candidate_count == 0:
        raise CashAdmissionControlIntegrityError("R5 baseline 沒有 ENTRY candidates")
    for values in by_symbol.values():
        values.sort(key=lambda item: (item[0], item[1]))
    indexes = {symbol: 0 for symbol in by_symbol}
    matched = 0
    highest_price: Decimal | None = None
    for bar in bars:
        values = by_symbol.get(bar.symbol)
        if values is None:
            continue
        index = indexes[bar.symbol]
        while index < len(values):
            created_at, _ = values[index]
            if bar.timestamp <= created_at:
                break
            if bar.timestamp.date() > created_at.date():
                index += 1
                continue
            if bar.timestamp.date() < created_at.date():
                break
            highest_price = bar.open if highest_price is None else max(highest_price, bar.open)
            matched += 1
            index += 1
        indexes[bar.symbol] = index
    missing = candidate_count - matched
    if highest_price is None:
        raise CashAdmissionControlIntegrityError("R5 preflight 找不到任何 next-bar open")
    return CashAdmissionPreflightStatistics(
        s_max=max(len(values) for values in distinct_daily.values()),
        p_max=highest_price,
        candidate_order_count=candidate_count,
        matched_next_bar_count=matched,
        missing_next_bar_count=missing,
        baseline_signal_multiplicity_digest=digest(
            dict(sorted(baseline_signal_keys.items()))
        ),
    )


def derive_cash_admission_sizing(
    *,
    s_max: int,
    p_max: Decimal | str | int,
    min_lot_shares: int,
    slippage_bps: Decimal | str | int,
    commission_rate: Decimal | str | int,
) -> CashAdmissionSizing:
    """Apply the frozen Decimal-only C/f derivation exactly once."""

    highest_price = decimal(p_max)
    slippage = decimal(slippage_bps)
    commission = decimal(commission_rate)
    if s_max <= 0 or highest_price <= 0 or min_lot_shares <= 0:
        raise CashAdmissionControlIntegrityError(
            "R5 sizing 要求 S_max、P_max 與 minimum lot 均大於 0"
        )
    if slippage < 0 or commission < 0:
        raise CashAdmissionControlIntegrityError("R5 cost identity 不可為負")
    entry_cost_multiplier = (
        Decimal("1") + slippage / Decimal("10000")
    ) * (Decimal("1") + commission)
    if entry_cost_multiplier <= 0:
        raise CashAdmissionControlIntegrityError("R5 entry cost multiplier 不合法")
    buffer_ratio = Decimal(str(ALGORITHM_IDENTITY["buffer_ratio"]))
    fraction_raw = buffer_ratio / (Decimal(s_max) * entry_cost_multiplier)
    fraction = fraction_raw.quantize(Decimal("0.000000000001"), rounding=ROUND_DOWN)
    if fraction <= 0:
        raise CashAdmissionControlIntegrityError("R5 position fraction 向下取整後為 0")
    minimum_lot_notional = highest_price * Decimal(min_lot_shares)
    cash_raw = minimum_lot_notional / fraction
    cash = cash_raw.quantize(Decimal("1"), rounding=ROUND_CEILING)
    allocation_ratio = Decimal(s_max) * fraction * entry_cost_multiplier
    if cash * fraction < minimum_lot_notional:
        raise CashAdmissionControlIntegrityError("R5 sizing 無法購買最低整張")
    if allocation_ratio > buffer_ratio:
        raise CashAdmissionControlIntegrityError("R5 sizing 超過 80% session buffer")
    return CashAdmissionSizing(
        entry_cost_multiplier=entry_cost_multiplier,
        position_fraction_raw=fraction_raw,
        position_fraction=fraction,
        starting_cash_raw=cash_raw,
        starting_cash=cash,
        minimum_lot_notional=minimum_lot_notional,
        maximum_session_allocation_ratio=allocation_ratio,
    )


def build_cash_admission_preflight(
    *,
    identity: Mapping[str, Any],
    s_max: int,
    p_max: Decimal | str | int,
    candidate_order_count: int,
    matched_next_bar_count: int,
    missing_next_bar_count: int,
    baseline_signal_multiplicity_digest: str,
) -> dict[str, Any]:
    canonical_identity = dict(identity)
    _exact_fields(canonical_identity, _IDENTITY_FIELDS, "R5 preflight identity")
    for field_name in (
        "baseline_config_digest",
        "baseline_result_digest",
        "dataset_digest",
        "dataset_manifest_digest",
        "dataset_bars_sha256",
        "strategy_set_snapshot_digest",
        "atomic_strategy_run_snapshot_digest",
        "dataset_amount_contract_digest",
    ):
        canonical_identity[field_name] = require_sha256(
            canonical_identity[field_name], field_name
        )
    if not str(canonical_identity["baseline_run_id"]).strip():
        raise CashAdmissionControlIntegrityError("baseline_run_id 不可為空")
    if not str(canonical_identity["dataset_id"]).strip():
        raise CashAdmissionControlIntegrityError("dataset_id 不可為空")
    statistics = {
        "s_max": int(s_max),
        "p_max": str(decimal(p_max)),
        "candidate_order_count": int(candidate_order_count),
        "matched_next_bar_count": int(matched_next_bar_count),
        "missing_next_bar_count": int(missing_next_bar_count),
        "baseline_signal_multiplicity_digest": require_sha256(
            baseline_signal_multiplicity_digest,
            "baseline signal multiplicity digest",
        ),
    }
    if min(
        statistics["candidate_order_count"],
        statistics["matched_next_bar_count"],
        statistics["missing_next_bar_count"],
    ) < 0:
        raise CashAdmissionControlIntegrityError("R5 coverage count 不可為負")
    sizing = derive_cash_admission_sizing(
        s_max=statistics["s_max"],
        p_max=statistics["p_max"],
        min_lot_shares=int(canonical_identity["min_lot_shares"]),
        slippage_bps=canonical_identity["slippage_bps"],
        commission_rate=canonical_identity["commission_rate"],
    ).to_dict()
    body: dict[str, Any] = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "algorithm_identity": dict(ALGORITHM_IDENTITY),
        "identity": canonical_identity,
        "statistics": statistics,
        "sizing": sizing,
    }
    return {**body, "artifact_digest": digest(body)}


def verify_cash_admission_preflight(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    _exact_fields(
        raw,
        frozenset(
            {
                "schema_version",
                "control_contract_version",
                "algorithm_identity",
                "identity",
                "statistics",
                "sizing",
                "artifact_digest",
            }
        ),
        "R5 preflight",
    )
    if raw["schema_version"] != PREFLIGHT_SCHEMA_VERSION:
        raise CashAdmissionControlIntegrityError("R5 preflight schema version 不支援")
    if raw["control_contract_version"] != CONTROL_CONTRACT_VERSION:
        raise CashAdmissionControlIntegrityError("R5 control contract version 不支援")
    if dict(raw["algorithm_identity"]) != ALGORITHM_IDENTITY:
        raise CashAdmissionControlIntegrityError("R5 algorithm identity 已漂移")
    identity = dict(raw["identity"])
    statistics = dict(raw["statistics"])
    sizing = dict(raw["sizing"])
    _exact_fields(identity, _IDENTITY_FIELDS, "R5 preflight identity")
    _exact_fields(statistics, _STATISTIC_FIELDS, "R5 preflight statistics")
    _exact_fields(sizing, _SIZING_FIELDS, "R5 preflight sizing")
    rebuilt = build_cash_admission_preflight(
        identity=identity,
        s_max=int(statistics["s_max"]),
        p_max=statistics["p_max"],
        candidate_order_count=int(statistics["candidate_order_count"]),
        matched_next_bar_count=int(statistics["matched_next_bar_count"]),
        missing_next_bar_count=int(statistics["missing_next_bar_count"]),
        baseline_signal_multiplicity_digest=str(
            statistics["baseline_signal_multiplicity_digest"]
        ),
    )
    if raw != rebuilt:
        raise CashAdmissionControlIntegrityError("R5 preflight 無法由 identity 重建")
    require_sha256(raw["artifact_digest"], "preflight artifact_digest")
    return rebuilt


class CashAdmissionPreflightCatalog:
    """Canonical local artifact locator; paths never enter immutable identity."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def path_for(self, artifact_digest: str) -> Path:
        return self._root / f"{require_sha256(artifact_digest, 'preflight digest')}.json"

    def load(self, artifact_digest: str) -> dict[str, Any]:
        path = self.path_for(artifact_digest)
        try:
            payload = path.read_bytes()
        except FileNotFoundError as error:
            raise KeyError(f"找不到 R5 preflight artifact：{artifact_digest}") from error
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CashAdmissionControlIntegrityError("R5 preflight 不是有效 canonical JSON") from error
        verified = verify_cash_admission_preflight(value)
        if payload != (canonical_json(verified) + "\n").encode("utf-8"):
            raise CashAdmissionControlIntegrityError("R5 preflight artifact bytes 不 canonical")
        if verified["artifact_digest"] != artifact_digest:
            raise CashAdmissionControlIntegrityError("R5 preflight locator 與 digest 不一致")
        return verified

    def save(self, preflight: Mapping[str, Any]) -> Path:
        verified = verify_cash_admission_preflight(preflight)
        self._root.mkdir(parents=True, exist_ok=True)
        target = self.path_for(str(verified["artifact_digest"]))
        payload = (canonical_json(verified) + "\n").encode("utf-8")
        try:
            with target.open("xb") as stream:
                stream.write(payload)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise CashAdmissionControlIntegrityError(
                    "相同 R5 preflight digest 已存在不同 bytes"
                )
        return target


def build_research_control_snapshot(
    *,
    preflight: Mapping[str, Any],
    actor_id: str,
    change_note: str,
    created_at: str,
) -> dict[str, Any]:
    verified = verify_cash_admission_preflight(preflight)
    actor = actor_id.strip()
    note = change_note.strip()
    if not actor or not note:
        raise CashAdmissionControlIntegrityError("R5 actor 與 change note 不可為空")
    sizing = dict(verified["sizing"])
    body = {
        "schema_version": "cash-admission-control-snapshot-v1",
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "registration_revision": 1,
        "baseline_run_id": verified["identity"]["baseline_run_id"],
        "preflight": verified,
        "preflight_digest": verified["artifact_digest"],
        "allowed_config_delta": {
            "starting_cash": sizing["starting_cash"],
            "position_fraction": sizing["position_fraction"],
        },
        "actor_id": actor,
        "change_note": note,
        "created_at": created_at,
    }
    return {**body, "snapshot_digest": digest(body)}


def verify_research_control_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    expected = frozenset(
        {
            "schema_version",
            "control_contract_version",
            "registration_revision",
            "baseline_run_id",
            "preflight",
            "preflight_digest",
            "allowed_config_delta",
            "actor_id",
            "change_note",
            "created_at",
            "snapshot_digest",
        }
    )
    _exact_fields(raw, expected, "R5 research control snapshot")
    verified_preflight = verify_cash_admission_preflight(dict(raw["preflight"]))
    if raw["schema_version"] != "cash-admission-control-snapshot-v1":
        raise CashAdmissionControlIntegrityError("R5 snapshot schema version 不支援")
    if raw["control_contract_version"] != CONTROL_CONTRACT_VERSION:
        raise CashAdmissionControlIntegrityError("R5 snapshot contract version 不支援")
    if int(raw["registration_revision"]) != 1:
        raise CashAdmissionControlIntegrityError("R5 snapshot revision 未經 Review 授權")
    if raw["baseline_run_id"] != verified_preflight["identity"]["baseline_run_id"]:
        raise CashAdmissionControlIntegrityError("R5 snapshot baseline identity 不一致")
    if raw["preflight_digest"] != verified_preflight["artifact_digest"]:
        raise CashAdmissionControlIntegrityError("R5 snapshot preflight digest 不一致")
    expected_delta = {
        "starting_cash": verified_preflight["sizing"]["starting_cash"],
        "position_fraction": verified_preflight["sizing"]["position_fraction"],
    }
    if dict(raw["allowed_config_delta"]) != expected_delta:
        raise CashAdmissionControlIntegrityError("R5 snapshot config delta 未經授權")
    require_sha256(raw["snapshot_digest"], "research control snapshot digest")
    body = {key: item for key, item in raw.items() if key != "snapshot_digest"}
    if digest(body) != raw["snapshot_digest"]:
        raise CashAdmissionControlIntegrityError("R5 snapshot digest 無法重建")
    return raw


def _entry_signal_keys(orders: Iterable[Mapping[str, Any]]) -> Counter[str]:
    keys: Counter[str] = Counter()
    for order in orders:
        if str(order.get("side")) != "ENTRY":
            continue
        key = {
            "symbol": str(order.get("symbol") or ""),
            "created_at": str(order.get("created_at") or ""),
            "primary_strategy_id": str(order.get("primary_strategy_id") or ""),
            "triggered_strategy_ids": [
                str(item) for item in order.get("triggered_strategy_ids", ())
            ],
        }
        if not key["symbol"] or not key["created_at"] or not key["primary_strategy_id"]:
            raise CashAdmissionControlIntegrityError("ENTRY order signal key 不完整")
        keys[canonical_json(key)] += 1
    return keys


def entry_signal_multiplicity_digest(
    orders: Iterable[Mapping[str, Any]],
) -> str:
    return digest(dict(sorted(_entry_signal_keys(orders).items())))


def cash_admission_projection_digest(result: Mapping[str, Any]) -> str:
    """Bind every ENTRY order/fill field used to prove cash admission."""

    return digest(
        {
            "entry_orders": [
                dict(item)
                for item in result.get("orders", ())
                if str(item.get("side")) == "ENTRY"
            ],
            "entry_fills": [
                dict(item)
                for item in result.get("fills", ())
                if str(item.get("side")) == "ENTRY"
            ],
        }
    )


def build_cash_admission_postflight(
    *,
    baseline_orders: Iterable[Mapping[str, Any]],
    control_result: Mapping[str, Any],
    preflight: Mapping[str, Any],
    control_run_id: str,
    control_config_digest: str,
    control_result_digest: str,
    identity_validation_digest: str,
) -> dict[str, Any]:
    """Build diagnostics-only evidence; performance is never embedded here."""

    verified_preflight = verify_cash_admission_preflight(preflight)
    control_orders = [dict(item) for item in control_result.get("orders", ())]
    baseline_keys = _entry_signal_keys(baseline_orders)
    control_keys = _entry_signal_keys(control_orders)
    entry_orders = [item for item in control_orders if item.get("side") == "ENTRY"]
    entry_fills = [
        item for item in control_result.get("fills", ())
        if item.get("side") == "ENTRY"
    ]
    non_filled = [item for item in entry_orders if item.get("status") != "FILLED"]
    reason_counts = Counter(
        canonical_json(
            {
                "status": str(item.get("status") or "UNKNOWN"),
                "reason": str(item.get("reason") or ""),
            }
        )
        for item in non_filled
    )
    statistics = dict(verified_preflight["statistics"])
    candidate_count = int(statistics["candidate_order_count"])
    conditions = {
        "preflight_has_no_missing_next_bar": int(statistics["missing_next_bar_count"]) == 0,
        "preflight_coverage_matches_candidates": (
            int(statistics["matched_next_bar_count"]) == candidate_count
        ),
        "entry_order_count_matches_candidates": len(entry_orders) == candidate_count,
        "entry_fill_count_matches_candidates": len(entry_fills) == candidate_count,
        "all_entry_orders_filled": not non_filled,
        "entry_signal_multiplicity_matches_baseline": baseline_keys == control_keys,
        "baseline_signal_multiplicity_matches_preflight": (
            digest(dict(sorted(baseline_keys.items())))
            == statistics["baseline_signal_multiplicity_digest"]
        ),
    }
    accepted = all(conditions.values())
    diagnostics = {
        "candidate_order_count": candidate_count,
        "control_entry_order_count": len(entry_orders),
        "control_entry_fill_count": len(entry_fills),
        "non_filled_entry_order_count": len(non_filled),
        "non_filled_reason_counts": dict(sorted(reason_counts.items())),
        "baseline_signal_key_count": sum(baseline_keys.values()),
        "baseline_distinct_signal_key_count": len(baseline_keys),
        "control_signal_key_count": sum(control_keys.values()),
        "control_distinct_signal_key_count": len(control_keys),
        "baseline_signal_multiplicity_digest": digest(dict(sorted(baseline_keys.items()))),
        "control_signal_multiplicity_digest": digest(dict(sorted(control_keys.items()))),
    }
    body = {
        "schema_version": POSTFLIGHT_SCHEMA_VERSION,
        "control_contract_version": CONTROL_CONTRACT_VERSION,
        "control_run_id": control_run_id,
        "baseline_run_id": verified_preflight["identity"]["baseline_run_id"],
        "preflight_digest": verified_preflight["artifact_digest"],
        "control_config_digest": require_sha256(
            control_config_digest, "control config digest"
        ),
        "control_result_digest": require_sha256(
            control_result_digest, "control result digest"
        ),
        "control_admission_projection_digest": cash_admission_projection_digest(
            control_result
        ),
        "identity_validation_digest": require_sha256(
            identity_validation_digest, "identity validation digest"
        ),
        "conditions": conditions,
        "diagnostics": diagnostics,
        "verdict": "ACCEPTED" if accepted else "INVALID",
    }
    return {**body, "postflight_digest": digest(body)}


def cash_admission_identity_validation_digest(
    *,
    baseline_run: Mapping[str, Any],
    control_run: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> str:
    verified = verify_cash_admission_preflight(preflight)
    return digest(
        {
            "baseline_run_id": baseline_run["run_id"],
            "baseline_config_digest": baseline_run["config_digest"],
            "baseline_result_digest": baseline_run["result_digest"],
            "control_run_id": control_run["run_id"],
            "control_config_digest": control_run["config_digest"],
            "dataset_id": control_run["dataset_id"],
            "dataset_digest": control_run["dataset_digest"],
            "preflight_digest": verified["artifact_digest"],
        }
    )


def verify_cash_admission_postflight(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    expected = frozenset(
        {
            "schema_version",
            "control_contract_version",
            "control_run_id",
            "baseline_run_id",
            "preflight_digest",
            "control_config_digest",
            "control_result_digest",
            "control_admission_projection_digest",
            "identity_validation_digest",
            "conditions",
            "diagnostics",
            "verdict",
            "postflight_digest",
        }
    )
    _exact_fields(raw, expected, "R5 postflight")
    if raw["schema_version"] != POSTFLIGHT_SCHEMA_VERSION:
        raise CashAdmissionControlIntegrityError("R5 postflight schema version 不支援")
    if raw["control_contract_version"] != CONTROL_CONTRACT_VERSION:
        raise CashAdmissionControlIntegrityError("R5 postflight contract version 不支援")
    for field_name in (
        "preflight_digest",
        "control_config_digest",
        "control_result_digest",
        "control_admission_projection_digest",
        "identity_validation_digest",
        "postflight_digest",
    ):
        require_sha256(raw[field_name], field_name)
    conditions = dict(raw["conditions"])
    accepted = bool(conditions) and all(value is True for value in conditions.values())
    if raw["verdict"] != ("ACCEPTED" if accepted else "INVALID"):
        raise CashAdmissionControlIntegrityError("R5 postflight verdict 與條件不一致")
    body = {key: item for key, item in raw.items() if key != "postflight_digest"}
    if digest(body) != raw["postflight_digest"]:
        raise CashAdmissionControlIntegrityError("R5 postflight digest 無法重建")
    return raw


def recompute_backtest_result_digest(result: Mapping[str, Any]) -> str:
    """Rebuild the immutable digest defined by metrics.summarize_run()."""

    summary = dict(result.get("summary", {}))
    summary.pop("result_digest", None)
    return digest(
        {
            "summary": summary,
            "trades": list(result.get("trades", [])),
            "equity": list(result.get("daily_equity", [])),
            "decisions": list(result.get("decisions", [])),
        }
    )
