"""Frozen-input, non-formal offline A/B diagnostic for the institutional MVP."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog
from backtest.domain import (
    AggregationPolicy,
    BacktestRunConfig,
    HistoricalBar,
    StrategySetSnapshot,
    digest as backtest_digest,
)
from backtest.engine import BacktestEngineResult
from backtest.finmind_snapshot import FinMindSnapshotPlan
from backtest.strategies import StrategyRegistry
from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.evaluation import (
    FORMAL_PROTOCOL_DIGEST,
    MINIMUM_TARGET_SESSIONS,
    qualified_symbols_for_mvp,
)


PLAN_SCHEMA_VERSION = "institutional_mvp_offline_ab_plan_v1"
RESULT_SCHEMA_VERSION = "institutional_mvp_offline_ab_result_v1"
PLAN_STATUS = "FROZEN_NON_FORMAL_OFFLINE_AB_INPUTS"
RESULT_STATUS = "NON_FORMAL_MVP_OBSERVATION_ONLY"
CHANGE_POLICY = "IMMUTABLE_APPEND_ONLY_REVISIONS"
PLAN_PREFIX = "institutional-mvp-offline-ab-plan-v1"
RESULT_PREFIX = "institutional-mvp-offline-ab-result-v1"

_ENTRY_STRATEGY = "legacy_gap_volume_vwap_entry_v1"
_EXIT_STRATEGIES = (
    "stop_loss_exit_v1",
    "take_profit_exit_v1",
    "end_of_day_exit_v1",
)
_PRIORITY = _EXIT_STRATEGIES
_SOURCE_PATHS = (
    "backtest/dataset.py",
    "backtest/domain.py",
    "backtest/engine.py",
    "backtest/strategies.py",
    "institutional_mvp/diagnostic.py",
    "institutional_mvp/evaluation.py",
    "institutional_mvp/series.py",
    "scripts/run_finmind_mvp_offline_diagnostic.py",
)
_PLAN_PERMISSIONS = {
    "formal_outcome_generation_allowed": False,
    "holdout_execution_allowed": False,
    "non_formal_offline_ab_execution_allowed": True,
    "order_submission_allowed": False,
    "production_allowed": False,
    "provider_call_allowed": False,
    "runtime_strategy_binding_allowed": False,
}
_RESULT_PERMISSIONS = {
    "formal_outcome_generation_allowed": False,
    "holdout_execution_allowed": False,
    "order_submission_allowed": False,
    "production_allowed": False,
    "provider_call_allowed": False,
    "runtime_strategy_binding_allowed": False,
}
_LIMITATIONS = (
    "NON_FORMAL_MVP_DIAGNOSTIC_ONLY",
    "NO_CAUSAL_OR_FULL_MARKET_CLAIM",
    "NO_FORMAL_TRAIN_VALIDATION_HOLDOUT_SPLIT",
    "CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED",
    "FORMAL_PIT_UNIVERSE_NOT_AVAILABLE",
    "RAW_PRICE_UNADJUSTED",
    "AMOUNT_DERIVED_PROXY",
    "FINMIND_VOLUME_COMMON_LOTS_LEGACY_THRESHOLD_LABEL_MISMATCH",
    "REFERENCE_METADATA_CURRENT_NOT_PIT",
    "CANDIDATE_SYMBOL_COVERAGE_BELOW_FORMAL_THRESHOLD",
    "CANDIDATE_EXCLUSIONS_CONCENTRATED_BY_MARKET",
)


class InstitutionalMvpDiagnosticError(RuntimeError):
    """A non-formal diagnostic input or result failed closed."""


@dataclass(frozen=True)
class FrozenCatalogBarView:
    """Read-only window over one immutable Catalog Dataset."""

    catalog: HistoricalDatasetCatalog
    plan: Mapping[str, Any]

    @property
    def dataset_id(self) -> str:
        return _text(
            _mapping(self.plan.get("price_dataset_reference"), "price reference").get(
                "dataset_id"
            ),
            "dataset_id",
        )

    @property
    def total_bar_count(self) -> int:
        return _positive_integer(
            _mapping(self.plan.get("bar_view"), "bar_view").get(
                "expected_bar_count"
            ),
            "expected_bar_count",
        )

    @property
    def terminal_timestamp_by_symbol(self) -> dict[str, datetime]:
        rows = _sequence(
            _mapping(self.plan.get("bar_view"), "bar_view").get(
                "terminal_timestamps"
            ),
            "terminal_timestamps",
        )
        output: dict[str, datetime] = {}
        for item in rows:
            row = _mapping(item, "terminal timestamp")
            symbol = _text(row.get("symbol"), "terminal symbol")
            timestamp = datetime.fromisoformat(
                _text(row.get("timestamp"), "terminal timestamp")
            )
            if timestamp.utcoffset() is None or symbol in output:
                raise InstitutionalMvpDiagnosticError(
                    "diagnostic terminal timestamp contract drifted"
                )
            output[symbol] = timestamp
        return output

    def iter_bars(self) -> Iterator[HistoricalBar]:
        _verify_plan_identity(self.plan)
        view = _mapping(self.plan.get("bar_view"), "bar_view")
        symbols = set(_text_sequence(view.get("symbols"), "bar_view symbols"))
        sessions = set(_date_sequence(view.get("context_sessions"), "context sessions"))
        expected_terminals = self.terminal_timestamp_by_symbol
        observed_terminals: dict[str, datetime] = {}
        count = 0
        for bar in self.catalog.iter_bars_ordered(self.dataset_id):
            session = bar.session_date or bar.timestamp.date()
            if bar.symbol not in symbols or session not in sessions:
                continue
            count += 1
            observed_terminals[bar.symbol] = bar.timestamp
            yield bar
        if count != self.total_bar_count:
            raise InstitutionalMvpDiagnosticError(
                "frozen Catalog view bar count differs from metadata plan"
            )
        if observed_terminals != expected_terminals:
            raise InstitutionalMvpDiagnosticError(
                "frozen Catalog view terminal timestamps differ from metadata plan"
            )


def source_code_identities(project_root: Path) -> list[dict[str, str]]:
    """Hash the exact source bytes that define the diagnostic replay."""
    root = Path(project_root)
    rows: list[dict[str, str]] = []
    for relative in _SOURCE_PATHS:
        path = root / relative
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return rows


def build_offline_ab_plan(
    *,
    price_dataset_reference: Mapping[str, Any],
    dataset_manifest: DatasetManifest | Mapping[str, Any],
    snapshot_plan: FinMindSnapshotPlan,
    candidate_series: Mapping[str, Any],
    coverage_audit: Mapping[str, Any],
    evaluation_universe: Mapping[str, Any],
    formal_protocol: Mapping[str, Any],
    code_identities: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Freeze every A/B input before price values or outcomes are opened."""
    manifest = (
        dataset_manifest.to_dict()
        if isinstance(dataset_manifest, DatasetManifest)
        else dict(dataset_manifest)
    )
    _verify_manifest_binding(manifest, price_dataset_reference)
    _verify_upstream_artifacts(
        price_dataset_reference=price_dataset_reference,
        candidate_series=candidate_series,
        coverage_audit=coverage_audit,
        evaluation_universe=evaluation_universe,
    )
    strategy_contract, cost_model = _verify_formal_strategy_contract(formal_protocol)
    identities = _canonical_code_identities(code_identities)

    qualified_symbols = qualified_symbols_for_mvp(snapshot_plan)
    if (
        price_dataset_reference.get("selection_audit_digest")
        != snapshot_plan.selection_audit_digest
        or price_dataset_reference.get("plan_identity_digest")
        != snapshot_plan.plan_identity_digest
    ):
        raise InstitutionalMvpDiagnosticError(
            "price reference differs from the frozen snapshot plan"
        )
    qualification = _mapping(
        coverage_audit.get("symbol_qualification"), "symbol_qualification"
    )
    if (
        qualification.get("qualified_symbol_count") != len(qualified_symbols)
        or qualification.get("qualified_symbol_digest")
        != sha256_text(canonical_json(qualified_symbols))
    ):
        raise InstitutionalMvpDiagnosticError(
            "qualified price symbols differ from the coverage audit"
        )

    membership = _sequence(evaluation_universe.get("membership"), "membership")
    target_sessions = tuple(
        sorted({_date_text(_mapping(row, "membership").get("target_session"), "target_session") for row in membership})
    )
    if len(target_sessions) < MINIMUM_TARGET_SESSIONS:
        raise InstitutionalMvpDiagnosticError(
            "offline A/B requires at least 60 frozen target sessions"
        )
    membership_pairs = tuple(
        sorted(
            (
                _date_text(_mapping(row, "membership").get("target_session"), "target_session"),
                _text(_mapping(row, "membership").get("symbol"), "membership symbol"),
            )
            for row in membership
        )
    )
    if len(set(membership_pairs)) != len(membership_pairs):
        raise InstitutionalMvpDiagnosticError("frozen membership must be unique")

    source_by_target: dict[str, str] = {}
    for raw in _sequence(candidate_series.get("batch_references"), "batch_references"):
        row = _mapping(raw, "batch reference")
        source = _date_text(row.get("source_session"), "source_session")
        target = _date_text(row.get("target_session"), "target_session")
        previous = source_by_target.setdefault(target, source)
        if previous != source:
            raise InstitutionalMvpDiagnosticError(
                "candidate series target session has conflicting source sessions"
            )
    if set(source_by_target) != set(target_sessions):
        raise InstitutionalMvpDiagnosticError(
            "candidate series sessions differ from the frozen universe"
        )

    source_sessions = tuple(source_by_target[target] for target in target_sessions)
    trading_dates = tuple(
        _date_text(value, "snapshot trading date")
        for value in _sequence(
            _mapping(snapshot_plan.identity.get("source_contract"), "source_contract").get(
                "trading_dates"
            ),
            "trading_dates",
        )
    )
    trading_index = {session: index for index, session in enumerate(trading_dates)}
    for source, target in zip(source_sessions, target_sessions):
        target_index = trading_index.get(target)
        if (
            target_index is None
            or target_index == 0
            or trading_dates[target_index - 1] != source
        ):
            raise InstitutionalMvpDiagnosticError(
                "diagnostic source/target sessions differ from Dataset order"
            )
    context_set = set(source_sessions) | set(target_sessions)
    context_sessions = tuple(session for session in trading_dates if session in context_set)
    if len(context_sessions) != len(context_set):
        raise InstitutionalMvpDiagnosticError(
            "diagnostic context sessions are outside the Dataset"
        )
    bar_view = _build_bar_view(
        snapshot_plan=snapshot_plan,
        symbols=qualified_symbols,
        context_sessions=context_sessions,
    )

    body: dict[str, Any] = {
        "arms": {
            "institutional_filter": {
                "entry_eligibility_count": len(membership_pairs),
                "entry_eligibility_digest": sha256_text(
                    canonical_json(membership_pairs)
                ),
                "rule": "EXACT_FROZEN_TARGET_SESSION_SYMBOL_MEMBERSHIP",
            },
            "price_only": {
                "entry_eligibility_count": len(qualified_symbols)
                * len(target_sessions),
                "rule": "QUALIFIED_PRICE_SYMBOL_X_FROZEN_TARGET_SESSION",
            },
        },
        "authority": "OWNER_AUTHORIZED_PR_MVP_EVAL_005_NON_FORMAL_OFFLINE_AB_ONLY",
        "bar_view": bar_view,
        "candidate_series_reference": _artifact_reference(candidate_series),
        "change_policy": CHANGE_POLICY,
        "code_identities": identities,
        "comparison_contract": {
            "only_permitted_arm_difference": "ENTRY_ELIGIBILITY_PREDICATE",
            "outcome_scope": "ALL_60_FROZEN_TARGET_SESSIONS_NO_HOLDOUT_CLAIM",
            "price_bars_strategy_cost_capital_and_exits_identical": True,
        },
        "coverage_audit_reference": _artifact_reference(coverage_audit),
        "evidence_scope": {
            "holdout_read": False,
            "outcome_read_before_plan_freeze": False,
            "price_or_kbar_value_read_before_plan_freeze": False,
            "provider_call_performed": False,
        },
        "evaluation_universe_reference": _artifact_reference(evaluation_universe),
        "execution_permissions": dict(_PLAN_PERMISSIONS),
        "formal_protocol_reference": {
            "canonical_sha256": FORMAL_PROTOCOL_DIGEST,
            "status": "STRATEGY_AND_COST_IDENTITY_REFERENCE_ONLY_NOT_FORMAL_RUN",
        },
        "limitations": list(_LIMITATIONS),
        "membership": {
            "membership_count": len(membership_pairs),
            "membership_digest": sha256_text(canonical_json(membership_pairs)),
            "qualified_price_symbol_count": len(qualified_symbols),
            "qualified_price_symbol_digest": sha256_text(
                canonical_json(qualified_symbols)
            ),
            "target_session_count": len(target_sessions),
            "target_session_digest": sha256_text(canonical_json(target_sessions)),
            "target_sessions": list(target_sessions),
        },
        "price_dataset_reference": dict(price_dataset_reference),
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": PLAN_STATUS,
        "strategy_contract": strategy_contract,
        "transaction_cost_model": cost_model,
    }
    return _with_identity(body, PLAN_PREFIX)


