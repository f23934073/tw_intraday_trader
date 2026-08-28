"""Offline coverage audit and non-formal MVP evaluation-universe contracts."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from backtest.finmind_snapshot import FinMindSnapshotPlan
from institutional_data.serialization import canonical_json, sha256_text


COVERAGE_SCHEMA_VERSION = "finmind_mvp_price_coverage_audit_v1"
UNIVERSE_SCHEMA_VERSION = "mvp_evaluation_universe_v1"
COVERAGE_STATUS = "PASS_FOR_NON_FORMAL_MVP_FREEZE_ONLY"
UNIVERSE_STATUS = "FROZEN_NON_FORMAL_MVP"
UNIVERSE_SCOPE = "FINMIND_DATASET_COVERED_CURRENT_SNAPSHOT_MVP"
CHANGE_POLICY = "IMMUTABLE_APPEND_ONLY_REVISIONS"
MINIMUM_TARGET_SESSIONS = 60
MINIMUM_SYMBOL_COVERAGE_RATE = Decimal("0.95")
MINIMUM_SYMBOL_SESSION_COVERAGE_RATE = Decimal("0.99")
MINIMUM_AGGREGATE_SESSION_COVERAGE_RATE = Decimal("0.99")
FORMAL_PROTOCOL_DIGEST = (
    "b769cf1b672e15d599cf610d22bda49d37981ddc36ae999b120b52702b197dc4"
)
COVERAGE_AMENDMENT_DIGEST = (
    "6a5a943e720dc3bf0e9bc952805539a4c0a460d3f8137462f714773fbaba96ab"
)
FORMAL_PRICE_COVERAGE_CONTRACT_DIGEST = (
    "6fb84bf8bd4950fe5558488590762f55da335ff3215b5c561fe39ec2c1457384"
)


class InstitutionalMvpEvaluationError(RuntimeError):
    """Offline coverage or universe construction failed closed."""


@dataclass(frozen=True)
class _SnapshotProfile:
    trading_dates: tuple[str, ...]
    included_symbols: tuple[str, ...]
    market_by_symbol: Mapping[str, str]
    partition_by_key: Mapping[tuple[str, str], Mapping[str, Any]]
    ready_by_symbol: Mapping[str, int]
    empty_by_symbol: Mapping[str, int]
    excluded_symbols: tuple[Mapping[str, Any], ...]


def qualified_symbols_for_mvp(snapshot_plan: FinMindSnapshotPlan) -> tuple[str, ...]:
    """Reconstruct the exact full-window symbols admitted by the MVP audit."""
    return _qualified_symbols(_profile_snapshot(snapshot_plan))


def _qualified_symbols(profile: _SnapshotProfile) -> tuple[str, ...]:
    return tuple(
        symbol
        for symbol in profile.included_symbols
        if _decimal_rate(
            profile.ready_by_symbol[symbol],
            profile.ready_by_symbol[symbol] + profile.empty_by_symbol[symbol],
        )
        >= MINIMUM_SYMBOL_SESSION_COVERAGE_RATE
    )


def build_mvp_price_coverage_audit(
    *,
    price_dataset_reference: Mapping[str, Any],
    snapshot_plan: FinMindSnapshotPlan,
    candidate_series: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit metadata-only price coverage and the candidate-to-price join."""
    _verify_series_identity(candidate_series)
    if candidate_series.get("price_dataset_reference") != dict(
        price_dataset_reference
    ):
        raise ValueError("candidate series and price Dataset lineage differ")
    profile = _profile_snapshot(snapshot_plan)
    _verify_dataset_snapshot_binding(
        price_dataset_reference=price_dataset_reference,
        snapshot_plan=snapshot_plan,
        profile=profile,
    )
    session_count = len(profile.trading_dates)
    included_symbol_count = len(profile.included_symbols)
    excluded_symbol_count = len(profile.excluded_symbols)
    acquisition_target_count = included_symbol_count + excluded_symbol_count
    included_partition_count = len(profile.partition_by_key)
    ready_partition_count = sum(profile.ready_by_symbol.values())
    empty_partition_count = sum(profile.empty_by_symbol.values())

    qualified_symbols = _qualified_symbols(profile)
    excluded_qualification = _qualification_exclusions(
        profile=profile,
        qualified_symbols=set(qualified_symbols),
        session_count=session_count,
    )
    qualified_ready = sum(profile.ready_by_symbol[symbol] for symbol in qualified_symbols)
    qualified_expected = len(qualified_symbols) * session_count
    symbol_rate = _decimal_rate(len(qualified_symbols), acquisition_target_count)
    aggregate_rate = (
        _decimal_rate(qualified_ready, qualified_expected)
        if qualified_expected
        else Decimal("0")
    )
    numeric_gate_pass = (
        symbol_rate >= MINIMUM_SYMBOL_COVERAGE_RATE
        and aggregate_rate >= MINIMUM_AGGREGATE_SESSION_COVERAGE_RATE
    )

    candidate_rows = _candidate_rows(candidate_series)
    qualified_set = set(qualified_symbols)
    included_memberships: list[dict[str, Any]] = []
    excluded_memberships: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    market_counts: dict[str, Counter[str]] = defaultdict(Counter)
    expected_candidate_symbols: dict[str, str] = {}
    included_candidate_symbols: set[str] = set()
    included_target_sessions: set[str] = set()
    trading_session_index = {
        session: index for index, session in enumerate(profile.trading_dates)
    }
    for row in candidate_rows:
        symbol = row["symbol"]
        target_session = row["target_session"]
        market = row["market"]
        target_index = trading_session_index.get(target_session)
        if (
            target_index is None
            or target_index == 0
            or profile.trading_dates[target_index - 1] != row["source_session"]
        ):
            raise ValueError(
                "candidate source/target sessions differ from Dataset session order"
            )
        previous_market = expected_candidate_symbols.setdefault(symbol, market)
        if previous_market != market:
            raise ValueError("candidate symbol market mapping changed within series")
        dataset_market = profile.market_by_symbol.get(symbol)
        if dataset_market is not None and dataset_market != market:
            raise ValueError("candidate market mapping differs from price Dataset")
        partition = profile.partition_by_key.get((symbol, target_session))
        if symbol not in profile.ready_by_symbol:
            reason = "SYMBOL_NOT_IN_PRICE_DATASET"
        elif symbol not in qualified_set:
            reason = "SYMBOL_BELOW_0_99_FULL_WINDOW_READY_COVERAGE"
        elif partition is None:
            reason = "TARGET_PARTITION_MISSING"
        elif partition["status"] != "READY":
            reason = "TARGET_PARTITION_NOT_READY"
        else:
            reason = "INCLUDED"
        reason_counts[reason] += 1
        market_counts[market][reason] += 1
        lineage = {
            "candidate_batch_digest": row["candidate_batch_digest"],
            "candidate_entry_digest": row["candidate_entry_digest"],
            "source_session": row["source_session"],
            "symbol": symbol,
            "target_session": target_session,
        }
        if reason == "INCLUDED":
            assert partition is not None
            included_memberships.append(
                {
                    **lineage,
                    "price_partition_digest": _digest(
                        partition.get("canonical_sha256"),
                        "price partition digest",
                    ),
                }
            )
            included_candidate_symbols.add(symbol)
            included_target_sessions.add(target_session)
        else:
            excluded_memberships.append(
                {**lineage, "market": market, "reason_code": reason}
            )

    candidate_symbol_rate = (
        _decimal_rate(len(included_candidate_symbols), len(expected_candidate_symbols))
        if expected_candidate_symbols
        else Decimal("0")
    )
    market_concentration = {
        market: {
            "candidate_observation_count": sum(counts.values()),
            "excluded_observation_count": sum(
                value for reason, value in counts.items() if reason != "INCLUDED"
            ),
            "included_observation_count": counts["INCLUDED"],
            "included_observation_rate": _rate_text(
                counts["INCLUDED"], sum(counts.values())
            ),
        }
        for market, counts in sorted(market_counts.items())
    }
    every_target_has_member = len(included_target_sessions) == int(
        candidate_series.get("overlapping_target_session_count", 0)
    )
    mvp_freeze_allowed = (
        numeric_gate_pass
        and len(included_target_sessions) >= MINIMUM_TARGET_SESSIONS
        and every_target_has_member
        and bool(included_memberships)
    )
    issues = [
        "CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED",
        "FORMAL_PIT_UNIVERSE_NOT_AVAILABLE",
        "CORPORATE_ACTION_POLICY_NOT_RESOLVED_FOR_FORMAL_EVALUATION",
        "SIZE_LIQUIDITY_INDUSTRY_DELISTED_CONCENTRATION_NOT_AVAILABLE",
    ]
    if not candidate_rows:
        issues.append("CANDIDATE_SERIES_HAS_NO_OBSERVATIONS")
    if candidate_symbol_rate < MINIMUM_SYMBOL_COVERAGE_RATE:
        issues.append("CANDIDATE_SYMBOL_COVERAGE_BELOW_FORMAL_THRESHOLD")
    market_rates = {
        item["included_observation_rate"] for item in market_concentration.values()
    }
    if len(market_rates) > 1:
        issues.append("CANDIDATE_EXCLUSIONS_CONCENTRATED_BY_MARKET")

    body: dict[str, Any] = {
        "candidate_join": {
            "candidate_observation_count": len(candidate_rows),
            "candidate_observation_coverage_rate": _rate_text_or_zero(
                len(included_memberships), len(candidate_rows)
            ),
            "candidate_symbol_count": len(expected_candidate_symbols),
            "candidate_symbol_coverage_rate": _rate_text_or_zero(
                len(included_candidate_symbols), len(expected_candidate_symbols)
            ),
            "candidate_target_session_count": int(
                candidate_series["overlapping_target_session_count"]
            ),
            "excluded_membership_count": len(excluded_memberships),
            "excluded_memberships": excluded_memberships,
            "included_membership_count": len(included_memberships),
            "included_membership_digest": sha256_text(
                canonical_json(included_memberships)
            ),
            "included_memberships": included_memberships,
            "included_symbol_count": len(included_candidate_symbols),
            "included_target_session_count": len(included_target_sessions),
            "issue_reason_distribution": dict(sorted(reason_counts.items())),
            "market_concentration": market_concentration,
            "status": (
                "NO_CANDIDATE_OBSERVATIONS"
                if not candidate_rows
                else (
                    "COVERED_SUBSET_AVAILABLE_FORMAL_COVERAGE_FAILED"
                    if candidate_symbol_rate < MINIMUM_SYMBOL_COVERAGE_RATE
                    else "COVERED_SUBSET_AVAILABLE"
                )
            ),
        },
        "candidate_series_reference": {
            "artifact_digest": candidate_series["artifact_digest"],
            "artifact_id": candidate_series["artifact_id"],
            "batch_count": candidate_series["batch_count"],
            "source_sessions_digest": candidate_series["series_plan_reference"][
                "source_sessions_digest"
            ],
            "target_sessions_digest": candidate_series["series_plan_reference"][
                "target_sessions_digest"
            ],
        },
        "change_policy": CHANGE_POLICY,
        "dataset_coverage": {
            "acquisition_target_symbol_count": acquisition_target_count,
            "empty_partition_count": empty_partition_count,
            "included_market_mapping": _market_mapping_counts(profile),
            "included_resolved_partition_count": included_partition_count,
            "included_symbol_count": included_symbol_count,
            "ready_partition_count": ready_partition_count,
            "ready_partition_rate_for_included_symbols": _rate_text(
                ready_partition_count, included_partition_count
            ),
            "resolved_partition_rate_for_acquisition_targets": _rate_text(
                included_partition_count, acquisition_target_count * session_count
            ),
            "session_count": session_count,
            "symbol_completion_rate": _rate_text(
                included_symbol_count, acquisition_target_count
            ),
        },
        "evidence_scope": {
            "bars_file_opened_or_iterated": False,
            "institutional_candidate_metadata_read": True,
            "outcome_or_holdout_read": False,
            "price_or_kbar_value_read": False,
            "provider_call_performed": False,
            "return_or_pnl_read": False,
        },
        "execution_permissions": {
            "formal_population_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "mvp_evaluation_universe_freeze_allowed": mvp_freeze_allowed,
            "order_submission_allowed": False,
            "outcome_generation_allowed": False,
            "runtime_strategy_binding_allowed": False,
        },
        "formal_contract_reference": {
            "coverage_amendment_digest": COVERAGE_AMENDMENT_DIGEST,
            "formal_price_coverage_contract_digest": FORMAL_PRICE_COVERAGE_CONTRACT_DIGEST,
            "formal_protocol_digest": FORMAL_PROTOCOL_DIGEST,
            "status": "REFERENCE_ONLY_NOT_SATISFIED_BY_MVP",
        },
        "issues": issues,
        "missingness_concentration": {
            "ADV20_LIQUIDITY_COHORT": "UNKNOWN_NOT_AVAILABLE",
            "INDUSTRY_CODE": "UNKNOWN_NOT_AVAILABLE",
            "LISTING_STATUS_ACTIVE_VS_LATER_DELISTED": "UNKNOWN_NOT_AVAILABLE",
            "MARKET": market_concentration,
            "MARKET_CAP_COHORT": "UNKNOWN_NOT_AVAILABLE",
            "formal_owner_review_status": "NOT_ELIGIBLE_FOR_FORMAL_REVIEW",
        },
        "price_dataset_reference": dict(price_dataset_reference),
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "scope": {
            "claim_all_taiwan_equities_allowed": False,
            "denominator": (
                f"FINMIND_ACQUISITION_DECLARED_{acquisition_target_count}_SYMBOL_"
                "CURRENT_SNAPSHOT"
            ),
            "formal_pit_scope": False,
            "name": UNIVERSE_SCOPE,
        },
        "snapshot_plan_reference": {
            "handoff_evidence_digest": snapshot_plan.handoff_evidence_digest,
            "operation_audit_digest": snapshot_plan.operation_audit_digest,
            "plan_identity_digest": snapshot_plan.plan_identity_digest,
            "selection_audit_digest": snapshot_plan.selection_audit_digest,
            "source_snapshot_digest": snapshot_plan.identity[
                "source_snapshot_digest"
            ],
        },
        "status": COVERAGE_STATUS if mvp_freeze_allowed else "BLOCKED",
        "symbol_qualification": {
            "aggregate_ready_partition_count": qualified_ready,
            "aggregate_session_coverage_rate": _rate_text_or_zero(
                qualified_ready, qualified_expected
            ),
            "expected_partition_count_for_qualified_symbols": qualified_expected,
            "excluded_symbols": excluded_qualification,
            "minimum_aggregate_session_coverage_rate": str(
                MINIMUM_AGGREGATE_SESSION_COVERAGE_RATE
            ),
            "minimum_per_symbol_session_coverage_rate": str(
                MINIMUM_SYMBOL_SESSION_COVERAGE_RATE
            ),
            "minimum_symbol_coverage_rate": str(MINIMUM_SYMBOL_COVERAGE_RATE),
            "numeric_gate_pass": numeric_gate_pass,
            "qualified_symbol_count": len(qualified_symbols),
            "qualified_symbol_digest": sha256_text(canonical_json(qualified_symbols)),
            "symbol_coverage_rate": _rate_text(
                len(qualified_symbols), acquisition_target_count
            ),
        },
    }
    return _with_identity(body, "finmind-mvp-price-coverage-audit-v1")


