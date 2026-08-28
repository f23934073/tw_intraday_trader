#!/usr/bin/env python3
"""Classify a frozen git porcelain manifest for HYG-001."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from collections import defaultdict
from pathlib import Path


T1_PATHS = {
    "backtest/atomic_benchmark/application.py",
    "backtest/atomic_benchmark/preflight.py",
    "backtest/migrations/018_r6_dynamic_entry_reserve.sql",
    "scripts/apply_r6_g3_migration_018.py",
    "scripts/audit_atomic_entry_benchmark_eligibility.py",
    "scripts/preflight_atomic_entry_benchmark.py",
    "scripts/supervise_atomic_entry_benchmark_preflight.py",
    "tests/test_apply_r6_g3_migration_018.py",
    "tests/test_atomic_entry_benchmark_full_dataset.py",
    "tests/test_atomic_entry_benchmark_postgres.py",
    "tests/test_audit_atomic_entry_benchmark_eligibility.py",
    "tests/test_supervise_atomic_entry_benchmark_preflight.py",
    "architecture/r6_g3_dynamic_entry_reserve_amendment_a2.md",
}

T2_PATHS = {
    "backtest/finmind_snapshot.py",
    "backtest/finmind_selection_bundle.py",
    "backtest/finmind_source_repair.py",
    "backtest/fugle_source_repair.py",
    "scripts/build_finmind_phase82_selection_bundle.py",
    "scripts/capture_fugle_source_repair_candidate.py",
    "scripts/derive_fugle_source_repair_candidate.py",
    "scripts/download_finmind_sponsor_history.py",
    "scripts/manage_finmind_source_repair.py",
    "scripts/verify_finmind_selection_bundle.py",
    "tests/test_finmind_selection_bundle.py",
    "tests/test_finmind_source_repair.py",
    "tests/test_finmind_sponsor_history.py",
    "tests/test_fugle_source_repair.py",
    "docs/",
    "docs/finmind_source_repair.md",
}

T3_PATHS = {
    "market_data/late_delivery_capture.py",
    "market_data/late_delivery_capture_cli.py",
    "market_data/late_delivery_daily_cli.py",
    "market_data/late_delivery_evidence.py",
    "scripts/launchd/com.stevehuang.tw-intraday-trader.d-health-late-001-open-20260828.plist",
    "scripts/run_one_shot_late_delivery_open.py",
    "tests/test_late_delivery_capture.py",
    "tests/test_late_delivery_evidence.py",
    "tests/test_run_one_shot_late_delivery_open.py",
}

T4_PATHS = {
    "market_data/shioaji_momentum_stream.py",
    "tests/test_shioaji_momentum_stream.py",
}

T5_PATHS = {
    "scripts/launchd/com.stevehuang.tw-intraday-trader.freshness-calibration.plist",
    "tests/test_freshness_calibration_schedule.py",
}

T6_PATHS = {
    "tests/test_backtest_sqlite_postgres_migration.py",
    "tests/test_strategy_migrations.py",
}

T7_PATHS = {
    ".gitignore",
    "WORKFLOW.md",
    "architecture/hygiene_plans_index.md",
    "architecture/institutional_module_boundary_implementation_plan.md",
    "architecture/local_paper_kill_switch_durability_implementation_plan.md",
    "architecture/local_paper_tax_slippage_implementation_plan.md",
    "architecture/planning_log_single_source_implementation_plan.md",
    "architecture/price_coverage_source_digest_drift_implementation_plan.md",
    "architecture/r6_g3_dynamic_entry_reserve_amendment_a2.md",
    "architecture/static_analysis_ci_implementation_plan.md",
    "architecture/working_tree_commit_packaging_implementation_plan.md",
    "findings.md",
    "progress.md",
    "research/working_tree_triage_2026-08-28.md",
    "research/working_tree_triage_2026-08-28.raw.txt",
    "scripts/triage_working_tree.py",
    "task_plan.md",
}

T9_PATHS = {
    "data/",
    "tests/test_price_coverage_scan_segment_manifest.py",
}


def classify(path: str) -> str:
    if path in T1_PATHS:
        return "T1"
    if path in T2_PATHS:
        return "T2"
    if path in T3_PATHS:
        return "T3"
    if path in T4_PATHS:
        return "T4"
    if path in T5_PATHS:
        return "T5"
    if path in T6_PATHS:
        return "T6"
    if path in T7_PATHS or path.startswith(".planning/"):
        return "T7"
    if path in T9_PATHS:
        return "T9"

    json_prefixes = (
        "research/captures/freshness_broker_account/",
        "research/captures/freshness_quote/",
        "research/freshness_calibration/broker_account_scheduled_runs/",
        "research/freshness_calibration/scheduled_runs/",
    )
    if path.startswith(json_prefixes) and path.endswith(".json"):
        return "T8"
    if path.startswith("research/freshness_calibration/reviews/") and path.endswith(
        ".md"
    ):
        return "T8"
    if path.startswith(
        (
            "records/market_events/2026-08-25/",
            "records/market_events/2026-08-26/",
            "records/market_events/2026-08-27/",
            "records/market_events/2026-08-28/",
            "research/finmind_source_repairs/",
            "research/late_delivery_evidence/runtime/",
            "research/trade_management_shadow/session_input_drafts/",
        )
    ):
        return "T8"
    if path == "research/finmind_source_repair_9960_20260320_tpex_daily_v1.json":
        return "T8"
    if path.startswith("research/trade_management_shadow/premarket_2026082") and (
        path.endswith(".json") or path.endswith(".json.sha256")
    ):
        return "T8"
    return "UNCLASSIFIED"


def live_manifest() -> bytes:
    return subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-at", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--head", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = args.manifest.read_bytes() if args.manifest else live_manifest()
    digest = hashlib.sha256(manifest).hexdigest()
    groups: dict[str, list[str]] = defaultdict(list)
    tracked_count = 0
    untracked_count = 0

    for raw_line in manifest.decode("utf-8").splitlines():
        if len(raw_line) < 4:
            groups["UNCLASSIFIED"].append(raw_line)
            continue
        status = raw_line[:2]
        path = raw_line[3:]
        groups[classify(path)].append(raw_line)
        if status == "??":
            untracked_count += 1
        else:
            tracked_count += 1

    lines = [
        "# HYG-001 Working Tree Triage — 2026-08-28",
        "",
        "## Frozen baseline",
        "",
        f"- Snapshot timestamp: `{args.snapshot_at}`",
        f"- Branch: `{args.branch}`",
        f"- HEAD: `{args.head}`",
        f"- Manifest SHA-256: `{digest}`",
        f"- Tracked/modified entries: `{tracked_count}`",
        f"- Untracked entries: `{untracked_count}`",
        f"- Total entries: `{tracked_count + untracked_count}`",
        "- PCD-001 handoff: `tests/test_price_coverage_scan_segment_manifest.py` remains T9 and must stay unstaged.",
        "",
    ]

    for group in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "UNCLASSIFIED"):
        entries = sorted(groups.get(group, []))
        lines.extend([f"## {group} ({len(entries)})", "", "```text"])
        lines.extend(entries)
        lines.extend(["```", ""])

    lines.extend(
        [
            "## Execution ledger",
            "",
            "- Backup: pending verification record.",
            "- Commits: pending.",
            "- Deferred groups: none recorded yet.",
            "- T8 retention note: scheduled evidence follows the existing repository convention; a separate owner decision is still needed for long-term retention policy.",
        ]
    )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 2 if groups.get("UNCLASSIFIED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