def verify_offline_ab_plan(
    payload: Mapping[str, Any],
    **dependencies: Any,
) -> None:
    _verify_plan_identity(payload)
    expected = build_offline_ab_plan(**dependencies)
    if dict(payload) != expected:
        raise InstitutionalMvpDiagnosticError(
            "offline A/B plan differs from exact dependency reconstruction"
        )


def build_run_config(plan: Mapping[str, Any]) -> BacktestRunConfig:
    """Reconstitute the one unchanged price strategy configuration."""
    _verify_plan_identity(plan)
    price = _mapping(plan.get("price_dataset_reference"), "price reference")
    contract = _mapping(plan.get("strategy_contract"), "strategy_contract")
    costs = _mapping(plan.get("transaction_cost_model"), "cost model")
    position = _mapping(contract.get("position_policy"), "position_policy")
    return BacktestRunConfig(
        dataset_id=_text(price.get("dataset_id"), "dataset_id"),
        dataset_digest=_digest(price.get("manifest_digest"), "manifest_digest"),
        strategy_set=StrategySetSnapshot(
            entry_strategy_ids=(_ENTRY_STRATEGY,),
            exit_strategy_ids=_EXIT_STRATEGIES,
            entry_policy=AggregationPolicy.ANY,
            exit_policy=AggregationPolicy.ANY,
            priority_order=_PRIORITY,
        ),
        starting_cash=Decimal(
            _text(position.get("starting_cash_twd"), "starting_cash_twd")
        ),
        position_fraction=Decimal(
            _text(position.get("position_fraction"), "position_fraction")
        ),
        commission_rate=Decimal(
            _text(costs.get("commission_rate"), "commission_rate")
        ),
        sell_tax_rate=Decimal(
            _text(costs.get("sell_tax_rate"), "sell_tax_rate")
        ),
        slippage_bps=Decimal(
            _text(costs.get("slippage_bps_each_fill"), "slippage_bps_each_fill")
        ),
        min_lot_shares=_positive_integer(
            position.get("minimum_lot_shares"), "minimum_lot_shares"
        ),
        engine_version="backtest-engine-v2",
        experiment_id="pr-mvp-eval-005-non-formal-offline-ab",
        research_baseline_digest=FORMAL_PROTOCOL_DIGEST,
        change_note="Frozen non-formal institutional outer-filter diagnostic",
        dataset_amount_contract=dict(
            _mapping(
                _mapping(plan.get("bar_view"), "bar_view").get("amount_contract"),
                "amount_contract",
            )
        ),
    )


