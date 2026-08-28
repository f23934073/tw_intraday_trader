"""Freeze or execute the provider-free PR-MVP-EVAL-005 offline A/B diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog  # noqa: E402
from backtest.engine import HistoricalBacktestEngine  # noqa: E402
from backtest.finmind_snapshot import FinMindSnapshotPlan  # noqa: E402
from config import twse_calendar_2026  # noqa: E402
from config.institutional_mvp import (  # noqa: E402
    DEFAULT_CANDIDATE_SERIES,
    DEFAULT_CANDIDATE_SERIES_PLAN,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PRICE_DATASET_MANIFEST,
    DEFAULT_PRICE_DATASET_PLAN,
    load_daily_policy,
)
from institutional_mvp.diagnostic import (  # noqa: E402
    FrozenCatalogBarView,
    InstitutionalMvpDiagnosticError,
    build_offline_ab_plan,
    build_offline_ab_result,
    build_run_config,
    institutional_entry_eligibility,
    price_only_entry_eligibility,
    source_code_identities,
    verify_offline_ab_plan,
    verify_offline_ab_result,
)
from institutional_mvp.evaluation import (  # noqa: E402
    verify_mvp_evaluation_universe,
    verify_mvp_price_coverage_audit,
)
from institutional_mvp.series import (  # noqa: E402
    InstitutionalMvpSeriesError,
    load_canonical_artifact,
    publish_content_addressed_json,
    verify_candidate_series_manifest,
    verify_candidate_series_plan,
)
from market_data.equity_calendar import ReviewedEquityCalendar  # noqa: E402
from scripts.build_finmind_mvp_evaluation_universe import (  # noqa: E402
    _load_exact_batches,
)
from scripts.run_finmind_institutional_mvp_series import (  # noqa: E402
    load_price_dataset_reference,
)


DEFAULT_COVERAGE_AUDIT = (
    DEFAULT_OUTPUT_ROOT
    / "coverage_audits/8c60c80a18b3c4aecdaaaff547231203b54361718d4d8638f1ee400ee1690470.json"
)
DEFAULT_EVALUATION_UNIVERSE = (
    DEFAULT_OUTPUT_ROOT
    / "evaluation_universes/dd1f4f30d7795a3dc4d802f51d23f52f8cd3fa0a17d01f2c57f71713011120e3.json"
)
DEFAULT_FORMAL_PROTOCOL = (
    PROJECT_ROOT
    / "research/institutional_evaluation/protocols/formal_evaluation_gate_v1.json"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze-plan", action="store_true")
    mode.add_argument("--execute-plan", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--dataset-manifest", type=Path, default=DEFAULT_PRICE_DATASET_MANIFEST
    )
    parser.add_argument("--dataset-plan", type=Path, default=DEFAULT_PRICE_DATASET_PLAN)
    parser.add_argument(
        "--candidate-series-plan", type=Path, default=DEFAULT_CANDIDATE_SERIES_PLAN
    )
    parser.add_argument("--candidate-series", type=Path, default=DEFAULT_CANDIDATE_SERIES)
    parser.add_argument("--coverage-audit", type=Path, default=DEFAULT_COVERAGE_AUDIT)
    parser.add_argument(
        "--evaluation-universe", type=Path, default=DEFAULT_EVALUATION_UNIVERSE
    )
    parser.add_argument("--formal-protocol", type=Path, default=DEFAULT_FORMAL_PROTOCOL)
    args = parser.parse_args(argv)

    try:
        dependencies = _load_dependencies(args)
        expected_plan = build_offline_ab_plan(**dependencies)
        verify_offline_ab_plan(expected_plan, **dependencies)
        if args.freeze_plan:
            path, created = publish_content_addressed_json(
                args.output_root,
                category="diagnostic_plans",
                payload=expected_plan,
            )
            print(
                f"status={'PUBLISHED' if created else 'IDEMPOTENT_REPLAY'} "
                f"plan_digest={expected_plan['artifact_digest']} "
                f"expected_bars={expected_plan['bar_view']['expected_bar_count']} "
                f"target_sessions={expected_plan['membership']['target_session_count']} "
                f"path={path}"
            )
            return 0

        assert args.execute_plan is not None
        frozen_plan = load_canonical_artifact(args.execute_plan)
        verify_offline_ab_plan(frozen_plan, **dependencies)
        if frozen_plan != expected_plan:
            raise InstitutionalMvpDiagnosticError(
                "execution plan differs from current exact reconstruction"
            )
        result, result_path, created = _execute(
            plan=frozen_plan,
            universe=dependencies["evaluation_universe"],
            dataset_root=args.dataset_manifest.parent.parent,
            output_root=args.output_root,
        )
    except (
        InstitutionalMvpDiagnosticError,
        InstitutionalMvpSeriesError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"ERROR code=NON_FORMAL_OFFLINE_AB_FAILED type={type(error).__name__}",
            file=sys.stderr,
        )
        return 1

    comparison = result["comparison"]
    print(
        f"status={'PUBLISHED' if created else 'IDEMPOTENT_REPLAY'} "
        f"result_digest={result['artifact_digest']} "
        f"price_trades={result['arms']['price_only']['closed_trade_count']} "
        f"institutional_trades={result['arms']['institutional_filter']['closed_trade_count']} "
        f"expectancy_delta_twd={comparison['expectancy_twd_delta']} "
        f"path={result_path}"
    )
    return 0


def _load_dependencies(args: argparse.Namespace) -> dict[str, object]:
    price_reference = load_price_dataset_reference(
        manifest_path=args.dataset_manifest,
        dataset_plan_path=args.dataset_plan,
    )
    manifest_raw = json.loads(args.dataset_manifest.read_bytes())
    snapshot_raw = json.loads(args.dataset_plan.read_bytes())
    protocol = json.loads(args.formal_protocol.read_bytes())
    if not all(
        isinstance(value, Mapping)
        for value in (manifest_raw, snapshot_raw, protocol)
    ):
        raise ValueError("diagnostic metadata inputs must be JSON objects")
    manifest = DatasetManifest.from_dict(manifest_raw)
    snapshot_plan = FinMindSnapshotPlan.from_dict(snapshot_raw)
    calendar = ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH)
    policy = load_daily_policy()
    series_plan = load_canonical_artifact(args.candidate_series_plan)
    verify_candidate_series_plan(
        series_plan,
        calendar=calendar,
        policy=policy,
        price_dataset_reference=price_reference,
    )
    candidate_series = load_canonical_artifact(args.candidate_series)
    batches = _load_exact_batches(args.output_root, candidate_series)
    verify_candidate_series_manifest(
        candidate_series,
        plan=series_plan,
        batches=batches,
        calendar=calendar,
        policy=policy,
    )
    coverage = load_canonical_artifact(args.coverage_audit)
    universe = load_canonical_artifact(args.evaluation_universe)
    verify_mvp_price_coverage_audit(
        coverage,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=candidate_series,
    )
    verify_mvp_evaluation_universe(
        universe,
        coverage_audit=coverage,
        price_dataset_reference=price_reference,
        snapshot_plan=snapshot_plan,
        candidate_series=candidate_series,
    )
    return {
        "price_dataset_reference": price_reference,
        "dataset_manifest": manifest,
        "snapshot_plan": snapshot_plan,
        "candidate_series": candidate_series,
        "coverage_audit": coverage,
        "evaluation_universe": universe,
        "formal_protocol": protocol,
        "code_identities": source_code_identities(PROJECT_ROOT),
    }


def _execute(
    *,
    plan: Mapping[str, object],
    universe: Mapping[str, object],
    dataset_root: Path,
    output_root: Path,
) -> tuple[Mapping[str, object], Path, bool]:
    catalog = HistoricalDatasetCatalog(dataset_root)
    view = FrozenCatalogBarView(catalog, plan)
    config = build_run_config(plan)
    print(
        f"ARM_START arm=price_only selected_bars={view.total_bar_count}",
        file=sys.stderr,
        flush=True,
    )
    price = HistoricalBacktestEngine().run(
        config=config,
        bars=view.iter_bars(),
        bars_are_ordered=True,
        total_bars=view.total_bar_count,
        terminal_timestamp_by_symbol=view.terminal_timestamp_by_symbol,
        entry_eligibility=price_only_entry_eligibility(plan),
    )
    print(
        f"ARM_COMPLETE arm=price_only trades={len(price.trades)}",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"ARM_START arm=institutional_filter selected_bars={view.total_bar_count}",
        file=sys.stderr,
        flush=True,
    )
    institutional = HistoricalBacktestEngine().run(
        config=config,
        bars=view.iter_bars(),
        bars_are_ordered=True,
        total_bars=view.total_bar_count,
        terminal_timestamp_by_symbol=view.terminal_timestamp_by_symbol,
        entry_eligibility=institutional_entry_eligibility(plan, universe),
    )
    print(
        f"ARM_COMPLETE arm=institutional_filter trades={len(institutional.trades)}",
        file=sys.stderr,
        flush=True,
    )
    result = build_offline_ab_result(
        plan=plan,
        evaluation_universe=universe,
        price_only_result=price,
        institutional_result=institutional,
    )
    verify_offline_ab_result(
        result,
        plan=plan,
        evaluation_universe=universe,
        price_only_result=price,
        institutional_result=institutional,
    )
    path, created = publish_content_addressed_json(
        output_root,
        category="diagnostic_results",
        payload=result,
    )
    return result, path, created


if __name__ == "__main__":
    raise SystemExit(main())
