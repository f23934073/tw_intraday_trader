"""Plan or materialize one consistent FinMind history snapshot.

PostgreSQL registration and default binding remain disabled until later gates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.dataset import DatasetManifest, HistoricalDatasetCatalog  # noqa: E402
from backtest.finmind_history import TAIPEI  # noqa: E402
from backtest.finmind_snapshot import (  # noqa: E402
    FinMindSemanticSnapshotReader,
    FinMindSnapshotPlan,
    load_snapshot_plan,
    save_snapshot_plan,
    verify_snapshot_plan_handoff,
)


def create_snapshot_plan(
    *,
    source: Path,
    stock_info_raw: Path,
    snapshot_out: Path,
    plan_out: Path,
    actor: str,
    planned_at: datetime | None = None,
) -> FinMindSnapshotPlan:
    """Create one copy/plan pair and remove the copy if planning fails."""

    source = source.resolve()
    stock_info_raw = stock_info_raw.resolve()
    snapshot_out = snapshot_out.resolve()
    plan_out = plan_out.resolve()
    if snapshot_out.exists():
        raise FileExistsError(snapshot_out)
    if plan_out.exists():
        raise FileExistsError(plan_out)
    snapshot_identity: tuple[int, int] | None = None
    plan: FinMindSnapshotPlan | None = None

    def register_snapshot_ownership(path: Path) -> None:
        nonlocal snapshot_identity
        snapshot_stat = path.stat()
        snapshot_identity = (snapshot_stat.st_dev, snapshot_stat.st_ino)

    try:
        FinMindSemanticSnapshotReader.backup_source(
            source,
            snapshot_out,
            on_published=register_snapshot_ownership,
        )
        plan = FinMindSemanticSnapshotReader(snapshot_out).plan(
            stock_info_raw=stock_info_raw,
            actor=actor,
            planned_at=planned_at or datetime.now(TAIPEI),
            source_path=source,
            plan_output_parent=plan_out.parent,
        )
        save_snapshot_plan(plan, plan_out)
    except BaseException:
        if not _is_complete_plan_pair(plan, plan_out) and _has_file_identity(
            snapshot_out, snapshot_identity
        ):
            snapshot_out.unlink(missing_ok=True)
        raise
    if plan is None:
        raise AssertionError("snapshot plan was not created")
    return plan


def _has_file_identity(path: Path, expected: tuple[int, int] | None) -> bool:
    """Return whether path is still the file created by this invocation."""

    if expected is None:
        return False
    try:
        observed = path.stat()
    except FileNotFoundError:
        return False
    return (observed.st_dev, observed.st_ino) == expected


def _is_complete_plan_pair(
    expected: FinMindSnapshotPlan | None,
    plan_path: Path,
) -> bool:
    if expected is None or not plan_path.is_file():
        return False
    try:
        observed = load_snapshot_plan(plan_path)
    except (OSError, ValueError):
        return False
    return observed.to_dict() == expected.to_dict()


def execute_snapshot_plan(
    *,
    plan_file: Path,
    dataset_root: Path,
    snapshot_file: Path | None = None,
    stock_info_raw: Path | None = None,
) -> DatasetManifest:
    """Materialize only the copied files and canonical identity in a saved plan."""

    plan = load_snapshot_plan(Path(plan_file).resolve())
    effective_snapshot = _resolve_execute_path(
        snapshot_file,
        plan.locators,
        "copied_sqlite_path",
    )
    effective_reference = _resolve_execute_path(
        stock_info_raw,
        plan.locators,
        "taiwan_stock_info_raw_path",
    )
    verify_snapshot_plan_handoff(
        plan,
        snapshot_file=effective_snapshot,
        stock_info_raw=effective_reference,
    )

    operation_audit = plan.operation_audit
    recomputed = FinMindSemanticSnapshotReader(effective_snapshot).plan(
        stock_info_raw=effective_reference,
        actor=str(operation_audit.get("actor") or "execute-verifier"),
        planned_at=datetime.fromisoformat(str(operation_audit["planned_at"])),
        plan_output_parent=Path(dataset_root).resolve(),
    )
    if (
        recomputed.identity != plan.identity
        or recomputed.plan_identity_digest != plan.plan_identity_digest
    ):
        raise ValueError("snapshot semantic identity does not match the saved plan")

    identity = plan.identity
    selection = identity["selection"]
    counts = identity["counts"]
    source_contract = identity["source_contract"]
    required_free_bytes = int(
        operation_audit.get("expected_output_size_bytes") or 1
    )
    reader = FinMindSemanticSnapshotReader(effective_snapshot)
    catalog = HistoricalDatasetCatalog(Path(dataset_root).resolve())
    with reader.open_symbol_bar_streams(plan) as streams:
        manifest = catalog.create_finmind_snapshot_dataset(
            dataset_id=str(identity["dataset_id"]),
            symbol_streams=streams,
            created_at=datetime.fromisoformat(str(identity["snapshot_identity_at"])),
            source=str(source_contract["source"]),
            requested_symbols=tuple(
                str(value) for value in selection["included_symbols"]
            ),
            expected_bar_count=int(counts["bar_count"]),
            start_date=str(source_contract["start_date"]),
            end_date=str(source_contract["end_date"]),
            issues=tuple(str(value) for value in identity["issues"]),
            volume_contract=dict(identity["volume_contract"]),
            amount_contract=dict(identity["amount_contract"]),
            source_snapshot_digest=str(identity["source_snapshot_digest"]),
            plan_identity=dict(identity),
            plan_identity_digest=plan.plan_identity_digest,
            required_free_bytes=required_free_bytes,
        )
    verify_snapshot_plan_handoff(
        plan,
        snapshot_file=effective_snapshot,
        stock_info_raw=effective_reference,
    )
    return manifest


def _resolve_execute_path(
    override: Path | None,
    locators: Mapping[str, object],
    field: str,
) -> Path:
    if override is not None:
        return Path(override).resolve()
    if not str(locators.get(field) or "").strip():
        raise ValueError(f"snapshot plan locator is missing: {field}")
    return Path(str(locators[field])).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="建立或封存 FinMind 歷史資料的一致性快照"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--plan",
        action="store_true",
        help="只建立 SQLite online backup 與 snapshot plan；不建立 Dataset",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="依 saved plan 封存 immutable Dataset；不寫 PostgreSQL",
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--stock-info-raw", type=Path)
    parser.add_argument("--snapshot-out", type=Path)
    parser.add_argument("--plan-out", type=Path)
    parser.add_argument("--plan-file", type=Path)
    parser.add_argument("--snapshot-file", type=Path)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path(os.environ.get("BACKTEST_DATA_DIR", "data/backtest")),
    )
    parser.add_argument("--actor", default="local-researcher")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.plan:
        required = (args.source, args.stock_info_raw, args.snapshot_out, args.plan_out)
        if any(value is None for value in required):
            parser.error(
                "--plan requires --source, --stock-info-raw, --snapshot-out, and --plan-out"
            )
        plan = create_snapshot_plan(
            source=args.source,
            stock_info_raw=args.stock_info_raw,
            snapshot_out=args.snapshot_out,
            plan_out=args.plan_out,
            actor=args.actor,
        )
        identity = plan.identity
        counts = identity["counts"]
        output = {
            "bar_count": counts["bar_count"],
            "dataset_id": identity["dataset_id"],
            "excluded_symbol_count": plan.selection_audit["snapshot_counts"][
                "excluded_symbol_count"
            ],
            "included_symbol_count": counts["included_symbol_count"],
            "plan_identity_digest": plan.plan_identity_digest,
            "plan_out": str(args.plan_out.resolve()),
            "snapshot_out": str(args.snapshot_out.resolve()),
            "source_snapshot_digest": identity["source_snapshot_digest"],
        }
    else:
        if args.plan_file is None:
            parser.error("--execute requires --plan-file")
        manifest = execute_snapshot_plan(
            plan_file=args.plan_file,
            dataset_root=args.dataset_root,
            snapshot_file=args.snapshot_file,
            stock_info_raw=args.stock_info_raw,
        )
        output = manifest.to_dict()
    print(json.dumps(output, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