def price_only_entry_eligibility(plan: Mapping[str, Any]):
    view = _mapping(plan.get("bar_view"), "bar_view")
    symbols = set(_text_sequence(view.get("symbols"), "bar_view symbols"))
    sessions = set(
        _date_sequence(
            _mapping(plan.get("membership"), "membership").get("target_sessions"),
            "target_sessions",
        )
    )
    return lambda session, symbol: session in sessions and symbol in symbols


def institutional_entry_eligibility(plan: Mapping[str, Any], universe: Mapping[str, Any]):
    if _artifact_reference(universe) != plan.get("evaluation_universe_reference"):
        raise InstitutionalMvpDiagnosticError(
            "execution universe differs from the frozen diagnostic plan"
        )
    pairs = {
        (
            date.fromisoformat(
                _date_text(_mapping(row, "membership").get("target_session"), "target_session")
            ),
            _text(_mapping(row, "membership").get("symbol"), "membership symbol"),
        )
        for row in _sequence(universe.get("membership"), "membership")
    }
    membership = _mapping(plan.get("membership"), "membership")
    pair_projection = tuple(sorted((session.isoformat(), symbol) for session, symbol in pairs))
    if (
        len(pairs)
        != _positive_integer(membership.get("membership_count"), "membership_count")
        or sha256_text(canonical_json(pair_projection))
        != membership.get("membership_digest")
    ):
        raise InstitutionalMvpDiagnosticError(
            "execution membership differs from the frozen diagnostic plan"
        )
    return lambda session, symbol: (session, symbol) in pairs