def verify_mvp_price_coverage_audit(
    payload: Mapping[str, Any],
    *,
    price_dataset_reference: Mapping[str, Any],
    snapshot_plan: FinMindSnapshotPlan,
    candidate_series: Mapping[str, Any],
) -> None:
    _verify_identity(payload, "finmind-mvp-price-coverage-audit-v1")
    expected = build_mvp_price_coverage_audit(
        price_dataset_reference=price_dataset_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=candidate_series,
    )
    if dict(payload) != expected:
        raise ValueError("MVP price coverage audit differs from exact reconstruction")


def build_mvp_evaluation_universe(
    *,
    coverage_audit: Mapping[str, Any],
    price_dataset_reference: Mapping[str, Any],
    snapshot_plan: FinMindSnapshotPlan,
    candidate_series: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze only the exact covered membership from a verified MVP audit."""
    verify_mvp_price_coverage_audit(
        coverage_audit,
        price_dataset_reference=price_dataset_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=candidate_series,
    )
    permissions = _mapping(
        coverage_audit.get("execution_permissions"), "coverage permissions"
    )
    if permissions.get("mvp_evaluation_universe_freeze_allowed") is not True:
        raise InstitutionalMvpEvaluationError(
            "coverage audit does not authorize an MVP universe freeze"
        )
    join = _mapping(coverage_audit.get("candidate_join"), "candidate_join")
    members = join.get("included_memberships")
    if not isinstance(members, list) or len(members) < MINIMUM_TARGET_SESSIONS:
        raise InstitutionalMvpEvaluationError("covered MVP membership is insufficient")
    if len({(item["target_session"], item["symbol"]) for item in members}) != len(
        members
    ):
        raise ValueError("MVP universe membership identities must be unique")
    target_sessions = tuple(sorted({item["target_session"] for item in members}))
    symbols = tuple(sorted({item["symbol"] for item in members}))
    if len(target_sessions) < MINIMUM_TARGET_SESSIONS:
        raise InstitutionalMvpEvaluationError(
            "MVP universe requires at least 60 target sessions"
        )
    body: dict[str, Any] = {
        "change_policy": CHANGE_POLICY,
        "coverage_audit_reference": {
            "artifact_digest": coverage_audit["artifact_digest"],
            "artifact_id": coverage_audit["artifact_id"],
        },
        "evidence_scope": {
            "bars_file_opened_or_iterated": False,
            "outcome_or_holdout_read": False,
            "price_or_kbar_value_read": False,
            "return_or_pnl_read": False,
        },
        "execution_permissions": {
            "formal_population_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "mvp_universe_observation_allowed": True,
            "order_submission_allowed": False,
            "outcome_generation_allowed": False,
            "production_allowed": False,
            "runtime_strategy_binding_allowed": False,
        },
        "limitations": list(coverage_audit["issues"]),
        "membership": members,
        "membership_count": len(members),
        "membership_digest": sha256_text(canonical_json(members)),
        "price_dataset_reference": dict(coverage_audit["price_dataset_reference"]),
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": UNIVERSE_SCHEMA_VERSION,
        "scope": UNIVERSE_SCOPE,
        "status": UNIVERSE_STATUS,
        "symbol_count": len(symbols),
        "symbol_digest": sha256_text(canonical_json(symbols)),
        "target_session_count": len(target_sessions),
        "target_session_digest": sha256_text(canonical_json(target_sessions)),
    }
    return _with_identity(body, "finmind-mvp-evaluation-universe-v1")


def verify_mvp_evaluation_universe(
    payload: Mapping[str, Any],
    *,
    coverage_audit: Mapping[str, Any],
    price_dataset_reference: Mapping[str, Any],
    snapshot_plan: FinMindSnapshotPlan,
    candidate_series: Mapping[str, Any],
) -> None:
    _verify_identity(payload, "finmind-mvp-evaluation-universe-v1")
    expected = build_mvp_evaluation_universe(
        coverage_audit=coverage_audit,
        price_dataset_reference=price_dataset_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=candidate_series,
    )
    if dict(payload) != expected:
        raise ValueError("MVP evaluation universe differs from exact audit membership")


def _profile_snapshot(snapshot_plan: FinMindSnapshotPlan) -> _SnapshotProfile:
    snapshot_plan.verify_digests()
    identity = snapshot_plan.identity
    source_contract = _mapping(identity.get("source_contract"), "source_contract")
    raw_dates = source_contract.get("trading_dates")
    if not isinstance(raw_dates, list):
        raise ValueError("snapshot trading_dates must be a list")
    trading_dates = tuple(_text(item, "trading date") for item in raw_dates)
    if tuple(sorted(set(trading_dates))) != trading_dates:
        raise ValueError("snapshot trading_dates must be canonical")
    trading_date_set = set(trading_dates)
    selection = _mapping(identity.get("selection"), "selection")
    raw_symbols = selection.get("included_symbols")
    if not isinstance(raw_symbols, list):
        raise ValueError("snapshot included_symbols must be a list")
    symbols = tuple(_text(item, "included symbol") for item in raw_symbols)
    if tuple(sorted(set(symbols))) != symbols:
        raise ValueError("snapshot included_symbols must be canonical")
    reference = _mapping(identity.get("reference"), "reference")
    raw_mapping = reference.get("mapping")
    if not isinstance(raw_mapping, list):
        raise ValueError("snapshot reference mapping must be a list")
    market_by_symbol: dict[str, str] = {}
    for item in raw_mapping:
        row = _mapping(item, "reference row")
        symbol = _text(row.get("symbol"), "reference symbol")
        market = _text(row.get("market"), "reference market")
        if symbol in market_by_symbol or market not in {"TWSE", "TPEX"}:
            raise ValueError("snapshot reference mapping is invalid")
        market_by_symbol[symbol] = market
    if set(market_by_symbol) != set(symbols):
        raise ValueError("snapshot reference mapping coverage is incomplete")
    raw_partitions = identity.get("included_partitions")
    if not isinstance(raw_partitions, list):
        raise ValueError("snapshot included_partitions must be a list")
    partition_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    ready_by_symbol: Counter[str] = Counter()
    empty_by_symbol: Counter[str] = Counter()
    previous: tuple[str, str] | None = None
    for item in raw_partitions:
        row = _mapping(item, "partition row")
        key = (
            _text(row.get("symbol"), "partition symbol"),
            _text(row.get("session_date"), "partition session"),
        )
        status = _text(row.get("status"), "partition status")
        bar_count = _nonnegative_integer(row.get("bar_count"), "partition bar_count")
        if (
            key[0] not in market_by_symbol
            or key[1] not in trading_date_set
            or status not in {"READY", "EMPTY"}
            or (status == "READY" and bar_count == 0)
            or (status == "EMPTY" and bar_count != 0)
            or key in partition_by_key
            or (previous is not None and key <= previous)
        ):
            raise ValueError("snapshot partition contract is invalid")
        _digest(row.get("canonical_sha256"), "partition canonical_sha256")
        partition_by_key[key] = row
        (ready_by_symbol if status == "READY" else empty_by_symbol)[key[0]] += 1
        previous = key
    if len(partition_by_key) != len(symbols) * len(trading_dates):
        raise ValueError("snapshot included partition matrix is incomplete")
    selection_audit = snapshot_plan.selection_audit
    if selection_audit.get("included_symbols") != list(symbols):
        raise ValueError("snapshot selection audit symbol membership drifted")
    excluded = selection_audit.get("excluded_symbols")
    if not isinstance(excluded, list) or not all(isinstance(item, Mapping) for item in excluded):
        raise ValueError("snapshot excluded symbol evidence is invalid")
    excluded_symbol_set: set[str] = set()
    for item in excluded:
        row = _mapping(item, "excluded symbol row")
        symbol = _text(row.get("symbol"), "excluded symbol")
        if symbol in excluded_symbol_set or symbol in market_by_symbol:
            raise ValueError("snapshot excluded symbol membership is invalid")
        excluded_symbol_set.add(symbol)
        missing = _date_sequence(
            row.get("missing_session_dates"), "missing_session_dates"
        )
        invalid = _date_sequence(
            row.get("invalid_session_dates"), "invalid_session_dates"
        )
        extra = _date_sequence(row.get("extra_session_dates"), "extra_session_dates")
        if (
            not set(missing).issubset(trading_date_set)
            or not set(invalid).issubset(trading_date_set)
            or set(missing) & set(invalid)
            or set(extra) & trading_date_set
        ):
            raise ValueError("snapshot excluded symbol session evidence is invalid")
        _text_sequence(row.get("reason_codes"), "excluded symbol reason_codes")
    counts = _mapping(identity.get("counts"), "snapshot counts")
    expected_counts = {
        "bar_count": sum(
            _nonnegative_integer(row.get("bar_count"), "partition bar_count")
            for row in partition_by_key.values()
        ),
        "empty_partition_count": sum(empty_by_symbol.values()),
        "included_partition_count": len(partition_by_key),
        "included_symbol_count": len(symbols),
        "ready_partition_count": sum(ready_by_symbol.values()),
    }
    if dict(counts) != expected_counts:
        raise ValueError("snapshot count projection drifted")
    audit_counts = _mapping(
        selection_audit.get("snapshot_counts"), "selection audit counts"
    )
    if dict(audit_counts) != {
        **expected_counts,
        "excluded_symbol_count": len(excluded),
    }:
        raise ValueError("snapshot selection audit count projection drifted")
    return _SnapshotProfile(
        trading_dates=trading_dates,
        included_symbols=symbols,
        market_by_symbol=market_by_symbol,
        partition_by_key=partition_by_key,
        ready_by_symbol={symbol: ready_by_symbol[symbol] for symbol in symbols},
        empty_by_symbol={symbol: empty_by_symbol[symbol] for symbol in symbols},
        excluded_symbols=tuple(excluded),
    )


def _verify_dataset_snapshot_binding(
    *,
    price_dataset_reference: Mapping[str, Any],
    snapshot_plan: FinMindSnapshotPlan,
    profile: _SnapshotProfile,
) -> None:
    identity = snapshot_plan.identity
    expected = {
        "bar_count": identity["counts"]["bar_count"],
        "dataset_id": identity["dataset_id"],
        "observed_symbol_count": len(profile.included_symbols),
        "plan_identity_digest": snapshot_plan.plan_identity_digest,
        "selection_audit_digest": snapshot_plan.selection_audit_digest,
        "source_snapshot_digest": identity["source_snapshot_digest"],
    }
    if any(price_dataset_reference.get(key) != value for key, value in expected.items()):
        raise ValueError("price Dataset and snapshot plan binding drifted")
    source = _mapping(identity.get("source_contract"), "source_contract")
    if (
        price_dataset_reference.get("start_date") != source.get("start_date")
        or price_dataset_reference.get("end_date") != source.get("end_date")
        or price_dataset_reference.get("source") != source.get("source")
        or price_dataset_reference.get("issues") != identity.get("issues")
        or price_dataset_reference.get("universe_scope")
        != identity.get("universe_scope")
        or identity.get("universe_scope") != "CURRENT_SNAPSHOT"
        or identity.get("research_eligible") is not False
        or price_dataset_reference.get("research_eligible") is not False
        or price_dataset_reference.get("universe_selection")
        != "FINMIND_COMPLETE_SYMBOLS_V1"
        or price_dataset_reference.get("storage_format") != "JSONL_FULL_V1"
        or price_dataset_reference.get("profile") != "KBAR_1M_V1"
        or price_dataset_reference.get("payload_order") != "TIMESTAMP_SYMBOL"
    ):
        raise ValueError("price Dataset coverage or research boundary drifted")


def _qualification_exclusions(
    *, profile: _SnapshotProfile, qualified_symbols: set[str], session_count: int
) -> list[dict[str, Any]]:
    exclusions = [
        {
            "empty_partition_count": profile.empty_by_symbol[symbol],
            "expected_partition_count": session_count,
            "ready_partition_count": profile.ready_by_symbol[symbol],
            "ready_partition_rate": _rate_text(
                profile.ready_by_symbol[symbol], session_count
            ),
            "reason_code": "SYMBOL_SESSION_READY_COVERAGE_BELOW_0_99",
            "symbol": symbol,
        }
        for symbol in profile.included_symbols
        if symbol not in qualified_symbols
    ]
    for item in profile.excluded_symbols:
        symbol = _text(item.get("symbol"), "excluded symbol")
        missing = item.get("missing_session_dates")
        invalid = item.get("invalid_session_dates")
        if not isinstance(missing, list) or not isinstance(invalid, list):
            raise ValueError("snapshot exclusion session evidence is invalid")
        exclusions.append(
            {
                "invalid_partition_count": len(invalid),
                "missing_partition_count": len(missing),
                "reason_code": "ACQUISITION_SYMBOL_EXCLUDED",
                "source_reason_codes": list(item.get("reason_codes") or []),
                "symbol": symbol,
            }
        )
    return sorted(exclusions, key=lambda item: item["symbol"])


def _candidate_rows(candidate_series: Mapping[str, Any]) -> list[dict[str, str]]:
    references = candidate_series.get("batch_references")
    if not isinstance(references, list) or len(references) < MINIMUM_TARGET_SESSIONS:
        raise ValueError("candidate series has insufficient batch references")
    if _nonnegative_integer(candidate_series.get("batch_count"), "batch count") != len(
        references
    ):
        raise ValueError("candidate series batch count drifted")
    if _nonnegative_integer(
        candidate_series.get("overlapping_target_session_count"),
        "overlapping target session count",
    ) != len(references):
        raise ValueError("candidate series overlapping session count drifted")
    rows: list[dict[str, str]] = []
    source_sessions: list[str] = []
    ordered_targets: list[str] = []
    target_sessions: set[str] = set()
    for reference in references:
        batch = _mapping(reference, "candidate batch reference")
        source_session = _date_text(batch.get("source_session"), "source_session")
        target_session = _date_text(batch.get("target_session"), "target_session")
        if date.fromisoformat(source_session) >= date.fromisoformat(target_session):
            raise ValueError("candidate source session must precede target session")
        if target_session in target_sessions:
            raise ValueError("candidate series target sessions must be unique")
        target_sessions.add(target_session)
        source_sessions.append(source_session)
        ordered_targets.append(target_session)
        candidates = batch.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("candidate series candidates must be a list")
        if _nonnegative_integer(
            batch.get("candidate_count"), "candidate count"
        ) != len(candidates):
            raise ValueError("candidate series candidate count drifted")
        batch_symbols: set[str] = set()
        entry_digests: set[str] = set()
        for rank, candidate in enumerate(candidates, start=1):
            item = _mapping(candidate, "candidate reference")
            symbol = _text(item.get("symbol"), "candidate symbol")
            if symbol in batch_symbols:
                raise ValueError("candidate batch symbols must be unique")
            batch_symbols.add(symbol)
            if _positive_integer(item.get("rank"), "candidate rank") != rank:
                raise ValueError("candidate ranks must be contiguous and ordered")
            entry_digest = _digest(
                item.get("entry_digest"), "candidate entry digest"
            )
            if entry_digest in entry_digests:
                raise ValueError("candidate entry digests must be unique within batch")
            entry_digests.add(entry_digest)
            market = _text(item.get("market"), "candidate market")
            if market not in {"TWSE", "TPEX"}:
                raise ValueError("candidate market is invalid")
            rows.append(
                {
                    "candidate_batch_digest": _digest(
                        batch.get("artifact_digest"), "candidate batch digest"
                    ),
                    "candidate_entry_digest": entry_digest,
                    "market": market,
                    "source_session": source_session,
                    "symbol": symbol,
                    "target_session": target_session,
                }
            )
    if ordered_targets != sorted(ordered_targets):
        raise ValueError("candidate series target sessions must be ordered")
    plan_reference = _mapping(
        candidate_series.get("series_plan_reference"), "series plan reference"
    )
    if _digest(
        plan_reference.get("source_sessions_digest"), "source sessions digest"
    ) != sha256_text(canonical_json(source_sessions)):
        raise ValueError("candidate source sessions digest drifted")
    if _digest(
        plan_reference.get("target_sessions_digest"), "target sessions digest"
    ) != sha256_text(canonical_json(ordered_targets)):
        raise ValueError("candidate target sessions digest drifted")
    return rows


def _market_mapping_counts(profile: _SnapshotProfile) -> dict[str, int]:
    return dict(sorted(Counter(profile.market_by_symbol.values()).items()))


def _with_identity(body: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    digest = sha256_text(canonical_json(body))
    return {
        "artifact_digest": digest,
        "artifact_id": f"{prefix}-{digest[:20]}",
        **body,
    }


def _verify_series_identity(payload: Mapping[str, Any]) -> None:
    _verify_identity(payload, "finmind-institutional-mvp-candidate-series-v1")
    if payload.get("schema_version") != "institutional_mvp_candidate_series_v1":
        raise ValueError("candidate series schema drifted")
    if (
        payload.get("status")
        != "MVP_INSTITUTIONAL_CANDIDATE_SERIES_OBSERVATION_ONLY"
        or payload.get("change_policy") != CHANGE_POLICY
        or payload.get("research_eligibility")
        != {"formal_pit_eligible": False, "research_eligible": False}
        or payload.get("evidence_scope")
        != {
            "backtest_or_holdout_read": False,
            "institutional_flow_fields_read": True,
            "price_or_kbar_read": False,
            "return_or_pnl_read": False,
        }
        or payload.get("execution_permissions")
        != {
            "evaluation_universe_freeze_allowed": False,
            "holdout_execution_allowed": False,
            "institutional_candidate_series_observation_allowed": True,
            "order_submission_allowed": False,
            "outcome_generation_allowed": False,
            "runtime_strategy_binding_allowed": False,
        }
    ):
        raise ValueError("candidate series observation-only authority drifted")
    plan_reference = _mapping(
        payload.get("series_plan_reference"), "series plan reference"
    )
    plan_digest = _digest(
        plan_reference.get("artifact_digest"), "series plan artifact digest"
    )
    if plan_reference.get("artifact_id") != (
        f"finmind-institutional-mvp-series-plan-v1-{plan_digest[:20]}"
    ):
        raise ValueError("candidate series plan identity drifted")


def _verify_identity(payload: Mapping[str, Any], prefix: str) -> None:
    identity = dict(payload)
    digest = _digest(identity.pop("artifact_digest", None), "artifact_digest")
    artifact_id = _text(identity.pop("artifact_id", None), "artifact_id")
    if sha256_text(canonical_json(identity)) != digest:
        raise ValueError("artifact digest mismatch")
    if artifact_id != f"{prefix}-{digest[:20]}":
        raise ValueError("artifact id mismatch")


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be canonical non-empty text")
    return value


def _date_text(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a canonical ISO date") from error
    if parsed.isoformat() != text:
        raise ValueError(f"{field_name} must be a canonical ISO date")
    return text


def _text_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = tuple(_text(item, field_name) for item in value)
    if not result or tuple(sorted(set(result))) != result:
        raise ValueError(f"{field_name} must be canonical and non-empty")
    return result


def _date_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = tuple(_date_text(item, field_name) for item in value)
    if tuple(sorted(set(result))) != result:
        raise ValueError(f"{field_name} must be canonical")
    return result


def _digest(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field_name} must be lowercase SHA-256")
    return text


def _nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    parsed = _nonnegative_integer(value, field_name)
    if parsed == 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _decimal_rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise ValueError("coverage rate counts are invalid")
    return Decimal(numerator) / Decimal(denominator)


def _rate_text(numerator: int, denominator: int) -> str:
    return format(_decimal_rate(numerator, denominator), ".12f")


def _rate_text_or_zero(numerator: int, denominator: int) -> str:
    if denominator == 0:
        if numerator != 0:
            raise ValueError("coverage rate counts are invalid")
        return "0.000000000000"
    return _rate_text(numerator, denominator)