def build_offline_ab_result(
    *,
    plan: Mapping[str, Any],
    evaluation_universe: Mapping[str, Any],
    price_only_result: BacktestEngineResult,
    institutional_result: BacktestEngineResult,
) -> dict[str, Any]:
    """Publish deterministic observations without a formal PASS/FAIL claim."""
    _verify_plan_identity(plan)
    _verify_identity(evaluation_universe, "finmind-mvp-evaluation-universe-v1")
    if _artifact_reference(evaluation_universe) != plan.get(
        "evaluation_universe_reference"
    ):
        raise InstitutionalMvpDiagnosticError(
            "result universe differs from the frozen diagnostic plan"
        )
    institutional_entry_eligibility(plan, evaluation_universe)
    target_sessions = tuple(
        _date_sequence(
            _mapping(plan.get("membership"), "membership").get("target_sessions"),
            "target_sessions",
        )
    )
    price_symbols = set(
        _text_sequence(
            _mapping(plan.get("bar_view"), "bar_view").get("symbols"),
            "bar_view symbols",
        )
    )
    membership_pairs = {
        (
            date.fromisoformat(
                _date_text(_mapping(row, "membership").get("target_session"), "target_session")
            ),
            _text(_mapping(row, "membership").get("symbol"), "membership symbol"),
        )
        for row in _sequence(evaluation_universe.get("membership"), "membership")
    }
    position = _mapping(
        _mapping(plan.get("strategy_contract"), "strategy_contract").get(
            "position_policy"
        ),
        "position_policy",
    )
    starting_cash = Decimal(
        _text(position.get("starting_cash_twd"), "starting_cash_twd")
    )
    price_summary = _summarize_arm(
        result=price_only_result,
        target_sessions=set(target_sessions),
        eligible=lambda session, symbol: session in set(target_sessions)
        and symbol in price_symbols,
        starting_cash=starting_cash,
    )
    institutional_summary = _summarize_arm(
        result=institutional_result,
        target_sessions=set(target_sessions),
        eligible=lambda session, symbol: (session, symbol) in membership_pairs,
        starting_cash=starting_cash,
    )
    comparison = _comparison(price_summary, institutional_summary)
    body: dict[str, Any] = {
        "arms": {
            "institutional_filter": institutional_summary,
            "price_only": price_summary,
        },
        "change_policy": CHANGE_POLICY,
        "comparison": comparison,
        "diagnostic_plan_reference": _artifact_reference(plan),
        "evidence_scope": {
            "holdout_read": False,
            "non_formal_outcome_generated": True,
            "price_or_kbar_value_read": True,
            "provider_call_performed": False,
        },
        "execution_permissions": dict(_RESULT_PERMISSIONS),
        "formal_protocol_reference": dict(plan["formal_protocol_reference"]),
        "limitations": list(plan["limitations"]),
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": RESULT_STATUS,
    }
    return _with_identity(body, RESULT_PREFIX)


def verify_offline_ab_result(
    payload: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    evaluation_universe: Mapping[str, Any],
    price_only_result: BacktestEngineResult,
    institutional_result: BacktestEngineResult,
) -> None:
    _verify_identity(payload, RESULT_PREFIX)
    expected = build_offline_ab_result(
        plan=plan,
        evaluation_universe=evaluation_universe,
        price_only_result=price_only_result,
        institutional_result=institutional_result,
    )
    if dict(payload) != expected:
        raise InstitutionalMvpDiagnosticError(
            "offline A/B result differs from exact engine reconstruction"
        )


def _build_bar_view(
    *,
    snapshot_plan: FinMindSnapshotPlan,
    symbols: tuple[str, ...],
    context_sessions: tuple[str, ...],
) -> dict[str, Any]:
    symbol_set = set(symbols)
    session_set = set(context_sessions)
    selected: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw in _sequence(
        snapshot_plan.identity.get("included_partitions"), "included_partitions"
    ):
        row = _mapping(raw, "included partition")
        symbol = _text(row.get("symbol"), "partition symbol")
        session = _date_text(row.get("session_date"), "partition session")
        if symbol not in symbol_set or session not in session_set:
            continue
        key = (symbol, session)
        if key in selected:
            raise InstitutionalMvpDiagnosticError(
                "diagnostic bar view contains duplicate partitions"
            )
        selected[key] = row
    expected_keys = {(symbol, session) for symbol in symbols for session in context_sessions}
    if set(selected) != expected_keys:
        raise InstitutionalMvpDiagnosticError(
            "diagnostic bar view is missing qualified symbol/session partitions"
        )
    projections: list[dict[str, Any]] = []
    total_bars = 0
    terminal_by_symbol: dict[str, str] = {}
    for key in sorted(selected):
        row = selected[key]
        status = _text(row.get("status"), "partition status")
        bar_count = _nonnegative_integer(row.get("bar_count"), "partition bar_count")
        first = row.get("first_event_at")
        last = row.get("last_event_at")
        if status == "READY":
            if bar_count < 1 or not isinstance(first, str) or not isinstance(last, str):
                raise InstitutionalMvpDiagnosticError(
                    "READY diagnostic partition metadata is invalid"
                )
            total_bars += bar_count
            terminal_by_symbol[key[0]] = last
        elif status == "EMPTY":
            if bar_count != 0 or first is not None or last is not None:
                raise InstitutionalMvpDiagnosticError(
                    "EMPTY diagnostic partition metadata is invalid"
                )
        else:
            raise InstitutionalMvpDiagnosticError(
                "diagnostic bar view requires resolved READY/EMPTY partitions"
            )
        projections.append(
            {
                "bar_count": bar_count,
                "canonical_sha256": _digest(
                    row.get("canonical_sha256"), "partition digest"
                ),
                "first_event_at": first,
                "last_event_at": last,
                "session_date": key[1],
                "status": status,
                "symbol": key[0],
            }
        )
    if not terminal_by_symbol or set(terminal_by_symbol) != set(symbols):
        raise InstitutionalMvpDiagnosticError(
            "diagnostic bar view lacks a terminal bar for a qualified symbol"
        )
    amount_contract = dict(
        _mapping(snapshot_plan.identity.get("amount_contract"), "amount_contract")
    )
    volume_contract = dict(
        _mapping(snapshot_plan.identity.get("volume_contract"), "volume_contract")
    )
    amount_body = dict(amount_contract)
    amount_digest = _digest(amount_body.pop("digest", None), "amount digest")
    expected_amount_body = {
        "is_actual_turnover": False,
        "kind": "DERIVED_CLOSE_X_VOLUME_PROXY",
        "vwap_semantic": "COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY",
    }
    if (
        sha256_text(canonical_json(amount_body)) != amount_digest
        or amount_body != expected_amount_body
        or volume_contract != {"unit": "COMMON_LOTS"}
    ):
        raise InstitutionalMvpDiagnosticError(
            "Dataset amount or volume semantics differ from the approved MVP contract"
        )
    return {
        "amount_contract": amount_contract,
        "context_session_count": len(context_sessions),
        "context_session_digest": sha256_text(canonical_json(context_sessions)),
        "context_sessions": list(context_sessions),
        "expected_bar_count": total_bars,
        "partition_count": len(projections),
        "partition_projection_digest": sha256_text(canonical_json(projections)),
        "symbols": list(symbols),
        "terminal_timestamps": [
            {"symbol": symbol, "timestamp": terminal_by_symbol[symbol]}
            for symbol in symbols
        ],
        "volume_contract": volume_contract,
    }


def _verify_manifest_binding(
    manifest: Mapping[str, Any], price_reference: Mapping[str, Any]
) -> None:
    stored_digest = _digest(manifest.get("manifest_digest"), "manifest_digest")
    if DatasetManifest.from_dict(manifest).manifest_digest != stored_digest:
        raise InstitutionalMvpDiagnosticError("Dataset manifest digest drifted")
    expected = {
        "bar_count": manifest.get("bar_count"),
        "bars_sha256": manifest.get("bars_sha256"),
        "dataset_id": manifest.get("dataset_id"),
        "end_date": manifest.get("end_date"),
        "issues": manifest.get("issues"),
        "manifest_digest": stored_digest,
        "observed_symbol_count": len(
            _text_sequence(manifest.get("observed_symbols"), "observed_symbols")
        ),
        "payload_order": manifest.get("payload_order"),
        "plan_identity_digest": manifest.get("plan_identity_digest"),
        "profile": manifest.get("profile"),
        "research_eligible": manifest.get("research_eligible"),
        "selection_audit_digest": price_reference.get(
            "selection_audit_digest"
        ),
        "source": manifest.get("source"),
        "source_snapshot_digest": manifest.get("source_snapshot_digest"),
        "start_date": manifest.get("start_date"),
        "storage_format": manifest.get("storage_format"),
        "universe_scope": manifest.get("universe_scope"),
        "universe_selection": manifest.get("universe_selection"),
    }
    if expected != dict(price_reference):
        raise InstitutionalMvpDiagnosticError(
            "Dataset manifest differs from the approved price reference"
        )
    if (
        manifest.get("research_eligible") is not False
        or manifest.get("payload_order") != "TIMESTAMP_SYMBOL"
        or manifest.get("storage_format") != "JSONL_FULL_V1"
        or manifest.get("profile") != "KBAR_1M_V1"
    ):
        raise InstitutionalMvpDiagnosticError(
            "Dataset is outside the approved non-formal streaming contract"
        )


def _verify_upstream_artifacts(
    *,
    price_dataset_reference: Mapping[str, Any],
    candidate_series: Mapping[str, Any],
    coverage_audit: Mapping[str, Any],
    evaluation_universe: Mapping[str, Any],
) -> None:
    _verify_identity(
        candidate_series, "finmind-institutional-mvp-candidate-series-v1"
    )
    _verify_identity(coverage_audit, "finmind-mvp-price-coverage-audit-v1")
    _verify_identity(evaluation_universe, "finmind-mvp-evaluation-universe-v1")
    if (
        candidate_series.get("schema_version")
        != "institutional_mvp_candidate_series_v1"
        or candidate_series.get("status")
        != "MVP_INSTITUTIONAL_CANDIDATE_SERIES_OBSERVATION_ONLY"
        or coverage_audit.get("schema_version")
        != "finmind_mvp_price_coverage_audit_v1"
        or coverage_audit.get("status") != "PASS_FOR_NON_FORMAL_MVP_FREEZE_ONLY"
        or evaluation_universe.get("schema_version") != "mvp_evaluation_universe_v1"
        or evaluation_universe.get("status") != "FROZEN_NON_FORMAL_MVP"
    ):
        raise InstitutionalMvpDiagnosticError("upstream MVP authority drifted")
    if (
        coverage_audit.get("price_dataset_reference")
        != dict(price_dataset_reference)
        or evaluation_universe.get("price_dataset_reference")
        != dict(price_dataset_reference)
        or evaluation_universe.get("coverage_audit_reference")
        != _artifact_reference(coverage_audit)
        or coverage_audit.get("candidate_series_reference", {}).get(
            "artifact_digest"
        )
        != candidate_series.get("artifact_digest")
    ):
        raise InstitutionalMvpDiagnosticError("upstream MVP lineage drifted")
    for artifact in (coverage_audit, evaluation_universe, candidate_series):
        permissions = _mapping(
            artifact.get("execution_permissions"), "upstream permissions"
        )
        if any(
            permissions.get(field) is True
            for field in (
                "formal_population_freeze_allowed",
                "outcome_generation_allowed",
                "holdout_execution_allowed",
                "runtime_strategy_binding_allowed",
                "order_submission_allowed",
                "production_allowed",
            )
        ):
            raise InstitutionalMvpDiagnosticError(
                "upstream artifact carries forbidden execution authority"
            )
    membership = _sequence(evaluation_universe.get("membership"), "membership")
    if (
        evaluation_universe.get("membership_count") != len(membership)
        or evaluation_universe.get("membership_digest")
        != sha256_text(canonical_json(membership))
    ):
        raise InstitutionalMvpDiagnosticError("frozen universe membership drifted")


def _verify_formal_strategy_contract(
    protocol: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_text(canonical_json(protocol)) != FORMAL_PROTOCOL_DIGEST:
        raise InstitutionalMvpDiagnosticError("formal protocol digest drifted")
    lock = _mapping(protocol.get("execution_lock"), "formal execution_lock")
    if any(lock.get(field) is not False for field in (
        "holdout_execution_allowed",
        "holdout_outcome_materialization_allowed",
        "outcome_generation_allowed",
    )):
        raise InstitutionalMvpDiagnosticError("formal protocol lock drifted")
    contract = dict(_mapping(protocol.get("strategy_contract"), "strategy_contract"))
    cost = dict(
        _mapping(protocol.get("transaction_cost_model"), "transaction_cost_model")
    )
    expected_entries = [
        {
            "definition_digest": StrategyRegistry()
            .definition(_ENTRY_STRATEGY)
            .definition_digest,
            "strategy_id": _ENTRY_STRATEGY,
            "version": "v1",
        }
    ]
    expected_exits = [
        {
            "definition_digest": StrategyRegistry().definition(strategy).definition_digest,
            "strategy_id": strategy,
            "version": "v1",
        }
        for strategy in _EXIT_STRATEGIES
    ]
    if (
        contract.get("entry_strategies") != expected_entries
        or contract.get("exit_strategies") != expected_exits
        or contract.get("priority_order") != list(_PRIORITY)
        or contract.get("entry_policy") != "ANY"
        or contract.get("exit_policy") != "ANY"
        or contract.get("holding_period") != "INTRADAY_FLAT_BY_END_OF_DAY"
        or cost
        != {
            "commission_rate": "0.001425",
            "cost_model_id": "tw_equity_intraday_cost_v1",
            "sell_tax_rate": "0.003",
            "slippage_bps_each_fill": "5",
        }
    ):
        raise InstitutionalMvpDiagnosticError(
            "current strategy or cost identity differs from the frozen protocol"
        )
    return contract, cost


def _canonical_code_identities(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    output = [
        {
            "path": _text(row.get("path"), "code path"),
            "sha256": _digest(row.get("sha256"), "code sha256"),
        }
        for row in rows
    ]
    output.sort(key=lambda row: row["path"])
    if tuple(row["path"] for row in output) != tuple(sorted(_SOURCE_PATHS)):
        raise InstitutionalMvpDiagnosticError("diagnostic source identity set drifted")
    return output


def _summarize_arm(
    *,
    result: BacktestEngineResult,
    target_sessions: set[date],
    eligible,
    starting_cash: Decimal,
) -> dict[str, Any]:
    if result.unresolved_positions:
        raise InstitutionalMvpDiagnosticError(
            "diagnostic engine result contains unresolved positions"
        )
    trades: list[dict[str, Any]] = []
    session_values = {session: [] for session in sorted(target_sessions)}
    for trade in result.trades:
        session = trade.entry_decision.event_at.date()
        if session not in target_sessions or not eligible(session, trade.symbol):
            raise InstitutionalMvpDiagnosticError(
                "engine produced a trade outside the frozen arm eligibility"
            )
        if trade.exit_fill.filled_at.date() != session:
            raise InstitutionalMvpDiagnosticError(
                "diagnostic trade violated the intraday-flat contract"
            )
        projection = {
            "entry_at": trade.entry_fill.filled_at.isoformat(),
            "entry_price": str(trade.entry_fill.price),
            "entry_signal_at": trade.entry_decision.event_at.isoformat(),
            "exit_at": trade.exit_fill.filled_at.isoformat(),
            "exit_price": str(trade.exit_fill.price),
            "exit_strategy_id": trade.exit_decision.primary_strategy_id,
            "gross_pnl": str(trade.gross_pnl),
            "net_pnl": str(trade.net_pnl),
            "shares": trade.entry_fill.shares,
            "symbol": trade.symbol,
            "total_cost": str(
                trade.entry_fill.total_cost + trade.exit_fill.total_cost
            ),
        }
        trades.append(projection)
        session_values[session].append(trade.net_pnl)
    net_values = [Decimal(row["net_pnl"]) for row in trades]
    gross_values = [Decimal(row["gross_pnl"]) for row in trades]
    costs = [Decimal(row["total_cost"]) for row in trades]
    wins = sum(value > 0 for value in net_values)
    losses = sum(value < 0 for value in net_values)
    gross_profit = sum((value for value in net_values if value > 0), Decimal(0))
    gross_loss = -sum((value for value in net_values if value < 0), Decimal(0))
    count = len(trades)
    win_rate = Decimal(wins) / Decimal(count) if count else Decimal(0)
    expectancy = sum(net_values, Decimal(0)) / Decimal(count) if count else Decimal(0)
    equity_values = [point.equity for point in result.daily_equity]
    peak = starting_cash
    max_drawdown = Decimal(0)
    for value in equity_values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    final_equity = equity_values[-1] if equity_values else starting_cash
    per_session = [
        {
            "closed_trade_count": len(session_values[session]),
            "net_pnl": str(sum(session_values[session], Decimal(0))),
            "session": session.isoformat(),
        }
        for session in sorted(session_values)
    ]
    return {
        "closed_trade_count": count,
        "decision_count": len(result.decisions),
        "engine_result_digest": backtest_digest(result.to_dict()),
        "expectancy_twd": _decimal_text(expectancy),
        "final_equity_twd": str(final_equity),
        "gross_pnl_twd": str(sum(gross_values, Decimal(0))),
        "loss_count": losses,
        "max_drawdown_rate": _decimal_text(max_drawdown),
        "net_pnl_twd": str(sum(net_values, Decimal(0))),
        "order_count": len(result.orders),
        "per_session": per_session,
        "per_session_digest": sha256_text(canonical_json(per_session)),
        "profit_factor": (
            _decimal_text(gross_profit / gross_loss) if gross_loss > 0 else None
        ),
        "total_explicit_cost_twd": str(sum(costs, Decimal(0))),
        "total_return_rate": _decimal_text(
            (final_equity - starting_cash) / starting_cash
            if starting_cash
            else Decimal(0)
        ),
        "trade_observation_digest": sha256_text(canonical_json(trades)),
        "unresolved_position_count": len(result.unresolved_positions),
        "win_count": wins,
        "win_rate": _decimal_text(win_rate),
    }


def _comparison(
    price: Mapping[str, Any], institutional: Mapping[str, Any]
) -> dict[str, Any]:
    price_count = int(price["closed_trade_count"])
    institutional_count = int(institutional["closed_trade_count"])
    return {
        "closed_trade_count_delta": institutional_count - price_count,
        "expectancy_twd_delta": _decimal_text(
            Decimal(institutional["expectancy_twd"])
            - Decimal(price["expectancy_twd"])
        ),
        "interpretation": "OBSERVED_ASSOCIATION_ONLY_NO_FORMAL_INFERENCE",
        "max_drawdown_rate_delta": _decimal_text(
            Decimal(institutional["max_drawdown_rate"])
            - Decimal(price["max_drawdown_rate"])
        ),
        "net_pnl_twd_delta": str(
            Decimal(institutional["net_pnl_twd"])
            - Decimal(price["net_pnl_twd"])
        ),
        "total_return_rate_delta": _decimal_text(
            Decimal(institutional["total_return_rate"])
            - Decimal(price["total_return_rate"])
        ),
        "trade_retention_rate": _decimal_text(
            Decimal(institutional_count) / Decimal(price_count)
            if price_count
            else Decimal(0)
        ),
        "win_rate_delta": _decimal_text(
            Decimal(institutional["win_rate"]) - Decimal(price["win_rate"])
        ),
    }


def _verify_plan_identity(payload: Mapping[str, Any]) -> None:
    _verify_identity(payload, PLAN_PREFIX)
    if (
        payload.get("schema_version") != PLAN_SCHEMA_VERSION
        or payload.get("status") != PLAN_STATUS
        or payload.get("change_policy") != CHANGE_POLICY
        or payload.get("execution_permissions") != _PLAN_PERMISSIONS
        or payload.get("research_eligibility")
        != {"formal_pit_eligible": False, "research_eligible": False}
    ):
        raise InstitutionalMvpDiagnosticError("offline A/B plan authority drifted")


def _artifact_reference(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "artifact_digest": _digest(payload.get("artifact_digest"), "artifact_digest"),
        "artifact_id": _text(payload.get("artifact_id"), "artifact_id"),
    }


def _with_identity(body: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    digest = sha256_text(canonical_json(body))
    return {
        "artifact_digest": digest,
        "artifact_id": f"{prefix}-{digest[:20]}",
        **body,
    }


def _verify_identity(payload: Mapping[str, Any], prefix: str) -> None:
    body = dict(payload)
    digest = _digest(body.pop("artifact_digest", None), "artifact_digest")
    artifact_id = _text(body.pop("artifact_id", None), "artifact_id")
    if sha256_text(canonical_json(body)) != digest:
        raise InstitutionalMvpDiagnosticError("diagnostic artifact digest mismatch")
    if artifact_id != f"{prefix}-{digest[:20]}":
        raise InstitutionalMvpDiagnosticError("diagnostic artifact id mismatch")


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstitutionalMvpDiagnosticError(f"{field_name} must be an object")
    return value


def _sequence(value: object, field_name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise InstitutionalMvpDiagnosticError(f"{field_name} must be an array")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise InstitutionalMvpDiagnosticError(
            f"{field_name} must be canonical non-empty text"
        )
    return value


def _digest(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise InstitutionalMvpDiagnosticError(f"{field_name} must be lowercase SHA-256")
    return text


def _date_text(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    if date.fromisoformat(text).isoformat() != text:
        raise InstitutionalMvpDiagnosticError(f"{field_name} must be an ISO date")
    return text


def _text_sequence(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(_text(item, field_name) for item in _sequence(value, field_name))


def _date_sequence(value: object, field_name: str) -> tuple[date, ...]:
    return tuple(
        date.fromisoformat(_date_text(item, field_name))
        for item in _sequence(value, field_name)
    )


def _nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InstitutionalMvpDiagnosticError(
            f"{field_name} must be a nonnegative integer"
        )
    return value


def _positive_integer(value: object, field_name: str) -> int:
    parsed = _nonnegative_integer(value, field_name)
    if parsed < 1:
        raise InstitutionalMvpDiagnosticError(f"{field_name} must be positive")
    return parsed


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001")), "f")
